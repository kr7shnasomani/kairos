"""Auth — Task 19: JWT exchange, refresh, /me, role enforcement."""

from tests.conftest import ADMIN_EMAIL, seed_password


async def test_login_admin(anon_client):
    r = await anon_client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": seed_password("admin")})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert "user_id" in body


async def test_login_wrong_password(anon_client):
    r = await anon_client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "WRONG"})
    assert r.status_code == 401


async def test_login_unknown_email(anon_client):
    r = await anon_client.post("/auth/login", json={"email": "nobody@kairos.local", "password": "x"})
    assert r.status_code == 401


async def test_me_returns_user(admin_client):
    r = await admin_client.get("/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert "user_id" in body
    assert "role" in body
    assert body["role"] == "admin"


async def test_me_engineer_role(engineer_client):
    r = await engineer_client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "engineer"


async def test_me_field_role(field_client):
    r = await field_client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "field_worker"


async def test_invalid_token_rejected(anon_client):
    r = await anon_client.get("/assets/", headers={"Authorization": "Bearer this-is-not-a-valid-jwt"})
    assert r.status_code == 401


async def test_refresh_token(anon_client):
    login = await anon_client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": seed_password("admin")})
    assert login.status_code == 200
    refresh_token = login.json()["refresh_token"]

    r = await anon_client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


# ---------------------------------------------------------------------------
# The `demo` role (security review C1): reads everything an admin reads, writes only the Copilot's
# (synthesize, rca-pack, answer feedback), deny-by-default for every other write.
# ---------------------------------------------------------------------------

import pytest


async def test_me_demo_role(demo_client):
    r = await demo_client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "demo"


@pytest.mark.parametrize("path", [
    "/assets/", "/documents/", "/briefs/", "/events/", "/audit-log/", "/compliance/dashboard",
    "/governance/conflicts", "/governance/moc", "/governance/model-gate/history",
    "/elicitation/offboarding", "/annotations/stats",
])
async def test_demo_can_read_what_an_admin_reads(demo_client, path):
    r = await demo_client.get(path)
    assert r.status_code == 200, (path, r.text)


@pytest.mark.parametrize(("path", "body"), [
    ("/events/work-order", {"source_system": "x", "site_id": "SITE_001", "work_order_id": "WO-X", "asset_id": "X",
                            "failure_code": "X", "description": "x"}),
    ("/events/plant-state", {"site_id": "SITE_001", "state": "shutdown"}),
    ("/assets/", {"tag_number": "T", "name": "n", "equipment_class": "PUMP", "criticality": "critical",
                  "site_id": "SITE_001", "facility_id": "F", "eam_source": "t", "confirmed_by_user_id": "d"}),
    ("/annotations/", {"document_id": "D", "entity_text": "t", "entity_type": "T", "is_correct": True}),
    ("/governance/moc/MOC-X/approve", {}),
    ("/briefs/00000000-0000-0000-0000-000000000000/ack", {}),
    ("/briefs/00000000-0000-0000-0000-000000000000/feedback", {"rating": "incorrect"}),
])
async def test_demo_is_refused_writes(demo_client, path, body):
    """Refused by OPA before the handler runs, so none of these touch a store."""
    r = await demo_client.post(path, json=body)
    assert r.status_code == 403, (path, r.text)


async def test_demo_is_refused_document_ingest(demo_client):
    r = await demo_client.post(
        "/documents/ingest",
        files={"file": ("test_demo.txt", b"demo", "text/plain")},
        data={"document_type": "procedure"},
    )
    assert r.status_code == 403
