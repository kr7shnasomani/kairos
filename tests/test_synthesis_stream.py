"""Streaming synthesis — the safety property, and the gates it shares with the non-streaming path.

The whole reason this needs its own tests: `CONFIDENCE:` arrives AFTER `ANSWER:` in the response
contract, and `result_gate` can turn a complete answer into a refusal based on it. So a
safety-critical answer must never be streamed to the screen — the operator would read text that
is about to be retracted, which is the "hedged partial answer" the architecture forbids outright.

Pure logic + a stubbed provider. No stack, no secrets, no network.
"""

import pytest

from api.config import settings
from api.services.llm import SAFETY_CRITICAL_CATEGORIES, LLMService

AUTHORITATIVE_EVIDENCE = [
    {"document_id": "OEM-1", "text": "MAWP is 16.2 bar", "authority_level": 2, "asset_id": "HE-301"},
]


async def _collect(llm, **kwargs):
    return [(e, d) async for e, d in llm.synthesize_stream(**kwargs)]


# =============================================================================
# The safety property
# =============================================================================

@pytest.mark.parametrize("category", sorted(SAFETY_CRITICAL_CATEGORIES))
async def test_safety_critical_categories_never_emit_answer_text(category, monkeypatch):
    """No `delta` event for any safety-critical category, whatever the model returns."""
    llm = LLMService(settings)

    async def _fake_cascade(prompt, context):
        return {"answer": "ANSWER: 16.2 bar\nCONFIDENCE: 0.9\nSOURCES_USED: 1", "sources": context}

    monkeypatch.setattr(llm, "_synthesize_cascade", _fake_cascade)
    # If this were ever streamed, the stub would make it obvious.
    monkeypatch.setattr(llm, "_stream_nim", lambda p: (_ for _ in ()).throw(AssertionError("streamed a safety answer")))

    events = await _collect(
        llm, query="max allowable pressure for HE-301",
        retrieved_context=AUTHORITATIVE_EVIDENCE, query_category=category,
    )
    assert not [e for e, _ in events if e == "delta"], f"{category} must not stream answer text"
    assert events[-1][0] == "done"


async def test_safety_critical_status_tells_the_client_why_no_text_is_coming(monkeypatch):
    llm = LLMService(settings)
    monkeypatch.setattr(llm, "_synthesize_cascade",
                        lambda p, c: _async({"answer": "ANSWER: x\nCONFIDENCE: 0.9", "sources": c}))

    events = await _collect(
        llm, query="max allowable pressure for HE-301",
        retrieved_context=AUTHORITATIVE_EVIDENCE, query_category="max_allowable_pressure",
    )
    synth = [d for e, d in events if e == "status" and d.get("stage") == "synthesizing"]
    assert synth and synth[0]["streaming_text"] is False
    assert "Safety-critical" in (synth[0]["reason"] or "")


async def test_post_gate_still_retracts_a_low_confidence_streamed_answer(monkeypatch):
    """The whole point: a safety answer whose CONFIDENCE is below threshold becomes a refusal,
    and because nothing was streamed, no retracted text was ever shown."""
    llm = LLMService(settings)
    monkeypatch.setattr(llm, "_synthesize_cascade",
                        lambda p, c: _async({"answer": "ANSWER: probably ~16 bar\nCONFIDENCE: 0.2\nSOURCES_USED: 1",
                                             "sources": c}))

    events = await _collect(
        llm, query="max allowable pressure for HE-301",
        retrieved_context=AUTHORITATIVE_EVIDENCE, query_category="max_allowable_pressure",
    )
    assert not [e for e, _ in events if e == "delta"]
    _, done = events[-1]
    assert done["refused"] is True
    assert done["answer"] is None
    assert done["sources"], "a refusal still returns sources for direct verification"


async def test_evidence_gate_refuses_before_any_provider_call(monkeypatch):
    """Refused on the evidence — the model must not be called at all."""
    llm = LLMService(settings)

    def _boom(*a, **k):
        raise AssertionError("provider called despite an evidence-gate refusal")

    monkeypatch.setattr(llm, "_synthesize_cascade", _boom)
    monkeypatch.setattr(llm, "_stream_nim", _boom)

    events = await _collect(
        llm, query="max allowable pressure for HE-301",
        retrieved_context=[{"document_id": "QN-1", "text": "operator thinks ~20 bar", "authority_level": 5}],
        query_category="max_allowable_pressure",
    )
    assert events[-1][0] == "done"
    assert events[-1][1]["refused"] is True


# =============================================================================
# Non-safety-critical streaming
# =============================================================================

