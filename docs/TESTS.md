# Kairos — Integration Test Suite

## How to run

All tests run **inside Docker**. There is no host shortcut: host package resolution differs from
the pinned images and produces false results — `auth.test.ts` and `api.test.ts` fail on the host
and pass in the container. A host run will lie to you.

### Flow checks — the stack, driven through the UI (`tools/e2e_flows.sh`)

Walks what a reviewer clicks, as each persona, against a loaded stack: pages render with no error screen
or console error, role redirects, API refusals (field worker → quarantine 403, engineer → PTW countersign
403), a sourced Copilot answer and a safety refusal, an RCA pack with no duplicated events, and an audit
pack that lists each document once. Uses host-installed `agent-browser`, so it runs on a developer
machine, not in CI.

```bash
./tools/e2e_flows.sh            # changes no workflow state — safe on demo data
./tools/e2e_flows.sh --mutate   # also PTW dual sign-off, deviation raise/resolve, supersede via the UI
```

`--mutate` leaves signed briefs, a resolved deviation and a superseded document behind: run it on a stack
you will reset, never on the dataset you are about to demo or benchmark.

### Tier 1 — service-free (494 tests, no stack, no secrets, no network)

These need nothing running. This is what CI's `unit` job executes on every push.

```bash
docker compose run --rm --no-deps -e KAIROS_SKIP_TEST_CLEANUP=1 kairos-backend-api \
  pytest -q tests/test_{pii,query_category,search_fusion,ingestion_formats,http_pool,\
model_validation,pid,auth_cache,config_guardrail,briefs_countersign,topology_verify,\
ot_coverage,phase_gate,extraction_path,timestamp_alignment,model_gate_classes,ner_parse,\
superseded_filter,brief_signing,attribution_evidence,authz_boundary,brief_paging,asset_bulk_import,quarantine_item_id,purge_safety,synthesis_stream,graph_query_policy,event_reorder,supply_chain,form_extraction,cross_functional,offboarding_session_id,corpus_filter,\
alias_expansion,ner_fallback,asset_tag_filter,linked_document_scope,nim_retry,rca_timeline,audit_evidence}.py
```

All **44** files, **494 tests** (2026-09-14). The seven newest:
`test_alias_expansion.py` — a query naming a confirmed alias (P-101) also searches its canonical asset.
`test_ner_fallback.py` — NIM NER calls are capped at 4 concurrent; a timeout or 5xx is retried but a 4xx
is not; a long document is extracted in chunks and merged, and a failed chunk keeps the others while
flagging recall as a floor; an unset `OLLAMA_BASE_URL` goes straight to regex.
`test_asset_tag_filter.py` — document references (WO-, PTW-, SOP-, month-year stamps) never become
alias candidates or quarantine items, and "HE-301 Shell and Tube Heat Exchanger" resolves to HE-301.
`test_linked_document_scope.py` — an asset-scoped search also matches documents the graph links to the
asset, the asset's own documents rank first within an authority level, and a graph outage degrades to
the primary-asset scope.
`test_nim_retry.py` — a NIM 502/503/504 is retried once before the cascade hands the answer to a
different model; a client error is never retried.
`test_rca_timeline.py` — the RCA timeline shows an event recorded in both Supabase and Neo4j once, orders
mixed UTC offsets by instant, and reads a naive timestamp as UTC.
`test_supabase_http.py` — Supabase REST reads survive a dropped pooled HTTP/2 connection: a GET/HEAD that hits a
dead connection is retried once, a second failure still raises, a write is never replayed, and every PostgREST
session in the process goes through the retry transport.
`test_synthesis_stream.py` also pins the streaming route's terminal events: a successful stream ends on `done` with
no `error`, and a failed one ends on `error` without exposing the exception text.
`test_image_utils.py` — the one shared NIM image downscale helper (OCR and P&ID): an image that fits after JPEG
re-encoding keeps full resolution, one already under the ceiling is sent untouched, one no step can fit returns
nothing, and both callers keep their return shapes.
`test_ocr_review_release.py` — releasing a document held by the OCR gate rebuilds ingestion's workflow params
from the stored vault URL and names the reviewer; a document whose artifact path cannot be recovered is refused.
`test_document_extraction_view.py` — the document extraction view and redacted export read entities back from
the graph edges carrying the document id: the entity is the non-document endpoint, a re-linked entity is
listed once at its strongest confidence, and only `MENTIONS_PERSON` names feed redaction.
`test_audit_evidence.py` — the compliance audit pack lists a document linked by several edges or assets
once, verified if any link is, with its highest confidence and every asset it covers.
`test_attribution_evidence.py` (12 tests) covers the pure
decision functions `_attribute` and `_classify_attestation` in `workers/attribution.py`,
including the brownfield regression that `genuine_failure` was unreachable on uninstrumented assets.
`test_authz_boundary.py` (41 tests) covers the trust boundary — which routes are policy-enforced,
that the middleware carries no second token verifier, fail-closed behaviour when OPA is
unreachable, and token-derived site scope.
`test_brief_paging.py` (14 tests) covers `routers/briefs.page_inbox` — the Layer 8 inbox rules that
break silently when reordered: `limit` applies *after* the governor/frozen filters rather than in
SQL (limiting the query let a full page of critical briefs hide a normal-priority one permanently),
the page is trimmed *before* pushes are recorded so an off-page brief cannot spend EEMUA governor
budget, and `delivered + frozen_page` never exceeds `limit`.
`test_quarantine_item_id.py` (10 tests) covers `dependencies.valid_quarantine_item_id` and
asserts all four quarantine-by-id routes are wired to it.
`test_offboarding_session_id.py` (14 tests) covers `routers/elicitation._session_uuid` and pins
the fix for the off-boarding 500s: `offboarding_sessions.id` is a UUID column, so an unparseable
path segment reached PostgREST as 22P02 and surfaced as a 500 on a public route. It also asserts
no off-boarding handler has gone back to `.single()` — that raises PGRST116 on zero rows, which
made each handler's own 404 unreachable and turned every unknown programme into a 500.
`test_purge_safety.py` (24 tests) asserts no purge prefix or exact id can match a real id —
including `WO-2026-0714`, whose promoted item the compliance caveat cites — that every prefix
ends in `-`, and that nothing sits in both a prefix and an `_EXACT` list.
`test_synthesis_stream.py` (14 tests) covers the SSE path: **every safety-critical category
emits zero `delta` events**, the post-gate still retracts a low-confidence answer, the evidence
gate refuses before any provider call, and both synthesis paths call the same two gate methods.
`test_asset_bulk_import.py` (15 tests) covers `routers/assets.partition_import_rows` — existing
assets are skipped rather than overwritten (Neo4j uses `ON CREATE SET`, but the Supabase write is an
`upsert` that would otherwise replace `identity_confirmed_by` on re-import), duplicates within one
payload are reported rather than collapsed, and rows for another site are refused *before* the
existence check so the response cannot leak which asset ids exist in a site the caller cannot read.
The seven conformance files (`briefs_countersign` … `model_gate_classes`) are part of this tier —
an earlier version of this command listed only the first nine and undercounted it.

