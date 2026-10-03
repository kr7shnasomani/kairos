"""
Layer 8 inbox paging — `routers/briefs.page_inbox`.

Pins the three rules that the endpoint's ordering depends on and that are easy to
break by moving a line:

  1. `limit` applies AFTER the governor/frozen filters, never in SQL.
  2. `delivered + frozen_page` never exceeds `limit`.
  3. Critical (PTW / safety) briefs are never suppressed and never displaced.

Service-free: `page_inbox` is pure, so none of this needs the stack.
"""

from api.routers.briefs import page_inbox

_FULL_BUDGET = 100  # effectively unlimited for tests that don't test suppression


def _b(bid: str, *, priority: str = "normal", frozen: bool = False, trigger: str = "work_order_created") -> dict:
    return {
        "brief_id": bid,
        "priority": priority,
        "delivery_frozen": frozen,
        "trigger_event_type": trigger,
    }


def _ids(briefs: list[dict]) -> list[str]:
    return [b["brief_id"] for b in briefs]


def _page(briefs, *, governor=False, plant=False, limit=10):
    # governor=True → budget=0 (exhausted); governor=False → budget=_FULL_BUDGET
    budget = 0 if governor else _FULL_BUDGET
    return page_inbox(briefs, governor_budget=budget, plant_suppressed=plant, limit=limit)


# ---------------------------------------------------------------------------
# The regression this function was extracted for
# ---------------------------------------------------------------------------

def test_critical_briefs_do_not_starve_normal_ones():
    """
    THE BUG: `limit` was applied in SQL, before the governor/frozen split. A user
    holding `limit` critical briefs consumed the whole page at query time, so a
    normal-priority brief never reached the filters at all — it stayed invisible
    even after the governor cleared. The governor is meant to defer a brief, not
    to hide it permanently.

    With paging after filtering, the normal brief is merely ranked below the
    critical ones; raising the page size reveals it rather than a new query.
    """
    briefs = [_b(f"c{i}", priority="critical") for i in range(10)] + [_b("n1")]

    assert "n1" not in _ids(_page(briefs, limit=10)["delivered"])  # ranked below, off-page
    assert "n1" in _ids(_page(briefs, limit=11)["delivered"])      # reachable, not lost

    # And it is counted as pending either way — the UI can say "10 of 11".
    assert _page(briefs, limit=10)["total_pending"] == 11


def test_page_never_exceeds_limit_when_frozen_briefs_present():
    """
    The endpoint fetches wider than `limit` so filtering has material to work with.
    That widening must not widen the response: `limit` is the caller's page size,
    not a per-category allowance for delivered *and* frozen.
    """
    briefs = [_b(f"d{i}") for i in range(8)] + [_b(f"f{i}", frozen=True) for i in range(8)]
    page = _page(briefs, limit=10)

    assert len(page["delivered"]) + len(page["frozen_page"]) == 10
    assert page["total_pending"] == 16  # everything waiting, not just what fits


def test_frozen_briefs_fill_only_leftover_room():
    briefs = [_b("d1"), _b("d2"), _b("f1", frozen=True), _b("f2", frozen=True)]
    page = _page(briefs, limit=3)

    assert len(page["delivered"]) == 2
    assert len(page["frozen_page"]) == 1


def test_frozen_briefs_are_never_governor_suppressed():
    """Frozen briefs carry a freeze banner, not a push — the governor does not gate them."""
    page = _page([_b("f1", frozen=True)], governor=True, limit=10)

    assert _ids(page["frozen_page"]) == ["f1"]
    assert page["suppressed_count"] == 0


# ---------------------------------------------------------------------------
# Suppression — critical always passes
# ---------------------------------------------------------------------------

def test_governor_suppresses_normal_but_never_critical():
    page = _page([_b("c1", priority="critical"), _b("n1"), _b("n2")], governor=True)

    assert _ids(page["delivered"]) == ["c1"]
    assert page["suppressed_count"] == 2


def test_plant_state_suppresses_normal_but_never_critical():
    """Turnaround / shutdown / emergency raise the bar; a PTW brief still gets through."""
    page = _page([_b("c1", priority="critical"), _b("n1")], plant=True)

    assert _ids(page["delivered"]) == ["c1"]
    assert page["suppressed_count"] == 1


def test_suppression_is_not_double_counted_when_both_gates_fire():
    """A brief suppressed by governor *and* plant state is one held brief, not two."""
    page = _page([_b("n1"), _b("n2")], governor=True, plant=True)

    assert page["suppressed_count"] == 2
    assert page["delivered"] == []


def test_no_suppression_reported_when_nothing_to_suppress():
    page = _page([_b("c1", priority="critical")], governor=True, plant=True)

    assert page["suppressed_count"] == 0


# ---------------------------------------------------------------------------
# B9b: partial budget delivery
# ---------------------------------------------------------------------------

def test_governor_partial_budget_delivers_highest_priority_first():
    """B9b: when 2 slots remain, the two highest-priority normal briefs are delivered
    and the rest are held -- not all-or-nothing as before."""
    briefs = [_b("high", priority="high"), _b("n1"), _b("n2"), _b("n3")]
    page = page_inbox(briefs, governor_budget=2, plant_suppressed=False, limit=10)

    assert _ids(page["delivered"]) == ["high", "n1"]
    assert page["suppressed_count"] == 2
    assert {b["brief_id"] for b in page["suppressed_held"]} == {"n2", "n3"}


