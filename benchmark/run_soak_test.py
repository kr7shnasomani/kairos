#!/usr/bin/env python3
"""
Kairos — soak test (backlog #4).

WHAT THIS IS FOR, AND WHY IT IS NOT THE LOAD TEST
  `run_load_test.py` sweeps *concurrency* — 1→50 VU over a few minutes — and answers "how many
  simultaneous users before p95 degrades". It cannot answer "does this process survive a working
  day", because nothing runs long enough for a leak to become visible.

  This holds a *steady, low* load for a long window and watches the slope of four things: resident
  memory, open connections, latency, and error rate. A rising RSS **slope** is the finding; a single
  high reading is not.

WHAT IT STRESSES — the three components in this codebase shaped like leaks
  • `services/http.py shared_client()` — cached per event loop; Celery opens a fresh loop per task,
    so a mistake accumulates clients rather than reusing one.
  • `services/llm.py _LRU` (maxsize 512) — bounded in entry *count*, not bytes; 512 Jina v3 vectors
    is a real resident footprint.
  • The Neo4j Aura driver pool (`dependencies.py`: liveness_check_timeout=30,
    max_connection_lifetime=300) — Aura closes idle connections within minutes, and this already
    produced one live bug (`SessionExpired`). Phase 3 below is the direct regression test for it.

COST
  **No model provider is touched.** It reuses `run_load_test.py`'s reads-only endpoint list, where
  model-backed endpoints are excluded by default, so it cannot spend NIM / Jina / Gemini / Groq
  quota however long it runs.

USAGE (detached, durable log — /tmp does not survive a container rebuild)
  docker exec -d kairos-backend-api sh -c \\
    'python benchmark/run_soak_test.py --minutes 60 > /app/.benchmark_runs/soak.log 2>&1'

  --minutes N   soak duration (default 60)
  --vu N        concurrent workers (default 5 — this is about duration, not saturation)
  --interval N  seconds between samples (default 60)
  --idle N      phase-3 idle window in minutes (default 10; 0 skips the recovery check)
  --selftest    assert the slope/verdict maths and exit (no stack needed)
"""

import argparse
import asyncio
import os
import re
import sys
import time

sys.path.insert(0, "/app")

import httpx

from benchmark.run_load_test import READ_ENDPOINTS

API = os.getenv("API_BASE_URL", "http://localhost:8000")
KEY = os.getenv("INTERNAL_API_KEY", "kairos-internal-dev-key")
HEAD = {"Authorization": f"Bearer {KEY}"}

# Every one of these is Neo4j-backed. Phase 3 re-issues them after an idle window: this is exactly
# the path that threw `SessionExpired` when the driver pool lacked liveness checking.
NEO4J_ENDPOINTS = [
    "/compliance/dashboard",
    "/assets/EQ-101/knowledge",
    "/graph/asset/EQ-101",
    "/governance/blast-radius/DOC-NONE",
]


# ── sampling ────────────────────────────────────────────────────────────────────────────────
def _rss_kb() -> int:
    """Resident memory of every process in this container, summed.

    Read from /proc rather than `docker stats` because this runs *inside* the API container —
    no docker socket, no extra tooling. Summing all PIDs catches uvicorn workers, not just PID 1.
    """
    total = 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/status") as f:
                m = re.search(r"^VmRSS:\s+(\d+) kB", f.read(), re.M)
            if m:
                total += int(m.group(1))
        except (OSError, ProcessLookupError):
            continue          # process exited between listdir and open — normal
    return total


def _established() -> int:
    """Count ESTABLISHED sockets (state 01) across IPv4 + IPv6."""
    n = 0
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(path) as f:
                next(f, None)                     # header
                n += sum(1 for line in f if line.split()[3] == "01")
        except (OSError, IndexError):
            continue
    return n


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


# Samples dropped from the trend before fitting: the pre-load baseline plus the first loaded
# sample. Both are warm-up, not growth — an idle process holds ~295 MB and 3 connections, and the
# moment load starts it jumps to ~320 MB and ~35 connections as the pools fill. Regressing over
# that step reports the ramp as a slope: a 2-minute smoke run produced "+728 MB/hour" while the
# loaded samples read 319 → 322 → 322 → 323, i.e. flat. Same class of error as the load test's
# knee detector firing on a single noisy sample.
_WARMUP_SAMPLES = 2

# Below this many *steady-state* samples there is no trend to fit, and the honest answer is
# "not enough data" rather than a leak verdict extrapolated from noise.
_MIN_TREND_SAMPLES = 4