**This list, `AGENTS.md`'s, and CI's `unit` job must stay identical.** They drifted once already:
CI ran only the first nine files while the docs claimed the whole tier was gated, so eleven
service-free suites — every conformance test among them — never ran on a push. Fixed 2026-08-17.

```bash
```

### Tier 2 — full integration suite (needs the stack)

```bash
# Full suite
docker exec kairos-backend-api python -m pytest tests/ -q --timeout=120

# Single file / single test
docker exec kairos-backend-api python -m pytest tests/test_events.py -v --timeout=120
docker exec kairos-backend-api python -m pytest tests/test_governance.py::test_promote_quarantine_item -v

# DB-write verification tests (slower — wait for Temporal pipeline ~60s)
docker exec kairos-backend-api python -m pytest tests/test_db_writes.py -v --timeout=180
```

Prerequisites: the stack must be up, and seed users must exist — if login fails, run:

```bash
docker exec kairos-backend-api python scripts/seed_users.py
```

> ⚠️ **Run tier 2 against local stores, never cloud.** The suite creates and purges test
> entities and the teardown purge is unreliable against cloud Supabase, so a cloud run
> pollutes the golden dataset. Bring up `docker compose --profile local-stores up` and point
> `.env` at the local containers (see `INFRA.md` §`NEO4J_LOCAL_PASSWORD`). Set
> `KAIROS_SKIP_TEST_CLEANUP=1` to skip the purge entirely.

### CI

`.github/workflows/tests.yml` mirrors the two tiers:

| Job | Needs | Behaviour |
|---|---|---|
| `unit` | nothing | Runs the 494 service-free tests on every push and fork PR, plus the benchmark grader selftest. Must stay green. |
| `integration` | `--profile local-stores` + a **throwaway** `CI_SUPABASE_*` project | Runs the full suite. **Skips with exit 0** when `CI_SUPABASE_URL` is unset, so a missing optional credential is never a red build. |

Neo4j, Qdrant, Elasticsearch and Redis run as local containers in CI, so Aura and Qdrant Cloud
are never touched.

To enable tier 2, set the secrets yourself — there is deliberately no script that reads them
out of `.env`:

```bash
gh secret set CI_SUPABASE_URL                # from a THROWAWAY Supabase project, not production
gh secret set CI_SUPABASE_ANON_KEY
gh secret set CI_SUPABASE_SERVICE_ROLE_KEY
gh secret set CI_SUPABASE_JWT_SECRET
gh secret set NVIDIA_NIM_API_KEY
gh secret set JINA_API_KEY
gh secret set GROQ_API_KEY
```

> **Recommended: leave the integration job disabled.** Enabling it costs **~20 provider calls
> per push** — every `/search` embeds the query via Jina, `/search/synthesize` walks the
> NIM → OpenRouter → Gemini cascade, and elicitation calls the LLM. Gemini's free tier is a few hundred requests/day and
> is shared with the benchmark harnesses, so a busy day of pushes exhausts it; once it 429s,
> synthesis silently returns no answer and *measured answer quality collapses* (observed:
> 24/25 → 13/25). Tier-1 gives 415 green tests with **zero** provider calls, which is the
> signal CI should be providing. Enable tier 2 only for a deliberate pre-release run, against
> a throwaway Supabase project.

**Never point CI at the production Supabase project** — `make init-all` reinitialises schema and
the suite purges entities, so it would corrupt the golden dataset on every push.

---

## Architecture

Tests live at the **project root** in `tests/`, mounted into the container via `docker-compose.yml`:

```
tests/                        ← project root (NOT inside backend/)
  __init__.py                 ← makes tests/ a proper package (prevents site-packages conflict)
  conftest.py                 ← shared fixtures: auth tokens, HTTP clients, shared_asset_id
  test_annotations.py
  test_assets.py
  test_audit_log.py
  test_auth.py
  test_briefs.py
  test_compliance.py
  test_db_writes.py           ← DB-level verification: Neo4j edges, Qdrant vectors, ES documents
  test_documents.py
  test_elicitation.py
  test_events.py
  test_governance.py
  test_health.py
  test_model_validation.py    ← Layer-0 NER span-overlap matcher (pure logic, no network)
  test_ot_connector.py
  test_pid.py                 ← P&ID topology JSON parsing (pure logic)
  test_search.py
  test_contract.py            ← response-shape contract tests for endpoints that historically drift
  # service-free tier (no stack, no secrets, no network — CI's `unit` job)
  test_pii.py                 ← PII redaction at the export boundary
  test_query_category.py      ← safety classification + both refusal gates + parse regressions
  test_search_fusion.py       ← RRF retrieval fusion
  test_ingestion_formats.py   ← spreadsheet + email ingestion
  test_http_pool.py           ← per-event-loop client + embedding LRU
  test_auth_cache.py          ← verified-token cache
  test_config_guardrail.py    ← fail-closed secret guardrail
  test_briefs_countersign.py  ← PTW dual sign-off
  test_topology_verify.py     ← P&ID element-by-element gate
  test_ot_coverage.py         ← coverage from verified topology only
  test_phase_gate.py          ← deployment phase gating
  test_extraction_path.py     ← extraction_path / handwriting_suspect flags
  test_timestamp_alignment.py ← cross-source drift
  test_model_gate_classes.py  ← per-asset-class model gate
  test_ner_parse.py           ← NER truncation recovery (max_tokens cliff)
  test_superseded_filter.py   ← superseded docs excluded from default retrieval
  test_brief_signing.py       ← HMAC acknowledgment signatures
  test_attribution_evidence.py ← pure attribution decision functions
  test_authz_boundary.py      ← policy enforcement, fail-closed, token-derived site scope
  test_brief_paging.py        ← Layer 8 inbox paging: limit after filtering, trim before push
  test_asset_bulk_import.py   ← Layer 1 golden-record import partitioning + tenancy boundary
  test_quarantine_item_id.py  ← Layer 6 quarantine id guard: malformed id 404s, never 500s
  test_purge_safety.py        ← purge matchers can never reach real ids (the DOC-X incident)
  test_synthesis_stream.py    ← SSE synthesis: safety-critical categories never stream text
  test_graph_query_policy.py  ← ARCHITECTURE §7: no unbounded traversal; + what may be called a conflict
  test_event_reorder.py       ← Layer 8 delay compensation; PTW never waits behind the hold
  test_supply_chain.py        ← ARCHITECTURE §8: served model matches the pin; submission outliers
  test_form_extraction.py     ← form fields reach quarantine ONLY; never a KNOWLEDGE_EDGE
  test_cross_functional.py    ← the function mapping is complete; an unmapped type inflates the result
  test_offboarding_session_id.py ← UUID path params 404 rather than 500 (`maybe_single`, not `single`)
  test_corpus_filter.py       ← test-artifact predicate: every real corpus name pinned against over-matching
pytest.ini                    ← project root
```

Suite size: **576 tests collected** across 50 files (`pytest tests/ --collect-only`, 2026-08-23).
The last full green run was **412 passed · 0 failed** (2026-08-22) and is **superseded** — 164 tests
have landed since. **There is no current full-suite pass count**: re-run tier 2 against local stores
to get one, and do not quote 412 as a pass figure for the present tree. **1 known transient flake**
(`test_briefs.py::test_attribution_worker_queues_recheck` — a work-order POST occasionally 500s under
concurrent load; passes deterministically in isolation).

**Volume mounts** (in `docker-compose.override.yml` under `kairos-backend-api` — they are dev-only;
the base `docker-compose.yml` bakes code into the image and mounts no source):

```yaml
volumes:
  - ./backend:/app
  - ./tests:/app/tests         # test files
  - ./pytest.ini:/app/pytest.ini
```

**Environment variables** set on the container for tests:

| Variable | Value | Purpose |
|---|---|---|
| `PYTHONPATH` | `/app` | Ensures `tests/` resolves to `/app/tests/`, not the ML library's `tests` package in site-packages |
| `OT_CONNECTOR_URL` | `http://kairos-backend-go:8090` | Go connector URL (different inside vs. outside Docker) |
| `API_BASE_URL` | *(unset — defaults to `http://localhost:8000`)* | FastAPI base URL; localhost works inside the API container because uvicorn binds there |

---

## Configuration (`pytest.ini`)

```ini
[pytest]
asyncio_mode = auto     # all async tests run automatically without @pytest.mark.asyncio
testpaths = tests
timeout = 90            # per-test timeout in seconds (overridable per-request with timeout= param)
pythonpath = .          # adds rootdir to sys.path (belt-and-suspenders alongside PYTHONPATH env)
```

---

## Fixtures (`tests/conftest.py`)

All fixtures are **session-scoped tokens** (sync) + **function-scoped async clients**.

### Admin auth — INTERNAL_API_KEY (never expires)

`admin_client` does **not** log in via Supabase. It uses the static `INTERNAL_API_KEY` (`kairos-internal-dev-key`) as a Bearer token. FastAPI's `get_current_user` detects this key and returns `role=admin` without calling Supabase. This eliminates JWT expiry failures mid-run.

```python
admin_client     # AsyncClient with Bearer kairos-internal-dev-key (role=admin, never expires)
```

### Tokens — session scope (sync `httpx.post`)

```python
engineer_token   # logs in as engineer@kairos.local — role: engineer
field_token      # logs in as field_worker@kairos.local — role: field_worker
```

Session scope avoids re-authenticating on every test. Sync `httpx.post` avoids event-loop scope conflicts with pytest-asyncio.

### HTTP Clients — function scope (async)

```python
admin_client     # AsyncClient with INTERNAL_API_KEY (role=admin)
engineer_client  # AsyncClient authenticated as engineer
field_client     # AsyncClient authenticated as field_worker
anon_client      # AsyncClient with no auth header
```

Each test gets a fresh client, ensuring no state bleeds between tests.

### Shared asset — session scope

```python
shared_asset_id  # Creates one PUMP asset once; reused by tests that need an existing asset
```

Tests that need deduplication isolation must create their own assets with `uid()`.

### `uid()` utility

```python
from tests.conftest import uid
# returns uuid4().hex[:8].upper() — e.g. "A3F2C1B9"
# used to generate unique IDs per test run to avoid collisions
```

### Data hygiene — automatic teardown

Tests run against the live stack and create ephemeral entities with known id prefixes
(`ASSET-TEST-`, `ASSET-DEDUP-`, `ASSET-EV-`, `ASSET-ACK-`, `WO-*`, `DOC-*`). A session-scoped
autouse fixture in `conftest.py` (`_cleanup_test_data`) purges all of them at the end of the run
via `scripts/purge_test_data.py`, so the suite no longer accumulates junk in Neo4j, Supabase, or
Elasticsearch.

