"""
Demo tenant, kept apart from real data inside the same stores.

WHY THIS EXISTS
  The public demo login shows a large showcase plant. Its rows live in the same Supabase, Neo4j,
  Qdrant and Elasticsearch as the real data (no second deployment), so something has to keep the
  two apart. The rule is one-directional and cheap to check:

    * every showcase row is marked: an asset id, event id, MoC id or off-boarding person id that
      starts with `DEMO-`, a site id in `DEMO_SITES`, or a document whose `access_tags.site_id` is
      in `DEMO_SITES`;
    * a real account never reads a marked row (`scope`, `asset_guard`, `search_site_filter`);
    * the `demo` role reads everything, real and showcase, as it always has, and (once the write
      guard lands) may write only to marked rows.

  Marker columns are listed once, below, per table. No schema change is needed: every table that
  can hold showcase data already has a text column the loader controls.

  Filters are applied in the query, never after it. A Python filter on a paginated or aggregated
  result breaks `count` and `range` (same rule as `corpus.REAL_ASSET_CYPHER`).

WHAT THIS DELIBERATELY DOES NOT DO
  It does not hide a showcase row that is fetched by its own id: the id is the capability, and a
  real account has no way to learn one. List, count, aggregate and search reads are the leak
  surface, and `tests/test_tenant_isolation.py` fails the build if a new one is added unscoped.
"""

import asyncio
import time
from collections.abc import Mapping

import structlog
from fastapi import HTTPException, status

log = structlog.get_logger(__name__)

DEMO_PREFIX = "DEMO-"
DEMO_SITES = ("SITE_DEMO", "SITE_DEMO_B")

# PostgREST `like` takes `*` as the wildcard.
_LIKE = f"{DEMO_PREFIX}*"
_SITES_IN = "(" + ",".join(DEMO_SITES) + ")"


def is_demo_user(user: Mapping | None) -> bool:
    """The demo identity is the `demo` role. `None` (internal callers) is a real caller."""
    return bool(user) and user.get("role") == "demo"


# Whether every caller sees the showcase plant (`SHOWCASE_VISIBLE_TO_ALL`, set at startup). Off in code so
# the isolation tests and any script that never starts the API behave as before; the shipped `.env.example`
# turns it on. The demo role always sees it, and its WRITES stay fenced to showcase rows either way.
VISIBLE_TO_ALL = False


def sees_showcase(user: Mapping | None) -> bool:
    """Whether this caller's READS include the showcase plant."""
    return VISIBLE_TO_ALL or is_demo_user(user)


def is_demo_id(value: str | None) -> bool:
    return bool(value) and value.startswith(DEMO_PREFIX)


def is_demo_site(site_id: str | None) -> bool:
    return site_id in DEMO_SITES


def feeds_statistics(user: Mapping | None, asset_id: str | None = None) -> bool:
    """Whether an action may feed a statistic that real mode reads (the circuit breaker's overrides,
    the model gate's validation corpus). A showcase action, by the demo role or on a showcase asset,
    must not: the action still succeeds, it just leaves the real statistics alone."""
    return not (is_demo_user(user) or is_demo_id(asset_id))


# --- what the demo role may write ------------------------------------------------------------
# The demo role is not an admin: a role gate that names `engineer` or `reliability` admits it, one
# that names only `admin` does not (the model gate and provider probes spend quota and write
# statistics, so they stay closed). Every write it does make must land on a showcase row, which the
# guards below check, and a route that is not in DEMO_WRITE_ALLOWED is refused before its handler
# runs (`dependencies.demo_write_fence`). `tests/test_tenant_isolation.py` fails when an allowed
# route has no guard in its handler.

DEMO_ACTS_AS = frozenset({"engineer", "reliability"})

DEMO_DENIED = "The demo account can only change the showcase plant."


def has_role(user: Mapping | None, *roles: str) -> bool:
    """`user.role in roles`, and also true for the demo role when `roles` names engineer or reliability."""
    role = (user or {}).get("role")
    return role in roles or (role == "demo" and bool(DEMO_ACTS_AS & set(roles)))


def _deny() -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DEMO_DENIED)


def guard_asset(user: Mapping | None, asset_id: str | None) -> None:
    """A demo write that names an asset must name a showcase one (and must name one)."""
    if is_demo_user(user) and not is_demo_id(asset_id):
        _deny()


def guard_site(user: Mapping | None, site_id: str | None) -> None:
    if is_demo_user(user) and not is_demo_site(site_id):
        _deny()


def guard_document(user: Mapping | None, row: Mapping | None) -> None:
    if is_demo_user(user) and not is_demo_document(row):
        _deny()


# A showcase quarantine item with no equipment of its own (an off-boarding answer, an ad-hoc note)
# hangs off this placeholder showcase asset, so it is recognised as showcase by its asset id. The
# loader creates the asset. Without it the item would carry a NULL asset, which means "real".
DEMO_GENERAL_ASSET = f"{DEMO_PREFIX}GENERAL"


