-- ============================================================================
-- Migration 011: Audit Logging & Security Tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.audit_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    actor TEXT NOT NULL,                  -- 'user' or 'agent'
    action TEXT NOT NULL,                 -- 'supabase_connect', 'campaign_send', 'memory_save', etc.
    details JSONB,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_org_id ON public.audit_logs(org_id);

ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_logs_tenant_policy ON public.audit_logs
    FOR ALL USING (
        org_id IN (SELECT org_id FROM tenants WHERE owner_auth_uid = auth.uid())
    );
