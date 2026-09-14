# Kairos — Benchmarks & Evaluation

> Maps directly to the Problem Statement's **Evaluation Focus**. Every number here is
> **reproducible** against the loaded golden dataset — no hand-picked figures.
> Latest measured run (raw script output): [`../benchmark/RESULTS.md`](../benchmark/RESULTS.md).

## The harness

Self-contained evaluation harness + evidence, in `benchmark/` (mounted into the API container at
`/app/benchmark` — the scripts import the running app, so they execute inside it).

| File | What |
|------|------|
| `run_benchmark.py` | Retrieval · answer quality · provenance · per-category · latency percentiles · 95% CIs · KG-linkage (both cuts) |
| `run_kg_completeness.py` | KG linkage completeness, document-centric, with the unlinked remainder classified and dangling provenance reported separately |
| `run_cross_functional.py` | Cross-functional discovery counterfactual: whole-corpus retrieval vs one function's documents alone. Embeddings only, no LLM quota |
| `run_ocr_gate.py` | OCR accuracy against the dataset's declared clean/degraded pairings. Scores recall of operationally salient tokens, not character error rate |
| `verify_layers.py` | Per-layer smoke + latency (PASS/FAIL table) |
| `run_compliance_eval.py` | **Compliance gap-detection precision / recall / F1** vs ground truth derived from the dataset manifest |
| `run_time_to_answer.py` | **Time-to-answer vs BM25-only keyword search** — machine time, documents opened, modelled human time |
| `run_load_test.py` | **Concurrency sweep** — p50/p95/p99, throughput, error rate, first-bottleneck detection |
| `run_soak_test.py` | **Soak** — RSS and connection-count *slope* under sustained low load, latency drift, error rate, and a post-idle Neo4j recovery probe |
| `questions.json` | **37** domain-expert Q&A across 15 categories, grounded in `dataset/00_Reference/00_KAIROS_CANON.md` |
| `scripts/run_model_validation.py` | **Layer-0 entity-extraction F1** vs `validation_corpus`, per entity type, with extraction-path counts and a `VALID`/`SUSPECT` verdict |
| `RESULTS.md` | Raw output of the scripts (results only — this file holds the interpretation) |
| `scripts/seed_validation_corpus.py` | Seeds the Layer-0 NER ground-truth set (`validation_corpus`) that `scripts/run_model_validation.py` scores. **40 labels** (was 13) as of 2026-08-15 — every one verified present in that document's *indexed* text before being added |

> **Sizes, and what limits them.** The question set was widened **25 → 37** on 2026-08-15, then
> **37 → 46** on 2026-09-13 (personnel, dates, aliases, hydrotest ratio, PG-18 and PESO facts from the
> canon; each kept only after a retrieval-only run showed its fact reaching context — one that did not
> was dropped rather than tuned). The first widening was made so no
> category sits at n=1 (eight did, where a single flip moved a category from 100% to 0%); retrieval
> holds at 37/37 and the interval tightened from [87–100%] to [91–100%]. The NER corpus went
> **13 → 40** labels, but `ORGANIZATION` only reaches n=3: the golden corpus contains exactly two
> unambiguous vendors. "Rajgarh Petrochemical Complex" appears in 13 documents and was deliberately
> **not** labelled — it reads equally well as ORGANIZATION or LOCATION, and a ground truth that
> punishes a defensible answer is worse than a smaller one. That n=3 is a property of the dataset,
> not of the labelling effort.

`run_compliance_eval.py`, `run_time_to_answer.py` and `run_load_test.py` cover evaluation criteria
that once had **no number attached** — compliance gap accuracy and time-to-answer are named in the
problem statement, and scalability had only single-user sequential figures behind it. All three
have since been run against a loaded stack and their raw output is in `RESULTS.md` §4–§6.

> Two harness defects were found by running them rather than reading them, both fixed 2026-08-17:
> `run_benchmark.py` had no error handling around its retrieval calls, so one slow `/search` raised
> `ReadTimeout` out of `main()` and **discarded 21 of 37 already-graded questions** — ~20 minutes of
> paced synthesis for zero output. It now degrades a single question's context instead, and
> `--checkpoint` records each graded question as it lands so a crash costs the remainder, not the
> run. `run_time_to_answer.py` fired synthesis **back-to-back with no pacing** (the pattern that
> drives NIM into its timeout tail and drains the free Gemini tier) and allowed **180 s** per call —
> twice the browser's budget — so it recorded latencies no user could experience and scored calls
> the product would have aborted as successes. Both now match `run_benchmark.py`: 15 s pacing, 90 s
> cap.

## Methodology (fully deterministic — no LLM-as-judge)

Grading uses **no LLM**, so every number is reproducible. An LLM judge would be non-deterministic
(breaking that claim), circular (an LLM grading an LLM shares blind spots and rewards confident verbosity),
and slower — a poor fit for a platform whose pitch is reproducibility and provenance.

- **Per-question routing** — each question pulls context from the *right* source: hybrid `/search`,
  the asset's graph `/knowledge`, and/or `/aliases`. Not everything is forced through `/search`.
- **Retrieval** — keyword-in-context signal (does the fact actually reach the synthesis context?).
- **Answer quality** — the synthesized answer must **state the required fact(s) without negating them**:
  `must_all` = every token (exact / multi-part facts like part numbers, pressures, valve sets); `answer_any`
  = any correct-answer token (comparative questions whose correct keyword differs from the retrieval keyword);
  else `expect_any`. A required fact wrapped in a negator (*"not 16.2 bar"*) does **not** count. This kills the
  two failure modes of naive keyword scoring — false positives from negation and false negatives from strict
  wording — while staying deterministic.
- **Provenance** — every non-refused answer must cite `sources[]` (Kairos rule: no claim without provenance).
  A refusal is a valid, correct outcome (the safety gate) and carries its own sources.
- **Per-category scoring** — every question carries a `category` (current-fact, temporal-supersession,
  safety-isolation, counterfactual, alias-resolution, regulatory, traceability, …); results break down by
  category so a regression in one capability is visible, not averaged away.
- **95% confidence intervals** — each headline rate reports a Wilson score interval (the correct CI for small-n
  proportions), so `25/25` reads honestly as "100%, 95% CI [87–100%]" rather than implying infinite precision.
- **Latency percentiles** — synthesis latency is reported p50 / p95 / avg, not just a mean a single slow
  question can distort.
- **Entity-extraction F1 (Layer-0 model gate)** — `run_model_validation.py` scores the NER model against a
  human-verified ground-truth set (`validation_corpus`, seeded from canon by `seed_validation_corpus.py`),
  reporting precision / recall / F1 per entity type. Matching is **partial (span-overlap)** — the NER standard —
  so a prediction of "FISCHER PUMPS LTD." correctly credits the entity "Fischer". Ground truth is anchored to
  clean-text documents so the score isolates NER quality from OCR noise.
- **KG linkage / time-to-answer** — deterministic Cypher + per-request latency.

The grader + stats logic has a stack-free self-check: `python benchmark/run_benchmark.py --selftest`.
Only the *answer text* and the *NER output* are non-deterministic (they come from the LLMs under test);
their grading/scoring is exact. Retrieval / provenance / KG / CIs are the fully reproducible headline figures;
answer-quality varies by ±1 question and entity-F1 by a few points run-to-run (both are stochastic-model
snapshots, not fixed constants).

## How to reproduce

```bash
make load-dataset                       # load the golden corpus (seeds aliases + family history)
make verify                             # per-layer smoke + latency (13/13)
make verify ARGS=--full                 # + P&ID-VLM + synthesize checks (hit NIM)
make benchmark                          # routing + synthesis + deterministic grading + retrieval + KG
make benchmark ARGS=--retrieval-only    # fast: retrieval + KG only, no synthesis
docker exec kairos-backend-api python benchmark/run_benchmark.py --selftest             # grader + stats self-check
docker exec kairos-backend-api python scripts/seed_validation_corpus.py                 # seed NER ground truth
docker exec kairos-backend-api python scripts/run_model_validation.py --model-name <m>  # entity-extraction F1
docker exec -d kairos-backend-api python benchmark/run_soak_test.py --minutes 60 --vu 5   # soak (72 min; log to /app/.benchmark_runs/)
```

---

## Results

Measured **2026-08-16** — the first full sweep on the shipping configuration (37 questions, 40 NER
labels, `NVIDIA_NIM_TIMEOUT=60`). Raw output → [`../benchmark/RESULTS.md`](../benchmark/RESULTS.md).