- Skip cleanup for a run: set `KAIROS_SKIP_TEST_CLEANUP=1`.
- Clean up manually at any time: `make purge-test-data`.
- Cleanup never fails the suite — if a store is unreachable it logs and moves on.
- Do **not** rely on UI-side filtering of test prefixes to keep demos clean; keep the *canonical*
  state (the golden dataset, see [`DATASET.md`](./DATASET.md)) free of test data by rebuilding.

---

## Test files and coverage

### Conformance workstreams — service-free (added 2026-08-16)

These run with **no stack, no secrets, no network** and are part of CI's `unit` job. They were
written service-free deliberately: Supabase has no local counterpart, so a write-heavy test would
have to hit the production project.

| File | Covers | Cases |
|---|---|---|
| `test_briefs_countersign.py` | PTW dual sign-off — two distinct signers required, self-countersign rejected, double-countersign rejected. Includes the regression for scoping the read by recipient, which made every real countersign 404. | 7 |
| `test_topology_verify.py` | P&ID element-by-element gate — partial confirmation does not promote, one disputed element blocks canonical, confirming promotes the existing edge. Includes the `.neq()`-vs-NULL regression that emptied the element map. | 11 |
| `test_ot_coverage.py` | Coverage from **verified** topology only; unverified topology is not coverage; no linked drawing → `none`, never a fabricated tag. | 6 |
| `test_phase_gate.py` | Deployment phases — default is 3 (inert), phase 1 disables synthesis, phase < 3 persists a brief but suppresses the push. | 6 |
| `test_extraction_path.py` | `extraction_path` / `handwriting_suspect` on every OCR envelope; engineering drawings excluded; confidence untouched by the flag. | 8 |
| `test_timestamp_alignment.py` | Cross-**source-system** drift only; same-source events are not drift; unparseable timestamps skipped rather than read as epoch-zero. | 9 |
| `test_model_gate_classes.py` | Per-asset-class gate — a regressed class is blocked, others unaffected, enforcement off by default, lookup failure fails **open**. | 6 |
| `test_superseded_filter.py` | **Superseded documents must not read as current.** ES and Qdrant both exclude them by default; the exclusion is `must_not superseded`, never `must active`, because `kairos_assets` docs and pre-existing Qdrant points carry no `status` at all and would otherwise vanish. Time-travel (`as_of`) re-includes them. Covers the `Filter(must=…) or None` regression that dropped the exclusion when no other condition existed. | 7 |
| `test_brief_signing.py` | **HMAC acknowledgment signatures.** Deterministic, and bound to every fact it claims — brief, signer, action, timestamp, key. A signature captured on one brief cannot be replayed onto another, and ack vs countersign never collide. | 3 |
| `test_ner_parse.py` | **NER truncation recovery.** `max_tokens: 1024` truncates the JSON on entity-dense documents; `json.loads` rejected the whole response and the document fell to the regex path (ASSET_TAG only). Salvage keeps the complete objects and flags `parse_recovered`; unrecoverable garbage still returns `None`. | 8 |

`test_query_category.py` also gained the post-synthesis safety gate cases and the
`parse_synthesis_response` regressions (missing `ANSWER:` marker; RCA citing a document called
`None`).

> **What these cannot catch.** Every bug this project's unit suite has missed was a *query
> semantics* bug — `.neq()` against a NULL JSONB key, `.in_()` against a set the fake ignores. Test
> doubles implement filters as passthroughs, so a filter whose bug *is* its filtering always passes.
> Those need a real database or a real browser; see `implementation/e2e-sweep.md`.

### `test_health.py` — Stack liveness (3 tests)
| Test | What it verifies |
|---|---|
| `test_health_returns_200` | `GET /health` → 200 |
| `test_health_response_shape` | Response has `status`, `timestamp` fields |
| `test_health_detailed` | `GET /health/detailed` → all 5 service pings succeed |

### `test_auth.py` — Authentication (Layer 0, 8 tests)
| Test | What it verifies |
|---|---|
| `test_login_admin` | Admin JWT obtained |
| `test_login_engineer` | Engineer JWT obtained |
| `test_login_field` | Field worker JWT obtained |
| `test_login_wrong_password` | 401 on bad credentials |
| `test_login_unknown_email` | 401 on unknown email |
| `test_me_admin/engineer/field` | `GET /auth/me` returns correct role per token |
| `test_invalid_token_rejected` | Malformed Bearer token → 401 in all modes |
| `test_refresh_token` | Token refresh flow works |

### `test_assets.py` — Asset MDM (Tasks 1-3, Layer 1, 15 tests)
| Test | What it verifies |
|---|---|
| `test_create_asset` | POST /assets/ → 201, asset in Supabase + Neo4j |
| `test_create_asset_is_idempotent` | Duplicate asset_id → 200 (MERGE, not error) |
| `test_create_asset_auto_id` | No asset_id supplied → one is generated |
| `test_get_asset` | GET /assets/{id} → correct fields |
| `test_get_asset_not_found` | Unknown asset_id → 404 |
| `test_list_assets` | GET /assets/ → items/total envelope |
| `test_list_assets_filter_site` | `?site_id=` filter works |
| `test_list_assets_filter_equipment_class` | `?equipment_class=` filter works |
| `test_get_asset_aliases` | Alias resolution (TAG → canonical ID) |
| `test_get_asset_hierarchy` | Parent-child hierarchy traversal |
| `test_get_asset_knowledge` | Knowledge graph facts for an asset |
| `test_get_asset_knowledge_as_of` | Bitemporal `as_of` filtering on graph edges |
| `test_get_asset_knowledge_invalid_as_of` | Malformed `as_of` → 422 |
| `test_field_worker_cannot_create_asset` | Role enforcement: field_worker → 403 on POST |
| `test_field_worker_can_list_assets` | field_worker can GET /assets/ |

