"""
Governance router — Layer 7: Dual-Track Governance and Adjudication Plane.
Manages knowledge conflicts, MoC items, quarantine review, and blast-radius reports.
"""

import asyncio
import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status

from api.dependencies import (
    CurrentUserDep,
    Neo4jDep,
    QuarantineItemIdDep,
    SettingsDep,
    SupabaseDep,
    require_role,
)
from api.models.document import PromoteQuarantineRequest, RequestQuarantineInfoRequest
from api.services.corpus import document_rows
from api.services.graph import GraphService
from api.services.identity import display_names
from api.services.metrics import conflicts_open
from api.services.sla_service import SLAService

log = structlog.get_logger(__name__)
router = APIRouter()


# =============================================================================
# Conflicts
# =============================================================================

@router.get("/conflicts", summary="List open knowledge conflicts")
async def list_conflicts(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    track: str | None = Query(None, description="'administrative' or 'engineering'"),
    asset_id: str | None = Query(None),
    conflict_status: str | None = Query(None, alias="status", description="open, pending_moc, resolved"),
    include_non_asserting: bool = Query(
        False,
        description="Include conflicts on provenance/structural relationship types "
        "(DOCUMENTED_BY and friends). Off by default — these are co-documentation, not "
        "contradictions, and they were 93 of 94 stored rows.",
    ),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
) -> dict:
    """
    Returns conflicts from the dual-track governance plane.
    - Administrative: minor inconsistencies, lightweight review, 5-day SLA.
    - Engineering: safety-critical contradictions, requires MoC, 24h SLA for critical equipment.

    Rows whose `parameter` is a provenance or structural relationship type are excluded by
    default. `GraphService.detect_conflict` no longer creates them, but the ones already written
    cannot be removed — they live in a cloud store — so they are filtered on the way out.
    Filtered in the QUERY, never in Python: `count` and `range` are computed by PostgREST, so
    dropping rows afterwards would report a total the page could never show and silently break
    pagination.
    """
    await SLAService.check_and_escalate(supabase)

    now = datetime.now(UTC)
    query = supabase.table("knowledge_conflicts").select(
        "conflict_id, track, asset_id, parameter, source_a, source_b, authority_a, authority_b, severity, status, sla_deadline, escalated_at, created_at",
        count="exact",
    )
    if not include_non_asserting:
        query = query.not_.in_("parameter", sorted(GraphService.NON_ASSERTING_RELATIONSHIPS))
    if track:
        query = query.eq("track", track)
    if asset_id:
        query = query.eq("asset_id", asset_id)
    if conflict_status:
        query = query.eq("status", conflict_status)

    result = await asyncio.to_thread(
        lambda: query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    )
    items = []
    for row in result.data or []:
        sla_due_at = row.get("sla_deadline")
        is_overdue = bool(sla_due_at and datetime.fromisoformat(sla_due_at.replace("Z", "+00:00")) < now)
        items.append({**row, "sla_due_at": sla_due_at, "is_overdue": is_overdue})
    return {"items": items, "total": result.count or 0, "limit": limit, "offset": offset}


@router.get("/conflicts/{conflict_id}", summary="Get conflict detail and blast-radius report")
async def get_conflict(
    conflict_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    driver: Neo4jDep,
) -> dict:
    """Returns full conflict detail including both conflicting sources and blast-radius impact."""
    result = await asyncio.to_thread(
        lambda: supabase.table("knowledge_conflicts")
        .select("*")
        .eq("conflict_id", conflict_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conflict '{conflict_id}' not found")

    conflict = result.data[0]
    # Compute blast-radius from the older document (source_a)
    source_a_doc_id = conflict.get("source_a", {}).get("document_id")
    blast = {}
    if source_a_doc_id:
        blast = await GraphService(driver).get_blast_radius(source_a_doc_id)

    return {"conflict": conflict, "blast_radius": blast}


@router.post("/conflicts/{conflict_id}/resolve", summary="Resolve an administrative conflict")
async def resolve_conflict(
    conflict_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    resolution: dict = Body(...),
) -> dict:
    """
    Resolves an administrative-track conflict (no MoC required).
    Engineering-track conflicts can only be resolved via MoC webhook.
    """
    result = await asyncio.to_thread(
        lambda: supabase.table("knowledge_conflicts")
        .select("conflict_id, track, status")
        .eq("conflict_id", conflict_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Conflict '{conflict_id}' not found")

    conflict = result.data[0]
    if conflict["track"] == "engineering":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Engineering-track conflicts must be resolved via MoC webhook (POST /governance/moc/webhook).",
        )

    now = datetime.now(UTC).isoformat()
    await asyncio.to_thread(
        lambda: supabase.table("knowledge_conflicts").update({
            "status": "resolved",
            "resolved_by": current_user.get("user_id", "unknown"),
            "resolved_at": now,
        }).eq("conflict_id", conflict_id).execute()
    )
    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "conflict_resolved",
            "entity_type": "conflict",
            "entity_id": conflict_id,
            "performed_by": current_user.get("user_id", "unknown"),
            "details": {"resolution": resolution, "track": "administrative"},
        }).execute()
    )
    log.info("conflict.resolved", conflict_id=conflict_id, resolver=current_user.get("user_id"))
    return {"status": "resolved", "conflict_id": conflict_id}


