# Kairos — Backend Implementation Plan

## Current State

**Implemented and verified.** Every router, worker, service, and Go handler below is fully wired end-to-end against the five datastores — this document is now the *reference* for how each piece was built, not a to-do list. The API serves live data across all domains (assets, briefs, copilot, RCA, governance, compliance, events), the Temporal document pipeline runs, and the golden dataset loads through the real ingestion path (10 assets, 20 documents, 4 events, 1 voice note). DB schemas are applied and consolidated into `db/schema.sql`. Integration suite: 150 passing, self-cleaning on teardown.

The task breakdown that follows records the objective, endpoints, and verification step for each backend capability, in the order it was built.

---

## Task 1: Apply DB Schemas and Verify Connectivity

**Objective:** Apply Neo4j constraints/indices and Qdrant collections. Confirm all backends reachable from the API container. Add a detailed health endpoint as the canonical service check throughout development.

- Run `make init-all` to apply `db/neo4j/init_schema.cypher` and create Qdrant collections
- Wire the `lifespan` function in `api/main.py` to call `VectorStoreService.ensure_collections()` and `SearchEngineService.ensure_indices()` on startup
- Add `GET /health/detailed` that pings all five backends (Neo4j, Qdrant, ES, Redis, Temporal) and returns individual status per service

**Test:** `GET /health/detailed` returns green for all services.

---

## Task 2: Asset MDM Backbone — `/assets` Router

**Objective:** Fully wire all 6 asset endpoints so canonical asset nodes can be created, queried, and alias-mapped in Neo4j and Supabase.

- `POST /assets` — call `GraphService.create_asset_node()` using `MERGE`, write row to Supabase `assets` table; hard-require `confirmed_by_user_id` to be a non-empty user ID (no AI-inferred identities, ever)
- `GET /assets` — Cypher: `MATCH (a:Asset) WHERE a.site_id = $site_id RETURN a SKIP $offset LIMIT $limit`; also index into ES `kairos_assets`
- `GET /assets/{asset_id}` — `GraphService.get_asset()`
- `GET /assets/{asset_id}/aliases` — query `asset_alias_map` Supabase table
- `GET /assets/{asset_id}/hierarchy` — Neo4j traversal: `MATCH path = (a:Asset {asset_id: $id})<-[:PARENT_OF*0..5]-(root) RETURN nodes(path)`
- `GET /assets/{asset_id}/knowledge` — `GraphService.get_asset_knowledge_at()`, pass `as_of` as parsed datetime

**Test:** Create asset "P-101", retrieve it, retrieve its empty knowledge, confirm MERGE-safe on duplicate creation call.

---

## Task 3: Immutable Vault — `POST /documents/ingest`

**Objective:** Store uploaded files in Supabase Storage with SHA-256 hash, write to `documents` table, queue the Temporal ingestion workflow.

- Compute `hashlib.sha256(bytes).hexdigest()` before anything else
- Check `documents` table for duplicate SHA-256 (idempotent — same file ingested twice returns existing `document_id`)
- Upload raw bytes to Supabase Storage bucket `kairos-vault` at path `{document_type}/{document_id}/{filename}` — file stored unchanged, no preprocessing
- Insert row into `documents` (status=`active`) and `extraction_jobs` (stage=`queued`)
- Link to asset in `document_asset_links` if `asset_id` provided
- Trigger `DocumentIngestionWorkflow` via Temporal client
- Implement `GET /documents/{document_id}`, `GET /documents/{document_id}/status`, `GET /documents/` list with filtering

**Test:** Upload PDF, verify SHA-256 in DB, verify blob in Supabase Storage, verify Temporal workflow started in UI at `localhost:8088`.

---

## Task 4: OCR — `run_ocr` Temporal Activity

**Objective:** Wire the `store_in_vault` and `run_ocr` Temporal activities to execute OCR via NVIDIA NIM and update job status.

- `store_in_vault` activity: download file bytes from Supabase Storage, verify SHA-256 matches, update `extraction_jobs` stage to `ocr_running`
- `run_ocr` activity: call `OCRService.extract_text(file_bytes, mime_type)`, update `extraction_jobs` with `ocr_confidence` and advance stage to `ner_running`; if `overall_confidence < 0.5`, set stage to `review_required`, stop pipeline, push to a Redis Stream `kairos:events:review_required`. Fast path: PyMuPDF extracts native text from digital PDFs (no API call); images and scanned PDFs go to NVIDIA NIM Nemotron-OCR-v2.

**Test:** Ingest a real PDF, poll `/documents/{id}/status`, confirm `ocr_confidence > 0` and stage advances correctly.

---

## Task 5: NER + Entity-to-Asset Linking — `run_ner` and `link_to_graph` Activities

**Objective:** Extract industrial entities and link them to canonical asset nodes. Low-confidence and unresolved entities go to quarantine, never to the canonical graph.

- `run_ner` activity: call `NERService.extract_entities(text)`, update `extraction_jobs.entity_count`, advance stage to `graph_linking`
- `link_to_graph` activity:
  - For `ASSET_TAG` entities: call `NERService.resolve_asset_tag(raw_tag, alias_map)` where `alias_map` is fetched from `asset_alias_map`; if resolved → create graph edge; if unresolved → insert into `asset_alias_map` with `confirmed=False` and route entity to `quarantine_items` (never auto-link)
  - For resolved entities: call `GraphService.create_knowledge_edge()` with all five mandatory properties: `valid_from=now`, `authority_level=document.authority_level`, `document_id`, `confidence`, `verification_status='unverified'`
  - Entities with `confidence < 0.7` go to `quarantine_items` table, never to the canonical graph

**Test:** Ingest a document mentioning "P-101", verify a Neo4j edge created with all 5 properties; verify low-confidence entities appear in `quarantine_items`, not as graph edges.

---

## Task 6: Vector and Text Indexing — `index_vectors` and `index_text` Activities

**Objective:** Make ingested documents searchable via Qdrant (semantic) and Elasticsearch (exact).

- `index_vectors` activity: chunk text into 512-token segments with 50-token overlap; embed each chunk via `LLMService.embed(chunk)` (Jina AI `jina-embeddings-v3` primary, Ollama `nomic-embed-text` fallback); call `VectorStoreService.upsert()` to `kairos_documents` collection with payload `{document_id, asset_id, chunk_index, authority_level, is_quarantine: False, text}`
- `index_text` activity: `es_client.index(index=ELASTICSEARCH_INDEX_DOCUMENTS, id=document_id, document={document_id, asset_id, title, content, document_type, authority_level, status, ingested_at})`
- Steps 5 and 6 run in parallel inside the Temporal workflow (already wired with `workflow.wait([...])`)

**Test:** Complete a full ingestion, verify points in Qdrant dashboard, verify document in ES index.

---

## Task 7: Hybrid Search — `/search` Router

**Objective:** Implement the full hybrid retrieval pipeline with authority-ranked re-ranking. Phase 1: retrieval only, no synthesis.

- `GET /search`: run three retrievals in parallel via `asyncio.gather()`:
  1. `SearchEngineService.search(query, asset_id)` — ES exact match (tag numbers, clause refs, doc IDs)
  2. `VectorStoreService.search(collection, embed(q), asset_id, authority_min)` — semantic
  3. `GraphService.get_asset_knowledge_at(asset_id, as_of)` if `asset_id` provided — graph facts
- Merge results, deduplicate by `document_id`, re-rank: sort by `authority_level ASC` then `relevance_score DESC`
- Apply `as_of` time-travel: validity window filtering already handled in `GraphService.get_asset_knowledge_at()`
- If `include_quarantine=True`, add a Qdrant search filtered to `is_quarantine=True` with explicit labeling
- `synthesis=None` in Phase 1 response

**Test:** Index a document, search for a tag number (expect ES hit), search for a concept (expect Qdrant hit), search with `as_of` before ingestion (expect no results).

---

## Task 8: LLM Synthesis — `POST /search/synthesize`

**Objective:** Implement synthesis with mandatory source citation and explicit safety-critical refusal. Phase 2 gate — no-ops cleanly if no LLM configured.

- Return `{"message": "No LLM configured"}` if neither NIM nor Ollama available (clean Phase 1 fallback)
- Call `LLMService.synthesize(query, retrieved_context, query_category)` — NIM and Ollama paths are already implemented
- Parse LLM response to extract `ANSWER:`, `CONFIDENCE:`, `SOURCES_USED:` from the structured prompt output
- For `query_category` in `SAFETY_CRITICAL_CATEGORIES`: refusal logic already in `LLMService.synthesize()` — wire `query_category` from the request body
- Log every synthesis call to `audit_log`: `{action: 'synthesis', entity_type: 'query', details: {query, sources_used, confidence, refused}}`

**Test:** Synthesize with NIM/Ollama, verify source citations in response; test a safety-critical category with low-confidence context, verify refusal with source documents returned directly.

---

## Task 9: Dual-Track Conflict Detection + Blast-Radius

**Objective:** Detect conflicts when edges are written, classify track, trigger MoC for engineering conflicts, and implement all governance endpoints.

- Add `detect_conflict()` to `GraphService`: before committing a new edge, query for existing active edges on the same parameter with a different value; if found, insert into `knowledge_conflicts` table
- Track classification: `authority_level <= 3` AND parameter in `{pressure, temperature, inspection_interval, isolation_procedure, material_spec}` → `track='engineering'`, SLA = 24h for safety_critical, 5 days otherwise; else → `track='administrative'`, SLA = 5 days
- `GET /governance/conflicts` — query `knowledge_conflicts` with filters
- `GET /governance/blast-radius/{document_id}` — call `GraphService.get_blast_radius()` (already implemented)
- `GET /governance/quarantine` — query `quarantine_items`
- `POST /governance/quarantine/{id}/promote` — call `GraphService.create_knowledge_edge()` with `verification_status='verified'`, close superseded edge, write audit log; requires `reliability` or `admin` role
- `POST /governance/quarantine/{id}/dispute` — update `review_status='disputed'`
- `POST /documents/{id}/supersede` — update old document `status='superseded'`, call `GraphService.close_validity_window()` on all edges with that `document_id`, trigger blast-radius analysis, create `moc_items` row if any affected edge had `authority_level <= 3`
- `POST /governance/moc/webhook` — verify webhook signature, call `GraphService.close_validity_window()` on old edge, promote new edge to `verification_status='verified'`, clear pending conflict, write audit log

**Test:** Ingest two documents with conflicting pressure values for the same asset, verify conflict row with `track='engineering'`; supersede the old document, verify its edges have `verification_status='superseded'` and blast-radius report is populated.

---

## Task 10: Compliance Gap Detection — `/compliance` Router

**Objective:** Seed a minimal regulatory framework and implement gap detection against current documented procedures.

- Seed 10-15 regulatory clauses as `Concept` nodes in Neo4j (OISD-117 or ISO 45001 sample) via `scripts/seed_regulations.py`; each node: `{concept_id, type:'Regulation', framework, clause_id, requirement_text, applies_to_equipment_class}`
- `GET /compliance/gaps`: Cypher — for each applicable `Regulation` node, check if a verified `KNOWLEDGE_EDGE` exists from an `Asset` of that class to a `Document` of type `procedure` with `valid_to IS NULL`; missing edge = gap; gap severity: `critical` if `authority_level=1`, `major` if 2, `minor` otherwise
- `GET /compliance/dashboard`: aggregate gaps by severity/framework/asset_class
- `GET /compliance/audit-pack`: gather `Document` nodes linked to requested `framework` clauses, organized by `clause_id`; flag clauses with `confidence < 0.7` as requiring human review; block clearances below threshold

**Test:** Seed regulations, create assets without linked procedures, verify gaps detected; link a verified procedure edge, verify gap clears.

---

## Task 11: Event Ingestion and Normalization — `/events` Router

**Objective:** Wire all event ingestion endpoints with canonical normalization (dedup, correlation) and publication to Redis Streams.

- `POST /events/work-order`: call `EventBusService.is_duplicate(asset_id, 'work_order_created')`; if duplicate return `{status: 'deduplicated'}`; else publish via `EventBusService.publish_work_order()`, insert into `operational_events`, trigger brief assembly (Task 12)
- `POST /events/ptw`: always `priority='critical'`; publish to `REDIS_STREAM_PTW`; immediately publish to `REDIS_STREAM_BRIEFS` with `priority='critical'` to bypass governor
- `POST /events/shift-handover`: publish to `REDIS_STREAM_SHIFT_HANDOVER`
- `POST /events/alarm`: publish to `REDIS_STREAM_ALARMS`
- `POST /events/{event_id}/ack`: write to `audit_log`: `{action: 'brief_acknowledged', performed_by, details: {event_id, timestamp, signature}}`

**Test:** POST a work order event, verify Redis Stream entry via `redis-cli XRANGE kairos:events:work_orders - +`; POST the same event again within 10 minutes, verify dedup response.

---

## Task 12: Brief Assembly Engine

**Objective:** Implement `api/services/brief_engine.py` — the core that queries the graph and assembles contextual briefs for each event type.

- `BriefEngine.assemble_work_order_brief(event)`: run in parallel via `asyncio.gather()`:
  1. `GraphService.get_asset_knowledge_at(asset_id)` — failure history
  2. `VectorStoreService.search(kairos_knowledge, embed("failure " + failure_code), asset_id)` — similar failures
  3. Supabase: `SELECT * FROM quarantine_items WHERE asset_id = $1 AND review_status = 'pending'`
  4. Supabase: `SELECT * FROM knowledge_conflicts WHERE asset_id = $1 AND status = 'open'`
  5. ES search for `asset_id` filtered to `document_type='procedure'`
  - Assemble `Brief`: headline = top finding from history, body = raw retrieved facts (Phase 1) or LLM synthesis (Phase 2), warnings = open conflicts, quarantine_flags = unverified items
- `BriefEngine.assemble_ptw_brief(event)`: Neo4j query for isolation topology of all `asset_ids` in boundary, maintenance history of each isolation device, PTW-type regulatory requirements, quarantine deviation flags
- `BriefEngine.assemble_shift_handover_brief(event)`: open work orders, active alarms, pending conflicts
- Delivery: save `Brief` to Supabase `briefs` table, publish to `REDIS_STREAM_BRIEFS` with `recipient_user_id` as field, update `briefs.delivered_at`

**Test:** Seed P-101 with failure history, POST a work order event for P-101, call `GET /briefs` as the assigned technician, verify brief contains source-cited failure history.

---

## Task 13: EEMUA 191 Governor — `/briefs` Router

**Objective:** Implement the push governor, brief retrieval, acknowledgment, and feedback. Hard ceiling: ≤6 push events per operator per hour; PTW briefs are never suppressed.

- `GET /briefs`: query Supabase `briefs WHERE recipient_user_id = $1 AND acknowledged_at IS NULL`; check `EventBusService.get_governor_state(user_id)`; always return `priority='critical'` briefs; suppress `normal` priority if `push_count_last_hour >= ceiling`; call `EventBusService.record_push(user_id)` for each brief returned
- `GET /briefs/{brief_id}`: Supabase query with authorization check (`recipient_user_id == current_user.user_id`)
- `POST /briefs/{brief_id}/ack`: update `briefs` with `acknowledged_at`, `acknowledged_by`; for `requires_countersignature=True` (PTW briefs), do NOT set `acknowledged_at` until countersignature received; write `audit_log` entry
- `POST /briefs/{brief_id}/feedback`: insert into `brief_feedback`; if `rating='incorrect'` trigger background task to re-evaluate source document confidence
- `GET /briefs/governor/status`: return `EventBusService.get_governor_state(user_id)`
- Cool-down: in brief delivery, also check `SELECT COUNT(*) FROM briefs WHERE recipient_user_id=$1 AND asset_id=$2 AND created_at > NOW() - INTERVAL '4 hours'` before generating a new brief for the same asset

**Test:** Deliver 6 normal briefs to a user, verify 7th is suppressed; deliver a PTW brief, verify it appears regardless of count.

---

## Task 14: Auth + OPA Policy Enforcement

**Objective:** Wire Supabase Auth JWT verification and OPA policy enforcement into all protected routes.

- `POST /auth/login`: call `supabase.auth.sign_in_with_password({"email", "password"})`, return JWT
- `POST /auth/refresh`: call `supabase.auth.refresh_session(refresh_token)`
- Verify `APP_DEBUG=False` path in `get_current_user()` actually rejects invalid tokens
- Add `OPAMiddleware`: for `POST/PUT/DELETE` routes, construct OPA input `{user: {user_id, role, site_id}, action, resource}` and call `POST http://kairos-opa:8181/v1/data/kairos/authz/allow`; deny with 403 if result is not `true`
- Apply `require_role("admin", "engineer")` to governance promotion/resolution; `require_role("admin")` to MDM bootstrap; field_worker locked to read-only
- Configure Supabase RLS on `briefs` and `quarantine_items` to enforce `recipient_user_id = auth.uid()` and `site_id` isolation

**Test:** Authenticate as `field_worker`, attempt `POST /governance/quarantine/{id}/promote`, verify 403; same with `admin` token, verify 200.

---

## Task 15: Elicitation Engine

**Objective:** Implement graph-derived micro-interview questions at work order closeout and store responses in quarantine.

- `POST /elicitation/trigger`: check trigger conditions — (a) failure code occurrence count for this equipment class in `operational_events` < 3, (b) `resolution_time_hours > 90th percentile` for this failure type, (c) `novel_troubleshooting=True`; if any met, start `MicroInterviewWorkflow` via Temporal
- `generate_interview_questions` activity: query Neo4j for known vs unknown failure modes on this asset; pass gap list to `LLMService.synthesize()` with prompt: "Generate 3-5 targeted diagnostic questions. Known: {known}. Unknown: {unknown}. Be specific, not generic." Max 5 questions.
- `GET /elicitation/{work_order_id}/questions`: return generated questions for mobile delivery
- `POST /elicitation/{work_order_id}/responses`: accept question-answer pairs, call `store_elicitation_response` activity — insert into `quarantine_items` with `input_type='elicitation_response'` and `session_context={questions, work_order_id}`

**Test:** Trigger elicitation for a rare failure code, verify questions are graph-derived (reference specific asset history), submit responses, verify quarantine item with session context.

---

## Task 16: Attribution Worker

**Objective:** Wire the three parallel attribution checks in `workers/attribution.py`. Confidence adjustments only happen when all three checks confirm a genuine recommendation failure.

- `_check_telemetry_baseline(asset_id, work_order_id)`: call `GET http://kairos-backend-go:8090/ot/coverage/{asset_id}`; if `coverage_percent == 0` return `{primary_check: False, reason: 'not_instrumented'}`; if instrumented, call `GET /ot/query?asset_id=...&tag=...&from=maintenance_date&to=maintenance_date+30days` and check if mean value returned to ±2σ of historical baseline
- `_check_failure_code_match(work_order_id)`: query `operational_events` for both work orders' `failure_code`; map codes to failure mode families via a static dict; `matched=True` only if same family
- `_check_execution_compliance(work_order_id)`: query `operational_events.payload->>'close_notes'`; keyword-match recommended action items against close notes; `compliant=True` if found
- Wire attribution trigger in `POST /events/work-order`: query `SELECT COUNT(*) FROM operational_events WHERE asset_id=$1 AND event_type='work_order_created' AND occurred_at > NOW() - INTERVAL '30 days'`; if count > 1, enqueue `attribution.evaluate_outcome.delay(work_order_id, asset_id)`

**Test:** Create two work orders for the same asset within 30 days, verify attribution task fires; simulate execution deviation, verify no confidence adjustment made.

---

## Task 17: Go Connector — Historian Federation + EAM Sync

**Objective:** Implement the OT historian query and EAM asset sync Go handlers. Use mock data for demo when external systems are not configured.

