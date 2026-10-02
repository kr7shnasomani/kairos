# Kairos — Agent Context

## YOU MUST DO THIS BEFORE EVERY TASK

**1. Run `/ponytail lite`** — mandatory scope gate. No exceptions.  
**2. Match your domain in the table below and invoke ALL listed skills before writing code.** Skills are orders, not suggestions.  
**3. Read every file you will touch. Trace the full call chain.**

> ## 🛑 NEVER WRITE TO A CLOUD STORE
>
> **Do not create, modify or delete data in Supabase, Neo4j Aura, Qdrant Cloud or Elasticsearch —
> ever — without the user explicitly asking for that specific write in that specific session.**
> These hold the **golden dataset**, every benchmark figure is measured against it, and there is no
> backup. "It's just a backfill / re-index / one-off script" is exactly the thing this forbids.
>
> This is **stricter** than the older "Vault: never delete" and "tests: local stores only" rules
> below, which cover narrower cases and have been mistaken for the whole rule.
>
> **Reads are fine.** So are: the service-free test tier, anything under
> `-e KAIROS_SKIP_TEST_CLEANUP=1`, and the read-only harnesses (`run_ocr_gate.py`,
> `run_kg_completeness.py`). `tests/conftest.py` runs `purge_test_data.py` as an **autouse session
> teardown** — always pass `KAIROS_SKIP_TEST_CLEANUP=1` unless you have decided otherwise on purpose.
>
> Consequence you must accept rather than fix: some numbers are pinned below their true value
> because closing the gap needs a write. See
> [`status.md` § Open decisions](docs/implementation/status.md#open-decisions--blocked-on-a-human-call-not-on-work) — **D2**.

> **Picking up this project fresh? Start at
> [`status.md` § Open decisions](docs/implementation/status.md#open-decisions--blocked-on-a-human-call-not-on-work).**
> Those items are specified and cheap — they are waiting on a human call, not on engineering, so
> they are the wrong thing to "just implement" and the right thing to ask about. **D1 (what makes an
> OCR extraction quarantine) is decided — any span < 0.7 holds the document — and no open item has a
> data-integrity consequence.**
>
> **Hit a bug, a build failure, or something that looks wrong?** Check
> [`docs/implementation/status.md` § Known Pitfalls](docs/implementation/status.md#known-pitfalls)
> **before debugging** — it is almost certainly already documented there. That file also holds open
> work, current benchmark numbers, and CI/tooling detail. Read it when you need it, not every task.

---

## Skill Dispatch (MANDATORY — invoke every match before writing)

| Domain | Invoke these skills |
|---|---|
| React / Next.js / RSC / page / component / hook | `vercel-react-best-practices` · `vercel-composition-patterns` |
| Tailwind class / token / `@theme` / CSS variable | `tailwind-4-docs` · `tailwind-design-system` |
| UI primitive / polish / anything in `ui.tsx` | `emil-design-eng` · `baseline-ui` · `web-design-guidelines` |
| Animation / motion / keyframe / skeleton | `review-animations` · `fixing-motion-performance` · `animation-vocabulary` |
| Route / page / view transition | `vercel-react-view-transitions` |
| TypeScript type / interface / generic / review | `typescript-advanced-types` · `typescript-react-reviewer` |
| React Flow / graph canvas / node / edge | `react-flow-code-review` |
| a11y / ARIA / focus / contrast / keyboard / screen reader | `accessibility` · `fixing-accessibility` · `accessibility-compliance` |
| PWA / offline / service worker / IndexedDB | `pwa-development` |
| Performance / CWV / LCP / CLS / INP / bundle | `performance` · `core-web-vitals` |
| Neo4j Cypher / graph query | `neo4j-cypher-skill` |
| Neo4j Python driver / `execute_query` | `neo4j-driver-python-skill` |
| Neo4j Go driver | `neo4j-driver-go-skill` |
| Neo4j GraphRAG / retrieval / document import | `neo4j-graphrag-skill` · `neo4j-document-import-skill` |
| Neo4j CSV import / vector index / GenAI plugin | `neo4j-import-skill` · `neo4j-vector-index-skill` · `neo4j-genai-plugin-skill` |
| Neo4j graph modeling / RBAC / security | `neo4j-modeling-skill` · `neo4j-security-skill` |
| Qdrant client / search / quality | `qdrant-clients-sdk` · `qdrant-search-quality` |
| Qdrant performance / scaling / monitoring | `qdrant-performance-optimization` · `qdrant-scaling` · `qdrant-monitoring` |
| Qdrant model migration / version upgrade | `qdrant-model-migration` · `qdrant-version-upgrade` |
| Redis data model / connections | `redis-core` · `redis-connections` |
| Redis security / monitoring | `redis-security` · `redis-observability` |
| Elasticsearch / ES\|QL / authz | `elasticsearch-onboarding` · `elasticsearch-esql` · `elasticsearch-authz` |
| Grafana dashboard / panel | `grafana-oss` · `dashboarding` |
| Grafana alerting / IRM / SLO | `alerting-irm` |
| Prometheus / PromQL / Loki / Tempo | `prometheus` · `promql` · `loki` · `tempo` |
| OTEL / instrumentation / LLM observability | `opentelemetry` · `observability-edot-python-instrument` · `observability-llm-obs` · `observability-logs-search` |
| FastAPI / Pydantic / new project scaffold | `fastapi` · `fastapi-templates` |
| Python code / design patterns / perf / tests | `python-code-style` · `python-design-patterns` · `python-performance-optimization` · `python-testing-patterns` |
| Celery task / queue / worker | `celery-expert` |
| Go code / errors / performance / tests | `golang-code-style` · `golang-error-handling` · `golang-performance` · `golang-testing` |
| Docker / Compose / multi-stage Dockerfile | `docker-expert` · `multi-stage-dockerfile` |
| GitHub Actions / CI-CD | `github-actions-templates` |
| Temporal workflow / activity / worker | `temporal-developer` |
| Supabase / Postgres query / migration / auth | `supabase` · `supabase-postgres-best-practices` |
| AI model selection / HuggingFace | `huggingface-best` · `huggingface-local-models` |
| Complexity / YAGNI / over-engineering / debt | `ponytail` · `ponytail-review` · `ponytail-audit` · `ponytail-debt` |

Full manifest with descriptions: `.agents/SKILL_MANIFEST.md`

---

## Documentation

| Purpose | Path |
|---|---|
| **Open work · pitfalls · benchmarks · conformance · CI detail** | **`docs/implementation/status.md`** |
| 13-layer architecture | `ARCHITECTURE.md` |
| REST API reference · backend services/workers/config | `docs/API.md` · `BACKEND.md` |
| Infra (ports, stores, dev cmds) · Docker build & run modes | `docs/INFRA.md` · `DOCKER.md` |
| Database schemas · frontend routes & wiring | `docs/DATABASE.md` · `FRONTEND.md` |
| Implementation plans · E2E sweep (42 routes × 5 personas) | `docs/implementation/BE.md` · `FE.md` · `e2e-sweep.md` |
| Tests · golden dataset · benchmarks (results → `benchmark/RESULTS.md`) | `docs/TESTS.md` · `DATASET.md` · `BENCHMARKS.md` |
| Backend fixtures (mock-by-design) · deploy (AWS EC2 backend + Vercel frontend) | `docs/FIXTURES.md` · `DEPLOY.md` |

---

## Stack

**Backend:** FastAPI (Python 3.12) · **Neo4j Aura (cloud)** · **Qdrant Cloud** · ES 8.13 · Redis 7.2 · Temporal · Celery · Go 1.25 (Gin) · OPA · **OTEL → Grafana Cloud** · Supabase (Postgres + Storage + Auth + Vault)  
**Frontend:** Next.js 16 · React 19 · Tailwind CSS **v4** (not v3) · TypeScript strict · `node:20-alpine`  
**Models (cloud only):** LLM → NIM `nvidia/nemotron-3-super-120b-a12b` (thinking off) | NER → NIM `meta/llama-3.2-11b-vision-instruct` | OCR → NIM `nvidia/nemotron-ocr-v2` | Embed → Jina `jina-embeddings-v3` | STT → Groq `whisper-large-v3` — names in `.env`  
**Synthesis cascade:** Nebius Token Factory → NIM → OpenRouter → Gemini → Ollama, built by `services/model_providers.py` (`synthesis_cascade`). A tier with no API key is not in the list, so with only `NVIDIA_NIM_API_KEY` set this is NIM-only, as before. **Token Factory ships unkeyed in the repo, and is keyed in the local `.env` since 2026-09-23.** It serves the same Nemotron build as NIM, so activating it changes who serves the model, not which model answers. **A key being present is enough to spend credits:** whenever the stack runs it is tier 1 and every answer and brief bills Nebius. No call has been made yet (user decision, `status.md` P14); comment the key line out to revert to NIM with no code change. Whether it becomes the primary path is not yet decided. NVIDIA retired `llama-3.1-70b` (410, 2026-09-13); tier 1 is now Nemotron, so an OpenRouter (`llama-3.1-70b`) or Gemini answer is a fallback model and the benchmark marks such a run SUSPECT (`tokenfactory` and `nim` both count as the pinned model). `NVIDIA_NIM_TIMEOUT=60` **must stay under** the frontend's 90 s budget for `POST /search/synthesize`.  
**Cloud stores:** Neo4j (Aura), Qdrant, Supabase, Grafana — creds in `.env` only; local Neo4j/Qdrant are profile-gated (`--profile local-stores`). ES · Redis · Temporal · OPA · Go stay local. **Ports:** API `8000` · Frontend `3000` · ES `9200` · Redis `6379` · Temporal `7233/8088` · OPA `8181` · Go `8090`

---

## Dev Commands

Full list: `docs/INFRA.md §9`. Reset: `make nuke → dev → init-all → seed → load-dataset`. Gotcha rebuilds: `--no-deps --build kairos-frontend` (new npm deps) · `--force-recreate kairos-backend-api` (NIM env).

**Tests — Docker only, never the host.** Host package resolution differs from the pinned images and produces false results.
- Service-free tier (**839 tests**, 52 files, no stack/secrets/network — CI's `unit` job runs exactly this list; in the container 836 pass and 3 skip, because `infra/` and `.github/` are not mounted):
  `docker compose run --rm --no-deps -e KAIROS_SKIP_TEST_CLEANUP=1 kairos-backend-api pytest -q tests/test_{pii,query_category,search_fusion,ingestion_formats,http_pool,model_validation,pid,auth_cache,config_guardrail,briefs_countersign,topology_verify,ot_coverage,phase_gate,extraction_path,timestamp_alignment,model_gate_classes,ner_parse,superseded_filter,brief_signing,attribution_evidence,authz_boundary,brief_paging,asset_bulk_import,asset_counts,quarantine_item_id,purge_safety,synthesis_stream,graph_query_policy,event_reorder,supply_chain,form_extraction,cross_functional,offboarding_session_id,corpus_filter,alias_expansion,ner_fallback,asset_tag_filter,linked_document_scope,nim_retry,rca_timeline,audit_evidence,document_extraction_view,image_utils,ocr_review_release,supabase_http,redate_demo,sec_auth,sec_authz,sec_documents,sec_infra,sec_llm,cr_fixes}.py`
- Full suite (needs the stack; **local stores only, never cloud**): `docker exec kairos-backend-api python -m pytest tests/ -q --timeout=120`

---

## Non-Negotiable Rules

### Frontend
- **Tailwind v4 syntax only.** v4 ≠ v3 — invoke `tailwind-4-docs` first.
- Colors from `var(--token)` only. Never hardcode hex. One component, three palettes (light · dark · sunlight).
- No new npm deps unless the task names one. React Flow is the only pre-approved addition.
- SSR: `API_INTERNAL_URL` for server components; `NEXT_PUBLIC_API_URL` for browser. Never hardcode.
- **Live-only: there are no fixtures to fall back to.** `DataSource` is a single member (`"live"`), so a fallback cannot return without a type error. Fetchers **throw**; the app shows real data, a skeleton, or error+retry. Timeouts: reads 4 s, writes 8 s, `synthesize()` 90 s. Flatten backend shapes inside the `api.ts` fetcher (adapter layer).
- **A fetcher that does NOT return `Fetched<>` is outside `useFetch`'s guard — it must `throw`.** `synthesize()` / `getRcaPack()` return bare values. Never add a fixture fallback to one. `lib/rca.ts` `rcaFor` is **test-only** — importing it from `api.ts` reintroduces the bug.
- **Backend fixture fallbacks must be disclosed in the UI** (P&ID `topology_source: "demo_fixture"`). Never render one as extracted data.
- **Safety-critical = `RefusalCard` only.** Never a hedged answer.
- Every answer / brief / RCA hypothesis shows `sources[]` + `AuthorityBadge`. No claim without provenance.
- **Eyebrows are the area alone** (`Governance`, `Assure`) and UI copy carries **no `·` separators** — use a comma, or drop the separator for label+value (`L3 Standard`).
- **Filled and secondary actions use `Button` / `ButtonLink`** (`components/ui.tsx`) — they carry the shared `.fill-sweep` hover. Never hand-roll a `bg-accent` button.
- `PageHeader`'s `compact` is for per-record views (`/assets/[id]`) only; a top-level page keeps the full title size.
- **End a session only through `clearSession()` (explicit sign-out: wipes caches, offline queue, Copilot history) or `expireSession()` (forced 401: keeps the queue).** Never remove the tokens by hand. `supersedeDocument` can answer `pending_moc_approval` (HTTP 202): branch on `status`, never treat a 2xx as done.
- `next.config.ts` sets the CSP and security headers; `script-src` keeps `'unsafe-inline'` on purpose (Next 16 inline scripts), so do not add inline event handlers or `dangerouslySetInnerHTML`.
- No `console.log` in committed code.

### Backend
- **Neo4j edges — all 6 on every write:** `valid_from · valid_to · authority_level · document_id · confidence · verification_status`. `valid_to` uses sentinel `9999-12-31`, never NULL.
- Vault: permanent. Never delete. Supersede by closing `valid_to`. Supabase Storage: immutable.
  **This is the narrow case — the broad rule is 🛑 NEVER WRITE TO A CLOUD STORE at the top of this file.**
- **Event ingest: `mark_seen` runs last** (a failed ingest must stay retryable), and `operational_events` rows go in through `_store_event` (insert, 409 on a conflicting `event_id`), never an upsert. The pending-brief slot is per work order. Document authority 1 to 3 may be asserted only by `reliability` or `admin` (others are capped to 4), and superseding a 1 to 3 document needs an approved MoC.
- Quarantine: one-way gate. `confidence < 0.7` → quarantine. Human-only promotion. No auto-promote.
- Assets: `MERGE (a:Asset {asset_id: $id}) SET a += $props` — never CREATE.
- Phase 2 synthesis **only** in `POST /search/synthesize`, never auto-triggered. The server retrieves its own evidence and always derives `query_category`; a client `context` or `query_category` is accepted and ignored, so the safety gate cannot be fed fake metadata. The gate clears on confidence ≥ 0.7 **or** authority ≤ 3, and runs **twice** — on the evidence, then on the result.
- **Only *relevant, same-asset* evidence may clear the safety gate** (`_authority_candidates`, `services/llm.py`). Rank by `relevance_score`, **never by position** — `SearchService` sorts by `(authority_level, -rrf)`, so a top-K-by-position filter is a no-op.
- **A conflict needs two *claims*.** `GraphService.NON_ASSERTING_RELATIONSHIPS` (`DOCUMENTED_BY`, `MENTIONS_PERSON`, `MENTIONS_ORGANISATION`, `CONTAINS_TOPOLOGY_ELEMENT`) records provenance/structure, so two of them never contradict. `detect_conflict` returns `None` for them **before** the Cypher, and `/governance/conflicts` filters the same set **in the query** (filtering in Python breaks `count`/`range`). Edges carry no value, so value-comparison would be a schema change — do not attempt it.
- **Test artifacts are filtered on read, never deleted.** `services/corpus.py` is the one predicate (shared with `run_kg_completeness.py`); they were 87 of 108 active vault documents. An id with no `documents` row (`PROMOTED-<uuid>`) is **kept** — unclassifiable is not disposable — and every caller reports its excluded count. Test **assets** use the same module: `TEST_ASSET_PREFIXES` (`QA-TEST-` plus the integration suite's `ASSET-*` ids), applied **inside the Cypher** via `REAL_ASSET_CYPHER` (asset list, compliance, coverage) so `total` stays correct, and each of those responses reports `excluded_test_assets` (`excluded_test_asset_count`). Never import the purge script's prefix list: it deletes, this only hides.
- **Compliance findings are clause-scoped** — a gap means no document of that clause's `requires_document_type` is linked to the asset.
- **PII redaction runs at export, never at ingestion** — redacting on ingest breaks retrieval.
- **Outbound model calls use `shared_client()`** (`services/http.py`) — pooled **per event loop**, never per-call and never global (Celery runs a fresh loop per task). Always pass an explicit `timeout=`.
- **PTW briefs need two distinct signatures.** `POST /briefs/{id}/countersign` (reliability/admin). **Never scope the countersign read by recipient** — the countersigner is by definition not the recipient.
- **P&ID topology is candidate, not canonical, until element-by-element engineer verification.**
- **Instrumentation coverage counts only *verified* topology.** `coverage_type: "none"` ≠ "no sensors". Never fabricate a sensor tag.
- **Report-only flags ship OFF:** `TIMESTAMP_DRIFT_ENFORCE=False`, `MODEL_GATE_ENFORCE=False`, `KAIROS_PHASE=3`.
- **Timestamp drift = same event, different source systems.** Never `occurred_at` vs `ingested_at`.
- EEMUA governor: `check_governor(user_id)` before every brief. ≤6/operator/hour. PTW always exempt.
- Celery: lazy imports inside task body. 6 queues: `ingestion,extraction,attribution,transcription,elicitation,validation`.
- Secrets: never hardcode. Seeded user passwords live only in `.env` as `KAIROS_SEED_PASSWORD_*` (gitignored); the Go connector needs `CONNECTOR_SHARED_SECRET` and refuses to start without it. All via `api/config.py` Settings → env vars. **`.env` and `.env.example` stay in sync** — same variable names, same order and section headings. Adding a setting means adding it to both: `.env.example` carries the safe default, `.env` the real value. Drifted twice before (19 variables missing locally on 2026-09-23) and it hides nothing until something silently falls back to a code default.
- **Authz fails closed.** `_ask_opa` returns `self.debug` when OPA is unreachable — never bare `True`. Any `read_*` action added to `kairos.rego` must also go in `_sensitive_actions`, or the catch-all grants it to every role. The event ingest routes need the `ingest_event` action (engineer, reliability, admin, and the internal key, which resolves to admin). The `demo` role (public one-click demo) reads everything an admin reads plus `synthesize`, `rca_pack` and `answer_feedback`, and is deny-by-default for every other write (never `write_api`, never in the catch-all). Never gate `OPTIONS` (CORS preflight carries no token, and this middleware is outermost). Read grants mirror `frontend/src/components/use-role.ts` — a role that can open a page but not call its API is a broken page, not a closed boundary.
- **One token verifier: `dependencies.resolve_token`.** Role and `site_id` are read from `app_metadata` only (users can edit `user_metadata`; `scripts/migrate_roles_to_app_metadata.py` must run before a deploy of that change). Never decode a Supabase JWT by hand — this project issues **ES256**, so an HS256 decode silently rejects every token and degrades authz to the dev bypass. Verify by probing the live API with a restricted persona and confirming a **403**; policy tests alone cannot tell you the layer is reached.
- **Site scope comes from the token, never the query string** — `dependencies.site_scope`. A blank `site_id` means *no* rows, not *all* rows.

### Both
- **NEVER modify or delete data in a cloud store.** Supabase (`ernffgrvdcikwwhkhiix`), Neo4j Aura and
  Qdrant Cloud hold the demo/golden data and have **no local equivalent** — `docker-compose.yml` has
  no local Supabase (its one postgres is Temporal's), so a bad delete is unrecoverable. Reads are
  fine. Standing user instruction, 2026-08-23. Two traps: (1) `backend/scripts/purge_test_data.py`
  runs as an **autouse session fixture** (`tests/conftest.py`), so merely adding a table to
  `SUPABASE_TARGETS` arms an irreversible cloud delete on the next suite run — no one has to invoke
  it; (2) the **full test suite writes heavily to cloud Supabase**. Only the service-free tier is
  safe to run. Propose cleanup as a dry run and stop — the deletion is the user's call.
- Root-cause errors — one fix in the shared function beats guards at every caller.
- `structlog` only. Never `print()`, never stdlib `logging`.
- Routers thin: handler → service → result. No business logic in routers.
- Stay in scope. Note unrelated breakage — don't fix it mid-task.

---

## Where Things Live

| Concern | Path |
|---|---|
| FastAPI entrypoint / config / DI | `backend/api/main.py` · `config.py` · `dependencies.py` |
| Routers / Services / Models | `backend/api/routers\|services\|models/*.py` |
| Temporal workflow · Celery/Temporal workers | `backend/workflows/document_pipeline.py` · `backend/workers/` |
| Go OT connectors | `backend/connectors/` |
| Neo4j · Supabase schema (source of truth) · unapplied SQL · seed scripts | `db/neo4j/init_schema.cypher` · `db/schema.sql` · `db/migrations/` · `backend/scripts/` |
| Golden dataset (mounted `/app/dataset`) | `dataset/` · canon: `dataset/00_Reference/00_KAIROS_CANON.md` |
| Frontend API client · types · primitives · shell | `frontend/src/lib/api.ts` · `types.ts` · `components/ui.tsx` · `app-shell.tsx` |
| Frontend design tokens · icon set | `frontend/src/app/globals.css` · `components/icon.tsx` (Phosphor; never hand-draw an `<svg>` icon) |

**Supabase** project `ernffgrvdcikwwhkhiix` · bucket `kairos-vault` (private, immutable, 500 MB) · **tooling** `gh` for PRs/CI, Supabase MCP for SQL (prefer over `docker exec`) · **release** `git tag v{version} && git push origin v{version}`