# =============================================================================
# Quarantine Layer
# =============================================================================

@router.get("/quarantine", summary="List items in the quarantine layer")
async def list_quarantine(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    asset_id: str | None = Query(None),
    reviewer_id: str | None = Query(None),
    review_status: str | None = Query(None, description="pending, promoted, disputed, archived"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
) -> dict:
    """
    Returns unverified field inputs awaiting review.
    All quarantine results are clearly labeled as non-canonical.
    Items with input_type='elicitation_response' include full session_context (questions + answers).
    """
    await SLAService.check_and_escalate(supabase)

    now = datetime.now(UTC)
    query = supabase.table("quarantine_items").select(
        "item_id, asset_id, content, input_type, submitted_by, submitted_at, reviewer_id, review_status, work_order_id, session_context, sla_due_at, escalated_at",
        count="exact",
    )
    # The P&ID manifest row is pipeline bookkeeping (it indexes a drawing's elements for the topology
    # page) — not a field input anyone can promote or dispute, yet it sat in the review queue reading
    # "PID_TOPOLOGY_MANIFEST:DOC-…". Excluded in the query so `total` still matches the list.
    query = query.not_.like("content", "PID_TOPOLOGY_MANIFEST:%")
    if asset_id:
        query = query.eq("asset_id", asset_id)
    if reviewer_id:
        query = query.eq("reviewer_id", reviewer_id)
    # `all` exists for the review page: it shows Promoted/Disputed counts and a Resolved tab, which
    # were permanently 0/empty while it could only ever fetch pending rows.
    if review_status and review_status != "all":
        query = query.eq("review_status", review_status)
    elif not review_status:
        query = query.eq("review_status", "pending")  # default: pending items only

    result = await asyncio.to_thread(
        lambda: query.order("submitted_at", desc=True).range(offset, offset + limit - 1).execute()
    )
    items = []
    rows = result.data or []
    # Submitter/reviewer are auth UUIDs for anything a signed-in user did; the review panel showed them raw.
    names = await display_names(supabase, [r.get("submitted_by") for r in rows] + [r.get("reviewer_id") for r in rows])
    for row in rows:
        sla = row.get("sla_due_at")
        is_overdue = bool(sla and datetime.fromisoformat(sla.replace("Z", "+00:00")) < now)
        items.append({
            **row,
            "is_overdue": is_overdue,
            "submitted_by_name": names.get(row.get("submitted_by")),
            "reviewer_name": names.get(row.get("reviewer_id")),
        })
    return {
        "items": items,
        "total": result.count or 0,
        "limit": limit,
        "offset": offset,
        "note": "All items are unverified field inputs — not reviewed by engineering authority.",
    }


@router.post("/quarantine/{item_id}/promote", summary="Promote quarantine item to canonical graph")
async def promote_quarantine_item(
    item_id: QuarantineItemIdDep,
    payload: PromoteQuarantineRequest,
    supabase: SupabaseDep,
    driver: Neo4jDep,
    current_user: dict = Depends(require_role("reliability", "admin")),
) -> dict:
    """
    Human authority promotes an unverified field input to the canonical temporal graph.
    Requires reliability or admin role — matches OPA `can_promote_quarantine` and the
    frontend PROMOTE_ROLES. Engineers resolve conflicts/MoC but do not promote quarantine.
    """
    result = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items")
        .select("*")
        .eq("item_id", item_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Quarantine item '{item_id}' not found")

    item = result.data[0]
    if item["review_status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item already has review_status='{item['review_status']}'.",
        )

    asset_id = item.get("asset_id")
    if not asset_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quarantine item has no asset_id — cannot link to graph.")

    ctx = item.get("session_context") or {}
    document_id = ctx.get("document_id") or f"PROMOTED-{item_id}"
    now = datetime.now(UTC)

    graph = GraphService(driver)
    # Ensure Document node exists
    await graph.merge_document_node(document_id, {"authority_level": payload.authority_level, "document_type": payload.document_type})

    edge_result = await graph.create_knowledge_edge(
        source_id=asset_id,
        source_label="Asset",
        target_id=document_id,
        target_label="Document",
        relationship_type=payload.relationship_type,
        valid_from=now,
        authority_level=payload.authority_level,
        document_id=document_id,
        confidence=1.0,  # human-verified
        verification_status="verified",
    )

    now_iso = now.isoformat()
    await asyncio.to_thread(
        lambda: supabase.table("quarantine_items").update({
            "review_status": "promoted",
            "reviewer_id": current_user.get("user_id", "unknown"),
            "reviewed_at": now_iso,
        }).eq("item_id", item_id).execute()
    )

    # If conflict detected on the newly promoted edge, insert it
    conflict = edge_result.get("conflict")
    conflict_id = None
    if conflict:
        conflict_row = await asyncio.to_thread(
            lambda cd=conflict: supabase.table("knowledge_conflicts").insert({
                "track": cd["track"],
                "asset_id": asset_id,
                "parameter": cd["parameter"],
                "source_a": cd["source_a"],
                "source_b": cd["source_b"],
                "authority_a": cd["authority_a"],
                "authority_b": cd["authority_b"],
                "severity": cd["severity"],
                "status": "pending_moc" if cd["track"] == "engineering" else "open",
                "sla_deadline": (now + timedelta(hours=cd["sla_hours"])).isoformat(),
            }).execute()
        )
        if conflict_row.data:
            conflict_id = conflict_row.data[0].get("conflict_id")

    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "quarantine_promoted",
            "entity_type": "quarantine_item",
            "entity_id": item_id,
            "performed_by": current_user.get("user_id", "unknown"),
            "details": {
                "edge_id": edge_result["edge_id"],
                "asset_id": asset_id,
                "relationship_type": payload.relationship_type,
                "authority_level": payload.authority_level,
                "notes": payload.notes,
                "conflict_id": conflict_id,
            },
        }).execute()
    )

    # Feed validation corpus — every human promotion is a verified ground truth
    entity = ctx.get("entity") or {}
    entity_text = entity.get("text") or (item.get("content") or "")[:200]
    entity_type = entity.get("entity_type") or ""
    if entity_text and entity_type:
        try:
            await asyncio.to_thread(
                lambda: supabase.table("validation_corpus").insert({
                    "document_id": document_id,
                    "entity_text": entity_text,
                    "entity_type": entity_type,
                    "span_start": entity.get("start"),
                    "span_end": entity.get("end"),
                    "authority": "human_promotion",
                    "promoted_by": current_user.get("user_id", "unknown"),
                }).execute()
            )
        except Exception as exc:
            log.warning("validation_corpus.insert_failed", item_id=item_id, error=str(exc))

    if conflict is not None:
        conflicts_open.add(1, {"track": conflict.get("track", "unknown")})
    log.info("quarantine.promoted", item_id=item_id, asset_id=asset_id, edge_id=edge_result["edge_id"])
    return {
        "status": "promoted",
        "item_id": item_id,
        "edge_id": edge_result["edge_id"],
        "conflict_detected": conflict is not None,
        "conflict_id": conflict_id,
    }