- `GET /ot/query`: implement `PIWebAPIClient.Query()` in `internal/ot/client.go` calling `{PI_WEBAPI_BASE_URL}/streams/{webid}/recorded?startTime={from}&endTime={to}` with Basic Auth; if `PI_WEBAPI_BASE_URL` is empty, return a configurable mock fixture (50 points with realistic vibration values) so the attribution worker can function for demo
- `GET /ot/coverage/{asset_id}`: call FastAPI `GET /assets/{asset_id}/knowledge` to retrieve instrumentation tags from graph; return coverage map
- `POST /eam/sync`: if `EAM_ODS_ENDPOINT` is empty, parse `fixtures/sample_assets.json`; for each record, POST to `http://kairos-backend-api:8000/assets`
- `POST /eam/work-order`: forward payload to `http://kairos-backend-api:8000/events/work-order`

**Test:** Call `GET /ot/query` with no PI config, verify mock time-series returned; call `POST /eam/sync` with fixture file, verify assets appear in FastAPI.

---

## Task 18: OpenTelemetry Instrumentation + Grafana Dashboards

**Objective:** Ensure all services emit traces and metrics to the OTEL collector, and provision Grafana dashboards for the demo.

- Confirm `setup_telemetry(app)` in `api/main.py` is wiring `FastAPIInstrumentor`, `RedisInstrumentor`, and `HTTPXClientInstrumentor` correctly; add `Neo4jInstrumentor` if available
- Add custom OTEL metrics: `kairos.briefs.delivered` counter, `kairos.governor.suppressed` counter, `kairos.ingestion.duration` histogram, `kairos.conflicts.open` gauge
- Update `backend/otel/otel-config.yaml` to route traces to Grafana Tempo and metrics to Prometheus (add receivers and exporters)
- Provision two Grafana dashboards in `backend/grafana/provisioning/`:
  1. **Ingestion Pipeline** — documents ingested/hour, OCR confidence distribution, NER entity count, pipeline stage breakdown
  2. **Operational Intelligence** — briefs delivered/hour, governor suppression rate, open conflicts by track, compliance gap count by severity

**Test:** Run `make dev`, ingest 3 documents, deliver 2 briefs, verify traces + metrics appear in Grafana Cloud.

---

## Task 19: Whisper Voice Transcription (Layer 3)

**Objective:** Accept voice notes from the elicitation engine, transcribe via Whisper, run through NER, and store in quarantine. Architecture requires this for tacit knowledge capture from field technicians.

- Create `api/services/whisper.py` with `WhisperService`: calls **Groq API** (`GROQ_API_KEY`, `GROQ_WHISPER_MODEL=whisper-large-v3`) via sync `httpx` — no local model, no heavy deps. `transcribe(audio_bytes, filename) -> {text, language, confidence, segments}`. confidence derived from `avg_logprob` across Groq verbose_json segments.
- Add `GROQ_API_KEY` and `GROQ_WHISPER_MODEL` to `api/config.py` Settings.
- `POST /elicitation/{work_order_id}/voice`: accept `UploadFile` + `submitted_by` form field; store raw bytes in Supabase Storage at `voice_notes/{work_order_id}/{sha256[:8]}_{filename}` (immutable, SHA-256 dedup); queue Celery task; return 202.
- `workers/voice_transcription.py`: Celery task on `transcription` queue — download from storage, verify SHA-256, call `WhisperService.transcribe()`, run `NERService.extract_entities()` in new asyncio loop, insert `quarantine_items` with `input_type='voice_note'` and full `session_context`.
- Add `workers.voice_transcription` to `celery_app.py` includes; add `transcription` queue to docker-compose Celery worker command.

**Test:** Upload `test.wav` to `POST /elicitation/WO-TEST-001/voice`, verify 202 + `task_id`; wait for Celery task; verify `quarantine_items` row with `input_type='voice_note'`, transcript text, and `work_order_id=WO-TEST-001`.

---

## Task 20: Engineering Drawing Topology — Vision Model (Layer 3, Path B)

**Objective:** Handle `document_type='pid_drawing'` without destroying spatial relationships via standard OCR. Extract topology with a cloud vision-language model (Path B), gate canonical promotion behind human verification. Path A (custom YOLOv9 + LayoutLMv3 on GPU) is the future upgrade — see ARCHITECTURE.md Layer 3.

- In `run_ocr` Temporal activity: detect `document_type == 'pid_drawing'`; skip standard OCR; call `PIDService.extract_topology(file_bytes, mime_type)` (`api/services/pid.py`) — sends the drawing image to NIM `meta/llama-3.2-11b-vision-instruct` and parses the topology JSON (equipment nodes, valves, instrumentation loops, isolation boundaries). Falls back to `backend/fixtures/pid_topology_mock.json` when the model is unreachable/unparseable; `topology_source` (`vision_model` | `demo_fixture`) is threaded through so a fixture never masquerades as real.
- Store topology as a `Document` node in Neo4j with `document_type='pid_topology'`, create graph edges for each extracted element with `verification_status='unverified'` — all routed to human verification queue via `quarantine_items` with `input_type='deviation_flag'`
- `GET /documents/{document_id}/topology` — return the topology JSON (+ `topology_source`) for the engineer verification UI
- `backend/fixtures/pid_topology_mock.json` is the demo/fallback sample: 5 equipment nodes, 3 isolation valves, 2 instrumentation loops, 1 isolation boundary

**Test:** Ingest a `pid_drawing` (e.g. `dataset/02_Document_Corpus/pid_line3_isolation_boundary.png`), verify OCR is skipped, verify topology items appear in `GET /governance/quarantine`, verify `GET /documents/{id}/topology` returns topology with `topology_source`. Parser unit tests: `tests/test_pid.py`.

---

## Task 21: Active Learning Annotation Interface (Layer 3)

**Objective:** Backend support for inline entity correction in search results — the mechanism that bootstraps Hinglish NER accuracy from normal search usage.

- Add migration `006_ner_annotations.sql`: `ner_annotations(id UUID PK, document_id TEXT, entity_text TEXT, entity_type TEXT, corrected_type TEXT, is_correct BOOL, span_start INT, span_end INT, annotated_by TEXT, created_at TIMESTAMPTZ)`
- `POST /annotations` — insert row into `ner_annotations`; if `is_correct=False`, find matching `quarantine_items` entry by `document_id` + entity span and update its `confidence` downward; write to `audit_log`
- `GET /annotations?document_id=X` — return all annotations for a document (frontend uses this to render highlighted entity spans with correction state)
- `GET /annotations/stats` — aggregate counts: `{total, corrections_this_week, top_corrected_entity_types}` — used by the compliance/model health dashboard

**Test:** Ingest a document, call `GET /search`, take a low-confidence entity, POST correction to `/annotations` with `is_correct=False`, verify row in `ner_annotations` and confidence updated on linked quarantine item.

---

## Task 22: SPC-Based Circuit Breaker (Layer 7)

**Objective:** Halt automated extraction per asset class when override rates drift outside control limits. Prevents model drift from silently corrupting the knowledge base.

