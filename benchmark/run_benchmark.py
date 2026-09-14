"""
Kairos — Domain-expert benchmark (PS "Evaluation Focus").

Methodology (fully deterministic — no LLM judge, so every number is reproducible):
  • Per-question routing  — each question pulls context from the right source(s):
    hybrid `/search`, the asset's graph `/knowledge`, and/or `/aliases`.
  • Retrieval precision    — keyword-in-context signal (does the fact reach the context?).
  • Answer quality         — the synthesized answer must *state* the required fact(s) and not negate
    them: `must_all` = every token (exact/multi-part facts), `answer_any` = any correct-answer token
    (comparative questions), else `expect_any`. A fact wrapped in a negator ("not 16.2") fails.
  • Provenance             — every non-refused answer must cite sources[] (Kairos: no claim w/o provenance).
  • KG linkage             — deterministic Cypher (assets linked, edges, verification).
  • Time-to-answer         — latency per question.
Entity-extraction F1 is the Layer-0 model gate: backend/scripts/run_model_validation.py.

Streams per question. Requires the golden dataset loaded (`make load-dataset`).
Run:
    docker exec kairos-backend-api python benchmark/run_benchmark.py                 # full (routing + synthesis + grading)
    docker exec kairos-backend-api python benchmark/run_benchmark.py --retrieval-only # fast, retrieval + KG only

WHY THERE IS A --delay, AND WHY IT DEFAULTS TO NON-ZERO
  The shared NVIDIA NIM endpoint has a heavy, random latency tail that worsens under
  back-to-back load. Measured on one identical 73-token synthesis payload:

      back-to-back : 30.2s · TIMEOUT(78s) · 47.4s · 14.2s
      paced 20s    :  8.6s · 10.6s · 16.2s

  No rate-limit headers are returned — the endpoint just queues. A NIM call that outlives
  NVIDIA_NIM_TIMEOUT falls through to the Gemini tier, which is a *free-tier key*; enough
  fallthrough in one run exhausts it, after which Gemini returns 429 and every subsequent
  NIM timeout becomes a no-answer. That is measured as poor answer quality, which it is not.

  So pacing is not politeness — it is what keeps the run on the model whose quality is being
  measured. Note the corollary: LOWERING NVIDIA_NIM_TIMEOUT does not speed anything up, it
  just caps the number and moves the work to Gemini, burning the free tier faster.

  The run now reports which provider answered each question and refuses to present a
  contaminated run as a clean measurement.
"""

import argparse
import asyncio
import json
import math
import os
import time
from collections import Counter, defaultdict

import httpx

API = os.getenv("VERIFY_API_URL", "http://localhost:8000")
QUESTIONS = os.getenv("BENCHMARK_FILE", "/app/benchmark/questions.json")
# Mirrors the frontend's budget for POST /search/synthesize (frontend/src/lib/api.ts) ON PURPOSE.
# It used to be 120 s, which is how a real regression slipped through: with NVIDIA_NIM_TIMEOUT at
# 90 s the Gemini fallbacks landed at 92-102 s, so the harness scored them as successes while the
# browser aborted them. A benchmark that is more patient than the product cannot see the product's
# failures. Keep these two numbers in step; a call that exceeds it is recorded as `timeout`, which
# the validity verdict then flags.
SYNTH_TIMEOUT = float(os.getenv("BENCHMARK_SYNTH_TIMEOUT", "90"))
# Retrieval is cheap relative to synthesis, but `/search` embeds via Jina and fans out to ES,
# Qdrant and Neo4j, so its tail is longer than the 30 s client default that used to apply here.
RETRIEVAL_TIMEOUT = float(os.getenv("BENCHMARK_RETRIEVAL_TIMEOUT", "60"))




def _kw_hit(blob: str, terms: list[str]) -> bool:
    """Retrieval signal: does any expected term reach the (context) blob?"""
    low = blob.lower()
    return any(t.lower() in low for t in terms)


# A required fact wrapped in one of these is NOT a correct statement of it
# ("the limit is not 16.2 bar"). ponytail: 20-char lookbehind heuristic, not a parser —
# upgrade to dependency parsing only if a real answer defeats it.
_NEGATORS = ("not ", "no ", "n't ", "never ", "isn't", "wasn't", "aren't", "rather than", "instead of", "no longer")


