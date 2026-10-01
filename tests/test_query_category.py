"""Safety-critical query classification + refusal gate (services/llm.py).

These guard the gate that was previously unreachable: nothing in the system set
query_category, so SAFETY_CRITICAL_CATEGORIES never fired. Pure logic, no services.
"""

import pytest

from api.services.llm import SAFETY_CRITICAL_CATEGORIES, LLMService
from api.services.model_providers import Provider

classify = LLMService.classify_query_category


@pytest.mark.parametrize(
    "query,expected",
    [
        ("What is the maximum allowable pressure for HE-301?", "max_allowable_pressure"),
        ("MAWP for the pressure vessel?", "max_allowable_pressure"),
        ("current max operating pressure engineering value", "max_allowable_pressure"),
        ("What is the PSV set pressure on V-247?", "pressure_relief_setting"),
        ("relief valve setting for the vessel", "pressure_relief_setting"),
        ("Which valves make up the isolation boundary for V-247?", "isolation_interlock_sequence"),
        ("lockout tagout sequence for the feed pump", "isolation_interlock_sequence"),
        ("Which valve is the primary safety isolation valve for V-247?", "isolation_interlock_sequence"),
        ("flange bolt torque specification", "torque_specification"),
        ("motor insulation class for EQ-102", "electrical_rating"),
        ("emergency shutdown setpoint for the compressor", "safety_shutdown_setpoint"),
    ],
)
def test_safety_critical_queries_are_classified(query, expected):
    assert classify(query) == expected
    assert expected in SAFETY_CRITICAL_CATEGORIES


@pytest.mark.parametrize(
    "query",
    [
        "What are the known aliases for pump EQ-101?",
        "Which field technician worked on the seal repair?",
        "How many mechanical seal failures has EQ-101 had?",
        "Which OEM manufactures the HE-3xx heat exchangers?",
        # Regression (benchmark Q06): the equipment is *named* "isolation valve", but the
        # question asks a date. Bare "isolation" used to match and refuse it, hiding a fact
        # the vault holds. Refusing a lookup is as wrong as guessing a parameter.
        "When was isolation valve XV-203 last inspected?",
        "Which work order documents the isolation valve replacement?",
    ],
)
def test_non_safety_queries_are_not_classified(query):
    assert classify(query) is None


@pytest.mark.parametrize(
    "query",
    [
        "Can HE-302 handle 45 bar?",
        "What pressure does HE-302 withstand?",
        "How tight should the P-101 flange bolts be?",
        "What is the rated current of motor M-12?",
        "At what temperature does K-101 shut down?",
        # Fail-closed extras: a bare quantity with a unit, no tag needed.
        "Is 120 psi acceptable on the feed line?",
        "Will the seal survive 150 degC?",
        "What is the max voltage for EQ-102?",
    ],
)
def test_parameter_questions_that_fit_no_list_fail_closed(query):
    """Security review M5: each of these used to return None and skip the gate entirely."""
    assert classify(query) in SAFETY_CRITICAL_CATEGORIES


@pytest.mark.parametrize(
    "query",
    [
        "Who last worked on pump P-101?",
        "When was HE-302 last inspected?",
        "How many work orders were raised for K-101?",
        "Show the work order history for HE-302",
        "Which bulletin covers the pressure change for HE-302?",
        "Which seal part number superseded FSL-2240A?",
        "What improvement does seal part FSL-2240B have over FSL-2240A?",
        "What are the known aliases for pump EQ-101?",
    ],
)
def test_benign_intents_naming_a_tag_are_still_not_classified(query):
    assert classify(query) is None


def test_relief_setting_wins_over_generic_pressure():
    """Ordering guard: 'relief set pressure' contains 'pressure' but is not MAWP."""
    assert classify("relief valve set pressure on the separator") == "pressure_relief_setting"


async def test_refuses_safety_query_on_unauthoritative_evidence(settings_fixture=None):
    """Only field-observation evidence (level 5) -> refuse, do not answer."""
    from api.config import settings

    llm = LLMService(settings)
    result = await llm.synthesize(
        query="max allowable pressure for HE-301",
        retrieved_context=[{"document_id": "QN-1", "text": "operator thinks ~20 bar", "authority_level": 5}],
        query_category="max_allowable_pressure",
    )
    assert result["refused"] is True
    assert result["answer"] is None
    assert result["sources"], "refusal must still return the sources for direct verification"


