"""Keep the showcase plant current: shift its history forward so it always reads as recent.

The showcase is generated relative to its load time, so a month later its newest event is a month old.
`redate` moves every loader-written row forward by a whole number of days, the newest event landing on
"yesterday", and keeps order, spacing and time of day. Same idea as `scripts/redate_demo.py` for the
golden data, and the same discipline:

  * It moves only the rows the loader wrote, found by their deterministic ids (`build_showcase` is
    the list). A row a visitor created during a demo has a random id and is never matched, so it can
    neither become the anchor nor be pushed into the future.
  * It only UPDATES time columns. No row is created or deleted, and nothing outside the showcase
    markers is read for writing.
  * A same-day re-run shifts by zero.

`plan` is pure (tested without a store); `apply_plan` writes.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

TIME_COLUMNS: dict[str, tuple[str, ...]] = {
    "operational_events": ("occurred_at", "received_at"),
    "briefs": ("created_at", "delivered_at", "acknowledged_at", "countersigned_at"),
    "brief_feedback": ("submitted_at",),
    "knowledge_conflicts": ("created_at", "sla_deadline", "escalated_at", "resolved_at"),
    "moc_items": ("created_at", "approved_at"),
    "quarantine_items": ("submitted_at", "reviewed_at", "sla_due_at", "escalated_at"),
    "elicitation_sessions": ("created_at", "updated_at"),
    "offboarding_sessions": ("created_at", "retirement_date"),
    "offboarding_session_items": ("scheduled_for", "completed_at"),
    "plant_operating_states": ("set_at", "expires_at"),
}
PRIMARY_KEY = {
    "operational_events": "event_id", "briefs": "brief_id", "brief_feedback": "id", "knowledge_conflicts": "conflict_id",
    "moc_items": "moc_id", "quarantine_items": "item_id", "elicitation_sessions": "session_id",
    "offboarding_sessions": "id", "offboarding_session_items": "id", "plant_operating_states": "id",
}
# Time-valued keys inside an event's JSON payload.
PAYLOAD_TIME_KEYS = ("occurred_at", "received_at", "handover_time", "expected_return_date", "planned_start")


def shift_value(value: Any, delta: timedelta) -> Any:
    """A timestamp (or a date-only string) moved by `delta`; anything else is returned untouched."""
    if not isinstance(value, str) or not value:
        return value
    try:
        if len(value) == 10:  # a DATE column
            return (datetime.fromisoformat(value) + delta).date().isoformat()
        return (datetime.fromisoformat(value.replace("Z", "+00:00")) + delta).isoformat()
    except ValueError:
        return value


def delta_for(newest_event_iso: str, now: datetime) -> timedelta:
    """Whole days that put the newest loader event on yesterday. Zero when it already is, or later."""
    newest = datetime.fromisoformat(newest_event_iso.replace("Z", "+00:00"))
    days = int(((now - timedelta(days=1)) - newest).total_seconds() // 86400)
    return timedelta(days=max(days, 0))


def shift_row(table: str, row: dict, delta: timedelta) -> dict:
    """The full row with its time columns moved. Full, not partial: an upsert of a partial row would
    fail the table's NOT NULL columns before reaching the conflict."""
    out = dict(row)
    for col in TIME_COLUMNS[table]:
        if col in out:
            out[col] = shift_value(out[col], delta)
    if table == "operational_events" and isinstance(out.get("payload"), dict):
        payload = dict(out["payload"])
        for key in PAYLOAD_TIME_KEYS:
            if key in payload:
                payload[key] = shift_value(payload[key], delta)
        out["payload"] = payload
    return out


def plan(rows_by_table: dict[str, list[dict]], now: datetime) -> tuple[timedelta, dict[str, list[dict]]]:
    """(delta, rows to write) for the loader's rows as they are stored now."""
    events = rows_by_table.get("operational_events") or []
    if not events:
        return timedelta(0), {}
    newest = max(e["occurred_at"] for e in events)
    delta = delta_for(newest, now)
    if not delta:
        return delta, {}
    return delta, {t: [shift_row(t, r, delta) for r in rows] for t, rows in rows_by_table.items() if rows}


def loader_ids(sc) -> dict[str, list[str]]:
    """The primary keys of every row the loader wrote, by table. Deterministic, so also on a re-run."""
    return {table: [r[PRIMARY_KEY[table]] for r in sc.tables()[table]] for table in PRIMARY_KEY}


def fetch_rows(sb, ids: dict[str, list[str]]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for table, keys in ids.items():
        rows: list[dict] = []
        for i in range(0, len(keys), 100):
            rows += sb.table(table).select("*").in_(PRIMARY_KEY[table], keys[i:i + 100]).execute().data or []
        out[table] = rows
    return out


def apply_plan(sb, driver_session, writes: dict[str, list[dict]]) -> None:
    """Write shifted rows (events last, because they carry the anchor, so a failed run is repeatable)."""
    for table in [t for t in writes if t != "operational_events"] + (["operational_events"] if "operational_events" in writes else []):
        rows = writes[table]
        for i in range(0, len(rows), 100):
            sb.table(table).upsert(rows[i:i + 100], on_conflict=PRIMARY_KEY[table]).execute()
    if driver_session is not None and "operational_events" in writes:
        driver_session.run(
            "UNWIND $rows AS r MATCH (e:Event {event_id: r.event_id}) SET e.occurred_at = r.occurred_at",
            rows=[{"event_id": r["event_id"], "occurred_at": r["occurred_at"]} for r in writes["operational_events"]],
        )


def redate(sb, driver, sc, *, apply: bool, now: datetime | None = None) -> dict:
    """Plan (and with `apply` perform) the shift. Returns what was, or would be, done."""
    now = now or datetime.now(UTC)
    rows = fetch_rows(sb, loader_ids(sc))
    delta, writes = plan(rows, now)
    summary = {"days": delta.days, "rows": {t: len(r) for t, r in writes.items()}, "applied": False}
    if apply and writes:
        if driver is not None:
            with driver.session() as session:
                apply_plan(sb, session, writes)
        else:
            apply_plan(sb, None, writes)
        summary["applied"] = True
    return summary


if __name__ == "__main__":  # pragma: no cover - the CLI is scripts/redate_showcase.py
    print(json.dumps({"hint": "run scripts/redate_showcase.py"}))