@router.post("/quarantine/{item_id}/dispute", summary="Dispute a quarantine item as incorrect")
async def dispute_quarantine_item(
    item_id: QuarantineItemIdDep,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    reason: dict = Body(...),
) -> dict:
    """Flags a quarantine item as disputed with a reason. Does not delete it."""
    result = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items")
        .select("item_id, review_status, asset_id, session_context")
        .eq("item_id", item_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Quarantine item '{item_id}' not found")
    item = result.data[0]
    if item["review_status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item is already '{item['review_status']}', cannot dispute.",
        )

    now_iso = datetime.now(UTC).isoformat()
    await asyncio.to_thread(
        lambda: supabase.table("quarantine_items").update({
            "review_status": "disputed",
            "reviewer_id": current_user.get("user_id", "unknown"),
            "reviewed_at": now_iso,
        }).eq("item_id", item_id).execute()
    )

    # Circuit breaker: record quarantine rejection override
    from api.services.circuit_breaker import CircuitBreakerService
    cb = CircuitBreakerService(supabase)
    asset_class = "unknown"
    q_asset_id = item.get("asset_id")
    if q_asset_id:
        asset_row = await asyncio.to_thread(
            lambda: supabase.table("assets").select("equipment_class").eq("asset_id", q_asset_id).execute()
        )
        if asset_row.data:
            asset_class = asset_row.data[0].get("equipment_class") or "unknown"
    doc_id = (item.get("session_context") or {}).get("document_id")
    await cb.record_override(asset_class, doc_id, "quarantine_rejection")

    log.info("quarantine.disputed", item_id=item_id, user=current_user.get("user_id"))
    return {"status": "disputed", "item_id": item_id, "reason": reason}


@router.post("/quarantine/{item_id}/request-info", summary="Record a reviewer request for more quarantine evidence")
async def request_quarantine_info(
    item_id: QuarantineItemIdDep,
    payload: RequestQuarantineInfoRequest,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """Layer 6's fourth review action: a reviewer asks for clarification instead of
    promoting or disputing. The item stays 'pending' (still actionable in the queue);
    the request and note are recorded to the audit log for provenance.

    ponytail: audit-log-backed, no new review_status. Promote to a first-class
    'info_requested' status + queue badge only if reviewers need it visible without
    reading the audit trail.
    """
    result = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items")
        .select("item_id, review_status, asset_id, work_order_id, input_type")
        .eq("item_id", item_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Quarantine item '{item_id}' not found")

    item = result.data[0]
    if item["review_status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Item is already '{item['review_status']}', cannot request more information.",
        )

    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "quarantine_info_requested",
            "entity_type": "quarantine_item",
            "entity_id": item_id,
            "performed_by": current_user.get("user_id", "unknown"),
            "details": {
                "note": payload.note,
                "asset_id": item.get("asset_id"),
                "work_order_id": item.get("work_order_id"),
                "input_type": item.get("input_type"),
            },
        }).execute()
    )
    log.info("quarantine.info_requested", item_id=item_id, user=current_user.get("user_id"))
    return {"status": "requested", "item_id": item_id}


