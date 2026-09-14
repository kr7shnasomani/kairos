"""
Documents router — Layer 2: Immutable Evidence Vault + Layer 3: Perception Engine.
Handles document ingestion into the vault, triggers the extraction pipeline,
and surfaces extraction status and results.
"""

import asyncio
import hashlib
import time
from datetime import UTC, datetime

import shortuuid
import structlog
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from api.config import settings
from api.dependencies import (
    CurrentUserDep,
    ElasticsearchDep,
    Neo4jDep,
    QdrantDep,
    SettingsDep,
    SupabaseDep,
    TemporalDep,
    require_role,
)
from api.models.document import DocumentStatus, ExtractionResult, VaultDocument
from api.services.corpus import is_test_artifact
from api.services.graph import GraphService, entities_from_edges, person_names_from_edges
from api.services.identity import display_name
from api.services.metrics import ingestion_duration
from api.services.ner import NERService
from api.services.pii import PIIService
from api.services.topology import TopologyVerificationService
from api.services.vector_store import VectorStoreService
from workflows.document_pipeline import DocumentIngestionWorkflow

log = structlog.get_logger(__name__)
router = APIRouter()


def _access_tags(current_user: dict, authority_level: int) -> dict:
    """Permission tags stamped onto a vault artifact at ingestion (Layer 2).

    ARCHITECTURE.md L2 specifies six things each artifact receives; this was the missing one.
    The spec says the tags are "derived from the source system's IAM configuration" — Kairos has
    **no external source-system IAM feed** (no SAP/Maximo/DMS identity plane), so deriving them
    from an imaginary one would be fabrication. They are derived instead from the deployment's
    own enforced RBAC, and `derived_from` says so plainly rather than implying an upstream
    authority that does not exist. If an EAM IAM feed is ever connected, that becomes the source
    and `derived_from` changes with it.

    `required_action` is not decorative: it is the actual OPA action that gates document reads
    (`read_documents`), so the tag records the rule the API really enforces rather than a
    parallel scheme that could silently drift from it.

    `site_id` comes from the verified token, never from the request — same rule as `site_scope`.
    """
    return {
        "site_id": current_user.get("site_id") or None,
        "required_action": "read_documents",
        # Authority 1–2 are regulatory/engineering standards, 3–4 controlled operational
        # documents, 5 informational field material. This mirrors the authority hierarchy that
        # already governs retrieval rather than inventing a second classification axis.
        "classification": (
            "regulatory" if authority_level <= 2
            else "controlled" if authority_level <= 4
            else "informational"
        ),
        "ingested_by": current_user.get("user_id", "unknown"),
        "derived_from": "kairos_rbac",
    }


class TopologyElementDecision(BaseModel):
    """One engineer verdict on one extracted P&ID element."""

    element_id: str
    decision: str = Field(description="confirmed | corrected | rejected")
    note: str | None = None


class TopologyVerifyRequest(BaseModel):
    decisions: list[TopologyElementDecision] = Field(min_length=1)


