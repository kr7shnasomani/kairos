"""
Kairos — Layer smoke + latency verification.

Runs one real action per architecture layer against the LIVE stack and prints a
PASS/FAIL + latency (ms) table. Doubles as a smoke test and a light perf check.

Run inside the API container:
    docker exec kairos-backend-api python scripts/verify_layers.py
    docker exec kairos-backend-api python scripts/verify_layers.py --full   # + slow LLM/VLM checks (hit NIM)

Exit code: 0 if all checks pass, 1 otherwise (usable in CI).
"""

import argparse
import asyncio
import os
import sys
import time

import httpx

API = os.getenv("VERIFY_API_URL", "http://localhost:8000")
GO = os.getenv("OT_CONNECTOR_URL", "http://kairos-backend-go:8090")
FRONTEND = os.getenv("VERIFY_FRONTEND_URL", "http://kairos-frontend:3000")
PID_IMAGE = "/app/dataset/02_Document_Corpus/pid_line3_isolation_boundary.png"

_results: list[tuple[str, str, bool, float, str]] = []  # (layer, check, ok, ms, note)


async def _val(ok: bool, note: str) -> tuple[bool, str]:
    return ok, note


async def main(full: bool) -> None:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        token = None
        try:
            r = await c.post(f"{API}/auth/login", json={"email": "admin@kairos.local", "password": "KairosAdmin123!"})
            token = r.json().get("access_token")
        except Exception:
            pass
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        async def run(layer: str, check: str, coro) -> None:
            t = time.perf_counter()
            try:
                ok, note = await coro
            except Exception as e:  # noqa: BLE001 — report, don't crash the run
                ok, note = False, type(e).__name__
            _results.append((layer, check, ok, (time.perf_counter() - t) * 1000, note))

        async def GET(path: str, base: str = API, timeout: float = 20) -> tuple[bool, str]:
            r = await c.get(f"{base}{path}", headers=headers, timeout=timeout)
            return r.status_code == 200, f"HTTP {r.status_code}"

        # --- fast checks (one representative action per layer) ---
        await run("Auth", "POST /auth/login", _val(token is not None, "token ok" if token else "NO TOKEN"))
        await run("L0 Validation", "GET /governance/validation-corpus/stats", GET("/governance/validation-corpus/stats"))
        await run("L1 MDM", "GET /assets", GET("/assets?limit=1"))
        await run("L2 Vault", "GET /documents", GET("/documents/?limit=1"))
        await run("L4 Graph", "GET /governance/circuit-breaker", GET("/governance/circuit-breaker"))
        await run("L5 OT (mock)", "GET /ot/query (go connector)", GET("/ot/query?asset_id=P-101&tag=VIBE", base=GO))
        await run("L6 Quarantine", "GET /governance/quarantine", GET("/governance/quarantine?limit=1"))
        await run("L7 Governance", "GET /governance/conflicts", GET("/governance/conflicts?limit=1"))
        await run("L8 Events/Briefs", "GET /briefs", GET("/briefs"))
        await run("L9 Elicitation", "GET /elicitation/offboarding", GET("/elicitation/offboarding"))
        await run("L11 Retrieval", "GET /search", GET("/search?q=seal+failure&limit=3"))
        await run("L12 Frontend", "GET / (frontend)", GET("/", base=FRONTEND))
        await run("Datastores", "GET /health/detailed", GET("/health/detailed"))

        # --- slow checks (LLM/VLM — hit NIM; opt-in) ---
        if full:
            await run("L3 Perception (VLM)", "P&ID topology extract", _pid_check())
            await run("L11 Synthesis (LLM)", "POST /search/synthesize", _synthesize(c, headers))

    _print_table()
    sys.exit(0 if all(ok for _, _, ok, _, _ in _results) else 1)


async def _pid_check() -> tuple[bool, str]:
    from api.services.pid import PIDService

    with open(PID_IMAGE, "rb") as f:
        topo = await PIDService().extract_topology(f.read(), "image/png")
    if not topo:
        return False, "None (NIM unreachable?)"
    n = sum(len(topo.get(k, [])) for k in ("equipment_nodes", "isolation_valves", "instrumentation_loops", "isolation_boundaries"))
    return n > 0, f"{n} elements extracted"


async def _synthesize(c: httpx.AsyncClient, headers: dict) -> tuple[bool, str]:
    r = await c.post(
        f"{API}/search/synthesize",
        headers=headers,
        json={"query": "What is the maintenance history for pump P-101?", "context": []},
        timeout=120,
    )
    j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    return r.status_code == 200, f"HTTP {r.status_code}, answer={'yes' if j.get('answer') else 'none'}"


def _print_table() -> None:
    passed = sum(1 for r in _results if r[2])
    print("\n  Kairos — Layer Verification")
    print("  " + "=" * 78)
    print(f"  {'LAYER':<22}{'CHECK':<38}{'STATUS':<7}{'ms':>7}")
    print("  " + "-" * 78)
    for layer, check, ok, ms, note in _results:
        print(f"  {layer:<22}{check:<38}{'PASS' if ok else 'FAIL':<7}{ms:>7.0f}   {note}")
    print("  " + "-" * 78)
    print(f"  {passed}/{len(_results)} checks passed\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Kairos per-layer smoke + latency check")
    ap.add_argument("--full", action="store_true", help="include slow LLM/VLM checks (hit NIM)")
    asyncio.run(main(ap.parse_args().full))
