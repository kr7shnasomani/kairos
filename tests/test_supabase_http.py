"""Service-free: Supabase REST reads survive a dropped pooled connection; writes are never replayed.

Cloud Supabase closes idle HTTP/2 connections, and the next request on one failed with
`RemoteProtocolError: Server disconnected` — a 500 on /briefs, /governance/conflicts and others.
"""

import httpx
import pytest
from postgrest._sync.client import SyncPostgrestClient

from api.supabase_http import RetryStaleConnection


class _Flaky(httpx.BaseTransport):
    """Fails the first `failures` requests the way a dead pooled connection does, then succeeds."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.calls <= self.failures:
            raise httpx.RemoteProtocolError("Server disconnected", request=request)
        return httpx.Response(200, json=[{"ok": True}], request=request)


def _client(inner: _Flaky) -> httpx.Client:
    return httpx.Client(transport=RetryStaleConnection(inner), base_url="https://example.supabase.co")


def test_a_read_on_a_dead_connection_is_retried_once():
    inner = _Flaky(failures=1)
    assert _client(inner).get("/rest/v1/briefs").status_code == 200
    assert inner.calls == 2


def test_a_read_that_fails_again_still_raises():
    inner = _Flaky(failures=2)
    with pytest.raises(httpx.RemoteProtocolError):
        _client(inner).get("/rest/v1/briefs")
    assert inner.calls == 2


def test_a_write_is_never_replayed():
    inner = _Flaky(failures=1)
    with pytest.raises(httpx.RemoteProtocolError):
        _client(inner).post("/rest/v1/audit_log", json={"action": "x"})
    assert inner.calls == 1


def test_every_postgrest_session_goes_through_the_retry_transport():
    import api  # noqa: F401 — importing the package installs the retry

    pg = SyncPostgrestClient("https://example.supabase.co/rest/v1", headers={"apikey": "k"})
    assert isinstance(pg.session._transport, RetryStaleConnection)
    assert str(pg.session.base_url).startswith("https://example.supabase.co/rest/v1")
    assert pg.session.headers["apikey"] == "k"