### `test_documents.py` — Document Vault + Pipeline (Tasks 4-8, 20, Layers 2-3, 16 tests)
| Test | What it verifies |
|---|---|
| `test_ingest_document_accepted` | POST /documents/ingest → 202, SHA-256 in response |
| `test_ingest_duplicate_is_idempotent` | Same bytes → status=duplicate, same document_id |
| `test_ingest_document_linked_to_asset` | `asset_id` param links doc to asset in Supabase |
| `test_pipeline_advances_beyond_queued` | Temporal worker moves stage past "queued" within 60s |
| `test_get_extraction_status` | GET /documents/{id}/status → pipeline_stage field |
| `test_extraction_status_not_found` | Unknown doc_id → 404 |
| `test_get_extraction_results` | `/extraction` endpoint returns `graph_edges_created` |
| `test_get_document_metadata` | GET /documents/{id} → metadata fields |
| `test_get_document_not_found` | Unknown doc → 404 |
| `test_list_documents` | GET /documents/ → items/total envelope |
| `test_list_documents_by_asset` | `?asset_id=` filter works |
| `test_list_documents_by_type` | `?document_type=` filter works |
| `test_supersede_document` | Vault immutability: old doc marked superseded, edges closed |
| `test_supersede_already_superseded_returns_409` | Double supersede → 409 |
| `test_topology_not_found_for_non_pid` | Non-P&ID doc has no topology → 404 |
| `test_topology_endpoint_exists_for_pid_drawing` | P&ID drawing → topology endpoint responds (200 or 404, never 5xx) |

### `test_db_writes.py` — DB-Level Write Verification (Tasks 4-6, Layers 2-3)
Queries Neo4j, Qdrant, and Elasticsearch directly after the document pipeline completes. These tests are slower (~60-90s) because they wait for the full Temporal pipeline.

| Test | What it verifies |
|---|---|
| `test_neo4j_knowledge_edge_written` | All 6 required KNOWLEDGE_EDGE properties present: `valid_from`, `valid_to` (stored as sentinel `9999-12-31 23:59:59 UTC` for open-ended edges — Neo4j drops null properties so a real datetime is used), `authority_level`, `document_id`, `confidence`, `verification_status` |
| `test_neo4j_document_node_written` | Document node is merged into Neo4j with matching `document_id` |
| `test_qdrant_vectors_indexed` | At least one vector chunk in `kairos_documents` collection with `document_id` payload |
| `test_elasticsearch_document_indexed` | Document findable in `kairos_documents` ES index by `document_id` term query |

> **Timeout:** Use `--timeout=180` when running `test_db_writes.py` alone. The shared test suite uses `--timeout=120` which may be tight for pipeline-heavy tests.

> **`_ingest_and_wait()` helper:** Ingests a document then polls the pipeline status until a terminal stage is reached — `_TERMINAL = {"complete", "review_required", "failed"}`. Intermediate stages such as `ner_running` are passed through without aborting; only genuinely stuck or unknown states cause a skip.

### `test_annotations.py` — NER Active Learning (Task 21, Layer 3, 8 tests)
| Test | What it verifies |
|---|---|
| `test_annotation_stats_shape` | `/annotations/stats` returns total, corrections_this_week, top types |
| `test_create_annotation_correct` | `is_correct=True` → 201, feeds validation corpus |
| `test_create_annotation_correction` | `is_correct=False` + corrected_type → 201 |
| `test_create_annotation_feeds_corpus` | Correct annotation appears in validation corpus stats |
| `test_list_annotations_returns_created` | Listed annotations match what was submitted |
| `test_list_annotations_requires_document_id` | Missing `document_id` param → 422 |
| `test_list_annotations_empty_for_unknown_doc` | Unknown doc → empty list, not error |
| `test_annotation_missing_required_fields` | Missing entity_text/type/is_correct → 422 |

> **Note:** Annotations require a real `document_id` (FK constraint on `ner_annotations`). Tests ingest a document first.

### `test_events.py` — Event Ingestion (Tasks 13-16, 33, Layer 8)
| Test | What it verifies |
|---|---|
| `test_ingest_work_order` | 202, `status=accepted`, `brief_task_id` present |
| `test_work_order_deduplication` | Same payload twice → second is `deduplicated` |
| `test_work_order_recurring_detection` | `recurring_detected` field present on second WO |
| `test_get/ack_event` | Event retrieval and acknowledgement |
| `test_ingest_ptw` | PTW event → `priority=critical`, `brief_id` generated |
| `test_ingest_shift_handover` | Handover event → brief task queued |
| `test_ingest_alarm` | Alarm → 202 accepted |
| `test_ingest_tag_out` / dedup | LOTO tag-out + deduplication |
| `test_ingest_inspection_complete_passed` | High confidence → `quarantine_item_id=null` |
| `test_ingest_inspection_complete_low_confidence_quarantined` | confidence < 0.7 → quarantine |
| `test_deviation_flag_and_resolve` | Flag deviation → resolve with `disputed` resolution |
| `test_deviation_flag_resolve_promoted` | `resolution=promoted` + `moc_warranted=False` → `briefs_unfrozen` in response, `moc_id=null` |
| `test_deviation_flag_resolve_moc_warranted` | `resolution=promoted` + `moc_warranted=True` → `moc_id` starts with `MOC-` |
| `test_ingest_inspection_with_document_id` | Inspection with `document_id` → INSPECTION_RECORD Neo4j edge → `edge_id` non-null |
| `test_set_and_get_plant_state` | Plant state gate: normal/turnaround/shutdown/emergency |

> **Dedup isolation:** Tests that assert deduplication behavior create fresh unique assets with `uid()` to avoid bleeding from `shared_asset_id`.