# =============================================================================
# SLA Report
# =============================================================================

@router.get("/sla-report", summary="SLA escalation report for conflicts and quarantine items")
async def get_sla_report(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """
    Runs lazy SLA escalation then returns counts of overdue conflicts and quarantine items.
    """
    escalation_result = await SLAService.check_and_escalate(supabase)

    now = datetime.now(UTC).isoformat()

    overdue_conflicts = await asyncio.to_thread(
        lambda: supabase.table("knowledge_conflicts")
        .select("conflict_id, track, asset_id, sla_deadline, escalated_at, status", count="exact")
        .lt("sla_deadline", now)
        .neq("status", "resolved")
        .execute()
    )
    overdue_quarantine = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items")
        .select("item_id, asset_id, input_type, content, sla_due_at, escalated_at", count="exact")
        .lt("sla_due_at", now)
        .eq("review_status", "pending")
        .execute()
    )

    return {
        "checked_at": escalation_result["checked_at"],
        "escalated_this_run": {
            "conflicts": escalation_result["conflicts_escalated"],
            "quarantine_items": escalation_result["quarantine_escalated"],
        },
        "overdue_conflicts": overdue_conflicts.data or [],
        "overdue_conflicts_total": overdue_conflicts.count or 0,
        "overdue_quarantine_items": overdue_quarantine.data or [],
        "overdue_quarantine_total": overdue_quarantine.count or 0,
    }


