"""
Kairos — FastAPI Application Entry Point
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import settings
from api.dependencies import get_es_client, get_qdrant_client
from api.middleware.opa import OPAMiddleware
from api.middleware.ratelimit import RateLimitMiddleware
from api.middleware.telemetry import setup_telemetry
from api.routers import (
    annotations,
    assets,
    audit_log,
    auth,
    briefs,
    compliance,
    documents,
    elicitation,
    events,
    governance,
    health,
    search,
)
from api.services.search_engine import SearchEngineService
from api.services.vector_store import VectorStoreService

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle: startup and shutdown."""
    log.info("kairos.startup", env=settings.APP_ENV, version=settings.APP_VERSION)

    # Ensure collections/indices exist. A cloud store blip must not stop the API from booting: they
    # already exist after `make init-all`, a failure here used to exit the process on every hot reload,
    # and /health/detailed reports a store that is actually down.
    try:
        qdrant_client = await get_qdrant_client(settings)
        await VectorStoreService(qdrant_client, settings).ensure_collections()
    except Exception as exc:  # noqa: BLE001 — startup must survive a transient store outage
        log.error("startup.qdrant_ensure_failed", error=repr(exc))

    try:
        es_client = await get_es_client(settings)
        await SearchEngineService(es_client, settings).ensure_indices()
    except Exception as exc:  # noqa: BLE001 — startup must survive a transient store outage
        log.error("startup.elasticsearch_ensure_failed", error=repr(exc))

    yield

    # Drain the pooled outbound HTTP client so in-flight provider connections close
    # cleanly instead of being dropped when the loop stops.
    from api.services.http import close_shared_client

    await close_shared_client()
    log.info("kairos.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Kairos API",
        description=(
            "Industrial Operational Intelligence Platform — "
            "proactive, event-driven knowledge delivery for asset-intensive industries."
        ),
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -------------------------------------------------------------------------
    # OPA policy enforcement (write routes + sensitive reads)
    # -------------------------------------------------------------------------
    app.add_middleware(
        OPAMiddleware,
        opa_url=settings.OPA_URL,
        settings=settings,
        debug=settings.dev_bypass_allowed,
    )

    # -------------------------------------------------------------------------
    # Per-IP rate limit (added last = outermost → rejects spam before any work)
    # -------------------------------------------------------------------------
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=settings.REDIS_URL,
        # Enforced only in production (0 = pass-through) so dev + the test suite, which burst many
        # requests from one IP, never trip it. It's a public-exposure guard, not a dev concern.
        limit_per_minute=settings.RATE_LIMIT_PER_MINUTE if settings.APP_ENV == "production" else 0,
    )

    # -------------------------------------------------------------------------
    # OpenTelemetry (no-op when OTEL endpoint is not configured)
    # -------------------------------------------------------------------------
    if settings.APP_ENV != "test":
        setup_telemetry(app)

    # -------------------------------------------------------------------------
    # Routers — one per domain layer
    # -------------------------------------------------------------------------
    app.include_router(health.router, prefix="/health", tags=["Health"])
    app.include_router(auth.router, prefix="/auth", tags=["Auth"])
    app.include_router(assets.router, prefix="/assets", tags=["Assets (Layer 1)"])
    app.include_router(documents.router, prefix="/documents", tags=["Documents (Layer 2-3)"])
    app.include_router(search.router, prefix="/search", tags=["Search (Layer 11)"])
    app.include_router(events.router, prefix="/events", tags=["Events (Layer 8)"])
    app.include_router(briefs.router, prefix="/briefs", tags=["Briefs (Layer 8)"])
    app.include_router(governance.router, prefix="/governance", tags=["Governance (Layer 7)"])
    app.include_router(compliance.router, prefix="/compliance", tags=["Compliance"])
    app.include_router(elicitation.router, prefix="/elicitation", tags=["Elicitation (Layer 6)"])
    app.include_router(annotations.router, prefix="/annotations", tags=["Annotations (Layer 3)"])
    app.include_router(audit_log.router, prefix="/audit-log", tags=["Audit Log"])

    # -------------------------------------------------------------------------
    # Global exception handler
    # -------------------------------------------------------------------------
    # A specific handler runs inside CORS; the catch-all `Exception` handler below runs outside it, so
    # a Supabase constraint error reached the browser as an opaque "Failed to fetch" with no status.
    from postgrest.exceptions import APIError

    @app.exception_handler(APIError)
    async def supabase_api_error_handler(request, exc: APIError) -> JSONResponse:
        code = getattr(exc, "code", None)
        log.warning("supabase_api_error", code=code, detail=getattr(exc, "details", None), path=str(request.url))
        if code == "23503":  # foreign-key violation — the request referenced a record that does not exist
            return JSONResponse(status_code=422, content={"detail": f"Referenced record does not exist: {getattr(exc, 'details', '')}"})
        if code == "23505":  # unique violation
            return JSONResponse(status_code=409, content={"detail": "A record with these identifiers already exists."})
        return JSONResponse(status_code=500, content={"detail": "Database request failed. Check logs for details."})

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc: Exception) -> JSONResponse:
        log.error("unhandled_exception", exc=str(exc), path=str(request.url))
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Check logs for details."},
        )

    return app


app = create_app()