async def test_ordinary_query_streams_text(monkeypatch):
    llm = LLMService(settings)

    async def _fake_stream(prompt):
        for piece in ("ANSWER: the pump ", "was replaced ", "in June."):
            yield piece

    monkeypatch.setattr(llm, "_stream_nim", _fake_stream)
    monkeypatch.setattr(type(llm), "nim_available", property(lambda self: True))

    events = await _collect(
        llm, query="when was the pump replaced?",
        retrieved_context=[{"document_id": "D1", "text": "replaced June", "authority_level": 4}],
        query_category="maintenance_history",
    )
    deltas = [d["text"] for e, d in events if e == "delta"]
    assert deltas, "an ordinary query should stream"
    assert "".join(deltas) == "ANSWER: the pump was replaced in June."
    assert events[-1][0] == "done"


async def test_stream_failure_falls_back_and_tells_the_client_to_discard(monkeypatch):
    """A mid-stream failure re-synthesizes via the cascade. The client must be told to drop the
    partial text, or it would concatenate two different answers into one that no model produced."""
    llm = LLMService(settings)

    async def _broken_stream(prompt):
        yield "ANSWER: partial"
        raise RuntimeError("connection reset")

    monkeypatch.setattr(llm, "_stream_nim", _broken_stream)
    monkeypatch.setattr(type(llm), "nim_available", property(lambda self: True))
    monkeypatch.setattr(llm, "_synthesize_cascade",
                        lambda p, c: _async({"answer": "ANSWER: complete answer", "sources": c}))

    events = await _collect(
        llm, query="when was the pump replaced?",
        retrieved_context=[{"document_id": "D1", "text": "replaced June", "authority_level": 4}],
        query_category="maintenance_history",
    )
    assert [e for e, _ in events if e == "restart"], "client must be told to discard partial text"
    assert events[-1][0] == "done"
    assert events[-1][1]["answer"] == "ANSWER: complete answer"


async def test_empty_context_terminates_without_calling_a_provider(monkeypatch):
    llm = LLMService(settings)

    def _boom(*a, **k):
        raise AssertionError("provider called with no evidence")

    monkeypatch.setattr(llm, "_synthesize_cascade", _boom)
    events = await _collect(llm, query="anything", retrieved_context=[], query_category=None)
    assert events[-1][0] == "done"
    assert events[-1][1]["answer"] is None


# =============================================================================
# The gates are shared, not forked
# =============================================================================

def test_streaming_and_non_streaming_use_the_same_gate_methods():
    """If either path ever grows its own copy of a refusal rule, they will drift and whichever
    an operator hits will be the wrong one."""
    import inspect

    src = inspect.getsource(LLMService.synthesize_stream)
    assert "self.evidence_gate(" in src
    assert "self.result_gate(" in src
    non_streaming = inspect.getsource(LLMService.synthesize)
    assert "self.evidence_gate(" in non_streaming
    assert "self.result_gate(" in non_streaming


def test_stream_route_maps_to_the_same_authz_action_as_its_sibling():
    from api.middleware.opa import action_for

    assert action_for("POST", "/search/synthesize/stream") == action_for("POST", "/search/synthesize")


async def _async(value):
    return value


# =============================================================================
# The route itself — terminal events
# =============================================================================

async def _route_events(monkeypatch, fake_stream):
    """Run `POST /search/synthesize/stream` with a stubbed LLM and return (event names, body)."""
    from api.models.document import SynthesizeRequest
    from api.routers import search as search_router

    class _FakeLLM:
        def __init__(self, _settings):
            pass

        classify_query_category = staticmethod(lambda query: None)
        parse_synthesis_response = staticmethod(lambda answer: {"answer": answer})
        synthesize_stream = fake_stream

    monkeypatch.setattr(search_router, "LLMService", _FakeLLM)
    response = await search_router.synthesize_stream(
        SynthesizeRequest(query="what failed on EQ-101?", context=[]),
        current_user={"user_id": "u-1"}, settings=settings, driver=None,
    )
    body = "".join([c if isinstance(c, str) else c.decode() async for c in response.body_iterator])
    return [line.split(":", 1)[1].strip() for line in body.splitlines() if line.startswith("event:")], body


async def test_a_successful_stream_ends_on_done_without_an_error_event(monkeypatch):
    """Regression: the `error` yield once sat outside the except block, so every successful stream
    ended `done` → `error` and the client threw away a good answer."""
    async def _ok(self, query, context, category):
        yield "delta", {"text": "Mechanical seal"}
        yield "done", {"answer": "Mechanical seal", "sources": context}

    events, _ = await _route_events(monkeypatch, _ok)
    assert events == ["delta", "done"]


async def test_a_failed_stream_ends_on_error_without_exposing_the_exception(monkeypatch):
    async def _boom(self, query, context, category):
        yield "status", {"stage": "retrieving"}
        raise RuntimeError("internal host nim-internal:8443 refused")

    events, body = await _route_events(monkeypatch, _boom)
    assert events == ["status", "error"]
    assert "nim-internal" not in body and "RuntimeError" not in body
