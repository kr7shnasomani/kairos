"""
Auth middleware — request-level auth context and audit logging.
"""

import time

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

log = structlog.get_logger(__name__)


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request with user identity, path, method, status code, and latency."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        # Extract user identity from request state (set by auth dependency)
        user_id = getattr(request.state, "user_id", "anonymous")

        log.info(
            "http.request",
            method=request.method,
            path=request.scope["path"],
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
            user_id=user_id,
        )
        return response
