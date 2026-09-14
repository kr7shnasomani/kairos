"""Documents — Tasks 4-8: vault ingest, OCR/NER pipeline, extraction status, supersede."""

import asyncio
from tests.conftest import uid

_SAMPLE_TEXT = b"""
Kairos Integration Test Document
Asset: P-101 Centrifugal Pump
Procedure: Check bearing temperature every 4 hours during operation.
Failure mode: Seal leak due to shaft misalignment.
Operating pressure: 45 PSI maximum.
"""


async def _ingest(client, asset_id=None, content=None, doc_type="procedure"):
    if content is None:
        content = _SAMPLE_TEXT + f"\nRun-ID: {uid()}".encode()
    files = {"file": (f"test_{uid()}.txt", content, "text/plain")}
    data = {
        "document_type": doc_type,
        "source_system": "integration_test",
        "authority_level": "4",
    }
    if asset_id:
        data["asset_id"] = asset_id
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
