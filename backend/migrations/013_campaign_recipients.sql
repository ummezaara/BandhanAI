-- ============================================================================
-- Migration 013: Campaign Recipient Previews and Send Tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.campaign_recipients (
    recipient_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES public.marketing_campaigns(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    customer_name TEXT,
    customer_email TEXT NOT NULL,
    subject TEXT,
    body TEXT,
    recommended_products JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_campaign_recipients_org_id
    ON public.campaign_recipients(org_id);

CREATE INDEX IF NOT EXISTS idx_campaign_recipients_campaign_id
    ON public.campaign_recipients(campaign_id);

ALTER TABLE public.campaign_recipients ENABLE ROW LEVEL SECURITY;

CREATE POLICY campaign_recipients_tenant_policy ON public.campaign_recipients
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );
