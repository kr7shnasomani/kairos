# Kairos — Database Reference

Four persistence systems, each with a distinct responsibility. No system is interchangeable with another.

| System | Role | Hosting |
|--------|------|------|
| **Neo4j (Aura 2025.x)** | Temporal Reality Graph — the knowledge authority | **Cloud (Neo4j Aura)** · local `7474`/`7687` only with `--profile local-stores` (image pinned to 5.x) |
| **Supabase (PostgreSQL 15)** | Relational backbone — events, briefs, governance, auth | **Cloud (managed)** |
| **Qdrant v1.9.4** | Vector store — semantic search over extracted knowledge | **Cloud (Qdrant Cloud)** · local `6333`/`6334` only with `--profile local-stores` |
| **Elasticsearch 8.13** | Full-text exact search — keyword, tag, document retrieval | Local container · `9200` |
| **Redis 7.2** | Event streams · EEMUA governor · Celery broker · dedup cache | Local container · `6379` |

> **Aura note:** the Neo4j database is named after the instance (e.g. `2016aa75`), **not** `neo4j` — always
> open sessions with `database=settings.NEO4J_DATABASE`. Cloud Qdrant **requires payload indexes** on any
> filter field (`asset_id`, `document_id`, `is_quarantine`) — `init_qdrant.py` creates them.

---

## 1. Neo4j — Temporal Reality Graph

**Architecture layer:** Layer 4 (Temporal Reality Graph)

Neo4j is the primary knowledge store. It holds the authoritative, time-versioned graph of assets, documents, events, and the relationships between them. All reads requiring temporal context (`as_of` time-travel, authority pre-filtering, blast-radius traversal) go through Neo4j.

### Node Labels

| Label | Primary Key | Purpose |
|-------|-------------|---------|
| `Asset` | `asset_id` | Physical equipment (pumps, valves, heat exchangers). Always `MERGE`, never `CREATE`. |
| `Document` | `document_id` | Ingested documents in the immutable vault. Merged before any edge write. |
| `Event` | `event_id` | Operational events (work orders, alarms, PTW, inspections). |
| `Person` | `person_id` | Engineers, operators, named individuals. |
| `Concept` | `concept_id` | Extracted knowledge fragments (failure modes, parameters, procedures) **and regulation clauses** (`type: 'Regulation'`) + P&ID topology elements. |
| `Organisation` | `org_id` | Platform root + external organisations. Seed: `KAIROS_PLATFORM`. |

### Regulation Concept Properties (`Concept {type: 'Regulation'}`)

Seeded by `backend/scripts/seed_regulations.py`; read by `GET /compliance/{gaps,dashboard,audit-pack}`.

| Property | Type | Notes |
|----------|------|-------|
| `concept_id` | String | e.g. `OISD-117-4.1.1` |
| `framework` | String | `OISD_117`, `ISO_45001`, … — stored with underscores, **not** the display form `OISD-117` |
| `clause_id` | String | e.g. `4.1.1` |
| `requirement_text` | String | Verbatim clause requirement |
| `applies_to_equipment_class` | String \| null | `null` = applies to every equipment class. Matched against `Asset.equipment_class` by equality **or substring either way**, so `pump` matches `rotating_centrifugal_pump` |
| `requires_document_type` | List\<String\> \| null | **Evidence type that satisfies this clause** — e.g. `["procedure"]`, `["inspection_report"]`, `["oem_manual"]`. `null` (pre-mapping seeds) = any document type counts, so older graphs keep working instead of reporting a false gap on every clause |
| `authority_level` | Integer | 1–5. Drives finding severity: 1 → `critical`, 2 → `major`, else `minor` |

> `requires_document_type` is what makes gap detection clause-specific. Without it the query could
> only ask "does this asset have *any* verified procedure", which ignored the clause entirely and —
> since nothing but manual quarantine promotion ever writes `verification_status='verified'` —
> reported every (regulation × asset) pair as a gap unconditionally. Values must match the
> `document_type` strings the loader actually assigns (see `scripts/load_demo_dataset.py`), or the
> gap becomes unclosable.

### Asset Node Properties

| Property | Type | Notes |
|----------|------|-------|
| `asset_id` | String | Primary key — unique constraint |
| `tag_number` | String | Plant tag (indexed) |
| `name` | String | Human-readable name |
| `equipment_class` | String | e.g. `centrifugal_pump`, `control_valve` (indexed) |
| `criticality` | String | `safety_critical` · `critical` · `non_critical` |
| `site_id` | String | Facility site identifier (indexed) |
| `facility_id` | String | Sub-site grouping |
| `status` | String | `active` · `decommissioned` · `under_review` |
| `eam_source` | String | Origin system (`manual`, `sap`, `maximo`) |

