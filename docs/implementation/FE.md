# Kairos — Frontend Implementation Plan

> ⚠️ **Superseded on the data-source policy.** This build plan predates the **live-only** switch. Tasks
> below that say "keep the live→fixture `{data, source}` pattern", "1500 ms abort", "show the demo chip", or
> "fall back to fixture on empty" are **historical** — the app is now live-only (real data · skeleton ·
> error+retry, never a fixture; 4 s default timeout). Also stale here: governance promotion is
> `reliability`/`admin` (not `admin`/`engineer`). See `docs/FRONTEND.md §6` and `docs/FIXTURES.md §3` for
> the current behavior. The rest of each task (routes, layouts, API calls) still holds.

> The contract for the point-of-action interface layer (ARCHITECTURE.md Layer 12). This document is to the frontend what `docs/implementation/BE.md` is to the backend: a fully-scoped, task-by-task build plan traceable to the architecture. Every task names the files it touches, the API calls it makes, the architecture layer it serves, and a verification step. Nothing in the architecture's interface surface is left unscoped.

---

## Current State

The frontend is a Next.js 16 / React 19 / Tailwind v4 app (`frontend/`) with **all 36 plan tasks implemented** (Tasks 1–36, including 8b, 20b, 20c) plus the Task-31 projects registry, and wired live to the backend — fixture fallbacks were removed; fetchers throw and the UI shows real data, a skeleton, or error+retry. Against the full Layer 12 architectural vision it now scores ~95/100. All routes are TypeScript-clean (`npx tsc --noEmit`), ESLint-clean (0 errors), and `next build` passes.

**Browser verification is COMPLETE** (2026-07-11). Every desktop route was verified against the golden dataset with admin/engineer sessions, and all field routes (8–12) with a real `field_worker` session at mobile width (the bottom tab bar was later removed — mobile navigates via the hamburger sidebar). Seven live-data crashes were found and fixed during the sweep — all frontend-type-vs-backend-contract mismatches (`compliance/dashboard.total_gaps`, SLA report, circuit breaker, model-gate validation corpus, blast radius, P&ID topology, offboarding list) — plus a production-only service-worker refresh-loop fix and a new `/field/voice` index page (the "Voice" bottom tab was a dead link). Details in `AGENTS.md` "Known Pitfalls" and `docs/FRONTEND.md` §6.

**Built (live-only):** login, briefs inbox + detail (ack/feedback/PTW dual-sign), copilot (phase-gated + voice), assets list + detail + bootstrap + MDM, RCA, compliance cockpit + audit-pack + non-conformance, governance conflicts + quarantine + MoC + SLA + circuit-breaker + model-gate, documents list + detail + ingestion + comparison + topology (P&ID), knowledge graph (React Flow), time-travel timeline, blast-radius panel, annotation panel, elicitation + offboarding, voice capture, deviation flag, offline shell + sync queue, audit trail, management overview + cross-site + plant-state, events list + detail, audit trail.

**Reusable foundation already in place — build on it, never duplicate:**
- `src/lib/api.ts` — SSR-aware `API_BASE`, `getJson`/`postJson`, live→fixture fetchers returning `{ data, source }`.
- `src/lib/types.ts` — TS types derived from `docs/API.md` (single source of truth).
- `src/components/ui.tsx` — `StatusBadge`, `AuthorityBadge`, `SourceChip`, `Modal`, `Button`.
- `src/components/app-shell.tsx` — sidebar + mobile drawer + auth guard + role-gated nav.
- `src/app/globals.css` — "Paper" theme: one-UI-two-palettes tokens, `:focus-visible`, `prefers-reduced-motion`, `.tabular`.
- `src/components/use-role.ts`, `theme-toggle.tsx`, `skeleton.tsx`, `brief-*.tsx`.

**The 65-point gap this plan closes (mapped to Layer 12 personas):**
- **Field / point-of-action app** — mobile-first, single-handed, sunlight-legible, offline+sync, voice input, elicitation & deviation capture. Almost entirely absent.
- **Engineer & reliability desktop workspace** — graph visualization, time-travel timeline, P&ID topology viewer, blast-radius, document comparison, RCA workspace, audit trail. Mostly absent.
- **Quality & compliance cockpit** — audit-pack assembly, non-conformance tracking, inspection records. Partial.
- **Project & procurement workspace** — engineering doc registry, revision tracking, procurement history. Absent.
- **Management & cross-functional dashboard** — live KPIs, knowledge coverage, cross-site alerts, plant-state control. Fixture-only.
- **Governance depth** — MoC UI, SLA report, SPC circuit breaker, Layer 0 model gate. Endpoints exist, no UI.
- **Trust arc** — Phase 1/2/3 deployment state is invisible to users.
- **Front door & identity** — no document-ingestion UI (the entry point of Flow C and the PS's first pillar, Universal Document Ingestion) and no MDM identity-confirmation surface (Layer 1's "no AI-invented identities" principle) exist today.

---

## Format Conventions & Ground Rules

- Every task follows the `BE.md` shape: **Objective → steps (files / components / API calls) → Test.**
- Each task tags its **architecture layer(s)** and, where scope is cut for the MVP, carries a `ponytail:` note naming the leaner choice and the upgrade path.
- **Phase mapping:** the interface must reflect the trust arc — Phase 1 (retrieval), Phase 2 (assisted synthesis + feedback), Phase 3 (governed proactive). Features gate on phase where the architecture says so.
- **No new dependency** unless a task names it. The only pre-approved addition is a graph renderer (React Flow) for Task 15; charts are pure SVG/CSS; voice uses the native `MediaRecorder` API; offline uses the native Service Worker + IndexedDB — no libraries.
- **`frontend/` ownership:** this plan is the authorization to work in `frontend/`. Follow `frontend/DESIGN.md` for every visual decision; reuse `ui.tsx` primitives; never build a "dark version" of a component.

---

## Persona → Route Map

| Layer 12 persona | Routes | Task group |
|---|---|---|
| Field / point-of-action | `/briefs`, `/briefs/[id]`, `/field/elicitation/[workOrderId]`, `/field/*`, voice, offline | B |
| Copilot (all users) | `/copilot`, inline annotation | C |
| Engineer & reliability desktop | `/assets/[id]`, `/assets/bootstrap`, `/graph`, `/rca`, `/documents/[id]`, `/documents/ingest`, `/offboarding`, `/governance/*`, `/audit` | D |
| Quality & compliance cockpit | `/compliance`, `/compliance/audit-pack`, `/compliance/nonconformance` | E |
| Governance operations | `/governance/moc`, `/governance/sla`, `/governance/timestamp-drift`, `/governance/push-volume-gate`, `/governance/circuit-breaker`, `/governance/model-gate` | F |
| Project & procurement | `/projects`, `/documents` (registry mode) | G |
| Management & cross-functional | `/management`, `/management/cross-site`, `/management/plant-state` | H |
| Operational events | `/events/*` | I |

---

# Group A — Foundation & Contract

## Task 1: Complete the API client + type surface

**Layer:** all · **Objective:** Every backend endpoint that exists but has no frontend fetcher gets one, plus a matching TypeScript type. The client stays the single integration boundary; pages never call `fetch` directly.

