"""
Annotations router — Layer 3: Active Learning Annotation Interface.
Operators correct low-confidence NER extractions inline in search results.
Every correction feeds the facility-specific NER training corpus.
"""

import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import CurrentUserDep, SupabaseDep

log = structlog.get_logger(__name__)
router = APIRouter()

# Only these roles can add to the validation corpus, the ground truth the model gate scores against.
# Any role may still record a correction; it just does not become ground truth.
_CORPUS_ROLES = frozenset({"reliability", "admin"})

# Corrections one user may submit per hour. Generous for a person fixing extractions, far below what
# a loop needs to move the circuit breaker's Z-score.
_ANNOTATIONS_PER_HOUR = 60


class AnnotationRequest(BaseModel):
    document_id: str
    entity_text: str
    entity_type: str
    corrected_type: str | None = None
    is_correct: bool
    span_start: int | None = None
    span_end: int | None = None


# =============================================================================
# POST /annotations
# =============================================================================

@router.post("/", summary="Submit NER entity correction", status_code=status.HTTP_201_CREATED)
async def create_annotation(
    payload: AnnotationRequest,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """
    Records an operator correction on a low-confidence NER extraction.
    If is_correct=False, locates the matching quarantine item and lowers its confidence by 0.1.
    Every correction feeds the facility-specific NER training corpus.
    """
    annotated_by = current_user.get("user_id", "unknown")

    # Rate limit and de-duplicate against this user's own earlier annotations. The table already
    # holds everything needed (annotated_by, document_id, entity_text), so no new store is added.
    hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    recent = await asyncio.to_thread(
        lambda: supabase.table("ner_annotations")
        .select("id", count="exact")
        .eq("annotated_by", annotated_by)
        .gte("created_at", hour_ago)
        .execute()
    )
    if (recent.count or 0) >= _ANNOTATIONS_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many corrections in the last hour. Try again later.",
        )
    prior_overrides: list[dict] = []
    if not payload.is_correct:
        prior = await asyncio.to_thread(
            lambda: supabase.table("ner_annotations")
            .select("entity_text")
            .eq("annotated_by", annotated_by)
            .eq("document_id", payload.document_id)
            .eq("is_correct", False)
            .limit(200)
            .execute()
        )
        prior_overrides = prior.data or []

    # Insert annotation row
    result = await asyncio.to_thread(
        lambda: supabase.table("ner_annotations").insert({
            "document_id": payload.document_id,
            "entity_text": payload.entity_text,
            "entity_type": payload.entity_type,
            "corrected_type": payload.corrected_type,
            "is_correct": payload.is_correct,
            "span_start": payload.span_start,
            "span_end": payload.span_end,
            "annotated_by": annotated_by,
        }).execute()
    )
    annotation_id = result.data[0]["id"]

    # Feed validation corpus — confirmed correct entities are verified ground truth, so only the
    # roles that own the model gate can contribute to it.
    if payload.is_correct and current_user.get("role") in _CORPUS_ROLES:
        try:
            await asyncio.to_thread(
                lambda: supabase.table("validation_corpus").insert({
                    "document_id": payload.document_id,
                    "entity_text": payload.entity_text,
                    "entity_type": payload.entity_type,
                    "span_start": payload.span_start,
                    "span_end": payload.span_end,
                    "authority": "annotation_correction",
                    "promoted_by": annotated_by,
                }).execute()
            )
        except Exception as exc:
            log.warning("validation_corpus.insert_failed", document_id=payload.document_id, error=str(exc))

    quarantine_updated = False
    # One user's repeat corrections on the same document add one override, and the same entity
    # lowers its quarantine confidence once: each call used to count as a fresh signal.
    first_for_document = not prior_overrides
    first_for_entity = all(r.get("entity_text") != payload.entity_text for r in prior_overrides)
    if not payload.is_correct:
        # Find matching quarantine item by document_id + entity_text, lower confidence
        q_rows: list[dict] = []
        if first_for_entity:
            q_result = await asyncio.to_thread(
                lambda: supabase.table("quarantine_items")
                .select("item_id, session_context, asset_id")
                .filter("session_context", "cs", json.dumps({"document_id": payload.document_id}))
                .eq("input_type", "deviation_flag")
                .limit(50)
                .execute()
            )
            q_rows = q_result.data or []
        matched_asset_id = None
        for row in q_rows:
            ctx = row.get("session_context") or {}
            entity = ctx.get("entity") or {}
            if entity.get("text") == payload.entity_text:
                new_conf = max(0.0, float(entity.get("confidence", 0.5)) - 0.1)
                entity["confidence"] = new_conf
                ctx["entity"] = entity
                await asyncio.to_thread(
                    lambda iid=row["item_id"], c=ctx: supabase.table("quarantine_items")
                    .update({"session_context": c})
                    .eq("item_id", iid)
                    .execute()
                )
                matched_asset_id = row.get("asset_id")
                quarantine_updated = True
                break

        # Circuit breaker: record annotation correction override (once per user and document)
        if first_for_document:
            from api.services.circuit_breaker import CircuitBreakerService
            cb = CircuitBreakerService(supabase)
            ann_asset_class = "unknown"
            if matched_asset_id:
                asset_row = await asyncio.to_thread(
                    lambda: supabase.table("assets").select("equipment_class").eq("asset_id", matched_asset_id).execute()
                )
                if asset_row.data:
                    ann_asset_class = asset_row.data[0].get("equipment_class") or "unknown"
            await cb.record_override(ann_asset_class, payload.document_id, "annotation_correction")

        # Audit trail
        await asyncio.to_thread(
            lambda: supabase.table("audit_log").insert({
                "action": "ner_annotation_correction",
                "entity_type": "annotation",
                "entity_id": annotation_id,
                "performed_by": annotated_by,
                "details": {
                    "document_id": payload.document_id,
                    "entity_text": payload.entity_text,
                    "entity_type": payload.entity_type,
                    "corrected_type": payload.corrected_type,
                    "quarantine_confidence_updated": quarantine_updated,
                },
            }).execute()
        )

    log.info(
        "annotation.created",
        annotation_id=annotation_id,
        document_id=payload.document_id,
        is_correct=payload.is_correct,
        quarantine_updated=quarantine_updated,
    )
    return {
        "annotation_id": annotation_id,
        "document_id": payload.document_id,
        "is_correct": payload.is_correct,
        "quarantine_confidence_updated": quarantine_updated,
    }


