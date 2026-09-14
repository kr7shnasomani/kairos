# Kairos — Benchmark Results

Raw output of the evaluation scripts, and nothing else. For methodology, root causes, decision
history and caveats, see:

- Methodology and interpretation: [`../docs/BENCHMARKS.md`](../docs/BENCHMARKS.md)
- Current numbers, staleness flags, caveats and fix history:
  [`../docs/implementation/status.md` § Benchmarks — current numbers](../docs/implementation/status.md#benchmarks--current-numbers)
- Root-cause writeups for numbers that changed: `status.md` § Pending

## Summary

| Metric | Result | Harness |
|---|---|---|
| Layer smoke checks | 13/13 pass | `verify_layers.py` |
| Retrieval (fact reaches context) | 46/46 (100%) | `run_benchmark.py` |
| Query answer quality | 41/46 (89.1%), VALID | `run_benchmark.py` |
| Provenance — all responses, incl. refusals | 46/46 (100%) | `run_benchmark.py` |
| Provenance — correct answers only | 41/41 (100%) | `run_benchmark.py` |
| Entity-extraction F1 (Layer 0) | 0.805 on 40 labels, VALID | `run_model_validation.py` |
| Compliance gap detection | P 1.000 · R 0.838 · F1 0.912 | `run_compliance_eval.py` |
| Retrieval reach by arm | exact 33/37 (89.2%) · semantic 35/37 (94.6%) · hybrid 35/37 (94.6%) | `run_retrieval_baseline.py` |
| Proactive brief quality (Layer 8) | 6/6 graded checks pass | `run_brief_eval.py` |
| Adversarial safety | 0 unsafe answers / 15 questions, VALID | `run_safety_eval.py` |
| Concurrency | 2275 requests · 0% errors · knee at 50 VU | `run_load_test.py` |
| Soak — memory / connection leakage | PASS, no leak signal | `run_soak_test.py` |
| OCR accuracy on paired images | 2/4 scoreable — handwriting mean recall 0.333 (Layer 3 limitation); 2 correctly in review, not indexed | `run_ocr_gate.py` |
| KG linkage completeness | 18/21 (85%) documents linked | `run_kg_completeness.py` |
| Cross-functional discovery | NULL on this corpus | `run_cross_functional.py` |

## 1. `verify_layers.py` — per-layer smoke + latency

```
  LAYER                 CHECK                                 STATUS      ms
  ------------------------------------------------------------------------------
  Auth                  POST /auth/login                      PASS         0   token ok
  L0 Validation         GET /governance/validation-corpus/stat PASS       492   HTTP 200
  L1 MDM                GET /assets                           PASS      1670   HTTP 200
  L2 Vault              GET /documents                        PASS       163   HTTP 200
  L4 Graph              GET /governance/circuit-breaker       PASS       212   HTTP 200
  L5 OT (mock)          GET /ot/query (go connector)          PASS        31   HTTP 200
  L6 Quarantine         GET /governance/quarantine            PASS       199   HTTP 200
  L7 Governance         GET /governance/conflicts             PASS       230   HTTP 200
  L8 Events/Briefs      GET /briefs                           PASS       363   HTTP 200
  L9 Elicitation        GET /elicitation/offboarding          PASS       406   HTTP 200
  L11 Retrieval         GET /search                           PASS      3672   HTTP 200
  L12 Frontend          GET / (frontend)                      PASS       180   HTTP 200
  Datastores            GET /health/detailed                  PASS       339   HTTP 200
  ------------------------------------------------------------------------------
  13/13 checks passed
```

## 2. `run_benchmark.py` — domain-expert Q&A

**Current — 2026-09-13, 46 questions, checkpoint `run_20260913_nemotron_46q.jsonl`** (synthesis on NIM
`nvidia/nemotron-3-super-120b-a12b`; clean reload with chunked NER, linked-document search scope and the
NIM 503 retry; question set widened 37 → 46 the same day):

```
Retrieval (fact reaches context):    46/46 (100%)  95% CI [92–100%]
Answer quality (correct/total):      41/46 (89.1%) 95% CI [77–95%]
Answer provenance (sourced/correct): 46/46 (100%) all responses · 41/41 correct answers
Synthesis latency:                   p50 1530 ms · p95 9805 ms · avg 3077 ms
Provider mix:                        nim 40 · refused 6
Run validity:                        VALID — 40/46 answered by the pinned NIM model
```

By category (retrieval · answer · provenance):
```
    aggregation            2/2 · 1/2 · 2/2
    alias-resolution       3/3 · 3/3 · 3/3
    blast-radius           2/2 · 2/2 · 2/2
    causal                 3/3 · 2/3 · 3/3
    counterfactual         2/2 · 2/2 · 2/2
    current-fact           6/6 · 6/6 · 6/6
    mdm                    2/2 · 2/2 · 2/2
    personnel              5/5 · 4/5 · 5/5
    regulatory             3/3 · 2/3 · 3/3
    safety-isolation       3/3 · 3/3 · 3/3
    supersession           2/2 · 2/2 · 2/2
    temporal               4/4 · 4/4 · 4/4
    temporal-history       2/2 · 2/2 · 2/2
    temporal-supersession  2/2 · 2/2 · 2/2
    traceability           5/5 · 4/5 · 5/5
  KG linkage (assets):     10/10 assets linked (100%) · 146 edges (11 verified)
  KG linkage (documents):  19/21 (90%) · 0 quarantined by design · 2 unexplained · 0 dangling
```

Misses: Q02 (causal), Q09 (aggregation), Q24 (traceability), Q41 (personnel, new) and Q46 (regulatory,
new). All five retrieved the fact (`retr=1`) and were answered by the pinned model — synthesis gaps, not
retrieval gaps. New questions were kept after scoring, including the two that missed.

**Prior — 2026-09-13, 37 questions, checkpoint `run_20260913_nemotron.jsonl`** (before the final
reload; same model):

```
Retrieval (fact reaches context):    37/37 (100%)  95% CI [91–100%]
Answer quality (correct/total):      35/37 (94.6%) 95% CI [82–99%]
Answer provenance (sourced/correct): 37/37 (100%) all responses · 35/35 correct answers
Synthesis latency:                   p50 2469 ms · p95 7292 ms · avg 3083 ms
Provider mix:                        nim 33 · refused 4
Run validity:                        VALID — 33/37 answered by the pinned NIM model
```

By category (retrieval · answer · provenance):
```
    aggregation            2/2 · 1/2 · 2/2
    alias-resolution       2/2 · 2/2 · 2/2
    blast-radius           2/2 · 2/2 · 2/2
    causal                 2/2 · 1/2 · 2/2
    counterfactual         2/2 · 2/2 · 2/2
    current-fact           6/6 · 6/6 · 6/6
    mdm                    2/2 · 2/2 · 2/2
    personnel              3/3 · 3/3 · 3/3
    regulatory             2/2 · 2/2 · 2/2
    safety-isolation       2/2 · 2/2 · 2/2
    supersession           2/2 · 2/2 · 2/2
    temporal               2/2 · 2/2 · 2/2
    temporal-history       2/2 · 2/2 · 2/2
    temporal-supersession  2/2 · 2/2 · 2/2
    traceability           4/4 · 4/4 · 4/4
  KG linkage (assets):     9/10 assets linked (90%) · 90 edges (4 verified)
  KG linkage (documents):  19/21 (90%) · 0 quarantined by design · 2 unexplained · 0 dangling
```

Misses: Q02 (causal) and Q09 (aggregation — a count across work orders, two of which rank below
the retrieval cut-off). Both retrieved the fact (`retr=1`); neither is a fallback or a refusal.

**Prior — 2026-08-24, checkpoint `run_20260824_1351_postfix.jsonl`** (Llama 3.1 70B, since retired):

```
Retrieval (fact reaches context):    37/37 (100%)  95% CI [91–100%]
Answer quality (correct/total):      36/37 (97.3%) 95% CI [86–100%]
Answer provenance (sourced/correct): 37/37 (100%) all responses · 36/36 correct answers
Synthesis latency:                   p50 8242 ms · avg 16879 ms
Provider mix:                        nim 31 · openrouter 2 · refused 4
Run validity:                        VALID
```

By category (retrieval · answer · provenance):
```
    aggregation            2/2 · 2/2 · 2/2
    alias-resolution       2/2 · 2/2 · 2/2
    blast-radius           2/2 · 2/2 · 2/2
    causal                 2/2 · 1/2 · 2/2
    counterfactual         2/2 · 2/2 · 2/2
    current-fact           6/6 · 6/6 · 6/6
    mdm                    2/2 · 2/2 · 2/2
    personnel              3/3 · 3/3 · 3/3
    regulatory             2/2 · 2/2 · 2/2
    safety-isolation       2/2 · 2/2 · 2/2
    supersession           2/2 · 2/2 · 2/2
    temporal               2/2 · 2/2 · 2/2
    temporal-history       2/2 · 2/2 · 2/2
    temporal-supersession  2/2 · 2/2 · 2/2
    traceability           4/4 · 4/4 · 4/4
  KG linkage (assets):     16/55 (29%, unfiltered — see status.md) · 172 edges (11 verified)
  KG linkage (documents):  16/21 (76%) · 1 quarantined by design · 4 unexplained · 0 dangling
```

**Prior — 2026-08-17:**

```
Retrieval (fact reaches context):    37/37 (100%)  95% CI [91–100%]
Answer quality (correct/total):      33/37 (89.2%) 95% CI [79–97%]
Answer provenance (sourced/correct): 33/33 (100%)  95% CI [91–100%]
Synthesis latency:                   p50 32141 ms · p95 66039 ms · avg 34146 ms
KG linkage:                          10/10 assets linked (100%) · 45 edges (2 verified)
Provider mix:                        25 nim · 8 openrouter · 4 refused
Run validity:                        VALID
```

By category (retrieval · answer · provenance):
```
    aggregation            2/2 · 1/2 · 2/2
    alias-resolution       2/2 · 2/2 · 2/2
    blast-radius           2/2 · 1/2 · 2/2
    causal                 2/2 · 2/2 · 2/2
    counterfactual         2/2 · 2/2 · 2/2
    current-fact           6/6 · 6/6 · 6/6
    mdm                    2/2 · 2/2 · 2/2
    personnel              3/3 · 3/3 · 3/3
    regulatory             2/2 · 2/2 · 2/2
    safety-isolation       2/2 · 2/2 · 2/2
    supersession           2/2 · 2/2 · 2/2
    temporal               2/2 · 2/2 · 2/2
    temporal-history       2/2 · 2/2 · 2/2
    temporal-supersession  2/2 · 2/2 · 2/2
    traceability           4/4 · 3/4 · 4/4
```

## 3. `run_model_validation.py` — Layer-0 entity-extraction F1

```json
{
  "model_name": "meta/llama-3.2-11b-vision-instruct",
  "corpus_size": 40,
  "precision": 0.7857,
  "recall": 0.825,
  "f1": 0.8049,
  "by_entity_type": {
    "ASSET_TAG":    {"precision": 1.0, "recall": 0.8,    "f1": 0.8889, "count": 30},
    "MATERIAL":     {"precision": 0.0, "recall": 0.0,    "f1": 0.0,    "count": 0},
    "ORGANIZATION": {"precision": 1.0, "recall": 0.6667, "f1": 0.8,    "count": 3},
    "PERSON":       {"precision": 1.0, "recall": 1.0,    "f1": 1.0,    "count": 7}
  },
  "passed": false,
  "regressed_entity_types": ["ASSET_TAG"],
  "extraction_paths": {"nim": 15},
  "fallback_extractions": 0,
  "validity": "VALID"
}
```

## 4. `run_compliance_eval.py` — compliance gap-detection accuracy

```
  Applicable (clause × asset) pairs in ground truth: 52
  Findings returned by /compliance/gaps:             47
    of which gap:                 31
    of which unverified_evidence: 16

  Gap detection — precision 1.000  recall 0.838  F1 0.912
    true positives  31
    false positives 0   (flagged a gap that the dataset satisfies)
    false negatives 6   (missed a real gap)

  Full status agreement: 46/52 pairs

  False negatives:
    10.2.1   EQ-101   reported nothing
    4.1.1    EQ-101   reported nothing
    4.1.2    EQ-103   reported unverified_evidence
    8.1.1    EQ-101   reported nothing
    8.2.1    EQ-101   reported nothing
    9.1.1    EQ-101   reported nothing
```

## 5. `run_time_to_answer.py` — time-to-answer vs BM25 keyword search

```
  Questions: 37   assumption: 120s to read one document

  MACHINE TIME
    BM25-only mean:                 34.8 ms
    Kairos retrieve+synth:       26749.0 ms

  DOCUMENTS OPENED BEFORE THE FACT
    BM25-only mean rank:            1.35
    fact in top-10 for:        36/37 questions
    Kairos:                         1.00  (cited source, verified once)

  MODELLED HUMAN TIME TO A TRUSTED ANSWER
    traditional:                   100.0 min total  (2.7 min/question)
    Kairos:                         90.5 min total  (2.4 min/question)
    reduction:                       9.5 %
```

## 6. `run_load_test.py` — concurrency sweep

```
  Endpoints: 9 (reads only)
  Requests per worker per level: 25

    VU   reqs      rps    p50 ms    p95 ms    p99 ms    max ms    err
  ------------------------------------------------------------------------------
     1     25      5.8     135.9     272.6    1076.3    1076.3  0.0%
     5    125     26.5     147.0     352.4     819.0     943.2  0.0%
    10    250     50.4     159.4     375.9     511.5     801.5  0.0%
    25    625     72.3     269.9     777.6     985.4    1164.0  0.0%
    50   1250     74.5     499.8    1839.5    2139.0    2356.9  0.0%

  p95 relative to single-user baseline:
    1 VU 1.00x · 5 VU 1.29x · 10 VU 1.38x · 25 VU 2.85x · 50 VU 6.75x
  First sustained bottleneck: p95 exceeds 3x baseline from 50 VU upward.
```

## 7. `run_retrieval_baseline.py` — retrieval reach by arm

```
  arm                reach            95% CI
  --------------------------------------------
  exact-only      33/37  89.2%        [75–96%]
  semantic-only   35/37  94.6%        [82–99%]
  hybrid          35/37  94.6%        [82–99%]

  Hybrid vs best single method (semantic-only): +0.0 pts
```

## 8. `run_safety_eval.py` — adversarial safety

```
  Kairos — Adversarial Safety Eval   15 questions
  UNSAFE ANSWERS:            0
  Refusals:                  12
  Not classified as safety:  0
  Run validity:              VALID
```

## 9. `run_brief_eval.py` — proactive brief quality (Layer 8)

```
  Kairos — Proactive Brief Quality (Layer 8)   6/6 cases pass

  case   result   detail
  ----------------------------------------------------------------------------
  B01    PASS       [soft, not graded: FSL-2240B]
  B02    PASS       [soft, not graded: histor, prior, previous]
  B03    PASS       [soft, not graded: XV-203, XV-204, PG-18]
  B04    PASS
  B05    PASS
  B06    PASS

  7 soft expectation(s) unmet — these are REPORTED, not graded.
```

## 10. `run_soak_test.py` — memory and connection-pool behaviour over hours

```
Kairos — Soak Test   60 min · 5 VU · sample every 60s
Endpoints: 9 (reads only — no provider quota)
==============================================================================
BASELINE   rss    315.5 MB · conns  10

 elapsed     rss MB   conns    p50 ms    p95 ms     reqs    err
------------------------------------------------------------------------------
    1.0m      330.2      38     226.5     955.1      504      0
    2.0m      332.3      40     205.4     612.4      562      0
    3.0m      334.2      38     208.5     365.5      624      0
    4.0m      335.4      38     203.6     546.4      608      3
    5.0m      335.4      36     224.8    1262.1      479      7
    6.0m      335.8      34     216.1    1571.8      390      9
    7.0m      334.4      34     181.6     345.2      668      9
    8.0m      337.7      34     196.5     359.9      632      9
    9.0m      337.9      35     192.3     373.9      632      9
   10.0m      337.6      35     195.8     672.8      567      9
   11.0m      336.4      33     198.2     703.3      587      9
   12.0m      338.4      34     180.6     347.7      653      9
   13.0m      337.1      35     207.0     493.2      612     11
   14.0m      338.6      35     229.8     521.9      585     13
   15.0m      339.3      37     215.3     436.4      608     13
   16.0m      337.9      35     198.3     422.1      643     15
   17.0m      336.6      36     167.4     324.0      682     15
   18.0m      340.3      34     164.3     312.0      689     15
   19.0m      339.3      36     169.2     328.9      684     17
   20.0m      340.4      36     161.3     361.7      678     17
   21.0m      338.3      35     196.9     567.2      603     21
   22.0m      337.9      33     204.2     432.9      626     21
   23.0m      340.6      35     161.8     293.0      699     21
   24.0m      336.6      35     156.6     284.2      699     21
   25.0m      338.0      36     177.1     321.0      681     21
   26.0m      340.1      33     194.8     355.4      650     21
   27.0m      339.6      35     191.8     367.2      654     23
   28.0m      339.1      37     192.1     351.1      652     23
   29.0m      341.7      38     201.8     485.0      613     28
   30.0m      340.3      37     187.7     385.1      652     28
   31.0m      339.7      36     178.2     341.2      668     28
   32.0m      340.8      39     193.1     431.8      639     28
   33.0m      343.1      38     198.3     391.5      652     29
   34.0m      342.3      40     200.7     401.4      634     29
   35.0m      339.6      39     203.1     396.4      634     29
   36.0m      341.9      37     177.4     329.4      671     29
   37.0m      338.9      39     197.2     460.1      636     29
   38.0m      341.7      37     198.8     402.7      640     29
   39.0m      342.0      37     192.7     380.3      651     29
   40.0m      339.5      37     188.9     374.0      650     29
   41.0m      342.8      42     185.7     344.1      662     29
   42.0m      342.9      41     173.3     389.4      670     31
   43.0m      341.3      44     170.0     365.3      680     31
   44.0m      340.9      43     199.4     400.3      646     31
   45.0m      342.7      45     213.7     429.7      613     31
   46.0m      341.3      42     210.0     407.4      624     31
   47.0m      342.9      44     201.1     398.9      639     31
   48.0m      343.1      38     197.4     379.3      648     31
   49.0m      341.0      37     209.0     412.5      631     31
   50.0m      343.5      38     190.8     335.2      659     31
   51.0m      341.2      38     205.7     349.5      638     31
   52.0m      342.8      37     156.3     338.5      690     31
   53.0m      341.1      35     171.2     488.0      640     33
   54.0m      344.0      38     274.5    1694.4      407     41
   55.0m      343.0      38     198.5     575.5      588     41
   56.0m      342.8      36     180.2     400.3      661     41
   57.0m      342.6      37     185.9     413.6      633     41
   58.0m      340.5      35     154.4     318.7      706     41
   59.0m      345.5      37     181.3     360.4      659     41
   60.0m      345.4      37     182.5     365.3      657     41

IDLE 10 min — no traffic, so Aura can close pooled connections…
Recovery probes (a SessionExpired here is a real failure):
  /compliance/dashboard                        OK
  /assets/EQ-101/knowledge                     OK
  /graph/asset/EQ-101                          OK
  /governance/blast-radius/DOC-NONE            OK

==============================================================================
Requests: 37842 · errors: 41 (0.11%)
RSS   315.5 MB idle → 342.3 MB (warm-up +14.6 MB, then slope +8.6 MB/hour over 59 steady samples)
Conns 10 idle → 14 (steady slope +4.2/hour)

VERDICT
  memory           FLAT      +8.6 MB/hour
  connections      STABLE    +4.2/hour
  errors           CLEAN     0.11%
  idle recovery    OK        4/4 endpoints

PASS — no leak signal over this window.
```

## 11. `run_ocr_gate.py` — OCR accuracy on the paired image documents

**Current — 2026-08-24, after the D2 backfill:**

```
OCR ACCURACY GATE — recall of operationally salient tokens
  reference = the clean sibling declared in dataset_manifest.csv

  scanned_oem_bulletin_degraded.png      UNSCOREABLE — no OCR text indexed (nothing to score)
  scanned_inspection_degraded.png        UNSCOREABLE — no OCR text indexed (nothing to score)
  handwritten_shift_log.png              0.3333  (3/9 tokens, handwritten)
      asset_tag      1/3
      reference      1/3
      date           1/3
      missed: PG-18, WO-2026, PG-18, WO-2026-0714, 15-JUL-2026, 24-JUN-2026
  handwritten_inspection_note.png        0.3333  (3/9 tokens, handwritten)
      asset_tag      1/3
      reference      1/3
      date           1/3
      missed: EQ-101, WO-2026, EQ-101, WO-2026-0714, 15-JAN-2026, 15-JUL-2026

  2 image(s) produced NO OCR text and are excluded from the means:
    scanned_oem_bulletin_degraded.png  (no_ocr_text)
    scanned_inspection_degraded.png  (no_ocr_text)

  scanned (degraded)   mean recall: n/a
  handwritten          mean recall: 0.3333
```

**Prior — 2026-08-23:**

```
  scanned_oem_bulletin_degraded.png      UNSCOREABLE — no OCR text indexed (nothing to score)
  scanned_inspection_degraded.png        UNSCOREABLE — no OCR text indexed (nothing to score)
  handwritten_shift_log.png              UNSCOREABLE — no OCR text indexed (nothing to score)
  handwritten_inspection_note.png        UNSCOREABLE — no OCR text indexed (nothing to score)

  NOTHING SCOREABLE.
```

## 12. `run_kg_completeness.py` — document-centric linkage completeness

**Current — 2026-08-24, after the D2 backfill:**

```
KG LINKAGE COMPLETENESS
  linked                 18/21  (85%)
  excluded — test docs     87   (ann_test_*/scratch: they measure test hygiene, not linkage)
  unlinked — quarantined    1   (Layer 6 working as designed, not a miss)
  unlinked — unexplained    2
  promoted-only edges       7   (field knowledge, no vault document by design)
  dangling provenance       0

  by document type (linked/active):
    inspection_report  6/7   85%      procedure    5/5  100%
    oem_manual         3/4   75%      shift_log    2/2  100%
    ptw                1/1  100%      regulation   0/1    0%
    pid_drawing        1/1  100%
```

**Prior — 2026-08-23:**

```
  linked                 16/21  (76%)
  unlinked — unexplained    4
```

## 13. `run_cross_functional.py` — cross-functional discovery

```
Result: NULL on this corpus — the silo counterfactual does not separate from the
full-corpus arm at 24 documents.
```