@router.post("/ingest", summary="Ingest a document into the immutable vault", status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    temporal: TemporalDep,
    file: UploadFile = File(...),
    asset_id: str | None = Form(None, description="Canonical asset ID to link this document to"),
    document_type: str = Form(..., description="oem_manual, procedure, inspection_report, ptw, shift_log, regulation"),
    source_system: str = Form("manual_upload"),
    authority_level: int = Form(4, ge=1, le=5, description="1=Regulatory 2=Engineering 3=OEM 4=Procedure 5=Field"),
    occurred_at: str | None = Form(None, description="Source document timestamp ISO8601 (e.g. 2024-01-15T08:30:00Z)"),
) -> dict:
    """
    Ingests a document into the immutable vault (Supabase Storage).

    - Computes SHA-256 before anything touches the file.
    - Duplicate SHA-256 is idempotent: returns the existing document_id immediately.
    - Stores the original artifact byte-for-byte unchanged — no preprocessing before storage.
    - Inserts rows in `documents` and `extraction_jobs`, links to asset if provided.
    - Triggers the durable `DocumentIngestionWorkflow` via Temporal.

    Returns immediately with document_id + job_id. Poll /documents/{document_id}/status.
    """
    _ingest_start = time.monotonic()

    # Abuse guard: reject oversized uploads. Check the declared size first (avoids buffering a
    # huge body into memory), then backstop against the actual bytes read.
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit.")
    file_bytes = await file.read()
    if len(file_bytes) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit.")
    sha256 = hashlib.sha256(file_bytes).hexdigest()

    # Idempotency: same file ingested twice returns the existing record
    existing = await asyncio.to_thread(
        lambda: supabase.table("documents")
        .select("document_id, sha256_hash, status")
        .eq("sha256_hash", sha256)
        .execute()
    )
    if existing.data:
        existing_doc = existing.data[0]
        log.info("ingest.duplicate", sha256=sha256, document_id=existing_doc["document_id"])
        return {
            "status": "duplicate",
            "document_id": existing_doc["document_id"],
            "sha256": sha256,
            "message": "Identical file already exists in the vault.",
        }

    document_id = f"DOC-{shortuuid.uuid()[:12].upper()}"
    storage_path = f"{document_type}/{document_id}/{file.filename}"
    mime_type = file.content_type or "application/octet-stream"
    now = datetime.now(UTC).isoformat()

    # Upload raw bytes — no transformation, no preprocessing (Layer 2 immutability)
    try:
        await asyncio.to_thread(
            lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
                storage_path,
                file_bytes,
                {"content-type": mime_type},
            )
        )
    except Exception as exc:
        log.error("ingest.storage_upload_failed", document_id=document_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Vault storage upload failed: {exc}",
        )

    # Stable authenticated URL — Supabase Storage pattern for private buckets
    vault_url = (
        f"{settings.SUPABASE_URL}/storage/v1/object/authenticated"
        f"/{settings.SUPABASE_STORAGE_BUCKET}/{storage_path}"
    )

    # Insert canonical vault record + job atomically-ish; clean up blob if DB fails
    try:
        await asyncio.to_thread(
            lambda: supabase.table("documents").insert({
                "document_id": document_id,
                "sha256_hash": sha256,
                "file_name": file.filename,
                "file_size_bytes": len(file_bytes),
                "mime_type": mime_type,
                "document_type": document_type,
                "authority_level": authority_level,
                "source_system": source_system,
                "vault_url": vault_url,
                "status": "active",
                "ingested_at": now,
                "ingested_by": current_user.get("user_id", "unknown"),
                "occurred_at": occurred_at,
                "access_tags": _access_tags(current_user, authority_level),
            }).execute()
        )

        job_result = await asyncio.to_thread(
            lambda: supabase.table("extraction_jobs").insert({
                "document_id": document_id,
                "pipeline_stage": "queued",
                "progress_pct": 0,
                "created_at": now,
            }).execute()
        )
    except Exception as exc:
        # Blob is in Storage but DB failed — remove the orphaned blob
        log.error("ingest.db_insert_failed", document_id=document_id, error=str(exc))
        try:
            await asyncio.to_thread(
                lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([storage_path])
            )
        except Exception as cleanup_exc:
            log.error("ingest.orphan_cleanup_failed", storage_path=storage_path, error=str(cleanup_exc))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Vault DB registration failed: {exc}")

    job_id = job_result.data[0]["job_id"]

    # Link to canonical asset if provided
    if asset_id:
        await asyncio.to_thread(
            lambda: supabase.table("document_asset_links").insert({
                "document_id": document_id,
                "asset_id": asset_id,
                "linked_at": now,
            }).execute()
        )

    # Audit trail (fire-and-forget on failure — document is already committed)
    try:
        await asyncio.to_thread(
            lambda: supabase.table("audit_log").insert({
                "action": "document_ingested",
                "entity_type": "document",
                "entity_id": document_id,
                "performed_by": current_user.get("user_id", "unknown"),
                "details": {
                    "sha256": sha256,
                    "document_type": document_type,
                    "authority_level": authority_level,
                    "file_name": file.filename,
                    "asset_id": asset_id,
                    "source_system": source_system,
                },
            }).execute()
        )
    except Exception as exc:
        log.warning("ingest.audit_log_failed", document_id=document_id, error=str(exc))

    # Trigger durable extraction workflow via Temporal
    # Pass vault_path (not file bytes) — activities download from Storage directly
    try:
        await temporal.start_workflow(
            DocumentIngestionWorkflow.run,
            args=[{
                "document_id": document_id,
                "vault_path": storage_path,
                "mime_type": mime_type,
                "asset_id": asset_id,
                "document_type": document_type,
                "authority_level": authority_level,
                "job_id": str(job_id),
            }],
            id=f"ingest-{document_id}",
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )
        workflow_status = "triggered"
    except Exception as exc:
        # Temporal down: vault record and DB row are committed; workflow can be re-triggered
        log.warning("ingest.temporal_unavailable", document_id=document_id, error=str(exc))
        workflow_status = "workflow_pending"

    ingestion_duration.record(time.monotonic() - _ingest_start, {"document_type": document_type})
    log.info(
        "ingest.complete",
        document_id=document_id,
        sha256=sha256,
        job_id=str(job_id),
        workflow=workflow_status,
    )
    return {
        "status": "accepted",
        "document_id": document_id,
        "job_id": str(job_id),
        "sha256": sha256,
        "vault_path": storage_path,
        "workflow": workflow_status,
        "message": f"Document queued for extraction. Poll /documents/{document_id}/status for progress.",
    }


