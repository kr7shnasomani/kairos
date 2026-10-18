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


# =============================================================================
# The RCA agent: bounded, locked to the asset, and honest about what it could not support
# =============================================================================

import json as _json  # noqa: E402
from datetime import UTC as _UTC  # noqa: E402
from datetime import datetime as _dt  # noqa: E402

from api.services import rca_agent  # noqa: E402
from api.services.rca_agent import RcaAgent, parse_check, parse_step  # noqa: E402

ALL = set(rca_agent.TOOLS)


def test_a_plan_reply_names_a_known_tool_and_clamps_its_args():
    assert parse_step('{"tool": "failure_history", "args": {"years": 40}, "why": "go back"}', ALL) == (
        "failure_history", {"years": 10}, "go back")
    assert parse_step('noise {"tool": "search_documents", "args": {"query": "seal flush"}} noise', ALL)[1] == {"query": "seal flush"}


def test_the_plan_cannot_name_an_asset():
    """An injected 'look up DEMO-X' can pick a tool, never a different asset: no tool takes one."""
    step = parse_step('{"tool": "sister_assets", "args": {"asset_id": "DEMO-OTHER"}, "why": "x"}', ALL)
    assert step == ("sister_assets", {}, "x")


def test_anything_unreadable_or_repeated_stops_the_plan():
    assert parse_step("I think we should look at history", ALL) is None
    assert parse_step('{"tool": "done", "why": "enough"}', ALL) is None
    assert parse_step('{"tool": "rm -rf", "args": {}}', ALL) is None
    assert parse_step('{"tool": "failure_history"}', ALL - {"failure_history"}) is None
    assert parse_step('{"tool": "search_documents", "args": {"query": ""}}', ALL) is None


def test_a_check_reply_must_cover_every_hypothesis():
    assert parse_check('[{"n":1,"supported":true,"reason":"a"},{"n":2,"supported":false,"reason":"b"}]', 2) == [
        (True, "a"), (False, "b")]
    assert parse_check('[{"n":1,"supported":true}]', 2) is None
    assert parse_check("all supported", 1) is None


class _LLM:
    """Replies in order; records what it was asked."""

    def __init__(self, replies):
        self.replies, self.prompts = list(replies), []

    async def _synthesize_cascade(self, prompt, context):
        self.prompts.append(str(prompt))
        return {"answer": self.replies.pop(0) if self.replies else None}

    async def rca_synthesize(self, failure_code, timeline, evidence):
        return {"answer": "HYPOTHESES:\n1. x | evidence_weight: 0.5 | sources: DOC-1\nCONFIDENCE: 0.8"}


def _agent(llm, **kw):
    agent = RcaAgent(llm=llm, graph=None, vector_store=None, supabase=None, settings=None, user={"role": "engineer"},
                     asset_id="EQ-101", asset_class="centrifugal_pump", site_pin=None, include_quarantine=False)
    for name, fn in kw.items():
        setattr(agent, name, fn)
    return agent


async def test_the_plan_stops_at_the_step_cap_and_never_repeats_a_tool():
    replies = [_json.dumps({"tool": t, "why": "w"}) for t in ["asset_knowledge", "pending_changes", "sister_assets", "failure_history", "search_documents"]]

    async def found(*_a, **_k):
        return "ok"

    agent = _agent(_LLM(replies), _tool_asset_knowledge=found, _tool_pending_changes=found,
                   _tool_sister_assets=found, _tool_failure_history=found)
    out = await agent.run("SEAL-FAIL", _dt(2026, 7, 15, tzinfo=_UTC), [], [])
    assert [s["tool"] for s in out["investigation"].steps] == ["asset_knowledge", "pending_changes", "sister_assets", "failure_history"]
    assert out["synthesis"]["answer"].startswith("HYPOTHESES")


async def test_field_notes_are_not_offered_unless_quarantine_was_asked_for():
    llm = _LLM([_json.dumps({"tool": "field_notes", "why": "w"})])
    out = await _agent(llm).run("SEAL-FAIL", _dt(2026, 7, 15, tzinfo=_UTC), [], [])
    assert out["investigation"].steps == [] and "field_notes" not in llm.prompts[0]


async def test_a_failed_lookup_is_recorded_and_the_investigation_continues():
    async def boom(*_a, **_k):
        raise RuntimeError("neo4j down")

    llm = _LLM([_json.dumps({"tool": "asset_knowledge", "why": "w"}), _json.dumps({"tool": "done"})])
    out = await _agent(llm, _tool_asset_knowledge=boom).run("SEAL-FAIL", _dt(2026, 7, 15, tzinfo=_UTC), [], [])
    assert out["investigation"].steps[0]["found"] == "The lookup failed."


async def test_the_check_drops_what_its_sources_do_not_support():
    hyps = [{"hypothesis": "seal wear", "sources": ["DOC-1"]}, {"hypothesis": "bad batch", "sources": ["DOC-2"]},
            {"hypothesis": "guess", "sources": []}]
    llm = _LLM(['[{"n":1,"supported":true,"reason":"stated"},{"n":2,"supported":false,"reason":"not stated"}]'])
    kept, dropped = await _agent(llm).check(hyps, [{"document_id": "DOC-1", "text": "seal wear"}], elapsed=10)
    assert [h["hypothesis"] for h in kept] == ["seal wear"]
    assert {h["hypothesis"]: h["check_reason"] for h in dropped} == {"bad batch": "not stated", "guess": "Cites no source document."}


async def test_an_unreadable_check_keeps_every_cited_hypothesis_marked_unchecked():
    hyps = [{"hypothesis": "seal wear", "sources": ["DOC-1"]}]
    kept, dropped = await _agent(_LLM(["looks fine"])).check(hyps, [], elapsed=10)
    assert kept[0]["check"] == "unchecked" and dropped == []
    kept, _ = await _agent(_LLM([])).check(hyps, [], elapsed=99)  # past the budget: not checked at all
    assert kept[0]["check"] == "unchecked"


class _Q:
    def __init__(self, log):
        self.log = log

    @property
    def not_(self):
        self.log.append(("not_",))
        return self

    def __getattr__(self, name):
        def call(*a, **_k):
            self.log.append((name, *a))
            return self
        return call

    def execute(self):
        class R:
            data = []
        return R()


class _SB:
    def __init__(self):
        self.log = []

    def table(self, name):
        self.log.append(("table", name))
        return _Q(self.log)


async def test_sister_equipment_comes_from_the_same_plant_as_the_asset():
    for asset, expected in (("EQ-101", [("not_",), ("like", "asset_id", "DEMO-*")]), ("DEMO-P-1101A", [("like", "asset_id", "DEMO-*")])):
        sb = _SB()
        agent = RcaAgent(llm=None, graph=None, vector_store=None, supabase=sb, settings=None, user={"role": "demo"},
                         asset_id=asset, asset_class="centrifugal_pump", site_pin=None, include_quarantine=False)
        inv = rca_agent.Investigation(timeline=[], evidence=[])
        await agent._tool_sister_assets(inv, "SEAL-FAIL", _dt(2026, 7, 15, tzinfo=_UTC))
        tail = sb.log[sb.log.index(("neq", "asset_id", asset)) + 1:]
        assert all(op in tail for op in expected), tail
