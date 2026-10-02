"""Governance — Tasks 21-25, 34: conflicts, quarantine, MoC, SLA, circuit breaker, model gate.

Security pass (2026-09-30 review, H7): the MoC webhook is authenticated by an HMAC, not a user token.
The sender puts unix seconds in `X-Webhook-Timestamp` and a hex HMAC-SHA256 of `"{ts}." + raw body`
(key `MOC_WEBHOOK_SECRET`) in `X-Webhook-Signature`; a request more than 5 minutes off is stale and an
approved MoC cannot be re-opened. These tests sign with the same `MOC_WEBHOOK_SECRET` the API
container holds. Where it is unset (APP_ENV=development) the API accepts an unsigned request and the
signing-failure tests skip.
"""

import hashlib
import hmac
import json
import os
import time

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from tests.conftest import uid

_MOC_SECRET = os.getenv("MOC_WEBHOOK_SECRET") or None


def _signed_webhook(payload, *, timestamp=None, secret=None):
    """`content` and `headers` for a MoC webhook call: the exact bytes that are signed are the bytes sent."""
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    secret = secret or _MOC_SECRET
    if secret:
        ts = str(int(time.time()) if timestamp is None else timestamp)
        headers["X-Webhook-Timestamp"] = ts
        headers["X-Webhook-Signature"] = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"content": body, "headers": headers}


async def _moc_id_from_deviation(admin_client, asset_id, note):
    """Create a MoC the way the UI does: a deviation flag resolved with moc_warranted."""
    r1 = await admin_client.post("/events/deviation-flag", json={"asset_id": asset_id, "description": note})
    assert r1.status_code == 202
    r2 = await admin_client.post(f"/events/deviation-flag/{r1.json()['item_id']}/resolve", json={
        "resolution": "promoted",
        "moc_warranted": True,
        "notes": "MoC warranted by inspection evidence",
    })
    assert r2.status_code == 200
    moc_id = r2.json().get("moc_id")
    assert moc_id is not None, "moc_warranted=True should return a moc_id"
    return moc_id


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------

async def test_list_conflicts_shape(admin_client):
    r = await admin_client.get("/governance/conflicts")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body


async def test_list_conflicts_filter_track(admin_client):
    r = await admin_client.get("/governance/conflicts", params={"track": "administrative"})
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["track"] == "administrative"


async def test_conflict_not_found(admin_client):
    r = await admin_client.get(f"/governance/conflicts/{uuid4()}")
    assert r.status_code == 404


async def test_resolve_conflict_not_found(admin_client):
    """Resolving a non-existent conflict UUID → 404."""
    r = await admin_client.post(f"/governance/conflicts/{uuid4()}/resolve", json={"resolution": "accepted"})
    assert r.status_code == 404


async def test_resolve_administrative_conflict(admin_client):
    """Resolve an administrative-track conflict if one exists; skip otherwise."""
    r = await admin_client.get("/governance/conflicts", params={"track": "administrative", "status": "open"})
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        pytest.skip("No open administrative-track conflicts in DB")
    conflict_id = items[0]["conflict_id"]

    r2 = await admin_client.post(f"/governance/conflicts/{conflict_id}/resolve", json={
        "resolution": "accepted",
        "notes": "Resolved by integration test",
    })
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "resolved"
    assert body["conflict_id"] == conflict_id


async def test_resolve_engineering_track_conflict_rejected(admin_client):
    """Engineering-track conflicts must go through MoC webhook → 400."""
    r = await admin_client.get("/governance/conflicts", params={"track": "engineering"})
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        pytest.skip("No engineering-track conflicts in DB")
    conflict_id = items[0]["conflict_id"]

    r2 = await admin_client.post(f"/governance/conflicts/{conflict_id}/resolve", json={"resolution": "accepted"})
    assert r2.status_code == 400


# ---------------------------------------------------------------------------
# Quarantine
# ---------------------------------------------------------------------------

async def test_list_quarantine_shape(admin_client):
    r = await admin_client.get("/governance/quarantine")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert "note" in body


async def test_quarantine_defaults_to_pending(admin_client):
    r = await admin_client.get("/governance/quarantine")
    for item in r.json()["items"]:
        assert item["review_status"] == "pending"


async def test_quarantine_filter_by_review_status(admin_client):
    r = await admin_client.get("/governance/quarantine", params={"review_status": "disputed"})
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["review_status"] == "disputed"


