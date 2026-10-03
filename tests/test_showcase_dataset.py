"""
The showcase plant: the dataset, its markers, and the loader's safety rails.

Service-free. What matters here is the property the whole feature rests on: every row the loader can
write is recognisably showcase (`api/services/tenant.py`), so a real account never sees it, and
nothing in it can collide with or join real data. The loader's own writes are exercised only through
its pure pieces; the cloud write itself is a deliberate step the owner approves.
"""

import inspect
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from api.services import tenant
from scripts import load_showcase
from scripts.showcase import files
from scripts.showcase.docs import CONFLICTS, build_documents
from scripts.showcase.history import build_showcase, unmarked
from scripts.showcase.spec import GENERAL_ASSET, SITE_A, SITE_B, build_assets

ANCHOR = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
DEMO_USER = "11111111-1111-1111-1111-111111111111"
DOCTYPES = {"oem_manual", "procedure", "inspection_report", "ptw", "shift_log", "regulation", "pid_drawing"}


@pytest.fixture(scope="module")
def assets():
    return build_assets()


@pytest.fixture(scope="module")
def docs(assets):
    return build_documents(assets, ANCHOR)


@pytest.fixture(scope="module")
def sc(assets):
    return build_showcase(assets, ANCHOR, DEMO_USER)


# --- assets -------------------------------------------------------------------------------------

def test_the_plant_is_big_enough_to_look_like_a_plant(assets):
    assert len(assets) >= 150
    assert {a.site_id for a in assets} == {SITE_A, SITE_B}
    assert Counter(a.criticality for a in assets).keys() == {"safety_critical", "critical", "non_critical"}


def test_every_asset_is_marked_unique_and_correctly_parented(assets):
    ids = [a.asset_id for a in assets]
    assert len(ids) == len(set(ids)) and all(tenant.is_demo_id(i) for i in ids)
    assert all(tenant.is_demo_site(a.site_id) for a in assets)
    assert len({a.tag for a in assets}) == len(assets)
    seen = {GENERAL_ASSET.asset_id}
    for a in assets:  # parents are always listed before their children
        assert a.parent is None or a.parent in seen or a.parent in {x.asset_id for x in assets}
        seen.add(a.asset_id)
    by_id = {a.asset_id: a for a in assets}
    assert all(by_id[a.parent].site_id == a.site_id for a in assets if a.parent)
    assert max(load_showcase.depth(a, by_id) for a in assets) == 2  # unit, equipment, instrument


def test_equipment_classes_let_the_seeded_regulations_apply(assets):
    classes = " ".join(a.equipment_class for a in assets)
    for word in ("pump", "vessel", "valve", "compressor"):
        assert word in classes


def test_asset_batches_post_parents_first(assets):
    batches = load_showcase.asset_batches([GENERAL_ASSET, *assets])
    posted: set[str] = set()
    for batch in batches:
        for a in batch:
            assert a.parent is None or a.parent in posted
        posted |= {a.asset_id for a in batch}
    assert len(posted) == len(assets) + 1


def test_asset_rows_match_the_bulk_import_contract(assets):
    from api.models.asset import AssetImportRow

    for a in assets[:30]:
        AssetImportRow(**load_showcase.asset_row(a))


# --- nothing joins real data ------------------------------------------------------------------

def _golden_vocabulary():
    words = {"Suresh Yadav", "Vikram Desai", "Ananya Iyer", "Fischer", "Meridian", "FSL-2240", "MHT-PB", "FP-SB"}
    canon = Path("/app/dataset/01_Structured_Backbone/asset_registry.csv")
    if canon.exists():
        words |= {line.split(",")[0] for line in canon.read_text().splitlines()[1:] if line}
    return words


def test_no_golden_name_tag_or_part_number_appears_anywhere(assets, docs, sc):
    blob = " ".join(d.text for d in docs) + " ".join(a.tag + a.name for a in assets) + str(sc.tables()) + str(sc.live_events)
    for word in _golden_vocabulary():
        assert not re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", blob), word


# --- documents ---------------------------------------------------------------------------------

def test_documents_are_valid_and_each_names_its_asset(assets, docs):
    ids = {a.asset_id: a for a in assets}
    assert len(docs) >= 60
    assert len({d.file_name for d in docs}) == len(docs)
    for d in docs:
        assert d.document_type in DOCTYPES and 1 <= d.authority <= 5
        assert d.asset_id in ids
        assert ids[d.asset_id].tag in d.text, d.file_name  # the pipeline links on the tag in the text
        assert d.age_days > 0
    assert Counter(d.document_type for d in docs).keys() >= {"procedure", "oem_manual", "inspection_report", "ptw", "shift_log", "regulation"}


def test_every_conflict_is_stated_by_both_of_its_sources(docs):
    by_name = {d.file_name: d for d in docs}
    assert len(CONFLICTS) >= 10
    for c in CONFLICTS:
        sop, bulletin = by_name[c.sop_file], by_name[c.bulletin_file]
        assert f"{c.old} {c.unit}" in sop.text and f"{c.new} {c.unit}" in bulletin.text
        assert sop.authority == 4 and bulletin.authority == 3  # the older, weaker source against the newer, stronger one
        assert sop.age_days > bulletin.age_days


