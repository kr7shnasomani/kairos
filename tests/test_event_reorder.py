"""Layer 8 delay compensation — ARCHITECTURE.md §Layer 8, third normalization operation.

The architecture asks for out-of-sequence events to be "buffered and reordered before being
committed to the trigger queue", with a configurable late-arrival window.

Kairos implements this by delaying the **derived output** rather than the source of record:
events are written to `operational_events` immediately, and brief assembly is deferred by
`LATE_ARRIVAL_WINDOW_MINUTES`. A later event for the same asset revokes the pending task and
re-enqueues, so the brief waits for stragglers; assembly then reads events back ordered by
`occurred_at`, which is where the reordering happens. Nothing is ever held in a buffer that
could lose it.

The load-bearing exemption is PTW. A uniform hold would deliver a safety brief *after* the
permit was issued, so PTW is immediate. It leaves other events' pending briefs alone: they go to
other recipients (the technician, the site), and their assembly already reads the permit back
from `operational_events`.

Source inspection. No stack, no secrets, no network.
"""

import asyncio
import inspect
from types import SimpleNamespace

from api.config import Settings
from api.routers import events as events_router

SOURCE = inspect.getsource(events_router)


def test_late_arrival_window_is_configurable():
    s = Settings()
    assert s.LATE_ARRIVAL_WINDOW_MINUTES > 0
    assert "LATE_ARRIVAL_WINDOW_MINUTES * 60" in SOURCE, (
        "brief assembly must be deferred by the configured late-arrival window"
    )


def test_brief_assembly_is_deferred_not_immediate():
    """The buffer. Without `countdown`, a brief is assembled from the first event alone and a
    correlated event arriving 10 s later has nothing to attach to."""
    assert "countdown=window_secs" in SOURCE


def test_a_later_event_revokes_the_pending_brief():
    """The reorder tolerance: re-enqueuing restarts the window so the brief captures both
    events, instead of emitting one brief per event."""
    assert "control.revoke(" in SOURCE
    assert "kairos:brief_pending:" in SOURCE


def test_ptw_is_exempt_from_the_hold_and_leaves_other_briefs_alone():
    """The safety-critical exemption. A held PTW brief is worse than no buffering at all —
    the permit would already be issued by the time the brief arrived. And it must not cancel the
    technician's work-order brief: different recipient, different brief."""
    ptw = SOURCE[SOURCE.index("PTW events always trigger"):]
    ptw = ptw[: ptw.index("@router.post", 10)] if "@router.post" in ptw[10:] else ptw
    assert "countdown" not in ptw, "PTW must not be delayed by the late-arrival window"
    assert "control.revoke(" not in ptw, "a PTW must not cancel another event's pending brief"


def test_pending_brief_slot_is_per_event_not_per_asset():
    """Two work orders on one asset go to two technicians. A per-asset slot made the second
    revoke the first's queued brief, so only the last technician was briefed."""
    assert 'f"kairos:brief_pending:{payload.asset_id}:{payload.work_order_id}"' in SOURCE
    assert 'f"kairos:brief_pending:{payload.asset_id}"' not in SOURCE


def test_assembly_reads_events_ordered_by_occurred_at():
    """Where the actual reordering happens: arrival order does not matter because assembly
    reads the source of record back in `occurred_at` order."""
    from api.services import brief_engine

    assert '.order("occurred_at"' in inspect.getsource(brief_engine)


# --- Dedup is recorded after the ingest succeeds, never before ----------------------------------


class _FakeRedis:
    def __init__(self):
        self.keys: dict[str, str] = {}

    async def exists(self, key):
        return int(key in self.keys)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True


def _bus():
    from api.services.event_bus import EventBusService

    return EventBusService(_FakeRedis(), Settings())


def test_checking_for_a_duplicate_does_not_record_the_event():
    """Recording at check time meant a POST that then failed (Supabase 500) made the connector's
    retry answer "deduplicated", so a critical PTW brief was never created."""

    async def run():
        bus = _bus()
        assert await bus.is_duplicate("EQ-1", "ptw_generated", business_id="PTW-9") is False
        assert await bus.is_duplicate("EQ-1", "ptw_generated", business_id="PTW-9") is False, (
            "a failed first attempt must leave the retry free to run"
        )
        await bus.mark_seen("EQ-1", "ptw_generated", business_id="PTW-9")
        assert await bus.is_duplicate("EQ-1", "ptw_generated", business_id="PTW-9") is True

    asyncio.run(run())


def test_every_duplicate_check_is_paired_with_a_mark_after_success():
    assert SOURCE.count("is_duplicate(") == SOURCE.count("mark_seen(") > 0