### `test_briefs.py` — Brief Delivery + EEMUA 191 Governor (Tasks 8, 13, 16, Layer 8)
| Test | What it verifies |
|---|---|
| `test_get_my_briefs_shape` | Response includes `briefs`, `total_pending`, `governor_state` |
| `test_governor_ceiling_is_6` | Hard ceiling is exactly 6 pushes/operator/hour |
| `test_governor_state_is_valid_value` | State is one of: normal / suppressed |
| `test_get_governor_status_endpoint` | `/briefs/governor/status` responds with push count + ceiling |
| `test_get_briefs_unacknowledged_only_default` | `?unacknowledged_only=True` returns only pending briefs |
| `test_get_briefs_all_including_acknowledged` | `?unacknowledged_only=False` includes all briefs |
| `test_brief_not_found_returns_404` | GET `/briefs/{uuid}` with non-existent UUID → 404 |
| `test_ack_nonexistent_brief_returns_404` | POST `.../ack` for non-existent brief → 404 |
| `test_brief_feedback_requires_rating` | Feedback with valid rating → 200/404/422, never 500 |
| `test_ack_brief_via_ptw` | PTW with `issuing_engineer_id=service-kairos-connector` → `brief_id` returned immediately → ack → 200 with `status` field |
| `test_attribution_worker_queues_recheck` | `rating=incorrect` on a real brief → `confidence_recheck_queued` row in `audit_log` |

> **UUID requirement:** Brief, conflict, and quarantine endpoints use PostgreSQL UUID columns. Tests use `str(uuid4())` for fake IDs — plain strings cause Postgres parse errors → 500.

### `test_search.py` — Hybrid Search + Synthesis (Tasks 9-12, Layer 11, 11 tests)
| Test | What it verifies |
|---|---|
| `test_search_returns_response_shape` | `query`, `results`, `total`, `retrieval_methods` present |
| `test_search_empty_query_rejected` | Missing `q` param → 422 |
| `test_search_with_asset_scope` | `?asset_id=` filter works |
| `test_search_authority_filter` | `?authority_min=` param accepted |
| `test_search_with_as_of` | `?as_of=` time-travel filter works |
| `test_search_result_fields` | Each result has `retrieval_method` and `relevance_score` |
| `test_search_asset_scoped_endpoint` | `GET /search/assets/{id}` works |
| `test_synthesize_response_shape` | POST /search/synthesize → `refused`, `safety_critical`, `sources` |
| `test_synthesize_safety_critical_refusal` | `query_category=max_allowable_pressure` → `safety_critical=True` |
| `test_rca_pack_response_shape` | `/rca-pack` → `timeline`, `hypotheses`, `supporting_documents` |
| `test_rca_pack_refused_on_low_confidence_safety` | `refused` field present and boolean |

> **Safety categories:** Must use exact keys from `SAFETY_CRITICAL_CATEGORIES` in `backend/api/services/llm.py`: `max_allowable_pressure`, `isolation_interlock_sequence`, `torque_specification`, `electrical_rating`, `pressure_relief_setting`, `safety_shutdown_setpoint`. Other strings won't trigger the safety gate.

> **LLM timeouts:** Synthesize and RCA pack tests use `timeout=120.0` per-request — LLM calls can be slow.

### `test_governance.py` — Governance Layer (Tasks 21-25, 34, Layer 7, 23 tests)
| Test | What it verifies |
|---|---|
| `test_list_conflicts_shape` | Conflicts list → items/total envelope |
| `test_list_conflicts_filter_track` | `?track=administrative` filter works |
| `test_conflict_not_found` | UUID that doesn't exist → 404 |
| `test_resolve_conflict_not_found` | POST resolve on non-existent UUID → 404 |
| `test_resolve_administrative_conflict` | Resolve open admin-track conflict → `status=resolved` (skipped if none exist) |
| `test_resolve_engineering_track_conflict_rejected` | Engineering-track conflicts require MoC webhook → 400 (skipped if none exist) |
| `test_list_quarantine_shape` | Quarantine list → items/total/note envelope |
| `test_quarantine_defaults_to_pending` | Default filter returns only `review_status=pending` items |
| `test_quarantine_filter_by_review_status` | `?review_status=disputed` filter works |
| `test_promote_quarantine_item` | Low-confidence inspection → quarantine → promote → `edge_id` returned |
| `test_dispute_quarantine_item` | Quarantine item → dispute → `status=disputed` |
| `test_double_promote_returns_409` | Promoting already-promoted item → 409 |
| `test_sla_report_shape` | SLA escalation report fields present |
| `test_circuit_breaker_shape` | SPC circuit breaker states per asset class |
| `test_list_moc_shape` | GET /governance/moc → items/total envelope |
| `test_get_conflict_detail` | GET `/governance/conflicts/{id}` → 200 with `conflict` + `blast_radius` fields (skipped if no conflicts) |
| `test_moc_webhook_bad_payload` | Malformed webhook payload → 400 |
| `test_moc_webhook_valid_payload` | Valid MoC webhook (created via deviation flag resolve) → 200, `moc_id` + `resolution` in response |
| `test_blast_radius_nonexistent_doc` | Blast radius for unknown doc → 200 empty (not 404) |
| `test_validation_corpus_stats` | Corpus coverage stats by entity type |
| `test_model_gate_history` | GET /governance/model-gate/history → items/total |
| `test_model_gate_run_requires_admin` | field_worker → 403; admin → 200 with `task_id` |

### `test_compliance.py` — Compliance (Task 26, Layer 7, 9 tests)
| Test | What it verifies |
|---|---|
| `test_list_frameworks` | GET /compliance/frameworks → list of regulatory frameworks |
| `test_compliance_dashboard_shape` | GET /compliance/dashboard → gap counts by framework |
| `test_list_gaps` | GET /compliance/gaps → items/total envelope |
| `test_list_gaps_filter_framework` | `?framework=` filter works |
| `test_audit_pack_shape` | GET /compliance/audit-pack → `status=draft`, `note` contains sign-off warning |
| `test_audit_pack_oisd_117` | OISD_117 audit pack generated without error |
| `test_gaps_reduce_after_document_promotion` | Promoting a procedure clears its compliance gaps |

