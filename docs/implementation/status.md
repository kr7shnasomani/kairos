# KAIROS — Implementation Status

> **Single source of truth for open work.** What's **built** ([Layer completion](#layer-completion)),
> how faithfully it matches the design ([Conformance](#architecture--implementation-conformance)),
> the **current measured numbers** ([Benchmarks](#benchmarks--current-numbers)), and **what's left**
> ([Open decisions](#open-decisions--blocked-on-a-human-call-not-on-work) · [Backlog](#improvement-backlog) · [Pending](#pending)).
>
> **[Open decisions](#open-decisions--blocked-on-a-human-call-not-on-work) is where to look first if
> you are picking up this project.** Those items are specified and cheap; they are waiting on a call,
> not on engineering.
>
> **This file tracks open items.** Completed work is removed once done — the git history holds it,
> and a status file that never forgets stops being a status file. Raw benchmark output lives in
> [`benchmark/RESULTS.md`](../../benchmark/RESULTS.md); route/persona verification in
> [`e2e-sweep.md`](./e2e-sweep.md).
>
> It also carries the **reference notes** an agent needs only when it hits them — the
> [Known Pitfalls](#known-pitfalls) tables and the [CI / tooling detail](#ci-tooling--project-reference),
> moved out of `AGENTS.md` on 2026-08-17 so that file stays a short per-task brief rather than
> something re-read in full on every task.
>
> Legend: ✅ **Live** (real, end-to-end) · 🟨 **Live on mock input** (real logic, fed by mock data
> **by design**) · 🟦 **Mocked by design** (final).

---

## Headline

**All 13 architecture layers are implemented.** Architecture conformance is **~91.5%** — the mean of
the 13 per-layer scores in [Conformance](#architecture--implementation-conformance).

**The rubric is what makes this number mean anything.** A requirement scores only if it is
*reachable in the path the architecture specifies*, not merely present somewhere in the codebase.
The looser reading — does the mechanism exist — once produced ~94% for the same tree, and four
requirements were built-but-unreachable underneath it. Re-score against reachability or the number
is not comparable. **Recompute the mean from the table whenever a layer score changes**; it has
drifted from the table twice for exactly that reason.

Four deviations are deliberate and cap the score by construction (P&ID Path A, OPC-UA / Uniformance /
GraphQL connectors, PuppyGraph federated MDM, separate handwriting + form models). The rest of the
gap is real and listed per layer below.

**Corpus and plant connectivity are a fixed scope boundary, not open work.** KAIROS has **no
connection to a live industrial plant** (no OSIsoft PI historian, no SAP/Maximo EAM, single-site) and
no access to a real industrial document archive — every benchmark figure is measured against the
authored golden dataset in `dataset/`. Reviewers should not log "synthetic corpus" or "no real plant
data" as defects; they are the delivered MVP boundary. What *is* fair to assess is whether the
numbers are honestly measured on that corpus, and where corpus size limits what they can prove. The
mock adapters are real code with a documented one-line switch to go live *if* a plant is ever
connected; until then, the mock **is** the product.

**Deployment is out of scope** (user decision 2026-08-15). The Aura keep-alive is done and
independent of deployment (`.github/workflows/uptime.yml`, daily 03:17 UTC; GitHub disables
scheduled workflows after 60 days of repo inactivity). That workflow also carries the
**idle-connection recovery probe** (added 2026-08-23): it queries Aura, idles 11 minutes past
`max_connection_lifetime`, then reuses **the same pool** — the direct regression test for the
`SessionExpired` bug, which `run_soak_test.py --idle` otherwise only catches in a 70-minute run
nobody does per change. It deliberately does **not** live in `tests.yml`: CI's integration job
runs a *local* Neo4j container, which does not close idle connections the way Aura does, so the
probe would pass there regardless of the pool settings — a green check proving nothing. Its pool
settings mirror `dependencies.py` and must be changed together, and it is reads-only (`RETURN 1`),
so unlike the integration suite it cannot touch the demo dataset.

---

## Layer completion

| # | Layer | Status | Evidence (code) | Notes |
|---|-------|:------:|-----------------|-------|
| 0 | Empirical Validation & Model Safety | ✅ | `workers/model_validation.py`, `services/circuit_breaker.py`, `validation_corpus`, `/governance/model-gate/*` | — |
| 1 | Deterministic Identity & MDM Backbone | ✅ | `/assets` (`MERGE`, `identity_confirmed_by` required), **`POST /assets/bulk`** golden-record import, `asset_alias_map`, `services/graph.py` | EAM *connector* = Go-connector **fixture** (no SAP/Maximo) — mock by design. The golden-record **import path** is no longer missing (2026-08-22): bulk import exists, so a plant no longer has to be bootstrapped one asset at a time |
| 2 | Immutable Evidence Vault | ✅ | Supabase Storage (`kairos-vault`), SHA-256 dedup, `documents`, `POST /documents/ingest` | — |
| 3 | Multimodal Perception Engine | ✅ | OCR (NIM Nemotron), NER (NIM llama-3.2-11b-vision), voice (Groq Whisper), annotations, **P&ID topology** (`services/pid.py`) | Path A (custom YOLO+LayoutLM on GPU) = optional future accuracy upgrade, `requirements-cv.txt` |
| 4 | Temporal Reality Graph | ✅ | Neo4j, `KNOWLEDGE_EDGE` (6 props), `as_of` time-travel, blast-radius, conflict detection | All 6 designed node types now written (2026-08-17). Corpus backfill via `scripts/backfill_graph_nodes.py`: `Event` done 2026-08-23 (137/137), `Person`/`Organisation` done 2026-08-23 (102 docs, `validity: VALID`, 42 nodes; 14 unindexed documents remain an *indexing* gap) |
| 5 | Zero-Copy OT Virtualization | 🟦 | Go connector `/ot/query`, `/ot/connectors` (`MockHistorianClient`); coverage map in Python at `/assets/{id}/ot-coverage` | **Mock by design — no plant historian.** Real path (`PIWebAPIClient`) is built; set `PI_WEBAPI_BASE_URL` to go live. OPC-UA is a stub. Go `/ot/coverage` was **deleted 2026-08-16** (fabricated sensor tags); coverage now derives from *verified* topology only. |
| 6 | Quarantine Knowledge Layer | ✅ | `quarantine_items` one-way gate, `/governance/quarantine` promote / dispute / request-info | — |
| 7 | Dual-Track Governance & Adjudication | ✅ | `knowledge_conflicts`, MoC webhook (signature-verified), SLA escalation, circuit breaker, blast-radius | — |
| 8 | Operational Event & Proactive Delivery | ✅ | 8 event sources, Redis Streams, EEMUA governor, `services/brief_engine.py`, plant-state suppression, PTW dual sign-off | — |
| 9 | Structured Knowledge Elicitation | ✅ | `MicroInterviewWorkflow` (`workflows/elicitation_workflow.py`), off-boarding programmes | — |
| 10 | Telemetry-Grounded Outcome Attribution | ✅ | `workers/attribution.py` — `_attribute`, `_classify_attestation`, `_check_closeout_attestation` (pure), triggered from `POST /events/work-order` | Brownfield branch fixed 2026-08-17: `evidence_role` now branches the decision; uninstrumented assets use closeout attestation as primary; 12 service-free tests |
| 11 | Reasoning & Synthesis | ✅ | Hybrid search, `/search/synthesize`, `/search/rca-pack`, safety refusal (NIM Nemotron 3 Super 120B + Jina embed; `llama-3.1-70b` retired 2026-09-13) | — |
| 12 | Phased Deployment, Trust & Point-of-Action Interface | ✅ | Next.js frontend, `PhaseBadge`, field mode, all routes | Cross-site advisories render an honest "unavailable" panel (single-site MVP, by design) |

**Score: 12 ✅ live + 1 🟨 live-on-mock + Layer 5 🟦 mock-by-design.** The only non-real data paths
are the external-plant integrations, which are mock **by design**.

---

## Architecture ⇄ Implementation Conformance

> Design-vs-reality audit of `docs/ARCHITECTURE.md` against the code, re-run independently
> **2026-08-17**. Scored on whether each requirement is *reachable in the path the architecture
> specifies*, not merely present somewhere — the looser reading is what produced the earlier ~94%.
> ✅ **Conformant** · 🟡 **Partial** (built, simplified from spec) · 🔵 **Deferred by design** ·
> ⚠️ **Drift**. Re-run when `ARCHITECTURE.md` or a layer's core service changes.

| Layer | Verdict | Score | One-line |
|---|:--:|:--:|---|
| 0 · Empirical Validation & Model Safety | 🟡 | 94 | Corpus grows from human promotions/annotations; scores per entity type, per asset class **and per document type**; `make model-gate` exits non-zero on regression. **92 → 94 on 2026-08-23:** a run now records `validity` / `fallback_extractions` / `extraction_paths`, so a run that never reached the model can no longer be read as a measurement, and only a `VALID` run may serve as the baseline. Still not auto-run by CI/CD, and `MODEL_GATE_ENFORCE` ships off — which is what keeps this from a higher score |
| 1 · Deterministic Identity & MDM | 🟡 | 88 | Human-confirmed `MERGE` assets, alias resolution **with a confirm endpoint**, quarantine for unlinkable knowledge, **and the golden-record bulk import the architecture opens with** (`POST /assets/bulk`, 2026-08-22 — confirming authority from the verified token, partial success with per-row reporting, existing assets skipped never overwritten, cross-site rows refused *before* the existence check). The EAM *connector* is still a fixture; the import path it would feed is now real |
| 2 · Immutable Evidence Vault | ✅ | 97 | Supabase Storage, SHA-256 dedup, version chain, never-delete; supersession now propagates to ES + Qdrant. **IAM-derived access tags** now stamped at ingestion (migration 017) — all 6 of the things the spec says each artifact receives. Tags derive from KAIROS's own enforced RBAC and say so (`derived_from: kairos_rbac`); there is no external source-system IAM feed to read |
| 3 · Multimodal Perception | 🟡 | 80 | Two-path OCR, NIM NER, P&ID **vision** (Path B) + element-by-element verification gate, voice. Form/checklist parsing now has a live path to quarantine (2026-08-23); layout-awareness outstanding. **The 80 is understated and the reason was misattributed.** It was read as a handwriting-model gap; probing the CV endpoint on 2026-08-23 showed the model transcribes the handwritten notes at 0.91 confidence. The OCR path fails for two *engineering* reasons instead — a response key the parser never reads (`text_prediction.text`), and a 180 KB base64 ceiling the degraded scans exceed 11-13x. **Both fixed 2026-08-23** and all four images now return text (see Pending). The score still cannot move yet: nothing downstream reads OCR output that never reached Elasticsearch, so re-scoring waits on the one-off re-extraction, not on further code. |
| 4 · Temporal Reality Graph | 🟡 | 92 | 6 edge props ✅, time-travel ✅, blast-radius ✅, **all 6 node types now written** (Event via `OCCURRED_ON` from all 6 event routes; Person/Organisation from extraction), and **timestamp alignment now runs on the document-ingestion path** by correlating a document against sibling events for the same asset. Also fixed: `valid_to` was compared to `datetime()` as a string, which yields NULL in Cypher — conflict detection and document supersession were both matching zero rows. Existing corpus is not backfilled with the new node types |
| 5 · Zero-Copy OT Virtualization | 🔵 | 70 | Mock historian by design; `PIWebAPIClient` built; connector registry self-reports config state; OPC-UA/Honeywell/GraphQL fail loudly rather than empty-as-success. Coverage map is derived from verified topology **only — never joined to the historian tag registry**, which is half the spec's derivation |
| 6 · Quarantine Knowledge | ✅ | 97 | One-way gate, searchable+labelled, 4 review actions, SLA escalation. No per-item domain-owner assignment |
| 7 · Dual-Track Governance | 🟡 | 97 | Admin vs engineering tracks, per-criticality SLA, SPC circuit breaker, MoC webhook signature verification, **pending-MoC banner on every output type** — synthesized answers, `GET /search/`, `/search/assets/{id}` and `/rca-pack`. Conflict detection itself was inert until the `valid_to` fix (see L4). SPC has no deployment-maturity dimension |
| 8 · Event Subscription & Delivery | 🟡 | 95 | 8 sources, dedup on **all six** routes keyed by business id, correlate/late-arrival, EEMUA governor, cool-down, priority ordering, **HMAC-signed** PTW dual sign-off, pilot gate (advisory by design) |
| 9 · Knowledge Elicitation | ✅ | 95 | Micro-interviews on all 3 designed triggers, off-boarding programmes |
| 10 · Outcome Attribution | ✅ | 92 | Brownfield branch fixed 2026-08-17: `evidence_role` now routes the decision; uninstrumented assets use the human-verified work-order closeout attestation as primary evidence; `_attribute` and `_classify_attestation` are pure + service-free tested (12 tests). **No authority downgrade** on confirmed failure — audit flag only, deliberately conservative |
| 11 · Reasoning & Synthesis | 🟡 | 97 | Hybrid retrieval (exact+semantic+graph+authority re-rank), double safety refusal gate, all output types, superseded documents excluded from default retrieval, and **engineer-verified P&ID topology admitted as gate evidence** for isolation queries — carrying the edge's own authority, never a privileged one |
| 12 · Phased Deployment & Interface | 🟡 | 96 | Phase badge, field mode, point-of-action UI, **answer feedback wired to the backend**. Phase/pilot *activation* remains operational, not code |

**Overall ~91.5%** (mean of the 13 per-layer scores: 1190/13 = 91.54). L1 85 → 88 on 2026-08-22 with
the golden-record bulk import; L0 92 → 94 on 2026-08-23 with model-gate run validity and the
per-document-type cut. No layer carries a ⚠️ — L4's node-type drift closed 2026-08-17.
Streaming synthesis deliberately moved **no** score: `ARCHITECTURE.md` asks for progressive render
nowhere, so it is a latency improvement, not a conformance gain.
L10's brownfield branch was fixed 2026-08-17 (72 → 92).

### Divergences that remain

#### 🟡 L4 — the graph fills forward; `Event` is now backfilled, `Person`/`Organisation` is not

**Backfilled 2026-08-23 (Events only):** `scripts/backfill_graph_nodes.py` closes the gap between
Supabase and the graph. `--events` moved the missing 21 of 137 operational events into `Event` +
`OCCURRED_ON` — **no model calls**, every write a `MERGE`, and a second dry run reports 0 missing,
so it is idempotent. Run it after any bulk event import.

**`--entities`, two runs on 2026-08-23.** Run 1: 102 documents, **33** nodes, `validity: SUSPECT`
(`nim: 91, regex: 11`). Run 2: 102 documents, **37** nodes, still `SUSPECT` (`nim: 94, regex: 8`).

**The retry cost was the finding, and it is fixed.** Run 2 spent 102 NIM calls to gain 4 nodes,
because the gap was inferred purely from the absence of an edge — and a document that genuinely
mentions no person or organisation never acquires one, so it is indistinguishable from one never
processed and was re-extracted on every run.

`Document.entity_backfill_at` (2026-08-23) is now stamped when an extraction **reaches the model**,
and `_entity_gap` skips marked documents; `--force` ignores the marker after an NER model change.
A regex-fallback pass is deliberately **not** stamped — regex cannot emit `PERSON` or
`ORGANIZATION` at all, so marking it would bake in a miss that merely looks like an absence of
people. Verified live: gap 116 → 115 on marking one document, back to 116 under `--force`.

**Run 3 closed it: 102 documents, `validity: VALID` (`nim: 102`, zero fallbacks), 42 nodes, and
the gap fell 116 → 14 in one pass** instead of re-extracting all 116 forever.

The last 14 exposed a second version of the same wart and are now reported separately: they have
**no text in Elasticsearch**, so they can never be extracted, and counting them as "pending"
produced a run that reported 0 extractions while still claiming work remained. They are
deliberately **not** marked — re-indexing must make them eligible again — but `_partition_by_text`
now names them as an **indexing** gap rather than an extraction one. The dry run correctly says
"nothing to do".


All 6 designed node types are written as of 2026-08-17 (`Event` via `OCCURRED_ON` from all six event
routes; `Person`/`Organisation` from the extraction path). **Only newly ingested documents and newly
received events materialise them.** Backfilling the existing corpus needs a re-ingestion run
(≈1 NIM call per document) and has not been done, so the current graph reflects what has been written
since that date, not the whole corpus. The write path is closed; the gap is data, not code.

Two details that are load-bearing if this is ever touched: `OCCURRED_ON` is deliberately **not** a
`KNOWLEDGE_EDGE` — an event is a fact with its own timestamp, not a temporal assertion that could be
superseded or carry an authority level, and overloading the type would inject non-claims into every
authority-filtered query. And the label is `Organisation`, matching the uniqueness constraint in
`init_schema.cypher`; `Organization` would create a second, unconstrained label indistinguishable in
query output.

#### 🟡 L4 — timestamp handling detects drift but doesn't normalize, and runs in the wrong place
The pipeline **detects** drift beyond `TIMESTAMP_DRIFT_TOLERANCE_MINUTES` (60) and flags it for
review. Two gaps remain: the design's *normalize-to-historian* step is not implemented (no live
historian, and `canonical_timestamp` is computed but never written back), and the check runs **only**
on Layer-8 compound events — never on the document-ingestion path, where the design places it
("before committing any validity window to the graph"). Closing the second half needs a correlation
concept for documents; `compound_event_id` is events-only.

#### 🟡 L0 — per-asset-class scoring is in L0; enforcement routes through L7
Both halves are built: `workers/model_validation.py` partitions the corpus and reports
`by_asset_class` + `regressed_asset_classes`, and the **SPC circuit breaker** in L7 is the single
mechanism that halts extraction for a class. What is missing is automation — `make model-gate` must
be run by a human or a pipeline; nothing invokes it on deploy, and `MODEL_GATE_ENFORCE` ships off, so
a regression reports rather than blocks.

*(Superseded 2026-08-17: an earlier entry here claimed per-asset-class scoring lived only in L7. It
has been in L0 since the class-partitioning change.)*

#### 🟡 L8 — pilot monitoring gate is reporting-only
`GET /governance/push-volume-gate` computes peak per-operator-per-hour volume over a rolling window
and reports whether the deployment sits within EEMUA-191 norms. It **never blocks** Phase 3 at
runtime: a deployment with under 30 days of history would otherwise be unable to deliver briefs at
all. Phase activation stays a deliberate `KAIROS_PHASE` decision informed by that number.

*(Superseded 2026-08-17: an earlier entry here said this gate was "not implemented", contradicting
the layer table in the same document.)*

---

## Mock-by-design (final — not pending)

Mock because the real counterpart is an **external system KAIROS does not own**, or an enterprise
scale-out beyond the single-site MVP:

| Item | Where | To go live (if a plant is ever connected) |
|------|-------|-------------------------------------------|
| OT historian (PI Web API) | `connectors/internal/ot/client.go` | set `PI_WEBAPI_BASE_URL` + creds (`PIWebAPIClient` already built) |
| OT historian (OPC-UA) | `connectors/internal/ot/client.go` | implement `gopcua` read (stub) |
| EAM asset sync (SAP/Maximo) | `connectors/internal/eam/client.go` | set `EAM_ODS_ENDPOINT` + implement SAP ODS query (stub) |
| Cross-site pattern advisories | `frontend .../management/cross-site` | multi-site control-plane feed |

---

## Benchmarks — current numbers

**Measured 2026-08-16/17** on the shipping configuration: 37 questions, 40 NER labels,
`NVIDIA_NIM_TIMEOUT=60`. (Sweep 08-16; `run_benchmark`, `run_safety_eval` and `run_brief_eval` re-run 08-17.) Raw output: [`benchmark/RESULTS.md`](../../benchmark/RESULTS.md).
Methodology: [`docs/BENCHMARKS.md`](../BENCHMARKS.md).

| Metric | Result | Harness |
|---|---|---|
| Layer smoke checks | **13/13 pass** | `verify_layers.py` |
| Retrieval (fact reaches context) | **46/46 (100%)** CI [92–100%] | `run_benchmark.py` |
| Query answer quality | **41/46 (89.1%)**, `VALID` — **current, re-measured 2026-09-13** on Nemotron 3 Super over 46 questions (widened from 37 that day), on a clean reload with chunked NER, the linked-document search scope, provenance stubs kept out of result slots and the NIM 503 retry. 40/46 answered by NIM, 6 correct refusals, 0 fallbacks. Misses: Q02, Q09, Q24, Q41, Q46 — all retrieved the fact | `run_benchmark.py` |
| Provenance — all responses, incl. refusals | **46/46 (100%)** CI [92–100%] | `run_benchmark.py` |
| Provenance — correct answers only | **41/41 (100%)** | `run_benchmark.py` (`sourced/correct`) |
| Synthesis latency | p50 **1.5 s** · p95 **9.8 s** · mean **3.1 s** — current, 2026-09-13 on Nemotron 3 Super, 46 questions (was p50 8.2 s · mean 16.9 s on 2026-08-24, and p50 32.1 s · p95 66.0 s on 2026-08-17, both on Llama 3.1 70B) | `run_benchmark.py` |
| Entity-extraction F1 (Layer 0) | **0.805** on 40 labels — `VALID`, 0 of 15 fell back | `run_model_validation.py` |
| Model gate, in-app (Layer 0) | **0.7816** (P 0.723 · R 0.850) on **40 scored labels** of the 52-row `validation_corpus` — `VALID`, **0 of 27 extractions fell back**. 12 `COMPONENT` labels reported as `unscoreable` (2026-08-23) | `POST /governance/model-gate/run` |
| Compliance gap detection | **P 1.000 · R 0.838 · F1 0.912**, zero false positives | `run_compliance_eval.py` |
| Retrieval reach by arm | exact **33/37 (89.2%)** · semantic **35/37 (94.6%)** · hybrid **35/37 (94.6%)** (n=37, CIs overlap) — **STALE.** Measured 2026-08-17, before the 2026-08-24 `/search` test-artifact fix, and the harness doesn't inherit it even if re-run as-is (constructs `SearchService` without `supabase`) | `run_retrieval_baseline.py` |
| Proactive brief quality (Layer 8) | **6/6 graded** — structural only; content expectations unmet, see RESULTS §9 | `run_brief_eval.py` |
| Adversarial safety | **0 unsafe answers** / 15 questions — 12 refusals, S05 now answers — run validity `VALID`. Measured 2026-08-17; calls `GET /search` directly so it inherits the 2026-08-24 fix, but **not re-run since** — do not re-run on demo day (provider-quota risk) | `run_safety_eval.py` |
| Concurrency | **2275 req · 0% errors · knee at 50 VU** | `run_load_test.py` |
| Soak (60 min, cloud stores) | **PASS — no leak signal.** RSS **+8.6 MB/h** · conns +4.2/h · **0.11%** of 37,842 req · idle recovery 4/4 | `run_soak_test.py` |
| OCR accuracy, paired images | **2/4 scoreable** (2026-08-24, after **D2**'s backfill) — handwriting mean recall **0.333**, a recorded Layer 3 limitation (no separate handwriting model), not a new regression. The other 2 (degraded scans) correctly triggered the 2026-08-24 span-confidence gate and stopped at `review_required` — quarantine working as designed, not a shortfall. See [D2 executed](#d2-ocr-backfill-executed--2-of-4-documents-fixed-2026-08-24) | `run_ocr_gate.py` — read-only, **no model calls** |
| KG linkage completeness | **18/21 (85%)** linked · 1 quarantined by design · 2 unexplained · **0 dangling provenance** · 87 test docs excluded. Moved from 16/21 by the same **D2** backfill — 2 of the 4 previously-unexplained documents now have real graph edges; the other 2 remain correctly quarantined, which is the ceiling here, not a gap | `run_kg_completeness.py` — read-only |
| Cross-functional discovery | **NULL on this corpus** — the silo counterfactual does not separate at 24 documents. A corpus limit, recorded rather than hidden | `run_cross_functional.py` (spends embed quota) |

### How to read these — the caveats that still apply

- **Quote per-category rates with their n.** 15 categories, minimum n=2; at n=2 a single flip moves a
  category by 50%. `ORGANIZATION` F1 rests on n=3 — do not quote it to four decimals.
- **`ORGANIZATION` cannot be grown from this corpus.** It holds exactly two unambiguous vendors
  (Fischer, Meridian). "Rajgarh Petrochemical Complex" appears in 13 documents and is deliberately
  **unlabelled** — it reads equally as ORGANIZATION or LOCATION, and a ground truth that punishes a
  defensible answer is worse than a smaller one. Raising n needs **new source documents**.
- **A `VALID` entity-F1 means zero fallbacks.** 15 of 15 extractions ran on the NIM model with zero timeouts and zero JSON parse failures. This successfully validates the fixes for both the timeout latency issues and the JSON truncation issues.
- **Per-document-type is the informative cut** (added 2026-08-23, the PS criterion that had no
  runner). Measured: `ptw` **1.000** (6 labels) · `procedure` **1.000** (9) · `shift_log` **1.000** (2)
  · `inspection_report` **0.706** (16) · `oem_manual` **0.600** (7, precision 0.462). The model is
  effectively perfect on structured, templated documents and loses accuracy on prose-heavy OEM
  manuals — a shape the per-entity-type and per-asset-class cuts both hide. Small n applies: at 2–9
  labels a single flip moves a type substantially, so treat `shift_log` and `procedure` as
  directional. It costs **zero** extra model calls because every partition shares the run cache.
- **Quote the gate's F1 with `scored_labels`, never alone.** 0.7816 is measured on the **40** labels
  that are both annotated in the corpus and requested by the prompt. The other 12 are `COMPONENT`,
  a type the extractor is never asked for, so scoring them measured the corpus's label space rather
  than the model — and it cost twice, booking a false negative on `COMPONENT` *and* a false positive
  on whatever in-taxonomy type the model gave the same span. Excluding them moved F1 0.6733 → 0.7816
  and recall 0.654 → 0.850. **The 12 labels are a real gap to close** (either teach the prompt
  `COMPONENT` or remap the ground truth), just not a model defect.
- **The in-app gate's number is not a regression from the 0.7317 in its own history — it is the first
  trustworthy number, and the old one was flattering the model.** Every gate entry before 2026-08-23
  was written without a validity field, and the one audited on 2026-08-22 had **52 of 55 extractions
  fall through to the regex path**, which only matches `ASSET_TAG`. That is why those runs show
  `ASSET_TAG` at 1.000 and `PERSON` / `COMPONENT` / `ORGANIZATION` at 0.000: the regex's output was
  being attributed to the model. **Do not quote any gate entry lacking `validity: "VALID"`**, and do
  not read the drop as the model getting worse. The two figures in the table above are also *not*
  comparable to each other — different corpora (40 curated labels vs the 52-row live
  `validation_corpus`) and different harnesses.
- **Compliance F1 drifts downward as humans legitimately promote knowledge.** Its ground truth is
  derived from the static dataset manifest, so evidence promoted into the graph afterwards reads as a
  false negative. Five of six FNs in this run are one promotion on EQ-101 (`PROMOTED-f17b1416…`, a
  verified `procedure`), which genuinely covers those clauses. **The truth table is deliberately not
  amended** — grading a system against its own output measures nothing. Precision, the
  safety-relevant direction, stays 1.000.
- **All 3 refusals are genuine**, verified against the graph: no asset involved carries an
  authoritative (≤L3) source for the parameter asked. Q25 is the instructive case — the bulletin
  revising the HE-3xx limit to 16.2 bar is linked to **HE-301**, while Q25 asks about **HE-302/303**,
  so answering would mean extrapolating a safety-critical limit onto assets no source covers. The
  grader counts a refusal as correct, so this was audited specifically: raw score = adjusted score.
- **Latency is the honest cost of the 60 s cap.** Lowering the cap cannot make inference faster; it
  truncates the number and moves work to the fallback tier. Direct probing of NVIDIA's endpoint
  returned 8.6 s–>90 s for identical work with no rate-limit headers. `NVIDIA_NIM_TIMEOUT` must also
  stay **under** the frontend's 90 s budget for `POST /search/synthesize`.
- **Time-to-answer is a floor set by corpus size.** BM25 finds the answer-bearing document at mean
  rank 1.35 across ~20 documents — keyword search is already good at this scale, so there is little
  room to improve on it. The 120 s/document reading assumption is an input, not a measurement.
- **The soak says "no leak signal", not "no leak".** `+8.6 MB/hour` clears the harness's FLAT
  threshold (`<10`) but sits at 86% of it, measured across a band that oscillates ~11 MB over 59
  samples — the slope's uncertainty is plausibly its own size. Quote it as *no leak signal detectable
  over a 60-minute window*, never as "memory is flat", and do not extrapolate to a shift. The 41
  errors (0.11%) are **counted, not classified**: the harness captures no status codes, so their
  attribution to cloud-store resets is an inference from their burst shape.
- **Neither the load sweep nor the soak speaks to scale.** 50 VU and a 24-document corpus are not
  evidence for 10k assets, and the soak speaks to hours, not days. Both are **reads-only** — the
  model path is never exercised by either.
- **Time-to-answer's reduction fell 25.6% → 9.5%, for two honest reasons, not a regression.** BM25's
  mean rank *improved* on the wider question set (1.52 → 1.35), so the baseline itself got better;
  and KAIROS machine time rose (15.7 s → 26.7 s) because the 60 s cap keeps work on NIM instead of
  truncating onto a faster fallback. The old figure also used a **180 s** client budget — twice what
  the browser allows — so it counted calls the product would have aborted. Now pinned to the
  frontend's real 90 s budget, paced like `run_benchmark.py`.
- **Retrieval-baseline's first run measured semantic-only at 0/37**, which is what exposed a real
  regression: the superseded-document filter added a Qdrant filter on `status`, Qdrant Cloud rejects
  filters on unindexed fields with HTTP 400, and `hybrid_search`'s `return_exceptions=True` swallowed
  the error as a log line. Hybrid retrieval had silently degraded to Elasticsearch-only across the
  whole system, and no test caught it — only this baseline did. Fixed by adding `status` to
  `PAYLOAD_INDEXES` in `scripts/init_qdrant.py`. Report hybrid as *matching*, not beating, the best
  single arm — margins are within the n=37 confidence interval.
- **The adversarial-safety score was earned, not observed — three defects had to be fixed before it
  measured anything, each found by the harness itself:** run 1 read `0 unsafe · VALID` but was a
  false green (the harness didn't follow redirects, so all 15 requests hit a 307 and returned
  nothing — zero answers scored as zero unsafe); run 2 found 2 real unsafe answers (a value stated
  for the wrong asset, and a fabricated extrapolation no source covers); run 3 over-corrected to
  `SUSPECT` (15/15 refused, including answerable questions); run 4 reached `0 unsafe · 14 refusals ·
  VALID` after three code fixes in `services/llm.py` (a classification regex too literal to match
  "maximum allowable operating pressure"; the authority anchor comparing evidence to evidence instead
  of evidence to the question's actual asset; family references like "HE-3xx series" escaping the
  anchor entirely). Run 5 is current: **S05 now answers** after engineer-verified P&ID topology was
  admitted as gate evidence.
- **The proactive-brief eval's 7 unmet soft targets are correct aspirational targets, not defects.**
  They're cross-references to related assets and prior-event terms the embedding-based brief engine
  doesn't surface from its retrieval window. Promoting them to graded (`must_all`) would need either
  a wider retrieval window or structured link-traversal in `BriefEngine` — not built, left as
  `should_contain` (reported, not scored) until that path exists.

---

## Open decisions — blocked on a human call, not on work

> Everything here is **specified, understood and cheap to execute**. None of it is waiting on
> engineering; each is waiting on someone deciding what the right answer is. Kept separate from the
> [Backlog](#improvement-backlog) so a reader can tell "nobody has built this" from "nobody has
> decided this".

| # | Decision | Options | Consequence of not deciding | Recorded |
|---|---|---|---|---|
| D1 | **What makes an OCR extraction quarantine?** | (a) leave it on the weighted average — status quo, the worst scan passes at 0.719; (b) quarantine if **any** span < 0.7; (c) quarantine on a `min_span_confidence` floor | Garbled text from degraded scans reaches the **canonical graph** as verified-grade fact. The safety-relevant direction, and the only open item with a data-integrity consequence | Backlog #15 |
| D2 | **Re-extract the 4 image documents?** | Requires a one-off backfill writing to Neo4j + Qdrant + Elasticsearch + Supabase | **Decided and executed 2026-08-24, with explicit per-write authorization** (the standing no-cloud-writes rule requires that in-session for each write; given here). 2 of 4 completed the full pipeline; 2 correctly quarantined by the span-gate instead of indexing — see [D2 executed](#d2-ocr-backfill-executed--2-of-4-documents-fixed-2026-08-24) | Pending, D2 executed |
| D3 | **The 12 `COMPONENT` labels in `validation_corpus`** | (a) teach the prompt the type; (b) remap the ground truth; (c) leave them `unscoreable` | Model-gate F1 keeps carrying an asterisk. Deliberately deferred — nothing consumes the type and 3 distinct entities cannot validate adding one to production extraction | Pending |
| D4 | **Full-suite pass count** | Needs a throwaway Supabase project + `CI_SUPABASE_*` | **Decided 2026-08-23: not doing it.** No secrets, no per-push provider spend. Accepted consequence: no current full-suite pass count; the service-free tier is the only enforced backstop | Pitfalls, CI reference |
| D5 | **Attention-list row wording** | Settled 2026-08-23 — `Overdue quarantine · {input_type}`, reasoning in `attention-list.tsx` | None; recorded so it is not re-opened | Verification snapshot |
| D6 | **Which asset-list columns to render, and how** | `GET /assets/` now ships `open_work_orders_count` + `compliance_gap_count` on every row and `AssetSummary` carries them, so the **data is available and the backend work is done** | Two columns a design review asked for stay unrendered. Purely presentational — no correctness or safety consequence. Note `docs/design/BACKEND-ASK.md`, referenced by the original ask, **does not exist in this repo** | Pending, B-5 |
| D7 | **Should a total embedding failure raise instead of degrading silently?** | `_embed_ollama` returns `[]` rather than raising (`services/llm.py`) and `search_service` gathers with `return_exceptions=True`, so search silently degrades to ES + graph with one log line | **Decided 2026-08-23: leave it.** Changing failure semantics on the retrieval hot path is a bigger change than the symptom justifies. Recorded so it reads as a decision, not an oversight — do not "fix" it without re-opening the decision | Pending, B-1 |
| D8 | **Do `e2e_shift_log.txt` and `kairos_ingest_test.pdf` count as corpus?** | Neither appears in `dataset/00_Reference/dataset_manifest.csv` **or anywhere under `dataset/`**; the manifest holds exactly the other 21 | **Decided 2026-08-23: they do not.** `e2e_` and `kairos_` added to the predicate — both name a file after this system or its harness, never after plant equipment, and both were verified against the whole vault to match only their two targets. A `_test\.ext` stem rule was **rejected**: it would also swallow a plausible real `hydro_test.pdf`. Linkage re-run in the same change: **16/21 (76%)**, four unexplained unchanged | Benchmarks, `RESULTS.md` §12 |

**D1 is the one that matters** — it is the only open item with a data-integrity consequence. D2 and
D7 are decided (do not re-open them without saying so); D3–D6 are cosmetic or accepted. If only one
decision gets made, make D1.

**D8 was executed as one package (2026-08-23)** — predicate, harness re-run and every published
figure moved together, because splitting them is exactly how the linkage number went stale before.
A manifest **allowlist** was rejected as the mechanism even though it would be exact here:
`POST /documents/ingest` is a live path, and an allowlist would make every newly ingested document
invisible in the graph. The denylist stays, and widening it needs the same evidence bar.

### Next actions — in order, with their safety class

> For an agent picking this up cold. **Safety class is the first thing to read**: 🟢 writes nothing
> outside the repo · 🟡 spends provider quota · 🔴 writes to a cloud store (**forbidden** without an
> explicit ask — see the rule at the top of `AGENTS.md`).

| Order | Action | Class | Blocked by | Est. |
|---|---|---|---|---|
| 1 | **Decide D1**, then add the predicate to `services/ocr.py` | 🟢 | a human decision | ~1 h |
| 2 | ~~Re-run `run_benchmark.py`~~ **Done 2026-09-13** — 41/46 (89.1%), `VALID`, on Nemotron 3 Super (46 questions); see `RESULTS.md` §2. Unblocks Backlog #13 | ✅ | — | — |
| 3 | **Record a synthesis verdict** when 2 runs (Backlog #8) | 🟢 | step 2 | ~1 h |
| 4 | **Consolidate the two downscale helpers** (Backlog #16) | 🟡 one P&ID vision call to re-validate | nothing | ~1 h |
| 5 | **Decide D8**, then widen the corpus predicate + re-run `run_kg_completeness.py` + update the quoted figure — one commit | 🟢 | a human decision | ~30 min |
| 6 | **Form-parsing layout pass** (Backlog #6) | 🟡 | nothing | ~1 d |
| — | **Re-extract the 4 image documents** — would move the OCR gate, L3's score and linkage 16/21 → 20/21 | 🔴 | **D2 — do not do this** | — |
| — | **FastAPI major upgrade** (Backlog #2) | 🟢 | see caution below | 1–2 d |

**Caution on the FastAPI upgrade specifically.** It is code-only, but it carries real breakage risk
across every router *and* there is **no current full-suite pass count** to catch a regression (D4) —
the 476-test service-free tier is the only backstop, and it cannot exercise queries or routing. Do
not start it casually. `ecdsa` has no released fix regardless, so it closes 7 of 8 advisories, not 8.

**What is already done and must not be re-opened:** the OCR parse and size-ceiling defects (fixed and
live-verified 2026-08-23), the "no handwriting model" attribution (disproven — the model reads it at
~0.90), the composite index (impossible by construction), Go `/ot/coverage` (deleted on purpose),
supervised ML (settled, permanent), and everything under
[Reported UI/wiring issues](#reported-uiwiring-issues--triaged-and-fixed-2026-08-23) — in particular
`/system-health` is **not** an outage (all four providers answer 200) and the graph/conflict noise is
test pollution filtered on read, **never** a cleanup script against a cloud store. Each is recorded
with its reasoning in this file; check before re-filing any of them as a gap.

---

## Improvement backlog

> **Numbers are retired, never renumbered.** The gaps are deliberate: items are cross-referenced by
> number from elsewhere in this file and from `e2e-sweep.md`, so reusing a number silently
> re-points an existing reference at different work. Closed so far — **1** streaming synthesis
> (2026-08-23), **3** surface held briefs (2026-08-23), **4** soak test (2026-08-22),
> **5** event reorder buffer (2026-08-23 — the entry was wrong; it was already implemented),
> **9** model supply-chain integrity (2026-08-23), **10** per-document-type extraction accuracy
> (2026-08-23), **11** KG linkage completeness (2026-08-23), **12** cross-functional discovery
> (2026-08-23 — measured; NULL on this corpus).

### Tier 1 — highest value

| # | Improvement | Why it matters | Est. |
|---|---|---|---|
| 15 | **OCR confidence gating — the number is honest, the gate is not yet** | `overall_confidence` now reports the model's own length-weighted per-span confidence instead of a hardcoded `0.95` (2026-08-23), so a garbled scan and a clean one are finally distinguishable. **The hazard is not closed.** The worst corpus document scores **0.719 — above the `0.7` quarantine line — so it would still reach the canonical graph**, carrying `EO-xxx` for `EQ-xxx` and a mangled date, while 4 of its 22 spans sit below 0.7 and one at 0.253. A single average cannot express "4 of 22 spans are unreliable", and the dangerous failure here is one misread value (`16.2 bar` as `18.5 bar`), not a poor mean. Closing it means gating on **shape** rather than average — quarantine when any span falls below `_LOW_CONFIDENCE_SPAN`, or on a `min_span_confidence` floor. **This is a policy decision, not a code gap:** it changes what quarantines, and over-tightening pushes clean documents into a review queue, which is the failure mode `ARCHITECTURE.md §3` explicitly warns against. The signals (`min_span_confidence`, `low_confidence_spans`, `span_count`) are already emitted and `ocr.low_confidence_spans` logs every affected document, so the gate is one predicate once the rule is chosen. | ~1 h once decided |
| 2 | **Backend dependency advisories — 10 left, both blocked upstream** | Was 16 across 4 packages; **protobuf and setuptools cleared 2026-08-23** and their suppressions removed, so the gate now catches a regression in either. The unlock was one transitive package: `setuptools` was **not** a stale cap — OTEL 0.45b0 imported `pkg_resources`, which setuptools 78+ removes, so lifting it alone crashed `api.main` on import. OTEL ≥0.49b0 drops `pkg_resources` but needs protobuf 5, which `grpcio-tools 1.62.3` forbade; `qdrant-client` asks only for `grpcio-tools>=1.41.0` and `temporalio` declares `protobuf>=3.20` with no ceiling, so pinning **`grpcio-tools>=1.66`** moved protobuf to 5.29.6 and OTEL to 1.28.0/0.49b0 with **both clients untouched**. What is left is genuinely blocked, not deferred: **`starlette 0.37.2`** (7 advisories) is pinned transitively by `fastapi==0.111.1` (`>=0.37.2,<0.38.0`) and the fixes run 0.40.0 → 1.3.1, i.e. a **FastAPI major upgrade** — a separate piece of work with real breakage risk across every router. **`ecdsa 0.19.2`** has an **empty `fix_versions`**: no released fix exists at all, so nothing can be done but re-check upstream periodically; it arrives via `python-jose[cryptography]`, and dropping that dependency is the only other lever. Dependabot PR #22 (41-package group) remains the blunt alternative. | FastAPI major: 1–2 d |

### Tier 2

> **#4 (soak test) closed 2026-08-22** — PASS, no leak signal: RSS +8.6 MB/h, connections +4.2/h,
> 0.11% errors over 37,842 requests, idle recovery 4/4. Numbers, raw output and the three things the
> run does **not** establish are in [`benchmark/RESULTS.md` §10](../../benchmark/RESULTS.md). The
> number is retired rather than reused, because items 5–14 are cross-referenced by it elsewhere.

| # | Improvement | Why it matters | Est. |
|---|---|---|---|
| 6 | **Form / checklist parsing — path is live and the destination is settled; layout-awareness is the remaining half** | **The dead stub is gone (2026-08-23).** Its docstring claimed "form extraction is handled by Temporal activities" — untrue; nothing in `document_pipeline.py` touched forms, so the comment was hiding the gap rather than pointing at an implementation. **The destination question that kept this unbuilt is answered: quarantine, always.** `api/services/forms.py` writes no `KNOWLEDGE_EDGE` and assigns no authority level, because a ticked checkbox has neither a signer nor a citable source — Layer 6's one-way gate with human-only promotion is exactly the mechanism for this, and `tests/test_form_extraction.py` asserts via AST that the module cannot write to the graph. Reuses the existing `field_observation` `input_type` (a form field *is* field input) so no CHECK-constraint migration is needed, and each item carries a note stating its own ceiling so a reviewer is not relying on a module docstring. **What is left is the title's actual subject.** The parser is deterministic `label: value` + checkbox state, no model call. Measured on the two real corpus forms: 2 and 1 fields — high precision, low recall. That trade is deliberate for a one-way gate (noise trains reviewers to bulk-approve), and live data already caught one over-match: an unspaced hyphen was splitting asset tags, turning `XV-203` into label `XV` / value `203`. True layout-aware parsing — cell geometry, ruled boxes, multi-column tables — needs a vision model and is the upgrade path. | ~1 d for the vision pass |
| 16 | **Two copies of the inline-image downscale** | `OCRService._shrink_for_inline` and `PIDService._fit_b64` solve the same problem in two modules, and `_NIM_IMAGE_SIZE_LIMIT = 180_000` is defined in both. They were written independently — which is *why* Path B never hit the OCR size bug — and were deliberately not merged when the OCR fix landed, because consolidating touches the live-validated P&ID path. Two behavioural differences to preserve if merged: the OCR copy tries an **unscaled JPEG first** (which alone took the corpus's 11.3x-over scan from 2,027,896 to 102,628 base64 chars, costing no resolution, where `_fit_b64` starts at 0.85 and always resizes), and it returns raw bytes rather than an encoded string. Cross-referenced in both docstrings so they cannot drift unnoticed. | ~1 h + one P&ID vision call to re-validate |
| 7 | **Graph query policy — hot-asset Redis precompute only** | Four of the five `ARCHITECTURE.md §7` requirements are now closed or settled. **Composite index:** impossible, settled 2026-08-22 (`asset_id` is a node property, the validity window a relationship property). **Traversal depth limits:** `graph.MAX_TRAVERSAL_DEPTH` is the single policy bound, interpolated into the one variable-length traversal, and `tests/test_graph_query_policy.py` fails if any unbounded `*` ships. **Authority pre-filter before traversal:** no multi-hop query exists for it to apply to — the Layer 4 hot path is a 1-hop expand, where filter-after-expand *is* the plan (`PROFILE`: `NodeUniqueIndexSeek` → `Expand(All)` → `Filter`). **Query-perf regression test:** `make graph-perf` (`scripts/verify_graph_perf.py`) asserts plan **shape**, so it catches the anchor regression that already happened once without going flaky as the corpus grows. **Left: hot-asset Redis precompute.** Deliberately not built — at this corpus size it is speculative, and a precomputed view that goes stale after a knowledge write is precisely the 'silent propagation of outdated information' the architecture calls the most dangerous failure mode. Build it when a `PROFILE` on a real corpus shows the seek+expand is no longer enough, and give it explicit invalidation on every `KNOWLEDGE_EDGE` write. | 1–2 d when triggered |
| 8 | **OCR gate built 2026-08-23 — and it found the OCR path is returning nothing** | **The stated blocker was false.** This entry said "OCR has no labelled ground truth in the corpus"; `dataset/00_Reference/dataset_manifest.csv` declares **three pairings by design** — files 20→6, 21→12, and 22/23→24 (`shift_log.txt`, "same 2 events"). The dataset was built for this test. `benchmark/run_ocr_gate.py` scores **recall of operationally salient tokens** (asset tags, measurements with units, standards references, dates) against the clean sibling's text — deliberately not character error rate, which weights whitespace equally with reading `16.2 bar` as `18.5 bar`, the most dangerous error this system can make and a real limit in this corpus. Recall not F1: an OCR pass that drops a pressure limit is the failure being caught; extra tokens are only noise. **First run scored nothing, and that was the finding** — it surfaced two engineering defects in `services/ocr.py`, both **fixed and live-verified 2026-08-23** (see Pending). The gate is still `UNSCOREABLE` until the four images are re-extracted and re-indexed, because this harness reads Elasticsearch and makes no model calls of its own. An image with no OCR output is reported `UNSCOREABLE`, never as recall 0.0: "produced nothing" and "produced wrong text" are different failures, and averaging the first into an accuracy number reports the wrong problem. **Synthesis gating is deliberately NOT folded in.** Quality is already measured by `run_benchmark.py` at ~30 min of model quota per run; a gate that expensive cannot run per change. The honest form is to record a verdict when the benchmark runs, not to make the gate run the benchmark. | OCR done; synthesis verdict ~1 h |

| 17 | **`/assets/bootstrap` is half-wired — the lists are hardcoded and the alias buttons call nothing** | Reported from the UI 2026-08-24: confirming an identity or accepting/rejecting an alias appears to work, then every row returns on reload. **`Confirm identity` is genuinely live** — it calls `confirmAssetIdentity()` → `POST /assets`, which sets `identity_confirmed{,_by,_at}` and writes an `audit_log` row. Everything else on the page is not. **Both queues are frontend constants**: `SEED_PROVISIONAL` and `SEED_ALIASES` in `frontend/src/app/(app)/assets/bootstrap/page.tsx`, rendered undisclosed as if extracted — which breaks the live-only rule in `CLAUDE.md` (fetchers throw; a fixture is never presented as real data). **The alias Confirm and Reject are the same function**: both are `setAliases(l => l.filter(...))` with no API call, so Reject silently records an acceptance-shaped no-op. Row removal after a confirm is local state, not a refetch, which is why the seeds come back. **Two-thirds of the backend already exists**: `POST /assets/{asset_id}/aliases/{alias}/confirm` and `GET /assets/{asset_id}/aliases` are implemented and simply never called. **Two real gaps before this can be finished**: there is **no reject-alias endpoint at all**, and **nothing lists provisional assets** — `GET /assets` exists but was not verified to filter on unconfirmed identity, so the provisional queue needs either a new endpoint or a documented filter. Wiring the alias half alone would ship a real Confirm beside a still-fake Reject, which is worse than two honest fixtures. **Demo note:** every `Confirm identity` click writes `P-207` / `HX-14B` / `V-88` plus audit rows into cloud Neo4j + Supabase. `POST /assets` MERGEs and upserts so repeat clicks are idempotent and will not error, but the seeded assets are real once clicked. | ~2 h frontend once the two endpoints exist |

### Measurement gaps — PS evaluation criteria without a runner

**None remain (2026-08-23).** `ARCHITECTURE.md §9` names the thirteen harnesses, and the last three
criteria without a runner closed together: **#10** per-document-type extraction accuracy, **#11** KG
linkage completeness, **#12** cross-functional discovery. The heading is kept rather than deleted
because those numbers are cross-referenced by number from elsewhere in this file — re-open it only if
a new PS criterion arrives without a harness.

### Tier 3 — architectural ceilings

| # | Improvement | Why it matters | Est. |
|---|---|---|---|
| 13 | **A real agent loop — the premise for the recommended form is stale; re-measure first** | Still true that every LLM call is single-shot with no planning or tool-use loop, and that this caps an Innovation score. **But the recommended form — a bounded re-retrieval loop on the refusal path — no longer targets anything.** It was justified by the "four honest misses" (Q02, Q07, Q09, Q29), which `RESULTS.md` describes as the gate refusing. Probed live 2026-08-23: **none of the four refuses, and all four now answer correctly** — Q07 returns all three expected valves (`XV-203`, `XV-204`, `PG-18`), Q02 contains "thermal cycling", Q09 contains 2018/2021/2025, Q29 names the hydrotest procedures. Two of the four could never have been refusals at all: `classify_query_category` returns `None` for Q02/Q09/Q29, and both gates only fire for a safety-critical category. They were fixed by the intervening work (the `valid_to` NULL fix, the restored `asset_id_unique` anchor, verified topology admitted as gate evidence). **Do not build the loop against these four.** Re-run `run_benchmark.py` first — the 33/37 figure predates those fixes and understates current quality. If a real refusal population exists after that, size the loop against it; otherwise this reduces to the generic-agent question, which the architecture's human-authority position argues against. | re-measure first |
| 14 | **Custom P&ID parser (Path A)** | `requirements-cv.txt` pins the YOLOv9 + LayoutLMv3 stack but it is intentionally not installed. Path B (cloud VLM) works and every element is human-verified, so this is an accuracy upgrade, not a gap. | 1 w+ |

### Known limitations — recorded, not planned

- **No supervised ML, permanently — settled, not pending.** PyTorch / scikit-learn / LightGBM are
  not installed and will not be. A 24-document corpus cannot train a model that beats the
  deterministic path. The quantitative story is SPC control charts, Wilson intervals, RRF and 2σ
  baselines — statistical methods where the data supports them. **Do not re-file this as a gap.**

  *Why it stays unbuilt:* any supervised model trained on 24 documents cannot outperform the
  deterministic path, and shipping one would mean presenting a model fit on nothing as a credential.
  The first question it invites — "what was your training set size?" — has no good answer.

  *Framing for any deck or writeup:* "Statistical methods where the data supports them — SPC control
  charts for drift detection, Wilson intervals on all reported rates, RRF for retrieval fusion.
  Supervised ML is roadmap, not shipped: a 24-document corpus cannot train a model that outperforms
  the deterministic path, and we chose not to ship one that looks impressive and measures nothing."

  *The threshold at which this changes:* enough verified operational history to fit a distribution
  per equipment class. `ARCHITECTURE.md §8`'s extraction anomaly detection is the natural first step
  and is plain statistics, not a trained model — neither is reachable on the present corpus.

- **The `(asset_id, valid_from, valid_to)` composite index cannot exist — settled 2026-08-22, do not
  re-file.** `ARCHITECTURE.md §7` asks for it, but `asset_id` is a **node** property and the validity
  window is a **relationship** property, so no single entity carries all three. `PROFILE` confirms the
  hot path is anchor → `Expand(All)` → `Filter`, and a relationship index is not consulted for edges
  reached by expansion. What actually mattered was the **anchor**: restoring the missing
  `asset_id_unique` constraint changed the plan from `NodeByLabelScan` (10 rows / 11 dbHits) to
  `NodeUniqueIndexSeek` (1 row / 2 dbHits). Reasoning is recorded in `init_schema.cypher` and the
  `get_asset_knowledge_at` docstring, both of which previously claimed the composite index existed.

- **Go `GET /ot/coverage/{id}` is deleted on purpose — do not restore it.** Removed 2026-08-16 because
  it returned hardcoded `{asset}-VIBE` / `{asset}-TEMP` / `75%` for every asset, which Layer 5 forbids
  outright. Two tests pinning that behaviour survived until 2026-08-22 — one asserting "unknown asset
  falls back to mock coverage, still 200", i.e. *requiring* the fabrication. They were removed with a
  comment saying why, because the obvious way to make a red suite green is to re-add the route.
  Instrumentation coverage derives from **verified topology only**, in Python, at
  `GET /assets/{id}/ot-coverage`.

- **Dependabot version updates cannot run on push — do not try to wire it.** `interval` accepts only
  daily / weekly / monthly; there is no event trigger and no API to force a run (the "Check for
  updates" button is UI-only). Set to **daily** 2026-08-22. It also *looks* idle when working: every
  ecosystem groups all patterns into one PR, and an open group PR is **rebased in place** rather than
  replaced. The per-push equivalent is `.github/workflows/deps-audit.yml`.

- **Compliance counts are computed live**, O(clauses × assets) with a subquery per pair; `EXPLAIN`
  confirms `CartesianProduct`, and the dashboard variant is deliberately unbounded because a `LIMIT`
  would silently undercount a compliance posture. At 12 clauses × 10 assets it is instant. Materialise
  into Supabase on a scheduled scan only when scaling past a few thousand assets.
- **Retrieval is RRF, with no cross-encoder rerank or query planner**, and dedupe is per-document so a
  long document contributes one chunk. Retrieval scores 37/37, so there is nothing to gain on this
  corpus — but RRF scores measured **0.0156–0.0325 across all six hits of one query**, i.e. it barely
  discriminates here. Invisible at 20 documents, material on a real archive. Revisit when the corpus
  grows.

---

## Pending

### Reported UI/wiring issues — triaged and fixed 2026-08-23

A second external list (11 items, reported against a local build) was verified item by item against
`main`, the live stack and the databases — not against the report. **All fixes are frontend or
read-path only; nothing here writes to a cloud store.**

| # | Reported | Verdict | Fix |
|---|---|---|---|
| 1 | `/rca` shows retry, backend works | Real. Reporter's fix was **not in the repo** | `getRcaPack` inherited the 8 s write default on a call that measures ~90 s, so the abort always beat the response. Both synthesis endpoints now share `SYNTHESIS_TIMEOUT_MS` |
| 2 | Copilot conversation resets on navigation | Real, but **a feature, not a defect** — `useState` with no persistence layer of any kind | Not built. Needs its own scope (lifetime, per-tab vs per-user, logout behaviour) |
| 3 | `/system-health` shows all models down | **Not a backend fault.** All four providers returned HTTP 200 when probed inside the container; zero probe failures in 24 h of logs | Monitoring is opt-in and off by default, and the off state rendered as `degraded` — a pulsing amber dot identical to a real outage. Added an `idle` tone that does not pulse |
| 4 · 8 | Copilot shows "Low confidence · 0%" | Real, and the highest-value item | The backend returns `confidence: null` when the model emits no parseable `CONFIDENCE:` marker; the client coerced it to `0`. **130 of 573 non-refused answers (~23%)** were affected. `CopilotAnswer.confidence` is now `number \| null` — the compiler found both readers — and renders "Confidence not reported". The RCA path had the identical bug behind a `Number.isFinite` guard that `?? 0` made unreachable |
| 5 | Quarantine actions scroll out of reach | **Already fixed** — actions live in an `absolute bottom-0` footer inside a `fixed inset-0` drawer with `pb-24` clearance and body scroll locked; they cannot scroll away | None needed |
| 6 | Horizontal scrollbar under Recent Signals | Real | `overflow-y-auto` leaves `overflow-x` computed as `auto`; the rows overflow by 4 px — exactly the `pr-1` padding. Added `overflow-x-hidden` to both copies (the graph page had the same pattern) |
| 7 | Supersede dialog affects page scroll | **Did not reproduce.** Lock works, no jump, position restored | None. Only remaining mechanism is scrollbar-gutter shift on a machine with always-visible scrollbars — ask the reporter to confirm before spending time |
| 9 · 11 | Graph UI bug / blank item | Unverifiable — no reproduction steps, one entry submitted empty | — |
| 10 | Conflicts show `DOCUMENTED BY` and `— vs —` | Real, both halves | See [Graph and conflicts were rendering test pollution](#graph-and-conflicts-were-rendering-test-pollution--fixed-2026-08-23) below |
| — | No theme control on the landing page | Real, and **deliberately not fixed** | `globals.css` documents that surface as single-palette; its `--lp-*` tokens have no dark variant, so mounting `ThemeToggle` would ship a visibly dead control. Needs a landing dark palette authored first |

**Found while fixing, not on the list — the graph could hang forever.** Two independent call sites
invoked `getKnowledgeGraph` with no `catch`: the page used a bare `.then()`, and `KnowledgeGraph`
awaited inside an async function called without one. The fetcher throws by design under the
live-only policy, so a timeout became an unhandled rejection, `setLoading(false)` never ran, and the
canvas bounced its dots while the tiles read "Loading nodes" — no error, no retry. The page now uses
`useFetch` like every other page; the canvas has its own error state. Verified live.

---

### Graph and conflicts were rendering test pollution — fixed 2026-08-23

Both surfaces were dominated by rows the test suite wrote into the vault. **Neither fix deletes
anything**; both filter on read.

**The graph.** `GET /assets/{id}/knowledge` returned **60 edges for EQ-101, ~53 of them pointing at
`test_*` files**, drawn as an unreadable hairball of one repeated relationship type.
`run_kg_completeness.py` had already solved this for the benchmark and *reported* its exclusions;
the API had never been given the same rule. The predicate now lives in `api/services/corpus.py` and
the harness imports it, so there is one definition rather than two. **EQ-101 is now 7 facts with
`excluded_test_documents: 53`**, surfaced in the UI as "53 test documents hidden".

**Conflicts.** 93 of 94 stored conflicts were `DOCUMENTED_BY` — two documents describing one asset,
which is what an archive *is*. `detect_conflict` fires on a shared `relationship_type` from
different documents and **never compares what they assert**, because a `KNOWLEDGE_EDGE` has no
value property; that absence is also why those rows carry no `value` and rendered "— vs —".
`GraphService.NON_ASSERTING_RELATIONSHIPS` now excludes provenance and structural types before the
query runs, and `GET /governance/conflicts` applies the same set when reading rows written earlier —
in the query, not in Python, so `count` and `range` stay honest. **The queue is now 1 conflict: the
real HE-301 pressure contradiction (18.5 bar vs 16.2 bar), which the noise had pushed off page one.**

The conflicts column reads `value` when present and names both sources when not, so the HE-301 row
is unchanged while the rest show real provenance instead of an em dash. "vs" is reserved for a
genuine disagreement.

> **Not done, and deliberately:** narrowing detection to compare *values* would need a value
> property on every edge — a schema change plus a backfill, i.e. a cloud write. Revisit only if
> edges ever carry their asserted value.

---

### `/search` was also serving test pollution ahead of real evidence — fixed 2026-08-24

Same failure class as the graph/conflicts entry above, one layer over: `/search` never applied
`api/services/corpus.py`'s test-artifact filter at all — not "applied it too late", **never called
it**. `SearchService`'s graph retrieval source returns one hit per `DOCUMENTED_BY` edge with no
relevance signal beyond RRF rank, so on an asset with heavy test-sweep history it filled every
result slot with content-free `"<asset> documented by <id>. Verification: unverified."` stubs
before real evidence was ever ranked.

**Found via the 2026-08-24 `run_benchmark.py` re-run** (triggered because `personnel` regressed
0/3 sometime between the 2026-08-17 and 2026-08-22 checkpoints — unrelated to that day's OCR work,
which landed after the regression was already present). Confirmed live on `EQ-101`: **56 of 68 raw
retrieval candidates were test artifacts**; `GET /search?asset_id=EQ-101&limit=20` returned 18 of 20
results as graph stubs, and the document actually containing the answer
(`DOC-4O66SJPAHVBY` — a work-order sign-off form naming both the technician and the reviewing
engineer) never appeared even at limit 20.

**Fix.** `search_service.py` / `search.py` — `SearchService` now takes an optional `supabase` client
and excludes test-artifact candidates via `corpus.test_artifact_ids()` **before** `_fuse()`
truncates to `limit`, not after — filtering post-truncation would still lose real evidence to junk
that had already outranked it. Reuses the existing predicate; no new filtering logic, no cloud
writes, no schema change.

**Verified in order, not just claimed:**
1. Live re-test of the exact failing call — `DOC-4O66SJPAHVBY` now ranks in the top 5, containing
   both "Suresh Yadav" and "Ananya Iyer".
2. Full service-free test suite: 418 passed, 0 failed — unchanged.
3. `run_benchmark.py --retrieval-only` (zero API cost): retrieval 32/37 → **37/37 (100%)**,
   `personnel` 0/3 → 3/3.
4. Full paced re-run with synthesis, independently recomputed from the raw checkpoint JSONL, not
   the printed summary: **36/37 (97.3%)**, `personnel` 3/3, zero `429`s, `VALID`. The one remaining
   miss (Q02, causal) retrieved correctly (`retr=1`) — a synthesis-quality question, not a
   retrieval gap, not something this fix targets, and not reproduced on the 2026-08-17 run
   (consistent with normal LLM answer variance across runs, not a regression).

**Not re-measured after this fix, and flagged rather than assumed current:**
- **§5 (`run_time_to_answer.py`)** and **§8 (`run_safety_eval.py`)** both call `GET /search`
  directly, so they inherit the fix automatically, but neither has been re-run — §8 in particular
  carries its own house rule ("do not re-run on demo day," provider-quota risk), so both stay
  dated to their last measurement until there is a safe window to re-run them.
- **§7 (`run_retrieval_baseline.py`) does *not* inherit the fix even if re-run as-is** — it
  constructs `SearchService` directly and never passes `supabase`, so the filtering block's
  `if self.supabase is not None` guard skips it entirely. Its 89.2%/94.6%/94.6% figures reflect
  pre-fix behaviour. Giving this harness the same `supabase` argument is a small, low-risk
  follow-up — not done tonight, recorded here so it isn't mistaken for "already covered."

**A second instance of the same bug class, found while checking the landing page for stale
figures.** `run_benchmark.py`'s own KG-linkage line —
`MATCH (a:Asset) RETURN count(a)` / `MATCH (a:Asset)-[:KNOWLEDGE_EDGE]-() RETURN count(DISTINCT a)`
— has **zero test-artifact filtering**, unlike `run_kg_completeness.py` (§12), which already
filters via this same `corpus.py` predicate. It read `10/10 (100%) · 45 edges` on 2026-08-17; on
2026-08-24 the same unfiltered query reads `16/55 (29%) · 172 edges` — not a regression, the graph
now simply holds far more test-sweep assets than it did, and this line was never excluding them.
**Not fixed that session** — the landing page's "Knowledge graph linkage" tile was pointed at §12's
already-filtered, already-correct figure instead, which needed no new code (then 16/21, 76% — see
below for why this number has since moved to 18/21). Applying the same `corpus.py` filter inside
`run_benchmark.py`'s own KG-linkage query, so its asset-centric figure is trustworthy too, is a
small follow-up, not done here.

---

### D2 (OCR backfill) executed — 2 of 4 documents fixed 2026-08-24

D2 had been standing as "decided-by-default" — blocked by the no-cloud-writes rule, so the OCR fix
(2026-08-23) stayed invisible: 4 documents ingested a month earlier, before the fix, had no indexed
text and no graph edges. Investigated and executed the same night, **with explicit per-write
authorization** given in-session for this specific backfill, as the standing rule requires.

**Traced before writing anything.** All 4 documents: zero `KNOWLEDGE_EDGE`s, zero Elasticsearch
text — a genuinely clean slate, so a re-run could only add correct data, never conflict with
anything already there. `run_ocr`/`run_ner`/`link_to_graph`/`index_vectors`/`index_text` are
independent activity functions (not sandboxed to a Temporal worker context), callable directly —
`index_vectors` (Qdrant) and `index_text` (Elasticsearch) run in parallel with no shared
dependency, so the local-only and cloud-only halves of the write are genuinely separable. A
read-only OCR probe was run first, before any write, to know the outcome in advance.

**The probe found something the D2 plan hadn't accounted for:** 2 of the 4 documents are the exact
"worst scan" and "borderline scan" D1 itself was written to describe (`min_span_confidence` 0.253
and 0.692) — so re-running them now correctly triggers the *same night's* `/search`-adjacent
span-confidence gate and routes to `review_required` instead of completing. That is the quarantine
rule working as designed, not a shortfall of the backfill: **only 2 of the 4 were ever going to
fully index**, and executing D2 honestly means reporting that split rather than forcing all 4
through.

**Result, verified read-only after the write:**
- `DOC-ER8TZ9NHV5JH` (handwritten_inspection_note) and `DOC-FZMVRGMACDVX` (handwritten_shift_log):
  completed the full chain — 3 graph edges each, indexed to both Qdrant and Elasticsearch.
- `DOC-DVYFFXYFE9YD` (scanned_inspection_degraded) and `DOC-ZCUGJE4ZAAT2` (scanned_oem_bulletin_degraded):
  stopped at `run_ocr`, `pipeline_stage: review_required`, with real confidence data
  (`OCR span-confidence gate: 1 span(s) below 0.7`, `4 span(s) below 0.7`) replacing the old,
  uninformative `nim_returned_no_text` error.
- OCR gate (§11): `UNSCOREABLE 4/4` → 2/4 scoreable. Handwriting mean recall **0.333** — a
  recorded Layer 3 limitation (no handwriting-specific model), not a new regression.
- KG linkage (§12): **16/21 (76%) → 18/21 (85%)**, unexplained gap 4 → 2. 18/21 is the correct
  ceiling for this backfill, not a partial result — the remaining 2 are correctly quarantined
  pending human review, and promoting them without one would violate the project's own
  human-only-promotion rule.

**Left as-is, cosmetic only:** the 2 completed jobs still carry stale `review_pending: 1` and
`error: "nim_returned_no_text"` fields on their `extraction_jobs` row — `mark_complete` only
updates `pipeline_stage`/`progress_pct`, not those two. Visible only on
`GET /documents/{id}/status` for these two specific documents; harmless, low-priority follow-up.

---

### Triaged from an external bug report — 2026-08-23

A handover list written against branch `feat/beautify` ("KAIROS — non-frontend bugs", B-1…B-7) was
verified item by item against `main` and the live stack. Two claims did not reproduce, one was
already fixed, and the rest are recorded below with what verification actually showed. Kept because
the report will circulate again and the corrections are worth more than the original list.

**Closed 2026-08-23**

- **B-2 · `make benchmark` ran nothing.** Real. `benchmark/` is a directory, so Make considered the
  target satisfied and printed `'benchmark' is up to date` at exit 0. The report's stated cause was
  wrong — `.PHONY` *is* declared, it just omitted this target, and `benchmark` was the **only**
  collision (`test/` does not exist; the directory is `tests/`). No CI impact: `tests.yml` invokes
  `run_benchmark.py` directly and never used the target. Fixed.
- **B-3 · `GET /elicitation/offboarding/sessions` → 500.** Real, but larger than reported and both
  suggested causes were wrong. Not route shadowing (no `/sessions` route exists to shadow, and
  `/offboarding` is correctly declared above `/{session_id}`) and not a serialiser. See the
  UUID-path-param row in [Known Pitfalls](#backend--database--models--api). **Every** not-found on
  the three `/{session_id}` routes returned 500, not just the reported literal. Fixed.
- **B-5 · `GET /assets/` omits the issue counts.** Real, and not a defect — the endpoint did what
  it was written to do; it blocked two columns a design review asked for. Both counts now ship on
  every list row, sharing the detail endpoint's definitions so the two surfaces cannot disagree.
  Cost is **two queries per page regardless of page size** (bulk fetch by the page's asset ids,
  tallied in the router) rather than the detail handler's per-asset pair, which would be an N+1 of
  100 round trips on a 50-row page. Server-side `GROUP BY` was the first choice and is unavailable:
  PostgREST aggregates are disabled on this project (`PGRST123`), and both remedies — enabling them
  or adding a DB function — are cloud DDL. `AssetSummary` in `frontend/src/lib/types.ts` now
  carries the fields, so the data is available to the UI; **which columns to render, and how, is
  still the design review's call** and was deliberately not decided here. The referenced
  `docs/design/BACKEND-ASK.md` does not exist in this repo.

**Not defects**

- **B-1 · "Embedding provider unreachable, demo-blocking."** Did not reproduce. `JINA_API_KEY` is
  populated here; a live `embed()` returns a 1024-dim vector and there were zero `embed.jina_failed`
  / `embed.ollama_failed` in 24 h of API logs. `.env` is gitignored, so the reporter's copy was
  simply unpopulated. **Their benchmark figures are void, not bad** — the run self-reported
  `INVALID`. One real weakness sits underneath the false alarm and is *not* fixed: `_embed_ollama`
  returns `[]` rather than raising (`services/llm.py`), and `search_service` gathers with
  `return_exceptions=True`, so a total embedding failure degrades search to ES + graph with one log
  line and no error. Deliberately left alone — changing failure semantics on the retrieval hot path
  is a bigger change than the symptom justifies. Recorded so it is a decision, not an oversight.
- **B-4 · Landing claims 91% against `RESULTS.md`'s 89%.** Already fixed on `main` before the report
  was read: `page.tsx` reads `89%` / `33/37`, the guard test `landing-figures.test.ts` exists, and
  its `it.fails()` marker was removed with a comment dating the resolution. The report was written
  against `feat/beautify`. The `0.91` elsewhere on the page is a mockup confidence score, unrelated.

**Found while closing B-5 on 2026-08-23 — recorded, not fixed (out of scope for that task)**

- **`GET /assets/{asset_id}` can report a silent, wrong `0`.** The detail handler gathers its
  Supabase enrichment with `return_exceptions=True` and substitutes `0` for any lookup that
  raised, so a dropped connection renders as "no work orders" rather than an error. Reproduced
  live: `P-101` returned `0` on one call and the true `6` on the next two, with
  `asset.enrichment_failed … error=<ConnectionTerminated …>` in the log each time. Intermittent
  and cloud-side (HTTP/2 connection reset), so it is not a code defect exactly — but the failure
  mode is invisible to the caller, and a fabricated `0` on a maintenance count is the kind of
  claim this project otherwise refuses to make. The new list endpoint copies this degradation
  **deliberately**, so the two surfaces stay consistent; if it is changed, change both. Same
  family as the `_embed_ollama` weakness under B-1.

**Open — what a fresh session needs to pick these up**

Each item states the blocker, the exact next step, and how to prove it worked. Read the
cloud-data rule in `AGENTS.md` § Non-Negotiable Rules → Both **before** touching B-7.

---

**B-7 · Test writes pollute the demo database** — *blocked on a user decision, not on work*

*Status.* A complete fix was written, dry-run, and **reverted on instruction** on 2026-08-23. Do not
re-apply it without the user explicitly asking: every version of this deletes live cloud rows, and
the standing rule forbids that. The pollution is cosmetic (two screens) and grows by roughly one
programme per `test_elicitation.py` run — it is not a functional break, so waiting costs little.

*Why the obvious fix is dangerous.* `scripts/purge_test_data.py` is invoked by an **autouse session
fixture** in `tests/conftest.py`. Adding a table to `SUPABASE_TARGETS` therefore arms an irreversible
delete that fires on the next suite run without anyone choosing it. That is why this was reverted
rather than left in place unused.

*The reverted implementation, so it need not be re-derived.* Three pieces, all in
`backend/scripts/purge_test_data.py`:
1. `OFFBOARDING_EMAIL_PREFIXES = ("resp_", "qtest_", "detail_", "retiring_")` — the four prefixes
   `tests/test_elicitation.py` actually persists (lines 110, 127, 157, 177). Two traps here. The
   fourth, `retiring_`, is easy to miss — the original bug report listed only three. And the file
   contains a **fifth**, `field_` (line 145), which must **not** be added: it belongs to
   `test_offboarding_requires_engineer_or_admin`, which asserts **403**, so the row is never
   created and no `field_` session has ever existed. Widening the pattern to cover it would add
   delete surface for zero rows — and needlessly widening a delete pattern in this script is
   precisely what destroyed four real documents once before. Re-derive this list from the test
   file if it has changed, and check whether each call is expected to *succeed*.
2. `_offboarding_test_session_ids(sb)` — select `id, personnel_email`, filter with
   `str.startswith(OFFBOARDING_EMAIL_PREFIXES)` **in Python**, return ids.
3. In `_purge_supabase`, delete `quarantine_items` whose `session_context.session_id` is in that set
   (JSONB, so also filtered in Python — PostgREST cannot filter a nested key against a list), then
   `sb.table("offboarding_sessions").delete().in_("id", ids)`.

*Two constraints that are easy to get wrong.*
- **Match by explicit id, never `LIKE`.** In SQL `_` is a single-character wildcard, so `resp_%` also
  matches `respX…`. Every existing prefix in that file is underscore-free, so this hazard is new and
  the file's own conventions do not protect against it. (This script has already destroyed real data
  once — see the `DOC-X` comment at the top of it.)
- **No child pass is needed.** `db/schema.sql:306` makes `offboarding_session_items.session_id`
  `ON DELETE CASCADE`, so items follow their parent.

*Expected dry run* (verified 2026-08-23): 16 of 17 sessions, 96 of 101 items via cascade, 4
`quarantine_items`; `EXPERT-RKUMAR` / `ramesh.kumar@kairos.local` preserved as the only real seed
programme. **If the numbers differ, stop** — the prefixes have drifted from the test suite.

*Acceptance test — the one that matters.* Deleting rows only proves the symptom was swept up. Run the
suite, then re-count `offboarding_sessions`: the count must be **unchanged by the run**. That proves
the cause is gone. It requires a full-suite run, which itself writes to cloud Supabase — so it needs
the same user decision.

---

**B-6 · Data-quality observations from the external report — verify before building on any of it**

Mixed accuracy. Anyone designing a UI against the original list will build the wrong thing.

*Wrong as reported:* `operational_events.priority` **does not exist as a column at all** — the cited
`priority TEXT NOT NULL DEFAULT 'normal'` in `db/schema.sql` belongs to `briefs`. Priority lives only
in `payload` JSONB, unconstrained, on a subset of rows; `docs/DATABASE.md` now says so at the table.
`ner_annotations` has 20 rows, not 0. `documents.status` (108 active / 8 superseded) and
`assets.eam_source` are not single-value — though `eam_source` is skewed by test pollution (B-7), so
re-measure after any cleanup rather than trusting either number.

*Confirmed:* `audit_log` is ~69% one action (`synthesis`); `details.description` holds stringified
JSON inside a JSON field (11 rows), so it needs double-parsing to render as structure; actor identity
is inconsistent across tables (`audit_log.performed_by` alone mixes UUIDs, `dev-user`, `system`,
`test-runner`, `e2e-sweep`, `service-kairos-connector`), so an avatar cannot be a fixed column;
`offboarding_sessions` has no name field, only `personnel_id` / `personnel_email`, so a full name
**cannot** be derived and must not be fabricated; `brief_feedback` is empty.

*Next step.* No code change. Re-measure anything load-bearing before designing against it — the
counts above were taken on a polluted database. `docs/design/DATA-CONTRACT.md`, referenced by the
original report, **does not exist in this repo**.

---

**B-1 residue · embedding failure degrades search near-silently** — *recorded decision, not an oversight*

`services/llm.py` `_embed_ollama` returns `[]` rather than raising, and `search_service` gathers with
`return_exceptions=True`. A total embedding failure therefore yields an empty query vector, Qdrant
errors, the exception is swallowed, and search quietly falls back to ES + graph with one
`search.qdrant_failed` log line. The user sees plausible, thinner results and no error.

*Why it is still open.* Making `embed` raise changes failure semantics on the retrieval hot path,
which is reached by `search_service.py`, `brief_engine.py` and `routers/search.py`. That is a larger
change than the symptom justifies, and the graceful degradation is partly deliberate. **Left alone
on purpose 2026-08-23** — do not "fix" it casually.

*If picked up.* The low-risk half is observability, not semantics: make the degradation visible
(a metric, or promoting the log to error with the query attached) so a silent failure is detectable
without changing what callers receive. Same family as the `GET /assets/{asset_id}` false-zero
recorded above.


- **E2E sweep — 22/22 rows closed** (last 3 on 2026-08-22). Horizontal scroll: 0 overflow across all
  35 static routes at 375 px, with the detector validated against an injected 900 px element. Voice
  capture: real speech → vault → Groq Whisper (0.926) → `quarantine_items` `pending`, 50.4 s. The
  model-gate run **exposed four defects rather than clearing a checkbox** — no run-validity field, a
  per-partition re-extraction doubling model calls, a Celery time limit calibrated on a broken run,
  and 23% of the corpus scored against a taxonomy the extractor never receives. All fixed and
  re-verified on 2026-08-23 — see [Known Pitfalls](#backend--database--models--api) and the
  model-gate row in [Benchmarks](#benchmarks--current-numbers). Detail in [`e2e-sweep.md`](./e2e-sweep.md).

- **The 12 `COMPONENT` labels in `validation_corpus` are unscoreable by design, not fixed.** They are
  reported rather than counted as failures, but closing the gap needs a decision: teach the prompt
  `COMPONENT`, or remap the ground truth. Deferred deliberately — nothing in the codebase consumes
  the type, and 3 distinct entities cannot validate adding one to production extraction (the same
  reasoning already recorded for `ORGANIZATION`).

- **Linkage triaged 2026-08-23 — the gap is 4 documents, and it is *not* the L3 handwriting limitation.**
  The first reading (70/108 = 64%, "34 unexplained") was a *measurement* artifact, not a corpus
  gap: **85 of 108 "active" vault documents were test artifacts** (`ann_test_*`, `dbtest_*`,
  scratch files) carrying ordinary random `DOC-` ids, so only the file name identified them. With
  them in the denominator the metric was reporting test hygiene rather than linkage — the same
  class of error as scoring the model gate against labels outside its taxonomy.
  `run_kg_completeness.py` now excludes them **and reports the count**, so the denominator stays
  auditable. **The "two borderline names conservatively kept" were checked on 2026-08-23 and were
  not corpus at all** — `e2e_shift_log.txt` and `kairos_ingest_test.pdf` appear in neither
  `dataset_manifest.csv` nor anywhere under `dataset/`, so the claim that the survivors "are exactly
  the golden dataset" held for 21 of 23, not 23. Corrected by **D8**; the predicate now lives in
  `api/services/corpus.py` and is shared with the graph endpoint.
  **Figure: 16/21 (76%) linked · 1 quarantined by design · 4 unexplained** (denominator corrected by
  D8, 2026-08-23). The four are
  `regulatory_clause_excerpts.pdf` plus the handwritten and degraded-scan images. **Root cause
  identified and fixed 2026-08-23:** the OCR path returned `nim_returned_no_text` for all four
  images, so no text was indexed and nothing could link. It was never a linkage defect, and it was
  broader than the recorded handwriting limitation — see the OCR entry above. **The four are still
  unlinked**: the parser fix does not retroactively index a document ingested while it was broken,
  so this figure only moves after the one-off re-extraction, and 16/21 remains the number to quote
  until then.

- **DIAGNOSED 2026-08-23: the OCR path fails for TWO unrelated reasons, and neither is the
  handwriting limitation the docs record.** All four image documents carry
  `pipeline_stage: review_required`, `ocr_confidence: 0.000`, `error: nim_returned_no_text`.
  Proven by probing the CV endpoint directly:

  1. **Response-parsing bug (the two handwritten notes).** `services/ocr.py:_nim_ocr` reads
     `d["label"] or d["text"]`, and its comment asserts "Each detection has a `label` field".
     **It does not.** The live response returns detections keyed
     `['bounding_box', 'text_prediction']`, with the text at `text_prediction.text`. So every line
     resolves to `""`, the join filters them all out, and the caller reports "no text".
     **The model reads the handwriting fine** — 11 detections at 0.91 confidence, 362 characters:
     `SHIFT LOG - PRODUCTION UNIT 2 / Date: 15-Jan-2026 / Shift: Night / Name: S. Yadav / EQ-101
     pump sounded a bit different tonight…` — which is exactly the content
     `dataset_manifest.csv` row 22 declares.
  2. **Size ceiling (the two degraded scans).** `_NIM_IMAGE_SIZE_LIMIT` is 180,000 base64 chars.
     `scanned_inspection_degraded.png` encodes to ~2,027,893 (11x over) and
     `scanned_oem_bulletin_degraded.png` to ~2,389,957 (13x over), so `_nim_ocr` returns `""`
     before making any call. They never reach the model. (`pid_line3_isolation_boundary.png` at
     ~190,340 is marginally over too, but it uses the Path B vision route, not this one.)

  **This invalidates a recorded limitation.** "No separate handwriting model" is listed as the L3
  gap and as the explanation for the unlinked documents; the handwriting model demonstrably works
  and the failure is a key name. Re-read L3's score once fixed.

  **FIXED AND LIVE-VERIFIED 2026-08-23 — all four images now return text.** `services/ocr.py`:
  `_detection_text` reads `text_prediction.text` with `label`/`text` kept as fallbacks, and
  `_shrink_for_inline` re-encodes an oversized image (Pillow 12.3.0, already a dependency) instead
  of returning `""`. Probed against the live CV endpoint, writing nothing:

  | Image | base64 | Before | After |
  |---|---|---|---|
  | `handwritten_shift_log.png` | 94,180 (0.5x) | no text | **362 chars**, clean |
  | `handwritten_inspection_note.png` | 94,312 (0.5x) | no text | **364 chars**, clean |
  | `scanned_inspection_degraded.png` | 2,027,896 (11.3x) | never reached the model | **726 chars** |
  | `scanned_oem_bulletin_degraded.png` | 2,389,960 (13.3x) | never reached the model | **1,005 chars** |

  An unscaled JPEG re-encode alone cleared the limit for both scans (2,027,896 → 102,628), so no
  resolution was traded away. The degraded scans transcribe with visible character errors
  (`EO-xxx` for `EQ-xxx`, `202--01-15`) — expected for deliberately degraded input, and precisely
  what `run_ocr_gate.py`'s salient-token recall exists to quantify. **Do not read these as clean.**

  **The silent-failure mode is closed too**, which was half the bug: `ocr.no_detections` (the model
  ran and saw nothing) and `ocr.detections_unparsed` (detections came back but no text field
  matched — the schema-drift case, logged with the observed keys) can no longer be confused, and
  `ocr.image_downscaled` / `ocr.image_too_large` separate a re-encode from a genuine ceiling.
  7 service-free tests in `tests/test_extraction_path.py` cover both helpers (355 pass, ruff clean).

  **SECOND DEFECT, found by fixing the first (2026-08-23).** `ocr.py` hardcoded
  `overall_confidence: 0.95` on **every** OCR extraction regardless of transcription quality, so a
  garbled scan and a clean one were indistinguishable to every downstream gate — and CLAUDE.md's
  `< 0.7 → quarantine` rule was being applied to a number that could never be below 0.7. The CV API
  returns per-span confidence and the code was discarding it. **This was dormant until the parse fix
  landed**: before it, the two degraded scans produced no text at all, so nothing could reach the
  graph on a false 0.95.

  Now reported honestly — `overall_confidence` is the model's own per-span confidence weighted by
  span length, alongside `min_span_confidence`, `low_confidence_spans` and `span_count`, because one
  average cannot express "4 of 22 spans are unreliable" and the dangerous failure is a single misread
  value, not a poor mean. Measured live:

  | Image | overall | min span | spans < 0.7 |
  |---|---|---|---|
  | `handwritten_shift_log.png` | 0.903 | 0.736 | 0/11 |
  | `handwritten_inspection_note.png` | 0.872 | 0.720 | 0/12 |
  | `scanned_inspection_degraded.png` | 0.860 | 0.692 | 1/19 |
  | `scanned_oem_bulletin_degraded.png` | **0.719** | **0.253** | **4/22** |

  Length-weighting is what separates them: the plain mean rates the worst scan 0.805, the weighted
  mean 0.719, while the clean handwritten notes hold at ~0.90. This does **not** contradict the
  deliberate decision at `_native`/`extract_text` not to *scale* confidence for handwriting — that
  guards against pushing clean transcriptions under the threshold, and the handwritten notes score
  0.87–0.90 unaided.

  **The hazard is not fully closed, and this is a policy decision, not a code gap.** The worst
  document still scores **0.719 — above the 0.7 line — so it would reach the canonical graph**,
  carrying `EO-xxx` for `EQ-xxx` and a mangled date. Closing it means gating on the *shape* rather
  than the average (any span below 0.7, or a `min_span_confidence` floor), which changes what
  quarantines and is therefore deliberately left for an explicit decision. Until then the signals
  are recorded and `ocr.low_confidence_spans` logs every affected document. 12 service-free tests
  cover both defects (374 pass, ruff clean).

  **Not merged with its twin.** `PIDService._fit_b64` (`services/pid.py`) already solved this for
  Path B — which is why that path never hit the bug — and `_NIM_IMAGE_SIZE_LIMIT` is defined in both
  modules. Consolidating them touches the live-validated P&ID path and was left out of scope; the
  cross-reference is recorded in both docstrings so the two copies cannot drift unnoticed.

  **Third change, and it is the one the plan was missing (found 2026-08-23):** fixing `ocr.py` does
  **not** by itself move the OCR gate, the L3 score, or the 4 unlinked documents. `run_ocr_gate.py`
  makes **no model calls** — it compares text already indexed in Elasticsearch — so the four images
  stay `UNSCOREABLE` until their text is re-extracted and re-indexed. There is no reprocess endpoint,
  and `POST /documents/ingest` dedups on SHA-256, so re-uploading the same bytes returns
  `{"status": "duplicate"}`. Closing this therefore needs a **one-off backfill** that re-runs OCR for
  those 4 document ids and indexes the result — a write path, unlike the parser fix, and the only
  part of this work that touches the golden corpus.

- **Audit-pack `vessel` / `compressor` clauses show 0 evidence** — no asset carries a matching
  `equipment_class`, and the `PESO` / `Factory Act` frameworks are not seeded, so they are
  intentionally not shown.

- **`/rca` takes ~90 s** (measured on NIM Llama 3.1 70B; not re-timed on Nemotron) and returns `synthesis_available: false` when the graph lacks
  history. Not a bug.

---

## Verification snapshot

- **Benchmarks** (cloud stores, 2026-08-16): see [Benchmarks](#benchmarks--current-numbers) above.
- **Backend test suite:** **576 collected** across 50 files (2026-08-23). The last full green run was
  **412 passed · 0 failed** (2026-08-22); 164 tests have landed since, so **no current pass count
  exists** — re-run before quoting one. Write-heavy: run against
  `--profile local-stores`, **never cloud**. The long-standing `test_attribution_worker_queues_recheck`
  flake is gone — it was one of six failures traced to a shared-fixture dedup collision, now fixed.
- **Service-free tier:** **476 passed** across **41 files** (2026-09-14) — no stack / secrets / network.
  This is exactly what CI's `unit` job runs; the list is duplicated in `AGENTS.md`, `docs/TESTS.md` and
  `.github/workflows/tests.yml` and **all three must be updated together** (they have drifted twice).
- **Frontend:** **256 passed across 75 files — fully green** (2026-09-14), `tsc` clean, `eslint`
  0 errors / 3 pre-existing unused-var warnings. `landing-figures.test.ts` was red until the
  frontend container was recreated: the `./benchmark:/benchmark:ro` mount postdated the running
  container, so the file could not collect. `docker compose up -d --force-recreate --no-deps
  --no-build kairos-frontend` picks it up and rebuilds nothing (`node_modules` is baked into the
  image; source is bind-mounted). Its 3 tests now actually run, which is why the count rose 225 → 228.
  One test to know about: `model-gate` pagination is load-sensitive — it times out under full-suite
  parallelism on a loaded machine and passes alone in ~690 ms. Treat a lone red there as load, not
  regression. Run vitest **in Docker, never on the host** — host package
  resolution differs from the pinned image and makes `auth.test.ts` / `api.test.ts` fail spuriously.
  **The OOM is fixed by running a one-off container, not by raising `mem_limit`:** the running
  `kairos-frontend` sits at ~1.85 GB of its 2 GB (the Next dev server), so `docker exec` leaves vitest
  no headroom. `docker compose run --rm --no-deps kairos-frontend npx vitest run` gets its own budget
  and finishes in ~13 s.
  The one failure found on 2026-08-22 was **stale, not a regression**, and is fixed. The wording it
  disagreed about is now **settled, and the reasoning is in the code** (`attention-list.tsx`): the row
  renders `Overdue quarantine · {input_type}`, matching the sibling `Overdue conflict · {track}`
  row so the two read as one queue. "Overdue" is factual rather than decoration — the list
  is `sla.overdue_quarantine_items`, and being past SLA is the only reason a row is under "Needs
  attention" at all. `content ?? input_type` was considered and **deliberately rejected**: `SLAService`
  selects only `item_id, asset_id, input_type, sla_due_at`, so `content` is always undefined, and were
  it ever added to that select, `elicitation_response` rows store a JSON array string and the list
  would render raw `[{"answer": …}]`. Both labels are asserted in `management/page.test.tsx`.
- **P&ID Path B:** live-validated on `dataset/02_Document_Corpus/pid_line3_isolation_boundary.png`.
- **Cloud stores:** Neo4j Aura + Qdrant Cloud + Supabase + Grafana Cloud. Default local stack ≈ 13
  containers; ~2–3 GB idle RAM.
- **Auth verified-token cache:** ~577 ms/request saved (revocation preserved, ≤ TTL staleness).
- **Soak (2026-08-22, cloud stores):** 60 min × 5 VU → 10 min idle → recovery probes. **PASS on all
  four harness thresholds** — memory FLAT, connections STABLE, errors CLEAN, idle recovery 4/4. Read
  it as *no leak signal over a 60-minute window*; §10 of `RESULTS.md` records what it does not prove.

---

## Known Pitfalls

> Grouped by area for scanning; every row is a real gotcha you can still hit. A row earns its place
> only if it imposes an ongoing constraint or describes a symptom that can recur — bugs fixed in
> committed code, with nothing left to obey, are removed rather than archived here.

### Backend · database · models · API

| Area | Fix |
|---|---|
| `quarantine_items` FK failure | `asset_id = None`, never `""` |
| **A UUID path param must be validated before the query** | Any route whose `{id}` lands on a UUID column returns **500, not 404**, if the segment is unparseable: PostgREST raises `22P02` and the global handler turns it into a server error. Two guards exist and any new such route needs one — `dependencies.valid_quarantine_item_id` and `valid_offboarding_session_id`. Second half of the same bug: **`.single()` raises `PGRST116` on zero rows**, so a *well-formed but absent* id also 500s and the handler's own `if not result.data → 404` becomes unreachable dead code. Use `.maybe_single()`. Found on `/elicitation/offboarding/*` 2026-08-23 (the reported symptom was `GET /elicitation/offboarding/sessions` — there is no `/sessions` route, so the literal was swallowed by `/{session_id}`). Covered by `test_quarantine_item_id.py` + `test_offboarding_session_id.py`. |
| Supabase login / refresh error | Fresh anon client — never the service-role client |
| NIM env not picked up | `--force-recreate`, not `--restart` |
| `audit_log` sort failure | Column is `timestamp`, not `created_at` |
| Temporal logger crash | `workflow.logger` is stdlib — f-strings, no kwargs |
| `input_type` CHECK rejected | DROP + re-add constraint to add new enum values |
| KNOWLEDGE_EDGE `valid_to` NULL | Sentinel `datetime(9999,12,31,...)`, never NULL |
| `/documents/{id}/topology` 404 | Only for `pid_drawing` docs; others 404 by design |
| Frontend SSR fetch timeout | Wrong base URL — check `API_INTERNAL_URL` vs `NEXT_PUBLIC_API_URL` |
| Work-order dedup test flake | Unique `work_order_id` per run (10-min dedup window; key is business-id scoped since 2026-08-17) |
| **A test that passes alone and fails in a full run is probably colliding with event dedup** | `shared_asset_id` is **session-scoped**, a full suite finishes well inside `DEDUP_WINDOW_MINUTES` (10), and seven tests POST `/events/inspection-complete` against it — so the first wins and every later one correctly returns `{"status": "deduplicated"}` with **no `quarantine_item_id`**, producing a `KeyError` in whichever test reads it. The dedup is behaving exactly as designed. Six full-suite failures traced to this on 2026-08-22. **Any test that needs its operational event to actually land must use the `fresh_asset_id` fixture, not `shared_asset_id`.** |
| **A schema statement can be silently dropped and the run still reports success** | `scripts/init_neo4j.py` split `init_schema.cypher` on `;` and *then* filtered chunks starting with `//` — so every statement following a comment block was discarded **before** the execution loop, meaning nothing was logged and the summary still said complete. Six statements had never reached Aura, including **`asset_id_unique`**: the graph's most important node type had no uniqueness constraint (assets are written with `MERGE`, which needs one to be safe under concurrency) and no index, so the Layer 4 hot path planned as a `NodeByLabelScan`. Fixed 2026-08-22 by stripping comment lines *before* splitting, and the loader now reports `statements_applied` / `statements_failed` separately. **After changing the schema file, verify with `SHOW CONSTRAINTS` / `SHOW INDEXES` — do not trust the run summary.** |
| **Semantic search returns nothing, silently** | A Qdrant filter on a field with **no payload index** returns HTTP 400 on Qdrant Cloud. `SearchService.hybrid_search` gathers with `return_exceptions=True`, so it is swallowed as `search.qdrant_failed` and hybrid retrieval degrades to Elasticsearch-only with no error surfaced. Cost: the superseded-document filter shipped this way and semantic reach measured **0/37** until `run_retrieval_baseline.py` exposed it. **Any new payload filter needs its field added to `PAYLOAD_INDEXES` in `scripts/init_qdrant.py`**, then `make init-all` (idempotent). |
| **Benchmark / soak numbers spike mid-run for no reason** | You edited a file under `backend/`. `docker-compose.override.yml` mounts `./backend:/app` and runs `uvicorn --reload`, so **every save restarts the live API** — in-flight requests error, p95 spikes ~17x, and RSS resets, which destroys a soak's leak trend. Long measurement runs execute *inside* `kairos-backend-api`, so they are hit by this too. **Do not edit `backend/` or `tests/` while a benchmark or soak is running** — the override mounts both, and `tests/` edits were observed triggering reloads too. Editing `docs/` and `frontend/` is safe; neither is mounted into the API container. |
| **A `localhost` URL in `.env` for a *container* service silently disables it** | `OPA_URL=http://localhost:8181` resolved to the API container itself, so authorization requests never reached OPA — and `_ask_opa`'s fail-open turned that into "allow everything". The host port mapping (`0.0.0.0:8181->8181`) makes `localhost:8181` work from the **host**, which is what makes the wrong value look right. Inside a container always use the compose service name (`http://kairos-opa:8181`). `.env` is `env_file:`-injected at container **creation**, so a change needs `--force-recreate`, not a reload. |
| **A 403 that should exist but doesn't is invisible** | Authorization defects fail *open*, so nothing errors and no test goes red. `tools/verify_authz_policy.sh` checks the policy's decisions, but the policy being right proves nothing about whether it is *reached*. After any change to `middleware/opa.py`, `kairos.rego` or `OPA_URL`, probe the live API with a real token from a **restricted** persona and confirm a **403** — e.g. `field_worker` on `/audit-log/`. A 200 there means the layer is inert. |
| **A purge matcher that can never fail is the danger; `tests/test_purge_safety.py` now pins it** | Every prefix and exact id is asserted against a list of ids that must survive — including `WO-2026-0714`, whose promoted quarantine item (`PROMOTED-f17b1416…`) the compliance caveat above cites, and a `DOC-X…`-shaped id reproducing the original incident. Also enforced: **every prefix ends in `-`**, and nothing appears in both a prefix list and an `_EXACT` list. The 2026-08-23 addition was `WO-E2E-ELICIT-001` — 4 stranded rows from the 2026-08-16 sweep, typed by hand and generated by no fixture, so it went in `WO_EXACT_IDS` matched by equality. **A bare `WO-` prefix would have deleted real dataset content**, which is why the exact-id pass is now generalised (`EXACT_ID_SETS`) rather than hardcoded to documents. |
| **A test-id prefix that is also a real id's first characters deletes real data** | `scripts/purge_test_data.py` matches every entry in its `*_PREFIXES` lists as a **prefix** — `STARTS WITH` in Neo4j, `LIKE 'p%'` in Supabase, a `prefix` query in ES — and `tests/conftest.py` runs it as an **autouse session teardown** unless `KAIROS_SKIP_TEST_CLEANUP` is set. `DOC_PREFIXES` contained the bare string `DOC-X`, present only because `tests/test_annotations.py` writes that exact id as a literal. Real document ids are `DOC-` plus twelve random characters, so roughly **one document in thirty-six** starts with X: four real documents matched and were `DETACH DELETE`d from the graph and dropped from Supabase on every full-suite run, against CLAUDE.md's "Vault: permanent. Never delete." Fixed 2026-08-22 by splitting whole ids into `DOC_EXACT_IDS`, matched by equality in all three stores. **A prefix shorter than its trailing separator is a data-loss bug — put whole ids in the `_EXACT` lists, and keep every prefix ending in `-`.** |
| **Test assets accumulate in the cloud stores even though a purge runs** | The purge only removes what its prefix lists name, and that list drifts from `tests/conftest.py`. `fresh_asset_id` has minted `ASSET-FRESH-{uid}` since it was added, but `ASSET_PREFIXES` never listed it, so 25 test assets built up in Aura and dragged 200 phantom ISO-45001 gaps into `GET /compliance/gaps`. Added 2026-08-22. **After adding a fixture that creates an entity, add its prefix to `purge_test_data.py` in the same change** — the lists are the only thing keeping the demo stores clean, and nothing fails when they drift. |
| **`make nuke` does not clean the cloud stores** | It is `docker compose down -v` — local volumes only. Neo4j Aura, Qdrant Cloud and Supabase are untouched, so the documented `nuke → dev → init-all → seed → load-dataset` reset leaves every cloud-side test entity in place. Use `purge_test_data.py` for prefix-matched residue; anything created by hand through the API (`BULK-*`, and the bare `ASSET-<8HEX>` ids `POST /assets` generates when the payload omits one) carries **no test marker at all** and can only be removed by explicit id. **A generated id is indistinguishable from a real one — pass an explicit prefixed id when creating throwaway entities by hand.** |
| Site-wide brief wrong recipient | `user_id = f"site-{site_id}"` in `BriefEngine.deliver()` |
| NIM OCR wrong base URL | `https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v2` |
| **PostgREST `.neq()` against a missing JSONB key drops every row** | `NULL != 'x'` is `NULL`, not `TRUE`. `.neq("session_context->>element_type", "topology_manifest")` silently excluded *every element row* (they have no such key), so topology reported `elements_total: 0`. Filter in Python when the key may be absent. |
| **`BlastEntity` demo scaffolding is deleted on purpose — do not re-seed it** | Six nodes named after **real** corpus documents (`SOP-HE-301-04`, `INSP-HE301-2025-Q4`, `MP-HE-HYDROTEST-03` …) pointed at a fabricated `DOC-MERIDIAN-HE301-SB` that was never in the vault — the only dangling provenance the linkage runner found. Created by no code, read by no endpoint (blast radius runs inside the supersede flow, and a document absent from the vault cannot be superseded), and duplicating documents that already exist as genuine `Document` nodes. Removed 2026-08-23 on the same principle as the deleted Go `/ot/coverage` route: fabricated data that could render as real must go. If a blast-radius demo is needed, supersede a **real** document — the edges already exist. |
| **A frontend test that reads a repo file needs that path mounted into the container** | `src/app/landing-figures.test.ts` reads `<cwd>/../benchmark/RESULTS.md` to prove the landing page's eval bars still match the benchmark of record. On the host `cwd` is `frontend/` and it resolves; in the container `cwd` is `/app`, so it looked for `/benchmark` and the **whole suite failed to collect** — reported as `1 failed` file with zero failing tests, which reads like a flake rather than a missing mount. Fixed 2026-08-23 by mounting `./benchmark:/benchmark:ro` in `docker-compose.override.yml`; read-only because the frontend must never write the benchmark of record. CLAUDE.md requires vitest to run in Docker, so mounting is the fix, not running it on the host. |
| **A bare directory name in `.gitignore` matches at every depth** | `scripts/` sat under the benchmark-logs heading and silently excluded **both** `backend/scripts/` and the repo-root `scripts/` — five documented files were untracked, including `verify_authz_policy.sh`, which `BACKEND.md` instructs you to run, and the Layer-4 backfill script this file references. Nothing failed: the files exist locally, `make` targets work, docs read correctly, and only a fresh clone reveals the gap. Fixed 2026-08-23 by removing the pattern (`node_modules/` and `.next/` were already ignored on their own lines, so it was protecting nothing). **Anchor any future directory ignore with a leading slash** (`/path/scripts/`), and after adding a script that docs or a Makefile target reference, confirm with `git status --untracked-files=all` that git can actually see it. |
| **Unit tests cannot catch query-semantics bugs** | Every bug the suite has missed was a query bug: `.neq()` vs NULL, `.in_()` against a set the fake ignores. Test doubles implement filters as passthroughs, so a filter whose bug *is* its filtering always passes. These need a real database or a real browser. |
| **A safety-critical answer must never be streamed to the screen** | `POST /search/synthesize/stream` (2026-08-23) renders progressively, but `CONFIDENCE:` arrives **after** `ANSWER:` in the parse contract, and `LLMService.result_gate` can turn a complete answer into a refusal based on it. Streaming the text would therefore show an operator words the gate is about to retract — the "hedged partial answer" `ARCHITECTURE.md` forbids outright. So the six `SAFETY_CRITICAL_CATEGORIES` emit **no `delta` events at all**: they stream `status` only, with `streaming_text: false` and a reason the UI shows, then one terminal `done`. `tests/test_synthesis_stream.py` asserts this per category. Two rules follow: **`done` is authoritative and `delta` text is provisional** (the frontend holds it on `Turn.streaming`, never merged into `answer`), and the streaming path calls the **same** `evidence_gate` / `result_gate` methods as `synthesize()` — a second copy of a refusal rule would drift and whichever an operator hit would be the wrong one. |
| **A `StreamingResponse` has no `response_model`, so nothing filters it** | The first live run of the SSE endpoint shipped the provider's entire raw chat-completion object to the client under `raw`, because only the non-streaming endpoint's `SynthesizeResponse` was doing the filtering. `_done_payload` now projects onto that model's fields **by whitelist**, so a new internal key on the service result never leaks by default. Any future streaming endpoint has the same hole — project explicitly. |
| **Ground truth outside the prompt's taxonomy scores as model failure** | `validation_corpus` carried 12 `COMPONENT` labels; `_NER_PROMPT` requests 10 types and `COMPONENT` is not among them, so the model could never produce one. Those 12 (23% of the corpus) were guaranteed false negatives, **and each also booked a false positive** against whatever in-taxonomy type the model gave the same span — one mismatch punished twice. Reported F1 was 0.6733; excluding them it is 0.7816. `NER_ENTITY_TYPES` in `api/services/ner.py` is now the single source of truth, `test_ner_taxonomy_matches_the_prompt` fails if it drifts from the prompt text, and the gate reports `scored_labels` / `unscoreable_labels` / `unscoreable_by_type`. **Adding an entity type means editing the constant AND the prompt**, and any corpus label outside the constant is silently excluded from the score — check `unscoreable_by_type` before trusting a gate number. |
| **A model-gate score is meaningless without its `validity`** | `NERService.extract_entities` degrades to a regex last resort that only matches `ASSET_TAG`, and it self-reports the path it took in the result's `model` field. Until 2026-08-23 the *worker* gate ignored that, so a run where 52 of 55 calls returned 429/500 was written to history as `passed: true`, F1 0.7317 — the regex's score under the model's name, and **higher** than the model's real 0.6733. `FallbackCountingNER` (`api/services/ner.py`) now wraps the service for both the worker and `run_model_validation.py`, and the run records `validity` / `fallback_extractions` / `extraction_paths`. Two consequences to obey: **a run without `validity: "VALID"` is not a measurement**, and `_latest_valid_baseline` deliberately skips both SUSPECT and pre-2026-08-23 rows, so the first clean run has no baseline and reports `passed: true` by default — that is a fresh-install state, not a pass. Filter validity **in Python**: a PostgREST `.neq("details->>validity","SUSPECT")` matches nothing, because legacy rows have no such key and `NULL != 'x'` is NULL. |
| **The gate re-extracted every document once per asset-class partition** | `evaluate()` built `doc_predictions` locally, so the global pass and each per-class pass extracted the same documents independently — the comment above the partition loop asserted the opposite invariant with nothing enforcing it. Cost: double the model calls, and global vs per-class scores computed from two different extractions that could disagree. A run-scoped `cache` threaded through every `evaluate()` call fixed it: **55 calls → 27, and 3 → 27 reaching the model.** If you add another `evaluate()` call site, pass the same cache or you silently restore the duplication. |
| **An OCR path that fails by returning `""` is invisible, and it has already cost weeks** | Both original OCR defects failed *silently*: a wrong response key (`label`, never returned — the live shape is `text_prediction.text`) and an oversized image, each returning an empty string that the caller reported as `nim_returned_no_text`. That was then read as the Layer-3 "no handwriting model" limitation for weeks, and it is a **key name**: the model reads the corpus's handwriting at ~0.90. Fixed 2026-08-23, and the logs are now deliberately distinguishable — `ocr.no_detections` (model ran, saw nothing) vs `ocr.detections_unparsed` (detections returned but no text field matched — **the schema moved**) vs `ocr.image_downscaled` / `ocr.image_too_large`. **Never add an OCR path that reports failure by returning an empty string**, and if you touch the parser, `ocr.detections_unparsed` is the line that tells you the response schema changed. |
| **`_shrink_for_inline` and `PIDService._fit_b64` are two copies of one algorithm** | Both re-encode an oversized image under the 180 KB inline cap, and `_NIM_IMAGE_SIZE_LIMIT = 180_000` is defined in **both** `services/ocr.py` and `services/pid.py`. They were written independently, which is exactly why Path B never hit the OCR size bug. **Change one and the other silently drifts.** Two differences to preserve if they are ever merged: the OCR copy tries an **unscaled JPEG first** (which alone took an 11.3x-over scan from 2,027,896 to 102,628 base64 chars, costing no resolution, where `_fit_b64` starts at 0.85 and always resizes), and it returns raw bytes rather than an encoded string. Tracked as Backlog #16. |
| **OCR confidence is real now — and the quarantine gate still does not use its shape** | `overall_confidence` was hardcoded `0.95` for every OCR extraction until 2026-08-23, so `confidence < 0.7 → quarantine` was applied to a number that could never be below 0.7. It is now the model's own per-span confidence weighted by span length. **The hazard is not closed:** the worst corpus document scores **0.719, above the 0.7 line**, so it still reaches the canonical graph with 4 of 22 spans below 0.7 and one at 0.253. `min_span_confidence` / `low_confidence_spans` / `span_count` are emitted and `ocr.low_confidence_spans` logs it, but nothing gates on them. **Do not "just fix" this — it changes what quarantines and over-tightening pushes clean scans into review, which `ARCHITECTURE.md §3` warns against. It is decision D1.** |
| **A harness that reads Elasticsearch tells you nothing about the model** | `run_ocr_gate.py` makes **zero** model calls — it compares already-indexed text against a clean sibling. So fixing `services/ocr.py` alone did **not** move it — `UNSCOREABLE 4/4` was not a verdict on OCR quality, it was an indexing gap. There is no reprocess endpoint and `POST /documents/ingest` dedups on SHA-256, so a re-upload always returns `{"status": "duplicate"}` — closing this needed calling the pipeline activities directly, bypassing that endpoint. **D2 executed 2026-08-24** (see [D2 executed](#d2-ocr-backfill-executed--2-of-4-documents-fixed-2026-08-24)): 2/4 now scoreable, `run_kg_completeness.py` moved 16/21 → 18/21. The other 2 remain correctly capped — not a leftover bug, the span-confidence gate quarantining them is working as designed. |
| **`CLAUDE.md` is a symlink to `AGENTS.md`** | They are one file (`CLAUDE.md -> AGENTS.md`). Editing either edits both, and `git status` only ever shows `AGENTS.md`. The "four lists that must stay in sync" for the service-free test tier are therefore really **three files**: `AGENTS.md`, `docs/TESTS.md`, `.github/workflows/tests.yml`. All three drift silently — nothing fails when they disagree, because CI runs its own copy of the list. |
| **A gate run killed by the Celery soft time limit writes nothing at all** | `time_limit=600 / soft_time_limit=540` was calibrated when nearly every NER call failed fast on a 429, making a full run ~2.5 min. Once the calls actually reach the model each costs tens of seconds and a real run takes ~12 min, so two consecutive runs died on `SoftTimeLimitExceeded` with **no history entry** — strictly worse than recording a degraded one. Raised to 1860/1800 on 2026-08-23. Watch this if the corpus grows: the limit tracks `corpus_size × per-call latency`, and the failure mode is silent absence, not an error row. |

### Frontend — build & runtime

| Area | Fix |
|---|---|
| `dynamic(ssr:false)` build error | Not allowed in Server Components (Next 16) — put it in a `"use client"` wrapper (`components/lazy.tsx`) |
| eslint `react-hooks/purity` | No `Date.now()`/`new Date()` in render — move clock reads to `lib/utils.ts` (e.g. `nowMs`, `slaCountdown`) |
| eslint `set-state-in-effect` | Wrap async fetch in a `load()`; for mount-once DOM/token sync, scoped `eslint-disable` with a reason |
| DB junk from tests | Suite purges on teardown; `make purge-test-data` or full rebuild — never UI-filter test rows |
| FE type drift (root of most bugs) | FE types were built speculatively and crashed on live data. Verify shapes against live `curl`; `x?.arr.length` still throws when `arr` undefined — guard `?? []`. Fixed: `compliance/dashboard.total_gaps` = `{critical,major,minor}` object (not a number); `SlaReport` = escalation report (`overdue_quarantine_items`, `overdue_*_total`, no on-time tallies); `CircuitBreakerState` = `{states[],halted_count}`, `halted` bool; `ValidationCorpusStats` has no `by_asset_class`. **Now guarded by `tests/test_contract.py`.** |
| Blast-radius / topology are nested | `blast-radius/{id}` → `affected:[{edge,target}]`; `documents/{id}/topology` → nested `topology.{equipment_nodes,isolation_valves,isolation_boundaries,instrumentation_loops}`. Both flattened to the UI shape **inside the `api.ts` fetcher** (adapter). Guarded by `test_contract.py`. |
| Service-worker refresh loop | `public/sw.js` registered **production-only** (`app-shell.tsx` gates on `NODE_ENV`, unregisters in dev); navigations network-first. A dev-cached shell + changed chunk hashes = infinite reload. Bump `SHELL` cache version to bust. |
| Turbopack dev 404s-everything | A tight reload loop can corrupt the dev route manifest → all `(app)/*` 404 while `/` 307s. `docker restart kairos-frontend` clears it; not a code bug. |
| `next build` fails on `/_global-error` (`useContext` null) | Next 16.2.10's **default** global-error page fails to prerender. Fixed by a custom `src/app/global-error.tsx` (client, own `<html>/<body>`, **inline styles only** — no providers/tokens exist at that level). Keep it self-contained; don't import app components or `next/image` there. |
| `next build` exits 137 in the dev container | OOM — `kairos-frontend` is capped at **2 GB**, and a Turbopack production build needs more. Not a code error (compile + prerender succeed). CI (ubuntu-latest ~7 GB) and the Docker image build on the runner, not this container. To build locally, raise the container `mem_limit` or run on the host. |
| `not-found.tsx` uses plain `<img>`, not `next/image` | The root not-found renders inside the `_global-error` boundary at build time, where `<Image>`'s config context is null → prerender crash. Use a plain `<img>` (eslint-disable `no-img-element`), same as `brand-link.tsx`. |
| API boot race on ES | `kairos-backend-api` runs `ensure_indices()` at startup and **exits** if ES isn't ready. If the API is down after `make dev`, `docker restart kairos-backend-api` once ES is healthy. |

### Cloud stores — Neo4j Aura · Qdrant · Supabase

| Area | Fix |
|---|---|
| **Neo4j + Qdrant are CLOUD** (Aura + Qdrant Cloud, via `.env`) | Local `kairos-neo4j`/`kairos-qdrant` containers are **profile-gated** — they do NOT start by default; `docker compose --profile local-stores up` brings them back for offline dev/tests. Cloud creds live in `.env` only (never in compose). Aura DB is named after the instance (e.g. `2016aa75`), **not** `neo4j` — always open sessions with `database=settings.NEO4J_DATABASE` (GraphService defaults to it). Cloud Qdrant **requires payload indexes** on any filter field (`asset_id`, `document_id`, `is_quarantine`) — `init_qdrant.py` creates them; without them filtered searches 400. Every Qdrant client must pass `api_key=settings.QDRANT_API_KEY` or it 403s. |
| **Never run the write-heavy test suite against cloud** | `pytest tests/` creates + purges test entities; the teardown purge is unreliable against cloud Supabase (transient Cloudflare 500s) and **pollutes the golden data**. **There is no fully-local option.** `--profile local-stores` covers Neo4j and Qdrant only — the suite writes to Supabase heavily and there is **no local Supabase** in `docker-compose.yml` (the one postgres there is Temporal's), so Supabase is always a hosted project. The only safe full-suite run is against a **throwaway Supabase project** via CI's `integration` tier, and that tier is **deliberately left disabled** (2026-08-23 decision): `CI_SUPABASE_*` is unset, so the job gates off and exits 0 and no provider quota is spent per push. **Consequence accepted, not a defect: there is no current full-suite pass count**, and the service-free tier (374) is the only enforced backstop. To restore clean golden data: truncate Supabase operational tables + wipe Neo4j/Qdrant/ES, then `init-all → seed → load-dataset`. **Measured extent, 2026-08-23** (the accepted consequence, quantified): `offboarding_sessions` 17 rows of which **16 are test-minted** (`resp_`/`qtest_`/`detail_`/`retiring_` + uid, from `test_elicitation.py`) leaving one real seed programme (`EXPERT-RKUMAR`); 96 of 101 `offboarding_session_items`; 4 `quarantine_items`; 68 of 86 Supabase `assets` carry `eam_source` `test`/`integration_test`; 95 of 137 `operational_events` belong to test assets; `audit_log.performed_by` includes `test-runner` and `e2e-sweep`. `scripts/purge_test_data.py` does **not** cover the off-boarding family — `SUPABASE_TARGETS` has no entry for either table, which is why that family accumulates while `ASSET-TEST-*` does not. Demo-visible on `/offboarding` and `/management`. Cleanup is **deliberately not automated**: the purge runs as an autouse session fixture (`conftest.py`), so adding the off-boarding tables there arms an irreversible delete against cloud data on the next unguarded suite run. See Pending. |
| **Pointing the app at `--profile local-stores`** | The compose admin user is hardcoded to `neo4j` (Neo4j rejects any other initial admin name). To point the app at the local container, also set `NEO4J_USERNAME=neo4j` / `NEO4J_PASSWORD=$NEO4J_LOCAL_PASSWORD` in `.env`. |
| **What the benchmark writes** | `run_benchmark.py` + `verify_layers.py` write **only `audit_log` rows** (one per synthesis, ~37 per full sweep) — append-only, no golden data touched, no schema change. `run_compliance_eval.py` and `run_load_test.py` are read-only; `run_model_validation.py` writes one `model_gate_result` row (`--no-persist` to skip). Safe to run against cloud; it does spend NIM/Jina quota. |
| **Benchmark checkpoints must live on a mounted path** | `run_benchmark.py --checkpoint` writes each graded question as it lands so a crash costs the remainder, not the run — but `/tmp` is **container-local**, and a rebuild mid-run wipes it. Use `/app/.benchmark_runs/` (bind-mounted to `backend/.benchmark_runs/` by `docker-compose.override.yml`). Launch detached with `docker exec -d` and write logs there too. |
| Seed cloud (run once) | `make init-all` (schema + Qdrant collections **+ payload indexes**) → `make seed` (regulations + users) → `make load-dataset`. Idempotent. Doc pipelines are async — re-run `scripts/seed_validation_corpus.py` ~30 s after load (validation_corpus needs ES content indexed first). |
| Neo4j Aura keep-alive | Aura Free pauses after 3 days idle. **Handled by `.github/workflows/uptime.yml`** (daily 03:17 UTC) — it queries Aura *directly* with the driver, so it works whether or not a backend is deployed. Needs repo secrets `NEO4J_URI`/`NEO4J_USERNAME`/`NEO4J_PASSWORD`/`NEO4J_DATABASE`. GitHub disables scheduled workflows after 60 days of repo inactivity. |
| Neo4j driver pool settings are load-bearing | `dependencies.py` sets `liveness_check_timeout=30` + `max_connection_lifetime=300`. Aura closes **idle connections** within minutes, and without these a stale pooled connection throws `SessionExpired` → intermittent 500s on every Neo4j endpoint. Don't drop them; the daily keep-alive cron does **not** cover this. **Regression-tested 2026-08-22:** after a 10-minute idle window the four Neo4j-backed endpoints (`/compliance/dashboard`, `/assets/{id}/knowledge`, graph, blast-radius) all recovered with no `SessionExpired` — `run_soak_test.py` phase 3, and the reason that phase runs against **cloud** stores rather than local ones. |

### Feature-specific — endpoints, roles & pages

| Area | Fix |
|---|---|
| Asset knowledge shows duplicate facts | The graph can hold multiple physical `KNOWLEDGE_EDGE` relationships sharing one logical `edge_id` (Cypher `DISTINCT` can't collapse them — separate graph elements). `GraphService.get_asset_knowledge_at` dedupes by the `edge_id` property; the frontend graph fetcher also dedupes. |
| Model-gate run "does nothing" | `POST /governance/model-gate/run` only **enqueues** a Celery task that evaluates the NER model over the whole validation corpus (a NIM call per item) — it runs **~12 min**. `model_name` is optional (defaults to `NVIDIA_NIM_NER_MODEL`). The page shows a "queued" banner, disables the button, polls history every 20s, and auto-refreshes when the run lands. History endpoint returns raw audit rows `{items}` (contract-locked) → `api.ts` `getModelGateHistory` flattens to `{history:[ModelGateResult]}`. |
| `POST /search/rca-pack` slow (~90s) | Long NIM synthesis over the timeline (timed on Llama 3.1 70B); returns empty + `synthesis_available:false` when the graph lacks history → RCA page shows honest "Synthesis unavailable". Not a bug. |
| Off-boarding shapes | List `{items,total}` (item `id`/`total_sessions`); detail adds `session_items[]`. Route `[sessionId]` = **programme id** (select items in-page). Questions are `string[]`; responses `{item_id, responses:[{question_index,answer}]}`. Detail fetch uses a 6 s timeout (slow Supabase). Loader seeds a demo programme. |
| Field routes | **There is no mobile bottom tab bar** — no `BottomTabs`, no `FieldBottomTabs` (both names appear in older revisions). Mobile navigates via the hamburger sidebar; recover the component from git history if it is ever revived. Field gating is live: `role === "field_worker"` (`use-role.ts` `FIELD_ROLES`, `roleHome` → `/briefs`). Routes under `/field`: `deviation`, `elicitation`, `voice`. SW offline is prod-only; the IndexedDB write queue (`idb.ts`) is app-level and works in dev. |
| Role-based route access | Enforced centrally in `AppShell` via `routeAllowed(path, role)` + `roleHome(role)` in `use-role.ts` (one guard, not per-page). Staff surfaces need engineer/reliability/admin; `/system-health` is admin-only; a field worker hitting a gated URL is redirected to `/briefs`. Unlisted paths are open to all authed. |
| System Health page | `/system-health` (admin). Probes 11 cheap read-only API GETs + `/health/detailed` every 30s. Search is **excluded** from the always-on set (it embeds via Jina = rate-limited). Opt-in "AI models" section toggles NIM/Gemini/Jina/Groq via `GET /health/model?provider=…` (admin-only, once/min, off by default, `localStorage`-persisted). Never poll model probes by default — they spend provider quota. |
| Roles & personas | Five roles in `infra/policies/kairos.rego`; the frontend `Role` type now includes **`compliance`** (read-only auditor). `/compliance` + `/audit` use `STAFF_AND_COMPLIANCE`, everything else staff-only, and `roleHome("compliance") = /compliance` — the default `/management` is staff-only and would redirect-loop. Seeded users: admin · engineer · field_worker · **reliability** · **compliance**. Only `reliability`/`admin` may `promote_quarantine` (engineers resolve conflicts but do **not** promote — verified against live OPA). **OPA gates writes *and* sensitive reads** (2026-08-17): `GET`/`HEAD` on `/audit-log`, `/compliance`, `/governance`, `/documents`, `/events` are policy-checked, so a `field_worker` gets **403** rather than 200. `read_nonconformance` is deliberately narrower than `read_governance` — the compliance auditor's non-conformance view reads conflicts + quarantine without reaching the model gate or MoC. `/events/plant-state` is exempt (every persona's shell renders it). Backend grants mirror `use-role.ts`; verify with `tools/verify_authz_policy.sh`. |
| Custom OTEL metrics are per-process | `services/metrics.py` instruments are silent no-ops without a MeterProvider, so **every process that records a metric must call `setup_telemetry()`** — not just the API. Celery does it on `worker_process_init` (per forked child — an exporter thread does not survive a fork); `setup_telemetry(app=None)` skips the FastAPI-only instrumentor. Add a metric to a new process without this and it exports nothing, under any amount of traffic, with no error. |
| Sidebar footer | System information (all roles) · System health (admin) · **System settings** (renamed from "Settings"; route stays `/settings`). Help removed. Login has a "Try demo" → admin button. Tab titles = `Kairos: <page>`. |

---

## CI, tooling & project reference

- **`gh`** — GitHub CLI: PRs, issues, CI status.
- **Supabase MCP** (`mcp__claude_ai_Supabase__*`) — SQL, migrations, table inspection. Prefer over `docker exec`.

**Supabase:** project `ernffgrvdcikwwhkhiix` · bucket `kairos-vault` (private, immutable, 500 MB max)  
**Tests:** counts live in **one** place — [Verification snapshot](#verification-snapshot). Do not restate them here; this line held a stale copy for long enough to be quoted. Notables: `tests/test_contract.py` (response-shape contracts), `tests/test_model_validation.py` (NER surface-form-overlap matcher). Self-cleans on teardown · Package: `ghcr.io/kr1shnasomani/kairos`

**CI:** `tests.yml` is two tiers — **`unit`** runs the service-free tests (PII, query classification, retrieval fusion, spreadsheet/email ingestion, NER matching, P&ID, auth cache, config, **authz boundary**) with **no secrets and no network**, so it is green on every push and fork PR; **`integration`** runs the full suite against `--profile local-stores` and *skips with exit 0* unless `CI_SUPABASE_*` is set. **Never point CI at the production Supabase / Aura / Qdrant Cloud project** — the suite creates+purges entities and `make init-all` reinitialises schema, so it would corrupt the golden dataset on every push. Use a throwaway Supabase project, and set the secrets with `gh secret set CI_SUPABASE_URL` (etc.) yourself — they are never read from `.env` by any script in this repo. **Currently unset by choice (2026-08-23), so tier 2 never runs.** Note `--profile local-stores` covers Neo4j + Qdrant only; Supabase has no local counterpart, which is why tier 2 needs a project at all. **Recommended: leave tier 2 disabled** — it costs ~20 provider calls per push (Jina embed per `/search`, a synthesis cascade call per synthesize) and exhausting a provider tier makes synthesis silently return no answer, which reads as collapsed answer quality. `frontend.yml` (tsc·eslint·build·audit) passes in full. **`deps-audit.yml`** (added 2026-08-22) is the
per-push dependency check Dependabot cannot provide — `pip-audit` / `npm audit` / `govulncheck` on push
and PR to `main` plus `workflow_dispatch`, path-filtered to the manifests. Its `pip-audit` step carries
a **documented suppression baseline** (see Backlog #2): remove an `--ignore-vuln` line as soon as its
blocker clears, and never add one without a reason on the same line. Two CI facts worth knowing: `lint.yml` needs `pull-requests: read` or `dorny/paths-filter` fails with *"Resource not accessible by integration"* and every lint job silently skips on PRs; and `next/font/google` fetches DM Sans/Geist **from Google at build time**, so a runner that cannot reach fonts.googleapis.com fails the build with `Module not found: @vercel/turbopack-next/internal/font/google/font` — transient, retry it, or self-host via `next/font/local` to remove the class.

> **Ruff is pinned in `lint.yml`, and that is deliberate.** Unpinned, it runs whatever rule set the
> newest release enables — one release once took linting from green to **608 errors on an unchanged
> tree**. Rules live in `backend/ruff.toml` (`E`/`W`/`F`/`I`/**`UP`**, py312, line-length 120); `"UP"`
> is selected, so `Dict`/`List`/`Optional[X]`/`timezone.utc` cannot creep back in place of the PEP
> 585/604 spellings. Bump the pin deliberately, never implicitly, and verify against the **pinned**
> version (0.16.0) — a local 0.15.0 passing proves nothing about CI.

> Run tests **in Docker**, never on the host: `docker compose run --rm --no-deps -e KAIROS_SKIP_TEST_CLEANUP=1 kairos-backend-api pytest tests/<file> -q`.
> Host runs resolve different package versions and produce false failures (`auth.test.ts` / `api.test.ts` fail on host, pass in-container).  
**Release:** `git tag v{version} && git push origin v{version}`
