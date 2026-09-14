"""
Search service — hybrid retrieval pipeline (Layer 11).
Parallel ES exact + Qdrant semantic + Neo4j graph traversal, authority re-ranked.
"""

import asyncio
import re
import time
from datetime import datetime
from typing import Any

import structlog

from api.models.document import SearchResult
from api.services.corpus import document_rows, partition_test_artifacts
from api.services.graph import GraphService
from api.services.llm import LLMService
from api.services.search_engine import SearchEngineService
from api.services.vector_store import VectorStoreService

log = structlog.get_logger(__name__)

# Reciprocal Rank Fusion constant. 60 is the value from the original Cormack et al.
# paper and the de-facto default; it damps the gap between rank 1 and rank 2 so a
# single source cannot dominate the fused ordering on its own.
_RRF_K = 60

# Confirmed aliases change only when a human confirms one, so a short cache keeps a Supabase round
# trip off every search. ponytail: process-local TTL, stale for at most this long after a confirm.
_ALIAS_TTL_SECONDS = 60.0
_alias_cache: tuple[float, list[dict[str, str]]] = (0.0, [])


def expand_query_aliases(query: str, aliases: list[dict[str, str]]) -> str:
    """Append the canonical asset id for every confirmed alias the query names.

    Documents are indexed under the canonical id ("EQ-101"), while people ask with the name they
    use on site ("P-101", "Feed Pump A", "the old Fischer"). Without this, exact match finds nothing
    and the answer is built from whatever semantic search happens to return. The original wording is
    kept so nothing the user typed stops matching; matching is whole-phrase and case-insensitive.
    """
    canonical: list[str] = []
    for row in aliases:
        alias, target = row.get("alias") or "", row.get("canonical_asset_id") or ""
        if not alias or not target or target in canonical:
            continue
        if re.search(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", query, re.IGNORECASE) and not re.search(
            rf"(?<![\w-]){re.escape(target)}(?![\w-])", query, re.IGNORECASE
        ):
            canonical.append(target)
    return f"{query} {' '.join(canonical)}" if canonical else query


