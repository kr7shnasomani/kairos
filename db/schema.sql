-- =============================================================================
-- Kairos — Consolidated Supabase (PostgreSQL) schema
-- =============================================================================
-- Single source of truth for the relational schema: migrations 001–016 folded
-- into their base tables. Apply to a fresh database to get the full current schema.
-- The live applied history is tracked by Supabase in supabase_migrations.schema_migrations.
-- See docs/DATABASE.md for the annotated reference + the per-migration changelog.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Assets — MDM backbone (Layer 1) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS assets (
    asset_id        TEXT PRIMARY KEY,
    tag_number      TEXT NOT NULL,
    name            TEXT NOT NULL,
    equipment_class TEXT NOT NULL,
    criticality     TEXT NOT NULL CHECK (criticality IN ('safety_critical', 'critical', 'non_critical')),
    site_id         TEXT NOT NULL,
    facility_id     TEXT NOT NULL,
    parent_asset_id TEXT REFERENCES assets(asset_id),
    eam_source      TEXT NOT NULL DEFAULT 'manual',
    identity_confirmed    BOOLEAN NOT NULL DEFAULT FALSE,
    identity_confirmed_by TEXT,
    identity_confirmed_at TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'decommissioned', 'under_review')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_assets_site  ON assets(site_id);
CREATE INDEX IF NOT EXISTS idx_assets_class ON assets(equipment_class);
CREATE INDEX IF NOT EXISTS idx_assets_tag   ON assets(tag_number);

-- ── Asset alias map (Layer 1) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS asset_alias_map (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    alias              TEXT NOT NULL UNIQUE,
    alias_source       TEXT NOT NULL,
    confidence         NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    confirmed          BOOLEAN NOT NULL DEFAULT FALSE,
    confirmed_by       TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Documents — immutable vault registry (Layer 2) ──────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    document_id     TEXT PRIMARY KEY,
    sha256_hash     TEXT NOT NULL UNIQUE,
    file_name       TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    mime_type       TEXT NOT NULL,
    document_type   TEXT NOT NULL,
    authority_level INTEGER NOT NULL CHECK (authority_level BETWEEN 1 AND 5),
    source_system   TEXT NOT NULL,
    vault_url       TEXT,
    status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'superseded', 'archived', 'disputed')),
    version_chain   TEXT REFERENCES documents(document_id),
    occurred_at     TIMESTAMPTZ,                          -- migration 009
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ingested_by     TEXT NOT NULL,
    -- migration 017 — Layer 2: the IAM-derived permission tags each artifact is specified to
    -- receive on ingestion. {site_id, required_action, classification, ingested_by, derived_from}
    access_tags     JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_documents_status    ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_type      ON documents(document_type);
CREATE INDEX IF NOT EXISTS idx_documents_authority ON documents(authority_level);
CREATE INDEX IF NOT EXISTS idx_documents_access_site ON documents ((access_tags ->> 'site_id'));

CREATE TABLE IF NOT EXISTS document_asset_links (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    asset_id    TEXT NOT NULL REFERENCES assets(asset_id),
    linked_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, asset_id)
);