# =============================================================================
# Circuit Breaker (SPC — Layer 7)
# =============================================================================

@router.get("/circuit-breaker", summary="SPC circuit breaker status per asset class")
async def get_circuit_breaker_status(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """
    Returns the current Z-score and halted status for every asset class
    that has recorded extraction overrides in the last 30 days.
    A halted asset class blocks new graph writes until override rate normalises.
    """
    from api.services.circuit_breaker import CircuitBreakerService
    cb = CircuitBreakerService(supabase)
    states = await cb.get_all_states()
    return {
        "states": states,
        "halted_count": sum(1 for s in states if s["halted"]),
    }


# =============================================================================
# MoC (Management of Change)
# =============================================================================

@router.get("/moc", summary="List MoC items")
async def list_moc(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    moc_status: str | None = Query(None, alias="status", description="draft, pending_approval, approved, rejected"),
) -> dict:
    """Returns Management of Change items, optionally filtered by status."""
    query = supabase.table("moc_items").select(
        "moc_id, conflict_id, asset_id, description, status, approved_by, approved_at, created_at, blast_radius",
        count="exact",
    )
    if moc_status:
        query = query.eq("status", moc_status)
    result = await asyncio.to_thread(
        lambda: query.order("created_at", desc=True).limit(100).execute()
    )
    # The list's "Blast radius" column read `blast_radius_count`, which this endpoint never returned, so
    # every MoC showed 0 affected records. The drafted blast radius is stored on the row.
    items = []
    for row in result.data or []:
        blast = row.pop("blast_radius", None) or []
        items.append({**row, "blast_radius_count": len(blast) if isinstance(blast, list) else 0})
    return {"items": items, "total": result.count or 0}


async def _resolve_moc_conflict(
    supabase, driver, conflict_id, approved_by: str, now: datetime, now_iso: str
) -> None:
    """Close the superseded edge's validity window and mark the linked conflict resolved.

    Shared by the MoC webhook and the in-app approve endpoint so the graph mutation
    (close old edge → resolve conflict) lives in exactly one place. No-ops when the MoC
    has no linked conflict or the conflict/edge can't be found.
    """
    if not conflict_id:
        return
    conflict_result = await asyncio.to_thread(
        lambda: supabase.table("knowledge_conflicts").select("*").eq("conflict_id", str(conflict_id)).execute()
    )
    if not conflict_result.data:
        return
    conflict = conflict_result.data[0]
    old_edge_id = (conflict.get("source_a") or {}).get("edge_id")
    if old_edge_id:
        await GraphService(driver).close_validity_window(old_edge_id, now)
    await asyncio.to_thread(
        lambda: supabase.table("knowledge_conflicts").update({
            "status": "resolved",
            "resolved_by": approved_by,
            "resolved_at": now_iso,
        }).eq("conflict_id", str(conflict_id)).execute()
    )


@router.post("/moc/webhook", summary="Receive MoC resolution webhook from plant MoC system")
async def receive_moc_webhook(
    supabase: SupabaseDep,
    driver: Neo4jDep,
    payload: dict = Body(...),
    x_webhook_signature: str | None = Header(None),
) -> dict:
    """
    Receives MoC resolution from the plant's EAM/SAP MoC system.
    On approval: closes old validity window, promotes new fact to canonical, clears conflict.
    On rejection: logs outcome, keeps conflict open.
    """
    # Signature check when secret is configured.
    #
    # Configuring the secret is what turns verification on; once on, an unsigned request is
    # REJECTED rather than accepted. The previous condition (`moc_secret and x_webhook_signature`)
    # made the check opt-in *by the caller* — anyone could skip verification by omitting the
    # header, which is the one party you cannot trust to choose. Combined with the missing
    # Settings field (getattr always returned None) no MoC webhook was ever verified.
    from api.config import get_settings
    settings = get_settings()
    moc_secret = settings.MOC_WEBHOOK_SECRET
    if moc_secret:
        if not x_webhook_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Webhook-Signature header",
            )
        import json
        expected = hmac.new(
            moc_secret.encode(),
            json.dumps(payload, sort_keys=True).encode(),
            hashlib.sha256,
        ).hexdigest()  # hmac.new is the stdlib constructor alias
        if not hmac.compare_digest(expected, x_webhook_signature):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    moc_id = payload.get("moc_id")
    resolution_status = payload.get("status")  # "approved" or "rejected"
    approved_by = payload.get("approved_by", "webhook")

    if not moc_id or resolution_status not in ("approved", "rejected"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload must include moc_id and status (approved|rejected)")

    moc_result = await asyncio.to_thread(
        lambda: supabase.table("moc_items").select("*").eq("moc_id", moc_id).execute()
    )
    if not moc_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"MoC '{moc_id}' not found")

    moc = moc_result.data[0]
    conflict_id = moc.get("conflict_id")
    now = datetime.now(UTC)
    now_iso = now.isoformat()

    await asyncio.to_thread(
        lambda: supabase.table("moc_items").update({
            "status": resolution_status,
            "approved_by": approved_by if resolution_status == "approved" else None,
            "approved_at": now_iso if resolution_status == "approved" else None,
            "webhook_received_at": now_iso,
        }).eq("moc_id", moc_id).execute()
    )

    if resolution_status == "approved" and conflict_id:
        # Close the superseded edge and resolve the conflict (shared with in-app approve).
        await _resolve_moc_conflict(supabase, driver, conflict_id, approved_by, now, now_iso)

    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "moc_webhook_received",
            "entity_type": "moc_item",
            "entity_id": moc_id,
            "performed_by": approved_by,
            "details": {"resolution_status": resolution_status, "conflict_id": str(conflict_id) if conflict_id else None},
        }).execute()
    )

    log.info("moc.webhook_received", moc_id=moc_id, status=resolution_status)
    return {"status": "received", "moc_id": moc_id, "resolution": resolution_status}