def test_event_insert_is_idempotent_on_event_id():
    """A retry after a partial failure re-runs the handler; a plain insert would hit the primary
    key and 500 forever, so the brief would still never be created. It must not be an upsert
    either: `event_id` is client-supplied, so that let any ingest role overwrite another event."""
    assert ".upsert(" not in SOURCE and "on_conflict" not in SOURCE
    assert SOURCE.count("await _store_event(supabase, {") >= 6


class _EventsTable:
    def __init__(self, db):
        self.db, self.op, self.row, self.filters = db, "select", None, {}

    def insert(self, row):
        self.op, self.row = "insert", row
        return self

    def upsert(self, *_a, **_k):
        raise AssertionError("an upsert lets a caller overwrite another event")

    def select(self, *_a):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, *_a):
        return self

    def execute(self):
        from postgrest.exceptions import APIError

        if self.op == "insert":
            if self.row["event_id"] in self.db.rows:
                raise APIError({"code": "23505", "message": "duplicate key value"})
            self.db.rows[self.row["event_id"]] = self.row
            return SimpleNamespace(data=[self.row])
        return SimpleNamespace(data=[r for r in self.db.rows.values() if r["event_id"] == self.filters["event_id"]])


class _EventsDB:
    def __init__(self):
        self.rows: dict[str, dict] = {}

    def table(self, _name):
        return _EventsTable(self)


def _event_row(**over):
    return {"event_id": "ev-1", "event_type": "work_order_created", "site_id": "SITE_001",
            "asset_id": "EQ-101", "payload": {"work_order_id": "WO-1"}, **over}


def test_store_event_inserts_a_new_event():
    db = _EventsDB()
    asyncio.run(events_router._store_event(db, _event_row()))
    assert db.rows["ev-1"]["asset_id"] == "EQ-101"


def test_store_event_accepts_an_identical_retry():
    db = _EventsDB()
    asyncio.run(events_router._store_event(db, _event_row()))
    asyncio.run(events_router._store_event(db, _event_row(received_at="later")))  # same event, a retry


def test_store_event_refuses_to_overwrite_another_event_and_changes_nothing():
    import pytest
    from fastapi import HTTPException

    db = _EventsDB()
    asyncio.run(events_router._store_event(db, _event_row()))
    for change in ({"payload": {"work_order_id": "WO-2"}}, {"asset_id": "EQ-999"},
                   {"site_id": "SITE_002"}, {"event_type": "ptw_generated"}):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(events_router._store_event(db, _event_row(**change)))
        assert exc.value.status_code == 409
    assert db.rows["ev-1"] == _event_row()


def test_store_event_reraises_other_database_errors():
    import pytest
    from postgrest.exceptions import APIError

    class Down(_EventsDB):
        def table(self, _name):
            t = _EventsTable(self)
            t.execute = lambda: (_ for _ in ()).throw(APIError({"code": "23503", "message": "fk"}))
            return t

    with pytest.raises(APIError):
        asyncio.run(events_router._store_event(Down(), _event_row()))


# --- The cool-down must not swallow a different kind of brief ------------------------------------


class _Table:
    def __init__(self, rows):
        self.rows, self.filters = rows, []

    def select(self, *_a, **_k):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def gte(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def insert(self, row):
        self.rows.append(row)
        return self

    def execute(self):
        return SimpleNamespace(data=[r for r in self.rows if all(r.get(k) == v for k, v in self.filters)])


class _Supabase:
    def __init__(self):
        self.briefs: list[dict] = []

    def table(self, _name):
        return _Table(self.briefs)


def _brief(brief_id, trigger, priority="normal"):
    from api.models.brief import Brief

    return Brief(
        brief_id=brief_id, trigger_event_id="e", trigger_event_type=trigger, asset_id="EQ-1",
        recipient_user_id="tech-1", priority=priority, headline="h", body="b", confidence=0.8,
    )


def _engine():
    from api.services.brief_engine import BriefEngine

    engine = BriefEngine.__new__(BriefEngine)
    engine.supabase = _Supabase()
    engine.settings = SimpleNamespace(KAIROS_PHASE=2)  # stores the brief, skips the Redis push
    return engine


def test_cooldown_does_not_suppress_the_recurring_failure_brief():
    """WO-1 at 09:05, then a same-family WO-2 at 10:00: the "failed twice" brief is a different
    kind of message to the same technician and must not be swallowed by WO-1's cool-down."""

    async def run():
        engine = _engine()
        assert await engine.deliver(_brief("b1", "work_order_created"), None) == "b1"
        return await engine.deliver(_brief("b2", "recurring_failure_detected", "high"), None)

    assert asyncio.run(run()) == "b2"


def test_cooldown_still_collapses_a_repeat_of_the_same_kind():
    async def run():
        engine = _engine()
        await engine.deliver(_brief("b1", "work_order_created"), None)
        return await engine.deliver(_brief("b2", "work_order_created"), None)

    assert asyncio.run(run()) == "b1"