- Extend `src/lib/api.ts` with fetchers (keeping the live→fixture `{ data, source }` pattern and 1500 ms abort) for the currently-unwired endpoints:
  - Governance: `GET /governance/sla-report`, `GET /governance/moc`, `GET /governance/moc/{id}`, `GET /governance/circuit-breaker`, `GET /governance/model-gate/history`, `GET /governance/validation-corpus/stats`, `POST /governance/model-gate/run`, `GET /governance/blast-radius/{document_id}`.
  - Annotations: `POST /annotations`, `GET /annotations?document_id=`, `GET /annotations/stats`.
  - Elicitation: `POST /elicitation/trigger`, `GET /elicitation/{wo}/questions`, `POST /elicitation/{wo}/responses`, `POST /elicitation/{wo}/voice`, and the offboarding set (`POST /elicitation/offboarding`, `GET /elicitation/offboarding`, `GET /elicitation/offboarding/{id}`, `.../questions`, `.../responses`).
  - Events: `POST /events/tag-out`, `POST /events/inspection-complete`, `POST /events/alarm`, `POST /events/shift-handover`, `POST /events/deviation-flag`, `POST /events/deviation-flag/{id}/resolve`, `POST /events/plant-state`, `GET /events/plant-state/{site_id}`, `GET /events/{id}`, `POST /events/{id}/ack`, `GET /events/governor-state/{user_id}`.
  - Documents: `GET /documents/{id}/topology`, `POST /documents/{id}/supersede`, `GET /documents/{id}/status`.
  - Audit: `GET /audit-log?entity_type=&entity_id=&limit=`.
  - Health/aggregate: `GET /health/detailed`.
  - OT coverage: `GET /ot/coverage/{asset_id}` (via a FastAPI passthrough to the Go connector — the frontend must not call the Go service directly; add the passthrough if it does not exist) for the instrumentation coverage indicator (Task 15).
- Add corresponding interfaces to `src/lib/types.ts`: `SlaReport`, `MocItem`, `CircuitBreakerState`, `ModelGateResult`, `ValidationCorpusStats`, `BlastRadiusReport`, `Annotation`, `AnnotationStats`, `ElicitationQuestion`, `ElicitationSession`, `OffboardingProgramme`, `OperationalEvent`, `PlantState`, `TopologyGraph`, `AuditLogEntry`, `HealthDetailed`. Mirror the exact backend Pydantic shapes in `backend/api/models/`.
- Keep write helpers (`postJson`) role-agnostic; role gating lives in the UI (Task 2).

**Test:** `npx tsc --noEmit` passes; each new fetcher, called from a scratch page against the running backend, returns `source: "live"` for a seeded entity and `source: "demo"` when the container is stopped.

---

## Task 2: Auth hardening + full role model

**Layer:** 12 (trust) · **Objective:** Close the SSR auth gap and expand role gating to every role the OPA policy defines, so the interface reflects real authority rather than the dev bypass.

- `src/lib/auth.ts`: add a `refreshOn401` wrapper — on any `401` from `postJson`/`getJson`, call `POST /auth/refresh` once, retry, else `logout()` → `/login`.
- SSR reads: server components currently rely on the backend dev-bypass. Add a `getServerToken()` path (read the token from a cookie mirror of `localStorage`) so SSR fetches carry `Authorization` when auth hardening is enabled. `ponytail:` keep the dev-bypass default for demo; gate the cookie path behind an env flag (`NEXT_PUBLIC_AUTH_STRICT`).
- `src/components/use-role.ts`: extend `Role` handling to the full set — `admin`, `engineer`, `reliability`, `field_worker`, and add `compliance`/`quality` if present in `GET /auth/me`. Export `PROMOTE_ROLES`, `RESOLVE_ROLES`, `ADMIN_ROLES`, `FIELD_ROLES`.
- `app-shell.tsx`: nav groups gate per persona — field workers see the field/operate set only; reliability/engineer see the desktop workspace; compliance sees the cockpit; admin sees everything including model-gate and plant-state controls.

**Test:** Log in as each seeded user (`field_worker`, `engineer`, `admin`); verify the nav renders exactly the routes that role may use; force an expired token, verify one silent refresh then graceful redirect on repeat failure.

---

## Task 3: Global phase indicator, source honesty, and governor surface

**Layer:** 8, 12 · **Objective:** Make the trust arc and data provenance visible everywhere — the architecture's phased-deployment thesis is currently invisible to users.

- Add `PhaseBadge` to `ui.tsx`: reads deployment phase (`NEXT_PUBLIC_KAIROS_PHASE`, default `3` for demo) and renders `Phase 1 · Retrieval` / `Phase 2 · Assisted` / `Phase 3 · Proactive`. Placed in the app-shell header. Features that are phase-gated read the same value.
- Add a persistent `DemoDataChip` pattern: any page whose fetch returned `source: "demo"` shows a small "Demo data" chip in the header region (the honest-badge rule already in `api.ts`).
- Add a governor status pill to the shell: consume `GET /events/governor-state/{user_id}` (or the `governor_state` block already returned by `GET /briefs`), showing `push_count_last_hour / ceiling` and a `suppressed` state color.

**Test:** Toggle `NEXT_PUBLIC_KAIROS_PHASE`; verify the badge and any phase-gated feature flip. Stop the backend; verify every page shows the demo chip. Drive briefs past the ceiling; verify the governor pill turns `suppressed`.

---

## Task 4: Extend the shared primitive library

**Layer:** 12 (design system) · **Objective:** Add the reusable primitives every later task needs, grounded in the `DESIGN.md` refero map, so no task re-styles ad hoc.

- Add to `src/components/ui.tsx` (or split into `ui/` if it grows past ~250 lines):
  - `KpiCard` — mono numeral + label + optional threshold line (refero: Axiom/Resend). Pure CSS.
  - `DataTable` — dense rows, status badges, overflow menu, empty state (refero: Linear/Hashnode).
  - `FilterTabs` — segmented control for list filtering (briefs, governance, documents).
  - `Timeline` — vertical event spine with time gutter (refero: Sentry trace / n8n). Pure SVG/CSS.
  - `EvidenceLineage` — collapsible provenance panel: source chips → authority badge → vault link → audit entries.
  - `ConfidenceMeter` — 0–1 bar with verified/caution/danger banding.
  - `RefusalCard` — the safety-critical explicit-refusal presentation (danger tone, "returned sources directly", escalation line).
  - `EmptyState` — icon + message + optional action, used wherever live data is empty and no fixture applies.
- Each primitive: light+dark from tokens only, visible focus, `aria` roles. No new dependency.

**Test:** Render a Storybook-less demo route `/dev/primitives` (dev-only, deleted before commit) showing every primitive in light and dark; confirm tokens drive both palettes and keyboard focus is visible.

---

# Group B — Field / Point-of-Action Interface (Layer 12 mobile, Layers 8/9/3)

This is the largest gap and the architectural heart of Kairos: knowledge delivered at the kairos moment, on any device, in field conditions.

## Task 5: Field-mode responsive shell + point-of-action layout

**Layer:** 12 · **Objective:** A mobile-first surface built for a technician standing at an asset — single-handed, sunlight-legible, no menu-diving to reach an urgent answer.

- Add a `field` layout variant to `app-shell.tsx`: on small viewports (and when role is `field_worker`), replace the sidebar with a bottom tab bar (Briefs · Copilot · Scan/Voice · Me) — thumb-reachable, ≥44px targets.
- Add a "sunlight" high-contrast mode: a third `data-contrast="high"` attribute on `<html>` that raises token contrast (darker ink, stronger borders, brighter accent) without changing layout — one UI, extra palette. Toggle in `theme-toggle.tsx`, persisted in `localStorage`.
- Brief-first reading pattern: key finding in the first two lines, detail below (already the brief format; enforce it in `brief-card.tsx`/`brief-detail.tsx` typography).
- Route group `src/app/(app)/field/` for capture surfaces (voice, deviation, elicitation) so they share the field chrome.

**Test:** In device emulation (375px), verify one-handed reach of every primary action, contrast toggle raises legibility without reflow, and a brief's key finding is readable without scrolling.

---

## Task 6: Brief inbox refinement (governor, priority, freeze, cooldown)

**Layer:** 8 · **Objective:** Make the inbox express the full Layer 8 delivery model — priority order, EEMUA governor state, frozen briefs, cool-down.

