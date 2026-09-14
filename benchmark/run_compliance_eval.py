#!/usr/bin/env python3
"""
Kairos — compliance gap-detection accuracy.

Measures the "compliance gap detection accuracy" evaluation criterion, which previously
had no number attached to it.

METHOD
  Ground truth is derived from the golden dataset manifest (which document types are
  actually linked to which asset — see backend/scripts/load_demo_dataset.py) crossed with
  each clause's declared evidence requirement (`requires_document_type`, seeded by
  backend/scripts/seed_regulations.py).

  That truth table is built independently of the Cypher under test. The endpoint answers
  from Neo4j KNOWLEDGE_EDGEs, so a disagreement means real breakage somewhere in
  ingestion → asset linking → equipment-class applicability → the gap query. This is an
  end-to-end measurement, not a restatement of the query.

  Expected status per applicable (clause, asset) pair:
    gap                 asset has no document of the clause's required type
    unverified_evidence asset has one, but no human has verified the edge
  The golden dataset contains no verified edges (verification is a manual promotion), so
  "has the document" resolves to unverified_evidence rather than covered.

LIMITATIONS (state these alongside any number this prints)
  1. This scores whether the system correctly finds the evidence it was told to look for.
     It does NOT validate that the clause → document-type mapping is the semantically right
     reading of each regulation; that mapping is a human judgement encoded in the seed.

  2. ASSET_DOC_TYPES below is the loader's *declared* asset→document mapping. The live graph
     legitimately holds more links than that: the extraction pipeline also links a document
     to any asset tag it finds in the text. So a disagreement can mean either a real system
     error OR an extraction-derived link the manifest does not know about — check the graph
     before calling it a bug. (Verified case: EQ-103 is declared with no documents here, but
     the graph correctly links it to an oem_manual and an inspection_report found by
     extraction, so `unverified_evidence` was the right answer and the ground truth was the
     wrong one.)

     Do NOT "fix" this by copying the system's own output into the truth table — that
     destroys the independence that makes this measurement worth anything.

USAGE
  docker compose exec kairos-backend-api python /app/benchmark/run_compliance_eval.py
"""

import argparse
import asyncio
import os
import sys

import httpx

API = os.getenv("API_BASE_URL", "http://localhost:8000")
KEY = os.getenv("INTERNAL_API_KEY", "kairos-internal-dev-key")

# --- Ground truth -----------------------------------------------------------------
# Equipment class per asset, after the loader's normalisation of asset_registry.csv
# ("Rotating - Centrifugal Pump" -> "rotating_centrifugal_pump").
ASSET_CLASS = {
    "EQ-101": "rotating_centrifugal_pump",
    "EQ-102": "rotating_centrifugal_pump",
    "EQ-103": "rotating_centrifugal_pump",
    "V-247": "valve_gate",
    "XV-203": "valve_isolation",
    "XV-204": "valve_isolation",
    "PG-18": "instrument_bypass",
    "HE-301": "he-3xx_series",
    "HE-302": "he-3xx_series",
    "HE-303": "he-3xx_series",
}

# Document types linked to each asset by load_demo_dataset.py DOCS.
ASSET_DOC_TYPES = {
    "EQ-101": {"oem_manual", "inspection_report"},
    "EQ-102": {"inspection_report"},
    "EQ-103": set(),
    "V-247": {"ptw", "pid_drawing"},
    "XV-203": {"inspection_report"},
    "XV-204": set(),
    "PG-18": set(),
    "HE-301": {"oem_manual", "procedure", "inspection_report"},
    "HE-302": {"procedure", "inspection_report"},
    "HE-303": {"procedure"},
}

# (clause_id, applies_to_equipment_class, requires_document_type) — mirrors seed_regulations.py.
CLAUSES = [
    ("4.1.1", "pump", "procedure"),
    ("4.1.2", "pump", "inspection_report"),
    ("4.2.1", "vessel", "inspection_report"),
    ("4.2.2", "vessel", "oem_manual"),
    ("4.3.1", "valve", "procedure"),
    ("4.3.2", "valve", "inspection_report"),
    ("5.1.1", "compressor", "procedure"),
    ("5.1.2", "compressor", "procedure"),
    ("8.1.1", None, "procedure"),
    ("8.2.1", None, "procedure"),
    ("9.1.1", None, "procedure"),
    ("10.2.1", None, "procedure"),
]


def applies(reg_class: str | None, asset_class: str) -> bool:
    """Mirrors the applicability predicate in the gap Cypher."""
    if reg_class is None:
        return True
    return reg_class == asset_class or reg_class in asset_class or asset_class in reg_class


