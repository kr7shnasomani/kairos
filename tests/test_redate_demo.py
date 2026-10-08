"""The demo re-date shift must move only the golden story, preserve it, and be safe to re-run.

Pure functions over in-memory rows. No stack, no secrets, no network.
"""

from datetime import UTC, datetime

from scripts.redate_demo import golden_keys, golden_sessions, plan_events, plan_offboarding

NOW = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)

# Shaped like the files in dataset/04_Events_And_Quarantine/.
DATASET = [
    {"event_id": "EVT-2026-032201", "event_type": "recurring_failure_detected", "source_system": "CMMS",
     "timestamp": "2026-03-22T09:15:00+05:30", "canonical_asset_id": "EQ-102", "payload": {}},
    {"event_id": "EVT-2026-071503", "event_type": "shift_handover", "source_system": "SHIFT_SCHEDULING",
     "timestamp": "2026-07-15T18:00:00+05:30", "payload": {"outgoing_shift_lead": "Vikram Desai"}},
]

# Shaped like the operational_events rows the loader stores from those files.
ROWS = [
    {"event_id": "a", "event_type": "work_order_created", "source_system": "CMMS",
     "occurred_at": "2026-03-22T03:45:00+00:00",
     "payload": {"work_order_id": "EVT-2026-032201", "occurred_at": "2026-03-22T09:15:00+05:30"}},
    {"event_id": "b", "event_type": "shift_handover", "source_system": "SHIFT_SCHEDULING",
     "occurred_at": "2026-07-15T12:30:00+00:00",
     "payload": {"outgoing_shift_lead_id": "Vikram Desai", "occurred_at": "2026-07-15T18:00:00+05:30",
                 "handover_time": "2026-07-15T18:00:00+05:30"}},
    # Created live in the UI, newer than the story: must neither anchor nor move.
    {"event_id": "live", "event_type": "work_order_created", "source_system": "manual",
     "occurred_at": "2026-09-14T10:27:03+00:00", "payload": {"work_order_id": "WO-QA-20260914-155635"}},
]


def _plan(rows=ROWS, now=NOW):
    return plan_events(rows, golden_keys(DATASET), now)


def test_only_golden_events_move():
    _, changes = _plan()
    assert {old["event_id"] for old, _, _ in changes} == {"a", "b"}


def test_newest_golden_event_lands_yesterday_and_spacing_is_kept():
    delta, changes = _plan()
    new = {old["event_id"]: n["occurred_at"] for old, n, _ in changes}
    assert new["b"] == "2026-09-26T12:30:00+00:00"
    gap = datetime.fromisoformat(new["b"]) - datetime.fromisoformat(new["a"])
    assert gap == datetime.fromisoformat(ROWS[1]["occurred_at"]) - datetime.fromisoformat(ROWS[0]["occurred_at"])
    assert delta.seconds == 0  # whole days: time of day is preserved


def test_payload_and_neo4j_keep_the_source_offset():
    _, changes = _plan()
    _, new, neo4j = {old["event_id"]: c for c in changes for old in [c[0]]}["b"]
    assert new["payload"]["handover_time"] == "2026-09-26T18:00:00+05:30"
    assert neo4j == "2026-09-26T18:00:00+05:30"  # what the event routes wrote, not Supabase's UTC


def test_rerun_on_the_same_day_is_a_no_op():
    _, changes = _plan()
    delta, _ = _plan([n for _, n, _ in changes] + [ROWS[2]], NOW.replace(hour=20))
    assert delta.days == 0


def test_offboarding_first_interview_lands_yesterday():
    session = {"id": "s", "retirement_date": "2026-09-30"}
    items = [{"id": "i1", "scheduled_for": "2026-09-13T19:10:54+00:00"},
             {"id": "i2", "scheduled_for": "2026-09-20T19:10:44+00:00"}]
    _, retirement, new_items = plan_offboarding(session, items, NOW)
    assert retirement == "2026-10-13"
    assert new_items[0]["scheduled_for"].startswith("2026-09-26")


def test_showcase_offboarding_programmes_are_left_to_the_showcase_redate():
    sessions = [{"id": "a", "personnel_id": "EMP-001"}, {"id": "b", "personnel_id": "DEMO-EMP-7"}, {"id": "c"}]
    assert [s["id"] for s in golden_sessions(sessions)] == ["a", "c"]
