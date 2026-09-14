#!/usr/bin/env python3
"""
Kairos — concurrency load test.

Supplies the scalability evidence the project had none of: every other number in
benchmark/RESULTS.md is single-user and sequential, so nothing showed how the stack
behaves under concurrent load.

WHAT IT DOES
  Sweeps concurrency levels against read endpoints, reporting p50/p95/p99, throughput and
  error rate at each level. The useful output is the *shape*: the level at which p95 starts
  climbing is where the first bottleneck is, and that is the number worth quoting.

WHAT IT DELIBERATELY DOES NOT DO
  Model-backed endpoints (/search, /search/synthesize, /search/rca-pack) are excluded by
  default. They call NIM/Jina per request, so a 50-user sweep would burn provider quota and
  hit rate limits — the same reason /system-health keeps model probes opt-in. Pass
  --include-models to measure them, knowing each request spends real quota.

  This is a load test, not a soak test: it says nothing about memory growth or connection
  leakage over hours.

  No new dependency — httpx + asyncio are already in the image, and an HTTP load generator
  is not worth a locust/k6 install.

USAGE
  docker compose exec kairos-backend-api python /app/benchmark/run_load_test.py
  docker compose exec kairos-backend-api python /app/benchmark/run_load_test.py --levels 1,10,50
"""

import argparse
import asyncio
import os
import statistics
import sys
import time

import httpx

API = os.getenv("API_BASE_URL", "http://localhost:8000")
KEY = os.getenv("INTERNAL_API_KEY", "kairos-internal-dev-key")

# Cheap graph/Postgres reads — the endpoints a plant actually hammers.
READ_ENDPOINTS = [
    "/assets",
    "/documents",
    "/briefs",
    "/compliance/dashboard",
    "/compliance/gaps?limit=50",
    "/governance/quarantine",
    "/governance/conflicts",
    "/events",
    "/health/detailed",
]

# Each of these spends provider quota per call. Opt-in only.
MODEL_ENDPOINTS = ["/search?q=mechanical+seal+failure&limit=5"]


async def _one(client: httpx.AsyncClient, path: str) -> tuple[float, bool]:
    t = time.perf_counter()
    try:
        r = await client.get(f"{API}{path}", headers={"Authorization": f"Bearer {KEY}"})
        # 2xx only. A bare `< 400` counted 307s as success, so an un-followed redirect
        # measured redirect latency instead of the endpoint's real work.
        return (time.perf_counter() - t) * 1000, 200 <= r.status_code < 300
    except Exception:
        return (time.perf_counter() - t) * 1000, False


async def _level(paths: list[str], concurrency: int, requests_per_worker: int) -> dict:
    """Runs `concurrency` workers, each issuing `requests_per_worker` requests round-robin."""
    latencies: list[float] = []
    failures = 0

    async def worker(worker_id: int) -> None:
        nonlocal failures
        limits = httpx.Limits(max_connections=concurrency + 10, max_keepalive_connections=concurrency)
        async with httpx.AsyncClient(timeout=30.0, limits=limits, follow_redirects=True) as client:
            for i in range(requests_per_worker):
                path = paths[(worker_id + i) % len(paths)]
                ms, ok = await _one(client, path)
                latencies.append(ms)
                if not ok:
                    failures += 1

    started = time.perf_counter()
    await asyncio.gather(*(worker(i) for i in range(concurrency)))
    wall = time.perf_counter() - started

    latencies.sort()

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        return latencies[min(len(latencies) - 1, int(len(latencies) * p))]

    total = len(latencies)
    return {
        "concurrency": concurrency,
        "requests": total,
        "wall_s": wall,
        "rps": total / wall if wall else 0.0,
        "p50": statistics.median(latencies) if latencies else 0.0,
        "p95": pct(0.95),
        "p99": pct(0.99),
        "max": latencies[-1] if latencies else 0.0,
        "errors": failures,
        "error_rate": failures / total if total else 0.0,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="1,5,10,25,50", help="comma-separated concurrency levels")
    ap.add_argument("--requests", type=int, default=10, help="requests per worker per level")
    ap.add_argument("--include-models", action="store_true", help="also load model-backed endpoints (spends quota)")
    args = ap.parse_args()

    paths = READ_ENDPOINTS + (MODEL_ENDPOINTS if args.include_models else [])
    levels = [int(x) for x in args.levels.split(",") if x.strip()]

    print("  Kairos — Concurrency Load Test")
    print("  " + "=" * 78)
    print(f"  Endpoints: {len(paths)} ({'incl. model-backed' if args.include_models else 'reads only'})")
    print(f"  Requests per worker per level: {args.requests}")
    print()
    print(f"  {'VU':>4} {'reqs':>6} {'rps':>8} {'p50 ms':>9} {'p95 ms':>9} {'p99 ms':>9} {'max ms':>9} {'err':>6}")
    print("  " + "-" * 78)

    results = []
    for concurrency in levels:
        r = await _level(paths, concurrency, args.requests)
        results.append(r)
        print(
            f"  {r['concurrency']:>4} {r['requests']:>6} {r['rps']:>8.1f} {r['p50']:>9.1f}"
            f" {r['p95']:>9.1f} {r['p99']:>9.1f} {r['max']:>9.1f} {r['error_rate']:>5.1%}"
        )
        await asyncio.sleep(1)  # let connection pools drain between levels

    baseline = results[0]["p95"] or 1.0
    print()
    print("  p95 relative to single-user baseline:")
    factors = []
    for r in results:
        factor = r["p95"] / baseline
        factors.append((r["concurrency"], factor))
        print(f"    {r['concurrency']:>4} VU  ->  {factor:5.2f}x")

    # A knee must be SUSTAINED: exceeding 3x at one level then dropping back below it at a
    # higher level is sampling noise, not a bottleneck. Requiring every higher level to stay
    # above the threshold stops this harness reporting opposite conclusions on consecutive
    # runs of the same system — which it did before this guard existed.
    knee = None
    for i, (vu, factor) in enumerate(factors):
        if factor > 3.0 and all(f > 3.0 for _, f in factors[i:]):
            knee = vu
            break

    noisy = any(f > 3.0 for _, f in factors) and knee is None
    baseline_samples = results[0]["requests"]

    print()
    if knee:
        print(f"  First sustained bottleneck: p95 exceeds 3x baseline from {knee} VU upward.")
        print("  Quote this number, not the single-user latency.")
    elif noisy:
        print("  No SUSTAINED degradation: p95 crosses 3x at some level but drops back below it")
        print("  at a higher one, so the crossing is sampling noise. Read the absolute p50/p95")
        print("  and error columns above instead of any single ratio.")
    else:
        print(f"  p95 stayed within 3x baseline through {levels[-1]} concurrent users.")

    if baseline_samples < 20:
        print(f"  ⚠ baseline is only {baseline_samples} requests — ratios are high-variance.")
        print("    Re-run with --requests 20 or more before quoting a degradation factor.")

    worst = max(results, key=lambda r: r["error_rate"])
    if worst["error_rate"]:
        print(f"  Errors appear at {worst['concurrency']} VU ({worst['error_rate']:.1%}) — investigate before quoting throughput.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