def guard_person(user: Mapping | None, personnel_id: str | None) -> None:
    """A demo off-boarding programme must be about a showcase person."""
    if is_demo_user(user) and not is_demo_id(personnel_id):
        _deny()


async def work_order_asset(supabase, work_order_id: str) -> str | None:
    """The asset a work-order id or tag resolves to (work-order event, then asset id, then confirmed alias)."""
    tag = (work_order_id or "").strip()

    def lookup() -> str | None:
        wo = (
            supabase.table("operational_events").select("asset_id")
            .filter("payload->>work_order_id", "eq", tag).limit(1).execute()
        )
        if wo.data and wo.data[0].get("asset_id"):
            return wo.data[0]["asset_id"]
        direct = supabase.table("assets").select("asset_id").eq("asset_id", tag).limit(1).execute()
        if direct.data:
            return direct.data[0]["asset_id"]
        alias = (
            supabase.table("asset_alias_map").select("canonical_asset_id")
            .eq("alias", tag).eq("confirmed", True).limit(1).execute()
        )
        return alias.data[0]["canonical_asset_id"] if alias.data else None

    return await asyncio.to_thread(lookup)


async def guard_work_order(supabase, user: Mapping | None, work_order_id: str) -> None:
    """A demo voice note names a work order or an asset tag; it must resolve to a showcase asset.

    Same resolution the voice worker does, done before the upload so a demo note can never be filed
    against a real asset.
    """
    if not is_demo_user(user):
        return
    guard_asset(user, await work_order_asset(supabase, work_order_id))


# table -> (key column, marker column). The marker is the column a showcase row is recognised by:
# an asset or person id with the `DEMO-` prefix, or (events) a showcase site id.
_ROW_MARKERS = {
    "operational_events": ("event_id", "site_id"),
    "briefs": ("brief_id", "asset_id"),
    "knowledge_conflicts": ("conflict_id", "asset_id"),
    "quarantine_items": ("item_id", "asset_id"),
    "moc_items": ("moc_id", "asset_id"),
    "elicitation_sessions": ("session_id", "asset_id"),
    "offboarding_sessions": ("id", "personnel_id"),
    "documents": ("document_id", None),
}


async def is_showcase_row(supabase, table: str, key) -> bool | None:
    """Whether the stored row is a showcase row; None when there is no such row. A row with a NULL
    marker is real by definition."""
    key_col, marker = _ROW_MARKERS[table]
    columns = "access_tags" if table == "documents" else marker
    result = await asyncio.to_thread(
        lambda: supabase.table(table).select(columns).eq(key_col, key).limit(1).execute()
    )
    row = (result.data or [None])[0]
    if row is None:
        return None
    if table == "documents":
        return is_demo_document(row)
    if marker == "site_id":
        return is_demo_site(row.get(marker))
    return is_demo_id(row.get(marker))


async def guard_row(supabase, user: Mapping | None, table: str, key) -> None:
    """A demo action on an existing row must be on a showcase row. A missing row passes: the handler
    answers 404 as it always did."""
    if is_demo_user(user) and await is_showcase_row(supabase, table, key) is False:
        _deny()


# By-id reads: the path parameter that names a record, and where to look it up. A real account asking
# for a showcase record gets the 404 a missing record gets (`dependencies.showcase_read_fence`).
READ_BY_ID_TABLE = {
    "document_id": "documents", "brief_id": "briefs", "conflict_id": "knowledge_conflicts", "moc_id": "moc_items",
    "event_id": "operational_events", "session_id": "offboarding_sessions",
}


async def names_showcase_record(supabase, path_params: Mapping) -> bool:
    """True when any path parameter of the request names a showcase record."""
    for name, value in path_params.items():
        if name == "asset_id" and is_demo_id(value):
            return True
        if name == "site_id" and is_demo_site(value):
            return True
        if name == "work_order_id" and is_demo_id(await work_order_asset(supabase, value)):
            return True
        if name in READ_BY_ID_TABLE and await is_showcase_row(supabase, READ_BY_ID_TABLE[name], value):
            return True
    return False


