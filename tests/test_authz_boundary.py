"""Trust boundary — OPA enforcement surface, claim mapping, fail-closed, and site tenancy.

Pure logic + one localhost connection-refused probe. No stack, no secrets, no network egress.
"""

import asyncio
import re
from pathlib import Path

import pytest
from fastapi import HTTPException

from api import dependencies as deps
from api.config import Settings
from api.dependencies import resolve_token, site_scope
from api.middleware.opa import OPAMiddleware, action_for

# =============================================================================
# Which routes are policy-enforced
# =============================================================================


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        # writes — unchanged mapping
        ("POST", "/governance/quarantine/abc/promote", "promote_quarantine"),
        ("POST", "/documents/ingest", "ingest_document"),
        ("POST", "/assets/", "write_assets"),
        ("POST", "/events/work-order", "ingest_event"),
        ("POST", "/events/ptw", "ingest_event"),
        # field-worker event flows stay on the catch-all
        ("POST", "/events/deviation-flag", "write_api"),
        ("POST", "/events/abc/ack", "write_api"),
        # sensitive reads — previously enforced nowhere
        ("GET", "/audit-log/", "read_audit"),
        ("GET", "/compliance/gaps", "read_compliance"),
        ("GET", "/compliance/dashboard", "read_compliance"),
        ("GET", "/documents/", "read_documents"),
        ("GET", "/events/", "read_events"),
        # the two /governance children the compliance auditor's non-conformance view reads —
        # they must resolve BEFORE the generic /governance entry or compliance is locked out
        ("GET", "/governance/conflicts", "read_nonconformance"),
        ("GET", "/governance/quarantine", "read_nonconformance"),
        ("GET", "/governance/model-gate/history", "read_governance"),
        ("GET", "/governance/circuit-breaker", "read_governance"),
        # reads the UI treats as open to every authenticated role — must stay unenforced,
        # or the field-worker flows break without closing any boundary
        ("GET", "/search/", None),
        ("GET", "/briefs/", None),
        ("GET", "/assets/EQ-101", None),
        ("GET", "/elicitation/questions", None),
        ("GET", "/annotations/", None),
        # shell context every persona renders — a field worker must still be able to see that
        # the plant is in shutdown, even though the rest of /events is staff-only
        ("GET", "/events/plant-state/SITE_001", None),
        # ...but declaring a plant state is still a write and stays gated
        ("POST", "/events/plant-state", "write_api"),
        # never enforced
        ("GET", "/health/", None),
        ("POST", "/auth/login", None),
        ("GET", "/docs", None),
    ],
)
def test_action_for(method, path, expected):
    assert action_for(method, path) == expected


def test_cors_preflight_is_never_gated():
    # This middleware is outermost, so it sees the preflight before CORSMiddleware — and a
    # preflight carries no Authorization header. Gating it 401s every cross-origin request.
    assert action_for("OPTIONS", "/compliance/gaps") is None
    assert action_for("OPTIONS", "/documents/ingest") is None
    assert action_for("HEAD", "/compliance/gaps") == "read_compliance"


# =============================================================================
# One verification path — the middleware must not carry its own copy
# =============================================================================


def _settings(**over) -> Settings:
    return Settings(INTERNAL_API_KEY="internal-test-key", AUTH_CACHE_TTL_SECONDS=60, **over)


def test_middleware_and_dependency_share_one_verifier():
    # Regression guard for the defect that made authorization inert: the middleware had a
    # second, HS256-only implementation, but this project's Supabase issues ES256 tokens, so
    # it rejected every real token and fell through to the dev bypass. There must be exactly
    # one verifier, and the middleware must use it.
    import inspect

    from api.middleware import opa

    assert not hasattr(opa, "jwt"), "middleware must not decode tokens itself"
    assert "resolve_token" in inspect.getsource(opa.OPAMiddleware._user_from_request)


def test_internal_service_key_resolves_without_a_round_trip():
    user = asyncio.run(resolve_token("internal-test-key", _settings()))
    assert user is not None and user["role"] == "admin"


def test_cached_token_is_returned_without_calling_supabase(monkeypatch):
    deps._auth_cache.clear()
    monkeypatch.setattr(
        deps, "create_client", lambda *a, **k: pytest.fail("must not re-verify a cached token")
    )
    deps._auth_cache_put("tok-live", {"user_id": "u9", "role": "compliance", "site_id": "S1"}, ttl=60)
    assert asyncio.run(resolve_token("tok-live", _settings()))["role"] == "compliance"
    deps._auth_cache.clear()


def test_unverifiable_token_is_not_a_user(monkeypatch):
    deps._auth_cache.clear()

    def _boom(*a, **k):
        raise RuntimeError("supabase says no")

    monkeypatch.setattr(deps, "create_client", _boom)
    assert asyncio.run(resolve_token("garbage", _settings())) is None


