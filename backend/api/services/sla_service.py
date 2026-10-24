"""
SLA Service — Layer 7: Governance SLA tracking and lazy escalation.
Called inline from governance endpoints; no scheduled worker required.
"""

from datetime import UTC, datetime
from typing import Any

import structlog

from api.services import tenant

log = structlog.get_logger(__name__)

_ESCALATION_ROLE = "reliability_engineer"


class SLAService:
    @staticmethod
    async def check_and_escalate(supabase) -> dict[str, Any]:
        """
        Finds overdue conflicts and quarantine items, marks them escalated, and writes audit_log rows.
        Returns counts for the SLA report. Idempotent — escalated_at IS NOT NULL rows are skipped.
        """
        import asyncio
        now = datetime.now(UTC).isoformat()

        # --- knowledge_conflicts overdue (use existing sla_deadline column) ---
        overdue_conflicts = await asyncio.to_thread(
            lambda: supabase.table("knowledge_conflicts")
            .select("conflict_id, track, asset_id, sla_deadline, status")
            .lt("sla_deadline", now)
            .is_("escalated_at", "null")
            .neq("status", "resolved")
            .execute()
        )
        # One conditional batch update per table, and audit rows only for what that update changed.
        # It ran one update and one audit insert per row, on every list GET, so two concurrent reads
        # escalated the same row twice and wrote two audit rows for it.
        conflict_rows = await _escalate(
            supabase, "knowledge_conflicts", "conflict_id", overdue_conflicts.data or [],
            {"escalated_at": now, "escalated_to": _ESCALATION_ROLE},
        )
        await _audit(supabase, "knowledge_conflict", "conflict_id", conflict_rows, lambda r: {
            "track": r["track"], "asset_id": r["asset_id"], "sla_deadline": r["sla_deadline"],
        })

        overdue_quarantine = await asyncio.to_thread(
            lambda: supabase.table("quarantine_items")
            .select("item_id, asset_id, input_type, sla_due_at")
            .lt("sla_due_at", now)
            .is_("escalated_at", "null")
            .eq("review_status", "pending")
            .execute()
        )
        quarantine_rows = await _escalate(
            supabase, "quarantine_items", "item_id", overdue_quarantine.data or [], {"escalated_at": now},
        )
        await _audit(supabase, "quarantine_item", "item_id", quarantine_rows, lambda r: {
            "asset_id": r["asset_id"], "input_type": r["input_type"], "sla_due_at": r["sla_due_at"],
        })

        return {
            "conflicts_escalated": len(conflict_rows),
            "quarantine_escalated": len(quarantine_rows),
            "checked_at": now,
        }


_ESCALATE_CHUNK = 100


async def _escalate(supabase, table: str, key: str, rows: list[dict], values: dict) -> list[dict]:
    """Mark `rows` escalated in one update, only where still unescalated. Returns the rows it changed."""
    import asyncio
    if not rows:
        return []
    by_id = {r[key]: r for r in rows}
    ids = list(by_id)
    escalated: list[dict] = []
    # Chunked: every id goes into the URL, and one request for a large backlog can pass the gateway's
    # URL limit and escalate nothing.
    for start in range(0, len(ids), _ESCALATE_CHUNK):
        chunk = ids[start:start + _ESCALATE_CHUNK]
        changed = await asyncio.to_thread(
            lambda c=chunk: supabase.table(table).update(values).in_(key, c).is_("escalated_at", "null").execute()
        )
        escalated += [by_id[r[key]] for r in (changed.data or []) if r.get(key) in by_id]
    return escalated


async def _audit(supabase, entity_type: str, key: str, rows: list[dict], details) -> None:
    import asyncio
    if not rows:
        return
    await asyncio.to_thread(lambda: supabase.table("audit_log").insert([{
        "action": "sla_escalated",
        "entity_type": entity_type,
        "entity_id": r[key],
        "performed_by": "system",
        "details": {**details(r), "escalated_to": _ESCALATION_ROLE, **tenant.audit_marker(r["asset_id"])},
    } for r in rows]).execute())
    log.info("sla.escalated", entity_type=entity_type, count=len(rows))
