"""Security review, group AUTH/ROLES/SECRETS — pure logic, no stack, secrets or network.

Covers H1 (role from app_metadata), H7 boot guard, L1 logout, L4 constant-time key compare,
L5 APP_ENV fails closed, L6 generic auth errors, L7 /health/detailed gated, and the seeded-password
move into the environment.
"""

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials

from api import dependencies as deps
from api.config import Settings, get_settings
from api.dependencies import resolve_token
from api.routers import auth as auth_router
from api.routers import health as health_router
from scripts import migrate_roles_to_app_metadata as migrate
from scripts import seed_users

PROD_SAFE = dict(
    _env_file=None,
    APP_DEBUG=False,
    APP_SECRET_KEY="prod-secret",
    INTERNAL_API_KEY="prod-internal-key",
    NEO4J_PASSWORD="prod-neo4j-pw",
    SUPABASE_SERVICE_ROLE_KEY="svc",
    SUPABASE_JWT_SECRET="jwt",
    MOC_WEBHOOK_SECRET="hook",
)


def _settings(**over) -> Settings:
    return Settings(_env_file=None, INTERNAL_API_KEY="internal-test-key", AUTH_CACHE_TTL_SECONDS=0, **over)


# =============================================================================
# H1: authorization data comes from app_metadata, never user_metadata
# =============================================================================


def _fake_supabase(user):
    auth = SimpleNamespace(get_user=lambda token: SimpleNamespace(user=user))
    return lambda *a, **k: SimpleNamespace(auth=auth)


def _user(app=None, meta=None):
    return SimpleNamespace(id="u-1", email="u@kairos.local", app_metadata=app, user_metadata=meta)


def test_role_and_site_come_from_app_metadata(monkeypatch):
    monkeypatch.setattr(deps, "create_client", _fake_supabase(_user({"role": "engineer", "site_id": "SITE_9"})))
    out = asyncio.run(resolve_token("tok", _settings()))
    assert (out["role"], out["site_id"]) == ("engineer", "SITE_9")


def test_self_edited_user_metadata_cannot_grant_a_role(monkeypatch):
    # The exploit: PUT /auth/v1/user {"data": {"role": "admin", "site_id": "X"}} as yourself.
    monkeypatch.setattr(
        deps, "create_client", _fake_supabase(_user(app={}, meta={"role": "admin", "site_id": "SITE_X"}))
    )
    out = asyncio.run(resolve_token("tok", _settings()))
    assert (out["role"], out["site_id"]) == ("field_worker", "")


def test_user_metadata_cannot_override_app_metadata(monkeypatch):
    monkeypatch.setattr(
        deps,
        "create_client",
        _fake_supabase(_user(app={"role": "compliance", "site_id": "S1"}, meta={"role": "admin"})),
    )
    assert asyncio.run(resolve_token("tok", _settings()))["role"] == "compliance"


def test_missing_app_metadata_is_least_privilege(monkeypatch):
    monkeypatch.setattr(deps, "create_client", _fake_supabase(_user(app=None, meta=None)))
    assert asyncio.run(resolve_token("tok", _settings()))["role"] == "field_worker"


# =============================================================================
# H1: migration script is additive and dry-run by default
# =============================================================================


def test_plan_copies_missing_keys_without_overwriting():
    u = _user(app={"provider": "email", "role": "engineer"}, meta={"role": "admin", "site_id": "SITE_001"})
    assert migrate.plan_for(u) == {"provider": "email", "role": "engineer", "site_id": "SITE_001"}


def test_plan_skips_unknown_roles_and_noops():
    assert migrate.plan_for(_user(app={}, meta={"role": "superuser"})) is None
    assert migrate.plan_for(_user(app={"role": "admin", "site_id": "S"}, meta={"role": "admin"})) is None
    assert migrate.plan_for(_user(app=None, meta=None)) is None


