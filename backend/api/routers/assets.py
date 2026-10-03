"""
Assets router — Layer 1: Deterministic MDM Backbone.
Manages canonical asset identities, alias resolution, and the asset hierarchy.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import shortuuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import (
    CurrentUserDep,
    ElasticsearchDep,
    Neo4jDep,
    SettingsDep,
    SupabaseDep,
    require_role,
    site_scope,
)
from api.models.asset import AssetBulkImport, AssetCreate
from api.services import tenant
from api.services.corpus import document_rows, partition_test_artifacts
from api.services.coverage import CoverageService
from api.services.graph import GraphService
from api.services.ot_coverage import OtCoverageService

log = structlog.get_logger(__name__)
router = APIRouter()

_SITE_ASSET_CAP = 10000


async def resolve_canonical_asset_id(asset_id: str, graph: GraphService, supabase) -> str | None:
    """Resolve a tag to its canonical asset_id.

    Returns `asset_id` unchanged if it's already a canonical graph node; if it's a
    **confirmed** alias in `asset_alias_map` (e.g. `P-101` → `EQ-101`), returns the
    canonical id; otherwise `None`. Lets `/assets/{id}/*` accept legacy tag aliases
    instead of 404ing.
    """
    if await graph.get_asset(asset_id):
        return asset_id
    res = await asyncio.to_thread(
        lambda: supabase.table("asset_alias_map")
        .select("canonical_asset_id")
        .eq("alias", asset_id)
        .eq("confirmed", True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]["canonical_asset_id"]
    return None


async def scoped_asset(graph: GraphService, asset_id: str, current_user: dict) -> dict:
    """The asset node, or 404 when it does not exist **or** sits on a site the caller may not see.

    One 404 for both, so the response does not reveal that another site holds that id. `site_scope`
    returns None for admin (every site) and the caller's own site otherwise, and fails closed for an
    account with no site. The showcase plant is also readable when the caller may see it.
    """
    asset = await graph.get_asset(asset_id)
    site = site_scope(current_user, None)
    if not asset or not tenant.on_visible_site(current_user, asset.get("site_id"), site):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found")
    return asset


def _id_prefix(current_user: dict) -> str:
    """Generated asset ids: `DEMO-` for the demo role, so what it registers is showcase data."""
    return tenant.DEMO_PREFIX if tenant.is_demo_user(current_user) else "ASSET-"


def partition_import_rows(
    rows: list, existing_ids: set[str], allowed_site: str | None
) -> dict:
    """
    Split a golden-record import into create / skip / reject. Pure — the caller supplies the
    set of ids already in the graph and the site the token permits.

    Three rejection classes, all of which a real EAM export produces:

    * **already_present** — the asset is in the graph. Skipped, never overwritten. Neo4j's
      `ON CREATE SET` already refuses to clobber, but Supabase writes with `upsert`, which
      would happily replace `identity_confirmed_by` with a re-import. Filtering here means the
      two stores cannot disagree about who confirmed an identity.
    * **duplicate_in_payload** — the same `asset_id` twice in one file. The first wins; the
      rest are reported rather than silently collapsed, because a duplicated row usually means
      the export was joined wrong and the operator needs to know.
    * **site_forbidden** — the row targets a site the caller's token does not cover. Bulk
      import must not become the write-side hole in the tenancy boundary that `site_scope`
      closes on the read side. `allowed_site=None` is admin (cross-site).

    Rows without an `asset_id` are new by definition — one is generated at write time, so they
    can never collide and are always creatable.
    """
    to_create, already_present, duplicate_in_payload, site_forbidden = [], [], [], []
    seen: set[str] = set()

    for idx, row in enumerate(rows):
        aid = row.asset_id
        if allowed_site is not None and row.site_id != allowed_site:
            site_forbidden.append({"row": idx, "asset_id": aid, "site_id": row.site_id})
            continue
        if aid:
            if aid in seen:
                duplicate_in_payload.append({"row": idx, "asset_id": aid})
                continue
            seen.add(aid)
            if aid in existing_ids:
                already_present.append({"row": idx, "asset_id": aid})
                continue
        to_create.append((idx, row))

    return {
        "to_create": to_create,
        "already_present": already_present,
        "duplicate_in_payload": duplicate_in_payload,
        "site_forbidden": site_forbidden,
    }


@router.post("/bulk", summary="Bulk-import assets from an EAM golden record (Layer 1)")
async def bulk_import_assets(
    payload: AssetBulkImport,
    driver: Neo4jDep,
    supabase: SupabaseDep,
    es: ElasticsearchDep,
    current_user: dict = Depends(require_role("admin", "engineer")),
) -> dict:
    """
    Layer 1's golden-record bootstrap — the half of the MDM import that had no endpoint.

    The architecture opens with "Kairos begins every deployment by ingesting the enterprise
    golden record", then separately describes a human bootstrap for assets the golden record is
    *missing*. Only the second existed: `POST /assets/` takes one asset at a time, so a plant
    could only be bootstrapped by hand.

    The confirming authority is the caller, from the verified token — not a per-row field.
    Every created asset still lands `identity_confirmed=True` with that id and an `audit_log`
    row, so provenance is identical to single registration.

    **Partial success is the contract, not a fallback.** One malformed row in a 500-row export
    must not cost the other 499; the response reports every row that did not land and why. A
    caller can fix those rows and re-post the whole file — creation is idempotent, so the rows
    that already succeeded come back as `already_present` rather than duplicating.
    """
    user_id = current_user.get("user_id", "")
    # The demo role imports only showcase assets, on showcase sites, with `DEMO-` ids.
    for row in payload.assets:
        tenant.guard_site(current_user, row.site_id)
        if row.asset_id:
            tenant.guard_asset(current_user, row.asset_id)
    allowed_site = (
        None if current_user.get("role") in ("admin", "demo") else (current_user.get("site_id") or "")
    )
    if allowed_site == "":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has no site assigned; ask an administrator to set one.",
        )

    graph = GraphService(driver)

    # One lookup for the whole payload rather than a query per row — an existence check that
    # costs N round-trips is what makes people import in small batches and lose atomicity.
    candidate_ids = [r.asset_id for r in payload.assets if r.asset_id]
    existing_ids = await graph.existing_asset_ids(candidate_ids) if candidate_ids else set()

    part = partition_import_rows(payload.assets, existing_ids, allowed_site)

    created: list[str] = []
    created_pairs: list[tuple[str, object]] = []  # (resolved id, row) — rows may have no asset_id
    failed: list[dict] = []
    now = datetime.now(UTC).isoformat()

    async def _process_creation_row(idx: int, row: Any) -> tuple[bool, int, str, Any]:
        asset_id = row.asset_id or f"{_id_prefix(current_user)}{shortuuid.uuid()[:8].upper()}"
        try:
            await graph.create_asset_node({
                "asset_id": asset_id,
                "tag_number": row.tag_number,
                "name": row.name,
                "equipment_class": row.equipment_class,
                "criticality": row.criticality,
                "site_id": row.site_id,
                "facility_id": row.facility_id,
                "eam_source": row.eam_source,
                "identity_confirmed": True,
                "parent_asset_id": row.parent_asset_id,
            })
            await asyncio.to_thread(
                lambda r=row, a=asset_id: supabase.table("assets").upsert({
                    "asset_id": a,
                    "tag_number": r.tag_number,
                    "name": r.name,
                    "equipment_class": r.equipment_class,
                    "criticality": r.criticality,
                    "site_id": r.site_id,
                    "facility_id": r.facility_id,
                    "parent_asset_id": r.parent_asset_id,
                    "eam_source": r.eam_source,
                    "identity_confirmed": True,
                    "identity_confirmed_by": user_id,
                    "identity_confirmed_at": now,
                }).execute()
            )
            return (True, idx, asset_id, row)
        except Exception as exc:
            log.warning("asset.bulk_row_failed", row=idx, asset_id=asset_id, error=str(exc))
            return (False, idx, asset_id, str(exc))

    chunk_size = 50
    for i in range(0, len(part["to_create"]), chunk_size):
        chunk = part["to_create"][i:i + chunk_size]
        results = await asyncio.gather(*(_process_creation_row(idx, row) for idx, row in chunk))
        for success, idx, asset_id, data in results:
            if success:
                created.append(asset_id)
                created_pairs.append((asset_id, data))
            else:
                failed.append({"row": idx, "asset_id": asset_id, "error": "write_failed"})

    # ES is a search index, not a system of record — a failed index must not fail the import.
    # The asset is already canonical in Neo4j and Supabase; it is only harder to search for.
    # Driven by (id, row) pairs captured at write time — a row whose asset_id was generated has
    # no id on the row itself, so pairing at creation is the only way to index it correctly.
    # Process the ES index in smaller asyncio chunks so it doesn't hang
    chunk_size = 50
    for i in range(0, len(created_pairs), chunk_size):
        chunk = created_pairs[i:i + chunk_size]
        tasks = []
        for aid, row in chunk:
            tasks.append(
                es.index(index=tenant.store_for("kairos_assets", demo=tenant.is_demo_id(aid)), id=aid, document={
                    "asset_id": aid,
                    "tag_number": row.tag_number,
                    "name": row.name,
                    "equipment_class": row.equipment_class,
                    "criticality": row.criticality,
                    "site_id": row.site_id,
                    "facility_id": row.facility_id,
                    "eam_source": row.eam_source,
                })
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                log.warning("asset.bulk_es_index_failed", asset_id=chunk[idx][0], error=str(result))

    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "asset_bulk_imported",
            "entity_type": "asset",
            "entity_id": f"bulk:{len(created)}",
            "performed_by": user_id,
            "details": {
                "submitted": len(payload.assets),
                "created": len(created),
                "already_present": len(part["already_present"]),
                "duplicate_in_payload": len(part["duplicate_in_payload"]),
                "site_forbidden": len(part["site_forbidden"]),
                "failed": len(failed),
            },
        }).execute()
    )

    log.info(
        "asset.bulk_imported", performed_by=user_id, submitted=len(payload.assets),
        created=len(created), skipped=len(part["already_present"]), failed=len(failed),
    )
    return {
        "submitted": len(payload.assets),
        "created": len(created),
        "created_asset_ids": created,
        "already_present": part["already_present"],
        "duplicate_in_payload": part["duplicate_in_payload"],
        "site_forbidden": part["site_forbidden"],
        "failed": failed,
    }


@router.post("/", summary="Register a new canonical asset", status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreate,
    driver: Neo4jDep,
    supabase: SupabaseDep,
    es: ElasticsearchDep,
    current_user: dict = Depends(require_role("admin", "engineer")),
) -> dict:
    """
    Creates a deterministic asset node in the MDM backbone (Neo4j + Supabase).
    AI-inferred identities are never accepted — confirmed_by_user_id is mandatory.
    Uses MERGE in Neo4j so duplicate registrations are idempotent.
    """
    site_scope(current_user, payload.site_id, write=True)  # a non-admin may only register assets on their own site
    tenant.guard_site(current_user, payload.site_id)
    asset_id = payload.asset_id or f"{_id_prefix(current_user)}{shortuuid.uuid()[:8].upper()}"
    tenant.guard_asset(current_user, asset_id)
    now = datetime.now(UTC).isoformat()
    # Who confirmed the identity comes from the session, never from the request body — the body
    # field is client-supplied, so trusting it let any engineer or admin record the confirmation as
    # someone else (and the UI fell back to the literal "admin"). Same rule as alias confirm/reject.
    confirmed_by = current_user.get("user_id") or payload.confirmed_by_user_id

    graph = GraphService(driver)
    # Registering is create-only. Neo4j's ON CREATE keeps the old node, but the Supabase write used
    # to `upsert`, so re-posting an id from another site rewrote that site's row while the graph kept
    # the old values, leaving the two stores disagreeing. An existing id on a different site is
    # refused here; an id already in Supabase is refused by the insert below.
    existing = await graph.get_asset(asset_id)
    if existing and existing.get("site_id") != payload.site_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Asset '{asset_id}' is already registered.")
    await graph.create_asset_node({
        "asset_id": asset_id,
        "tag_number": payload.tag_number,
        "name": payload.name,
        "equipment_class": payload.equipment_class,
        "criticality": payload.criticality,
        "site_id": payload.site_id,
        "facility_id": payload.facility_id,
        "eam_source": payload.eam_source,
        "identity_confirmed": True,
        "parent_asset_id": payload.parent_asset_id,
    })

    supabase_row = {
        "asset_id": asset_id,
        "tag_number": payload.tag_number,
        "name": payload.name,
        "equipment_class": payload.equipment_class,
        "criticality": payload.criticality,
        "site_id": payload.site_id,
        "facility_id": payload.facility_id,
        "parent_asset_id": payload.parent_asset_id,
        "eam_source": payload.eam_source,
        "identity_confirmed": True,
        "identity_confirmed_by": confirmed_by,
        "identity_confirmed_at": now,
    }
    try:
        await asyncio.to_thread(lambda: supabase.table("assets").insert(supabase_row).execute())
    except Exception as exc:
        if "23505" in str(exc):  # unique_violation: the id is already registered
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=f"Asset '{asset_id}' is already registered."
            ) from exc
        raise

    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "asset_created",
            "entity_type": "asset",
            "entity_id": asset_id,
            "performed_by": confirmed_by,
            "details": {"tag_number": payload.tag_number, "eam_source": payload.eam_source},
        }).execute()
    )

    # Index into ES kairos_assets for exact-match search (tag numbers, names)
    try:
        await es.index(
            index=tenant.store_for("kairos_assets", demo=tenant.is_demo_id(asset_id)),
            id=asset_id,
            document={
                "asset_id": asset_id,
                "tag_number": payload.tag_number,
                "name": payload.name,
                "equipment_class": payload.equipment_class,
                "criticality": payload.criticality,
                "site_id": payload.site_id,
                "facility_id": payload.facility_id,
                "eam_source": payload.eam_source,
            },
        )
    except Exception as exc:
        log.warning("asset.es_index_failed", asset_id=asset_id, error=str(exc))

    log.info("asset.created", asset_id=asset_id, tag_number=payload.tag_number, confirmed_by=confirmed_by)
    return {"asset_id": asset_id, "tag_number": payload.tag_number, "status": "created"}


async def _issue_counts(supabase, asset_ids: list[str]) -> dict[str, dict[str, int | None]]:
    """Open work orders + open compliance gaps for a page of assets, in two queries total.

    The obvious implementation — the detail handler's two `count="exact"` queries, per asset —
    is an N+1 that costs 100 Supabase round trips for a 50-row page. This fetches only the
    `asset_id` column for the page's assets and tallies in Python, so cost is fixed at two
    queries regardless of page size.

    Server-side `GROUP BY` would be better still, but PostgREST aggregates are disabled on this
    project (`PGRST123`), and the alternatives — enabling them or adding a DB function — are both
    cloud DDL.

    Definitions are copied from `get_asset` deliberately: the list and the detail page must not
    disagree about the same number. Note `open_work_orders_count` counts `work_order_created`
    events, which is what the detail endpoint has always returned.

    Degrades the way `get_asset` does — a failed lookup yields null ("unknown", rendered "—") and
    a warning, never a 500 on the list and never a 0 that reads as a clean record. An asset with
    no rows is a real 0.
    """
    blank = {"open_work_orders_count": 0, "compliance_gap_count": 0}
    if not asset_ids:
        return {}

    wo_future = asyncio.to_thread(
        lambda: supabase.table("operational_events")
        .select("asset_id", count="exact")
        .in_("asset_id", asset_ids)
        .eq("event_type", "work_order_created")
        .execute()
    )
    gap_future = asyncio.to_thread(
        lambda: supabase.table("knowledge_conflicts")
        .select("asset_id", count="exact")
        .in_("asset_id", asset_ids)
        .eq("status", "open")
        .execute()
    )
    wo_result, gap_result = await asyncio.gather(wo_future, gap_future, return_exceptions=True)

    counts: dict[str, dict[str, int | None]] = {aid: dict(blank) for aid in asset_ids}
    for field, result in (("open_work_orders_count", wo_result), ("compliance_gap_count", gap_result)):
        if isinstance(result, BaseException):
            log.warning("asset.list_counts_failed", field=field, error=str(result))
            for aid in asset_ids:
                counts[aid][field] = None
            continue
        rows = result.data or []
        # PostgREST caps rows server-side (`db-max-rows`). A silent cap would undercount every
        # asset on the page, so compare against the exact count and say so rather than serve a
        # number that looks fine and is wrong.
        if result.count is not None and len(rows) < result.count:
            log.warning(
                "asset.list_counts_truncated",
                field=field, returned=len(rows), total=result.count,
            )
        for row in rows:
            aid = row.get("asset_id")
            if aid in counts:
                counts[aid][field] += 1
    return counts


@router.get("/", summary="List all registered assets")
async def list_assets(
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    supabase: SupabaseDep,
    site_id: str | None = Query(None),
    equipment_class: str | None = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0),
) -> dict:
    """Paginated list of canonical asset nodes from the MDM backbone (Neo4j).

    `site_id` narrows within the caller's own site; it cannot widen past it (see `site_scope`).
    """
    graph = GraphService(driver)
    result = await graph.list_assets(
        site_id=site_scope(current_user, site_id),
        equipment_class=equipment_class,
        skip=offset,
        limit=limit,
        hide_demo=tenant.hides_demo(current_user),
    )
    assets = result["assets"]
    counts = await _issue_counts(supabase, [a["asset_id"] for a in assets if a.get("asset_id")])
    items = [
        {**a, **counts.get(a.get("asset_id"), {"open_work_orders_count": 0, "compliance_gap_count": 0})}
        for a in assets
    ]
    return {"items": items, "total": result["total"], "limit": limit, "offset": offset,
            "excluded_test_assets": result["excluded_test_assets"]}


# NOTE: must stay ABOVE "/{asset_id}" — FastAPI matches in declaration order, so a later
# literal path is swallowed by the earlier path parameter and "coverage" would be looked up
# as an asset id.
@router.get("/coverage", summary="Knowledge-coverage matrix across all assets")
async def asset_coverage(
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    supabase: SupabaseDep,
    settings: SettingsDep,
) -> dict:
    """
    Per-asset knowledge coverage: facts held, how many are authoritative, how many are
    human-verified, linked documents, and pending quarantine.

    Read-only and model-free — no OCR/NER/embedding call, so it spends no provider quota.
    """
    svc = CoverageService(driver, settings.NEO4J_DATABASE, supabase)
    hide_demo = tenant.hides_demo(current_user)
    items = await svc.asset_coverage(hide_demo)
    site = site_scope(current_user, None)
    if site:
        # The coverage rows carry no site, so keep the ones whose asset is on the caller's site.
        # ponytail: one capped page of the site's asset ids; push the site into the Cypher in
        # CoverageService when a site can hold more than this many assets.
        site_ids = {
            a["asset_id"]
            for a in (
                await GraphService(driver).list_assets(site_id=site, limit=_SITE_ASSET_CAP, hide_demo=hide_demo)
            )["assets"]
        }
        items = [i for i in items if i["asset_id"] in site_ids]
    return {"items": items, "total": len(items), "excluded_test_assets": await svc.excluded_test_assets(hide_demo)}


@router.get("/provisional", summary="Assets awaiting human identity confirmation (Layer 1)")
async def list_provisional_assets(current_user: CurrentUserDep, supabase: SupabaseDep) -> dict:
    """Registered records whose identity no qualified user has confirmed yet.

    Feeds the identity-confirmation queue, which used to render a hardcoded list instead of this.
    """
    query = (
        supabase.table("assets")
        .select("asset_id, tag_number, name, equipment_class, criticality, site_id, facility_id, eam_source")
        .eq("identity_confirmed", False)
    )
    query = tenant.pin_site(query, current_user, site_scope(current_user, None))
    query = tenant.scope_site(query, current_user)
    result = await asyncio.to_thread(lambda: query.order("created_at", desc=True).limit(100).execute())
    items = result.data or []
    return {"items": items, "total": len(items)}


@router.get("/aliases/pending", summary="Unconfirmed tag-alias candidates proposed by extraction (Layer 1)")
async def list_pending_aliases(current_user: CurrentUserDep, supabase: SupabaseDep) -> dict:
    """Alias candidates the NER pipeline proposed and no human has confirmed or rejected."""
    site = site_scope(current_user, None)
    result = await asyncio.to_thread(
        lambda: tenant.scope(
            supabase.table("asset_alias_map")
            .select("alias, canonical_asset_id, confidence, alias_source, created_at")
            .eq("confirmed", False),
            current_user, "canonical_asset_id",
        ).order("confidence", desc=True).limit(100).execute()
    )
    items = result.data or []
    if site and items:
        # The alias map has no site column: keep candidates whose canonical asset is on the caller's site.
        ids = list({i["canonical_asset_id"] for i in items})
        on_site = await asyncio.to_thread(
            lambda: tenant.pin_site(supabase.table("assets").select("asset_id").in_("asset_id", ids), current_user, site).execute()
        )
        allowed = {r["asset_id"] for r in (on_site.data or [])}
        items = [i for i in items if i["canonical_asset_id"] in allowed]
    return {"items": items, "total": len(items)}


@router.post("/{asset_id}/aliases/{alias}/reject", summary="Reject a proposed tag alias (Layer 1)")
async def reject_asset_alias(
    asset_id: str,
    alias: str,
    driver: Neo4jDep,
    supabase: SupabaseDep,
    current_user: dict = Depends(require_role("admin", "engineer")),
) -> dict:
    """Human authority rejects an alias candidate.

    Only an unconfirmed candidate can be rejected — a confirmed alias is used for resolution, and
    withdrawing one is a different decision than turning down a proposal. The row is removed (it is an
    extraction guess, not vault evidence) and the rejection is audited.
    """
    tenant.guard_asset(current_user, asset_id)
    await scoped_asset(GraphService(driver), asset_id, current_user)
    existing = await asyncio.to_thread(
        lambda: supabase.table("asset_alias_map")
        .select("alias")
        .eq("alias", alias)
        .eq("canonical_asset_id", asset_id)
        .eq("confirmed", False)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No unconfirmed alias '{alias}' proposed for asset '{asset_id}'.",
        )
    rejected_by = current_user.get("user_id", "unknown")
    await asyncio.to_thread(
        lambda: supabase.table("asset_alias_map")
        .delete()
        .eq("alias", alias)
        .eq("canonical_asset_id", asset_id)
        .eq("confirmed", False)
        .execute()
    )
    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "asset_alias_rejected",
            "entity_type": "asset",
            "entity_id": asset_id,
            "performed_by": rejected_by,
            "details": {"alias": alias},
        }).execute()
    )
    log.info("asset.alias_rejected", asset_id=asset_id, alias=alias, rejected_by=rejected_by)
    return {"status": "rejected", "alias": alias, "canonical_asset_id": asset_id}


@router.get("/{asset_id}", summary="Get asset by canonical ID")
async def get_asset(
    asset_id: str,
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    supabase: SupabaseDep,
) -> dict:
    """Returns the canonical asset node with live operational enrichment."""
    graph = GraphService(driver)
    asset = await scoped_asset(graph, asset_id, current_user)

    wo_future = asyncio.to_thread(
        lambda: supabase.table("operational_events")
        .select("event_id", count="exact")
        .eq("asset_id", asset_id)
        .eq("event_type", "work_order_created")
        .execute()
    )
    gap_future = asyncio.to_thread(
        lambda: supabase.table("knowledge_conflicts")
        .select("conflict_id", count="exact")
        .eq("asset_id", asset_id)
        .eq("status", "open")
        .execute()
    )
    inspection_future = graph.get_last_inspection_date(asset_id)
    # Identity attribution lives in Supabase, not on the graph node: the write path sets
    # `identity_confirmed` on the Neo4j node but records *who* confirmed it and *when* in
    # `assets` + `audit_log`. Reading only the node meant no surface could show who vouched for
    # an asset's identity — on the layer whose entire claim is deterministic, human-confirmed
    # identity, the provenance existed but was unreachable.
    identity_future = asyncio.to_thread(
        lambda: supabase.table("assets")
        .select("identity_confirmed, identity_confirmed_by, identity_confirmed_at")
        .eq("asset_id", asset_id)
        .limit(1)
        .execute()
    )

    wo_result, gap_result, last_inspection, identity_result = await asyncio.gather(
        wo_future, gap_future, inspection_future, identity_future, return_exceptions=True
    )

    identity: dict = {}
    if not isinstance(identity_result, BaseException) and identity_result.data:
        identity = identity_result.data[0]
    elif isinstance(identity_result, BaseException):
        log.warning("asset.identity_lookup_failed", asset_id=asset_id, error=str(identity_result))

    for name, result in (("work_orders", wo_result), ("compliance_gaps", gap_result),
                         ("last_inspection", last_inspection)):
        if isinstance(result, BaseException):
            log.warning("asset.enrichment_failed", asset_id=asset_id, field=name, error=str(result))

    return {
        **asset,
        # A failed lookup is null ("unknown"), never 0: rendered as "0 compliance gaps" it would be
        # good news that may not be true. The frontend shows null as "—".
        "open_work_orders_count": None if isinstance(wo_result, BaseException) else (wo_result.count or 0),
        "compliance_gap_count": None if isinstance(gap_result, BaseException) else (gap_result.count or 0),
        "last_inspection_date": None if isinstance(last_inspection, BaseException) else last_inspection,
        # Graph node wins on the boolean (it is the canonical MDM record); Supabase supplies the
        # attribution the node does not carry.
        "identity_confirmed": asset.get("identity_confirmed", identity.get("identity_confirmed")),
        "identity_confirmed_by": identity.get("identity_confirmed_by"),
        "identity_confirmed_at": identity.get("identity_confirmed_at"),
    }


@router.get("/{asset_id}/aliases", summary="List all known tag aliases for an asset")
async def get_asset_aliases(
    asset_id: str,
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    supabase: SupabaseDep,
) -> list:
    """
    Returns all known naming variants for a canonical asset ID from the alias map.
    Used by the extraction pipeline to resolve tag references in documents.
    """
    await scoped_asset(GraphService(driver), asset_id, current_user)
    result = await asyncio.to_thread(
        lambda: supabase.table("asset_alias_map")
        .select("*")
        .eq("canonical_asset_id", asset_id)
        .execute()
    )
    return result.data or []


@router.post("/{asset_id}/aliases/{alias}/confirm", summary="Confirm a learned tag alias (Layer 1)")
async def confirm_asset_alias(
    asset_id: str,
    alias: str,
    driver: Neo4jDep,
    supabase: SupabaseDep,
    current_user: dict = Depends(require_role("admin", "engineer")),
) -> dict:
    """
    Human authority confirms an alias candidate the extraction pipeline proposed.

    The NER path writes unresolved tags as `confirmed: False` candidates
    (`workflows/document_pipeline.py`), and `resolve_canonical_asset_id` only ever reads
    **confirmed** rows — so without this endpoint a learned alias could never become usable and
    candidates accumulated forever. This is the human half of "AI-assisted linking is allowed only
    after human confirmation" (ARCHITECTURE.md Layer 1).

    Idempotent: re-confirming an already-confirmed alias is a no-op, not an error.
    """
    tenant.guard_asset(current_user, asset_id)
    await scoped_asset(GraphService(driver), asset_id, current_user)
    existing = await asyncio.to_thread(
        lambda: supabase.table("asset_alias_map")
        .select("alias, canonical_asset_id, confirmed")
        .eq("alias", alias)
        .eq("canonical_asset_id", asset_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No alias '{alias}' proposed for asset '{asset_id}'.",
        )
    if existing.data[0]["confirmed"]:
        return {"status": "already_confirmed", "alias": alias, "canonical_asset_id": asset_id}

    confirmed_by = current_user.get("user_id", "unknown")
    await asyncio.to_thread(
        lambda: supabase.table("asset_alias_map")
        .update({"confirmed": True, "confirmed_by": confirmed_by})
        .eq("alias", alias)
        .eq("canonical_asset_id", asset_id)
        .execute()
    )
    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "asset_alias_confirmed",
            "entity_type": "asset",
            "entity_id": asset_id,
            "performed_by": confirmed_by,
            "details": {"alias": alias},
        }).execute()
    )

    log.info("asset.alias_confirmed", asset_id=asset_id, alias=alias, confirmed_by=confirmed_by)
    return {"status": "confirmed", "alias": alias, "canonical_asset_id": asset_id, "confirmed_by": confirmed_by}


@router.get("/{asset_id}/hierarchy", summary="Get asset parent-child hierarchy")
async def get_asset_hierarchy(
    asset_id: str,
    current_user: CurrentUserDep,
    driver: Neo4jDep,
) -> dict:
    """
    Returns the asset's position in the facility hierarchy by traversing
    PARENT_OF relationships in Neo4j (up to 10 levels).
    """
    graph = GraphService(driver)
    await scoped_asset(graph, asset_id, current_user)
    hierarchy = await graph.get_asset_hierarchy(asset_id)
    if not hierarchy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found")
    return hierarchy


@router.get("/{asset_id}/ot-coverage", summary="Instrumentation coverage map for an asset")
async def get_asset_ot_coverage(
    asset_id: str,
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    supabase: SupabaseDep,
) -> dict:
    """
    Which components on this asset are actually monitored by historian tags (Layer 5).

    Derived from **engineer-verified** P&ID topology only. An asset whose drawings have not been
    verified returns `coverage_type: "none"` — the honest answer, not a guess. Layer 10 uses this
    to decide whether a repair can be judged by telemetry or needs human closeout attestation.
    """
    await scoped_asset(GraphService(driver), asset_id, current_user)
    return await OtCoverageService(supabase).asset_coverage(asset_id)


def _edge_view(edge_id: str, source: str, target: str, label: str, edge: dict | None = None) -> dict:
    """A graph edge for the UI. `structural` edges (position in the hierarchy, an event on the asset) are
    not knowledge facts: they carry no authority or validity window, only that two things are related."""
    e = edge or {}
    return {
        "id": edge_id, "source": source, "target": target, "label": label, "structural": edge is None,
        "authority_level": int(e.get("authority_level", 5)), "verification_status": str(e.get("verification_status", "verified")),
        "valid_from": str(e.get("valid_from", "2020-01-01T00:00:00")), "valid_to": str(e.get("valid_to", "9999-12-31T23:59:59")),
        "document_id": str(e.get("document_id", "")), "confidence": float(e.get("confidence", 1.0)),
    }


@router.get("/{asset_id}/graph", summary="The asset and its surroundings, two hops out, for the graph view")
async def get_asset_graph(
    asset_id: str,
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    supabase: SupabaseDep,
    as_of: str | None = Query(None, description="ISO8601 timestamp: the documents valid at that moment"),
) -> dict:
    """Nodes and edges around an asset: its place in the hierarchy, the documents about it, the people and
    organisations those documents mention, the other assets they cover, and its latest events. Capped per
    kind (see `GraphService.get_asset_neighbourhood`). Accepts a tag alias like `/knowledge` does; documents
    that are test artifacts are left out and counted."""
    graph = GraphService(driver)
    canonical = await resolve_canonical_asset_id(asset_id, graph, supabase)
    if not canonical:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found")
    await scoped_asset(graph, canonical, current_user)
    as_of_dt: datetime | None = None
    if as_of:
        try:
            as_of_dt = datetime.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid as_of format: '{as_of}'. Use ISO8601.")
    hood = await graph.get_asset_neighbourhood(canonical, hide_demo=tenant.hides_demo(current_user), as_of=as_of_dt)
    if not hood:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found")

    doc_ids = [d["document_id"] for d, _ in hood["documents"]]
    rows = await document_rows(supabase, doc_ids) if doc_ids else []
    names = {r["document_id"]: r["file_name"] for r in rows if r.get("file_name")}
    artifacts = partition_test_artifacts(rows)
    documents = [(d, r) for d, r in hood["documents"] if d["document_id"] not in artifacts]
    shown_docs = {d["document_id"] for d, _ in documents}

    nodes: dict[str, dict] = {}

    def node(node_id: str, kind: str, label: str, props: dict) -> None:
        nodes.setdefault(node_id, {"id": node_id, "kind": kind, "label": label, "properties": props})

    def asset_label(a: dict) -> str:
        return a.get("tag_number") or a.get("name") or a["asset_id"]

    edges: list[dict] = []
    centre = hood["asset"]
    node(canonical, "Asset", asset_label(centre), centre)
    if hood["parent"]:
        p = hood["parent"]
        node(p["asset_id"], "Asset", asset_label(p), p)
        edges.append(_edge_view(f"parent-{p['asset_id']}", p["asset_id"], canonical, "PARENT_OF"))
    for c in hood["children"]:
        node(c["asset_id"], "Asset", asset_label(c), c)
        edges.append(_edge_view(f"child-{c['asset_id']}", canonical, c["asset_id"], "PARENT_OF"))
    for d, r in documents:
        did = d["document_id"]
        name = names.get(did) or d.get("title") or did
        node(did, "Document", name.rsplit(".", 1)[0], {**d, "title": name})
        edges.append(_edge_view(f"doc-{did}", canonical, did, r.get("relationship_type", "DOCUMENTED_BY"), r))
    id_of = {"Person": "person_id", "Organisation": "org_id"}
    for doc, x, kind, r in hood["mentions"]:
        if doc not in shown_docs:
            continue
        xid = x.get(id_of[kind], "")
        node(xid, kind, x.get("name", xid), x)
        edges.append(_edge_view(f"m-{doc}-{xid}", doc, xid, r.get("relationship_type", "MENTIONS"), r))
    for doc, o, r in hood["related"]:
        if doc not in shown_docs:
            continue
        node(o["asset_id"], "Asset", asset_label(o), o)
        edges.append(_edge_view(f"rel-{o['asset_id']}-{doc}", o["asset_id"], doc, r.get("relationship_type", "DOCUMENTED_BY"), r))
    for e in hood["events"]:
        eid = e["event_id"]
        node(eid, "Event", str(e.get("event_type", "event")).replace("_", " "), e)
        edges.append(_edge_view(f"ev-{eid}", canonical, eid, "OCCURRED_ON"))

    # A document that names the same person twice (re-ingested, or two mentions) yields two edges with one
    # id; the view draws one line, and a duplicate id would be a duplicate React key.
    edges = list({e["id"]: e for e in edges}.values())
    return {
        "asset_id": canonical, "requested_id": asset_id, "resolved_from_alias": canonical != asset_id,
        "as_of": as_of or "now", "nodes": list(nodes.values()), "edges": edges, "excluded_test_documents": len(hood["documents"]) - len(documents),
    }


@router.get("/{asset_id}/knowledge", summary="Get all knowledge graph facts for an asset")
async def get_asset_knowledge(
    asset_id: str,
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    supabase: SupabaseDep,
    as_of: str | None = Query(None, description="ISO8601 timestamp for time-travel query"),
    include_test_data: bool = Query(
        False,
        description="Include facts sourced from test/sweep artifacts. Off by default — they are "
        "~79% of the active vault and drown the real corpus.",
    ),
) -> dict:
    """
    Returns all temporal graph edges (facts) for this asset.
    Accepts a canonical id or a confirmed tag alias (e.g. P-101 → EQ-101).
    Pass as_of for time-travel queries — returns state of knowledge at that moment.

    Facts sourced from test artifacts are excluded by default and **counted** in
    `excluded_test_documents`. The filter cannot live in Cypher: the classifier is the vault
    `file_name`, which is a Supabase column, while the Neo4j node carries only `document_id`.
    See `api/services/corpus.py` for why an unresolvable id is kept rather than dropped.
    """
    graph = GraphService(driver)
    canonical = await resolve_canonical_asset_id(asset_id, graph, supabase)
    if not canonical:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found")
    await scoped_asset(graph, canonical, current_user)

    as_of_dt: datetime | None = None
    if as_of:
        try:
            as_of_dt = datetime.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid as_of format: '{as_of}'. Use ISO8601.")

    facts = await graph.get_asset_knowledge_at(canonical, as_of=as_of_dt)

    excluded = 0
    doc_ids = [(f.get("edge") or {}).get("document_id") for f in facts if (f.get("edge") or {}).get("document_id")]
    rows = await document_rows(supabase, doc_ids) if doc_ids else []
    # Document nodes carry no title, so the UI fell back to the raw id ("DOC-KUXNJRUQYXYQ"). The same
    # lookup that classifies test artifacts supplies the vault file name.
    file_names = {r["document_id"]: r["file_name"] for r in rows if r.get("file_name")}
    for f in facts:
        target = f.get("target")
        edge_doc = (f.get("edge") or {}).get("document_id") or ""
        # A promoted quarantine item has no vault document (`PROMOTED-<item_id>`), so it gets a label
        # saying what it is rather than the raw id.
        name = file_names.get(edge_doc) or ("Promoted field input" if edge_doc.startswith("PROMOTED-") else None)
        if name and isinstance(target, dict) and not target.get("title") and target.get("document_id"):
            target["title"] = name
    if not include_test_data and facts:
        artifact_ids = partition_test_artifacts(rows)
        if artifact_ids:
            kept = [
                f for f in facts
                if (f.get("edge") or {}).get("document_id") not in artifact_ids
            ]
            excluded = len(facts) - len(kept)
            facts = kept

    return {
        "asset_id": canonical,
        "requested_id": asset_id,
        "resolved_from_alias": canonical != asset_id,
        "as_of": as_of or "now",
        "fact_count": len(facts),
        # Reported, never silent: the denominator stays auditable. A filter that hides how much
        # it removed is how the linkage figure stayed wrong for as long as it did.
        "excluded_test_documents": excluded,
        "facts": facts,
    }
