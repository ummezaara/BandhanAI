-- ============================================================================
-- Migration 006: Approved Customer Table Mappings
-- Run AFTER migration 005_tenant_data_connections.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.crm_customer_mappings (
    mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    connection_id UUID NOT NULL REFERENCES public.tenant_data_connections(connection_id) ON DELETE CASCADE,
    schema_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'rejected', 'superseded')),
    field_map JSONB NOT NULL,
    confidence NUMERIC,
    reasoning TEXT,
    safe_preview JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    approved_by UUID,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crm_customer_mappings_org_connection
    ON public.crm_customer_mappings(org_id, connection_id);

CREATE INDEX IF NOT EXISTS idx_crm_customer_mappings_status
    ON public.crm_customer_mappings(org_id, status);

ALTER TABLE public.crm_customer_mappings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS crm_customer_mappings_owner_policy
    ON public.crm_customer_mappings;

CREATE POLICY crm_customer_mappings_owner_policy
    ON public.crm_customer_mappings
    FOR ALL USING (
        org_id IN (
            SELECT org_id
            FROM public.tenants
            WHERE owner_auth_uid = auth.uid()
        )
    );