async def test_promote_quarantine_item(admin_client, fresh_asset_id):
    """Create a quarantine item via inspection event, then promote it."""
    from tests.conftest import uid
    now = datetime.now(timezone.utc).isoformat()

    # Create a low-confidence inspection → goes to quarantine
    r = await admin_client.post("/events/inspection-complete", json={
        "event_id": uid(),
        "source_system": "test",
        "site_id": "SITE_001",
        "occurred_at": now,
        "received_at": now,
        "asset_id": fresh_asset_id,
        "inspection_type": "thermal_imaging",
        "result": "conditional",
        "performed_by": "TECH-TEST",
        "confidence": 0.5,
    })
    assert r.status_code == 202
    item_id = r.json()["quarantine_item_id"]
    assert item_id is not None

    r2 = await admin_client.post(f"/governance/quarantine/{item_id}/promote", json={
        "relationship_type": "DOCUMENTED_BY",
        "authority_level": 4,
        "document_type": "inspection_report",
        "notes": "Promoted by integration test",
    })
    assert r2.status_code == 200
    body = r2.json()
    assert body["status"] == "promoted"
    assert body["item_id"] == item_id
    assert "edge_id" in body


async def test_dispute_quarantine_item(admin_client, fresh_asset_id):
    now = datetime.now(timezone.utc).isoformat()
    r = await admin_client.post("/events/inspection-complete", json={
        "event_id": uid(),
        "source_system": "test",
        "site_id": "SITE_001",
        "occurred_at": now,
        "received_at": now,
        "asset_id": fresh_asset_id,
        "inspection_type": "visual",
        "result": "failed",
        "performed_by": "TECH-TEST",
        "confidence": 0.4,
    })
    item_id = r.json()["quarantine_item_id"]

    r2 = await admin_client.post(
        f"/governance/quarantine/{item_id}/dispute",
        json={"reason": "Incorrect observation — misread sensor"},
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "disputed"


async def test_request_quarantine_info_is_audited(admin_client, fresh_asset_id):
    """Layer 6 fourth review action: request more info leaves the item pending."""
    now = datetime.now(timezone.utc).isoformat()
    r = await admin_client.post("/events/inspection-complete", json={
        "event_id": uid(),
        "source_system": "test",
        "site_id": "SITE_001",
        "occurred_at": now,
        "received_at": now,
        "asset_id": fresh_asset_id,
        "inspection_type": "visual",
        "result": "conditional",
        "performed_by": "TECH-TEST",
        "confidence": 0.4,
    })
    item_id = r.json()["quarantine_item_id"]

    response = await admin_client.post(
        f"/governance/quarantine/{item_id}/request-info",
        json={"note": "Please attach the calibration record."},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "requested", "item_id": item_id}

    # Item stays pending (still actionable), so it can still be promoted/disputed after.
    listing = await admin_client.get("/governance/quarantine", params={"review_status": "pending"})
    assert any(it["item_id"] == item_id for it in listing.json()["items"])


async def test_double_promote_returns_409(admin_client, fresh_asset_id):
    now = datetime.now(timezone.utc).isoformat()
    r = await admin_client.post("/events/inspection-complete", json={
        "event_id": uid(),
        "source_system": "test",
        "site_id": "SITE_001",
        "occurred_at": now,
        "received_at": now,
        "asset_id": fresh_asset_id,
        "inspection_type": "vibration",
        "result": "failed",
        "performed_by": "TECH-TEST",
        "confidence": 0.3,
    })
    item_id = r.json()["quarantine_item_id"]

    promote = {"relationship_type": "DOCUMENTED_BY", "authority_level": 4, "document_type": "inspection_report"}
    r1 = await admin_client.post(f"/governance/quarantine/{item_id}/promote", json=promote)
    r2 = await admin_client.post(f"/governance/quarantine/{item_id}/promote", json=promote)
    assert r1.status_code == 200
    assert r2.status_code == 409


# ---------------------------------------------------------------------------
# SLA report
# ---------------------------------------------------------------------------

async def test_sla_report_shape(admin_client):
    r = await admin_client.get("/governance/sla-report")
    assert r.status_code == 200
    body = r.json()
    assert "checked_at" in body
    assert "escalated_this_run" in body
    assert "overdue_conflicts" in body
    assert "overdue_quarantine_items" in body


# ---------------------------------------------------------------------------
# Circuit breaker (Task 25)
# ---------------------------------------------------------------------------

async def test_circuit_breaker_shape(admin_client):
    r = await admin_client.get("/governance/circuit-breaker")
    assert r.status_code == 200
    body = r.json()
    assert "states" in body
    assert "halted_count" in body


# ---------------------------------------------------------------------------
# MoC
# ---------------------------------------------------------------------------

async def test_list_moc_shape(admin_client):
    r = await admin_client.get("/governance/moc")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body


async def test_get_conflict_detail(admin_client):
    """GET /governance/conflicts/{id} returns conflict detail + blast_radius; skip if no conflicts."""
    r = await admin_client.get("/governance/conflicts")
    assert r.status_code == 200
    items = r.json()["items"]
    if not items:
        pytest.skip("No conflicts in DB")
    conflict_id = items[0]["conflict_id"]

    r2 = await admin_client.get(f"/governance/conflicts/{conflict_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert "conflict" in body
    assert "blast_radius" in body
    assert body["conflict"]["conflict_id"] == conflict_id


async def test_moc_webhook_bad_payload(admin_client):
    r = await admin_client.post("/governance/moc/webhook", **_signed_webhook({"moc_id": "FAKE"}))
    assert r.status_code == 400


async def test_moc_webhook_valid_payload(admin_client, shared_asset_id):
    """Valid, signed MoC webhook payload → 200 with moc_id and resolution in response."""
    moc_id = await _moc_id_from_deviation(admin_client, shared_asset_id, "Webhook test — topology change confirmed")

    # Test that the webhook accepts the moc_id with a valid status
    r3 = await admin_client.post("/governance/moc/webhook", **_signed_webhook({
        "moc_id": moc_id,
        "status": "rejected",
        "approved_by": "test-runner",
    }))
    assert r3.status_code == 200
    body = r3.json()
    assert body["moc_id"] == moc_id
    assert body["resolution"] == "rejected"


async def test_moc_webhook_without_a_signature_is_refused(admin_client):
    if not _MOC_SECRET:
        pytest.skip("MOC_WEBHOOK_SECRET is not set: the API accepts unsigned webhooks in development")
    r = await admin_client.post("/governance/moc/webhook", json={"moc_id": "FAKE", "status": "approved"})
    assert r.status_code == 401


async def test_moc_webhook_with_a_wrong_signature_is_refused(admin_client):
    if not _MOC_SECRET:
        pytest.skip("MOC_WEBHOOK_SECRET is not set: the API accepts unsigned webhooks in development")
    r = await admin_client.post(
        "/governance/moc/webhook", **_signed_webhook({"moc_id": "FAKE", "status": "approved"}, secret="not-the-secret")
    )
    assert r.status_code == 401


async def test_moc_webhook_stale_timestamp_is_refused(admin_client):
    """A correctly signed body older than 5 minutes is a replay, not a fresh call."""
    if not _MOC_SECRET:
        pytest.skip("MOC_WEBHOOK_SECRET is not set: the API accepts unsigned webhooks in development")
    stale = int(time.time()) - 6 * 60
    r = await admin_client.post(
        "/governance/moc/webhook", **_signed_webhook({"moc_id": "FAKE", "status": "approved"}, timestamp=stale)
    )
    assert r.status_code == 401


async def test_moc_webhook_cannot_reopen_an_approved_moc(admin_client, shared_asset_id):
    moc_id = await _moc_id_from_deviation(admin_client, shared_asset_id, "Webhook replay test")
    approve = {"moc_id": moc_id, "status": "approved", "approved_by": "test-runner"}

    first = await admin_client.post("/governance/moc/webhook", **_signed_webhook(approve))
    assert first.status_code == 200
    # An in-window replay of a captured body, or a "rejected" follow-up, is refused.
    assert (await admin_client.post("/governance/moc/webhook", **_signed_webhook(approve))).status_code == 409
    reject = await admin_client.post("/governance/moc/webhook", **_signed_webhook({**approve, "status": "rejected"}))
    assert reject.status_code == 409


# ---------------------------------------------------------------------------
# Blast radius
# ---------------------------------------------------------------------------

async def test_blast_radius_nonexistent_doc(admin_client):
    r = await admin_client.get("/governance/blast-radius/DOC-NONEXISTENT-XYZ")
    assert r.status_code == 200  # returns empty blast radius, not 404


# ---------------------------------------------------------------------------
# Validation corpus & model gate (Task 34)
# ---------------------------------------------------------------------------

async def test_validation_corpus_stats(admin_client):
    r = await admin_client.get("/governance/validation-corpus/stats")
    assert r.status_code == 200
    body = r.json()
    assert "total_corpus_size" in body
    assert "by_entity_type" in body


async def test_model_gate_history(admin_client):
    r = await admin_client.get("/governance/model-gate/history")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body


async def test_model_gate_run_requires_admin(admin_client, field_client):
    r_field = await field_client.post("/governance/model-gate/run", params={"model_name": "mXLM-RoBERTa"})
    assert r_field.status_code == 403

    r_admin = await admin_client.post("/governance/model-gate/run", params={"model_name": "mXLM-RoBERTa"})
    assert r_admin.status_code == 200
    assert "task_id" in r_admin.json()
