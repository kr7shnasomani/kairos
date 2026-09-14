"""
Retry a Supabase REST read once when its pooled HTTP/2 connection turns out to be dead.

postgrest-py 0.16 builds its own `httpx.Client(http2=True)` and exposes no way to configure it.
Supabase closes idle HTTP/2 connections; the next request that reuses one fails with
`RemoteProtocolError` ("Server disconnected" / `ConnectionTerminated`) and the endpoint returns 500.
This was recorded in `status.md` as intermittent and cloud-side, and it surfaced as a crash screen
in QA. httpx drops the dead connection from the pool when it fails, so one immediate retry lands
on a fresh connection.

Only GET and HEAD are retried. A write that died mid-flight may already have been applied, and
replaying it could insert a duplicate row, so writes still raise.

ponytail: this replaces the library's session factory. Swap it for a custom `httpx_client` in
`ClientOptions` once supabase-py is upgraded to a version that accepts one.
"""

import httpx
import structlog
from postgrest._sync.client import SyncPostgrestClient
from postgrest.utils import SyncClient

log = structlog.get_logger(__name__)

_IDEMPOTENT = frozenset({"GET", "HEAD"})
_STALE_CONNECTION = (httpx.RemoteProtocolError, httpx.ReadError)


class RetryStaleConnection(httpx.BaseTransport):
    """Transport wrapper: retry an idempotent request once after a dropped connection."""

    def __init__(self, inner: httpx.BaseTransport) -> None:
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return self._inner.handle_request(request)
        except _STALE_CONNECTION as exc:
            if request.method not in _IDEMPOTENT:
                raise
            log.warning("supabase.stale_connection_retry", method=request.method, path=request.url.path,
                        error=type(exc).__name__)
            return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def _create_session(self, base_url, headers, timeout, verify=True) -> SyncClient:
    # Same settings postgrest-py uses (HTTP/2, redirects, timeout, headers), plus the retry wrapper.
    # With an explicit transport httpx ignores the client-level http2/verify, so they go on the transport.
    return SyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
        transport=RetryStaleConnection(httpx.HTTPTransport(http2=True, verify=verify)),
    )


def install() -> None:
    """Route every PostgREST session in this process through `RetryStaleConnection`. Idempotent."""
    if getattr(SyncPostgrestClient.create_session, "_retry_stale_connection", False):
        return
    _create_session._retry_stale_connection = True
    SyncPostgrestClient.create_session = _create_session