### KNOWLEDGE_EDGE — All 6 Properties, No Exceptions

Every relationship written to Neo4j uses the `KNOWLEDGE_EDGE` type. Six properties are **mandatory on every write** — Neo4j silently drops properties set to `null`, so missing any property breaks temporal queries and the "all 6" invariant.

| Property | Type | Rules |
|----------|------|-------|
| `valid_from` | DateTime | ISO 8601 UTC. Always `ingested_at` or `occurred_at` (whichever is canonical after drift check). |
| `valid_to` | DateTime | ISO 8601 UTC. Use sentinel `9999-12-31T23:59:59Z` for open-ended (never `null`). |
| `authority_level` | Integer | 1–5. Lower = higher authority. Pre-filter: `r.authority_level <= $max_level`. |
| `document_id` | String | Source document that justified this edge. Must reference an existing Document node. |
| `confidence` | Float | 0.0–1.0. `< 0.7` → edge goes to quarantine, never to canonical graph. |
| `verification_status` | String | `unverified` (NER output) · `verified` (human-promoted) · `disputed` (conflict-flagged). |

**`valid_to` sentinel rule:** `GraphService.create_knowledge_edge()` defaults `valid_to` to `datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)` when no expiry is given. All "currently active" Cypher queries use `(r.valid_to IS NULL OR r.valid_to > datetime())` to cover both legacy null edges and sentinel edges.

**Supersession (never deletion):** To retire an edge, call `close_validity_window(edge_id, valid_to=now())`. Never `DELETE`. The vault is permanent.

### Relationship Types

| Type | From → To | Meaning |
|------|-----------|---------|
| `KNOWLEDGE_EDGE` | Any → Any | All domain knowledge relationships |
| `PARENT_OF` | Asset → Asset | Physical hierarchy (Production Line → Pump) |
| `DOCUMENTED_BY` | Asset → Document | Asset backed by a document |
| `CAUSED_BY` | Event → Event | **Designed, not implemented** — written nowhere in the codebase, and `Event` nodes are never created either (see the L4 divergence in `implementation/status.md`). Causal chains run through `operational_events.compound_event_id` in Supabase instead. |
| `INSPECTION_RECORD` | Asset → Document | Inspection completion with result |

### Constraints and Indices

**Uniqueness constraints** (prevent duplicates):
```cypher
Asset.asset_id · Document.document_id · Event.event_id
Person.person_id · Concept.concept_id · Organisation.org_id
```

**Node property indices** (hot-path lookups):
```
Asset: tag_number, site_id, equipment_class, criticality
Document: document_type, status, authority_level
Event: event_type, occurred_at
```

**Edge property indices** (temporal query performance):
```
KNOWLEDGE_EDGE: valid_from, authority_level, verification_status, document_id
```

### Authority Pre-filter (non-negotiable)

Every graph traversal query must include this filter before any path expansion:
```cypher
WHERE r.authority_level <= $max_level AND r.valid_from <= $as_of
```
This gates authority level and prevents future-dated edges from appearing in historical queries.

### GraphService — Available Methods

All Neo4j access goes through `backend/api/services/graph.py`. Never write Cypher in routers.

| Method | What It Does |
|--------|-------------|
| `create_asset_node(data)` | `MERGE (a:Asset {asset_id}) SET a += props` + `PARENT_OF` if parent given |
| `get_asset(asset_id)` | Single node lookup |
| `list_assets(site_id, equipment_class, skip, limit)` | Paginated with total count |
| `get_asset_hierarchy(asset_id)` | Ancestors + children via `PARENT_OF` |
| `get_asset_knowledge_at(asset_id, as_of, authority_min)` | Time-travel edge query |
| `merge_document_node(document_id, props)` | Idempotent `MERGE` — always call before writing an edge to a document |
| `create_knowledge_edge(...)` | Creates `KNOWLEDGE_EDGE` with all 6 mandatory properties; validates label whitelist |
| `close_validity_window(edge_id, valid_to)` | Supersession — never deletion |
| `detect_conflict(asset_id, parameter, new_value)` | Checks for contradicting active edges on same parameter |
| `get_blast_radius(document_id)` | Downstream impact traversal; returns `{edge, source, target}` per affected edge (affected entity = `source`), deduped by `edge_id` |
| `get_event_timeline(asset_id, from_dt, to_dt)` | Chronological Event nodes for RCA |

### Init

```bash
make init-neo4j
# or:
docker exec kairos-backend-api python scripts/init_neo4j.py
```

Schema file: `db/neo4j/init_schema.cypher`