class _FakeAdmin:
    def __init__(self, users):
        self.users, self.updates = users, []

    def list_users(self, page=None, per_page=None):
        return self.users if page == 1 else []

    def update_user_by_id(self, uid, attrs):
        self.updates.append((uid, attrs))


def _run_migration(monkeypatch, argv):
    admin = _FakeAdmin([_user(app={}, meta={"role": "reliability", "site_id": "SITE_001", "name": "R"})])
    monkeypatch.setattr(migrate, "create_client", lambda *a, **k: SimpleNamespace(auth=SimpleNamespace(admin=admin)))
    assert migrate.main(argv) == 0
    return admin


def test_migration_dry_run_writes_nothing(monkeypatch):
    assert _run_migration(monkeypatch, []).updates == []


def test_migration_apply_writes_app_metadata_only(monkeypatch):
    updates = _run_migration(monkeypatch, ["--apply"]).updates
    assert updates == [("u-1", {"app_metadata": {"role": "reliability", "site_id": "SITE_001", "name": "R"}})]


# =============================================================================
# L4: constant-time internal key compare
# =============================================================================


def test_internal_key_uses_compare_digest(monkeypatch):
    calls = []
    real = deps.hmac.compare_digest
    monkeypatch.setattr(deps.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    assert asyncio.run(resolve_token("internal-test-key", _settings()))["role"] == "admin"
    assert calls


def test_internal_key_mismatch_and_non_ascii_do_not_authenticate(monkeypatch):
    def _no_supabase(*a, **k):
        raise RuntimeError("rejected")

    monkeypatch.setattr(deps, "create_client", _no_supabase)
    deps._auth_cache.clear()
    for token in ("internal-test-kex", "internal-test-ke", "ключ-ключ", ""):
        assert asyncio.run(resolve_token(token, _settings())) is None


# =============================================================================
# L5: only an exact (normalised) "development" enables dev conveniences
# =============================================================================


@pytest.mark.parametrize("raw", ["Production", " PRODUCTION ", "production"])
def test_app_env_is_normalised(raw):
    assert Settings(APP_ENV=raw, **PROD_SAFE).APP_ENV == "production"


@pytest.mark.parametrize("raw", ["Development", " development "])
def test_development_spelling_is_normalised(raw):
    s = Settings(_env_file=None, APP_ENV=raw, APP_DEBUG=True)
    assert s.is_development and s.dev_bypass_allowed


@pytest.mark.parametrize("env", ["prod", "staging", "dev", "test", "devel", ""])
def test_unrecognised_env_is_not_development(env):
    s = Settings(APP_ENV=env, **PROD_SAFE)
    assert not s.is_development and not s.dev_bypass_allowed


@pytest.mark.parametrize("env", ["prod", "staging", "Prod", "test"])
def test_unrecognised_env_still_refuses_default_admin_key(env):
    with pytest.raises(ValueError, match="INTERNAL_API_KEY"):
        Settings(_env_file=None, APP_ENV=env, APP_DEBUG=False)


def test_rate_limit_is_off_only_in_development():
    import api.main as main

    src = Path(main.__file__).read_text()
    assert "0 if settings.is_development else settings.RATE_LIMIT_PER_MINUTE" in src


# =============================================================================
# H7 (config part): MoC webhook secret is part of the production boot guard
# =============================================================================


def test_production_refuses_without_moc_webhook_secret():
    bad = {**PROD_SAFE, "MOC_WEBHOOK_SECRET": None}
    with pytest.raises(ValueError, match="MOC_WEBHOOK_SECRET"):
        Settings(APP_ENV="production", **bad)
    with pytest.raises(ValueError, match="MOC_WEBHOOK_SECRET"):
        Settings(APP_ENV="production", **{**PROD_SAFE, "MOC_WEBHOOK_SECRET": ""})


def test_development_does_not_need_moc_webhook_secret():
    Settings(_env_file=None, APP_ENV="development", MOC_WEBHOOK_SECRET=None)


# =============================================================================
# L6: generic login/refresh errors; the upstream detail is logged, not returned
# =============================================================================


def _raising_client(message):
    def _boom(*a, **k):
        raise RuntimeError(message)

    auth = SimpleNamespace(sign_in_with_password=_boom, refresh_session=_boom)
    return lambda *a, **k: SimpleNamespace(auth=auth)


def test_login_does_not_echo_upstream_error(monkeypatch):
    monkeypatch.setattr(auth_router, "create_client", _raising_client("Invalid login credentials: no such user"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_router.login(auth_router.LoginRequest(email="a@b.c", password="x"), _settings()))
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid credentials"


def test_refresh_does_not_echo_upstream_error(monkeypatch):
    monkeypatch.setattr(auth_router, "create_client", _raising_client("refresh_token_not_found"))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_router.refresh(auth_router.RefreshRequest(refresh_token="r"), _settings()))
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid refresh token"


def test_supabase_fk_violation_does_not_echo_row_details():
    from postgrest.exceptions import APIError

    import api.main as main

    app = main.create_app()
    handler = app.exception_handlers[APIError]
    exc = APIError({"code": "23503", "details": 'Key (secret_col)=(secret) is not present in table "t"', "message": "m"})
    resp = asyncio.run(handler(SimpleNamespace(url="http://x/y"), exc))
    assert resp.status_code == 422
    assert b"secret" not in resp.body


# =============================================================================
# L1: POST /auth/logout revokes the session server-side, best effort
# =============================================================================


class _Sb:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail
        self.auth = SimpleNamespace(admin=SimpleNamespace(sign_out=self._sign_out))

    def _sign_out(self, token, scope):
        self.calls.append((token, scope))
        if self.fail:
            raise RuntimeError("session already gone")


def _creds(token="tok-1"):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_logout_revokes_session_and_drops_cache():
    sb = _Sb()
    deps._auth_cache_put("tok-1", {"user_id": "u"}, ttl=60)
    out = asyncio.run(auth_router.logout(sb, _creds()))
    assert out == {"status": "ok"}
    assert sb.calls == [("tok-1", "local")]
    assert deps._auth_cache_get("tok-1") is None


def test_logout_is_ok_even_when_revoke_fails():
    assert asyncio.run(auth_router.logout(_Sb(fail=True), _creds())) == {"status": "ok"}


def test_logout_requires_a_token():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_router.logout(_Sb(), None))
    assert exc.value.status_code == 401