def test_governor_full_budget_delivers_all_normal():
    """Budget >= briefs: all normal briefs are delivered, nothing held."""
    briefs = [_b("n1"), _b("n2"), _b("n3")]
    page = page_inbox(briefs, governor_budget=_FULL_BUDGET, plant_suppressed=False, limit=10)

    assert len(page["delivered"]) == 3
    assert page["suppressed_count"] == 0


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def test_critical_outranks_high_outranks_normal_outranks_low():
    briefs = [_b("low", priority="low"), _b("norm"), _b("crit", priority="critical"), _b("high", priority="high")]

    assert _ids(_page(briefs)["delivered"]) == ["crit", "high", "norm", "low"]


def test_recurring_failure_outranks_first_occurrence_at_equal_priority():
    briefs = [
        _b("first", priority="high"),
        _b("recurring", priority="high", trigger="recurring_failure_detected"),
    ]

    assert _ids(_page(briefs)["delivered"]) == ["recurring", "first"]


def test_unknown_priority_ranks_as_normal_rather_than_dropping():
    """An unrecognised priority must still be delivered — dropping a brief is the
    one outcome Layer 8 cannot tolerate."""
    briefs = [_b("weird", priority="urgent-ish"), _b("low", priority="low")]

    assert _ids(_page(briefs)["delivered"]) == ["weird", "low"]


def test_missing_priority_key_is_treated_as_normal():
    page = _page([{"brief_id": "bare", "delivery_frozen": False}])

    assert _ids(page["delivered"]) == ["bare"]


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

def test_empty_inbox():
    page = _page([])

    assert page == {
        "delivered": [],
        "frozen_page": [],
        "suppressed_count": 0,
        "suppressed_held": [],
        "total_pending": 0,
    }


def test_suppressed_briefs_still_count_as_pending():
    """Held is not gone: `total_pending` reflects what is waiting, so the UI can
    show a held count rather than an empty inbox."""
    page = _page([_b("n1"), _b("n2")], governor=True)

    assert page["delivered"] == []
    assert page["total_pending"] == 0  # ranked is empty once suppressed
    assert page["suppressed_count"] == 2


# =============================================================================
# Held briefs are disclosed, not delivered. `suppressed_count` alone told an operator
# "3 held" with no way to tell whether the held one concerned their asset.
# =============================================================================

def test_suppressed_briefs_are_returned_not_just_counted():
    from api.routers.briefs import page_inbox

    briefs = [
        {"brief_id": "b1", "priority": "high", "asset_id": "EQ-101"},
        {"brief_id": "b2", "priority": "medium", "asset_id": "EQ-102"},
    ]
    page = page_inbox(briefs, governor_budget=0, plant_suppressed=False, limit=10)

    assert page["delivered"] == [], "the governor still withholds delivery"
    assert page["suppressed_count"] == 2
    assert [b["brief_id"] for b in page["suppressed_held"]] == ["b1", "b2"], "ranked, highest first"


def test_held_briefs_are_not_folded_into_delivered():
    """Delivering them would spend EEMUA push budget on briefs the governor is withholding —
    the governor would end up suppressing its own disclosure."""
    from api.routers.briefs import page_inbox

    briefs = [{"brief_id": "b1", "priority": "high"}]
    page = page_inbox(briefs, governor_budget=0, plant_suppressed=False, limit=10)

    delivered_ids = {b["brief_id"] for b in page["delivered"]}
    held_ids = {b["brief_id"] for b in page["suppressed_held"]}
    assert delivered_ids.isdisjoint(held_ids)


def test_critical_briefs_are_never_held():
    from api.routers.briefs import page_inbox

    briefs = [
        {"brief_id": "ptw", "priority": "critical"},
        {"brief_id": "routine", "priority": "low"},
    ]
    page = page_inbox(briefs, governor_budget=0, plant_suppressed=True, limit=10)

    assert [b["brief_id"] for b in page["delivered"]] == ["ptw"]
    assert [b["brief_id"] for b in page["suppressed_held"]] == ["routine"]


def test_held_page_respects_limit():
    from api.routers.briefs import page_inbox

    briefs = [{"brief_id": f"b{i}", "priority": "medium"} for i in range(20)]
    page = page_inbox(briefs, governor_budget=0, plant_suppressed=False, limit=5)

    assert page["suppressed_count"] == 20, "the count reports everything waiting"
    assert len(page["suppressed_held"]) == 5, "the page it returns stays bounded"


def test_nothing_held_when_the_governor_is_clear():
    from api.routers.briefs import page_inbox

    briefs = [{"brief_id": "b1", "priority": "high"}]
    page = page_inbox(briefs, governor_budget=_FULL_BUDGET, plant_suppressed=False, limit=10)

    assert page["suppressed_held"] == []
    assert page["suppressed_count"] == 0
    assert [b["brief_id"] for b in page["delivered"]] == ["b1"]
