"""
OPA middleware — policy enforcement for write operations and sensitive reads.
Calls kairos-opa for the enforced routes; denies with 403 if OPA returns false.
Skips the check when `dev_bypass_allowed` and no Authorization header (dev bypass, same as auth).

Fails **closed**: if OPA cannot be reached, the request is denied outside dev. An authorization
layer that answers "allow" when it is down is not an authorization layer.
"""


import httpx
import structlog
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from api.dependencies import resolve_token

log = structlog.get_logger(__name__)

_SKIP_PREFIXES = ("/health", "/auth", "/docs", "/openapi", "/redoc")
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# OPTIONS is deliberately absent: this middleware is the outermost one, so it sees the CORS
# preflight before CORSMiddleware does — and a preflight carries no Authorization header, so
# enforcing it would 401 every cross-origin request the browser app makes.
_READ_METHODS = frozenset({"GET", "HEAD"})

# Routes mapped to OPA action names from kairos.rego
_ACTION_MAP = (
    ("/governance/quarantine", "promote_quarantine"),
    ("/governance/moc", "resolve_admin_conflict"),
    ("/governance/conflicts", "resolve_admin_conflict"),
    ("/documents", "ingest_document"),
    ("/assets", "write_assets"),
    # The Copilot's POSTs get their own action so the read-only `demo` role can use them without
    # being granted the `write_api` catch-all. Every other role gets it from the catch-all as before.
    ("/search/synthesize", "synthesize"),
    # The operational-event feed. Listed by route, not by the `/events` prefix, so field-worker
    # flows (deviation-flag, ack) and the engineer-only plant-state stay on the `write_api` catch-all.
    ("/events/work-order", "ingest_event"),
    ("/events/ptw", "ingest_event"),
    ("/events/shift-handover", "ingest_event"),
    ("/events/alarm", "ingest_event"),
    ("/events/tag-out", "ingest_event"),
    ("/events/inspection-complete", "ingest_event"),
)

# Inbound webhooks authenticated by their own HMAC, not a user token. The plant's MoC system has
# no Kairos login, so OPA (which needs a user) would reject every legitimate call. Exact paths:
# `routers/governance.py` makes the signature mandatory wherever auth is enforced, so exempting the
# route here removes a layer that could never have applied, not a layer that was doing work.
_SIGNED_WEBHOOKS = frozenset({("POST", "/governance/moc/webhook")})

# Shell context every authenticated role needs, sitting under an otherwise-gated prefix.
# `components/app-shell.tsx` renders plant state for *every* persona — a field worker who cannot
# see that the plant is in shutdown is a safety regression, not a closed boundary. Checked first,
# so it wins over the prefix map below. (Declaring a plant state is a POST and stays gated.)
_READ_ALLOW_PREFIXES = ("/events/plant-state",)

# Reads that leak governed material to roles the UI already refuses to show it to.
# `use-role.ts` gates these surfaces client-side; without this map the backend enforced
# nothing, so the audit trail and the compliance cockpit were readable by any authenticated
# role — including `field_worker` — by calling the API directly.
#
# Derived from the FE route table, not invented here: each action grants exactly the API
# prefixes that the routes of that role group actually call. `read_nonconformance` is the one
# split — `/compliance/nonconformance` reads conflicts + quarantine, so the compliance auditor
# needs those two `/governance` children while still being kept out of the model gate, MoC
# approvals and the circuit breaker.
#
# ORDER MATTERS: first prefix match wins, so the two `/governance` children must precede the
# generic `/governance` entry or they would resolve to `read_governance` and lock compliance out.
#
# Deliberately narrow. `/search`, `/briefs`, `/assets`, `/elicitation` and `/annotations` reads
# stay unenforced: the UI treats them as open to every authenticated role, so gating them would
# break the field-worker flows without closing a boundary.
_READ_ACTION_MAP = (
    ("/audit-log", "read_audit"),
    ("/compliance", "read_compliance"),
    ("/governance/conflicts", "read_nonconformance"),
    ("/governance/quarantine", "read_nonconformance"),
    ("/governance", "read_governance"),
    ("/documents", "read_documents"),
    ("/events", "read_events"),
)

# The read-only `demo` role is deny-by-default, so the reads other roles leave unenforced must be
# named for it. Anything under neither this map nor `_READ_ACTION_MAP` resolves to `_DEMO_FALLBACK`,
# which no rule grants (offboarding/personnel, annotations, elicitation, ...). Only the demo role
# pays the extra OPA call; for every other role these GETs stay unenforced, as the UI expects.
_DEMO_READ_ACTION_MAP = (
    ("/search", "read_search"),
    ("/briefs", "read_briefs"),
    ("/assets", "read_assets"),
)
_DEMO_FALLBACK = "read_other"


def action_for(method: str, path: str, role: str | None = None) -> str | None:
    """OPA action for this request, or None when the route is not policy-enforced.

    `role` only matters for "demo": see `_DEMO_READ_ACTION_MAP`."""
    if any(path.startswith(p) for p in _SKIP_PREFIXES):
        return None
    if (method, path) in _SIGNED_WEBHOOKS:
        return None
    if method in _WRITE_METHODS:
        for prefix, name in _ACTION_MAP:
            if path.startswith(prefix):
                return name
        return "write_api"  # non-sensitive catch-all; allowed by rego for any authenticated role
    if method in _READ_METHODS:
        if any(path.startswith(p) for p in _READ_ALLOW_PREFIXES):
            return None
        for prefix, name in _READ_ACTION_MAP:
            if path.startswith(prefix):
                return name
        if role == "demo":
            return next((n for p, n in _DEMO_READ_ACTION_MAP if path.startswith(p)), _DEMO_FALLBACK)
    return None


class OPAMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, opa_url: str, settings, debug: bool = False):
        super().__init__(app)
        self.opa_url = f"{opa_url}/v1/data/kairos/authz/allow"
        self.settings = settings
        self.debug = debug

    async def dispatch(self, request: Request, call_next):
        # `scope["path"]`, never `request.url.path`: url is rebuilt from the Host header, so
        # `Host: x/health` turns `/events/work-order` into `/health/events/work-order`, which the
        # skip list then treats as exempt and OPA is never asked. The scope path is what routes.
        path = request.scope["path"]
        action = action_for(request.method, path)
        user = None
        if action is None:
            # Unenforced for most roles, but the read-only demo role is deny-by-default. Only a
            # GET that carries a token costs a lookup, and it is the cached one the route repeats.
            if request.method not in _READ_METHODS:
                return await call_next(request)
            user = await self._user_from_request(request)
            action = action_for(request.method, path, (user or {}).get("role"))
            if action is None:
                return await call_next(request)

        user = user or await self._user_from_request(request)
        if user is None:
            if self.debug:
                return await call_next(request)  # no token in dev → pass through
            return JSONResponse({"detail": "Authentication required"}, status_code=401)

        allowed = await self._ask_opa(user, action, path)
        if not allowed:
            log.info(
                "opa.denied",
                user_id=user.get("user_id"),
                role=user.get("role"),
                action=action,
                path=path,
            )
            return JSONResponse(
                {"detail": f"Forbidden: role '{user.get('role')}' is not permitted to perform this action"},
                status_code=403,
            )
        return await call_next(request)

    async def _user_from_request(self, request: Request) -> dict | None:
        """Identify the caller using the app's ONE token-verification path.

        This used to decode the JWT itself with a shared HS256 secret. Supabase issues **ES256**
        tokens here, so that decode always failed, every caller looked anonymous, and the whole
        middleware degraded to the dev pass-through — authorization that ran but never decided.
        `resolve_token` delegates to Supabase (which owns the signing keys) and shares the auth
        cache with `get_current_user`, so this costs no extra round-trip.
        """
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        return await resolve_token(auth[7:], self.settings)

    async def _ask_opa(self, user: dict, action: str, resource: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(
                    self.opa_url,
                    json={"input": {"user": user, "action": action, "resource": resource}},
                )
                return resp.status_code == 200 and resp.json().get("result", False)
        except Exception as exc:
            # Fail closed outside dev. This used to `return True` unconditionally, so OPA being
            # down — or unreachable, or misconfigured — silently disabled authorization
            # everywhere instead of taking the API offline. In dev the pass-through stays, so a
            # stack without the OPA container still works.
            log.error("opa.unreachable", error=str(exc), action=action, fail_open=self.debug)
            return self.debug
