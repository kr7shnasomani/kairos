# Kairos code review

**Repository:** `kr7shnasomani/kairos`, branch `main`, commit `a1d7ed4` (latest at the time of review)
**Date:** 2026-10-01
**Companion document:** the 2026-09-30 security review. Security and authorization findings live there and are **not repeated** here. Its findings and their status are listed one per line in [`implementation/status.md` § Accepted risks and deploy checklist](./implementation/status.md#accepted-risks-and-deploy-checklist-from-the-2026-09-30-security-review).

> **Status, 2026-10-01.** This file is the open backlog except for the items below, which the security pass fixed or settled. They are left in the text for history; do not re-file them.
>
> | Item | Status | Where |
> |---|---|---|
> | **B2** event duplicate check marks the event before it is saved | Fixed | `EventBusService.is_duplicate` is read-only and `mark_seen` runs last in every event route; `_store_event` is an insert that accepts an identical retry; `inspection-complete` stores the event first (`routers/events.py`, `services/event_bus.py`) |
> | **B3** a second event on the asset cancels the first event's brief | Fixed | The pending slot is `kairos:brief_pending:{asset_id}:{work_order_id}`, only a re-report of the same work order revokes it, and PTW and tag-out take no slot |
> | **B7** the 4-hour cool-down suppresses the "failed twice" alert | Fixed | `BriefEngine.deliver` matches on `trigger_event_type` as well as recipient and asset |
> | **B16** creating an asset overwrites the Supabase row (same upsert as security M8) | Fixed with M8 | `POST /assets/` is create-only: an `insert`, `409` on a conflict, site-scoped |
> | **S6** unused Python dependencies | Fixed, except `numpy` | `python-jose`, `passlib`, `flower`, `rich`, `tenacity`, `python-dateutil` and `pytz` are removed; `numpy` stays pinned because `qdrant-client` 1.9.1 needs it. `pip-audit` now reports nothing |
> | **S7** vendored agent skills for tech the repo does not use | Done by the owner | Removed from `.agents/skills/`; `.agents/SKILL_MANIFEST.md` marks the ones that moved to the global skills as not vendored |
>
> Everything else below (B1, B4, B5, B6, B8 to B15, the other S items, the performance and test-gap lists) is **still open**.

## How this was produced

Four review skills ran in parallel, each through its own agent, over the whole existing codebase. There is no pending diff, so each skill was pointed at the current code instead.

| Skill | Lens | Scope |
|---|---|---|
| `/code-review` (high effort) | Correctness bugs | Backend, then frontend, then the Go connector |
| `/engineering:code-review` | Performance, reliability, error handling, test gaps | Backend, workflows, workers, Go, frontend |
| `/ponytail:ponytail-review` | Line-level over-engineering | Core backend and frontend modules |
| `/ponytail:ponytail-audit` | Repo-wide: what to delete, merge or replace | Whole repo |

- **Read-only.** Nothing was run, built or changed, and no cloud stores or LLM providers were called.
- **How findings were checked.** Every finding comes from an agent reading the code path end to end. I then re-read the code for **every High** and for each item marked ✔.
- **Confidence labels.** *Plausible* means the code is confirmed, but the impact depends on runtime conditions: load, provider behaviour, or a Supabase setting.

---

## Summary

| Area | High | Medium | Low |
|---|---|---|---|
| Correctness and reliability | 7 | 26 | 22 |
| Performance and scalability | 0 | 8 | 10 |
| Simplification | — | — | about 2,800 lines at code level, plus about 3,000 lines of code and config and about 9,900 lines of docs and vendored skills at structural level (the two overlap, so treat these as upper bounds) |

**Verdict: request changes.** The basics are solid:
- blocking Supabase calls are consistently offloaded to threads;
- clients are pooled;
- every outbound call has a timeout;
- lists paginate;
- Cypher, Elasticsearch and Qdrant calls are parameterised;
- the safety gate has 17+ unit tests.

The main problem is a single pattern: **failures that disappear**. A failed OCR page, a failed lookup, a failed workflow step or a failed save gets turned into "nothing found", "complete" or "duplicate". In this product a technician reads that as "nothing on file", so these are **safety-relevant**, not cosmetic. Most fixes are small and local.

### Fix these first

| # | What | Findings | Effort |
|---|---|---|---|
| 1 | Stop ingestion from silently losing documents and pages | B1, B5 | Small to medium |
| 2 | Stop safety briefs from being dropped | B2, B3, B7 | Small |
| 3 | Show degraded lookups in briefs instead of empty sections | B4 | Small |
| 4 | Fix the deviation-flag freeze | B6 | Medium |
| 5 | Two one-line query fixes | B12, B13 | Tiny |
| 6 | Delete dead weight: unused deps, the write-only event bus, dead code | S4, S6, S9 | Small |

---

## 1. Correctness and reliability

### High

#### B1. OCR silently drops pages that fail, and the document still passes the quality gate ✔

- **Where:** `backend/api/services/ocr.py:104-123`. `_nim_ocr` returns `""` on a 429, 5xx or timeout (`ocr.py:225-232`).
- **Defect:** A page whose OCR call fails is skipped, and confidence is computed only over the pages that succeeded.
- **Failure:**
  - A 40-page scanned inspection report arrives during a NIM rate-limit burst, and pages 12–20 fail.
  - The rest average 0.9, so the gate passes and the job is marked `complete`.
  - The page with the pressure limit is never indexed, and nothing records that pages are missing.
- **Fix:** Count failed pages. If any page failed, return `requires_review` (or raise so Temporal retries), and store `pages_failed` and `page_count` on the job.

#### B2. The event duplicate check marks an event as seen before it is saved ✔

- **Where:** `backend/api/services/event_bus.py:254-260` (`exists` then `setex`).
- **Called from:** `routers/events.py:114, 268, 347, 412, 693, 782`. The inserts happen later (e.g. `:145, :282`).
- **Defect:** The dedup key is written during the check itself, whether or not the rest of the handler succeeds. The check is also not atomic.
- **Failure:**
  - A PTW POST fails on the Supabase insert and returns 500.
  - The connector's retry within `DEDUP_WINDOW_MINUTES` gets `202 deduplicated`.
  - The event is never stored, and **the critical PTW brief is never created**.
  - Two simultaneous identical events can both pass the check.
  - For inspection-complete, the Neo4j edge and the quarantine row are written *before* the event insert, so the stores end up out of step.
- **Fix:** Use `SET key 1 NX EX ttl` only after the insert commits, or `DEL` the key in the exception path. Make the insert idempotent on `event_id`.

#### B3. A second event on the same asset cancels the first event's brief ✔

- **Where:**
  - `routers/events.py:178-188` (work order)
  - `:274-280` (PTW)
  - `:741-749` (tag-out)
- **Defect:** All three share the key `kairos:brief_pending:{asset_id}`. Each one revokes the queued brief task and re-queues a brief built only from its own event.
- **Failure:**
  - WO-1 (technician A) and WO-2 (technician B) hit EQ-101 within five minutes. Only B gets a brief.
  - A tag-out, or a PTW to the issuing engineer, likewise wipes out the assigned technician's work-order brief.
  - The code comment at `:112` says two distinct events on one asset must both produce briefs.
- **Fix:** Key the slot per business id (`brief_pending:{asset}:{work_order_id}`), or merge the pending events into one brief for every recipient.

#### B4. Brief assembly turns lookup failures into "nothing on file" ✔

- **Where:** `backend/api/services/brief_engine.py`. The pattern `r if not isinstance(r, Exception) else []`, with no logging, appears at `:56-62, 187-190, 253-258, 311-317, 395-401, 462-468`.
- **Failure:**
  - Supabase blips during a PTW. The critical brief then says nothing about quarantined items inside the isolation boundary.
  - Neo4j is unreachable. A work-order brief then says "no prior knowledge on file — first occurrence".
  - The brief is stored, so it is never retried, and the 4-hour cooldown suppresses a corrected brief.
- **Fix:** Log each exception and add a `degraded_sources` warning to the brief, or fail the Celery task so it retries.

#### B5. A document can get stuck permanently, because re-uploading it returns "duplicate" ✔

- **Where:**
  - `routers/documents.py:212-219`: the asset link is inserted *outside* the try, after the document and job rows are committed.
  - `:244-263`: the Temporal start. When Temporal is down it returns `workflow_pending`, and nothing ever re-triggers the workflow.
  - `:125-140`: the SHA-256 duplicate check.
  - `workflows/document_pipeline.py:1060-1189`: there is no failure handler, and nothing ever writes `pipeline_stage = "failed"`.
- **Three ways in:**
  1. An unknown or aliased `asset_id` violates the foreign key (`db/schema.sql:74`) after the rows exist, so the request returns 422.
  2. Temporal is down at upload time.
  3. An activity uses up its 5 retries. The job then stays at `queued`, `ocr_running`, `ner_running` or `graph_linking` forever, and the UI keeps polling "in progress".
- **Why it's permanent:** The re-upload matches the SHA-256 check and returns `duplicate`, and the only re-run path requires the `review_required` stage. The document is never indexed.
- **Fix:**
  - Validate `asset_id` (with `resolve_canonical_asset_id`) before any write.
  - Wrap the workflow in a try block and call a `mark_failed` activity.
  - Let the duplicate branch, or a new route, re-start jobs that are `queued` or `failed`.
  - Mark deterministic errors as non-retryable.

#### B6. The deviation-flag brief freeze is broken in four ways (✔ for a)

- **Where:**
  - `routers/events.py:494-500` (freeze) and `:579-585` (unfreeze)
  - `services/brief_engine.py:551-572` (`deliver`)
  - `routers/governance.py:289-295, 391-396`
  - `workflows/document_pipeline.py:276, 288, 791, 903`
- **The four problems:**
  - **a. New briefs aren't frozen.** The freeze only updates briefs that already exist, and `deliver()` never checks for an open flag.
  - **b. Promote or Dispute leaves briefs frozen forever.** The review panel offers these next to "Resolve deviation", and they move the item out of `pending` without unfreezing. "Resolve" then returns 409.
  - **c. Resolving one flag unfreezes briefs another flag still covers.** The unfreeze matches on asset only.
  - **d. Pipeline review items are labelled `input_type = "deviation_flag"`.** So the UI claims briefs are frozen when they aren't, and resolving such an item unfreezes a real flag's briefs.
- **Fix:**
  - Work out "frozen" from open flags (in `deliver` or when reading) instead of a stored boolean.
  - Route Promote and Dispute through the unfreeze helper.
  - Give pipeline items their own `input_type`.

#### B7. The 4-hour cooldown suppresses the "failed twice" alert ✔

- **Where:** `services/brief_engine.py:526-547`, triggered from `routers/events.py:191-203`.
- **Defect:** The cooldown matches on recipient and asset for any brief that isn't critical, and the recurring-failure brief is only `high`.
- **Failure:** WO-1 is delivered at 09:05. WO-2, in the same failure family, arrives at 10:00 for the same technician (or the site). The recurring brief returns WO-1's id instead of being delivered. A failed-inspection brief to the site is suppressed the same way.
- **Fix:** Include `trigger_event_type` in the cooldown match, or exempt recurring-failure and failed-inspection briefs.

### Medium

| # | Finding | Where | Fix | Confidence |
|---|---|---|---|---|
| B8 ✔ | **Recurrence detection never matches failure codes outside the 16-entry family table.** The current code maps with `.get(code, code)`, but prior rows map with `.get(code, "?")`. So `CORROSION` twice in 90 days never produces a recurring-failure brief. | `routers/events.py:125, 138` | Use `.get(code, code)` on both sides, with the same case folding the attribution worker uses | confirmed |
| B9 ✔ | **The alert governor miscounts.** (a) `incr` then `expire(3600)` resets the TTL on every push, so one push every 50 minutes reaches the ceiling of 6 after about 5 hours. (b) Suppression is all-or-nothing, so one inbox load below the ceiling can deliver 10 at once. | `services/event_bus.py:125-131`; `routers/briefs.py:78-87, 183-216` | A sorted set of timestamps (`ZADD` / `ZREMRANGEBYSCORE` / `ZCARD`); pass the remaining budget into `page_inbox` | confirmed |
| B10 | **When the circuit breaker halts graph writes, the workflow still finishes as `complete`.** `link_to_graph` returns `circuit_breaker_halted: True`, the workflow ignores it, and the document ends with 0 edges. The only signal is a write to a Redis stream nothing reads. | `workflows/document_pipeline.py:553-574, 1143-1177` | Set `review_required` or `graph_halted` so it can be replayed | confirmed |
| B11 ✔ | **The circuit breaker never trips on a steady baseline.** Equal weeks (e.g. `[1,1,1]`) give `std = 0`, so the z-score is 0, and even 50 overrides don't halt. Bucket 3 also spans days 21–30 (9 days). | `services/circuit_breaker.py:100-110` | If `std == 0`, halt when `current > mean + k` (or use `std = max(std, 1)`); bucket strictly by 7 days | confirmed |
| B12 ✔ | **`last_inspection_date` is always null.** The query matches the relationship type `-[r:INSPECTION_RECORD]->`, but every knowledge edge is created as `:KNOWLEDGE_EDGE {relationship_type: 'INSPECTION_RECORD'}` (`graph.py:547`). | `services/graph.py:833` | `MATCH (a)-[r:KNOWLEDGE_EDGE {relationship_type:'INSPECTION_RECORD'}]->(:Document)` | confirmed |
| B13 ✔ | **Briefs never get vector evidence.** `_vector_search` queries `QDRANT_COLLECTION_KNOWLEDGE`, but ingestion only writes `QDRANT_COLLECTION_DOCUMENTS` (`document_pipeline.py:977`). A comment at `search.py:563-566` shows the RCA route was already fixed for exactly this: 0 points, measured 2026-08-24. | `services/brief_engine.py:660` | Search `QDRANT_COLLECTION_DOCUMENTS` | confirmed |
| B14 | **A supersede that half-fails can't be retried.** Supabase is flipped to `superseded` first. If Elasticsearch, Qdrant or Neo4j then fails, the response says "re-run", but a re-run gets 409 "already superseded". Old content stays live, or its edges stay open. | `routers/documents.py:959-1017` | Allow an idempotent re-run on an already-superseded document, or flip Supabase last | confirmed |
| B15 | **Time-travel search returns documents that didn't exist yet.** With `as_of` set, only the graph is time-filtered, and Elasticsearch and Qdrant just include superseded documents. `?as_of=2025-01-01` returns, and synthesises from, a September-2026 procedure. | `services/search_service.py:92-126` | Filter ES and Qdrant on `ingested_at`/`occurred_at ≤ as_of` (add the field to the Qdrant payload) | confirmed |
| B16 | **Creating an asset overwrites the Supabase row, while Neo4j keeps the old values.** This is the same upsert as security M8, with same-site triggers. Re-running the EAM sync resets `identity_confirmed_by` and nulls `parent_asset_id`. The bootstrap "Confirm" button turns SAP records into `eam_source = "manual"`. The Go connector's "exists" branch never runs, because the API never returns 409. | `routers/assets.py:291-293`; `graph.py:146-158`; `connectors/cmd/connector/main.go:283-322`; `frontend/.../assets/bootstrap/page.tsx:60-70` | `insert` plus a 409, or skip existing rows as `/assets/bulk` does | confirmed |
| B17 | **The external MoC system it's built for can't call the MoC webhook.** OPA maps it to `resolve_admin_conflict` and returns 401 without a Kairos user token. The HMAC is also computed over `json.dumps(payload, sort_keys=True)`, not the raw bytes, so a sender's own signature won't match. | `middleware/opa.py:31, 101-105`; `routers/governance.py:618-624` | Exempt the route from OPA once the HMAC is mandatory (see security H7); verify against `await request.body()` | confirmed |
| B18 | **Off-boarding question generation never finds graph facts.** The API stores `equipment_class.upper()`, but Neo4j values are lowercase, so interviews always fall back to generic questions. The query also reads `n.name`, which Document nodes don't have. | `routers/elicitation.py:322`; `workers/offboarding.py:66-79`; `workflows/elicitation_workflow.py:75-81` | Match with `toLower`; return document titles | confirmed / plausible |
| B19 | **PI historian errors look like "no data", and mock telemetry counts as evidence.** The Go client never checks `resp.StatusCode`, so a 4xx or 5xx becomes `data: []`. Attribution ignores `mock: true`, so synthetic telemetry is treated as primary evidence. | `connectors/internal/ot/client.go:92-130`; `workers/attribution.py:130-141` | Error on non-2xx; treat mock data or an HTTP error as `unavailable` | confirmed |
| B20 | **Retried activities create duplicate quarantine, conflict and P&ID rows.** Low-confidence entities, conflicts and P&ID elements are inserted with no dedup, and edges use `CREATE`. A failure late in the activity reruns it all. Duplicate P&ID items stay pending forever, because verification keeps only one row per element. | `document_pipeline.py:22-27, 252-297, 787-833`; `graph.py:547`; `topology.py:82-93` | Deterministic keys with `upsert(on_conflict=…)`; `MERGE` edges on `edge_id` | confirmed |
| B21 | **NER's inner retry budget exceeds the activity timeout.** 3 × 120 s plus backoff is more than the 300 s `start_to_close`, so Temporal retries 5×. That is about 45 NIM calls per document when NIM is slow, and it ends in B5. | `services/ner.py:27-30, 185, 229-244`; `document_pipeline.py:1135-1140` | Keep only one retry layer; make the inner budget smaller than the activity timeout | confirmed |
| B22 | **NER only ever reads the first 2,000 characters.** Asset tags after roughly page one never reach the graph or quarantine, and `entity_count` looks complete. | `services/ner.py:32, 215, 254` | Chunk the whole text (the semaphore already exists), or record `ner_truncated_at` | confirmed |
| B23 | **The worker's Neo4j driver is missing the Aura idle-connection fix the API has, and failed edge writes are only logged.** The first document after an idle hour loses some `DOCUMENTED_BY` edges but is still marked complete. | `document_pipeline.py:69-83, 766-770, 836-837, 880-881`; compare `dependencies.py:38-50` | Reuse the API's driver settings; quarantine or re-raise when a write fails | plausible |
| B24 | **Selects with no limit are silently cut off at PostgREST's row cap (1,000 by default).** This affects the alias map plus all assets, coverage, circuit-breaker samples and the EEMUA push-volume gate. With more than 1,000 assets, tags stop resolving. | `document_pipeline.py:502-515`; `coverage.py:87-99`; `circuit_breaker.py:71-78, 149-154`; `governance.py:813-817, 887-892` | `count="exact"` or a `GROUP BY` RPC; look up only the candidate tags with `in_` | plausible (depends on `db-max-rows`) |
| B25 | **Off-boarding Celery tasks scheduled days ahead are redelivered roughly every hour.** `acks_late` is on, and Redis's default 1-hour visibility timeout is shorter than the ETA. Each copy makes an LLM call and resets `questions_ready`, even after the expert has answered. | `routers/elicitation.py:359-378`; `workers/celery_app.py:45`; `workers/offboarding.py:147-152` | Raise `visibility_timeout` above the longest ETA, or schedule from the database with beat; guard on `status == 'pending'` | plausible (documented Celery behaviour) |
| B26 | **Voice transcription failures are returned as successful results and never retried.** The note never reaches quarantine, but the worker was already told "accepted". | `workers/voice_transcription.py:59-77`; `routers/elicitation.py:264-271` | Raise, with `autoretry_for=(httpx.HTTPError,)` and backoff | confirmed |
| B27 | **The synthesis cascade has no overall deadline.** The browser gives up at 90 s, but the server keeps trying tiers for up to about 5 minutes, spending paid quota on answers nobody receives. | `services/llm.py:636-712`; `frontend/src/lib/api.ts:186` | `asyncio.timeout(~85)`; skip any tier whose timeout exceeds the remaining budget | confirmed |
| B28 | **Elicitation answers show "saved offline" on every error.** The API blocks on `execute_workflow`, so anything slower than 8 s gets queued client-side while the server finishes, and replay then creates a duplicate. A 422 is shown as queued and later silently deleted. The queue is only flushed on the `online` event. | `routers/elicitation.py:184-196`; `app/(app)/field/elicitation/[workOrderId]/page.tsx:136-147`; `lib/idb.ts:91-109` | `start_workflow` with the fixed id `elicitation-store-{wo}` and return 202; queue only on a real network failure; flush after login | confirmed |
| B29 | **Any `/auth/me` failure logs the user out.** `resolve_token` turns any Supabase exception into a 401, and `getMe()` returns `null` on a timeout or 5xx. The app shell then logs out. A field tablet loses its session during a backend restart or on a bad connection. | `dependencies.py:225-235`; `lib/auth.ts:32-43`; `components/app-shell.tsx:337-356` | 503 for errors that aren't auth errors; log out only on a confirmed 401 after the refresh fails | confirmed |
| B30 | **Copilot answers land under the wrong question after "New chat".** `newChat()` resets `nextId` to 0 while requests are still running, so a late answer overwrites the new turn and is saved. | `app/(app)/copilot/page.tsx:120-123, 142-165` | Never reset `nextId`, or ignore callbacks from the old conversation | confirmed |
| B31 | **Reads stop working about an hour after sign-in in non-strict builds.** `getJson` refreshes on a 401 only when `isStrictAuth()`. | `lib/api.ts:365-377` | Refresh and retry whenever a token was sent | confirmed |
| B32 | **An empty asset registry or vault shows as a load error.** Both fetchers `throw new Error("empty")` on zero items, so a fresh deployment never shows "Register assets". | `lib/api.ts:458, 761` | Drop the length check | confirmed |
| B33 | **Governance counts are wrong.** "Pending" uses the `total` of a `review_status = all` query, so 10 pending plus 300 resolved shows 310. `limit = 200/50`, newest first, pushes the oldest overdue items off the page. | `app/(app)/governance/page.tsx:94`; `lib/api.ts:470, 484` | Fetch the pending and open items separately | confirmed |

### Low

| Finding | Where |
|---|---|
| The RCA "pre-incident" timeline has no upper date bound. With `LIMIT 50 ASC`, the events closest to the incident are cut off. | `routers/search.py:521-530`; `graph.py:755-769` |
| `/search?as_of=garbage` returns 500 instead of 422. | `routers/search.py:119` |
| `asyncio.create_task(...)` for the feedback recheck keeps no reference, so it can be garbage-collected before it runs. | `routers/briefs.py:500` |
| The OPA and rate-limit middlewares sit outside CORS, so their 401, 403 and 429 responses lack CORS headers. The browser only sees "Failed to fetch". | `backend/api/main.py:85-112` |
| `redate_demo.py` rounds to whole days, so a second run on the same day can shift events again, up to about 12 hours into the future. It writes to cloud stores with no backup. | `backend/scripts/redate_demo.py:88-90` |
| The drift source is always "unknown": the select omits `source_system`, and then the code reads it. ✔ | `document_pipeline.py:517-523, 682` |
| The late-arrival window defaults to 30 minutes in the pipeline but 5 in `Settings`. | `document_pipeline.py:668` |
| Topology promotion marks the quarantine row verified even when the edge write fails. It fails safe, but silently. | `services/topology.py:170-192` |
| The authority filter is applied after Qdrant's `limit`, so `authority_min = 1` can return 0 hits while matches exist. | `services/vector_store.py:133-148` |
| `ackBrief` and `sendBriefFeedback` expect `ack_status` and `feedback_recorded`, which the backend never returns. | `frontend/src/lib/api.ts` |
| The typed brief signature is never sent to or stored by `/briefs/{id}/ack`, although the UI says "Your signature is logged". | `components/brief-detail.tsx`; `routers/briefs.py` |
| Event detail loads forever on any fetch error (no `.catch`). | `app/(app)/events/[id]/page.tsx:25-29` |
| The elicitation page crashes when `questions` is empty. | `app/(app)/field/elicitation/[workOrderId]/page.tsx:120-123` |
| An older RCA request can overwrite a newer one. | `app/(app)/rca/page.tsx:39-48` |
| "Open in vault" on briefs links to the authenticated URL and gets a 400. | `components/brief-detail.tsx:209-213` |
| The SSE `error` frame is swallowed by the parse `try/catch`. | `lib/api.ts:275-280` |
| Re-record leaves the old clip in the parent component, so the old clip is submitted. | `components/voice-recorder.tsx:49-67` |
| `relativeTime` shows future times as "just now", and `slaCountdown` goes negative instead of saying "overdue". | `lib/utils.ts:9-34` |
| Missing briefs and assets render the error screen instead of a 404. | `app/(app)/briefs/[id]`; `assets/[id]` |
| Date-only strings are parsed as UTC, so IST users can't pick "today" between 00:00 and 05:30. | `copilot/_components/composer.tsx:32-33`; `copilot/page.tsx:265` |
| Go `/eam/sync` returns 200 "completed" even when every asset failed. `/ot/query` can end up with `from` after `to`. | `connectors/cmd/connector/main.go:117-126, 274-280` |
| `circuit_breaker.py` recomputes `current_7d`, and its `StatisticsError` handler can never fire. | `services/circuit_breaker.py:81, 102-106` |

---

## 2. Performance and scalability

### Medium

| # | Finding | Where | Fix | Confidence |
|---|---|---|---|---|
| P1 | **Embedding makes one sequential HTTP call per chunk, and any failure restarts from chunk 0.** A 500-page manual is about 570 chunks, which hits the 5-minute activity timeout. The 512-entry cache thrashes on retry. | `document_pipeline.py:966-993`; `services/llm.py:905-932` | Send 32–64 chunks per Jina request (the API accepts lists); upsert the points in one call; heartbeat | code confirmed, timeout plausible |
| P2 | **`/assets/coverage` blocks the event loop.** It is the only sync supabase-py call on an async path; everything else is correctly offloaded with `to_thread`. | `services/coverage.py:42-43, 95` | `await asyncio.to_thread(...)`, both calls in a `gather` | confirmed |
| P3 | **Celery publishes (`apply_async`, `delay`, `control.revoke`) are synchronous broker I/O inside async handlers.** When Redis is slow, the whole API, including SSE, freezes. | `routers/events.py:184, 186, 200, 225, 278, 387, 748, 862`; `elicitation.py:251, 378`; `governance.py:847` | Wrap each in `asyncio.to_thread` | blocking confirmed, stall plausible |
| P4 | **GET list endpoints perform SLA escalation writes, one row at a time.** 150 overdue items means about 300 sequential writes on page load. The frontend's 4 s timeout aborts, and two reviewers escalate the same rows twice. | `routers/governance.py:65, 186, 477`; `services/sla_service.py:27-91` | One bulk update plus one bulk audit insert, run on a schedule rather than inside GET | confirmed |
| P5 | **Bulk asset import makes about three sequential cloud writes per row.** 2,000 rows is about 6,000 round trips, while the UI gives up at 60 s. | `routers/assets.py:151-209` | One `UNWIND` Cypher statement, one Supabase `upsert(list)`, one ES `bulk` | code confirmed, duration plausible |
| P6 | **CPU-heavy PDF and image work runs on the Temporal worker's event loop.** Rasterising a 200-page scan starves every other activity. | `services/ocr.py:272-298, 422-434`; `workers/temporal_worker.py:37-51` | `asyncio.to_thread`, or sync activities on a thread pool | plausible |
| P7 | **Single uvicorn process, and about 250 Supabase calls share the default thread pool** (`min(32, cpu + 4)`). On 2 vCPUs, only 6 Supabase calls run at once. | `backend/Dockerfile:76` | The async Supabase client on hot paths, or a larger dedicated executor; 2+ workers | plausible |
| P8 | **Topology "Confirm all" and OT coverage make N sequential round trips over JSONB and text filters with no index.** A 100-element P&ID is about 200 calls, beyond the 8 s client timeout. | `services/topology.py:62-67, 153-193`; `services/ot_coverage.py:44-51, 77-82` | One `update().in_()` plus one `UNWIND`; index `session_context->>'source_document_id'` | plausible |

### Low

| Finding | Where |
|---|---|
| Brief assembly creates 5 new store clients per task, never closes Qdrant, and has no retry. | `workers/brief_assembly.py:46-60, 84-90` |
| The per-event-loop httpx client is never closed in Celery tasks, so sockets accumulate until the worker recycles. | `services/http.py:27-52` |
| OPA creates a new `httpx.AsyncClient` for every guarded request. | `middleware/opa.py:138` |
| A new Supabase client is built on every auth-cache miss. | `dependencies.py:228` |
| The circuit-breaker probe does a full-table select plus 2 queries per class, and System Health polls it every 30 s. | `services/circuit_breaker.py:147-159` |
| Timestamp alignment runs up to 200 sequential queries, and when enforcement is on, every page view inserts a conflict row. | `routers/governance.py:945-955`; `services/timestamp_alignment.py:146-156` |
| The RCA timeline scans every `Event` in the window with a per-row `EXISTS`. | `services/graph.py:755-769` |
| Redis clients have no socket timeouts, so the fail-open rate limiter hangs for the OS connect timeout during a partition. | `dependencies.py:110-115`; `middleware/ratelimit.py:26` |
| `useRole` and `useMe` each re-fetch `/auth/me`, although the app shell already has the user. | `components/use-role.ts:9-28` |
| The landing page is one 131 KB `"use client"` module, so all static copy ships as JavaScript. | `frontend/src/app/page.tsx` |

---

## 3. Test coverage gaps

These are the riskiest paths that no service-free test covers. The safety gate itself is well tested: 17 tests in `test_query_category.py`, plus `test_synthesis_stream.py`.

| Gap | Covers |
|---|---|
| **Quarantine routing** (`link_to_graph`) has no unit test. Integration tests are skipped in CI. Extract the per-entity decision into a pure function and test all four outcomes. | B20, B23 |
| **Partial OCR failure:** no test for "some pages failed". | B1 |
| **Workflow failure path:** no test that exhausted retries leave the job at `failed`. | B5 |
| **Brief assembly:** nothing tests what `assemble_ptw_brief` or `assemble_work_order_brief` produce, or what happens when a lookup fails. | B4, B7 |
| **Event dedup:** no test that a half-failed ingest can be retried. | B2 |
| **Pending-brief slot:** no test with two work orders on one asset. | B3 |

---

## 4. Simplification: structural (repo-wide)

This comes from `/ponytail:ponytail-audit`. "Deliberate" means `AGENTS.md` or `status.md` records it as a chosen design. Those items are weighed, not dismissed.

| # | Cut | Why (verified) | Saves |
|---|---|---|---|
| S1 | **Replace the Go OT connector service with about 60 lines of Python.** | It is a mock historian (`status.md:87`, "mock by design") plus an HTTP forwarder. `/eam/*` is only called by tests. This also removes security finding M14. *Deliberate:* Go is listed in the stack, but no problem statement requires it. | 1 container, about 1,020 lines, 1 language, 3 CI jobs |
| S2 | **Replace the OPA sidecar with an in-process role table.** | Only `/v1/data/kairos/authz/allow` is ever queried ✔. Five rego rules (`valid_authority_override`, `asset_accessible`, `can_resolve_moc`, `can_promote_quarantine`, `can_countersign_brief`) are never evaluated and appear only in comments ✔. `status.md` records three sidecar-only failures. **Get security sign-off first.** The minimum safe step is deleting the 5 dead rules. | 1 container, about 250 lines |
| S3 | **Drop the separate elicitation Temporal worker.** | Its two workflows each wrap one activity. One is called synchronously inside a request, so durability buys nothing. The other is started only by `/elicitation/trigger`, which nothing in the product calls. The larger question of Celery and Temporal both existing is *deliberate*, so it is flagged, not recommended. | 1 container (1 GB memory limit), about 100 lines |
| S4 | **Delete the Redis Streams "event bus".** | 4 `xadd` sites and **0 readers** ✔. The `redis_stream_id` written back to Supabase after every event is never read. `DATABASE.md:688` wrongly says the workers consume it. Leave the column alone, since changing it would mean a cloud write. | About 130 lines, 7 settings, 1 Supabase write per event |
| S5 | **Trim the docs.** | `API.md` (3,202 lines) restates `/docs` and OpenAPI. The finished plans `BE.md`, `FE.md` and `ui-overhaul.md` (1,517 lines) are in git history. There are overlaps between `DOCKER.md` and `INFRA.md`, a `FIXTURES.md` marked "historical", and a hand-maintained test catalogue. | About 5,100 lines |
| S6 | **Remove 8 unused Python dependencies:** `python-jose`, `passlib`, `flower`, `rich`, `tenacity`, `python-dateutil`, `pytz`, `numpy`. | 0 imports each ✔. **Removing `python-jose` also clears the unfixable `ecdsa` advisory that `status.md:418` is waiting on.** | 8 deps plus their transitive deps |
| S7 | **Delete vendored agent skills for tech the repo doesn't use.** | The repo has no Loki, no Go↔Neo4j, no Neo4j vector index or GenAI, no `LOAD CSV`, no ES security and no Elastic observability, and one skill is a new-project scaffold. | 9 skill directories, about 4,760 lines |
| S8 | **Delete the dead observability configs.** | `infra/otel`, `infra/tempo` and `infra/grafana/provisioning` are mounted by no compose file ✔. `INFRA.md:203` already calls them dead. Keep `dashboards-import/`. | 6 files, 368 lines |
| S9 | **Delete dead backend code.** | Never used: `middleware/auth.py` (never mounted ✔), `models/graph_nodes.py` (never imported ✔), 3 unused models, the stub `workers/ingestion.py`, `link_entities`, `health_check`, `test_artifact_ids`. Also `run_form_extraction`, which is never dispatched ✔ although its comment says "live": wire it up or delete it, together with `forms.py`. | About 220–340 lines |
| S10 | **Trim CI.** | `docker-publish.yml` and the image pushes in `release.yml` publish to GHCR, but deployment builds on the server and nothing pulls from GHCR ✔. `neo4j-idle-recovery` tests a hand copy on Neo4j driver v6, while the app pins 5.21. npm audit runs three times. There are CodeQL template leftovers. | About 280 lines, 1 workflow |
| S11 | **Replace the service-free test list with a directory split.** | The list is hand-maintained in 4 places and has drifted before. Moving the 15 stack-dependent tests into `tests/integration/` means a unit run can't trigger the cloud purge. | About 185 lines, plus the drift risk |
| S12 | **Remove smaller dead items.** | The Ollama fallback tier: no container, an unreachable default URL, and 768-dimensional embeddings in 1024-dimensional collections. Also dead Go code (`internal/eam`, `relay.go`, `OPCUAClient`), `@playwright/test`, unread settings, 8 unneeded apt packages in the backend image, `requirements-cv.txt`, phantom Makefile targets, and the Celery result backend nothing reads. | About 400 lines, several deps |

**Kept on purpose:**
- the golden dataset and cloud stores;
- the benchmark harness;
- the Temporal document pipeline;
- the synthesis cascade;
- the uptime keep-alive;
- `db/backups/knowledge_edges_pre_dedup.json` (unreferenced, but possibly the only pre-dedup copy);
- `deck/`.

---

## 5. Simplification: code level

This comes from `/ponytail:ponytail-review`, applied to `backend/api`, `workflows`, `workers`, `frontend/src/lib` and `frontend/src/components`. The top items by payoff:

| # | Cut | Where | Saves |
|---|---|---|---|
| C1 | **Remove 35 no-op `try { … } catch (e) { throw e instanceof Error ? e : new Error(String(e)) }` wrappers** ✔. Each carries the same copied comment. | `frontend/src/lib/api.ts` | About 200 lines |
| C2 | **Replace 34 hand-built `audit_log` inserts** ✔ with one shared `_audit()` helper. It already exists in `documents.py:541`, which still inlines 4 more itself. | Routers, services, workers, pipeline | About 200 lines |
| C3 | **Cut comment and docstring prose.** 20% of backend lines (3,522 of 17,302) are comments, mostly incident history that belongs in git or `status.md`. One claim is now false: `graph.py:815-831` says "no Event node is ever written", but `merge_event_node` writes one. | `config.py` (153 of 341 lines), `llm.py`, `graph.py`, `corpus.py`, routers | About 480 lines |
| C4 | **Merge the event-ingest sequence** (insert → Event node → publish → stream-id write-back), pasted 6 times, and the defer-brief block, pasted 3 times, into two helpers. | `routers/events.py` | About 125 lines |
| C5 | **Use one builder per store.** Store clients are built 9 (Supabase), 5 (Neo4j), 5 (ES) and 3 (Qdrant) different ways, half of them reading raw `os.environ` with defaults that have drifted from `Settings`. This is the root cause of B23. | Workflows and workers vs `dependencies.py` | About 110 lines |
| C6 | **Keep one copy of `FloatingEdge` / `borderIntersect`**, currently in three copies. Export it from `lib/graph-theme.tsx`. | `knowledge-graph.tsx`, `blast-radius-panel.tsx`, `topo-node.tsx` | About 65 lines |
| C7 | **Build asset fields in one place.** They are hand-copied into 6 dict literals, `site_scope` is re-implemented, the ES index name is hardcoded, and counts are re-queried. | `routers/assets.py` | About 65 lines |
| C8 | **Share one set of failure-mode Cypher and question-parsing helpers.** There are two copies of each. | `workers/offboarding.py` ≈ `workflows/elicitation_workflow.py` | About 60 lines |
| C9 | **Replace the double exception swallowing in brief assembly** (7 helpers plus 6 gather-unpack blocks) with one `_gather_or_empty()` that logs. This is also the fix for B4. | `services/brief_engine.py:613-838` | About 45 lines |
| C10 | **Route all token handling through `fetchWithSession`.** Token, refresh and clear-session logic is rebuilt in 5 places, and one inlines `clearSession()`'s keys. | `frontend/src/lib/api.ts`, `lib/idb.ts` | About 40 lines |
| C11 | **Delete dead frontend code:** 5 `api.ts` exports with no callers, `getQueueLength`, `useAnimatedNumber`, 2 utils, `KpiCard` delta and spark props, `EvidenceLineage.auditEntries`, and the never-populated `CopilotAnswer.entities`, which makes the 162-line `entity-annotations.tsx` unreachable. | `frontend/src/lib`, `components` | About 300 lines |
| C12 | **Remove dead parts of the event bus.** `check_governor` has 0 callers ✔, and the live path re-implements it in `briefs.py:178-181`. `AGENTS.md:158` and `BACKEND.md` still tell agents to call it. | `services/event_bus.py` | About 58 lines |
| C13 | **Swap small hand-rolled code for stdlib:** `collections.Counter` for 7 hand tallies, `asyncio.run` in voice transcription, and dropping 12 `.replace("Z", "+00:00")` calls, which Python 3.11+ no longer needs. | Various | About 35 lines |
| C14 | **Remove duplicated rules:** the compliance applicability predicate appears 3 times, the conflict-row dict twice, the UUID path guards twice, the worker `main()` twice, and there are 2 focus traps. | Various | About 120 lines |
| C15 | **Move `rcaFor` and its fixture packs into the RCA test.** They are test-only but live in a production module. | `frontend/src/lib/rca.ts:15-89` | 75 production lines |

The full per-line list (68 items) was produced by the review agent. Ask if you want it as a separate file.

---

## What was checked and is fine

- **Async hygiene:** every Supabase and Storage call on an async path is offloaded with `to_thread`, except P2.
- **Clients:** API clients are pooled process singletons, including the Aura liveness settings.
- **Timeouts:** every outbound call has one.
- **Pagination:** lists paginate with `range()` and `count = "exact"`.
- **Retries that are already idempotent:** `index_vectors` uses deterministic `uuid5` point ids, and ES indexes by `document_id`.
- **Bounded caches:** embedding LRU, auth cache and alias cache.
- **Neo4j:** traversal depth and blast radius are bounded.
- **Countersign:** separation of duties is enforced on the server.
- **Frontend:**
  - SSE framing, `useFetch` stale-response guards, optimistic rollback and lazy-loaded graph panels are all correct.
  - Heavy chart libraries are imported only where they are used.
- **Go:** response bodies are closed, contexts are propagated, and shutdown is graceful.
