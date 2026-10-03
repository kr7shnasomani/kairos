"""
Model Validation Worker — Layer 0: Rolling validation corpus and model gate.
Evaluates NER model accuracy against human-verified ground truth entities.
"""

import asyncio
import sys

sys.path.insert(0, "/app")

from collections import Counter, defaultdict
from typing import Any

import structlog

from workers.celery_app import celery_app

log = structlog.get_logger(__name__)


@celery_app.task(
    queue="validation",
    name="workers.model_validation.run_model_gate",
    acks_late=True,
    # 600/540 was calibrated when almost every NER call failed fast on a 429, so a full run took
    # ~2.5 min. Once the calls actually reach the model each one costs tens of seconds, and two
    # consecutive runs were killed mid-flight by SoftTimeLimitExceeded — writing NO history entry
    # at all, which is worse than recording a degraded one. The work legitimately takes this long;
    # the limit was measuring a broken run. Celery still hard-kills at `time_limit`, and the task
    # is admin-triggered rather than automatic, so a long slot is not contended.
    time_limit=1860,
    soft_time_limit=1800,
)
def run_model_gate(model_name: str) -> dict[str, Any]:
    from api.services.http import run_with_client
    return run_with_client(_run_gate(model_name))


async def _run_gate(model_name: str) -> dict[str, Any]:
    from elasticsearch import AsyncElasticsearch
    from supabase import create_client

    from api.config import Settings
    from api.services.ner import FallbackCountingNER, NERService

    settings = Settings()
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

    es_kwargs: dict = {"hosts": [settings.ELASTICSEARCH_URL]}
    if settings.ELASTICSEARCH_USERNAME:
        es_kwargs["basic_auth"] = (settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD)
    es = AsyncElasticsearch(**es_kwargs)

    # Wrapped so the run can report whether it actually reached the model — a gate that cannot
    # distinguish a model score from a regex-fallback score is not a gate. See status.md #15.
    ner = FallbackCountingNER(NERService(model=model_name))  # the gate must score the model it was asked about
    try:
        corpus_result = await asyncio.to_thread(
            lambda: supabase.table("validation_corpus").select("*").execute()
        )
        corpus = corpus_result.data or []

        if not corpus:
            return {
                "model_name": model_name,
                "corpus_size": 0,
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "passed": False,
                "by_entity_type": {},
                "error": "empty corpus",
            }

        run_cache: dict[str, list[dict[str, Any]]] = {}
        metrics = await evaluate(ner, es, corpus, settings, cache=run_cache)

        # Per-asset-class scoring (Layer 0). The architecture is explicit: a model that passes on
        # global metrics but fails on a specific class must be blocked *for that class*. A single
        # global F1 cannot express that, so partition the corpus and score each class.
        #
        # Partitioning costs no extra model calls *because* `run_cache` is shared across every
        # evaluate() call below. Without it each document is extracted twice — this comment
        # asserted the invariant before anything enforced it (fixed 2026-08-22).
        class_map = await _document_asset_classes(supabase, [row["document_id"] for row in corpus])
        partitions: dict[str, list[dict[str, Any]]] = {}
        for row in corpus:
            partitions.setdefault(class_map.get(row["document_id"], "unclassified"), []).append(row)

        by_asset_class: dict[str, Any] = {}
        for asset_class, subset in partitions.items():
            sub_metrics = await evaluate(ner, es, subset, settings, cache=run_cache)
            by_asset_class[asset_class] = {
                "precision": sub_metrics["precision"],
                "recall": sub_metrics["recall"],
                "f1": sub_metrics["f1"],
                "corpus_size": len(subset),
            }

        # Per-document-type scoring — the cut the problem statement asks for. Same partition
        # mechanic as asset class, and free in model calls because `run_cache` is shared.
        type_map = await _document_types(supabase, [row["document_id"] for row in corpus])
        type_partitions: dict[str, list[dict[str, Any]]] = {}
        for row in corpus:
            type_partitions.setdefault(type_map.get(row["document_id"], "unknown"), []).append(row)

        by_document_type: dict[str, Any] = {}
        for doc_type, subset in type_partitions.items():
            sub_metrics = await evaluate(ner, es, subset, settings, cache=run_cache)
            by_document_type[doc_type] = {
                "precision": sub_metrics["precision"],
                "recall": sub_metrics["recall"],
                "f1": sub_metrics["f1"],
                "corpus_size": len(subset),
                "scored_labels": sub_metrics["scored_labels"],
            }

        # Incumbent baseline: the most recent run that actually reached the model. A SUSPECT run
        # scores the regex fallback, so letting one become the baseline silently lowers the bar
        # every later run is compared against.
        #
        # Filtered in Python, NOT in PostgREST: `.neq("details->>validity", "SUSPECT")` would drop
        # every row, because legacy entries have no `validity` key at all and `NULL != 'x'` is NULL
        # rather than TRUE. Runs predating this field are treated as unusable rather than assumed
        # good — the run that exposed this had 52/55 extractions fall back.
        baseline_result = await asyncio.to_thread(
            lambda: supabase.table("audit_log")
            .select("details")
            .eq("action", "model_gate_result")
            .order("timestamp", desc=True)
            .limit(20)
            .execute()
        )
        baseline_result.data = _latest_valid_baseline(baseline_result.data)
        passed = True
        regressed_classes: list[str] = []
        if baseline_result.data:
            baseline_details = baseline_result.data[0].get("details", {}) or {}
            baseline_types = baseline_details.get("by_entity_type", {})
            for etype, scores in metrics["by_entity_type"].items():
                if scores["f1"] < baseline_types.get(etype, {}).get("f1", 0.0):
                    passed = False
                    break

            # A per-class regression blocks that class even when the global score holds.
            baseline_classes = baseline_details.get("by_asset_class", {})
            for asset_class, scores in by_asset_class.items():
                prior = baseline_classes.get(asset_class, {}).get("f1")
                if prior is not None and scores["f1"] < prior:
                    regressed_classes.append(asset_class)

        result: dict[str, Any] = {
            "model_name": model_name,
            "corpus_size": len(corpus),
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
            "passed": passed,
            "by_entity_type": metrics["by_entity_type"],
            "by_asset_class": by_asset_class,
            "by_document_type": by_document_type,
            "regressed_asset_classes": regressed_classes,
            # How much of the corpus the score above actually covers. `corpus_size` is the row
            # count; `scored_labels` is what was measurable. They differ when the corpus carries
            # labels outside the extractor's taxonomy.
            "scored_labels": metrics["scored_labels"],
            "unscoreable_labels": metrics["unscoreable_labels"],
            "unscoreable_by_type": metrics["unscoreable_by_type"],
            # Orthogonal to `passed`, matching run_model_validation.py: `passed` means "no
            # regression against the baseline", `validity` means "was this measurable at all".
            "extraction_paths": dict(ner.paths),
            "fallback_extractions": ner.fallback_count,
            "validity": ner.validity,
            # Report-only unless explicitly enabled — see Settings.MODEL_GATE_ENFORCE.
            "enforcement": "enforced" if settings.MODEL_GATE_ENFORCE else "advisory_only",
            "blocked_asset_classes": regressed_classes if settings.MODEL_GATE_ENFORCE else [],
        }

        await asyncio.to_thread(
            lambda: supabase.table("audit_log").insert({
                "action": "model_gate_result",
                "entity_type": "model_gate",
                "entity_id": model_name,
                "performed_by": "system",
                "details": result,
            }).execute()
        )

        log.info("model_gate.complete", model_name=model_name, f1=result["f1"], passed=passed)
        return result
    finally:
        await es.close()