def test_every_piece_of_equipment_has_records_so_its_knowledge_and_graph_are_never_empty(assets, docs):
    from scripts.showcase.docs import CONFLICT_BY_TAG, RECORDS_PER_ASSET

    per_asset = Counter(d.asset_id for d in docs)
    for a in assets:
        if a.equipment_class == "process_unit" or a.tag in CONFLICT_BY_TAG:
            continue
        assert per_asset[a.asset_id] >= RECORDS_PER_ASSET, f"{a.tag} has {per_asset[a.asset_id]} documents"
    # An asset in a conflict keeps exactly the documents that make the conflict: records would add a third voice.
    records = [d for d in docs if d.file_name.startswith(("DS-", "TEST-", "MAINT-"))]
    assert records and not [d for d in records if d.title.rsplit(", ", 1)[1] in CONFLICT_BY_TAG]
    by_kind = Counter(d.file_name.split("-", 1)[0] for d in records)
    assert by_kind["DS"] > 100 and by_kind["TEST"] > 100 and by_kind["MAINT"] > 100
    assert {d.authority for d in records} == {3, 4, 5}


def test_a_record_names_its_asset_and_states_no_operating_limit_a_manual_owns(assets, docs):
    tag_of = {a.asset_id: a.tag for a in assets}
    for d in (d for d in docs if d.file_name.startswith(("DS-", "TEST-", "MAINT-"))):
        assert f"Primary equipment: {tag_of[d.asset_id]}," in d.text
        for owned in ("minimum continuous flow", "bearing temperature alarm", "maximum fill level", "stroke test interval",
                      "cleaning interval", "maximum loading rate", "corrosion allowance"):
            assert owned not in d.text.lower(), f"{d.file_name} states {owned}"


def test_every_piece_of_equipment_has_a_timeline_and_every_elicitation_session_matches_its_work_order(assets, sc):
    by_asset = Counter(e["asset_id"] for e in sc.history_events)
    thin = [a.tag for a in assets if a.equipment_class != "process_unit" and by_asset[a.asset_id] < 2]
    assert not thin, f"fewer than two events: {thin}"
    wo_asset = {e["payload"]["work_order_id"]: e["asset_id"] for e in sc.history_events if e["event_type"] == "work_order_created"}
    for s in sc.elicitation_sessions:
        assert wo_asset[s["work_order_id"]] == s["asset_id"], s["work_order_id"]


def test_documents_render_to_real_files(docs):
    pdf = next(d for d in docs if d.mime == "application/pdf")
    txt = next(d for d in docs if d.mime != "application/pdf")
    import fitz

    rendered = files.render_document(pdf)
    assert rendered.startswith(b"%PDF") and fitz.open(stream=rendered, filetype="pdf")[0].get_text().strip()
    assert files.render_document(txt).decode() == txt.text


# --- the rows the loader writes directly ------------------------------------------------------------

def test_every_direct_row_carries_a_showcase_marker(sc):
    assert unmarked(sc) == []


def test_a_row_without_a_marker_is_caught(sc):
    import copy

    broken = copy.deepcopy(sc)
    broken.quarantine[0]["asset_id"] = "EQ-101"
    broken.history_events[0]["site_id"] = "SITE_001"
    assert {t for t, _ in unmarked(broken)} == {"quarantine_items", "operational_events"}


def test_ids_are_deterministic_and_dates_move_with_the_anchor(assets):
    a = build_showcase(assets, ANCHOR, DEMO_USER)
    b = build_showcase(assets, ANCHOR, DEMO_USER)
    later = build_showcase(assets, ANCHOR + timedelta(days=30), DEMO_USER)
    for table in ("knowledge_conflicts", "moc_items", "quarantine_items", "briefs", "offboarding_sessions"):
        assert [r[next(k for k in r if k.endswith("id"))] for r in getattr(a, {
            "knowledge_conflicts": "conflicts", "moc_items": "moc_items", "quarantine_items": "quarantine",
            "briefs": "briefs", "offboarding_sessions": "offboarding_sessions"}[table])] == [
            r[next(k for k in r if k.endswith("id"))] for r in getattr(b, {
                "knowledge_conflicts": "conflicts", "moc_items": "moc_items", "quarantine_items": "quarantine",
                "briefs": "briefs", "offboarding_sessions": "offboarding_sessions"}[table])]
    assert [e["event_id"] for e in a.history_events] == [e["event_id"] for e in later.history_events]
    shifted = {e["event_id"]: e["occurred_at"] for e in later.history_events}
    for e in a.history_events:
        delta = datetime.fromisoformat(shifted[e["event_id"]]) - datetime.fromisoformat(e["occurred_at"])
        assert delta == timedelta(days=30), e["event_id"]  # the plant never ages: only the anchor moves