async def test_authoritative_evidence_clears_the_gate(monkeypatch):
    """
    OEM-authority evidence (level 3) must not be refused just for lacking a `confidence`
    field — hybrid search and graph facts carry authority_level, not confidence, so a
    confidence-only gate would refuse every safety query. Cascade stubbed: this asserts
    the gate opened, not what the model said.
    """
    from api.config import settings

    llm = LLMService(settings)
    monkeypatch.setattr(
        llm, "_synthesize_cascade", lambda prompt, ctx: _answer({"answer": CONTRACT_24, "sources": ctx})
    )
    result = await llm.synthesize(
        query="max allowable pressure for HE-301",
        retrieved_context=[{"document_id": "OEM-1", "text": "MAWP 24 bar", "authority_level": 3}],
        query_category="max_allowable_pressure",
    )
    assert not result.get("refused")
    assert result.get("refusal_reason") is None
    assert "MAWP is 24 bar" in result["answer"]


async def _answer(payload):
    return payload


# A contract-conformant model answer. The post-synthesis gate refuses a safety-critical answer that
# omits its CONFIDENCE line (security review M4), so a stub that clears the gate must carry one.
CONTRACT_X = "ANSWER: x\nCONFIDENCE: 0.9\nSOURCES_USED: 1"
CONTRACT_24 = "ANSWER: MAWP is 24 bar\nCONFIDENCE: 0.9\nSOURCES_USED: 1"


# Stand-in cascade for the tests below: three tiers, no keys that could reach a real endpoint.
RATE_LIMITED_TIERS = [
    Provider(name=name, base_url="https://stub.test/v1", api_key="k", model=f"{name}-model", timeout=5.0)
    for name in ("nim", "openrouter", "gemini")
]


# --- Provider cascade: exhausted quota must not look like a wrong answer ------------
# Repeated benchmark runs exhausted the Gemini free tier; every NIM timeout then became a
# silent no-answer, dragging measured answer quality from 24/25 to 13/25. A 429 is an
# operational limit with a fix, so it must be labelled as one.

async def test_all_providers_rate_limited_reports_the_reason(monkeypatch):
    from api.config import settings

    llm = LLMService(settings)
    # The provider list is stubbed wholesale, so no tier can reach the network whatever keys the
    # environment happens to carry. Before the registry existed this test stubbed each tier by
    # name, and adding OpenRouter silently let a real key through: the cascade made a live call,
    # which both failed the assertion and put a network round-trip inside the service-free suite.
    monkeypatch.setattr(LLMService, "providers", property(lambda self: RATE_LIMITED_TIERS))
    monkeypatch.setattr(LLMService, "ollama_available", property(lambda self: False))

    async def limited(provider, prompt, context):
        return {"answer": None, "error": "429", "sources": context,
                "rate_limited": True, "failed_provider": provider.name}

    monkeypatch.setattr(llm, "_synthesize_provider", limited)

    result = await llm.synthesize(query="seal part number for EQ-101", retrieved_context=[
        {"document_id": "OEM-1", "text": "P/N MS-4471-B", "authority_level": 3}
    ])

    assert result["answer"] is None
    assert result["rate_limited"] is True
    assert "quota exhausted" in result["message"]
    assert all(p in result["message"] for p in ("nim", "openrouter", "gemini"))
    assert "not a knowledge gap" in result["message"]


async def test_ordinary_failure_is_not_reported_as_rate_limited(monkeypatch):
    """A timeout or 500 must not be mislabelled as a quota problem."""
    from api.config import settings

    llm = LLMService(settings)
    # One tier only, and stubbed: a real key in the environment would otherwise reach the network.
    # It would still pass (an answer sets neither flag), which is worse — a silently
    # network-dependent test in the suite that is meant to have none.
    monkeypatch.setattr(LLMService, "providers", property(lambda self: RATE_LIMITED_TIERS[:1]))
    monkeypatch.setattr(LLMService, "ollama_available", property(lambda self: False))

    async def timed_out(provider, prompt, context):
        return {"answer": None, "error": "ReadTimeout", "sources": context,
                "rate_limited": False, "failed_provider": provider.name}

    monkeypatch.setattr(llm, "_synthesize_provider", timed_out)
    result = await llm.synthesize(query="seal part number", retrieved_context=[
        {"document_id": "OEM-1", "text": "x", "authority_level": 3}
    ])
    assert not result.get("rate_limited")
    assert not result.get("message")


# --- Safety gate: authority must come from RELEVANT evidence -------------------------
# Found by manual QA 2026-08-15. The gate took min(authority_level) over the whole retrieved
# context, so one unrelated authoritative document anywhere in it cleared a safety-critical
# refusal. In the live copilot that was the normal case (top-6 hybrid hits nearly always include
# an L1 regulation), so the gate almost never fired.

async def _synth(llm, query, context):
    return await llm.synthesize(query=query, retrieved_context=context,
                                query_category="isolation_interlock_sequence")


