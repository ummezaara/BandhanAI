-- ============================================================================
-- Migration 007: Explainable Customer Risk Snapshots
-- Run AFTER migration 006_crm_customer_mappings.sql
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.customer_risk_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    connection_id UUID NOT NULL REFERENCES public.tenant_data_connections(connection_id) ON DELETE CASCADE,
    mapping_id UUID NOT NULL REFERENCES public.crm_customer_mappings(mapping_id) ON DELETE CASCADE,
    external_customer_id TEXT,
    customer_label TEXT,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'unknown')),
    risk_score NUMERIC,
    reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
    computed_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_customer_risk_snapshots_org_id
    ON public.customer_risk_snapshots(org_id);

CREATE INDEX IF NOT EXISTS idx_customer_risk_snapshots_org_level
    ON public.customer_risk_snapshots(org_id, risk_level, computed_at DESC);

ALTER TABLE public.customer_risk_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS customer_risk_snapshots_owner_policy
    ON public.customer_risk_snapshots;

CREATE POLICY customer_risk_snapshots_owner_policy
    ON public.customer_risk_snapshots
    FOR ALL USING (
        org_id IN (
            SELECT org_id
            FROM public.tenants
            WHERE owner_auth_uid = auth.uid()
        )
    );

