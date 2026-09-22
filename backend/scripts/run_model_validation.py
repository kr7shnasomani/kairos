"""
CLI: run NER model validation against the rolling validation corpus.

Usage (inside Docker):
    python scripts/run_model_validation.py --model-name meta/llama-3.2-11b-vision-instruct
    python scripts/run_model_validation.py --model-name <m> --no-persist   # don't write audit_log

Outputs per-entity-type precision, recall, F1 and overall metrics to stdout.

TWO THINGS THIS SCRIPT REPORTS BEYOND THE RAW F1
  1. Fallback count. `NERService.extract_entities` degrades to a regex last resort when the model
     call fails or its reply will not parse, and that resort only matches ASSET_TAG. Those documents
     then contribute *regex* output to a score labelled with the model's name — the same
     "authoritative-looking F1 attributed to a model that was never invoked" defect the model-gate
     already had once, surviving as a per-document failure mode. A run with any fallback is marked
     SUSPECT and its F1 is a ceiling, not a measurement.
  2. Persistence. Results are written to `audit_log` as `model_gate_result`, the same row shape the
     Celery gate writes, so a CLI run reaches /governance/model-gate instead of vanishing at stdout.
"""

import argparse
import asyncio
import json
import sys

sys.path.insert(0, "/app")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NER model validation against validation_corpus")
    parser.add_argument("--model-name", required=True, help="Model identifier label for this run")
    parser.add_argument("--no-persist", action="store_true",
                        help="skip the audit_log write (dry run / experimenting)")
    args = parser.parse_args()

    result = asyncio.run(_run(args.model_name, persist=not args.no_persist))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("passed") else 1)


async def _run(model_name: str, persist: bool = True) -> dict:
    from elasticsearch import AsyncElasticsearch
    from supabase import create_client

    from api.config import Settings
    from api.services.ner import FallbackCountingNER, NERService
    from workers.model_validation import evaluate

    settings = Settings()
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)

    # the gate must score the model it was asked about; the wrapper records which path answered
    ner = FallbackCountingNER(NERService(model=model_name))
    try:
        corpus_result = supabase.table("validation_corpus").select("*").execute()
        corpus = corpus_result.data or []

        if not corpus:
            print("WARNING: validation_corpus is empty — no metrics to compute", file=sys.stderr)
            return {"model_name": model_name, "corpus_size": 0, "passed": False}

        print(f"Evaluating {len(corpus)} corpus entries for model: {model_name}", file=sys.stderr)
        metrics = await evaluate(ner, es, corpus, settings)

        # Regression check against the incumbent, mirroring workers/model_validation.py.
        # Fetched BEFORE _persist so the run cannot be compared against itself.
        #
        # Without this, `passed` was only ever set on the empty-corpus path, so
        # `result.get("passed")` was None on every real run and main() always exited 1 — a gate
        # that fails a *passing* model cannot be wired into a deploy, which is why it never was.
        # No baseline (first ever run) = pass: that run establishes the baseline.
        passed = True
        regressed: list[str] = []
        try:
            baseline_result = await asyncio.to_thread(
                lambda: supabase.table("audit_log")
                .select("details")
                .eq("action", "model_gate_result")
                .order("timestamp", desc=True)
                .limit(1)
                .execute()
            )
            if baseline_result.data:
                baseline_types = (baseline_result.data[0].get("details") or {}).get("by_entity_type", {})
                for etype, scores in metrics["by_entity_type"].items():
                    prior = baseline_types.get(etype, {}).get("f1")
                    if prior is not None and scores["f1"] < prior:
                        regressed.append(etype)
                passed = not regressed
        except Exception as exc:  # noqa: BLE001
            # An unreachable baseline must not read as "passed" — that would wave through a
            # regression on the one check whose whole job is to catch it.
            print(f"ERROR: baseline lookup failed ({type(exc).__name__}: {exc}) — failing closed",
                  file=sys.stderr)
            passed = False

        fallbacks = ner.fallback_count
        result = {
            "model_name": model_name,
            "corpus_size": len(corpus),
            **metrics,
            "passed": passed,
            "regressed_entity_types": regressed,
            "extraction_paths": dict(ner.paths),
            "fallback_extractions": fallbacks,
            # A fallback contributes regex output (ASSET_TAG only) to a model-attributed score, so
            # the F1 above is an upper bound rather than a measurement of this model.
            "validity": "SUSPECT" if fallbacks else "VALID",
        }

        if fallbacks:
            print(
                f"WARNING: {fallbacks}/{sum(ner.paths.values())} extraction(s) fell back to a "
                f"non-model path {dict(ner.paths)} — F1 is a CEILING, not a measurement.",
                file=sys.stderr,
            )

        if persist:
            await _persist(supabase, model_name, result)

        return result
    finally:
        await es.close()


async def _persist(supabase, model_name: str, result: dict) -> None:
    """
    Write the run to `audit_log` in the same shape `workers/model_validation.py` uses, so CLI runs
    and Celery-triggered runs land in one series on /governance/model-gate. Append-only; never updates
    or deletes. A persistence failure must not discard an otherwise-good measurement, so it warns
    rather than raising — the metrics are already on stdout by then.
    """
    try:
        await asyncio.to_thread(
            lambda: supabase.table("audit_log").insert({
                "action": "model_gate_result",
                "entity_type": "model_gate",
                "entity_id": model_name,
                "performed_by": "cli",  # distinguishes these from the worker's "system" rows
                "details": result,
            }).execute()
        )
        print(f"Persisted to audit_log (model_gate_result / {model_name})", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - reporting beats losing the run
        print(f"WARNING: audit_log write failed ({type(exc).__name__}: {exc})", file=sys.stderr)


if __name__ == "__main__":
    main()
