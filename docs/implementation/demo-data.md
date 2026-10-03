# Demo mode: full showcase data with working actions

Plan written 2026-10-03. Nothing in this file is built yet. It replaces the one-line plan in
[`status.md` D9](./status.md#open-decisions--blocked-on-a-human-call-not-on-work).

## 1. Goal

Two modes, one codebase.

| Mode | Who | Data | Writes |
|---|---|---|---|
| **Real** | every named account (admin, engineer, field worker, reliability, compliance) | the existing data, exactly as today | as today |
| **Demo** | the one-click demo login | a large showcase plant, on its own tenant | **every action works**, on demo rows only |

A demo visitor must be able to open any page and see a plant that looks big and alive, and click any
action (resolve a conflict, promote a quarantine item, sign a PTW, ingest a document, set plant state,
run an RCA) and watch it work. A demo token must never write a real row.

**Decision, 2026-10-03: the showcase is real data in the real stores, so every login sees it** (`SHOWCASE_VISIBLE_TO_ALL`,
default true). The partition by markers below stays in the code behind that one switch: set it false and real accounts see
real data alone again, with no data change. Consequences accepted: search, the graph and the Copilot for every account draw on
both plants, so the benchmark must be run with the switch off to measure the golden dataset alone.

## 2. What the code review of the current state found

1. **Isolation is partial.** `dependencies.site_scope` pins non-admins to their own `site_id`, and
   `site_id` exists on `assets`, `operational_events`, `plant_operating_states`, the document's
   `access_tags` and the Elasticsearch mapping. the `site_scope` docstring in `dependencies.py` records that search and
   documents have no real site boundary yet. The `demo` role also reads **cross-site**, like admin. So today a second
   site would **not** be isolated. Section 4 fixes that.
2. **Writes are blocked for demo in two places.** OPA denies every write for `demo`, and 20 pages wrap
   their controls in `DemoGate`. Both change, but only once the backend enforces the tenant on every
   write (section 5).
3. **There is no local Supabase,** so even the local stack writes to the cloud project. Rehearsal is therefore a dry run plus fakes (section 7), not a local copy; the real load is one deliberate step.
4. **Blocker found while starting the benchmark: NVIDIA retired the pinned LLM.**
   `nvidia/nemotron-3-super-120b-a12b` answers `410 Gone` on NIM and is gone from `/v1/models`. Live
   Copilot answers now come from the OpenRouter fallback. This hits the demo (every Copilot, RCA and
   brief answer) and the benchmark (a fallback run is marked SUSPECT). It is decision Q1 below and
   comes before any benchmark number is quoted.

## 3. The showcase plant (the data)

One fictional plant, built to look like a real mid-size site, deterministic (seeded generator), every
id prefixed `DEMO-`, every date relative to load time so it never goes stale.

| Area | Volume | Notes |
|---|---|---|
| Sites | 2 | `SITE_DEMO` (the plant) and `SITE_DEMO_B` (a tank farm), so `/management/cross-site` has real patterns |
| Assets | about 120 | site, unit, system, equipment, part hierarchy; pumps, exchangers, valves, compressors, instruments, safety systems; all criticality classes; aliases and tag variants |
| Documents | about 150 | procedures, P&IDs with verified and candidate topology, OEM manuals and bulletins, inspection reports, MoC records, regulatory filings; supersede chains; some held by the OCR gate |
| Events | about 400 over 90 days | work orders, PTWs, tag-outs, inspections, alarms, shift handovers; recurring-failure chains (the same seal failing twice), some drift between source systems |
| Briefs | about 40 | all trigger types, per recipient role, some acknowledged, some suppressed by the governor, PTW briefs awaiting a countersign |
| Governance | 12 conflicts, 25 quarantine items, 6 MoC | across every state (open, pending MoC, resolved, disputed, promoted), every input type, overdue and fresh SLAs |
| Plant state | 90 days of history | including a halted period |
| Knowledge capture | 3 off-boarding programmes, 8 elicitation sessions, voice notes | retiring-expert transfer with real interview text |
| Compliance | clause coverage with a spread of gaps, 2 signed audit packs | OISD, ISO 45001, Factory Act, PESO |
| Reliability | circuit-breaker baselines, 6 model-gate runs, push-volume history | enough history for the charts to mean something |
| Audit trail | a few hundred rows | produced by the loader doing real actions, not inserted by hand |

### Page by page (each must have data and a working action)

| Page | Data it needs | Demo actions that must work |
|---|---|---|
| Overview | KPIs, 14-day event trend, attention list, recent signals | open any card |
| Briefs, brief detail | per-recipient briefs of every type | acknowledge, feedback, PTW countersign |
| Copilot | indexed demo documents and graph facts | ask, rate answer, annotate entities, safety refusal still refuses |
| Assets, asset detail, register, bootstrap | the hierarchy, aliases, knowledge, provisional assets | register, bulk import, confirm identity |
| Events, event detail | 90-day stream | emit each event type, acknowledge, correlate, knowledge capture link |
| Voice, deviation, elicitation | open work orders | record a note (quarantines), raise a deviation, answer a micro-interview |
| RCA | recurring-failure chains | generate a pack |
| Graph, coverage | the temporal graph and coverage matrix | filter, time-travel |
| Compliance, audit pack, non-conformance | clause coverage and gaps | sign an audit pack |
| Governance hub, conflicts, quarantine, MoC, SLA, drift, push volume, circuit breaker, model gate | every state above | resolve, promote, dispute, request info, MoC approve, run model gate |
| Documents, detail, compare, topology, ingest | the document set | ingest a new file, supersede, release or reject an OCR hold, verify topology, redacted export |
| Audit trail, projects, off-boarding | the loader's own actions | complete an off-boarding interview |
| System health, settings | live probes | read only |

## 4. Isolation design (decided 2026-10-03: current stores only, nothing new)

**Decision:** no second deployment, no new Supabase project, no new Neo4j, no schema change. The
showcase lives in the same stores as the real data and is kept apart by a marker that every table
already has room for. An earlier draft proposed a separate demo stack and a tenant column on every
table; the audit below (about 170 Supabase calls, 75 Cypher queries, workers that build their own
clients) showed that either would be a large, risky change to real mode.

**One direction, easy to check.** A real account never reads a showcase row. The `demo` role reads
everything (real and showcase), as it always has, and may write only to showcase rows.

| Store | Marker | Real accounts | Demo role |
|---|---|---|---|
| Supabase `assets`, `asset_alias_map`, `briefs`, `knowledge_conflicts`, `quarantine_items`, `moc_items`, `elicitation_sessions`, `document_asset_links` | `asset_id` (or `canonical_asset_id`) starts with `DEMO-`. A showcase quarantine item always has a showcase asset, so a NULL asset is real | hidden by `tenant.scope(..., nullable=True)` on every list and aggregate read | no filter |
| `operational_events`, `plant_operating_states` | `site_id` in `SITE_DEMO`, `SITE_DEMO_B` | `tenant.scope_site` | no filter |
| `documents` | `access_tags.site_id` in the demo sites | `tenant.scope_document_site` | no filter |
| `offboarding_sessions` | `personnel_id` starts with `DEMO-` | `tenant.scope` | no filter |
| `audit_log` | actor is a demo account, entity id starts with `DEMO-`, or `details.tenant = demo` for system rows | `tenant.scope_audit` | no filter |
| Neo4j | asset id starts with `DEMO-` | `$hide_demo` parameter in `DEMO_VISIBLE_CYPHER`, beside `REAL_ASSET_CYPHER`; the parameter defaults to hide, and a caller that omits it fails loudly | `hide_demo = false` |
| Qdrant and Elasticsearch | separate `_demo` collection and indices in the same services, written by the pipeline for a showcase document | never queried | queried as well as the real one |
| Storage | path prefix `demo/` | unreachable by id | |

Filters are always in the query, never in Python, so `count` and `range` stay correct. Wildcards use
`*`: this project's Supabase edge answers 500 to a `%` pattern (verified 2026-10-03, read-only).
`or` filters combine as AND when repeated (verified).

**Done (2026-10-03, not deployed):** `services/tenant.py`; `site_scope` lets the demo role see every
site; the list and aggregate reads in governance (conflicts, quarantine, SLA report, MoC, push volume,
timestamp drift), events, elicitation and off-boarding, assets (list, coverage, provisional, aliases),
documents, audit log, and the three compliance Cypher queries are scoped; `tests/test_tenant_isolation.py`
(30 tests) pins every filter shape and keeps a registry of the reads that must be scoped.

**Still to do in this phase:** search and briefs (route the `_demo` collection and indices through
`VectorStoreService` and `SearchEngineService`, and write to them from the pipeline), annotation and
circuit-breaker statistics, the SLA service's audit marker, the benchmark's own document query
(`run_kg_completeness.py` must exclude showcase documents).

## 5. Making actions work safely

- OPA gives `demo` the write actions it needs, but **the backend refuses a demo write whose target is
  not a showcase row** (asset id, site or document marker above), so a policy mistake cannot reach real
  data. `DemoGate` is removed from the 20 pages.
- A demo action must not feed a statistic that real mode reads: it skips the `extraction_overrides`
  and `validation_corpus` inserts (they drive the circuit breaker and the model gate) and the model
  gate itself stays admin-only. The action still succeeds.
- Actions that spend money or are irreversible in the real world get limits, not a block:
  document ingest, Copilot, RCA, brief assembly are capped per demo session per hour; the MoC webhook
  is stubbed in demo.
- Demo writes stay append-only like everything else (supersede, never delete).
- **Reset:** `make reset-demo` re-seeds the showcase. It is the only code path that deletes, it can
  only match the markers above, and it ships with a safety test in the style of `test_purge_safety.py`.
- **Staying fresh:** every showcase date is an offset from load time, and a small scheduled re-anchor
  shifts only showcase rows forward each day (the idea of `redate-demo`, scoped to the markers).

## 6. How the data is made

- The showcase is part of `dataset/` itself: new `showcase_*` files beside the golden ones in the same folders
  (`00_Reference` to `05_Governance_And_Handover`; the sixth is new). A seeded generator (`scripts/showcase/`, `make generate-showcase`)
  writes it; the loader, the redate and the reset read only the files, so a hand edit is what gets loaded. Dates are
  stored at a snapshot anchor and moved to load time on read (`scripts/showcase/files.py`).
- **Documents go through the real pipeline** (OCR, NER, embedding, graph linking, quarantine), so the
  graph, search and Copilot answers are genuine and the quarantine items arise naturally. Structured
  rows (assets, events, plant state, history) load through the real API wherever a route exists, so
  every row is created by the same code paths a user would hit and the audit trail fills itself.
- Idempotent (`DEMO-` ids, insert-or-skip), resumable, and dated against "now" at load time.

## 7. Loading, with the real data protected

The load writes into the current cloud stores, so it is a deliberate step: a dry run first (prints
every row it would create, creates nothing), then a go-ahead from you for the real run. The run is
additive only. Before and after it, `tools/` compares the real-mode counts (assets, documents,
conflicts, quarantine, events as admin) and they must be identical.

## 8. Phases and status (2026-10-03)

| # | Step | Writes to cloud? | Status |
|---|---|---|---|
| 0 | Replace the retired LLM; re-run the benchmark on it | audit rows only | **Done** (Nemotron 3 Ultra, 43/46) |
| 1 | Read isolation: `tenant.py`, scoped reads, search stores, statistics, audit marker, tests | no | **Done** |
| 2 | Write guard and by-id read fence (`showcase_read_fence`, `demo_write_fence`, `tenant.guard_*`), OPA grants, `DemoGate` removal, demo cap, skipped statistic writes | no | **Done** |
| 3 | Showcase generator (`scripts/showcase/`) and loader with a dry run | no | **Done**, dry run clean against the live stores |
| 4 | `make redate-showcase`, `SHOWCASE_AUTO_REDATE`, `make reset-showcase` | no | **Done** |
| 5 | Tests for every piece, docs pass, offline suite, frontend suite | no | **Done** (954 backend, 353 frontend) |
| 6 | Load the showcase into the current stores through the local backend, verify locally | **yes** | **Done 2026-10-03.** Real-mode counts unchanged; isolation, search, by-id reads, actions and the golden linkage figure checked (status.md P19) |
| 7 | Deploy the backend to EC2 (the live API has none of the isolation code yet), then commit and push (the frontend deploys from the push) | deploy | Waiting for your go-ahead |

What the load does, in order: creates the `_demo` Qdrant collection and Elasticsearch indices (the only place that
does), posts the assets as the demo account (parents first), writes the aliases the pipeline resolves tags through,
ingests the documents (about 470) through the real pipeline and waits for it, writes the history (events, briefs, conflicts,
MoC, quarantine, knowledge capture, plant states) with the real document ids in the sources, mirrors the events into
the graph, posts nine live events so the real assembler builds current briefs (one permit awaits its second signature),
and fails loudly if any real-mode count moved.

Limits worth knowing: facts a visitor promotes into the graph stay after a reset (the graph supersedes, it does not
delete); the vault is never reset; the live events and the briefs they produce are not re-dated (their ids are random,
so the re-date cannot tell them from a visitor's rows); a demo account is shared, so the two-signature rule needs the
pre-seeded permit, which the demo account can countersign because someone else acknowledged it.

## 9. Rules that stay

- No cloud write without an explicit ask in that session (step 6 is that ask).
- Real data is never changed. The only new behaviour for a real account is "hide showcase rows", and
  that filter has a test per read.
- The benchmark site and every benchmark figure are untouched by showcase data.
- Provenance, quarantine and safety refusals behave identically in demo mode.

## 10. Decisions

| # | Question | Answer |
|---|---|---|
| Q1 | Replacement for the retired LLM | `nvidia/nemotron-3-ultra-550b-a55b` on NIM (see `status.md` P18) |
| Q2 | Isolation | Current stores only, marker based (section 4). Decided 2026-10-03 |
| Q3 | May `make reset-demo` delete showcase rows | Default yes, with the safety test, and only on your go-ahead |
| Q4 | Two demo sites so cross-site has data | Default two |
| Q5 | Hourly cap on LLM-backed demo actions | Default 20 per session |
