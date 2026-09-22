# End-to-end verification sweep

Full-system check: every route, every persona, feature-level — not a crash-grep.

**Why this file exists.** An earlier "regression sweep" opened 10 list routes and grepped for
"Something went wrong". It reported `briefs: 0 errors` at the exact moment the brief **detail**
page was throwing an error boundary for reliability users. A crash-grep on index routes is not
end-to-end verification and must not be presented as one.

## How to use

Driven with the `agent-browser` skill against `http://localhost:3000`.

- **Pass** = the feature does its job, not merely that the page rendered.
- Record the *observed* result, not "looks fine".
- Bugs found go in [`status.md`](./status.md), with the query/UI path that exposed them.

**Standing constraint:** no test may write to production Supabase. Read paths are free; write
paths (ack, countersign, verify, promote, ingest) do write — those are legitimate application
operations, but note each one you exercise.

## Logins

| Persona | Email | Password |
|---|---|---|
| admin | `admin@kairos.local` | `KairosAdmin123!` |
| engineer | `engineer@kairos.local` | `KairosEngineer123!` |
| reliability | `reliability@kairos.local` | `KairosReliability123!` |
| field_worker | `field_worker@kairos.local` | `KairosField123!` |
| compliance | `compliance@kairos.local` | `KairosCompliance123!` |

Role gating lives in `use-role.ts` (`routeAllowed` / `roleHome`). Expected: staff surfaces need
engineer/reliability/admin; `/system-health` is admin-only; `/compliance` + `/audit` also allow
compliance; a field worker hitting a gated URL redirects to `/briefs`.

---

## Legend

✅ verified this session · ⬜ not verified · ⛔ blocked · N/A not applicable to persona

---

## A. Routes × feature check