# =============================================================================
# L7: /health/detailed needs a signed-in user; /health/ and the API docs stay public
# =============================================================================


def _health_client(debug_bypass: bool) -> TestClient:
    app = FastAPI()
    app.include_router(health_router.router, prefix="/health")
    for dep in (
        deps.get_neo4j_driver,
        deps.get_qdrant_client,
        deps.get_es_client,
        deps.get_redis,
        deps.get_temporal_client,
    ):
        app.dependency_overrides[dep] = lambda: None  # checks then fail per-store, still a JSON body
    settings = _settings(APP_DEBUG=debug_bypass)
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_health_detailed_rejects_anonymous_callers():
    assert _health_client(debug_bypass=False).get("/health/detailed").status_code == 401


def test_health_detailed_accepts_a_signed_in_caller():
    r = _health_client(debug_bypass=False).get(
        "/health/detailed", headers={"Authorization": "Bearer internal-test-key"}
    )
    assert r.status_code in (200, 503) and "checks" in r.json()


def test_health_liveness_stays_public():
    assert _health_client(debug_bypass=False).get("/health/").status_code == 200


def test_docs_and_openapi_stay_reachable_without_a_token():
    import api.main as main
    from api.middleware.opa import action_for

    app = main.create_app()
    assert (app.docs_url, app.openapi_url) == ("/docs", "/openapi.json")
    for path in ("/docs", "/openapi.json", "/redoc", "/auth/logout"):
        assert action_for("GET" if "logout" not in path else "POST", path) is None