def _stated(answer: str, token: str) -> bool:
    """True if `token` appears in `answer` in at least one non-negated position."""
    low, tok = answer.lower(), token.lower()
    i = low.find(tok)
    while i != -1:
        if not any(neg in low[max(0, i - 20):i] for neg in _NEGATORS):
            return True
        i = low.find(tok, i + 1)
    return False


def _grade_answer(answer: str, q: dict) -> bool:
    """Deterministic answer correctness — required facts stated and not negated.
    `must_all` → every token (exact/multi-part facts); `answer_any` → any token
    (comparative answers whose correct keyword differs from the retrieval keyword);
    else `expect_any` → any token."""
    if not answer:
        return False
    if q.get("must_all"):
        return all(_stated(answer, t) for t in q["must_all"])
    return any(_stated(answer, t) for t in (q.get("answer_any") or q["expect_any"]))


def _pct(vals: list[float], p: float) -> float:
    """p-th percentile (nearest-rank) — deterministic, no numpy."""
    if not vals:
        return 0.0
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def _wilson(k: int, n: int) -> tuple[float, float]:
    """95% Wilson score interval for a k/n success rate — the right CI for small-n proportions.
    Deterministic, stdlib only (no scipy)."""
    if n == 0:
        return (0.0, 0.0)
    z, phat = 1.96, k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


async def _get(c: httpx.AsyncClient, url: str, h: dict, params: dict | None = None) -> dict | list | None:
    """
    One retrieval GET. Returns the decoded body on 200, else None.

    A retrieval failure must degrade *this question's context* — never end the run. The three
    calls below used to invoke `c.get` directly, so a single slow `/search` (Jina embed + ES +
    Qdrant + Neo4j all sit behind it) raised `ReadTimeout` out of `main()` and discarded every
    question already graded. Observed 2026-08-16: the run died on Q22 and threw away 21 questions
    of paced synthesis — ~20 minutes of provider quota for zero output. A question that loses its
    context scores as a retrieval miss, which is the honest outcome; the run continues.

    One helper rather than three try/except blocks: the guard belongs where the request is made.
    """
    try:
        r = await c.get(url, headers=h, params=params, timeout=RETRIEVAL_TIMEOUT)
        if r.status_code != 200:
            print(f"  ! retrieval HTTP {r.status_code} on {url}", flush=True)
            return None
        return r.json()
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        print(f"  ! retrieval failed ({type(e).__name__}) on {url}", flush=True)
        return None


async def _gather_context(c: httpx.AsyncClient, h: dict, q: dict) -> list[dict]:
    """Route the question to its proper source(s) and return synthesis context items."""
    sources = q.get("context_sources", ["search"])
    aid = q.get("asset_id")
    ctx: list[dict] = []

    if "search" in sources:
        params = {"q": q["question"], "limit": 5}
        if aid:
            params["asset_id"] = aid
        body = await _get(c, f"{API}/search", h, params)
        if body:
            ctx += body.get("results", [])

    if aid and "knowledge" in sources:
        body = await _get(c, f"{API}/assets/{aid}/knowledge", h)
        if body:
            for f in body.get("facts", [])[:8]:
                edge = f.get("edge") or {}
                ctx.append({"text": json.dumps(f)[:400], "document_id": edge.get("document_id", "graph"), "authority_level": edge.get("authority_level", 3)})

    if aid and "aliases" in sources:
        body = await _get(c, f"{API}/assets/{aid}/aliases", h)
        if body:
            aliases = [a.get("alias") for a in body if a.get("alias")]
            if aliases:
                ctx.append({"text": f"Known aliases for {aid}: {', '.join(aliases)}", "document_id": "alias_map", "authority_level": 1})

    return ctx



