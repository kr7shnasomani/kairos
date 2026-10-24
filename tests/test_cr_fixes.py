"""Regression tests for the cheap fixes from the 2026-10 code review (docs/code-review.md, now in git history) (B8, B11, B12, B13 and four Low items).

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

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _Session:
    def __init__(self, record, seen, params=None):
        self._record, self._seen, self._params = record, seen, params if params is not None else []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def run(self, cypher, **params):
        self._seen.append(cypher)
        self._params.append(params)
        return _Result(self._record)


class _Driver:
    def __init__(self, record=None):
        self.record, self.seen, self.params = record, [], []

    def session(self, **_k):
        return _Session(self.record, self.seen, self.params)


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


# --- 2026-10-22 review: edge retries and time travel ----------------------------------------------


def test_knowledge_edge_write_is_idempotent_on_edge_id():
    from api.services.graph import GraphService

    driver = _Driver()
    asyncio.run(GraphService(driver, "neo4j").create_knowledge_edge(
        "EQ-101", "Asset", "DOC-1", "Document", "DOCUMENTED_BY",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC), authority_level=3, document_id="DOC-1", confidence=0.9,
    ))

    write = driver.seen[-1]
    # A Temporal retry re-runs the same write; CREATE added a second copy of the edge every time.
    assert "MERGE (src)-[r:KNOWLEDGE_EDGE {edge_id: $edge_id}]->(tgt)" in write
    assert "CREATE (src)" not in write
    for prop in ("valid_from", "valid_to", "authority_level", "document_id", "confidence", "verification_status"):
        assert f"r.{prop} = ${prop}" in write


def test_time_travel_cutoff_is_the_same_instant_whatever_the_offset():
    from api.services.graph import GraphService

    driver = _Driver()
    graph = GraphService(driver, "neo4j")
    asyncio.run(graph.get_asset_knowledge_at("EQ-101", as_of=datetime.fromisoformat("2026-05-01T10:00:00+05:30")))
    asyncio.run(graph.get_asset_knowledge_at("EQ-101", as_of=datetime.fromisoformat("2026-05-01T04:30:00")))

    assert driver.params[0]["as_of"] == driver.params[1]["as_of"] == "2026-05-01T04:30:00+00:00"
    assert "datetime(r.valid_from) <= datetime($as_of)" in driver.seen[0]


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

    # `check` reads the real clock, so the rows are dated from it, not from the fixed NOW above.
    now = datetime.now(UTC)
    rows = [{"created_at": (now - timedelta(days=w * 7 + 1)).isoformat()} for w, n in enumerate(per_week) for _ in range(n)]
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


# --- Guards for the kept parts of the 2 October Antigravity batch -----------------------------------


def test_every_workflow_activity_is_registered_with_the_temporal_worker():
    """An activity the workflow calls but the worker does not register fails only when it is reached,
    which for a failure-handling activity is exactly when something has already gone wrong."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    base = next(c for c in (root / "backend", Path("/app")) if (c / "workflows" / "document_pipeline.py").exists())
    pipeline = (base / "workflows" / "document_pipeline.py").read_text()
    worker = (base / "workers" / "temporal_worker.py").read_text()
    activities = re.findall(r"@activity\.defn\s*\n(?:async )?def (\w+)", pipeline)
    assert activities, "no activities found"
    registered = worker.split("activities=[")[1]
    for name in activities:
        assert re.search(rf"\b{name}\b", registered), f"{name} is not registered with the worker"


def test_cors_is_the_outermost_middleware_so_401_403_429_carry_cors_headers():
    """Starlette inserts each added middleware at index 0, so the one added last is outermost. When CORS
    sat innermost, the OPA and rate-limit responses had no CORS headers and the browser only saw
    "Failed to fetch"."""
    from starlette.middleware.cors import CORSMiddleware

    from api.main import app

    names = [m.cls.__name__ for m in app.user_middleware]
    # OpenTelemetry's instrument_app may wrap the stack; CORS must still sit outside everything we add.
    assert names.index("CORSMiddleware") < min(i for i, n in enumerate(names) if n != "CORSMiddleware" and "OpenTelemetry" not in n)


def test_run_with_client_closes_the_shared_client_even_when_the_task_fails():
    import asyncio

    from api.services import http

    closed = []

    async def fake_close():
        closed.append(True)

    original = http.close_shared_client
    http.close_shared_client = fake_close
    try:
        async def boom():
            raise RuntimeError("task failed")

        try:
            http.run_with_client(boom())
        except RuntimeError:
            pass
        assert closed == [True]
        assert http.run_with_client(asyncio.sleep(0, result=7)) == 7
    finally:
        http.close_shared_client = original


def test_pipeline_quarantine_row_is_inserted_once_across_retries():
    from workflows.document_pipeline import _quarantine_once

    rows: list[dict] = []

    class _Q:
        def __init__(self):
            self.filters: dict = {}

        def select(self, *_a):
            return self

        def eq(self, col, val):
            self.filters[col] = val
            return self

        def limit(self, _n):
            return self

        def insert(self, row):
            self.row = row
            return self

        def execute(self):
            if hasattr(self, "row"):
                rows.append(self.row)
                return SimpleNamespace(data=[self.row])
            hit = [r for r in rows if r["content"] == self.filters["content"]
                   and r["session_context"].get("source_document_id") == self.filters["session_context->>source_document_id"]]
            return SimpleNamespace(data=hit)

    sb = SimpleNamespace(table=lambda _n: _Q())
    row = {"content": "PID element: XV-1 (valve)", "session_context": {"source_document_id": "D-1"}}
    # A Temporal retry re-runs the activity; the second attempt must not add a second review item.
    assert asyncio.run(_quarantine_once(sb, row, "source_document_id", "D-1")) is True
    assert asyncio.run(_quarantine_once(sb, row, "source_document_id", "D-1")) is False
    assert len(rows) == 1


