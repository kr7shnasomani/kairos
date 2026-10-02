"""Briefs — Tasks 17-18: EEMUA 191 governor, brief delivery, ack, feedback.

Security pass (2026-09-30 review, L11): an acknowledgement is final (a second ack is a 409) and
feedback needs read access to the brief, so a brief you cannot open is a 404 for ack and feedback too.
"""

from uuid import uuid4


async def test_get_my_briefs_shape(admin_client):
    r = await admin_client.get("/briefs/")
    assert r.status_code == 200
    body = r.json()
    assert "briefs" in body
    assert "total_pending" in body
    assert "suppressed_count" in body
    assert "governor_state" in body
    gov = body["governor_state"]
    assert "push_count_last_hour" in gov
    assert "ceiling" in gov
    assert "state" in gov


async def test_governor_ceiling_is_6(admin_client):
    r = await admin_client.get("/briefs/")
    gov = r.json()["governor_state"]
    assert gov["ceiling"] == 6


async def test_governor_state_is_valid_value(admin_client):
    r = await admin_client.get("/briefs/")
    state = r.json()["governor_state"]["state"]
    assert state in ("normal", "suppressed")


async def test_get_governor_status_endpoint(admin_client):
    r = await admin_client.get("/briefs/governor/status")
    assert r.status_code == 200
    body = r.json()
    assert "push_count_last_hour" in body
    assert "ceiling" in body
    assert "state" in body


async def test_get_briefs_unacknowledged_only_default(admin_client):
    r = await admin_client.get("/briefs/", params={"unacknowledged_only": True})
    assert r.status_code == 200
    for b in r.json()["briefs"]:
        assert b.get("acknowledged_at") is None or b.get("frozen") is True


async def test_get_briefs_all_including_acknowledged(admin_client):
    r = await admin_client.get("/briefs/", params={"unacknowledged_only": False})
    assert r.status_code == 200
    assert "briefs" in r.json()


async def test_brief_not_found_returns_404(admin_client):
    r = await admin_client.get(f"/briefs/{uuid4()}")
    assert r.status_code == 404


async def test_ack_nonexistent_brief_returns_404(admin_client):
    r = await admin_client.post(f"/briefs/{uuid4()}/ack")
    assert r.status_code == 404


async def test_brief_feedback_requires_rating(admin_client):
    from datetime import datetime, timezone
    r = await admin_client.post(f"/briefs/{uuid4()}/feedback", json={
        "rating": "accurate",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    })
    # Feedback needs read access to the brief, so an unknown brief is a 404
    assert r.status_code == 404


async def _ptw_brief_id(admin_client):
    """POST a PTW for a fresh asset with the connector as issuing engineer; return the brief id.

    PTW briefs are addressed to the issuing engineer (here the admin test identity) and carry
    requires_countersignature=True, so only that user and staff may open them."""
    from datetime import datetime, timezone
    from tests.conftest import uid as _uid

    # Use a fresh asset so 4h cool-down (per recipient+asset) never triggers
    fresh_asset_id = f"ASSET-ACK-{_uid()}"
    ra = await admin_client.post("/assets/", json={
        "asset_id": fresh_asset_id,
        "tag_number": f"TAG-ACK-{_uid()}",
        "name": "Brief Ack Test Asset",
        "equipment_class": "PUMP",
        "criticality": "critical",
        "site_id": "SITE_001",
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "test-runner",
    })
    assert ra.status_code == 201

    now = datetime.now(timezone.utc).isoformat()
    r = await admin_client.post("/events/ptw", json={
        "event_id": _uid(),
        "source_system": "PTW_system",
        "site_id": "SITE_001",
        "occurred_at": now,
        "received_at": now,
        "ptw_id": f"PTW-ACK-{_uid()}",
        "work_area": "Ack Test Bay",
        "asset_ids": [fresh_asset_id],
        "ptw_type": "isolation",
        "issuing_engineer_id": "service-kairos-connector",  # matches admin_client user_id
    })
    assert r.status_code == 202
    brief_id = r.json().get("brief_id")
    assert brief_id is not None, "PTW handler must return brief_id immediately"
    return brief_id


async def test_ack_brief_via_ptw(admin_client):
    """
    POST PTW with issuing_engineer_id=service-kairos-connector assembles a brief immediately.
    ACK that brief → 200 with status field present.
    PTW briefs have requires_countersignature=True → status=pending_countersignature.
    """
    brief_id = await _ptw_brief_id(admin_client)

    r2 = await admin_client.post(f"/briefs/{brief_id}/ack")
    assert r2.status_code == 200
    body = r2.json()
    assert body["brief_id"] == brief_id
    assert "status" in body  # "acknowledged" or "pending_countersignature" for PTW


async def test_second_ack_is_409(admin_client):
    """An acknowledgement is final: re-acking would swap the acknowledger the countersigner is checked against."""
    brief_id = await _ptw_brief_id(admin_client)
    assert (await admin_client.post(f"/briefs/{brief_id}/ack")).status_code == 200
    assert (await admin_client.post(f"/briefs/{brief_id}/ack")).status_code == 409


async def test_non_recipient_cannot_ack_or_rate_a_brief(admin_client, field_client):
    """A brief addressed to someone else is a 404 for a non-staff caller, for ack and feedback alike."""
    from datetime import datetime, timezone

    brief_id = await _ptw_brief_id(admin_client)
    assert (await field_client.post(f"/briefs/{brief_id}/ack")).status_code == 404
    feedback = await field_client.post(f"/briefs/{brief_id}/feedback", json={
        "rating": "accurate",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    })
    assert feedback.status_code == 404


async def test_attribution_worker_queues_recheck(admin_client):
    """
    Attribution worker: rating=incorrect on a real brief → audit_log row with
    action=confidence_recheck_queued (Task 16, Task 13).
    """
    import asyncio
    from datetime import datetime, timezone

    # Ingest a work order so a brief gets assembled
    from tests.conftest import uid as _uid
    now = datetime.now(timezone.utc).isoformat()
    wo_r = await admin_client.post("/events/work-order", json={
        "event_id": _uid(),
        "source_system": "attribution_test",
        "site_id": "SITE_001",
        "occurred_at": now,
        "received_at": now,
        "work_order_id": f"WO-ATTR-{_uid()}",
        "asset_id": "P-101",
        "failure_code": "BEARING_WEAR",
        "description": "Attribution worker test work order",
        "priority": "high",
    })
    assert wo_r.status_code == 202

    # Grab any existing brief — we just need a real UUID
    briefs_r = await admin_client.get("/briefs/", params={"unacknowledged_only": False})
    assert briefs_r.status_code == 200
    briefs = briefs_r.json()["briefs"]
    if not briefs:
        import pytest
        pytest.skip("No briefs in DB — cannot test attribution worker")

    brief_id = briefs[0]["brief_id"]

    # Submit incorrect rating — triggers asyncio.create_task(_recheck_brief_sources)
    feedback_r = await admin_client.post(f"/briefs/{brief_id}/feedback", json={
        "rating": "incorrect",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    })
    assert feedback_r.status_code == 200

    # _recheck_brief_sources is fire-and-forget; give it a moment to write to DB
    await asyncio.sleep(1)

    # Verify audit_log has the recheck entry
    log_r = await admin_client.get("/audit-log/", params={
        "entity_type": "brief",
        "entity_id": brief_id,
        "action": "confidence_recheck_queued",
    })
    assert log_r.status_code == 200
    entries = log_r.json()["items"]
    assert len(entries) >= 1, f"No confidence_recheck_queued entry in audit_log for brief {brief_id}"
