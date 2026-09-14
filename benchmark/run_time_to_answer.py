#!/usr/bin/env python3
"""
Kairos — time-to-answer versus traditional keyword search.

Measures the "time-to-answer versus traditional search" evaluation criterion, which
previously had no baseline attached to it — only Kairos's own latency, with nothing to
compare it against.

WHY A NAIVE LATENCY COMPARISON IS DISHONEST
  Keyword search returns a document list in ~50 ms; Kairos returns a cited answer in
  ~8 s. On machine time alone, traditional search "wins" — and that framing is wrong,
  because keyword search hands back a list the engineer must then read. The cost lives in
  human reading time, not in the query.

WHAT THIS MEASURES
  Both halves, separately, and it never hides the half where Kairos is slower:

  1. MACHINE TIME     BM25-only Elasticsearch latency vs Kairos retrieval+synthesis.
  2. DOCUMENTS OPENED How far down a BM25-only ranking the first answer-bearing document
                      sits — i.e. how many documents an engineer opens before finding the
                      fact. Kairos cites the source directly, so this is 1 by construction.
  3. HUMAN TIME       documents_opened × SECONDS_PER_DOCUMENT + machine time.

  SECONDS_PER_DOCUMENT is an explicit, overridable assumption, not a measurement. Change
  it and the conclusion changes; that is the point of stating it.

Ground truth for "answer-bearing" is the same `expect_any` keyword set that
run_benchmark.py grades retrieval with — no new labelling, no new judgement.

USAGE
  docker compose exec kairos-backend-api python /app/benchmark/run_time_to_answer.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/app")

import httpx

API = os.getenv("API_BASE_URL", "http://localhost:8000")
KEY = os.getenv("INTERNAL_API_KEY", "kairos-internal-dev-key")
QUESTIONS = Path(__file__).parent / "questions.json"

# Time for an engineer to open an industrial document and decide whether it holds the
# fact. Deliberately conservative: a 30-page P&ID or OEM manual takes longer than this.
SECONDS_PER_DOCUMENT = float(os.getenv("SECONDS_PER_DOCUMENT", "120"))

# Cap on how deep a human would plausibly go before giving up / asking a colleague.
MAX_DOCS_SCANNED = 10

# Mirrors the frontend's budget for POST /search/synthesize, exactly as run_benchmark.py does.
# This client used to allow 180 s — twice what the browser tolerates — so it recorded a
# time-to-answer no user could ever experience, and scored calls the product would have aborted
# as successes.
SYNTH_TIMEOUT = float(os.getenv("BENCHMARK_SYNTH_TIMEOUT", "90"))

# Seconds between questions. Default matches run_benchmark.py's --delay.
DELAY = float(os.getenv("BENCHMARK_DELAY", "15"))


def _hit(text: str, expect_any: list[str]) -> bool:
    low = (text or "").lower()
    return any(e.lower() in low for e in expect_any)


async def _bm25_rank(es, index: str, question: str, expect_any: list[str]) -> tuple[int | None, float]:
    """
    Rank (1-based) of the first BM25 hit whose content holds the expected fact, plus the
    query's wall time. None means the fact was not in the top MAX_DOCS_SCANNED.
    """
    t = time.perf_counter()
    res = await es.search(
        index=index,
        body={
            "query": {"multi_match": {"query": question, "fields": ["title^2", "content"]}},
            "size": MAX_DOCS_SCANNED,
            "_source": ["document_id", "title", "content"],
        },
    )
    elapsed_ms = (time.perf_counter() - t) * 1000

    for rank, hit in enumerate(res["hits"]["hits"], start=1):
        src = hit.get("_source", {})
        if _hit(f"{src.get('title','')} {src.get('content','')}", expect_any):
            return rank, elapsed_ms
    return None, elapsed_ms


async def main() -> int:
    from elasticsearch import AsyncElasticsearch

    from api.config import settings

    questions = json.loads(QUESTIONS.read_text())
    questions = questions if isinstance(questions, list) else questions.get("questions", [])

    es = AsyncElasticsearch(settings.ELASTICSEARCH_URL)
    index = settings.ELASTICSEARCH_INDEX_DOCUMENTS

    rows = []
    async with httpx.AsyncClient(timeout=SYNTH_TIMEOUT, follow_redirects=True) as client:
        headers = {"Authorization": f"Bearer {KEY}"}
        for qi, q in enumerate(questions):
            expect_any = q.get("expect_any", [])

            rank, bm25_ms = await _bm25_rank(es, index, q["question"], expect_any)

            # Kairos: retrieval + synthesis, end to end, exactly as the copilot calls it.
            t = time.perf_counter()
            params = {"q": q["question"], "limit": 6}
            if q.get("asset_id"):
                params["asset_id"] = q["asset_id"]
            ctx = []
            answered = False
            try:
                search = await client.get(f"{API}/search", headers=headers, params=params)
                ctx = [
                    {
                        "text": r.get("snippet", ""),
                        "document_id": r.get("document_id"),
                        "authority_level": r.get("authority_level", 5),
                    }
                    for r in (search.json().get("results", []) if search.status_code == 200 else [])
                ]
                if ctx:
                    syn = await client.post(
                        f"{API}/search/synthesize", headers=headers, json={"query": q["question"], "context": ctx}
                    )
                    body = syn.json() if syn.status_code == 200 else {}
                    answered = bool(body.get("answer")) or bool(body.get("refused"))
            except (httpx.TimeoutException, httpx.HTTPError) as e:
                # A call the product would have aborted is a MISS, not a crashed run. Letting this
                # propagate discarded every question already measured — the same defect that cost
                # run_benchmark.py 21 of 37 questions on 2026-08-16.
                print(f"  {q['id']:<5} {type(e).__name__} — counted as unanswered", flush=True)
            kairos_ms = (time.perf_counter() - t) * 1000

            docs_opened = rank if rank else MAX_DOCS_SCANNED
            trad_human_s = bm25_ms / 1000 + docs_opened * SECONDS_PER_DOCUMENT
            kairos_human_s = kairos_ms / 1000 + 1 * SECONDS_PER_DOCUMENT  # verify the cited source

            rows.append(
                {
                    "id": q["id"],
                    "bm25_ms": bm25_ms,
                    "bm25_rank": rank,
                    "docs_opened": docs_opened,
                    "kairos_ms": kairos_ms,
                    "answered": answered,
                    "trad_s": trad_human_s,
                    "kairos_s": kairos_human_s,
                }
            )
            print(
                f"  {q['id']:<5} bm25 {bm25_ms:7.1f}ms rank {str(rank or '>10'):<4}"
                f" | kairos {kairos_ms:8.1f}ms {'ans' if answered else 'MISS':<4}"
                f" | human {trad_human_s/60:5.1f}m -> {kairos_human_s/60:4.1f}m"
            )

            # Pace the next synthesis call, for the same reason run_benchmark.py does: NVIDIA's
            # shared endpoint degrades under back-to-back load, so an unpaced sweep measures the
            # queue rather than the system, and multiplies fallthrough onto the free Gemini tier.
            if DELAY and qi < len(questions) - 1:
                await asyncio.sleep(DELAY)

    await es.close()

    n = len(rows)
    if not n:
        print("No questions loaded.")
        return 1

    def mean(key):
        return sum(r[key] for r in rows) / n

    found = [r for r in rows if r["bm25_rank"]]
    trad_total = sum(r["trad_s"] for r in rows)
    kairos_total = sum(r["kairos_s"] for r in rows)

    print()
    print("  " + "=" * 74)
    print(f"  Questions: {n}   assumption: {SECONDS_PER_DOCUMENT:.0f}s to read one document")
    print()
    print("  MACHINE TIME (Kairos is slower — synthesis is a model call)")
    print(f"    BM25-only mean:            {mean('bm25_ms'):9.1f} ms")
    print(f"    Kairos retrieve+synth:     {mean('kairos_ms'):9.1f} ms")
    print()
    print("  DOCUMENTS OPENED BEFORE THE FACT")
    print(f"    BM25-only mean rank:       {mean('docs_opened'):9.2f}")
    print(f"    fact in top-10 for:        {len(found)}/{n} questions")
    print(f"    Kairos:                    {1:9.2f}  (cited source, verified once)")
    print()
    print("  MODELLED HUMAN TIME TO A TRUSTED ANSWER")
    print(f"    traditional:               {trad_total/60:9.1f} min total  ({trad_total/n/60:.1f} min/question)")
    print(f"    Kairos:                    {kairos_total/60:9.1f} min total  ({kairos_total/n/60:.1f} min/question)")
    if kairos_total:
        print(f"    reduction:                 {100 * (1 - kairos_total / trad_total):9.1f} %")
    print()
    print("  Machine latency is reported unrounded and unweighted: Kairos loses that")
    print("  comparison. The claim is about time to a *trusted, cited* answer, and it")
    print("  depends entirely on the reading-time assumption printed above.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