# =============================================================================
# Fail closed when OPA is unreachable
# =============================================================================


def _middleware(debug: bool) -> OPAMiddleware:
    # Port 1 on loopback refuses immediately — no egress, no waiting on a timeout.
    return OPAMiddleware(app=None, opa_url="http://127.0.0.1:1", settings=_settings(), debug=debug)


def test_unreachable_opa_denies_outside_dev():
    mw = _middleware(debug=False)
    assert asyncio.run(mw._ask_opa({"role": "engineer"}, "write_assets", "/assets")) is False


def test_unreachable_opa_still_passes_through_in_dev():
    mw = _middleware(debug=True)
    assert asyncio.run(mw._ask_opa({"role": "engineer"}, "write_assets", "/assets")) is True


def test_internal_service_key_is_recognised_by_the_middleware():
    # Fail-closed would otherwise 401 every Go-connector and Celery write.
    mw = _middleware(debug=False)

    class _Req:
        headers = {"Authorization": "Bearer internal-test-key"}

    user = asyncio.run(mw._user_from_request(_Req()))
    assert user is not None and user["role"] == "admin"


def test_request_without_a_bearer_header_is_anonymous():
    mw = _middleware(debug=False)

    class _Req:
        headers = {}

    assert asyncio.run(mw._user_from_request(_Req())) is None


# =============================================================================
# Site tenancy — derived from the token, never the query string
# =============================================================================

_ENGINEER = {"role": "engineer", "site_id": "SITE_001"}


def test_non_admin_is_pinned_to_own_site_when_none_requested():
    assert site_scope(_ENGINEER, None) == "SITE_001"


def test_non_admin_may_restate_own_site():
    assert site_scope(_ENGINEER, "SITE_001") == "SITE_001"


def test_non_admin_cannot_read_another_site():
    with pytest.raises(HTTPException) as exc:
        site_scope(_ENGINEER, "SITE_002")
    assert exc.value.status_code == 403


def test_account_without_a_site_gets_nothing_rather_than_everything():
    with pytest.raises(HTTPException) as exc:
        site_scope({"role": "engineer", "site_id": ""}, None)
    assert exc.value.status_code == 403


def test_admin_keeps_the_cross_site_view():
    admin = {"role": "admin", "site_id": "SITE_001"}
    assert site_scope(admin, None) is None
    assert site_scope(admin, "SITE_002") == "SITE_002"


# =============================================================================
# Dev bypass requires debug AND a non-production env
# =============================================================================


@pytest.mark.parametrize(
    ("env", "debug", "expected"),
    [
        ("development", True, True),
        ("development", False, False),
        ("production", True, False),  # the mis-set-env case the guardrail alone could miss
        ("production", False, False),
    ],
)
def test_dev_bypass_allowed(env, debug, expected):
    # APP_ENV=production trips the secret guardrail, so build the production cases with the
    # secrets already set — the property, not the guardrail, is what is under test here.
    extra = (
        {
            "INTERNAL_API_KEY": "set",
            "APP_SECRET_KEY": "set",
            "NEO4J_PASSWORD": "set",
            "SUPABASE_SERVICE_ROLE_KEY": "set",
            "SUPABASE_JWT_SECRET": "set",
            "MOC_WEBHOOK_SECRET": "set",
        }
        if env == "production"
        else {}
    )
    if env == "production" and debug:
        # the guardrail refuses to construct at all — which is itself the enforcement
        with pytest.raises(ValueError, match="APP_DEBUG must be false"):
            Settings(APP_ENV=env, APP_DEBUG=debug, **extra)
        return
    assert Settings(APP_ENV=env, APP_DEBUG=debug, **extra).dev_bypass_allowed is expected


# =============================================================================
# The `demo` role (security review C1): sees everything and works the showcase plant. Policy is the
# coarse layer; the API fence and the per-handler guards are the fine one (`test_tenant_isolation.py`).
# =============================================================================

_REGO = Path(__file__).resolve().parents[1] / "infra" / "policies" / "kairos.rego"
_needs_rego = pytest.mark.skipif(not _REGO.exists(), reason="infra/ is not mounted in this container")

_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _demo_grants() -> set[str]:
    text = _REGO.read_text()
    line = next(ln for ln in text.splitlines() if ln.strip().startswith('"demo":'))
    return set(re.findall(r'"([a-z_*]+)"', line.split(":", 1)[1]))


