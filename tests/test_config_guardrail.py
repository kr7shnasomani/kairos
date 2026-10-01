"""Prod fail-closed guardrail — Settings refuses insecure defaults when APP_ENV=production.

Pure logic, no network. `_env_file=None` skips the .env layer; explicit kwargs win over OS env.
"""

import pytest

from api.config import Settings

# All guarded secrets set to non-default values → a valid prod config.
SAFE = dict(
    _env_file=None,
    APP_DEBUG=False,
    APP_SECRET_KEY="prod-secret",
    INTERNAL_API_KEY="prod-internal-key",
    NEO4J_PASSWORD="prod-neo4j-pw",
    SUPABASE_SERVICE_ROLE_KEY="svc",
    SUPABASE_JWT_SECRET="jwt",
    MOC_WEBHOOK_SECRET="hook",
)


def test_prod_boots_when_all_secrets_set():
    Settings(APP_ENV="production", **SAFE)  # must not raise


def test_prod_refuses_default_internal_api_key():
    bad = {**SAFE, "INTERNAL_API_KEY": "kairos-internal-dev-key"}
    with pytest.raises(ValueError, match="INTERNAL_API_KEY"):
        Settings(APP_ENV="production", **bad)


def test_prod_refuses_app_debug_true():
    bad = {**SAFE, "APP_DEBUG": True}
    with pytest.raises(ValueError, match="APP_DEBUG"):
        Settings(APP_ENV="production", **bad)


def test_dev_ignores_defaults():
    Settings(APP_ENV="development", _env_file=None,
             INTERNAL_API_KEY="kairos-internal-dev-key", APP_DEBUG=True)  # must not raise