# =============================================================================
# Seeded passwords live in the environment, not the codebase
# =============================================================================


def test_seed_refuses_to_run_without_passwords(monkeypatch):
    for u in seed_users.TEST_USERS:
        monkeypatch.delenv(u["password_env"], raising=False)
    monkeypatch.setattr(seed_users, "create_client", lambda *a, **k: pytest.fail("must refuse before connecting"))
    with pytest.raises(SystemExit, match="KAIROS_SEED_PASSWORD_ADMIN"):
        asyncio.run(seed_users.seed())


def test_seed_names_every_missing_variable(monkeypatch):
    for u in seed_users.TEST_USERS:
        monkeypatch.delenv(u["password_env"], raising=False)
    monkeypatch.setenv("KAIROS_SEED_PASSWORD_ADMIN", "x")
    with pytest.raises(SystemExit) as exc:
        asyncio.run(seed_users.seed())
    assert "KAIROS_SEED_PASSWORD_ADMIN" not in str(exc.value)
    assert "KAIROS_SEED_PASSWORD_COMPLIANCE" in str(exc.value)


def test_seed_creates_users_with_app_metadata_and_env_passwords(monkeypatch):
    created = []
    admin = SimpleNamespace(
        list_users=lambda: [],
        create_user=lambda payload: created.append(payload)
        or SimpleNamespace(user=SimpleNamespace(email=payload["email"], id="i")),
    )
    monkeypatch.setattr(seed_users, "create_client", lambda *a, **k: SimpleNamespace(auth=SimpleNamespace(admin=admin)))
    for u in seed_users.TEST_USERS:
        monkeypatch.setenv(u["password_env"], f"pw-for-{u['email']}")
    asyncio.run(seed_users.seed())
    assert len(created) == len(seed_users.TEST_USERS)
    for p in created:
        assert p["password"] == f"pw-for-{p['email']}"
        assert p["app_metadata"]["role"] == p["email"].split("@")[0]
        assert "role" not in p["user_metadata"] and "site_id" not in p["user_metadata"]


_OLD_PASSWORD = re.compile(r"Kairos(Admin|Engineer|Field|Reliability|Compliance)123")


def test_no_seeded_password_is_committed_in_owned_files():
    # Resolves from the repo root on the host and from /app in the container (where only
    # backend/ and tests/ are mounted); a file that is not mounted is simply not checked.
    here = Path(__file__).resolve()
    roots = {here.parent.parent, here.parent.parent.parent}
    names = [
        "backend/scripts/seed_users.py",
        "scripts/seed_users.py",
        "tests/conftest.py",
        "conftest.py",
        "README.md",
        "tools/e2e_flows.sh",
        "tools/capture_landing_shots.sh",
        "benchmark/verify_layers.py",
        "benchmark/run_benchmark.py",
    ]
    seen = 0
    for root in roots:
        for name in names:
            f = root / name
            if f.is_file():
                seen += 1
                assert not _OLD_PASSWORD.search(f.read_text()), f"seeded password found in {f}"
    assert seen >= 1


# =============================================================================
# Display names come from app_metadata, never the user-editable user_metadata
# =============================================================================


def _identity_supabase(user):
    admin = SimpleNamespace(get_user_by_id=lambda uid: SimpleNamespace(user=user))
    return SimpleNamespace(auth=SimpleNamespace(admin=admin))


def test_display_name_ignores_a_self_edited_user_metadata_name():
    from api.services.identity import display_name

    user = _user(app={"name": "Real Name"}, meta={"name": "Someone Else"})
    assert asyncio.run(display_name(_identity_supabase(user), "u-1")) == "Real Name"


def test_display_name_falls_back_to_the_email_local_part_not_user_metadata():
    from api.services.identity import display_name

    user = _user(app={}, meta={"name": "Someone Else"})
    assert asyncio.run(display_name(_identity_supabase(user), "u-1")) == "u"


