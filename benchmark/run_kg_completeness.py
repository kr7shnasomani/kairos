"""
KG linkage completeness — the PS evaluation criterion, with a definition it can be held to.

THE DEFINITION
  **Linkage completeness is the fraction of active vault documents whose knowledge is reachable
  in the graph** — a document counts as linked when at least one `KNOWLEDGE_EDGE` carries its
  `document_id`. The unlinked remainder is *classified*, never left as a bare percentage.

WHY NOT THE OBVIOUS ONE
  `run_benchmark.py` already prints "assets linked / total assets", which reads 100% as soon as
  every asset has one edge. That is reachability, not completeness: it is satisfied by a graph
  holding a single fact per asset while the rest of the corpus never landed. It answers "can I
  traverse to an asset", where the criterion asks "did the knowledge get in".

  Document-centric is the harder and more honest cut, because the denominator is the corpus you
  actually ingested rather than the entities you happened to create.

WHAT IS DELIBERATELY NOT A FAILURE
  A document whose knowledge sits in **quarantine** is not an incompleteness. Layer 6 exists to
  hold knowledge that cannot be linked with confidence, and the one-way gate is the designed
  outcome for it — scoring it as a miss would penalise the system for behaving correctly. It is
  reported on its own line.

  Likewise a `PROMOTED-<uuid>` document id on an edge is not dangling provenance: promotion from
  quarantine mints that id for field knowledge that never had a vault document
  (`routers/governance.py`). Counted separately rather than as an integrity error.

THE REVERSE DIRECTION MATTERS MORE
  An edge citing a `document_id` with no vault row is **dangling provenance** — the graph asserts
  a fact and points at evidence that cannot be produced. That is worse than a missing link: an
  operator following the citation finds nothing, and the architecture's whole claim is that no
  answer exists without retrievable provenance. Reported separately, and it is the number to fix
  first if it is ever non-zero.

USAGE
  docker compose run --rm --no-deps kairos-backend-api python benchmark/run_kg_completeness.py

Exits non-zero only on dangling provenance — completeness itself is a measurement, not a gate,
because the honest value depends on how much of the corpus has been through extraction.
"""

import asyncio
import sys

from neo4j import AsyncGraphDatabase
from supabase import create_client

from api.config import Settings
from api.services import tenant
from api.services.corpus import is_test_artifact

# Minted by `POST /governance/quarantine/{id}/promote` for field knowledge with no vault document.
_PROMOTED_PREFIX = "PROMOTED-"

# Documents written by the test suite and by hand during sweeps. They carry ordinary random
# `DOC-` ids, so only the FILE NAME identifies them.
#
# They must leave the denominator or this measures test hygiene rather than linkage: 69 of 108
# "active" documents were test artifacts on 2026-08-23, dragging the reported figure to 64% when
# the real corpus was 33/39 = 84%. Same class of error as scoring the model gate against ground
# truth outside its taxonomy — the metric was answering a question nobody asked.
#
# Excluded, never silently: the count is reported so the denominator is always auditable.
#
# The predicate itself now lives in `api/services/corpus.py` — this harness proved the problem,
# but `GET /assets/{id}/knowledge` needs the same rule and two copies of a filter like this
# drift. `benchmark/` already imports from `api/`, so the shared home is there.


