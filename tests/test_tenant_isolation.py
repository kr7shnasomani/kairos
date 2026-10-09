"""
Showcase data stays out of real accounts (`services/tenant.py`).

Service-free: a recording query stands in for PostgREST and a recording session for Neo4j. What is
pinned here is the SHAPE of every filter and which reads carry one, because the shape is what keeps a
real account from ever seeing a `DEMO-` row, and the registry below is what stops a refactor from
dropping one silently.
"""

import ast
import pathlib

import pytest
from api.dependencies import site_scope
from api.services import tenant
from api.services.corpus import REAL_ASSET_CYPHER, excluded_test_asset_count

REAL = {"user_id": "u-real", "role": "engineer", "site_id": "SITE_001"}
ADMIN = {"user_id": "u-admin", "role": "admin", "site_id": "SITE_001"}
DEMO = {"user_id": "u-demo", "role": "demo", "site_id": "SITE_001"}


class _Q:
    """Chainable query that records calls; `not_` is a property, as in postgrest-py."""

    def __init__(self):
        self.ops = []

    @property
    def not_(self):
        self.ops.append(("not_",))
        return self

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.ops.append((name, *args))
            return self

        return call


# --- PostgREST shapes --------------------------------------------------------------------------


def test_a_real_caller_hides_showcase_rows_and_the_demo_role_does_not():
    assert tenant.scope(_Q(), REAL, "asset_id").ops == [("not_",), ("like", "asset_id", "DEMO-*")]
    assert tenant.scope(_Q(), ADMIN, "asset_id").ops == [("not_",), ("like", "asset_id", "DEMO-*")]
    assert tenant.scope(_Q(), None, "asset_id").ops == [("not_",), ("like", "asset_id", "DEMO-*")]
    assert tenant.scope(_Q(), DEMO, "asset_id").ops == []


def test_a_nullable_column_keeps_its_null_rows():
    """PostgREST's `not.like` drops NULLs; a quarantine item with no asset is real by definition."""
    assert tenant.scope(_Q(), REAL, "asset_id", nullable=True).ops == [
        ("or_", "asset_id.is.null,asset_id.not.like.DEMO-*")
    ]


def test_site_and_document_scopes():
    assert tenant.scope_site(_Q(), REAL).ops == [("not_",), ("in_", "site_id", ["SITE_DEMO", "SITE_DEMO_B"])]
    assert tenant.scope_site(_Q(), DEMO).ops == []
    assert tenant.scope_document_site(_Q(), REAL).ops == [
        ("or_", "access_tags->>site_id.is.null,access_tags->>site_id.not.in.(SITE_DEMO,SITE_DEMO_B)")
    ]
    assert tenant.scope_document_site(_Q(), DEMO).ops == []


def test_wildcard_is_star_not_percent():
    """This Supabase project's edge answers 500 to a `%` pattern, so every like uses `*`."""
    assert "%" not in tenant.DEMO_PREFIX + "*"
    for call in (tenant.scope(_Q(), REAL, "x", nullable=True).ops, tenant.scope(_Q(), REAL, "x").ops):
        assert not any("%" in str(part) for op in call for part in op)


def test_the_demo_role_reads_every_site_and_everyone_else_stays_pinned():
    assert site_scope(DEMO, None) is None
    assert site_scope(ADMIN, "SITE_X") == "SITE_X"
    assert site_scope(REAL, None) == "SITE_001"
    with pytest.raises(Exception):  # noqa: B017 — HTTPException 403
        site_scope(REAL, "SITE_DEMO")


# --- the audit trail ---------------------------------------------------------------------------


class _Auth:
    def __init__(self, users):
        self.admin = type("A", (), {"list_users": staticmethod(lambda: users)})()


class _User:
    def __init__(self, uid, role):
        self.id = uid
        self.app_metadata = {"role": role}
        self.user_metadata = {}


async def test_real_callers_hide_the_demo_identitys_audit_rows():
    tenant._demo_ids = (float("-inf"), [])
    sb = type("S", (), {"auth": _Auth([_User("d-1", "demo"), _User("a-1", "admin")])})()
    q = await tenant.scope_audit(_Q(), REAL, sb)
    assert ("not_",) in q.ops and ("in_", "performed_by", ["d-1"]) in q.ops
    assert ("or_", "entity_id.is.null,entity_id.not.like.DEMO-*") in q.ops
    assert ("or_", "details->>tenant.is.null,details->>tenant.neq.demo") in q.ops
    assert (await tenant.scope_audit(_Q(), DEMO, sb)).ops == []


