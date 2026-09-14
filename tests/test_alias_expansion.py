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
