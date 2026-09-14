"""Service-free: the compliance audit pack lists each evidence document once."""

from api.routers.compliance import _dedupe_evidence


def test_a_document_linked_several_times_is_listed_once_with_its_strongest_link():
    evidence = [
        {"document_id": "DOC-SOP", "asset_id": "HE-301", "confidence": 0.8, "verification_status": "unverified"},
        {"document_id": "DOC-SOP", "asset_id": "HE-302", "confidence": 0.95, "verification_status": "verified"},
        {"document_id": "DOC-SOP", "asset_id": "HE-301", "confidence": 0.6, "verification_status": "unverified"},
        {"document_id": "DOC-INSP", "asset_id": "HE-301", "confidence": 0.9, "verification_status": "unverified"},
    ]

    deduped = _dedupe_evidence(evidence)

    assert [e["document_id"] for e in deduped] == ["DOC-SOP", "DOC-INSP"]
    sop = deduped[0]
    assert sop["verification_status"] == "verified"
    assert sop["confidence"] == 0.95
    assert sop["asset_ids"] == ["HE-301", "HE-302"]


def test_entries_without_a_document_id_are_dropped():
    assert _dedupe_evidence([{"asset_id": "HE-301"}, {"document_id": "", "asset_id": "HE-302"}]) == []