def expected_findings() -> dict[tuple[str, str], str]:
    truth: dict[tuple[str, str], str] = {}
    for clause_id, reg_class, required in CLAUSES:
        for asset_id, asset_class in ASSET_CLASS.items():
            if not applies(reg_class, asset_class):
                continue
            has_evidence = required in ASSET_DOC_TYPES[asset_id]
            truth[(clause_id, asset_id)] = "unverified_evidence" if has_evidence else "gap"
    return truth


# --- Scoring ----------------------------------------------------------------------

async def main(max_false_negatives: int = 0) -> int:
    truth = expected_findings()

    # Generous: the gap query is O(clauses × assets) with a subquery per pair, and Aura
    # round-trips are slow enough that 30 s is not sufficient even at demo scale.
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
        resp = await client.get(
            f"{API}/compliance/gaps",
            headers={"Authorization": f"Bearer {KEY}"},
            params={"limit": 500},
        )
        if resp.status_code != 200:
            print(f"FAIL: GET /compliance/gaps -> HTTP {resp.status_code}: {resp.text[:300]}")
            return 1
        body = resp.json()

    reported = {(i["clause_id"], i["asset_id"]): i["status"] for i in body.get("items", [])}

    exp_gaps = {k for k, v in truth.items() if v == "gap"}
    got_gaps = {k for k, v in reported.items() if v == "gap"}

    tp = sorted(exp_gaps & got_gaps)
    fp = sorted(got_gaps - exp_gaps)
    fn = sorted(exp_gaps - got_gaps)

    precision = len(tp) / (len(tp) + len(fp)) if (tp or fp) else 0.0
    recall = len(tp) / (len(tp) + len(fn)) if (tp or fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # Status agreement across every applicable pair, gap and unverified alike.
    status_checked = [k for k in truth if k in reported or truth[k] != "covered"]
    agree = sum(1 for k in status_checked if reported.get(k, "covered") == truth[k])

    print("  Kairos — Compliance Gap Detection Accuracy")
    print("  " + "=" * 72)
    print(f"  Applicable (clause × asset) pairs in ground truth: {len(truth)}")
    print(f"  Findings returned by /compliance/gaps:             {len(reported)}")
    print(f"    of which gap:                 {len(got_gaps)}")
    print(f"    of which unverified_evidence: {len(reported) - len(got_gaps)}")
    print()
    print(f"  Gap detection — precision {precision:.3f}  recall {recall:.3f}  F1 {f1:.3f}")
    print(f"    true positives  {len(tp)}")
    print(f"    false positives {len(fp)}   (flagged a gap that the dataset satisfies)")
    print(f"    false negatives {len(fn)}   (missed a real gap)")
    print()
    print(f"  Full status agreement: {agree}/{len(status_checked)} pairs")

    if fp:
        print("\n  False positives:")
        for clause_id, asset_id in fp[:10]:
            print(f"    {clause_id:<8} {asset_id:<8} expected {truth.get((clause_id, asset_id), 'not-applicable')}")
    if fn:
        print("\n  False negatives:")
        for clause_id, asset_id in fn[:10]:
            print(f"    {clause_id:<8} {asset_id:<8} reported {reported.get((clause_id, asset_id), 'nothing')}")

    print()
    print("  Note: measures retrieval of the evidence each clause declares it requires.")
    print("  It does not validate that the clause -> document-type mapping is the correct")
    print("  reading of the regulation — that mapping is a human judgement in the seed.")

    # A false negative is a missed compliance gap — the failure mode that matters.
    #
    # `--max-false-negatives` exists so CI can gate on this without going permanently red on a
    # KNOWN ground-truth artefact: 4.1.2/EQ-103 is declared with no documents in the loader's
    # mapping, but the graph correctly links EQ-103 to an oem_manual and an inspection_report,
    # so `unverified_evidence` is the right answer and the truth table is wrong. That is
    # documented rather than "fixed" by editing the truth table to match the system's output,
    # which would destroy the independence the measurement depends on.
    #
    # False POSITIVES are never tolerated at any setting — flagging a gap the dataset satisfies
    # is the claim this harness exists to defend ("precision 1.000, 0 false positives").
    if fp:
        print(f"\n  GATE FAIL: {len(fp)} false positive(s) — a gap was reported that the dataset satisfies.")
        return 1
    if len(fn) > max_false_negatives:
        print(f"\n  GATE FAIL: {len(fn)} false negative(s) exceeds the allowed {max_false_negatives}.")
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Compliance gap-detection accuracy")
    ap.add_argument("--max-false-negatives", type=int, default=0,
                    help="allowed false negatives before failing (CI pins the known truth-table artefact at 1)")
    _args = ap.parse_args()
    sys.exit(asyncio.run(main(max_false_negatives=_args.max_false_negatives)))