- `src/app/(app)/briefs/page.tsx` + `brief-inbox.tsx`: group by priority (PTW-critical → safety-critical WO → recurring → normal), each group a labeled section; `FilterTabs` for `All / Unacknowledged / Critical`.
- Render the top-level `governor_state`, `suppressed_count`, and `next_delivery_allowed_at` from `BriefsResponse` as a banner: "N briefs held — governor at push_count/ceiling, next delivery HH:MM".
- Frozen briefs (`frozen: true`, `freeze_reason`) render with a distinct locked treatment and a link to the deviation flag that caused the freeze (Task 10).
- Cool-down: if a brief is the newer of a same-asset pair inside the 4h window, show a subtle "recent brief for this asset" note.

**Test:** Seed briefs across all priorities + one frozen; verify grouping order, governor banner math matches the response, frozen brief shows locked state, PTW brief never appears suppressed.

---

## Task 7: Brief detail + PTW dual sign-off flow

**Layer:** 8 · **Objective:** Implement the highest-leverage safety interaction — the PTW brief with mandatory dual acknowledgment and cryptographic evidence lineage (Flow B).

- `src/app/(app)/briefs/[id]/page.tsx` + `brief-detail.tsx`:
  - Standard briefs: show headline, body, action items, warnings, `sources[]` (each with `AuthorityBadge`, `SourceChip`, vault link, quarantine flag), then the ack + feedback form (`POST /briefs/{id}/ack`, `POST /briefs/{id}/feedback`).
  - PTW briefs (`requires_countersignature: true`): two-step gate — (a) issuing engineer acknowledges brief content, (b) Shift Lead countersignature confirming isolation strategy. The brief is not "delivered/acknowledged" until both are captured. Surface the isolation sequence, per-device inspection status, and the quarantined deviation flag (e.g. PG-18) marked explicitly unverified.
  - Render `EvidenceLineage` for the full "what knowledge was shown, when, to whom" trail; display the cryptographic-signature confirmation returned by the ack endpoint.
- Safety-critical styling: danger accents, no dismiss-without-ack, feedback chips (Accurate / Missing Context / Incorrect) per the Phase 2 feedback contract.

**Test:** Open a PTW brief; verify ack alone does not mark it delivered until countersignature; verify both signatures show in the lineage; verify a normal brief acks in one step; verify `incorrect` feedback posts and triggers the source re-check.

---

## Task 8: Elicitation micro-interview UI

**Layer:** 9 · **Objective:** Let a technician answer graph-derived micro-interview questions at work-order closeout in under two minutes.

- Route `src/app/(app)/field/elicitation/[workOrderId]/page.tsx`: fetch questions via `GET /elicitation/{wo}/questions`; render 3–5 questions — multiple-choice where the backend supplies options, short free-text otherwise; show the graph-derived context line for each ("previous 2 failures attributed to lubrication…").
- Submit via `POST /elicitation/{wo}/responses`; on success show a confirmation that the response entered quarantine (non-canonical) and thank the user.
- Trigger surface: where a work order is shown as closed with elicitation pending, deep-link into this page (the backend decides trigger conditions via `POST /elicitation/trigger`).
- Keep it field-friendly: one question per screen on mobile, progress dots, large tap targets.

**Test:** Trigger elicitation for a rare failure code; verify questions reference specific asset history; submit; verify a `quarantine_items` row with `input_type='elicitation_response'` and preserved `session_context`.

---

## Task 8b: Off-boarding knowledge-transfer interview UI

**Layer:** 9 · **Flow:** D · **Objective:** The dedicated surface that drives Flow D — a retiring expert completes a scheduled series of graph-derived knowledge-transfer sessions (the architecture describes ~6 sessions over 10 weeks, each focused on a specific equipment family/failure mode). Task 1 wires the endpoints and Task 22 reviews the responses; this task is the missing page that conducts the sessions.

- **Programme list** — route `src/app/(app)/(desktop)/offboarding/page.tsx` (role-gated `engineer`/`admin`): `GET /elicitation/offboarding` → active programmes with personnel, retirement date, and completion percentage (sessions completed / total). This is a desktop surface per the architecture ("conducted through the desktop interface with voice input option"), not a field surface.
- **Programme detail** — `.../offboarding/[sessionId]/page.tsx`: `GET /elicitation/offboarding/{id}` → the six session items, each with its equipment family, focus failure modes, scheduled date, and status (`pending` / `questions_ready` / `completed`).
- **Session interview** — for a `questions_ready` session: `GET /elicitation/offboarding/{id}/questions` renders the graph-derived questions with the "here's what we know / here's the gap" context the architecture specifies; answer via free-text or MCQ with the `VoiceRecorder` (Task 9) as an input option for hands-free response; submit via `POST /elicitation/offboarding/{id}/responses`. On submit, confirm the response entered quarantine with full session context and advance the session status.
- **Create programme** (admin): `POST /elicitation/offboarding` with `{personnel_id, personnel_email, retirement_date}`; explain that the system auto-selects the top equipment families by that person's work-order density.
- **Coverage tie-in:** link each programme to the knowledge-coverage KPI (Task 32) so leadership sees which retiring-expert gaps are being closed.

**Test:** Create a programme for a seeded engineer; verify 6 session items with spaced dates and distinct equipment families; open a `questions_ready` session and verify graph-derived questions render; submit an answer (typed and via voice); verify a `quarantine_items` row with `input_type='offboarding_response'` and full `session_context`, and the session advances to `completed`.

---

## Task 9: Voice note capture

**Layer:** 3, 9 · **Objective:** Hands-light tacit-knowledge capture — record a voice note in the field, submit for Whisper transcription + NER → quarantine.

- Add `VoiceRecorder` component using the native `MediaRecorder` API (no dependency): record/stop/playback/re-record, waveform or timer, size guard.
- Route `src/app/(app)/field/voice/[workOrderId]/page.tsx` (and an entry from elicitation): submit the blob to `POST /elicitation/{wo}/voice` as multipart with `submitted_by`; show the returned `202 + task_id` and a transcription-pending state; poll or show "processing — will appear in quarantine".
- Permission + fallback: if `getUserMedia` is denied, fall back to file-upload of an audio file.

**Test:** Record a short clip (or upload `fixtures/test.wav` equivalent), submit; verify `202` with `task_id`; after the Celery task, verify a `quarantine_items` row with `input_type='voice_note'`, transcript text, and the work order id.

---

## Task 10: Physical deviation flag (field freeze)

**Layer:** 6, 8 · **Objective:** A field tech flags a physical deviation from the P&ID; the UI raises it and reflects the downstream brief freeze until an engineer resolves it (edge case: undocumented modification).

- Route `src/app/(app)/field/deviation/page.tsx`: form `{asset_id, description, affected_topology_path}` → `POST /events/deviation-flag`; confirmation explains that dependent briefs are now frozen.
- Reflect freeze state in the brief inbox/detail (Task 6) — affected briefs show `frozen` with reason "Physical deviation flag pending resolution".
- Engineer resolution surface (desktop, role-gated `engineer`/`admin`): from the quarantine review (Task 22) or a dedicated action, `POST /events/deviation-flag/{id}/resolve` with promote/dispute + optional MoC-warranted flag; on resolve, briefs return to normal delivery.

**Test:** Raise a deviation for P-101; verify affected briefs show frozen; resolve as engineer; verify briefs return to normal and, if MoC-warranted, an MoC item appears (Task 27).

---

## Task 11: Offline mode + background sync

**Layer:** 12 · **Objective:** The field app must function without connectivity and sync when it returns — an explicit architecture hard requirement for field use.

