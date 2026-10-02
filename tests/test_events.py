"""Events — Tasks 13-16, 33: work orders, PTW, shift handover, alarms, tag-out, deviations.

Security pass (2026-09-30 review, status.md): the six ingest routes need the `ingest_event` action
(engineer, reliability, admin, internal key) and are site-scoped, so `field_worker` and `compliance`
get 403 and a non-admin cannot report for another site. `admin_client` is the internal key (role
admin, every site). An inspection's `document_id` must be an `inspection_report` already in the
vault, and a reporter can lower the evidence confidence but never raise it above 0.85. `event_id` is
insert-only: a different payload under a used id is a 409. Acknowledging needs an event on the
caller's site and, for non-staff, a brief addressed to them.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from tests.conftest import OTHER_SITE, uid


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _vault_document(client, document_type):
    """Ingest a throwaway vault document (a `test_` file name, so reads hide it) and return its id."""
    r = await client.post("/documents/ingest", files={
        "file": (f"test_evt_{uid()}.txt", f"events test {document_type} {uid()}".encode(), "text/plain"),
    }, data={
        "document_type": document_type,
        "source_system": "integration_test",
        "authority_level": "4",
    })
    assert r.status_code == 202, f"vault ingest failed: {r.text}"
    return r.json()["document_id"]


def _inspection_payload(asset_id, **over):
    return {
        "event_id": uid(),
        "source_system": "inspection_app",
        "site_id": "SITE_001",
        "occurred_at": _now(),
        "received_at": _now(),
        "asset_id": asset_id,
        "inspection_type": "thickness_measurement",
        "result": "passed",
        "performed_by": "TECH-001",
        "confidence": 0.92,
        **over,
    }


def _work_order_payload(asset_id):
    return {
        "event_id": str(uid()),
        "source_system": "SAP_PM",
        "site_id": "SITE_001",
        "occurred_at": _now(),
        "received_at": _now(),
        "work_order_id": f"WO-{uid()}",
        "asset_id": asset_id,
        "failure_code": "BEARING_WEAR",
        "description": "Bearing temperature elevated above threshold",
        "priority": "high",
    }


# ---------------------------------------------------------------------------
# Work order
# ---------------------------------------------------------------------------

async def test_ingest_work_order(admin_client, shared_asset_id):
    r = await admin_client.post("/events/work-order", json=_work_order_payload(shared_asset_id))
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert "event_id" in body
    assert "stream_entry_id" in body
    assert "brief_task_id" in body


async def test_work_order_deduplication(admin_client):
    # Use a fresh asset so the first post is guaranteed "accepted" (no prior dedup window)
    fresh_asset_id = f"ASSET-DEDUP-{uid()}"
    r_asset = await admin_client.post("/assets/", json={
        "asset_id": fresh_asset_id,
        "tag_number": f"TAG-DEDUP-{uid()}",
        "name": "Dedup Test Asset",
        "equipment_class": "PUMP",
        "criticality": "critical",
        "site_id": "SITE_001",
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "test-runner",
    })
    assert r_asset.status_code == 201

    payload = _work_order_payload(fresh_asset_id)
    r1 = await admin_client.post("/events/work-order", json=payload)
    r2 = await admin_client.post("/events/work-order", json=payload)
    assert r1.status_code == 202
    assert r2.status_code == 202
    # First is accepted, second (same asset+type within window) is deduplicated
    assert r1.json()["status"] == "accepted"
    assert r2.json()["status"] == "deduplicated"


async def test_work_order_recurring_detection(admin_client, shared_asset_id):
    """Two WOs with same failure_code on the same asset → recurring_detected on second."""
    payload1 = _work_order_payload(shared_asset_id)
    payload2 = {**_work_order_payload(shared_asset_id), "event_id": uid(), "work_order_id": f"WO-{uid()}"}
    # Send first, then wait a tick (dedup window is asset+event_type based, not failure_code)
    await admin_client.post("/events/work-order", json=payload1)
    # Use a different asset to bypass dedup but same failure family
    asset2 = f"ASSET-{uid()}"
    r_asset = await admin_client.post("/assets/", json={
        "asset_id": asset2,
        "tag_number": f"TAG-{uid()}",
        "name": "Recurrence Test Asset",
        "equipment_class": "PUMP",
        "criticality": "critical",
        "site_id": "SITE_001",
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "test-runner",
    })
    assert r_asset.status_code == 201
    payload2["asset_id"] = asset2
    r2 = await admin_client.post("/events/work-order", json=payload2)
    assert r2.status_code == 202
    assert "recurring_detected" in r2.json()


async def test_get_event(admin_client):
    # Use a fresh unique asset to avoid dedup window from shared_asset_id
    fresh_asset_id = f"ASSET-EV-{uid()}"
    r_asset = await admin_client.post("/assets/", json={
        "asset_id": fresh_asset_id,
        "tag_number": f"TAG-EV-{uid()}",
        "name": "Event Get Test Asset",
        "equipment_class": "PUMP",
        "criticality": "critical",
        "site_id": "SITE_001",
        "facility_id": "FAC_001",
        "eam_source": "test",
        "confirmed_by_user_id": "test-runner",
    })
    assert r_asset.status_code == 201

    payload = _work_order_payload(fresh_asset_id)
    r = await admin_client.post("/events/work-order", json=payload)
    assert r.status_code == 202
    event_id = r.json()["event_id"]

    r2 = await admin_client.get(f"/events/{event_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["event_id"] == event_id
    assert "correlated_event_ids" in body


async def test_list_events_filters_and_paginates(admin_client, shared_asset_id):
    created = await admin_client.post("/events/work-order", json=_work_order_payload(shared_asset_id))
    assert created.status_code == 202

    response = await admin_client.get("/events/?event_type=work_order_created&limit=1&offset=0")
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert body["total"] >= 1
    assert all(item["event_type"] == "work_order_created" for item in body["items"])


async def test_acknowledge_event(admin_client, shared_asset_id):
    payload = _work_order_payload(shared_asset_id)
    r = await admin_client.post("/events/work-order", json=payload)
    event_id = r.json()["event_id"]

    r2 = await admin_client.post(f"/events/{event_id}/ack", json={
        "user_id": "test-runner",
        "role": "engineer",
        "acknowledged_at": _now(),
    })
    assert r2.status_code == 200
    assert r2.json()["status"] == "acknowledged"
    # Who acknowledged comes from the token, never from the body's `user_id`.
    assert r2.json()["user_id"] == "service-kairos-connector"


async def test_acknowledge_event_is_idempotent_per_user(admin_client, fresh_asset_id):
    event_id = (await admin_client.post("/events/work-order", json=_work_order_payload(fresh_asset_id))).json()["event_id"]
    first = await admin_client.post(f"/events/{event_id}/ack", json={})
    second = await admin_client.post(f"/events/{event_id}/ack", json={})
    assert first.status_code == 200 and "repeat" not in first.json()
    assert second.status_code == 200
    assert second.json()["repeat"] is True


async def test_acknowledge_unknown_event_is_404(field_client):
    r = await field_client.post(f"/events/{uuid4()}/ack", json={})
    assert r.status_code == 404


async def test_acknowledge_requires_a_stake_in_the_event(admin_client, field_client, fresh_asset_id):
    """A non-staff caller who is not the recipient of a brief the event triggered gets 403."""
    # An alarm triggers no brief of its own, so nobody (the site-wide address included) is a recipient.
    created = await admin_client.post("/events/alarm", json=_ingest_bodies(fresh_asset_id)["/events/alarm"])
    assert created.status_code == 202
    r = await field_client.post(f"/events/{created.json()['event_id']}/ack", json={})
    assert r.status_code == 403


async def test_event_on_another_site_is_404_to_a_non_admin(admin_client, engineer_client, shared_asset_id):
    """get_event and ack answer 404 (not 403) for another site's event, so its existence is not disclosed."""
    alarm_id = f"ALM-{uid()}"
    created = await admin_client.post("/events/alarm", json={
        "event_id": uid(),
        "source_system": "DCS",
        "site_id": OTHER_SITE,
        "occurred_at": _now(),
        "received_at": _now(),
        "alarm_id": alarm_id,
        "asset_id": shared_asset_id,
        "alarm_tag": f"{shared_asset_id}-HH",
        "alarm_description": "Other-site alarm",
        "severity": "high",
        "acknowledged_by": "OPS-001",
    })
    assert created.status_code == 202
    event_id = created.json()["event_id"]

    assert (await admin_client.get(f"/events/{event_id}")).status_code == 200  # admin sees every site
    assert (await engineer_client.get(f"/events/{event_id}")).status_code == 404
    assert (await engineer_client.post(f"/events/{event_id}/ack", json={})).status_code == 404


