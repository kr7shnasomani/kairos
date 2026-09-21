"""Model supply-chain integrity — ARCHITECTURE.md §8 mitigations 1 and 3.

Pure logic. No stack, no secrets, no network.
"""

import pytest

from api.services.supply_chain import submission_pattern_outliers, verify_served_model

PIN = "meta/llama-3.1-70b-instruct"


# =============================================================================
# Mitigation 1 — did the provider run the model we pinned?
# =============================================================================

def test_matching_model_is_not_a_mismatch():
    assert verify_served_model(PIN, {"model": PIN}) is None


def test_a_casing_difference_is_the_same_model():
    """Nebius's catalog capitalises the pin ("Nemotron-3-Super-120b-a12b"); warning on that would
    fire on every Token Factory answer and get the check ignored."""
    assert verify_served_model("nvidia/nemotron-3-super-120b-a12b",
                               {"model": "nvidia/Nemotron-3-Super-120b-a12b"}) is None


def test_a_different_model_is_flagged_as_substitution():
    """The supply-chain risk for a hosted model: the provider quietly serves something else."""
    m = verify_served_model(PIN, {"model": "mistralai/mixtral-8x7b"})
    assert m and m["severity"] == "substitution"
    assert m["served"] == "mistralai/mixtral-8x7b"


def test_a_qualified_variant_is_flagged_separately_not_as_substitution():
    """`...-instruct-turbo` is the same family. Calling it substitution would be a false
    positive; ignoring it would hide a quantised or distilled variant."""
    m = verify_served_model(PIN, {"model": PIN + "-turbo"})
    assert m and m["severity"] == "variant"


def test_a_provider_that_reports_no_model_is_not_a_mismatch():
    """Silence is not substitution. Treating it as one would fire on every provider that omits
    the field and get the check switched off."""
    assert verify_served_model(PIN, {"choices": []}) is None
    assert verify_served_model(PIN, None) is None
    assert verify_served_model("", {"model": PIN}) is None


# =============================================================================
# Mitigation 3 — unusual document-submission patterns
# =============================================================================

def test_too_few_accounts_reports_nothing_rather_than_a_weak_signal():
    """With three accounts the busiest is trivially the 'outlier'. A check that always fires is
    one nobody reads."""
    out = submission_pattern_outliers(["a"] * 50 + ["b", "c"])
    assert out["flagged"] == []
    assert out["verdict"] == "insufficient_accounts"


def test_a_dominant_submitter_is_flagged():
    submitters = ["bulk"] * 60 + [f"user{i}" for i in range(1, 8) for _ in range(3)]
    out = submission_pattern_outliers(submitters)
    assert out["verdict"] == "outliers_found"
    assert [f["submitted_by"] for f in out["flagged"]] == ["bulk"]


def test_evenly_spread_submissions_are_clean():
    submitters = [f"user{i}" for i in range(1, 9) for _ in range(5)]
    out = submission_pattern_outliers(submitters)
    assert out["flagged"] == []
    assert out["verdict"] == "clean"


def test_threshold_uses_the_median_not_the_mean():
    """One bulk account would drag a mean far enough that nothing else ever clears it —
    the outlier would raise the bar that is supposed to catch it."""
    submitters = ["whale"] * 1000 + [f"u{i}" for i in range(1, 9) for _ in range(2)]
    out = submission_pattern_outliers(submitters)
    assert out["median_per_account"] == 2
    assert [f["submitted_by"] for f in out["flagged"]] == ["whale"]


@pytest.mark.parametrize("blank", [[], ["", None, ""]])
def test_no_submitters_is_handled(blank):
    out = submission_pattern_outliers(blank)
    assert out["flagged"] == []
    assert out["total_submissions"] == 0