---

## 2. Supabase — PostgreSQL Relational Store

**Architecture layers:** Layer 1 (Asset MDM) · Layer 2 (Vault registry) · Layer 3 (Pipeline tracking) · Layer 6 (Quarantine) · Layer 7 (Governance) · Layer 8 (Events + Briefs)

Supabase provides PostgreSQL 15, Auth (JWT via Supabase Auth), and Storage (the immutable vault bucket). The FastAPI backend always uses the **service-role key** (bypasses RLS). The anon/user key is reserved for future frontend direct-access flows.

### Tables — Full Schema

#### `assets` — MDM mirror of Neo4j
```sql
asset_id        TEXT PRIMARY KEY
tag_number      TEXT NOT NULL
name            TEXT NOT NULL
equipment_class TEXT NOT NULL
criticality     TEXT CHECK IN ('safety_critical','critical','non_critical')
site_id         TEXT NOT NULL
facility_id     TEXT NOT NULL
parent_asset_id TEXT REFERENCES assets(asset_id)
eam_source      TEXT DEFAULT 'manual'
identity_confirmed      BOOLEAN DEFAULT FALSE
identity_confirmed_by   TEXT
identity_confirmed_at   TIMESTAMPTZ
status          TEXT CHECK IN ('active','decommissioned','under_review')
created_at      TIMESTAMPTZ DEFAULT NOW()
updated_at      TIMESTAMPTZ DEFAULT NOW()
```
Indices: `site_id`, `equipment_class`, `tag_number`

#### `asset_alias_map` — Tag alias resolution
```sql
id                  UUID PRIMARY KEY
canonical_asset_id  TEXT REFERENCES assets(asset_id)
alias               TEXT UNIQUE
alias_source        TEXT
confidence          NUMERIC(4,3) -- 0–1
confirmed           BOOLEAN DEFAULT FALSE
confirmed_by        TEXT
created_at          TIMESTAMPTZ
```

#### `documents` — Immutable vault registry
```sql
document_id     TEXT PRIMARY KEY
sha256_hash     TEXT UNIQUE   -- dedup gate
file_name       TEXT
file_size_bytes BIGINT
mime_type       TEXT
document_type   TEXT
authority_level INTEGER CHECK BETWEEN 1 AND 5
source_system   TEXT
vault_url       TEXT          -- Supabase Storage signed URL
status          TEXT CHECK IN ('active','superseded','archived','disputed')
version_chain   TEXT REFERENCES documents(document_id)  -- supersession chain
occurred_at     TIMESTAMPTZ   -- source document timestamp (migration 009)
ingested_at     TIMESTAMPTZ DEFAULT NOW()
ingested_by     TEXT
```
Indices: `status`, `document_type`, `authority_level`

**Vault rule:** Never `UPDATE` or `DELETE`. Supersede by setting `status='superseded'` on the old row and creating a new row linked via `version_chain`.

#### `document_asset_links` — Document ↔ Asset join
```sql
id          UUID PRIMARY KEY
document_id TEXT REFERENCES documents(document_id)
asset_id    TEXT REFERENCES assets(asset_id)
linked_at   TIMESTAMPTZ
UNIQUE (document_id, asset_id)
```

#### `extraction_jobs` — Temporal pipeline state tracking
```sql
job_id          UUID PRIMARY KEY  -- auto-generated by Postgres, read back after insert
document_id     TEXT REFERENCES documents(document_id)
pipeline_stage  TEXT DEFAULT 'queued'
progress_pct    INTEGER DEFAULT 0
ocr_confidence  NUMERIC(4,3)
entity_count    INTEGER
graph_edges     INTEGER
review_pending  INTEGER DEFAULT 0
error           TEXT
timestamp_drift_detected BOOLEAN DEFAULT FALSE  -- migration 009; cross-source skew only.
                                               -- The pipeline stopped setting it 2026-08-17: an
                                               -- occurred_at/ingested_at gap is ingest lag, not drift.
started_at      TIMESTAMPTZ
completed_at    TIMESTAMPTZ
created_at      TIMESTAMPTZ DEFAULT NOW()
```

Pipeline stages (in order): `queued` → `ocr_running` → `ner_running` → `graph_linking` → `indexing` → `complete` / `review_required` / `failed`