async def test_offtopic_authoritative_source_no_longer_clears_the_gate(monkeypatch):
    """An OEM bulletin for a DIFFERENT asset must not vouch for this one.

    Measured on the real corpus: asking for V-247's isolation boundary retrieved two Fischer
    L3 bulletins about EQ-101 pump seals, ranked 3rd/4th by relevance. They cleared the gate.
    """
    from api.config import settings

    llm = LLMService(settings)
    monkeypatch.setattr(llm, "_synthesize_cascade", lambda prompt, ctx: _answer({"answer": CONTRACT_X, "sources": ctx}))

    ctx = [
        {"document_id": "DOC-PTW", "text": "permit to work V-247", "authority_level": 4,
         "relevance_score": 0.0325, "asset_id": "V-247"},
        {"document_id": "DOC-FISCHER", "text": "EQ-1xx seal bulletin", "authority_level": 3,
         "relevance_score": 0.0313, "asset_id": "EQ-101"},
        {"document_id": "DOC-REGREF", "text": "standards index", "authority_level": 1,
         "relevance_score": 0.0156, "asset_id": None},
    ]
    result = await _synth(llm, "isolation boundary for V-247", ctx)
    assert result.get("refused") is True


async def test_on_topic_authoritative_source_still_clears_the_gate(monkeypatch):
    """The gate must not become a blanket refusal — that is why the authority arm exists.
    An OEM bulletin for the SAME asset is exactly the evidence it should accept."""
    from api.config import settings

    llm = LLMService(settings)
    monkeypatch.setattr(llm, "_synthesize_cascade", lambda prompt, ctx: _answer({"answer": CONTRACT_X, "sources": ctx}))

    ctx = [
        {"document_id": "DOC-OEM", "text": "HE-3xx max operating pressure 16.2 bar", "authority_level": 3,
         "relevance_score": 0.033, "asset_id": "HE-301"},
        {"document_id": "DOC-SOP", "text": "site procedure", "authority_level": 4,
         "relevance_score": 0.031, "asset_id": "HE-301"},
    ]
    result = await _synth(llm, "maximum allowable pressure for HE-301", ctx)
    assert not result.get("refused")


async def test_context_without_relevance_scores_keeps_previous_behaviour(monkeypatch):
    """Hand-assembled context (graph facts, elicitation) carries no scores; do not silently
    change refusal behaviour for callers that never knew to send them."""
    from api.config import settings

    llm = LLMService(settings)
    monkeypatch.setattr(llm, "_synthesize_cascade", lambda prompt, ctx: _answer({"answer": CONTRACT_X, "sources": ctx}))

    ctx = [{"document_id": "DOC-SOP", "text": "site procedure", "authority_level": 4},
           {"document_id": "DOC-REG", "text": "regulation", "authority_level": 1}]
    result = await _synth(llm, "isolation boundary for V-247", ctx)
    assert not result.get("refused")


# --- Post-synthesis safety gate + parse-contract leak (found live 2026-08-16) -----------------

from api.services.llm import LLMService  # noqa: E402


def test_parser_recovers_answer_when_the_model_omits_the_ANSWER_marker():
    """
    Regression: models often start with the prose and omit `ANSWER:`. The parser returned
    answer=None, the caller fell back to the raw text, and the user was shown the parse contract
    itself — "…CONFIDENCE: 0.0 UNCERTAINTY: … SOURCES_USED: None" — as the answer.
    """
    raw = (
        "The torque specification for the EQ-999 flange bolts is not specified in the sources.\n"
        "CONFIDENCE: 0.0\n"
        "UNCERTAINTY: Not mentioned in any provided document.\n"
        "SOURCES_USED: None"
    )
    parsed = LLMService.parse_synthesis_response(raw)

    assert parsed["answer"] is not None
    assert "CONFIDENCE:" not in parsed["answer"]
    assert "SOURCES_USED:" not in parsed["answer"]
    assert parsed["confidence"] == 0.0
    assert parsed["sources_used"] == []


def test_well_formed_response_still_parses_unchanged():
    raw = "ANSWER: Torque is 120 Nm.\nCONFIDENCE: 0.92\nUNCERTAINTY: none\nSOURCES_USED: 1, 2"
    parsed = LLMService.parse_synthesis_response(raw)

    assert parsed["answer"] == "Torque is 120 Nm."
    assert parsed["confidence"] == 0.92
    assert parsed["sources_used"] == [1, 2]


