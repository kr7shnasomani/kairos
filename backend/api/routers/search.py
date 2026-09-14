"""
Search router — Layer 11: Reasoning and Synthesis Layer.
Hybrid retrieval: exact match (ES) + semantic vector (Qdrant) + graph traversal (Neo4j).
"""

import asyncio
import json
from datetime import datetime, timedelta

import structlog
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from api.dependencies import (
    CurrentUserDep,
    ElasticsearchDep,
    Neo4jDep,
    QdrantDep,
    SettingsDep,
    SupabaseDep,
)
from api.models.document import (
    AnswerFeedbackRequest,
    RCAPackRequest,
    RCAPackResponse,
    SearchResponse,
    SynthesizeRequest,
    SynthesizeResponse,
)
from api.services.corpus import document_rows
from api.services.graph import GraphService
from api.services.llm import SAFETY_CRITICAL_CATEGORIES, LLMService, query_asset_tags
from api.services.search_engine import SearchEngineService
from api.services.search_service import SearchService
from api.services.timeline import merge_timeline
from api.services.vector_store import VectorStoreService

log = structlog.get_logger(__name__)

router = APIRouter()


async def pending_moc_warnings(supabase, sources: list[dict]) -> list[dict]:
    """
    Open engineering-track conflicts awaiting MoC resolution for any asset cited in an answer.

    ARCHITECTURE.md Layer 7 and Flow C both require it: while a parameter conflict is in the MoC
    queue the canonical graph is deliberately NOT updated, so an answer drawn from that asset is
    reporting a value that is under formal dispute. Without this the user sees a confident answer
    and no indication that engineering is actively resolving a contradiction on it.

    Returns [] on any lookup failure — a warning that cannot be fetched must not take the answer
    down with it, but the failure is logged rather than hidden.
    """
    asset_ids = sorted({s.get("asset_id") for s in sources if s.get("asset_id")})
    if not asset_ids:
        return []
    try:
        conflicts = await asyncio.to_thread(
            lambda: supabase.table("knowledge_conflicts")
            .select("conflict_id, asset_id, parameter, severity, sla_deadline")
            .eq("status", "pending_moc")
            .in_("asset_id", asset_ids)
            .execute()
        )
        rows = conflicts.data or []
        if not rows:
            return []

        # Identify the MoC "by number" — moc_items.conflict_id is the link.
        mocs = await asyncio.to_thread(
            lambda: supabase.table("moc_items")
            .select("moc_id, conflict_id, status")
            .in_("conflict_id", [r["conflict_id"] for r in rows])
            .execute()
        )
        by_conflict = {m["conflict_id"]: m for m in (mocs.data or [])}
    except Exception as exc:  # noqa: BLE001
        log.warning("synthesis.pending_moc_lookup_failed", error=str(exc))
        return []

    return [
        {
            "conflict_id": r["conflict_id"],
            "asset_id": r["asset_id"],
            "parameter": r["parameter"],
            "severity": r["severity"],
            "moc_id": (by_conflict.get(r["conflict_id"]) or {}).get("moc_id"),
            "moc_status": (by_conflict.get(r["conflict_id"]) or {}).get("status"),
        }
        for r in rows
    ]