@router.get("/moc/{moc_id}", summary="Get MoC item detail with conflicting sources")
async def get_moc_item(
    moc_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    driver: Neo4jDep,
) -> dict:
    """Return one MoC item enriched with the conflicting sources + blast-radius count from
    its linked knowledge_conflicts row. The moc_items table stores only the linkage; the
    parameter/source_a/source_b live on the conflict, so the detail view joins them here.
    """
    moc_result = await asyncio.to_thread(
        lambda: supabase.table("moc_items").select("*").eq("moc_id", moc_id).execute()
    )
    if not moc_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"MoC '{moc_id}' not found")
    moc = moc_result.data[0]

    parameter: str = ""
    source_a: dict = {}
    source_b: dict = {}
    blast_count = 0
    conflict_id = moc.get("conflict_id")
    if conflict_id:
        conflict_result = await asyncio.to_thread(
            lambda: supabase.table("knowledge_conflicts")
            .select("parameter, source_a, source_b")
            .eq("conflict_id", str(conflict_id)).execute()
        )
        if conflict_result.data:
            conflict = conflict_result.data[0]
            parameter = conflict.get("parameter") or ""
            source_a = conflict.get("source_a") or {}
            source_b = conflict.get("source_b") or {}
            blast_doc = source_b.get("document_id") or source_a.get("document_id")
            if blast_doc:
                try:
                    blast = await GraphService(driver).get_blast_radius(blast_doc)
                    blast_count = blast.get("affected_count", 0)
                except Exception:  # noqa: BLE001 — blast radius is best-effort enrichment
                    log.warning("moc.blast_radius_failed", moc_id=moc_id, document_id=blast_doc)

    # The drafted blast radius stored on the MoC is a floor: the graph traversal can see fewer affected
    # records than the draft listed (e.g. before downstream documents are linked).
    stored_blast = moc.get("blast_radius") or []
    blast_count = max(blast_count, len(stored_blast) if isinstance(stored_blast, list) else 0)

    # Name the conflicting documents — the sign-off panel showed bare ids an engineer cannot read.
    ids = [s.get("document_id") for s in (source_a, source_b) if s.get("document_id")]
    names = {r["document_id"]: r.get("file_name") for r in await document_rows(supabase, ids)} if ids else {}
    for s in (source_a, source_b):
        if s.get("document_id") and not s.get("file_name") and names.get(s["document_id"]):
            s["file_name"] = names[s["document_id"]]

    return {
        "moc_id": moc["moc_id"],
        "asset_id": moc.get("asset_id"),
        "parameter": parameter,
        "source_a": source_a,
        "source_b": source_b,
        "blast_radius_count": blast_count,
        "status": moc.get("status"),
        "created_at": moc.get("created_at"),
        "draft_content": moc.get("description"),
    }


