"""
Re-date the demo data so it reads as current, without changing what happened or in what order.

The golden dataset's events carry fixed dates (2026-03-22, 2026-07-15), copied verbatim by
`load_demo_dataset.py`. As the calendar moves on they age out of the RCA and recurring-failure
windows and every "2mo ago" label gets older. Everything else the loader writes (SLA deadlines,
brief times) is already relative to load time and is left alone — overdue SLAs are real content.

Algorithm: one anchor, one whole-day delta, applied to every golden-event timestamp.

    anchor = newest golden event's occurred_at
    delta  = (now - 1 day) - anchor, rounded to whole days    # newest reads as "yesterday"
    t     := t + delta

Only GOLDEN events move: the rows the loader created from `dataset/04_Events_And_Quarantine/`,
identified with the loader's own mapping by (source_system, event_type, work order / PTW id / shift
lead). Events created live during a demo or by a QA sweep never match, so they can neither become
the anchor nor be pushed into the future. Spacing and time of day are kept; a same-day re-run is 0.

Off-boarding programmes are anchored separately (first interview -> yesterday), because their dates
come from load time, not from the dataset. Showcase programmes (a `DEMO-` person) are skipped:
`redate_showcase.py` owns them, and anchoring them here would flatten their staggered schedules.

Writes, in an order that makes a re-run after any failure safe:
  1. Neo4j `Event.occurred_at` — absolute values computed from Supabase's pre-state, so a repeat
     writes the same values.
  2. `operational_events` — one bulk upsert, i.e. one transaction. This moves the anchor, so it
     goes last among the event writes.
  3. Per off-boarding programme: the session's retirement date, then its items in one bulk upsert;
     if the items fail, the retirement date is put back before the error is raised.

This WRITES TO THE CLOUD GOLDEN STORES with --apply. Dry-run by default: logs the plan only.

    python scripts/redate_demo.py            # dry run
    python scripts/redate_demo.py --apply    # write
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

sys.path.insert(0, "/app")

import structlog
from neo4j import GraphDatabase
from supabase import create_client

from api.config import Settings
from api.services.tenant import is_demo_id
from scripts.load_demo_dataset import DATASET_DIR, _event_endpoint_and_body

log = structlog.get_logger(__name__)

# Loader endpoint -> the event_type that endpoint stores.
_STORED_TYPE = {
    "/events/work-order": "work_order_created",
    "/events/ptw": "ptw_generated",
    "/events/shift-handover": "shift_handover",
}
# The business id each event type carries in its stored payload; the first present one is the identity.
_KEY_FIELDS = ("work_order_id", "ptw_id", "outgoing_shift_lead_id")
# Points on the event's own timeline. `received_at` is excluded: it is when *Kairos* received the
# event, and moving it would invent an ingest history.
_PAYLOAD_TIME_FIELDS = ("occurred_at", "handover_time", "planned_start")


def _key(source_system: str, event_type: str, fields: dict) -> tuple:
    return source_system, event_type, next((fields[f] for f in _KEY_FIELDS if fields.get(f)), None)


def golden_keys(dataset_events: list[dict]) -> set[tuple]:
    """Identity of every event the loader stores from these dataset JSONs."""
    keys = set()
    for ev in dataset_events:
        # Persona ids are not part of the identity, so any placeholder will do.
        mapped = _event_endpoint_and_body(ev, defaultdict(str))
        if mapped:
            endpoint, body = mapped
            keys.add(_key(body["source_system"], _STORED_TYPE[endpoint], body))
    return keys


def _shift(value: str, delta: timedelta) -> str:
    """Shift an ISO timestamp, keeping its original UTC offset."""
    return (datetime.fromisoformat(value) + delta).isoformat()


def _delta_to_yesterday(anchor: datetime, now: datetime) -> timedelta:
    # Whole days: keeps every event's time of day and makes a same-day re-run an exact no-op.
    return timedelta(days=round(((now - timedelta(days=1)) - anchor).total_seconds() / 86400))


def plan_events(rows: list[dict], keys: set[tuple], now: datetime) -> tuple[timedelta, list[tuple[dict, dict, str]]]:
    """Return the delta and, per golden event, (old row, new row, new Neo4j occurred_at)."""
    golden = [r for r in rows if _key(r["source_system"], r["event_type"], r.get("payload") or {}) in keys]
    if not golden:
        return timedelta(0), []
    delta = _delta_to_yesterday(max(datetime.fromisoformat(r["occurred_at"]) for r in golden), now)
    changes = []
    for r in golden:
        payload = dict(r.get("payload") or {})
        for field in _PAYLOAD_TIME_FIELDS:
            if isinstance(payload.get(field), str):
                payload[field] = _shift(payload[field], delta)
        occurred = _shift(r["occurred_at"], delta)
        # The event routes write the payload's own ISO string (its source offset) to Neo4j, and
        # graph.py compares it as a string, so keep that representation rather than Supabase's UTC.
        changes.append(({**r}, {**r, "occurred_at": occurred, "payload": payload}, payload.get("occurred_at") or occurred))
    return delta, changes


def golden_sessions(sessions: list[dict]) -> list[dict]:
    """The off-boarding programmes this script may move: every one that is not a showcase row."""
    return [s for s in sessions if not is_demo_id(s.get("personnel_id"))]


def plan_offboarding(session: dict, items: list[dict], now: datetime) -> tuple[timedelta, str | None, list[dict]]:
    """Return the delta, the new retirement date and the shifted item rows."""
    scheduled = [i for i in items if i.get("scheduled_for")]
    if not scheduled:
        return timedelta(0), session.get("retirement_date"), []
    delta = _delta_to_yesterday(min(datetime.fromisoformat(i["scheduled_for"]) for i in scheduled), now)
    retirement = session.get("retirement_date")
    if retirement:
        retirement = (date.fromisoformat(retirement) + delta).isoformat()
    return delta, retirement, [{**i, "scheduled_for": _shift(i["scheduled_for"], delta)} for i in scheduled]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the shift; otherwise log the plan only")
    args = parser.parse_args()

    settings = Settings()
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    now = datetime.now(UTC)
    log.info("redate.mode", apply=args.apply,
             note="writing to the cloud stores" if args.apply else "dry run, nothing written; pass --apply")

    dataset_events = [json.loads(p.read_text())
                      for p in sorted((DATASET_DIR / "04_Events_And_Quarantine").glob("event_*.json"))]
    keys = golden_keys(dataset_events)
    # ponytail: unpaginated, filtered to the dataset's own source systems and types; the loader writes
    # a handful of such rows, so PostgREST's 1,000-row page is never the ceiling.
    rows = (supabase.table("operational_events").select("*")
            .in_("source_system", sorted({k[0] for k in keys}))
            .in_("event_type", sorted({k[1] for k in keys}))
            .execute()).data or []
    delta, changes = plan_events(rows, keys, now)
    log.info("redate.events", golden=len(changes), expected=len(keys), shift_days=delta.days)
    for old, new, _ in sorted(changes, key=lambda c: c[1]["occurred_at"]):
        log.info("redate.event", type=old["event_type"], asset=old.get("asset_id"),
                 before=old["occurred_at"], after=new["occurred_at"])

    offboarding = []
    sessions = supabase.table("offboarding_sessions").select("id, retirement_date, personnel_id").execute().data or []
    for s in golden_sessions(sessions):
        items = supabase.table("offboarding_session_items").select("*").eq("session_id", s["id"]).execute().data or []
        off_delta, retirement, new_items = plan_offboarding(s, items, now)
        offboarding.append((s, retirement, new_items))
        log.info("redate.offboarding", session=s["id"], shift_days=off_delta.days,
                 retirement_before=s.get("retirement_date"), retirement_after=retirement, interviews=len(new_items))

    if not args.apply:
        return

    if changes:
        with GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)) as driver:
            driver.execute_query(
                "UNWIND $rows AS row MATCH (e:Event {event_id: row.id}) SET e.occurred_at = row.occurred_at",
                rows=[{"id": str(new["event_id"]), "occurred_at": neo4j_occ} for _, new, neo4j_occ in changes],
            )
        supabase.table("operational_events").upsert([new for _, new, _ in changes], on_conflict="event_id").execute()

    for s, retirement, new_items in offboarding:
        if not new_items:
            continue
        supabase.table("offboarding_sessions").update({"retirement_date": retirement}).eq("id", s["id"]).execute()
        try:
            supabase.table("offboarding_session_items").upsert(new_items, on_conflict="id").execute()
        except Exception:
            # Put the retirement date back so a re-run starts from a consistent programme.
            supabase.table("offboarding_sessions").update(
                {"retirement_date": s.get("retirement_date")}).eq("id", s["id"]).execute()
            raise
    log.info("redate.done")


if __name__ == "__main__":
    main()