@router.get("/", response_model=SearchResponse, summary="Hybrid knowledge search")
async def search(
    settings: SettingsDep,
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    qdrant: QdrantDep,
    es: ElasticsearchDep,
    supabase: SupabaseDep,
    q: str = Query(..., description="Natural language or structured query"),
    asset_id: str | None = Query(None, description="Scope search to a specific asset"),
    authority_min: int = Query(5, ge=1, le=5, description="Minimum authority level to include (1=Regulatory only, 5=all)"),
    include_quarantine: bool = Query(False, description="Include unverified quarantine layer items"),
    as_of: str | None = Query(None, description="ISO8601 timestamp for time-travel search"),
    limit: int = Query(10, le=50),
) -> SearchResponse:
    """
    Hybrid retrieval using three parallel methods:
    1. Exact match (ES) — tag numbers, part numbers, clause refs, document IDs
    2. Semantic vector search (Qdrant) — conceptual queries
    3. Graph traversal (Neo4j) — relationship and time-travel queries (requires asset_id)

    Results are authority-ranked: regulatory requirements (level 1) outrank field observations (level 5).
    Phase 1: retrieval only. synthesis=None until Phase 2.
    """
    as_of_dt = datetime.fromisoformat(as_of) if as_of else None

    svc = SearchService(
        graph=GraphService(driver, settings.NEO4J_DATABASE),
        vector=VectorStoreService(qdrant, settings),
        engine=SearchEngineService(es, settings),
        llm=LLMService(settings),
        supabase=supabase,
    )
    results = await svc.hybrid_search(
        query=q,
        collection=settings.QDRANT_COLLECTION_DOCUMENTS,
        asset_id=asset_id,
        authority_min=authority_min,
        include_quarantine=include_quarantine,
        as_of=as_of_dt,
        limit=limit,
    )

    # Batch-fetch vault_url from Supabase so frontend can render "view source" links
    doc_ids = [r.document_id for r in results if r.document_id]
    if doc_ids:
        vault_rows = await asyncio.to_thread(
            lambda: supabase.table("documents")
            .select("document_id, vault_url")
            .in_("document_id", doc_ids)
            .execute()
        )
        vault_map = {row["document_id"]: row.get("vault_url") for row in (vault_rows.data or [])}
        for r in results:
            r.vault_url = vault_map.get(r.document_id)

    methods = sorted({r.retrieval_method for r in results})
    return SearchResponse(
        query=q,
        results=results,
        total=len(results),
        retrieval_methods=methods,
        pending_moc=await pending_moc_warnings(supabase, [{"asset_id": r.asset_id} for r in results]),
    )


@router.get("/assets/{asset_id}", summary="Search within a specific asset's knowledge")
async def search_asset(
    asset_id: str,
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    qdrant: QdrantDep,
    es: ElasticsearchDep,
    settings: SettingsDep,
    supabase: SupabaseDep,
    q: str = Query(...),
    limit: int = Query(10, le=50),
) -> SearchResponse:
    """Asset-scoped hybrid search — delegates to the main search with asset_id locked."""
    svc = SearchService(
        graph=GraphService(driver, settings.NEO4J_DATABASE),
        vector=VectorStoreService(qdrant, settings),
        engine=SearchEngineService(es, settings),
        llm=LLMService(settings),
        supabase=supabase,
    )
    results = await svc.hybrid_search(
        query=q,
        collection=settings.QDRANT_COLLECTION_DOCUMENTS,
        asset_id=asset_id,
        authority_min=5,
        include_quarantine=False,
        as_of=None,
        limit=limit,
    )
    methods = sorted({r.retrieval_method for r in results})
    return SearchResponse(
        query=q,
        results=results,
        total=len(results),
        retrieval_methods=methods,
        pending_moc=await pending_moc_warnings(supabase, [{"asset_id": asset_id}]),
    )


_TOPOLOGY_EVIDENCE_CATEGORIES = {"isolation_interlock_sequence"}


async def _verified_topology_evidence(query: str, graph: GraphService) -> list[dict]:
    """Engineer-verified P&ID elements for the assets the query names, as gate-eligible evidence.

    Layer 3 → Layer 11. An isolation question ("which valves make up the isolation boundary for
    V-247?") is answerable from the drawing, but retrieval only ever returned *documents* — so the
    best available evidence was the authority-4 site PTW, the gate correctly refused it, and the
    verified drawing sat unused in the graph. That was a wiring gap presenting as a safety refusal.

    Two properties make this safe to admit:

    - **Verified only.** `get_verified_topology_for_asset` returns nothing that an engineer has not
      confirmed element-by-element, so an unverified vision reading can never reach the gate.
    - **The edge's own authority, not an invented one.** `authority_level` and `confidence` are
      read off the `CONTAINS_TOPOLOGY_ELEMENT` edge. Topology does not get a privileged authority
      for being topology; it clears the gate only if the edge it came from already would.

    `asset_id` is set to the queried tag so `_authority_candidates`' same-asset filter matches, and
    `relevance_score` is set high because this evidence was selected *by* asset rather than ranked
    into position — an item with no score would drop the whole context out of the scored branch.
    """
    tags = query_asset_tags(query)
    if not tags:
        return []
    results = await asyncio.gather(
        *[graph.get_verified_topology_for_asset(t) for t in sorted(tags)],
        return_exceptions=True,
    )
    evidence: list[dict] = []
    for tag, rows in zip(sorted(tags), results, strict=False):
        if isinstance(rows, Exception):
            log.warning("synthesis.topology_evidence_failed", asset=tag, error=str(rows))
            continue
        for r in rows:
            label = r.get("label") or r.get("element_id")
            element_type = (r.get("element_type") or "element").replace("_", " ").rstrip("s")
            evidence.append({
                "document_id": r.get("document_id"),
                "asset_id": tag,
                "authority_level": r.get("authority_level"),
                "confidence": r.get("confidence"),
                "relevance_score": 1.0,
                "verification_status": r.get("verification_status"),
                "source_type": "verified_pid_topology",
                "title": f"P&ID topology — {label} ({element_type})",
                "content": (
                    f"{element_type.capitalize()} {label} appears on the P&ID drawing containing "
                    f"{tag}, engineer-verified by {r.get('verified_by') or 'unknown'}."
                ),
            })
    if evidence:
        log.info("synthesis.topology_evidence_added", assets=sorted(tags), elements=len(evidence))
    return evidence