### `test_elicitation.py` — Elicitation (Tasks 19, 29-31, Layer 9, 12 tests)
| Test | What it verifies |
|---|---|
| `test_voice_note_ingest_accepted` | Audio file upload → 202, `task_id` + `sha256` in response |
| `test_voice_note_idempotent` | Same bytes twice → both 202 (accepted or duplicate) |
| `test_trigger_no_conditions_not_triggered` | No trigger conditions met → `triggered=False` |
| `test_trigger_novel_troubleshooting_triggers` | `novel_troubleshooting=True` → `triggered=True`, workflow_id |
| `test_elicitation_questions_not_found` | GET questions for unknown WO → 404 |
| `test_submit_elicitation_responses` | Trigger novel → get questions → submit responses → 200 |
| `test_create_offboarding_programme` | Creates programme, returns `session_id`, `total_sessions` |
| `test_offboarding_requires_engineer_or_admin` | field_worker → 403 |
| `test_submit_offboarding_responses` | Create programme → get items → submit responses for first item |
| `test_list_offboarding_shape` | GET /elicitation/offboarding → items with completion_pct |
| `test_get_offboarding_programme` | GET /elicitation/offboarding/{id} → session items with statuses |
| `test_get_offboarding_questions_for_session` | GET questions for specific session item |

> **Voice note MIME type:** Supabase storage bucket does not allow `audio/wav`. Tests use `application/octet-stream` as content type.

> **Voice dedup is async:** The dedup check reads from `quarantine_items` which is populated by the Celery transcription worker. Both uploads correctly return 202 but the second may not yet show `status=duplicate` synchronously.

### `test_audit_log.py` — Audit Trail (Task 25, Layer 7, 9 tests)
| Test | What it verifies |
|---|---|
| `test_audit_log_shape` | GET /audit-log/ → items/total/limit/offset envelope |
| `test_audit_log_filter_entity_type` | `?entity_type=brief` returns only brief entries |
| `test_audit_log_filter_action` | `?action=brief_acknowledged` filters correctly |
| `test_audit_log_filter_performed_by` | `?performed_by=` filter works |
| `test_audit_log_has_entries_after_asset_write` | Log is non-empty after test setup actions |
| `test_audit_log_entry_fields` | Each entry has `action`, `entity_type`, `performed_by` |
| `test_audit_log_filter_combined` | Combined `entity_type` + `action` filter works |
| `test_audit_log_filter_entity_id` | `?entity_id=` filter returns only entries for that entity |
| `test_audit_log_pagination` | Page 1 and page 2 entries don't overlap |

### `test_ot_connector.py` — Go OT Connector (Task 17, Layer 5, 8 tests)
Hits the **Go service at port 8090** (`http://kairos-backend-go:8090` inside Docker, `http://localhost:8090` from host).

| Test | What it verifies |
|---|---|
| `test_ot_connector_health` | `/health` → `status=ok`, `service=kairos-connector` |
| `test_ot_query_requires_asset_and_tag` | Missing params → 400 |
| `test_ot_query_returns_timeseries` | `/ot/query?asset_id=&tag=` → `data[]`, `from`, `to` |
| `test_ot_query_mock_flag` | `mock=true` when `PI_WEBAPI_BASE_URL` not set |
| `test_ot_coverage.py` (6 cases, service-free) | `GET /assets/{id}/ot-coverage` — verified loops yield real drawing tags; **unverified topology is not coverage**; no linked drawing → `none`, never a fabricated tag |
| `test_ot_coverage_unknown_asset` | Unknown asset → 200 with mock coverage (not 404) |
| `test_eam_sync_returns_completed` | `/eam/sync` loads fixture → `status=completed`, `synced>=0` |
| `test_eam_work_order_forwarding` | Go `/eam/work-order` → proxied to FastAPI → `status=accepted/deduplicated` |

### `test_pii.py` — PII redaction, DPDP export boundary (5 tests, **no services**)

| Test | Asserts |
|---|---|
| `test_redacts_structured_identifiers` | Email, phone, Aadhaar, PAN, employee ID, shift ID all masked — asserts each literal is *absent* from the output |
| `test_person_names_masked_with_stable_pseudonym` | Same name → same `[PERSON_1]` twice, so cross-references survive |
| `test_equipment_tags_and_part_numbers_are_not_pii` | `EQ-101`, `MS-4471-B`, `XV-203`, `OISD-117` pass through untouched — redaction must not damage operational content |
| `test_clean_text_is_returned_unchanged` | No PII → identical text, `pii_found=False` |
| `test_spans_reference_original_offsets` | Span offsets index the original text, not the masked output |

### `test_query_category.py` — Safety-critical classification + refusal gate (32 tests, **no services**)

| Test | Asserts |
|---|---|
| `test_safety_critical_queries_are_classified` (×10) | MAWP, PSV set pressure, isolation boundary, torque, insulation class, ESD setpoint each map to the right category |
| `test_non_safety_queries_are_not_classified` (×4) | Alias, personnel, failure-count, OEM queries return `None` |
| `test_relief_setting_wins_over_generic_pressure` | Ordering guard: "relief valve set pressure" → `pressure_relief_setting`, not `max_allowable_pressure` |
| `test_refuses_safety_query_on_unauthoritative_evidence` | Level-5 field observation only → `refused=True`, `answer=None`, sources still returned |
| `test_authoritative_evidence_clears_the_gate` | Level-3 OEM evidence with no `confidence` field → **not** refused (cascade stubbed) |

### `test_search_fusion.py` — RRF retrieval fusion (6 tests, **no services**)

| Test | Asserts |
|---|---|
| `test_bm25_scale_does_not_beat_cosine` | A BM25 score of 98.6 does not outrank a cosine 0.91 at equal authority; the doc both sources agree on wins |
| `test_authority_still_outranks_relevance` | Level 1 before level 5 regardless of fused score — the safety property holds |
| `test_merge_keeps_the_longest_snippet` | Duplicate collapse keeps the richer snippet, so synthesis still sees the fact |
| `test_documents_without_ids_are_dropped` | Empty `document_id` never enters the ranking |
| `test_graph_edge_renders_readable_snippet` | A graph hit carries text, not `""` |
| `test_unverified_graph_edge_is_flagged_quarantine` | `verification_status != verified` → `is_quarantine` |

### `test_ingestion_formats.py` — Spreadsheet + email ingestion (4 tests, **no services**)

