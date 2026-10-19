-- ============================================================================
-- Migration 010: Stripe Billing Schema Updates
-- ============================================================================

ALTER TABLE public.tenants
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'active',
ADD COLUMN IF NOT EXISTS subscription_tier TEXT DEFAULT 'growth';
