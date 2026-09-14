"""Service-free: tag-shaped references are not equipment, and a tag with its description still resolves."""

import pytest

from api.services.ner import NERService


@pytest.mark.parametrize(
    "raw",
    [
        "JAN-2025", "MAY-2025", "SB-2025", "PB-2026", "WO-2025", "WO-2026-0714", "PTW-2026-0714",
        "SOP-HE-301-04", "INSP-HE302-2025-Q4", "MHT-PB-2026-11", "GEN-11", "HE-3xx", "HE-3xx Series",
        # What the LLM extractor labels ASSET_TAG once it answers instead of the regex fallback
        # (2026-09-13 reload): phrases, a failure code and a year-stamped engineering reference.
        "heat exchangers", "tubesheet", "shell-side", "Balanced mechanical seal",
        "pressure-retaining equipment", "MECH-SEAL-FAIL", "MHT-ENG-2026-03",
    ],
)
def test_reference_identifiers_are_not_equipment(raw):
    assert NERService.is_reference_identifier(raw)


@pytest.mark.parametrize("raw", ["EQ-101", "PG-18", "XV-203", "P-101", "HX-14B", "FSL-2240A"])
def test_equipment_tags_are_not_references(raw):
    assert not NERService.is_reference_identifier(raw)


def test_tag_with_description_resolves_by_its_leading_tag():
    alias_map = {"HE-301": "HE-301", "P-101": "EQ-101"}
    svc = NERService()
    assert svc.resolve_asset_tag("HE-301 Shell and Tube Heat Exchanger", alias_map) == "HE-301"
    assert svc.resolve_asset_tag("P-101", alias_map) == "EQ-101"
    assert svc.resolve_asset_tag("XV-999 Unknown Valve", alias_map) is None