# Routes the demo role may call with a write method. Each handler guards its own target
# (`guard_*`), except the ones in DEMO_UNGUARDED, which only append to the audit log.
DEMO_UNGUARDED = frozenset({
    ("POST", "/auth/logout"),
    ("POST", "/auth/refresh"),
    ("POST", "/search/synthesize"),
    ("POST", "/search/synthesize/stream"),
    ("POST", "/search/feedback"),
    ("POST", "/search/rca-pack"),
})
DEMO_GUARDED = frozenset({
    ("POST", "/annotations/"),
    ("POST", "/assets/"),
    ("POST", "/assets/bulk"),
    ("POST", "/assets/{asset_id}/aliases/{alias}/confirm"),
    ("POST", "/assets/{asset_id}/aliases/{alias}/reject"),
    ("POST", "/briefs/{brief_id}/ack"),
    ("POST", "/briefs/{brief_id}/countersign"),
    ("POST", "/briefs/{brief_id}/feedback"),
    ("POST", "/elicitation/trigger"),
    ("POST", "/elicitation/{work_order_id}/responses"),
    ("POST", "/elicitation/{work_order_id}/voice"),
    ("POST", "/elicitation/offboarding"),
    ("POST", "/elicitation/offboarding/{session_id}/responses"),
    ("POST", "/governance/conflicts/{conflict_id}/resolve"),
    ("POST", "/governance/quarantine/{item_id}/promote"),
    ("POST", "/governance/quarantine/{item_id}/dispute"),
    ("POST", "/governance/quarantine/{item_id}/request-info"),
    ("POST", "/governance/moc/{moc_id}/approve"),
    ("POST", "/events/work-order"),
    ("POST", "/events/ptw"),
    ("POST", "/events/shift-handover"),
    ("POST", "/events/alarm"),
    ("POST", "/events/tag-out"),
    ("POST", "/events/inspection-complete"),
    ("POST", "/events/deviation-flag"),
    ("POST", "/events/deviation-flag/{item_id}/resolve"),
    ("POST", "/events/plant-state"),
    ("POST", "/events/{event_id}/ack"),
    ("POST", "/documents/ingest"),
    ("POST", "/documents/{document_id}/ocr-review/release"),
    ("POST", "/documents/{document_id}/ocr-review/reject"),
    ("POST", "/documents/{document_id}/topology/verify"),
    ("POST", "/documents/{document_id}/supersede"),
})
DEMO_WRITE_ALLOWED = DEMO_UNGUARDED | DEMO_GUARDED


# --- Supabase / PostgREST -------------------------------------------------------------------

def scope(query, user: Mapping | None, column: str, *, nullable: bool = False):
    """Hide showcase rows from a real caller on a `DEMO-` prefixed text column.

    `nullable=True` keeps rows whose column is NULL (a quarantine item with no asset is real by
    definition: showcase rows always carry a showcase asset). Without it PostgREST's
    `not.like` would drop NULLs.
    """
    if sees_showcase(user):
        return query
    if nullable:
        return query.or_(f"{column}.is.null,{column}.not.like.{_LIKE}")
    return query.not_.like(column, _LIKE)


def scope_site(query, user: Mapping | None, column: str = "site_id", *, nullable: bool = False):
    """Hide showcase sites from a real caller. Same shape as `scope`, for a site column."""
    if sees_showcase(user):
        return query
    if nullable:
        return query.or_(f"{column}.is.null,{column}.not.in.{_SITES_IN}")
    return query.not_.in_(column, list(DEMO_SITES))


def scope_document_site(query, user: Mapping | None):
    """Hide showcase documents (`access_tags.site_id`) from a real caller."""
    if sees_showcase(user):
        return query
    col = "access_tags->>site_id"
    return query.or_(f"{col}.is.null,{col}.not.in.{_SITES_IN}")


# --- Neo4j ----------------------------------------------------------------------------------

# Cypher guard for a query that binds assets as `a`. Parameterised (not inlined per caller) so one
# constant serves both audiences, and a caller that forgets to pass `hide_demo` fails loudly with
# "expected parameter" instead of silently showing showcase assets to a real account.
DEMO_VISIBLE_CYPHER = f"($hide_demo = false OR NOT a.asset_id STARTS WITH '{DEMO_PREFIX}')"

# The site pin for a query that binds assets as `a` and takes `$site_id` (None: every site). A caller
# pinned to a site reads that site, plus the showcase plant when the caller may see it (`$hide_demo`
# false); it never reads another real site.
SITE_PIN_CYPHER = (
    f"($site_id IS NULL OR a.site_id = $site_id OR ($hide_demo = false AND a.asset_id STARTS WITH '{DEMO_PREFIX}'))"
)


def on_visible_site(user: Mapping | None, row_site: str | None, pinned: str | None) -> bool:
    """Whether a row on `row_site` is readable by a caller whose `site_scope` answer is `pinned`.

    `pinned` None means every site (admin, demo). Otherwise the caller's own site, plus showcase sites
    for a caller that sees the showcase plant.
    """
    return pinned is None or row_site == pinned or (sees_showcase(user) and is_demo_site(row_site))


def pin_site(query, user: Mapping | None, pinned: str | None, column: str = "site_id"):
    """PostgREST twin of `on_visible_site`: narrow `query` to the caller's site (and the showcase sites)."""
    if not pinned:
        return query
    if sees_showcase(user):
        return query.or_(f"{column}.eq.{pinned},{column}.in.{_SITES_IN}")
    return query.eq(column, pinned)


