-- =============================================================================
-- Kairos — FULL Supabase data reset (destructive)
-- =============================================================================
-- Empties EVERY table in the public schema (schema, RLS, and auth users kept).
-- Use to return the cloud DB to a pristine state before reloading the golden
-- dataset. `make nuke` only clears LOCAL Docker volumes — it never touches the
-- managed Supabase project, so this is the only way to clean the cloud store.
--
-- Applied via Supabase MCP on 2026-07-10 (see db/maintenance/CHANGELOG.md).
-- Reload afterwards: make seed && make load-dataset.
-- =============================================================================
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('TRUNCATE TABLE public.%I RESTART IDENTITY CASCADE', r.tablename);
  END LOOP;
END $$;
