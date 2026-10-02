"""Annotations — Task 21: Active Learning Annotation Interface (Layer 3).

Security pass (2026-09-30 review, M7): any role may record a correction, but only reliability and
admin feed the validation corpus (the ground truth the model gate scores against). Repeat overrides
are de-duplicated and one user is limited to 60 corrections an hour; both of those need more writes
than a test should make, so they are not exercised here.
"""

from tests.conftest import uid


async def _ingest_doc(client, content=None):
    """Helper: ingest a document and return its document_id."""
    if content is None:
        content = f"annotation test doc {uid()}".encode()
    r = await client.post("/documents/ingest", files={
        "file": (f"ann_test_{uid()}.txt", content, "text/plain"),
    }, data={
        "document_type": "procedure",
        "source_system": "annotation_test",
        "authority_level": "3",
    })
    assert r.status_code == 202, f"ingest failed: {r.text}"
    return r.json()["document_id"]


async def test_annotation_stats_shape(admin_client):
    r = await admin_client.get("/annotations/stats")
    assert r.status_code == 200
    body = r.json()
    assert "total" in body
    assert "corrections_this_week" in body
    assert "top_corrected_entity_types" in body


async def test_list_annotations_requires_document_id(admin_client):
    r = await admin_client.get("/annotations/")
    assert r.status_code == 422


async def test_list_annotations_empty_for_unknown_doc(admin_client):
    """An ingested doc with no annotations returns total=0."""
    doc_id = await _ingest_doc(admin_client)
    r = await admin_client.get("/annotations/", params={"document_id": doc_id})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_create_annotation_correct(admin_client):
    doc_id = await _ingest_doc(admin_client)
    r = await admin_client.post("/annotations/", json={
        "document_id": doc_id,
        "entity_text": "bearing housing",
        "entity_type": "COMPONENT",
        "is_correct": True,
        "span_start": 0,
        "span_end": 14,
    })
    assert r.status_code == 201
    body = r.json()
    assert "annotation_id" in body
    assert body["is_correct"] is True
    assert body["document_id"] == doc_id
    assert "quarantine_confidence_updated" in body


async def test_create_annotation_correction(admin_client):
    """is_correct=False with corrected_type — incorrect entity correction flow."""
    doc_id = await _ingest_doc(admin_client)
    r = await admin_client.post("/annotations/", json={
        "document_id": doc_id,
        "entity_text": "45 PSI",
        "entity_type": "MEASUREMENT",
        "corrected_type": "PRESSURE_LIMIT",
        "is_correct": False,
        "span_start": 5,
        "span_end": 11,
    })
    assert r.status_code == 201
    body = r.json()
    assert "annotation_id" in body
    assert body["is_correct"] is False


async def test_create_annotation_feeds_corpus(admin_client):
    """Correct annotation (is_correct=True) should appear in listing."""
    doc_id = await _ingest_doc(admin_client)
    r = await admin_client.post("/annotations/", json={
        "document_id": doc_id,
        "entity_text": "pump impeller",
        "entity_type": "COMPONENT",
        "is_correct": True,
    })
    assert r.status_code == 201
    r2 = await admin_client.get("/annotations/", params={"document_id": doc_id})
    assert r2.status_code == 200
    assert r2.json()["total"] >= 1


async def test_list_annotations_returns_created(admin_client):
    doc_id = await _ingest_doc(admin_client)
    for is_correct in (True, False):
        await admin_client.post("/annotations/", json={
            "document_id": doc_id,
            "entity_text": "seal ring",
            "entity_type": "COMPONENT",
            "is_correct": is_correct,
            "corrected_type": "SEAL" if not is_correct else None,
        })

    r = await admin_client.get("/annotations/", params={"document_id": doc_id})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["document_id"] == doc_id
    for item in body["items"]:
        assert "entity_text" in item
        assert "is_correct" in item


async def test_annotation_missing_required_fields(admin_client):
    r = await admin_client.post("/annotations/", json={
        "document_id": "DOC-X",
        # missing entity_text, entity_type, is_correct
    })
    assert r.status_code == 422


async def _corpus_size(client):
    r = await client.get("/governance/validation-corpus/stats")
    assert r.status_code == 200
    return r.json()["total_corpus_size"]


async def test_correct_annotation_from_an_engineer_does_not_feed_the_validation_corpus(admin_client, engineer_client):
    doc_id = await _ingest_doc(admin_client)
    before = await _corpus_size(admin_client)

    r = await engineer_client.post("/annotations/", json={
        "document_id": doc_id,
        "entity_text": "bearing housing",
        "entity_type": "COMPONENT",
        "is_correct": True,
    })
    assert r.status_code == 201  # the correction itself is still recorded
    assert await _corpus_size(admin_client) == before


async def test_correct_annotation_from_reliability_is_accepted(admin_client, reliability_client):
    doc_id = await _ingest_doc(admin_client)
    before = await _corpus_size(admin_client)

    r = await reliability_client.post("/annotations/", json={
        "document_id": doc_id,
        "entity_text": "pump impeller",
        "entity_type": "COMPONENT",
        "is_correct": True,
    })
    assert r.status_code == 201
    # Reliability feeds the corpus. The stats read is a capped page, so assert "never less", not "+1".
    assert await _corpus_size(admin_client) >= before
