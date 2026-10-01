-- 017: enable row-level security on the 14 public tables that lacked it (security review M1).
-- NOT APPLIED. Run it by hand against the live project (Supabase SQL editor or MCP) after review,
-- and record the run in db/maintenance/CHANGELOG.md.
--
-- Supabase exposes every `public` table through PostgREST, so with RLS off the public anon key can
-- read, write and delete these rows directly, bypassing the API, OPA and the audit log.
--
-- No policies are created on purpose. With RLS enabled and no policy, the anon and authenticated
-- roles see nothing. The FastAPI backend, workers and scripts use the service-role key, which
-- bypasses RLS, so they are unaffected. Idempotent: re-running is a no-op.
-- The other 5 tables (assets, documents, briefs, quarantine_items, audit_log) were done in 001/004.

ALTER TABLE asset_alias_map            ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_asset_links       ENABLE ROW LEVEL SECURITY;
ALTER TABLE extraction_jobs            ENABLE ROW LEVEL SECURITY;
ALTER TABLE operational_events         ENABLE ROW LEVEL SECURITY;
ALTER TABLE brief_feedback             ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_conflicts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE moc_items                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE elicitation_sessions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE ner_annotations            ENABLE ROW LEVEL SECURITY;
ALTER TABLE extraction_overrides       ENABLE ROW LEVEL SECURITY;
ALTER TABLE plant_operating_states     ENABLE ROW LEVEL SECURITY;
ALTER TABLE validation_corpus          ENABLE ROW LEVEL SECURITY;
ALTER TABLE offboarding_sessions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE offboarding_session_items  ENABLE ROW LEVEL SECURITY;
