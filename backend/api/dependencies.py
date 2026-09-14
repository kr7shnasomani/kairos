"""
Kairos — FastAPI Dependency Injection
Provides shared clients as FastAPI dependencies (injected per-request or application-wide).
"""

import asyncio
import hashlib
import time
import uuid
from typing import Annotated

import redis.asyncio as aioredis
import structlog
from elasticsearch import AsyncElasticsearch
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from neo4j import AsyncDriver, AsyncGraphDatabase
from qdrant_client import AsyncQdrantClient
from supabase import Client, create_client
from temporalio.client import Client as TemporalClient

from api.config import Settings, get_settings

log = structlog.get_logger(__name__)

SettingsDep = Annotated[Settings, Depends(get_settings)]

# =============================================================================
# Neo4j — Temporal Reality Graph
# =============================================================================

_neo4j_driver: AsyncDriver | None = None


async def get_neo4j_driver(settings: SettingsDep) -> AsyncDriver:
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD),
            # Aura Free closes idle connections; without pool hygiene the next query on a
            # stale pooled connection throws SessionExpired ("defunct connection") → the
            # intermittent 500s seen on Neo4j-backed endpoints (compliance/dashboard,
            # /assets/{id}/knowledge, graph, blast-radius). Liveness-check a connection
            # that's been idle before handing it out, and recycle connections well before
            # Aura's idle timeout so they never go stale.
            liveness_check_timeout=30,          # ping (RESET) a connection idle >30s; replace if dead
            max_connection_lifetime=300,        # recycle after 5 min, below Aura's idle window
            connection_acquisition_timeout=60,
        )
    return _neo4j_driver


Neo4jDep = Annotated[AsyncDriver, Depends(get_neo4j_driver)]


# =============================================================================
# Qdrant — Vector Store
# =============================================================================

_qdrant_client: AsyncQdrantClient | None = None


async def get_qdrant_client(settings: SettingsDep) -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
    return _qdrant_client


QdrantDep = Annotated[AsyncQdrantClient, Depends(get_qdrant_client)]


# =============================================================================
# Elasticsearch — Exact Search
# =============================================================================

_es_client: AsyncElasticsearch | None = None


async def get_es_client(settings: SettingsDep) -> AsyncElasticsearch:
    global _es_client
    if _es_client is None:
        kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
        if settings.ELASTICSEARCH_USERNAME:
            kwargs["basic_auth"] = (
                settings.ELASTICSEARCH_USERNAME,
                settings.ELASTICSEARCH_PASSWORD,
            )
        _es_client = AsyncElasticsearch(**kwargs)
    return _es_client


ElasticsearchDep = Annotated[AsyncElasticsearch, Depends(get_es_client)]


# =============================================================================
# Redis — Cache + Streams
# =============================================================================

_redis_client: aioredis.Redis | None = None


async def get_redis(settings: SettingsDep) -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            password=settings.REDIS_PASSWORD or None,
            db=settings.REDIS_DB_CACHE,
            decode_responses=True,
        )
    return _redis_client


RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]


# =============================================================================
# Temporal — Workflow Orchestration
# =============================================================================

_temporal_client: TemporalClient | None = None


async def get_temporal_client(settings: SettingsDep) -> TemporalClient:
    global _temporal_client
    if _temporal_client is None:
        _temporal_client = await TemporalClient.connect(
            settings.TEMPORAL_ADDRESS,
            namespace=settings.TEMPORAL_NAMESPACE,
        )
    return _temporal_client


TemporalDep = Annotated[TemporalClient, Depends(get_temporal_client)]


# =============================================================================
# Supabase — Document Vault, Relational DB, Auth
# Uses service role key: bypasses RLS (backend-only access)
# =============================================================================

_supabase_client: Client | None = None


def get_supabase(settings: SettingsDep) -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _supabase_client


SupabaseDep = Annotated[Client, Depends(get_supabase)]


# =============================================================================
# Auth — JWT Bearer token verification
# =============================================================================

bearer_scheme = HTTPBearer(auto_error=False)

# --- Verified-token cache -----------------------------------------------------
# ponytail: tiny in-process TTL cache so a valid token skips the Supabase Auth
# round-trip on every request. Revocation is still enforced — just up to
# AUTH_CACHE_TTL_SECONDS stale. Per-worker; entries keyed by token hash.
_AUTH_CACHE_MAX = 2048
_auth_cache: dict[str, tuple[float, dict]] = {}


def _auth_cache_get(token: str) -> dict | None:
    entry = _auth_cache.get(hashlib.sha256(token.encode()).hexdigest())
    if entry is None:
        return None
    expires_at, user = entry
    if time.monotonic() >= expires_at:
        _auth_cache.pop(hashlib.sha256(token.encode()).hexdigest(), None)
        return None
    return user


def _auth_cache_put(token: str, user: dict, ttl: int) -> None:
    if ttl <= 0:
        return
    if len(_auth_cache) >= _AUTH_CACHE_MAX:
        now = time.monotonic()
        for k in [k for k, (exp, _) in _auth_cache.items() if now >= exp]:
            _auth_cache.pop(k, None)
        if len(_auth_cache) >= _AUTH_CACHE_MAX:
            _auth_cache.clear()  # bounded worst case; rare
    _auth_cache[hashlib.sha256(token.encode()).hexdigest()] = (time.monotonic() + ttl, user)


async def resolve_token(token: str, settings: Settings) -> dict | None:
    """Verify a bearer token and return the Kairos user dict, or None if it is not valid.

    **The single token-verification path.** The OPA middleware used to carry its own copy —
    `jose.jwt.decode(..., algorithms=["HS256"])` against `SUPABASE_JWT_SECRET` — which could
    never succeed: this project's Supabase issues **ES256** tokens signed with an asymmetric
    JWT signing key, so every real token failed to decode, the middleware saw an anonymous
    caller, and authorization silently did nothing. Verification belongs to Supabase, which
    knows its own signing keys and rotation; duplicating it here meant one copy could be
    (and was) wrong without anything failing loudly.

    Returns None rather than raising, so the two callers can choose their own failure: the
    dependency raises 401, the middleware denies or falls through in dev.
    """
    # Internal service bypass — Go connector and Celery workers call with INTERNAL_API_KEY
    if settings.INTERNAL_API_KEY and token == settings.INTERNAL_API_KEY:
        return {"user_id": "service-kairos-connector", "email": "connector@internal", "role": "admin", "site_id": "SITE_001", "sub": "service-connector"}

    # Fast path: recently-verified token — skips the Supabase Auth round-trip. The middleware
    # runs before the dependency, so it populates this and the dependency reads it back: one
    # round-trip per token per TTL, not two.
    cached = _auth_cache_get(token)
    if cached is not None:
        return cached

    try:
        # Use a fresh client with anon key for token verification — keeps the global
        # service-role client's session clean (auth.get_user mutates client state).
        verify_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        result = await asyncio.to_thread(lambda: verify_client.auth.get_user(token))
        user = result.user
        if not user:
            return None
    except Exception as exc:
        log.info("auth.token_rejected", error=str(exc))
        return None

    meta = user.user_metadata or {}
    user_dict = {
        "user_id": str(user.id),
        "email": user.email,
        # The app role lives in user_metadata. The token's top-level `role` is Supabase's
        # Postgres role ("authenticated"), which matches no entry in kairos.rego.
        "role": meta.get("role", "field_worker"),
        "site_id": meta.get("site_id", ""),
        "sub": str(user.id),
    }
    _auth_cache_put(token, user_dict, settings.AUTH_CACHE_TTL_SECONDS)
    return user_dict


async def get_current_user(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> dict:
    """
    Decode and validate the JWT bearer token.
    In development, if no token is provided and `dev_bypass_allowed`, returns a mock user.
    In production, raises 401 for missing/invalid tokens.
    """
    if not credentials:
        if settings.dev_bypass_allowed:
            # Allow unauthenticated access in dev for rapid iteration
            log.warning("auth.bypass", reason="dev_bypass_allowed, no token provided")
            return {"user_id": "dev-user", "role": "engineer", "site_id": "SITE_001"}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await resolve_token(credentials.credentials, settings)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUserDep = Annotated[dict, Depends(get_current_user)]


# =============================================================================
# Role-Based Access Control helpers
# =============================================================================

def require_role(*roles: str):
    """
    Dependency factory: raises 403 if the current user's role is not in `roles`.
    Usage: Depends(require_role("engineer", "admin"))
    """
    async def _check(current_user: CurrentUserDep) -> dict:
        user_role = current_user.get("role", "")
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' does not have access. Required: {list(roles)}",
            )
        return current_user
    return _check


