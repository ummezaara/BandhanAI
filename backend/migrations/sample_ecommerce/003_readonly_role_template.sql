-- ============================================================================
-- Optional Read-only Role Template
-- ============================================================================
-- Replace the password before running.
-- Use this role's connection string in BandhanAI, not the Supabase postgres user.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bandhan_readonly') THEN
        CREATE ROLE bandhan_readonly WITH LOGIN PASSWORD 'replace_with_a_strong_password';
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO bandhan_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO bandhan_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO bandhan_readonly;