async def test_safety_critical_low_self_confidence_refuses_rather_than_hedges(monkeypatch):
    """
    Regression, found live in the UI: a torque query for a non-existent asset retrieved an
    unrelated L3 OEM bulletin, cleared the *pre*-gate on authority, and the model honestly replied
    "not specified" with CONFIDENCE 0.0 — which rendered as a hedged low-confidence answer.

    For a safety-critical parameter that is the forbidden outcome: a hedge reads as confirmation
    to a technician under time pressure. The gate now also inspects the result, not just the
    evidence.
    """
    from api.config import settings

    llm = LLMService(settings)
    monkeypatch.setattr(
        llm, "_synthesize_cascade",
        lambda prompt, ctx: _answer({
            "answer": "Not specified in the provided sources.\nCONFIDENCE: 0.0\nSOURCES_USED: None",
            "sources": ctx,
        }),
    )
    result = await llm.synthesize(
        query="torque specification for EQ-999 flange bolts",
        retrieved_context=[{"document_id": "OEM-1", "text": "EQ-1xx seal spec", "authority_level": 3}],
        query_category="torque_specification",
    )

    assert result["refused"] is True
    assert result["answer"] is None
    assert "does not hedge" in result["refusal_reason"]


async def test_safety_critical_high_self_confidence_is_not_refused(monkeypatch):
    """The post-gate must not fire on a well-supported answer — a false refusal trains operators
    to route around the gate, which is its own safety failure."""
    from api.config import settings

    llm = LLMService(settings)
    monkeypatch.setattr(
        llm, "_synthesize_cascade",
        lambda prompt, ctx: _answer({
            "answer": "ANSWER: Torque is 120 Nm.\nCONFIDENCE: 0.93\nSOURCES_USED: 1",
            "sources": ctx,
        }),
    )
    result = await llm.synthesize(
        query="torque specification for EQ-101 flange bolts",
        retrieved_context=[{"document_id": "OEM-1", "text": "120 Nm", "authority_level": 3}],
        query_category="torque_specification",
    )

    assert not result.get("refused")
    assert "120 Nm" in result["answer"]


def test_parser_handles_the_whole_contract_on_one_line():
    """
    Root cause of the live copilot hedge. NIM returned the contract inline —
    "…not in the sources. CONFIDENCE: 0.0 UNCERTAINTY: … SOURCES_USED: None" — with no newlines.
    The old `^KEY:` (MULTILINE) anchor matched nothing, so confidence/uncertainty/sources_used all
    came back empty. Two consequences: the raw contract leaked to the user as the answer, and the
    post-synthesis safety gate never fired because it had no confidence to judge.
    """
    raw = ("The torque specification for the EQ-999 flange bolts is not mentioned in the provided "
           "source documents. CONFIDENCE: 0.0 UNCERTAINTY: Not stated anywhere. SOURCES_USED: None")
    parsed = LLMService.parse_synthesis_response(raw)

    assert parsed["confidence"] == 0.0
    assert parsed["uncertainty"] == "Not stated anywhere."
    assert parsed["sources_used"] == []
    assert "CONFIDENCE:" not in parsed["answer"]
    assert parsed["answer"].endswith("source documents.")


def test_parser_handles_inline_markers_with_real_sources():
    raw = "ANSWER: Torque is 120 Nm. CONFIDENCE: 0.91 UNCERTAINTY: none SOURCES_USED: 1, 3"
    parsed = LLMService.parse_synthesis_response(raw)

    assert parsed["answer"] == "Torque is 120 Nm."
    assert parsed["confidence"] == 0.91
    assert parsed["sources_used"] == [1, 3]


def test_rca_hypotheses_never_cite_a_document_called_none():
    """
    Found live: RCA returned three hypotheses each with sources ['None'] — the model's
    "SOURCES_USED: None" taken literally as a document id. That is a fabricated provenance chip on
    a surface whose rule is that no claim appears without provenance; citing nothing is honest,
    citing "None" is not.
    """
    raw = (
        "HYPOTHESES:\n"
        "1. Seal failure from improper installation | evidence_weight: 0.5 | sources: None\n"
        "2. Wear from prolonged operation | evidence_weight: 0.4 | sources: DOC-A, DOC-B\n"
        "3. Manufacturing defect | evidence_weight: 0.1 | sources: N/A\n"
        "4. Thermal cycling | evidence_weight: 0.2 | "
        "sources: [No specific document_id, inferred from work_order_created: seal failure]\n"
        "5. Vibration | evidence_weight: 0.3 | sources: speculative\n"
    )
    out = LLMService.parse_rca_response(raw) if hasattr(LLMService, "parse_rca_response") else None
    if out is None:
        import pytest
        pytest.skip("parse_rca_response not exposed as a static helper")
    hyps = out["hypotheses"]
    assert hyps[0]["sources"] == []
    assert hyps[1]["sources"] == ["DOC-A", "DOC-B"]
    assert hyps[2]["sources"] == []
    # Prose masquerading as a citation must not become several fake document ids.
    assert hyps[3]["sources"] == []
    # A bare English word is not a document id — every real one carries a digit or hyphen.
    assert hyps[4]["sources"] == []
