"""STAGED — copy to benchmark/run_brief_eval.py after SOAK_DONE.

Proactive-brief quality (Layer 8) — the eval the suite was missing.

WHY THIS EXISTS. Every other benchmark measures retrieval and Q&A: whether Kairos answers a
question well. But the project's thesis is that *retrieval is the wrong paradigm* and the unit of
value is a brief delivered before anyone asks. That claim had exactly one check behind it —
`verify_layers.py` asserting `GET /briefs` returns 200 — which is liveness, not quality.

WHAT IT MEASURES. For each trigger event, assemble the real brief through `BriefEngine` and grade
its content deterministically: did the brief carry the facts a technician needed, cite sources,
label quarantined input, and set the right priority for a safety-critical permit.

WHY IT CALLS BriefEngine DIRECTLY rather than POSTing to /events. The event routes defer assembly
by LATE_ARRIVAL_WINDOW_MINUTES (default 5) through a Celery countdown, so an end-to-end run would
take 30+ minutes and measure the scheduler rather than the brief. This exercises the same
assembly path the worker calls.

COST: embeddings only. `BriefEngine` never calls synthesis (only `llm.embed`), so this does not
consume LLM quota and is safe to run repeatedly.

    docker exec kairos-backend-api python benchmark/run_brief_eval.py
    docker exec kairos-backend-api python benchmark/run_brief_eval.py --report-only
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

# Reuse the negation-aware matcher rather than re-implementing it — the negation guard is the
# part that silently rots, and one copy is the only way it stays consistent with run_benchmark.
sys.path.insert(0, str(Path(__file__).parent))
from run_benchmark import _stated  # noqa: E402

EXPECTATIONS = Path(__file__).parent / "brief_expectations.json"


def _brief_blob(brief) -> str:
    """Everything the recipient can actually read, as one searchable string."""
    parts = [
        brief.headline or "",
        brief.body or "",
        " ".join(brief.action_items or []),
        " ".join(brief.warnings or []),
        " ".join(brief.quarantine_flags or []),
    ]
    for s in brief.sources or []:
        parts.append(getattr(s, "document_id", "") or "")
        parts.append(getattr(s, "title", "") or "")
    return " ".join(parts)


async def _assemble(engine, case: dict):
    from api.models.event import InspectionCompleteEvent, PTWEvent, TagOutEvent, WorkOrderEvent

    trigger, ev = case["trigger"], case["event"]
    if trigger == "work_order_created":
        return await engine.assemble_work_order_brief(WorkOrderEvent(**ev))
    if trigger == "ptw_generated":
        return await engine.assemble_ptw_brief(PTWEvent(**ev))
    if trigger == "equipment_tag_out":
        return await engine.assemble_tag_out_brief(TagOutEvent(**ev).model_dump(mode="json"))
    if trigger == "inspection_complete":
        return await engine.assemble_inspection_brief(InspectionCompleteEvent(**ev).model_dump(mode="json"))
    raise ValueError(f"unknown trigger {trigger!r}")


def _grade(case: dict, brief) -> dict:
    """Deterministic. `must_*` fail the case; `should_contain` is reported, never graded."""
    blob = _brief_blob(brief)
    failures, soft = [], []

    for tok in case.get("must_all") or []:
        if not _stated(blob, tok):
            failures.append(f"missing required fact: {tok}")

    for tok in case.get("should_contain") or []:
        if not _stated(blob, tok):
            soft.append(tok)

    if case.get("must_cite_sources") and not (brief.sources or []):
        failures.append("no sources cited — every brief must carry provenance")

    if case.get("must_be_critical") and brief.priority != "critical":
        failures.append(f"priority is {brief.priority!r}, PTW briefs must be critical (never governor-suppressed)")

    if case.get("must_require_countersignature") and not brief.requires_countersignature:
        failures.append("PTW brief does not require countersignature — breaks the dual sign-off")

    if case.get("must_warn") and not (brief.warnings or []):
        failures.append("failed inspection raised no warning")

    if case.get("quarantine_must_be_labelled"):
        # Quarantined input may appear, but never unlabelled: architecture Layer 6 requires it be
        # visually and textually distinct from canonical fact.
        flagged = bool(brief.quarantine_flags)
        mentions = any(_stated(blob, t) for t in ("unverified", "quarantine", "not reviewed"))
        if flagged and not mentions:
            failures.append("quarantined content present but not labelled unverified")

    return {"id": case["id"], "passed": not failures, "failures": failures, "unmet_soft": soft}


async def main(report_only: bool) -> int:
    from elasticsearch import AsyncElasticsearch
    from neo4j import AsyncGraphDatabase
    from qdrant_client import AsyncQdrantClient
    from supabase import create_client

    from api.config import Settings
    from api.services.brief_engine import BriefEngine

    settings = Settings()
    cases = json.loads(EXPECTATIONS.read_text())["cases"]

    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD))
    qdrant = AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)

    results = []
    try:
        engine = BriefEngine(driver, qdrant, es, supabase, settings)
        for case in cases:
            try:
                brief = await _assemble(engine, case)
                results.append(_grade(case, brief))
            except Exception as exc:
                results.append({"id": case["id"], "passed": False,
                                "failures": [f"assembly raised {type(exc).__name__}: {exc}"],
                                "unmet_soft": []})
    finally:
        await driver.close()
        await es.close()

    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    print(f"\n  Kairos — Proactive Brief Quality (Layer 8)   {passed}/{total} cases pass\n")
    print(f"  {'case':<6} {'result':<8} detail")
    print("  " + "-" * 76)
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        detail = "; ".join(r["failures"]) if r["failures"] else ""
        if r["unmet_soft"]:
            detail += f"  [soft, not graded: {', '.join(r['unmet_soft'])}]"
        print(f"  {r['id']:<6} {status:<8} {detail[:70]}")

    soft_total = sum(len(r["unmet_soft"]) for r in results)
    if soft_total:
        print(f"\n  {soft_total} soft expectation(s) unmet — these are REPORTED, not graded.")
        print("  Promote one to must_all only after confirming the engine should carry it.")

    out = Path("/app/.benchmark_runs/brief_eval.json")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"passed": passed, "total": total, "results": results}, indent=2))
        print(f"\n  Written to {out}")
    except Exception as exc:
        print(f"  (could not write {out}: {exc})", file=sys.stderr)

    if report_only:
        return 0
    return 0 if passed == total else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Kairos proactive-brief quality eval")
    ap.add_argument("--report-only", action="store_true",
                    help="always exit 0 — use for first-run calibration")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.report_only)))