def _span_match(pred_text: str, gt_text_lower: str) -> bool:
    """Partial-match: predicted and ground-truth spans overlap (one contains the other),
    case-insensitive. Standard relaxed NER scoring; `gt_text_lower` is already lowercased.
    The contained side must be >=4 chars so a stray "18" can't match "PG-18"."""
    a = pred_text.strip().lower()
    if not a:
        return False
    if a == gt_text_lower:
        return True
    shorter, longer = (a, gt_text_lower) if len(a) <= len(gt_text_lower) else (gt_text_lower, a)
    return len(shorter) >= 4 and shorter in longer


def _latest_valid_baseline(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Newest run that actually reached the model, as a 0- or 1-element list.

    A SUSPECT run scored the regex fallback, so adopting one as the baseline silently lowers
    the bar for every later comparison. Rows written before `validity` existed carry no such
    key and are treated as unusable rather than assumed good — the run that motivated this had
    52 of 55 extractions fall back while still recording `passed: true`.

    Returning an empty list means "no baseline", which the caller already handles by leaving
    `passed = True` — the same thing it did on a fresh install.
    """
    return [r for r in (rows or []) if ((r.get("details") or {}).get("validity") == "VALID")][:1]


async def evaluate(
    ner: Any,
    es: Any,
    corpus: list[dict[str, Any]],
    settings: Any,
    cache: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Run NER over corpus documents and compute precision/recall/F1 per entity type.

    `cache` is a run-scoped document -> entities map shared across every call in one gate run.
    Without it each document is extracted **twice** — once by the global pass and again by its
    asset-class pass — which is what the partitioning comment above wrongly claimed it avoided.
    Sharing it halves the model calls and, more importantly, makes the global and per-class
    scores derive from the *same* extraction instead of two independent ones that can disagree.
    """
    doc_ids = list({row["document_id"] for row in corpus})

    doc_texts: dict[str, str] = {}
    for doc_id in doc_ids:
        try:
            resp = await es.search(
                index=settings.ELASTICSEARCH_INDEX_DOCUMENTS,
                body={
                    "query": {"term": {"document_id": doc_id}},
                    "_source": ["content", "text"],
                    "size": 1,
                },
            )
            hits = resp["hits"]["hits"]
            if hits:
                src = hits[0]["_source"]
                doc_texts[doc_id] = src.get("content") or src.get("text") or ""
        except Exception as exc:
            log.warning("model_gate.doc_fetch_failed", doc_id=doc_id, error=str(exc))

    # Run NER once per unique document (not per corpus row) — fewer model calls and no intra-run
    # variance from re-extracting the same doc, so a single flaky call can't spuriously miss.
    doc_predictions: dict[str, list[dict[str, Any]]] = cache if cache is not None else {}
    for doc_id in doc_ids:
        if doc_id in doc_predictions:  # already extracted earlier in this run
            continue
        text = doc_texts.get(doc_id)
        if text is None:  # doc not indexed — score each row against its own entity text as a fallback
            continue
        try:
            ner_result = await ner.extract_entities(text)
            doc_predictions[doc_id] = ner_result.get("entities", []) if ner_result else []
        except Exception as exc:
            log.warning("model_gate.ner_failed", doc_id=doc_id, error=str(exc))
            doc_predictions[doc_id] = []

    by_type: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})

    # Ground-truth labels the extractor is never asked to produce cannot be scored against it.
    # Counting them booked a false negative on the unrequested type AND a false positive on
    # whatever type the model assigned the same span — one taxonomy mismatch penalised twice.
    # They are excluded and reported, so the score describes the model rather than the gap
    # between the corpus's label space and the prompt's.
    unscoreable: Counter = Counter()
    from api.services.ner import NER_ENTITY_TYPES  # lazy: Celery workers import api inside the body

    for row in corpus:
        if row["entity_type"] not in NER_ENTITY_TYPES:
            unscoreable[row["entity_type"]] += 1
            continue
        doc_id = row["document_id"]
        gt_text = row["entity_text"].strip().lower()
        gt_type = row["entity_type"]

        if doc_id in doc_predictions:
            predicted = doc_predictions[doc_id]
        else:  # unindexed doc: extract from the entity text itself
            # Cached on the same run-scoped map under a separate key space. This path is the one
            # that dominates when documents are missing from Elasticsearch, and it was re-running
            # for every partition pass as well as the global one.
            row_key = f"row::{row['entity_text']}"
            if row_key in doc_predictions:
                predicted = doc_predictions[row_key]
            else:
                try:
                    ner_result = await ner.extract_entities(row["entity_text"])
                    predicted = ner_result.get("entities", []) if ner_result else []
                except Exception as exc:
                    log.warning("model_gate.ner_failed", doc_id=doc_id, error=str(exc))
                    predicted = []
                doc_predictions[row_key] = predicted

        # Partial (span-overlap) match — the standard for NER eval: a prediction of
        # "FISCHER PUMPS LTD." credits the ground-truth "Fischer". Exact whole-string equality
        # under-counts multi-word entities the model extracts with a broader span.
        predicted_types_for_text = {
            e["entity_type"]
            for e in predicted
            if _span_match(e.get("text", ""), gt_text)
        }

        if gt_type in predicted_types_for_text:
            by_type[gt_type]["tp"] += 1
        else:
            by_type[gt_type]["fn"] += 1

        for e in predicted:
            if _span_match(e.get("text", ""), gt_text) and e.get("entity_type") != gt_type:
                by_type[e["entity_type"]]["fp"] += 1

    entity_metrics: dict[str, dict[str, Any]] = {}
    total_tp = total_fp = total_fn = 0

    for etype, counts in by_type.items():
        tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
        total_tp += tp
        total_fp += fp
        total_fn += fn
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        entity_metrics[etype] = {
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "count": tp + fn,
        }

    overall_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1 = 2 * overall_p * overall_r / (overall_p + overall_r) if (overall_p + overall_r) > 0 else 0.0

    return {
        "precision": round(overall_p, 4),
        "recall": round(overall_r, 4),
        "f1": round(overall_f1, 4),
        "by_entity_type": entity_metrics,
        # Denominator transparency: a score is not interpretable without knowing how much of the
        # corpus it covers. `unscoreable_labels` is a corpus/prompt taxonomy gap to close, not a
        # model failure — quote `scored_labels` alongside the F1.
        "scored_labels": total_tp + total_fn,
        "unscoreable_labels": sum(unscoreable.values()),
        "unscoreable_by_type": dict(unscoreable),
    }


