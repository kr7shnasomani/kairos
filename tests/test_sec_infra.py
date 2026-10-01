"""Infrastructure hardening from the security review (M1, M11, M14, L15).

Pure file checks. No stack, no secrets, no network. The Docker test image mounts only ./backend,
./tests and ./db, so checks on files outside those skip there and run on a full checkout.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.exists():
        pytest.skip(f"{rel} is not mounted in this environment")
    return p.read_text()


def _rls_tables(sql: str) -> set[str]:
    return set(re.findall(r"ALTER TABLE\s+(\w+)\s+ENABLE ROW LEVEL SECURITY", sql, re.I))


def test_every_schema_table_has_rls():
    """M1: Supabase exposes `public` tables through PostgREST, so a table without RLS is open to
    anyone holding the anon key."""
    sql = _read("db/schema.sql")
    tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", sql, re.I))
    assert len(tables) >= 19
    assert tables - _rls_tables(sql) == set()


def test_rls_migration_covers_the_tables_the_schema_enabled_late():
    sql = _read("db/schema.sql")
    mig = _read("db/migrations/017_enable_rls_remaining_tables.sql")
    early = {"assets", "documents", "briefs", "quarantine_items", "audit_log"}
    tables = set(re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", sql, re.I))
    assert _rls_tables(mig) == tables - early
    assert "CREATE POLICY" not in mig  # service-role bypasses RLS; no policies on purpose


def test_caddy_caps_request_bodies_and_sets_security_headers():
    """M11/L13."""
    cf = _read("infra/caddy/Caddyfile")
    assert re.search(r"request_body\s*\{\s*max_size\s+30MB\s*\}", cf)
    assert "X-Content-Type-Options" in cf and "Referrer-Policy" in cf
    assert "encode" not in re.sub(r"#.*", "", cf)  # compression buffers the SSE answer stream


def test_dev_connector_port_is_loopback_only():
    """M14: the connector forwards to the API as admin."""
    ov = _read("docker-compose.override.yml")
    assert '"127.0.0.1:8090:8090"' in ov
    assert not re.search(r'-\s*"8090:8090"', ov)


def test_connector_callers_send_the_shared_secret():
    for rel in ("backend/workers/attribution.py", "backend/api/routers/health.py"):
        assert "X-Connector-Secret" in _read(rel), rel


def test_third_party_actions_are_pinned_to_commit_shas():
    """L15: first-party `actions/*` and `github/*` may float; everything else needs a SHA."""
    wf = ROOT / ".github" / "workflows"
    if not wf.exists():
        pytest.skip(".github is not mounted in this environment")
    loose = []
    for f in sorted(wf.glob("*.yml")):
        for line in f.read_text().splitlines():
            m = re.match(r"\s*(?:-\s*)?uses:\s*([^@\s]+)@(\S+)", line)
            if not m or m[1].startswith(("actions/", "github/", "./")):
                continue
            if not re.fullmatch(r"[0-9a-f]{40}", m[2]):
                loose.append(f"{f.name}: {m[1]}@{m[2]}")
    assert loose == []
