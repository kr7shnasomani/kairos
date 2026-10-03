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
        conflict_rows = overdue_conflicts.data or []

        for row in conflict_rows:
            cid = row["conflict_id"]
            await asyncio.to_thread(
                lambda r=row: supabase.table("knowledge_conflicts").update({
                    "escalated_at": now,
                    "escalated_to": _ESCALATION_ROLE,
                }).eq("conflict_id", r["conflict_id"]).execute()
            )
            await asyncio.to_thread(
                lambda r=row: supabase.table("audit_log").insert({
                    "action": "sla_escalated",
                    "entity_type": "knowledge_conflict",
                    "entity_id": r["conflict_id"],
                    "performed_by": "system",
                    "details": {
                        "track": r["track"],
                        "asset_id": r["asset_id"],
                        "sla_deadline": r["sla_deadline"],
                        "escalated_to": _ESCALATION_ROLE,
                        **tenant.audit_marker(r["asset_id"]),
                    },
                }).execute()
            )
            log.info("sla.conflict_escalated", conflict_id=cid, track=row["track"])

        # --- quarantine_items overdue ---
        overdue_quarantine = await asyncio.to_thread(
            lambda: supabase.table("quarantine_items")
            .select("item_id, asset_id, input_type, sla_due_at")
            .lt("sla_due_at", now)
            .is_("escalated_at", "null")
            .eq("review_status", "pending")
            .execute()
        )
        quarantine_rows = overdue_quarantine.data or []

        for row in quarantine_rows:
            await asyncio.to_thread(
                lambda r=row: supabase.table("quarantine_items").update({
                    "escalated_at": now,
                }).eq("item_id", r["item_id"]).execute()
            )
            await asyncio.to_thread(
                lambda r=row: supabase.table("audit_log").insert({
                    "action": "sla_escalated",
                    "entity_type": "quarantine_item",
                    "entity_id": r["item_id"],
                    "performed_by": "system",
                    "details": {
                        "asset_id": r["asset_id"],
                        "input_type": r["input_type"],
                        "sla_due_at": r["sla_due_at"],
                        "escalated_to": _ESCALATION_ROLE,
                        **tenant.audit_marker(r["asset_id"]),
                    },
                }).execute()
            )
            log.info("sla.quarantine_escalated", item_id=row["item_id"])

        return {
            "conflicts_escalated": len(conflict_rows),
            "quarantine_escalated": len(quarantine_rows),
            "checked_at": now,
        }
