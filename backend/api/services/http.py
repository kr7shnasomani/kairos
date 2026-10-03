"""
Shared pooled HTTP client for outbound model-provider calls.

Every model call used to open its own `httpx.AsyncClient`, which means a fresh TCP
handshake and TLS negotiation per request — no keep-alive, no connection reuse. On a
30-second LLM call that overhead is noise, but on embeddings (one per search, small and
frequent) it is a meaningful share of the latency, and under concurrency it is a socket
churn problem rather than a latency one.

The client is cached per event loop, not globally. An `AsyncClient` binds to the loop that
created it, and this code runs under several: the FastAPI loop, and a fresh `asyncio.run()`
loop per Celery task. A single global client would be reused across a dead loop and raise.
"""

import asyncio

import httpx
import structlog

log = structlog.get_logger(__name__)

# Providers are external and rate-limited; a large pool buys nothing and risks tripping
# their concurrency limits. Keep-alives are what actually matter here.
_LIMITS = httpx.Limits(max_connections=32, max_keepalive_connections=16, keepalive_expiry=30.0)

# loop id -> (loop, client). Holding the loop itself lets us detect reuse across loops.
_clients: dict[int, tuple[asyncio.AbstractEventLoop, httpx.AsyncClient]] = {}


def shared_client(default_timeout: float = 30.0) -> httpx.AsyncClient:
    """
    Returns a pooled client for the running event loop, creating one if needed.

    Pass a per-request `timeout=` to `.post()`/`.get()` when a call needs longer than the
    default — the client's timeout is only a fallback, so one shared client serves the
    fast embedding calls and the slow vision calls alike.
    """
    loop = asyncio.get_running_loop()
    key = id(loop)

    entry = _clients.get(key)
    if entry is not None:
        cached_loop, client = entry
        if cached_loop is loop and not client.is_closed:
            return client
        # Stale: the loop was replaced (id reuse) or the client was closed under us.
        _clients.pop(key, None)

    client = httpx.AsyncClient(limits=_LIMITS, timeout=default_timeout)
    _clients[key] = (loop, client)
    log.debug("http.pool_created", loop_id=key, pools=len(_clients))
    return client


async def close_shared_client() -> None:
    """
    Closes the client for the running loop. Called from the FastAPI shutdown hook so the
    API drains its pool cleanly; short-lived Celery loops are left to process teardown.
    """
    loop: asyncio.AbstractEventLoop | None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    entry = _clients.pop(id(loop), None)
    if entry is None:
        return
    _, client = entry
    if not client.is_closed:
        await client.aclose()
        log.debug("http.pool_closed", loop_id=id(loop))


def run_with_client(coro):
    """
    Runs a coroutine via asyncio.run(), ensuring the shared HTTP client is closed
    before the event loop tears down. Useful for Celery tasks.
    """
    async def wrapper():
        try:
            return await coro
        finally:
            await close_shared_client()
    return asyncio.run(wrapper())
