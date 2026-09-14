"""Service-free: the RCA timeline shows each event once, ordered on a single UTC clock."""

from api.services.timeline import merge_timeline


def test_the_same_event_from_both_stores_appears_once_with_its_description():
    supabase = [{"event_id": "E1", "occurred_at": "2026-09-13T14:30:25+00:00", "description": "Seal weep", "source": "operational_events"}]
    neo4j = [{"event_id": "E1", "occurred_at": "2026-09-13T14:30:25", "description": "", "source": "neo4j"}]

    timeline = merge_timeline(supabase, neo4j)

    assert len(timeline) == 1
    assert timeline[0]["description"] == "Seal weep"
    assert timeline[0]["occurred_at"] == "2026-09-13T14:30:25+00:00"


def test_offsets_are_ordered_by_instant_not_by_string():
    # 05:58+05:30 is 00:28 UTC — before 01:00 UTC, though it sorts after it as a string.
    events = [
        {"event_id": "LATER", "occurred_at": "2026-07-15T01:00:00+00:00"},
        {"event_id": "EARLIER", "occurred_at": "2026-07-15T05:58:00+05:30"},
    ]

    assert [e["event_id"] for e in merge_timeline(events)] == ["EARLIER", "LATER"]


def test_a_naive_timestamp_is_read_as_utc():
    timeline = merge_timeline([{"event_id": "E1", "occurred_at": "2026-09-13T14:30:25.911558"}])

    assert timeline[0]["occurred_at"] == "2026-09-13T14:30:25.911558+00:00"


def test_events_without_an_id_are_kept_not_collapsed():
    events = [{"occurred_at": "2026-01-01T00:00:00Z", "description": "a"}, {"occurred_at": "2026-01-01T00:00:00Z", "description": "b"}]

    assert len(merge_timeline(events)) == 2
