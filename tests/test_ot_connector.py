"""OT Connector — Task 17: Go service at port 8090 (Layer 5: zero-copy OT virtualisation)."""

import os
import pytest
import httpx

OT_BASE_URL = os.getenv("OT_CONNECTOR_URL", "http://localhost:8090")


@pytest.fixture
async def ot_client():
    headers = {"X-Connector-Secret": os.getenv("CONNECTOR_SHARED_SECRET", "kairos-connector-dev-secret")}
    async with httpx.AsyncClient(base_url=OT_BASE_URL, timeout=15.0, headers=headers) as client:
        yield client


async def test_ot_connector_health(ot_client):
    r = await ot_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "kairos-connector"


async def test_ot_query_requires_asset_and_tag(ot_client):
    r = await ot_client.get("/ot/query")
    assert r.status_code == 400


async def test_ot_query_returns_timeseries(ot_client, shared_asset_id):
    r = await ot_client.get("/ot/query", params={
        "asset_id": shared_asset_id,
        "tag": f"{shared_asset_id}-VIBE",
    })
    assert r.status_code == 200
    body = r.json()
    assert "asset_id" in body
    assert "tag" in body
    assert "data" in body
    assert isinstance(body["data"], list)
    # Mock historian returns data points
    assert "from" in body
    assert "to" in body


async def test_ot_query_mock_flag(ot_client):
    """Mock historian is used when PI_WEBAPI_BASE_URL is not set."""
    r = await ot_client.get("/ot/query", params={
        "asset_id": "ASSET-001",
        "tag": "ASSET-001-TEMP",
    })
    assert r.status_code == 200
    body = r.json()
    # In dev, PI_WEBAPI_BASE_URL is unset so mock=True
    assert "mock" in body


# REMOVED 2026-08-22: `test_ot_coverage_returns_shape` and `test_ot_coverage_unknown_asset`.
#
# They exercised `GET /ot/coverage/{asset_id}` on the Go connector, which was **deliberately
# deleted on 2026-08-16** (see docs/API.md §13 and docs/BACKEND.md) because it returned
# hardcoded `{asset}-VIBE` / `{asset}-TEMP` / `75%` for every asset — fabricated sensor tags,
# which Layer 5 forbids outright: coverage counts only *verified* topology, and
# `coverage_type: "none"` is not the same claim as "no sensors".
#
# The second test asserted "unknown asset falls back to mock coverage — still 200", i.e. it
# pinned the fabrication as required behaviour. Left in place, it would have pressured whoever
# tried to make the suite green into re-adding the bug the deletion removed.
#
# Instrumentation coverage now derives from verified topology in Python:
#   GET /assets/{asset_id}/ot-coverage  →  api/services/ot_coverage.py
# covered by tests/test_ot_coverage.py, which pins the honest behaviour instead — an asset with
# no linked drawing reports none rather than guessing, and unverified topology is not coverage.


async def test_eam_sync_returns_completed(ot_client):
    r = await ot_client.post("/eam/sync")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert "total" in body
    assert "synced" in body
    assert body["synced"] >= 0


async def test_eam_work_order_forwarding(ot_client, shared_asset_id):
    """Go connector forwards work order payload to FastAPI /events/work-order."""
    from datetime import datetime, timezone
    from tests.conftest import uid as _uid
    payload = {
        "event_id": _uid(),
        "source_system": "SAP_PM",
        "site_id": "SITE_001",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "work_order_id": f"WO-GO-{_uid()}",
        "asset_id": shared_asset_id,
        "failure_code": "BEARING_WEAR",
        "description": "Go connector forwarding test",
        "priority": "high",
    }
    r = await ot_client.post("/eam/work-order", json=payload)
    # Go connector forwards to FastAPI — expect 202 (accepted or deduplicated)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] in ("accepted", "deduplicated")
    assert "event_id" in body