def test_every_row_points_at_a_row_that_exists(assets, sc):
    ids = {a.asset_id for a in assets} | {GENERAL_ASSET.asset_id}
    for table, rows in sc.tables().items():
        for r in rows:
            for col in ("asset_id", "canonical_asset_id"):
                if r.get(col) is not None:
                    assert r[col] in ids, (table, col, r[col])
    brief_ids = {b["brief_id"] for b in sc.briefs}
    assert all(f["brief_id"] in brief_ids for f in sc.brief_feedback)
    session_ids = {s["id"] for s in sc.offboarding_sessions}
    assert all(i["session_id"] in session_ids for i in sc.offboarding_items)
    conflict_ids = {c["conflict_id"] for c in sc.conflicts}
    assert all(m["conflict_id"] in conflict_ids for m in sc.moc_items if m["conflict_id"])
    alias_values = [a["alias"] for a in sc.aliases]
    assert len(alias_values) == len(set(alias_values))  # `asset_alias_map.alias` is unique


def test_values_satisfy_the_tables_check_constraints(sc):
    assert {q["input_type"] for q in sc.quarantine} <= {"field_observation", "voice_note", "elicitation_response", "deviation_flag", "offboarding_response"}
    assert {q["review_status"] for q in sc.quarantine} <= {"pending", "promoted", "disputed", "archived"}
    assert {c["track"] for c in sc.conflicts} <= {"administrative", "engineering"}
    assert {c["status"] for c in sc.conflicts} <= {"open", "pending_moc", "resolved"}
    assert {m["status"] for m in sc.moc_items} <= {"draft", "pending_approval", "approved", "rejected"}
    assert {p["state"] for p in sc.plant_states} <= {"normal", "turnaround", "shutdown", "emergency"}
    assert {s["status"] for s in sc.offboarding_sessions} <= {"scheduled", "in_progress", "completed", "cancelled"}
    assert {i["status"] for i in sc.offboarding_items} <= {"pending", "questions_ready", "completed"}
    assert {e["status"] for e in sc.elicitation_sessions} <= {"pending", "questions_ready", "completed"}
    assert all(0 <= a["confidence"] <= 1 for a in sc.aliases)


def test_the_governance_pages_have_every_state_to_show(sc):
    assert {c["status"] for c in sc.conflicts} == {"open", "pending_moc", "resolved"}
    assert {c["track"] for c in sc.conflicts} == {"administrative", "engineering"}
    assert {m["status"] for m in sc.moc_items} >= {"draft", "pending_approval", "approved", "rejected"}
    assert {q["input_type"] for q in sc.quarantine} == {"field_observation", "voice_note", "elicitation_response", "deviation_flag", "offboarding_response"}
    assert {"pending", "disputed", "archived"} <= {q["review_status"] for q in sc.quarantine}
    assert any(q["escalated_at"] for q in sc.quarantine)  # an overdue item, for the SLA report
    assert any(q["review_status"] == "pending" and not q["escalated_at"] for q in sc.quarantine)
    assert {s["status"] for s in sc.offboarding_sessions} >= {"scheduled", "in_progress"}
    assert any(b["requires_countersignature"] and not b["countersigned_by"] for b in sc.briefs)  # awaits a second signature
    assert any(b["requires_countersignature"] and b["countersigned_by"] for b in sc.briefs)
    assert {b["trigger_event_type"] for b in sc.briefs} >= {"work_order", "ptw", "alarm", "shift_handover", "recurring_failure_detected"}


def test_the_demo_user_can_second_sign_the_permit_it_did_not_acknowledge(sc):
    waiting = next(b for b in sc.briefs if b["requires_countersignature"] and not b["countersigned_by"])
    assert waiting["acknowledged_by"] and waiting["acknowledged_by"] != DEMO_USER  # the dual-signature rule needs a second person
    assert waiting["recipient_user_id"] == DEMO_USER


def test_there_are_recurring_failures_and_cross_system_clock_drift(sc):
    from api.utils.failure_families import failure_family

    chains = defaultdict(int)
    for e in sc.history_events:
        if e["event_type"] == "work_order_created":
            chains[(e["asset_id"], failure_family(e["payload"]["failure_code"]))] += 1
    assert sum(1 for n in chains.values() if n >= 3) >= 3
    assert any(e["event_subtype"] == "recurring" for e in sc.history_events)
    groups = defaultdict(list)
    for e in sc.history_events:
        if e["compound_event_id"]:
            groups[e["compound_event_id"]].append(e)
    assert len(groups) >= 6 and all(len({x["source_system"] for x in g}) == 2 for g in groups.values())
    from api.services.timestamp_alignment import TimestampAlignmentService

    drifting = [g for g in groups.values() if TimestampAlignmentService.analyse(g, 60)["drift_detected"]]
    assert 3 <= len(drifting) < len(groups)


def test_the_history_covers_ninety_days_and_every_event_type(sc):
    assert len(sc.history_events) >= 300
    times = [datetime.fromisoformat(e["occurred_at"]) for e in sc.history_events]
    assert max(times) <= ANCHOR and (ANCHOR - min(times)).days >= 85
    assert {e["event_type"] for e in sc.history_events} == {
        "work_order_created", "inspection_complete", "alarm_acknowledged", "ptw_generated", "equipment_tag_out", "shift_handover"}
    assert {e["site_id"] for e in sc.history_events} == {SITE_A, SITE_B}