def site_scope(current_user: dict, requested: str | None) -> str | None:
    """Resolve the `site_id` a site-filtered read may actually see.

    Tenancy was previously a **client-supplied query parameter**: `GET /assets?site_id=X`
    and the two `/compliance` reads passed whatever the caller typed straight into Cypher, so
    any authenticated user could read any site by editing the URL. The site now comes from the
    verified token, not the request.

    - `admin` keeps the cross-site view (`requested`, or `None` for all sites).
    - Everyone else is pinned to their own `site_id`; asking for someone else's is a 403 rather
      than a silent re-scope, so a caller is never told it read one site while reading another.
    - An account with no `site_id` gets nothing. Fail closed: a blank site used to mean
      "no filter" — i.e. every site — which is exactly backwards.

    ponytail: single-site MVP, so this is the whole tenancy boundary for reads that already
    carry a site axis. Search/documents have no site column yet — see the note in status.md.
    """
    if current_user.get("role") == "admin":
        return requested
    own = current_user.get("site_id") or ""
    if not own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has no site assigned; ask an administrator to set one.",
        )
    if requested and requested != own:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not permitted to read site '{requested}'.",
        )
    return own


# =============================================================================
# Path-parameter validation
# =============================================================================

def valid_quarantine_item_id(item_id: str) -> str:
    """Reject a malformed `quarantine_items.item_id` before it reaches PostgREST.

    `item_id` is a UUID column (`db/schema.sql`), so a non-UUID path segment makes
    PostgREST raise `22P02 invalid input syntax for type uuid`; supabase-py turns that
    into an exception and `main.py`'s global handler turns *that* into a **500**. The
    caller gets a server error for what is only an id that does not exist, and the
    handler's own 404 branch is never reached because the query raises first.

    404 rather than 422: all four routes already answer 404 for a well-formed-but-absent
    id, and to a reviewer both are the same situation - "that item is not there".
    Splitting one user-visible outcome across two status codes on id *shape* would leak
    the column type into the API contract.

    ponytail: guards the id, not the lookup. The four handlers keep their own `select`
    (different columns, different 409 wording); consolidating those is a refactor, not
    this bug. `/events/deviation-flag/{item_id}/resolve` reads the same table, so it
    shares the guard and its slightly more general "quarantine item" wording.
    """
    try:
        uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarantine item '{item_id}' not found",
        ) from None
    return item_id


QuarantineItemIdDep = Annotated[str, Depends(valid_quarantine_item_id)]


def valid_offboarding_session_id(session_id: str) -> str:
    """Reject a malformed `offboarding_sessions.id` before it reaches PostgREST.

    Same failure as `valid_quarantine_item_id` above, on a different table: the column is
    UUID, so a non-UUID path segment raised `22P02` and surfaced as a **500** on a public
    route. `GET /elicitation/offboarding/sessions` is the case that exposed it — there is
    no `/sessions` route, so the literal was matched by `/offboarding/{session_id}` and
    looked up as an id. A route that does not exist must answer 404, not 500.

    Fixing the shape is only half of it: the handlers also called `.single()`, which raises
    `PGRST116` on zero rows, so a *well-formed* id for an absent programme 500'd too and
    each handler's own 404 branch was unreachable. Those now use `.maybe_single()`.

    404 rather than 422, for the reason given above — one user-visible outcome ("that
    programme is not there") should not split across two status codes on id shape.

    ponytail: a sibling of the quarantine guard rather than a generalisation of it. Merging
    the two into one factory is a refactor of working code, not this bug.
    """
    try:
        uuid.UUID(session_id)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found",
        ) from None
    return session_id


OffboardingSessionIdDep = Annotated[str, Depends(valid_offboarding_session_id)]