@router.post("/synthesize", response_model=SynthesizeResponse, summary="Synthesize an answer from retrieved knowledge")
async def synthesize(
    payload: SynthesizeRequest,
    current_user: CurrentUserDep,
    settings: SettingsDep,
    supabase: SupabaseDep,
    driver: Neo4jDep,
) -> SynthesizeResponse:
    """
    Assembles retrieved knowledge into a provenance-backed answer via NIM or Ollama.
    Safety-critical categories trigger explicit refusal when evidence confidence is low.
    No-ops cleanly when no LLM is configured (Phase 1 fallback).

    Phase gate (Layer 12): in Phase 1 the deployment is retrieval-only by design — trust in
    retrieval is established before trust in synthesis is requested. The caller still gets its
    retrieved sources, so the answer surface degrades rather than breaking.
    """
    if settings.KAIROS_PHASE < 2:
        log.info("synthesis.phase_gated", phase=settings.KAIROS_PHASE, query_category=payload.query_category)
        return SynthesizeResponse(
            answer=None,
            sources=payload.context or [],
            refused=False,
            message=(
                "Synthesis is not enabled in Phase 1 (shadow / retrieval mode). "
                "The retrieved source documents are returned for direct review."
            ),
        )

    llm = LLMService(settings)

    # Derive the category when the caller didn't supply one. Classifying here rather
    # than in each client means the safety gate applies to every caller — frontend,
    # benchmark, and anything added later — instead of only the ones that remember.
    category = payload.query_category or LLMService.classify_query_category(payload.query)

    # Admit engineer-verified drawing topology alongside the retrieved documents. Server-side for
    # the same reason the category is derived here: every caller gets it, not just the ones that
    # remember to ask.
    context = list(payload.context or [])
    if category in _TOPOLOGY_EVIDENCE_CATEGORIES:
        context += await _verified_topology_evidence(
            payload.query, GraphService(driver, settings.NEO4J_DATABASE)
        )

    result = await llm.synthesize(payload.query, context, category)

    parsed: dict = {}
    if result.get("answer"):
        parsed = LLMService.parse_synthesis_response(result["answer"])

    refused = bool(result.get("refused"))
    safety_critical = category in SAFETY_CRITICAL_CATEGORIES if category else False

    # Computed from the sources actually returned (refusals include them too), so a refusal
    # that hands back source documents still says those documents are under MoC dispute.
    pending_moc = await pending_moc_warnings(supabase, result.get("sources", []) or [])

    try:
        await asyncio.to_thread(
            lambda: supabase.table("audit_log").insert({
                "action": "synthesis",
                "entity_type": "query",
                "performed_by": current_user.get("user_id", "unknown"),
                "details": {
                    "query": payload.query,
                    "query_category": category,
                    "sources_used": parsed.get("sources_used", []),
                    "confidence": parsed.get("confidence"),
                    "refused": refused,
                },
            }).execute()
        )
    except Exception as exc:
        log.warning("synthesis.audit_log_failed", error=str(exc))

    return SynthesizeResponse(
        answer=parsed.get("answer") or result.get("answer"),
        sources=result.get("sources", []),
        confidence=parsed.get("confidence") or result.get("confidence"),
        refused=refused,
        refusal_reason=result.get("refusal_reason"),
        safety_critical=safety_critical,
        sources_used=parsed.get("sources_used", []),
        uncertainty=parsed.get("uncertainty") or result.get("uncertainty"),
        model=result.get("model"),
        message=result.get("message"),
        rate_limited=bool(result.get("rate_limited")),
        pending_moc=pending_moc,
    )


