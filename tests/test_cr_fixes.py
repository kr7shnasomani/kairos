"""Regression tests for the cheap fixes from docs/code-review.md (B8, B11, B12, B13 and four Low items).

Service-free: fakes only. No stack, no secrets, no network.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.config import Settings

# --- B12: last_inspection_date reads the KNOWLEDGE_EDGE that is actually written -----------------


class _Result:
    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


class _Session:
    def __init__(self, record, seen):
        self._record, self._seen = record, seen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def run(self, cypher, **params):
        self._seen.append(cypher)
        return _Result(self._record)


class _Driver:
    def __init__(self, record=None):
        self.record, self.seen = record, []

    def session(self, **_k):
        return _Session(self.record, self.seen)


def test_last_inspection_query_matches_the_knowledge_edge_property_not_a_relationship_type():
    from api.services.graph import GraphService

    driver = _Driver({"inspection_date": "2026-09-14T10:26:36+00:00"})
    got = asyncio.run(GraphService(driver, "neo4j").get_last_inspection_date("EQ-101"))

    assert got == "2026-09-14T10:26:36+00:00"
    cypher = driver.seen[0]
    # `create_knowledge_edge` writes every edge as :KNOWLEDGE_EDGE {relationship_type: ...}; a
    # `[r:INSPECTION_RECORD]` pattern matches no edge, so the field was always null.
    assert "[r:KNOWLEDGE_EDGE {relationship_type: 'INSPECTION_RECORD'}]" in cypher
    assert "[r:INSPECTION_RECORD]" not in cypher


def test_last_inspection_is_none_when_there_is_no_record():
    from api.services.graph import GraphService

    assert asyncio.run(GraphService(_Driver(None), "neo4j").get_last_inspection_date("EQ-1")) is None


# --- B13: briefs search the collection ingestion writes -----------------------------------------


def test_brief_vector_search_uses_the_documents_collection():
    from api.services.brief_engine import BriefEngine

    calls = []

    class _Vector:
        async def search(self, collection, vector, **kw):
            calls.append(collection)
            return [{"payload": {}}]

    class _Llm:
        async def embed(self, *_a, **_k):
            return [0.0]

    engine = BriefEngine.__new__(BriefEngine)
    engine.settings, engine.vector, engine.llm = Settings(), _Vector(), _Llm()

    hits = asyncio.run(engine._vector_search("failure SEAL-FAIL", "EQ-1"))

    assert hits and calls == [engine.settings.QDRANT_COLLECTION_DOCUMENTS]
    assert calls[0] != engine.settings.QDRANT_COLLECTION_KNOWLEDGE


# --- B8: recurrence uses one mapping on both sides ----------------------------------------------


def _rows(*codes):
    return [{"payload": {"failure_code": c}} for c in codes]


def test_recurrence_counts_an_unknown_code_against_itself():
    """`CORROSION` twice in 90 days never recurred: the current side mapped to `CORROSION`, the
    prior side to the `"?"` sentinel."""
    from api.routers.events import _count_recurrences
    from api.utils.failure_families import failure_family

    assert _count_recurrences(_rows("CORROSION"), failure_family("CORROSION")) == 1


def test_recurrence_folds_case_and_whitespace_on_both_sides():
    from api.routers.events import _count_recurrences
    from api.utils.failure_families import failure_family

    assert _count_recurrences(_rows("corrosion", " Corrosion "), failure_family("CORROSION")) == 2
    assert _count_recurrences(_rows("seal-fail"), failure_family("LEAK-MECH")) == 1  # same family


def test_recurrence_ignores_other_families_and_blank_codes():
    from api.routers.events import _count_recurrences
    from api.utils.failure_families import failure_family

    assert _count_recurrences(_rows("BEARING-FAIL", "CORROSION"), failure_family("SEAL-FAIL")) == 0
    # Two work orders that both omit a code are not a recurrence of anything.
    assert _count_recurrences([{"payload": {}}, {"payload": None}, *_rows("")], failure_family("")) == 0
    assert _count_recurrences(_rows("", None), failure_family(None)) == 0


# --- B11: circuit breaker ----------------------------------------------------------------------

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat()


def test_weeks_are_strict_seven_day_windows():
    from api.services.circuit_breaker import _weekly_counts

    stamps = [_ago(0.1), _ago(6.9), _ago(7.1), _ago(13.9), _ago(14.1), _ago(20.9), _ago(21.1), _ago(27.9)]
    assert _weekly_counts(stamps, NOW) == [2, 2, 2, 2]


def test_the_oldest_window_is_not_nine_days_wide():
    """Days 28 to 30 used to be folded into the last bucket (`min(.., 3)`)."""
    from api.services.circuit_breaker import _weekly_counts

    assert _weekly_counts([_ago(28.5), _ago(29.9), _ago(60)], NOW) == [0, 0, 0, 0]


def test_a_future_timestamp_counts_as_the_current_week():
    from api.services.circuit_breaker import _weekly_counts

    assert _weekly_counts([(NOW + timedelta(minutes=5)).isoformat()], NOW) == [1, 0, 0, 0]


class _Table:
    def __init__(self, data):
        self._data = data

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        return SimpleNamespace(data=self._data)


class _Supabase:
    def __init__(self, override_rows):
        self._rows = override_rows

    def table(self, name):
        return _Table(self._rows if name == "extraction_overrides" else [])


def _check(per_week: list[int]):
    """Run `check` with `per_week[i]` overrides in week i (0 = current)."""
    from api.services.circuit_breaker import CircuitBreakerService

    rows = [{"created_at": _ago(w * 7 + 1)} for w, n in enumerate(per_week) for _ in range(n)]
    return asyncio.run(CircuitBreakerService(_Supabase(rows)).check("pump"))


def test_a_flat_baseline_can_trip():
    """`[1, 1, 1]` gave std 0 and a z-score of 0, so 50 overrides never halted."""
    out = _check([50, 1, 1, 1])
    assert out["halted"] is True
    assert out["override_count_7d"] == 50


def test_a_flat_baseline_does_not_trip_on_ordinary_noise():
    assert _check([3, 1, 1, 1])["halted"] is False  # mean + 2 is not exceeded
    assert _check([4, 1, 1, 1])["halted"] is True


def test_a_varying_baseline_keeps_the_z_score_rule():
    assert _check([9, 1, 2, 3])["halted"] is True  # mean 2, std 1, z = 7
    assert _check([3, 1, 2, 3])["halted"] is False


def test_no_history_is_not_a_halt():
    out = _check([40, 0, 0, 0])
    assert out["halted"] is False and out["reason"] == "insufficient_history"


# --- Low: /search?as_of=garbage is a 422 --------------------------------------------------------


def test_search_rejects_a_bad_as_of_with_422():
    from api.routers.search import search

    with pytest.raises(HTTPException) as exc:
        asyncio.run(search(
            settings=Settings(), current_user={}, driver=None, qdrant=None, es=None, supabase=None,
            q="pump", asset_id=None, authority_min=5, include_quarantine=False, as_of="garbage", limit=10,
        ))
    assert exc.value.status_code == 422


# --- Low: the feedback recheck task is referenced until it is done -------------------------------


def test_feedback_recheck_task_is_kept_alive_until_done(monkeypatch):
    from api.models.brief import BriefFeedback
    from api.routers import briefs

    started, release = asyncio.Event(), asyncio.Event()

    async def slow_recheck(*_a):
        started.set()
        await release.wait()

    monkeypatch.setattr(briefs, "_recheck_brief_sources", slow_recheck)
    monkeypatch.setattr(briefs, "_may_read", lambda *_a: True)
    supabase = SimpleNamespace(table=lambda _n: _Table([{"brief_id": "B-1"}]))

    async def run():
        out = await briefs.submit_feedback(
            "B-1", BriefFeedback(rating="incorrect"), {"user_id": "u1"}, supabase
        )
        assert out["status"] == "received"
        await started.wait()
        assert len(briefs._background_tasks) == 1, "the loop only holds a weak reference to a task"
        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not briefs._background_tasks, "a finished task must be discarded"

    asyncio.run(run())


# --- Low: the Event-node comment no longer claims none is written --------------------------------


def test_graph_service_no_longer_claims_event_nodes_are_never_written():
    import inspect

    from api.services import graph

    src = inspect.getsource(graph)
    assert "No `Event` node is ever written" not in src
    assert "merge_event_node" in src