@router.get("/", summary="List vault documents")
async def list_documents(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    asset_id: str | None = None,
    document_type: str | None = None,
    doc_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Lists documents in the vault with optional filtering by asset, type, or status.

    Test-sweep artifacts are excluded — filtered here at the query level, never deleted,
    same predicate `governance.py`/`assets.py` already use (`api/services/corpus.py`). This
    endpoint paginates with `.range()`, so the exclusion has to live in the query itself: a
    page-then-filter-in-Python approach would under-fill pages and understate `total`. On this
    vault the split is stark — 87 of 108 active documents are test artifacts, almost entirely
    `.txt`, so an unfiltered first page shows nothing but test noise ahead of every real PDF
    and image (they only start appearing past position 87). `excluded_test_documents` is
    reported per the project's own rule that a filter must never hide its own effect.

    Excluded ids are resolved via a plain `file_name` scan + `is_test_artifact()` in Python,
    not `.ilike()` — this Supabase project's PostgREST/Cloudflare edge 500s on `ilike`
    entirely (confirmed: fails even as the only filter on an otherwise-plain query, while
    `.eq()`/`.neq()`/`.in_()` all work), so pattern-matching has to happen client-side and the
    exclusion applied as a plain `.not_.in_()` id list instead.
    """
    base_filters_query = supabase.table("documents").select("document_id, file_name")
    query = supabase.table("documents").select("*", count="exact")

    if document_type:
        query = query.eq("document_type", document_type)
        base_filters_query = base_filters_query.eq("document_type", document_type)
    if doc_status:
        query = query.eq("status", doc_status)
        base_filters_query = base_filters_query.eq("status", doc_status)

    if asset_id:
        # Get document IDs linked to this asset first
        link_result = await asyncio.to_thread(
            lambda: supabase.table("document_asset_links")
            .select("document_id")
            .eq("asset_id", asset_id)
            .execute()
        )
        linked_ids = [r["document_id"] for r in (link_result.data or [])]
        if not linked_ids:
            return {"items": [], "total": 0, "limit": limit, "offset": offset, "excluded_test_documents": 0}
        query = query.in_("document_id", linked_ids)
        base_filters_query = base_filters_query.in_("document_id", linked_ids)

    candidates = await asyncio.to_thread(lambda: base_filters_query.execute())
    excluded_ids = [r["document_id"] for r in (candidates.data or []) if is_test_artifact(r.get("file_name"))]
    excluded_test_documents = len(excluded_ids)
    # Chunked, not one `.not_.in_()` with the whole list — Supabase/PostgREST puts every value
    # in the URL (see corpus.py's own `_LOOKUP_CHUNK`), so a long enough exclusion list becomes
    # an over-long query string. 87+ test artifacts already exist on this vault; chunking is
    # what keeps this endpoint correct as that count keeps growing, not just today.
    _CHUNK = 200
    for start in range(0, len(excluded_ids), _CHUNK):
        query = query.not_.in_("document_id", excluded_ids[start : start + _CHUNK])

    result = await asyncio.to_thread(
        lambda: query.order("ingested_at", desc=True).range(offset, offset + limit - 1).execute()
    )
    items = result.data or []
    total = result.count or 0

    # Attach asset_links per document (one batch query, no N+1) so consumers such as
    # the projects portfolio can classify documents by the equipment class of their
    # linked assets. Without this the list omits asset_links and everything reads as
    # "Unclassified".
    doc_ids = [d["document_id"] for d in items]
    if doc_ids:
        links_result = await asyncio.to_thread(
            lambda: supabase.table("document_asset_links")
            .select("document_id, asset_id")
            .in_("document_id", doc_ids)
            .execute()
        )
        links_by_doc: dict[str, list[str]] = {}
        for row in (links_result.data or []):
            links_by_doc.setdefault(row["document_id"], []).append(row["asset_id"])
        for d in items:
            d["asset_links"] = links_by_doc.get(d["document_id"], [])

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "excluded_test_documents": excluded_test_documents,
    }


@router.get("/{document_id}/status", summary="Poll extraction pipeline status")
async def get_extraction_status(
    document_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> DocumentStatus:
    """Returns the current status of the OCR → NER → graph extraction pipeline for a document."""
    result = await asyncio.to_thread(
        lambda: supabase.table("extraction_jobs")
        .select("*")
        .eq("document_id", document_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No extraction job found for document '{document_id}'",
        )
    row = result.data[0]
    return DocumentStatus(
        document_id=document_id,
        pipeline_stage=row["pipeline_stage"],
        progress_percent=row["progress_pct"],
        ocr_confidence=row.get("ocr_confidence"),
        ner_entity_count=row.get("entity_count"),
        graph_edges_created=row.get("graph_edges"),
        review_items_pending=row.get("review_pending", 0),
        error=row.get("error"),
        updated_at=datetime.fromisoformat(row["created_at"]) if row.get("created_at") else datetime.now(UTC),
    )


@router.get("/{document_id}/extraction", summary="Get extraction results (entities, facts)")
async def get_extraction_results(
    document_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    driver: Neo4jDep,
) -> ExtractionResult:
    """
    Returns structured extraction results: extracted entities, confidence scores,
    graph edges created, and items routed to human review.

    Entities are read back from what the pipeline actually wrote — the graph edges carrying this
    `document_id` — rather than re-running NER, so the view shows exactly what entered the graph.
    Low-confidence entities never reach the graph; they are the quarantine rows whose
    `session_context.document_id` names this document.
    """
    doc_result = await asyncio.to_thread(
        lambda: supabase.table("documents").select("document_id, mime_type").eq("document_id", document_id).execute()
    )
    if not doc_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found")

    try:
        blast = await GraphService(driver).get_blast_radius(document_id)
        entities = entities_from_edges(document_id, blast.get("affected", []))
    except Exception as exc:  # noqa: BLE001 — a graph outage degrades to "no entities", not a 500
        log.warning("document.extraction_graph_unavailable", document_id=document_id, error=str(exc))
        entities = []

    review_result = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items")
        .select("item_id, content, review_status, submitted_at, session_context")
        .eq("session_context->>document_id", document_id)
        .order("submitted_at", desc=True)
        .limit(100)
        .execute()
    )
    review_items = [
        {
            "item_id": r.get("item_id"),
            "content": r.get("content"),
            "review_status": r.get("review_status"),
            "submitted_at": r.get("submitted_at"),
        }
        for r in (review_result.data or [])
    ]

    job_result = await asyncio.to_thread(
        lambda: supabase.table("extraction_jobs")
        .select("entity_count, graph_edges")
        .eq("document_id", document_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    job = job_result.data[0] if job_result.data else {}

    # Derived from the stored mime type rather than persisted separately — the vault already
    # records exactly which path the document had to take, so a new column would duplicate it.
    mime = (doc_result.data[0] or {}).get("mime_type", "") if doc_result.data else ""
    went_through_ocr = mime.startswith("image/") or mime == "application/pdf"

    return ExtractionResult(
        document_id=document_id,
        extraction_model=f"{settings.NVIDIA_NIM_NER_MODEL} + {settings.NVIDIA_NIM_OCR_MODEL}",
        entities=entities,
        graph_edges_created=job.get("graph_edges") or 0,
        vector_chunks_indexed=0,
        review_items=review_items,
        extraction_path="ocr" if mime.startswith("image/") else "native",
        # Only images can carry handwriting. A digital PDF has a text layer; a scanned one is an
        # image and is caught by the branch above.
        handwriting_suspect=mime.startswith("image/") and went_through_ocr,
    )


def vault_storage_path(vault_url: str | None) -> str | None:
    """The Storage object path inside the vault bucket, recovered from a document's stored `vault_url`.

    The documents table keeps only the authenticated URL, so this is the one place that path is parsed.
    """
    marker = f"/object/authenticated/{settings.SUPABASE_STORAGE_BUCKET}/"
    idx = (vault_url or "").find(marker)
    return vault_url[idx + len(marker):] if idx != -1 and vault_url else None


def release_workflow_params(doc: dict, asset_id: str | None, job_id: str, reviewed_by: str) -> dict:
    """Workflow params to re-run extraction on a document a human released from the OCR gate.

    Same shape as ingestion, plus `ocr_reviewed_by`, which tells `run_ocr` that a person has looked at
    the scan and accepted it — the gate is recorded as overridden rather than silently skipped.
    Raises ValueError when the vault path cannot be recovered: re-running without the artifact would
    extract nothing.
    """
    vault_path = vault_storage_path(doc.get("vault_url"))
    if not vault_path:
        raise ValueError(f"Vault storage path unavailable for {doc.get('document_id')}")
    return {
        "document_id": doc["document_id"],
        "vault_path": vault_path,
        "mime_type": doc.get("mime_type") or "application/octet-stream",
        "asset_id": asset_id,
        "document_type": doc.get("document_type") or "unknown",
        "authority_level": doc.get("authority_level") or 4,
        "job_id": job_id,
        "ocr_reviewed_by": reviewed_by,
    }


class OcrReviewDecision(BaseModel):
    note: str | None = Field(None, max_length=1000, description="Why the reviewer released or rejected the scan")


async def _held_job(supabase, document_id: str) -> dict:
    """The document's latest extraction job, which must be the one the OCR gate stopped (409 otherwise)."""
    result = await asyncio.to_thread(
        lambda: supabase.table("extraction_jobs").select("*").eq("document_id", document_id)
        .order("created_at", desc=True).limit(1).execute()
    )
    job = result.data[0] if result.data else None
    if not job or job.get("pipeline_stage") != "review_required":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document '{document_id}' is not held for OCR review.",
        )
    return job


