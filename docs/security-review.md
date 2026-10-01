# Kairos security review

**Repository:** `kr7shnasomani/kairos`, branch `main`, commit `a1d7ed4` (the latest at review time)
**Date:** 2026-09-30
**Type:** Manual review of the whole codebase: backend (FastAPI), frontend (Next.js), Go connector, infrastructure, CI, and the full git history (137 commits).
**Method:** I read the code directly. Parallel reviewers covered backend routes, file ingestion, LLM and RAG paths plus the Go connector, and the frontend. I re-read the code behind every finding below myself before including it. Nothing was run against the live deployment or any cloud store.

> This complements CodeQL; it does not replace it. CodeQL is good at finding code patterns (injection, unsafe functions). Most of what follows is **authorization and business-logic** flaws, which pattern scanners do not catch: who is allowed to do what, and which data the safety gate trusts.

---

## Summary

| Severity | Count |
|---|---|
| Critical | 1 |
| High | 7 |
| Medium | 14 |
| Low | 16 |

**The short version:**

1. **The live demo gives any visitor admin access to live data** (C1). Everything else matters less until this is closed.
2. **Roles come from a field users can edit themselves** (H1), so once the demo login is gone, any user could still promote themselves to admin.
3. **Several safety-critical paths trust the caller** (H2–H6). That includes the synthesis safety gate, document authority levels, operational events, compliance evidence and MoC approval. Any logged-in role, or any uploader, can set the inputs that the "refuse when unsure" design depends on.

**What is in good shape:**
- No secrets anywhere in git history.
- No SQL, Cypher or Elasticsearch injection.
- OPA fails closed.
- Production refuses to boot with default secrets.
- Datastores are not exposed publicly.
- No XSS sinks.
- CI does not leak secrets.