| PS "Evaluation Focus" criterion | Kairos metric | Result |
|---|---|---|
| **Time-to-answer** | Per-layer latency + synthesis percentiles | **13/13 layers PASS**; synthesis **p50 1.5 s · p95 9.8 s** (Nemotron 3 Super on NIM at the 60 s cap, 46 questions, 2026-09-13) |
| **OCR accuracy (Layer 0 extension)** | Recall of salient tokens (asset tags, measurements, references, dates) vs the clean sibling declared in `dataset_manifest.csv`. **The harness makes no model calls** — it reads text already indexed in Elasticsearch, so it is free and safe to run alongside anything | **Unscoreable 4/4, re-confirmed 2026-08-23** — reported as UNSCOREABLE rather than recall 0.0, because nothing was produced and that is an indexing finding, not an accuracy one. **The two OCR defects behind it are now fixed** (a response key the parser never read, and a size ceiling that silently dropped oversized images); all four images transcribe correctly when probed directly. The gate still scores nothing because these documents were ingested *before* the fix and no reprocess endpoint exists, so their text was never indexed. It moves only after a re-extraction — a cloud-store write, out of scope under the no-cloud-writes rule. See `RESULTS.md` §11 |
| **Cross-functional knowledge discovery** | Counterfactual (`run_cross_functional.py`): questions the full corpus reaches that **no single function's documents** reach alone | **0 of 37** required crossing functions (31/37 reached overall; 21 answerable by one function alone, 7 by two, 3 by three). **A null result, reported as such** — at ~4 documents per function a silo search is near-exhaustive, so there is no gap to close on this corpus (2026-08-23) |
| **KG linkage completeness** | **Document-centric** (`run_kg_completeness.py`): active vault documents with ≥1 `KNOWLEDGE_EDGE` carrying their `document_id`, test artifacts excluded from the denominator, remainder classified | **18/21 (85%) linked · 1 quarantined by design (Layer 6) · 2 unexplained · 0 dangling** · 87 test documents excluded (re-run 2026-08-24 after **D2**'s backfill; see `RESULTS.md` §12). Two of the original four handwritten/degraded documents were re-extracted and now have real graph edges. The 2 remaining unexplained are the degraded scans (`scanned_inspection_degraded`, `scanned_oem_bulletin_degraded`) — both correctly triggered the 2026-08-24 span-confidence gate and stopped at `review_required`, an earlier staging state than formal Layer 6 quarantine, which is why they read as "unexplained" rather than "quarantined" here. The 1 quarantined-by-design item is `regulatory_clause_excerpts.pdf`, unrelated to this fix |
| KG linkage — asset cut | Assets linked into the graph + edge verification (Cypher) | **Not currently trustworthy as published** — the underlying query (`MATCH (a:Asset) RETURN count(a)`) has no test-artifact filter, unlike the document cut above. On 2026-08-24 it reads 16/55 (29%), not because linkage regressed but because the graph now holds far more test-sweep assets than it did when 10/10 was last measured. **Quote the document cut above for the PS criterion** until this query is filtered to match |
| **Query answer quality** | Golden Q&A (46): answer states the correct fact, not negated, with sources | **41/46 (89.1%)**, 95% CI [77–95%]; run validity **VALID**, 40/46 answered by the pinned NIM model, 6 correct refusals (5 honest misses — Q02, Q09, Q24, Q41, Q46, all of which retrieved the fact; 2026-09-13) |
| **Provenance** | Does every non-refused answer cite `sources[]`? | **46/46 (100%)**, 95% CI [92–100%] |
| **Retrieval quality** | Does the correct source surface for each question? | **46/46 (100%)**, 95% CI [92–100%] |
| **Entity-extraction accuracy** | Layer-0 model gate: precision / recall / F1 per entity type | **F1 0.805** on 40 labels; PERSON 1.0 (n=7), ASSET_TAG 0.889 (n=30), ORGANIZATION 0.8 (n=3). **`VALID`** — 0 of 15 extractions fell back |
| **Compliance gap detection** | Precision / recall / F1 vs an independently-derived truth table | **P 1.000 · R 0.838 · F1 0.912**, zero false positives |
| **Cross-functional discovery** | Cross-site advisories | 🟦 fixture (single-site MVP, by design) |

> **Comparing against the older 23/25 or 24/25 is comparing different tests.** Those were 25
> questions with eight categories at n=1; this is 37 with none below n=2. Read per-category rates
> with the n attached — at n=2 a single flip moves a category by 50%.

Per-category breakdown (15 categories) and per-question output: [`../benchmark/RESULTS.md`](../benchmark/RESULTS.md).

### Time-to-answer vs "traditional search"

> **This was previously an argument, not a measurement.** The paragraph below cited the problem
> statement's own industry figures against Kairos's retrieval latency — which compares a measured
> number to a survey statistic, not a baseline on the same corpus. `run_time_to_answer.py` now
> measures both halves on the same question set. Run it before quoting any reduction figure.

Why a naive latency comparison would be dishonest: BM25 returns a document list in ~50 ms while
Kairos returns a cited answer in ~8 s. On machine time alone, keyword search wins — the real cost
of keyword search is the human reading the list it hands back. So the harness reports three things
separately and never hides the one Kairos loses:

| Measure | What it captures |
|---|---|
| **Machine time** | BM25-only ES latency vs Kairos retrieval + synthesis. Kairos is slower. |
| **Documents opened** | Rank of the first answer-bearing document in a BM25-only ranking — how many documents an engineer opens before finding the fact. Kairos cites the source, so this is 1. |
| **Modelled human time** | `documents_opened × SECONDS_PER_DOCUMENT + machine time` |

`SECONDS_PER_DOCUMENT` (default 120 s, overridable) is an **explicit assumption, not a
measurement** — change it and the conclusion changes. Answer-bearing ground truth reuses the same
`expect_any` keyword sets `run_benchmark.py` already grades retrieval with, so no new labelling
judgement enters.

### Compliance gap-detection accuracy

`run_compliance_eval.py` scores the `gap` classification against ground truth built from the golden
dataset manifest (which document types are linked to which asset) crossed with each clause's
declared `requires_document_type`. That truth table is constructed **independently of the Cypher
under test**, so a disagreement means real breakage in ingestion → asset linking → equipment-class
applicability → the gap query. Verified to derive **52 applicable (clause × asset) pairs: 37
expected gaps, 15 with evidence** — a discriminating target, not an all-gaps one.

Two honest caveats: it scores whether the system finds the evidence it was *told* to look for, not
whether the clause → document-type mapping is the right reading of each regulation (that mapping is
a human judgement in the seed). And **vessel and compressor clauses apply to zero assets** in the
current dataset, so 4 of 12 clauses are never exercised.

### Scalability

`run_load_test.py` sweeps concurrency (default 1→50) over cheap read endpoints and flags the level
at which p95 exceeds 3× the single-user baseline — that number, not the single-user latency, is the
one to quote. Model-backed endpoints are **excluded by default** so a sweep cannot burn NIM/Jina
quota; `--include-models` opts in. It is a load test, not a soak test: a sweep that finishes in
minutes says nothing about memory growth or connection leakage over hours.

`run_soak_test.py` covers that second question, and reuses the same reads-only endpoint list, so it
**cannot spend provider quota however long it runs**. Three things about how it is graded:

- **The slope is the finding, a single reading is not.** It fits a least-squares slope per hour over
  RSS and connection count, and **excludes the warm-up samples** — pools and the `_LRU` filling to
  their initial watermark is a step, not a trend, and including it once turned a 2-minute smoke run
  into a reported "+728 MB/hour". Below `_MIN_TREND_SAMPLES` it reports **NO DATA** rather than
  extrapolating a leak verdict from noise.
- **The thresholds are fixed and low-ceremony:** memory `FLAT` under +10 MB/h, connections `STABLE`
  under +5/h, errors `CLEAN` under 1%. A few MB/hour is normal for a Python process under load
  (allocator arenas, a bounded cache filling); tens of MB/hour is not. **Read a passing slope as "no
  leak signal at this window length", not as "flat"** — a result at 80–90% of the threshold, inside
  an oscillation band of similar size, is not distinguishable from zero over one hour.
- **Phase 3 is the part with teeth.** After the load stops it idles ~10 minutes — long enough for
  Aura to prune idle pooled connections — then probes each Neo4j-backed endpoint, where a
  `SessionExpired` is a real failure. This is why the soak is run against **cloud stores**: local
  containers do not prune idle connections, so the same run against `--profile local-stores` would
  pass without testing anything.

The harness counts errors but does not classify them, so attributing a burst to store-side resets
rather than application degradation is an inference from its shape (bursty, non-accelerating,
followed by quiet) — say so when reporting it.

---

## What the fixes did

| Fix | Effect |
|-----|--------|
| **Seed canonical aliases** — loader now writes `alias_table.csv` into `asset_alias_map` | Q08 retrieves (P-101 / Feed Pump A / "the old Fischer") |
| **Ingest family maintenance history** — loader ingests `work_orders_eq101_family.csv` (the EQ-102 counterfactual narrative that no event path indexed) | Q10 retrieves + answers |
| **Wider ES highlight** — `number_of_fragments` 3 → 8 so the snippet spans the doc | Q12 surfaces OISD/PESO regardless of query wording (helps real synthesis too) |
| **Stronger deterministic grader** — `must_all` / `answer_any` + negation guard + provenance gate | kills false positives (negated facts) and false negatives (strict wording), no LLM |

## Notes (honest reading of the numbers)

- **The 3 answer misses are honest, not benchmark bugs.** Q09 (`aggregation` — EQ-101 failure count),
  Q29 (`blast-radius`) and Q35 (`traceability`) all *retrieve* correctly and cite sources; the synthesis
  declines to commit. Q09 has missed since the 25-question era — EQ-101's full failure history lives in a
  family CSV scoped to EQ-102 (one `asset_id` per document) — so it is a standing weakness, not a new one.
  Left visible on purpose; gaming them to 37/37 would defeat a reproducible benchmark.
- **All 3 refusals are genuine, and were audited rather than assumed.** The grader counts a refusal as a
  correct outcome, which means a gate that over-refuses would silently *raise* the score. Each refusal
  (Q07, Q19, Q25) was checked against the graph: no asset involved carries an authoritative (≤L3) source
  for the safety-critical parameter asked. Q25 is the instructive case — the bulletin revising the HE-3xx
  limit to 16.2 bar is linked to **HE-301**, while Q25 asks about **HE-302/303**, so answering would mean
  extrapolating a pressure limit onto assets no source covers. Raw and adjusted scores are identical.
- **The `VIA` column records the answering provider per question.** In that run NIM and OpenRouter both
  served `llama-3.1-70b`, so 11 of 34 OpenRouter answers still counted as the same model. NVIDIA retired
  that model on 2026-09-13 and tier 1 is now Nemotron 3 Super 120B, so from then on **only `nim` counts as
  the pinned model** — an OpenRouter or Gemini answer marks the run `SUSPECT`.
- **Entity-F1 uses partial-match on a canon-grounded set.** `ORGANIZATION` is canon-limited to 3 samples,
  so a single stochastic miss swings its per-type rate — quote it with the n. The benchmark also surfaced a
  real code smell — `NERService` can drop a regex-added `ASSET_TAG` when the model labels the same token
  `MATERIAL` (dedup collision); noted for a follow-up, out of benchmark scope.
- **A `SUSPECT` entity-F1 is a ceiling, not a score.** Any extraction that falls back lands on the regex
  path, which matches `ASSET_TAG` only, so a run with fallbacks reports a floor on the model's real
  accuracy rather than measuring it. **The current run is `VALID`: 15 of 15 extractions ran on the NIM
  model, zero timeouts and zero parse failures**, so 0.805 is the model's score and not a ceiling.
  Both historical causes are closed — the 30 s timeout (`services/ner.py` now reads
  `NVIDIA_NIM_TIMEOUT`) and the response-parsing defect (`max_tokens: 1024` truncated JSON on
  entity-dense documents; `_salvage_objects` now recovers complete objects from a truncated array).
  Keep this caveat: it is how to read a `SUSPECT` verdict if one reappears.
- **Compliance F1 drifts downward as humans promote knowledge, and that is a property of the harness.**
  Its ground truth is derived from the static dataset manifest, so evidence a human promotes into the graph
  afterwards reads as a false negative. Five of the six FNs in the 2026-08-16 run are one such promotion on
  EQ-101. The truth table is **not** amended to match — that would destroy the independence that makes the
  number meaningful. Precision, the safety-relevant direction, stays 1.000.
- **"0% verified" edges is a safety feature, not a gap.** Every edge is `unverified` until a human promotes
  it (quarantine one-way gate); 0% auto-verified proves the governance gate is enforced.
- **10/10 counts the canonical golden assets** (P-101, HE-301…); integration-test rows are excluded from the
  linkage figure.

## Functional validation (correctness, separate from accuracy)
- Backend test suite: **~175 passed · 3 skipped — *stale: not re-measured since 2026-08-16; ~53 tests added, so treat this as a floor*** (1 = transient NIM timeout in-sandbox).
- Contract tests (`test_contract.py`) pin the API response shapes that historically drift.
- Layer 3 P&ID vision extraction: live-validated on `pid_line3_isolation_boundary.png`.