async def _audit(supabase, action: str, document_id: str, user_id: str, details: dict) -> None:
    try:
        await asyncio.to_thread(
            lambda: supabase.table("audit_log").insert({
                "action": action, "entity_type": "document", "entity_id": document_id,
                "performed_by": user_id, "details": details,
            }).execute()
        )
    except Exception as exc:  # noqa: BLE001 — the decision itself is already committed
        log.warning("document.ocr_review_audit_failed", document_id=document_id, action=action, error=str(exc))


@router.post("/{document_id}/ocr-review/release", summary="Release a document held by the OCR gate")
async def release_held_document(
    document_id: str,
    supabase: SupabaseDep,
    temporal: TemporalDep,
    decision: OcrReviewDecision | None = None,
    current_user: dict = Depends(require_role("reliability", "admin")),
) -> dict:
    """
    A reviewer has looked at the original scan and judged it legible: re-run extraction past the gate.

    Human-only, like quarantine promotion (reliability/admin). Extracted facts still enter the graph as
    `unverified` edges and low-confidence entities still quarantine, so releasing the scan does not
    verify what is read from it. The previous job row is kept; the release gets a new one.
    """
    held = await _held_job(supabase, document_id)
    reviewer = current_user.get("user_id", "unknown")

    doc_result = await asyncio.to_thread(
        lambda: supabase.table("documents")
        .select("document_id, vault_url, mime_type, document_type, authority_level")
        .eq("document_id", document_id).limit(1).execute()
    )
    if not doc_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found")
    link_result = await asyncio.to_thread(
        lambda: supabase.table("document_asset_links").select("asset_id").eq("document_id", document_id).limit(1).execute()
    )
    asset_id = link_result.data[0]["asset_id"] if link_result.data else None

    try:
        params = release_workflow_params(doc_result.data[0], asset_id, "pending", reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    job_result = await asyncio.to_thread(
        lambda: supabase.table("extraction_jobs").insert({
            "document_id": document_id, "pipeline_stage": "queued", "progress_pct": 0,
            "created_at": datetime.now(UTC).isoformat(),
        }).execute()
    )
    job_id = str(job_result.data[0]["job_id"])
    params["job_id"] = job_id

    try:
        await temporal.start_workflow(
            DocumentIngestionWorkflow.run,
            args=[params],
            id=f"ocr-release-{document_id}-{shortuuid.uuid()[:8]}",
            task_queue=settings.TEMPORAL_TASK_QUEUE,
        )
    except Exception as exc:
        log.error("document.ocr_release_workflow_failed", document_id=document_id, error=str(exc))
        await asyncio.to_thread(
            lambda: supabase.table("extraction_jobs").update({
                "pipeline_stage": "review_required", "error": held.get("error"), "review_pending": 1,
            }).eq("job_id", job_id).execute()
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The extraction workflow could not be started — the document is still held. Try again.",
        ) from exc

    await _audit(supabase, "ocr_review_released", document_id, reviewer, {
        "note": (decision.note if decision else None), "held_job_id": held.get("job_id"),
        "gate_reason": held.get("error"), "release_job_id": job_id,
    })
    log.info("document.ocr_review_released", document_id=document_id, reviewer=reviewer, job_id=job_id)
    return {"status": "released", "document_id": document_id, "job_id": job_id}


@router.post("/{document_id}/ocr-review/reject", summary="Reject a document held by the OCR gate")
async def reject_held_document(
    document_id: str,
    supabase: SupabaseDep,
    decision: OcrReviewDecision | None = None,
    current_user: dict = Depends(require_role("reliability", "admin")),
) -> dict:
    """
    A reviewer judged the scan unreadable: nothing is extracted from it, ever, from this job.

    The vault artifact is never deleted (immutability) — the job is closed as `rejected` so it leaves the
    review state, and a legible rescan is ingested as a new document (and may supersede this one).
    """
    held = await _held_job(supabase, document_id)
    reviewer = current_user.get("user_id", "unknown")
    note = (decision.note if decision else None) or "scan unreadable"
    await asyncio.to_thread(
        lambda: supabase.table("extraction_jobs").update({
            "pipeline_stage": "rejected", "review_pending": 0,
            "error": f"Rejected at OCR review: {note}",
            "completed_at": datetime.now(UTC).isoformat(),
        }).eq("job_id", held["job_id"]).execute()
    )
    await _audit(supabase, "ocr_review_rejected", document_id, reviewer, {
        "note": note, "job_id": held.get("job_id"), "gate_reason": held.get("error"),
    })
    log.info("document.ocr_review_rejected", document_id=document_id, reviewer=reviewer)
    return {"status": "rejected", "document_id": document_id}


@router.get("/{document_id}/artifact-url", summary="Get a short-lived signed URL to open the vault artifact")
async def get_artifact_url(
    document_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """
    Private vault buckets can't be opened by a plain browser navigation — the stored
    `/object/authenticated/` URL requires an Authorization header a browser can't send
    (Supabase returns 400 "headers must have required property 'authorization'"). Return
    a short-lived signed URL instead: the token rides in the query string, so `window.open`
    works without a header.
    """
    doc_result = await asyncio.to_thread(
        lambda: supabase.table("documents")
        .select("vault_url")
        .eq("document_id", document_id)
        .limit(1)
        .execute()
    )
    if not doc_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found")

    storage_path = vault_storage_path(doc_result.data[0].get("vault_url"))
    if not storage_path:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Artifact storage path unavailable")

    try:
        signed = await asyncio.to_thread(
            lambda: supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(storage_path, 3600)
        )
    except Exception as exc:
        log.error("artifact.sign_failed", document_id=document_id, error=str(exc))
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not sign artifact URL: {exc}")

    # supabase-py has returned this key as signedURL / signedUrl / signed_url across versions.
    signed_url = signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url")
    if not signed_url:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Signed URL missing from storage response")
    if signed_url.startswith("/"):
        signed_url = f"{settings.SUPABASE_URL}{signed_url}"
    return {"signed_url": signed_url, "expires_in": 3600}


@router.get("/{document_id}/topology", summary="Get extracted P&ID topology for engineer verification")
async def get_document_topology(
    document_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """
    Returns the topology JSON extracted from a pid_drawing document.
    All elements are unverified — engineer must confirm element-by-element before canonical promotion.
    """
    result = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items")
        .select("session_context, item_id, submitted_at")
        .eq("content", f"PID_TOPOLOGY_MANIFEST:{document_id}")
        .eq("input_type", "deviation_flag")
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No P&ID topology found for document '{document_id}'. "
                   "Ensure it was ingested with document_type='pid_drawing'.",
        )

    ctx = result.data[0]["session_context"]
    svc = TopologyVerificationService(supabase)
    statuses = await svc.element_statuses(document_id)
    summary = svc.summarize(statuses)
    return {
        "document_id": document_id,
        "manifest_item_id": str(result.data[0]["item_id"]),
        # Derived from what reviewers actually did, element by element. This was previously a
        # hardcoded "unverified" literal, so every element rendered identically forever.
        **summary,
        "elements": statuses,
        "topology": ctx.get("topology", {}),
        # "vision_model" = real extraction; "demo_fixture" = fell back (show a demo chip).
        "topology_source": ctx.get("topology_source", "demo_fixture"),
        "extracted_at": result.data[0]["submitted_at"],
    }


@router.post("/{document_id}/topology/verify", summary="Engineer verification of P&ID topology elements")
async def verify_document_topology(
    document_id: str,
    payload: TopologyVerifyRequest,
    supabase: SupabaseDep,
    driver: Neo4jDep,
    current_user: dict = Depends(require_role("engineer", "reliability", "admin")),
) -> dict:
    """
    Records element-by-element engineer verification and promotes each confirmed element's
    existing graph edge from `unverified` to `verified`.

    This is the gate the architecture calls non-negotiable regardless of model accuracy: the
    perception engine produces *candidate* topology, and a qualified engineer decides, element by
    element, what becomes canonical. Safety-critical groups (isolation boundaries, instrumentation
    loops) must be fully confirmed before `canonical_ready` turns true.
    """
    svc = TopologyVerificationService(supabase, GraphService(driver))
    result = await svc.verify_elements(
        document_id=document_id,
        decisions=[d.model_dump() for d in payload.decisions],
        reviewer_id=current_user.get("user_id", ""),
    )
    if not result["applied"] and result["unknown_elements"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No decision applied — unknown element ids or decisions: {result['unknown_elements']}",
        )
    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "topology_elements_verified",
            "entity_type": "document",
            "entity_id": document_id,
            "performed_by": current_user.get("user_id", ""),
            "details": {
                "applied": result["applied"],
                "verification_status": result["verification_status"],
                "canonical_ready": result["canonical_ready"],
            },
        }).execute()
    )
    return result


