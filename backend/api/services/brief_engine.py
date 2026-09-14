"""
Brief Assembly Engine — Layer 8: Contextual brief construction from the knowledge graph.
Phase 1: raw retrieved facts. Phase 2 (not wired): LLM synthesis.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from elasticsearch import AsyncElasticsearch
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient
from supabase import Client

from api.config import Settings
from api.models.brief import Brief, SourceCitation
from api.models.event import PTWEvent, ShiftHandoverEvent, WorkOrderEvent
from api.services.event_bus import EventBusService
from api.services.graph import GraphService
from api.services.llm import LLMService
from api.services.metrics import briefs_delivered
from api.services.vector_store import VectorStoreService

log = structlog.get_logger(__name__)


class BriefEngine:
    def __init__(
        self,
        driver: AsyncDriver,
        qdrant: AsyncQdrantClient,
        es: AsyncElasticsearch,
        supabase: Client,
        settings: Settings,
    ):
        self.graph = GraphService(driver)
        self.vector = VectorStoreService(qdrant, settings)
        self.es = es
        self.supabase = supabase
        self.settings = settings
        self.llm = LLMService(settings)

    # -------------------------------------------------------------------------
    # Work order brief
    # -------------------------------------------------------------------------

    async def assemble_work_order_brief(self, event: WorkOrderEvent) -> Brief:
        graph_task = self.graph.get_asset_knowledge_at(event.asset_id)
        vector_task = self._vector_search(f"failure {event.failure_code}", event.asset_id)
        quarantine_task = self._get_quarantine(event.asset_id)
        conflicts_task = self._get_open_conflicts(event.asset_id)
        procedures_task = self._es_procedures(event.asset_id)

        results = await asyncio.gather(
            graph_task, vector_task, quarantine_task, conflicts_task, procedures_task,
            return_exceptions=True,
        )
        graph_edges, vector_hits, quarantine_items, conflicts, procedures = [
            r if not isinstance(r, Exception) else [] for r in results
        ]

        sources = await _resolve_source_documents(
            self.supabase, _sources_from_graph(graph_edges) + _sources_from_vector(vector_hits)
        )
        warnings = [c["parameter"] for c in conflicts if isinstance(c, dict) and "parameter" in c]
        quarantine_flags = [q["item_id"] for q in quarantine_items if isinstance(q, dict)]
        action_items = [
            p.get("title") or p.get("document_id", "Review procedure")
            for p in procedures[:3]
        ]

        failure_code = (event.failure_code or "").strip()
        fc_known = bool(failure_code) and failure_code.upper() != "UNKNOWN"
        doc_ids = _distinct_docs(graph_edges)
        rel_summary = _summarize_relationships(graph_edges)

        # Operator-facing headline: lead with the most actionable signal, not raw
        # edge internals. Authority/verification are surfaced by the source badges.
        if conflicts:
            headline = (
                f"{event.asset_id}: {len(conflicts)} open knowledge conflict(s) — resolve before work"
                + (f" (failure code {failure_code})" if fc_known else "")
            )
        elif quarantine_items:
            headline = (
                f"{event.asset_id}: {len(quarantine_items)} unverified field observation(s) on file — "
                "review before work"
            )
        elif graph_edges:
            headline = (
                f"{event.asset_id}: {len(graph_edges)} knowledge record(s) on file"
                + (f" across {len(doc_ids)} source document(s)" if doc_ids else "")
                + (f" — work order failure code {failure_code}" if fc_known else "")
            )
        else:
            headline = (
                f"{event.asset_id}: no prior knowledge on file"
                + (f" — first occurrence of failure code {failure_code}" if fc_known else " for this work order")
            )

        lead = f"Work order {event.work_order_id} on {event.asset_id}"
        if fc_known:
            lead += f", failure code {failure_code}"
        body_lines = [lead + "."]
        if graph_edges:
            summary = f"\n{len(graph_edges)} knowledge record(s) on file"
            if rel_summary:
                summary += f" — {rel_summary}"
            summary += ". Authority and verification status are shown per source below."
            body_lines.append(summary)
            if doc_ids:
                body_lines.append(
                    "Source documents: " + ", ".join(doc_ids[:5]) + (" …" if len(doc_ids) > 5 else "")
                )
        if vector_hits:
            body_lines.append(f"\nSimilar failure patterns from {len(vector_hits[:3])} related record(s):")
            for h in vector_hits[:3]:
                p = h.get("payload", {})
                excerpt = (p.get("content") or "").strip()
                if excerpt:
                    excerpt = excerpt[:140] + ("…" if len(excerpt) > 140 else "")
                    body_lines.append(f"  • {excerpt} [{p.get('document_id', '?')}]")
                else:
                    body_lines.append(f"  • {p.get('document_id', '?')}")
        if procedures:
            body_lines.append(f"\nApplicable procedures ({len(procedures)} on file):")
            for p in procedures[:3]:
                body_lines.append(f"  • {p.get('title') or p.get('document_id', '?')}")
        if quarantine_items:
            body_lines.append(
                f"\n⚠ {len(quarantine_items)} unverified field observation(s) linked to this asset — "
                "not yet reviewed by engineering."
            )
        if conflicts:
            params = ", ".join(sorted({c.get("parameter", "?") for c in conflicts if isinstance(c, dict)}))
            body_lines.append(f"\n⚠ Open knowledge conflict(s) on: {params}. Resolve via governance before acting.")

        # Enrich with correlated events from the same compound event window
        correlated = await self._get_correlated_events(str(event.event_id))
        for c in correlated:
            et = c.get("event_type", "")
            p = c.get("payload") or {}
            if et == "alarm_acknowledged":
                body_lines.append(
                    f"\n[DCS ALARM correlated] Tag: {p.get('alarm_tag', '?')} — {p.get('alarm_description', '')}"
                )
            elif et == "ptw_generated":
                body_lines.append(
                    f"\n[PTW correlated] ID: {p.get('ptw_id', '?')} | Isolation: {p.get('isolation_points', [])}"
                )
            elif et in ("shift_handover", "work_order_created"):
                body_lines.append(f"\n[{et.upper()} correlated] at {c.get('occurred_at', '?')}")

        confidence = _calc_confidence(graph_edges, vector_hits)

        return Brief(
            brief_id=str(uuid.uuid4()),
            trigger_event_id=event.event_id,
            trigger_event_type=event.event_type,
            asset_id=event.asset_id,
            work_order_id=event.work_order_id,
            recipient_user_id=event.assigned_technician_id or f"site-{event.site_id}",
            priority="normal",
            headline=headline,
            body="\n".join(body_lines),
            action_items=action_items,
            warnings=warnings,
            quarantine_flags=quarantine_flags,
            sources=sources,
            confidence=confidence,
        )

    # -------------------------------------------------------------------------
    # PTW brief
    # -------------------------------------------------------------------------

    async def assemble_ptw_brief(self, event: PTWEvent) -> Brief:
        topology_task = self._isolation_topology(event.asset_ids)
        reqs_task = self._ptw_regulatory_requirements(event.asset_ids)
        quarantine_task = asyncio.gather(
            *[self._get_quarantine(aid) for aid in event.asset_ids],
            return_exceptions=True,
        )

        results = await asyncio.gather(topology_task, reqs_task, quarantine_task, return_exceptions=True)
        topology, regulations, per_asset_quarantine = [
            r if not isinstance(r, Exception) else [] for r in results
        ]

        # Flatten quarantine flags across all assets in boundary
        quarantine_flags: list[str] = []
        for q_list in (per_asset_quarantine or []):
            if isinstance(q_list, list):
                quarantine_flags += [q["item_id"] for q in q_list if isinstance(q, dict)]

        sources = await _resolve_source_documents(self.supabase, _sources_from_graph(topology))
        warnings = []
        if quarantine_flags:
            warnings.append(f"{len(quarantine_flags)} quarantine item(s) in isolation boundary — review before work")
        if regulations:
            warnings += [r.get("requirement_text", "") for r in regulations[:2]]

        body_lines = [
            f"PTW {event.ptw_id} | Type: {event.ptw_type} | Area: {event.work_area}",
            f"Isolation boundary: {', '.join(event.asset_ids)}",
        ]
        if topology:
            body_lines.append(f"\nGraph knowledge for boundary assets ({len(topology)} records):")
            for e in topology[:5]:
                edge = e.get("edge", {})
                body_lines.append(
                    f"  • {_humanize_rel(edge.get('relationship_type'))} · confidence {edge.get('confidence', '?')}"
                )
        if regulations:
            body_lines.append(f"\nRegulatory requirements ({len(regulations)}):")
            for r in regulations[:3]:
                body_lines.append(f"  • [{r.get('clause_id', '?')}] {r.get('requirement_text', '')}")

        primary_asset = event.asset_ids[0] if event.asset_ids else None
        return Brief(
            brief_id=str(uuid.uuid4()),
            trigger_event_id=event.event_id,
            trigger_event_type=event.event_type,
            asset_id=primary_asset,
            ptw_id=event.ptw_id,
            recipient_user_id=event.issuing_engineer_id,
            priority="critical",
            headline=f"PTW {event.ptw_id} ({event.ptw_type.upper()}) — {len(event.asset_ids)} asset(s) in boundary",
            body="\n".join(body_lines),
            action_items=[
                "Verify all isolation points per PTW checklist",
                "Confirm no active quarantine deviations in boundary",
                "Sign and countersign before work commences",
            ],
            warnings=warnings,
            quarantine_flags=quarantine_flags,
            sources=sources,
            confidence=_calc_confidence(topology, []),
            requires_countersignature=True,
        )

    # -------------------------------------------------------------------------
    # Shift handover brief
    # -------------------------------------------------------------------------

    async def assemble_shift_handover_brief(self, event: ShiftHandoverEvent) -> Brief:
        open_wo_task = self._get_open_work_orders(event.site_id)
        active_alarms_task = self._get_active_alarms(event.site_id)
        conflicts_task = self._get_open_conflicts(None)  # site-wide

        results = await asyncio.gather(
            open_wo_task, active_alarms_task, conflicts_task, return_exceptions=True
        )
        open_wos, alarms, conflicts = [
            r if not isinstance(r, Exception) else [] for r in results
        ]

        warnings = [c["parameter"] for c in conflicts if isinstance(c, dict) and "parameter" in c]

        body_lines = [
            f"Shift handover at {event.handover_time} | Site: {event.site_id}",
            f"Outgoing: {event.outgoing_shift_lead_id} → Incoming: {event.incoming_shift_lead_id}",
        ]
        if open_wos:
            body_lines.append(f"\nOpen work orders ({len(open_wos)}):")
            for wo in open_wos[:5]:
                body_lines.append(f"  • {wo.get('event_id', '?')} — {wo.get('payload', {}).get('description', '')}")
        if alarms:
            body_lines.append(f"\nActive/recent alarms ({len(alarms)}):")
            for a in alarms[:5]:
                body_lines.append(f"  • {a.get('event_id', '?')} [{a.get('asset_id', '?')}]")
        if conflicts:
            body_lines.append(f"\nOpen knowledge conflicts ({len(conflicts)}) — review required")

        return Brief(
            brief_id=str(uuid.uuid4()),
            trigger_event_id=event.event_id,
            trigger_event_type=event.event_type,
            recipient_user_id=event.incoming_shift_lead_id,
            priority="high",
            headline=(
                f"Shift handover: {len(open_wos)} open WO(s), {len(alarms)} alarm(s), "
                f"{len(conflicts)} open conflict(s)"
            ),
            body="\n".join(body_lines),
            action_items=["Review open work orders", "Acknowledge active alarms", "Resolve open knowledge conflicts"],
            warnings=warnings,
            quarantine_flags=[],
            sources=[],
            confidence=0.9,
        )

    # -------------------------------------------------------------------------
    # Recurring failure brief
    # -------------------------------------------------------------------------

    async def assemble_recurring_failure_brief(self, event_dict: dict[str, Any]) -> Brief:
        asset_id = event_dict["asset_id"]
        failure_code = event_dict.get("failure_code", "UNKNOWN")
        recurrence_count = event_dict.get("recurrence_count", 1)
        failure_family = event_dict.get("failure_family", failure_code)
        event_id = event_dict.get("event_id")

        graph_task = self.graph.get_asset_knowledge_at(asset_id)
        vector_task = self._vector_search(f"failure {failure_code} {failure_family}", asset_id)
        timeline_task = self._get_failure_timeline(asset_id)
        quarantine_task = self._get_quarantine(asset_id)

        results = await asyncio.gather(
            graph_task, vector_task, timeline_task, quarantine_task,
            return_exceptions=True,
        )
        graph_edges, vector_hits, timeline, quarantine_items = [
            r if not isinstance(r, Exception) else [] for r in results
        ]

        sources = await _resolve_source_documents(
            self.supabase, _sources_from_graph(graph_edges) + _sources_from_vector(vector_hits)
        )
        quarantine_flags = [q["item_id"] for q in quarantine_items if isinstance(q, dict)]

        total_occurrences = recurrence_count + 1
        headline = (
            f"Asset {asset_id} has failed with {failure_code} "
            f"{total_occurrences} time(s) in 90 days — recurring {failure_family} failure pattern"
        )

        body_lines = [
            f"Failure code: {failure_code} | Family: {failure_family} | Total occurrences (90 days): {total_occurrences}",
        ]

        if timeline:
            body_lines.append(f"\nFailure timeline — {len(timeline)} work order(s) in 90 days:")
            prev_ts: str | None = None
            for i, row in enumerate(timeline[:6]):
                occurred = row.get("occurred_at", "?")
                fc = (row.get("payload") or {}).get("failure_code", "?")
                body_lines.append(f"  [{i + 1}] {occurred} — {fc}")
                if prev_ts and occurred != "?":
                    try:
                        t1 = datetime.fromisoformat(occurred.replace("Z", "+00:00"))
                        t2 = datetime.fromisoformat(prev_ts.replace("Z", "+00:00"))
                        days_between = abs((t2 - t1).days)
                        body_lines.append(f"       ↑ {days_between} day(s) since prior failure")
                    except Exception:
                        pass
                prev_ts = occurred if occurred != "?" else prev_ts
            if len(timeline) >= 3:
                body_lines.append("\n⚠ Three or more failures in 90 days — check for accelerating degradation")

        if vector_hits:
            body_lines.append(f"\nRelated patterns across equipment class (top {min(3, len(vector_hits))}):")
            for h in vector_hits[:3]:
                p = h.get("payload", {})
                body_lines.append(f"  • [{p.get('document_id', '?')}] score={h.get('score', 0):.2f}")

        return Brief(
            brief_id=str(uuid.uuid4()),
            trigger_event_id=event_id,
            trigger_event_type="recurring_failure_detected",
            asset_id=asset_id,
            work_order_id=event_dict.get("work_order_id"),
            recipient_user_id=event_dict.get("assigned_technician_id") or f"site-{event_dict.get('site_id', 'unknown')}",
            priority="high",
            headline=headline,
            body="\n".join(body_lines),
            action_items=[
                f"Investigate root cause of recurring {failure_family} failure ({total_occurrences}× in 90 days)",
                "Review failure interval trend — check for accelerating degradation",
                "Raise reliability review if interval between failures is decreasing",
            ],
            warnings=[f"Recurring {failure_family} failure — pattern suggests systematic issue"],
            quarantine_flags=quarantine_flags,
            sources=sources,
            confidence=_calc_confidence(graph_edges, vector_hits),
        )

    # -------------------------------------------------------------------------
    # Tag-out brief
    # -------------------------------------------------------------------------

    async def assemble_tag_out_brief(self, event_dict: dict[str, Any]) -> Brief:
        asset_id = event_dict["asset_id"]
        tag_out_reason = event_dict.get("tag_out_reason", "")
        performed_by = event_dict.get("performed_by", "unknown")
        event_id = event_dict.get("event_id")

        topology_task = self._asset_pid_topology(asset_id)
        ptw_task = self._get_active_ptw_for_asset(asset_id)
        moc_task = self._get_open_moc(asset_id)
        compliance_task = self._get_asset_compliance_obligations(asset_id)

        results = await asyncio.gather(
            topology_task, ptw_task, moc_task, compliance_task,
            return_exceptions=True,
        )
        topology, ptw_items, moc_items, compliance_reqs = [
            r if not isinstance(r, Exception) else [] for r in results
        ]

        dep_count = len(topology) + len(ptw_items) + len(moc_items)
        headline = f"Asset {asset_id} is being tagged out — {dep_count} downstream dependencies identified"

        body_lines = [
            f"Tag-out raised by: {performed_by} | Reason: {tag_out_reason}",
        ]
        if topology:
            body_lines.append(f"\nP&ID isolation topology — {len(topology)} connected element(s):")
            for t in topology[:5]:
                body_lines.append(f"  • {t.get('element', '?')} [{t.get('type', '?')}]")
        if ptw_items:
            body_lines.append(f"\nActive PTW items referencing this asset ({len(ptw_items)}):")
            for p in ptw_items[:3]:
                body_lines.append(f"  • PTW {(p.get('payload') or {}).get('ptw_id', '?')} at {p.get('occurred_at', '?')}")
        if moc_items:
            body_lines.append(f"\nOpen MoC items for this asset ({len(moc_items)}):")
            for m in moc_items[:3]:
                body_lines.append(f"  • {m.get('moc_id', '?')} — {m.get('description', '')[:80]}")
        if compliance_reqs:
            body_lines.append(f"\nCompliance obligations on tag-out ({len(compliance_reqs)} regulation(s)):")
            for r in compliance_reqs[:3]:
                body_lines.append(f"  • [{r.get('clause_id', '?')}] {r.get('requirement_text', '')[:80]}")

        return Brief(
            brief_id=str(uuid.uuid4()),
            trigger_event_id=event_id,
            trigger_event_type="equipment_tag_out",
            asset_id=asset_id,
            recipient_user_id=f"site-{event_dict.get('site_id', 'unknown')}",
            priority="high",
            headline=headline,
            body="\n".join(body_lines),
            action_items=[
                f"Verify {len(topology)} downstream elements are safely isolated",
                "Confirm no active PTW items conflict with tag-out scope",
                "Update CMMS with expected return date before work commences",
            ],
            warnings=["Open MoC items exist for this asset"] if moc_items else [],
            quarantine_flags=[],
            sources=[],
            confidence=0.85,
        )

    # -------------------------------------------------------------------------
    # Inspection brief
    # -------------------------------------------------------------------------

    async def assemble_inspection_brief(self, event_dict: dict[str, Any]) -> Brief:
        asset_id = event_dict["asset_id"]
        inspection_type = event_dict.get("inspection_type", "")
        result = event_dict.get("result", "")
        findings = event_dict.get("findings", "")
        performed_by = event_dict.get("performed_by", "unknown")
        event_id = event_dict.get("event_id")

        timeline_task = self._get_failure_timeline(asset_id)
        last_inspection_task = self._get_last_inspection(asset_id)
        compliance_task = self._get_asset_compliance_obligations(asset_id)

        results = await asyncio.gather(
            timeline_task, last_inspection_task, compliance_task,
            return_exceptions=True,
        )
        timeline, last_inspections, compliance_reqs = [
            r if not isinstance(r, Exception) else [] for r in results
        ]

        headline = (
            f"Inspection {inspection_type} FAILED on {asset_id} — "
            f"{len(timeline)} prior failure(s) in 90 days"
        ) if result == "failed" else (
            f"Inspection {inspection_type} on {asset_id} — findings require review"
        )

        body_lines = [
            f"Inspector: {performed_by} | Type: {inspection_type} | Result: {result.upper()}",
        ]
        if findings:
            body_lines.append(f"Findings: {findings}")
        if timeline:
            body_lines.append(f"\nFailure history — {len(timeline)} work order(s) in 90 days:")
            for row in timeline[:5]:
                body_lines.append(f"  • {row.get('occurred_at', '?')} — {(row.get('payload') or {}).get('failure_code', '?')}")
        if last_inspections:
            prev = last_inspections[0]
            body_lines.append(
                f"\nPrevious inspection: {prev.get('occurred_at', '?')} "
                f"— result: {(prev.get('payload') or {}).get('result', '?')}"
            )
        if compliance_reqs:
            body_lines.append(f"\nRelated compliance obligations ({len(compliance_reqs)}):")
            for r in compliance_reqs[:2]:
                body_lines.append(f"  • [{r.get('clause_id', '?')}] {r.get('requirement_text', '')[:80]}")

        return Brief(
            brief_id=str(uuid.uuid4()),
            trigger_event_id=event_id,
            trigger_event_type="inspection_complete",
            asset_id=asset_id,
            recipient_user_id=f"site-{event_dict.get('site_id', 'unknown')}",
            priority="high",
            headline=headline,
            body="\n".join(body_lines),
            action_items=[
                f"Review inspection findings for {asset_id}",
                "Raise corrective work order if defects confirmed",
                "Check compliance obligations — inspection interval may be affected",
            ],
            warnings=[f"Inspection result: {result.upper()}"] if result == "failed" else [],
            quarantine_flags=[],
            sources=[],
            confidence=0.8,
        )

    # -------------------------------------------------------------------------
    # Delivery — save to Supabase, publish to briefs Redis stream
    # -------------------------------------------------------------------------

    async def deliver(self, brief: Brief, redis) -> str:
        """
        Saves brief to Supabase and publishes to Redis briefs stream.
        Cool-down: if a brief for the same (recipient, asset) was delivered within
        the last 4 hours, skips delivery and returns the existing brief_id.
        PTW briefs (priority='critical') always bypass cool-down.
        """
        if brief.asset_id and brief.priority != "critical":
            cooldown_floor = (datetime.now(UTC) - timedelta(hours=4)).isoformat()
            existing = await asyncio.to_thread(
                lambda: self.supabase.table("briefs")
                .select("brief_id")
                .eq("recipient_user_id", brief.recipient_user_id)
                .eq("asset_id", brief.asset_id)
                .gte("created_at", cooldown_floor)
                .limit(1)
                .execute()
            )
            if existing.data:
                prior_id = existing.data[0]["brief_id"]
                log.info(
                    "brief_engine.cooldown_suppressed",
                    asset_id=brief.asset_id,
                    recipient=brief.recipient_user_id,
                    prior_brief_id=prior_id,
                )
                return prior_id

        delivered_at = datetime.now(UTC).isoformat()

        row = {
            "brief_id": brief.brief_id,
            "trigger_event_id": brief.trigger_event_id,
            "trigger_event_type": brief.trigger_event_type,
            "asset_id": brief.asset_id,
            "work_order_id": brief.work_order_id,
            "ptw_id": brief.ptw_id,
            "recipient_user_id": brief.recipient_user_id,
            "priority": brief.priority,
            "headline": brief.headline,
            "body": brief.body,
            "action_items": [ai for ai in brief.action_items],
            "warnings": brief.warnings,
            "quarantine_flags": brief.quarantine_flags,
            "sources": [s.model_dump() for s in brief.sources],
            "confidence": brief.confidence,
            "requires_countersignature": brief.requires_countersignature,
            "delivered_at": delivered_at,
        }
        await asyncio.to_thread(
            lambda: self.supabase.table("briefs").insert(row).execute()
        )

        # Phase gate (Layer 12). Proactive *push* is the Phase 3 capability — before that the
        # brief is still assembled and readable in the inbox, it is simply not pushed at the
        # operator. Persisting it and skipping the publish is the difference between
        # "not yet trusted to interrupt you" and "not built".
        if self.settings.KAIROS_PHASE < 3:
            log.info(
                "brief_engine.proactive_suppressed_by_phase",
                brief_id=brief.brief_id,
                phase=self.settings.KAIROS_PHASE,
            )
            return brief.brief_id

        bus = EventBusService(redis, self.settings)
        await bus.publish(self.settings.REDIS_STREAM_BRIEFS, {
            "brief_id": brief.brief_id,
            "recipient_user_id": brief.recipient_user_id,
            "priority": brief.priority,
            "trigger_event_id": brief.trigger_event_id,
            "trigger_event_type": brief.trigger_event_type,
            "headline": brief.headline,
        })

        briefs_delivered.add(1, {
            "priority": brief.priority,
            "trigger_event_type": brief.trigger_event_type,
        })
        log.info(
            "brief_engine.delivered",
            brief_id=brief.brief_id,
            recipient=brief.recipient_user_id,
            priority=brief.priority,
            trigger=brief.trigger_event_type,
        )
        return brief.brief_id

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    async def _get_failure_timeline(self, asset_id: str) -> list[dict[str, Any]]:
        """90-day work order history for an asset — used for recurrence interval analysis."""
        cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        try:
            result = await asyncio.to_thread(
                lambda: self.supabase.table("operational_events")
                .select("occurred_at, payload")
                .eq("asset_id", asset_id)
                .eq("event_type", "work_order_created")
                .gte("occurred_at", cutoff)
                .order("occurred_at", desc=True)
                .limit(20)
                .execute()
            )
            return result.data or []
        except Exception as e:
            log.warning("brief_engine.failure_timeline_failed", error=str(e))
            return []

    async def _get_correlated_events(self, event_id: str) -> list[dict[str, Any]]:
        """Fetches other events sharing the same compound_event_id."""
        try:
            row = await asyncio.to_thread(
                lambda: self.supabase.table("operational_events")
                .select("compound_event_id")
                .eq("event_id", event_id)
                .execute()
            )
            compound_id = row.data[0].get("compound_event_id") if row.data else None
            if not compound_id:
                return []
            corr = await asyncio.to_thread(
                lambda: self.supabase.table("operational_events")
                .select("event_type, payload, occurred_at")
                .eq("compound_event_id", compound_id)
                .neq("event_id", event_id)
                .execute()
            )
            return corr.data or []
        except Exception as e:
            log.warning("brief_engine.correlated_events_failed", error=str(e))
            return []

    async def _vector_search(self, query: str, asset_id: str) -> list[dict[str, Any]]:
        try:
            vector = await self.llm.embed(query, task="retrieval.query")
            return await self.vector.search(
                self.settings.QDRANT_COLLECTION_KNOWLEDGE,
                vector,
                asset_id=asset_id,
                limit=5,
            )
        except Exception as e:
            log.warning("brief_engine.vector_search_failed", error=str(e))
            return []

    async def _get_quarantine(self, asset_id: str) -> list[dict[str, Any]]:
        result = await asyncio.to_thread(
            lambda: self.supabase.table("quarantine_items")
            .select("item_id, review_status")
            .eq("asset_id", asset_id)
            .eq("review_status", "pending")
            .execute()
        )
        return result.data or []

    async def _get_open_conflicts(self, asset_id: str | None) -> list[dict[str, Any]]:
        query = self.supabase.table("knowledge_conflicts").select("conflict_id, parameter, track, severity").in_("status", ["open", "pending_moc"])
        if asset_id:
            query = query.eq("asset_id", asset_id)
        result = await asyncio.to_thread(lambda: query.execute())
        return result.data or []

    async def _es_procedures(self, asset_id: str) -> list[dict[str, Any]]:
        try:
            resp = await self.es.search(
                index=self.settings.ELASTICSEARCH_INDEX_DOCUMENTS,
                body={
                    "query": {"bool": {
                        "must": [
                            {"term": {"asset_id": asset_id}},
                            {"term": {"document_type": "procedure"}},
                        ],
                        # A brief that cites a superseded procedure is worse than one that cites
                        # none — the technician has no way to tell it was replaced.
                        "must_not": [{"term": {"status": "superseded"}}],
                    }},
                    "_source": ["document_id", "title", "authority_level"],
                    "size": 5,
                },
            )
            return [h["_source"] for h in resp["hits"]["hits"]]
        except Exception as e:
            log.warning("brief_engine.es_procedures_failed", error=str(e))
            return []

    async def _isolation_topology(self, asset_ids: list[str]) -> list[dict[str, Any]]:
        """Graph edges for all assets in the PTW isolation boundary."""
        edges: list[dict[str, Any]] = []
        tasks = [self.graph.get_asset_knowledge_at(aid) for aid in asset_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                edges.extend(r)
        return edges

    async def _ptw_regulatory_requirements(self, asset_ids: list[str]) -> list[dict[str, Any]]:
        """Regulations that apply to the equipment inside the isolation boundary.

        This returned the first 5 OISD clauses regardless of what was being isolated, so a valve
        permit listed pump-overhaul and pressure-vessel rules as its regulatory warnings.
        """
        cypher = f"""
        MATCH (a:Asset) WHERE a.asset_id IN $asset_ids
        MATCH (reg:Concept {{type: 'Regulation'}})
        WHERE {_CLAUSE_APPLIES_TO_ASSET}
        RETURN DISTINCT reg.clause_id AS clause_id, reg.requirement_text AS requirement_text
        ORDER BY clause_id
        LIMIT 5
        """
        async with self.graph.driver.session(database=self.graph.database) as session:
            result = await session.run(cypher, asset_ids=asset_ids)
            return [dict(r) async for r in result]

    async def _get_open_work_orders(self, site_id: str) -> list[dict[str, Any]]:
        result = await asyncio.to_thread(
            lambda: self.supabase.table("operational_events")
            .select("event_id, asset_id, payload, occurred_at")
            .eq("event_type", "work_order_created")
            .eq("site_id", site_id)
            .order("occurred_at", desc=True)
            .limit(10)
            .execute()
        )
        return result.data or []

    async def _asset_pid_topology(self, asset_id: str) -> list[dict[str, Any]]:
        """Engineer-verified P&ID elements on the drawing containing this asset.

        Delegates to `GraphService.get_verified_topology_for_asset` so briefs and synthesis read
        topology through one query. This method previously matched
        `(:Asset)-[{relationship_type:'pid_topology'}]->()` — a relationship type nothing writes,
        in a direction that does not exist — so it returned `[]` for every asset and every PTW and
        tag-out brief silently shipped with no isolation devices. It read as "this asset has no
        topology" when the real meaning was "this query cannot match anything".
        """
        rows = await self.graph.get_verified_topology_for_asset(asset_id)
        # Keep the {element, type} shape the brief body and `_sources_from_graph` expect.
        return [
            {
                "element": r.get("label") or r.get("element_id"),
                "type": r.get("element_type"),
                "element_id": r.get("element_id"),
                "document_id": r.get("document_id"),
                "verification_status": r.get("verification_status"),
            }
            for r in rows
        ]

    async def _get_active_ptw_for_asset(self, asset_id: str) -> list[dict[str, Any]]:
        """Supabase query for active PTW events referencing this asset in their payload."""
        try:
            result = await asyncio.to_thread(
                lambda: self.supabase.table("operational_events")
                .select("event_id, payload, occurred_at")
                .eq("event_type", "ptw_generated")
                .contains("payload", {"asset_ids": [asset_id]})
                .order("occurred_at", desc=True)
                .limit(5)
                .execute()
            )
            return result.data or []
        except Exception as e:
            log.warning("brief_engine.active_ptw_failed", error=str(e))
            return []

    async def _get_open_moc(self, asset_id: str) -> list[dict[str, Any]]:
        """Supabase query for open MoC items for this asset."""
        try:
            result = await asyncio.to_thread(
                lambda: self.supabase.table("moc_items")
                .select("moc_id, description, status, created_at")
                .eq("asset_id", asset_id)
                .eq("status", "draft")
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )
            return result.data or []
        except Exception as e:
            log.warning("brief_engine.open_moc_failed", error=str(e))
            return []

    async def _get_asset_compliance_obligations(self, asset_id: str) -> list[dict[str, Any]]:
        """Neo4j query for regulations applicable to this asset's equipment class."""
        cypher = f"""
        MATCH (a:Asset {{asset_id: $asset_id}})
        MATCH (reg:Concept {{type: 'Regulation'}})
        WHERE {_CLAUSE_APPLIES_TO_ASSET}
        RETURN reg.clause_id AS clause_id, reg.requirement_text AS requirement_text
        LIMIT 5
        """
        try:
            async with self.graph.driver.session(database=self.graph.database) as session:
                result = await session.run(cypher, asset_id=asset_id)
                return [dict(r) async for r in result]
        except Exception as e:
            log.warning("brief_engine.compliance_obligations_failed", error=str(e))
            return []

    async def _get_last_inspection(self, asset_id: str) -> list[dict[str, Any]]:
        """Supabase query for the most recent prior inspection event for this asset."""
        try:
            result = await asyncio.to_thread(
                lambda: self.supabase.table("operational_events")
                .select("event_id, occurred_at, payload")
                .eq("asset_id", asset_id)
                .eq("event_type", "inspection_complete")
                .order("occurred_at", desc=True)
                .limit(3)
                .execute()
            )
            return result.data or []
        except Exception as e:
            log.warning("brief_engine.last_inspection_failed", error=str(e))
            return []

    async def _get_active_alarms(self, site_id: str) -> list[dict[str, Any]]:
        result = await asyncio.to_thread(
            lambda: self.supabase.table("operational_events")
            .select("event_id, asset_id, occurred_at")
            .eq("event_type", "alarm_acknowledged")
            .eq("site_id", site_id)
            .order("occurred_at", desc=True)
            .limit(10)
            .execute()
        )
        return result.data or []