async def test_event_feed_is_pinned_to_the_callers_site(engineer_client):
    r = await engineer_client.get("/events/", params={"limit": 50})
    assert r.status_code == 200
    assert all(item["site_id"] == "SITE_001" for item in r.json()["items"])


# ---------------------------------------------------------------------------
# Who may ingest: `ingest_event` is staff (and the connector) only, and site-scoped
# ---------------------------------------------------------------------------

def _ingest_bodies(asset_id):
    base = {"source_system": "test", "site_id": "SITE_001", "occurred_at": _now(), "received_at": _now()}
    return {
        "/events/work-order": {**base, "event_id": uid(), "work_order_id": f"WO-{uid()}", "asset_id": asset_id,
                               "failure_code": "BEARING_WEAR", "description": "x", "priority": "high"},
        "/events/ptw": {**base, "event_id": uid(), "ptw_id": f"PTW-{uid()}", "work_area": "Bay", "asset_ids": [asset_id],
                        "ptw_type": "isolation", "issuing_engineer_id": "ENG-001"},
        "/events/shift-handover": {**base, "event_id": uid(), "outgoing_shift_lead_id": "OPS-OUT",
                                   "incoming_shift_lead_id": "OPS-IN", "handover_time": _now()},
        "/events/alarm": {**base, "event_id": uid(), "alarm_id": f"ALM-{uid()}", "asset_id": asset_id,
                          "alarm_tag": f"{asset_id}-HH", "alarm_description": "x", "severity": "high",
                          "acknowledged_by": "OPS-001"},
        "/events/tag-out": {**base, "event_id": uid(), "asset_id": asset_id, "tag_out_reason": "x",
                            "performed_by": "TECH-001"},
        "/events/inspection-complete": _inspection_payload(asset_id),
        "/events/plant-state": {"site_id": "SITE_001", "state": "normal"},
    }