-- ── Extraction pipeline tracking (Layer 3) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS extraction_jobs (
    job_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id     TEXT NOT NULL REFERENCES documents(document_id),
    pipeline_stage  TEXT NOT NULL DEFAULT 'queued',
    progress_pct    INTEGER NOT NULL DEFAULT 0,
    ocr_confidence  NUMERIC(4,3),
    entity_count    INTEGER,
    graph_edges     INTEGER,
    review_pending  INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    timestamp_drift_detected BOOLEAN NOT NULL DEFAULT FALSE,   -- migration 009
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Operational events (Layer 8) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS operational_events (
    event_id          TEXT PRIMARY KEY,
    event_type        TEXT NOT NULL,
    source_system     TEXT NOT NULL,
    site_id           TEXT NOT NULL,
    asset_id          TEXT REFERENCES assets(asset_id),
    payload           JSONB NOT NULL DEFAULT '{}',
    occurred_at       TIMESTAMPTZ NOT NULL,
    received_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    redis_stream_id   TEXT,
    compound_event_id UUID,                                -- migration 010
    event_subtype     TEXT                                 -- migration 012
);
CREATE INDEX IF NOT EXISTS idx_events_type     ON operational_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_asset    ON operational_events(asset_id);
CREATE INDEX IF NOT EXISTS idx_events_occurred ON operational_events(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_compound ON operational_events(compound_event_id);

-- ── Proactive briefs (Layer 8) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS briefs (
    brief_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trigger_event_id   TEXT,
    trigger_event_type TEXT NOT NULL,
    asset_id           TEXT REFERENCES assets(asset_id),
    recipient_user_id  TEXT NOT NULL,
    priority           TEXT NOT NULL DEFAULT 'normal',
    headline           TEXT NOT NULL,
    body               TEXT NOT NULL,
    action_items       JSONB NOT NULL DEFAULT '[]',        -- migration 003
    warnings           JSONB NOT NULL DEFAULT '[]',        -- migration 003
    quarantine_flags   JSONB NOT NULL DEFAULT '[]',        -- migration 003
    sources            JSONB NOT NULL DEFAULT '[]',
    confidence         NUMERIC(4,3),
    work_order_id      TEXT,                               -- migration 003
    ptw_id             TEXT,                               -- migration 003
    delivery_frozen    BOOLEAN NOT NULL DEFAULT FALSE,     -- migration 008
    requires_countersignature BOOLEAN NOT NULL DEFAULT FALSE,
    delivered_at       TIMESTAMPTZ,
    acknowledged_at    TIMESTAMPTZ,
    acknowledged_by    TEXT,
    countersigned_by   TEXT,
    countersigned_at   TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_briefs_recipient ON briefs(recipient_user_id);
CREATE INDEX IF NOT EXISTS idx_briefs_asset     ON briefs(asset_id);
CREATE INDEX IF NOT EXISTS idx_briefs_delivered ON briefs(delivered_at);
CREATE INDEX IF NOT EXISTS idx_briefs_frozen    ON briefs(asset_id, delivery_frozen) WHERE delivery_frozen = TRUE;

CREATE TABLE IF NOT EXISTS brief_feedback (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    brief_id     UUID NOT NULL REFERENCES briefs(brief_id),
    rating       TEXT NOT NULL CHECK (rating IN ('accurate', 'missing_context', 'incorrect')),
    notes        TEXT,
    submitted_by TEXT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Governance: conflicts (Layer 7) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_conflicts (
    conflict_id  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    track        TEXT NOT NULL CHECK (track IN ('administrative', 'engineering')),
    asset_id     TEXT REFERENCES assets(asset_id),
    parameter    TEXT NOT NULL,
    source_a     JSONB NOT NULL,
    source_b     JSONB NOT NULL,
    authority_a  INTEGER,
    authority_b  INTEGER,
    severity     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'pending_moc', 'resolved')),
    sla_deadline TIMESTAMPTZ,
    escalated_at TIMESTAMPTZ,                              -- migration 015
    escalated_to TEXT,                                     -- migration 015
    resolved_by  TEXT,
    resolved_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_conflicts_status ON knowledge_conflicts(status);
CREATE INDEX IF NOT EXISTS idx_conflicts_asset  ON knowledge_conflicts(asset_id);

-- ── Quarantine — unverified knowledge gate (Layer 6) ────────────────────────
CREATE TABLE IF NOT EXISTS quarantine_items (
    item_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id        TEXT REFERENCES assets(asset_id),
    content         TEXT NOT NULL,
    input_type      TEXT NOT NULL CHECK (input_type IN
                      ('field_observation', 'voice_note', 'elicitation_response', 'deviation_flag', 'offboarding_response')),
    submitted_by    TEXT NOT NULL,
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewer_id     TEXT,
    review_status   TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending', 'promoted', 'disputed', 'archived')),
    reviewed_at     TIMESTAMPTZ,
    work_order_id   TEXT,
    session_context JSONB DEFAULT '{}',
    sla_due_at      TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '5 days'),   -- migration 015
    escalated_at    TIMESTAMPTZ                                        -- migration 015
);
CREATE INDEX IF NOT EXISTS idx_quarantine_status ON quarantine_items(review_status);
CREATE INDEX IF NOT EXISTS idx_quarantine_asset  ON quarantine_items(asset_id);

-- ── Governance: Management of Change (Layer 7) ──────────────────────────────
CREATE TABLE IF NOT EXISTS moc_items (
    moc_id              TEXT PRIMARY KEY,
    conflict_id         UUID REFERENCES knowledge_conflicts(conflict_id),
    asset_id            TEXT REFERENCES assets(asset_id),
    description         TEXT NOT NULL,
    conflicting_sources JSONB NOT NULL DEFAULT '[]',
    blast_radius        JSONB NOT NULL DEFAULT '[]',
    status              TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'pending_approval', 'approved', 'rejected')),
    approved_by         TEXT,
    approved_at         TIMESTAMPTZ,
    webhook_received_at TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Audit log — immutable action record ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id           BIGSERIAL PRIMARY KEY,
    action       TEXT NOT NULL,
    entity_type  TEXT,
    entity_id    TEXT,
    performed_by TEXT NOT NULL,
    details      JSONB DEFAULT '{}',
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW()    -- NOTE: column is 'timestamp', not 'created_at'
);
CREATE INDEX IF NOT EXISTS idx_audit_entity    ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);