def test_live_events_are_valid_for_the_real_api_and_name_the_demo_user_as_recipient(assets, sc):
    from api.models.event import (
        AlarmEvent,
        InspectionCompleteEvent,
        PTWEvent,
        ShiftHandoverEvent,
        TagOutEvent,
        WorkOrderEvent,
    )

    models = {"/events/work-order": WorkOrderEvent, "/events/ptw": PTWEvent, "/events/shift-handover": ShiftHandoverEvent,
              "/events/alarm": AlarmEvent, "/events/tag-out": TagOutEvent, "/events/inspection-complete": InspectionCompleteEvent}
    ids = {a.asset_id for a in assets}
    for route, body in sc.live_events:
        models[route](**body)
        assert tenant.is_demo_site(body["site_id"])
        for k in ("asset_id",):
            assert body.get(k) is None or body[k] in ids
    recipients = {b.get("assigned_technician_id") or b.get("issuing_engineer_id") or b.get("incoming_shift_lead_id") for _, b in sc.live_events}
    assert DEMO_USER in recipients


# --- the loader's safety rails -----------------------------------------------------------------

def test_the_loader_writes_nothing_without_apply_and_the_confirmation():
    src = inspect.getsource(load_showcase.main)
    gate = src.index("if not args.apply")
    assert "SHOWCASE_CONFIRM" in src[gate:src.index("password =")]
    for write in ("init_demo_stores(", "post_assets(", "ingest_documents(", "write_history(", "materialise_events(", "post_live_events("):
        assert src.index(write) > gate, f"{write} runs before the --apply gate"


def test_the_alias_map_is_written_after_the_assets_and_before_any_document():
    src = inspect.getsource(load_showcase.main)
    assert src.index("post_assets(") < src.index("write_aliases(") < src.index("ingest_documents(")
    assert "asset_alias_map" not in inspect.getsource(load_showcase.write_history)  # not again after the pipelines


def test_the_loader_refuses_to_start_when_real_mode_changes_or_a_row_is_unmarked():
    src = inspect.getsource(load_showcase.main)
    assert "after != before" in src and "unmarked(sc)" in src and "alias_clashes_with_real_assets" in src


def test_the_real_counts_query_hides_showcase_rows_the_way_real_accounts_do(monkeypatch):
    calls = []

    class Q:
        def __init__(self, table):
            self.table = table

        def select(self, *a, **k):
            return self

        def limit(self, *a):
            return self

        @property
        def not_(self):
            calls.append((self.table, "not_"))
            return self

        def in_(self, *a):
            calls.append((self.table, "in_", a[0]))
            return self

        def like(self, *a):
            calls.append((self.table, "like", a[1]))
            return self

        def or_(self, expr):
            calls.append((self.table, "or_", expr))
            return self

        def execute(self):
            return type("R", (), {"count": 7})()

    class SB:
        def table(self, name):
            return Q(name)

    counts = load_showcase.real_counts(SB())
    assert set(counts) == {t for t, _ in load_showcase.REAL_COUNTS} and set(counts.values()) == {7}
    flat = str(calls)
    assert "DEMO-*" in flat and "SITE_DEMO" in flat and "%" not in flat


# --- keeping the plant current ------------------------------------------------------------------

def test_redate_moves_only_the_loaders_rows_forward_by_whole_days_and_keeps_spacing(sc):
    from scripts.showcase import redate as rd

    now = ANCHOR + timedelta(days=40, hours=3)
    stored = {t: [dict(r) for r in rows] for t, rows in sc.tables().items() if t in rd.PRIMARY_KEY}
    delta, writes = rd.plan(stored, now)
    assert delta.days >= 38 and delta.seconds == 0  # a whole number of days
    newest = max(datetime.fromisoformat(r["occurred_at"]) for r in writes["operational_events"])
    assert timedelta(0) <= (now - newest) - timedelta(days=1) < timedelta(days=1)  # newest event lands on yesterday
    old = {r["event_id"]: datetime.fromisoformat(r["occurred_at"]) for r in sc.history_events}
    for r in writes["operational_events"]:
        assert datetime.fromisoformat(r["occurred_at"]) - old[r["event_id"]] == delta
        assert datetime.fromisoformat(r["payload"]["occurred_at"]) - old[r["event_id"]] == delta  # the payload moves too
    # the same shift for every table, and the full row comes back (an upsert of a partial row would fail)
    quarantine = {r["item_id"]: r for r in sc.quarantine}
    for r in writes["quarantine_items"]:
        before = quarantine[r["item_id"]]
        assert set(r) == set(before) and r["content"] == before["content"] and r["asset_id"] == before["asset_id"]
        assert datetime.fromisoformat(r["submitted_at"]) - datetime.fromisoformat(before["submitted_at"]) == delta