@router.get("/{document_id}", summary="Get vault document metadata")
async def get_document(
    document_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> VaultDocument:
    """Returns the vault metadata for a document including SHA-256 hash, version chain, and status."""
    result = await asyncio.to_thread(
        lambda: supabase.table("documents").select("*").eq("document_id", document_id).execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found in vault",
        )
    doc = result.data[0]

    links_result = await asyncio.to_thread(
        lambda: supabase.table("document_asset_links")
        .select("asset_id")
        .eq("document_id", document_id)
        .execute()
    )
    asset_links = [r["asset_id"] for r in (links_result.data or [])]

    # `ingested_by` is the uploader's user id, which the detail page printed raw
    # ("3m ago · ff28c093-…"). Resolve a readable name; loaders and connectors write non-UUID ids
    # that are not auth users, so a failed lookup keeps the id rather than failing the read.
    ingested_by_name = await display_name(supabase, doc["ingested_by"])

    return VaultDocument(
        document_id=doc["document_id"],
        sha256_hash=doc["sha256_hash"],
        file_name=doc["file_name"],
        file_size_bytes=doc["file_size_bytes"],
        mime_type=doc["mime_type"],
        document_type=doc["document_type"],
        authority_level=doc["authority_level"],
        source_system=doc["source_system"],
        vault_url=doc.get("vault_url"),
        ingested_at=datetime.fromisoformat(doc["ingested_at"]),
        ingested_by=doc["ingested_by"],
        ingested_by_name=ingested_by_name,
        status=doc["status"],
        version_chain=doc.get("version_chain"),
        asset_links=asset_links,
        # Was hardcoded `[]` — the field existed on the response model and was never populated
        # from anything, so the artifact always reported no access tags.
        access_tags=doc.get("access_tags") or {},
    )


@router.get("/{document_id}/redacted", summary="Export a document's text with PII redacted (DPDP)")
async def get_redacted_document(
    document_id: str,
    current_user: CurrentUserDep,
    es: ElasticsearchDep,
    supabase: SupabaseDep,
    driver: Neo4jDep,
) -> dict:
    """
    Returns the document's extracted text with personal identifiers masked — the
    DPDP Act 2023 export boundary for cross-site knowledge sharing.

    Names come from the Person nodes the pipeline already linked to this document
    (`MENTIONS_PERSON`), which is the same NER output computed once at ingestion. Re-running
    NER here took up to two minutes per export; it is kept only as the fallback for a document
    that never reached the graph. Structured identifiers (email, phone, Aadhaar, PAN,
    employee/shift IDs) are matched by pattern. The vault copy is never modified.
    """
    result = await es.search(
        index=settings.ELASTICSEARCH_INDEX_DOCUMENTS,
        body={"query": {"term": {"document_id": document_id}}, "size": 1},
    )
    hits = result.get("hits", {}).get("hits", [])
    if not hits:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No indexed text for document '{document_id}' — it may still be in extraction.",
        )

    source = hits[0].get("_source", {})
    text = source.get("content") or ""

    affected: list[dict] | None
    try:
        affected = (await GraphService(driver).get_blast_radius(document_id)).get("affected", [])
    except Exception as exc:  # noqa: BLE001 — fall back to live NER rather than fail the export
        log.warning("document.redaction_graph_unavailable", document_id=document_id, error=str(exc))
        affected = None
    if affected:
        person_names = person_names_from_edges(affected)
    else:
        ner_result = await NERService().extract_entities(text) if text else {"entities": []}
        person_names = [
            e["text"] for e in ner_result.get("entities", []) if e.get("entity_type") == "PERSON"
        ]

    redaction = PIIService().redact(text, person_names)

    log.info(
        "document.redacted_export",
        document_id=document_id,
        performed_by=current_user.get("user_id", "unknown"),
        pii_found=redaction["pii_found"],
        counts=redaction["counts"],
    )

    # ARCHITECTURE.md requires redaction operations to be "logged and auditable" — a
    # structlog line alone is not auditable, so every export lands in audit_log with the
    # PII type counts. Counts only: never the matched values, or the audit trail would
    # itself become the PII leak.
    try:
        await asyncio.to_thread(
            lambda: supabase.table("audit_log").insert({
                "action": "pii_redacted_export",
                "entity_type": "document",
                "entity_id": document_id,
                "performed_by": current_user.get("user_id", "unknown"),
                "details": {
                    "pii_found": redaction["pii_found"],
                    "pii_counts": redaction["counts"],
                    "pii_span_count": len(redaction["spans"]),
                    "basis": "DPDP Act 2023 export boundary",
                },
            }).execute()
        )
    except Exception as exc:
        log.warning("document.redaction_audit_failed", document_id=document_id, error=str(exc))

    return {
        "document_id": document_id,
        "document_type": source.get("document_type"),
        "redacted_text": redaction["redacted_text"],
        "pii_found": redaction["pii_found"],
        "pii_counts": redaction["counts"],
        "pii_span_count": len(redaction["spans"]),
        "note": "DPDP Act 2023 export boundary. Vault original is unmodified and retains full text.",
    }


