"""
Shared fixtures for Kairos integration tests.
Requires `make dev` to be running before executing the suite.
"""

import os
import sys
import asyncio
from pathlib import Path

import pytest
import httpx
from uuid import uuid4

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Session teardown purges the test residue these fixtures create (see scripts/purge_test_data.py).
# In the container PYTHONPATH=/app already exposes `scripts`; on the host shortcut, add backend/.
try:
    from scripts.purge_test_data import purge as _purge_test_data
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
    try:
        from scripts.purge_test_data import purge as _purge_test_data
    except ImportError:
        _purge_test_data = None


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_data():
    """Delete every test-prefixed entity after the suite so runs don't accumulate DB junk."""
    yield
    if os.getenv("KAIROS_SKIP_TEST_CLEANUP") or _purge_test_data is None:
        return
    try:
        asyncio.run(_purge_test_data())
    except Exception as exc:  # cleanup must never fail the suite
        print(f"[conftest] test-data cleanup skipped: {exc}")

# Static internal key — never expires, returns role=admin.
# Defined in backend/api/config.py INTERNAL_API_KEY default.
_INTERNAL_KEY = os.getenv("INTERNAL_API_KEY", "kairos-internal-dev-key")

ADMIN_EMAIL = "admin@kairos.local"
ADMIN_PASSWORD = "KairosAdmin123!"
ENGINEER_EMAIL = "engineer@kairos.local"
ENGINEER_PASSWORD = "KairosEngineer123!"
FIELD_EMAIL = "field_worker@kairos.local"
FIELD_PASSWORD = "KairosField123!"


def uid() -> str:
    return uuid4().hex[:8].upper()


# ---------------------------------------------------------------------------
# Session-scoped token fixtures (sync — avoids event-loop scope conflicts)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def engineer_token():
    r = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"email": ENGINEER_EMAIL, "password": ENGINEER_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Engineer login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def field_token():
    r = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"email": FIELD_EMAIL, "password": FIELD_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Field login failed: {r.text}"
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Per-test async HTTP clients
# ---------------------------------------------------------------------------

@pytest.fixture
async def admin_client():
    # Uses INTERNAL_API_KEY — never expires, role=admin. No login required.
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {_INTERNAL_KEY}"},
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture
async def engineer_client(engineer_token):
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {engineer_token}"},
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture
async def field_client(field_token):
    async with httpx.AsyncClient(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {field_token}"},
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture
async def anon_client():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        yield client


# ---------------------------------------------------------------------------
# Session-scoped shared asset (created once, reused across tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def shared_asset_id():
    asset_id = f"ASSET-TEST-{uid()}"
    r = httpx.post(
        f"{BASE_URL}/assets/",
        json={
            "asset_id": asset_id,
            "tag_number": f"TAG-{asset_id}",
            "name": f"Integration Test Asset {asset_id}",
            "equipment_class": "PUMP",
            "criticality": "critical",
            "site_id": "SITE_001",
            "facility_id": "FAC_001",
            "eam_source": "integration_test",
            "confirmed_by_user_id": "test-runner",
        },
        headers={"Authorization": f"Bearer {_INTERNAL_KEY}"},
        timeout=30,
    )
    assert r.status_code in (200, 201), f"Shared asset creation failed: {r.text}"
    return asset_id


def _create_asset(asset_id: str) -> str:
    r = httpx.post(
        f"{BASE_URL}/assets/",
        json={
            "asset_id": asset_id,
            "tag_number": f"TAG-{asset_id}",
            "name": f"Integration Test Asset {asset_id}",
            "equipment_class": "PUMP",
            "criticality": "critical",
            "site_id": "SITE_001",
            "facility_id": "FAC_001",
            "eam_source": "integration_test",
            "confirmed_by_user_id": "test-runner",
        },
        headers={"Authorization": f"Bearer {_INTERNAL_KEY}"},
        timeout=30,
    )
    assert r.status_code in (200, 201), f"Asset creation failed: {r.text}"
    return asset_id


@pytest.fixture
def fresh_asset_id():
    """
    A brand-new asset per test — use this instead of `shared_asset_id` whenever the
    test needs its operational event to actually land.

    WHY THIS EXISTS: Layer 8 canonical event normalization collapses events that share
    an asset id and event type inside `DEDUP_WINDOW_MINUTES` (default 10). `shared_asset_id`
    is session-scoped, a full suite run finishes well inside that window, and seven tests
    POST `/events/inspection-complete` against it — so the first one wins and every later
    one correctly returns `{"status": "deduplicated"}` with no `quarantine_item_id`.

    That is the dedup working as designed, not a bug, but it makes any test that needs a
    real quarantine item order-dependent: green alone, red in a full run. A unique asset
    keeps each test's precondition its own.
    """
    return _create_asset(f"ASSET-FRESH-{uid()}")