def _selftest() -> None:
    """Assert the deterministic grader — the negation guard is the part that can silently rot."""
    # must_all: every token, non-negated
    assert _grade_answer("Use seal FSL-2240B for the pump.", {"must_all": ["FSL-2240B"]})
    assert not _grade_answer("Do not use FSL-2240B.", {"must_all": ["FSL-2240B"]})   # negated → wrong
    assert not _grade_answer("Isolation needs XV-203 and XV-204.", {"must_all": ["XV-203", "XV-204", "PG-18"]})  # missing PG-18
    assert _grade_answer("The limit is 16.2 bar now.", {"must_all": ["16.2"]})
    assert not _grade_answer("The limit is not 16.2 bar.", {"must_all": ["16.2"]})   # negated numeric
    # answer_any: any correct-answer token
    assert _grade_answer("No, it is a different failure family.", {"answer_any": ["different", "unrelated"]})
    assert not _grade_answer("It was a seal failure again.", {"answer_any": ["different", "unrelated"]})
    # expect_any fallback + empty answer
    assert _grade_answer("Thermal cycling precedes it.", {"expect_any": ["thermal"]})
    assert not _grade_answer("", {"must_all": ["x"]})
    # stats helpers
    lo, hi = _wilson(10, 12)
    assert 0.0 <= lo < 10 / 12 < hi <= 1.0          # CI brackets the point estimate
    assert _wilson(0, 0) == (0.0, 0.0)              # no divide-by-zero on empty
    assert _pct([1, 2, 3, 4], 50) == 3 and _pct([], 95) == 0.0
    # validity verdict — the gate that stops a quota-starved run being quoted as a model result
    assert _validity(Counter(nim=25), 25, 25, False).startswith("VALID")
    assert _validity(Counter(nim=20, refused=5), 25, 25, False).startswith("VALID")
    # openrouter serves a different model from nim since the 2026-09 switch, so it is a fallback
    assert _validity(Counter(openrouter=25), 25, 25, False).startswith("SUSPECT")
    assert _validity(Counter(nim=13, openrouter=12), 25, 25, False).startswith("SUSPECT")
    assert _validity(Counter(nim=23, openrouter=2), 25, 25, False).startswith("VALID")
    assert _validity(Counter(nim=20, gemini=5), 25, 25, False).startswith("SUSPECT")   # 5 > 25//10
    assert _validity(Counter(nim=23, gemini=2), 25, 25, False).startswith("VALID")     # 2 tolerated as noise
    assert _validity(Counter(nim=22, gemini=3), 25, 25, False).startswith("SUSPECT")   # 3 starts moving the score
    assert _validity(Counter(nim=10, **{"429": 2}), 12, 25, True).startswith("INVALID")
    assert _validity(Counter(nim=10, **{"429": 1}), 11, 25, False).startswith("INVALID")
    # no-answer rows invalidate, and outrank a smaller Gemini complaint (the 2026-08-15 17/25 run)
    assert _validity(Counter(nim=12, gemini=3, refused=3, **{"-": 7}), 25, 25, False).startswith("INVALID")
    assert "no answer" in _validity(Counter(nim=18, **{"-": 7}), 25, 25, False)
    assert _validity(Counter(nim=24, timeout=1), 25, 25, False).startswith("SUSPECT")
    assert _provider_mix(Counter(nim=3, gemini=1)) == "nim 3 · gemini 1"
    assert _provider_mix(Counter()) == "(none)"
    print("selftest: OK")


def _load_checkpoint(path: str) -> dict[str, dict]:
    """Rows already graded by an earlier attempt, keyed by question id.

    Insurance, not a cache: a full sweep is ~30 minutes of *paced* synthesis, and losing it to one
    slow call means re-spending the whole provider budget to learn the same thing. Rows are
    disclosed in the summary, never silently merged — a resumed run is two points in time and the
    reader has to be able to see that.
    """
    rows: dict[str, dict] = {}
    if not path or not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue          # a torn last line from a killed process — ignore it
            if row.get("id"):
                rows[row["id"]] = row
    return rows


