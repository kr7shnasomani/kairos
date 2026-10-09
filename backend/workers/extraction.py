"""
Extraction workers.

Entity linking is not a Celery task: it runs as the `link_to_graph` Temporal activity inside
`DocumentIngestionWorkflow`.

`run_form_extraction` is live as of 2026-08-23. Its previous stub claimed "form extraction is
handled by Temporal activities", which was **not true** — nothing in `document_pipeline.py`
touched forms, so the docstring was hiding a gap rather than pointing at an implementation.
"""

import asyncio
import sys

sys.path.insert(0, "/app")

import structlog

from workers.celery_app import celery_app

log = structlog.get_logger(__name__)


@celery_app.task(
    queue="extraction",
    name="workers.extraction.run_form_extraction",
    acks_late=True,
    time_limit=300,
    soft_time_limit=240,
)
def run_form_extraction(document_id: str, asset_id: str | None = None) -> dict:
    """Parse a form/checklist into quarantine items. Never writes to the canonical graph.

    Every field lands in Layer 6's one-way gate as unverified field input, because a ticked
    checkbox carries no authority a `KNOWLEDGE_EDGE` could honestly record. Human promotion is
    the only route to canonical — see `api/services/forms.py` for the full reasoning.
    """
    from api.services.http import run_with_client
    return run_with_client(extract_form(document_id, asset_id))


async def extract_form(document_id: str, asset_id: str | None, submitted_by: str = "extraction_pipeline") -> dict:
    """Parse one vault document's form fields into quarantine items. Also called inline by
    `POST /documents/{id}/extract-form`, which is the only thing that triggers it: a person asks."""
    # Lazy imports inside the task body — Celery runs a fresh event loop per task.
    from elasticsearch import AsyncElasticsearch
    from supabase import create_client

    from api.config import Settings
    from api.services.forms import combine_fields, parse_form_fields, parse_form_tables, quarantine_items_for

    settings = Settings()
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)
    try:
        # Document text lives in Elasticsearch; `documents` holds provenance only.
        resp = await es.search(
            index=settings.ELASTICSEARCH_INDEX_DOCUMENTS,
            body={"query": {"term": {"document_id": document_id}},
                  "_source": ["content", "text"], "size": 1},
        )
        hits = resp["hits"]["hits"]
        src = hits[0]["_source"] if hits else {}
        text = src.get("content") or src.get("text") or ""
    finally:
        await es.close()

    if not text.strip():
        log.warning("form_extraction.no_text", document_id=document_id)
        return {"document_id": document_id, "fields": 0, "status": "no_text"}

    # A digital form is a ruled table: read its cells, then add what the line parser finds outside them.
    tables = await _form_tables(supabase, settings, document_id)
    fields = combine_fields(parse_form_tables(tables), parse_form_fields(text), tables)
    if not fields:
        log.info("form_extraction.no_fields", document_id=document_id)
        return {"document_id": document_id, "fields": 0, "status": "no_fields"}

    rows = quarantine_items_for(document_id, fields, asset_id=asset_id, submitted_by=submitted_by)
    await asyncio.to_thread(lambda: supabase.table("quarantine_items").insert(rows).execute())

    log.info("form_extraction.complete", document_id=document_id, fields=len(rows),
             destination="quarantine")
    return {"document_id": document_id, "fields": len(rows), "status": "quarantined"}


async def _form_tables(supabase, settings, document_id: str) -> list:
    """Table cells of the vault PDF behind `document_id`; empty for any other format or on any failure
    (the line parser still runs, so a missing table read costs recall, never the task)."""
    from api.routers.documents import vault_storage_path
    from api.services.forms import extract_tables

    try:
        row = await asyncio.to_thread(
            lambda: supabase.table("documents").select("mime_type, vault_url").eq("document_id", document_id).limit(1).execute()
        )
        doc = (row.data or [{}])[0]
        path = vault_storage_path(doc.get("vault_url"))
        if doc.get("mime_type") != "application/pdf" or not path:
            return []
        pdf = await asyncio.to_thread(lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).download(path))
        return await asyncio.to_thread(extract_tables, pdf)
    except Exception as exc:  # noqa: BLE001
        log.warning("form_extraction.tables_unavailable", document_id=document_id, error=str(exc))
        return []