-- ── Elicitation sessions (Layer 9, migration 005) ───────────────────────────
CREATE TABLE IF NOT EXISTS elicitation_sessions (
    session_id    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    work_order_id TEXT NOT NULL,
    asset_id      TEXT REFERENCES assets(asset_id),
    questions     JSONB NOT NULL DEFAULT '[]',
    status        TEXT NOT NULL CHECK (status IN ('pending', 'questions_ready', 'completed')),
    triggered_by  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_elicitation_wo ON elicitation_sessions(work_order_id);

-- ── NER active-learning annotations (Layer 3, migration 006) ────────────────
CREATE TABLE IF NOT EXISTS ner_annotations (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id    TEXT REFERENCES documents(document_id),
    entity_text    TEXT,
    entity_type    TEXT,
    corrected_type TEXT,
    is_correct     BOOLEAN,
    span_start     INTEGER,
    span_end       INTEGER,
    annotated_by   TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ner_document ON ner_annotations(document_id);
CREATE INDEX IF NOT EXISTS idx_ner_created  ON ner_annotations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ner_wrong    ON ner_annotations(corrected_type) WHERE is_correct = FALSE;

-- ── SPC circuit breaker (Layer 7, migration 007) ────────────────────────────
CREATE TABLE IF NOT EXISTS extraction_overrides (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_class   TEXT,
    document_id   TEXT,
    override_type TEXT CHECK (override_type IN ('manual_correction', 'quarantine_rejection', 'annotation_correction')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_overrides_class ON extraction_overrides(asset_class, created_at DESC);

-- ── Plant operating state (Layer 8, migration 011) ──────────────────────────
CREATE TABLE IF NOT EXISTS plant_operating_states (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    site_id    TEXT,
    state      TEXT CHECK (state IN ('normal', 'turnaround', 'shutdown', 'emergency')),
    set_by     TEXT,
    set_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_plant_state_site ON plant_operating_states(site_id, set_at DESC);

-- ── Layer 0 validation corpus (migration 014) ───────────────────────────────
CREATE TABLE IF NOT EXISTS validation_corpus (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id TEXT,
    entity_text TEXT,
    entity_type TEXT,
    span_start  INTEGER,
    span_end    INTEGER,
    authority   TEXT CHECK (authority IN ('human_promotion', 'annotation_correction')),
    promoted_by TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_corpus_entity   ON validation_corpus(entity_type);
CREATE INDEX IF NOT EXISTS idx_corpus_document ON validation_corpus(document_id);

-- ── Off-boarding interview series (Layer 9 / Flow D, migration 013) ──────────
CREATE TABLE IF NOT EXISTS offboarding_sessions (
    id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    personnel_id          TEXT,
    personnel_email       TEXT,
    retirement_date       DATE,
    total_sessions        INT DEFAULT 6,
    session_interval_days INT DEFAULT 12,
    status                TEXT CHECK (status IN ('scheduled', 'in_progress', 'completed', 'cancelled')),
    created_by            TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS offboarding_session_items (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          UUID REFERENCES offboarding_sessions(id) ON DELETE CASCADE,
    session_number      INT,
    equipment_family    TEXT,
    focus_failure_modes TEXT[],
    status              TEXT CHECK (status IN ('pending', 'questions_ready', 'completed')),
    questions           JSONB DEFAULT '[]',
    scheduled_for       TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_offboarding_items_session ON offboarding_session_items(session_id);

-- ── Row-Level Security (migrations 001, 004) ────────────────────────────────
ALTER TABLE assets            ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents         ENABLE ROW LEVEL SECURITY;
ALTER TABLE briefs            ENABLE ROW LEVEL SECURITY;
ALTER TABLE quarantine_items  ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log         ENABLE ROW LEVEL SECURITY;

-- The FastAPI backend uses the service-role key (bypasses RLS). These policies
-- apply only to direct anon/authenticated Supabase access.
DROP POLICY IF EXISTS briefs_recipient_isolation ON briefs;
CREATE POLICY briefs_recipient_isolation ON briefs
    FOR SELECT TO authenticated USING (recipient_user_id = (SELECT auth.uid())::text);

DROP POLICY IF EXISTS quarantine_submitter_isolation ON quarantine_items;
CREATE POLICY quarantine_submitter_isolation ON quarantine_items
    FOR SELECT TO authenticated USING (submitted_by = (SELECT auth.uid())::text);

-- ── Storage: immutable vault bucket (migrations 002, 016) ───────────────────
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'kairos-vault', 'kairos-vault', FALSE, 524288000,
    ARRAY['application/pdf', 'image/png', 'image/jpeg', 'image/tiff',
          'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'text/plain', 'text/csv', 'application/octet-stream',
          'audio/mpeg', 'audio/wav', 'audio/webm', 'audio/mp4', 'audio/ogg']  -- audio: migration 016
)
ON CONFLICT (id) DO UPDATE SET allowed_mime_types = EXCLUDED.allowed_mime_types;