# =============================================================================
# LEGACY_ROLE_FALLBACK: temporary, explicit, off-by-default bridge for un-migrated accounts
# =============================================================================


def test_fallback_defaults_to_off():
    assert Settings(_env_file=None).LEGACY_ROLE_FALLBACK is False


def test_flag_off_ignores_user_metadata(monkeypatch):
    meta = {"role": "admin", "site_id": "SITE_001", "name": "Evil"}
    monkeypatch.setattr(deps, "create_client", _fake_supabase(_user(app={}, meta=meta)))
    out = asyncio.run(resolve_token("tok", _settings(LEGACY_ROLE_FALLBACK=False)))
    assert (out["role"], out["site_id"], out["name"]) == ("field_worker", "", None)


def test_flag_on_without_app_role_uses_legacy_values(monkeypatch):
    meta = {"role": "engineer", "site_id": "SITE_001", "name": "Eng"}
    monkeypatch.setattr(deps, "create_client", _fake_supabase(_user(app={"provider": "email"}, meta=meta)))
    out = asyncio.run(resolve_token("tok", _settings(LEGACY_ROLE_FALLBACK=True)))
    assert (out["role"], out["site_id"], out["name"]) == ("engineer", "SITE_001", "Eng")


def test_flag_on_app_role_wins_over_user_metadata_admin(monkeypatch):
    app = {"role": "engineer", "site_id": "S1", "name": "Real"}
    monkeypatch.setattr(
        deps, "create_client", _fake_supabase(_user(app=app, meta={"role": "admin", "site_id": "X", "name": "Evil"}))
    )
    out = asyncio.run(resolve_token("tok", _settings(LEGACY_ROLE_FALLBACK=True)))
    assert (out["role"], out["site_id"], out["name"]) == ("engineer", "S1", "Real")


def test_flag_on_user_metadata_admin_cannot_override_demo(monkeypatch):
    monkeypatch.setattr(
        deps, "create_client", _fake_supabase(_user(app={"role": "demo"}, meta={"role": "admin"}))
    )
    assert asyncio.run(resolve_token("tok", _settings(LEGACY_ROLE_FALLBACK=True)))["role"] == "demo"


def test_fallback_warns_once_per_user(monkeypatch):
    deps._legacy_warned.clear()
    events = []
    monkeypatch.setattr(deps.log, "warning", lambda event, **kw: events.append(event))
    user = _user(app={}, meta={"role": "engineer"})
    for _ in range(3):
        deps.auth_metadata(user, _settings(LEGACY_ROLE_FALLBACK=True))
    assert events == ["auth.legacy_role_fallback"]


def test_display_name_honours_the_same_fallback(monkeypatch):
    from api.config import get_settings
    from api.services import identity

    user = _user(app={}, meta={"role": "engineer", "name": "Legacy Name"})
    sb = SimpleNamespace(auth=SimpleNamespace(admin=SimpleNamespace(get_user_by_id=lambda uid: SimpleNamespace(user=user))))
    monkeypatch.setattr("api.config.get_settings", lambda: _settings(LEGACY_ROLE_FALLBACK=True))
    assert asyncio.run(identity.display_name(sb, "u-1")) == "Legacy Name"
    monkeypatch.setattr("api.config.get_settings", lambda: _settings(LEGACY_ROLE_FALLBACK=False))
    assert asyncio.run(identity.display_name(sb, "u-1")) == "u"


def test_production_boots_with_fallback_on_but_warns(monkeypatch):
    import api.config as config

    events = []
    monkeypatch.setattr(config.log, "warning", lambda event, **kw: events.append(event))
    Settings(APP_ENV="production", LEGACY_ROLE_FALLBACK=True, **PROD_SAFE)  # must not raise
    assert "config.legacy_role_fallback_enabled" in events