def test_redate_is_a_no_op_when_the_plant_is_already_current_and_on_a_same_day_rerun(sc):
    from scripts.showcase import redate as rd

    stored = {t: [dict(r) for r in rows] for t, rows in sc.tables().items() if t in rd.PRIMARY_KEY}
    assert rd.plan(stored, ANCHOR) == (timedelta(0), {})
    _, writes = rd.plan(stored, ANCHOR + timedelta(days=10))
    assert rd.plan(writes, ANCHOR + timedelta(days=10)) == (timedelta(0), {})  # shifted once, nothing left to shift


def test_redate_handles_dates_nulls_and_odd_values():
    from scripts.showcase.redate import shift_value

    d = timedelta(days=5)
    assert shift_value("2026-10-30", d) == "2026-11-04"  # a DATE column
    assert shift_value(None, d) is None and shift_value("", d) == "" and shift_value("not a time", d) == "not a time"
    assert shift_value("2026-10-01T00:00:00Z", d) == "2026-10-06T00:00:00+00:00"


def test_redate_finds_the_loader_rows_by_id_and_no_visitor_row(sc):
    from scripts.showcase import redate as rd

    ids = rd.loader_ids(sc)
    assert set(ids) == set(rd.PRIMARY_KEY)
    assert all(i.startswith("DEMO-EVT-") for i in ids["operational_events"])  # a visitor's event has a uuid, never matches
    assert len(ids["briefs"]) == len({*ids["briefs"]})


def test_redate_is_off_by_default_and_only_runs_from_the_flag():
    from api.config import Settings
    from api.main import _showcase_redate_loop, lifespan

    assert Settings().SHOWCASE_AUTO_REDATE is False
    src = inspect.getsource(lifespan)
    assert "SHOWCASE_AUTO_REDATE" in src and "_showcase_redate_loop" in src
    assert inspect.iscoroutinefunction(_showcase_redate_loop)


# --- the reset: the only delete, and it cannot reach a real row --------------------------------------

class _Mem:
    """A tiny in-memory Supabase: select and delete with like/in_/eq filters. A delete with NO filter raises,
    which is exactly the mistake the reset must never make."""

    def __init__(self, tables):
        self.t = tables
        self.deleted = []

    def table(self, name):
        return _MemQuery(self, name)

    class _Auth:
        class admin:
            @staticmethod
            def list_users():
                return []


class _MemQuery:
    def __init__(self, db, name):
        self.db, self.name, self.filters, self.op, self.cols = db, name, [], "select", "*"

    def select(self, cols="*", count=None):
        self.cols = cols
        return self

    def delete(self):
        self.op = "delete"
        return self

    def limit(self, *_):
        return self

    def like(self, col, pat):
        assert pat.endswith("*")
        self.filters.append(lambda r: str(r.get(col) or "").startswith(pat[:-1]))
        return self

    def in_(self, col, vals):
        self.filters.append(lambda r: r.get(col) in vals)
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def execute(self):
        rows = [r for r in self.db.t.get(self.name, []) if all(f(r) for f in self.filters)]
        if self.op == "delete":
            if not self.filters:
                raise AssertionError(f"unfiltered delete on {self.name}")
            self.db.t[self.name] = [r for r in self.db.t[self.name] if r not in rows]
            self.db.deleted.append((self.name, len(rows)))
        return type("R", (), {"data": rows, "count": len(rows)})()