@pytest.mark.parametrize("route", sorted(_ingest_bodies("X")))
async def test_ingest_routes_refuse_non_staff_roles(route, field_client, compliance_client, shared_asset_id):
    """field_worker and compliance are refused before anything is written."""
    for client in (field_client, compliance_client):
        r = await client.post(route, json=_ingest_bodies(shared_asset_id)[route])
        assert r.status_code == 403, (route, r.text)


async def test_engineer_can_ingest_work_order(engineer_client, fresh_asset_id):
    r = await engineer_client.post("/events/work-order", json=_work_order_payload(fresh_asset_id))
    assert r.status_code == 202
    assert r.json()["status"] == "accepted"


async def test_reliability_can_ingest_shift_handover(reliability_client):
    r = await reliability_client.post("/events/shift-handover", json=_ingest_bodies("X")["/events/shift-handover"])
    assert r.status_code == 202
    assert r.json()["status"] == "accepted"


async def test_engineer_cannot_report_for_another_site(engineer_client, shared_asset_id):
    r = await engineer_client.post("/events/work-order", json={**_work_order_payload(shared_asset_id), "site_id": OTHER_SITE})
    assert r.status_code == 403


async def test_engineer_cannot_ingest_for_another_sites_asset(engineer_client, other_site_asset_id):
    """An asset on another site is reported as not registered, the same 404 as an unknown tag."""
    r = await engineer_client.post("/events/work-order", json=_work_order_payload(other_site_asset_id))
    assert r.status_code == 404


