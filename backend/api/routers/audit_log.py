"""
Audit log router — immutable evidence lineage trail.
Frontend uses this to render the evidence lineage panel per entity.
"""

import asyncio

import structlog
from fastapi import APIRouter, Query

from api.dependencies import CurrentUserDep, SupabaseDep
from api.services.identity import display_names

log = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/", summary="Query audit log by entity")
async def get_audit_log(
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
    entity_type: str | None = Query(None, description="asset, document, brief, conflict, quarantine_item, query"),
    entity_id: str | None = Query(None, description="ID of the specific entity"),
    action: str | None = Query(None, description="Filter by action type"),
    performed_by: str | None = Query(None, description="Filter by user ID"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
) -> dict:
    """
    Returns immutable audit trail entries for the evidence lineage panel.
    Ordered chronologically descending (most recent first).
    """
    query = supabase.table("audit_log").select(
        "id, action, entity_type, entity_id, performed_by, timestamp, details",
        count="exact",
    )
    if entity_type:
        query = query.eq("entity_type", entity_type)
    if entity_id:
        query = query.eq("entity_id", entity_id)
    if action:
        query = query.eq("action", action)
    if performed_by:
        query = query.eq("performed_by", performed_by)

    result = await asyncio.to_thread(
        lambda: query.order("timestamp", desc=True).range(offset, offset + limit - 1).execute()
    )
    items = result.data or []
    # The trail listed who acted as raw auth UUIDs; an auditor reads a name. The id stays for filtering.
    names = await display_names(supabase, [i.get("performed_by") for i in items])
    for i in items:
        i["performed_by_name"] = names.get(i.get("performed_by"))
    return {
        "items": items,
        "total": result.count or 0,
        "limit": limit,
        "offset": offset,
    }