@router.post("/moc/{moc_id}/approve", summary="Approve a MoC in-app (engineer/admin sign-off)")
async def approve_moc_item(
    moc_id: str,
    supabase: SupabaseDep,
    driver: Neo4jDep,
    current_user: dict = Depends(require_role("engineer", "admin")),
    payload: dict = Body(default={}),
) -> dict:
    """In-app MoC sign-off — engineer/admin authority (mirrors OPA can_resolve_moc). Marks the
    MoC approved, closes the superseded edge's validity window, and resolves the linked
    engineering-track conflict. Same effect as an approved MoC webhook, human-initiated.
    """
    approver = current_user.get("user_id", "unknown")
    note = (payload or {}).get("note")

    moc_result = await asyncio.to_thread(
        lambda: supabase.table("moc_items").select("*").eq("moc_id", moc_id).execute()
    )
    if not moc_result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"MoC '{moc_id}' not found")
    moc = moc_result.data[0]
    if moc.get("status") == "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="MoC already approved.")

    now = datetime.now(UTC)
    now_iso = now.isoformat()
    await asyncio.to_thread(
        lambda: supabase.table("moc_items").update({
            "status": "approved",
            "approved_by": approver,
            "approved_at": now_iso,
        }).eq("moc_id", moc_id).execute()
    )
    await _resolve_moc_conflict(supabase, driver, moc.get("conflict_id"), approver, now, now_iso)
    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "moc_approved",
            "entity_type": "moc_item",
            "entity_id": moc_id,
            "performed_by": approver,
            "details": {"note": note, "conflict_id": str(moc.get("conflict_id")) if moc.get("conflict_id") else None},
        }).execute()
    )
    log.info("moc.approved", moc_id=moc_id, approver=approver)
    return {"status": "approved", "moc_id": moc_id}


# =============================================================================
# Blast Radius
# =============================================================================

@router.get("/blast-radius/{document_id}", summary="Get blast-radius report for a document change")
async def get_blast_radius(
    document_id: str,
    current_user: CurrentUserDep,
    driver: Neo4jDep,
) -> dict:
    """
    Traverses the graph to identify all downstream facts, procedures, and relationships
    that derive from the specified document. Used when a document is superseded or disputed.
    """
    return await GraphService(driver).get_blast_radius(document_id)


# =============================================================================
# Layer 0 — Validation Corpus + Model Gate
# =============================================================================