See [What was checked and is fine](#what-was-checked-and-is-fine).

### Fix these first

| Order | Finding | Effort |
|---|---|---|
| 1 | C1: replace the admin demo login with a read-only demo account; rotate the seeded passwords | Small |
| 2 | H1: read `role` / `site_id` from `app_metadata`, not `user_metadata` | Small |
| 3 | H4: synthesis must retrieve its own evidence and derive the category server-side | Medium |
| 4 | H2, H3: gate `/events/*` writes and `/events/inspection-complete` behind the connector key or staff roles | Small |
| 5 | H5, H6: tie the authority an uploader may claim to their role; put supersede behind approval | Medium |
| 6 | H7: require `MOC_WEBHOOK_SECRET` in production | Small |
| 7 | M1: enable RLS on the 14 tables that don't have it | Small |

---

## Critical

### C1. The live demo button signs any visitor in as admin, and all seeded passwords are public

- **Where:**
  - `frontend/src/app/login/page.tsx:47-50`
  - `backend/scripts/seed_users.py:21-52`
  - `README.md:156-160`
  - `tests/conftest.py:44-49`
  - `tools/e2e_flows.sh:35-39`
- **What:** The one-click demo calls `doLogin("admin@kairos.local", "KairosAdmin123!")`. The password ships in the client JavaScript bundle, and the passwords for all five seeded roles are committed to the public repo.
- **Impact:** Anyone on the internet can act as admin against the production cloud stores. Per `AGENTS.md`, those stores hold the golden dataset and **have no backup**. Admin can:
  - supersede any document, which closes its graph edges;
  - promote quarantined knowledge;
  - write assets;
  - declare the plant state (which suppresses briefs);
  - approve MoC items;
  - run the model gate;
  - read the full audit log.
- **Status:** `docs/DEPLOY.md:41-42` records this as an **accepted risk**. It is listed as Critical anyway, because it makes every other access control in this report moot on the live site.
- **Fix:**
  - Create a dedicated `demo` role that can only read, grant it in `kairos.rego`, and point the demo button at it.
  - Change all five seeded passwords in Supabase, and stop committing them. Read them from environment variables in the tests and tools.

---

## High

### H1. Roles and sites come from `user_metadata`, which users can edit themselves

- **Where:**
  - `backend/api/dependencies.py:237-245`
  - `backend/scripts/seed_users.py:25-50`
  ```python
  meta = user.user_metadata or {}
  "role": meta.get("role", "field_worker"),
  "site_id": meta.get("site_id", ""),
  ```
- **Why it's a problem:** Supabase's own docs say `raw_user_meta_data` *"can be updated by the authenticated user and is not a good place to store authorization data"*. Access roles belong in `raw_app_meta_data`, which users cannot change.
- **Exploit:** A `field_worker` signs in and calls `PUT {SUPABASE_URL}/auth/v1/user`. The body is `{"data":{"role":"admin","site_id":"<any>"}}`, sent with their own token plus the anon key. Their next API call resolves as admin. That defeats every OPA rule, every `require_role` and every `site_scope` check.
  - If email signup is enabled in the Supabase project, a stranger can sign up with that metadata already set.
- **Condition:** The request needs the Supabase anon key.
  - This frontend does not ship it, which currently limits who can do this.
  - Supabase designs the anon key to be public, so its secrecy is not a control.
  - I could not check the live signup setting from the repo.
- **Fix:**
  - Store role and site in `app_metadata`: `auth.admin.update_user_by_id(id, {"app_metadata": {...}})`.
  - Read `user.app_metadata` in `resolve_token`.
  - Migrate the existing users.
  - Disable open signup in the Supabase dashboard if it is not needed.

### H2. Any signed-in role can create operational events and plant critical safety briefs

- **Where:** these routes in `backend/api/routers/events.py`:

  | Route | Line |
  |---|---|
  | `POST /events/work-order` | 93 |
  | `POST /events/ptw` | 244 |
  | `POST /events/shift-handover` | 326 |
  | `POST /events/alarm` | 397 |
  | `POST /events/tag-out` | 677 |

- **Why nothing stops it:**
  - Each route only requires `CurrentUserDep`.
  - `/events` is not in `_ACTION_MAP` (`backend/api/middleware/opa.py:29-35`), so these fall through to the `write_api` catch-all.
  - `kairos.rego:129-132` allows `write_api` for every role, including `field_worker` and `compliance`.
  - `site_id`, recipient ids and asset ids are taken from the request body (e.g. `events.py:287`) and are never compared with the caller's token.
- **Exploit:** A field worker posts a PTW event naming any engineer as `issuing_engineer_id`, with any text and any `site_id`.
  - This creates a **critical-priority** brief, which bypasses the alarm-rate governor and plant-state suppression.
  - The handler also revokes the asset's pending legitimate brief (`events.py:274-280`).
  - Posting a real `ptw_id` / `work_order_id` first makes the genuine connector event get dropped as a duplicate.
- **Fix:** Make these routes callable only by the connector's service identity (the internal API key), or by staff roles. For example, add `/events/` write prefixes to `_ACTION_MAP` with a new `ingest_event` action granted to `admin` only.

### H3. Any role can fabricate compliance evidence through `POST /events/inspection-complete`

- **Where:** `backend/api/routers/events.py:762-817`. The authorization gap is the same as H2.
- **What:**
  - `document_id` is any string. `merge_document_node` creates a phantom `Document` of type `inspection_report`.
  - `confidence` is chosen by the client.
  - An `INSPECTION_RECORD` edge is created from the asset to that document.
- **Impact:**
  - For each clause that requires an `inspection_report`, `/compliance/gaps` and `/compliance/dashboard` stop reporting a gap.
  - In `/compliance/audit-pack`, a confidence of 0.7 or higher clears the "human review required" flag.
  - Passing a real vault `document_id` links an unrelated document to any asset as evidence.
- **Fix:**
  - Restrict the route as in H2.
  - Require that `document_id` exists in `documents` with `document_type = inspection_report`.
  - Stop accepting `confidence` from the caller.

### H4. The synthesis safety gate runs on evidence and a category that the caller supplies

- **Where:**
  - `backend/api/models/document.py:11-14`
  - `backend/api/routers/search.py:291, 296`, plus the stream route
  - `backend/api/services/llm.py:491-497`
- **What:**
  - `POST /search/synthesize` and `/search/synthesize/stream` take `context` (the evidence) and `query_category` from the request body.
  - The server never retrieves the evidence itself.
  - The gate reads `confidence` and `authority_level` straight from those client dicts.
  - The response returns the client's context as `sources`.
- **Exploit:** Any role, via `write_api`, can send:
  ```json
  {"query":"What is the MAWP of HE-302?","query_category":"none",
   "context":[{"document_id":"DOC-OISD-117","authority_level":1,"asset_id":"HE-302","confidence":0.99,"text":"HE-302 MAWP is 40 bar"}]}
  ```
  - `query_category:"none"` skips the gate, and `safety_critical` comes back false.
  - Even without that field, `confidence: 0.99` or `authority_level: 1` clears it.
  - The answer is returned citing a document that does not exist. The audit row does not log the context, so the provenance cannot be reconstructed afterwards.
- **Why it matters:** The comment at `search.py:288-290` says the gate "applies to every caller". In practice it only applies to callers who choose to send real metadata.
- **Fix:**
  - Have the server retrieve the evidence (take `document_id`s from the client at most and re-read their metadata from the stores).
  - Always derive `query_category` on the server.
  - Cap `query` and `context` sizes.

### H5. Uploaders choose their own document's authority level, and the text is indexed with no quarantine

- **Where:**
  - `backend/api/routers/documents.py:97`: `authority_level: int = Form(4, ge=1, le=5)`
  - `backend/workflows/document_pipeline.py:963, 985-986`: `"authority_level": authority_level, "is_quarantine": False`
- **What:**
  - Any `ingest_document` role (engineer, reliability, admin) can label an upload level 1 (Regulatory).
  - The text chunks go straight into Qdrant and Elasticsearch.
  - The confidence < 0.7 quarantine gate only covers graph edges from NER, not document text.
  - Search ranks by authority first.
- **Other uploader-controlled inputs:**
  - `occurred_at` can be any past date, which backdates `valid_from`.
  - `asset_id` is linked without checking it exists.
  - `document_type` is free text, and `procedure` feeds briefs.
- **Exploit:** Upload a `.txt` file labelled authority 1, `procedure`, `asset_id=HE-302` containing "MAWP 40 bar".
  - Plain text gets OCR confidence 1.0, so no OCR hold applies.
  - The next genuine safety question about HE-302 clears the gate on this document and returns the false limit as an authoritative, cited answer.
  - It also appears in work-order and PTW briefs.
- **Fix:**
  - Allow levels 1–3 only for a designated role, or hold level 1–3 uploads until a second person approves them.
  - Record who asserted the level.

### H6. An engineer can supersede any document, including regulations, with no approval

- **Where:** `backend/api/routers/documents.py:926-1043` (`POST /documents/{id}/supersede`)
- **What:**
  - It closes every graph edge of the old document immediately (`:993`).
  - It marks the old document superseded in Elasticsearch and Qdrant, which drops it from default search and from briefs.
  - Only *afterwards* does it write a MoC row with `status: "draft"`, which gates nothing.
  - There is no check that the new document differs from the old one or is active, and no check of the caller's role against the old document's authority level.
- **Combined with H5:** Upload a forged "level 1" document, then supersede the real regulation with it.
- **Fix:**
  - For authority 1–3, create the MoC first and close the validity windows only when the MoC is approved (reuse `_resolve_moc_conflict`).
  - Reject `new_document_id == document_id` and replacements that are not `active`.

### H7. The MoC webhook signature is optional, so a `reliability` user can approve MoC items as someone else

- **Where:**
  - `backend/api/routers/governance.py:590-640`
  - `backend/api/config.py:283` (`MOC_WEBHOOK_SECRET: str | None = None`)
  - `.env.example:21` (commented out)
- **What:**
  - When the secret is unset, no signature is checked.
  - The route has no role dependency.
  - OPA maps `/governance/moc` to `resolve_admin_conflict`, which `reliability` holds.
  - `approved_by` is taken from the body.
  - By contrast, the in-app approval route `POST /governance/moc/{id}/approve` requires `engineer` or `admin`.
- **Exploit:** A reliability user posts `{"moc_id":"MOC-…","status":"approved","approved_by":"<an engineer's id>"}`.
  - The old fact's validity window closes.
  - The conflict resolves.
  - The audit log names the engineer as approver.
- **Condition:** Only while `MOC_WEBHOOK_SECRET` is unset. `DEPLOY.md` does not tell you to set it, and I could not see the live `.env`.
- **Fix:**
  - Add `MOC_WEBHOOK_SECRET` to the production boot guard in `config.py:308-330`.
  - Include a timestamp in the signed body and reject stale requests; right now a captured signed body can be replayed.

---

## Medium

### M1. Row-level security is off on 14 of 19 tables

- **Where:** `db/schema.sql:318-322`. Only `assets`, `documents`, `briefs`, `quarantine_items` and `audit_log` enable RLS.
- **Without RLS:**
  - `asset_alias_map`, `document_asset_links`, `extraction_jobs`, `operational_events`, `brief_feedback`
  - `knowledge_conflicts`, `moc_items`, `elicitation_sessions`, `ner_annotations`, `extraction_overrides`
  - `plant_operating_states`, `validation_corpus`, `offboarding_sessions`, `offboarding_session_items`
- **Impact:** In Supabase, `public` tables are exposed through PostgREST. Anyone holding the anon key can read, insert, update and **delete** rows in these tables directly, bypassing the API, OPA and the audit log.
  - That includes the governance tables (`moc_items`, `knowledge_conflicts`) and personal data (`offboarding_sessions.personnel_email`).
- **Condition:** Same as H1: the anon key is not in this frontend, but it is designed to be public. The live database may differ from `schema.sql`; check it in Supabase → Advisors → Security.
- **Fix:** Add `ALTER TABLE … ENABLE ROW LEVEL SECURITY` for all 14 tables. The backend uses the service-role key, so it is unaffected.

### M2. Filter injection in `GET /briefs/` through `site_id`

- **Where:** `backend/api/routers/briefs.py:166`
  ```python
  .or_(f"recipient_user_id.eq.{user_id},recipient_user_id.eq.{site_recipient}")  # site_recipient = f"site-{site_id}"
  ```
- **What:** `site_id` comes from `user_metadata` (H1). A value such as `SITE_001,recipient_user_id.neq.x` adds an extra OR condition, and the inbox then returns **every user's briefs**, up to 150. That is more than even an admin can list today.
- **Fix:** Use `.in_("recipient_user_id", [user_id, site_recipient])`, the same way `_brief_recipients` already does. This is needed even after H1 is fixed.

### M3. The Copilot's streaming endpoint writes no audit record and drops pending-MoC warnings

- **Where:** `backend/api/routers/search.py:346-445` (`synthesize_stream`). It has no `SupabaseDep`, no `audit_log` insert and no `pending_moc_warnings` call. The non-streaming route has both (`:313-331`).
- **Impact:** The Copilot UI always uses the stream (`frontend/src/lib/api.ts:643-646`), so **every production Copilot answer, including safety-critical ones, is unaudited**. The rule that an answer from an asset under a pending MoC must carry a warning is never applied in the UI.
- **Fix:** Share the audit and pending-MoC step between both routes.

### M4. LLM output is trusted for safety decisions (prompt injection)

- **Where:**
  - `backend/api/services/llm.py:579-621`: document text goes into a single user message, and its `[Source i | Authority Level n | Document: …]` header can be forged from inside the text.
  - `llm.py:554`: the post-synthesis gate passes when the model reports no `CONFIDENCE` at all (`if answer_confidence is None or …: return None`).
  - `llm.py:763, 783`: the first `CONFIDENCE:` in the output wins, and `sources_used` numbers are never checked against the context.
  - `backend/api/services/ner.py:367`: `confidence = float(item.get("confidence", 0.85))`. The model's own score decides graph versus quarantine, and a missing score defaults above the 0.7 threshold.
  - RCA: work-order text is inserted into the prompt, and hypothesis source ids are not checked against the evidence (`llm.py:797-886`). An unguarded `float()` on `CONFIDENCE: 0.8.` returns a 500.
- **Exploit:** A document uploaded for an asset contains a fake higher-authority source block and tells the model to answer with a planted value, or to omit the CONFIDENCE line.
- **Fix:**
  - Put instructions in a system message and wrap each document in delimiters with escaping.
  - Treat a missing confidence as a refusal for safety categories.
  - Reject citations outside the context.
  - Leave the NER `confidence` default below 0.7.

### M5. Gaps in the safety classifier and in same-asset anchoring

- **Where:** `backend/api/services/llm.py:107-150, 227-238, 253-267, 494`
- **What:**
  - **Classifier:** It is a keyword list that fails open. These wordings return no category, so they skip the gate:
    - "What is the highest pressure HE-302 can safely handle?"
    - "How many Nm should the P-101 bolts be tightened to?"
    - "What's the ESD trip value for LT-201?"
  - **Anchoring:**
    - Naming a second asset lets that asset's evidence clear the gate.
    - Asset names or aliases with no tag fall back to whichever document ranks first.
    - `max_confidence` is computed over the whole context instead of the anchored `gate_context`.
- **Fix:**
  - Make the classifier fail closed: when unsure, treat the query as safety-critical.
  - Require every tag in the query to be anchored.
  - Compute confidence over `gate_context`.

### M6. Any role can forge the actor on audit and quarantine records

- **Where:**

  | Location | Forged field |
  |---|---|
  | `events.py:995-1009` (`POST /events/{id}/ack`) | `"performed_by": payload.user_id`; `role` and `signature` come from the body |
  | `events.py:732` (tag-out) | `performed_by` |
  | `events.py:474` (deviation-flag) | `reported_by` |
  | `elicitation.py:191, 212, 485` | `submitted_by` |

- **What:** `current_user` is available in all of these, but the identity written is the one the client sent.
  - `deviation-flag` also freezes every unacknowledged brief for any asset on any site (`events.py:496`), and only engineer or admin can unfreeze.
- **Impact:** The audit trail read by the compliance role can show acknowledgements, reports and submissions by people who never made them.
- **Fix:** Always write `current_user["user_id"]` and drop the identity fields from the request models.

### M7. Any role can poison the model-gate ground truth and trip the circuit breaker

- **Where:** `backend/api/routers/annotations.py:36-137` (write_api, any role)
- **What:**
  - With `is_correct=true`, it inserts rows into `validation_corpus`, which is the ground truth the model gate scores against (`annotations.py:68`).
  - With `is_correct=false`, it calls `cb.record_override(...)` on every request (`:120`), with no limit and no dedup.
  - It lowers a matching quarantine item's confidence by 0.1 per call.
- **Exploit:** A field worker loops correction requests. The Z-score passes 2, and `link_to_graph` halts graph ingestion for that asset class (`document_pipeline.py:553-574`).
- **Fix:**
  - Restrict corpus inserts to reliability and admin.
  - Dedup overrides per user and document, and rate-limit them.

### M8. Site boundary is missing on many reads and writes

- **Where:** `site_scope` is applied only in `GET /assets/`, `/assets/provisional`, `/compliance/gaps` and `/compliance/dashboard`. It is absent from:
  - `GET /assets/{id}` and its sub-routes, `/assets/coverage`, `/assets/aliases/pending`
  - `GET /compliance/audit-pack`
  - `GET /events/` and `GET /events/{id}`
  - `POST /search/rca-pack`
  - `POST /events/plant-state` (engineer only, but any site: `events.py:645`)
  - alias confirm/reject
  - `POST /assets/`, which `upsert`s on `asset_id` (`assets.py:292`) and can overwrite another site's asset row while Neo4j keeps the old values
- **Impact today:** Low, because the system is single-site (`dependencies.py:318`). It becomes a real cross-tenant leak as soon as a second site is added.
- **Fix:** Apply `site_scope` to every lookup by id, and use `insert` rather than `upsert` for single asset create.

### M9. Retiring employees' data is readable by every role, and anyone can complete another person's programme

- **Where:** `backend/api/routers/elicitation.py:396-548`
- **What:**
  - `GET /elicitation/offboarding`, `/{id}` and `/questions` return `personnel_id`, `personnel_email` and `retirement_date` to every role. OPA does not enforce `/elicitation` reads.
  - `POST /elicitation/offboarding/{id}/responses` lets any role mark items, and the whole programme, `completed`, so the real knowledge-capture interview is lost.
- **Fix:**
  - Restrict the reads to staff roles and the person being offboarded.
  - Require the caller to be that person, or staff.

### M10. Shared devices keep one user's data and actions after sign-out

- **Where:**
  - `frontend/public/sw.js:11, 35-51, 60-83`
  - `frontend/src/lib/idb.ts:25-85`
  - `frontend/src/lib/api.ts:131-140`
  - `frontend/src/app/(app)/copilot/page.tsx:68, 113`
- **What:**
  - **API cache:** the service worker caches cross-origin API GETs under `/briefs`, `/assets` and `/elicitation`, keyed by URL, and serves them **cache-first even when online**. It also caches every successful page navigation. Logout (`clearSession`) only clears localStorage and the cookie; nothing calls `caches.delete`. The next user of the device is served the previous user's data first.
  - **Offline write queue:** queued writes (IndexedDB) store no user. On reconnect they are replayed with *whoever is now signed in* (`idb.ts:77-85`). Person A's offline elicitation answers get filed as person B's.
  - **Copilot history:** the Copilot conversation stays in `sessionStorage` across sign-out and sign-in in the same tab.
- **Why it matters here:** The product targets field tablets, which are often shared.
- **Fix:**
  - On logout, delete both caches, clear `kairos-queue` and sessionStorage, and post a message to the service worker.
  - Record the user id on each queued write and drop entries that don't match the current user.
  - Don't cache API responses cache-first while online.

### M11. Size and cost exhaustion

- **Voice upload:** `POST /elicitation/{wo}/voice` calls `await file.read()` with **no size limit** (`elicitation.py:218`), and any role can call it. The API container limit is 1500 MB.
- **PDF rendering:** `ocr.py:422-434` renders every PDF page to PNG in memory, with no page-count or page-size limit. A single oversized page is over 1 GB. The P&ID path uses 150 DPI (`pid.py:160`).
- **Spreadsheets:** XLSX files load every row of every sheet.
- **Retries:** the worker retries 5 times (`document_pipeline.py:22-27`), so one bad file repeatedly crashes the only ingestion worker.
- **Synthesis:** `query` and `context` have no size limit, and one request can trigger up to about 8 paid provider calls.
- **Proxy:** Caddy sets no `request_body` limit.
- **Fix:**
  - Apply `MAX_UPLOAD_MB` to the voice upload.
  - Cap PDF pages, page size and DPI, and XLSX rows.
  - Add `request_body { max_size 30MB }` in the Caddyfile.
  - Add `max_length` to `SynthesizeRequest`.

### M12. Client-supplied names go straight into service-role storage paths

- **Where:**
  - `backend/api/routers/documents.py:143`: `f"{document_type}/{document_id}/{file.filename}"`
  - `backend/api/routers/elicitation.py:236`: `f"voice_notes/{work_order_id}/{sha256[:8]}_{file.filename}"`
- **What:** The filename, `document_type` and `work_order_id` are not sanitised. The upload uses the service-role client, which bypasses storage policies. A filename containing `../` can place objects outside the document's folder, and possibly in another bucket, if the HTTP client or storage server resolves dot-segments.
- **Not confirmed:** I could not run the storage library here, and testing would mean writing to your cloud store, which your project rules forbid. Confirm it against a throwaway Supabase project.
- **Fix:** Use `PurePosixPath(file.filename).name` and allow only `[A-Za-z0-9._-]`. Validate `document_type` against a fixed list.

### M13. The ingestion pipeline links using unconfirmed aliases, and test-style names hide documents from reviewers

- **Where:**
  - `backend/workflows/document_pipeline.py:502-505` loads **all** `asset_alias_map` rows, confirmed or not. The API side filters `confirmed=True` (`assets.py:42-48`).
  - `backend/api/services/corpus.py:56`
- **Aliases:** One upload that mentions another asset's tag creates an unconfirmed alias pointing at the uploader's chosen asset. From then on, every later document with that tag links to the wrong asset, and none of them produce an "unresolved tag" quarantine item.
- **Hidden files:** File names matching the test-artifact pattern (`test_…`, `tmp…`, `kairos_…`) are hidden from the document list and from search, but brief assembly still uses them (`brief_engine.py:686-700`).
- **Fix:**
  - Filter `confirmed = true` in the pipeline.
  - Classify test artifacts by an explicit flag, not by a file name the uploader chooses.

### M14. The Go connector's listener has no authentication and forwards requests with the admin key

- **Where:**
  - `backend/connectors/cmd/connector/main.go:44-66`
  - `main.go:325-341` (forwarding with `Authorization: Bearer <INTERNAL_API_KEY>`)
- **What:**
  - `/ot/query`, `/eam/sync` and `/eam/work-order` accept requests from anyone who can reach port 8090.
  - `/eam/work-order` forwards the raw request body to FastAPI as admin.
  - In production, 8090 is only on the internal Docker network. In dev, `docker-compose.override.yml:64-65` publishes it on all interfaces.
  - Related: the PI tag is not URL-escaped (`internal/ot/client.go:84`), and `io.ReadAll` has no size limit.
- **Fix:**
  - Require a shared secret header on the connector.
  - Bind to `127.0.0.1` in dev.
  - Escape query parameters and use `http.MaxBytesReader`.

---

## Low

| # | Finding | Where | Fix |
|---|---|---|---|
| L1 | Access and refresh tokens are kept in `localStorage`, and the access token is copied into a cookie scripts can read. There is no server-side logout or revocation. | `frontend/src/lib/api.ts:94-106`; `backend/api/routers/auth.py` | Use HttpOnly cookies set by the backend; add a logout endpoint that revokes the refresh token. |
| L2 | No security headers: no CSP, `frame-ancestors`, `X-Content-Type-Options` or `Referrer-Policy`. | `frontend/next.config.ts`; no `vercel.json` | Add `headers()` in `next.config.ts`. |
| L3 | Route and query params go into API paths without encoding (`/events/${id}`, `/briefs/${id}`, compare `?a=&b=`), so a crafted link can redirect a victim's request to another API path. | `frontend/src/lib/api.ts:431, 772, 1224, 1234` | Wrap them in `encodeURIComponent`, as other calls already do. |
| L4 | The internal API key is compared with `==` (not constant-time). It is one static admin identity, shared by the connector and the workers, and never expires. | `backend/api/dependencies.py:215-216` | Use `hmac.compare_digest`, a narrower service role, and a separate key per service. |
| L5 | Every protection keys off the exact string `APP_ENV == "production"`. `"prod"` or `"Production"` silently turns on the dev bypass (no token becomes engineer), the OPA pass-through, no rate limit, and the default admin key. | `backend/api/config.py:23-44, 313` | Default to secure: enable bypasses only when `APP_ENV == "development"`. |
| L6 | Login and refresh return `detail=str(e)` (reveals whether an account exists). Vault errors echo exception text. | `auth.py:43, 61`; `documents.py:160, 207, 687`; `main.py:148` | Return generic messages and log the detail. |
| L7 | `/health/detailed` is unauthenticated and makes 5 store checks per request. `/docs` and `/openapi.json` are public in production. | `routers/health.py:45-130`; `main.py:76-78` | Require auth on `detailed`; disable docs in production. |
| L8 | NER ignores `NVIDIA_NIM_BASE_URL` and always sends the key and document text to NVIDIA's public endpoint. | `backend/api/services/ner.py:21` | Use the configured base URL. |
| L9 | Unredacted content goes to all external providers (by design, `pii.py:1-12`). The export redaction misses names after the first 2,000 characters, hyphenated Aadhaar numbers, and `+91 98765 43210`-style phones. | `pii.py`; `ner.py:32`; `documents.py:875-881` | Document this for customers; widen the patterns. |
| L10 | The uploaded `content-type` is stored and served back through signed URLs, so HTML or SVG can render on the storage origin. | `documents.py:144, 153` | Allow only known types; force `Content-Disposition: attachment`. |
| L11 | Brief ack overwrites an existing ack, and feedback has no recipient check. | `backend/api/routers/briefs.py:334-340, 490` | Reject if already acknowledged; check the recipient. |
| L12 | P&ID element ids from the vision model are used as global node ids (`ON CREATE`), so drawings can attach to each other's nodes. The demo fixture is used as a fallback when the model is down. | `document_pipeline.py:219-245`; `graph.py:315-318` | Prefix node ids with the document id. |
| L13 | The document upload size check runs after the whole body has been spooled to disk. | `documents.py:115-122` | Also limit at Caddy (M11). |
| L14 | Go connector error responses echo upstream and FastAPI error text, and the PI URL is logged. | `connectors/cmd/connector/main.go:38, 132, 322, 345` | Return generic errors. |
| L15 | Third-party GitHub Actions are pinned by tag, not commit SHA (`dorny/paths-filter`, `softprops/action-gh-release`, `hadolint`, `golangci-lint-action`, `ruff-action`). | `.github/workflows/*.yml` | Pin to SHAs; Dependabot can keep them updated. |
| L16 | The frontend Docker image can't turn on strict auth, because `NEXT_PUBLIC_AUTH_STRICT` is never passed as a build argument. The Vercel deployment is unaffected. | `frontend/Dockerfile:29-30` | Add the build arg. |

---

## What was checked and is fine

- **Secrets in git:** I scanned all 137 commits for NVIDIA, OpenRouter, Google, Groq, Jina, Grafana, AWS and GitHub keys, JWTs, private keys and Supabase keys. **Nothing found.** No `.env` file was ever committed. Only the Supabase project ref (`ernffgrvdcikwwhkhiix`) and placeholders appear, and the project ref is not a secret.
- **Injection:**
  - Cypher labels are allow-listed, and values are bound parameters.
  - Elasticsearch uses `multi_match` and `term`, never `query_string`.
  - Qdrant uses typed filters.
  - PostgREST uses `.eq` / `.in_` everywhere except M2.
  - No `eval`, `exec`, `subprocess`, `pickle` or `yaml.load`.
- **Authentication basics:**
  - Every data route requires a token in production.
  - OPA **fails closed** when it can't be reached.
  - Production refuses to boot with the default internal key, app secret or Neo4j password.
  - CORS uses an explicit origin list.
- **Network exposure:**
  - Production publishes only 80 and 443 (Caddy).
  - The API binds to `127.0.0.1:8000`.
  - Elasticsearch, Redis, OPA, Temporal and the Go connector sit on the internal Docker network only.
  - The dev override that publishes them is not deployed.
- **Rate-limit spoofing:** The limiter trusts `X-Forwarded-For`, but Caddy's documented default ignores client-supplied `X-Forwarded-*` headers when no `trusted_proxies` are configured, and none are.
- **Containers:** The backend image runs as uid 1001 and the Go image as non-root. Only the dev override runs as root.
- **Outbound HTTP:** TLS verification is on everywhere (no `verify=False` or `InsecureSkipVerify`). No URL comes from user input or document content, so there is no SSRF.
- **File parsing:** Pillow's decompression-bomb guard is intact. On Python 3.12, openpyxl's XML parsing does not resolve external entities. SVG is never parsed locally.
- **Frontend:**
  - No `dangerouslySetInnerHTML` except a static theme script.
  - No markdown or HTML rendering of API data.
  - No open redirects.
  - The YouTube embed id is constrained to 11 safe characters.
  - No secret `NEXT_PUBLIC_*` variables.
- **CI:**
  - No `pull_request_target` or `workflow_run` triggers, and no `${{ github.event.* }}` inside `run:` steps.
  - Secrets are used only in scheduled and push workflows.
  - Integration tests are disabled rather than pointed at production.
- **Role gates that hold:**
  - quarantine promotion, MoC approval in the app, model gate, OCR release;
  - topology verify, asset writes, bulk import (site-checked, max 5000 rows);
  - PTW countersign (separation of duties enforced on the server).

---

## Limits of this review

- **Static review only.** Nothing was run. I did not probe the live site or touch any cloud store. Your `AGENTS.md` forbids cloud writes, and several findings could only be proven with one.
- **Needs checking in the Supabase dashboard:**
  - whether email signup is enabled (affects H1);
  - whether the live database has RLS enabled on the 14 tables (M1);
  - whether production sets `MOC_WEBHOOK_SECRET` (H7).
- **M12 (storage paths)** depends on library and server path normalisation that I could not run. Confirm it against a throwaway project.
- **Dependency CVEs:** I did not do a full audit. `deps-audit.yml` and Dependabot already cover that. I found no key frontend package on a version with a known serious CVE.

**Sources:**
- Supabase, managing user data: `user_metadata` vs `app_metadata` — https://supabase.com/docs/guides/auth/managing-user-data
- Caddy, `reverse_proxy` handling of `X-Forwarded-*` and `trusted_proxies` — https://caddyserver.com/docs/caddyfile/directives/reverse_proxy