def test_reset_deletes_showcase_state_and_nothing_real(monkeypatch):
    from scripts import reset_showcase

    monkeypatch.setattr(reset_showcase, "tenant_demo_ids", lambda sb: ["demo-uid"])
    db = _Mem({
        "briefs": [
            {"brief_id": "b1", "asset_id": "DEMO-P-1", "recipient_user_id": "demo-uid"},
            {"brief_id": "b2", "asset_id": None, "recipient_user_id": "demo-uid"},       # the demo user's asset-less brief
            {"brief_id": "b3", "asset_id": None, "recipient_user_id": "site-SITE_DEMO"},
            {"brief_id": "r1", "asset_id": "EQ-101", "recipient_user_id": "real-user"},
            {"brief_id": "r2", "asset_id": None, "recipient_user_id": "real-user"},
            {"brief_id": "r3", "asset_id": None, "recipient_user_id": "site-SITE_001"},
        ],
        "brief_feedback": [{"id": "f1", "brief_id": "b1"}, {"id": "f2", "brief_id": "r1"}],
        "moc_items": [{"moc_id": "m1", "asset_id": "DEMO-P-1"}, {"moc_id": "m2", "asset_id": "HE-301"}, {"moc_id": "m3", "asset_id": None}],
        "quarantine_items": [{"item_id": "q1", "asset_id": "DEMO-P-1"}, {"item_id": "q2", "asset_id": "EQ-101"}, {"item_id": "q3", "asset_id": None}],
        "knowledge_conflicts": [{"conflict_id": "c1", "asset_id": "DEMO-V-1"}, {"conflict_id": "c2", "asset_id": "HE-301"}],
        "elicitation_sessions": [{"session_id": "s1", "asset_id": "DEMO-P-1"}, {"session_id": "s2", "asset_id": "EQ-101"}],
        "offboarding_sessions": [{"id": "o1", "personnel_id": "DEMO-EXPERT-X"}, {"id": "o2", "personnel_id": "EXPERT-RKUMAR"}],
        "operational_events": [{"event_id": "e1", "site_id": "SITE_DEMO"}, {"event_id": "e2", "site_id": "SITE_DEMO_B"}, {"event_id": "e3", "site_id": "SITE_001"}],
        "plant_operating_states": [{"id": "p1", "site_id": "SITE_DEMO"}, {"id": "p2", "site_id": "SITE_001"}],
        "documents": [{"document_id": "DOC-1", "access_tags": {"site_id": "SITE_DEMO"}}],
        "assets": [{"asset_id": "DEMO-P-1"}, {"asset_id": "EQ-101"}],
        "asset_alias_map": [
            {"alias": "A1", "canonical_asset_id": "DEMO-P-1", "confirmed": False, "alias_source": "ner_extraction:DOC-1"},  # a pipeline guess
            {"alias": "A2", "canonical_asset_id": "DEMO-P-1", "confirmed": False, "alias_source": "extraction:ner_candidate"},  # the dataset's own
            {"alias": "A3", "canonical_asset_id": "DEMO-P-1", "confirmed": True, "alias_source": "ner_extraction:DOC-1"},  # confirmed by someone
            {"alias": "A4", "canonical_asset_id": "EQ-101", "confirmed": False, "alias_source": "ner_extraction:DOC-9"},  # a real asset's guess
        ],
    })
    would = reset_showcase.plan(db)
    assert would["briefs"] == 3 and would["brief_feedback"] == 1 and would["operational_events"] == 2
    reset_showcase.delete_state(db)
    survivors = {t: [next(iter(r.values())) for r in rows] for t, rows in db.t.items()}
    assert survivors["briefs"] == ["r1", "r2", "r3"]
    assert survivors["brief_feedback"] == ["f2"]
    assert survivors["moc_items"] == ["m2", "m3"] and survivors["quarantine_items"] == ["q2", "q3"]
    assert survivors["knowledge_conflicts"] == ["c2"] and survivors["elicitation_sessions"] == ["s2"]
    assert survivors["offboarding_sessions"] == ["o2"]
    assert survivors["operational_events"] == ["e3"] and survivors["plant_operating_states"] == ["p2"]
    assert survivors["documents"] == ["DOC-1"] and survivors["assets"] == ["DEMO-P-1", "EQ-101"]  # the vault and assets are never touched
    assert would["asset_alias_map"] == 1 and survivors["asset_alias_map"] == ["A2", "A3", "A4"]


def test_every_reset_delete_is_a_marker_filter_and_the_vault_is_not_in_the_list():
    from scripts import reset_showcase

    tables = {t for t, _, _ in reset_showcase.MARKERS}
    assert not tables & {"documents", "extraction_jobs", "document_asset_links", "assets", "asset_alias_map", "audit_log"}  # aliases: `candidates()` only
    assert all(kind in ("prefix", "site") for _, _, kind in reset_showcase.MARKERS)
    src = inspect.getsource(reset_showcase.delete_state)
    assert src.count(".delete()") == 4 and "marked(" in src and "candidates(sb.table(\"asset_alias_map\").delete())" in src


def test_the_reset_needs_apply_and_its_own_confirmation():
    from scripts import reset_showcase

    src = inspect.getsource(reset_showcase.main)
    gate = src.index("if not args.apply")
    assert "SHOWCASE_CONFIRM" in src[gate:] and src.index("delete_state(") > gate
    assert reset_showcase.CONFIRM != load_showcase.CONFIRM  # a load confirmation cannot start a reset


def test_the_demo_account_is_moved_to_the_showcase_site_keeping_its_role():
    from types import SimpleNamespace

    updates = []
    user = SimpleNamespace(app_metadata={"role": "demo", "site_id": "SITE_001", "name": "Demo Visitor"})

    class Admin:
        @staticmethod
        def get_user_by_id(uid):
            return SimpleNamespace(user=user)

        @staticmethod
        def update_user_by_id(uid, attrs):
            updates.append((uid, attrs))

    sb = SimpleNamespace(auth=SimpleNamespace(admin=Admin))
    assert load_showcase.set_demo_site(sb, "u-1") is True
    assert updates == [("u-1", {"app_metadata": {"role": "demo", "site_id": SITE_A, "name": "Demo Visitor"}})]

    user.app_metadata = {"role": "demo", "site_id": SITE_A}
    updates.clear()
    assert load_showcase.set_demo_site(sb, "u-1") is False and updates == []  # already there: no write


def test_the_seeded_demo_user_lives_on_the_showcase_site():
    from scripts.seed_users import TEST_USERS as USERS

    demo = next(u for u in USERS if u["email"] == "demo@kairos.local")
    assert demo["app_metadata"]["site_id"] == SITE_A and demo["app_metadata"]["role"] == "demo"


SNAPSHOT_USER = "00000000-0000-0000-0000-00000000de40"


@pytest.fixture(scope="module")
def written(tmp_path_factory, assets, docs):
    root = tmp_path_factory.mktemp("showcase")
    snap = build_showcase(assets, ANCHOR, SNAPSHOT_USER)
    return root, files.write(root, assets, docs, snap, demo_user_placeholder=SNAPSHOT_USER)


