"""
Cross-functional knowledge discovery — the PS evaluation criterion, measured as a counterfactual.

THE CRITERION
  The problem statement asks for "demonstrated improvement in cross-functional knowledge
  discovery". In a plant, "cross-functional" means the silos knowledge actually sits in:
  operations writes shift logs, reliability writes inspection reports, engineering owns
  procedures and drawings, the vendor issues bulletins, safety issues permits, compliance holds
  the regulations. The problem is that a question asked inside one function is answered from that
  function's documents, because those are the ones its people know exist.

WHY THIS IS NOT A PROXY
  "Distinct document types per answer" is the obvious metric and it measures nothing: an answer
  can cite five document types and still be one a maintenance engineer would have found unaided.
  The criterion says *improvement*, and an improvement needs a counterfactual — what the asker
  would have found **without** the cross-silo view.

  So this runs two arms over the golden questions in benchmark/questions.json (37 when this was
  last measured; 46 since 2026-09-13):

    full   retrieval over the whole corpus (what ships)
    silo   retrieval restricted to ONE function's documents, once per function

  A question that the full arm reaches and **no single silo** reaches is a discovery that only
  exists because the silos were crossed. That is the number the criterion is asking for.

WHAT IT COSTS
  One embedding per question. **No LLM quota** — this is retrieval reach, not synthesis, so it is
  safe to re-run (same posture as `run_retrieval_baseline.py`).

THREE LIMITS, STATED RATHER THAN BURIED
  1. The function mapping below is a **declared judgment**, not data. `document_type` is the only
     signal the corpus carries about which discipline owns a document. Disagree with a row and
     the numbers move — that is why it is a visible constant and not buried in a query.
  2. The silo arm **simulates** a siloed search. It ranks the whole corpus once and then takes
     each function's best hits from that ranking, rather than rebuilding a per-silo index. It is
     an approximation of what a function-local search would surface, not an observation of what
     a human in that function actually does.
  3. n=37 (last run) on a 24-document corpus. Report the count, not a headline percentage.

    docker compose run --rm --no-deps kairos-backend-api python benchmark/run_cross_functional.py
"""

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "/app")

# document_type -> the plant function that owns it. A declared judgment; see limit 1 above.
FUNCTION_OF: dict[str, str] = {
    "shift_log": "operations",
    "inspection_report": "reliability",
    "procedure": "engineering",
    "pid_drawing": "engineering",
    "oem_manual": "vendor",
    "ptw": "safety",
    "regulation": "compliance",
}

# How deep the shared ranking goes before each silo takes its slice. Deep enough that a small
# function is not starved by a larger one dominating the head of the list.
_POOL = 50
# What a single function's own search would realistically put in front of someone.
_SILO_LIMIT = 6


def _expected_terms(q: dict) -> list[str]:
    return q.get("must_all") or q.get("answer_any") or q.get("expect_any") or []


def _reached(blob: str, q: dict) -> bool:
    """Did the expected fact reach this context at all? Same rule as run_retrieval_baseline."""
    low = blob.lower()
    terms = _expected_terms(q)
    if not terms:
        return False
    if q.get("must_all"):
        return all(t.lower() in low for t in terms)
    return any(t.lower() in low for t in terms)


async def main() -> int:
    from neo4j import AsyncGraphDatabase
    from supabase import create_client

    from api.config import Settings
    from api.services.graph import GraphService
    from api.services.llm import LLMService
    from api.services.search_engine import SearchEngineService
    from api.services.search_service import SearchService
    from api.services.vector_store import VectorStoreService

    settings = Settings()
    raw = json.loads(Path("/app/benchmark/questions.json").read_text())
    questions = raw if isinstance(raw, list) else raw.get("questions", [])
    questions = [q for q in questions if _expected_terms(q)]

    sb = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    docs = sb.table("documents").select("document_id, document_type, status").execute().data or []
    fn_of_doc = {
        d["document_id"]: FUNCTION_OF.get(d.get("document_type") or "", "unmapped")
        for d in docs if d.get("status") == "active"
    }
    functions = sorted({f for f in fn_of_doc.values() if f != "unmapped"})

    from elasticsearch import AsyncElasticsearch
    from qdrant_client import AsyncQdrantClient

    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)
    )
    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)
    qdrant = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    svc = SearchService(
        GraphService(driver, settings.NEO4J_DATABASE),
        VectorStoreService(qdrant, settings),
        SearchEngineService(es, settings),
        LLMService(settings),
    )

    full_hits = 0
    silo_only_full: list[str] = []          # full arm reached, no single silo did
    silo_reach_counts: list[int] = []       # how many silos could reach it alone
    per_function_hits: Counter = Counter()

    try:
        for q in questions:
            try:
                rows = await svc.hybrid_search(
                    query=q["question"],
                    collection=settings.QDRANT_COLLECTION_DOCUMENTS,
                    asset_id=q.get("asset_id"),
                    authority_min=5,
                    include_quarantine=False,
                    as_of=None,
                    limit=_POOL,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  {q['id']}: retrieval failed — {type(exc).__name__}: {exc}", file=sys.stderr)
                continue

            def blob_of(rs) -> str:
                return " ".join((r.snippet or "") + " " + (r.title or "") for r in rs)

            full_reached = _reached(blob_of(rows[:_SILO_LIMIT]), q)
            if full_reached:
                full_hits += 1

            reached_in = []
            for fn in functions:
                slice_ = [r for r in rows if fn_of_doc.get(r.document_id) == fn][:_SILO_LIMIT]
                if slice_ and _reached(blob_of(slice_), q):
                    reached_in.append(fn)
                    per_function_hits[fn] += 1

            silo_reach_counts.append(len(reached_in))
            if full_reached and not reached_in:
                silo_only_full.append(q["id"])
    finally:
        await driver.close()
        await es.close()

    n = len(questions)
    print("\nCROSS-FUNCTIONAL KNOWLEDGE DISCOVERY")
    print("  counterfactual: whole-corpus retrieval vs one function's documents alone\n")
    print(f"  questions                      {n}")
    print(f"  reached by full retrieval      {full_hits}/{n}")
    print(f"  reachable in NO single silo    {len(silo_only_full)}  <- discoveries that required crossing functions")
    if silo_only_full:
        print(f"    {', '.join(silo_only_full)}")

    if silo_reach_counts:
        dist = Counter(silo_reach_counts)
        print("\n  how many single functions could have found it alone:")
        for k in sorted(dist):
            label = "none" if k == 0 else f"{k} function(s)"
            print(f"    {label:16} {dist[k]:>3} question(s)")

    print("\n  per-function reach (questions this function's documents alone could answer):")
    for fn in functions:
        print(f"    {fn:14} {per_function_hits.get(fn, 0):>3}/{n}")

    print("\n  Limits: the function mapping is a declared judgment over `document_type`; the silo")
    print("  arm simulates a function-local search by slicing one shared ranking rather than")
    print(f"  rebuilding per-silo indexes; n={n} on a ~24-document corpus. Quote the counts, not a rate.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