class SearchService:
    def __init__(
        self,
        graph: GraphService,
        vector: VectorStoreService,
        engine: SearchEngineService,
        llm: LLMService,
        supabase: Any = None,
    ):
        self.graph = graph
        self.vector = vector
        self.engine = engine
        self.llm = llm
        # Optional: without it, test-artifact filtering below is skipped (fails open, same as
        # corpus.test_artifact_ids itself) rather than breaking callers that predate this param.
        self.supabase = supabase

    async def hybrid_search(
        self,
        query: str,
        collection: str,
        asset_id: str | None,
        authority_min: int,
        include_quarantine: bool,
        as_of: datetime | None,
        limit: int,
    ) -> list[SearchResult]:
        """
        Parallel retrieval from ES + Qdrant + Neo4j.
        Deduplicates by document_id (lowest authority_level wins, then highest score).
        Re-ranks: authority_level ASC, relevance_score DESC.
        """
        query = expand_query_aliases(query, await self._confirmed_aliases())
        query_vector = await self.llm.embed(query, task="retrieval.query")

        # Time-travel: a document superseded *today* was the current one at an earlier as_of, so
        # excluding it would answer the wrong question. Only the default (as_of=None, "what is
        # true now") filters superseded out.
        include_superseded = as_of is not None

        # A document is indexed under one primary `asset_id`, but often concerns several assets: the
        # EQ-1xx work-order CSV is filed under EQ-102 yet holds EQ-101's own seal-failure history, and
        # SOP-HE-GEN-11 is filed under no asset at all. The graph already links every asset a document
        # speaks about, so resolve those links first and let the text searches match either.
        # ponytail: one Neo4j round trip before the parallel searches, instead of a second search pass.
        graph_raw: list[dict[str, Any]] = []
        linked_ids: list[str] = []
        if asset_id:
            try:
                graph_raw = await self.graph.get_asset_knowledge_at(asset_id, as_of=as_of, authority_min=authority_min)
            except Exception as e:  # noqa: BLE001 — one of three sources; degrade to primary-asset scope
                log.error("search.graph_failed", error=str(e))
            linked_ids = sorted({d for h in graph_raw if (d := (h.get("edge") or {}).get("document_id"))})

        coros: list[Any] = [
            self.engine.search(
                query, asset_id=asset_id, limit=limit, include_superseded=include_superseded,
                document_ids=linked_ids,
            ),
            self.vector.search(
                collection, query_vector, limit=limit, asset_id=asset_id,
                authority_min=authority_min, include_superseded=include_superseded,
                document_ids=linked_ids,
            ),
        ]
        if include_quarantine:
            coros.append(
                self.vector.search(
                    collection, query_vector, limit=limit, asset_id=asset_id,
                    authority_min=authority_min, quarantine_only=True,
                    include_superseded=include_superseded, document_ids=linked_ids,
                )
            )

        gathered = await asyncio.gather(*coros, return_exceptions=True)

        es_raw = gathered[0] if not isinstance(gathered[0], Exception) else []
        qdrant_raw = gathered[1] if not isinstance(gathered[1], Exception) else []

        quarantine_raw: list[dict[str, Any]] = []
        if include_quarantine:
            quarantine_raw = gathered[2] if not isinstance(gathered[2], Exception) else []

        if isinstance(gathered[0], Exception):
            log.error("search.es_failed", error=str(gathered[0]))
        if isinstance(gathered[1], Exception):
            log.error("search.qdrant_failed", error=str(gathered[1]))

        # Test-artifact filtering — MUST happen before _fuse truncates to `limit`, not after.
        # The graph source in particular returns one hit per DOCUMENTED_BY edge with no
        # relevance signal of its own beyond RRF rank, so on an asset with many test-sweep
        # edges (see services/corpus.py's module docstring) it was filling every result slot
        # with content-free "documented by" stubs before real evidence was ever ranked.
        file_names: dict[str, str] = {}
        if self.supabase is not None:
            all_ids = (
                [h.get("document_id") for h in es_raw]
                + [h.get("payload", {}).get("document_id") for h in qdrant_raw]
                + [h.get("edge", {}).get("document_id") for h in graph_raw]
                + [h.get("payload", {}).get("document_id") for h in quarantine_raw]
            )
            rows = await document_rows(self.supabase, all_ids)
            file_names = {r["document_id"]: r["file_name"] for r in rows if r.get("file_name")}
            artifact_ids = partition_test_artifacts(rows)
            if artifact_ids:
                before = len(es_raw) + len(qdrant_raw) + len(graph_raw) + len(quarantine_raw)
                es_raw = [h for h in es_raw if h.get("document_id") not in artifact_ids]
                qdrant_raw = [h for h in qdrant_raw if h.get("payload", {}).get("document_id") not in artifact_ids]
                graph_raw = [h for h in graph_raw if h.get("edge", {}).get("document_id") not in artifact_ids]
                quarantine_raw = [
                    h for h in quarantine_raw if h.get("payload", {}).get("document_id") not in artifact_ids
                ]
                after = len(es_raw) + len(qdrant_raw) + len(graph_raw) + len(quarantine_raw)
                log.info("search.test_artifacts_excluded", excluded=before - after, remaining=after)

        results = self._fuse(
            [
                self._normalize_es(es_raw),
                self._normalize_qdrant(qdrant_raw, is_quarantine=False),
                self._normalize_graph(self._rankable_graph_hits(graph_raw, es_raw, qdrant_raw), asset_id),
                self._normalize_qdrant(quarantine_raw, is_quarantine=True),
            ],
            limit,
            asset_id=asset_id,
        )
        # The indexes carry the document id as the title, so a cited source read "DOC-KUXNJRUQYXYQ".
        # The vault file name is already in hand from the artifact lookup above — no extra query.
        for r in results:
            name = file_names.get(r.document_id)
            if name and (not r.title or r.title == r.document_id):
                r.title = name
        return results

    async def _confirmed_aliases(self) -> list[dict[str, str]]:
        """Confirmed alias → canonical rows, cached. Fails open to no expansion, never to an error."""
        global _alias_cache
        if self.supabase is None:
            return []
        fetched_at, rows = _alias_cache
        if time.monotonic() - fetched_at < _ALIAS_TTL_SECONDS:
            return rows
        try:
            res = await asyncio.to_thread(
                lambda: self.supabase.table("asset_alias_map")
                .select("alias, canonical_asset_id")
                .eq("confirmed", True)
                .execute()
            )
            rows = res.data or []
        except Exception as exc:  # noqa: BLE001 — search must still answer without aliases
            log.warning("search.alias_lookup_failed", error=str(exc))
            return rows
        _alias_cache = (time.monotonic(), rows)
        return rows

    def _fuse(
        self, ranked_lists: list[list[SearchResult]], limit: int, asset_id: str | None = None
    ) -> list[SearchResult]:
        """
        Reciprocal Rank Fusion across the retrieval sources, then authority-first ordering.

        RRF replaces a direct comparison of ES relevance against Qdrant cosine similarity:
        those are different scales (BM25 is unbounded, cosine is 0–1), so comparing them
        numerically ranked by whichever source happened to emit bigger numbers. RRF uses
        each source's *rank*, which is scale-free, and rewards documents that more than one
        source agrees on.

        Authority stays the primary sort key — a regulatory source outranking a field
        observation is a deliberate safety property, not a relevance artefact. RRF decides
        order *within* an authority level, which is where the scale bug actually did damage.
        """
        fused: dict[str, float] = {}
        best: dict[str, SearchResult] = {}

        for results in ranked_lists:
            for rank, r in enumerate(results, start=1):
                if not r.document_id:
                    continue
                fused[r.document_id] = fused.get(r.document_id, 0.0) + 1.0 / (_RRF_K + rank)
                best[r.document_id] = self._better(best.get(r.document_id), r)

        # Within an authority level, the queried asset's own documents come before documents that
        # are only graph-linked to it (filed under another asset, or none). Without this a linked
        # shift log could push the asset's own closeout form out of `limit` (benchmark Q36).
        ranked = sorted(
            best.values(),
            key=lambda x: (
                x.authority_level,
                bool(asset_id) and x.asset_id != asset_id,
                -fused.get(x.document_id, 0.0),
            ),
        )
        for r in ranked:
            r.relevance_score = round(fused.get(r.document_id, 0.0), 6)
        return ranked[:limit]

    @staticmethod
    def _better(existing: SearchResult | None, candidate: SearchResult) -> SearchResult:
        """
        Picks the representative record for a document seen by several sources.

        Lowest authority_level wins (most authoritative). Text is merged rather than
        dropped: collapsing duplicates by document_id used to discard the losing record's
        snippet, so a semantic chunk containing the answer could be replaced by an ES hit
        with a shorter excerpt — and synthesis then never saw the fact.
        """
        if existing is None:
            return candidate

        winner, loser = (
            (candidate, existing) if candidate.authority_level < existing.authority_level else (existing, candidate)
        )
        # Keep the longest available snippet and any title/vault_url either side resolved.
        if len(loser.snippet or "") > len(winner.snippet or ""):
            winner.snippet = loser.snippet
        winner.title = winner.title or loser.title
        winner.vault_url = winner.vault_url or loser.vault_url
        # Surfaced by more than one method — record it rather than hiding one.
        if loser.retrieval_method not in winner.retrieval_method:
            winner.retrieval_method = f"{winner.retrieval_method}+{loser.retrieval_method}"
        winner.is_quarantine = winner.is_quarantine and loser.is_quarantine
        return winner

    def _normalize_es(self, hits: list[dict]) -> list[SearchResult]:
        return [
            SearchResult(
                document_id=h.get("document_id") or "",
                asset_id=h.get("asset_id"),
                document_type=h.get("document_type", "unknown"),
                title=h.get("title") or "",
                snippet=h.get("snippet") or "",
                authority_level=h.get("authority_level", 5),
                # Real indexed status, not a hardcoded "active" — a superseded document reached
                # via time-travel must say so rather than presenting itself as current.
                status=h.get("status") or "active",
                relevance_score=float(h.get("score") or 0),
                retrieval_method="exact",
                is_quarantine=False,
            )
            for h in hits
        ]

    def _normalize_qdrant(self, hits: list[dict], is_quarantine: bool) -> list[SearchResult]:
        return [
            SearchResult(
                document_id=p.get("document_id") or "",
                asset_id=p.get("asset_id"),
                document_type=p.get("document_type", "unknown"),
                title="",
                snippet=(p.get("text") or "")[:1800],  # full semantic chunk so synthesis sees facts not near the query terms
                authority_level=p.get("authority_level", 5),
                status=p.get("status") or "active",
                relevance_score=float(h.get("score") or 0),
                retrieval_method="semantic",
                is_quarantine=is_quarantine,
            )
            for h in hits
            for p in [h.get("payload", {})]
        ]

    @staticmethod
    def _rankable_graph_hits(graph_raw: list[dict], es_raw: list[dict], qdrant_raw: list[dict]) -> list[dict]:
        """Graph hits that may compete for a result slot.

        A provenance edge (`GraphService.NON_ASSERTING_RELATIONSHIPS`: "EQ-101 documented by X") states
        no fact, so on its own it renders a content-free stub that ranks by the *edge's* authority. Once
        extraction linked every document an asset is mentioned in, a level-1 regulation stub and level-4
        PTW/checklist stubs filled the top of an EQ-101 search and pushed the asset's own closeout form —
        the document holding the answer — out of the limit (benchmark Q14, Q15, 2026-09-13). Such an
        edge still widens the text-search scope (`linked_ids`) and still boosts a document that text
        search also found; it just never takes a slot by itself.
        """
        text_ids = {h.get("document_id") for h in es_raw} | {(h.get("payload") or {}).get("document_id") for h in qdrant_raw}
        return [
            h for h in graph_raw
            if (h.get("edge") or {}).get("relationship_type") not in GraphService.NON_ASSERTING_RELATIONSHIPS
            or (h.get("edge") or {}).get("document_id") in text_ids
        ]

    def _normalize_graph(self, hits: list[dict], asset_id: str | None) -> list[SearchResult]:
        return [
            SearchResult(
                document_id=edge.get("document_id") or "",
                asset_id=asset_id,
                document_type=target.get("document_type", "unknown"),
                # A graph-only hit's target node often carries no `title` property (assets,
                # concepts, and some Document nodes never got one set). "" used to flow straight
                # through every caller's `title ?? fallback` — `??` only catches null/undefined,
                # not empty string — leaving copilot source cards with a blank line where the
                # title belongs. document_id is always present and is what every other retrieval
                # method already falls back to.
                title=target.get("title") or edge.get("document_id") or "",
                # A graph hit used to carry snippet="" — it entered the ranking but gave
                # synthesis nothing to read, so a fact that existed only as an edge was
                # invisible to the answer. Render the relationship as text instead.
                snippet=self._edge_snippet(edge, target, asset_id),
                authority_level=edge.get("authority_level", 5),
                status="active",
                relevance_score=float(edge.get("confidence") or 0.5),
                retrieval_method="graph",
                is_quarantine=edge.get("verification_status") != "verified",
            )
            for h in hits
            for edge in [h.get("edge", {})]
            for target in [h.get("target", {})]
        ]

    @staticmethod
    def _edge_snippet(edge: dict[str, Any], target: dict[str, Any], asset_id: str | None) -> str:
        """Renders a knowledge edge as a readable fact line for the synthesis context."""
        relationship = str(edge.get("relationship_type") or "related to").replace("_", " ").lower()
        label = (
            target.get("title")
            or target.get("label")
            or target.get("tag_number")
            or target.get("document_id")
            or target.get("concept_id")
            or "unnamed entity"
        )
        parts = [f"{asset_id or 'Asset'} {relationship} {label}."]
        if edge.get("valid_from"):
            parts.append(f"Valid from {edge['valid_from']}.")
        if edge.get("verification_status"):
            parts.append(f"Verification: {edge['verification_status']}.")
        if edge.get("confidence") is not None:
            parts.append(f"Confidence {edge['confidence']}.")
        return " ".join(parts)