| # | Route | What "working" means | Status |
|---|---|---|---|
| 1 | `/` (landing) | Renders, nav anchors scroll, CTA → login | ✅ renders, 0 console errors |
| 2 | `/login` | Real login for all 5 personas; "Explore the live demo" → admin | ✅ all 5 personas — ✅ **API-verified 2026-08-17**: engineer/compliance/reliability login 200 and the **token's** role matches the persona (asserted, not assumed) |
| 3 | `/briefs` | Inbox lists live briefs; governor state shown; empty state honest | ✅ **API-verified 2026-08-17** — envelope carries `governor_state` (5/6, `normal`), `total_pending`, `suppressed_count` |
| 4 | `/briefs/[id]` | Evidence lineage; ack; **PTW dual sign-off** | ✅ full two-user flow |
| 5 | `/copilot` | Query returns a cited answer; refusal card on safety-critical | ✅ **FIXED + verified live** — the query that previously hedged now renders **"Safety-critical query — refused"** via the new **post-gate** (`self-reported confidence 0.0, 0 sources cited`). Scaffolding leak gone. This is the first live exercise of the post-gate; the benchmark's refusals were all pre-gate. |
| 6 | `/assets` | Live list, filters, pagination | ✅ **API-verified 2026-08-17** — `equipment_class` filter narrows 10→3; `site_id` filter applies |
| 7 | `/assets/[id]` | Detail + knowledge graph + **OT coverage badge** | ✅ coverage badge live |
| 8 | `/assets/bootstrap` | MDM human confirmation flow | ✅ **API-verified 2026-08-17** — register→201, `identity_confirmed_by` persisted. **Noted gap:** `GET /assets/{id}` reads the Neo4j node, which carries only `identity_confirmed`, so the attribution is stored (Supabase + audit_log) but not surfaced by the read API. Probe purged. |
| 9 | `/events` | Live event list | ✅ **API-verified 2026-08-17** — 17 events, `event_type` filter → 6, pagination pages don't overlap |
| 10 | `/events/[id]` | Event detail + linked brief | ✅ renders real payload (PTW Generated, V-247), 0 console errors |
| 11 | `/documents` | Vault list | ✅ **API-verified 2026-08-17** — 24 docs, `document_type` filter → 4 |
| 12 | `/documents/[id]` | Metadata, version chain, **handwriting-suspect chip** | ✅ **API-verified 2026-08-17** — detail returns `extraction_path: "native"`, `handwriting_suspect: false`; the **list** endpoint deliberately doesn't project them. 1 `pid_drawing`, correctly **not** flagged as handwriting |
| 13 | `/documents/[id]/topology` | **Element-by-element verify → canonical gate** | ✅ full flow, 0/2 → 2/2 |
| 14 | `/documents/ingest` | Upload → pipeline progress | ✅ **write path verified** — upload → 202 + SHA-256 + vault path → Temporal pipeline `graph_linking` → `complete` in ~8 s → 8 entities, 1 graph edge, 0 review items. Vault `active`, linked to EQ-101, retrievable via hybrid search. W7 flags correct (`native` / not handwriting). |
| 15 | `/documents/compare` | Two-document diff | ✅ **API-verified 2026-08-17** — both documents fetch 200; `document_type`/`authority_level`/`ingested_at` differ, so the diff has real content to render |
| 16 | `/graph` | React Flow graph, time-travel `as_of` | ✅ **API-verified 2026-08-17** — EQ-101 knowledge 7 facts now vs **0** `as_of=2020-01-01`, so the temporal filter genuinely applies |
| 17 | `/rca` | RCA pack generation (~90 s) or honest "unavailable" | ✅ **verified** — 4 timeline events, 3 hypotheses, `synthesis_available: true`. ⚠️ Found + fixed: hypotheses cited a document literally called `None` (fabricated provenance). |
| 18 | `/compliance` | Gap dashboard; `total_gaps` object shape | ✅ **API-verified 2026-08-17** — `total_gaps` is the object `{critical:7, major:24, minor:0}`; 47 gaps; framework filter → 11 |
| 19 | `/compliance/nonconformance` | NC tracking | ✅ renders, 0 console errors |
| 20 | `/compliance/audit-pack` | Evidence package assembly | ✅ **API-verified 2026-08-17** — OISD_117: 8 clauses / 6 evidence docs; ISO_45001: 4 / 52. `status=draft` + sign-off `note` present. (It is a **GET**; `TESTS.md` said POST and was corrected.) |
| 21 | `/audit` | Audit trail, sorted by `timestamp` | ✅ **API-verified 2026-08-17** — 630 rows, `action` filter → 479, pagination pages don't overlap |
| 22 | `/governance` | Overview counters | ✅ **API-verified 2026-08-17** — conflicts / quarantine / sla-report / circuit-breaker all 200 with their documented envelopes |
| 23 | `/governance/quarantine` | Promote / dispute / request-info | ✅ **write path verified** — engineer promote **403**, reliability promote **200**, graph edge confirmed present on EQ-101. |
| 24 | `/governance/conflicts` | Admin vs engineering track split | ✅ renders, 0 console errors |
| 25 | `/governance/moc` | MoC list | ✅ renders, 0 console errors |
| 26 | `/governance/moc/[id]` | MoC detail + approve | ✅ **write path verified** — field_worker approve **403**, engineer approve **200** → status `approved`. |
| 27 | `/governance/model-gate` | Run enqueues; history; **per-asset-class rows** | ✅ renders, 0 console errors · ✅ **run verified 2026-08-23** — `validity: VALID`, **0 fallbacks, all 27 extractions on NIM**, **F1 0.7816** on 40 scored labels (12 `COMPONENT` disclosed as unscoreable), per-asset-class **and** per-document-type rows. Took ~12 min, not the ~2.5 min this row used to claim: the old figure was a run in which almost every call failed fast on a 429. Closing this row took four fixes (run-validity recording, a run-scoped extraction cache, a raised Celery time limit, and taxonomy alignment) — see status.md Known Pitfalls |
| 28 | `/governance/circuit-breaker` | Live breaker state, **no fabricated rows** | ✅ 0 fabricated |
| 29 | `/governance/sla` | Escalation report shape | ✅ renders, 0 console errors |
| 30 | `/management` | Exec KPI view | ✅ **API-verified 2026-08-17** — all 5 core fetches 200 (conflicts · quarantine · SLA · compliance · events) |
| 31 | `/management/coverage` | Knowledge-coverage heatmap | ✅ renders, 0 console errors |
| 32 | `/management/cross-site` | Honest "single-site" state; **eyebrow must not say Layer 13** | ✅ **fixed** — eyebrow was 'Layer 13' (no such layer); now 'Overview · All sites' (2026-09-22 plain-language pass). Honest empty state correct. |
| 33 | `/management/plant-state` | Plant state set/read (admin) | ✅ **API-verified 2026-08-17** **write path** — normal → set `turnaround` (202) → read back `turnaround` → restored to `normal`. Full round trip. |
| 34 | `/projects` | Project/procurement registry | ✅ renders, 0 console errors |
| 35 | `/offboarding` | Programme list | ✅ **API-verified 2026-08-17** — 1 programme; detail returns 5 session items, and `/offboarding/{id}/questions` returns **5 questions per item** (the items themselves don't carry questions — that is the documented shape) |
| 36 | `/offboarding/[sessionId]` | Session items, responses (6 s timeout) | ✅ **API-verified 2026-08-17** **write path** — response submitted → 200 with a `quarantine_item_id`, so the answer lands in quarantine, never the canonical graph |
| 37 | `/field/voice` | Recorder UI | ✅ renders, 0 console errors · ✅ **capture 2026-08-22** — synthesised speech → vault → Groq `whisper-large-v3` (confidence 0.926, English) → `quarantine_items` row `pending` with the correct transcript, 50.4 s end to end. NER enrichment degraded to the regex path (NIM 500) and still wrote the item, i.e. the path degrades without losing the note |
| 38 | `/field/voice/[workOrderId]` | Capture → transcription | ✅ **write path verified** — upload → 202 + SHA-256 dedup + vault path → Groq Whisper transcribed → quarantine `voice_note`, `pending`, never auto-promoted. |
| 39 | `/field/deviation` | Physical deviation flag | ✅ **API-verified 2026-08-17** **write path** — flag on EQ-101 → 202, **4 briefs frozen**; resolve `disputed` → 200, **4 briefs unfrozen**, `moc_id: null`. Freeze/unfreeze proven both directions. |
| 40 | `/field/elicitation/[workOrderId]` | Micro-interview questions + responses | ✅ **write path verified** — trigger fired on real conditions (`rare_failure_code`, `novel_troubleshooting`) → Temporal generated 4 graph-derived questions → responses submitted → quarantine with question context preserved. |
| 41 | `/system-health` | 11 probes; AI-model toggles **off by default** | ✅ **API-verified 2026-08-17** — `/health/detailed` 200 reporting `status: ready`, live phase 3. Model probes deliberately **not** exercised: they spend provider quota and are off by default. |
| 42 | ~~`/system-benchmarks`~~ | Live benchmark cockpit | ➖ page removed 2026-09-22 |
| 43 | ~~`/system-information`~~ | Static explainer | ➖ page removed 2026-09-22 |
| 44 | `/settings` | System settings | ✅ renders, 0 console errors |

## B. Personas × access control

| Persona | Expected | Status |
|---|---|---|
| admin | everything incl. `/system-health` | ✅ partial |
| engineer | staff surfaces; **cannot** promote quarantine or countersign | ✅ countersign 403 confirmed |
| reliability | staff + promote + countersign | ✅ countersign confirmed |
| field_worker | `/briefs` + `/field/*`; gated URLs redirect to `/briefs` | ✅ **verified** — home `/briefs`; `/governance`, `/system-health`, `/management`, `/compliance`, `/audit` all redirect to `/briefs` |
| compliance | `/compliance` + `/audit` only; home = `/compliance`, no redirect loop | ✅ **verified** (token asserted) — home `/compliance`; `/compliance` + `/audit` accessible; `/governance`, `/management`, `/system-health` redirect to `/compliance`. `/briefs` + `/assets` open, which is by design (unlisted paths are open to all authed). |

## C. Cross-cutting

| Check | Status |
|---|---|
| Dark mode across main routes | ✅ re-verified 2026-09-23 after the dark palette was re-cut into three greys: rail `rgb(10,10,10)`, page `rgb(16,16,16)`, cards `rgb(24,24,24)`, fg `rgb(245,245,244)`. The earlier warm dark (`rgb(20,17,14)` / `rgb(237,233,226)`) is gone |
| Mobile viewport (375px) — hamburger nav, no bottom tab bar | ✅ briefs/assets/governance at 375×812 — no horizontal scroll, no error boundary |
| No `console.error` on any route | ✅ **0 console errors across all 44 routes** (swept when the two system pages still existed; 42 live routes since 2026-09-22) |
| No page scrolls horizontally | ✅ **all 34 static routes at 375×812 and 1440×900, 0 overflow** (re-swept 2026-09-22 across the then-36 routes; two were removed since).<br>Earlier run: all 35 static routes at 375×812 (2026-08-22). Detector validated by injecting a 900 px element: 0 → +525 px → 0, culprit named |
| Phase badge reflects live backend phase | ➖ removed 2026-09-22 (internal rollout jargon; phase still in `/health/detailed`) |
| Phase 1 suppresses synthesis, writes nothing | ✅ (curl, 324→324) |

---

---

## Coverage

**Routes: 44/44 reached** — every route loads with zero console errors and no error boundary,
including all dynamic `[id]` routes (IDs must be fetched from the API; they cannot be swept by URL).
**Personas: 5/5** verified for home route and access control. **Cross-cutting:** dark mode, mobile
375px, zero console errors system-wide.

### Update 2026-08-17 — 19 of the 22 open rows closed

Verified through the **API layer**, which is where these features actually live: filters, pagination,
time-travel, envelopes, freeze/unfreeze and the write paths are backend behaviours, and asserting them
against live data is stronger evidence than watching a page render. Persona results assert the **role
inside the token**, never the login that was attempted.

Four write paths were exercised and each was returned to its prior state: plant-state (set → read back
→ restored), deviation flag (4 briefs frozen → 4 unfrozen), an offboarding response (lands in
quarantine by design), and an MDM registration (probe assets purged from Supabase **and** Neo4j; the
10 golden assets were re-counted intact afterwards).

**Three rows remain open, deliberately:**

| Row | Why it is still open |
|---|---|
| 27 `/governance/model-gate` run | A ~2.5-minute Celery task costing ~15 NIM calls. Its *output* is already measured — `run_model_validation.py` produced F1 **0.805 · `VALID`** (0 of 15 fell back) on the post-fix run — so triggering it again buys a UI observation for real quota. |
| 38 `/field/voice` capture | Spends Groq transcription quota. The path is proven end-to-end elsewhere in this file (upload → SHA-256 dedup → vault → Whisper → quarantine `voice_note`, never auto-promoted). |
| 110 horizontal scroll on the remaining routes | Genuinely a browser check — no API stands in for layout. Three routes were checked at 375 px; the rest were not. |

**One gap found here, since fixed.** `GET /assets/{id}` read only the Neo4j node, which carries
`identity_confirmed` but not `identity_confirmed_by`/`_at` — so on the layer whose entire claim is
deterministic, human-confirmed identity, the attribution was stored (Supabase `assets` + `audit_log`)
but unreachable by any UI. `routers/assets.py` now fans out a Supabase identity lookup alongside the
existing enrichments and merges it into the response: the **graph node wins on the boolean** (it is
the canonical MDM record) and Supabase supplies `identity_confirmed_by` / `identity_confirmed_at`. The
lookup is in the same `asyncio.gather` as the other enrichments and degrades to `None` on failure, so
it cannot make the endpoint slower or fail it.

**Write paths: 6/6 verified** — ingest, quarantine promote, MoC approve, elicitation
trigger+submit, voice capture, RCA pack. Each was driven with real authenticated users and **the
negative case checked too** — the role that must be refused actually is. A write path that works but
does not refuse is half-tested.

### What "44/44" does and does not mean

It means nothing is broken, unreachable, or throwing. It does **not** mean every feature was driven
end to end. Rows still marked ⬜ are behaviours not exercised — mostly write paths and long-running
operations.

**This distinction is the point of the file.** An earlier sweep reported `briefs: 0 errors` at the
exact moment the brief *detail* page was throwing for reliability users, because it only opened list
routes. A clean render is not a passing feature.

### Method — read before adding a result

- **Assert the identity before recording a persona result:**
  `agent-browser eval "JSON.parse(atob(localStorage.getItem('kairos-token').split('.')[1])).user_metadata.role"`.
  A login that silently failed will report the *previous* persona's behaviour as the new one's.
- **Refs go stale after any navigation** — re-snapshot before every interaction.
- **Use a full snapshot, not `-c`** — compact mode drops nodes and produces false negatives.

**The pattern behind every bug this sweep found:** they were all query-semantics or real-data bugs
that the unit suite passed clean. Test doubles implement filters as passthroughs, so a filter whose
bug *is* its filtering always passes. The service-free tier proves logic; it cannot prove queries —
those need a real database or a real browser. Open items go to [`status.md`](./status.md).

### Not a bug — checked, do not re-investigate

A voice note submitted against a work order created via `/elicitation/trigger` has `asset_id: null`.
The transcription worker resolves the asset from the corresponding **work-order event**
(`voice_transcription.py:82-91`); a trigger-only work order writes no `operational_events` row, so
there is nothing to resolve. Voice notes raised through `/events/work-order` do carry their asset.

## Known-good baselines

Backend service-free tier **415 passed** (33 files, 2026-08-23) · frontend **228 passed, 67/67 files
green** (2026-08-23) · ruff clean (0.16.0) · Go build + vet clean.

`landing-figures.test.ts` needs `./benchmark` mounted into the frontend container; recreate it if
that file fails to collect. `model-gate` pagination is load-sensitive under full-suite parallelism.
Detail in [`status.md` § Verification snapshot](./status.md#verification-snapshot).