async def test_the_first_demo_user_lookup_happens_on_a_freshly_booted_host(monkeypatch):
    """`time.monotonic()` is uptime: a CI runner or server up for under ten minutes read "fresh" from the start."""
    import api.services.tenant as t

    monkeypatch.setattr(t.time, "monotonic", lambda: 120.0)
    tenant._demo_ids = (float("-inf"), [])  # what the module starts with
    sb = type("S", (), {"auth": _Auth([_User("d-1", "demo")])})()
    assert await tenant.demo_user_ids(sb) == ["d-1"]


async def test_a_failed_demo_user_lookup_never_fails_the_read():
    tenant._demo_ids = (float("-inf"), [])

    class _Broken:
        auth = type("B", (), {"admin": type("C", (), {"list_users": staticmethod(lambda: 1 / 0)})()})()

    q = await tenant.scope_audit(_Q(), REAL, _Broken())
    assert ("or_", "entity_id.is.null,entity_id.not.like.DEMO-*") in q.ops  # entity filters still apply


# --- Cypher ------------------------------------------------------------------------------------


class _Result:
    async def single(self):
        return {"total": 3, "excluded": 0, "n": 0}

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _Session:
    def __init__(self, seen):
        self.seen = seen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, cypher, **params):
        self.seen.append((cypher, params))
        return _Result()


class _Driver:
    def __init__(self):
        self.seen = []

    def session(self, **kwargs):
        return _Session(self.seen)


async def test_asset_list_hides_showcase_assets_by_default_and_shows_them_when_asked():
    from api.services.graph import GraphService

    driver = _Driver()
    await GraphService(driver).list_assets()
    assert driver.seen and all(p["hide_demo"] is True for _, p in driver.seen)
    assert all(tenant.DEMO_VISIBLE_CYPHER in c for c, _ in driver.seen)
    assert all(REAL_ASSET_CYPHER in c for c, _ in driver.seen)

    driver = _Driver()
    await GraphService(driver).list_assets(hide_demo=False)
    assert all(p["hide_demo"] is False for _, p in driver.seen)


async def test_the_excluded_test_asset_count_carries_the_flag():
    seen = []
    await excluded_test_asset_count(_Session(seen), "SITE_001")
    assert seen[0][1] == {"site_id": "SITE_001", "hide_demo": True}
    assert tenant.DEMO_VISIBLE_CYPHER in seen[0][0]


def test_hides_demo_is_true_for_everyone_but_the_demo_role():
    assert tenant.hides_demo(REAL) and tenant.hides_demo(ADMIN) and tenant.hides_demo(None)
    assert not tenant.hides_demo(DEMO)


def test_every_compliance_query_that_lists_assets_carries_the_demo_guard():
    from api.routers import compliance

    for cypher in (compliance._GAP_CYPHER, compliance._DASHBOARD_CYPHER, compliance._AUDIT_CYPHER):
        assert tenant.DEMO_VISIBLE_CYPHER in cypher


# --- the registry of reads that must be scoped -----------------------------------------------------

API = pathlib.Path(__file__).resolve().parents[1] / "backend" / "api"
if not API.exists():  # inside the backend image the tree is /app
    API = pathlib.Path("/app/api")

# (file, function) pairs whose body must call into `tenant`. These are the list, count and aggregate
# reads: a read by a primary key from the request is the capability itself and is not listed. When a
# new list or aggregate read is added, add it here in the same change.
MUST_SCOPE = [
    ("routers/governance.py", "list_conflicts"),
    ("routers/governance.py", "list_quarantine"),
    ("routers/governance.py", "get_sla_report"),
    ("routers/governance.py", "list_moc"),
    ("routers/governance.py", "push_volume_gate"),
    ("routers/governance.py", "timestamp_drift_report"),
    ("routers/events.py", "list_events"),
    ("routers/elicitation.py", "trigger_elicitation"),
    ("routers/elicitation.py", "create_offboarding_programme"),
    ("routers/elicitation.py", "list_offboarding_programmes"),
    ("routers/assets.py", "list_assets"),
    ("routers/assets.py", "asset_coverage"),
    ("routers/assets.py", "cross_site_patterns"),
    ("routers/assets.py", "list_provisional_assets"),
    ("routers/assets.py", "list_pending_aliases"),
    ("routers/documents.py", "list_documents"),
    ("routers/audit_log.py", "get_audit_log"),
    ("routers/compliance.py", "list_compliance_gaps"),
    ("routers/compliance.py", "compliance_dashboard"),
    ("routers/compliance.py", "generate_audit_pack"),
]


def _function_source(relpath: str, name: str) -> str:
    src = (API / relpath).read_text()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{relpath}: no function {name}")


@pytest.mark.parametrize(("relpath", "name"), MUST_SCOPE)
def test_list_and_aggregate_reads_are_scoped(relpath, name):
    assert "tenant." in _function_source(relpath, name), f"{relpath}::{name} reads without a tenant scope"


# --- search stores -----------------------------------------------------------------------------


def test_store_naming_and_document_marking():
    assert tenant.demo_store("kairos_documents") == "kairos_documents_demo"
    assert tenant.store_for("kairos_documents", demo=False) == "kairos_documents"
    assert tenant.store_for("kairos_documents", demo=True) == "kairos_documents_demo"
    assert tenant.is_demo_document({"access_tags": {"site_id": "SITE_DEMO_B"}})
    assert tenant.is_demo_document({"site_id": "SITE_DEMO"})
    assert tenant.is_demo_document({"asset_id": "DEMO-P-101"})
    assert not tenant.is_demo_document({"access_tags": {"site_id": "SITE_001"}, "asset_id": "EQ-101"})
    assert not tenant.is_demo_document(None) and not tenant.is_demo_document({"access_tags": None})


class _Settings:
    QDRANT_COLLECTION_DOCUMENTS = "kairos_documents"
    QDRANT_COLLECTION_KNOWLEDGE = "kairos_knowledge"
    ELASTICSEARCH_INDEX_DOCUMENTS = "kairos_documents"
    ELASTICSEARCH_INDEX_ASSETS = "kairos_assets"


class _Point:
    def __init__(self, score, tag):
        self.id, self.score, self.payload = tag, score, {"authority_level": 3, "tag": tag}


class _Qdrant:
    def __init__(self, missing_demo=False):
        self.calls, self.missing_demo = [], missing_demo

    async def search(self, collection_name, **kwargs):
        self.calls.append(collection_name)
        if collection_name.endswith("_demo"):
            if self.missing_demo:
                raise RuntimeError("collection not found")
            return [_Point(0.9, "demo-hit")]
        return [_Point(0.5, "real-hit")]


async def test_a_real_caller_never_queries_the_showcase_collection():
    from api.services.vector_store import VectorStoreService

    q = _Qdrant()
    hits = await VectorStoreService(q, _Settings()).search("kairos_documents", [0.1])
    assert q.calls == ["kairos_documents"] and [h["payload"]["tag"] for h in hits] == ["real-hit"]


async def test_the_demo_role_searches_both_and_the_better_hit_wins():
    from api.services.vector_store import VectorStoreService

    q = _Qdrant()
    hits = await VectorStoreService(q, _Settings(), include_demo=True).search("kairos_documents", [0.1], limit=5)
    assert q.calls == ["kairos_documents", "kairos_documents_demo"]
    assert [h["payload"]["tag"] for h in hits] == ["demo-hit", "real-hit"]


async def test_a_missing_showcase_collection_degrades_to_the_real_one():
    from api.services.vector_store import VectorStoreService

    q = _Qdrant(missing_demo=True)
    hits = await VectorStoreService(q, _Settings(), include_demo=True).search("kairos_documents", [0.1])
    assert [h["payload"]["tag"] for h in hits] == ["real-hit"]


async def test_the_knowledge_collection_is_never_widened():
    from api.services.vector_store import VectorStoreService

    q = _Qdrant()
    await VectorStoreService(q, _Settings(), include_demo=True).search("kairos_knowledge", [0.1])
    assert q.calls == ["kairos_knowledge"]


class _ES:
    def __init__(self):
        self.searched = []

    async def search(self, index, body, **kwargs):
        self.searched.append((index, kwargs))
        return {"hits": {"hits": []}}


async def test_elasticsearch_indices_follow_the_caller():
    from api.services.search_engine import SearchEngineService

    es = _ES()
    await SearchEngineService(es, _Settings()).search("P-101")
    await SearchEngineService(es, _Settings(), include_demo=True).search("P-101")
    real, demo = es.searched
    assert real[0] == "kairos_documents,kairos_assets"
    assert demo[0] == "kairos_documents,kairos_assets,kairos_documents_demo,kairos_assets_demo"
    assert demo[1].get("ignore_unavailable") is True


async def test_demo_stores_are_not_created_at_startup():
    """`ensure_collections` and `ensure_indices` run on every boot, including a production deploy;
    creating the showcase collection there would be an unannounced cloud write."""
    import inspect

    from api.services.search_engine import SearchEngineService
    from api.services.vector_store import VectorStoreService

    assert "demo" not in inspect.getsource(VectorStoreService.ensure_collections).lower()
    assert "demo" not in inspect.getsource(SearchEngineService.ensure_indices).lower()


# --- statistics and the audit marker -----------------------------------------------------------


def test_a_showcase_action_does_not_feed_real_statistics():
    assert tenant.feeds_statistics(REAL, "EQ-101")
    assert tenant.feeds_statistics(REAL, None)
    assert not tenant.feeds_statistics(DEMO, "EQ-101")
    assert not tenant.feeds_statistics(REAL, "DEMO-EQ-101")
    assert not tenant.feeds_statistics(DEMO)


def test_system_rows_about_showcase_assets_are_marked_for_the_audit_filter():
    assert tenant.audit_marker("DEMO-V-1") == {"tenant": "demo"}
    assert tenant.audit_marker("EQ-101") == {} and tenant.audit_marker(None) == {}


async def test_actor_scope_hides_the_demo_identity_only_from_real_callers():
    tenant._demo_ids = (float("-inf"), [])
    sb = type("S", (), {"auth": _Auth([_User("d-1", "demo")])})()
    q = await tenant.scope_actor(_Q(), REAL, sb, "annotated_by")
    assert q.ops == [("not_",), ("in_", "annotated_by", ["d-1"])]
    assert (await tenant.scope_actor(_Q(), DEMO, sb, "annotated_by")).ops == []


# --- the write fence and the guards --------------------------------------------------------------


def _routes():
    from api.main import app

    out = []
    for r in app.routes:
        for m in (getattr(r, "methods", None) or set()) & {"POST", "PUT", "PATCH", "DELETE"}:
            out.append((m, r.path, r))
    return out


def test_every_route_the_demo_role_may_write_is_a_real_route():
    real = {(m, p) for m, p, _ in _routes()}
    assert tenant.DEMO_WRITE_ALLOWED <= real, sorted(tenant.DEMO_WRITE_ALLOWED - real)


def test_the_routes_a_demo_write_cannot_reach_are_exactly_the_ones_that_should_stay_closed():
    """A new write route is closed to the demo role until someone lists it. This pins today's set:
    login (no token yet), the signed MoC webhook, and the model gate (admin only, spends quota)."""
    closed = {(m, p) for m, p, _ in _routes()} - tenant.DEMO_WRITE_ALLOWED
    assert closed == {
        ("POST", "/auth/login"),
        ("POST", "/governance/moc/webhook"),
        ("POST", "/governance/model-gate/run"),
    }


def test_every_guarded_route_calls_a_guard_in_its_handler():
    handlers = {(m, p): r.endpoint for m, p, r in _routes()}
    import inspect

    for key in tenant.DEMO_GUARDED:
        source = inspect.getsource(handlers[key])
        assert "tenant.guard_" in source or "_canonical_asset" in source or "_id_prefix" in source, (
            f"{key} is open to the demo role but its handler never guards the target"
        )


async def test_the_fence_stops_a_demo_write_on_an_unlisted_route_and_leaves_everyone_else_alone(monkeypatch):
    from api import dependencies as deps
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    users = {"demo-token": DEMO, "real-token": REAL}

    async def fake_resolve(token, settings):
        return users.get(token)

    monkeypatch.setattr(deps, "resolve_token", fake_resolve)
    app = FastAPI(dependencies=[Depends(deps.demo_write_fence)])
    app.dependency_overrides[deps.get_settings] = lambda: None
    for method, path in (("POST", "/briefs/{brief_id}/ack"), ("POST", "/brand/new"), ("GET", "/brand/new")):
        app.add_api_route(path, lambda: {"ok": True}, methods=[method])
    c = TestClient(app)
    demo, real = {"Authorization": "Bearer demo-token"}, {"Authorization": "Bearer real-token"}
    assert c.post("/briefs/B-1/ack", headers=demo).status_code == 200
    assert c.post("/brand/new", headers=demo).status_code == 403
    assert c.get("/brand/new", headers=demo).status_code == 200
    assert c.post("/brand/new", headers=real).status_code == 200
    assert c.post("/brand/new").status_code == 200  # no token: the route's own auth decides


def test_the_demo_role_passes_a_role_gate_that_names_staff_but_never_admin_only():
    assert tenant.has_role(DEMO, "engineer", "admin")
    assert tenant.has_role(DEMO, "reliability", "admin")
    assert not tenant.has_role(DEMO, "admin")
    assert tenant.has_role(REAL, "engineer") and not tenant.has_role(REAL, "reliability")
    assert not tenant.has_role(None, "admin")


def test_demo_targets_must_be_showcase_rows():
    from fastapi import HTTPException

    tenant.guard_asset(REAL, "EQ-101")  # a real caller is not restricted by the guards
    tenant.guard_asset(DEMO, "DEMO-EQ-101")
    tenant.guard_site(DEMO, "SITE_DEMO_B")
    tenant.guard_person(DEMO, "DEMO-expert-1")
    tenant.guard_document(DEMO, {"access_tags": {"site_id": "SITE_DEMO"}})
    for call in (
        lambda: tenant.guard_asset(DEMO, "EQ-101"),
        lambda: tenant.guard_asset(DEMO, None),
        lambda: tenant.guard_site(DEMO, "SITE_001"),
        lambda: tenant.guard_person(DEMO, "someone-real"),
        lambda: tenant.guard_document(DEMO, {"access_tags": {"site_id": "SITE_001"}}),
    ):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 403


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        rows = self.rows.get(name, [])

        class Q:
            def select(self, *a, **k):
                return self

            def eq(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def execute(self):
                return type("R", (), {"data": rows})()

        return Q()


async def test_a_demo_action_on_an_existing_row_needs_a_showcase_marker():
    from fastapi import HTTPException

    showcase = _Rows({"quarantine_items": [{"asset_id": "DEMO-EQ-1"}], "operational_events": [{"site_id": "SITE_DEMO"}],
                      "documents": [{"access_tags": {"site_id": "SITE_DEMO"}, "asset_id": None}]})
    real = _Rows({"quarantine_items": [{"asset_id": "EQ-101"}], "operational_events": [{"site_id": "SITE_001"}],
                  "documents": [{"access_tags": {"site_id": "SITE_001"}, "asset_id": "EQ-101"}]})
    null_asset = _Rows({"quarantine_items": [{"asset_id": None}]})
    missing = _Rows({})
    for table, key in (("quarantine_items", "q1"), ("operational_events", "e1"), ("documents", "d1")):
        await tenant.guard_row(showcase, DEMO, table, key)
        await tenant.guard_row(real, REAL, table, key)  # a real caller is never restricted
        with pytest.raises(HTTPException):
            await tenant.guard_row(real, DEMO, table, key)
    with pytest.raises(HTTPException):
        await tenant.guard_row(null_asset, DEMO, "quarantine_items", "q1")  # NULL asset means real
    await tenant.guard_row(missing, DEMO, "quarantine_items", "q1")  # unknown row: the handler 404s


async def test_a_demo_voice_note_must_resolve_to_a_showcase_asset():
    from fastapi import HTTPException

    class Q:
        def __init__(self, table, db):
            self.table_name, self.db = table, db

        def select(self, *a, **k):
            return self

        def filter(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def execute(self):
            return type("R", (), {"data": self.db.get(self.table_name, [])})()

    class DB:
        def __init__(self, data):
            self.data = data

        def table(self, name):
            return Q(name, self.data)

    await tenant.guard_work_order(DB({"operational_events": [{"asset_id": "DEMO-EQ-1"}]}), DEMO, "WO-1")
    await tenant.guard_work_order(DB({"assets": [{"asset_id": "DEMO-EQ-2"}]}), DEMO, "DEMO-EQ-2")
    await tenant.guard_work_order(DB({"operational_events": [{"asset_id": "EQ-101"}]}), REAL, "WO-9")
    with pytest.raises(HTTPException):
        await tenant.guard_work_order(DB({"operational_events": [{"asset_id": "EQ-101"}]}), DEMO, "WO-9")
    with pytest.raises(HTTPException):
        await tenant.guard_work_order(DB({}), DEMO, "nothing-resolves")


# --- the demo budget ---------------------------------------------------------------------------


class _Redis:
    def __init__(self, fail=False):
        self.n, self.expired, self.fail = 0, 0, fail

    async def incr(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        self.n += 1
        return self.n

    async def expire(self, key, seconds):
        self.expired += 1


async def test_the_demo_budget_counts_only_the_demo_role_and_stops_at_the_cap():
    from api.dependencies import demo_llm_budget
    from fastapi import HTTPException

    class S:
        DEMO_LLM_ACTIONS_PER_HOUR = 2

    r = _Redis()
    await demo_llm_budget(REAL, r, S())
    await demo_llm_budget(ADMIN, r, S())
    assert r.n == 0  # a real account is never counted
    await demo_llm_budget(DEMO, r, S())
    await demo_llm_budget(DEMO, r, S())
    assert r.n == 2 and r.expired == 1  # the window is set once, on the first use
    with pytest.raises(HTTPException) as exc:
        await demo_llm_budget(DEMO, r, S())
    assert exc.value.status_code == 429


async def test_a_redis_outage_does_not_block_a_demo_action():
    from api.dependencies import demo_llm_budget

    class S:
        DEMO_LLM_ACTIONS_PER_HOUR = 1

    await demo_llm_budget(DEMO, _Redis(fail=True), S())  # fails open


def test_every_model_backed_route_carries_the_budget():
    from api.dependencies import demo_llm_budget

    expected = {
        ("POST", "/documents/ingest"), ("POST", "/search/synthesize"), ("POST", "/search/synthesize/stream"),
        ("POST", "/search/rca-pack"), ("POST", "/elicitation/trigger"), ("POST", "/elicitation/{work_order_id}/voice"),
        ("POST", "/events/work-order"), ("POST", "/events/ptw"), ("POST", "/events/shift-handover"),
        ("POST", "/events/alarm"), ("POST", "/events/tag-out"), ("POST", "/events/inspection-complete"),
    }
    carrying = {
        (m, p) for m, p, r in _routes() if demo_llm_budget in [d.call for d in r.dependant.dependencies]
    }
    assert carrying == expected


# --- by-id reads: a real account asking for a showcase record by its id ----------------------------

async def test_a_path_that_names_a_showcase_record_is_recognised_for_every_kind_of_id(monkeypatch):
    showcase = _Rows({"documents": [{"access_tags": {"site_id": "SITE_DEMO"}}], "briefs": [{"asset_id": "DEMO-P-1"}],
                      "knowledge_conflicts": [{"asset_id": "DEMO-P-1"}], "moc_items": [{"asset_id": "DEMO-P-1"}],
                      "operational_events": [{"site_id": "SITE_DEMO"}, {"asset_id": "DEMO-P-1"}],
                      "offboarding_sessions": [{"personnel_id": "DEMO-PER-1"}], "assets": [{"asset_id": "DEMO-P-1"}]})
    real = _Rows({"documents": [{"access_tags": {"site_id": "SITE_001"}}], "briefs": [{"asset_id": "EQ-101"}],
                  "knowledge_conflicts": [{"asset_id": None}], "moc_items": [{"asset_id": "V-247"}],
                  "operational_events": [{"site_id": "SITE_001", "asset_id": "EQ-101"}],
                  "offboarding_sessions": [{"personnel_id": "P-77"}], "assets": [{"asset_id": "EQ-101"}]})
    async def resolves_to(asset):
        async def fake(supabase, work_order_id):
            return asset
        return fake

    for params in ({"document_id": "d"}, {"brief_id": "b"}, {"conflict_id": "c"}, {"moc_id": "m"}, {"session_id": "s"}, {"event_id": "e"}):
        assert await tenant.names_showcase_record(showcase, params), params
        assert not await tenant.names_showcase_record(real, params), params
    assert await tenant.names_showcase_record(showcase, {"asset_id": "DEMO-P-1"})
    assert await tenant.names_showcase_record(showcase, {"site_id": "SITE_DEMO_B"})
    monkeypatch.setattr(tenant, "work_order_asset", await resolves_to("DEMO-P-1"))
    assert await tenant.names_showcase_record(showcase, {"work_order_id": "WO-DEMO-1"})
    monkeypatch.setattr(tenant, "work_order_asset", await resolves_to("EQ-101"))
    assert not await tenant.names_showcase_record(real, {"work_order_id": "WO-1"})
    assert not await tenant.names_showcase_record(real, {"asset_id": "EQ-101", "site_id": "SITE_001", "document_id": "d"})
    assert not await tenant.names_showcase_record(_Rows({}), {"document_id": "gone"})  # unknown id: the handler 404s as before
    assert not await tenant.names_showcase_record(_Rows({}), {"limit": "5"})  # parameters that name nothing


async def test_the_read_fence_hides_showcase_records_from_real_accounts_only(monkeypatch):
    from api import dependencies as deps
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    async def fake_resolve(token, settings):
        return {"demo-token": DEMO, "real-token": REAL}.get(token)

    monkeypatch.setattr(deps, "resolve_token", fake_resolve)
    app = FastAPI(dependencies=[Depends(deps.showcase_read_fence)])
    app.dependency_overrides[deps.get_settings] = lambda: None
    app.dependency_overrides[deps.get_supabase] = lambda: _Rows({})
    app.add_api_route("/assets/{asset_id}", lambda asset_id: {"ok": asset_id}, methods=["GET"])
    app.add_api_route("/assets/", lambda: {"ok": "list"}, methods=["GET"])
    c = TestClient(app)
    demo, real = {"Authorization": "Bearer demo-token"}, {"Authorization": "Bearer real-token"}
    assert c.get("/assets/DEMO-P-1101A", headers=real).status_code == 404
    assert c.get("/assets/DEMO-P-1101A", headers=demo).status_code == 200
    assert c.get("/assets/EQ-101", headers=real).status_code == 200
    assert c.get("/assets/", headers=real).status_code == 200  # no path parameter: nothing to look up
    assert c.get("/assets/DEMO-P-1101A").status_code == 200  # no token: the route's own authentication decides


def test_the_read_fence_is_installed_and_every_by_id_read_names_a_parameter_it_understands():
    from api.dependencies import showcase_read_fence
    from api.main import create_app

    app = create_app()
    assert showcase_read_fence in [d.dependency for d in app.router.dependencies]
    understood = {"asset_id", "site_id", "work_order_id", *tenant.READ_BY_ID_TABLE}
    unknown = {
        (r.path, p) for r in app.routes if "GET" in getattr(r, "methods", ()) for p in r.param_convertors
        if p not in understood
    }
    assert not unknown, f"a by-id read names a record the read fence cannot recognise: {sorted(unknown)}"


# --- SHOWCASE_VISIBLE_TO_ALL: every login sees the whole plant -------------------------------------

def test_with_the_setting_on_every_caller_reads_the_showcase_and_the_demo_role_stays_fenced(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", True)
    assert tenant.sees_showcase(REAL) and tenant.sees_showcase(None) and tenant.sees_showcase(DEMO)
    assert tenant.hides_demo(REAL) is False
    q = _Q()
    assert tenant.scope(q, REAL, "asset_id") is q and tenant.scope_site(q, REAL) is q and tenant.scope_document_site(q, REAL) is q
    # Reads open up; what the demo role may WRITE does not change.
    with pytest.raises(HTTPException):
        tenant.guard_asset(DEMO, "EQ-101")
    assert tenant.feeds_statistics(REAL, "DEMO-P-1") is False  # a showcase asset never feeds real statistics


def test_with_the_setting_off_only_the_demo_role_reads_the_showcase(monkeypatch):
    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", False)
    assert not tenant.sees_showcase(REAL) and not tenant.sees_showcase(None) and tenant.sees_showcase(DEMO)
    assert tenant.hides_demo(REAL) is True and tenant.hides_demo(DEMO) is False


def test_the_setting_widens_a_site_pinned_role_to_the_showcase_sites_and_no_further(monkeypatch):
    from fastapi import HTTPException

    engineer = {"role": "engineer", "site_id": "SITE_001"}
    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", False)
    assert site_scope(engineer, None) == "SITE_001"
    with pytest.raises(HTTPException):
        site_scope(engineer, "SITE_DEMO")

    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", True)
    assert site_scope(engineer, None) == "SITE_001"  # still pinned: never "every site"
    assert site_scope(engineer, "SITE_001") == "SITE_001"
    assert site_scope(engineer, "SITE_DEMO") == "SITE_DEMO"  # a read may name a showcase site
    with pytest.raises(HTTPException) as other_real_site:
        site_scope(engineer, "SITE_002")  # another real site is a 403 whatever the setting says
    assert other_real_site.value.status_code == 403
    with pytest.raises(HTTPException):
        site_scope({"role": "engineer", "site_id": ""}, None)  # a blank site still means no rows, never all rows


def test_a_write_never_widens_with_the_setting(monkeypatch):
    from fastapi import HTTPException

    engineer = {"role": "engineer", "site_id": "SITE_001"}
    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", True)
    assert site_scope(engineer, "SITE_001", write=True) == "SITE_001"
    for site in ("SITE_DEMO", "SITE_002"):
        with pytest.raises(HTTPException):
            site_scope(engineer, site, write=True)


def test_a_pinned_caller_reads_its_own_site_and_the_showcase_but_not_another_real_site(monkeypatch):
    engineer = {"role": "engineer", "site_id": "SITE_001"}
    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", True)
    assert tenant.on_visible_site(engineer, "SITE_001", "SITE_001")
    assert tenant.on_visible_site(engineer, "SITE_DEMO_B", "SITE_001")
    assert not tenant.on_visible_site(engineer, "SITE_002", "SITE_001")
    assert tenant.on_visible_site(ADMIN, "SITE_002", None)  # None: every site, as for admin

    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", False)
    assert not tenant.on_visible_site(engineer, "SITE_DEMO", "SITE_001")

    q = _Q()
    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", True)
    assert "SITE_001" in str(tenant.pin_site(q, engineer, "SITE_001").ops) and "SITE_DEMO" in str(tenant.pin_site(_Q(), engineer, "SITE_001").ops)
    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", False)
    assert "SITE_DEMO" not in str(tenant.pin_site(_Q(), engineer, "SITE_001").ops)
    assert tenant.pin_site(_Q(), engineer, None).ops == []  # no pin: untouched


def test_every_site_filtered_cypher_pins_to_the_site_and_the_showcase():
    from api.routers import compliance
    from api.services import corpus

    for cypher in (compliance._GAP_CYPHER, compliance._DASHBOARD_CYPHER, compliance._AUDIT_CYPHER, corpus._TEST_ASSET_COUNT_CYPHER):
        assert tenant.SITE_PIN_CYPHER in cypher
        assert "a.site_id = $site_id)" not in cypher  # no bare equality that would hide the showcase or widen past the site


async def test_the_read_fence_steps_aside_when_everyone_sees_the_showcase(monkeypatch):
    from api import dependencies as deps
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    async def fake_resolve(token, settings):
        return REAL

    monkeypatch.setattr(deps, "resolve_token", fake_resolve)
    app = FastAPI(dependencies=[Depends(deps.showcase_read_fence)])
    app.dependency_overrides[deps.get_settings] = lambda: None
    app.dependency_overrides[deps.get_supabase] = lambda: _Rows({})
    app.add_api_route("/assets/{asset_id}", lambda asset_id: {"ok": asset_id}, methods=["GET"])
    c, h = TestClient(app), {"Authorization": "Bearer t"}
    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", False)
    assert c.get("/assets/DEMO-P-1101A", headers=h).status_code == 404
    monkeypatch.setattr(tenant, "VISIBLE_TO_ALL", True)
    assert c.get("/assets/DEMO-P-1101A", headers=h).status_code == 200


def test_the_shipped_default_shows_the_showcase_to_everyone_and_the_api_applies_it_at_startup():
    import inspect

    from api import main
    from api.config import Settings

    assert Settings().SHOWCASE_VISIBLE_TO_ALL is True
    assert "tenant.VISIBLE_TO_ALL = settings.SHOWCASE_VISIBLE_TO_ALL" in inspect.getsource(main.lifespan)