- Add migration `007_circuit_breaker.sql`: `extraction_overrides(id UUID PK, asset_class TEXT, document_id TEXT, override_type TEXT CHECK IN ('manual_correction','quarantine_rejection','annotation_correction'), created_at TIMESTAMPTZ)`
- Create `api/services/circuit_breaker.py` with `CircuitBreakerService.check(asset_class) -> {halted: bool, z_score: float, reason: str}`: query `extraction_overrides` for 7-day rolling count; compute Z-score against 30-day historical mean using `(current - mean) / std`; if `z_score > 2.0` → `halted=True`, write to `audit_log`
- Wire into `link_to_graph` Temporal activity: call `circuit_breaker.check(asset_class)` before any graph writes; if `halted=True`, push document to `kairos:events:review_required` and return without writing graph edges
- `GET /governance/circuit-breaker` — return current state per asset class: `{asset_class, status, z_score, override_count_7d, halted_since}`
- Increment `extraction_overrides` when: quarantine item is rejected (`dispute` endpoint), annotation correction is submitted (`is_correct=False`), or manual review routes a document back

**Test:** Insert 15 `quarantine_rejection` overrides for `asset_class='pump'` within 7 days, call `GET /governance/circuit-breaker`, verify `status='halted'` for pumps; ingest a new pump document, verify graph edges are NOT created and document lands in review queue.

---

## Task 23: Physical Deviation Flag (Layer 6 / Layer 8)

**Objective:** Field technicians can flag physical deviations from engineering drawings. On flag, freeze all downstream automated brief delivery for affected asset topology paths until an engineer resolves it.

- `POST /events/deviation-flag` — accept `{asset_id, description, reported_by, affected_topology_path}`; insert into `quarantine_items` with `input_type='deviation_flag'`; set `delivery_frozen=True` on all unacknowledged `briefs` for this `asset_id`; publish to `REDIS_STREAM_ALARMS` with `severity='critical'`; write `audit_log`
- `POST /events/deviation-flag/{item_id}/resolve` — requires `engineer` or `admin` role; update `quarantine_items.review_status='promoted'` or `'disputed'`; set `delivery_frozen=False` on affected briefs; if MoC warranted (topology change confirmed), create `moc_items` row
- Add `delivery_frozen BOOLEAN NOT NULL DEFAULT FALSE` column to `briefs` table (migration `008_brief_freeze.sql`)
- Update `GET /briefs`: filter `delivery_frozen=False` for normal delivery; include frozen briefs in response with `{frozen: true, reason: 'Physical deviation flag pending resolution'}` so the frontend can display the freeze state

**Test:** POST a deviation flag for P-101; call `GET /briefs` for a user with P-101 briefs, verify frozen briefs show `frozen=true`; resolve the flag, verify briefs return to normal delivery.

---

## Task 24: Timestamp Normalization in Ingestion Pipeline (Layer 4)

**Objective:** Prevent incorrect temporal ordering in the graph from unsynchronized source system clocks. Architecture calls this a first-class ingestion requirement.

- Add `TIMESTAMP_DRIFT_TOLERANCE_MINUTES=60` to `api/config.py` Settings and `.env.example`
- In `link_to_graph` Temporal activity, before setting `valid_from` on any graph edge: compare `source_timestamp` (from document payload / event `occurred_at`) against `ingested_at` (Supabase Storage upload time); if `abs(source - ingested) > TIMESTAMP_DRIFT_TOLERANCE_MINUTES`, log to `audit_log` with `action='timestamp_drift_detected'` and `details={source_ts, ingested_ts, drift_minutes}`; use `ingested_at` as the canonical `valid_from` instead of the source timestamp
- Flag the document's `extraction_jobs` row with a `timestamp_drift_detected=True` column (add to migration `009_timestamp_drift.sql`) so reviewers can see which documents had clock drift

**Test:** Ingest a document with `occurred_at` set 5 hours in the future; verify the resulting Neo4j edge has `valid_from` equal to `ingested_at`, not the future timestamp; verify `audit_log` has a `timestamp_drift_detected` row.

---

## Task 25: Frontend Integration Contracts — API Response Completeness

**Objective:** Harden all API responses so the frontend can integrate without hitting missing fields or inconsistent envelope shapes.

- **Consistent list envelope**: all list endpoints must return `{items: [], total: int, limit: int, offset: int}` — fix `GET /assets`, `GET /governance/conflicts`, `GET /governance/quarantine`, `GET /compliance/gaps` which currently use inconsistent keys (`assets:`, `conflicts:`, `items:`, `gaps:`)
- **Asset detail**: `GET /assets/{asset_id}` must return a typed response including `open_work_orders_count` (query `operational_events`), `compliance_gap_count` (query `knowledge_conflicts`), `last_inspection_date` (query graph for most recent `Event` node of type `inspection`)
- **vault_url on search results**: `GET /search` results must include `vault_url` — the Supabase Storage public URL for the source document; required for "view source" links in the frontend; compute via `supabase.storage.from_(bucket).get_public_url(path)`
- **Governor state in briefs list**: `GET /briefs` response must include `{governor_state: {push_count_last_hour, ceiling, state}, suppressed_count: int, next_delivery_allowed_at: ISO8601}` at the top level so the frontend can render governor status without a separate request
- **Session context in quarantine**: `GET /governance/quarantine` items of `input_type='elicitation_response'` must include the full `session_context` (questions + answers) so the reviewer UI can show what was asked alongside the response
- **Audit trail endpoint**: `GET /audit-log?entity_type=X&entity_id=Y&limit=50` — frontend needs this to render the evidence lineage panel; currently the `audit_log` table exists but has no router endpoint

**Test:** Call each endpoint and verify the envelope shape; call `GET /assets/P-101` and verify `open_work_orders_count` is present; call `GET /search?q=seal+failure` and verify each result has a non-null `vault_url`; call `GET /audit-log?entity_type=document&entity_id=DOC-001` and verify chronological audit entries returned.

---

## Task 26: Delay Compensation for Event Normalization (Layer 8)

**Objective:** Implement the late-arrival buffer so brief assembly waits for correlated events from multiple source systems before triggering, preventing duplicate briefs from the same real-world action.

- In `POST /events/work-order` (and `/ptw`, `/shift-handover`): instead of triggering `BriefEngine.assemble_*` immediately, enqueue a Celery task with `apply_async(countdown=LATE_ARRIVAL_WINDOW_MINUTES * 60)` — default 5-minute delay
- Store the pending Celery task ID in Redis at key `kairos:brief_pending:{asset_id}:{event_type}` with TTL = late-arrival window; if a second event for the same asset arrives during the window, revoke the existing task (`celery_app.control.revoke(task_id)`) and re-enqueue with the merged compound payload
- After the countdown fires, brief assembly proceeds with all accumulated event data for that asset in the window
- `LATE_ARRIVAL_WINDOW_MINUTES` already exists in `config.py` — wire it into the Celery countdown value