def _append_checkpoint(path: str, row: dict) -> None:
    """Record one graded question immediately, so a later crash cannot un-spend it."""
    if not path:
        return
    try:
        with open(path, "a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError as e:  # a checkpoint failure must never discard a good measurement
        print(f"  ! checkpoint write failed ({type(e).__name__}: {e})", flush=True)


async def main(retrieval_only: bool, delay: float = 0.0, limit: int = 0, checkpoint: str = "") -> None:
    with open(QUESTIONS) as f:
        questions = json.load(f)["questions"]
    if limit:
        questions = questions[:limit]
    n = len(questions)

    # Checkpointing only applies to a full run; --retrieval-only is ~2 minutes and costs nothing
    # to repeat, so there is nothing to protect.
    checkpoint = "" if retrieval_only else checkpoint
    done = _load_checkpoint(checkpoint)
    if done:
        print(f"\n  Resuming: {len(done)} question(s) already graded in {checkpoint}", flush=True)

    print(f"\n  Kairos — Domain Benchmark  ({n} questions)")
    print("  " + "=" * 84)
    hdr = f"  {'ID':<5}{'QUESTION':<46}{'RETR':<6}"
    if not retrieval_only:
        hdr += f"  {'CORRECT':<8}{'SRC':<5}{'VIA':<9}{'ms':>6}"  # CORRECT = facts stated + not negated
    print(hdr)
    print("  " + "-" * 84, flush=True)

    retr_hits, correct_hits, prov_hits, syn_ms = 0, 0, 0, []
    # per-category tallies: cat -> {"n","retr","correct","prov"}
    cats: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "retr": 0, "correct": 0, "prov": 0})
    # Which tier actually answered. A run served largely by the Gemini fallback is not a
    # measurement of the production model, so this is counted, not just displayed.
    via_counts: Counter[str] = Counter()
    graded = 0            # questions that reached the grader (a 429 abort stops short of n)
    consecutive_429 = 0
    aborted = False

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.post(f"{API}/auth/login", json={"email": "admin@kairos.local", "password": "KairosAdmin123!"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        for qi, q in enumerate(questions):
            cat = q.get("category", "uncategorized")
            cats[cat]["n"] += 1
            prior = done.get(q["id"])
            spent = False     # did this question cost a synthesis call in *this* attempt?

            if prior:
                r_hit = bool(prior["retr"])
            else:
                ctx = await _gather_context(c, h, q)
                r_hit = _kw_hit(json.dumps(ctx), q["expect_any"])
            retr_hits += r_hit
            cats[cat]["retr"] += r_hit
            line = f"  {q['id']:<5}{q['question'][:44]:<46}{'HIT' if r_hit else 'miss':<6}"

            if not retrieval_only:
                correct, sourced, prov, ms = False, False, "-", 0.0
                if prior:
                    correct, sourced, prov, ms = bool(prior["correct"]), bool(prior["prov"]), prior["via"], float(prior["ms"])
                else:
                    spent = True
                    t = time.perf_counter()
                    try:
                        syn = await c.post(f"{API}/search/synthesize", headers=h, json={"query": q["question"], "context": ctx[:8]}, timeout=SYNTH_TIMEOUT)
                        ms = (time.perf_counter() - t) * 1000
                        body = syn.json() if syn.status_code == 200 else {}
                        refused = bool(body.get("refused"))
                        prov = body.get("model") or ("refused" if refused else "-")
                        # Correct = facts stated (not negated) AND provenance present. Refusal is a valid,
                        # correct outcome (safety gate) and carries its own sources.
                        sourced = refused or bool(body.get("sources"))
                        correct = (refused or _grade_answer(body.get("answer") or "", q)) and sourced
                        if body.get("rate_limited"):
                            prov, consecutive_429 = "429", consecutive_429 + 1
                        else:
                            consecutive_429 = 0
                    except (httpx.TimeoutException, httpx.HTTPError):
                        ms, prov = (time.perf_counter() - t) * 1000, "timeout"
                    _append_checkpoint(checkpoint, {
                        "id": q["id"], "retr": int(r_hit), "correct": int(correct),
                        "prov": int(sourced), "via": prov, "ms": round(ms),
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    })
                syn_ms.append(ms)
                via_counts[prov] += 1
                graded += 1
                correct_hits += correct
                prov_hits += sourced
                cats[cat]["correct"] += correct
                cats[cat]["prov"] += sourced
                line += f"  {'YES' if correct else 'no':<8}{'✓' if sourced else '·':<5}{prov:<9}{ms:>6.0f}"
                if prior:
                    line += "  (resumed)"

            print(line, flush=True)

            # Every tier returned 429 twice running: the quota is gone and every remaining
            # question would score as a miss. Stop rather than spend the rest of the run
            # manufacturing a low number that looks like a model result.
            if consecutive_429 >= 2:
                print("\n  ABORTED — all synthesis providers returned HTTP 429 twice in a row.", flush=True)
                print("  The remaining questions would score 0 for quota reasons, not model reasons.", flush=True)
                aborted = True
                break

            # Pace the next synthesis call. See the module docstring: back-to-back calls are
            # what push NIM into its timeout tail and spill the run onto the free Gemini tier.
            # A resumed row made no call, so there is nothing to pace away from — sleeping there
            # would add 15 s per already-graded question for no benefit.
            if delay and spent and qi < n - 1:
                await asyncio.sleep(delay)

    def _rate(k: int, tot: int) -> str:
        lo, hi = _wilson(k, tot)
        return f"{k}/{tot} ({100*k//tot if tot else 0}%)  95% CI [{100*lo:.0f}–{100*hi:.0f}%]"

    # An aborted run graded fewer questions than the file holds; rate against what actually ran.
    looped = sum(d["n"] for d in cats.values())
    print("  " + "-" * 84)
    print(f"  Retrieval (fact reaches context):    {_rate(retr_hits, looped)}")
    if not retrieval_only:
        print(f"  Answer quality (facts, not negated): {_rate(correct_hits, graded)}")
        print(f"  Provenance (sources cited):          {_rate(prov_hits, graded)}")
        print(f"  Synthesis latency:                   p50 {_pct(syn_ms,50):.0f} ms · p95 {_pct(syn_ms,95):.0f} ms · avg {sum(syn_ms)/len(syn_ms):.0f} ms")
        print(f"  Answered by:                         {_provider_mix(via_counts)}")
        print(f"  Run validity:                        {_validity(via_counts, graded, n, aborted)}")
        # Disclosed, never silent: a resumed run is two points in time, and a reader quoting the
        # headline is entitled to know that before treating it as one sitting.
        resumed = sum(1 for q in questions if q["id"] in done)
        if resumed:
            stamps = sorted({done[q["id"]].get("at", "?") for q in questions if q["id"] in done})
            print(f"  Resumed rows:                        {resumed}/{graded} carried from an earlier "
                  f"attempt ({stamps[0]} … {stamps[-1]})")

    print("\n  By category" + (" (retrieval · answer · provenance)" if not retrieval_only else " (retrieval)"))
    for cat in sorted(cats):
        d = cats[cat]
        if retrieval_only:
            print(f"    {cat:<22} {d['retr']}/{d['n']}")
        else:
            print(f"    {cat:<22} {d['retr']}/{d['n']} · {d['correct']}/{d['n']} · {d['prov']}/{d['n']}")
    try:
        print(f"  KG linkage (assets):               {await _kg_completeness()}")
        # The PS criterion is document-centric: "assets linked" reads 100% as soon as every asset
        # has one edge, which is reachability rather than completeness. Imported rather than
        # reimplemented so both harnesses report the same number.
        from run_kg_completeness import measure, summary_line
        print(f"  KG linkage (documents):            {summary_line(await measure())}")
    except Exception as e:  # noqa: BLE001
        print(f"  KG linkage:                        (unavailable: {type(e).__name__})")
    print("  Entity-extraction F1: backend/scripts/run_model_validation.py (Layer-0 model gate)\n")


def _provider_mix(via: "Counter[str]") -> str:
    """Which tier served each answer, most common first. `nim` is the production model."""
    return " · ".join(f"{k} {v}" for k, v in via.most_common()) or "(none)"


def _validity(via: "Counter[str]", graded: int, total: int, aborted: bool) -> str:
    """
    States plainly whether this run may be quoted as an answer-quality figure.

    A run served by the Gemini fallback measures the fallback, not the production model;
    a run that hit 429 measures an exhausted quota. Both previously printed a clean-looking
    score with nothing distinguishing them from a real result (see benchmark/RESULTS.md,
    runs 4-5 at 13/25 and 18/25).
    """
    if aborted:
        return f"INVALID — aborted on provider 429 after {graded}/{total} questions. Do not quote."
    if via.get("429"):
        return f"INVALID — {via['429']} question(s) hit provider quota (429). Do not quote."
    # A "-" row is a question where every provider failed, so no answer came back at all. It grades
    # as a miss and is indistinguishable in the score from the model being wrong — the exact
    # confusion this verdict exists to prevent. It was missed on the first pass: a run with 7 of
    # these still printed "SUSPECT: 3 from Gemini", naming the smaller problem.
    if via.get("-"):
        return (f"INVALID — {via['-']} question(s) returned no answer from any provider "
                "(infrastructure, not model quality). Do not quote.")
    # Only `nim` serves the pinned model. `openrouter` (llama-3.1-70b) and `gemini` are both a
    # different model since NVIDIA retired llama-3.1-70b and tier 1 moved to Nemotron (2026-09-13),
    # so either one confounds the score.
    same_model = via.get("nim", 0)
    # A stray fallback or two is noise; beyond ~10% the headline number is partly measuring
    # a different model, which is exactly the confound RESULTS.md warns about.
    fallback = via.get("gemini", 0) + via.get("openrouter", 0)
    if graded and fallback > max(1, graded // 10):
        return (f"SUSPECT — {fallback}/{graded} answers came from a fallback provider (openrouter/gemini), "
                "which is a different model. Re-run paced (--delay) before quoting.")
    if via.get("timeout"):
        return f"SUSPECT — {via['timeout']} question(s) timed out client-side. Re-run before quoting."
    return f"VALID — {same_model}/{graded} answered by the pinned NIM model."


async def _kg_completeness() -> str:
    from neo4j import AsyncGraphDatabase

    from api.config import Settings

    s = Settings()
    driver = AsyncGraphDatabase.driver(s.NEO4J_URI, auth=(s.NEO4J_USERNAME, s.NEO4J_PASSWORD))
    try:
        async with driver.session(database=s.NEO4J_DATABASE) as sess:
            async def scalar(cypher: str, key: str) -> int:
                rec = await (await sess.run(cypher)).single()
                return int(rec[key]) if rec and rec[key] is not None else 0

            assets = await scalar("MATCH (a:Asset) RETURN count(a) AS n", "n")
            linked = await scalar("MATCH (a:Asset)-[:KNOWLEDGE_EDGE]-() RETURN count(DISTINCT a) AS n", "n")
            edges = await scalar("MATCH ()-[k:KNOWLEDGE_EDGE]->() RETURN count(k) AS n", "n")
            verified = await scalar("MATCH ()-[k:KNOWLEDGE_EDGE]->() WHERE k.verification_status='verified' RETURN count(k) AS n", "n")
    finally:
        await driver.close()
    return (f"{linked}/{assets} assets linked ({(100*linked//assets) if assets else 0}%) · "
            f"{edges} edges ({verified} verified)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Kairos domain-expert benchmark")
    ap.add_argument("--retrieval-only", action="store_true", help="skip synthesis + grading (retrieval + KG only, fast)")
    ap.add_argument("--selftest", action="store_true", help="assert the grader logic and exit (no stack needed)")
    ap.add_argument("--delay", type=float, default=15.0,
                    help="seconds between synthesis calls (default 15). Pacing keeps the run on NIM "
                         "instead of spilling onto the free Gemini tier; --delay 0 restores the old behaviour.")
    ap.add_argument("--limit", type=int, default=0,
                    help="grade only the first N questions — a cheap calibration run to check the "
                         "provider mix before spending a full sweep. 0 = all.")
    ap.add_argument("--checkpoint", default="",
                    help="append each graded question to this JSONL and skip questions it already "
                         "holds. A full sweep is ~30 min of paced synthesis; without this, one slow "
                         "call re-spends the entire provider budget. Resumed rows are disclosed in "
                         "the summary. Delete the file to force a clean run. "
                         "PUT IT ON A HOST-MOUNTED PATH — /app/.benchmark_runs/ is bind-mounted, "
                         "/tmp is not: a container rebuild mid-run wiped /tmp and destroyed a "
                         "completed 37-question sweep on 2026-08-16.")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    else:
        asyncio.run(main(args.retrieval_only, args.delay, args.limit, args.checkpoint))