@router.post("/{document_id}/supersede", summary="Mark a document as superseded by a newer version")
async def supersede_document(
    document_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    driver: Neo4jDep,
    es: ElasticsearchDep,
    qdrant: QdrantDep,
    settings_dep: SettingsDep,
    new_document_id: str = Body(..., embed=True, description="document_id of the replacement document"),
) -> dict:
    """
    Closes the validity window on the old document and links it to the new version.
    The old artifact is NEVER deleted — immutability is non-negotiable.

    Side effects:
    - All Neo4j edges referencing this document have their valid_to window closed.
    - The ES document and every Qdrant chunk are flagged `status: superseded`, so the old
      version stops surfacing in default retrieval (ARCHITECTURE.md §8). Neither is deleted —
      a time-travel query still has to reach them.
    - Blast-radius analysis is computed and returned.
    - If any affected edge carried authority_level <= 3 (OEM/Engineering/Regulatory),
      a MoC draft is created in moc_items for engineering review.
    """
    # Verify both documents exist
    old_result = await asyncio.to_thread(
        lambda: supabase.table("documents")
        .select("document_id, status, authority_level")
        .eq("document_id", document_id)
        .execute()
    )
    if not old_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{document_id}' not found")
    if old_result.data[0]["status"] == "superseded":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document '{document_id}' is already superseded.",
        )

    new_result = await asyncio.to_thread(
        lambda: supabase.table("documents")
        .select("document_id, status")
        .eq("document_id", new_document_id)
        .execute()
    )
    if not new_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replacement document '{new_document_id}' not found in vault. Ingest it first.",
        )

    now = datetime.now(UTC)

    # Mark old document superseded in Supabase; link to new version via version_chain
    await asyncio.to_thread(
        lambda: supabase.table("documents").update({
            "status": "superseded",
        }).eq("document_id", document_id).execute()
    )
    await asyncio.to_thread(
        lambda: supabase.table("documents").update({
            "version_chain": document_id,
        }).eq("document_id", new_document_id).execute()
    )

    # Close all active Neo4j knowledge edges that reference the old document
    graph = GraphService(driver)
    closed_count = await graph.close_validity_windows_for_document(document_id, now)

    # Propagate the status to the retrieval indexes. Supabase stays the source of truth, so a
    # failure here is reported rather than raised — but it is NOT swallowed: an un-flagged index
    # keeps serving the old version as current, which is the exact §8 failure this closes.
    index_errors: list[str] = []
    try:
        await es.update(
            index=settings_dep.ELASTICSEARCH_INDEX_DOCUMENTS,
            id=document_id,
            body={"doc": {"status": "superseded"}},
        )
    except Exception as exc:
        # Only the store name goes back to the caller; the exception text stays in the log
        # (code scanning py/stack-trace-exposure).
        index_errors.append("elasticsearch")
        log.warning("document.supersede_es_update_failed", document_id=document_id, error=str(exc))

    try:
        await VectorStoreService(qdrant, settings_dep).mark_superseded(
            settings_dep.QDRANT_COLLECTION_DOCUMENTS, document_id
        )
    except Exception as exc:
        index_errors.append("qdrant")
        log.warning("document.supersede_qdrant_update_failed", document_id=document_id, error=str(exc))

    # Blast-radius analysis
    blast = await graph.get_blast_radius(document_id)

    # MoC required if any affected edge had authority_level <= 3 (OEM/Engineering/Regulatory)
    moc_required = any(
        edge.get("edge", {}).get("authority_level", 5) <= 3
        for edge in blast.get("affected", [])
    )
    moc_id = None
    if moc_required:
        moc_id = f"MOC-{shortuuid.uuid()[:8].upper()}"
        await asyncio.to_thread(
            lambda: supabase.table("moc_items").insert({
                "moc_id": moc_id,
                "asset_id": None,
                "description": (
                    f"Document '{document_id}' superseded by '{new_document_id}'. "
                    f"{closed_count} graph edges closed. "
                    f"{blast['affected_count']} downstream facts require review."
                ),
                "conflicting_sources": [{"old": document_id, "new": new_document_id}],
                "blast_radius": blast.get("affected", [])[:50],  # cap payload size
                "status": "draft",
            }).execute()
        )

    # Audit trail
    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "document_superseded",
            "entity_type": "document",
            "entity_id": document_id,
            "performed_by": current_user.get("user_id", "unknown"),
            "details": {
                "new_document_id": new_document_id,
                "edges_closed": closed_count,
                "blast_radius_count": blast["affected_count"],
                "moc_created": moc_id,
            },
        }).execute()
    )

    log.info(
        "document.superseded",
        old=document_id,
        new=new_document_id,
        edges_closed=closed_count,
        blast_radius=blast["affected_count"],
        moc_id=moc_id,
        index_errors=index_errors,
    )
    return {
        "status": "superseded",
        "old_document_id": document_id,
        "new_document_id": new_document_id,
        "edges_closed": closed_count,
        "blast_radius": blast,
        "moc_required": moc_required,
        "moc_id": moc_id,
        # Non-empty means the vault is superseded but an index still serves the old version as
        # current — re-run the supersede once the store is reachable.
        "index_errors": index_errors,
    }