def test_sla_escalation_runs_once_per_row_even_when_two_reads_overlap():
    from api.services.sla_service import SLAService

    conflicts = {"C-1": {"conflict_id": "C-1", "track": "engineering", "asset_id": "EQ-101",
                         "sla_deadline": "2026-01-01T00:00:00+00:00", "status": "open", "escalated_at": None}}
    audits: list = []

    class _T:
        def __init__(self, name):
            self.name, self.op, self.values, self.ids = name, "select", None, None

        def select(self, *_a):
            return self

        def lt(self, *_a):
            return self

        def neq(self, *_a):
            return self

        def eq(self, *_a):
            return self

        def is_(self, *_a):
            return self

        def in_(self, _col, ids):
            self.ids = ids
            return self

        def update(self, values):
            self.op, self.values = "update", values
            return self

        def insert(self, rows):
            self.op = "insert"
            audits.extend(rows if isinstance(rows, list) else [rows])
            return self

        def execute(self):
            if self.name != "knowledge_conflicts" or self.op == "insert":
                return SimpleNamespace(data=[])
            pending = [r for r in conflicts.values() if r["escalated_at"] is None]
            if self.op == "select":
                return SimpleNamespace(data=[dict(r) for r in pending])
            hit = [r for r in pending if r["conflict_id"] in self.ids]
            for r in hit:
                r.update(self.values)
            return SimpleNamespace(data=[dict(r) for r in hit])

    sb = SimpleNamespace(table=lambda n: _T(n))
    first = asyncio.run(SLAService.check_and_escalate(sb))
    second = asyncio.run(SLAService.check_and_escalate(sb))

    assert first["conflicts_escalated"] == 1 and second["conflicts_escalated"] == 0
    assert [a["entity_id"] for a in audits] == ["C-1"]


def test_sla_escalation_chunks_a_large_backlog():
    """Every id goes into the request URL, so a large backlog is sent in chunks, not one request."""
    from api.services import sla_service

    calls: list = []

    class _T:
        def update(self, _values):
            return self

        def in_(self, _col, ids):
            calls.append(list(ids))
            self.ids = ids
            return self

        def is_(self, *_a):
            return self

        def execute(self):
            return SimpleNamespace(data=[{"item_id": i} for i in self.ids])

    rows = [{"item_id": f"Q-{n}"} for n in range(sla_service._ESCALATE_CHUNK * 2 + 5)]
    sb = SimpleNamespace(table=lambda _n: _T())
    out = asyncio.run(sla_service._escalate(sb, "quarantine_items", "item_id", rows, {"escalated_at": "now"}))

    assert [len(c) for c in calls] == [sla_service._ESCALATE_CHUNK, sla_service._ESCALATE_CHUNK, 5]
    assert len(out) == len(rows)


def test_a_malformed_id_is_a_404_not_a_500():
    """`GET /briefs/governor` matched `/{brief_id}`, Postgres raised 22P02 on the non-uuid id, and the
    shared Supabase handler answered 500. A malformed id names no record: 404, for every by-id route."""
    from postgrest.exceptions import APIError

    from api.main import app

    handler = app.exception_handlers[APIError]
    request = SimpleNamespace(url="https://api/briefs/governor")
    resp = asyncio.run(handler(request, APIError({"code": "22P02", "message": "invalid input syntax for type uuid"})))
    assert resp.status_code == 404


def _deviation_payload(resolution):
    from api.models.event import DeviationFlagResolveRequest

    return DeviationFlagResolveRequest(resolution=resolution)


class _NoFlag:
    """A Supabase stand-in whose deviation-flag lookup finds nothing (the route then answers 404)."""

    def table(self, _name):
        return self

    def select(self, *_a):
        return self

    def eq(self, *_a):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


def test_an_engineer_cannot_promote_through_the_deviation_resolve_route():
    """Review C17: confirming a deviation marks its quarantine item `promoted`, and promotion is
    reliability/admin only. The route allowed an engineer to do it."""
    from api.routers import events

    engineer = {"user_id": "u-eng", "role": "engineer"}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(events.resolve_deviation_flag("3f2504e0-4f89-11d3-9a0c-0305e82c3301",
                                                  _deviation_payload("promoted"), _NoFlag(), engineer))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("user,resolution", [
    ({"user_id": "u-eng", "role": "engineer"}, "disputed"),     # an engineer can still dismiss
    ({"user_id": "u-rel", "role": "reliability"}, "promoted"),  # reliability can now confirm
    ({"user_id": "u-adm", "role": "admin"}, "promoted"),
])
def test_allowed_deviation_resolutions_reach_the_lookup(user, resolution):
    from api.routers import events

    with pytest.raises(HTTPException) as exc:
        asyncio.run(events.resolve_deviation_flag("3f2504e0-4f89-11d3-9a0c-0305e82c3301",
                                                  _deviation_payload(resolution), _NoFlag(), user))
    assert exc.value.status_code == 404  # past the role check, stopped only by the empty fake


def test_reliability_may_open_the_deviation_resolve_route():
    """The route's role gate names reliability; it used to stop at engineer and admin, so the role
    allowed to promote could not resolve a deviation flag at all."""
    import inspect

    from api.routers import events

    gate = inspect.signature(events.resolve_deviation_flag).parameters["current_user"].default.dependency
    asyncio.run(gate({"role": "reliability"}))
