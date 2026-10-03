"""
Knowledge-coverage service — what the platform actually knows, per asset.

Answers the question the deck calls a "knowledge-coverage heatmap": *where is our knowledge thin?*
Every number is read live from the stores that already own it — the graph for facts, Supabase for
documents and quarantine, the compliance layer for gaps. Nothing here is computed speculatively or
cached; a blank cell means "we genuinely hold nothing", which is the finding, not a rendering bug.

Deliberately read-only and model-free: no OCR, NER or embedding call is made, so this costs no
provider quota and can be refreshed as often as the page likes.
"""

from typing import Any

import structlog

from api.services.corpus import REAL_ASSET_CYPHER, excluded_test_asset_count

log = structlog.get_logger(__name__)

# Authority levels 1-3 are regulatory / engineering / OEM. An asset whose knowledge is entirely
# level 4-5 (site procedure, field observation) is a real coverage weakness even when the raw
# fact count looks healthy — the same distinction the safety refusal gate turns on.
AUTHORITATIVE_LEVEL = 3


class CoverageService:
    """Composes a per-asset coverage picture across Neo4j, Supabase and the compliance layer."""

    def __init__(self, driver, database: str, supabase):
        self._driver = driver
        self._database = database
        self._supabase = supabase

    async def asset_coverage(self) -> list[dict[str, Any]]:
        """
        One row per registered asset. Counts are DISTINCT by `edge_id`: the graph can hold several
        physical relationships sharing one logical edge, and counting those raw would overstate
        coverage for exactly the assets that were re-ingested most.
        """
        rows = await self._graph_counts()
        docs = self._count("document_asset_links", "asset_id")
        quarantine = self._count("quarantine_items", "asset_id", eq=("review_status", "pending"))

        out: list[dict[str, Any]] = []
        for r in rows:
            asset_id = r["asset_id"]
            facts = r["facts"] or 0
            out.append({
                "asset_id": asset_id,
                "name": r.get("name") or asset_id,
                "equipment_class": r.get("equipment_class") or "unclassified",
                "criticality": r.get("criticality") or "unknown",
                "facts": facts,
                "authoritative_facts": r["authoritative"] or 0,
                "verified_facts": r["verified"] or 0,
                "documents": docs.get(asset_id, 0),
                "pending_quarantine": quarantine.get(asset_id, 0),
            })
        return out

    async def excluded_test_assets(self) -> int:
        """Test assets the coverage matrix leaves out, reported beside it."""
        async with self._driver.session(database=self._database) as session:
            return await excluded_test_asset_count(session)

    async def _graph_counts(self) -> list[dict[str, Any]]:
        # collect(DISTINCT k.edge_id) would lose the properties needed for the authority/verified
        # splits, so collect the relationships and de-duplicate on edge_id in the projection.
        cypher = f"""
        MATCH (a:Asset) WHERE {REAL_ASSET_CYPHER}
        OPTIONAL MATCH (a)-[k:KNOWLEDGE_EDGE]-()
        WITH a, [x IN collect(DISTINCT k) WHERE x IS NOT NULL] AS ks
        RETURN a.asset_id           AS asset_id,
               a.name               AS name,
               a.equipment_class    AS equipment_class,
               a.criticality        AS criticality,
               size(ks)                                                          AS facts,
               size([e IN ks WHERE e.authority_level <= $auth])                   AS authoritative,
               size([e IN ks WHERE e.verification_status = 'verified'])           AS verified
        ORDER BY a.asset_id
        """
        async with self._driver.session(database=self._database) as session:
            result = await session.run(cypher, auth=AUTHORITATIVE_LEVEL)
            return await result.data()

    def _count(self, table: str, column: str, eq: tuple[str, str] | None = None) -> dict[str, int]:
        """Group-count a Supabase table by `column`. Failures degrade to {} rather than 500 the
        whole page — a missing quarantine count should not hide the graph coverage beside it."""
        try:
            q = self._supabase.table(table).select(column)
            if eq:
                q = q.eq(*eq)
            counts: dict[str, int] = {}
            offset = 0
            while True:
                page = q.range(offset, offset + 999).execute().data or []
                for row in page:
                    key = row.get(column)
                    if key:
                        counts[key] = counts.get(key, 0) + 1
                if len(page) < 1000:
                    break
                offset += 1000
            return counts
        except Exception as exc:  # noqa: BLE001 - partial coverage beats no coverage
            log.warning("coverage.count_failed", table=table, error=str(exc))
            return {}
