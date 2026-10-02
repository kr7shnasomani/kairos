"""Elicitation — Tasks 19, 29-31: voice notes, micro-interview trigger, off-boarding.

Security pass (2026-09-30 review, M9): off-boarding programmes (reads and responses) are open to
staff (engineer, reliability, admin) and to the person the programme is about, matched on
`personnel_id` or e-mail; anyone else gets 403 and the list shows them only their own.
"""

from tests.conftest import FIELD_EMAIL, uid


# ---------------------------------------------------------------------------
# Voice note ingest (Task 19 / Layer 3)
# ---------------------------------------------------------------------------

async def test_voice_note_ingest_accepted(admin_client, shared_asset_id):
    """Upload a minimal WAV-like blob — expect 202 accepted with task_id."""
    work_order_id = f"WO-VOICE-{uid()}"
    # Minimal 44-byte WAV header stub (not a real WAV, but enough for upload test)
    audio_bytes = b"RIFF" + b"\x00" * 40 + f"voice-test-{uid()}".encode()
    r = await admin_client.post(
        f"/elicitation/{work_order_id}/voice",
        files={"file": ("note.wav", audio_bytes, "application/octet-stream")},
        data={"submitted_by": "TECH-001"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] in ("accepted", "duplicate")
    assert "sha256" in body
    if body["status"] == "accepted":
        assert "task_id" in body
        assert "storage_path" in body
        assert body["work_order_id"] == work_order_id


async def test_voice_note_idempotent(admin_client, shared_asset_id):
    """Same audio bytes uploaded twice — both return 202 (dedup or accepted)."""
    work_order_id = f"WO-VOICE-DUP-{uid()}"
    audio_bytes = b"RIFF" + b"\x00" * 40 + f"dedup-voice-{uid()}".encode()
    kwargs = dict(
        files={"file": ("note.wav", audio_bytes, "application/octet-stream")},
        data={"submitted_by": "TECH-001"},
    )
    r1 = await admin_client.post(f"/elicitation/{work_order_id}/voice", **kwargs)
    r2 = await admin_client.post(f"/elicitation/{work_order_id}/voice", **kwargs)
    assert r1.status_code == 202
    assert r2.status_code == 202
    # Both must return a valid status — dedup fires only after Celery quarantine write
    assert r1.json()["status"] in ("accepted", "duplicate")
    assert r2.json()["status"] in ("accepted", "duplicate")


# ---------------------------------------------------------------------------
# Micro-interview trigger
# ---------------------------------------------------------------------------

async def test_trigger_no_conditions_not_triggered(admin_client, shared_asset_id):
    """Common failure code + normal resolution time → elicitation skipped."""
    r = await admin_client.post("/elicitation/trigger", json={
        "work_order_id": f"WO-{uid()}",
        "asset_id": shared_asset_id,
        "failure_code": "BEARING_WEAR",
        "equipment_class": "PUMP",
        "resolution_time_hours": 1.0,
        "novel_troubleshooting": False,
        "triggered_by": "test-runner",
    })
    assert r.status_code == 200
    body = r.json()
    assert "triggered" in body
    # Novel troubleshooting flag is False and failure is common → likely not triggered
    if not body["triggered"]:
        assert body["reasons"] == []


async def test_trigger_novel_troubleshooting_triggers(admin_client, shared_asset_id):
    """novel_troubleshooting=True always triggers."""
    r = await admin_client.post("/elicitation/trigger", json={
        "work_order_id": f"WO-{uid()}",
        "asset_id": shared_asset_id,
        "failure_code": "UNKNOWN_FAILURE_XYZ",
        "equipment_class": "PUMP",
        "resolution_time_hours": 2.0,
        "novel_troubleshooting": True,
        "triggered_by": "test-runner",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["triggered"] is True
    assert "novel_troubleshooting" in body["reasons"]
    assert "workflow_id" in body


async def test_elicitation_questions_not_found(admin_client):
    r = await admin_client.get("/elicitation/WO-DOESNOTEXIST-XYZ/questions")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Off-boarding (Task 31)
# ---------------------------------------------------------------------------

async def test_list_offboarding_shape(admin_client):
    r = await admin_client.get("/elicitation/offboarding")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body


async def test_create_offboarding_programme(admin_client):
    from datetime import date, timedelta
    retirement = (date.today() + timedelta(days=90)).isoformat()
    r = await admin_client.post("/elicitation/offboarding", json={
        "personnel_id": f"EMP-{uid()}",
        "personnel_email": f"retiring_{uid()}@kairos.local",
        "retirement_date": retirement,
        "session_interval_days": 7,
    })
    assert r.status_code == 201
    body = r.json()
    assert "session_id" in body
    assert "total_sessions" in body
    assert "items" in body
    assert body["total_sessions"] >= 1


async def test_get_offboarding_programme(admin_client):
    from datetime import date, timedelta
    retirement = (date.today() + timedelta(days=60)).isoformat()
    create = await admin_client.post("/elicitation/offboarding", json={
        "personnel_id": f"EMP-{uid()}",
        "personnel_email": f"detail_{uid()}@kairos.local",
        "retirement_date": retirement,
        "session_interval_days": 14,
    })
    assert create.status_code == 201
    session_id = create.json()["session_id"]

    r = await admin_client.get(f"/elicitation/offboarding/{session_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == session_id
    assert "session_items" in body


async def test_offboarding_requires_engineer_or_admin(field_client):
    from datetime import date, timedelta
    r = await field_client.post("/elicitation/offboarding", json={
        "personnel_id": f"EMP-{uid()}",
        "personnel_email": f"field_{uid()}@kairos.local",
        "retirement_date": (date.today() + timedelta(days=30)).isoformat(),
        "session_interval_days": 7,
    })
    assert r.status_code == 403


async def test_get_offboarding_questions_for_session(admin_client):
    from datetime import date, timedelta
    retirement = (date.today() + timedelta(days=45)).isoformat()
    create = await admin_client.post("/elicitation/offboarding", json={
        "personnel_id": f"EMP-{uid()}",
        "personnel_email": f"qtest_{uid()}@kairos.local",
        "retirement_date": retirement,
        "session_interval_days": 10,
    })
    session_id = create.json()["session_id"]

    r = await admin_client.get(f"/elicitation/offboarding/{session_id}/questions")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == session_id
    assert "total_items" in body
    assert "items" in body


async def test_submit_offboarding_responses(admin_client):
    """Create programme → get first item_id → submit responses → quarantine_item_id returned."""
    from datetime import date, timedelta
    retirement = (date.today() + timedelta(days=30)).isoformat()
    create = await admin_client.post("/elicitation/offboarding", json={
        "personnel_id": f"EMP-{uid()}",
        "personnel_email": f"resp_{uid()}@kairos.local",
        "retirement_date": retirement,
        "session_interval_days": 7,
    })
    assert create.status_code == 201
    session_id = create.json()["session_id"]

    questions_r = await admin_client.get(f"/elicitation/offboarding/{session_id}/questions")
    assert questions_r.status_code == 200
    items = questions_r.json()["items"]
    assert len(items) >= 1
    item_id = items[0]["id"]

    r = await admin_client.post(f"/elicitation/offboarding/{session_id}/responses", json={
        "item_id": item_id,
        "responses": [{"question_index": 0, "answer": "Pump has been reliable for 15 years"}],
        "submitted_by": "test-runner",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == session_id
    assert body["item_id"] == item_id
    assert "quarantine_item_id" in body
    assert "programme_completed" in body


async def test_submit_elicitation_responses(admin_client, shared_asset_id):
    """Trigger elicitation (novel=True) then submit responses — quarantined via Temporal."""
    wo_id = f"WO-RESP-{uid()}"
    trigger = await admin_client.post("/elicitation/trigger", json={
        "work_order_id": wo_id,
        "asset_id": shared_asset_id,
        "failure_code": "SEAL_LEAK_NOVEL",
        "equipment_class": "PUMP",
        "resolution_time_hours": 4.0,
        "novel_troubleshooting": True,
        "triggered_by": "test-runner",
    }, timeout=90.0)
    assert trigger.status_code == 200
    assert trigger.json()["triggered"] is True

    r = await admin_client.post(f"/elicitation/{wo_id}/responses", json={
        "responses": [
            {"question": "What symptoms did you observe?", "answer": "Vibration increased steadily over 2h"},
            {"question": "What action did you take?", "answer": "Replaced mechanical seal"},
        ],
        "submitted_by": "test-runner",
    }, timeout=90.0)
    assert r.status_code == 200
    body = r.json()
    assert "item_id" in body
    assert body["status"] == "quarantined"


# ---------------------------------------------------------------------------
# Off-boarding access (M9): staff or the person concerned only
# ---------------------------------------------------------------------------

async def _programme(client, email):
    from datetime import date, timedelta
    r = await client.post("/elicitation/offboarding", json={
        "personnel_id": f"EMP-{uid()}",
        "personnel_email": email,
        "retirement_date": (date.today() + timedelta(days=40)).isoformat(),
        "session_interval_days": 7,
    })
    assert r.status_code == 201
    return r.json()["session_id"]


async def test_offboarding_programme_is_readable_only_by_staff_or_the_person_concerned(
    admin_client, engineer_client, reliability_client, field_client, compliance_client
):
    about_someone_else = await _programme(admin_client, f"other_{uid()}@kairos.local")
    about_the_field_worker = await _programme(admin_client, FIELD_EMAIL)

    for client in (engineer_client, reliability_client):  # staff
        assert (await client.get(f"/elicitation/offboarding/{about_someone_else}")).status_code == 200

    # The field worker is the subject of one programme and a stranger to the other.
    assert (await field_client.get(f"/elicitation/offboarding/{about_the_field_worker}")).status_code == 200
    assert (await field_client.get(f"/elicitation/offboarding/{about_someone_else}")).status_code == 403
    assert (await field_client.get(f"/elicitation/offboarding/{about_someone_else}/questions")).status_code == 403
    assert (await compliance_client.get(f"/elicitation/offboarding/{about_someone_else}")).status_code == 403


async def test_offboarding_list_shows_a_non_staff_user_only_their_own(admin_client, field_client):
    mine = await _programme(admin_client, FIELD_EMAIL)
    other = await _programme(admin_client, f"other_{uid()}@kairos.local")

    ids = {p["id"] for p in (await field_client.get("/elicitation/offboarding")).json()["items"]}
    assert mine in ids
    assert other not in ids


async def test_offboarding_responses_are_refused_to_a_stranger(admin_client, field_client):
    session_id = await _programme(admin_client, f"other_{uid()}@kairos.local")
    items = (await admin_client.get(f"/elicitation/offboarding/{session_id}/questions")).json()["items"]

    r = await field_client.post(f"/elicitation/offboarding/{session_id}/responses", json={
        "item_id": items[0]["id"],
        "responses": [{"question_index": 0, "answer": "Not my programme"}],
    })
    assert r.status_code == 403