**Test:** POST a work order for P-101; within 30 seconds POST a PTW for the same asset; wait 5 minutes; verify only ONE brief generated (not two), and the brief includes context from both events.

---

## Task 27: Event Correlation — Compound Events (Layer 8)

**Objective:** Link events from different source systems referring to the same physical action into a single compound event, enriching the brief without generating separate deliveries.

- Add `correlate_events(primary_event, candidate_events) -> CompoundEvent` to `EventBusService`: groups events with same `asset_id` where `abs(occurred_at_a - occurred_at_b) < DEDUP_WINDOW_MINUTES`; merges into `CompoundEvent(primary_event, correlated_events: [], source_systems: [])`
- Pass `CompoundEvent` to `BriefEngine` — reads `correlated_events` to enrich content (PTW correlated → add isolation topology; alarm correlated → add DCS context)
- Add migration `010_compound_events.sql`: add `compound_event_id UUID` column to `operational_events` so correlated events reference each other
- `GET /events/{event_id}` — return event with `correlated_event_ids: []` list for the frontend audit trail

**Test:** POST a work order and alarm for P-101 within 2 minutes; call `GET /events/{work_order_event_id}`, verify `correlated_event_ids` contains the alarm event ID; verify the generated brief references both event contexts.

---

## Task 28: State-Based Push Suppression (Layer 8 Governor)

**Objective:** During turnarounds, planned shutdowns, or declared emergencies, the governor delivers only critical briefs. Architecture names this as a required governor component.

- Add migration `011_plant_state.sql`: `plant_operating_states(id UUID PK, site_id TEXT, state TEXT CHECK IN ('normal','turnaround','shutdown','emergency'), set_by TEXT, set_at TIMESTAMPTZ, expires_at TIMESTAMPTZ)`
- `POST /events/plant-state` — `engineer` or `admin` only; upsert current state for a site; write `audit_log`
- `GET /events/plant-state/{site_id}` — return current state (frontend needs this for the operator dashboard banner)
- Update `EventBusService.check_governor(user_id, priority, site_id)`: query `plant_operating_states`; if state is `turnaround`, `shutdown`, or `emergency` → suppress all briefs except `priority='critical'`; log suppression with `reason='plant_state_suppression'`
- Update `GET /briefs` to pass `site_id` from `current_user` into `check_governor()`
- Add `PLANT_STATE_DEFAULT=normal` to `config.py` and `.env.example`

**Test:** Set state to `turnaround` for SITE_001; trigger 3 normal work order events; verify no normal briefs delivered; trigger a PTW (`critical`); verify PTW brief delivered; reset to `normal`; verify normal briefs resume.

---

## Task 29: RCA Pack Generation (Layer 11)

**Objective:** Layer 11 explicitly lists "RCA packs" as a distinct synthesis output type — timeline of events, failure mode hypotheses ranked by evidence weight, supporting documents. Not covered by the generic synthesis endpoint.

- `POST /search/rca-pack` — accepts `{asset_id, incident_date: ISO8601, failure_code: str, include_quarantine: bool}`:
  1. Neo4j: all `Event` nodes linked to `asset_id` with `occurred_at >= incident_date - 90 days`, ordered chronologically — the failure timeline
  2. Qdrant semantic search: `embed(failure_code + " " + asset_class)` against `kairos_knowledge` — failure mode evidence
  3. Supabase: work orders, alarms, PTWs in the same 90-day window from `operational_events`
  4. Pass to `LLMService.synthesize()` with structured prompt: "Generate an RCA pack. Timeline: {events}. Evidence: {docs}. Rank failure mode hypotheses by evidence weight. Cite each to its source document."
  5. Return `{timeline: [{event_type, occurred_at, description, source}], hypotheses: [{hypothesis, evidence_weight, sources: [document_id]}], supporting_documents: [], confidence, refused: bool}`
- If LLM unavailable: return raw timeline + documents without synthesis (same fallback pattern as `/synthesize`)
- Log every call to `audit_log` with `action='rca_pack_generated'`, `entity_id=asset_id`
- Apply safety-critical refusal per hypothesis: if hypothesis involves a safety-critical parameter and `confidence < 0.7`, mark `refused=True` and return sources directly

**Test:** Seed P-101 with 3 Event nodes and 2 documents in Neo4j; POST to `/search/rca-pack`; verify `timeline` has >=3 events in chronological order, `hypotheses` has >=1 entry with `evidence_weight > 0`, all `sources` reference valid `document_id`s.

---

## Task 30: Recurring Failure Detection — Distinct Event Source (Layer 8)

**Objective:** When a work order is created for equipment that has failed with a similar failure code within the last 90 days, automatically publish a `recurring_failure_detected` event and assemble a pattern-focused brief. Architecture lists this as one of 8 canonical event sources but the attribution worker (Task 16) only handles confidence adjustment — it does not proactively push a brief.

- In `POST /events/work-order` handler, after dedup check, query `operational_events` for same `asset_id` + same failure family within 90 days: `SELECT COUNT(*) FROM operational_events WHERE asset_id=$1 AND event_type='work_order_created' AND occurred_at > NOW() - INTERVAL '90 days'`; map `failure_code` to failure family using `_FAILURE_FAMILIES` from `workers/attribution.py` — do NOT duplicate this dict; move it to `api/utils/failure_families.py` and import from there in both `attribution.py` and the events router
- If count ≥ 1 and same family: publish a `recurring_failure_detected` event to `REDIS_STREAM_WORK_ORDERS` with `event_subtype='recurring'` and `recurrence_count` field; set `brief_priority='high'` (below PTW critical, above normal)
- Add `BriefEngine.assemble_recurring_failure_brief(event)`: distinct from the standard WO brief — headline is pattern-focused: "EQ-101 has failed with [failure_code] [N] times in 90 days"; body pulls full failure timeline from Neo4j + Qdrant semantic search for that failure mode family across the equipment class; includes failure interval trend (is it accelerating?); includes attribution notes if available from `operational_events.payload`
- Add `event_subtype TEXT` column to `operational_events` via migration `012_event_subtype.sql`; populate `'recurring'` for recurring detections, `NULL` for standard

**Test:** Create two work orders for P-101 with failure_code `SEAL-FAIL` within 90 days; verify the second POST returns `recurring_detected: true` + `brief_id` for a recurring brief; verify brief headline references recurrence count; verify `event_subtype='recurring'` in `operational_events`.

---

## Task 31: Off-Boarding Interview Series — Retiring Expert Knowledge Transfer (Layer 9 / Flow D)