async def test_event_id_is_insert_only(admin_client, fresh_asset_id):
    """Reusing an event_id with a different payload is a 409 and leaves the stored event untouched."""
    first = _work_order_payload(fresh_asset_id)
    assert (await admin_client.post("/events/work-order", json=first)).status_code == 202

    # A different work order, so the dedup window does not intercept it before the insert.
    clash = {**first, "work_order_id": f"WO-{uid()}", "description": "Overwrite attempt"}
    r = await admin_client.post("/events/work-order", json=clash)
    assert r.status_code == 409

    stored = (await admin_client.get(f"/events/{first['event_id']}")).json()
    assert stored["payload"]["description"] == first["description"]


# ---------------------------------------------------------------------------
# PTW
# ---------------------------------------------------------------------------

async def test_ingest_ptw(admin_client, shared_asset_id):
    r = await admin_client.post("/events/ptw", json={
        "event_id": uid(),
        "source_system": "PTW_system",
        "site_id": "SITE_001",
        "occurred_at": _now(),
        "received_at": _now(),
        "ptw_id": f"PTW-{uid()}",
        "work_area": "Pump Hall A",
        "asset_ids": [shared_asset_id],
        "ptw_type": "isolation",
        "issuing_engineer_id": "ENG-001",
    })
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert body["priority"] == "critical"
    assert "brief_id" in body


# ---------------------------------------------------------------------------
# Shift handover
# ---------------------------------------------------------------------------

async def test_ingest_shift_handover(admin_client):
    r = await admin_client.post("/events/shift-handover", json={
        "event_id": uid(),
        "source_system": "DCS",
        "site_id": "SITE_001",
        "occurred_at": _now(),
        "received_at": _now(),
        "outgoing_shift_lead_id": "OPS-OUT-001",
        "incoming_shift_lead_id": "OPS-IN-001",
        "handover_time": _now(),
    })
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert "brief_task_id" in body


# ---------------------------------------------------------------------------
# Alarm
# ---------------------------------------------------------------------------

async def test_ingest_alarm(admin_client, shared_asset_id):
    r = await admin_client.post("/events/alarm", json={
        "event_id": uid(),
        "source_system": "DCS",
        "site_id": "SITE_001",
        "occurred_at": _now(),
        "received_at": _now(),
        "alarm_id": f"ALM-{uid()}",
        "asset_id": shared_asset_id,
        "alarm_tag": f"{shared_asset_id}-HH",
        "alarm_description": "High vibration on pump shaft",
        "severity": "high",
        "acknowledged_by": "OPS-001",
    })
    assert r.status_code == 202
    assert r.json()["status"] == "accepted"


# ---------------------------------------------------------------------------
# Tag-out (Task 33)
# ---------------------------------------------------------------------------

async def test_ingest_tag_out(admin_client, shared_asset_id):
    r = await admin_client.post("/events/tag-out", json={
        "event_id": uid(),
        "source_system": "LOTO_system",
        "site_id": "SITE_001",
        "occurred_at": _now(),
        "received_at": _now(),
        "asset_id": shared_asset_id,
        "tag_out_reason": "Planned maintenance — bearing replacement",
        "performed_by": "TECH-001",
    })
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert "stream_entry_id" in body


async def test_tag_out_deduplication(admin_client, shared_asset_id):
    payload = {
        "event_id": uid(),
        "source_system": "LOTO_system",
        "site_id": "SITE_001",
        "occurred_at": _now(),
        "received_at": _now(),
        "asset_id": shared_asset_id,
        "tag_out_reason": "Dup test",
        "performed_by": "TECH-001",
    }
    r1 = await admin_client.post("/events/tag-out", json=payload)
    r2 = await admin_client.post("/events/tag-out", json=payload)
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r2.json()["status"] == "deduplicated"


