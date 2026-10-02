"""Documents — Tasks 4-8: vault ingest, OCR/NER pipeline, extraction status, supersede.

Security pass (2026-09-30 review, H5 and H6): authority 1 to 3 may be asserted only by reliability or
admin (anyone else is capped to 4 and told so), `document_type` is one of seven, `asset_id` must be
registered and `occurred_at` is bounded. Superseding an authority 1 to 3 document needs reliability
or admin and an approved MoC (202 `pending_moc_approval` until then); a document cannot supersede
itself and the replacement must be active.
"""

import asyncio
from tests.conftest import uid

_SAMPLE_TEXT = b"""
Kairos Integration Test Document
Asset: P-101 Centrifugal Pump
Procedure: Check bearing temperature every 4 hours during operation.
Failure mode: Seal leak due to shaft misalignment.
Operating pressure: 45 PSI maximum.
"""


async def _ingest(client, asset_id=None, content=None, doc_type="procedure", authority="4", occurred_at=None):
    if content is None:
        content = _SAMPLE_TEXT + f"\nRun-ID: {uid()}".encode()
    files = {"file": (f"test_{uid()}.txt", content, "text/plain")}
    data = {
        "document_type": doc_type,
        "source_system": "integration_test",
        "authority_level": authority,
    }
    if asset_id:
        data["asset_id"] = asset_id
    if occurred_at:
        data["occurred_at"] = occurred_at
    return await client.post("/documents/ingest", files=files, data=data)


