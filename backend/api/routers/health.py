"""
Health router — liveness and readiness probes.
"""

import asyncio
import time

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from api.dependencies import (
    CurrentUserDep,
    ElasticsearchDep,
    Neo4jDep,
    QdrantDep,
    RedisDep,
    SettingsDep,
    TemporalDep,
    require_role,
)
from api.services.http import shared_client
from api.services.model_providers import all_tiers
from api.services.supply_chain import verify_served_model

log = structlog.get_logger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    service: str


@router.get("/", response_model=HealthResponse, summary="Liveness probe")
async def health_check() -> HealthResponse:
    """Returns 200 if the API process is alive."""
    from api.config import settings
    return HealthResponse(status="ok", version=settings.APP_VERSION, service="kairos-api")


@router.get("/detailed", summary="Detailed readiness probe")
async def detailed_health_check(
    response: Response,
    neo4j: Neo4jDep,
    qdrant: QdrantDep,
    es: ElasticsearchDep,
    redis: RedisDep,
    temporal: TemporalDep,
    settings: SettingsDep,
) -> dict:
    """
    Returns 200 when all downstream dependencies are reachable.
    Pings Neo4j, Qdrant, ES, Redis, and Temporal.
    """
    checks = {
        "neo4j": "pending",
        "qdrant": "pending",
        "elasticsearch": "pending",
        "redis": "pending",
        "temporal": "pending",
    }

    async def check_neo4j():
        try:
            await neo4j.verify_connectivity()
            checks["neo4j"] = "ok"
        except Exception as e:
            log.warning("health.check_failed", component="neo4j", error=str(e))
            checks["neo4j"] = "error"

    async def check_qdrant():
        try:
            await qdrant.get_collections()
            checks["qdrant"] = "ok"
        except Exception as e:
            log.warning("health.check_failed", component="qdrant", error=str(e))
            checks["qdrant"] = "error"

    async def check_es():
        try:
            await es.info()
            checks["elasticsearch"] = "ok"
        except Exception as e:
            log.warning("health.check_failed", component="elasticsearch", error=str(e))
            checks["elasticsearch"] = "error"

    async def check_redis():
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception as e:
            log.warning("health.check_failed", component="redis", error=str(e))
            checks["redis"] = "error"

    async def check_temporal():
        try:
            await temporal.service_client.check_health()
            checks["temporal"] = "ok"
        except Exception as e:
            log.warning("health.check_failed", component="temporal", error=str(e))
            checks["temporal"] = "error"

    await asyncio.gather(
        check_neo4j(),
        check_qdrant(),
        check_es(),
        check_redis(),
        check_temporal(),
    )

    overall_status = "ready"
    if any(status != "ok" for status in checks.values()):
        overall_status = "degraded"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    # Phase is served from live backend config, not a frontend build-time env var, so the badge
    # reports what is actually being enforced rather than what the image was built with.
    return {
        "status": overall_status,
        "checks": checks,
        "phase": settings.KAIROS_PHASE,
        "phase_enforced": {
            "synthesis": settings.KAIROS_PHASE >= 2,
            "proactive_delivery": settings.KAIROS_PHASE >= 3,
        },
    }


@router.get("/model", summary="Probe an external model provider (admin, opt-in)")
async def model_health_check(
    provider: str,
    settings: SettingsDep,
    _user: dict = Depends(require_role("admin")),
) -> dict:
    """Minimal liveness probe for a rate-limited model provider (any synthesis tier / Jina / Groq).

    Admin-only and NOT polled by default — each call spends real provider quota. The System Health
    page fires it at most once/minute per provider, and only when that provider's toggle is on.
    Uses the smallest possible request (1 token / 1 embedding / a models list).
    """
    provider = provider.lower()
    t0 = time.perf_counter()

    async def _post(url: str, key: str, body: dict) -> httpx.Response:
        async with httpx.AsyncClient(timeout=20) as c:
            return await c.post(url, headers={"Authorization": f"Bearer {key}"}, json=body)

    try:
        # Synthesis tiers come from the one registry the cascade uses, so a tier added there is
        # probeable here with no edit. Jina and Groq are not chat endpoints and stay special cases.
        synthesis = next((p for p in all_tiers(settings) if p.name == provider), None)
        served: str | None = None
        mismatch: dict | None = None
        if synthesis is not None:
            if not synthesis.api_key:
                return {"provider": provider, "ok": False, "detail": "not configured"}
            # Sends the tier's own extra_body, so a provider that rejects the thinking flag fails
            # here, visibly, instead of 400ing every real answer and silently falling through.
            r = await _post(synthesis.chat_url, synthesis.api_key,
                            {"model": synthesis.model, "messages": [{"role": "user", "content": "ping"}],
                             "max_tokens": 1, **synthesis.extra_body})
            model = synthesis.model
            if r.status_code < 300:
                body = r.json()
                served = body.get("model")
                mismatch = verify_served_model(synthesis.model, body)
        elif provider == "jina":
            if not settings.JINA_API_KEY:
                return {"provider": provider, "ok": False, "detail": "not configured"}
            r = await _post(settings.JINA_EMBED_URL, settings.JINA_API_KEY,
                            {"model": settings.JINA_EMBED_MODEL, "input": ["ping"]})
            model = settings.JINA_EMBED_MODEL
        elif provider == "groq":
            if not settings.GROQ_API_KEY:
                return {"provider": provider, "ok": False, "detail": "not configured"}
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.get("https://api.groq.com/openai/v1/models",
                                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"})
            model = settings.GROQ_WHISPER_MODEL
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown provider '{provider}'.")

        latency_ms = (time.perf_counter() - t0) * 1000
        return {"provider": provider, "ok": r.status_code < 300, "status": r.status_code,
                "model": model, "served_model": served, "model_mismatch": mismatch,
                "latency_ms": round(latency_ms), "detail": None if r.status_code < 300 else r.text[:120]}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — a probe failure is a status, not a 500
        log.warning("health.model_probe_failed", provider=provider, error=str(exc))
        return {"provider": provider, "ok": False,
                "latency_ms": round((time.perf_counter() - t0) * 1000), "detail": "probe failed"}


@router.get("/connectors", summary="OT historian connector registry (Layer 5)")
async def ot_connector_registry(
    current_user: CurrentUserDep,
    settings: SettingsDep,
) -> dict:
    """
    Which historian connectors this deployment supports, and which are actually configured.

    Layer 5's claim is that "new connector types are added without changing the core layer" — this
    makes that inspectable rather than asserted. An unconfigured connector says so; it never
    fabricates a reading and never fails silently, which is precisely what the deleted coverage
    handler did (hardcoded sensor tags for every asset, labelled `source: "knowledge_graph"`).
    """
    import os

    go_url = os.getenv("GO_CONNECTOR_URL", f"http://kairos-backend-go:{settings.GO_CONNECTOR_PORT}")
    try:
        client = shared_client(5.0)
        resp = await client.get(f"{go_url}/ot/connectors", timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        # The connector service being down is itself the honest answer — not an empty registry
        # that would read as "no connectors supported".
        log.warning("health.connector_registry_unreachable", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OT connector service is unreachable — connector registry unavailable.",
        ) from exc