- Add a Service Worker (native, via `next-pwa`-free manual registration or a `public/sw.js`): cache the app shell and the most recent briefs/assets read (stale-while-revalidate). `ponytail:` cache read-briefs + asset detail + the current elicitation questions only — not the whole corpus.
- Write queue: acks, feedback, elicitation responses, deviation flags, and voice submissions made offline are queued in IndexedDB and replayed on `online` event; show a "queued — will sync" state and a sync indicator in the shell.
- Conflict handling: replays are idempotent (backend ack/dedup already idempotent); on replay failure, surface the item for manual retry.

**Test:** Load `/briefs`, go offline (DevTools), open a cached brief, ack it (queues), submit a queued elicitation response; go online; verify both replay and the server reflects them; verify uncached routes show a clean offline empty state, not a crash.

---

## Task 12: Voice search input for Copilot

**Layer:** 12 · **Objective:** Hands-free querying — speak a question into the copilot.

- Reuse `VoiceRecorder` (Task 9) in the copilot composer, or the native Web Speech API (`SpeechRecognition`) where available for instant transcription; fall back to recording → the same voice transcription path, populating the query box.
- `ponytail:` if `SpeechRecognition` is unavailable, degrade to the record→transcribe path already built; do not add a cloud STT dependency to the frontend.

**Test:** In a supporting browser, dictate a query; verify it populates the composer and runs the normal synthesize path; verify graceful fallback where the API is absent.

---

# Group C — Copilot / Retrieval & Synthesis (Layers 11, 3, 0)

## Task 13: Copilot depth — citations, confidence, refusal, time-travel

**Layer:** 11 · **Objective:** Make the copilot express the full Layer 11 synthesis contract — mandatory source citation, confidence, explicit safety-critical refusal, quarantine-dependency flagging, and time-travel queries.

- `src/app/(app)/copilot/page.tsx`:
  - Every answer renders its `sources[]` as `SourceChip` + `AuthorityBadge` + vault link; a `ConfidenceMeter` shows the confidence score.
  - Safety-critical refusal: when `refused: true`, render `RefusalCard` (Task 4) — no synthesized prose, the returned source documents shown directly, the specific evidence gap named, and an "escalate to [authority]" line. Never render a hedged answer in this state.
  - Quarantine dependency: if any source `is_quarantine`, flag the answer as "draws on unverified field input" with the caution treatment.
  - Uncertainty (non-safety): when confidence is below threshold but not refused, show "what is known / not known / what would confirm it / where to escalate" rather than a confident answer.
  - `as_of` time-travel control: a date picker that passes `as_of` to the query so the user can ask "what did we know on <date>"; results reflect validity windows.
  - Phase gate: in Phase 1 the composer shows retrieval results only (no synthesis); synthesis UI activates in Phase 2+ (reads `PhaseBadge` value).
- Keep the existing empty-live-answer → curated fixture fallback, but never let a fixture mask a genuine refusal.

**Test:** Ask a safety-critical query with weak evidence → verify `RefusalCard` + sources, no prose; ask a normal query → verify citations + confidence; set `as_of` before a document's ingestion → verify it drops out; flip phase to 1 → verify synthesis UI hides.

---

## Task 14: Active Learning Annotation Interface

**Layer:** 3, 0 · **Objective:** Turn normal search into annotation — one-tap confirm/correct/delete of low-confidence entities inline in results, feeding `ner_annotations` and the Layer 0 corpus.

- In copilot/search results, render extracted entities as chips; low-confidence ones (below threshold) get an inline affordance: confirm (✓), correct (edit type), delete (✕).
- `POST /annotations` on each action with `{document_id, entity_text, entity_type, corrected_type?, is_correct, span_start, span_end}`; optimistic UI update; on `is_correct=false` the linked quarantine item confidence drops server-side (no client action needed).
- Surface `GET /annotations/stats` (`{total, corrections_this_week, top_corrected_entity_types}`) on the model-health/compliance dashboard (Task 30) and optionally a small "you've improved N extractions" nudge (the trust-building mechanism).
- `GET /annotations?document_id=` powers a document's highlighted-entity view (Task 20 detail).

**Test:** Run a search returning a low-confidence entity; correct its type; verify a `ner_annotations` row and the linked quarantine item's confidence updated; verify the stats endpoint count increments.

---

# Group D — Engineer & Reliability Desktop Workspace (Layer 12; Layers 4/2/7/11)

## Task 15: Temporal knowledge graph visualization

**Layer:** 4 · **Objective:** Render the asset-centric temporal graph in the browser — the depth of the knowledge graph made visible for planners and reliability engineers.

- Add **React Flow** (the one pre-approved dependency; lighter and more controllable than Neovis for our JSON-from-API model). Register in `package.json`; rebuild the frontend image.
- Route `src/app/(app)/graph/page.tsx` and an embedded panel on `/assets/[id]`: build nodes/edges from `GET /assets/{id}/knowledge` (facts = edges + target nodes). Node types colored by kind (Asset/Event/Document/Concept/Person/Org); edges colored by authority level (L1 verified-green → L5 caution-orange) and styled by verification status (solid=verified, dashed=unverified, red=disputed, faded=superseded).
- Interaction: click a node → side panel with its facts, sources, and vault links; click an edge → its six properties (`valid_from/to`, `authority_level`, `document_id`, `confidence`, `verification_status`).
- `ponytail:` render the neighborhood of the selected asset (1–2 hops), not the whole graph — depth-limit matches the backend's traversal policy; full-graph exploration is a later upgrade.
- **Instrumentation coverage indicator (Layer 5):** on the asset detail/graph side panel, show whether the asset has direct sensor coverage vs. only macro-level monitoring, from the Go connector's `GET /ot/coverage/{asset_id}` (surface it via a FastAPI passthrough added in Task 1). This is the visible expression of the instrumentation coverage map that Layer 10 attribution depends on — an engineer can see at a glance whether a failure mode is directly instrumented or must rely on human-verified closeout. `ponytail:` read-only indicator; managing the map is out of MVP scope.

**Test:** Open `/graph` for an asset with seeded knowledge; verify nodes/edges render, authority coloring is correct, edge inspector shows all six properties, and superseded edges are visually distinct.

---

## Task 16: Time-travel timeline / as-of view

**Layer:** 4 · **Objective:** Visualize validity windows and let the user scrub knowledge state to any historical moment (time-travel RCA).

- On `/graph` and `/assets/[id]`: add an `as_of` slider/date control that re-queries `GET /assets/{id}/knowledge?as_of=` and re-renders the graph/knowledge list for that instant — edges whose window doesn't contain `as_of` drop out.
- Add a `Timeline` (Task 4) view of an asset's edges as horizontal validity bars (from `valid_from` to `valid_to`, open windows using the 9999 sentinel rendered as "current"), so supersession is legible over time.
- Wire to the copilot `as_of` control (Task 13) for consistency.

**Test:** For an asset with a superseded pressure-limit edge, scrub `as_of` before and after the supersession date; verify the old value shows then the new; verify the timeline bars match the windows.

---

## Task 17: P&ID topology viewer

**Layer:** 3 · **Objective:** Render engineering-drawing topology (equipment nodes, flow connections, valves, instrumentation loops, isolation boundaries) and support element-by-element verification — never destroy spatial relationships with plain text.

- Route `src/app/(app)/documents/[id]/topology` (only for `document_type='pid_drawing'`): fetch `GET /documents/{id}/topology` (topology JSON from the Path B vision model; show a demo chip when `topology_source: "demo_fixture"`) and render with React Flow (reuse Task 15 canvas) — equipment nodes, connections as edges, isolation boundary as a highlighted region, instrumentation loops labeled.
- Verification UI: each element shows `verification_status`; unverified elements are highlighted for engineer confirmation (route through the quarantine/deviation queue — canonical promotion is gated by Layer 7, Task 22). Show the source drawing image alongside where available.
- Non-PID documents: the topology tab is hidden (endpoint 404s by design).