# -------------------------------------------------------------------------
# Module-level helpers
# -------------------------------------------------------------------------

# Friendly labels for the relationship types that appear on KNOWLEDGE_EDGEs, so
# brief bodies read as operator language instead of graph internals.
_REL_FRIENDLY = {
    "DOCUMENTED_BY": "document link",
    "HAS_MAX_PRESSURE": "pressure limit",
    "HAS_FAILURE_MODE": "failure mode",
    "INSPECTION_RECORD": "inspection record",
    "CONTAINS_TOPOLOGY_ELEMENT": "drawing element",
    "GOVERNED_BY": "governing procedure",
    "HAS_PARAMETER": "process parameter",
}


# Same applicability rule the compliance cockpit uses (routers/compliance.py): clauses name a coarse
# class ("valve") while assets carry a specific one ("valve_isolation"), so equality matched nothing
# and a tag-out brief listed no obligations. NULL = applies to every class.
_CLAUSE_APPLIES_TO_ASSET = """(reg.applies_to_equipment_class IS NULL
            OR a.equipment_class = reg.applies_to_equipment_class
            OR a.equipment_class CONTAINS reg.applies_to_equipment_class
            OR reg.applies_to_equipment_class CONTAINS a.equipment_class)"""


def _humanize_rel(rel: str | None) -> str:
    if not rel:
        return "record"
    return _REL_FRIENDLY.get(rel, rel.replace("_", " ").lower())