# ---------------------------------------------------------------------------
# Inspection complete
# ---------------------------------------------------------------------------

async def test_ingest_inspection_complete_passed(admin_client, fresh_asset_id):
    r = await admin_client.post("/events/inspection-complete", json={
        "event_id": uid(),
        "source_system": "inspection_app",
        "site_id": "SITE_001",
        "occurred_at": _now(),
        "received_at": _now(),
        "asset_id": fresh_asset_id,
        "inspection_type": "vibration_analysis",
        "result": "passed",
        "performed_by": "TECH-001",
        "confidence": 0.95,
    })
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    # High confidence → no quarantine
    assert body["quarantine_item_id"] is None


async def test_ingest_inspection_complete_low_confidence_quarantined(admin_client, fresh_asset_id):
    r = await admin_client.post("/events/inspection-complete", json={
        "event_id": uid(),
        "source_system": "inspection_app",
        "site_id": "SITE_001",
        "occurred_at": _now(),
        "received_at": _now(),
        "asset_id": fresh_asset_id,
        "inspection_type": "visual",
        "result": "conditional",
        "performed_by": "TECH-002",
        "confidence": 0.5,
    })
    assert r.status_code == 202
    body = r.json()
    # confidence < 0.7 → goes to quarantine
    assert body["quarantine_item_id"] is not None


# ---------------------------------------------------------------------------
# Deviation flag
# ---------------------------------------------------------------------------

async def test_deviation_flag_and_resolve(admin_client, shared_asset_id):
    r = await admin_client.post("/events/deviation-flag", json={
        "asset_id": shared_asset_id,
        "description": "P&ID shows valve V-101 but physical is missing",
        "affected_topology_path": "loop/feed/V-101",
    })
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    item_id = body["item_id"]

    r2 = await admin_client.post(f"/events/deviation-flag/{item_id}/resolve", json={
        "resolution": "disputed",
        "moc_warranted": False,
        "notes": "Confirmed as drawing error, not physical deviation",
    })
    assert r2.status_code == 200
    assert r2.json()["resolution"] == "disputed"


async def test_deviation_flag_resolve_invalid_resolution(admin_client, shared_asset_id):
    r = await admin_client.post("/events/deviation-flag", json={
        "asset_id": shared_asset_id,
        "description": "Test deviation",
    })
    item_id = r.json()["item_id"]

    r2 = await admin_client.post(f"/events/deviation-flag/{item_id}/resolve", json={
        "resolution": "not_a_real_resolution",
    })
    assert r2.status_code == 400


async def test_deviation_flag_resolve_promoted(admin_client, shared_asset_id):
    """resolution=promoted → 200, resolution field is promoted, briefs_unfrozen in response."""
    r = await admin_client.post("/events/deviation-flag", json={
        "asset_id": shared_asset_id,
        "description": "Topology confirmed changed — bypass valve installed",
    })
    assert r.status_code == 202
    item_id = r.json()["item_id"]

    r2 = await admin_client.post(f"/events/deviation-flag/{item_id}/resolve", json={
        "resolution": "promoted",
        "moc_warranted": False,
        "notes": "Physical change verified by engineer",
    })
    assert r2.status_code == 200
    body = r2.json()
    assert body["resolution"] == "promoted"
    assert "briefs_unfrozen" in body
    assert body["moc_id"] is None


async def test_deviation_flag_resolve_moc_warranted(admin_client, shared_asset_id):
    """moc_warranted=True → 200 and moc_id is returned in response."""
    r = await admin_client.post("/events/deviation-flag", json={
        "asset_id": shared_asset_id,
        "description": "Topology change requiring management of change sign-off",
    })
    assert r.status_code == 202
    item_id = r.json()["item_id"]

    r2 = await admin_client.post(f"/events/deviation-flag/{item_id}/resolve", json={
        "resolution": "promoted",
        "moc_warranted": True,
        "notes": "Confirmed — new bypass loop added to P&ID",
    })
    assert r2.status_code == 200
    body = r2.json()
    assert body["resolution"] == "promoted"
    assert body["moc_id"] is not None
    assert body["moc_id"].startswith("MOC-")