#### `operational_events` — Layer 8 event log
```sql
event_id         TEXT PRIMARY KEY
event_type       TEXT NOT NULL  -- work_order_created, ptw_generated, shift_handover, alarm, tag_out, inspection_complete, deviation_flag
source_system    TEXT
site_id          TEXT
asset_id         TEXT REFERENCES assets(asset_id)
payload          JSONB DEFAULT '{}'
occurred_at      TIMESTAMPTZ
received_at      TIMESTAMPTZ DEFAULT NOW()
redis_stream_id  TEXT
compound_event_id UUID         -- migration 010: links correlated same-asset events
event_subtype    TEXT          -- migration 012: 'recurring' when recurring failure detected
```
Indices: `event_type`, `asset_id`, `occurred_at DESC`, `compound_event_id`

> **There is no `priority` column here.** `GET /events` derives it from `payload.priority` and
> defaults to `"normal"` when the key is absent (`routers/events.py`), so priority is unconstrained
> JSONB — no CHECK, no default, and present on only a subset of rows. `models/event.py` documents
> `critical, high, normal, low` on `WorkOrderEvent`, but nothing enforces that at the database.
> A UI filter must therefore derive its options from the data present rather than hard-code the
> four levels, or it renders dead options. (The `priority TEXT NOT NULL DEFAULT 'normal'` in
> `db/schema.sql` belongs to **`briefs`**, not to this table — an easy misread, and one that has
> already produced a wrong bug report.)

#### `briefs` — Proactive brief delivery log
```sql
brief_id          UUID PRIMARY KEY
trigger_event_id  TEXT
trigger_event_type TEXT NOT NULL
asset_id          TEXT REFERENCES assets(asset_id)
recipient_user_id TEXT NOT NULL
priority          TEXT DEFAULT 'normal'  -- critical, high, normal, medium, low
headline          TEXT NOT NULL
body              TEXT NOT NULL
action_items      JSONB DEFAULT '[]'     -- migration 003
warnings          JSONB DEFAULT '[]'     -- migration 003
quarantine_flags  JSONB DEFAULT '[]'     -- migration 003
sources           JSONB DEFAULT '[]'     -- array of SourceCitation objects
confidence        NUMERIC(4,3)
work_order_id     TEXT                   -- migration 003
ptw_id            TEXT                   -- migration 003
delivery_frozen   BOOLEAN DEFAULT FALSE  -- migration 008: frozen by deviation flag
requires_countersignature BOOLEAN DEFAULT FALSE
delivered_at      TIMESTAMPTZ
acknowledged_at   TIMESTAMPTZ
acknowledged_by   TEXT
countersigned_by  TEXT
countersigned_at  TIMESTAMPTZ
created_at        TIMESTAMPTZ DEFAULT NOW()
```
Indices: `recipient_user_id`, `asset_id`, `delivered_at`, `(asset_id, delivery_frozen) WHERE delivery_frozen=TRUE`

**RLS:** Each authenticated user sees only briefs where `recipient_user_id = auth.uid()`. Site-wide briefs use `user_id = "site-{site_id}"` and are visible to all users on that site.

#### `brief_feedback`
```sql
id           UUID PRIMARY KEY
brief_id     UUID REFERENCES briefs(brief_id)
rating       TEXT CHECK IN ('accurate','missing_context','incorrect')
notes        TEXT
submitted_by TEXT
submitted_at TIMESTAMPTZ DEFAULT NOW()
```

#### `knowledge_conflicts` — Dual-track governance
```sql
conflict_id   UUID PRIMARY KEY
track         TEXT CHECK IN ('administrative','engineering')
asset_id      TEXT REFERENCES assets(asset_id)
parameter     TEXT
source_a      JSONB   -- { document_id, value, authority_level }
source_b      JSONB
authority_a   INTEGER
authority_b   INTEGER
severity      TEXT
status        TEXT DEFAULT 'open' CHECK IN ('open','pending_moc','resolved')
sla_deadline  TIMESTAMPTZ
escalated_at  TIMESTAMPTZ    -- migration 015
escalated_to  TEXT           -- migration 015
resolved_by   TEXT
resolved_at   TIMESTAMPTZ
created_at    TIMESTAMPTZ DEFAULT NOW()
```
Indices: `status`, `asset_id`

SLA default: 5 days from creation. `SLAService.check_and_escalate()` runs lazily on `GET /conflicts` and `GET /sla-report` — idempotent, writes `audit_log` on first escalation only.

#### `quarantine_items` — Unverified knowledge gate
```sql
item_id        UUID PRIMARY KEY
asset_id       TEXT REFERENCES assets(asset_id)  -- NULL when asset unknown (never empty string)
content        TEXT NOT NULL
input_type     TEXT CHECK IN ('field_observation','voice_note','elicitation_response','deviation_flag','offboarding_response')
submitted_by   TEXT
submitted_at   TIMESTAMPTZ DEFAULT NOW()
reviewer_id    TEXT
review_status  TEXT DEFAULT 'pending' CHECK IN ('pending','promoted','disputed','archived')
reviewed_at    TIMESTAMPTZ
work_order_id  TEXT
session_context JSONB DEFAULT '{}'
sla_due_at     TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '5 days')  -- migration 015
escalated_at   TIMESTAMPTZ                                       -- migration 015
```
Indices: `review_status`, `asset_id`

