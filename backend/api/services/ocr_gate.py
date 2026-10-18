"""
OCR accuracy scoring — the Layer 0 gate's extension to the OCR artifact.

`ARCHITECTURE.md` Layer 0: "Entity extraction is the gated artifact today; OCR, synthesis, and
entity linking are the extension path along the same interface."

WHY NOT CHARACTER ERROR RATE
  CER is the textbook OCR metric and it is the wrong one here. It weights every character equally,
  so a run that mangles whitespace and headers but preserves every number scores badly, while a
  run that reads "16.2 bar" as "18.5 bar" — the single most dangerous error this system can make,
  and a real pressure limit in this corpus — barely moves it.

  What matters industrially is whether the **operationally salient tokens survive**: asset tags,
  measured values with units, standards references, document ids, dates. Those are the things a
  technician acts on and the things the graph links. So the metric is recall over those tokens.

  This is the same principle as the model gate excluding ground truth outside the extractor's
  taxonomy: score what the artifact is actually for.

GROUND TRUTH ALREADY EXISTS
  It was claimed the corpus has no labelled OCR ground truth. `dataset/00_Reference/
  dataset_manifest.csv` declares three pairings **by design**:
    file 20 scanned_oem_bulletin_degraded.png -> "Same content as file 6"
    file 21 scanned_inspection_degraded.png   -> "Same content as file 12"
    files 22/23 handwritten_*.png             -> file 24 shift_log.txt, "same 2 events"
  The clean sibling's extracted text is the reference. No new labelling was required.

WHAT THIS CANNOT TELL YOU
  Token recall is not transcription quality: an OCR pass that emits the right numbers inside
  garbled prose scores well here and would still be unusable for retrieval. It is the safety-
  relevant direction, not a complete picture. Pair it with a human read of one sample.
"""

import re
from typing import Any

# Operationally salient token classes. Each is something a technician acts on, and each is
# something an OCR error silently corrupts.
_PATTERNS: dict[str, re.Pattern] = {
    # EQ-101, XV-203, HE-301, PG-18, FSL-2240B
    "asset_tag": re.compile(r"\b[A-Z]{1,4}-\d{2,4}[A-Z]?\b"),
    # 16.2 bar, 4.1 mm/s, 82 degrees, 110%
    "measurement": re.compile(
        r"\b\d+(?:\.\d+)?\s?(?:bar|psi|kpa|mpa|mm/s|mm|°c|degc|degrees?|hz|rpm|%|kv|amp|a)\b",
        re.IGNORECASE,
    ),
    # OISD-117, ISO 45001, FP-SB-2025-04, MHT-PB-2026-11
    "reference": re.compile(r"\b(?:[A-Z]{2,5}-){1,3}\d{2,4}(?:-\d{2,4})?\b"),
    # 15-Jan-2025, 2025-04-01, 24-Jun-2026
    "date": re.compile(r"\b(?:\d{1,2}-[A-Za-z]{3}-\d{4}|\d{4}-\d{2}-\d{2})\b"),
}


def salient_tokens(text: str) -> dict[str, set[str]]:
    """Operationally salient tokens in a document, grouped by class.

    Upper-cased for comparison: OCR case errors on a tag are a nuisance, not a safety event, and
    counting them as misses would bury the errors that matter.
    """
    out: dict[str, set[str]] = {}
    for name, pat in _PATTERNS.items():
        out[name] = {m.group(0).upper().strip() for m in pat.finditer(text or "")}
    return out


def reference_entry(reference_text: str, entry_date: str | None) -> str:
    """The one `---`-separated entry of a multi-entry reference that a scan reproduces.

    `shift_log.txt` holds both handwritten notes' events plus a later handover entry, and each note
    shows exactly one of them (manifest rows 22 and 23). Scored against the whole log, a perfect
    transcription of one note could recall at most about a third of the tokens. The entry is
    declared per image, never chosen by best overlap, so a misread date cannot pick a kinder
    reference. With no declared date, or no entry carrying it, the whole reference is used.
    """
    if not entry_date:
        return reference_text
    for block in re.split(r"^\s*-{3,}\s*$", reference_text or "", flags=re.MULTILINE):
        if re.search(rf"^\s*Entry:\s*{re.escape(entry_date)}\b", block, re.MULTILINE | re.IGNORECASE):
            return block
    return reference_text


def score_ocr(reference_text: str, ocr_text: str) -> dict[str, Any]:
    """Recall of salient tokens from `reference_text` in `ocr_text`.

    Recall, deliberately, not F1: an OCR pass that emits *extra* tokens is noisy, but an OCR pass
    that **drops a pressure limit** is the failure this gate exists to catch. Precision would let
    a run trade away a real number for a tidier output and still score well.
    """
    ref = salient_tokens(reference_text)
    got = salient_tokens(ocr_text)

    per_class: dict[str, Any] = {}
    total_expected = total_found = 0
    missed: list[str] = []

    for name in _PATTERNS:
        expected, found = ref[name], ref[name] & got[name]
        total_expected += len(expected)
        total_found += len(found)
        missed.extend(sorted(expected - found))
        per_class[name] = {
            "expected": len(expected),
            "recovered": len(found),
            "recall": round(len(found) / len(expected), 4) if expected else None,
        }

    return {
        "salient_recall": round(total_found / total_expected, 4) if total_expected else None,
        "expected_tokens": total_expected,
        "recovered_tokens": total_found,
        "missed_tokens": missed[:40],
        "by_class": per_class,
        # A reference with no salient tokens cannot score the OCR — say so rather than
        # reporting a vacuous 1.0, which is how a broken pairing would look like a pass.
        "scoreable": total_expected > 0,
    }