def _slope_per_hour(samples: list[tuple[float, float]]) -> float:
    """Least-squares slope in units/hour. Two points are enough; fewer is not a trend."""
    if len(samples) < 2:
        return 0.0
    n = len(samples)
    mx = sum(t for t, _ in samples) / n
    my = sum(v for _, v in samples) / n
    denom = sum((t - mx) ** 2 for t, _ in samples)
    if denom == 0:
        return 0.0
    slope_per_sec = sum((t - mx) * (v - my) for t, v in samples) / denom
    return slope_per_sec * 3600


# ── load ────────────────────────────────────────────────────────────────────────────────────
async def _worker(client: httpx.AsyncClient, stop: float, lat: list[float], errs: list[int]) -> None:
    i = 0
    while time.time() < stop:
        path = READ_ENDPOINTS[i % len(READ_ENDPOINTS)]
        i += 1
        t = time.perf_counter()
        try:
            r = await client.get(f"{API}{path}", headers=HEAD)
            lat.append((time.perf_counter() - t) * 1000)
            if not (200 <= r.status_code < 300):
                errs.append(r.status_code)
        except Exception:
            lat.append((time.perf_counter() - t) * 1000)
            errs.append(0)
        await asyncio.sleep(0.25)      # steady trickle, not a stress test


async def main(minutes: float, vu: int, interval: float, idle: float) -> int:
    t0 = time.time()
    stop_at = t0 + minutes * 60
    rss_samples: list[tuple[float, float]] = []
    conn_samples: list[tuple[float, float]] = []
    lat: list[float] = []
    errs: list[int] = []
    total_reqs = 0

    print(f"\n  Kairos — Soak Test   {minutes:g} min · {vu} VU · sample every {interval:g}s")
    print(f"  Endpoints: {len(READ_ENDPOINTS)} (reads only — no provider quota)")
    print("  " + "=" * 78)

    base_rss, base_conn = _rss_kb(), _established()
    print(f"  BASELINE   rss {base_rss / 1024:8.1f} MB · conns {base_conn:3d}")
    rss_samples.append((0.0, base_rss))
    conn_samples.append((0.0, base_conn))
    print(f"\n  {'elapsed':>8}  {'rss MB':>9}  {'conns':>6}  {'p50 ms':>8}  {'p95 ms':>8}  {'reqs':>7}  {'err':>5}")
    print("  " + "-" * 78)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        tasks = [asyncio.create_task(_worker(client, stop_at, lat, errs)) for _ in range(vu)]
        while time.time() < stop_at:
            await asyncio.sleep(min(interval, max(0.0, stop_at - time.time())))
            el = time.time() - t0
            rss, conn = _rss_kb(), _established()
            rss_samples.append((el, rss))
            conn_samples.append((el, conn))
            window, lat[:] = list(lat), []
            total_reqs += len(window)
            print(f"  {el/60:7.1f}m  {rss/1024:9.1f}  {conn:6d}  "
                  f"{_pct(window,50):8.1f}  {_pct(window,95):8.1f}  {len(window):7d}  {len(errs):5d}", flush=True)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        # ── phase 3: idle recovery ──────────────────────────────────────────────────────────
        recovery: list[tuple[str, str]] = []
        if idle > 0:
            print(f"\n  IDLE {idle:g} min — no traffic, so Aura can close pooled connections…", flush=True)
            await asyncio.sleep(idle * 60)
            print("  Recovery probes (a SessionExpired here is a real failure):")
            for path in NEO4J_ENDPOINTS:
                try:
                    r = await client.get(f"{API}{path}", headers=HEAD)
                    ok = "OK" if r.status_code < 500 else f"FAIL {r.status_code}"
                except Exception as e:
                    ok = f"FAIL {type(e).__name__}"
                recovery.append((path, ok))
                print(f"    {path:44} {ok}")

    post_rss, post_conn = _rss_kb(), _established()
    # Fit the trend on steady state only — see _WARMUP_SAMPLES.
    steady_rss = rss_samples[_WARMUP_SAMPLES:]
    steady_conn = conn_samples[_WARMUP_SAMPLES:]
    enough = len(steady_rss) >= _MIN_TREND_SAMPLES
    rss_slope = _slope_per_hour(steady_rss) / 1024
    conn_slope = _slope_per_hour(steady_conn)
    err_rate = 100 * len(errs) / total_reqs if total_reqs else 0.0
    warm_mb = (rss_samples[_WARMUP_SAMPLES - 1][1] - base_rss) / 1024 if len(rss_samples) >= _WARMUP_SAMPLES else 0.0

    print("\n  " + "=" * 78)
    print(f"  Requests: {total_reqs} · errors: {len(errs)} ({err_rate:.2f}%)")
    print(f"  RSS   {base_rss/1024:.1f} MB idle → {post_rss/1024:.1f} MB "
          f"(warm-up {warm_mb:+.1f} MB, then slope {rss_slope:+.1f} MB/hour over {len(steady_rss)} steady samples)")
    print(f"  Conns {base_conn} idle → {post_conn} (steady slope {conn_slope:+.1f}/hour)")
    print("\n  VERDICT")
    # Stated, never inferred. Thresholds are deliberately loose: this is a leak detector, not a
    # memory budget. A Python process that grows a few MB/hour under load is normal (allocator
    # arenas, LRU filling to its 512-entry cap); one that grows tens of MB/hour is not.
    verdicts = []
    if not enough:
        verdicts.append(("memory", "NO DATA", f"{len(steady_rss)} steady samples — need {_MIN_TREND_SAMPLES}"))
        verdicts.append(("connections", "NO DATA", "run longer, or lower --interval"))
    else:
        verdicts.append(("memory", "FLAT" if rss_slope < 10 else "GROWING", f"{rss_slope:+.1f} MB/hour"))
        verdicts.append(("connections", "STABLE" if conn_slope < 5 else "LEAKING", f"{conn_slope:+.1f}/hour"))
    verdicts.append(("errors", "CLEAN" if err_rate < 1 else "DEGRADED", f"{err_rate:.2f}%"))
    if recovery:
        bad = [p for p, s in recovery if s != "OK"]
        verdicts.append(("idle recovery", "OK" if not bad else "FAILED", f"{len(recovery)-len(bad)}/{len(recovery)} endpoints"))
    for name, state, detail in verdicts:
        print(f"    {name:16} {state:9} {detail}")

    failed = [v for v in verdicts if v[1] in ("GROWING", "LEAKING", "DEGRADED", "FAILED")]
    if not enough:
        print("\n  INCONCLUSIVE — too short to call a trend. Warm-up is excluded from the slope, "
              "so a\n  short run reports no data rather than extrapolating the ramp into a fake leak.")
    else:
        print(f"\n  {'PASS — no leak signal over this window.' if not failed else 'ATTENTION — ' + ', '.join(v[0] for v in failed)}")
    print("\n  Limits: speaks to hours, not days. A demo-scale dataset says nothing about 10k assets.")
    print("  Reads only — no synthesis, no embedding, so it does not exercise the model path.\n")
    return 1 if failed else 0


