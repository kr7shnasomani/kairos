"""Service-free: the extraction view and redacted export read entities back from graph edges."""

from api.services.graph import entities_from_edges, person_names_from_edges

DOC = "DOC-INSP-7"


def _row(rel, source, target, confidence=0.9, verification="unverified"):
    return {
        "edge": {"relationship_type": rel, "confidence": confidence, "verification_status": verification},
        "source": source,
        "target": target,
    }


def test_the_entity_is_the_endpoint_that_is_not_the_document():
    affected = [
        _row("DOCUMENTED_BY", {"asset_id": "HE-301"}, {"document_id": DOC}, verification="verified"),
        _row("MENTIONS_PERSON", {"document_id": DOC}, {"name": "Ravi Kumar"}),
        _row("MENTIONS_ORGANISATION", {"document_id": DOC}, {"name": "Meridian Pumps"}),
    ]

    entities = {(e["entity_type"], e["value"]): e for e in entities_from_edges(DOC, affected)}

    assert set(entities) == {("asset_tag", "HE-301"), ("person", "Ravi Kumar"), ("organisation", "Meridian Pumps")}
    assert entities[("asset_tag", "HE-301")]["linked_asset_id"] == "HE-301"
    assert entities[("asset_tag", "HE-301")]["requires_review"] is False
    assert entities[("person", "Ravi Kumar")]["requires_review"] is True


def test_a_relinked_entity_is_listed_once_with_its_strongest_confidence():
    affected = [
        _row("DOCUMENTED_BY", {"asset_id": "P-101"}, {"document_id": DOC}, confidence=0.72),
        _row("DOCUMENTED_BY", {"asset_id": "P-101"}, {"document_id": DOC}, confidence=0.95),
        _row("DOCUMENTED_BY", {"asset_id": "P-101"}, {"document_id": DOC}, confidence=0.8),
    ]

    entities = entities_from_edges(DOC, affected)

    assert len(entities) == 1
    assert entities[0]["confidence"] == 0.95


def test_nodes_without_an_identifying_value_are_skipped():
    assert entities_from_edges(DOC, [_row("DOCUMENTED_BY", {}, {"document_id": DOC})]) == []


def test_redaction_names_come_only_from_person_mentions():
    affected = [
        _row("MENTIONS_PERSON", {"document_id": DOC}, {"name": "Ravi Kumar"}),
        _row("MENTIONS_PERSON", {"document_id": DOC}, {"name": " Ravi Kumar "}),
        _row("MENTIONS_PERSON", {"document_id": DOC}, {"name": "Anita Desai"}),
        _row("MENTIONS_ORGANISATION", {"document_id": DOC}, {"name": "Meridian Pumps"}),
        _row("MENTIONS_PERSON", {"document_id": DOC}, {}),
    ]

    assert person_names_from_edges(affected) == ["Anita Desai", "Ravi Kumar"]