def present_asset(row: dict) -> dict:
    """The row as the UI should show it: the `DEMO-GENERAL` placeholder asset (it exists only so an item
    with no equipment still carries a showcase marker) is shown as no asset at all."""
    if row.get("asset_id") == DEMO_GENERAL_ASSET:
        row["asset_id"] = None
    return row


def link_allowed(document_is_showcase: bool, asset_id: str | None) -> bool:
    """Whether the ingest pipeline may link a document to a resolved asset. A showcase document links only to
    showcase assets, so it can never pile edges onto a real asset (the extractor does name assets a page does
    not). An unresolved tag (None) is left to the caller, as before."""
    return not (document_is_showcase and asset_id and not is_demo_id(asset_id))


def hides_demo(user: Mapping | None) -> bool:
    """Value for the `hide_demo` Cypher parameter: true unless this caller's reads include the showcase."""
    return not sees_showcase(user)


# --- Elasticsearch / Qdrant -----------------------------------------------------------------
# Showcase documents and assets are indexed into a sibling collection or index named `<base>_demo`,
# in the same Qdrant cluster and Elasticsearch. Real callers never query it; the demo role queries it
# as well as the real one. Creating the Qdrant collection is a cloud write, so it is done by the
# loader (`scripts/init_demo_stores.py`) and never at startup: nothing here adds it to
# `ensure_collections`.

DEMO_STORE_SUFFIX = "_demo"


def demo_store(base: str) -> str:
    """Name of the showcase sibling of a collection or index."""
    return base + DEMO_STORE_SUFFIX


def store_for(base: str, *, demo: bool) -> str:
    """Where a write goes: the sibling for showcase data, the base otherwise."""
    return demo_store(base) if demo else base


def is_demo_document(row: Mapping | None) -> bool:
    """A `documents` row (or pipeline metadata) that belongs to the showcase.

    Marked by `access_tags.site_id`, which the upload route stamps from the uploader's site; the
    pipeline metadata carries `site_id` directly, and a showcase asset is a second signal.
    """
    row = row or {}
    tags = row.get("access_tags") or {}
    return (
        is_demo_site(tags.get("site_id"))
        or is_demo_site(row.get("site_id"))
        or is_demo_id(row.get("asset_id"))
    )


# --- audit_log ------------------------------------------------------------------------------
# An audit row has no asset or site column, so it is marked three ways: the actor is the demo
# identity, the entity is a showcase id, or the row says so in `details.tenant` (system rows, such
# as an SLA escalation of a showcase conflict, that no demo user performed).

_DEMO_IDS_TTL = 600.0
# Fetched-at starts at -inf, not 0.0: `time.monotonic()` is the machine's uptime, so on a host booted less
# than ten minutes ago "now minus 0" is under the TTL and the first call would return the empty list.
_demo_ids: tuple[float, list[str]] = (float("-inf"), [])


async def demo_user_ids(supabase) -> list[str]:
    """Auth user ids whose `app_metadata.role` is `demo`, cached for ten minutes.

    ponytail: one `list_users` call (the project has a handful of accounts) instead of a column
    on every audit insert. Add `details.tenant` at the insert sites if the account list grows.
    """
    global _demo_ids
    if time.monotonic() - _demo_ids[0] < _DEMO_IDS_TTL:
        return _demo_ids[1]
    from api.dependencies import auth_metadata

    try:
        users = await asyncio.to_thread(lambda: supabase.auth.admin.list_users())
        ids = [u.id for u in users if auth_metadata(u).get("role") == "demo"]
    except Exception as exc:  # noqa: BLE001 — fail closed: keep the last good list, else hide nothing extra
        log.warning("tenant.demo_users_lookup_failed", error=str(exc))
        return _demo_ids[1]
    _demo_ids = (time.monotonic(), ids)
    return ids


def audit_marker(asset_id: str | None) -> dict:
    """Extra `audit_log.details` for a system row about showcase data, so `scope_audit` can hide it."""
    return {"tenant": "demo"} if is_demo_id(asset_id) else {}


async def scope_actor(query, user: Mapping | None, supabase, column: str):
    """Hide rows performed by the demo identity (`column` holds an auth user id) from a real caller."""
    if sees_showcase(user):
        return query
    ids = await demo_user_ids(supabase)
    return query.not_.in_(column, ids) if ids else query


async def scope_audit(query, user: Mapping | None, supabase):
    """Hide showcase audit rows from a real caller."""
    if sees_showcase(user):
        return query
    query = await scope_actor(query, user, supabase, "performed_by")
    query = query.or_(f"entity_id.is.null,entity_id.not.like.{_LIKE}")
    return query.or_("details->>tenant.is.null,details->>tenant.neq.demo")