@router.post("/synthesize/stream", summary="Synthesize an answer, streamed as Server-Sent Events")
async def synthesize_stream(
    payload: SynthesizeRequest,
    current_user: CurrentUserDep,
    settings: SettingsDep,
    driver: Neo4jDep,
) -> StreamingResponse:
    """Same answer as `POST /synthesize`, delivered progressively.

    Exists as a SEPARATE endpoint on purpose. `POST /synthesize` has two consumers of its parse
    contract (`workflows/elicitation_workflow.py` and this router) and a measured answer-quality
    figure attached to it; changing it to stream would put that number at risk for a purely
    presentational gain. This adds a surface, it does not alter one.

    Events (`event:` / `data:` JSON):
      * `status`  — pipeline stage. Carries `streaming_text: false` for safety-critical
                    categories, with a `reason` the UI can show.
      * `delta`   — a chunk of answer text. **Never emitted for a safety-critical category.**
      * `restart` — discard everything received so far; the answer was re-synthesized via the
                    fallback cascade and concatenating the two would fabricate a hybrid answer.
      * `done`    — terminal, always sent, carries the same shape `POST /synthesize` returns.
      * `error`   — terminal, only on an unexpected failure.

    A safety-critical answer is withheld until `result_gate` clears it, because `CONFIDENCE:`
    arrives after `ANSWER:` — see `LLMService.result_gate`. The client must therefore treat
    `done` as authoritative and never render `delta` text as final.
    """
    llm = LLMService(settings)
    category = payload.query_category or LLMService.classify_query_category(payload.query)

    context = list(payload.context or [])
    if category in _TOPOLOGY_EVIDENCE_CATEGORIES:
        context += await _verified_topology_evidence(
            payload.query, GraphService(driver, settings.NEO4J_DATABASE)
        )

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

    def _done_payload(data: dict, category: str | None) -> dict:
        """Project the service result onto `SynthesizeResponse`'s fields.

        A StreamingResponse has no `response_model`, so nothing filters this the way the
        non-streaming endpoint is filtered — the first live run shipped the provider's entire
        raw chat-completion object to the client under `raw`. Whitelisted, not blacklisted, so a
        new internal key added to the service result never leaks by default.
        """
        parsed = LLMService.parse_synthesis_response(data["answer"]) if data.get("answer") else {}
        # Strip the `ANSWER:`/`CONFIDENCE:` scaffolding exactly as the non-streaming endpoint
        # does, so a client switching between the two never sees raw markers.
        answer = parsed.get("answer") or data.get("answer")
        return {
            "answer": answer,
            "sources": data.get("sources", []) or [],
            "confidence": parsed.get("confidence") or data.get("confidence"),
            "refused": bool(data.get("refused")),
            "refusal_reason": data.get("refusal_reason"),
            "safety_critical": category in SAFETY_CRITICAL_CATEGORIES if category else False,
            "sources_used": parsed.get("sources_used", []),
            "uncertainty": parsed.get("uncertainty") or data.get("uncertainty"),
            "model": data.get("model"),
            "message": data.get("message"),
            "rate_limited": bool(data.get("rate_limited")),
        }

    async def _events():
        # The phase gate is repeated rather than shared with `synthesize()` because that handler
        # returns a response model and this one returns a byte stream; the *condition* is one
        # line and the divergence risk is lower than the coupling would be.
        if settings.KAIROS_PHASE < 2:
            yield _sse("done", {
                "answer": None,
                "sources": payload.context or [],
                "refused": False,
                "message": (
                    "Synthesis is not enabled in Phase 1 (shadow / retrieval mode). "
                    "The retrieved source documents are returned for direct review."
                ),
            })
            return
        try:
            async for event, data in llm.synthesize_stream(payload.query, context, category):
                if event == "done":
                    data = _done_payload(data, category)
                yield _sse(event, data)
        except Exception as exc:  # noqa: BLE001 — a dead stream must still terminate the client
            log.warning("synthesis.stream_error", error=str(exc), exc_type=type(exc).__name__)
            # The exception text is logged above, never streamed: sent to the browser it exposed
            # provider/internal details (code scanning py/stack-trace-exposure). This yield must
            # stay inside the except — outside it, every successful stream also ended in `error`.
            yield _sse("error", {"message": "Synthesis stream failed."})

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Without this an nginx/ingress in front buffers the whole response and delivers it
            # in one write, which is precisely the blank-screen behaviour this endpoint exists
            # to remove — the stream would still "work" and still feel like 65 s.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feedback", summary="Rate a synthesized answer (Phase 2 trust loop)")
