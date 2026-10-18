"""Service-free: confirmed asset aliases are expanded to their canonical id before retrieval."""

from api.services.search_service import expand_query_aliases

ALIASES = [
    {"alias": "P-101", "canonical_asset_id": "EQ-101"},
    {"alias": "Feed Pump A", "canonical_asset_id": "EQ-101"},
    {"alias": "the old Fischer", "canonical_asset_id": "EQ-101"},
    {"alias": "P-10", "canonical_asset_id": "EQ-999"},
]


def test_alias_in_question_appends_canonical_id():
    assert expand_query_aliases("What's the failure history of P-101?", ALIASES) == (
        "What's the failure history of P-101? EQ-101"
    )


def test_multiword_alias_is_case_insensitive_and_added_once():
    assert expand_query_aliases("feed pump a vs the old fischer", ALIASES) == "feed pump a vs the old fischer EQ-101"


def test_alias_must_match_whole_tag_not_a_prefix():
    # "P-10" must not fire inside "P-101", and "P-1011" is a different tag altogether.
    assert expand_query_aliases("inspect P-1011", ALIASES) == "inspect P-1011"


def test_query_already_naming_canonical_is_unchanged():
    assert expand_query_aliases("P-101 (EQ-101) seal", ALIASES) == "P-101 (EQ-101) seal"


def test_no_aliases_is_a_no_op():
    assert expand_query_aliases("EQ-101 seal failure", []) == "EQ-101 seal failure"


# =============================================================================
# The alias register reaches the model as evidence, and never vouches for a safety answer
# =============================================================================

from api.routers.search import _alias_evidence  # noqa: E402
from api.services.llm import LLMService  # noqa: E402

REGISTER = [
    {"alias": "P-102", "canonical_asset_id": "EQ-102"},
    {"alias": "Feed Pump B", "canonical_asset_id": "EQ-102"},
    {"alias": "P-1101A", "canonical_asset_id": "DEMO-P-1101A"},
    {"alias": "Crude feed pump A", "canonical_asset_id": "DEMO-P-1101A"},
]


def test_a_named_asset_brings_its_confirmed_aliases():
    [item] = _alias_evidence("What are the known aliases for pump EQ-102?", REGISTER, include_demo=False)
    assert item["asset_id"] == "EQ-102"
    assert "P-102" in item["text"] and "Feed Pump B" in item["text"]


def test_a_question_naming_no_asset_brings_none():
    assert _alias_evidence("Which standards apply to the facility?", REGISTER, include_demo=False) == []


def test_showcase_aliases_stay_hidden_from_a_real_account():
    q = "What are the aliases for P-1101A?"
    assert _alias_evidence(q, REGISTER, include_demo=False) == []
    assert _alias_evidence(q, REGISTER, include_demo=True)[0]["asset_id"] == "DEMO-P-1101A"


def test_the_register_cannot_clear_the_safety_gate():
    q = "What is the maximum operating pressure for EQ-102?"
    weak = {"document_id": "DOC-1", "asset_id": "EQ-102", "authority_level": 5, "relevance_score": 0.03, "text": "x"}
    context = [weak, *_alias_evidence(q, REGISTER, include_demo=False)]
    llm = object.__new__(LLMService)
    assert llm.evidence_gate(q, context, "max_allowable_pressure", aliases=REGISTER)["refused"] is True


def test_server_built_items_reach_the_prompt_text():
    llm = object.__new__(LLMService)
    block = llm._format_context([{"document_id": "DOC-P", "authority_level": 2, "content": "Valve XV-203 on the drawing."}])
    assert "Valve XV-203 on the drawing." in block
