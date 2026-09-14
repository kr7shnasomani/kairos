# Kairos Demo Dataset — Verification Report

Ran three layers of automated checks against all 31 dataset files + canon + manifest. This is not a self-assessment — every check below is an actual script run against the real files.

## Layer 1: File Presence & Integrity (67 checks)
Every file in the manifest exists, is non-zero bytes, and parses with the library that would actually read it (csv, json, pypdf, PIL, UTF-8 text decode). **Result: 67/67 PASS.**

Found and removed: 2 leftover `.tmp.jpg` intermediate files that had leaked into the outputs folder during scan degradation — not part of the dataset, now cleaned up.

## Layer 2: Structural Validity (included in the 67)
- CSVs checked for uniform column counts across every row (no ragged rows)
- JSONs checked for clean parsing
- PDFs checked for extractable text (catches a PDF that "looks right" but is actually image-only or corrupted)
- PNGs checked for valid image data and non-trivial dimensions
- Devanagari script confirmed actually present (not just claimed) in the multi-script file

**Found 2 real bugs here:**

| File | Bug | Fix |
|---|---|---|
| `work_orders_eq101_family.csv` | Unquoted comma in the WO-2026-0245 notes field split it into extra columns | Rewrote with `csv.writer` (auto-quotes fields containing commas) |
| `dataset_manifest.csv` | Same issue in 7 rows — free-text fields with embedded commas, unquoted | Rewrote the same way |

Both were hand-typed CSV rows where a comma inside a sentence broke the column alignment. A naive ingestion parser would have shifted every field after the break by one column. Real bug, now fixed and re-verified.

## Layer 3: Cross-File Consistency (39 checks)
This is the "does everything actually agree with everything else" layer — asset tags, personnel names, document IDs, part numbers, pressure values, date arithmetic, and the specific narrative threads (Flow A/B/C) resolving correctly across independently-written files.

**Result: 38 PASS, 1 expected non-issue, 0 fails.**

**Found and fixed 1 real content bug:**
- The handwritten EQ-101 vibration note (image) said *"thodi alag lagi"* (Hindi: "sounded different"). The quarantine JSON and shift log both said *"thodi different lagi"* (English word substituted). Same meaning, different word — but `quarantine_vibration_observation.json`'s field is literally named `content_text_original`, so it should match the actual original artifact verbatim. **Fixed:** the JSON now matches the handwritten image exactly. The shift log entry is left as-is deliberately — it's a same-day informal paraphrase typed by a different act of writing, not meant to be a verbatim duplicate (that's the same treatment already correctly used for the PG-18 entry).

**Found and fixed 2 false alarms in my own audit script** (documenting these because you asked me to verify *everything*, including my own checking):
- My first cross-reference check omitted `.txt` files from the search set, so it wrongly flagged `WO-2025-0631` as "missing" from `voice_note_transcript.txt` — it was there all along (confirmed via direct grep). Script bug, not a data bug.
- My first check also expected `WO-2026-0714` (EQ-101 seal failure) to appear inside `ptw_v247.pdf`. That was my own incorrect assumption — the work order and the PTW are two unrelated maintenance activities that just happen to share a demo date. They were never supposed to cross-reference each other.

**One remaining item, not a bug:** Priya Nair (Quality & Compliance Officer, defined in the canon personnel directory) doesn't appear in any of the 31 dataset files. None of the four flows (A/B/C or the general event layer) currently exercise the compliance-cockpit persona. This is a coverage gap only if you want to demo that persona specifically — say the word and I'll add a compliance-review artifact for her.

## Specific arithmetic/logic checks that were verified, not assumed
- Telemetry historical ramp ends exactly on 2025-05-15 (WO-2025-0631's open date) ✓
- Telemetry current ramp ends exactly on 2026-07-15 (WO-2026-0714's open date, i.e. today) ✓
- Counterfactual gap: CSV dates (WO-2026-0203 → WO-2026-0245) compute to 20 days open-to-open / 18 days close-to-open, matching the event JSON exactly ✓
- Hydrotest math: 18.5 × 1.10 = 20.35 bar and 16.2 × 1.10 = 17.82 bar, both appear correctly in `mp_he_hydrotest_03.pdf` ✓
- XV-203 inspection interval: 12-May-2025 + 18 months = 12-Nov-2026, consistent across the PTW and the inspection checklist ✓
- Part number story: WO-2025-0631 correctly shows the OLD part (FSL-2240A, the awareness gap); WO-2026-0203 correctly shows the NEW part (FSL-2240B) ✓

## Bottom line
2 real bugs found and fixed (1 CSV formatting issue affecting 2 files, 1 wording inconsistency in 1 file). 2 false alarms in my own verification logic, corrected and re-verified. 1 known non-issue (unused persona) flagged for your decision. Everything else — 100+ individual checks — passed against the actual files, not against my memory of what I intended to write.