async def _document_types(supabase, document_ids: list[str]) -> dict[str, str]:
    """Map each corpus document to its `documents.document_type`.

    The problem statement asks for extraction accuracy per **document type**; the gate previously
    reported per entity type and per asset class only. It is a one-hop lookup where the asset-class
    cut needs two, and because every `evaluate()` call shares the run's extraction cache, adding
    this partition costs **zero** extra model calls.

    Documents with no row fall into "unknown" rather than being dropped — excluding them would
    quietly shrink the corpus the gate reports on.
    """
    unique_ids = list({d for d in document_ids if d})
    if not unique_ids:
        return {}

    docs = await asyncio.to_thread(
        lambda: supabase.table("documents")
        .select("document_id, document_type")
        .in_("document_id", unique_ids)
        .execute()
    )
    return {r["document_id"]: r.get("document_type") or "unknown" for r in (docs.data or [])}


async def _document_asset_classes(supabase, document_ids: list[str]) -> dict[str, str]:
    """
    Map each corpus document to the equipment class of the asset it is linked to.

    `documents -> document_asset_links -> assets.equipment_class`. Documents with no asset link
    fall into "unclassified" rather than being dropped: excluding them would quietly shrink the
    corpus a gate reports on, which is the kind of silent narrowing Layer 0 exists to prevent.
    """
    unique_ids = list({d for d in document_ids if d})
    if not unique_ids:
        return {}

    links = await asyncio.to_thread(
        lambda: supabase.table("document_asset_links")
        .select("document_id, asset_id")
        .in_("document_id", unique_ids)
        .execute()
    )
    doc_to_asset = {r["document_id"]: r["asset_id"] for r in (links.data or [])}
    if not doc_to_asset:
        return {}

    assets = await asyncio.to_thread(
        lambda: supabase.table("assets")
        .select("asset_id, equipment_class")
        .in_("asset_id", list(set(doc_to_asset.values())))
        .execute()
    )
    asset_to_class = {r["asset_id"]: r.get("equipment_class") or "unclassified" for r in (assets.data or [])}
    return {doc: asset_to_class.get(asset, "unclassified") for doc, asset in doc_to_asset.items()}
