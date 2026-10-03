"""
Events router — Layer 8: Operational Event Subscription and Proactive Delivery.
Receives work orders, PTW events, shift handovers, alarms from operational systems.
Publishes to Redis Streams for async brief generation.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated

import shortuuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError

from api.config import settings as app_settings
from api.dependencies import (
    CurrentUserDep,
    ElasticsearchDep,
    Neo4jDep,
    QdrantDep,
    QuarantineItemIdDep,
    RedisDep,
    SettingsDep,
    SupabaseDep,
    demo_llm_budget,
    require_role,
    site_scope,
)
from api.models.event import (
    AlarmEvent,
    DeviationFlagEvent,
    DeviationFlagResolveRequest,
    EventAck,
    InspectionCompleteEvent,
    PlantStateEvent,
    PTWEvent,
    ShiftHandoverEvent,
    TagOutEvent,
    WorkOrderEvent,
)
from api.routers.briefs import _brief_recipients, _sign_acknowledgment
from api.services import tenant
from api.services.brief_engine import BriefEngine
from api.services.event_bus import EventBusService
from api.services.identity import display_name
from api.utils.failure_families import failure_family
from workers.attribution import evaluate_outcome
from workers.brief_assembly import assemble_brief

log = structlog.get_logger(__name__)
router = APIRouter()

# Who may feed operational events into the system. Mirrors the OPA `ingest_event` grant in
# infra/policies/kairos.rego (admin is "*"; the Go connector's internal key resolves to admin).
# These routes create critical-priority briefs and compliance evidence, so they are not open to
# every authenticated role the way field-worker flows (deviation flags, acks) are.
_INGEST_ROLES = ("engineer", "reliability", "admin")
IngestUserDep = Annotated[dict, Depends(require_role(*_INGEST_ROLES))]

# Ceiling on the confidence of an inspection-evidence edge. The reporter used to choose it freely:
# a caller-picked 0.7+ cleared the audit pack's "human review required" flag. The link is a staff
# assertion about a vault document, so it sits above the 0.7 quarantine line but stays
# `unverified` until a human verifies the edge. A caller may go lower, never higher.
INSPECTION_EVIDENCE_CONFIDENCE = 0.85


def _count_recurrences(prior_rows: list[dict], family: str) -> int:
    """Prior work orders in the same failure family. A blank code has no family, so two work
    orders that both omit one are not a recurrence. Same mapping on both sides of the compare."""
    if not family:
        return 0
    return sum(
        1 for row in prior_rows
        if failure_family((row.get("payload") or {}).get("failure_code")) == family
    )


async def _store_event(supabase, row: dict) -> None:
    """Insert an `operational_events` row; an identical re-post of the same event is a no-op.

    `event_id` is client-supplied, so an upsert would let any ingest role overwrite another
    event's payload, asset and site by posting its id. A duplicate key (Postgres 23505) is read
    back instead: the same event (type, asset, site, payload) is a retry after a partial failure
    and carries on; anything else is a 409 and the stored row is left exactly as it was.
    """
    try:
        await asyncio.to_thread(lambda: supabase.table("operational_events").insert(row).execute())
    except APIError as exc:
        if exc.code != "23505":
            raise
    else:
        return
    stored = await asyncio.to_thread(
        lambda: supabase.table("operational_events")
        .select("event_type, asset_id, site_id, payload")
        .eq("event_id", row["event_id"])
        .limit(1)
        .execute()
    )
    if not stored.data or any(stored.data[0].get(k) != row[k] for k in ("event_type", "asset_id", "site_id", "payload")):
        log.warning("events.event_id_conflict", event_id=row["event_id"])
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An event with this event_id already exists.")


async def _canonical_asset(asset_id: str | None, driver, supabase, current_user: dict | None = None) -> str | None:
    """The canonical id for an event's asset, accepting confirmed aliases ("P-101" → "EQ-101").

    Operational systems report the tag they know. Events used to be inserted with it verbatim, so an
    alias failed the `assets` foreign key and surfaced as an unhandled 500; an unknown tag is now a
    404 that names the tag instead.

    With `current_user`, an asset on another site is reported as not registered too (same 404, so
    its existence is not disclosed). Admin and the connector's service key see every site.
    """
    if not asset_id:
        return asset_id
    from api.routers.assets import resolve_canonical_asset_id
    from api.services.graph import GraphService

    canonical = await resolve_canonical_asset_id(asset_id, GraphService(driver), supabase)
    if not canonical:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' is not registered.")
    site = site_scope(current_user, None) if current_user else None
    if site is not None:
        node = await GraphService(driver).get_asset(canonical)
        if node and not tenant.on_visible_site(current_user, node.get("site_id"), site):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' is not registered.")
    tenant.guard_asset(current_user, canonical)  # a demo report must name a showcase asset
    return canonical


async def _materialise_event_node(
    driver,
    event_id,
    event_type: str,
    occurred_at: str,
    asset_id: str | None,
) -> None:
    """Mirror an operational event into the graph as an `Event` node (Layer 4).

    Events were written to Supabase only, so three of the six designed node types existed and
    `Event` — which already has two indexes declared for it in `init_schema.cypher` — was never
    written. Any traversal that wanted to reach an event had to leave the graph.

    Supabase remains the system of record. `merge_event_node` swallows its own failures, so a
    Neo4j outage degrades the graph view without failing the ingest: losing the event entirely
    because a secondary store was down would be the worse trade.
    """
    from api.services.graph import GraphService

    await GraphService(driver).merge_event_node(
        event_id=str(event_id),
        event_type=event_type,
        occurred_at=occurred_at,
        asset_id=asset_id,
    )


@router.post("/work-order", dependencies=[Depends(demo_llm_budget)], summary="Ingest work order event", status_code=status.HTTP_202_ACCEPTED)
async def ingest_work_order(
    payload: WorkOrderEvent,
    current_user: IngestUserDep,
    redis: RedisDep,
    supabase: SupabaseDep,
    settings: SettingsDep,
    driver: Neo4jDep,
    qdrant: QdrantDep,
    es: ElasticsearchDep,
) -> dict:
    """
    Receives a work order creation event from CMMS/EAM.
    Canonical deduplication: same asset + event_type within 10-min window → deduplicated.
    Persists to operational_events, publishes to Redis Stream for brief assembly.
    """
    site_scope(current_user, payload.site_id, write=True)  # a non-admin may only report for their own site
    tenant.guard_site(current_user, payload.site_id)
    payload.asset_id = await _canonical_asset(payload.asset_id, driver, supabase, current_user)
    bus = EventBusService(redis, settings)

    # Scoped by work_order_id: two *different* work orders on one asset inside the window are
    # two real events, not a duplicate — collapsing them loses the second technician's brief.
    if await bus.is_duplicate(payload.asset_id, payload.event_type, business_id=payload.work_order_id):
        log.info("events.work_order_deduplicated", event_id=payload.event_id, asset_id=payload.asset_id)
        return {"status": "deduplicated", "event_id": payload.event_id,
                "message": "Identical event received within dedup window."}

    event_dict = payload.model_dump(mode="json")

    # --- Recurrence detection (before insert so we can set event_subtype) ---
    recurring_detected = False
    recurring_brief_task_id = None
    recurrence_count = 0
    this_family = failure_family(payload.failure_code)
    try:
        cutoff_90 = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        prior_wos = await asyncio.to_thread(
            lambda: supabase.table("operational_events")
            .select("payload")
            .eq("asset_id", payload.asset_id)
            .eq("event_type", "work_order_created")
            .neq("event_id", payload.event_id)
            .gte("occurred_at", cutoff_90)
            .execute()
        )
        recurrence_count = _count_recurrences(prior_wos.data or [], this_family)
        if recurrence_count >= 1:
            recurring_detected = True
    except Exception as exc:
        log.warning("events.recurrence_detection_failed", error=str(exc))

    await _store_event(supabase, {
        "event_id": payload.event_id,
        "event_type": payload.event_type,
        "source_system": payload.source_system,
        "site_id": payload.site_id,
        "asset_id": payload.asset_id,
        "payload": event_dict,
        "occurred_at": payload.occurred_at.isoformat(),
        "received_at": payload.received_at.isoformat(),
        "event_subtype": "recurring" if recurring_detected else None,
    })

    await _materialise_event_node(
        driver, payload.event_id, payload.event_type,
        payload.occurred_at.isoformat(), payload.asset_id,
    )

    stream_id = await bus.publish_work_order(event_dict)

    await asyncio.to_thread(
        lambda sid=stream_id: supabase.table("operational_events")
        .update({"redis_stream_id": sid})
        .eq("event_id", payload.event_id)
        .execute()
    )

    # Correlate with other events for the same asset within DEDUP_WINDOW_MINUTES
    await bus.correlate_events(payload.asset_id, str(payload.event_id), payload.occurred_at, supabase)

    # Delay brief assembly to allow correlated events (e.g. PTW) to arrive first; assembly reads
    # them back from operational_events. The slot is per work order: this brief goes to *this*
    # work order's technician, so a second work order on the asset must not cancel it. Only a
    # re-report of the same work order revokes and re-enqueues.
    window_secs = settings.LATE_ARRIVAL_WINDOW_MINUTES * 60
    pending_key = f"kairos:brief_pending:{payload.asset_id}:{payload.work_order_id}"
    existing_id = await redis.get(pending_key)
    if existing_id:
        from workers.celery_app import celery_app as _app
        _app.control.revoke(existing_id, terminate=False)
        log.info("events.deferred_brief_revoked", asset_id=payload.asset_id, revoked_task=existing_id)
    task = assemble_brief.apply_async(args=[payload.event_type, event_dict], countdown=window_secs)
    await redis.setex(pending_key, window_secs + 60, task.id)
    task_id = task.id

    # Recurring failure brief — dispatched immediately at high priority
    if recurring_detected:
        recurring_event = {
            **event_dict,
            "event_subtype": "recurring",
            "recurrence_count": recurrence_count,
            "failure_family": this_family,
            "brief_priority": "high",
        }
        await bus.publish_work_order(recurring_event)
        recurring_task = assemble_brief.apply_async(
            args=["recurring_failure_detected", recurring_event],
            countdown=0,
        )
        recurring_brief_task_id = recurring_task.id
        log.info(
            "events.recurring_failure_detected",
            asset_id=payload.asset_id,
            failure_code=payload.failure_code,
            failure_family=this_family,
            recurrence_count=recurrence_count,
        )

    # Attribution: if this asset had a prior WO in the last 30 days, evaluate outcome
    try:
        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        count_result = await asyncio.to_thread(
            lambda: supabase.table("operational_events")
            .select("event_id", count="exact")
            .eq("asset_id", payload.asset_id)
            .eq("event_type", payload.event_type)
            .gte("occurred_at", cutoff)
            .execute()
        )
        if (count_result.count or 0) > 1:
            evaluate_outcome.delay(str(payload.event_id), payload.asset_id)
            log.info("attribution.enqueued", event_id=str(payload.event_id), asset_id=payload.asset_id)
    except Exception as exc:
        log.warning("attribution.enqueue_failed", error=str(exc))

    await bus.mark_seen(payload.asset_id, payload.event_type, business_id=payload.work_order_id)

    log.info("events.work_order_ingested", event_id=payload.event_id, asset_id=payload.asset_id,
             stream_id=stream_id, brief_task_id=task_id, brief_due_in_seconds=window_secs,
             recurring_detected=recurring_detected)
    return {
        "status": "accepted",
        "event_id": payload.event_id,
        "stream_entry_id": stream_id,
        "brief_task_id": task_id,
        "brief_due_in_seconds": window_secs,
        "recurring_detected": recurring_detected,
        "recurring_brief_task_id": recurring_brief_task_id,
    }


@router.post("/ptw", dependencies=[Depends(demo_llm_budget)], summary="Ingest Permit-to-Work event", status_code=status.HTTP_202_ACCEPTED)
async def ingest_ptw(
    payload: PTWEvent,
    current_user: IngestUserDep,
    redis: RedisDep,
    supabase: SupabaseDep,
    settings: SettingsDep,
    driver: Neo4jDep,
    qdrant: QdrantDep,
    es: ElasticsearchDep,
) -> dict:
    """
    PTW events always trigger a safety brief with mandatory sign-off.
    Immediate, never held by the late-arrival window. It leaves other events' pending briefs
    alone: they go to other recipients. Publishes to PTW stream AND directly to BRIEFS stream
    with priority=critical to bypass the EEMUA 191 governor.
    """
    site_scope(current_user, payload.site_id, write=True)
    tenant.guard_site(current_user, payload.site_id)
    payload.asset_ids = [await _canonical_asset(a, driver, supabase, current_user) for a in payload.asset_ids]
    bus = EventBusService(redis, settings)
    event_dict = payload.model_dump(mode="json")
    primary_asset_id = payload.asset_ids[0] if payload.asset_ids else None

    # Keyed on ptw_id, never on the asset: two distinct permits covering one asset during a
    # turnaround are both real, and dropping the second would drop a safety brief. Only the
    # *same permit* re-reported by a second source system is a duplicate here.
    if await bus.is_duplicate(primary_asset_id or "", payload.event_type, business_id=payload.ptw_id):
        log.info("events.ptw_deduplicated", event_id=payload.event_id, ptw_id=payload.ptw_id)
        return {"status": "deduplicated", "event_id": payload.event_id, "ptw_id": payload.ptw_id}

    await _store_event(supabase, {
        "event_id": payload.event_id,
        "event_type": payload.event_type,
        "source_system": payload.source_system,
        "site_id": payload.site_id,
        "asset_id": primary_asset_id,
        "payload": event_dict,
        "occurred_at": payload.occurred_at.isoformat(),
        "received_at": payload.received_at.isoformat(),
    })

    await _materialise_event_node(
        driver, payload.event_id, payload.event_type,
        payload.occurred_at.isoformat(), primary_asset_id,
    )

    stream_id = await bus.publish_ptw(event_dict)

    # Publish directly to briefs stream with critical priority — bypasses governor
    await bus.publish(settings.REDIS_STREAM_BRIEFS, {
        **event_dict,
        "priority": "critical",
        "trigger_event_type": payload.event_type,
    })

    await asyncio.to_thread(
        lambda sid=stream_id: supabase.table("operational_events")
        .update({"redis_stream_id": sid})
        .eq("event_id", payload.event_id)
        .execute()
    )

    engine = BriefEngine(driver, qdrant, es, supabase, settings)
    brief = await engine.assemble_ptw_brief(payload)
    brief_id = await engine.deliver(brief, redis)

    await bus.mark_seen(primary_asset_id or "", payload.event_type, business_id=payload.ptw_id)

    log.info("events.ptw_ingested", event_id=payload.event_id, ptw_id=payload.ptw_id,
             stream_id=stream_id, brief_id=brief_id)
    return {"status": "accepted", "event_id": payload.event_id, "priority": "critical",
            "stream_entry_id": stream_id, "brief_id": brief_id}


@router.post("/shift-handover", dependencies=[Depends(demo_llm_budget)], summary="Ingest shift handover event", status_code=status.HTTP_202_ACCEPTED)
async def ingest_shift_handover(
    payload: ShiftHandoverEvent,
    current_user: IngestUserDep,
    redis: RedisDep,
    supabase: SupabaseDep,
    settings: SettingsDep,
    driver: Neo4jDep,
    qdrant: QdrantDep,
    es: ElasticsearchDep,
) -> dict:
    """Triggers a shift handover brief for the incoming crew."""
    site_scope(current_user, payload.site_id, write=True)
    tenant.guard_site(current_user, payload.site_id)
    bus = EventBusService(redis, settings)

    # Handovers carry no asset. The crew pair plus the handover time identifies the event, so
    # the same handover posted by both the DCS and the CMMS collapses, while the next shift's
    # handover does not.
    handover_key = (
        f"{payload.outgoing_shift_lead_id}:{payload.incoming_shift_lead_id}:"
        f"{payload.handover_time.isoformat()}"
    )
    if await bus.is_duplicate("", payload.event_type, business_id=handover_key):
        log.info("events.shift_handover_deduplicated", event_id=payload.event_id)
        return {"status": "deduplicated", "event_id": payload.event_id}

    event_dict = payload.model_dump(mode="json")

    await _store_event(supabase, {
        "event_id": payload.event_id,
        "event_type": payload.event_type,
        "source_system": payload.source_system,
        "site_id": payload.site_id,
        "asset_id": None,
        "payload": event_dict,
        "occurred_at": payload.occurred_at.isoformat(),
        "received_at": payload.received_at.isoformat(),
    })

    await _materialise_event_node(
        driver, payload.event_id, payload.event_type,
        payload.occurred_at.isoformat(), None,
    )

    stream_id = await bus.publish_shift_handover(event_dict)

    await asyncio.to_thread(
        lambda sid=stream_id: supabase.table("operational_events")
        .update({"redis_stream_id": sid})
        .eq("event_id", payload.event_id)
        .execute()
    )

    window_secs = settings.LATE_ARRIVAL_WINDOW_MINUTES * 60
    pending_key = f"kairos:brief_pending:shift:{payload.site_id}"
    existing_id = await redis.get(pending_key)
    if existing_id:
        from workers.celery_app import celery_app as _app
        _app.control.revoke(existing_id, terminate=False)
        log.info("events.deferred_shift_brief_revoked", site_id=payload.site_id, revoked_task=existing_id)
    task = assemble_brief.apply_async(args=[payload.event_type, event_dict], countdown=window_secs)
    await redis.setex(pending_key, window_secs + 60, task.id)
    task_id = task.id

    await bus.mark_seen("", payload.event_type, business_id=handover_key)

    log.info("events.shift_handover_ingested", event_id=payload.event_id, stream_id=stream_id,
             brief_task_id=task_id, brief_due_in_seconds=window_secs)
    return {"status": "accepted", "event_id": payload.event_id, "stream_entry_id": stream_id,
            "brief_task_id": task_id, "brief_due_in_seconds": window_secs}


@router.post("/alarm", dependencies=[Depends(demo_llm_budget)], summary="Ingest alarm acknowledgment event", status_code=status.HTTP_202_ACCEPTED)
async def ingest_alarm(
    payload: AlarmEvent,
    current_user: IngestUserDep,
    redis: RedisDep,
    supabase: SupabaseDep,
    settings: SettingsDep,
    driver: Neo4jDep,
) -> dict:
    """Received when an operator acknowledges a DCS process alarm."""
    site_scope(current_user, payload.site_id, write=True)
    tenant.guard_site(current_user, payload.site_id)
    payload.asset_id = await _canonical_asset(payload.asset_id, driver, supabase, current_user)
    bus = EventBusService(redis, settings)

    # Keyed on alarm_id: a chattering instrument raising two *distinct* alarms on one asset is
    # two events; the same alarm relayed by DCS and CMMS is one.
    if await bus.is_duplicate(payload.asset_id, payload.event_type, business_id=payload.alarm_id):
        log.info("events.alarm_deduplicated", event_id=payload.event_id, alarm_id=payload.alarm_id)
        return {"status": "deduplicated", "event_id": payload.event_id, "alarm_id": payload.alarm_id}

    event_dict = payload.model_dump(mode="json")

    await _store_event(supabase, {
        "event_id": payload.event_id,
        "event_type": payload.event_type,
        "source_system": payload.source_system,
        "site_id": payload.site_id,
        "asset_id": payload.asset_id,
        "payload": event_dict,
        "occurred_at": payload.occurred_at.isoformat(),
        "received_at": payload.received_at.isoformat(),
    })

    await _materialise_event_node(
        driver, payload.event_id, payload.event_type,
        payload.occurred_at.isoformat(), payload.asset_id,
    )

    stream_id = await bus.publish(settings.REDIS_STREAM_ALARMS, event_dict)

    await asyncio.to_thread(
        lambda sid=stream_id: supabase.table("operational_events")
        .update({"redis_stream_id": sid})
        .eq("event_id", payload.event_id)
        .execute()
    )

    # Correlate alarm with other events for the same asset within DEDUP_WINDOW_MINUTES
    await bus.correlate_events(payload.asset_id, str(payload.event_id), payload.occurred_at, supabase)

    await bus.mark_seen(payload.asset_id, payload.event_type, business_id=payload.alarm_id)

    log.info("events.alarm_ingested", event_id=payload.event_id, alarm_id=payload.alarm_id,
             stream_id=stream_id)
    return {"status": "accepted", "event_id": payload.event_id, "stream_entry_id": stream_id}


# =============================================================================
# Physical Deviation Flag (Layer 6 / Layer 8)
# =============================================================================

@router.post("/deviation-flag", summary="Flag a physical deviation from engineering drawings", status_code=status.HTTP_202_ACCEPTED)
async def flag_deviation(
    payload: DeviationFlagEvent,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    redis: RedisDep,
    settings: SettingsDep,
    driver: Neo4jDep,
) -> dict:
    """
    Field technicians flag a physical state that does not match engineering drawings.
    Freezes all unacknowledged briefs for the affected asset until an engineer resolves it.
    Publishes to REDIS_STREAM_ALARMS with severity=critical.
    """
    # A technician types the tag painted on the equipment, which may be an alias. Unresolved, the
    # flag froze no briefs (they are keyed by canonical id) and the insert could fail its FK.
    payload.asset_id = await _canonical_asset(payload.asset_id, driver, supabase, current_user)
    # The reporter is the authenticated user, never a name the client sends: this flag freezes
    # every unacknowledged brief for the asset and only an engineer can lift it.
    reported_by = current_user.get("user_id", "unknown")

    deviation_sla = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    insert_result = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items").insert({
            "asset_id": payload.asset_id,
            "content": payload.description,
            "input_type": "deviation_flag",
            "submitted_by": reported_by,
            "sla_due_at": deviation_sla,
            "session_context": {
                "reported_by": reported_by,
                "affected_topology_path": payload.affected_topology_path,
                "asset_id": payload.asset_id,
            },
        }).execute()
    )
    item_id = insert_result.data[0]["item_id"]

    # Freeze all unacknowledged briefs for this asset
    frozen_result = await asyncio.to_thread(
        lambda: supabase.table("briefs")
        .update({"delivery_frozen": True})
        .eq("asset_id", payload.asset_id)
        .is_("acknowledged_at", "null")
        .execute()
    )
    frozen_count = len(frozen_result.data or [])

    bus = EventBusService(redis, settings)
    stream_id = await bus.publish(settings.REDIS_STREAM_ALARMS, {
        "event_type": "deviation_flag",
        "asset_id": payload.asset_id,
        "description": payload.description,
        "severity": "critical",
        "item_id": item_id,
        "reported_by": reported_by,
    })

    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "deviation_flag_raised",
            "entity_type": "quarantine_item",
            "entity_id": item_id,
            "performed_by": reported_by,
            "details": {
                "asset_id": payload.asset_id,
                "description": payload.description,
                "affected_topology_path": payload.affected_topology_path,
                "briefs_frozen": frozen_count,
                "stream_id": stream_id,
            },
        }).execute()
    )

    log.info("events.deviation_flag_raised", item_id=item_id, asset_id=payload.asset_id, frozen_count=frozen_count)
    return {
        "status": "accepted",
        "item_id": item_id,
        "asset_id": payload.asset_id,
        "briefs_frozen": frozen_count,
        "stream_entry_id": stream_id,
    }


@router.post("/deviation-flag/{item_id}/resolve", summary="Resolve a physical deviation flag")
async def resolve_deviation_flag(
    item_id: QuarantineItemIdDep,
    payload: DeviationFlagResolveRequest,
    supabase: SupabaseDep,
    current_user: dict = Depends(require_role("engineer", "admin")),
) -> dict:
    """
    Engineer resolves the deviation flag: promotes or disputes the quarantine item,
    unfreezes affected briefs, and optionally creates a MoC item if a topology change is confirmed.
    """
    if payload.resolution not in ("promoted", "disputed"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="resolution must be 'promoted' or 'disputed'")
    await tenant.guard_row(supabase, current_user, "quarantine_items", item_id)

    result = await asyncio.to_thread(
        lambda: supabase.table("quarantine_items")
        .select("item_id, review_status, asset_id, content")
        .eq("item_id", item_id)
        .eq("input_type", "deviation_flag")
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Deviation flag '{item_id}' not found")
    item = result.data[0]
    if item["review_status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Already '{item['review_status']}'")

    asset_id = item.get("asset_id")
    now_iso = datetime.now(UTC).isoformat()
    reviewer_id = current_user.get("user_id", "unknown")

    await asyncio.to_thread(
        lambda: supabase.table("quarantine_items").update({
            "review_status": payload.resolution,
            "reviewer_id": reviewer_id,
            "reviewed_at": now_iso,
        }).eq("item_id", item_id).execute()
    )

    # Unfreeze briefs for this asset
    unfreeze_result = await asyncio.to_thread(
        lambda: supabase.table("briefs")
        .update({"delivery_frozen": False})
        .eq("asset_id", asset_id)
        .eq("delivery_frozen", True)
        .execute()
    )
    unfrozen_count = len(unfreeze_result.data or [])

    # Create MoC item if topology change confirmed
    moc_id = None
    if payload.moc_warranted:
        moc_id = f"MOC-{shortuuid.uuid()[:8].upper()}"
        await asyncio.to_thread(
            lambda mid=moc_id: supabase.table("moc_items").insert({
                "moc_id": mid,
                "asset_id": asset_id,
                "description": f"Physical deviation confirmed: {item.get('content', '')}. {payload.notes or ''}".strip(),
                "conflicting_sources": [],
                "blast_radius": [],
                "status": "draft",
            }).execute()
        )

    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "deviation_flag_resolved",
            "entity_type": "quarantine_item",
            "entity_id": item_id,
            "performed_by": reviewer_id,
            "details": {
                "asset_id": asset_id,
                "resolution": payload.resolution,
                "moc_warranted": payload.moc_warranted,
                "moc_id": moc_id,
                "notes": payload.notes,
                "briefs_unfrozen": unfrozen_count,
            },
        }).execute()
    )

    log.info("events.deviation_flag_resolved", item_id=item_id, resolution=payload.resolution, moc_id=moc_id)
    return {
        "status": "resolved",
        "item_id": item_id,
        "resolution": payload.resolution,
        "briefs_unfrozen": unfrozen_count,
        "moc_id": moc_id,
    }


@router.post("/plant-state", summary="Set plant operating state for a site", status_code=status.HTTP_202_ACCEPTED)
async def set_plant_state(
    payload: PlantStateEvent,
    supabase: SupabaseDep,
    current_user: dict = Depends(require_role("engineer", "admin")),
) -> dict:
    """
    Sets or updates the plant operating state for a site.
    turnaround/shutdown/emergency suppresses all non-critical briefs for that site.
    """
    site_scope(current_user, payload.site_id, write=True)  # an engineer may only set their own site's state
    tenant.guard_site(current_user, payload.site_id)
    now_iso = datetime.now(UTC).isoformat()
    set_by = current_user.get("user_id", "unknown")

    await asyncio.to_thread(
        lambda: supabase.table("plant_operating_states").insert({
            "site_id": payload.site_id,
            "state": payload.state,
            "set_by": set_by,
            "set_at": now_iso,
            "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
        }).execute()
    )
    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "plant_state_changed",
            "entity_type": "site",
            "entity_id": payload.site_id,
            "performed_by": set_by,
            "details": {
                "state": payload.state,
                "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
            },
        }).execute()
    )
    log.info("events.plant_state_set", site_id=payload.site_id, state=payload.state, set_by=set_by)
    # The page renders "Set by … · when" straight from this response; returning neither left it
    # reading "Set by · —" after every change.
    return {
        "status": "set",
        "site_id": payload.site_id,
        "state": payload.state,
        "set_by": await display_name(supabase, set_by) or set_by,
        "set_at": now_iso,
        "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
    }


@router.post("/tag-out", dependencies=[Depends(demo_llm_budget)], summary="Ingest equipment tag-out event", status_code=status.HTTP_202_ACCEPTED)
async def ingest_tag_out(
    payload: TagOutEvent,
    current_user: IngestUserDep,
    redis: RedisDep,
    supabase: SupabaseDep,
    settings: SettingsDep,
    driver: Neo4jDep,
) -> dict:
    """
    Receives an equipment tag-out event. Deduplicates, publishes to TAG_OUT stream,
    inserts into operational_events, triggers delayed brief assembly.
    """
    site_scope(current_user, payload.site_id, write=True)
    tenant.guard_site(current_user, payload.site_id)
    payload.asset_id = await _canonical_asset(payload.asset_id, driver, supabase, current_user)
    bus = EventBusService(redis, settings)

    if await bus.is_duplicate(payload.asset_id, payload.event_type):
        log.info("events.tag_out_deduplicated", event_id=payload.event_id, asset_id=payload.asset_id)
        return {"status": "deduplicated", "event_id": payload.event_id}

    event_dict = payload.model_dump(mode="json")

    await _store_event(supabase, {
        "event_id": payload.event_id,
        "event_type": payload.event_type,
        "source_system": payload.source_system,
        "site_id": payload.site_id,
        "asset_id": payload.asset_id,
        "payload": event_dict,
        "occurred_at": payload.occurred_at.isoformat(),
        "received_at": payload.received_at.isoformat(),
        "event_subtype": None,
    })

    await _materialise_event_node(
        driver, payload.event_id, payload.event_type,
        payload.occurred_at.isoformat(), payload.asset_id,
    )

    stream_id = await bus.publish(settings.REDIS_STREAM_TAG_OUT, event_dict)

    await asyncio.to_thread(
        lambda sid=stream_id: supabase.table("operational_events")
        .update({"redis_stream_id": sid})
        .eq("event_id", payload.event_id)
        .execute()
    )

    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "equipment_tag_out",
            "entity_type": "asset",
            "entity_id": payload.asset_id,
            "performed_by": current_user.get("user_id", "unknown"),
            "details": {
                "reported_performed_by": payload.performed_by,  # source-system claim, unverified
                "tag_out_reason": payload.tag_out_reason,
                "expected_return_date": payload.expected_return_date.isoformat() if payload.expected_return_date else None,
                "stream_id": stream_id,
            },
        }).execute()
    )

    window_secs = settings.LATE_ARRIVAL_WINDOW_MINUTES * 60
    task = assemble_brief.apply_async(args=[payload.event_type, event_dict], countdown=window_secs)

    await bus.mark_seen(payload.asset_id, payload.event_type)

    log.info("events.tag_out_ingested", event_id=payload.event_id, asset_id=payload.asset_id,
             stream_id=stream_id, brief_task_id=task.id)
    return {
        "status": "accepted",
        "event_id": payload.event_id,
        "stream_entry_id": stream_id,
        "brief_task_id": task.id,
        "brief_due_in_seconds": window_secs,
    }


@router.post("/inspection-complete", dependencies=[Depends(demo_llm_budget)], summary="Ingest inspection completion event", status_code=status.HTTP_202_ACCEPTED)
async def ingest_inspection_complete(
    payload: InspectionCompleteEvent,
    current_user: IngestUserDep,
    redis: RedisDep,
    supabase: SupabaseDep,
    settings: SettingsDep,
    driver: Neo4jDep,
) -> dict:
    """
    Receives an inspection completion event. Creates a Neo4j knowledge edge if document_id
    provided, and that document must be an inspection report already in the vault: the edge is
    compliance evidence, so it cannot point at an id the caller made up. Triggers brief on failed
    result or non-empty findings. Correlates with other events for the same asset.
    """
    from api.services.graph import GraphService

    site_scope(current_user, payload.site_id, write=True)
    tenant.guard_site(current_user, payload.site_id)
    payload.asset_id = await _canonical_asset(payload.asset_id, driver, supabase, current_user)

    if payload.document_id:
        doc = await asyncio.to_thread(
            lambda: supabase.table("documents")
            .select("document_id, document_type")
            .eq("document_id", payload.document_id)
            .limit(1)
            .execute()
        )
        if not doc.data or doc.data[0].get("document_type") != "inspection_report":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="document_id must be an inspection_report already in the vault.",
            )

    # Scoped by inspection_type so a statutory and a routine inspection closing on the same
    # asset within the window are both recorded; only the same inspection re-reported collapses.
    if await EventBusService(redis, settings).is_duplicate(
        payload.asset_id, payload.event_type, business_id=f"{payload.asset_id}:{payload.inspection_type}"
    ):
        log.info("events.inspection_deduplicated", event_id=payload.event_id, asset_id=payload.asset_id)
        return {"status": "deduplicated", "event_id": payload.event_id}

    now = datetime.now(UTC)
    event_dict = payload.model_dump(mode="json")

    # Recorded first, as the system of record: if the graph edge or the quarantine row below
    # fails, the event is already stored and a retry (`_store_event` accepts an
    # identical re-post) finishes the job.
    await _store_event(supabase, {
        "event_id": payload.event_id,
        "event_type": payload.event_type,
        "source_system": payload.source_system,
        "site_id": payload.site_id,
        "asset_id": payload.asset_id,
        "payload": event_dict,
        "occurred_at": payload.occurred_at.isoformat(),
        "received_at": payload.received_at.isoformat(),
    })

    await _materialise_event_node(
        driver, payload.event_id, payload.event_type,
        payload.occurred_at.isoformat(), payload.asset_id,
    )

    # Create Neo4j knowledge edge if a supporting document is referenced
    edge_id = None
    if payload.document_id:
        graph = GraphService(driver)
        await graph.merge_document_node(
            payload.document_id,
            {
                # document_type is required for clause evidence matching in
                # /compliance/{gaps,audit-pack}; an untyped Document counts as no evidence.
                "document_type": "inspection_report",
                "inspection_type": payload.inspection_type,
                "result": payload.result,
            },
        )
        edge_result = await graph.create_knowledge_edge(
            source_id=payload.asset_id,
            source_label="Asset",
            target_id=payload.document_id,
            target_label="Document",
            relationship_type="INSPECTION_RECORD",
            valid_from=now,
            authority_level=4,
            document_id=payload.document_id,
            # The reporter can lower the edge's confidence (routing it to human review) but never
            # raise it above the server's own figure.
            confidence=min(payload.confidence, INSPECTION_EVIDENCE_CONFIDENCE),
            verification_status="unverified",
        )
        edge_id = edge_result.get("edge_id")

    # Quarantine low-confidence findings
    quarantine_item_id = None
    if payload.confidence < 0.7:
        qi = await asyncio.to_thread(
            lambda: supabase.table("quarantine_items").insert({
                "asset_id": payload.asset_id,
                "content": f"Inspection {payload.inspection_type}: {payload.findings or payload.result}",
                "input_type": "field_observation",
                "submitted_by": current_user.get("user_id", "unknown"),
                "session_context": {
                    "inspection_type": payload.inspection_type,
                    "result": payload.result,
                    "confidence": payload.confidence,
                    "document_id": payload.document_id,
                },
            }).execute()
        )
        quarantine_item_id = qi.data[0]["item_id"]

    bus = EventBusService(redis, settings)
    brief_task_id = None
    trigger_brief = payload.result == "failed" or bool(payload.findings)

    if trigger_brief:
        stream_id = await bus.publish(settings.REDIS_STREAM_WORK_ORDERS, event_dict)
        task = assemble_brief.apply_async(args=["inspection_complete", event_dict], countdown=0)
        brief_task_id = task.id
    else:
        stream_id = await bus.publish(settings.REDIS_STREAM_INSPECTIONS, event_dict)

    await asyncio.to_thread(
        lambda sid=stream_id: supabase.table("operational_events")
        .update({"redis_stream_id": sid})
        .eq("event_id", payload.event_id)
        .execute()
    )

    # Correlate with other events for same asset
    await bus.correlate_events(payload.asset_id, str(payload.event_id), payload.occurred_at, supabase)

    await bus.mark_seen(
        payload.asset_id, payload.event_type, business_id=f"{payload.asset_id}:{payload.inspection_type}"
    )

    log.info("events.inspection_complete_ingested", event_id=payload.event_id, asset_id=payload.asset_id,
             result=payload.result, edge_id=edge_id, brief_triggered=trigger_brief)
    return {
        "status": "accepted",
        "event_id": payload.event_id,
        "stream_entry_id": stream_id,
        "edge_id": edge_id,
        "quarantine_item_id": quarantine_item_id,
        "brief_task_id": brief_task_id,
    }


@router.get("/plant-state/{site_id}", summary="Get current plant operating state for a site")
async def get_plant_state_endpoint(
    site_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> dict:
    """Returns the active plant operating state for the operator dashboard banner."""
    site_id = site_scope(current_user, site_id)  # admin: any site; others: only their own
    bus = EventBusService(redis, settings)
    state = await bus.get_plant_state(site_id, supabase)
    # Who set it and when, for the "Set by … · when" line. No row (or an expired one) means the site
    # is on its configured default, which nobody set.
    latest = await asyncio.to_thread(
        lambda: supabase.table("plant_operating_states")
        .select("state, set_by, set_at, expires_at")
        .eq("site_id", site_id)
        .order("set_at", desc=True)
        .limit(1)
        .execute()
    )
    row = (latest.data or [None])[0]
    if not row or row.get("state") != state:
        return {"site_id": site_id, "state": state, "set_by": None, "set_at": None, "expires_at": None}
    return {
        "site_id": site_id,
        "state": state,
        "set_by": await display_name(supabase, row.get("set_by")) or row.get("set_by"),
        "set_at": row.get("set_at"),
        "expires_at": row.get("expires_at"),
    }


@router.get("/", summary="List operational events")
async def list_events(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    event_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """Returns the paginated event feed used by the operational-events workspace."""
    site = site_scope(current_user, None)  # None for admin (all sites); everyone else sees their own

    def fetch_events():
        query = (
            supabase.table("operational_events")
            .select("event_id,event_type,event_subtype,asset_id,site_id,occurred_at,payload", count="exact")
            .order("occurred_at", desc=True)
        )
        if event_type:
            query = query.eq("event_type", event_type)
        query = tenant.pin_site(query, current_user, site)
        query = tenant.scope_site(query, current_user)
        return query.range(offset, offset + limit - 1).execute()

    result = await asyncio.to_thread(fetch_events)
    items = [
        {
            **event,
            "priority": (event.get("payload") or {}).get("priority", "normal"),
            "acknowledged": False,
        }
        for event in (result.data or [])
    ]
    return {"items": items, "total": result.count or 0, "limit": limit, "offset": offset}


@router.get("/{event_id}", summary="Get event with correlated event IDs")
async def get_event(
    event_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """Returns an operational event with its correlated_event_ids for the frontend audit trail."""
    result = await asyncio.to_thread(
        lambda: supabase.table("operational_events")
        .select("event_id, event_type, asset_id, site_id, occurred_at, payload, compound_event_id, redis_stream_id, received_at")
        .eq("event_id", event_id)
        .execute()
    )
    site = site_scope(current_user, None)
    if not result.data or not tenant.on_visible_site(current_user, result.data[0].get("site_id"), site):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event '{event_id}' not found")

    event = result.data[0]
    correlated_event_ids: list = []
    if event.get("compound_event_id"):
        corr = await asyncio.to_thread(
            lambda: supabase.table("operational_events")
            .select("event_id")
            .eq("compound_event_id", event["compound_event_id"])
            .neq("event_id", event_id)
            .execute()
        )
        correlated_event_ids = [r["event_id"] for r in (corr.data or [])]

    return {**event, "correlated_event_ids": correlated_event_ids}


@router.post("/{event_id}/ack", summary="Acknowledge receipt of a brief")
async def acknowledge_event(
    event_id: str,
    payload: EventAck,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """
    Records cryptographically signed acknowledgment of a proactive brief.
    Audit trail: what knowledge was available, when delivered, confirmed by whom.

    Who, in what role, when and the signature are all produced here from the verified token and the
    server clock. The body's `user_id`, `role`, `acknowledged_at` and `signature` are ignored: the
    audit trail the compliance role reads must not show acknowledgements the named person never made.
    """
    user_id = current_user.get("user_id", "unknown")
    await tenant.guard_row(supabase, current_user, "operational_events", event_id)

    # Each ack is a server-signed audit row, so it needs an event that exists on the caller's site
    # (same 404 as `get_event`) and a caller with a stake in it: staff, or the recipient of a brief
    # that event triggered. Otherwise any role could mint unlimited signed rows for any id.
    site = site_scope(current_user, None)
    event = await asyncio.to_thread(
        lambda: supabase.table("operational_events")
        .select("event_id, site_id")
        .eq("event_id", event_id)
        .limit(1)
        .execute()
    )
    if not event.data or not tenant.on_visible_site(current_user, event.data[0].get("site_id"), site):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Event '{event_id}' not found")
    if not tenant.has_role(current_user, *_INGEST_ROLES):
        brief = await asyncio.to_thread(
            lambda: supabase.table("briefs")
            .select("brief_id")
            .eq("trigger_event_id", event_id)
            .in_("recipient_user_id", _brief_recipients(current_user))
            .limit(1)
            .execute()
        )
        if not brief.data:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a recipient of this event.")

    # Idempotent: one acknowledgement per user per event, a repeat returns the first.
    # ponytail: check-then-insert, so two simultaneous first acks can both write; a unique index
    # on audit_log would close that and is a schema change.
    prior = await asyncio.to_thread(
        lambda: supabase.table("audit_log")
        .select("id")
        .eq("action", "brief_acknowledged")
        .eq("entity_id", event_id)
        .eq("performed_by", user_id)
        .limit(1)
        .execute()
    )
    if prior.data:
        return {"status": "acknowledged", "event_id": event_id, "user_id": user_id, "repeat": True}

    now = datetime.now(UTC).isoformat()
    signature = _sign_acknowledgment(app_settings.APP_SECRET_KEY, event_id, user_id, "acknowledged", now)
    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "brief_acknowledged",
            "entity_type": "event",
            "entity_id": event_id,
            "performed_by": user_id,
            "details": {
                "event_id": event_id,
                "timestamp": now,
                "signature": signature,
                "signature_alg": "HMAC-SHA256",
                "role": current_user.get("role"),
                "notes": payload.notes,
            },
        }).execute()
    )
    log.info("events.brief_acknowledged", event_id=event_id, user_id=user_id)
    return {"status": "acknowledged", "event_id": event_id, "user_id": user_id}