def test_the_dataset_is_written_in_the_six_golden_style_folders(written, docs, sc):
    root, counts = written
    assert [p.name for p in sorted(root.iterdir())] == ["00_Reference", "01_Structured_Backbone", "02_Document_Corpus",
                                                        "03_Multiformat_Variants", "04_Events_And_Quarantine", "05_Governance_And_Handover"]
    pdfs = {d.file_name for d in docs if d.mime == "application/pdf"}
    assert {p.name for p in (root / files.CORPUS).iterdir()} == pdfs
    assert {p.name for p in (root / files.VARIANTS).iterdir()} == {d.file_name for d in docs} - pdfs
    assert counts["documents"] == len(docs) and (root / files.REGISTER[0] / files.REGISTER[1]).read_text().count("\n") == counts["assets"] + 1


def test_showcase_files_sit_beside_the_golden_ones_and_never_share_a_name(written, docs):
    root, _ = written
    golden = Path(__file__).resolve().parents[1] / "dataset" / "00_Reference" / "dataset_manifest.csv"
    golden_names = {ln.split(",")[1] for ln in golden.read_text().splitlines()[1:]} if golden.exists() else set()
    doc_names = {d.file_name for d in docs}
    written_files = [p for p in root.rglob("*") if p.is_file()]
    assert written_files
    for p in written_files:
        assert p.name in doc_names or p.name.startswith(("showcase_", "SHOWCASE_")), f"{p.name} is not a showcase-named file"
        assert p.name not in golden_names, f"{p.name} is a golden file name"
    assert not any(p.name.startswith("event_") for p in written_files)  # the golden loader globs event_*.json in 04


def test_every_table_the_loader_writes_has_a_home_in_the_dataset(sc):
    assert set(files.TABLE_HOME) == set(sc.tables()) == set(files.FIELD)


def test_what_is_read_back_is_what_was_written_and_the_loader_never_rebuilds_it(written, assets, docs):
    root, _ = written
    ds = files.read(root)
    assert ds.assets[0] == GENERAL_ASSET and ds.assets[1:] == assets
    assert [(d.file_name, d.document_type, d.authority, d.asset_id, d.age_days, d.mime) for d in ds.docs] == \
        [(d.file_name, d.document_type, d.authority, d.asset_id, d.age_days, d.mime) for d in docs]
    assert ds.docs[0].data()[:4] in (b"%PDF", docs[0].text.encode()[:4])
    assert ds.showcase.tables() == build_showcase(assets, ANCHOR, SNAPSHOT_USER).tables()
    src = inspect.getsource(load_showcase)
    assert "build_showcase" not in src and "build_documents" not in src and "build_assets" not in src


@pytest.mark.parametrize("days", [0, 7, 30])
def test_binding_moves_the_files_to_load_time_and_swaps_in_the_real_ids(written, assets, docs, days):
    root, _ = written
    ds = files.read(root)
    now = ANCHOR + timedelta(days=days)
    ids = {d.file_name: f"real-{i}" for i, d in enumerate(docs)}
    bound = files.bind(ds, now=now, demo_user_id=DEMO_USER, doc_ids=ids)
    built = build_showcase(assets, now, DEMO_USER, ids)
    assert bound.tables() == built.tables()  # every time column and id is the one a fresh build would write
    assert bound.live_events == built.live_events
    assert not [r for r in bound.tables().values() for row in r if SNAPSHOT_USER in str(row) or "DOC-PENDING" in str(row)]


def test_a_dry_bind_leaves_the_placeholders_and_still_passes_the_marker_audit(written):
    root, _ = written
    sc = files.bind(files.read(root), now=ANCHOR)
    assert unmarked(sc) == []
    assert any(SNAPSHOT_USER in str(r) for r in sc.briefs)


def test_redate_and_reset_take_their_ids_from_the_files_too():
    import inspect

    from scripts import redate_showcase, reset_showcase

    for mod in (redate_showcase, reset_showcase):
        src = inspect.getsource(mod)
        assert "files.read" in src and "build_showcase" not in src


# --- a showcase document never links to a real asset ---------------------------------------------

def test_a_showcase_document_links_only_to_showcase_assets():
    assert tenant.link_allowed(True, "DEMO-P-1101A") is True
    assert tenant.link_allowed(True, "EQ-101") is False  # the extractor names assets a page does not
    assert tenant.link_allowed(True, None) is True  # unresolved: the caller's usual path
    assert tenant.link_allowed(False, "EQ-101") is True and tenant.link_allowed(False, "DEMO-P-1101A") is True
    from workflows import document_pipeline

    src = inspect.getsource(document_pipeline.link_to_graph)
    assert src.count("tenant.link_allowed(showcase_doc") == 2  # the circuit-breaker candidates and the edge loop