def _selftest() -> None:
    assert abs(_slope_per_hour([(0, 100), (3600, 200)]) - 100) < 1e-6      # +100/hour
    assert _slope_per_hour([(0, 100), (3600, 100)]) == 0                    # flat
    assert _slope_per_hour([(0, 100)]) == 0                                 # one point is not a trend
    assert abs(_slope_per_hour([(0, 200), (3600, 100)]) + 100) < 1e-6       # negative slope
    assert _pct([1, 2, 3, 4], 50) == 3 and _pct([], 95) == 0.0
    # The warm-up bug, pinned: idle baseline + first loaded sample must not enter the trend.
    # With them included this series reads as a steep climb; excluded, it is flat.
    # Real numbers from the 2026-08-17 smoke run (kB): idle baseline, then load.
    warmup_series = [(0.0, 301_600), (30.0, 326_900), (60.0, 329_800), (90.0, 330_400), (120.0, 330_900)]
    with_warmup = _slope_per_hour(warmup_series) / 1024
    without = _slope_per_hour(warmup_series[_WARMUP_SAMPLES:]) / 1024
    assert with_warmup > 400, f"including warm-up must look like a huge leak, got {with_warmup:.0f}"
    assert without < with_warmup / 5, f"excluding warm-up must collapse the slope: {with_warmup:.0f} -> {without:.0f}"
    # …and with only 3 steady samples the verdict must be NO DATA regardless of that slope,
    # which is what stops a short run reporting a leak at all.
    assert len(warmup_series[_WARMUP_SAMPLES:]) < _MIN_TREND_SAMPLES
    assert _rss_kb() > 0, "RSS must be readable from /proc"
    assert _established() >= 0
    print("selftest: OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Kairos soak test — steady load, leak detection")
    ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("--vu", type=int, default=5)
    ap.add_argument("--interval", type=float, default=60)
    ap.add_argument("--idle", type=float, default=10, help="phase-3 idle window in minutes; 0 to skip")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
    else:
        sys.exit(asyncio.run(main(a.minutes, a.vu, a.interval, a.idle)))
