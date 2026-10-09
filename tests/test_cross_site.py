"""Cross-site failure patterns (`services/cross_site.py`): pure grouping, no stack."""

from api.services.cross_site import find_patterns

ASSETS = [
    {"asset_id": "A1", "equipment_class": "pump", "site_id": "S1"},
    {"asset_id": "A2", "equipment_class": "pump", "site_id": "S1"},
    {"asset_id": "B1", "equipment_class": "pump", "site_id": "S2"},
    {"asset_id": "C1", "equipment_class": "tank", "site_id": "S1"},
]


def _wo(asset_id: str, code: str, day: int = 1) -> dict:
    return {"asset_id": asset_id, "occurred_at": f"2026-09-{day:02d}T00:00:00+00:00", "payload": {"failure_code": code}}


def test_a_family_seen_at_two_sites_is_a_shared_pattern():
    # SEAL-FAIL and LEAK-MECH are one family ("seal"), so they count together.
    out = find_patterns([_wo("A1", "SEAL-FAIL", 1), _wo("A2", "LEAK-MECH", 3), _wo("B1", "SEAL-FAIL", 2)], ASSETS)
    assert len(out) == 1
    p = out[0]
    assert (p["equipment_class"], p["failure_family"], p["kind"], p["total_events"]) == ("pump", "seal", "shared", 3)
    s1, s2 = p["sites"]
    assert (s1["site_id"], s1["events"], s1["assets_affected"], s1["assets_in_class"]) == ("S1", 2, 2, 2)
    assert s1["last_seen"].startswith("2026-09-03")
    assert (s2["site_id"], s2["events"], s2["assets_in_class"]) == ("S2", 1, 1)


def test_recurring_at_one_site_warns_the_sister_site_that_runs_the_class():
    out = find_patterns([_wo("A1", "VIBE-HIGH"), _wo("A1", "BEARING-FAIL")], ASSETS)
    assert [p["kind"] for p in out] == ["advisory"]
    exposed = [s for s in out[0]["sites"] if s["site_id"] == "S2"][0]
    assert (exposed["events"], exposed["assets_affected"], exposed["last_seen"]) == (0, 0, None)


def test_one_work_order_is_an_incident_not_a_pattern():
    assert find_patterns([_wo("A1", "SEAL-FAIL"), _wo("B1", "VIBE-HIGH")], ASSETS) == []


def test_a_class_on_one_site_has_nothing_to_compare():
    assert find_patterns([_wo("C1", "SEAL-FAIL"), _wo("C1", "SEAL-FAIL")], ASSETS) == []


def test_blank_codes_and_unknown_assets_join_no_pattern():
    rows = [_wo("A1", ""), _wo("A1", " "), _wo("ZZ", "SEAL-FAIL"), _wo("ZZ", "SEAL-FAIL"), {"asset_id": "A1", "payload": None}]
    assert find_patterns(rows, ASSETS) == []


def test_the_output_carries_no_free_text_or_person():
    wo = _wo("A1", "SEAL-FAIL") | {"payload": {"failure_code": "SEAL-FAIL", "description": "R. Sharma saw a leak", "assigned_technician_id": "u-1"}}
    out = find_patterns([wo, wo, _wo("B1", "SEAL-FAIL")], ASSETS)
    assert "Sharma" not in repr(out) and "u-1" not in repr(out)
    assert set(out[0]) == {"equipment_class", "failure_family", "kind", "total_events", "sites"}