**Quarantine is a one-way gate.** Only human action via `POST /governance/quarantine/{item_id}/promote` can promote an item. No auto-promotion ever. Deviation flags override `sla_due_at` to 24h.

**`input_type` CHECK constraint:** Adding a new `input_type` requires dropping and re-adding the constraint. Current allowed values listed above.

#### `moc_items` — Management of Change
```sql
moc_id          TEXT PRIMARY KEY
conflict_id     UUID REFERENCES knowledge_conflicts(conflict_id)
asset_id        TEXT REFERENCES assets(asset_id)
description     TEXT
conflicting_sources JSONB DEFAULT '[]'
blast_radius    JSONB DEFAULT '[]'
status          TEXT DEFAULT 'draft' CHECK IN ('draft','pending_approval','approved','rejected')
approved_by     TEXT
approved_at     TIMESTAMPTZ
webhook_received_at TIMESTAMPTZ
created_at      TIMESTAMPTZ DEFAULT NOW()
```

#### `audit_log` — Immutable action record
```sql
id          BIGSERIAL PRIMARY KEY
action      TEXT NOT NULL
entity_type TEXT
entity_id   TEXT
performed_by TEXT NOT NULL
details     JSONB DEFAULT '{}'
timestamp   TIMESTAMPTZ DEFAULT NOW()   -- NOTE: column is 'timestamp', NOT 'created_at'
```
Indices: `(entity_type, entity_id)`, `timestamp DESC`

**Common pitfall:** The time column is `timestamp`, not `created_at`. Any `.order("created_at")` call will fail.

#### `elicitation_sessions` — Micro-interview state
```sql
session_id    UUID PRIMARY KEY
work_order_id TEXT NOT NULL
asset_id      TEXT REFERENCES assets(asset_id)
questions     JSONB DEFAULT '[]'
status        TEXT CHECK IN ('pending','questions_ready','completed')
triggered_by  TEXT
created_at    TIMESTAMPTZ DEFAULT NOW()
updated_at    TIMESTAMPTZ DEFAULT NOW()
```
Index: `work_order_id`

#### `ner_annotations` — Active learning corpus
```sql
id             UUID PRIMARY KEY
document_id    TEXT REFERENCES documents(document_id)
entity_text    TEXT
entity_type    TEXT
corrected_type TEXT
is_correct     BOOLEAN
span_start     INTEGER
span_end       INTEGER
annotated_by   TEXT
created_at     TIMESTAMPTZ DEFAULT NOW()
```
Indices: `document_id`, `created_at DESC`, `corrected_type WHERE is_correct=FALSE`

#### `extraction_overrides` — SPC circuit breaker
```sql
id            UUID PRIMARY KEY
asset_class   TEXT
document_id   TEXT
override_type TEXT CHECK IN ('manual_correction','quarantine_rejection','annotation_correction')
created_at    TIMESTAMPTZ DEFAULT NOW()
```
Index: `(asset_class, created_at DESC)` — 7-day rolling window check

#### `plant_operating_states` — Push suppression gate
```sql
id          UUID PRIMARY KEY
site_id     TEXT
state       TEXT CHECK IN ('normal','turnaround','shutdown','emergency')
set_by      TEXT
set_at      TIMESTAMPTZ DEFAULT NOW()
expires_at  TIMESTAMPTZ
```
Index: `(site_id, set_at DESC)` — latest state per site

**Effect:** `turnaround` / `shutdown` / `emergency` suppress normal-priority briefs at the EEMUA 191 governor. Critical (PTW) briefs always pass.

#### `validation_corpus` — NER model gate ground truth
```sql
id           UUID PRIMARY KEY
document_id  TEXT
entity_text  TEXT
entity_type  TEXT
span_start   INTEGER
span_end     INTEGER
authority    TEXT CHECK IN ('human_promotion','annotation_correction')
promoted_by  TEXT
created_at   TIMESTAMPTZ DEFAULT NOW()
```
Indices: `entity_type`, `document_id`

#### `offboarding_sessions` — Knowledge capture series
```sql
id                   UUID PRIMARY KEY
personnel_id         TEXT
personnel_email      TEXT
retirement_date      DATE
total_sessions       INT DEFAULT 6
session_interval_days INT DEFAULT 12
status               TEXT CHECK IN ('scheduled','in_progress','completed','cancelled')
created_by           TEXT
created_at           TIMESTAMPTZ DEFAULT NOW()
```