async def _poll_status(client, document_id, timeout=60, interval=3):
    """Poll until pipeline_stage leaves 'queued', or timeout."""
    for _ in range(timeout // interval):
        r = await client.get(f"/documents/{document_id}/status")
        assert r.status_code == 200
        stage = r.json()["pipeline_stage"]
        if stage not in ("queued",):
            return r.json()
        await asyncio.sleep(interval)
    return None  # timed out


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

async def test_ingest_document_accepted(admin_client):
    r = await _ingest(admin_client)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert "document_id" in body
    assert "job_id" in body
    assert "sha256" in body
    assert "vault_path" in body


async def test_ingest_document_linked_to_asset(admin_client, shared_asset_id):
    r = await _ingest(admin_client, asset_id=shared_asset_id)
    assert r.status_code == 202
    assert r.json()["status"] == "accepted"


async def test_ingest_duplicate_is_idempotent(admin_client):
    content = f"unique content {uid()}".encode()
    r1 = await _ingest(admin_client, content=content)
    r2 = await _ingest(admin_client, content=content)
    assert r1.status_code == 202
    assert r1.json()["status"] == "accepted"
    assert r2.status_code == 202
    assert r2.json()["status"] == "duplicate"
    assert r2.json()["document_id"] == r1.json()["document_id"]


async def test_authority_above_level_4_is_capped_for_an_engineer(engineer_client):
    r = await _ingest(engineer_client, authority="2")
    assert r.status_code == 202
    body = r.json()
    assert body["authority_requested"] == 2
    assert body["authority_level"] == 4
    assert body["authority_capped"] is True


async def test_authority_is_honoured_for_admin(admin_client):
    r = await _ingest(admin_client, authority="3")
    assert r.status_code == 202
    body = r.json()
    assert body["authority_level"] == 3
    assert body["authority_capped"] is False


async def test_authority_4_is_not_capped(engineer_client):
    r = await _ingest(engineer_client, authority="4")
    assert r.status_code == 202
    assert r.json()["authority_capped"] is False


async def test_ingest_rejects_an_unknown_document_type(admin_client):
    r = await _ingest(admin_client, doc_type="malware")
    assert r.status_code == 422


async def test_ingest_rejects_an_unregistered_asset(admin_client):
    r = await _ingest(admin_client, asset_id=f"ASSET-NOPE-{uid()}")
    assert r.status_code == 422


async def test_ingest_rejects_an_occurred_at_in_the_future(admin_client):
    r = await _ingest(admin_client, occurred_at="2999-01-01T00:00:00Z")
    assert r.status_code == 422


async def test_ingest_rejects_an_occurred_at_over_30_years_old(admin_client):
    r = await _ingest(admin_client, occurred_at="1900-01-01T00:00:00Z")
    assert r.status_code == 422


async def test_field_worker_cannot_ingest(field_client):
    r = await _ingest(field_client)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Status & pipeline
# ---------------------------------------------------------------------------

async def test_get_extraction_status(admin_client):
    r = await _ingest(admin_client)
    doc_id = r.json()["document_id"]

    r2 = await admin_client.get(f"/documents/{doc_id}/status")
    assert r2.status_code == 200
    body = r2.json()
    assert body["document_id"] == doc_id
    assert "pipeline_stage" in body
    assert "progress_percent" in body


async def test_pipeline_advances_beyond_queued(admin_client):
    """Temporal worker should move the document past 'queued' within 60 s."""
    r = await _ingest(admin_client, content=f"distinct {uid()}".encode())
    doc_id = r.json()["document_id"]
    final = await _poll_status(admin_client, doc_id, timeout=60)
    assert final is not None, "Timed out — Temporal worker may not be running"
    assert final["pipeline_stage"] != "queued"


async def test_extraction_status_not_found(admin_client):
    r = await admin_client.get("/documents/DOC-DOES-NOT-EXIST/status")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Metadata & list
# ---------------------------------------------------------------------------

async def test_get_document_metadata(admin_client):
    r = await _ingest(admin_client, content=f"meta {uid()}".encode())
    doc_id = r.json()["document_id"]

    r2 = await admin_client.get(f"/documents/{doc_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["document_id"] == doc_id
    assert body["document_type"] == "procedure"
    assert "sha256_hash" in body
    assert "vault_url" in body
    assert body["status"] == "active"


async def test_get_document_not_found(admin_client):
    r = await admin_client.get("/documents/DOC-NONEXISTENT-XYZ")
    assert r.status_code == 404


async def test_list_documents(admin_client):
    r = await admin_client.get("/documents/")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body


async def test_list_documents_by_asset(admin_client, shared_asset_id):
    await _ingest(admin_client, asset_id=shared_asset_id, content=f"linked {uid()}".encode())
    r = await admin_client.get("/documents/", params={"asset_id": shared_asset_id})
    assert r.status_code == 200
    assert r.json()["total"] >= 1


async def test_list_documents_by_type(admin_client):
    r = await admin_client.get("/documents/", params={"document_type": "procedure"})
    assert r.status_code == 200
    for doc in r.json()["items"]:
        assert doc["document_type"] == "procedure"


# ---------------------------------------------------------------------------
# Extraction results
# ---------------------------------------------------------------------------

async def test_get_extraction_results(admin_client):
    r = await _ingest(admin_client, content=f"extract {uid()}".encode())
    doc_id = r.json()["document_id"]

    r2 = await admin_client.get(f"/documents/{doc_id}/extraction")
    assert r2.status_code == 200
    body = r2.json()
    assert body["document_id"] == doc_id
    assert "graph_edges_created" in body


# ---------------------------------------------------------------------------
# Supersede (vault immutability)
# ---------------------------------------------------------------------------

async def test_supersede_document(admin_client):
    old = await _ingest(admin_client, content=f"old doc {uid()}".encode())
    new = await _ingest(admin_client, content=f"new doc {uid()}".encode())
    old_id = old.json()["document_id"]
    new_id = new.json()["document_id"]

    r = await admin_client.post(
        f"/documents/{old_id}/supersede",
        json={"new_document_id": new_id},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "superseded"
    assert body["old_document_id"] == old_id
    assert body["new_document_id"] == new_id
    assert "edges_closed" in body

    # Old doc should be marked superseded
    meta = await admin_client.get(f"/documents/{old_id}")
    assert meta.json()["status"] == "superseded"


async def test_supersede_already_superseded_returns_409(admin_client):
    old = await _ingest(admin_client, content=f"old2 {uid()}".encode())
    new = await _ingest(admin_client, content=f"new2 {uid()}".encode())
    old_id = old.json()["document_id"]
    new_id = new.json()["document_id"]

    await admin_client.post(f"/documents/{old_id}/supersede", json={"new_document_id": new_id})
    r2 = await admin_client.post(f"/documents/{old_id}/supersede", json={"new_document_id": new_id})
    assert r2.status_code == 409


async def test_document_cannot_supersede_itself(admin_client):
    r = await admin_client.post("/documents/DOC-SELF-NOT-NEEDED/supersede", json={"new_document_id": "DOC-SELF-NOT-NEEDED"})
    assert r.status_code == 400


async def test_replacement_must_be_active(admin_client):
    a = (await _ingest(admin_client, content=f"inactive-a {uid()}".encode())).json()["document_id"]
    b = (await _ingest(admin_client, content=f"inactive-b {uid()}".encode())).json()["document_id"]
    c = (await _ingest(admin_client, content=f"inactive-c {uid()}".encode())).json()["document_id"]
    assert (await admin_client.post(f"/documents/{a}/supersede", json={"new_document_id": b})).status_code == 200

    # `a` is now superseded, so it cannot be the replacement for `c`.
    r = await admin_client.post(f"/documents/{c}/supersede", json={"new_document_id": a})
    assert r.status_code == 409


async def test_supersede_of_high_authority_waits_for_an_approved_moc(admin_client, engineer_client):
    """Authority 1 to 3: reliability/admin only, 202 until the MoC is approved, then it applies."""
    old_id = (await _ingest(admin_client, content=f"gated old {uid()}".encode(), authority="3")).json()["document_id"]
    new_id = (await _ingest(admin_client, content=f"gated new {uid()}".encode())).json()["document_id"]
    path, body = f"/documents/{old_id}/supersede", {"new_document_id": new_id}

    # An engineer may not even request it.
    assert (await engineer_client.post(path, json=body)).status_code == 403

    pending = await admin_client.post(path, json=body)
    assert pending.status_code == 202
    assert pending.json()["status"] == "pending_moc_approval"
    moc_id = pending.json()["moc_id"]
    assert moc_id.startswith("MOC-SUP-")

    # Repeating the request is the same pending MoC, and the old document is untouched.
    again = await admin_client.post(path, json=body)
    assert again.status_code == 202
    assert again.json()["moc_id"] == moc_id
    assert (await admin_client.get(f"/documents/{old_id}")).json()["status"] == "active"

    # Approving the MoC lets the repeated request through.
    assert (await admin_client.post(f"/governance/moc/{moc_id}/approve", json={})).status_code == 200
    applied = await admin_client.post(path, json=body)
    assert applied.status_code == 200
    assert applied.json()["status"] == "superseded"
    assert (await admin_client.get(f"/documents/{old_id}")).json()["status"] == "superseded"


# ---------------------------------------------------------------------------
# P&ID topology (Task 20 / Layer 3)
# ---------------------------------------------------------------------------

async def test_topology_not_found_for_non_pid(admin_client):
    """A procedure document has no P&ID topology — expect 404."""
    r = await _ingest(admin_client, content=f"procedure doc {uid()}".encode(), doc_type="procedure")
    doc_id = r.json()["document_id"]
    r2 = await admin_client.get(f"/documents/{doc_id}/topology")
    assert r2.status_code == 404


async def test_topology_endpoint_exists_for_pid_drawing(admin_client):
    """P&ID drawing ingested as pid_drawing — topology endpoint responds (404 until parsed)."""
    r = await _ingest(admin_client, content=f"pid drawing {uid()}".encode(), doc_type="pid_drawing")
    assert r.status_code == 202
    doc_id = r.json()["document_id"]
    r2 = await admin_client.get(f"/documents/{doc_id}/topology")
    # May be 404 (not yet parsed) or 200 (parsed) — never 5xx
    assert r2.status_code in (200, 404)
    if r2.status_code == 200:
        body = r2.json()
        assert "document_id" in body
        assert "topology" in body