**Objective:** Implement the structured off-boarding interview series for retiring personnel. Architecture Flow D describes this in detail: identify high-knowledge-density individuals, schedule 6 sessions over 10 weeks, each session focused on a specific equipment family with graph-derived questions. The micro-interview (Task 15) is the mechanism; this is that mechanism applied on a scheduled multi-session arc.

- Add migration `013_offboarding_sessions.sql`: `offboarding_sessions(id UUID PK, personnel_id TEXT, personnel_email TEXT, retirement_date DATE, total_sessions INT DEFAULT 6, session_interval_days INT DEFAULT 12, status TEXT CHECK IN ('scheduled','in_progress','completed','cancelled'), created_by TEXT, created_at TIMESTAMPTZ)` and `offboarding_session_items(id UUID PK, session_id UUID FK, session_number INT, equipment_family TEXT, focus_failure_modes TEXT[], status TEXT CHECK IN ('pending','questions_ready','completed'), questions JSONB, scheduled_for TIMESTAMPTZ, completed_at TIMESTAMPTZ)`
- `POST /elicitation/offboarding` — `engineer` or `admin` only; accepts `{personnel_id, personnel_email, retirement_date}`; identifies high-knowledge-density by querying `operational_events WHERE performed_by=$personnel_id` grouped by equipment class (top 6 classes by work order count + novel troubleshooting flags); creates `offboarding_sessions` row + 6 `offboarding_session_items` spaced `session_interval_days` apart; for each session, dispatch `generate_offboarding_questions` via `apply_async(eta=scheduled_for)` on the `elicitation` queue (this is a delayed task, NOT Celery Beat — no beat process or beat_schedule involved); write `audit_log`. **Durability note:** `eta`-scheduled tasks spanning days/weeks are lost on worker restart. For production, replace `apply_async(eta=...)` with a Temporal `OffboardingWorkflow` using `workflow.sleep()` between sessions — consistent with how Tasks 3-6 and 15 already use Temporal for crash-survivable pipelines. For demo, `apply_async(eta=...)` on the existing worker is acceptable.
- Register `generate_offboarding_questions` task in `celery_app.py` includes and add `elicitation` to the `--queues` flag in the Celery worker command in `docker-compose.yml` (same pattern as Task 19 added `transcription`)
- `generate_offboarding_questions` Celery task (on `elicitation` queue): lazy-import `api.services.*` inside task body (see MEMORY.md Celery pitfall); for the session's `equipment_family`, query Neo4j for known vs unknown failure modes (same pattern as Task 15 `generate_interview_questions`); pass gaps to `LLMService.synthesize()` with a more specific prompt: "You are interviewing a retiring expert. Known facts about {equipment_family}: {known}. Gaps: {unknown}. Generate 5 questions a retiring engineer would uniquely know — focus on failure attribution accuracy, non-obvious operating conditions, and historical incidents not fully documented." Store questions in `offboarding_session_items.questions`; update status to `questions_ready`
- `GET /elicitation/offboarding/{session_id}/questions` — return questions for the session (same pattern as Task 15)
- `POST /elicitation/offboarding/{session_id}/responses` — accept question-answer pairs; call `store_elicitation_response` Temporal activity; insert into `quarantine_items` with `input_type='offboarding_response'` and `session_context={session_id, session_number, equipment_family, questions, personnel_id}`; update `session_items.status='completed'`; if all 6 sessions complete, update `offboarding_sessions.status='completed'`
- `GET /elicitation/offboarding` — list all active off-boarding programmes with completion percentage (sessions completed / total)
- `GET /elicitation/offboarding/{session_id}` — return programme detail with all session items and their status

**Test:** `POST /elicitation/offboarding` for `engineer@kairos.local`; verify 6 `offboarding_session_items` created with spaced `scheduled_for` dates covering 6 equipment families from their work order history; trigger `generate_offboarding_questions` manually for session 1; verify questions are graph-derived (reference specific failure modes on that equipment family); submit responses; verify `quarantine_items` row with `input_type='offboarding_response'` and full `session_context`.

---

## Task 32: Layer 0 — Rolling Validation Corpus and Model Gate

**Objective:** Every human-promoted quarantine item becomes part of the empirical baseline. Before any NER model configuration change is deployed, it must match or exceed the incumbent's precision/recall on this corpus. Architecture Layer 0 calls this a hard deployment gate.

- Add migration `014_validation_corpus.sql`: `validation_corpus(id UUID PK, document_id TEXT, entity_text TEXT, entity_type TEXT, span_start INT, span_end INT, authority TEXT CHECK IN ('human_promotion','annotation_correction'), promoted_by TEXT, created_at TIMESTAMPTZ)` — each row is a verified ground-truth entity extracted from a real document
- Wire corpus ingestion: in `POST /governance/quarantine/{id}/promote` (Task 9), after promoting the quarantine item, read entity from `quarantine_items.session_context->'entity'` (the live column is `session_context`, not `payload`; the JSON shape stores a single entity object, not a list) and insert into `validation_corpus` with `authority='human_promotion'`; in `POST /annotations` (Task 21), when `is_correct=True`, insert the confirmed entity into `validation_corpus` with `authority='annotation_correction'`
- Create `scripts/run_model_validation.py`: accepts `--model-name` CLI arg; for each row in `validation_corpus`, runs `NERService.extract_entities()` on the source document chunk (fetched from Supabase Storage or ES); compares predicted entity type against ground-truth `entity_type`; outputs per-entity-type precision, recall, F1 and overall metrics; also outputs per-asset-class breakdown
- `GET /governance/validation-corpus/stats` — return corpus size by entity type, by asset class, date of last update; used by the ops dashboard to show corpus coverage
- `POST /governance/model-gate/run` — `admin` only; triggers `run_model_validation.py` as a Celery task on the `validation` queue; returns `{task_id}`; stores result in `audit_log` with `action='model_gate_result'` and `details={model_name, precision, recall, f1, passed: bool}`; `passed=True` if all entity-type F1 scores ≥ incumbent baseline stored in `audit_log`. Register the validation task in `celery_app.py` includes and add `validation` to the `--queues` flag in the Celery worker command in `docker-compose.yml` (same pattern as Task 19 added `transcription`)
- `GET /governance/model-gate/history` — return last 20 model gate runs from `audit_log WHERE action='model_gate_result'` — so engineers can track accuracy trend over time

**Test:** Promote 3 quarantine items; verify 3 rows appear in `validation_corpus`; confirm correct entity; `POST /annotations` with `is_correct=True`; verify 4th row added with `authority='annotation_correction'`; call `POST /governance/model-gate/run`; poll `GET /governance/model-gate/history`; verify result entry with `precision`, `recall`, `f1`, `passed` fields.

---

## Task 33: Equipment Tag-Out + Inspection Completion Events (Layer 8)

