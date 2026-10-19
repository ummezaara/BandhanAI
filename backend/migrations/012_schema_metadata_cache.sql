-- ============================================================================
-- Migration 012: Tenant Schema Metadata Cache
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.schema_metadata_cache (
    metadata_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    connection_id UUID NOT NULL REFERENCES public.tenant_data_connections(connection_id) ON DELETE CASCADE,
    entity_map JSONB NOT NULL DEFAULT '{}'::jsonb,
    column_catalog JSONB NOT NULL DEFAULT '[]'::jsonb,
    join_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
    table_catalog JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence NUMERIC,
    errors JSONB NOT NULL DEFAULT '[]'::jsonb,
    discovered_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, connection_id)
);

CREATE INDEX IF NOT EXISTS idx_schema_metadata_cache_org_id
    ON public.schema_metadata_cache(org_id);

CREATE INDEX IF NOT EXISTS idx_schema_metadata_cache_connection_id
    ON public.schema_metadata_cache(connection_id);

ALTER TABLE public.schema_metadata_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY schema_metadata_cache_tenant_policy ON public.schema_metadata_cache
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );
