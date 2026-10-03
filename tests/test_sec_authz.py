"""Security review, group AUTHORIZATION / EVENTS / SITE SCOPE (H2, H3, H7 route, M2, M6, M7, M8, M9,
M11/M12 voice upload, L11).

Service-free: routers are mounted on a bare FastAPI app with their store dependencies overridden by
in-memory fakes. No stack, no secrets, no network, nothing written to any store.
"""

import hashlib
import hmac
import io
import re
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from api import dependencies as deps
from api.config import Settings
from api.middleware.opa import action_for
from api.routers import (
    annotations as annotations_router,
)
from api.routers import (
    assets as assets_router,
)
from api.routers import (
    briefs as briefs_router,
)
from api.routers import (
    elicitation as elicitation_router,
)
from api.routers import (
    events as events_router,
)
from api.routers import (
    governance as governance_router,
)
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

ENGINEER = {"user_id": "eng-1", "role": "engineer", "site_id": "SITE_001", "email": "eng@x.test"}
FIELD = {"user_id": "fw-1", "role": "field_worker", "site_id": "SITE_001", "email": "fw@x.test"}
COMPLIANCE = {"user_id": "co-1", "role": "compliance", "site_id": "SITE_001"}
RELIABILITY = {"user_id": "rel-1", "role": "reliability", "site_id": "SITE_001"}
ADMIN = {"user_id": "adm-1", "role": "admin", "site_id": "SITE_001"}
OTHER_SITE_ENGINEER = {"user_id": "eng-2", "role": "engineer", "site_id": "SITE_002"}


# =============================================================================
# Fakes
# =============================================================================


class FakeQuery:
    """Chainable stand-in for the supabase-py query builder; records every call."""

    def __init__(self, db: "FakeSupabase", table: str):
        self.db, self.table_name, self.ops = db, table, []

    @property
    def not_(self):
        """`query.not_.like(...)`: negation is a property in postgrest-py, so it must not be a call."""
        self.ops.append(("not_", (), {}))
        return self

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.ops.append((name, args, kwargs))
            return self

        return call

    def execute(self):
        self.db.calls.append((self.table_name, self.ops))
        verbs = {op[0] for op in self.ops}
        for verb in ("insert", "upsert", "update", "delete"):
            if verb in verbs:
                payload = next(op[1][0] for op in self.ops if op[0] == verb)
                self.db.writes.append((self.table_name, verb, payload))
        rows = self.db.rows.get(self.table_name, [])
        if "insert" in verbs and not rows:
            rows = [{"item_id": "q-1", "id": "ann-1"}]
        count = self.db.counts.get(self.table_name)
        return SimpleNamespace(data=rows, count=count)


class FakeStorageBucket:
    def __init__(self, db):
        self.db = db

    def upload(self, path, data, opts=None):
        self.db.uploads.append(path)


class FakeSupabase:
    def __init__(self, rows=None, counts=None):
        self.rows, self.counts = rows or {}, counts or {}
        self.calls, self.writes, self.uploads = [], [], []
        self.storage = SimpleNamespace(from_=lambda _b: FakeStorageBucket(self))

    def table(self, name):
        return FakeQuery(self, name)

    def inserted(self, table):
        return [p for t, v, p in self.writes if t == table and v == "insert"]

    def filters(self, table, column):
        """Every `.eq(column, value)` applied to `table` across the recorded queries."""
        out = []
        for t, ops in self.calls:
            if t == table:
                out += [op[1][1] for op in ops if op[0] == "eq" and op[1][0] == column]
        return out


def _client(router, prefix, user, supabase=None, settings=None, extra=None):
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[deps.get_current_user] = lambda: user
    app.dependency_overrides[deps.get_supabase] = lambda: supabase
    for dep in (deps.get_redis, deps.get_neo4j_driver, deps.get_qdrant_client, deps.get_es_client):
        app.dependency_overrides[dep] = lambda: None
    if settings is not None:
        app.dependency_overrides[deps.get_settings] = lambda: settings
    for dep, value in (extra or {}).items():
        app.dependency_overrides[dep] = value
    return TestClient(app, raise_server_exceptions=True)


# =============================================================================
# H2: ingest routes are not callable by every role
# =============================================================================

INGEST_PATHS = [
    "/events/work-order",
    "/events/ptw",
    "/events/shift-handover",
    "/events/alarm",
    "/events/tag-out",
    "/events/inspection-complete",
]


@pytest.mark.parametrize("path", INGEST_PATHS)
def test_ingest_routes_map_to_ingest_event(path):
    assert action_for("POST", path) == "ingest_event"


@pytest.mark.parametrize(
    "path",
    [
        "/events/deviation-flag",
        "/events/deviation-flag/abc/resolve",
        "/events/plant-state",
        "/events/some-event-id/ack",
    ],
)
def test_field_worker_event_flows_stay_on_write_api(path):
    # Field workers must still flag deviations and acknowledge briefs.
    assert action_for("POST", path) == "write_api"


def test_ingest_gate_never_applies_to_cors_preflight():
    assert action_for("OPTIONS", "/events/work-order") is None


@pytest.mark.parametrize("path", INGEST_PATHS)
@pytest.mark.parametrize("user", [FIELD, COMPLIANCE], ids=["field_worker", "compliance"])
def test_router_refuses_ingest_for_non_staff(path, user):
    """Defence in depth behind OPA: the handler's own role guard holds even if OPA is bypassed."""
    client = _client(events_router.router, "/events", user, FakeSupabase())
    assert client.post(path, json={}).status_code == 403


def _work_order(site="SITE_001"):
    return {
        "source_system": "SAP_PM", "site_id": site, "work_order_id": "WO-1", "asset_id": "EQ-101",
        "failure_code": "SEAL", "description": "leak",
    }


def test_engineer_cannot_report_for_another_site():
    client = _client(events_router.router, "/events", ENGINEER, FakeSupabase())
    assert client.post("/events/work-order", json=_work_order("SITE_002")).status_code == 403


def test_engineer_cannot_set_another_sites_plant_state():
    client = _client(events_router.router, "/events", ENGINEER, FakeSupabase())
    r = client.post("/events/plant-state", json={"site_id": "SITE_002", "state": "emergency"})
    assert r.status_code == 403


REGO = Path(__file__).resolve().parents[1] / "infra" / "policies" / "kairos.rego"


@pytest.mark.skipif(not REGO.exists(), reason="infra/ is not mounted in this container")
def test_rego_grants_ingest_event_to_staff_only_and_marks_it_sensitive():
    text = REGO.read_text()

    def role_actions(role):
        line = next(ln for ln in text.splitlines() if ln.strip().startswith(f'"{role}":'))
        return set(re.findall(r'"([a-z_*]+)"', line.split(":", 1)[1]))

    for allowed in ("engineer", "reliability", "admin"):
        assert "ingest_event" in role_actions(allowed) or role_actions(allowed) == {"*"}
    for denied in ("field_worker", "compliance"):
        assert "ingest_event" not in role_actions(denied)
    # Without this the catch-all `write_api` rule would hand the action to every role.
    sensitive = text[text.index("_sensitive_actions :="):]
    assert '"ingest_event"' in sensitive[: sensitive.index("}")]


# =============================================================================
# H3: inspection evidence
# =============================================================================


class FakeBus:
    def __init__(self, *_a, **_k):
        pass

    async def is_duplicate(self, *_a, **_k):
        return False

    async def mark_seen(self, *_a, **_k):
        return None

    async def publish(self, *_a, **_k):
        return "1-0"

    async def correlate_events(self, *_a, **_k):
        return None


class FakeGraph:
    edges: list = []

    def __init__(self, *_a, **_k):
        pass

    async def merge_event_node(self, **_k):
        return None

    async def merge_document_node(self, *_a, **_k):
        return None

    async def create_knowledge_edge(self, **kwargs):
        FakeGraph.edges.append(kwargs)
        return {"edge_id": "e-1"}


def _inspection(**over):
    body = {
        "source_system": "app", "site_id": "SITE_001", "asset_id": "EQ-101", "inspection_type": "visual",
        "result": "passed", "document_id": "DOC-1",
    }
    body.update(over)
    return body


@pytest.fixture
def inspection_env(monkeypatch):
    async def canonical(asset_id, *_a, **_k):
        return asset_id

    monkeypatch.setattr(events_router, "_canonical_asset", canonical)
    monkeypatch.setattr(events_router, "EventBusService", FakeBus)
    monkeypatch.setattr("api.services.graph.GraphService", FakeGraph)
    FakeGraph.edges = []


def test_inspection_document_must_exist_in_the_vault(inspection_env):
    db = FakeSupabase(rows={"documents": []})
    client = _client(events_router.router, "/events", ENGINEER, db)
    assert client.post("/events/inspection-complete", json=_inspection()).status_code == 422
    assert not db.inserted("operational_events") and not FakeGraph.edges


def test_inspection_document_must_be_an_inspection_report(inspection_env):
    db = FakeSupabase(rows={"documents": [{"document_id": "DOC-1", "document_type": "procedure"}]})
    client = _client(events_router.router, "/events", ENGINEER, db)
    assert client.post("/events/inspection-complete", json=_inspection()).status_code == 422
    assert not FakeGraph.edges


def test_caller_cannot_raise_the_evidence_edge_confidence(inspection_env):
    db = FakeSupabase(rows={"documents": [{"document_id": "DOC-1", "document_type": "inspection_report"}]})
    client = _client(events_router.router, "/events", ENGINEER, db)
    assert client.post("/events/inspection-complete", json=_inspection(confidence=1.0)).status_code == 202
    assert FakeGraph.edges[-1]["confidence"] == events_router.INSPECTION_EVIDENCE_CONFIDENCE
    # lowering is still honoured, and below 0.7 the finding goes to quarantine under the real actor
    r = client.post("/events/inspection-complete", json=_inspection(confidence=0.5, event_id="ev-2"))
    assert r.status_code == 202 and FakeGraph.edges[-1]["confidence"] == 0.5
    assert db.inserted("quarantine_items")[0]["submitted_by"] == "eng-1"


# =============================================================================
# M6: actor comes from the token
# =============================================================================


def _ack_db(**tables):
    rows = {"operational_events": [{"event_id": "ev-1", "site_id": "SITE_001"}], "briefs": [{"brief_id": "b-1"}]}
    return FakeSupabase(rows={**rows, **tables})


def test_ack_records_the_token_user_not_the_body():
    db = _ack_db()
    client = _client(events_router.router, "/events", FIELD, db)
    body = {"user_id": "someone-else", "role": "admin", "signature": "forged", "notes": "n"}
    assert client.post("/events/ev-1/ack", json=body).json()["user_id"] == "fw-1"
    row = db.inserted("audit_log")[0]
    assert row["performed_by"] == "fw-1"
    assert row["details"]["role"] == "field_worker"
    assert row["details"]["signature"] != "forged" and row["details"]["signature_alg"] == "HMAC-SHA256"


def test_ack_of_an_unknown_or_other_site_event_is_a_404_and_writes_nothing():
    for events in ([], [{"event_id": "ev-1", "site_id": "SITE_002"}]):
        db = _ack_db(operational_events=events)
        client = _client(events_router.router, "/events", FIELD, db)
        assert client.post("/events/ev-1/ack", json={}).status_code == 404
        assert db.inserted("audit_log") == []


def test_ack_by_a_non_recipient_is_refused_but_staff_may_ack():
    db = _ack_db(briefs=[])
    assert _client(events_router.router, "/events", FIELD, db).post("/events/ev-1/ack", json={}).status_code == 403
    assert db.inserted("audit_log") == []
    db = _ack_db(briefs=[])
    assert _client(events_router.router, "/events", ENGINEER, db).post("/events/ev-1/ack", json={}).status_code == 200
    assert len(db.inserted("audit_log")) == 1


def test_a_repeated_ack_is_idempotent_and_writes_no_second_row():
    db = _ack_db(audit_log=[{"id": 1}])  # the first acknowledgement already exists
    out = _client(events_router.router, "/events", FIELD, db).post("/events/ev-1/ack", json={}).json()
    assert out["repeat"] is True and out["user_id"] == "fw-1"
    assert db.inserted("audit_log") == []


def test_deviation_flag_reporter_is_the_token_user(monkeypatch):
    async def canonical(asset_id, *_a, **_k):
        return asset_id

    monkeypatch.setattr(events_router, "_canonical_asset", canonical)
    monkeypatch.setattr(events_router, "EventBusService", FakeBus)
    db = FakeSupabase(rows={"briefs": []})
    client = _client(events_router.router, "/events", FIELD, db)
    r = client.post("/events/deviation-flag", json={"asset_id": "EQ-1", "description": "d", "reported_by": "boss"})
    assert r.status_code == 202
    assert db.inserted("quarantine_items")[0]["submitted_by"] == "fw-1"
    assert db.inserted("audit_log")[0]["performed_by"] == "fw-1"


def test_tag_out_audit_actor_is_the_token_user(monkeypatch):
    async def canonical(asset_id, *_a, **_k):
        return asset_id

    monkeypatch.setattr(events_router, "_canonical_asset", canonical)
    monkeypatch.setattr(events_router, "EventBusService", FakeBus)
    monkeypatch.setattr("api.services.graph.GraphService", FakeGraph)
    monkeypatch.setattr(events_router.assemble_brief, "apply_async", lambda **_k: SimpleNamespace(id="t-1"))
    db = FakeSupabase()
    client = _client(events_router.router, "/events", ENGINEER, db)
    body = {"source_system": "app", "site_id": "SITE_001", "asset_id": "EQ-1", "tag_out_reason": "r",
            "performed_by": "forged-name"}
    assert client.post("/events/tag-out", json=body).status_code == 202
    audit = db.inserted("audit_log")[0]
    assert audit["performed_by"] == "eng-1"
    assert audit["details"]["reported_performed_by"] == "forged-name"


def test_elicitation_responses_submitter_is_the_token_user():
    class Temporal:
        async def execute_workflow(self, name, args, **_k):
            self.args = args
            return {"item_id": "i-1"}

    temporal = Temporal()
    db = FakeSupabase(rows={"elicitation_sessions": []})
    client = _client(
        elicitation_router.router, "/elicitation", FIELD, db, extra={deps.get_temporal_client: lambda: temporal}
    )
    r = client.post("/elicitation/WO-1/responses", json={"responses": [{"answer": "a"}], "submitted_by": "boss"})
    assert r.status_code == 200 and temporal.args["submitted_by"] == "fw-1"


# =============================================================================
# M7: validation corpus and override flooding
# =============================================================================

ANNOTATION = {"document_id": "DOC-1", "entity_text": "HE-302", "entity_type": "ASSET_TAG", "is_correct": True}


@pytest.mark.parametrize(("user", "inserted"), [(FIELD, False), (ENGINEER, False), (RELIABILITY, True), (ADMIN, True)])
def test_only_reliability_and_admin_feed_the_validation_corpus(user, inserted):
    db = FakeSupabase()
    client = _client(annotations_router.router, "/annotations", user, db)
    assert client.post("/annotations/", json=ANNOTATION).status_code == 201
    assert bool(db.inserted("validation_corpus")) is inserted
    assert db.inserted("ner_annotations"), "the correction itself is still recorded for every role"


@pytest.fixture
def overrides(monkeypatch):
    from api.services.circuit_breaker import CircuitBreakerService

    calls = []

    async def record(self, asset_class, document_id, override_type):
        calls.append((asset_class, document_id))

    monkeypatch.setattr(CircuitBreakerService, "record_override", record)
    return calls


def test_a_users_repeat_correction_on_one_document_records_one_override(overrides):
    wrong = {**ANNOTATION, "is_correct": False}
    db = FakeSupabase(rows={"quarantine_items": []})
    client = _client(annotations_router.router, "/annotations", FIELD, db)
    assert client.post("/annotations/", json=wrong).status_code == 201
    assert len(overrides) == 1

    # the same user has now corrected that document before
    db.rows["ner_annotations"] = [{"id": "a", "entity_text": "HE-302"}]
    assert client.post("/annotations/", json=wrong).status_code == 201
    assert len(overrides) == 1


def test_corrections_are_rate_limited_per_user(overrides):
    db = FakeSupabase(counts={"ner_annotations": annotations_router._ANNOTATIONS_PER_HOUR})
    client = _client(annotations_router.router, "/annotations", FIELD, db)
    assert client.post("/annotations/", json={**ANNOTATION, "is_correct": False}).status_code == 429
    assert not overrides and not db.inserted("ner_annotations")


# =============================================================================
# M8: site boundary
# =============================================================================


class FakeAssetGraph:
    def __init__(self, nodes):
        self.nodes = nodes

    async def get_asset(self, asset_id):
        return self.nodes.get(asset_id)


async def test_scoped_asset_hides_other_sites_behind_a_404():
    graph = FakeAssetGraph({"EQ-1": {"asset_id": "EQ-1", "site_id": "SITE_001"}})
    assert (await assets_router.scoped_asset(graph, "EQ-1", ENGINEER))["asset_id"] == "EQ-1"
    assert (await assets_router.scoped_asset(graph, "EQ-1", ADMIN))["asset_id"] == "EQ-1"
    for user in (OTHER_SITE_ENGINEER, ENGINEER):
        target = "EQ-9" if user is ENGINEER else "EQ-1"
        with pytest.raises(HTTPException) as exc:
            await assets_router.scoped_asset(graph, target, user)
        assert exc.value.status_code == 404


async def test_scoped_asset_fails_closed_for_an_account_with_no_site():
    graph = FakeAssetGraph({"EQ-1": {"asset_id": "EQ-1", "site_id": ""}})
    with pytest.raises(HTTPException) as exc:
        await assets_router.scoped_asset(graph, "EQ-1", {"user_id": "u", "role": "engineer", "site_id": ""})
    assert exc.value.status_code == 403


def test_single_asset_create_is_create_only_and_site_scoped():
    source = Path(assets_router.__file__).read_text()
    single = source[source.index('@router.post("/", summary="Register a new canonical asset"'):]
    single = single[: single.index("async def _issue_counts")]
    assert ".upsert(" not in single and ".insert(supabase_row)" in single

    payload = {"tag_number": "T", "name": "n", "equipment_class": "PUMP", "criticality": "critical",
               "site_id": "SITE_002", "facility_id": "F", "confirmed_by_user_id": "x"}
    client = _client(assets_router.router, "/assets", ENGINEER, FakeSupabase())
    assert client.post("/assets/", json=payload).status_code == 403


def test_events_reads_are_site_scoped():
    db = FakeSupabase(rows={"operational_events": [{"event_id": "e", "site_id": "SITE_002", "payload": {}}]})
    client = _client(events_router.router, "/events", ENGINEER, db)
    assert client.get("/events/").status_code == 200
    assert db.filters("operational_events", "site_id") == ["SITE_001"]
    assert client.get("/events/e").status_code == 404  # that event belongs to SITE_002

    admin_db = FakeSupabase(rows={"operational_events": [{"event_id": "e", "site_id": "SITE_002", "payload": {}}]})
    assert _client(events_router.router, "/events", ADMIN, admin_db).get("/events/e").status_code == 200


def test_audit_pack_query_is_site_filtered():
    from api.routers import compliance

    assert "$site_id IS NULL OR a.site_id = $site_id" in compliance._AUDIT_CYPHER


# =============================================================================
# M9: off-boarding
# =============================================================================

SESSION_ID = "6a3acd01-a8c3-4fe5-a43e-923fedf4611c"


def _offboarding_db(personnel_id="expert-1"):
    row = {"id": SESSION_ID, "personnel_id": personnel_id, "personnel_email": "expert@x.test",
           "total_sessions": 2, "status": "scheduled"}
    return FakeSupabase(rows={"offboarding_sessions": [row], "offboarding_session_items": []})


class _MaybeSingle(FakeQuery):
    """`.maybe_single()` yields one row, not a list."""

    def execute(self):
        res = super().execute()
        if any(op[0] == "maybe_single" for op in self.ops):
            res.data = res.data[0] if res.data else None
        return res


class OffboardingSupabase(FakeSupabase):
    def table(self, name):
        return _MaybeSingle(self, name)


def _off_client(user, personnel_id="expert-1"):
    base = _offboarding_db(personnel_id)
    db = OffboardingSupabase(rows=base.rows, counts={"offboarding_session_items": 0})
    return _client(elicitation_router.router, "/elicitation", user, db), db


def test_offboarding_list_hides_other_peoples_programmes():
    client, _ = _off_client(FIELD)
    assert client.get("/elicitation/offboarding").json()["total"] == 0
    staff, _ = _off_client(ENGINEER)
    assert staff.get("/elicitation/offboarding").json()["total"] == 1
    subject, _ = _off_client({"user_id": "expert-1", "role": "field_worker", "site_id": "SITE_001"})
    assert subject.get("/elicitation/offboarding").json()["total"] == 1


@pytest.mark.parametrize("suffix", ["", "/questions"])
def test_offboarding_detail_and_questions_need_staff_or_the_subject(suffix):
    url = f"/elicitation/offboarding/{SESSION_ID}{suffix}"
    assert _off_client(FIELD)[0].get(url).status_code == 403
    assert _off_client(COMPLIANCE)[0].get(url).status_code == 403
    assert _off_client(ENGINEER)[0].get(url).status_code != 403
    by_email = {"user_id": "u-9", "role": "field_worker", "site_id": "SITE_001", "email": "EXPERT@x.test"}
    assert _off_client(by_email)[0].get(url).status_code != 403


def test_only_staff_or_the_subject_can_complete_a_programme_item():
    body = {"item_id": "item-1", "responses": []}
    url = f"/elicitation/offboarding/{SESSION_ID}/responses"
    client, db = _off_client(FIELD)
    assert client.post(url, json=body).status_code == 403
    assert not db.inserted("quarantine_items") and not any(v == "update" for _, v, _ in db.writes)


def test_offboarding_response_submitter_is_the_token_user():
    subject = {"user_id": "expert-1", "role": "field_worker", "site_id": "SITE_001"}
    client, db = _off_client(subject)
    db.rows["offboarding_session_items"] = [{"id": "item-1", "session_number": 1, "equipment_family": "PUMP",
                                             "questions": []}]
    r = client.post(f"/elicitation/offboarding/{SESSION_ID}/responses",
                    json={"item_id": "item-1", "responses": [], "submitted_by": "boss"})
    assert r.status_code == 200
    assert db.inserted("quarantine_items")[0]["submitted_by"] == "expert-1"


# =============================================================================
# M11 / M12: voice upload size and storage path
# =============================================================================


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("note.wav", "note.wav"),
        ("../../etc/passwd", "passwd"),
        ("..\\..\\win.ini", "win.ini"),
        ("a b/c d.mp3", "c_d.mp3"),
        ("..", "fallback"),
        ("", "fallback"),
        (None, "fallback"),
        (".hidden", "hidden"),
        ("naïve$%.wav", "na_ve__.wav"),
    ],
)
def test_safe_segment(raw, expected):
    assert elicitation_router._safe_segment(raw, "fallback") == expected


def _voice_client(monkeypatch, max_mb=1):
    monkeypatch.setattr(elicitation_router, "get_settings", lambda: Settings(MAX_UPLOAD_MB=max_mb))
    queued = []
    monkeypatch.setattr(
        "workers.voice_transcription.transcribe_voice_note.delay",
        lambda **kw: queued.append(kw) or SimpleNamespace(id="t-1"),
    )
    db = FakeSupabase(rows={"quarantine_items": []})
    return _client(elicitation_router.router, "/elicitation", FIELD, db), db, queued


def test_voice_upload_over_the_limit_is_rejected_before_storage(monkeypatch):
    client, db, queued = _voice_client(monkeypatch, max_mb=1)
    big = io.BytesIO(b"\0" * (2 * 1024 * 1024))
    r = client.post("/elicitation/WO-1/voice", files={"file": ("a.wav", big, "audio/wav")})
    assert r.status_code == 413
    assert not db.uploads and not queued


def test_voice_upload_path_is_sanitised_and_submitter_is_the_token_user(monkeypatch):
    client, db, queued = _voice_client(monkeypatch)
    r = client.post(
        "/elicitation/WO-1/voice",
        data={"submitted_by": "boss"},
        files={"file": ("../../other-bucket/x y.wav", io.BytesIO(b"abc"), "audio/wav")},
    )
    assert r.status_code == 202
    sha8 = hashlib.sha256(b"abc").hexdigest()[:8]
    assert db.uploads == [f"voice_notes/WO-1/{sha8}_x_y.wav"]
    assert queued[0]["submitted_by"] == "fw-1" and queued[0]["filename"] == "x_y.wav"


# =============================================================================
# M2 / L11: briefs
# =============================================================================


def test_inbox_filters_recipients_with_in_not_an_or_string():
    source = Path(briefs_router.__file__).read_text()
    assert "recipient_user_id.eq.{" not in source
    # a hostile site claim is just another value in the list, never extra filter syntax
    hostile = {"user_id": "u1", "role": "field_worker", "site_id": "S,recipient_user_id.neq.x"}
    assert briefs_router._brief_recipients(hostile) == ["u1", "site-S,recipient_user_id.neq.x"]


def test_ack_is_final():
    db = FakeSupabase(rows={"briefs": [{"brief_id": "b-1", "requires_countersignature": False,
                                        "acknowledged_by": "fw-1", "acknowledged_at": "2026-01-01T00:00:00Z"}]})
    client = _client(briefs_router.router, "/briefs", FIELD, db)
    assert client.post("/briefs/b-1/ack").status_code == 409
    assert not db.writes


def test_ack_of_an_unacknowledged_brief_still_works():
    db = FakeSupabase(rows={"briefs": [{"brief_id": "b-1", "requires_countersignature": False,
                                        "acknowledged_by": None, "acknowledged_at": None}]})
    client = _client(briefs_router.router, "/briefs", FIELD, db)
    assert client.post("/briefs/b-1/ack").json()["status"] == "acknowledged"


def test_feedback_requires_being_able_to_read_the_brief():
    brief = {"brief_id": "b-1", "recipient_user_id": "someone-else", "requires_countersignature": False}
    body = {"rating": "accurate"}
    db = FakeSupabase(rows={"briefs": [brief]})
    assert _client(briefs_router.router, "/briefs", FIELD, db).post("/briefs/b-1/feedback", json=body).status_code == 404
    assert not db.inserted("brief_feedback")

    mine = {**brief, "recipient_user_id": "fw-1"}
    db = FakeSupabase(rows={"briefs": [mine]})
    assert _client(briefs_router.router, "/briefs", FIELD, db).post("/briefs/b-1/feedback", json=body).status_code == 200
    assert db.inserted("brief_feedback")


# =============================================================================
# H7: MoC webhook
# =============================================================================

SECRET = "s3cret"


def _sign(body: bytes, ts: float, secret=SECRET) -> str:
    return hmac.new(secret.encode(), str(int(ts)).encode() + b"." + body, hashlib.sha256).hexdigest()


def _verify(body=b'{"a": 1}', *, secret=SECRET, ts=None, sig=None, dev=False, now=None):
    now = time.time() if now is None else now
    ts = now if ts is None else ts
    governance_router.verify_moc_webhook(
        secret, body, _sign(body, ts) if sig is None else sig, str(int(ts)), dev_unsigned_ok=dev, now=now
    )


def test_a_fresh_correct_signature_passes():
    _verify()


def test_signature_covers_the_raw_bytes():
    body = b'{"moc_id": "M", "status": "approved"}'
    now = time.time()
    sig = _sign(body, now)
    with pytest.raises(HTTPException) as exc:  # same JSON, different bytes
        _verify(b'{"moc_id":"M","status":"approved"}', sig=sig, now=now)
    assert exc.value.status_code == 401
    with pytest.raises(HTTPException):
        _verify(b'{"moc_id": "M", "status": "approved", "approved_by": "x"}', sig=sig, now=now)


def test_a_stale_or_future_request_is_rejected_even_when_correctly_signed():
    now = time.time()
    for ts in (now - 3600, now + 3600):
        with pytest.raises(HTTPException) as exc:
            _verify(ts=ts, now=now)
        assert exc.value.status_code == 401


def test_the_timestamp_is_part_of_the_signed_material():
    now = time.time()
    body = b"{}"
    old_sig = _sign(body, now - 10)
    with pytest.raises(HTTPException):  # a captured signature cannot be re-stamped as fresh
        governance_router.verify_moc_webhook(SECRET, body, old_sig, str(int(now)), dev_unsigned_ok=False, now=now)


@pytest.mark.parametrize("missing", ["sig", "ts", "both"])
def test_missing_headers_are_rejected_when_a_secret_is_set(missing):
    now = time.time()
    sig = None if missing in ("sig", "both") else _sign(b"{}", now)
    ts = None if missing in ("ts", "both") else str(int(now))
    with pytest.raises(HTTPException) as exc:
        governance_router.verify_moc_webhook(SECRET, b"{}", sig, ts, dev_unsigned_ok=False, now=now)
    assert exc.value.status_code == 401


def test_no_secret_never_means_unsigned_where_auth_is_enforced():
    with pytest.raises(HTTPException) as exc:
        governance_router.verify_moc_webhook(None, b"{}", None, None, dev_unsigned_ok=False)
    assert exc.value.status_code == 503
    # a blank secret is no secret
    with pytest.raises(HTTPException):
        governance_router.verify_moc_webhook("", b"{}", None, None, dev_unsigned_ok=False)


def test_unsigned_is_accepted_only_where_the_dev_bypass_is_allowed():
    governance_router.verify_moc_webhook(None, b"{}", None, None, dev_unsigned_ok=True)
    assert Settings(APP_ENV="development", APP_DEBUG=True).dev_bypass_allowed is True
    assert Settings(APP_ENV="development", APP_DEBUG=False).dev_bypass_allowed is False


def test_webhook_route_is_exempt_from_opa_only_by_exact_path():
    assert action_for("POST", "/governance/moc/webhook") is None
    assert action_for("POST", "/governance/moc/MOC-1/approve") == "resolve_admin_conflict"
    assert action_for("POST", "/governance/moc") == "resolve_admin_conflict"


def _webhook_client(secret, db, debug=False):
    settings = Settings(MOC_WEBHOOK_SECRET=secret, APP_ENV="development", APP_DEBUG=debug)
    return _client(governance_router.router, "/governance", None, db, settings=settings,
                   extra={deps.get_neo4j_driver: lambda: None})


def test_webhook_end_to_end_uses_the_raw_body_and_signed_timestamp():
    db = FakeSupabase(rows={"moc_items": [{"moc_id": "M-1", "status": "draft", "conflict_id": None}]})
    client = _webhook_client(SECRET, db)
    body = b'{"moc_id": "M-1", "status": "rejected", "approved_by": "eng"}'
    now = time.time()
    headers = {"X-Webhook-Signature": _sign(body, now), "X-Webhook-Timestamp": str(int(now)),
               "Content-Type": "application/json"}
    assert client.post("/governance/moc/webhook", content=body, headers=headers).status_code == 200
    assert client.post("/governance/moc/webhook", content=body).status_code == 401
    tampered = body.replace(b"rejected", b"approved")
    assert client.post("/governance/moc/webhook", content=tampered, headers=headers).status_code == 401


def test_webhook_cannot_reopen_or_flip_an_approved_moc():
    db = FakeSupabase(rows={"moc_items": [{"moc_id": "M-1", "status": "approved", "conflict_id": None}]})
    client = _webhook_client(SECRET, db)
    body = b'{"moc_id": "M-1", "status": "rejected"}'
    now = time.time()
    headers = {"X-Webhook-Signature": _sign(body, now), "X-Webhook-Timestamp": str(int(now))}
    assert client.post("/governance/moc/webhook", content=body, headers=headers).status_code == 409
    assert not [w for w in db.writes if w[0] == "moc_items"]


def test_webhook_rejects_a_non_object_body():
    client = _webhook_client(None, FakeSupabase(), debug=True)
    assert client.post("/governance/moc/webhook", content=b"[1]").status_code == 400
    assert client.post("/governance/moc/webhook", content=b"not json").status_code == 400


# =============================================================================
# The OPA and rate-limit middleware decide on the routed path, not the Host-derived URL
# =============================================================================


def _middleware_client(middleware, **kwargs):
    app = FastAPI()

    @app.post("/events/work-order")
    async def work_order():
        return {"reached": True}

    app.add_middleware(middleware, **kwargs)
    return TestClient(app, raise_server_exceptions=True)


def test_opa_action_is_computed_from_the_routed_path_even_with_a_poisoned_host():
    """`Host: x/health` makes `request.url.path` `/health/events/work-order`, which the skip list
    treats as exempt, so OPA was never asked. The scope path is what the router matches."""
    from api.middleware.opa import OPAMiddleware

    client = _middleware_client(OPAMiddleware, opa_url="http://opa.invalid", settings=None, debug=False)
    for host in ("testserver", "x/health"):
        # Enforced route + no token + not dev => 401. A skipped route would have answered 200.
        assert client.post("/events/work-order", headers={"Host": host}).status_code == 401, host


def test_ratelimit_exemption_cannot_be_forged_through_the_host_header(monkeypatch):
    import api.middleware.ratelimit as rl

    hits = []

    class Redis:
        async def incr(self, key):
            hits.append(key)
            return 1

        async def expire(self, *_a):
            return True

    monkeypatch.setattr(rl.aioredis, "from_url", lambda *a, **k: Redis())
    client = _middleware_client(rl.RateLimitMiddleware, redis_url="redis://unused", limit_per_minute=10)
    assert client.post("/events/work-order", headers={"Host": "x/health"}).status_code == 200
    assert len(hits) == 1, "a Host-poisoned request must still be counted"


# =============================================================================
# C1: the demo identity, through the real OPAMiddleware
# =============================================================================

_DEMO_USER = {"user_id": "demo-1", "role": "demo", "site_id": "SITE_001", "email": "demo@kairos.local"}
# (method, path). Policy is the coarse layer: it lets the demo role reach every write route that the
# API fence then narrows to showcase rows (`test_tenant_isolation.py` covers the fence and the guards).
_DEMO_ROUTES = [
    ("GET", "/search/"), ("POST", "/search/synthesize"), ("POST", "/search/synthesize/stream"),
    ("POST", "/search/rca-pack"), ("POST", "/search/feedback"),
    ("GET", "/briefs/"), ("GET", "/assets/"), ("GET", "/documents/"),
    ("GET", "/compliance/dashboard"), ("GET", "/audit-log/"), ("GET", "/events/"),
    ("GET", "/governance/model-gate/history"), ("GET", "/elicitation/offboarding"),
    ("POST", "/documents/ingest"), ("POST", "/documents/D-1/supersede"),
    ("POST", "/documents/D-1/ocr-review/reject"), ("POST", "/assets/"),
    ("POST", "/assets/bulk"), ("POST", "/assets/EQ-1/aliases/x/confirm"),
    ("POST", "/events/work-order"), ("POST", "/events/plant-state"),
    ("POST", "/events/deviation-flag"), ("POST", "/events/abc/ack"),
    ("POST", "/briefs/B-1/ack"), ("POST", "/briefs/B-1/countersign"),
    ("POST", "/briefs/B-1/feedback"), ("POST", "/governance/quarantine/Q-1/promote"),
    ("POST", "/governance/conflicts/C-1/resolve"), ("POST", "/governance/moc/M-1/approve"),
    ("POST", "/annotations/"), ("POST", "/elicitation/offboarding"), ("POST", "/elicitation/W-1/responses"),
]


@pytest.mark.skipif(not REGO.exists(), reason="infra/ is not mounted in this container")
def test_a_demo_token_reads_everything_and_the_policy_admits_the_showcase_writes(monkeypatch):
    from api.middleware.opa import OPAMiddleware

    text = REGO.read_text()
    line = next(ln for ln in text.splitlines() if ln.strip().startswith('"demo":'))
    grants = set(re.findall(r'"([a-z_*]+)"', line.split(":", 1)[1]))

    async def fake_user(self, request):
        return dict(_DEMO_USER)

    async def fake_opa(self, user, action, resource):
        # The same decision the rego makes for demo: its explicit list, nothing from the catch-all.
        return action in grants

    monkeypatch.setattr(OPAMiddleware, "_user_from_request", fake_user)
    monkeypatch.setattr(OPAMiddleware, "_ask_opa", fake_opa)

    app = FastAPI()
    for method, path in _DEMO_ROUTES:
        app.add_api_route(path, lambda: {"reached": True}, methods=[method])
    app.add_middleware(OPAMiddleware, opa_url="http://opa.invalid", settings=None, debug=False)
    client = TestClient(app)

    for method, path in _DEMO_ROUTES:
        assert client.request(method, path).status_code == 200, (method, path)


def test_the_demo_user_resolves_from_app_metadata_with_the_demo_role(monkeypatch):
    deps._auth_cache.clear()
    user = SimpleNamespace(
        id="u-demo", email="demo@kairos.local",
        app_metadata={"role": "demo", "site_id": "SITE_001"},
        # a visitor editing their own user_metadata must not be able to promote themselves
        user_metadata={"role": "admin"},
    )
    client = SimpleNamespace(auth=SimpleNamespace(get_user=lambda token: SimpleNamespace(user=user)))
    monkeypatch.setattr(deps, "create_client", lambda *a, **k: client)
    import asyncio

    resolved = asyncio.run(deps.resolve_token("demo-token", Settings(AUTH_CACHE_TTL_SECONDS=0)))
    deps._auth_cache.clear()
    assert resolved["role"] == "demo" and resolved["site_id"] == "SITE_001"