@_needs_rego
def test_demo_role_has_an_explicit_allow_list_and_is_not_in_the_catch_all():
    text = _REGO.read_text()
    assert _demo_grants() == {
        "read_search", "read_briefs", "read_assets", "read_documents", "read_events",
        "read_compliance", "read_nonconformance", "read_audit", "read_governance", "read_other",
        "synthesize", "rca_pack", "answer_feedback",
        # The showcase writes. Each route is fenced to showcase rows by the API, not by this table.
        "write_api", "ingest_document", "ingest_event", "write_assets",
        "promote_quarantine", "resolve_admin_conflict",
    }
    # The catch-all names the five staff roles; demo holds its grants by name, so a new action is
    # refused for it until someone grants it here on purpose.
    catch_all = text[text.index("Catch-all"):]
    assert "demo" not in catch_all[catch_all.index("allow if"):]
    sensitive = text[text.index("_sensitive_actions :="):]
    sensitive = sensitive[: sensitive.index("}")]
    for action in ("read_audit", "read_governance", "read_events", "read_other", "read_search"):
        assert f'"{action}"' in sensitive
    for action in ("synthesize", "rca_pack", "answer_feedback"):
        assert f'"{action}"' not in sensitive  # the staff roles keep these through the catch-all


@_needs_rego
@pytest.mark.parametrize(
    ("path", "action"),
    [
        ("/search/", "read_search"),
        ("/briefs/B-1", "read_briefs"),
        ("/assets/EQ-101/knowledge", "read_assets"),
        ("/documents/", "read_documents"),
        ("/events/", "read_events"),
        ("/compliance/dashboard", "read_compliance"),
        ("/governance/conflicts", "read_nonconformance"),
        ("/governance/model-gate/history", "read_governance"),
        ("/audit-log/", "read_audit"),
        ("/elicitation/offboarding", "read_other"),
        ("/annotations/", "read_other"),
        ("/some/route/added/later", "read_other"),
    ],
)
def test_demo_can_read_everything_an_admin_reads(path, action):
    resolved = action_for("GET", path, "demo")
    assert resolved == action
    assert resolved in _demo_grants()


@_needs_rego
@pytest.mark.parametrize(
    ("method", "path", "action"),
    [
        ("POST", "/search/synthesize", "synthesize"),
        ("POST", "/search/rca-pack", "rca_pack"),
        ("POST", "/search/feedback", "answer_feedback"),
        ("POST", "/documents/ingest", "ingest_document"),
        ("POST", "/assets/", "write_assets"),
        ("POST", "/events/work-order", "ingest_event"),
        ("POST", "/governance/quarantine/Q-1/promote", "promote_quarantine"),
        ("POST", "/governance/conflicts/C-1/resolve", "resolve_admin_conflict"),
        ("POST", "/briefs/B-1/ack", "write_api"),
    ],
)
def test_demo_showcase_writes_resolve_to_granted_actions(method, path, action):
    assert action_for(method, path, "demo") == action
    assert action in _demo_grants()


@_needs_rego
def test_every_write_route_the_demo_role_can_reach_is_one_the_fence_lists():
    """Introspects the real app. Policy now admits the demo role to most writes, so the fence is what
    keeps an unlisted route closed; this proves every route policy would admit is either listed in
    `tenant.DEMO_WRITE_ALLOWED` or a route the fence refuses by design."""
    import re as _re

    from api.main import create_app
    from api.services import tenant

    granted = _demo_grants()
    unlisted_but_policy_admitted = set()
    for route in create_app().routes:
        methods = set(getattr(route, "methods", None) or ()) & _WRITE_METHODS
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        concrete = _re.sub(r"\{[^}]+\}", "x", path)
        for method in methods:
            action = action_for(method, concrete, "demo")
            if action in granted and (method, path) not in tenant.DEMO_WRITE_ALLOWED:
                unlisted_but_policy_admitted.add((method, path))
    # Policy admits these through `write_api`; the fence (and an admin-only role gate) refuse them.
    assert unlisted_but_policy_admitted == {("POST", "/governance/model-gate/run")}


def test_the_fence_is_installed_on_the_app_so_an_unlisted_write_route_stays_closed_to_demo():
    from api.dependencies import demo_write_fence
    from api.main import create_app

    assert demo_write_fence in [d.dependency for d in create_app().router.dependencies]


def test_other_roles_keep_the_unenforced_reads_and_the_same_decisions():
    # The demo fallback must not turn on OPA for GETs the other roles rely on being open.
    for role in (None, "engineer", "field_worker", "compliance"):
        assert action_for("GET", "/search/", role) is None
        assert action_for("GET", "/elicitation/offboarding", role) is None
        assert action_for("GET", "/audit-log/", role) == "read_audit"
    # Copilot POSTs carry their own actions; every staff role gets them from the rego catch-all.
    assert action_for("POST", "/search/synthesize") == "synthesize"
    assert action_for("POST", "/search/feedback") == "answer_feedback"
    assert action_for("POST", "/search/rca-pack") == "rca_pack"


def test_demo_never_gated_on_preflight_or_health():
    assert action_for("OPTIONS", "/search/", "demo") is None
    assert action_for("GET", "/health/detailed", "demo") is None
    assert action_for("GET", "/auth/me", "demo") is None
    assert action_for("GET", "/events/plant-state/SITE_001", "demo") is None
