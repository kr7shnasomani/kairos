> **MOSTLY HISTORICAL — but one fixture below is still live.**
>
> **`fixtures/pid_topology_mock.json` is NOT dead and must not be deleted.**
> `workflows/document_pipeline.py:211` falls back to it when the NIM vision model cannot parse a
> P&ID, and sets `topology_source: "demo_fixture"` — which the UI is required to disclose. That is
> the mock-by-design path, and removing the file breaks P&ID fallback. `fixtures/test.wav` is
> manual test audio for the voice-note flow (referenced from BE.md / FE.md), not used by code.
>
> Everything below about the **frontend** fixture system is historical:
>
> `lib/{fixtures,assets,governance,documents,events,compliance}.ts` and the `DemoChip` component
> were deleted on 2026-08-15, and `DataSource` narrowed to a single member (`"live"`) so a fallback
> cannot return without a type error. Fetchers now throw; the UI shows live data, a skeleton, or
> error+retry.
>
> Three of these paths were **not** dead when removed — `getEvents`, `governance/moc` and
> `governance/model-gate` rendered fabricated data on *successful* requests. Kept here as a record
> of what the system used to do and why it was removed.

# Kairos — Fixtures Reference

> **For AI coding agents:** This doc covers two very different kinds of fixture.
>
> **⚠️ The frontend is now LIVE-ONLY.** The web app never displays fabricated data. Every page shows
> **real backend data**, a **loading skeleton** while fetching, or an **error + retry** if the backend is
> unreachable — never a fixture. `useFetch` treats a fixture fallback as an error, server pages `throw`
> on it, and the few custom-client pages show an inline retry. See [§3](#3-frontend-live-only-policy).
>
> **Two paths used to bypass that policy and no longer do.** `synthesize()` and `getRcaPack()` in
> `lib/api.ts` do not return a `Fetched<>` envelope, so `useFetch`'s guard never applied to them —
> on any error they returned a hardcoded answer with invented document IDs, rendered identically to
> a real cited answer. Both now **throw**; the copilot shows a per-turn `AnswerError` with retry and
> the RCA page its existing `failed` state. The copilot fixtures (`SEAL`, `PRESSURE_REFUSAL`,
> `ISOLATION`, `GENERIC`, `answerFor`) are **deleted from `lib/copilot.ts`** — that file now holds
> types and suggestions only. `rcaFor` in `lib/rca.ts` survives but is marked **TEST-ONLY**
> (`rca/page.test.tsx` uses it to mock `getRcaPack`) and must never be imported by `api.ts`.
>
> **Backend fixtures below are mock-by-design** — they stand in for external plant systems Kairos does not
> own (EAM golden record, OT historian, P&ID vision model) and are the intended MVP state, not a gap. This
> doc maps each to the endpoint it backs, its data contract, and when it fires.

---

## Table of Contents

1. [Fixture Fallback Pattern](#1-fixture-fallback-pattern)
2. [Fixture Files](#2-fixture-files)
3. [Frontend Live-Only Policy](#3-frontend-live-only-policy)

---

## 1. Fixture Fallback Pattern

**Backend (Go connector):** Environment variable absent → fixture file loaded from disk.

```go
// EAM sync — fires when EAM_ODS_ENDPOINT is not set
if os.Getenv("EAM_ODS_ENDPOINT") == "" {
    // reads EAM_FIXTURE_PATH (default: /app/fixtures/sample_assets.json)
}
```

**Backend (Python API):** Live service unreachable → fixture JSON returned inline.

**Frontend:** LIVE-ONLY (see §3). Read fetchers return `{ data, source }`, but **`DataSource` is now a
single member — `"live"` (`api.ts:250`)**. There is no `"demo"` value to return, so a fixture fallback
cannot be reintroduced without a type error. Fetchers **throw** on failure. Read timeout **4 s**
(`getJson`), writes **8 s** (`postJson`), `synthesize()` **90 s**.

---

## 2. Fixture Files

### `fixtures/pid_topology_mock.json`

**Backed endpoint:** `GET /documents/{id}/topology`  
**Fires when:** Ingest-time **fallback** for `pid_drawing` documents when the Layer 3 vision model (`PIDService`, Path B) is unreachable or returns unparseable output. On the real path the topology comes from the model; the fallback is flagged `topology_source: "demo_fixture"` so it never masquerades as a real extraction.  
**Mount path:** `fixtures/` is mounted into `kairos-backend-api` and `kairos-celery-worker` at `/app/fixtures/`.

**Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `drawing_id` | string | P&ID drawing reference (e.g. `P-2301`) |
| `title` | string | Drawing title |
| `revision` | string | Revision code |
| `equipment_nodes[]` | array | Equipment items on the drawing |
| `equipment_nodes[].id` | string | Internal topology ID (`TOPO-EQ-*`) |
| `equipment_nodes[].tag` | string | Plant tag number |
| `equipment_nodes[].type` | string | Equipment type (e.g. `centrifugal_pump`) |
| `equipment_nodes[].equipment_class` | string | Class used for asset matching |
| `isolation_valves[]` | array | Isolation valve inventory |
| `isolation_valves[].tag` | string | Valve tag number |
| `isolation_valves[].normally_open` | bool | Default state |
| `instrumentation_loops[]` | array | Control/indication loops |
| `instrumentation_loops[].loop_id` | string | Loop identifier (e.g. `FIC-3047`) |
| `instrumentation_loops[].instruments[]` | string[] | Tag numbers in the loop |
| `isolation_boundaries[]` | array | Isolation boundary definitions |
| `isolation_boundaries[].primary_isolations[]` | string[] | Valve tags forming the boundary |
| `isolation_boundaries[].requires_double_block_bleed` | bool | PTW requirement flag |
| `isolation_boundaries[].regulatory_ref` | string | Regulation clause (e.g. `OISD-117-6.2`) |

**Demo content:** 5 equipment nodes (pump P-101, tank TK-201, heat exchanger HX-301, flow transmitter FT-3047, pressure gauge PG-18), 3 isolation valves, 2 instrumentation loops, 1 isolation boundary with double-block-bleed requirement.

---

### `backend/connectors/fixtures/sample_assets.json`

**Backed endpoint:** `POST /eam/sync` (Go connector)  
**Fires when:** `EAM_ODS_ENDPOINT` env var is not set (default in local dev).  
**Mount path:** Mounted into `kairos-backend-go` at `/app/fixtures/sample_assets.json`. Controlled by `EAM_FIXTURE_PATH` env var.

**Schema** (array of asset objects, matches `POST /assets` request body):

| Field | Type | Description |
|-------|------|-------------|
| `asset_id` | string | Canonical asset ID / tag number |
| `tag_number` | string | Plant tag (same as asset_id in demo) |
| `name` | string | Human-readable asset name |
| `equipment_class` | string | `pump`, `vessel`, `heat_exchanger`, `compressor`, `tank` |
| `criticality` | string | `safety_critical`, `critical`, `non_critical` |
| `site_id` | string | Site identifier (e.g. `SITE_001`) |
| `facility_id` | string | Facility within site (e.g. `FAC_PROCESS_A`) |
| `parent_asset_id` | string\|null | Parent asset for hierarchy |
| `eam_source` | string | Source system (e.g. `SAP_PM`) |

**Demo content:** 5 assets — P-101 (pump, safety_critical), V-201 (vessel, critical), HX-301 (heat exchanger, critical), C-401 (compressor, safety_critical), T-501 (tank, non_critical). All on `SITE_001`.

---

### `fixtures/test.wav`

**Backed endpoint:** `POST /elicitation/{work_order_id}/voice` (voice note upload — the frontend field route `/field/voice` posts here)  
**Fires when:** Used in integration tests and manual dev testing only — not a runtime fallback.  
**Purpose:** A short WAV file for testing the Groq Whisper transcription pipeline without needing a real recording. Feed it via the voice upload endpoint to exercise the full `transcribe_voice_note` Celery task.

---

## 3. Frontend Live-Only Policy

**The web app never shows fabricated data**, and this is now enforced by the type system rather than by
convention: `DataSource = "live"` is a single-member union, so a fetcher cannot return a fixture source
at all. Fetchers **throw** on failure.

- **Client pages (`useFetch`)** — a rejected fetcher becomes the page's error+retry state.
- **Server pages** (assets, asset detail, briefs, documents, doc detail, off-boarding) — **`throw` on demo**
  → the shared `(app)/error.tsx` boundary + `(app)/loading.tsx` skeleton. (`(app)/layout.tsx` is
  `dynamic = "force-dynamic"` so these render per request, never prerendered at build.)
- **Custom-client pages** (governance hub, MoC detail, plant-state, projects, off-boarding session, field
  elicitation) — show an inline "unavailable — retry" instead of the fixture.
- **`/management/cross-site`** has no backend (single-site MVP) — it shows an honest "No cross-site data in
  this deployment" state, not fabricated alerts.
- A few fetchers additionally treat **empty live data as a valid state** (e.g. `getComplianceGaps` no longer
  substitutes a fixture on empty).

So the net user experience everywhere is: **real data · loading skeleton · error+retry** — never a demo chip.

**The cleanup is done, not optional.** `<DemoChip>` and its 10 render sites were deleted on
2026-08-15, along with `lib/{fixtures,assets,compliance,documents,governance}.ts`. Verified
2026-08-17: none of those files exist and `DemoChip` appears nowhere in `frontend/src`.

Two files in that original list **survive deliberately, and are not fixture modules**:
`lib/copilot.ts` (live types + the real `SUGGESTIONS` constants + `metaAnswer()`) and `lib/rca.ts`
(live types + `RCA_PRESETS`, plus `rcaFor` which is **TEST-ONLY** and must never be imported by
`api.ts`).
