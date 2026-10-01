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