**Objective:** Two of the 8 canonical Layer 8 event sources — equipment tag-out and inspection completion — have no `POST /events/` endpoint and no brief assembly path. They are enumerated in the architecture alongside work order, PTW, shift handover, alarm, MoC completion, and recurring failure (now Task 30). Without these, the event subscription layer is 6/8 complete.

- `POST /events/tag-out` — accepts `{asset_id, tag_out_reason, performed_by, expected_return_date}`; dedup via `EventBusService.is_duplicate(asset_id, 'equipment_tag_out', window=10min)`; publish to new `REDIS_STREAM_TAG_OUT`; insert into `operational_events` with `event_type='equipment_tag_out'` and `event_subtype=NULL`; trigger `BriefEngine.assemble_tag_out_brief()` via Celery delay (same late-arrival window pattern as Task 26); write `audit_log`
- `BriefEngine.assemble_tag_out_brief(event)`: query Neo4j for asset's active isolation topology (any `pid_topology` edges on this asset), outstanding PTW items referencing this asset, compliance obligations triggered by taking this equipment class out of service, and any open MoC items that affect this asset; headline = "EQ-X is being tagged out — [N] downstream dependencies identified"; set `brief_priority='high'`
- `POST /events/inspection-complete` — accepts `{asset_id, inspection_type, result, performed_by, findings TEXT, document_id, confidence FLOAT (optional, default 1.0)}`; confidence represents the inspector's stated certainty in the finding — default `1.0` is correct for a direct human attestation (the inspector performed the inspection and is asserting the result); if `document_id` provided, call `GraphService.create_knowledge_edge()` with `authority_level=4`, `confidence=request.confidence` (default 1.0), `verification_status='unverified'`; route to quarantine only if `confidence < 0.7` (which will be rare for a direct human submission); if `result='failed'` or findings non-empty, publish to `REDIS_STREAM_WORK_ORDERS` to trigger a brief for the reliability engineer; insert into `operational_events` with `event_type='inspection_complete'`; call `EventBusService.correlate_events()` (Task 27 — may correlate with existing open WO for same asset)
- `BriefEngine.assemble_inspection_brief(event)` — only assembled on `result='failed'` or when findings reference safety-critical parameters: pulls failure history, open compliance items, last inspection record comparison, and flags if inspection interval deadline is approaching for any related equipment class
- Add both stream names (`REDIS_STREAM_TAG_OUT`, `REDIS_STREAM_INSPECTIONS`) to `config.py` Settings and `.env.example`

**Test:** `POST /events/tag-out` for P-101; verify `operational_events` row with `event_type='equipment_tag_out'`; verify brief assembled with isolation topology context; `POST /events/inspection-complete` for P-101 with `result='failed'` (no `confidence` field); verify Neo4j edge created with `confidence=1.0`, `verification_status='unverified'`; verify brief delivered to reliability engineer user.

---

## Task 34: Governance SLA Tracking + Escalation (Layer 7)

**Objective:** The architecture specifies explicit SLAs with automatic escalation — administrative conflicts: 5-day SLA, escalate to data governance lead at 7 days; engineering conflicts: 24h SLA for safety-critical equipment, 5-day SLA for non-critical. Backlog volume surfaced in the dashboard. None of this is implemented. **No Celery Beat process exists in docker-compose.yml and none should be added** — SLA escalation is implemented as a lazy inline check, consistent with how the circuit breaker and governor already work in this codebase.

- Add migration `015_sla_tracking.sql`: add `sla_due_at TIMESTAMPTZ`, `escalated_at TIMESTAMPTZ`, `escalated_to TEXT` columns to `knowledge_conflicts`; add `sla_due_at TIMESTAMPTZ`, `escalated_at TIMESTAMPTZ` columns to `quarantine_items`
- On `INSERT` into `knowledge_conflicts` (in Task 9 `detect_conflict()`): compute `sla_due_at` = `created_at + INTERVAL '5 days'` for `track='administrative'`, `created_at + INTERVAL '24 hours'` for `track='engineering'` on safety_critical assets, `created_at + INTERVAL '5 days'` for `track='engineering'` on non-critical; store in the row
- On `INSERT` into `quarantine_items` (all paths: Tasks 5, 9, 15, 19, 20, 23, 31): compute `sla_due_at = created_at + INTERVAL '5 days'` for standard items, `+ INTERVAL '24 hours'` for `input_type='deviation_flag'`
- Create `api/services/sla_service.py` with `SLAService.check_and_escalate(supabase) -> dict`: queries `knowledge_conflicts WHERE status='open' AND sla_due_at < NOW() AND escalated_at IS NULL`; for each overdue item, inserts into `audit_log` with `action='sla_escalated'` and `details={conflict_id, track, overdue_by_hours}`; sets `escalated_at=NOW()` on the row; same logic for `quarantine_items WHERE review_status='pending' AND sla_due_at < NOW() AND escalated_at IS NULL`; returns summary dict. **No Celery worker, no Beat, no additional queue.**
- Call `SLAService.check_and_escalate()` lazily at the top of three existing request handlers: `GET /governance/sla-report`, `GET /governance/conflicts`, and `GET /governance/quarantine` — exactly as `CircuitBreakerService.check()` is called inline in `link_to_graph` and `EventBusService.check_governor()` is called inline in `GET /briefs`
- `GET /governance/sla-report` — after running `check_and_escalate()`, return `{overdue_conflicts: [{conflict_id, track, asset_id, overdue_by_hours, escalated}], overdue_quarantine: [{item_id, asset_id, overdue_by_hours}], on_time_conflicts: int, on_time_quarantine: int}`
- Update `GET /governance/conflicts` and `GET /governance/quarantine` responses to include `sla_due_at` and `is_overdue: bool` fields so the frontend can render SLA countdown indicators

**Test:** Insert a conflict with `track='administrative'`; manually set `sla_due_at = NOW() - INTERVAL '1 minute'` in Supabase; call `GET /governance/sla-report`; verify `escalated_at` is now populated on the conflict row and `audit_log` has `action='sla_escalated'`; verify the conflict appears in `overdue_conflicts` in the response.

---

## Non-Negotiable Constraints (apply to every task)

- Every Neo4j edge write must carry all five properties: `valid_from`, `valid_to`, `authority_level`, `document_id`, `confidence`, `verification_status`
- Vault artifacts are never deleted, never overwritten — supersede only (close `valid_to`)
- Unverified inputs never auto-promote to the canonical graph — human action only
- Call `EventBusService.check_governor()` before every brief delivery; PTW briefs (`priority='critical'`) are always exempt
- Safety-critical parameter queries use explicit refusal, never hedged answers
- `MERGE` not `CREATE` for asset nodes in Neo4j
- Authority-level pre-filter before graph traversal, not after
- Never hardcode secrets — all via env vars
- `structlog` for all logging — never `print()` or stdlib `logging`