def _distinct_docs(edges: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for e in edges:
        doc = e.get("edge", {}).get("document_id")
        if doc and doc not in seen:
            seen.append(doc)
    return seen


def _summarize_relationships(edges: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for e in edges:
        label = _humanize_rel(e.get("edge", {}).get("relationship_type"))
        counts[label] = counts.get(label, 0) + 1
    parts = [f"{n}× {label}" for label, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    return ", ".join(parts[:4])


def _sources_from_graph(edges: list[dict[str, Any]]) -> list[SourceCitation]:
    sources = []
    for e in edges:
        edge = e.get("edge", {})
        doc_id = edge.get("document_id")
        if not doc_id:
            continue
        # The body was humanised long ago; this source list was not, and it is what an
        # operator actually reads under the prose. It used to emit the raw graph relationship
        # type ("DOCUMENTED_BY") as the excerpt and "unknown" as the type — internals leaking
        # into a point-of-action brief. `_humanize_rel` already existed for the body text.
        rel = _humanize_rel(edge.get("relationship_type"))
        verified = edge.get("verification_status") == "verified"
        sources.append(SourceCitation(
            document_id=doc_id,
            document_type=edge.get("document_type") or "linked record",
            title=doc_id,  # replaced with the real document title by `_resolve_source_documents`
            authority_level=edge.get("authority_level", 5),
            relevant_excerpt=(
                f"Linked to this asset as {rel}."
                if verified
                else f"Linked to this asset as {rel} — link not yet engineer-verified."
            ),
            # `is_quarantine` means "this came from the quarantine layer", NOT "this edge is
            # unverified". Conflating them badged every vault document as quarantine, because
            # every edge starts `unverified` by design — a warning that fires on all sources
            # discriminates nothing, and it mislabelled an authority-4 permit as an unverified
            # field observation. Edge verification is disclosed in the excerpt instead.
            is_quarantine=False,
        ))
    return sources


async def _resolve_source_documents(supabase, sources: list[SourceCitation]) -> list[SourceCitation]:
    """Fill in real document titles and vault links, batched.

    A brief's source list showed `title: "DOC-CPLLSP2QYWUN"` with `vault_url: null` — an opaque
    id an operator cannot act on, and no way to open the underlying document from a
    point-of-action surface. The ids are all we have at graph-read time; the human-readable
    identity lives in Supabase `documents`.

    Best-effort: on any lookup failure the caller keeps the id-titled sources rather than losing
    the citation entirely, because a brief without provenance is worse than one with a terse id.
    """
    doc_ids = sorted({s.document_id for s in sources if s.document_id})
    if not doc_ids:
        return sources
    try:
        rows = await asyncio.to_thread(
            lambda: supabase.table("documents")
            .select("document_id, file_name, document_type, vault_url")
            .in_("document_id", doc_ids)
            .execute()
        )
        by_id = {r["document_id"]: r for r in (rows.data or [])}
    except Exception as exc:  # noqa: BLE001
        log.warning("brief_engine.source_resolve_failed", error=str(exc), documents=len(doc_ids))
        return sources

    for s in sources:
        row = by_id.get(s.document_id)
        if not row:
            continue
        s.title = row.get("file_name") or s.title
        s.vault_url = row.get("vault_url") or s.vault_url
        if row.get("document_type"):
            s.document_type = row["document_type"]
    return sources


def _sources_from_vector(hits: list[dict[str, Any]]) -> list[SourceCitation]:
    sources = []
    for h in hits:
        p = h.get("payload", {})
        doc_id = p.get("document_id")
        if not doc_id:
            continue
        sources.append(SourceCitation(
            document_id=doc_id,
            document_type=p.get("document_type", "unknown"),
            title=p.get("title", doc_id),
            authority_level=p.get("authority_level", 5),
            # Was "Semantic similarity score: 0.412" — a retrieval debug value shown to an
            # operator as if it were an excerpt. Prefer real text; fall back to plain words.
            relevant_excerpt=(
                (p.get("text") or p.get("content") or "").strip()[:200]
                or "Matched this asset on semantic similarity."
            ),
            is_quarantine=p.get("is_quarantine", False),
        ))
    return sources


def _calc_confidence(graph_edges: list, vector_hits: list) -> float:
    if not graph_edges and not vector_hits:
        return 0.3
    verified = sum(
        1 for e in graph_edges
        if e.get("edge", {}).get("verification_status") == "verified"
    )
    if not graph_edges:
        return 0.6
    return min(0.5 + 0.1 * verified + 0.05 * min(len(vector_hits), 5), 0.95)