**Test:** Ingest a `pid_drawing`; open its topology tab; verify equipment/valves/isolation-boundary render from the topology JSON, unverified elements are highlighted, and a non-PID document shows no topology tab.

---

## Task 18: Blast-radius visualization

**Layer:** 4, 7 · **Objective:** When a document is superseded, show everything downstream it contaminates — make silent knowledge decay visible (Flow C).

- On `/documents/[id]` and the conflict/MoC surfaces: a "Blast radius" panel from `GET /governance/blast-radius/{document_id}` — the affected procedures/inspections/facts as a list and a small radial/tree diagram (React Flow), each item linking to its own detail with a "flagged for review" badge.
- Integrate with supersede (Task 20): after a supersede action, surface the resulting blast-radius report and the count of items flagged for review.

**Test:** Supersede a document that other facts reference; open its blast-radius panel; verify the affected downstream items are listed and marked for review, matching the backend report.

---

## Task 19: RCA assembly workspace

**Layer:** 11 · **Objective:** The engineer's RCA workbench — event timeline, evidence-weighted hypotheses, supporting documents, per-hypothesis safety refusal (Layer 11 RCA pack output type).

- Refine `src/app/(app)/rca/page.tsx`: inputs `{asset_id, incident_date (required), failure_code, include_quarantine}`; the `incident_date` field fixes the known 422/500 UX by always sending a valid ISO date.
- Render the response with `Timeline` (chronological events, each with source), hypotheses ranked by `evidence_weight` (bar + sources as `SourceChip`), and supporting documents with authority badges.
- Per-hypothesis safety refusal: hypotheses flagged `refused` render via `RefusalCard` with sources returned directly, not a synthesized claim.
- Keep the live→fixture fallback for backend 5xx, but show a clear "synthesis unavailable — raw timeline shown" state when `synthesis_available=false` rather than silently swapping to fixture.

**Test:** Generate an RCA for a seeded asset; verify timeline is chronological, hypotheses carry evidence weights and valid source ids, a safety-critical low-confidence hypothesis refuses; verify the incident_date contract no longer 422s.

---

## Task 20: Document comparison + supersede-chain viewer

**Layer:** 2 · **Objective:** Make the immutable vault's version chain legible — compare versions, walk the supersede chain, trigger supersession.

- `src/app/(app)/documents/[id]/page.tsx`: show full metadata (SHA-256, ingested_at/by, source_system, status, `version_chain`, asset links, OCR confidence), the vault link, and the highlighted-entity view (from `GET /annotations?document_id=`, Task 14).
- Supersede chain: render the chain (active ← superseded ← …) as a `Timeline`; each node links to its version. A superseded document is clearly labeled and never presented as current.
- Supersede action (role-gated engineer/admin): `POST /documents/{id}/supersede` with the new document; on success show the blast-radius report (Task 18) and, if any affected edge is authority ≤3, the auto-created MoC (Task 27).
- Side-by-side compare: for two versions, show a simple text/metadata diff. `ponytail:` metadata + extracted-fact diff only for the MVP; full visual PDF diff is a later upgrade.

**Test:** Open a document with a version chain; verify the chain renders and superseded versions are labeled; supersede a document; verify the blast-radius report and (if applicable) MoC creation surface.

---

## Task 20b: Document ingestion / upload UI

**Layer:** 2, 3 · **Flow:** C · **PS pillar:** Universal Document Ingestion · **Objective:** Provide the entry point of the whole platform — getting a document *into* the vault through the UI. The app can view documents and their pipeline artifacts but currently has no way to ingest one; this is the missing front door to Flow C and the Problem Statement's first pillar.

- Route `src/app/(app)/(desktop)/documents/ingest/page.tsx` (role-gated `engineer`/`admin`/document-control): drag-and-drop or file-picker upload; capture `document_type` (oem_manual / procedure / inspection_report / ptw / shift_log / regulation / pid_drawing), optional `asset_id` link, `source_system`, and `authority_level`.
- Submit multipart to `POST /documents/ingest`; surface the returned `document_id` and the SHA-256 dedup result (a re-uploaded identical file returns the existing id — show "already ingested" rather than a duplicate).
- **Pipeline status:** poll `GET /documents/{id}/status` and render the Temporal pipeline stages (queued → ocr → ner → graph_linking → indexing → complete, or `review_required` on low confidence) using the `Timeline` primitive; link to the resulting document detail (Task 20) and, for `pid_drawing`, the topology view (Task 17).
- Low-confidence / review-required outcomes link to the quarantine queue (Task 22). Multi-file batch upload is fine but each file is its own pipeline row.
- `ponytail:` no client-side OCR/preview — upload raw bytes and let the backend pipeline own extraction, exactly as the vault-immutability rule requires (no preprocessing before storage).

**Test:** Upload a PDF; verify a `document_id` returns and the status timeline advances past `queued`; re-upload the same file and verify the dedup "already ingested" path; upload a `pid_drawing` and verify it links to the topology view; confirm the raw file lands in Supabase Storage unchanged.

---

## Task 20c: MDM asset identity confirmation / bootstrap UI

**Layer:** 1 · **Objective:** Give Layer 1's "no AI-invented identities" governance principle a frontend expression — a surface where a qualified asset authority confirms a provisional or orphaned asset identity before any extracted knowledge links to it. The backend hard-requires `identity_confirmed_by` on asset creation; today nothing in the UI can supply it. `ponytail:` scoped as an admin/deployment-time surface, not a field flow — the leaner MVP build is a confirmation list, not a full MDM editor.