| Test | Asserts |
|---|---|
| `test_spreadsheet_rows_and_sheet_names_extracted` | Both sheets with names; every cell value present; blank rows dropped |
| `test_unreadable_spreadsheet_degrades_without_raising` | Garbage bytes → empty text + `requires_review`, no exception |
| `test_email_headers_body_and_attachment_names` | Headers, body and attachment *filename* extracted; attachment bytes never inlined |
| `test_mbox_archive_yields_every_message` | Both messages in a 2-message mbox are extracted |

### `test_http_pool.py` — Pooled HTTP client + embedding cache (8 tests, **no services**)

| Test | Asserts |
|---|---|
| `test_same_loop_reuses_one_client` | Second call in one loop returns the same client |
| `test_new_event_loop_gets_a_fresh_client` | Each `asyncio.run()` loop gets its own client — the Celery case a global client would break |
| `test_closed_client_is_replaced` | A closed client is never handed out again |
| `test_close_is_idempotent` | Double close does not raise |
| `test_cache_never_stores_a_failed_embedding` | `[]` is never cached — would poison every later search |
| `test_cache_evicts_least_recently_used` | LRU order respected at `maxsize` |
| `test_task_is_part_of_the_cache_key` | `retrieval.query` vs `retrieval.passage` do not collide |

---

## What the tests prove vs. what they don't

### Proven
- All API routes exist and return correct HTTP status codes
- Request/response contracts (shapes, required fields, error codes) are correct
- Auth and RBAC: roles enforced correctly (admin vs engineer vs field_worker)
- Deduplication logic works for work orders, tag-outs, documents, voice notes
- Quarantine gate: `confidence < 0.7` routes to quarantine; promote/dispute flows work
- Safety-critical refusal: exact SAFETY_CRITICAL_CATEGORIES trigger `safety_critical=True`
- EEMUA 191 governor ceiling is 6; governor state is valid
- Vault immutability: supersede closes edges, double-supersede returns 409
- Pipeline: Temporal worker advances document past "queued" within 60s
- **Conflict resolution:** non-existent UUID → 404; admin-track → resolved; engineering-track → 400
- **Elicitation responses:** novel troubleshooting and offboarding response submission work end-to-end
- **Go connector WO forwarding:** `POST /eam/work-order` proxied from Go to FastAPI
- **Attribution worker:** `rating=incorrect` → `confidence_recheck_queued` row in audit_log
- **Neo4j KNOWLEDGE_EDGE:** all 6 required properties present and correctly typed
- **Qdrant vectors:** document chunks indexed with `document_id` payload in `kairos_documents`
- **Elasticsearch:** document indexed in `kairos_documents` with correct `document_id`

### Not proven (known gaps)
- **Celery worker correctness end-to-end:** tasks are queued and accepted; the Neo4j confidence update after recheck is not verified — only that the task was queued
- **Concurrent correctness:** dedup under concurrent load, governor under burst
- **Attribution Neo4j edge update:** `confidence_recheck_queued` verifies the task was queued, not that Neo4j confidence values were updated afterwards

---

## Test users

Seeded by `docker exec kairos-backend-api python scripts/seed_users.py`:

| Email | Password | Role |
|---|---|---|
| `admin@kairos.local` | `KairosAdmin123!` | admin |
| `engineer@kairos.local` | `KairosEngineer123!` | engineer |
| `field_worker@kairos.local` | `KairosField123!` | field_worker |
| `reliability@kairos.local` | `KairosReliability123!` | reliability |
| `compliance@kairos.local` | `KairosCompliance123!` | compliance |

> **Admin client in tests:** `admin_client` does NOT use Supabase JWT. It uses `INTERNAL_API_KEY` (`kairos-internal-dev-key`) which never expires. This eliminates mid-run JWT expiry failures on long test suite runs.

---

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `ImportError: cannot import name 'uid' from 'tests.conftest'` | `PYTHONPATH` not set; site-packages `tests` package wins | Ensure `PYTHONPATH=/app` is in container env (set in docker-compose.yml) and `tests/__init__.py` exists |
| Admin login fails (401) | Test users not seeded | `docker exec kairos-backend-api python scripts/seed_users.py` |
| `422 Unprocessable Entity` on asset create | `criticality` value invalid | Use `critical` / `safety_critical` / `non_critical` — not `high`/`medium`/`low` |
| `500` on brief/conflict fake ID | UUID expected by Postgres | Use `str(uuid4())` not plain strings like `"BRIEF-FAKE"` |
| `500` on voice upload | Supabase bucket rejects `audio/wav` MIME | Use `application/octet-stream` in tests |
| Document ingest returns `status=duplicate` | Same bytes → same SHA-256 | Append `uid()` to content bytes to guarantee uniqueness |
| Work order dedup test fails (first call already `deduplicated`) | `shared_asset_id` was used by a prior test within the dedup window | Create a fresh unique asset per dedup test |
| `test_synthesize_safety_critical_refusal` → `safety_critical=False` | Wrong category key | Use exact key: `max_allowable_pressure` (see `backend/api/services/llm.py`) |
| Search result assertion fails on `score` field | Field is `relevance_score`, not `score` | Assert `relevance_score` |
| OT connector tests fail inside Docker | `localhost:8090` not reachable from API container | `OT_CONNECTOR_URL` env var routes to `http://kairos-backend-go:8090` |
| `test_db_writes.py` times out | Temporal pipeline takes >90s | Run with `--timeout=180` or check Temporal UI at `http://localhost:8088` for stuck workflows |
| `test_neo4j_knowledge_edge_written` fails with missing `valid_to` key | Neo4j silently drops null properties, so a null `valid_to` never appears on the edge | Fixed in `GraphService.create_knowledge_edge()`: open-ended edges now store sentinel `datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)` — test passes reliably |
| Mid-run admin token expiry (401 in long runs) | Supabase JWT TTL < 9-minute suite runtime | `admin_client` now uses `INTERNAL_API_KEY` — no expiry; engineer/field tokens can still expire on very slow stacks |