async def measure() -> dict:
    settings = Settings()
    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    all_rows = sb.table("documents").select("document_id, status, document_type, file_name, access_tags").execute().data or []
    # Showcase documents (services/tenant.py) are a separate plant; the real linkage is measured without them,
    # and so is their half of the graph: an edge citing one resolves to a showcase record, not a dangling id.
    showcase_docs = {r["document_id"] for r in all_rows if tenant.is_demo_document(r)}
    rows = [r for r in all_rows if r["document_id"] not in showcase_docs]
    # Superseded documents are excluded by design: Layer 2 keeps them forever, and retrieval
    # already filters them out, so requiring them to stay linked would measure the vault's memory
    # rather than the graph's coverage.
    all_active = {r["document_id"]: r for r in rows if r.get("status") == "active"}
    test_docs = {k: v for k, v in all_active.items() if is_test_artifact(v.get("file_name"))}
    active = {k: v for k, v in all_active.items() if k not in test_docs}

    quarantined_docs: set[str] = set()
    q = sb.table("quarantine_items").select("session_context").execute().data or []
    for item in q:
        ctx = item.get("session_context") or {}
        doc = ctx.get("document_id")
        if doc:
            quarantined_docs.add(doc)

    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
    )
    try:
        async with driver.session(database=settings.NEO4J_DATABASE) as sess:
            result = await sess.run(
                "MATCH (s)-[k:KNOWLEDGE_EDGE]->() WHERE k.document_id IS NOT NULL "
                "RETURN k.document_id AS doc, labels(s) AS source_labels"
            )
            edge_docs: set[str] = set()
            # Which node labels cite each document. Reachability is the difference between a
            # citation an operator can hit and one they cannot: the Layer 4 read path matches
            # `(a:Asset)-[:KNOWLEDGE_EDGE]->()`, so a dangling id cited only from a non-Asset
            # label never reaches an answer. Still a defect, but a contained one — and reporting
            # the labels is what lets a reader tell the two apart instead of guessing.
            doc_sources: dict[str, set[str]] = {}
            async for r in result:
                edge_docs.add(r["doc"])
                doc_sources.setdefault(r["doc"], set()).update(r["source_labels"] or [])
    finally:
        await driver.close()
    edge_docs -= showcase_docs

    linked = {d for d in active if d in edge_docs}
    unlinked = set(active) - linked
    unlinked_quarantined = unlinked & quarantined_docs
    unlinked_unexplained = unlinked - unlinked_quarantined

    promoted = {d for d in edge_docs if d.startswith(_PROMOTED_PREFIX)}
    dangling = {d for d in edge_docs if d not in active and d not in promoted and d not in set(
        r["document_id"] for r in rows)}

    by_type: dict[str, list[int]] = {}
    for doc_id, row in active.items():
        t = row.get("document_type") or "unknown"
        bucket = by_type.setdefault(t, [0, 0])
        bucket[1] += 1
        if doc_id in linked:
            bucket[0] += 1

    return {
        "active": len(active),
        "excluded_test_docs": len(test_docs),
        "linked": len(linked),
        "unlinked_quarantined": len(unlinked_quarantined),
        "unlinked_unexplained": len(unlinked_unexplained),
        "promoted_edges": len(promoted),
        "dangling": sorted(dangling),
        "dangling_sources": {d: sorted(doc_sources.get(d, set())) for d in sorted(dangling)},
        # Dangling ids cited from an Asset are reachable by the Layer 4 read path and can surface
        # in an answer; ones cited only from other labels cannot. Both are defects, only one is
        # operator-visible.
        "dangling_reachable": sorted(
            d for d in dangling if "Asset" in doc_sources.get(d, set())
        ),
        "by_type": by_type,
    }


def summary_line(m: dict) -> str:
    """One-line form, so `run_benchmark.py` can print the same number this runner computes."""
    pct = (100 * m["linked"] // m["active"]) if m["active"] else 0
    return (f"{m['linked']}/{m['active']} active documents linked ({pct}%) · "
            f"{m['unlinked_quarantined']} quarantined by design · "
            f"{m['unlinked_unexplained']} unexplained · {len(m['dangling'])} dangling")


async def main() -> int:
    m = await measure()
    pct = (100 * m["linked"] // m["active"]) if m["active"] else 0

    print("\nKG LINKAGE COMPLETENESS")
    print("  definition: active vault documents with >=1 KNOWLEDGE_EDGE carrying their document_id\n")
    print(f"  linked                 {m['linked']}/{m['active']}  ({pct}%)")
    print(f"  excluded — test docs   {m['excluded_test_docs']:>4}   (ann_test_*/scratch: they measure test hygiene, not linkage)")
    print(f"  unlinked — quarantined {m['unlinked_quarantined']:>4}   (Layer 6 working as designed, not a miss)")
    print(f"  unlinked — unexplained {m['unlinked_unexplained']:>4}   <- the real gap")
    print(f"  promoted-only edges    {m['promoted_edges']:>4}   (field knowledge, no vault document by design)")
    print(f"  dangling provenance    {len(m['dangling']):>4}   <- edges citing evidence that cannot be produced")

    print("\n  by document type (linked/active):")
    for t, (lk, tot) in sorted(m["by_type"].items(), key=lambda kv: -kv[1][1]):
        share = (100 * lk // tot) if tot else 0
        print(f"    {t:24} {lk:>3}/{tot:<3} {share:>3}%")

    if m["dangling"]:
        print("\n  DANGLING PROVENANCE — edges cite a document_id with no vault record:")
        for d in m["dangling"][:20]:
            labels = ", ".join(m["dangling_sources"].get(d, [])) or "?"
            reach = "REACHABLE from an Asset" if d in m["dangling_reachable"] else "not on the Asset read path"
            print(f"    {d}  cited by [{labels}] — {reach}")
        if m["dangling_reachable"]:
            print("\n  FAIL: a dangling id is cited from an Asset, so an answer can surface a "
                  "citation whose evidence cannot be produced.")
            return 1
        print("\n  Contained: no dangling id is cited from an Asset, so none can reach an answer "
              "through the Layer 4 read path. Still worth cleaning up, but not operator-visible.")
        return 0

    print("\n  no dangling provenance — every cited document_id resolves to a vault record or a "
          "promoted field item")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