async def submit_answer_feedback(
    payload: AnswerFeedbackRequest,
    current_user: CurrentUserDep,
    supabase: SupabaseDep,
) -> dict:
    """
    Records the single-tap rating on a synthesized answer: accurate / missing_context / incorrect.

    ARCHITECTURE.md Layer 12, Phase 2 calls this "direct input to the outcome attribution system
    and Layer 0 validation", not UX research. The copilot rendered these buttons but never sent
    the result anywhere, so the trust loop the phase is built around ended at local state.

    Written to `audit_log` alongside the `synthesis` row the same query already writes — no new
    table, and the pair (query, rating) is recoverable by `performed_by` + query text.
    """
    user_id = current_user.get("user_id", "unknown")
    await asyncio.to_thread(
        lambda: supabase.table("audit_log").insert({
            "action": "synthesis_feedback",
            "entity_type": "query",
            "performed_by": user_id,
            "details": {
                "query": payload.query,
                "rating": payload.rating,
                "note": payload.note,
                "sources_used": payload.sources_used,
                "model": payload.model,
            },
        }).execute()
    )
    log.info("synthesis.feedback_recorded", rating=payload.rating, user_id=user_id)
    return {"status": "recorded", "rating": payload.rating}


@router.post("/rca-pack", response_model=RCAPackResponse, summary="Generate RCA pack for an asset incident")
async def generate_rca_pack(
    payload: RCAPackRequest,
    current_user: CurrentUserDep,
    driver: Neo4jDep,
    qdrant: QdrantDep,
    supabase: SupabaseDep,
    settings: SettingsDep,
) -> RCAPackResponse:
    """
    Layer 11 RCA synthesis: assembles failure timeline + ranked hypotheses + supporting documents.

    Three parallel retrieval passes:
      1. Neo4j — Event nodes linked to asset in 90-day window (chronological timeline)
      2. Qdrant — semantic search on failure_code + asset_class against kairos_knowledge
      3. Supabase — operational_events (work orders, alarms, PTWs) in same window

    Passes combined evidence to LLMService for structured RCA synthesis.
    Falls back to raw timeline + documents when no LLM is configured.
    Safety-critical hypotheses: refused=True when confidence < 0.7.
    Every call written to audit_log.
    """
    window_start = payload.incident_date - timedelta(days=90)
    window_start_iso = window_start.isoformat()
    incident_iso = payload.incident_date.isoformat()

    graph = GraphService(driver, settings.NEO4J_DATABASE)
    llm = LLMService(settings)
    vector_store = VectorStoreService(qdrant, settings)

    # -- Parallel retrieval --
    neo4j_future = graph.get_event_timeline(payload.asset_id, window_start_iso)
    supabase_future = asyncio.to_thread(
        lambda: supabase.table("operational_events")
        .select("event_id, event_type, asset_id, occurred_at, payload")
        .eq("asset_id", payload.asset_id)
        .gte("occurred_at", window_start_iso)
        .in_("event_type", ["work_order_created", "alarm_acknowledged", "ptw_generated"])
        .order("occurred_at", desc=False)
        .limit(50)
        .execute()
    )
    asset_future = asyncio.to_thread(
        lambda: supabase.table("assets")
        .select("equipment_class")
        .eq("asset_id", payload.asset_id)
        .execute()
    )

    neo4j_events, supabase_result, asset_result = await asyncio.gather(
        neo4j_future, supabase_future, asset_future
    )

    # Normalise Supabase operational events into timeline format
    supabase_events = [
        {
            "event_id": row.get("event_id"),
            "event_type": row.get("event_type", ""),
            "occurred_at": row.get("occurred_at", ""),
            "description": (row.get("payload") or {}).get("description", ""),
            "source": "operational_events",
            "document_id": None,
        }
        for row in (supabase_result.data or [])
    ]

    # One entry per event, ordered on a UTC clock. Supabase first: its copy carries the description.
    timeline = merge_timeline(supabase_events, neo4j_events)

    # -- Qdrant semantic search --
    asset_class = (asset_result.data[0].get("equipment_class") or "") if asset_result.data else ""
    embed_query = f"{payload.failure_code} {asset_class}".strip()
    query_vector = await llm.embed(embed_query, task="retrieval.query")

    # `kairos_documents`, not `kairos_knowledge`: the ingestion pipeline only ever writes the
    # former (`document_pipeline.py`), so the knowledge collection is created by init_qdrant and
    # then stays empty — measured 2026-08-24, 0 points against 114. RCA was retrieving from it
    # and logging `evidence_count=0` on every call, which the model then answered honestly with
    # weight 0.0 on every hypothesis and no sources. That rendered as zero-width bars and read as
    # a broken chart rather than as "no evidence was found". Same payload shape (`asset_id`,
    # `authority_level`, `document_id`, `text`, `is_quarantine`), so only the name changes.
    evidence_hits = await vector_store.search(
        collection=settings.QDRANT_COLLECTION_DOCUMENTS,
        query_vector=query_vector,
        limit=10,
        asset_id=payload.asset_id,
        include_quarantine=payload.include_quarantine,
    )

    evidence = [
        {
            "document_id": h["payload"].get("document_id", ""),
            "text": h["payload"].get("text") or h["payload"].get("content", ""),
            "authority_level": h["payload"].get("authority_level", 5),
            "confidence": h.get("score", 0.5),
        }
        for h in evidence_hits
    ]

    # -- LLM synthesis --
    rca_result = await llm.rca_synthesize(payload.failure_code, timeline, evidence)

    hypotheses: list = []
    confidence: float | None = None
    refused = False
    synthesis_available = bool(rca_result.get("answer"))

    if synthesis_available:
        parsed = LLMService.parse_rca_response(rca_result["answer"])
        hypotheses = parsed["hypotheses"]
        confidence = parsed["confidence"]

        # Safety-critical refusal: low confidence on safety-relevant failure codes
        safety_keywords = {"pressure", "isolation", "torque", "electrical", "relief", "shutdown", "interlock"}
        code_lower = payload.failure_code.lower()
        if (confidence is not None and confidence < 0.7
                and any(kw in code_lower for kw in safety_keywords)):
            refused = True
            hypotheses = []

    # The vault file name is the title an engineer recognises; without it the pack listed bare
    # "DOC-9V7Z7YCEEXEC" ids under "Supporting documents".
    doc_rows = await document_rows(supabase, [e["document_id"] for e in evidence if e.get("document_id")])
    file_names = {r["document_id"]: r.get("file_name") for r in doc_rows}
    supporting_documents = [
        {
            "document_id": e["document_id"],
            "title": file_names.get(e["document_id"]) or e["document_id"],
            "authority_level": e["authority_level"],
            "confidence": e["confidence"],
        }
        for e in evidence
        if e.get("document_id")
    ]

    # -- Audit log --
    try:
        await asyncio.to_thread(
            lambda: supabase.table("audit_log").insert({
                "action": "rca_pack_generated",
                "entity_type": "asset",
                "entity_id": payload.asset_id,
                "performed_by": current_user.get("user_id", "unknown"),
                "details": {
                    "asset_id": payload.asset_id,
                    "incident_date": incident_iso,
                    "failure_code": payload.failure_code,
                    "timeline_events": len(timeline),
                    "evidence_docs": len(evidence),
                    "hypotheses_count": len(hypotheses),
                    "refused": refused,
                    "synthesis_available": synthesis_available,
                },
            }).execute()
        )
    except Exception as exc:
        log.warning("rca_pack.audit_log_failed", error=str(exc))

    log.info(
        "rca_pack.generated",
        asset_id=payload.asset_id,
        failure_code=payload.failure_code,
        timeline_count=len(timeline),
        evidence_count=len(evidence),
        hypotheses_count=len(hypotheses),
        synthesis_available=synthesis_available,
    )

    return RCAPackResponse(
        asset_id=payload.asset_id,
        incident_date=incident_iso,
        failure_code=payload.failure_code,
        timeline=timeline,
        hypotheses=hypotheses,
        supporting_documents=supporting_documents,
        confidence=confidence,
        refused=refused,
        synthesis_available=synthesis_available,
        pending_moc=await pending_moc_warnings(supabase, [{"asset_id": payload.asset_id}]),
    )
