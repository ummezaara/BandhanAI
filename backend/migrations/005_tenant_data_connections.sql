-- ============================================================================
-- Migration 005: Tenant-Owned Supabase Data Connections
-- Run AFTER migration 001_tenants.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.tenant_data_connections (
    connection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'supabase',
    display_name TEXT NOT NULL,
    project_url TEXT,
    encrypted_readonly_uri TEXT NOT NULL,
    default_schema TEXT NOT NULL DEFAULT 'public',
    allowed_schemas JSONB NOT NULL DEFAULT '["public"]'::jsonb,
    allowed_tables JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'connected', 'failed', 'disabled')),
    last_health_check_at TIMESTAMP,
    last_error TEXT,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tenant_data_connections_org_id
    ON public.tenant_data_connections(org_id);

CREATE INDEX IF NOT EXISTS idx_tenant_data_connections_status
    ON public.tenant_data_connections(org_id, status);

ALTER TABLE public.tenant_data_connections ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_data_connections_owner_policy
    ON public.tenant_data_connections;

CREATE POLICY tenant_data_connections_owner_policy
    ON public.tenant_data_connections
    FOR ALL USING (
        org_id IN (
            SELECT org_id
            FROM public.tenants
            WHERE owner_auth_uid = auth.uid()
        )
    );

