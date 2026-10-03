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
    return run_with_client(_run(document_id, asset_id))


async def _run(document_id: str, asset_id: str | None) -> dict:
    # Lazy imports inside the task body — Celery runs a fresh event loop per task.
    from elasticsearch import AsyncElasticsearch
    from supabase import create_client

    from api.config import Settings
    from api.services.forms import parse_form_fields, quarantine_items_for

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

    fields = parse_form_fields(text)
    if not fields:
        log.info("form_extraction.no_fields", document_id=document_id)
        return {"document_id": document_id, "fields": 0, "status": "no_fields"}

    rows = quarantine_items_for(document_id, fields, asset_id=asset_id)
    await asyncio.to_thread(lambda: supabase.table("quarantine_items").insert(rows).execute())

    log.info("form_extraction.complete", document_id=document_id, fields=len(rows),
             destination="quarantine")
    return {"document_id": document_id, "fields": len(rows), "status": "quarantined"}
