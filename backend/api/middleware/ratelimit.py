"""Per-client-IP rate limit for the public API.

Protects the open endpoints — especially /search/synthesize, which spends paid LLM quota — from a
single client exhausting them for everyone. Fixed-window counter in Redis (the broker/cache we
already run). ponytail: fixed-window is fine here; switch to sliding-window only if burst-at-the-
minute-boundary abuse ever shows up. Fails OPEN if Redis is unreachable — a cache hiccup must not
take the whole API down.
"""

import time

import redis.asyncio as aioredis
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = structlog.get_logger(__name__)

_EXEMPT = {"/health", "/health/detailed"}  # uptime probes must never be throttled


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_url: str, limit_per_minute: int):
        super().__init__(app)
        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._limit = limit_per_minute

    async def dispatch(self, request: Request, call_next):
        if self._limit <= 0 or request.scope["path"] in _EXEMPT:
            return await call_next(request)

        # Behind Caddy, request.client is the proxy — trust the first X-Forwarded-For hop.
        fwd = request.headers.get("x-forwarded-for", "")
        ip = fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")
        key = f"ratelimit:{ip}:{int(time.time()) // 60}"

        try:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, 60)
        except Exception as exc:  # noqa: BLE001 — fail open, availability over strict limiting
            log.warning("ratelimit.redis_unavailable", error=str(exc))
            return await call_next(request)

        if count > self._limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down and retry shortly."},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)