#### `offboarding_session_items`
```sql
id                UUID PRIMARY KEY
session_id        UUID REFERENCES offboarding_sessions(id) ON DELETE CASCADE
session_number    INT
equipment_family  TEXT
focus_failure_modes TEXT[]
status            TEXT CHECK IN ('pending','questions_ready','completed')
questions         JSONB DEFAULT '[]'
scheduled_for     TIMESTAMPTZ
completed_at      TIMESTAMPTZ
```
Index: `session_id`

### Row-Level Security

RLS is enabled on: `assets`, `documents`, `briefs`, `quarantine_items`, `audit_log`.

The FastAPI backend always uses `SUPABASE_SERVICE_ROLE_KEY` — service role bypasses RLS entirely. Policies apply only to direct Supabase client access (anon/authenticated roles):

| Table | Policy | Rule |
|-------|--------|------|
| `briefs` | `briefs_recipient_isolation` | `recipient_user_id = auth.uid()` |
| `quarantine_items` | `quarantine_submitter_isolation` | `submitted_by = auth.uid()` OR `role = 'admin'` |

### Storage Bucket — `kairos-vault`

Private bucket (no public access). All reads require a signed URL.

| Setting | Value |
|---------|-------|
| Name | `kairos-vault` |
| Public | `false` |
| Max file size | 500 MB |
| Allowed MIME types | PDF, PNG, JPEG, TIFF, XLS, XLSX, TXT, CSV, octet-stream, audio/* (mpeg·wav·webm·mp4·ogg — voice notes, migration 016) |

**Immutability:** Files are never overwritten. A new version creates a new document row linked via `version_chain`. The old file remains permanently.

### Migrations

The full schema is consolidated into a **single source-of-truth file, `db/schema.sql`** — apply it to a fresh database to get the current schema. The 16 original ordered migrations were folded in and are no longer kept as separate files; the live applied history remains tracked by Supabase in `supabase_migrations.schema_migrations` (timestamp-versioned). Going forward, make a schema change directly in `schema.sql` (and record any ad-hoc live run in `db/maintenance/CHANGELOG.md`).

The table below is the **schema-evolution changelog** — what each of the 16 folded-in migrations contributed to `schema.sql`:

| Migration | What It Added |
|-----------|-------------|
| `001_initial_schema.sql` | All core tables + RLS enable |
| `002_storage_bucket.sql` | `kairos-vault` bucket + RLS policies |
| `003_add_brief_content_columns.sql` | `action_items`, `warnings`, `quarantine_flags`, `work_order_id`, `ptw_id` on `briefs` |
| `004_rls_briefs_quarantine.sql` | RLS policies for `briefs` + `quarantine_items` |
| `005_elicitation_sessions.sql` | `elicitation_sessions` table |
| `006_ner_annotations.sql` | `ner_annotations` table |
| `007_circuit_breaker.sql` | `extraction_overrides` table |
| `008_brief_freeze.sql` | `delivery_frozen` column on `briefs` |
| `009_timestamp_drift.sql` | `occurred_at` on `documents`, `timestamp_drift_detected` on `extraction_jobs` |
| `010_compound_events.sql` | `compound_event_id` on `operational_events` |
| `011_plant_state.sql` | `plant_operating_states` table |
| `012_event_subtype.sql` | `event_subtype` on `operational_events` |
| `013_offboarding_sessions.sql` | `offboarding_sessions` + `offboarding_session_items` tables |
| `014_validation_corpus.sql` | `validation_corpus` table |
| `015_sla_tracking.sql` | `escalated_at` + `escalated_to` on `knowledge_conflicts`; `sla_due_at` + `escalated_at` on `quarantine_items` |
| `016_vault_audio_mime.sql` | Allow `audio/*` MIME types on the `kairos-vault` bucket (voice-note uploads) |

### Maintenance & data hygiene

`db/maintenance/` holds SQL you run **directly against cloud Supabase** — operations that
`make nuke` cannot do, because `make nuke` only wipes the *local* Docker volumes (Neo4j, ES,
Qdrant, Redis), never the hosted Supabase Postgres. Two files:

- **`reset_all_data.sql`** — `TRUNCATE` every `public` table (schema + auth kept). The only way to
  return the cloud database to a blank slate; run it via the Supabase SQL editor or MCP.
- **`CHANGELOG.md`** — a running log of every ad-hoc SQL/operation applied to the live project, so
  the hosted state is never a mystery.

For routine test-residue cleanup use the scripts, not raw SQL:

- `make purge-test-data` → `scripts/purge_test_data.py` clears test-prefixed rows
  (`ASSET-TEST/DEDUP/EV/ACK-*`, `WO-*`, `DOC-*`) from **Neo4j + Supabase + Elasticsearch** in one go.
- The integration suite also purges its own residue automatically on teardown (`conftest.py`).

---

## 3. Qdrant — Vector Store

**Architecture layer:** Layer 11 (Semantic Retrieval)

Qdrant stores 1024-dimensional embeddings produced by Jina AI `jina-embeddings-v3`. It powers semantic similarity search — finding knowledge fragments that are conceptually related to a query even when exact keywords don't match.

### Collections

| Collection | Name (config key) | Purpose |
|------------|-------------------|---------|
| Knowledge | `kairos_knowledge` (`QDRANT_COLLECTION_KNOWLEDGE`) | Extracted knowledge fragments — facts, parameters, failure modes linked to graph nodes |
| Documents | `kairos_documents` (`QDRANT_COLLECTION_DOCUMENTS`) | Full document text chunks for RAG-style retrieval |

### Vector Configuration

| Setting | Value |
|---------|-------|
| Dimensions | 1024 (`EMBEDDING_DIMENSION`) |
| Distance metric | Cosine |
| Embedding model | `jina-embeddings-v3` (Jina AI API) |
| Fallback model | `nomic-embed-text` (Ollama) |

### Point Schema (Payload)

Every Qdrant point carries this payload alongside the vector:

```json
{
  "document_id": "DOC-XXXX",
  "asset_id": "P-101",
  "authority_level": 2,
  "confidence": 0.91,
  "is_quarantine": false,
  "content": "Four mechanical-seal failures recorded 2018–2026...",
  "document_type": "maintenance_record",
  "chunk_index": 0
}
```

### Filtering

`VectorStoreService.search()` applies Qdrant payload filters before returning results:

| Filter | Behaviour |
|--------|-----------|
| `asset_id` | Restrict to a specific asset |
| `is_quarantine=False` | Default — exclude quarantine items |
| `is_quarantine=True` | `quarantine_only=True` — only quarantine items |
| `include_quarantine=True` | Include both canonical and quarantine |
| `authority_level <= authority_min` | Post-filter after vector search |

### Init

```bash
make init-qdrant
# or:
docker exec kairos-backend-api python scripts/init_qdrant.py
```

Collections are also created automatically at API startup via `VectorStoreService.ensure_collections()`.

### Access Pattern

```python
from api.services.vector_store import VectorStoreService

# Upsert
await vector.upsert(
    collection=settings.QDRANT_COLLECTION_KNOWLEDGE,
    point_id=str(uuid.uuid4()),
    vector=embedding,            # List[float], 1024 dims
    payload={"document_id": ..., "asset_id": ..., "authority_level": 2, ...}
)

# Search
hits = await vector.search(
    collection=settings.QDRANT_COLLECTION_KNOWLEDGE,
    query_vector=query_embedding,
    limit=10,
    asset_id="P-101",           # optional filter
    authority_min=3,
    include_quarantine=False,
)
```

---

## 4. Elasticsearch — Full-Text Search

**Architecture layer:** Layer 11 (Exact Retrieval)

Elasticsearch handles keyword search, tag lookups, and structured field queries. It runs alongside Qdrant in parallel during hybrid search — ES for exact/keyword hits, Qdrant for semantic hits — and results are merged and re-ranked by authority level.

### Indices

| Index | Config Key | Content |
|-------|-----------|---------|
| `kairos_assets` | `ELASTICSEARCH_INDEX_ASSETS` | Asset records (tag numbers, names, equipment class) |
| `kairos_documents` | `ELASTICSEARCH_INDEX_DOCUMENTS` | Document text content + metadata |
| `kairos_events` | `ELASTICSEARCH_INDEX_EVENTS` | Operational event payloads |

### Document Shape — `kairos_documents`

```json
{
  "document_id": "DOC-XXXX",
  "title": "EQ-101 Failure History Report",
  "content": "Four mechanical-seal failures...",
  "document_type": "maintenance_record",
  "authority_level": 2,
  "asset_ids": ["EQ-101", "P-101"],
  "ingested_at": "2026-07-01T10:00:00Z"
}
```

### Hybrid Search Flow

`GET /search?q=...` runs three queries in parallel:
1. ES full-text on `kairos_documents` (keyword match)
2. Qdrant semantic on `kairos_knowledge` (cosine similarity)
3. Neo4j graph traversal (authority-filtered edge walk)

Results are merged, deduplicated by `document_id`, and re-ranked by `authority_level` (ascending — lower authority level = higher trust).

---

## 5. Redis — Streams, Governor, Cache, Broker

**Architecture layer:** Layer 8 (Event Bus) · Cross-cutting (Cache + Broker)

Redis is used for four distinct concerns, each isolated to a separate database number.

### Database Allocation

| DB | Purpose |
|----|---------|
| `0` | Application cache + event streams |
| `1` | Celery broker + result backend |
| `2` | (reserved) |

### Event Streams (Redis Streams on DB 0)

All streams use `XADD`. Workers and the brief engine consume via `XREAD`. Stream IDs are stored in `operational_events.redis_stream_id` for traceability.

| Stream Key | Trigger | Consumer |
|------------|---------|----------|
| `kairos:events:work_orders` | `POST /events/work-order` | Brief engine, delay compensation |
| `kairos:events:ptw` | `POST /events/ptw` | Brief engine (immediate, no delay) |
| `kairos:events:shift_handover` | `POST /events/shift-handover` | Brief engine, delay compensation |
| `kairos:events:alarms` | `POST /events/alarm`, `POST /events/deviation-flag` | Alert pipeline |
| `kairos:events:briefs` | `BriefEngine.deliver()` | Frontend subscription (future) |
| `kairos:events:tag_out` | `POST /events/tag-out` | Brief engine, delay compensation |
| `kairos:events:inspections` | `POST /events/inspection-complete` | Brief engine |

### EEMUA 191 Governor Keys

```
kairos:governor:{user_id}:hourly_count   TTL: 3600s (rolling hour)
```

`EventBusService.check_governor(user_id)` reads this counter before every brief delivery. Hard ceiling: 6 pushes/operator/hour. PTW briefs bypass the ceiling unconditionally. Plant state (`turnaround`/`shutdown`/`emergency`) suppresses normal-priority briefs regardless of count.

### Delay Compensation Keys

```
kairos:brief_pending:{asset_id}          TTL: LATE_ARRIVAL_WINDOW + 60s
kairos:brief_pending:shift:{site_id}     TTL: LATE_ARRIVAL_WINDOW + 60s
```

A PTW arriving for the same asset within the window revokes the pending WO Celery task and assembles the PTW brief immediately. The Celery task ID is stored in this key.

### Dedup Keys

```
kairos:dedup:{asset_id}:{event_type}     TTL: 600s (10 minutes)
```

Identical `(asset_id, event_type)` pairs within 10 minutes collapse to `{status: "deduplicated"}`. Tests using `shared_asset_id` must use distinct asset IDs to avoid dedup collisions within the window.

### Celery (DB 1)

Celery broker and result backend both use `redis://kairos-redis:6379/1`.

Active queues (all must be in the `--queues` flag of `kairos-celery-worker`):

| Queue | Tasks |
|-------|-------|
| `ingestion` | `assemble_brief`, `assemble_recurring_failure_brief` |
| `extraction` | Entity linking, alias resolution |
| `attribution` | `evaluate_outcome` |
| `transcription` | `transcribe_voice` |
| `elicitation` | `generate_interview_questions`, `generate_offboarding_questions` |
| `validation` | `run_model_gate` |

---

## 6. Cross-System Patterns

### Write Order for Document Ingestion

```
1. Supabase Storage → upload file, get vault_url
2. Supabase documents → insert row (sha256 dedup gate)
3. Supabase extraction_jobs → insert row, read back auto-generated job_id
4. Temporal → start DocumentIngestionWorkflow
5. Neo4j → MERGE Document node
6. Neo4j → CREATE KNOWLEDGE_EDGE (all 6 properties)
7. Qdrant → upsert vector point
8. Elasticsearch → index document text
9. Supabase extraction_jobs → update stage=complete
```

### Confidence Routing

```
ocr_confidence < 0.5    → stage=review_required, stop pipeline
entity_confidence < 0.7 → quarantine_items (Supabase), no Neo4j write
entity_confidence ≥ 0.7 → KNOWLEDGE_EDGE verification_status=unverified
human promoted          → KNOWLEDGE_EDGE verification_status=verified
```

### Never Do

- `DELETE` in Neo4j or Supabase — supersede/close instead
- Store time-series historian data in any Kairos store — ephemeral only
- Set `valid_to=null` on a KNOWLEDGE_EDGE — use the sentinel `9999-12-31T23:59:59Z`
- Use `asset_id=""` in `quarantine_items` — use `None` / SQL NULL
- Call Supabase client directly in an async handler — always `asyncio.to_thread(lambda: ...)`
- Use `audit_log.created_at` — the column is `timestamp`