@router.get("/validation-corpus/stats", summary="Validation corpus coverage statistics")
async def validation_corpus_stats(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """Return corpus size by entity type and date of last update."""
    result = await asyncio.to_thread(
        lambda: supabase.table("validation_corpus")
        .select("entity_type, created_at")
        .execute()
    )
    rows = result.data or []

    by_entity_type: dict = {}
    last_updated_at = None
    for row in rows:
        et = row.get("entity_type", "unknown")
        by_entity_type[et] = by_entity_type.get(et, 0) + 1
        ts = row.get("created_at")
        if ts and (last_updated_at is None or ts > last_updated_at):
            last_updated_at = ts

    return {
        "total_corpus_size": len(rows),
        "by_entity_type": by_entity_type,
        "last_updated_at": last_updated_at,
    }


@router.post("/model-gate/run", summary="Trigger NER model gate evaluation")
async def run_model_gate_endpoint(
    settings: SettingsDep,
    current_user: dict = Depends(require_role("admin")),
    model_name: str | None = None,
) -> dict:
    """Admin only. Runs NER accuracy evaluation against the validation corpus on the validation
    queue. Defaults to the configured NER model when model_name is omitted, so the UI can trigger
    a run without knowing the model name."""
    from workers.model_validation import run_model_gate
    target_model = model_name or settings.NVIDIA_NIM_NER_MODEL
    task = run_model_gate.apply_async(args=[target_model])
    return {"task_id": task.id, "model_name": target_model, "status": "queued"}


@router.get("/model-gate/history", summary="Model gate run history")
async def model_gate_history(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """Return last 20 model gate runs from audit_log."""
    result = await asyncio.to_thread(
        lambda: supabase.table("audit_log")
        .select("id, entity_id, details, timestamp")
        .eq("action", "model_gate_result")
        .order("timestamp", desc=True)
        .limit(20)
        .execute()
    )
    return {"items": result.data or [], "total": len(result.data or [])}


@router.get("/push-volume-gate", summary="EEMUA 191 pilot monitoring gate (reporting only)")
async def push_volume_gate(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    settings: SettingsDep,
    days: int = Query(30, ge=1, le=90),
) -> dict:
    """
    The Phase 3 precondition from the architecture: push volume must stay within EEMUA 191 norms
    (<=6 per operator per hour) for 30 consecutive operating days before governed proactive mode
    is the default operating posture.

    **Reporting only — this never blocks Phase 3 at runtime.** The gate exists to tell an operator
    whether the push thesis is holding against real data; wiring it as a hard runtime block would
    mean a deployment with under 30 days of history could not deliver briefs at all, which is a
    worse failure than the one it prevents. Phase activation stays a deliberate configuration
    decision (`KAIROS_PHASE`), informed by this number.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    result = await asyncio.to_thread(
        lambda: supabase.table("briefs")
        .select("recipient_user_id, delivered_at")
        .gte("delivered_at", since)
        .execute()
    )
    rows = [r for r in (result.data or []) if r.get("delivered_at")]

    # Peak hourly rate per operator — the ceiling is a per-hour limit, so an average over the
    # window would hide exactly the bursts EEMUA 191 is written about.
    per_user_hour: dict[tuple[str, str], int] = {}
    for row in rows:
        hour_bucket = str(row["delivered_at"])[:13]  # YYYY-MM-DDTHH
        key = (row.get("recipient_user_id") or "unknown", hour_bucket)
        per_user_hour[key] = per_user_hour.get(key, 0) + 1

    ceiling = settings.MAX_PUSH_PER_USER_PER_HOUR
    peak = max(per_user_hour.values(), default=0)
    breaches = [
        {"recipient_user_id": user, "hour": hour, "count": count}
        for (user, hour), count in sorted(per_user_hour.items())
        if count > ceiling
    ]

    return {
        "window_days": days,
        "ceiling_per_operator_per_hour": ceiling,
        "peak_per_operator_per_hour": peak,
        "breach_count": len(breaches),
        "breaches": breaches[:20],
        "briefs_delivered": len(rows),
        "within_eemua_norms": len(breaches) == 0,
        "current_phase": settings.KAIROS_PHASE,
        # Named so no caller mistakes this for an enforcement point.
        "enforcement": "advisory_only",
    }


@router.get("/timestamp-drift", summary="Cross-source clock drift report (Layer 4)")
async def timestamp_drift_report(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    settings: SettingsDep,
    limit: int = Query(50, le=200),
) -> dict:
    """
    Clock drift between source systems reporting the *same* correlated event.

    Deliberately NOT `occurred_at` vs `ingested_at`: a document that occurred months before it was
    ingested is history, not skew, and comparing those would flag an entire golden corpus and bury
    the real signal. Only compound events — the same physical action seen by two or more systems —
    are comparable.

    Report-only while `TIMESTAMP_DRIFT_ENFORCE` is false: drift is surfaced here but opens no
    conflict row, so the check can be observed against real data before it creates review load.
    """
    from api.services.timestamp_alignment import TimestampAlignmentService

    result = await asyncio.to_thread(
        lambda: supabase.table("operational_events")
        .select("compound_event_id")
        .not_.is_("compound_event_id", "null")
        .limit(limit * 4)
        .execute()
    )
    compound_ids = list({r["compound_event_id"] for r in (result.data or []) if r.get("compound_event_id")})[:limit]

    svc = TimestampAlignmentService(supabase, settings)
    checked = [await svc.check_compound_event(cid) for cid in compound_ids]
    drifting = [c for c in checked if c.get("drift_detected")]

    return {
        "compound_events_checked": len(checked),
        "drift_detected_count": len(drifting),
        "tolerance_minutes": settings.TIMESTAMP_DRIFT_TOLERANCE_MINUTES,
        "enforcement": "enforced" if settings.TIMESTAMP_DRIFT_ENFORCE else "advisory_only",
        "items": drifting[:limit],
    }