- Route `src/app/(app)/(desktop)/assets/bootstrap/page.tsx` (role-gated `admin`): list provisional/unconfirmed asset holding nodes (assets lacking `identity_confirmed_by`, plus unresolved tag aliases with `confirmed=false` from `asset_alias_map`).
- Confirm action: `POST /assets` (or the confirmation endpoint) supplying `identity_confirmed_by = current_user.user_id` — deterministic human confirmation, never AI-inferred; on confirm the asset becomes canonical and linkable.
- Alias resolution: confirm or reject proposed alias→canonical mappings; a confirmed alias becomes searchable across all its naming variants (the alias resolver's human-in-the-loop step).
- Surface the rule in copy: knowledge that cannot link to a confirmed identity stays in quarantine under a provisional node, it is never fabricated.

**Test:** With an unconfirmed asset present, open the bootstrap page; confirm its identity as admin; verify `identity_confirmed_by` is set and the asset now appears canonical in `/assets`; confirm a pending alias and verify search resolves the variant to the canonical id; verify a non-admin cannot access the surface.

---

## Task 21: Conflict resolution workflow (dual-track)

**Layer:** 7 · **Objective:** Present knowledge conflicts with their track, authority comparison, MoC warning banners, and the resolve action — the dual-track governance made operable (Flow C).

- Refine `src/app/(app)/governance/conflicts/page.tsx` + detail: `DataTable` of conflicts with `track` (administrative/engineering), `parameter`, both sources with `AuthorityBadge`, `severity`, `status`, and SLA countdown (`sla_due_at`, `is_overdue`).
- Detail view: side-by-side `source_a` vs `source_b` with authority levels and dates; for engineering-track conflicts pending MoC, a prominent warning banner naming the pending MoC number (links to Task 27).
- Resolve action (role-gated engineer/admin) `POST /governance/conflicts/{id}/resolve`: administrative conflicts resolve inline (data-steward decision + note); engineering conflicts show that resolution flows through MoC and cannot be closed here directly (matches backend rejection of engineering-track direct resolve).
- Junk-data hygiene: filter obvious test rows (`ASSET-TEST-*`, `ASSET-EV-*`, `ASSET-DEDUP-*`) from the default view behind a "show test data" toggle so the dual-track thesis reads cleanly in demo.

**Test:** Open conflicts; verify track badges and authority comparison; attempt to resolve an engineering-track conflict inline → verify it's blocked with the MoC explanation; resolve an administrative conflict → verify status updates and audit entry.

---

## Task 22: Quarantine review queue

**Layer:** 6, 9 · **Objective:** The reviewer's queue — promote/dispute/archive unverified items, with the elicitation/offboarding/voice session context shown so the reviewer knows what was asked.

- Refine `src/app/(app)/governance/quarantine/page.tsx`: `DataTable` grouped/filterable by `input_type` (`field_observation`, `voice_note`, `elicitation_response`, `offboarding_response`, `deviation_flag`) and by equipment class; each row shows content, submitter, SLA countdown, `is_overdue`.
- Detail: for elicitation/offboarding/voice items, render the full `session_context` (questions + answers, work order, equipment family) via `EvidenceLineage`; for voice, link the transcript.
- Actions (role-gated per `PROMOTE_ROLES`): `POST .../promote` (with authority-level assignment + relationship type — this promotes to canonical and can create the Layer 0 corpus row), `POST .../dispute` (reason), archive. Every promotion shows the "one-way gate — human action only" affordance; no bulk auto-promote.
- **Request more information** (Layer 6 fourth review action): a reviewer can send an item back for clarification rather than promote/dispute/archive — e.g. re-trigger a targeted elicitation question or attach a reviewer note. `ponytail:` the backend currently exposes promote/dispute only, so ship this as a reviewer-note + optional elicitation re-trigger (Task 8) against existing endpoints; wire to a dedicated `request_info` action if/when the backend adds one. Flagged in the Demo-vs-Full table as backend-gated.
- Deviation-flag items link to the resolve action (Task 10).

**Test:** Open quarantine; filter by `voice_note`; open an elicitation item and verify questions+answers render; promote an item as engineer → verify canonical edge created and a `validation_corpus` row; dispute another → verify status change; verify field_worker sees read-only.

---

## Task 23: Audit trail / evidence lineage viewer

**Layer:** 7, 8 · **Objective:** Surface the immutable audit log — what knowledge was delivered, when, to whom, and every governance decision (legal defensibility).

- Route `src/app/(app)/audit/page.tsx`: `GET /audit-log?entity_type=&entity_id=&limit=` with filters (entity type, entity id, action, performed_by); render chronological entries (note: backend column is `timestamp`, order on that).
- Embed `EvidenceLineage` on brief detail, quarantine detail, conflict detail, and document detail — each pulls the audit entries for that entity so provenance is one click away.
- Actions surfaced: `synthesis`, `brief_acknowledged`, `sla_escalated`, `model_gate_result`, `timestamp_drift_detected`, promotions, resolutions.
- **Timestamp-drift review (Layer 4):** `timestamp_drift_detected` entries are not just logged — add a filtered "drift review" view that lists documents flagged for clock-drift beyond tolerance, showing source vs. ingested timestamps and the drift magnitude, so a reviewer can see which validity windows were normalized to `ingested_at`. `ponytail:` a filtered audit view for the MVP (the backend already normalizes automatically); a full accept/adjust workflow is a later upgrade.

**Test:** Perform an asset write and a brief ack; open `/audit` filtered to those entities; verify chronological entries with actor and action; verify the lineage panel on the brief shows its ack entry.

---

# Group E — Quality & Compliance Cockpit (Layer 12; Layers 7, 11)

## Task 24: Compliance gap dashboard depth

**Layer:** 11 · **Objective:** The quality manager's continuous compliance view — regulatory framework mapped against current procedures/equipment state, gaps by severity, remediation, with the false-negative posture the architecture demands.

- Refine `src/app/(app)/compliance/page.tsx`: `KpiCard` row (total gaps, by severity critical/major/minor, by framework); `DataTable` of gaps with `framework`, `clause_id`, `requirement_text`, `applies_to`, `asset_id`, `severity`, and a suggested-remediation column.
- `FilterTabs` by framework (OISD / ISO 45001 / PESO / …) and by severity; `GET /compliance/gaps?framework=` and `GET /compliance/dashboard`.
- False-negative framing (honest scope): a persistent note that this is high-recall audit-prep acceleration, that clearances for safety-critical clauses require human sign-off, and that clearances are blocked when evidence confidence is below threshold — never present a cleared clause as automated compliance.
- Empty-live handling: if live gaps are empty, show the curated fixture with the demo chip (existing pattern), not a blank board.

**Test:** Open compliance; verify KPI math matches the dashboard endpoint; filter by framework and severity; verify the human-sign-off/false-negative note is present; verify empty live gaps fall back to fixture with the demo chip.

---

## Task 25: Evidence / audit-pack assembly

**Layer:** 11 · **Objective:** Assemble an audit evidence package organized by regulatory clause, with mandatory human sign-off — the audit-preparation-acceleration deliverable.

- Route `src/app/(app)/compliance/audit-pack/page.tsx`: pick a framework → `GET /compliance/audit-pack?framework=`; render the canonical `evidence[]` records by `clause_id`, including `document_id`, status, and `clearance_blocked`. Do not invent document groups, confidence, or a client-side clearance action.
- Export affordance: a print/PDF-friendly layout (CSS print styles) for the desk-review pack. `ponytail:` browser print-to-PDF for the MVP; a server-generated signed pack is a later upgrade.
- Sign-off: a per-clause "reviewed by" capture (writes an audit-log entry) so the pack carries human attestation, not automated compliance.

**Test:** Generate an audit pack for a framework; verify evidence records and blocked clearances render correctly; verify print layout is clean. A signed attestation requires a dedicated backend endpoint.

---

## Task 26: Non-conformance tracking + inspection record management

**Layer:** 7, 11 · **Objective:** Track quality non-conformances linked to root-cause history, and manage inspection records — the remaining two cockpit responsibilities.

- Non-conformance view: derive from open conflicts + failed inspections + disputed items; each NC links to its RCA (Task 19) and the originating event/document. `ponytail:` compose from existing endpoints (conflicts, events with `result='failed'`, quarantine disputes) — no new backend needed; if a dedicated NC endpoint is later added, swap the source.
- Inspection records: list inspection events (`event_type='inspection_complete'`) with result, findings, performed_by, linked document; surface interval-deadline warnings when an inspection interval is approaching (from graph/knowledge).
- Link inspection failures to the brief they triggered and to any compliance gap they open.

**Test:** Create a failed inspection event; verify it appears as a non-conformance linked to its RCA and to the reliability brief it triggered; verify inspection records list with findings and any interval warning.

---

# Group F — Governance Operations (Layers 7, 0)

## Task 27: MoC workflow UI

**Layer:** 7 · **Objective:** Surface the Management-of-Change items Kairos auto-drafts on engineering conflicts/supersessions, and the warning banners that ride on affected facts until sign-off (Flow C). `ponytail:` a manual approval UI stands in for the full webhook cycle, per the architecture's mock note.

- Route `src/app/(app)/governance/moc/page.tsx` + `[id]`: `GET /governance/moc` list (status, affected asset/parameter, conflicting sources with authority, blast-radius count, created_at); detail shows the auto-drafted EWR content, both sources, and the blast-radius list (Task 18).
- Warning-banner integration: any fact/conflict/asset touched by a pending MoC shows a banner naming the MoC number and linking here (copilot answers, conflict detail, asset detail).
- Manual resolution (admin, demo stand-in for the signed webhook): a control that simulates the signed MoC returning — on confirm, the UI reflects the graph update (old edge window closed, new edge verified, banners cleared). Wire to whatever endpoint the backend exposes for this; if none, present it read-only and note the webhook is the production path.

**Test:** Create an engineering conflict/supersession that drafts an MoC; verify it appears in the MoC list with blast radius; verify affected surfaces show the pending-MoC banner; simulate resolution; verify banners clear.

---

## Task 28: SLA report page

**Layer:** 7 · **Objective:** Surface governance SLA state and escalations — overdue conflicts and quarantine items with countdowns (the case-management operating model).

- Route `src/app/(app)/governance/sla/page.tsx`: `GET /governance/sla-report` → `KpiCard`s (on-time vs overdue for conflicts and quarantine) + `DataTable`s of `overdue_conflicts` (track, asset, overdue_by_hours, escalated) and `overdue_quarantine`.
- Render SLA countdown indicators wherever `sla_due_at`/`is_overdue` appear (conflicts, quarantine — Tasks 21/22): green → amber → red as due time approaches, red past due.
- Note that hitting this page runs the lazy escalation check server-side (escalations get written on read) — reflect newly-escalated items.

**Test:** Insert a conflict, force `sla_due_at` into the past; load the SLA page; verify it appears in `overdue_conflicts`, shows escalated, and the audit log gained an `sla_escalated` entry.

---

## Task 29: SPC circuit-breaker state view

**Layer:** 7 · **Objective:** Show per-asset-class extraction health — where the SPC circuit breaker has halted automated extraction due to override drift.

- Route `src/app/(app)/governance/circuit-breaker/page.tsx`: `GET /governance/circuit-breaker` → per-asset-class cards/table with `status` (ok/halted), `z_score`, `override_count_7d`, `halted_since`; halted classes use the danger treatment and explain "automated extraction paused — routing to human review until retrain + Layer 0 pass".
- Link a halted class to its recent overrides/quarantine rejections that drove the Z-score.

**Test:** Insert enough overrides for one asset class to trip the breaker; load the page; verify that class shows `halted` with its Z-score and halted-since, others show ok.

---

## Task 30: Layer 0 model gate + validation-corpus dashboard

**Layer:** 0 · **Objective:** Make the model-safety plane visible — validation corpus coverage, model-gate history/trend, and (admin) the ability to run the gate.

- Route `src/app/(app)/governance/model-gate/page.tsx`: `GET /governance/validation-corpus/stats` (corpus size by entity type, by asset class, last update) as `KpiCard`s; `GET /governance/model-gate/history` (last 20 runs) as a table + a precision/recall/F1 trend line (`Timeline`/SVG).
- Admin action: `POST /governance/model-gate/run` (role-gated `admin`) → shows the returned `task_id` and a pending state; on completion the new result appears in history with `passed` badge.
- Fold in the annotation stats (Task 14) as the corpus-growth signal.

**Test:** As admin, run the model gate; verify a `task_id` returns and a new history row appears with precision/recall/F1/passed; verify corpus stats reflect promoted items and annotation corrections.

---

# Group G — Project & Procurement Workspace (Layer 12)

## Task 31: Engineering document registry + revision tracking + procurement history

**Layer:** 12 · **Objective:** The project/procurement surface — an engineering document registry with revision tracking, vendor document management, and asset-class failure/maintenance history accessible during procurement decisions.

- Registry mode on `src/app/(app)/documents/page.tsx` (or a `/projects` route): group documents by asset/equipment-class and document type; show revision chains (reuse Task 20 supersede-chain), source system, and vendor/OEM origin; `FilterTabs` by document type and by equipment class.
- Procurement history view: for a chosen equipment class, aggregate failure history and maintenance/work-order records across assets of that class (from `/assets/{id}/knowledge` + events) so a procurement officer evaluating a replacement sees the class's complete failure and maintenance record.
- Vendor document management: filter/group by `source_system`/OEM; surface OEM manuals and bulletins for a class together.
- `ponytail:` compose entirely from existing document/asset/event endpoints; no new backend. A dedicated project-workspace backend is a later upgrade.

**Test:** Open the registry; group by equipment class; verify revision chains render; open procurement history for a class with multiple assets; verify aggregated failure/maintenance history and OEM documents are shown together.

---

# Group H — Management & Cross-Functional Dashboard (Layer 12; scale)

## Task 32: Management overview — live wiring

**Layer:** 12 · **Objective:** Replace the fixture-only overview with an executive KPI view fed by live aggregates — situational awareness without operational detail.

- Refine `src/app/(app)/management/page.tsx`: fan-out fetch (parallel) `GET /health/detailed` (service health cards), `GET /assets/?limit=1` (total assets), `GET /briefs/` (pending + governor), `GET /compliance/dashboard` (gap posture), `GET /governance/conflicts?limit=1` (open conflicts), `GET /governance/quarantine?limit=1` (pending review).
- KPIs: knowledge coverage by asset class (from graph/knowledge counts), unresolved conflicts by track, compliance posture by severity, brief delivery + governor suppression rate, quarantine backlog + SLA breaches.
- **Elicitation participation tracking (Layer 9 edge case):** a KPI card for elicitation/off-boarding participation rate by department/individual — the organizational metric the architecture reports to operations leadership, and the surface that makes a non-participating expert's knowledge gap visible rather than hidden. Sourced from off-boarding programme completion (Task 8b) + elicitation response counts.
- **Outcome-attribution summary (Layer 10/0):** a light admin KPI reflecting the learning loop — counts of recommendations confirmed / degraded / flagged-for-execution-deviation, and briefs marked not-relevant, from the audit-log signal. `ponytail:` summary counts only for the MVP; a full per-recommendation attribution drill-down is a documented cut (deep Layer 10 analytics).
- Each KPI links through to its detail surface. Keep fixture fallback with the demo chip when live aggregates are empty.

**Test:** Load `/management` with the stack up; verify every KPI shows a live number matching its source endpoint and the health cards reflect `GET /health/detailed`; stop one backend service and verify its health card degrades.

---

## Task 33: Cross-site pattern alerts (mock)

**Layer:** 12, scale · **Objective:** Express the enterprise cross-site story — failure patterns detected at one site surfaced as advisories to sister sites, with the PII-redaction guarantee visible. `ponytail:` single-site MVP → this surface is mock/fixture, matching the architecture's explicit scope cut; wire live if a control-plane endpoint later exists.

- Route `src/app/(app)/management/cross-site/page.tsx`: render cross-site advisories (originating site, equipment class, failure mode, sanitized pattern, "relevant to your assets: …") from a fixture that mirrors the intended control-plane shape.
- PII-redaction note: show that only the sanitized technical pattern crosses the boundary (names/shift-ids replaced with role-generalized tokens) — the DPDP Act 2023 guarantee made visible.
- Clearly badge this surface as multi-site (architecture) vs single-site (this deployment).

**Test:** Open the cross-site page; verify advisories render with originating-site attribution and redacted personnel tokens; verify the single-site-scope badge is present.

---

## Task 34: Plant operating-state control

**Layer:** 8 · **Objective:** Let an engineer/admin set the plant operating state (normal/turnaround/shutdown/emergency) that drives governor state-based suppression, and show the current state as an operator banner.

- Route `src/app/(app)/management/plant-state/page.tsx` (role-gated engineer/admin): `GET /events/plant-state/{site_id}` current state; `POST /events/plant-state` to set state + expiry; confirmation explains the suppression consequence.
- Global banner: when state ≠ normal, the app-shell shows a site-wide banner ("Turnaround — only critical briefs are being delivered"), tying to the governor pill (Task 3).

**Test:** Set state to `turnaround`; verify the global banner appears and the briefs governor reflects state-based suppression (only critical briefs delivered); reset to normal; verify the banner clears.

---

# Group I — Operational Event Surfaces (Layer 8)

## Task 35: Event surfaces, acknowledgment, and correlation

**Layer:** 8 · **Objective:** Provide read/ack surfaces for the canonical event sources not yet visible (tag-out, inspection-complete, alarm, shift-handover) and show compound-event correlation.

- Route `src/app/(app)/events/page.tsx` + `[id]`: list `operational_events` (type, subtype, asset, occurred_at, priority) with `FilterTabs` by type; detail shows the event payload, the brief it triggered (if any), and `correlated_event_ids` (compound events) linked together.
- Acknowledge: `POST /events/{id}/ack` where applicable, writing the audit entry.
- Ingestion entry points for demo (role-gated): lightweight forms to POST tag-out / inspection-complete / alarm / shift-handover events so the proactive flows can be demonstrated end-to-end from the UI; each shows the resulting brief.
- Recurring-failure: surface `event_subtype='recurring'` events distinctly and link to the recurring-failure brief.

**Test:** POST a tag-out event from the UI; verify the event appears and its tag-out brief is linked; POST a work order + alarm for one asset within the window; verify the event detail shows `correlated_event_ids`; ack an event and verify the audit entry.

---

# Group J — Cross-Cutting Quality

## Task 36: Accessibility, dark-mode, and responsive sweep

**Layer:** 12 · **Objective:** Enforce the design system's non-negotiables across every screen built above — one UI in two (three, with sunlight) palettes, accessible and responsive.

- One-UI audit: confirm every new component reads colors from tokens only — no hardcoded hex, no separate dark markup; verify light/dark/high-contrast parity screen by screen.
- Accessibility: WCAG AA contrast on all token pairings; visible `:focus-visible` on every interactive element; `aria` roles on tables, dialogs, tabs, live regions for governor/sync status; `prefers-reduced-motion` respected (already global) on any new animation.
- Responsive: every field surface (Group B) verified single-handed at 375px; desktop workspaces (Groups D–H) verified at tablet and desktop widths; no horizontal scroll except intentional graph/timeline canvases.
- Per-page loading skeletons: replace the single shared `loading.tsx` with per-route skeletons where the shape differs (briefs vs graph vs table).
- **Multi-script / multilingual rendering (Layer 3):** the architecture names multi-script perception (Hindi, Hinglish, mixed-script) a core capability — verify entity chips, search results, document text, and NER output render Devanagari and mixed-script content correctly (font stack includes a Unicode fallback, no clipping, correct line-height for tall scripts). Explicit design check, not left to chance.

**Test:** Run an axe/Lighthouse pass on each route (a11y ≥ 95); toggle light/dark/high-contrast on every screen and confirm structural identity; emulate 375px/768px/1280px and confirm layout integrity and focus order.

---

## Non-Negotiable Frontend Constraints (apply to every task)

- **Source citation is mandatory.** Every synthesized answer, brief, and RCA hypothesis shows its `sources[]` with `AuthorityBadge` and a vault link. No claim without provenance.
- **Quarantine is always visually distinct and labeled** "Unverified field input — not reviewed by engineering authority." Answers that depend on quarantined knowledge flag that dependency.
- **Safety-critical = explicit refusal, never a hedged answer.** Use `RefusalCard`; return the source documents directly and name the escalation authority.
- **Degraded-source honesty.** When telemetry/OT context would normally appear but the historian is unavailable, show the explicit notice "Live telemetry is unavailable — analysis is based on documented history only" (Layer 5 / §8 edge case) rather than silently omitting it. Same principle as the demo-data chip: never hide a degraded state.
- **Reuse `ui.tsx` primitives.** No ad-hoc badges/buttons/modals. New shared pieces land in the primitive library (Task 4), grounded in the `DESIGN.md` refero map.
- **One component, two palettes.** Colors come from tokens; never build a "dark version." Sunlight/high-contrast is another palette on the same structure.
- **Every fetch keeps the live→fixture fallback** with an honest `source` badge; a fixture must never mask a genuine refusal or a genuine safety state.
- **SSR-aware `API_BASE`** stays the rule (Docker-internal for server components, host port for browser); pages never hardcode URLs and never call `fetch` outside `api.ts`.
- **Role-gated writes.** `field_worker` is read-only on staff surfaces; promote/resolve/model-gate/plant-state gate on the role sets in `use-role.ts`; the auth guard protects all `(app)` routes.
- **Mobile-first for field surfaces**, desktop-depth for workspaces; both from the same components.
- **No new dependency** unless the task names it. Only React Flow (Task 15) is pre-approved; charts are SVG/CSS, voice is `MediaRecorder`/Web Speech, offline is Service Worker + IndexedDB.
- **`structlog`/print rules are backend-only**; on the frontend, no `console.log` in committed code — use a small dev-guarded logger if needed.
- **Docker is the runtime.** Rebuild `kairos-frontend` only when `package.json` changes; `src/` and `public/` hot-reload via the volume mount.

---

## Demo-vs-Full Scope (deliberate cuts, not gaps)

| Surface | MVP / demo build | Full architecture (upgrade path) |
|---|---|---|
| Graph visualization (Task 15) | 1–2 hop neighborhood, React Flow | Full-graph exploration, server-side layout for tens of millions of nodes |
| Offline (Task 11) | App shell + recent briefs/assets + write queue | Full corpus offline, background differential sync |
| P&ID topology (Task 17) | Renders topology JSON from the cloud vision model (Path B); demo-fixture fallback flagged by `topology_source` | Path A: custom YOLOv9+LayoutLMv3 (local GPU) + in-canvas element sign-off |
| MoC (Task 27) | Manual approval stand-in | Signed MoC webhook round-trip |
| Cross-site (Task 33) | Honest "no data in a single-site deployment" state — no mock advisories | Live control-plane cross-site pattern feed |
| Audit-pack export (Task 25) | Browser print-to-PDF | Server-generated, signed evidence package |
| Document compare (Task 20) | Metadata + extracted-fact diff | Full visual PDF diff |
| Voice search (Task 12) | Web Speech API / record→transcribe | Always-on hands-free field querying |
| Non-conformance (Task 26) | Composed from existing endpoints | Dedicated NC tracking backend |
| Document ingestion (Task 20b) | Upload → pipeline status poll | Live drag-drop batch + inline extraction preview |
| MDM bootstrap (Task 20c) | Admin confirmation list | Full MDM editor + federated live-query (PuppyGraph) |
| Quarantine "request more info" (Task 22) | Reviewer note + elicitation re-trigger | Dedicated `request_info` backend action |
| Outcome-attribution (Task 32) | Summary counts from audit log | Per-recommendation attribution drill-down (Layer 10 analytics) |
| Timestamp-drift review (Task 23) | Dedicated report page `/governance/timestamp-drift` (report-only) | Accept/adjust normalization workflow |
| Instrumentation coverage (Task 15) | Read-only, from verified topology via `GET /assets/{id}/ot-coverage` (the Go `/ot/coverage` route was deleted) | Full coverage-map management surface |

Every cut above is an explicit decision matching the architecture's own "what to mock" guidance and single-site MVP scope — not a silent omission. Each names its upgrade path.

---

## Build Order (suggested)

1. **Foundation (Tasks 1–4)** — nothing else is clean without the client, types, roles, phase surface, and primitives.
2. **Field core (Tasks 5–7)** — the point-of-action thesis: field shell, brief inbox, PTW sign-off.
3. **Copilot + annotation (Tasks 13–14)** — the Phase 1/2 retrieval-and-feedback trust loop.
4. **Front door (Task 20b, 20c)** — document ingestion + MDM identity confirmation; the entry point that feeds every other surface with real data.
5. **Governance + engineer depth (Tasks 15–23, 27–30)** — the credibility of governed accuracy.
6. **Elicitation, off-boarding, voice, deviation, offline (Tasks 8, 8b, 9–12)** — tacit-knowledge capture + field robustness.
7. **Cockpit + procurement + management + events (Tasks 24–26, 31–35)** — the remaining personas.
8. **Quality sweep (Task 36)** — accessibility, palettes, responsive, skeletons, multi-script across everything.

Nothing in ARCHITECTURE.md Layer 12, no end-to-end flow (A–D), and no existing-but-unwired backend endpoint is left without a task above.