async def test_ingest_inspection_with_document_id(admin_client, fresh_asset_id):
    """Inspection with an inspection_report document_id → INSPECTION_RECORD Neo4j edge → edge_id not null."""
    doc_id = await _vault_document(admin_client, "inspection_report")
    r = await admin_client.post("/events/inspection-complete", json=_inspection_payload(fresh_asset_id, document_id=doc_id))
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "accepted"
    assert body["edge_id"] is not None  # non-null only when document_id provided


async def test_inspection_document_must_exist_in_the_vault(admin_client, fresh_asset_id):
    """The edge is compliance evidence, so it cannot point at an id the caller made up."""
    r = await admin_client.post(
        "/events/inspection-complete",
        json=_inspection_payload(fresh_asset_id, document_id=f"DOC-INSP-{uid()}"),
    )
    assert r.status_code == 422


async def test_inspection_document_must_be_an_inspection_report(admin_client, fresh_asset_id):
    doc_id = await _vault_document(admin_client, "procedure")
    r = await admin_client.post("/events/inspection-complete", json=_inspection_payload(fresh_asset_id, document_id=doc_id))
    assert r.status_code == 422


async def _evidence_confidence(admin_client, asset_id, edge_id):
    # The throwaway document is a `test_` file, so the knowledge read hides it unless asked.
    r = await admin_client.get(f"/assets/{asset_id}/knowledge", params={"include_test_data": True})
    assert r.status_code == 200
    edges = [f["edge"] for f in r.json()["facts"] if f["edge"].get("edge_id") == edge_id]
    assert len(edges) == 1, f"edge {edge_id} not found on {asset_id}"
    return float(edges[0]["confidence"])


async def test_inspection_evidence_confidence_cannot_be_raised_by_the_client(admin_client, fresh_asset_id):
    doc_id = await _vault_document(admin_client, "inspection_report")
    r = await admin_client.post("/events/inspection-complete", json=_inspection_payload(
        fresh_asset_id, document_id=doc_id, inspection_type="ceiling_check", confidence=0.99,
    ))
    assert r.status_code == 202
    assert await _evidence_confidence(admin_client, fresh_asset_id, r.json()["edge_id"]) <= 0.85


async def test_inspection_evidence_confidence_can_be_lowered_by_the_client(admin_client, fresh_asset_id):
    doc_id = await _vault_document(admin_client, "inspection_report")
    r = await admin_client.post("/events/inspection-complete", json=_inspection_payload(
        fresh_asset_id, document_id=doc_id, inspection_type="floor_check", confidence=0.75,
    ))
    assert r.status_code == 202
    assert await _evidence_confidence(admin_client, fresh_asset_id, r.json()["edge_id"]) == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Plant state
# ---------------------------------------------------------------------------

async def test_set_and_get_plant_state(admin_client):
    r = await admin_client.post("/events/plant-state", json={
        "site_id": "SITE_001",
        "state": "normal",
    })
    assert r.status_code == 202
    assert r.json()["state"] == "normal"

    r2 = await admin_client.get("/events/plant-state/SITE_001")
    assert r2.status_code == 200
    assert "state" in r2.json()


async def test_field_worker_cannot_set_plant_state(field_client):
    r = await field_client.post("/events/plant-state", json={"site_id": "SITE_001", "state": "shutdown"})
    assert r.status_code == 403


async def test_engineer_cannot_set_another_sites_plant_state(engineer_client):
    r = await engineer_client.post("/events/plant-state", json={"site_id": OTHER_SITE, "state": "shutdown"})
    assert r.status_code == 403


async def test_plant_state_read_is_pinned_to_the_callers_site(engineer_client):
    own = await engineer_client.get("/events/plant-state/SITE_001")
    other = await engineer_client.get(f"/events/plant-state/{OTHER_SITE}")
    assert own.status_code == 200
    assert other.status_code == 403