# =============================================================================
# GET /annotations
# =============================================================================

@router.get("/", summary="List annotations for a document")
async def list_annotations(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    document_id: str = Query(..., description="Document ID to fetch annotations for"),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
) -> dict:
    """Returns all NER annotations for a document, ordered by creation time."""
    result = await asyncio.to_thread(
        lambda: supabase.table("ner_annotations")
        .select("*", count="exact")
        .eq("document_id", document_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return {
        "items": result.data or [],
        "total": result.count or 0,
        "document_id": document_id,
        "limit": limit,
        "offset": offset,
    }


# =============================================================================
# GET /annotations/stats
# =============================================================================

@router.get("/stats", summary="Annotation corpus health statistics")
async def annotation_stats(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """
    Returns aggregate annotation counts for the model health dashboard.
    top_corrected_entity_types shows which entity types operators correct most often.
    """
    week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()

    total_result, week_result, incorrect_result = await asyncio.gather(
        asyncio.to_thread(
            lambda: supabase.table("ner_annotations").select("id", count="exact").execute()
        ),
        asyncio.to_thread(
            lambda: supabase.table("ner_annotations")
            .select("id", count="exact")
            .eq("is_correct", False)
            .gte("created_at", week_ago)
            .execute()
        ),
        asyncio.to_thread(
            lambda: supabase.table("ner_annotations")
            .select("corrected_type")
            .eq("is_correct", False)
            .not_.is_("corrected_type", "null")
            .execute()
        ),
    )

    type_counts = Counter(
        row["corrected_type"] for row in (incorrect_result.data or []) if row.get("corrected_type")
    )
    top_types = [
        {"corrected_type": t, "count": c}
        for t, c in type_counts.most_common(5)
    ]

    return {
        "total": total_result.count or 0,
        "corrections_this_week": week_result.count or 0,
        "top_corrected_entity_types": top_types,
    }