def test_the_reset_removes_stray_edges_only_where_a_showcase_document_sits_on_a_real_asset():
    from scripts import reset_showcase

    q = reset_showcase.STRAY_EDGES
    assert "k.document_id IN $ids" in q and "NOT a.asset_id STARTS WITH $prefix" in q  # both sides of the marker
    src = inspect.getsource(reset_showcase.stray_edges)
    assert src.count("DELETE k") == 1 and "STRAY_EDGES +" in src and "if delete and count" in src
    main_src = inspect.getsource(reset_showcase.main)
    assert main_src.index("SHOWCASE_CONFIRM") < main_src.index("stray_edges(settings, showcase_docs, delete=True)")


# --- the graph view: the asset and its surroundings ------------------------------------------------

def test_the_placeholder_asset_is_shown_as_no_asset():
    assert tenant.present_asset({"asset_id": tenant.DEMO_GENERAL_ASSET, "x": 1}) == {"asset_id": None, "x": 1}
    assert tenant.present_asset({"asset_id": "DEMO-P-1101A"}) == {"asset_id": "DEMO-P-1101A"}
    assert tenant.present_asset({"asset_id": None}) == {"asset_id": None}


async def test_the_graph_endpoint_builds_a_network_and_hides_test_documents(monkeypatch):
    from api.routers import assets as router

    def doc(i):
        edge = {"relationship_type": "DOCUMENTED_BY", "authority_level": 3, "verification_status": "unverified", "valid_from": "2026-01-01T00:00:00", "valid_to": "9999-12-31T23:59:59", "document_id": f"DOC-{i}", "confidence": 0.9}
        return {"document_id": f"DOC-{i}"}, edge
    person = {"person_id": "p1", "name": "Dr. Sunita Rao"}
    mention = {"relationship_type": "MENTIONS_PERSON", "authority_level": 3, "verification_status": "unverified", "valid_from": "2026-01-01T00:00:00", "valid_to": "9999-12-31T23:59:59", "document_id": "DOC-1", "confidence": 0.9}

    class FakeGraph:
        def __init__(self, driver): ...

        async def get_asset_neighbourhood(self, asset_id, *, hide_demo, as_of=None):
            assert asset_id == "DEMO-P-1" and hide_demo is True
            return {
                "asset": {"asset_id": "DEMO-P-1", "tag_number": "P-1"}, "parent": {"asset_id": "DEMO-UNIT", "name": "CDU"},
                "children": [{"asset_id": "DEMO-PT-1", "tag_number": "PT-1"}], "documents": [doc(1), doc(2), doc(3)],
                "mentions": [("DOC-1", person, "Person", mention), ("DOC-1", person, "Person", mention), ("DOC-2", person, "Person", {**mention, "document_id": "DOC-2"}),
                             ("DOC-3", person, "Person", {**mention, "document_id": "DOC-3"})],
                "related": [("DOC-1", {"asset_id": "DEMO-P-2", "tag_number": "P-2"}, {"relationship_type": "DOCUMENTED_BY"})],
                "events": [{"event_id": "E1", "event_type": "work_order_created"}],
            }

    async def canonical(asset_id, graph, supabase):
        return asset_id

    async def allowed(graph, asset_id, user):
        return {}

    async def rows(supabase, ids):
        return [{"document_id": "DOC-1", "file_name": "SOP-pump.pdf"}, {"document_id": "DOC-2", "file_name": "datasheet.pdf"},
                {"document_id": "DOC-3", "file_name": "ann_test_scratch.pdf"}]

    monkeypatch.setattr(router, "GraphService", FakeGraph)
    monkeypatch.setattr(router, "resolve_canonical_asset_id", canonical)
    monkeypatch.setattr(router, "scoped_asset", allowed)
    monkeypatch.setattr(router, "document_rows", rows)
    out = await router.get_asset_graph("DEMO-P-1", {"role": "engineer"}, object(), object(), None)

    kinds = Counter(n["kind"] for n in out["nodes"])
    assert kinds == {"Asset": 4, "Document": 2, "Person": 1, "Event": 1}  # the test document and its mention are gone
    assert out["excluded_test_documents"] == 1
    structural = {e["label"] for e in out["edges"] if e["structural"]}
    assert structural == {"PARENT_OF", "OCCURRED_ON"}  # position and events are not knowledge facts
    person_edges = [e for e in out["edges"] if e["target"] == "p1"]
    assert {e["source"] for e in person_edges} == {"DOC-1", "DOC-2"}  # one person joins two documents: a network, not a star
    assert len(person_edges) == 2  # DOC-1 names the person twice: one line, one React key
    assert len({e["id"] for e in out["edges"]}) == len(out["edges"])
    assert next(n for n in out["nodes"] if n["id"] == "DOC-1")["label"] == "SOP-pump"


def test_recurring_failure_assets_have_a_history_card_that_matches_their_work_orders(docs, sc):
    from scripts.showcase.docs import CHAINS

    cards = {d.file_name: d for d in docs if d.file_name.startswith("FAIL-")}
    for tag, _codes, days in CHAINS:
        card = cards[f"FAIL-{tag}-history-card.pdf"]
        assert f"failure {len(days)} in {days[0]} days" in card.text
        raised = [e for e in sc.history_events if e["event_type"] == "work_order_created" and e["asset_id"] == f"DEMO-{tag}"]
        assert len(raised) >= len(days)
