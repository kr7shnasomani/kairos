# Kairos — API Reference

> **For AI coding agents:** Every HTTP endpoint is documented here. Base URL: `http://localhost:8000`. All endpoints except `/health` and `POST /auth/login` require `Authorization: Bearer <access_token>`.
>
> Also read `docs/BACKEND.md` for architecture, service internals, and non-negotiable rules before modifying any endpoint.

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Health](#2-health)
3. [Assets (MDM)](#3-assets-mdm)
4. [Documents (Vault + Pipeline)](#4-documents-vault--pipeline)
5. [Search](#5-search)
6. [Events (Operational)](#6-events-operational)
7. [Briefs (Operator Intelligence)](#7-briefs-operator-intelligence)
8. [Governance](#8-governance)
9. [Compliance](#9-compliance)
10. [Elicitation](#10-elicitation)
11. [Annotations](#11-annotations)
12. [Audit Log](#12-audit-log)
13. [Go OT Connector (port 8090)](#13-go-ot-connector-port-8090)
14. [Error Codes](#14-error-codes)
15. [Auth Quick-Reference](#15-auth-quick-reference)

---

## 1. Authentication

**Prefix:** `/auth`

Supabase issues ES256 JWTs. Tokens expire after 1 hour. Role is stored in `user_metadata.role`, not the top-level Supabase role.

**Test credentials (seed via `docker exec kairos-backend-api python scripts/seed_users.py`):**

| Email | Password | Role |
|-------|----------|------|
| `admin@kairos.local` | `KairosAdmin123!` | `admin` |
| `engineer@kairos.local` | `KairosEngineer123!` | `engineer` |
| `field_worker@kairos.local` | `KairosField123!` | `field_worker` |
| `reliability@kairos.local` | `KairosReliability123!` | `reliability` |
| `compliance@kairos.local` | `KairosCompliance123!` | `compliance` |

**Dev mode:** When `APP_DEBUG=True` **and** `APP_ENV != "production"`, any request without an `Authorization` header is treated as `{user_id: "dev-user", role: "engineer", site_id: "SITE_001"}`. Both conditions are required — see `Settings.dev_bypass_allowed`.

**Service bypass:** Bearer token matching `INTERNAL_API_KEY` (default: `kairos-internal-dev-key`) returns a service admin account without calling Supabase. Used by the Go connector and Celery workers.

**Token verification has exactly one implementation:** `dependencies.resolve_token`, which delegates to Supabase and is shared by the route dependency and the OPA middleware. Never decode these JWTs by hand — they are **ES256**, so an HS256 decode silently rejects every one of them.

### Authorization — writes *and* sensitive reads

`POST/PUT/PATCH/DELETE` are policy-checked, and since **2026-08-17** so are `GET`/`HEAD` on the sensitive read prefixes. Roles below mirror the frontend route table in `components/use-role.ts`.

| Read prefix | OPA action | Roles allowed |
|---|---|---|
| `/audit-log` | `read_audit` | engineer · reliability · compliance · admin |
| `/compliance` | `read_compliance` | engineer · reliability · compliance · admin |
| `/governance/conflicts` · `/governance/quarantine` | `read_nonconformance` | engineer · reliability · compliance · admin |
| `/governance` (everything else) | `read_governance` | engineer · reliability · admin |
| `/documents` | `read_documents` | engineer · reliability · admin |
| `/events` | `read_events` | engineer · reliability · compliance · admin |

`field_worker` gets **403** on all six. `/search`, `/briefs`, `/assets`, `/elicitation` and `/annotations` reads stay open to every authenticated role. Two deliberate exemptions: **`OPTIONS`** is never gated (the CORS preflight carries no token, and this middleware is outermost), and **`/events/plant-state`** is exempt from `read_events` because every persona's app shell renders plant state.

**Site scope is derived from the token, not the query string.** `site_id` on `GET /assets/` and the two `/compliance` reads narrows within the caller's own site; requesting another site is a **403**, and an account with no `site_id` gets nothing rather than everything. `admin` keeps the cross-site view.

---

### `POST /auth/login`

Exchange email + password for a JWT pair.

**Auth required:** No

**Request body:**
```json
{
  "email": "admin@kairos.local",
  "password": "KairosAdmin123!"
}
```

**Response `200`:**
```json
{
  "access_token": "<ES256 JWT>",
  "refresh_token": "<opaque token>",
  "token_type": "bearer",
  "user_id": "uuid"
}
```

**Errors:** `401` invalid credentials, `400` malformed payload

> **Critical:** This handler uses a fresh anon Supabase client (never the service-role client). Using the service-role client for auth operations contaminates its session and causes RLS violations on all subsequent table writes.

---

### `POST /auth/refresh`

Exchange a refresh token for a new JWT pair.

**Auth required:** No

**Request body:**
```json
{ "refresh_token": "<token>" }
```

**Response `200`:** Same shape as `/auth/login`.

---

### `GET /auth/me`

Return the current user's profile decoded from the JWT.

**Auth required:** Yes (any role)

**Response `200`:**
```json
{
  "user_id": "uuid",
  "email": "admin@kairos.local",
  "role": "admin",
  "site_id": "SITE_001"
}
```

---

## 2. Health

**Prefix:** `/health`

---

### `GET /health/`

Liveness probe. Returns 200 if the API process is running.

**Auth required:** No

**Response `200`:**
```json
{
  "status": "healthy",
  "service": "kairos-api",
  "version": "0.1.0",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

### `GET /health/detailed`

Readiness probe. Checks all 5 downstream services concurrently.

**Auth required:** No

**Response `200`:**
```json
{
  "status": "healthy",
  "services": {
    "neo4j": "ok",
    "qdrant": "ok",
    "elasticsearch": "ok",
    "redis": "ok",
    "temporal": "ok"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

If any service is unreachable, its value is `"error: <message>"`.

---

### `GET /health/model`

Opt-in liveness probe for a **rate-limited model provider**. Makes the smallest possible real call
(1 token / 1 embedding / a models list) so the System Health page can show live model status.

**Auth required:** Yes — `admin` only. **Not** polled by default (each call spends provider quota).

**Query params:** `provider` — one of `nim | gemini | jina | groq`.

**Response `200`:**
```json
{ "provider": "nim", "ok": true, "status": 200, "model": "nvidia/nemotron-3-super-120b-a12b", "latency_ms": 2603, "detail": null }
```

`ok: false` with `detail: "not configured"` when the provider's API key is unset; `detail` carries the
error text when the upstream call fails. `400` for an unknown provider.

---

### `GET /health/connectors`

OT historian connector registry (Layer 5) — makes *"new connector types are added without changing
the core layer"* inspectable rather than asserted. Passthrough to the Go connector.

Every supported historian is listed with its configuration state and the env var that activates it.
An unconfigured connector reports itself as unconfigured; it never fabricates a reading and never
fails silently.

**Response `200`:** `{connectors: [{name, protocol, status, config_var, configured, detail}], active_count, serving_historian: {mock, note}}`

`status` is `active` (configured + implemented) · `not_configured` (implemented, no endpoint) ·
`registered` (in the connector layer, client not implemented in this build). **`503`** if the
connector service is unreachable — not an empty registry, which would read as "no connectors supported".

---

## 3. Assets (MDM)

**Prefix:** `/assets`

Asset MDM: Neo4j (graph) + Supabase (relational) + Elasticsearch (search). Asset identities are **human-confirmed** — no AI-inferred canonical IDs are accepted. All writes use `MERGE` in Neo4j, never `CREATE`.

**Required role for `POST /assets/`:** `admin` or `engineer` (OPA enforced)

---

### `POST /assets/`

Register a new canonical asset.

**Auth required:** Yes — `admin` or `engineer`

**Request body:**
```json
{
  "asset_id": "P-101",
  "tag_number": "P-101",
  "name": "Feed Pump Alpha",
  "equipment_class": "pump",
  "site_id": "SITE_001",
  "parent_asset_id": null,
  "criticality": "safety_critical",
  "design_pressure_bar": 12.5,
  "design_temperature_c": 180.0,
  "manufacturer": "Flowserve",
  "model_number": "PVXD-250",
  "eam_source": "SAP_PM",
  "eam_asset_id": "10001234",
  "confirmed_by_user_id": "admin@kairos.local",
  "additional_properties": {}
}
```

Key fields:
- `asset_id` — canonical identifier (tag number). Must be globally unique.
- `criticality` — `safety_critical | critical | non_critical`
- `confirmed_by_user_id` — **mandatory** (AI-inferred identities are rejected), but **not trusted**: the
  confirmer recorded in `identity_confirmed_by` and `audit_log.performed_by` is the **authenticated caller**.
  The body value is used only if the session carries no user id. Trusting it let a caller attribute a
  confirmation to someone else.
- `eam_source` — `SAP_PM | IBM_Maximo | other`

**Response `201`:**
```json
{
  "asset_id": "P-101",
  "tag_number": "P-101",
  "status": "created"
}
```

---

### `POST /assets/bulk`

Bulk-import assets from an EAM golden record — Layer 1's deterministic bootstrap. `POST /assets/`
registers one asset at a time; this is the path for loading a plant.

**Auth required:** Yes — `admin` or `engineer`

**Request body:**
```json
{
  "assets": [
    {
      "asset_id": "P-101",
      "tag_number": "P-101",
      "name": "Feed Pump Alpha",
      "equipment_class": "pump",
      "criticality": "safety_critical",
      "site_id": "SITE_001",
      "facility_id": "FAC_001",
      "parent_asset_id": null,
      "eam_source": "SAP_PM"
    }
  ]
}
```

- **No `confirmed_by_user_id` per row.** The confirming authority is the caller, taken from the
  verified token. A per-row field would let one import be attributed to someone else.
- `asset_id` may be omitted — one is generated, and such a row can never collide.
- 1–5000 rows. Split larger exports so a single failed request never costs a whole plant.

**Response `200`** — partial success is the contract, not a fallback. One malformed row in a
500-row export must not cost the other 499, so every row that did not land is reported with its
index in the submitted payload:

```json
{
  "submitted": 4,
  "created": 2,
  "created_asset_ids": ["P-101", "ASSET-7QK2M4XB"],
  "already_present":      [{"row": 1, "asset_id": "EQ-101"}],
  "duplicate_in_payload": [{"row": 2, "asset_id": "P-101"}],
  "site_forbidden":       [{"row": 3, "asset_id": "EQ-201", "site_id": "SITE_002"}],
  "failed":               []
}
```

| Bucket | Meaning |
|---|---|
| `already_present` | Asset exists. **Skipped, never overwritten** — a re-import cannot replace `identity_confirmed_by`. |
| `duplicate_in_payload` | Same `asset_id` twice in one file. First wins; usually means the export was joined wrong. |
| `site_forbidden` | Row targets a site the token does not cover. Checked *before* existence, so the response cannot leak which ids exist in an unreadable site. Admins are cross-site. |
| `failed` | The write itself errored. Row-level, so one bad row is one bad row. |

Re-posting the whole file after fixing rows is safe: creation is idempotent, so rows that already
succeeded return as `already_present` rather than duplicating.

---

### `GET /assets/`

List all registered assets.

**Auth required:** Yes

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `site_id` | string | — | Filter by site |
| `equipment_class` | string | — | Filter by class (pump, vessel, …) |
| `skip` | int | `0` | Pagination offset |
| `limit` | int | `50` | Page size (max 200) |

**Response `200`:**
```json
{
  "items": [
    {
      "asset_id": "EQ-101",
      "name": "Boiler Feed Pump A",
      "equipment_class": "pump",
      "criticality": "safety_critical",
      "site_id": "SITE_001",
      "open_work_orders_count": 5,
      "compliance_gap_count": 59
    }
  ],
  "total": 5,
  "limit": 50,
  "offset": 0
}
```

> **`open_work_orders_count` / `compliance_gap_count` are on every row** (added 2026-08-23; the
> list previously omitted them and only `GET /assets/{asset_id}` carried them, which blocked two
> columns the design review asked for). Definitions are shared with the detail endpoint —
> `operational_events` of type `work_order_created`, and `knowledge_conflicts` with
> `status = "open"` — so the list and the detail page can never disagree about the same number.
>
> **Always numeric, never null**: an asset with no rows is `0`. A failed Supabase lookup is also
> `0`, logged as `asset.list_counts_failed`; treat these as "best known" rather than
> guaranteed-live.
>
> Cost is **two queries per page regardless of page size** — the counts are fetched in bulk for
> the page's asset ids and tallied in the router, not queried per asset. Do not "simplify" this
> into the detail handler's per-asset `count="exact"` pair: that is an N+1 costing 100 round
> trips on a 50-row page. A server-side `GROUP BY` would be better still, but PostgREST
> aggregates are disabled on this project (`PGRST123`).

---

### `GET /assets/coverage`

Knowledge-coverage matrix across **all** assets — what backs the `/management/coverage` heatmap.
Per asset: facts held, how many are authoritative, how many are human-verified, linked documents
and pending quarantine items.

Read-only and **model-free** — no OCR/NER/embedding call, so it spends no provider quota.

> Declared **before** `/assets/{asset_id}` in `routers/assets.py` on purpose: FastAPI matches in
> declaration order, so the reverse would make `coverage` resolve as an `asset_id`.

**Response `200`:**
```json
{
  "items": [
    {
      "asset_id": "EQ-101",
      "fact_count": 5,
      "authoritative_count": 2,
      "verified_count": 1,
      "document_count": 4,
      "quarantine_pending": 21
    }
  ],
  "total": 10
}
```

---

### `GET /assets/{asset_id}`

Get a single asset by its canonical ID. Enriched with 3-parallel live counts.

**Auth required:** Yes

**Response `200`:**
```json
{
  "asset_id": "P-101",
  "tag_number": "P-101",
  "name": "Feed Pump Alpha",
  "equipment_class": "pump",
  "site_id": "SITE_001",
  "criticality": "safety_critical",
  "open_work_orders_count": 2,
  "compliance_gap_count": 0,
  "last_inspection_date": "2024-03-01T00:00:00Z"
}
```

`open_work_orders_count`, `compliance_gap_count`, and `last_inspection_date` are fetched in parallel from Supabase. **`404`** if not found.

---

### `GET /assets/{asset_id}/aliases`

List all known tag aliases (alternate tag numbers, legacy names) for an asset.

**Auth required:** Yes

**Response `200`:**
```json
[
  {
    "alias": "PUMP-101",
    "confidence": 0.95,
    "confirmed": true,
    "source": "P&ID Rev C"
  }
]
```

Aliases proposed by the extraction pipeline arrive `confirmed: false`. Only **confirmed** aliases
resolve a tag to its canonical asset, so an unconfirmed candidate is inert until a human signs it
off with the endpoint below.

---

### `POST /assets/{asset_id}/aliases/{alias}/confirm`

Confirm a tag alias the NER pipeline proposed, making it usable for tag resolution. This is the
human half of Layer 1's rule that AI-assisted linking is permitted **only after** human
confirmation.

**Auth required:** Yes (`engineer` or `admin`)

**Response `200`:**
```json
{
  "status": "confirmed",
  "alias": "PUMP-101",
  "canonical_asset_id": "P-101",
  "confirmed_by": "user-uuid"
}
```

Idempotent — re-confirming returns `{"status": "already_confirmed", ...}` rather than an error.
`404` if no such alias was proposed for that asset. Writes an `asset_alias_confirmed` audit row.

---

### `GET /assets/{asset_id}/hierarchy`

Get the parent–child asset hierarchy (up to 10 levels deep via Neo4j `PARENT_OF` traversal).

**Auth required:** Yes

**Response `200`:**
```json
{
  "asset_id": "P-101",
  "parent": null,
  "children": [
    { "asset_id": "P-101-SEAL", "name": "Mechanical Seal" }
  ]
}
```

---

| `GET` | `/assets/coverage` | Knowledge-coverage matrix across all assets — facts, authoritative facts, verified facts, linked documents, pending quarantine. Read-only and model-free (spends no provider quota). Declared **above** `/{asset_id}` so the literal path is not swallowed by the path parameter. |
### `GET /assets/{asset_id}/knowledge`

Get all temporal graph facts linked to this asset from Neo4j. Accepts a **canonical id or a confirmed tag alias** — `P-101` resolves to `EQ-101` via `asset_alias_map` (`resolve_canonical_asset_id`); the response echoes `requested_id` and `resolved_from_alias`. Facts are **deduped by `edge_id`** (the graph can hold physical duplicate relationships).

**Auth required:** Yes

Facts sourced from **test/sweep artifacts are excluded by default** and counted in
`excluded_test_documents`. The classifier is the vault `file_name` (`services/corpus.py`), which is
a Supabase column — the Neo4j node carries only `document_id` — so this cannot be a Cypher filter.
A `document_id` with no vault row (e.g. `PROMOTED-<uuid>`) is **kept**: unclassifiable is not
disposable.

**Auth required:** Yes

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `as_of` | ISO8601 datetime | `now` | Time-travel: return facts valid at this timestamp |
| `include_test_data` | bool | `false` | Include facts whose source document is a test artifact |

**Response `200`:**
```json
{
  "asset_id": "EQ-101",
  "requested_id": "P-101",
  "resolved_from_alias": true,
  "as_of": "now",
  "fact_count": 7,
  "excluded_test_documents": 53,
  "facts": [
    {
      "edge": {
        "edge_id": "EQ-101_DOCUMENTED_BY_DOC-FYBIYN95D7JH_2026-08-22T06:51:22Z",
        "relationship_type": "DOCUMENTED_BY",
        "authority_level": 3,
        "document_id": "DOC-FYBIYN95D7JH",
        "confidence": 0.95,
        "valid_from": "2026-08-22T06:51:22Z",
        "valid_to": "9999-12-31T23:59:59Z",
        "verification_status": "unverified"
      },
      "target": {
        "document_id": "DOC-FYBIYN95D7JH",
        "document_type": "oem_manual",
        "authority_level": 3
      }
    }
  ]
}
```

> Each fact is `{edge, target}` — the six mandatory edge properties plus the node the edge points
> at. There is **no `value`** on an edge; see `GET /governance/conflicts` for what that costs.

---

### `GET /assets/{asset_id}/ot-coverage`

Instrumentation coverage map (Layer 5) — which components on this asset are actually monitored.

Derived from **engineer-verified P&ID topology only**: verified `instrumentation_loops[].instruments[]`
are the sensor tags. Layer 10 uses this to decide whether a repair can be judged by telemetry or
needs human closeout attestation.

> Replaces a Go handler that returned hardcoded `{asset}-VIBE` / `{asset}-TEMP` / `75%` for **every**
> asset on both branches, including the one labelled `source: "knowledge_graph"`. That route is deleted.

**Response `200`:**
```json
{
  "asset_id": "V-247",
  "coverage_type": "direct | macro | none",
  "has_direct_sensors": true,
  "sensor_tags": ["FT-3047", "FV-3047"],
  "verified_loops": 1, "total_loops": 1,
  "derived_from": "verified_pid_topology",
  "source_documents": ["DOC-..."],
  "unverified_topology_present": false
}
```

`coverage_type: "none"` means **no verified drawing establishes instrumentation** — not a claim that
the equipment has no sensors. `unverified_topology_present` distinguishes review backlog from
genuine absence.

---

## 4. Documents (Vault + Pipeline)

**Prefix:** `/documents`

Documents are **immutable**. Once ingested, they can only be superseded (version chained), never deleted or overwritten. SHA-256 deduplication prevents duplicate ingestion.

---

### `POST /documents/ingest`

Ingest a document into the vault and trigger the full pipeline: OCR → NER → graph linking → vector indexing → text indexing.

**Auth required:** Yes (`engineer` or `admin`)

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | binary | Yes | PDF, PNG, JPG, TIFF |
| `document_type` | string | Yes | `procedure`, `regulation`, `engineering_drawing`, `maintenance_record`, `ptw`, `incident_report`, `material_certificate`, `datasheet` |
| `authority_level` | int 1–5 | Yes | 1=Regulatory, 2=Engineering, 3=OEM, 4=Procedure, 5=Field |
| `asset_ids` | string (JSON array) | No | `'["P-101","V-201"]'` |
| `source_system` | string | Yes | e.g. `SAP_DMS`, `SharePoint` |
| `access_tags` | string (JSON array) | No | e.g. `'["confidential","process"]'` |
| `occurred_at` | ISO8601 string | No | Source document date (used for timestamp drift detection) |

**Response `202`:**
```json
{
  "document_id": "doc-uuid",
  "job_id": "job-uuid",
  "workflow_id": "temporal-workflow-id",
  "status": "accepted",
  "message": "Ingestion pipeline started"
}
```

SHA-256 deduplication: if an identical file was previously ingested, returns the existing `document_id` with `status: "duplicate"`.

---

### `GET /documents/`

List vault documents.

**Auth required:** Yes

**Query params:**
| Param | Type | Default |
|-------|------|---------|
| `asset_id` | string | — |
| `document_type` | string | — |
| `status` | string | `active` |
| `authority_level` | int | — |
| `skip` | int | `0` |
| `limit` | int | `50` |

**Response `200`:**
```json
{
  "items": [...],
  "total": 12
}
```

Each item includes `asset_links: ["EQ-101", ...]` — the asset ids the document is linked to (batch-joined
from `document_asset_links`, one query, no N+1). Consumers such as the projects portfolio classify documents
by their linked assets' equipment class; without this every doc would read as "Unclassified".

---

### `GET /documents/{document_id}/artifact-url`

Get a short-lived Supabase **signed URL** to open the raw vault artifact in a browser.

**Auth required:** Yes

The stored `vault_url` points at Supabase's `/object/authenticated/` endpoint, which **requires an
`Authorization` header a plain link/`window.open` cannot send** (Supabase returns `400 headers must have
required property 'authorization'`). This endpoint mints a signed URL instead — the token rides in the query
string, so it opens without a header. The frontend "Open artifact" button fetches this (authenticated) then
`window.open`s the result.

**Response `200`:**
```json
{
  "signed_url": "https://…supabase.co/storage/v1/object/sign/kairos-vault/<path>?token=…",
  "expires_in": 3600
}
```

**Errors:** `404` document not found · `422` artifact path unavailable · `502` signing failed

---

### `GET /documents/{document_id}/status`

Poll the extraction pipeline status for a document.

**Auth required:** Yes

**Response `200`:**
```json
{
  "document_id": "doc-uuid",
  "pipeline_stage": "complete",
  "progress_percent": 100,
  "ocr_confidence": 0.903,
  "ner_entity_count": 12,
  "graph_edges_created": 8,
  "review_items_pending": 2,
  "error": null,
  "updated_at": "2024-01-01T00:00:00Z"
}
```

Pipeline stages (in order): `pending → ocr_pending → ocr_complete → ner_pending → ner_complete → graph_pending → graph_complete → index_pending → complete` (or `failed`).

`ocr_confidence` is the **model's own** per-span confidence weighted by span length — not a constant. It was hardcoded to `0.95` for every OCR extraction until 2026-08-23. Native-text paths (digital PDF, plain text, spreadsheet, email) report `1.0` because nothing was read off an image. A value below `0.5` sets `pipeline_stage: review_required`; the `< 0.7` quarantine rule applies downstream.

---

### `GET /documents/{document_id}/extraction`

What extraction wrote for this document. Nothing is re-extracted: `entities` are read back from the
graph edges carrying this `document_id` (the endpoint that is not the document — an Asset for
`DOCUMENTED_BY`, a Person for `MENTIONS_PERSON`, …), one per value at its strongest confidence.
`review_items` are the `quarantine_items` whose `session_context.document_id` names this document —
the low-confidence entities that never reached the graph. A graph outage degrades to no entities.

**Auth required:** Yes

**Response `200`:**
```json
{
  "document_id": "DOC-JTJELSCENM6M",
  "extraction_model": "meta/llama-3.2-11b-vision-instruct + nvidia/nemotron-ocr-v2",
  "entities": [
    {
      "entity_type": "asset_tag",
      "value": "EQ-101",
      "normalized_value": null,
      "confidence": 0.95,
      "linked_asset_id": "EQ-101",
      "requires_review": true
    },
    {"entity_type": "person", "value": "S. Yadav", "confidence": 0.95, "linked_asset_id": null, "requires_review": true}
  ],
  "graph_edges_created": 6,
  "vector_chunks_indexed": 0,
  "review_items": [
    {"item_id": "uuid", "content": "Low-confidence entity: 'HE301X' (confidence=0.52)", "review_status": "pending", "submitted_at": "2026-07-14T10:00:00Z"}
  ],
  "extraction_path": "native",
  "handwriting_suspect": false
}
```

Entity types: `asset_tag`, `person`, `organisation`, `topology_element`, otherwise the lower-cased
relationship type. `requires_review` is true until the edge is `verified`.

---

### `GET /documents/{document_id}`

Get vault document metadata.

**Auth required:** Yes

**Response `200`:**
```json
{
  "document_id": "doc-uuid",
  "sha256_hash": "abc123...",
  "file_name": "OISD-117.pdf",
  "file_size_bytes": 1048576,
  "mime_type": "application/pdf",
  "document_type": "regulation",
  "authority_level": 1,
  "source_system": "OISD",
  "vault_url": "https://supabase-url/storage/v1/...",
  "ingested_at": "2024-01-01T00:00:00Z",
  "ingested_by": "admin@kairos.local",
  "status": "active",
  "version_chain": null,
  "asset_links": ["P-101", "V-201"],
  "access_tags": []
}
```

`status` values: `active | superseded | archived | disputed`

---

### `GET /documents/{document_id}/topology`

Get the parsed P&ID / engineering drawing topology for a drawing document.

**Auth required:** Yes

Only available for documents with `document_type = "pid_drawing"` — all other types `404` by design. Topology is extracted at ingest time (OCR is skipped) by the Layer 3 vision model (`PIDService`, Path B); the response includes `topology_source` (`vision_model` when the model ran, `demo_fixture` when it fell back). Every element routes to element-by-element engineer verification before it becomes canonical.

**Response `200`:**
```json
{
  "document_id": "DOC-TS4FXYKHCQEF",
  "manifest_item_id": "3c0e469e-…",
  "verification_status": "unverified",
  "topology": {
    "title": "Feed Section P&ID - Pump P-101",
    "revision": "Rev-4",
    "drawing_id": "P-2301",
    "equipment_nodes": [
      {"id": "TOPO-EQ-001", "tag": "P-101", "type": "centrifugal_pump", "equipment_class": "pump", "service": "Feed Pump A", "design_temp_c": 80, "design_pressure_kpa": 800}
    ],
    "isolation_valves": [
      {"id": "TOPO-VLV-001", "tag": "XV-203", "type": "gate_valve", "service": "P-101 Suction Isolation", "normally_open": true, "last_inspected": "2024-06-15", "inspection_interval_months": 18}
    ],
    "isolation_boundaries": [
      {"id": "TOPO-ISO-001", "boundary_id": "ISO-P101-MAINT", "ptw_type": "mechanical", "primary_isolations": ["XV-203", "XV-204"], "bleed_vents": ["PG-18"], "regulatory_ref": "OISD-117-6.2", "requires_engineer_signoff": true, "requires_double_block_bleed": true}
    ],
    "instrumentation_loops": [
      {"id": "TOPO-LOOP-001", "loop_id": "FIC-3047", "type": "flow_control", "instruments": ["FT-3047", "FIC-3047", "FV-3047"], "design_range_m3h": "0-120", "alarm_low_m3h": 5, "alarm_high_m3h": 110}
    ]
  },
  "extracted_at": "2026-07-10T11:52:56Z"
}
```

> ⚠️ Elements are **grouped under a nested `topology` object** in four category arrays
> (`equipment_nodes`, `isolation_valves`, `isolation_boundaries`, `instrumentation_loops`) — there is no
> flat `equipment`/`valves`/`loops`/`boundaries` list and no explicit edges. The frontend
> `getDocumentTopology` fetcher flattens these into `{nodes, edges}`, synthesising boundary→valve/bleed
> edges from `primary_isolations` + `bleed_vents`.

**`404`** for any non-`pid_drawing` document, or if topology not yet extracted.

The response also carries the **verification roll-up**, derived from each element's review state
(it was previously a hardcoded `"unverified"` literal, so no reviewer action could change it):

```json
{
  "verification_status": "unverified | partially_verified | verified",
  "elements_total": 4, "elements_verified": 4, "elements_disputed": 0,
  "safety_critical_total": 2, "safety_critical_verified": 2,
  "canonical_ready": true,
  "elements": { "TOPO-LOOP-001": { "verification_status": "verified", "element_group": "instrumentation_loops", "reviewed_by": "...", "reviewed_at": "..." } }
}
```

---

### `POST /documents/{document_id}/topology/verify`

Element-by-element engineer verification — the Layer 3 → Layer 7 gate the architecture calls
non-negotiable regardless of model accuracy. Confirming an element promotes the
`CONTAINS_TOPOLOGY_ELEMENT` edge the ingestion pipeline already wrote from `unverified` to
`verified`; it does **not** create new edges.

**Auth required:** Yes — engineer, reliability, or admin.

**Request body:**
```json
{ "decisions": [ { "element_id": "TOPO-LOOP-001", "decision": "confirmed | corrected | rejected", "note": "optional" } ] }
```

**Response `200`:** the refreshed roll-up plus `applied: [...]` and `unknown_elements: [...]`.
Unknown element ids are reported, never silently ignored. `400` if no decision applied.

`canonical_ready` turns true only when **every** safety-critical element (isolation boundaries,
instrumentation loops) is confirmed and none are disputed.

---

### `POST /documents/{document_id}/ocr-review/release` · `POST /documents/{document_id}/ocr-review/reject`

The human decision on a document the OCR confidence gate held (`pipeline_stage: review_required` — see
D1: a mean below 0.5 **or any span below 0.7** holds the scan). The reviewer opens the original scan first.

**Auth required:** Yes · **Role:** `reliability` or `admin` (the same authority that promotes quarantine)

**Body (optional):** `{"note": "Pressure values legible on the original"}` — max 1000 chars, recorded in the audit trail.

- **release** re-runs `DocumentIngestionWorkflow` from the vault artifact with `ocr_reviewed_by` set, so
  `run_ocr` logs the gate as a human override (`activity.ocr_gate_released`) and continues. What is read still
  enters the graph as `unverified` edges and low-confidence entities still quarantine — releasing the scan does
  not verify its content. A new `extraction_jobs` row is created; the held one is kept.
  **`200`** `{status: "released", document_id, job_id}` · **`503`** if the workflow cannot start (the document stays held)
- **reject** closes the held job as `pipeline_stage: rejected` with the note. The artifact is never deleted;
  a legible rescan is ingested as a new document.
  **`200`** `{status: "rejected", document_id}`

Both write an `audit_log` row (`ocr_review_released` / `ocr_review_rejected`) with the gate reason.
**`409`** if the document's latest job is not held · **`403`** for any other role.

---

### `GET /documents/{document_id}/redacted`

Export the document's extracted text with personal identifiers masked — the DPDP Act 2023
export boundary.

**Auth required:** Yes

Redaction runs at **export only, never at ingestion**. Operational knowledge legitimately
contains personnel names ("which technician signed off the EQ-101 seal repair" is a real
maintenance question the vault must answer), so stripping names on the way in would destroy
retrieval. The vault copy is never modified.

PERSON names come from the Person nodes the pipeline already linked to the document
(`MENTIONS_PERSON`) — the same NER output, computed once at ingestion, so an export takes well
under a second instead of re-running NER for up to two minutes. A document with no graph edges
falls back to live `NERService`. Structured identifiers (email, phone, Aadhaar, PAN,
employee ID, shift ID) are matched by pattern in `services/pii.py`. Masks are **stable
pseudonyms** within a document — the same name is always `[PERSON_1]` — so cross-references
in the text survive redaction, which a blanket `[REDACTED]` would destroy.

Every call writes a `pii_redacted_export` row to `audit_log` with PII **type counts only**,
never the matched values.

**Response `200`:**
```json
{
  "document_id": "DOC-TS4FXYKHCQEF",
  "document_type": "shift_log",
  "redacted_text": "Shift handover. [PERSON_1] reported abnormal vibration on EQ-101. Contact [EMAIL_1].",
  "pii_found": true,
  "pii_counts": {"PERSON": 2, "EMAIL": 1, "SHIFT_ID": 1},
  "pii_span_count": 4,
  "note": "DPDP Act 2023 export boundary. Vault original is unmodified and retains full text."
}
```

**`404`** if the document has no indexed text yet (still in extraction).

> **Scope:** this is a per-document export boundary. `ARCHITECTURE.md` describes redaction as
> gating cross-site knowledge promotion; there is no cross-site promotion endpoint in the
> codebase, so that wiring does not exist yet. The redaction pipeline itself is real.

---

### `POST /documents/{document_id}/supersede`

Mark a document as superseded by a newer version. Closes `valid_to` on all Neo4j KNOWLEDGE_EDGE relationships sourced from this document.

**Auth required:** Yes (`engineer` or `admin`)

Also flags the old version `status: "superseded"` in **Elasticsearch and every Qdrant chunk**, so it
stops surfacing in default retrieval (ARCHITECTURE.md §8). Nothing is deleted from either store — a
time-travel query (`as_of`) still reaches it.

**Request body:**
```json
{
  "new_document_id": "doc-new-uuid"
}
```

**Response `200`:**
```json
{
  "status": "superseded",
  "old_document_id": "doc-old-uuid",
  "new_document_id": "doc-new-uuid",
  "edges_closed": 8,
  "blast_radius": { "document_id": "doc-old-uuid", "affected_count": 6, "affected": [] },
  "moc_required": true,
  "moc_id": "MOC-A1B2C3D4",
  "index_errors": []
}
```

`moc_id` is non-null when any affected edge carried `authority_level <= 3`.

**`index_errors` is the one field to check.** It names the stores that failed (`elasticsearch`, `qdrant`); the error detail is in the server log, never in the response. Non-empty means the vault row is superseded but a
search index still serves the old version as current — re-run the supersede once that store is
reachable. It is reported rather than raised because Supabase is the source of truth.

---

## 5. Search

**Prefix:** `/search`

Hybrid search across three engines in parallel. Results are authority-ranked (level 1 Regulatory > level 5 Field).

---

### `GET /search/`

Parallel hybrid search: ES exact + Qdrant 1024-dim semantic + Neo4j graph.

**Auth required:** Yes

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `q` | string | **required** | Search query |
| `asset_id` | string | — | Scope to one asset: documents filed under it **or** linked to it in the knowledge graph (a work-order log filed under EQ-102 that records EQ-101 failures matches EQ-101). Within an authority level, the asset's own documents rank first. |
| `limit` | int | `10` | Max results per engine |
| `include_quarantine` | bool | `false` | Include unverified quarantine items |
| `as_of` | ISO8601 datetime | `now` | Time-travel: return only facts valid at this time |
| `authority_min` | int 1–5 | `1` | Exclude sources below this authority level |

**Response `200`:**
```json
{
  "query": "max allowable pressure P-101",
  "results": [
    {
      "document_id": "doc-oisd-6.4",
      "asset_id": "P-101",
      "document_type": "regulation",
      "title": "OISD-117 Section 6.4 — Pressure Limits",
      "snippet": "Maximum allowable working pressure: 12.5 bar at 180°C",
      "authority_level": 1,
      "status": "active",
      "relevance_score": 0.95,
      "retrieval_method": "graph",
      "is_quarantine": false,
      "vault_url": "https://..."
    }
  ],
  "total": 1,
  "retrieval_methods": ["exact", "semantic", "graph"]
}
```

`retrieval_method` per result:
- `exact` — Elasticsearch tag number / document ID match
- `semantic` — Qdrant 1024-dim ANN (Jina embeddings)
- `graph` — Neo4j KNOWLEDGE_EDGE traversal (only when `asset_id` provided)

---

### `GET /search/assets/{asset_id}`

Search within a specific asset's knowledge. Same engines but asset pre-filtered.

**Auth required:** Yes

**Query params:** Same as `GET /search/` minus `asset_id`.

**Response `200`:** Same shape as `GET /search/`.

---

### `POST /search/synthesize`

**Phase 2.** Synthesize a natural-language answer from retrieved context using NVIDIA NIM (primary) or Ollama (fallback). Never originates knowledge — assembles only what was retrieved and passed in `context`.

**Auth required:** Yes

**Request body:**
```json
{
  "query": "What is the maximum allowable pressure for P-101?",
  "context": [
    {
      "document_id": "doc-oisd-6.4",
      "title": "OISD-117 Section 6.4",
      "snippet": "Maximum allowable working pressure: 12.5 bar at 180°C",
      "authority_level": 1,
      "confidence": 0.98
    }
  ],
  "query_category": "max_allowable_pressure"
}
```

`query_category` is optional. **When omitted, the endpoint derives it** from the query text
via `LLMService.classify_query_category` — a deterministic keyword classifier covering the six
safety-critical categories. Classifying server-side means the safety gate applies to every
caller (frontend, benchmark, anything added later) rather than only to callers that remember
to set it; previously nothing in the system set it, so the gate never fired.

When **every** provider tier fails and any returned `HTTP 429`, the response carries
`rate_limited: true` and a `message` naming the exhausted providers. An exhausted quota is an
operational limit with a fix, not the model being wrong — unlabelled the two are
indistinguishable, and a dead free tier reads as poor answer quality. (This is not
hypothetical: repeated benchmark runs exhausted the Gemini free tier and dragged measured
answer quality from 24/25 to 13/25 before the cause was visible.)

The refusal gate clears on **either** of two signals, and refuses only when both fail:

| Signal | Clears the gate when |
|---|---|
| Evidence confidence | any source has `confidence ≥ 0.7` |
| Source authority | any source has `authority_level ≤ 3` (regulatory / engineering / OEM) |

Both are needed because the hybrid-search and graph retrieval paths carry `authority_level`
but no `confidence` — a confidence-only gate read those as `0.0` and would refuse every
safety-critical query. On refusal the response carries `refused: true`, `answer: null`, and
the retrieved sources for direct verification.

Only **relevant, same-asset** evidence may clear the gate. An authoritative document about a
*different* asset cannot vouch for this answer — pass `relevance_score` on each context item to get
that tighter behaviour; context without it keeps the looser rule, so hand-assembled callers are not
silently re-scoped.

**The gate runs twice — once on the evidence, once on the result.** The pre-gate above cannot know
whether the model actually found the parameter. Observed live: a torque query for a non-existent
asset retrieved an unrelated authority-3 bulletin, cleared the pre-gate, and the model honestly
answered *"not specified in the provided source documents"* — which rendered as a **hedged
low-confidence answer**, the one outcome the architecture forbids for a safety-critical parameter.
So a synthesized answer whose *own* self-reported `CONFIDENCE:` is below threshold is converted into
a refusal. A response with no parse markers carries no self-assessment and is **not** refused —
a false refusal is its own safety failure, because it trains operators to route around the gate.

**Safety-critical categories (refusal when confidence < 0.7):**
`max_allowable_pressure` · `isolation_interlock_sequence` · `torque_specification` · `electrical_rating` · `pressure_relief_setting` · `safety_shutdown_setpoint`

**Response `200` — normal:**
```json
{
  "answer": "The maximum allowable working pressure for P-101 is 12.5 bar at 180°C, per OISD-117 Section 6.4.",
  "sources": [{"document_id": "doc-oisd-6.4", "authority_level": 1}],
  "confidence": 0.98,
  "refused": false,
  "safety_critical": true,
  "sources_used": [0],
  "uncertainty": "No post-2024 revision of OISD-117 §6.4 was found in the vault.",
  "model": "nim",
  "rate_limited": false,
  "pending_moc": []
}
```

`uncertainty` carries the model's own statement of what it could not establish; `rate_limited` is
`true` only when **every** provider tier returned HTTP 429 (see above). `model` names the provider tier
that actually answered — `nim` (Nemotron 3 Super 120B), `openrouter` (Llama 3.1 70B) or `gemini` — and
`served_model`, when present, is the exact model id the provider reported.

**`pending_moc` — the change-under-review warning.** Non-empty when an asset cited in the answer has
an open engineering-track conflict awaiting MoC sign-off. While a conflict sits in the MoC queue the
canonical graph is deliberately **not** updated, so the answer may be reporting a value that is under
formal dispute — architecture Layer 7 and Flow C both require the query to say so:

```json
"pending_moc": [
  {
    "conflict_id": "uuid",
    "asset_id": "HE-301",
    "parameter": "max_operating_pressure",
    "severity": "major",
    "moc_id": "MOC-A1B2C3D4",
    "moc_status": "pending_approval"
  }
]
```

Populated on refusals too, so a refusal that hands back source documents still discloses that those
documents are contested. The copilot renders it as a banner **above** the answer — after it, a
technician has already read the number. `moc_id` is null when a conflict is flagged but no MoC draft
has been raised yet.

*Scope:* currently returned by `POST /search/synthesize` only, not by `GET /search/` or
`POST /search/rca-pack`.

**Response `200` — refused:**
```json
{
  "answer": null,
  "refused": true,
  "refusal_reason": "Safety-critical parameter query refused: evidence confidence 0.35 is below threshold 0.70 for category max_allowable_pressure. Return sources directly.",
  "sources": [...],
  "safety_critical": true
}
```

An `audit_log` entry is written on every synthesis call.

---

### `POST /search/synthesize/stream`

Same answer as `POST /search/synthesize`, delivered progressively as Server-Sent Events. Identical
request body, and the terminal payload has the same shape as `SynthesizeResponse`.

A **separate** endpoint rather than a flag on the existing one: the `ANSWER:/CONFIDENCE:/…` parse
contract has two consumers (`routers/search.py`, `workflows/elicitation_workflow.py`) and a measured
answer-quality figure attached, so this adds a surface instead of altering one.

| Event | Meaning |
|---|---|
| `status` | Pipeline stage. `stage: "gating"`, then `stage: "synthesizing"` carrying `streaming_text` and, when false, a `reason` to display. |
| `delta` | A chunk of answer text — `{"text": "…"}`. **Never sent for a safety-critical category.** |
| `restart` | Discard everything received so far. The answer was re-synthesized by the fallback cascade; concatenating would splice two different answers. |
| `done` | Terminal, always sent. Same fields as `POST /search/synthesize`. |
| `error` | Terminal, only on unexpected failure. |

> **`done` is authoritative; `delta` text is provisional.** `CONFIDENCE:` arrives *after* `ANSWER:`,
> and the post-synthesis safety gate can convert a finished answer into a refusal based on it. The
> six `SAFETY_CRITICAL_CATEGORIES` therefore emit **no `delta` events at all** — they stream status
> only, so an operator is never shown a claim the gate is about to retract. A client must not render
> `delta` text as a final answer, and must drop it when `done` arrives.

Authorization is identical to `POST /search/synthesize` (both map to the `write_api` catch-all).
The response sets `X-Accel-Buffering: no`; without it a buffering proxy delivers the whole stream in
one write, which reproduces exactly the blank-screen wait this endpoint exists to remove.

```
event: status
data: {"stage": "synthesizing", "streaming_text": false, "reason": "Safety-critical category — the answer is withheld until the post-synthesis gate has cleared it."}

event: done
data: {"answer": "The maximum allowable pressure for HE-301 is 16.2 bar. [Source 1]", "refused": false, "safety_critical": true, ...}
```

---

### `POST /search/feedback`

Record the single-tap rating on a synthesized answer. Architecture Layer 12 Phase 2 treats this as
**direct input to outcome attribution and Layer 0 validation**, not UX research — it is the
trust-building mechanism the phase is built around.

**Auth required:** Yes

**Request body:**
```json
{
  "query": "What is the maximum allowable pressure for P-101?",
  "rating": "accurate",
  "note": "Matches the bulletin we have on file.",
  "sources_used": [0],
  "model": "nim"
}
```

`rating` must be one of `accurate` · `missing_context` · `incorrect`. `note`, `sources_used` and
`model` are optional.

**Response `200`:** `{"status": "recorded", "rating": "accurate"}`

Written to `audit_log` as action `synthesis_feedback`, alongside the `synthesis` row the query
already writes — no separate table. The copilot calls this fire-and-forget: a failed rating never
surfaces as an error over the answer, and the UI clears the selection rather than claiming a save
that did not happen.

---

### `POST /search/rca-pack`

**Layer 11 RCA synthesis.** Assembles a failure timeline, ranked hypotheses, and supporting documents for a specific asset incident.

**Auth required:** Yes

**Three parallel retrieval passes:**
1. **Neo4j** — Event nodes linked to the asset in a 90-day window (chronological timeline)
2. **Qdrant** — Semantic search on `failure_code + asset_class` against `kairos_knowledge`
3. **Supabase** — `operational_events` (work orders, alarms, PTWs) in the same 90-day window

Combined evidence is passed to `LLMService.rca_synthesize()`. Falls back to raw timeline + documents when LLM is unavailable.

**Safety-critical queries:** `refused=True` when the failure code matches a safety-critical category. Sources returned directly.

**Request body:**
```json
{
  "asset_id": "P-101",
  "incident_date": "2026-07-02T09:00:00Z",
  "failure_code": "SEAL-FAIL",
  "include_quarantine": false
}
```

**Response `200`:**
```json
{
  "asset_id": "P-101",
  "incident_date": "2026-07-02T09:00:00Z",
  "failure_code": "SEAL-FAIL",
  "timeline": [
    {
      "event_type": "vibration_alarm",
      "occurred_at": "2026-04-05T06:12:00",
      "description": "Elevated vibration on P-101",
      "source": "neo4j"
    }
  ],
  "hypotheses": [
    {
      "hypothesis": "Bearing wear caused by insufficient lubrication",
      "evidence_weight": 0.82,
      "sources": ["doc-p101-maint-record"]
    }
  ],
  "supporting_documents": [
    {
      "document_id": "doc-p101-failure-hist",
      "title": "P-101 Failure History",
      "authority_level": 2,
      "confidence": 0.91
    }
  ],
  "confidence": 0.85,
  "refused": false,
  "synthesis_available": true
}
```

- `synthesis_available: false` when NIM/Ollama is unavailable — timeline and documents still returned.
- `refused: true` with empty `hypotheses` when the failure code is safety-critical.
- Every call writes an `audit_log` entry with `action=rca_pack_generated`.

---

## 6. Events (Operational)

**Prefix:** `/events`

Event ingestion for CMMS work orders, Permit-to-Work, shift handovers, DCS alarms, equipment tag-outs, and inspections. All events:
1. Deduplicated via 10-minute Redis TTL key (same `asset_id` + `event_type`)
2. Written to `operational_events` (Supabase)
3. Published to the appropriate Redis Stream
4. Trigger brief assembly asynchronously

---

### `GET /events/`

Paginated operational-event feed (the `/events` workspace reads this).

| Param | Type | Default | Notes |
|---|---|---|---|
| `event_type` | string | — | Optional filter, e.g. `work_order_created` |
| `limit` | int | `50` | 1–200 |
| `offset` | int | `0` | ≥ 0 |

Ordered by `occurred_at` descending. Returns `event_id`, `event_type`, `event_subtype`, `asset_id`,
`site_id`, `occurred_at` and `payload` per item, with an exact `total`.

---

### `POST /events/work-order`

Ingest a CMMS work order.

**Auth required:** Yes

**Request body:**
```json
{
  "work_order_id": "WO-2024-001",
  "asset_id": "P-101",
  "failure_code": "VIBE-HIGH",
  "description": "Elevated vibration on feed pump",
  "priority": "high",
  "assigned_technician_id": "tech-uuid",
  "planned_start": "2024-01-02T08:00:00Z",
  "close_notes": null,
  "source_system": "SAP_PM",
  "site_id": "SITE_001",
  "occurred_at": "2024-01-01T22:00:00Z"
}
```

`close_notes` is populated when the WO is closed — used by the Celery attribution worker's execution compliance check.

`assigned_technician_id` is optional — if absent, brief is addressed site-wide.

**Side effects:**
- Recurring failure detection: if same asset had ≥1 prior WO in the last 90 days with the same failure family, `event_subtype=recurring` is set and a `recurring_failure_detected` event is published. A high-priority brief is assembled immediately.
- Attribution trigger: if same asset had a prior WO in the last 30 days, a Celery `evaluate_outcome` task is queued.
- Elicitation check: if failure code is rare, asset is uninstrumented, or priority is critical/urgent, a `MicroInterviewWorkflow` may be triggered on the `kairos-elicitation` queue.

**Response `202` — first event for asset:**
```json
{
  "event_id": "evt-uuid",
  "status": "accepted",
  "brief_task_id": "celery-task-uuid",
  "brief_due_in_seconds": 300,
  "stream_id": "1704067200000-0",
  "recurring_detected": false
}
```

Brief assembly is delayed by `LATE_ARRIVAL_WINDOW_MINUTES` (default 5 min) via `apply_async(countdown=...)` to allow correlated events to arrive first.

**Response `200` — duplicate within dedup window:** `{"event_id": "...", "status": "deduplicated"}`

---

### `POST /events/ptw`

Ingest a Permit-to-Work event.

**Auth required:** Yes

**Request body:**
```json
{
  "ptw_id": "PTW-2024-042",
  "work_area": "Pump Bay A",
  "asset_ids": ["P-101", "P-102"],
  "ptw_type": "hot_work",
  "issuing_engineer_id": "eng-uuid",
  "valid_from": "2024-01-02T06:00:00Z",
  "valid_to": "2024-01-02T18:00:00Z",
  "source_system": "PTW_System",
  "site_id": "SITE_001",
  "occurred_at": "2024-01-02T06:00:00Z"
}
```

PTW events always receive `priority: critical`. The EEMUA 191 governor always delivers PTW briefs regardless of push count. PTW handler also revokes any pending delayed WO brief for the same asset before assembling immediately.

**Response `202`:** Same shape as work order.

---

### `POST /events/shift-handover`

Ingest a shift handover event.

**Auth required:** Yes

**Request body:**
```json
{
  "outgoing_shift_lead_id": "lead-uuid-1",
  "incoming_shift_lead_id": "lead-uuid-2",
  "handover_time": "2024-01-02T06:00:00Z",
  "site_id": "SITE_001",
  "source_system": "DCS",
  "occurred_at": "2024-01-02T06:00:00Z"
}
```

**Response `202`:** Same shape.

---

### `POST /events/alarm`

Ingest an alarm acknowledgment.

**Auth required:** Yes (`field_worker` or higher — OPA exempts non-sensitive event writes)

**Request body:**
```json
{
  "alarm_id": "ALM-0042",
  "asset_id": "P-101",
  "alarm_tag": "P-101-VIBHI",
  "alarm_description": "Vibration high alarm — P-101 exceeds 4.5 mm/s",
  "severity": "high",
  "acknowledged_by": "tech-uuid",
  "source_system": "DCS",
  "site_id": "SITE_001",
  "occurred_at": "2024-01-01T22:05:00Z"
}
```

**Response `202`:** Same shape.

---

### `POST /events/tag-out`

Ingest an equipment tag-out event. Used when a physical tag-out (lockout/tagout) is applied to an asset.

**Auth required:** Yes

**Request body:**
```json
{
  "asset_id": "P-101",
  "tag_out_reason": "Planned maintenance — seal replacement",
  "performed_by": "tech-uuid",
  "expected_return_date": "2024-01-05T08:00:00Z",
  "source_system": "SAP_PM",
  "site_id": "SITE_001",
  "occurred_at": "2024-01-02T06:00:00Z"
}
```

**Side effects:**
- Inserts into `operational_events` and publishes to `kairos:events:tag_out` stream
- Writes `audit_log` entry with `action=equipment_tag_out`
- Triggers delayed brief assembly (same countdown as WO)

**Response `202`:**
```json
{
  "status": "accepted",
  "event_id": "evt-uuid",
  "stream_entry_id": "1704067200000-0",
  "brief_task_id": "celery-task-uuid",
  "brief_due_in_seconds": 300
}
```

---

### `POST /events/inspection-complete`

Ingest an inspection completion event. Optionally creates a Neo4j knowledge edge if a supporting document is provided. Low-confidence findings (<0.7) are automatically quarantined.

**Auth required:** Yes

**Request body:**
```json
{
  "asset_id": "P-101",
  "inspection_type": "visual",
  "result": "failed",
  "performed_by": "inspector-uuid",
  "findings": "Seal showing wear, recommend replacement within 30 days",
  "document_id": "DOC-INSP-P101-2024",
  "confidence": 1.0,
  "source_system": "SAP_PM",
  "site_id": "SITE_001",
  "occurred_at": "2024-01-02T10:00:00Z"
}
```

`result` values: `passed | failed | conditional`

**Side effects:**
- If `document_id` provided: creates `INSPECTION_RECORD` Neo4j edge with all 6 required properties
- If `confidence < 0.7`: inserts into `quarantine_items` with `input_type=field_observation`
- If `result = "failed"` or `findings` non-empty: triggers immediate brief assembly
- Correlates with other events for the same asset via `compound_event_id`
- Publishes to `kairos:events:inspections` (normal) or `kairos:events:work_orders` (failed/findings)

**Response `202`:**
```json
{
  "status": "accepted",
  "event_id": "evt-uuid",
  "stream_entry_id": "1704067200000-0",
  "edge_id": "neo4j-edge-id",
  "quarantine_item_id": null,
  "brief_task_id": "celery-task-uuid"
}
```

`edge_id` is `null` when no `document_id` was provided. `quarantine_item_id` is populated only when `confidence < 0.7`.

---

### `POST /events/deviation-flag`

Report a physical deviation from the last known state for an asset. Freezes all unacknowledged briefs for the asset until resolved. Carries a 24-hour SLA (overrides default 5-day quarantine SLA).

**Auth required:** Yes

**Request body:**
```json
{
  "asset_id": "P-101",
  "description": "Bypass valve observed open — not reflected in DCS state",
  "reported_by": "tech-uuid",
  "affected_topology_path": "P-101 → XV-101 → V-201"
}
```

**Response `202`:**
```json
{
  "item_id": "q-item-uuid",
  "asset_id": "P-101",
  "status": "quarantined",
  "briefs_frozen": 3,
  "stream_id": "1704067200000-0"
}
```

**Side effects:**
- Inserts item into `quarantine_items` with `input_type=deviation_flag` and `sla_due_at = NOW() + 24h`
- Sets `delivery_frozen=true` on all unacknowledged briefs for this asset
- Publishes to `kairos:events:alarms` stream
- Writes to `audit_log`

---

### `POST /events/deviation-flag/{item_id}/resolve`

Resolve a physical deviation flag. Unfreezes briefs and optionally creates an MoC record.

**Auth required:** Yes — `engineer` or `admin` (OPA enforced)

**Request body:**
```json
{
  "resolution": "promoted",
  "moc_warranted": true,
  "notes": "Bypass confirmed open per field inspection — MOC initiated"
}
```

`resolution` values: `promoted | disputed`

**Response `200`:**
```json
{
  "item_id": "q-item-uuid",
  "status": "resolved",
  "briefs_unfrozen": 3,
  "moc_id": "MOC-XXXXXXXX"
}
```

`moc_id` is only present when `moc_warranted=true`.

---

### `POST /events/plant-state`

Set the current plant operating state for a site. Non-critical briefs are suppressed during `turnaround`, `shutdown`, or `emergency` states.

**Auth required:** Yes — `engineer` or `admin`

**Request body:**
```json
{
  "site_id": "SITE_001",
  "state": "turnaround",
  "expires_at": null
}
```

`state` values: `normal | turnaround | shutdown | emergency`

`expires_at` (optional ISO8601 datetime) — if set, the state automatically reverts to `PLANT_STATE_DEFAULT` after this time.

**Response `202`:**
```json
{
  "status": "set",
  "site_id": "SITE_001",
  "state": "turnaround"
}
```

**Side effects:** Upserts `plant_operating_states` row; writes `audit_log` entry with `action=plant_state_changed`.

---

### `GET /events/plant-state/{site_id}`

Get the current plant operating state for a site.

**Auth required:** Yes

**Response `200`:**
```json
{
  "site_id": "SITE_001",
  "state": "turnaround"
}
```

Returns `PLANT_STATE_DEFAULT` (default: `"normal"`) if no state has been set or if the latest state has expired.

---

### `GET /events/{event_id}`

Get a single operational event with event correlation metadata.

**Auth required:** Yes

**Response `200`:**
```json
{
  "event_id": "evt-uuid",
  "event_type": "work_order_created",
  "asset_id": "P-101",
  "site_id": "SITE_001",
  "occurred_at": "2026-07-02T09:00:00Z",
  "payload": {},
  "compound_event_id": "compound-uuid",
  "correlated_event_ids": ["alarm-evt-uuid"]
}
```

`compound_event_id` and `correlated_event_ids` are set when this event was correlated with other same-asset events within `DEDUP_WINDOW_MINUTES`.

**`404`** if not found.

---

### `POST /events/{event_id}/ack`

Acknowledge receipt of an operational event.

**Auth required:** Yes

**Request body:**
```json
{
  "user_id": "tech-uuid",
  "role": "field_worker",
  "signature": "John Smith",
  "notes": "Acknowledged, will investigate"
}
```

**Response `200`:** `{"event_id": "...", "ack_recorded": true}`

---

## 7. Briefs (Operator Intelligence)

**Prefix:** `/briefs`

Operator intelligence briefs assembled from 5 parallel queries (Neo4j graph + Qdrant vectors + Elasticsearch + Supabase event history + regulatory graph). Governed by EEMUA 191: hard ceiling ≤6 push events/operator/hour, 4-hour asset cool-down per (recipient, asset) pair.

---

### `GET /briefs/`

Get pending briefs for the current user. Also returns site-wide briefs. Calls `record_push` per returned brief (counts against governor).

**Auth required:** Yes

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `unacknowledged_only` | bool | `true` | When true, filters to unacknowledged briefs only |
| `limit` | int | `10` | Max briefs (max 50) |

**Response `200`:**
```json
{
  "briefs": [
    {
      "brief_id": "brief-uuid",
      "recipient_user_id": "tech-uuid",
      "priority": "high",
      "trigger_event_type": "work_order_created",
      "headline": "P-101: Elevated vibration — 3 prior failures in 18 months",
      "body": "...",
      "action_items": ["Check coupling alignment", "Review last overhaul report"],
      "warnings": ["Active PTW in same area expires at 18:00"],
      "sources": [
        {
          "document_id": "DOC-P101-FAILURE-HIST",
          "document_type": "maintenance_record",
          "title": "P-101 Failure History Report",
          "authority_level": 2,
          "relevant_excerpt": "Three vibration-related failures in 18 months...",
          "vault_url": "https://...",
          "is_quarantine": false
        }
      ],
      "requires_countersignature": false,
      "delivery_frozen": false,
      "delivered_at": "2024-01-01T22:10:00Z"
    }
  ],
  "total_pending": 1,
  "suppressed_count": 0,
  "suppressed_held": [],
  "governor_state": {
    "push_count_last_hour": 1,
    "ceiling": 6,
    "state": "normal"
  },
  "next_delivery_allowed_at": null
}
```

**Suppression rules (in priority order):**
1. **EEMUA 191 governor:** If `push_count_last_hour >= ceiling`, all non-critical briefs suppressed.
2. **Plant state gate:** If plant state for the user's `site_id` is `turnaround`, `shutdown`, or `emergency`, non-critical briefs suppressed. Critical (PTW) briefs always pass.
3. **Frozen briefs:** Briefs with `delivery_frozen=true` (set by deviation flag) are included with `frozen=true` and `freeze_reason` but excluded from governor push counting.

**`suppressed_held` — what is being withheld, not just how many.** Carries the suppressed briefs
themselves (ranked, capped at `limit`), each tagged `suppressed: true` with a `suppression_reason`
of either `"Hourly push limit reached"` or `"Plant state — deliveries paused"`. `suppressed_count`
alone told an operator "3 held" with no way to judge whether the held one concerned their asset.

They are deliberately **not** in `briefs`: the handler records an EEMUA push for everything it
delivers, so folding them in would spend governor budget on briefs the governor is withholding — the
governor would end up suppressing its own disclosure. Withholding *delivery* is the point;
withholding *knowledge that something is withheld* is just an opaque counter.

---

### `GET /briefs/governor/status`

Get current push governor state for the authenticated user.

**Auth required:** Yes

**Response `200`:**
```json
{
  "user_id": "tech-uuid",
  "state": "normal",
  "push_count_last_hour": 3,
  "ceiling": 6,
  "next_delivery_allowed_at": null
}
```

`state` values: `normal | suppressed`

---

### `GET /briefs/{brief_id}`

Get a specific brief. Recipient-scoped: returns the brief only if it's addressed to the caller (`recipient_user_id == user_id`) **or to their site** (`recipient_user_id == site-{site_id}`) — otherwise `404`. Site-wide briefs (recipient `site-{site_id}`) are readable by any user at that site; without the site clause they were unopenable by anyone. Same scoping applies to `POST /briefs/{brief_id}/ack`.

**Auth required:** Yes

**Response `200`:** Full brief object. · **`404`** if not found or not addressed to the caller / their site.

---

### `POST /briefs/{brief_id}/ack`

Acknowledge a brief. Required for PTW briefs and any brief with `requires_countersignature: true`.

**Auth required:** Yes

**No request body.** The signer is the authenticated caller — accepting a `user_id` in the body
would let one user sign as another, which is exactly what an acknowledgment record must prevent.

For PTW briefs (`requires_countersignature: true`) this records the **first** signature only.
`acknowledged_at` is deliberately left null and the response status is `pending_countersignature` —
the brief is not complete until a second, distinct authority countersigns (see below).

**Response `200`:**
```json
{
  "brief_id": "...",
  "status": "acknowledged",
  "acknowledged_by": "tech-uuid",
  "signature": "9f2c…"
}
```

**`signature` is an HMAC-SHA256** over `brief_id | user_id | action | timestamp`, keyed by
`APP_SECRET_KEY` — the "cryptographically signed with the user's identity" requirement in
architecture Layer 8. It is stored in the immutable `audit_log` row (with `signature_alg`), not on
the `briefs` table, so the signed record lives where the audit trail already is and no schema
migration is needed. Changing any one bound fact produces a different signature, so an
acknowledgment captured on one brief cannot be replayed onto another.

---

### `POST /briefs/{brief_id}/countersign`

Second of the two signatures a PTW brief requires (architecture Flow B). Sets `acknowledged_at`,
because that is the moment both signatures exist.

**Auth required:** Yes — **reliability or admin** (OPA `can_countersign_brief`). Engineers
deliberately cannot countersign, so both signatures can never come from the issuing role.

**Request body:** none. Identity comes from the session, never a typed name.

**Rules enforced:**
- The countersigner must be a **different user** than `acknowledged_by` → `403`.
- The brief must already be acknowledged → `409`.
- Already countersigned → `409`. Not a PTW brief → `400`.
- **Not scoped by recipient.** The countersigner is by definition not the person the brief was
  delivered to; scoping this read by recipient made every countersign return `404`.

**Response `200`:**
```json
{
  "status": "acknowledged",
  "brief_id": "...",
  "acknowledged_by": "engineer-uuid",
  "countersigned_by": "reliability-uuid",
  "countersigned_at": "2026-08-16T09:12:00Z"
}
```

Writes its own HMAC to the `brief_countersigned` audit row, computed over the `countersigned`
action so it can never collide with the acknowledger's signature. The two signatures together are
the dual sign-off evidence for the permit.

---

### `POST /briefs/{brief_id}/feedback`

Submit feedback on brief accuracy.

**Auth required:** Yes

**Request body:**
```json
{
  "rating": "incorrect",
  "notes": "Pressure value shown is for a different vessel"
}
```

`rating` values: `accurate | missing_context | incorrect`

When `rating = "incorrect"`: writes `confidence_recheck_queued` to `audit_log` with `source_document_ids`.

**Response `200`:** `{"brief_id": "...", "feedback_recorded": true, "confidence_recheck_queued": true}`

---

## 8. Governance

**Prefix:** `/governance`

Knowledge conflict detection, quarantine management, Management of Change, SLA tracking, circuit breaker, validation corpus, and model gate.

---

### `GET /governance/conflicts`

List open knowledge conflicts. Runs lazy SLA escalation before returning results.

**Auth required:** Yes (`engineer`, `admin`, `reliability`)

**Query params:** `status` (`open | pending_moc | resolved | all`, default `open`), `track` (`administrative | engineering`), `asset_id`, `include_non_asserting` (bool, default `false`), `limit`, `offset`

Conflicts whose `parameter` is a **provenance or structural** relationship type
(`GraphService.NON_ASSERTING_RELATIONSHIPS` — `DOCUMENTED_BY`, `MENTIONS_PERSON`,
`MENTIONS_ORGANISATION`, `CONTAINS_TOPOLOGY_ELEMENT`) are excluded by default. Two documents
describing one asset is what an archive *is*, not a contradiction. `detect_conflict` no longer
creates them; rows written before that guard are filtered here, **in the query** — `count` and
`range` are computed by PostgREST, so filtering in Python would report a total the page can never
reach. `include_non_asserting=true` returns them.

Note the shape difference this exposes: only conflicts that record an actual disagreement carry
`value` on their sources. Auto-detected conflicts never did, because a `KNOWLEDGE_EDGE` has no
value property to compare — which is precisely why they should not have been conflicts.

**Response `200`:**
```json
{
  "items": [
    {
      "conflict_id": "conf-uuid",
      "track": "engineering",
      "asset_id": "P-101",
      "parameter": "max_allowable_pressure",
      "source_a": {"document_id": "doc-a", "value": "12.5 bar", "authority_level": 1},
      "source_b": {"document_id": "doc-b", "value": "15.0 bar", "authority_level": 2},
      "severity": "critical",
      "status": "open",
      "sla_due_at": "2024-01-06T00:00:00Z",
      "is_overdue": false,
      "escalated_at": null,
      "detected_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

Conflict tracks — assigned by `detect_conflict`, not by the shape of the disagreement:
- `engineering` — the new edge is authority **≤ 3** *and* the parameter name contains a
  safety-critical keyword (`pressure`, `temperature`, `inspection`, `isolation`, `material`).
  24 h SLA, resolvable only through the MoC webhook.
- `administrative` — everything else. 5-day SLA, resolvable in-app via
  `POST /governance/conflicts/{id}/resolve`.

`sla_due_at` maps to the existing `sla_deadline` column. `is_overdue` is computed inline. `escalated_at` is populated when SLA escalation fires.

---

### `GET /governance/conflicts/{conflict_id}`

Get conflict detail + blast-radius report.

**Auth required:** Yes

**Response `200`:** Full conflict object + `blast_radius: [{"asset_id": ..., "affected_facts": 5}]`

---

### `POST /governance/conflicts/{conflict_id}/resolve`

Resolve an administrative-track conflict. Engineering-track conflicts must be resolved via `POST /governance/moc/webhook`.

**Auth required:** Yes — `admin` or `engineer` (OPA enforced)

**Request body:**
```json
{
  "resolution": "accept_source_a",
  "notes": "OISD-117 takes precedence per engineering manager sign-off",
  "resolved_by": "admin@kairos.local"
}
```

**Response `200`:** `{"conflict_id": "...", "status": "resolved"}`

---

### `GET /governance/quarantine`

List items in the quarantine layer. Runs lazy SLA escalation before returning results.

**Auth required:** Yes

**Query params:** `asset_id`, `reviewer_id`, `review_status` (`pending | promoted | disputed | archived`), `limit`, `offset`

Default `review_status` is `pending`.

**Response `200`:**
```json
{
  "items": [
    {
      "item_id": "q-uuid",
      "asset_id": "P-101",
      "content": "Seal clearance 0.15mm from voice note",
      "input_type": "voice_note",
      "submitted_by": "tech-uuid",
      "review_status": "pending",
      "session_context": null,
      "sla_due_at": "2024-01-06T00:00:00Z",
      "is_overdue": false,
      "escalated_at": null,
      "quarantined_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0,
  "note": "All items are unverified field inputs — not reviewed by engineering authority."
}
```

Items enter quarantine when `confidence < 0.7` or entity resolution fails. `sla_due_at` defaults to `NOW() + 5 days`; deviation flags override to `NOW() + 24h`.

---

### `POST /governance/quarantine/{item_id}/promote`

Promote a quarantine item to the canonical graph. **Human action only — no auto-promotion, ever.**

**Auth required:** Yes — `reliability` or `admin` only (OPA `can_promote_quarantine`; `engineer` and `field_worker` get 403). The frontend hides the Promote button accordingly (`PROMOTE_ROLES`).

**Request body:**
```json
{
  "promoted_by": "reliability@kairos.local",
  "notes": "Verified against P&ID Rev D",
  "authority_level": 3,
  "valid_from": "2024-01-01T00:00:00Z"
}
```

On promotion, `detect_conflict()` runs. If a conflict is detected, `kairos.conflicts.open` metric increments.

**Response `200` — no conflict:**
```json
{
  "item_id": "q-uuid",
  "status": "promoted",
  "conflict_detected": false,
  "edge_id": "neo4j-edge-id"
}
```

**Response `200` — conflict detected:**
```json
{
  "item_id": "q-uuid",
  "status": "promoted",
  "conflict_detected": true,
  "conflict_id": "conf-uuid",
  "conflict_track": "engineering"
}
```

**Errors — shared by all four quarantine-by-id routes** (`promote`, `dispute`, `request-info`, and
`POST /events/deviation-flag/{item_id}/resolve`, which reads the same table):

| Status | When |
|---|---|
| `404` | No such item — **including a malformed `item_id`.** `quarantine_items.item_id` is a `UUID` column, so a non-UUID path segment made PostgREST raise `22P02` before the handler's own 404 branch was reached, and the global handler turned that into a **500**. `dependencies.valid_quarantine_item_id` now rejects it up front. 404 rather than 422 on purpose: to a reviewer a malformed id and an absent one are the same situation, and splitting one outcome across two status codes on id *shape* would leak the column type into the API contract. |
| `409` | The item is no longer `pending` (already promoted, disputed, or archived). |
| `400` | The item has no `asset_id`, so it cannot be linked to the graph (promote only). |

---

### `POST /governance/quarantine/{item_id}/dispute`

Mark a quarantine item as incorrect. Prevents accidental promotion.

**Auth required:** Yes

**Request body:** `{"disputed_by": "engineer@kairos.local", "reason": "Value is for V-201, not P-101"}`

**Response `200`:** `{"item_id": "...", "status": "disputed"}`

---

### `POST /governance/quarantine/{item_id}/request-info`

Layer 6's fourth review action — a reviewer asks for clarification instead of promoting or disputing. The item stays `pending` (still actionable); the request + note are recorded to the audit log (`action=info_requested`).

**Auth required:** Yes (same gate as promote — `reliability`/`admin`)

**Request body:** `{"note": "Which seal face — inboard or outboard?"}`

**Response `200`:** `{"item_id": "...", "status": "info_requested", "note": "..."}`

**Errors:** `404` item not found · `409` item is not `pending`

---

### `GET /governance/sla-report`

SLA escalation report for all overdue conflicts and quarantine items. Runs lazy escalation then returns full overdue inventory.

**Auth required:** Yes

**Response `200`:**
```json
{
  "checked_at": "2024-01-06T12:00:00Z",
  "escalated_this_run": {
    "conflicts": 1,
    "quarantine_items": 0
  },
  "overdue_conflicts": [
    {
      "conflict_id": "conf-uuid",
      "track": "engineering",
      "asset_id": "P-101",
      "sla_deadline": "2024-01-05T00:00:00Z",
      "escalated_at": "2024-01-06T12:00:00Z",
      "status": "open"
    }
  ],
  "overdue_conflicts_total": 1,
  "overdue_quarantine_items": [],
  "overdue_quarantine_total": 0
}
```

Escalation is idempotent — `escalated_this_run` is 0 on subsequent calls for already-escalated items.

---

### `GET /governance/moc`

List Management of Change records.

**Auth required:** Yes

**Query params:** `status` (`draft | pending_approval | approved | rejected`)

**Response `200`:**
```json
{
  "items": [...],
  "total": 3
}
```

---

### `GET /governance/moc/{moc_id}`

Get one MoC item enriched for the detail view. The `moc_items` table stores only the linkage; `parameter`, `source_a`, and `source_b` are joined from the linked `knowledge_conflicts` row, and `blast_radius_count` is computed from the affected document's graph traversal (best-effort).

**Auth required:** Yes

**Response `200`:**
```json
{
  "moc_id": "MOC-2024-007",
  "asset_id": "EQ-101",
  "parameter": "max_allowable_pressure",
  "source_a": { "value": "1200 psi", "document_id": "DOC-...", "edge_id": "..." },
  "source_b": { "value": "1400 psi", "document_id": "DOC-..." },
  "blast_radius_count": 3,
  "status": "pending",
  "created_at": "2024-02-20T10:00:00Z",
  "draft_content": "..."
}
```

**Response `404`:** `{"detail": "MoC '<id>' not found"}`

---

### `POST /governance/moc/{moc_id}/approve`

In-app MoC sign-off (engineer/admin authority — mirrors OPA `can_resolve_moc`). Marks the MoC approved, closes the superseded edge's validity window, and resolves the linked engineering-track conflict — the same effect as an approved MoC webhook, human-initiated. Shares the conflict-closing helper with the webhook path.

**Auth required:** Yes (`engineer` or `admin`)

**Request body:** `{ "note": "optional engineer note" }`

**Response `200`:** `{"status": "approved", "moc_id": "..."}`

**Response `409`:** `{"detail": "MoC already approved."}` · **`404`:** `{"detail": "MoC '<id>' not found"}`

---

### `POST /governance/moc/webhook`

Receive an MoC resolution webhook from the plant MoC system.

**Auth required:** Yes (`admin` or service key)

Optionally verifies HMAC-SHA256 signature via `X-Webhook-Signature` header when `MOC_WEBHOOK_SECRET` is configured.

**Request body:**
```json
{
  "moc_id": "MOC-2024-007",
  "status": "approved",
  "approved_by": "chief.engineer@plant.com",
  "effective_date": "2024-03-01T00:00:00Z"
}
```

`status` values: `approved | rejected`

On `approved`: closes the old validity window on the conflicting Neo4j edge and resolves the linked `knowledge_conflicts` row.

**Response `200`:** `{"status": "received", "moc_id": "...", "resolution": "approved"}`

---

### `GET /governance/circuit-breaker`

Get the current SPC circuit breaker state for all monitored entity types.

**Auth required:** Yes

One state per **asset class** that has recorded extraction overrides in the last 30 days. An asset class trips to `halted: true` when its 7-day override-count z-score exceeds 2.0; new extractions for that class are then queued for human review rather than written to the graph. An empty `states` array means no class has any override records yet (all ingestion paths open).

**Response `200`:**
```json
{
  "states": [
    {
      "asset_class": "pump",
      "halted": false,
      "z_score": 1.2,
      "reason": "within_normal_range",
      "override_count_7d": 3
    }
  ],
  "halted_count": 0
}
```

> ⚠️ Each state carries `asset_class` + boolean **`halted`** (not `entity_type` / a `status` string).
> `reason` is `z_score_exceeded | within_normal_range | stats_error`. There is no `override_rate`,
> `total_extractions_7d`, or `threshold` field.

---

### `GET /governance/blast-radius/{document_id}`

Get the blast-radius report for a proposed document change.

**Auth required:** Yes

**Response `200`:**
```json
{
  "document_id": "DOC-TS4FXYKHCQEF",
  "affected_count": 11,
  "affected": [
    {
      "edge": {
        "relationship_type": "DOCUMENTED_BY",
        "edge_id": "PG-18_DOCUMENTED_BY_DOC-…_2026-07-17T20:37:03Z",
        "authority_level": 5,
        "confidence": 0.9,
        "verification_status": "unverified",
        "valid_from": "2026-07-17T20:37:03Z",
        "valid_to": "9999-12-31T23:59:59Z",
        "document_id": "DOC-…"
      },
      "source": {
        "asset_id": "PG-18",
        "name": "Local Gauge Bypass",
        "equipment_class": "instrument_bypass"
      },
      "target": {
        "document_id": "DOC-…",
        "document_type": "shift_log"
      }
    }
  ]
}
```

> ⚠️ Each pair is `{edge, source, target}` + `affected_count`. **The affected entity is the edge `source`**
> (e.g. the asset whose knowledge derives from this document); `target` is usually the document node itself.
> Results are **deduped by `edge_id`** server-side (re-runs can leave duplicate relationships). Nodes are
> heterogeneous graph nodes; read a label from `source.name ?? source.tag_number ?? source.asset_id`.
> The frontend `getBlastRadius` fetcher flattens each pair into `{item_id, item_type, description,
> asset_id, flagged_for_review}` (flagged = edge `verification_status != "verified"`).

---

### `GET /governance/validation-corpus/stats`

Return validation corpus coverage statistics used by the model gate.

**Auth required:** Yes

**Response `200`:**
```json
{
  "total_corpus_size": 42,
  "by_entity_type": {
    "ASSET_TAG": 18,
    "process_parameter": 12,
    "FAILURE_MODE": 12
  },
  "last_updated_at": "2024-01-05T09:00:00Z"
}
```

The corpus is populated automatically when quarantine items are promoted (`authority=human_promotion`) or when annotations with `is_correct=True` are submitted (`authority=annotation_correction`).

---

### `POST /governance/model-gate/run`

Trigger NER model gate evaluation against the validation corpus.

**Auth required:** Yes — `admin` only

**Query params:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `model_name` | string | No | NER model to evaluate. **Defaults to `NVIDIA_NIM_NER_MODEL`** when omitted, so the UI can trigger a run without knowing the model name. |

**Response `200`:**
```json
{
  "task_id": "celery-task-uuid",
  "model_name": "meta/llama-3.2-11b-vision-instruct",
  "status": "queued"
}
```

The endpoint only **enqueues** the task and returns immediately. The Celery task runs on the `validation` queue and takes **~12 min** on the 52-row corpus (one NIM call per unique document; the three partition cuts share a cache and add none). `time_limit`/`soft_time_limit` are 1860/1800 — the earlier 600/540 was calibrated on a run where nearly every call failed fast on a 429, and killed two real runs mid-flight. Results are written to `audit_log` with `action=model_gate_result`. The gate compares F1 against the incumbent baseline; if lower, the run is marked `failed`. The UI polls `history` and auto-refreshes when the run lands.

---

### `GET /governance/model-gate/history`

Return the last 20 model gate run results.

**Auth required:** Yes

**Response `200`:**
```json
{
  "items": [
    {
      "id": "uuid",
      "entity_id": "meta/llama-3.2-11b-vision-instruct",
      "details": {
        "model_name": "meta/llama-3.2-11b-vision-instruct",
        "precision": 0.7234,
        "recall": 0.85,
        "f1": 0.7816,
        "passed": true,
        "validity": "VALID",
        "fallback_extractions": 0,
        "extraction_paths": {"nim": 27},
        "corpus_size": 52,
        "scored_labels": 40,
        "unscoreable_labels": 12,
        "unscoreable_by_type": {"COMPONENT": 12},
        "by_entity_type": {"ASSET_TAG": {"precision": 1.0, "recall": 0.8333, "f1": 0.9091, "count": 30}},
        "by_asset_class": {"he-3xx_series": {"precision": 1.0, "recall": 0.9, "f1": 0.9474, "corpus_size": 10}},
        "by_document_type": {"oem_manual": {"precision": 0.4615, "recall": 0.8571, "f1": 0.6, "corpus_size": 7, "scored_labels": 7}},
        "enforcement": "advisory_only",
        "regressed_asset_classes": [],
        "blocked_asset_classes": []
      },
      "timestamp": "2026-08-23T09:05:00Z"
    }
  ],
  "total": 1
}
```

> Shape is **contract-locked** to `{items, total}` (raw `audit_log` rows) by `tests/test_contract.py` and `tests/test_governance.py`. The frontend `getModelGateHistory` adapter flattens each row's `details` into the UI `ModelGateResult` shape and returns `{ history: [...] }`.

**Reading a run — three fields decide whether the score means anything.**

- **`validity`** — `"VALID"` only when every extraction reached the model. The NER service degrades
  to a regex last resort that emits `ASSET_TAG` and nothing else, so a `"SUSPECT"` run is scoring
  the fallback under the model's name. **A run without `validity: "VALID"` is not a measurement.**
  Entries written before 2026-08-23 have no `validity` key at all and must not be quoted; only a
  `VALID` run is eligible to serve as the baseline a later run is compared against.
- **`scored_labels` vs `corpus_size`** — `f1` covers `scored_labels`, not the whole corpus. Ground
  truth whose `entity_type` is outside the extractor's 10-type prompt taxonomy cannot be scored
  against it and is reported in `unscoreable_by_type` instead of counted as failure. Quote the F1
  with its denominator.
- **`passed`** — means "no regression against the baseline", and is orthogonal to `validity`. With
  no eligible baseline it is `true` by default, which is a fresh-install state rather than a pass.

`by_document_type` is the cut the problem statement asks for and costs no extra model calls: all
three partitions share the run's extraction cache.

---

### `GET /governance/push-volume-gate`

EEMUA 191 pilot monitoring gate — the architecture's Phase 3 precondition.

Computes **peak** per-operator-per-hour push volume over a rolling window (an average would hide
exactly the bursts EEMUA 191 exists to prevent).

**`enforcement: "advisory_only"` — this never blocks Phase 3 at runtime.** A deployment with under
30 days of history would otherwise be unable to deliver briefs at all, which is a worse failure than
the one it prevents. Phase activation stays a deliberate `KAIROS_PHASE` decision, informed by this.

**Response `200`:** `{window_days, ceiling_per_operator_per_hour, peak_per_operator_per_hour, breach_count, breaches[], briefs_delivered, within_eemua_norms, current_phase, enforcement}`

---

### `GET /governance/timestamp-drift`

Cross-source clock drift (Layer 4). Compares the **same correlated event as reported by different
source systems**, reusing the `compound_event_id` grouping Layer 8 already builds.

> Deliberately **not** `occurred_at` vs `ingested_at` — a document that occurred months before it was
> ingested is history, not skew, and that comparison would flag an entire golden corpus.

Report-only while `TIMESTAMP_DRIFT_ENFORCE=false`: drift is surfaced but opens no conflict row.

**Response `200`:** `{compound_events_checked, drift_detected_count, tolerance_minutes, enforcement, items[]}`

---

## 9. Compliance

**Prefix:** `/compliance`

Regulatory gap detection against 12 seeded frameworks (OISD-117, ISO 45001, and 10 others). Seed via `docker exec kairos-backend-api python scripts/seed_regulations.py`.

---

### `GET /compliance/gaps`

Evaluates every applicable (clause × asset) pair and returns the ones that are not
cleared. A clause is **covered** for an asset when the asset has an active, non-superseded
edge to a Document of the evidence type that clause requires (`requires_document_type`,
seeded per clause in `scripts/seed_regulations.py`).

Two kinds of finding are returned:

| `status` | Meaning |
|---|---|
| `gap` | No document of the required type is linked to the asset |
| `unverified_evidence` | Such a document exists, but no human has verified the edge |

Covered pairs are not returned. `severity` derives from the clause's `authority_level`:
level 1 → `critical`, level 2 → `major`, everything else → `minor`.

**Auth required:** Yes (`compliance` or `admin`)

**Query params:** `asset_id`, `framework`, `severity` (`critical | major | minor`),
`status` (`gap | unverified_evidence`), `limit` (≤500), `offset`

**Response `200`:**
```json
{
  "items": [
    {
      "concept_id": "OISD-117-4.1.1",
      "framework": "OISD_117",
      "clause_id": "4.1.1",
      "requirement_text": "Rotating equipment (pumps) shall have documented maintenance procedures...",
      "applies_to": "pump",
      "requires_document_type": ["procedure"],
      "authority_level": 1,
      "asset_id": "EQ-103",
      "tag_number": "EQ-103",
      "equipment_class": "rotating_centrifugal_pump",
      "site_id": "SITE-1",
      "evidence_count": 0,
      "verified_count": 0,
      "status": "gap",
      "severity": "critical"
    }
  ],
  "total": 52,
  "gap_total": 37,
  "unverified_total": 15,
  "limit": 100,
  "offset": 0,
  "framework": null,
  "last_scan": "realtime"
}
```

> Accuracy of this endpoint is measured by `benchmark/run_compliance_eval.py`, which scores
> gap precision/recall against ground truth derived independently from the dataset manifest.

---

### `GET /compliance/dashboard`

Compliance posture summary: counts by framework, severity and equipment class.

`total_gaps` counts only true gaps (no evidence of the required type).
`total_unverified_evidence` counts pairs where evidence exists but is unverified —
conflating the two is what previously made every clause read as non-compliant.
`by_framework` / `by_asset_class` break down gaps only.

**Auth required:** Yes (`compliance` or `admin`)

**Response `200`:**
```json
{
  "site_id": null,
  "total_gaps": {"critical": 12, "major": 40, "minor": 0},
  "total_unverified_evidence": {"critical": 3, "major": 12, "minor": 0},
  "by_framework": {
    "OISD_117": {"critical": 12, "major": 0, "minor": 0},
    "ISO_45001": {"critical": 0, "major": 40, "minor": 0}
  },
  "by_asset_class": {
    "pump": {"critical": 6, "major": 0, "minor": 0},
    "valve": {"critical": 6, "major": 0, "minor": 0}
  },
  "last_updated": "realtime"
}
```

> ⚠️ **`total_gaps` is an object `{critical, major, minor}`, not a number.** Severity buckets are
> `critical | major | minor` (not `high/medium`). `by_framework` and `by_asset_class` are keyed by
> those same severity buckets. There are no `cleared` / `open` / `by_severity` fields. Sum the three
> buckets to get a grand total; never render `total_gaps` directly.

---

### `GET /compliance/audit-pack`

Generate an audit evidence package (all gaps + evidence + clearance status).

**Auth required:** Yes (`compliance` or `admin`)

**Query params:** `framework` (optional filter)

**Response `200`:**
```json
{
  "generated_at": "2024-01-01T00:00:00Z",
  "framework": "OISD-117",
  "total_clauses": 24,
  "covered": 14,
  "clearance_blocked": false,
  "evidence": [
    {
      "clause_id": "6.4.2",
      "status": "covered",
      "document_id": "doc-oisd-evidence",
      "clearance_blocked": false
    }
  ]
}
```

---

### `GET /compliance/frameworks`

List all configured regulatory frameworks.

**Auth required:** Yes

**Response `200`:**
```json
[
  {
    "framework_id": "OISD-117",
    "name": "OISD Standard 117 — Inspection of Pressure Vessels",
    "clause_count": 24,
    "equipment_classes": ["vessel", "pressure_vessel"]
  }
]
```

---

## 10. Elicitation

**Prefix:** `/elicitation`

Knowledge gap elicitation via AI-generated micro-interviews and off-boarding programmes. Micro-interview responses and off-boarding responses are stored in `quarantine_items` for human review before graph promotion.

---

### `POST /elicitation/trigger`

Evaluate whether elicitation should be triggered. Three conditions trigger it:
1. Failure code not seen in the last 6 months for this asset
2. Asset has no knowledge graph edges (uninstrumented)
3. Work order priority is `critical` or `urgent`

**Auth required:** Yes

**Request body:**
```json
{
  "work_order_id": "WO-2024-001",
  "asset_id": "P-101",
  "failure_code": "SEAL-LEAK-EXT",
  "priority": "high"
}
```

**Response `200` — triggered:**
```json
{
  "work_order_id": "WO-2024-001",
  "triggered": true,
  "reason": "rare_failure_code",
  "session_id": "session-uuid",
  "workflow_id": "temporal-workflow-id"
}
```

**Response `200` — not triggered:** `{"triggered": false, "reason": "failure_code_seen_recently"}`

---

### `GET /elicitation/{work_order_id}/questions`

Get generated interview questions (available after workflow reaches `status=questions_ready`).

**Auth required:** Yes

**Response `200`:**
```json
{
  "work_order_id": "WO-2024-001",
  "status": "questions_ready",
  "questions": [
    "The previous two failures on this asset were attributed to lubrication intervals. Did the component condition suggest a different root cause this time?",
    "Were there operating changes in the days before the leak was noticed?"
  ]
}
```

> **Questions are a plain `string[]`**, not objects. Corrected 2026-08-16 — this block previously
> showed `{question_id, text, type}` objects, which the endpoint has never returned. The question
> *text* is therefore the identifier when submitting answers (see `POST …/responses` below).

An empty `questions` array means the Temporal workflow is still generating them — it makes a model
call per session, so poll rather than treating the first empty response as "no questions".

Returns `404` if no session exists yet. Sessions are **event-triggered** (`POST /elicitation/trigger`);
there is no session for an arbitrary work order id.

---

### `POST /elicitation/{work_order_id}/responses`

Submit Q&A responses. Stored in `quarantine_items` for expert review before graph promotion.

**Auth required:** Yes

**Request body:**
```json
{
  "responses": [
    {"question": "Did the bearing housing show thermal cycling?", "answer": "Yes — discolouration on the outboard face."},
    {"question_index": 1, "answer": "Shares the discharge header with EQ-102."}
  ],
  "submitted_by": "field_worker@kairos.local"
}
```

Questions are a `string[]`, so the question **text** is the identifier. `question_index` is
accepted as an alternative for callers holding the position instead; supply one or the other.
`submitted_by` is **optional** — it defaults to the authenticated user, matching
`POST /elicitation/offboarding/{session_id}/responses`.

> Corrected 2026-08-16. This block previously documented `session_id` and `question_id`, neither of
> which the endpoint has ever accepted. The request model was also an untyped `list[dict[str, str]]`,
> so a caller passing an integer got `"Input should be a valid string"` pointing at a key they had
> invented, with nothing indicating the real one. It is now a typed `ElicitationAnswer` model.

**Response `200`:**
```json
{
  "item_id": "q-item-uuid",
  "status": "quarantined"
}
```

Responses land in **quarantine**, never the canonical graph — elicitation output requires human
promotion (architecture Layer 9). The question context is stored alongside the answers so a
reviewer can see exactly what was asked.

---

### `POST /elicitation/{work_order_id}/voice`

Submit a voice note for a work order. Transcribed via Groq Whisper, NER extracted, stored as a `quarantine_items` entry.

**Auth required:** Yes

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | binary | Yes | Audio file (WAV, MP3, M4A, FLAC) |
| `submitted_by` | string | Yes | User ID of submitter |

**Processing pipeline:**
1. SHA-256 dedup check — returns existing item if same audio file submitted twice
2. Upload to Supabase Storage (`kairos-vault` bucket)
3. Celery task on `transcription` queue → Groq `whisper-large-v3` transcription
4. NER extraction on transcript text
5. Insert into `quarantine_items` with `input_type=voice_note`

**Response `202`:**
```json
{
  "status": "accepted",
  "work_order_id": "WO-2024-001",
  "task_id": "celery-task-uuid",
  "storage_path": "voice_notes/WO-2024-001/abc12345_note.wav",
  "sha256": "abc123...",
  "message": "Voice note stored. Transcription and NER running asynchronously."
}
```

---

### `POST /elicitation/offboarding`

Start an off-boarding interview programme for a departing employee. Identifies the top equipment families from the employee's work order history (up to 6), creates one session item per family, and schedules a Celery task to generate questions for each.

**Auth required:** Yes — `engineer` or `admin`

**Request body:**
```json
{
  "personnel_id": "tech-uuid",
  "personnel_email": "john.smith@plant.com",
  "retirement_date": "2024-06-30",
  "session_interval_days": 12
}
```

`session_interval_days` — spacing between successive interview sessions (default 12).

**Response `201`:**
```json
{
  "session_id": "session-uuid",
  "personnel_id": "tech-uuid",
  "total_sessions": 6,
  "items": [
    {
      "item_id": "item-uuid",
      "session_number": 1,
      "equipment_family": "centrifugal_pump",
      "scheduled_for": "2024-01-01T00:00:10Z"
    }
  ]
}
```

Session 1 fires in 10 seconds (demo/test). Subsequent sessions are spaced by `session_interval_days`.

---

### `GET /elicitation/offboarding`

List all active off-boarding programmes with completion percentage.

**Auth required:** Yes

**Response `200`:**
```json
{
  "items": [
    {
      "id": "session-uuid",
      "personnel_id": "tech-uuid",
      "personnel_email": "john.smith@plant.com",
      "retirement_date": "2024-06-30",
      "total_sessions": 6,
      "status": "scheduled",
      "sessions_completed": 1,
      "completion_pct": 17,
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

---

### `GET /elicitation/offboarding/{session_id}`

Get a specific off-boarding programme with all session items and their statuses.

**Auth required:** Yes

**Response `200`:**
```json
{
  "id": "session-uuid",
  "personnel_id": "tech-uuid",
  "personnel_email": "john.smith@plant.com",
  "retirement_date": "2024-06-30",
  "total_sessions": 6,
  "status": "scheduled",
  "session_items": [
    {
      "id": "item-uuid",
      "session_number": 1,
      "equipment_family": "centrifugal_pump",
      "status": "completed",
      "scheduled_for": "2024-01-01T00:00:10Z",
      "completed_at": "2024-01-01T00:05:00Z"
    }
  ]
}
```

**`404`** if not found — including when `{session_id}` is not a well-formed UUID.

> **`{session_id}` is validated before the query runs** (`dependencies.valid_offboarding_session_id`,
> a sibling of `valid_quarantine_item_id`). `offboarding_sessions.id` is a UUID column, so an
> unparseable segment previously reached PostgREST as `22P02` and surfaced as a **500** on a public
> route — `GET /elicitation/offboarding/sessions` was the reported case, since there is no
> `/sessions` route and the literal was matched by `/{session_id}`. A well-formed id for an absent
> programme 500'd too, because `.single()` raises `PGRST116` on zero rows and left each handler's
> own 404 unreachable; the handlers use `.maybe_single()`. Both halves apply to all three
> `/{session_id}` routes. Fixed 2026-08-23, pinned by `tests/test_offboarding_session_id.py`.

---

### `GET /elicitation/offboarding/{session_id}/questions`

Return questions for all session items in this programme (items with `status=questions_ready`).

**Auth required:** Yes

**Response `200`:**
```json
{
  "session_id": "session-uuid",
  "total_items": 6,
  "items_ready": 1,
  "items": [
    {
      "id": "item-uuid",
      "session_number": 1,
      "equipment_family": "centrifugal_pump",
      "status": "questions_ready",
      "questions": ["..."],
      "scheduled_for": "2024-01-01T00:00:10Z"
    }
  ]
}
```

---

### `POST /elicitation/offboarding/{session_id}/responses`

Submit responses for one session item. Stores in `quarantine_items` with `input_type=offboarding_response`.

**Auth required:** Yes

**Request body:**
```json
{
  "item_id": "item-uuid",
  "responses": [
    {"question_index": 0, "answer": "I check the mechanical seal weekly for any signs of leakage"},
    {"question_index": 1, "answer": "The most common failure is bearing wear, usually after 18 months"}
  ],
  "submitted_by": "tech-uuid"
}
```

`question_index` is an integer (0-based). `submitted_by` defaults to the current user if omitted.

**Response `200`:**
```json
{
  "session_id": "session-uuid",
  "item_id": "item-uuid",
  "quarantine_item_id": "q-item-uuid",
  "status": "completed",
  "message": "Responses stored in quarantine for expert review"
}
```

---

## 11. Annotations

**Prefix:** `/annotations`

Active learning annotation interface. Allows human reviewers to correct NER extraction errors. Each correction reduces the confidence of the associated quarantine item by 0.1 and is logged for circuit breaker monitoring.

---

### `POST /annotations/`

Submit a NER correction annotation.

**Auth required:** Yes (`engineer` or `admin`)

**Request body:**
```json
{
  "document_id": "doc-uuid",
  "entity_type": "process_parameter",
  "original_value": "12.5 bar",
  "corrected_value": "15.0 bar",
  "is_correct": false,
  "notes": "Wrong vessel — this value applies to V-201, not P-101"
}
```

**Side effects:**
- Inserts annotation into `ner_annotations`
- If `is_correct=false`: reduces `quarantine_items.confidence` by 0.1 for any pending quarantine item with matching `document_id` + `entity_type`; writes `audit_log` entry with `action=confidence_recheck_queued`; records a circuit breaker override for the entity type
- If `is_correct=true`: adds to `validation_corpus` with `authority=annotation_correction`

**Response `201`:**
```json
{
  "annotation_id": "ann-uuid",
  "document_id": "doc-uuid",
  "entity_type": "process_parameter",
  "is_correct": false,
  "quarantine_confidence_updated": true
}
```

---

### `GET /annotations/`

List annotations, optionally filtered by document.

**Auth required:** Yes

**Query params:** `document_id` (optional)

**Response `200`:** Array of annotation objects.

---

### `GET /annotations/stats`

Aggregated annotation statistics for dashboard display.

**Auth required:** Yes

**Response `200`:**
```json
{
  "total_annotations": 42,
  "corrections_this_week": 6,
  "top_corrected_entity_types": [
    {"entity_type": "FAILURE_MODE", "count": 3},
    {"entity_type": "process_parameter", "count": 2}
  ]
}
```

---

## 12. Audit Log

**Prefix:** `/audit-log`

Immutable audit trail. Every write operation in Kairos appends an entry. Read-only API.

> **Note:** The time column is `timestamp`, not `created_at`.

---

### `GET /audit-log/`

Query the audit log with optional filters.

**Auth required:** Yes (`engineer` or `admin`)

**Query params:**
| Param | Type | Description |
|-------|------|-------------|
| `action` | string | Filter by action type |
| `entity_type` | string | Filter by entity type (`document`, `brief`, `asset`, …) |
| `entity_id` | string | Filter by entity ID |
| `limit` | int | Max results (default 50) |

**Common action values:** `brief_acknowledged` · `confidence_recheck_queued` · `plant_state_changed` · `rca_pack_generated` · `timestamp_drift_detected` · `attribution_flag` · `quarantine_promoted` · `quarantine_disputed` · `info_requested` · `moc_resolved` · `moc_webhook_received` · `circuit_breaker_override` · `equipment_tag_out` · `sla_escalated` · `model_gate_result` · `offboarding_programme_created` · `recurring_failure_detected`

**Response `200`:**
```json
{
  "items": [
    {
      "id": "uuid",
      "action": "rca_pack_generated",
      "entity_type": "asset",
      "entity_id": "P-101",
      "performed_by": "engineer@kairos.local",
      "details": {
        "failure_code": "SEAL-FAIL",
        "timeline_events": 18,
        "synthesis_available": false
      },
      "timestamp": "2026-07-02T12:05:00Z"
    }
  ],
  "total": 1
}
```

---

## 13. Go OT Connector (port 8090)

> **`GET /ot/coverage/{asset_id}` was deleted (2026-08-16).** It returned hardcoded sensor tags for
> every asset. Instrumentation coverage is now derived from verified topology at
> `GET /assets/{asset_id}/ot-coverage`. `GET /ot/connectors` was added (see `/health/connectors`).


**Base URL:** `http://localhost:8090`

The Go connector (Gin) bridges OT historian data and EAM sync with the FastAPI backend. Uses `INTERNAL_API_KEY` as a service bearer token when calling FastAPI.

---

### `GET /health`

Connector liveness probe.

**Response `200`:** `{"status": "ok"}`

---

### `GET /ot/query`

Query historian time-series. Uses `PIWebAPIClient` if `PI_WEBAPI_BASE_URL` is configured, otherwise `MockHistorianClient` (50 sine-wave vibration points, mean≈1.8 mm/s, 2-minute span).

**Query params:**
| Param | Type | Description |
|-------|------|-------------|
| `tag` | string | Historian tag (e.g. `P-101.VIB`) |
| `from` | ISO8601 | Start time |
| `to` | ISO8601 | End time |

**Response `200`:**
```json
{
  "tag": "P-101.VIB",
  "from": "2024-01-01T22:00:00Z",
  "to": "2024-01-01T22:02:00Z",
  "points": [
    {"timestamp": "2024-01-01T22:00:00Z", "value": 1.82, "quality": "good"}
  ],
  "count": 50,
  "mock": true
}
```

`mock: true` when using `MockHistorianClient`. OT data is ephemeral — never stored in Kairos.

---

### `POST /eam/sync`

Sync EAM assets into Kairos. Reads `fixtures/sample_assets.json` if `EAM_ODS_ENDPOINT` is not configured (5 assets: P-101, V-201, HX-301, C-401, T-501). POSTs each to FastAPI `POST /assets`.

**Response `200`:**
```json
{
  "synced": 5,
  "failed": 0,
  "assets": ["P-101", "V-201", "HX-301", "C-401", "T-501"]
}
```

---

### `POST /eam/work-order`

Proxy an EAM work order into Kairos event ingestion. Forwards raw body to FastAPI `POST /events/work-order`.

**Request body:** Same as `POST /events/work-order`.

**Response:** Proxied response from FastAPI.

---

## 14. Error Codes

| HTTP Status | When |
|------------|------|
| `200` | Success |
| `201` | Resource created |
| `202` | Accepted — async operation started |
| `400` | Malformed request body / missing required field |
| `401` | Missing or invalid JWT |
| `403` | OPA policy denied (wrong role for the route) |
| `404` | Resource not found |
| `409` | Conflict (duplicate asset_id, document already superseded) |
| `422` | Pydantic validation error (field type mismatch) |
| `500` | Internal server error — check `docker logs kairos-backend-api 2>&1 \| tail -30` |

**OPA 403 response shape:**
```json
{
  "detail": "Access denied by policy",
  "required_action": "promote_quarantine",
  "user_role": "field_worker"
}
```

**Pydantic 422 response shape:**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "confirmed_by_user_id"],
      "msg": "Field required"
    }
  ]
}
```

---

## 15. Auth Quick-Reference

```bash
# Get a token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@kairos.local","password":"KairosAdmin123!"}' \
  | jq -r .access_token)

# Use it
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/assets/P-101

# Health check (no auth needed)
curl http://localhost:8000/health/detailed

# Internal service call (Go connector pattern)
curl -H "Authorization: Bearer kairos-internal-dev-key" \
  http://localhost:8000/assets/P-101

# Dev shortcut: omit Authorization header when APP_DEBUG=True and APP_ENV != production
# Treated as {user_id: "dev-user", role: "engineer", site_id: "SITE_001"}
curl http://localhost:8000/assets/P-101
```

**Role permission matrix:**

| Role | Can do |
|------|--------|
| `field_worker` | Read search, read briefs, ack briefs, post alarms, plant state. **403 on audit-log, compliance, governance, documents and the events feed** |
| `engineer` | Above + ingest documents, write assets, read/resolve governance, read documents + events + audit + compliance, start offboarding |
| `reliability` | Engineer's reads + promote quarantine, countersign briefs (no asset write) |
| `compliance` | Read search, compliance, audit, non-conformance (conflicts + quarantine) and events. **Not** the model gate, MoC, circuit breaker or documents |
| `admin` | Everything, including the cross-site view |

Verify the policy's decisions with `tools/verify_authz_policy.sh` (34 cases against a throwaway
OPA, safe to run while the stack is up). That checks the policy is *correct*; to check it is
*reached*, probe the live API with a restricted persona and confirm a 403 —
`curl -H "Authorization: Bearer $FIELD_TOKEN" localhost:8000/audit-log/` must not return 200.

---

## Appendix: OpenAPI

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
