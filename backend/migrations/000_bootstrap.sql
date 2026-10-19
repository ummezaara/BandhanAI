-- ============================================================================
-- Migration 000: Bootstrap Core CRM & Campaign Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.crm (
    customer_id bigint NOT NULL,
    name text NOT NULL,
    email text NOT NULL,
    region text,
    age bigint,
    income bigint,
    segment text,
    last_purchase timestamp without time zone,
    total_spend double precision,
    product_category text,
    churn_risk double precision,
    feedback_score double precision,
    products text[],
    CONSTRAINT crm_pkey PRIMARY KEY (customer_id)
);

CREATE TABLE IF NOT EXISTS public.marketing_campaigns (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL,
    type text,
    description text,
    status text DEFAULT 'draft'::text,
    created_at timestamp without time zone DEFAULT now(),
    CONSTRAINT marketing_campaigns_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.campaigning_emails (
    id bigserial NOT NULL,
    campaign_id uuid NOT NULL REFERENCES public.marketing_campaigns(id) ON DELETE CASCADE,
    customer_id bigint NOT NULL,
    email text NOT NULL,
    subject text NOT NULL,
    body text NOT NULL,
    sent_at timestamp without time zone DEFAULT now(),
    status text DEFAULT 'sent'::text,
    opened boolean NOT NULL DEFAULT false,
    CONSTRAINT campaigning_emails_pkey PRIMARY KEY (id)
);
