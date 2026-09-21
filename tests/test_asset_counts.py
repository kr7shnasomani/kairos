"""Service-free: a failed issue-count lookup is "unknown", never a clean 0.

`GET /assets/` and `GET /assets/{id}` both show open work orders and compliance gaps. Before
2026-09-22 a failed Supabase lookup returned 0, which renders as "0 compliance gaps": good news
that may not be true. The list helper is pinned here; the detail endpoint uses the same rule.
"""

from types import SimpleNamespace

from api.routers.assets import _issue_counts


class _Query:
    def __init__(self, outcome):
        self._outcome = outcome

    def select(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


class _Supabase:
    """`table(name)` returns a query whose `execute()` yields or raises the configured outcome."""

    def __init__(self, **outcomes):
        self._outcomes = outcomes

    def table(self, name):
        return _Query(self._outcomes[name])


def _rows(*asset_ids):
    return SimpleNamespace(data=[{"asset_id": a} for a in asset_ids], count=len(asset_ids))


async def test_counts_are_tallied_and_an_asset_with_no_rows_is_a_real_zero():
    supabase = _Supabase(operational_events=_rows("EQ-101", "EQ-101"), knowledge_conflicts=_rows("HE-301"))

    counts = await _issue_counts(supabase, ["EQ-101", "HE-301"])

    assert counts["EQ-101"] == {"open_work_orders_count": 2, "compliance_gap_count": 0}
    assert counts["HE-301"] == {"open_work_orders_count": 0, "compliance_gap_count": 1}


async def test_a_failed_lookup_is_unknown_for_that_field_only():
    supabase = _Supabase(operational_events=_rows("EQ-101"), knowledge_conflicts=RuntimeError("PostgREST 500"))

    counts = await _issue_counts(supabase, ["EQ-101", "HE-301"])

    assert counts["EQ-101"] == {"open_work_orders_count": 1, "compliance_gap_count": None}
    assert counts["HE-301"] == {"open_work_orders_count": 0, "compliance_gap_count": None}
