"""
Assets router — Layer 1: Deterministic MDM Backbone.
Manages canonical asset identities, alias resolution, and the asset hierarchy.
"""

import asyncio
from datetime import UTC, datetime

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
from api.services.corpus import document_rows, partition_test_artifacts
from api.services.coverage import CoverageService
from api.services.graph import GraphService
from api.services.ot_coverage import OtCoverageService

log = structlog.get_logger(__name__)
router = APIRouter()


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
    allowed_site = None if current_user.get("role") == "admin" else (current_user.get("site_id") or "")
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

    for idx, row in part["to_create"]:
        asset_id = row.asset_id or f"ASSET-{shortuuid.uuid()[:8].upper()}"
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
            created.append(asset_id)
            created_pairs.append((asset_id, row))
        except Exception as exc:
            # Row-level, so one bad row is one bad row. The graph write is idempotent, so a
            # retry of this file re-attempts exactly the rows that did not land.
            log.warning("asset.bulk_row_failed", row=idx, asset_id=asset_id, error=str(exc))
            # The exception text stays in the log: returned to the caller it exposed store
            # internals (code scanning py/stack-trace-exposure). The row id is enough to retry.
            failed.append({"row": idx, "asset_id": asset_id, "error": "write_failed"})

    # ES is a search index, not a system of record — a failed index must not fail the import.
    # The asset is already canonical in Neo4j and Supabase; it is only harder to search for.
    # Driven by (id, row) pairs captured at write time — a row whose asset_id was generated has
    # no id on the row itself, so pairing at creation is the only way to index it correctly.
    for aid, row in created_pairs:
        try:
            await es.index(index="kairos_assets", id=aid, document={
                "asset_id": aid,
                "tag_number": row.tag_number,
                "name": row.name,
                "equipment_class": row.equipment_class,
                "criticality": row.criticality,
                "site_id": row.site_id,
                "facility_id": row.facility_id,
                "eam_source": row.eam_source,
            })
        except Exception as exc:
            log.warning("asset.bulk_es_index_failed", asset_id=aid, error=str(exc))

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
    asset_id = payload.asset_id or f"ASSET-{shortuuid.uuid()[:8].upper()}"
    now = datetime.now(UTC).isoformat()
    # Who confirmed the identity comes from the session, never from the request body — the body
    # field is client-supplied, so trusting it let any engineer or admin record the confirmation as
    # someone else (and the UI fell back to the literal "admin"). Same rule as alias confirm/reject.
    confirmed_by = current_user.get("user_id") or payload.confirmed_by_user_id

    graph = GraphService(driver)
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
    await asyncio.to_thread(
        lambda: supabase.table("assets").upsert(supabase_row).execute()
    )

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
            index="kairos_assets",
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


async def _issue_counts(supabase, asset_ids: list[str]) -> dict[str, dict[str, int]]:
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

    Degrades the way `get_asset` does — a failed lookup yields 0 and a warning, never a 500 on
    the list. Absent assets get 0, never null, so the column is always numeric.
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

    counts: dict[str, dict[str, int]] = {aid: dict(blank) for aid in asset_ids}
    for field, result in (("open_work_orders_count", wo_result), ("compliance_gap_count", gap_result)):
        if isinstance(result, BaseException):
            log.warning("asset.list_counts_failed", field=field, error=str(result))
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
    )
    assets = result["assets"]
    counts = await _issue_counts(supabase, [a["asset_id"] for a in assets if a.get("asset_id")])
    items = [
        {**a, **counts.get(a.get("asset_id"), {"open_work_orders_count": 0, "compliance_gap_count": 0})}
        for a in assets
    ]
    return {"items": items, "total": result["total"], "limit": limit, "offset": offset}


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
    items = await svc.asset_coverage()
    return {"items": items, "total": len(items)}


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
    site = site_scope(current_user, None)
    if site:
        query = query.eq("site_id", site)
    result = await asyncio.to_thread(lambda: query.order("created_at", desc=True).limit(100).execute())
    items = result.data or []
    return {"items": items, "total": len(items)}


@router.get("/aliases/pending", summary="Unconfirmed tag-alias candidates proposed by extraction (Layer 1)")
async def list_pending_aliases(current_user: CurrentUserDep, supabase: SupabaseDep) -> dict:
    """Alias candidates the NER pipeline proposed and no human has confirmed or rejected."""
    result = await asyncio.to_thread(
        lambda: supabase.table("asset_alias_map")
        .select("alias, canonical_asset_id, confidence, alias_source, created_at")
        .eq("confirmed", False)
        .order("confidence", desc=True)
        .limit(100)
        .execute()
    )
    items = result.data or []
    return {"items": items, "total": len(items)}


@router.post("/{asset_id}/aliases/{alias}/reject", summary="Reject a proposed tag alias (Layer 1)")
async def reject_asset_alias(
    asset_id: str,
    alias: str,
    supabase: SupabaseDep,
    current_user: dict = Depends(require_role("admin", "engineer")),
) -> dict:
    """Human authority rejects an alias candidate.

    Only an unconfirmed candidate can be rejected — a confirmed alias is used for resolution, and
    withdrawing one is a different decision than turning down a proposal. The row is removed (it is an
    extraction guess, not vault evidence) and the rejection is audited.
    """
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
    asset = await graph.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found")

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
        "open_work_orders_count": 0 if isinstance(wo_result, BaseException) else (wo_result.count or 0),
        "compliance_gap_count": 0 if isinstance(gap_result, BaseException) else (gap_result.count or 0),
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
    supabase: SupabaseDep,
) -> list:
    """
    Returns all known naming variants for a canonical asset ID from the alias map.
    Used by the extraction pipeline to resolve tag references in documents.
    """
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
    hierarchy = await graph.get_asset_hierarchy(asset_id)
    if not hierarchy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Asset '{asset_id}' not found")
    return hierarchy


@router.get("/{asset_id}/ot-coverage", summary="Instrumentation coverage map for an asset")
async def get_asset_ot_coverage(
    asset_id: str,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """
    Which components on this asset are actually monitored by historian tags (Layer 5).

    Derived from **engineer-verified** P&ID topology only. An asset whose drawings have not been
    verified returns `coverage_type: "none"` — the honest answer, not a guess. Layer 10 uses this
    to decide whether a repair can be judged by telemetry or needs human closeout attestation.
    """
    return await OtCoverageService(supabase).asset_coverage(asset_id)


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
