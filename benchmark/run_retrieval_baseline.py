"""STAGED — copy to benchmark/run_retrieval_baseline.py after SOAK_DONE.

Retrieval baseline comparison — replaces the word "modelled".

The results table currently reports "9.5% modelled reduction in time-to-answer". `modelled` is the
weakest word in it, and it is attached to the core value claim. This measures the thing directly:
the same 37 golden questions run through each retrieval method alone, then through the hybrid
fusion, scored on whether the expected fact actually reaches the context.

    exact-only    Elasticsearch BM25
    semantic-only Qdrant vector
    hybrid        RRF fusion + authority ordering (what ships)

WHY THIS IS CHEAP. Retrieval only — no synthesis. It costs one Jina embedding per question per
vector-using arm, and nothing else. It does NOT consume LLM quota, so unlike the safety eval it is
safe to re-run.

WHAT IT CANNOT TELL YOU. Retrieval hit-rate is not answer quality: a fact reaching the context is
necessary, not sufficient. Report it as retrieval reach, and do not restate it as accuracy.

    docker exec kairos-backend-api python benchmark/run_retrieval_baseline.py
"""

import asyncio
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).parent))

QUESTIONS = Path(__file__).parent / "questions.json"


def _wilson(hits: int, n: int) -> tuple[float, float]:
    """95% Wilson score interval — same treatment the other benchmarks report."""
    if n == 0:
        return (0.0, 0.0)
    z = 1.96
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def _expected_terms(q: dict) -> list[str]:
    return q.get("must_all") or q.get("answer_any") or q.get("expect_any") or []


def _reached(blob: str, q: dict) -> bool:
    """Did the expected fact reach the retrieved context at all?"""
    low = blob.lower()
    terms = _expected_terms(q)
    if not terms:
        return False
    # must_all questions need every token present somewhere in the retrieved context.
    if q.get("must_all"):
        return all(t.lower() in low for t in terms)
    return any(t.lower() in low for t in terms)


async def _arm(name: str, questions: list[dict], settings) -> dict:
    """Run one retrieval configuration over every question."""
    from elasticsearch import AsyncElasticsearch
    from neo4j import AsyncGraphDatabase
    from qdrant_client import AsyncQdrantClient

    from api.services.graph import GraphService
    from api.services.llm import LLMService
    from api.services.search_engine import SearchEngineService
    from api.services.search_service import SearchService
    from api.services.vector_store import VectorStoreService

    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD))
    qdrant = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)

    llm = LLMService(settings)
    engine = SearchEngineService(es, settings)
    vector = VectorStoreService(qdrant, settings)
    svc = SearchService(GraphService(driver, settings.NEO4J_DATABASE), vector, engine, llm)

    hits = 0
    try:
        for q in questions:
            blob = ""
            try:
                if name == "exact-only":
                    rows = await engine.search(q["question"], asset_id=q.get("asset_id"), limit=6)
                    blob = " ".join((r.get("snippet") or "") + " " + (r.get("title") or "") for r in rows)
                elif name == "semantic-only":
                    vec = await llm.embed(q["question"], task="retrieval.query")
                    rows = await vector.search(
                        settings.QDRANT_COLLECTION_DOCUMENTS, vec, limit=6, asset_id=q.get("asset_id")
                    )
                    blob = " ".join((r.get("payload", {}) or {}).get("text", "") for r in rows)
                else:  # hybrid — what ships
                    rows = await svc.hybrid_search(
                        query=q["question"],
                        collection=settings.QDRANT_COLLECTION_DOCUMENTS,
                        asset_id=q.get("asset_id"),
                        authority_min=5,
                        include_quarantine=False,
                        as_of=None,
                        limit=6,
                    )
                    blob = " ".join((r.snippet or "") + " " + (r.title or "") for r in rows)
            except Exception as exc:
                print(f"    {q['id']} {name}: {type(exc).__name__}: {exc}", file=sys.stderr)
            if _reached(blob, q):
                hits += 1
    finally:
        await driver.close()
        await es.close()

    lo, hi = _wilson(hits, len(questions))
    return {"arm": name, "hits": hits, "n": len(questions), "rate": hits / len(questions), "ci": [lo, hi]}


async def main() -> int:
    from api.config import Settings

    settings = Settings()
    data = json.loads(QUESTIONS.read_text())
    questions = data if isinstance(data, list) else data.get("questions", data)

    arms = []
    for name in ("exact-only", "semantic-only", "hybrid"):
        print(f"  running {name} …")
        arms.append(await _arm(name, questions, settings))

    print(f"\n  Kairos — Retrieval Baseline   n={len(questions)} golden questions")
    print(f"\n  {'arm':<16}{'reach':>8}{'  95% CI':>18}")
    print("  " + "-" * 44)
    for a in arms:
        ci = f"[{a['ci'][0]*100:.0f}–{a['ci'][1]*100:.0f}%]"
        print(f"  {a['arm']:<16}{a['hits']}/{a['n']} {a['rate']*100:>5.1f}%{ci:>16}")

    hybrid = next(a for a in arms if a["arm"] == "hybrid")
    best_single = max((a for a in arms if a["arm"] != "hybrid"), key=lambda a: a["rate"])
    delta = (hybrid["rate"] - best_single["rate"]) * 100
    print(f"\n  Hybrid vs best single method ({best_single['arm']}): {delta:+.1f} pts")
    if hybrid["ci"][0] <= best_single["ci"][1]:
        print("  NOTE: the confidence intervals overlap — at n=37 this difference is suggestive,")
        print("  not established. Report it as such, or grow the question set.")

    out = Path("/app/.benchmark_runs/retrieval_baseline.json")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"arms": arms, "delta_pts": delta}, indent=2))
        print(f"\n  Written to {out}")
    except Exception as exc:
        print(f"  (could not write {out}: {exc})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
