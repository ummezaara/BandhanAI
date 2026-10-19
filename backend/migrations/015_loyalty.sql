-- ============================================================================
-- Migration 015: Tenant-scoped Loyalty & Rewards
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.loyalty_program_settings (
    org_id UUID PRIMARY KEY REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    purchase_amount NUMERIC(12, 2) NOT NULL DEFAULT 100 CHECK (purchase_amount > 0),
    base_points NUMERIC(12, 2) NOT NULL DEFAULT 10 CHECK (base_points > 0),
    point_expiry_months INTEGER NOT NULL DEFAULT 12 CHECK (point_expiry_months > 0),
    referrer_reward_points NUMERIC(12, 2) NOT NULL DEFAULT 200 CHECK (referrer_reward_points > 0),
    referred_reward_points NUMERIC(12, 2) NOT NULL DEFAULT 100 CHECK (referred_reward_points > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.loyalty_tier_rules (
    tier_rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    tier TEXT NOT NULL CHECK (tier IN ('Bronze', 'Silver', 'Gold', 'Platinum')),
    min_lifetime_points NUMERIC(12, 2) NOT NULL CHECK (min_lifetime_points >= 0),
    max_lifetime_points NUMERIC(12, 2),
    points_multiplier NUMERIC(8, 2) NOT NULL CHECK (points_multiplier > 0),
    UNIQUE (org_id, tier),
    UNIQUE (org_id, min_lifetime_points),
    CHECK (max_lifetime_points IS NULL OR max_lifetime_points >= min_lifetime_points)
);

CREATE TABLE IF NOT EXISTS public.loyalty_customer_accounts (
    loyalty_customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    display_name TEXT,
    email TEXT,
    available_points NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (available_points >= 0),
    lifetime_eligible_points NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (lifetime_eligible_points >= 0),
    current_tier TEXT NOT NULL DEFAULT 'Bronze'
        CHECK (current_tier IN ('Bronze', 'Silver', 'Gold', 'Platinum')),
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, loyalty_customer_id)
);

CREATE TABLE IF NOT EXISTS public.loyalty_customer_identities (
    identity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    loyalty_customer_id UUID NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('platform', 'external', 'import', 'manual', 'demo')),
    source_namespace TEXT NOT NULL,
    source_customer_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (org_id, loyalty_customer_id)
        REFERENCES public.loyalty_customer_accounts(org_id, loyalty_customer_id) ON DELETE CASCADE,
    UNIQUE (org_id, source_type, source_namespace, source_customer_key),
    UNIQUE (org_id, identity_id)
);

CREATE TABLE IF NOT EXISTS public.loyalty_rewards (
    reward_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    points_cost NUMERIC(12, 2) NOT NULL CHECK (points_cost > 0),
    reward_value NUMERIC(12, 2) NOT NULL CHECK (reward_value > 0),
    currency TEXT NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, reward_id),
    UNIQUE (org_id, points_cost)
);

CREATE TABLE IF NOT EXISTS public.loyalty_transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    loyalty_customer_id UUID NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN (
        'earn', 'redeem', 'expiry', 'referral', 'bonus', 'manual_adjustment'
    )),
    points_delta NUMERIC(12, 2) NOT NULL CHECK (points_delta <> 0),
    lifetime_points_delta NUMERIC(12, 2) NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL,
    source_reference TEXT,
    description TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    actor_auth_uid UUID,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (org_id, loyalty_customer_id)
        REFERENCES public.loyalty_customer_accounts(org_id, loyalty_customer_id) ON DELETE CASCADE,
    UNIQUE (org_id, idempotency_key),
    UNIQUE (transaction_id, org_id, loyalty_customer_id),
    CHECK (
        (
            is_demo
            AND transaction_type = 'manual_adjustment'
            AND lifetime_points_delta = 0
        )
        OR (
            NOT is_demo
            AND (
                (transaction_type IN ('earn', 'referral', 'bonus') AND points_delta > 0 AND lifetime_points_delta = points_delta)
                OR (transaction_type = 'manual_adjustment' AND lifetime_points_delta = points_delta)
                OR (transaction_type IN ('redeem', 'expiry') AND points_delta < 0 AND lifetime_points_delta = 0)
            )
        )
    ),
    CHECK (is_demo OR points_delta <= 0 OR expires_at IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS public.loyalty_purchase_events (
    purchase_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    loyalty_customer_id UUID NOT NULL,
    source_namespace TEXT NOT NULL,
    source_event_key TEXT NOT NULL,
    purchase_amount NUMERIC(12, 2) NOT NULL CHECK (purchase_amount > 0),
    currency TEXT NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
    purchased_at TIMESTAMPTZ NOT NULL,
    verification_reference TEXT NOT NULL CHECK (length(trim(verification_reference)) > 0),
    is_verified BOOLEAN NOT NULL DEFAULT TRUE CHECK (is_verified),
    is_demo BOOLEAN NOT NULL DEFAULT FALSE,
    transaction_id UUID,
    imported_by UUID NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (org_id, loyalty_customer_id)
        REFERENCES public.loyalty_customer_accounts(org_id, loyalty_customer_id) ON DELETE CASCADE,
    FOREIGN KEY (transaction_id, org_id, loyalty_customer_id)
        REFERENCES public.loyalty_transactions(transaction_id, org_id, loyalty_customer_id),
    UNIQUE (org_id, source_namespace, source_event_key),
    UNIQUE (org_id, purchase_event_id)
);

CREATE TABLE IF NOT EXISTS public.loyalty_point_allocations (
    allocation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    loyalty_customer_id UUID NOT NULL,
    earning_transaction_id UUID NOT NULL,
    consuming_transaction_id UUID NOT NULL,
    points_allocated NUMERIC(12, 2) NOT NULL CHECK (points_allocated > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (earning_transaction_id, org_id, loyalty_customer_id)
        REFERENCES public.loyalty_transactions(transaction_id, org_id, loyalty_customer_id),
    FOREIGN KEY (consuming_transaction_id, org_id, loyalty_customer_id)
        REFERENCES public.loyalty_transactions(transaction_id, org_id, loyalty_customer_id),
    UNIQUE (org_id, earning_transaction_id, consuming_transaction_id)
);

CREATE TABLE IF NOT EXISTS public.loyalty_redemptions (
    redemption_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    loyalty_customer_id UUID NOT NULL,
    reward_id UUID NOT NULL,
    transaction_id UUID NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('issued', 'fulfilled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (org_id, loyalty_customer_id)
        REFERENCES public.loyalty_customer_accounts(org_id, loyalty_customer_id) ON DELETE CASCADE,
    FOREIGN KEY (org_id, reward_id)
        REFERENCES public.loyalty_rewards(org_id, reward_id),
    FOREIGN KEY (transaction_id, org_id, loyalty_customer_id)
        REFERENCES public.loyalty_transactions(transaction_id, org_id, loyalty_customer_id),
    UNIQUE (org_id, redemption_id)
);

CREATE TABLE IF NOT EXISTS public.loyalty_referrals (
    referral_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    referrer_customer_id UUID NOT NULL,
    referred_customer_id UUID NOT NULL,
    referral_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'qualified')),
    qualified_purchase_event_id UUID,
    referrer_transaction_id UUID UNIQUE,
    referred_transaction_id UUID UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    qualified_at TIMESTAMPTZ,
    FOREIGN KEY (org_id, referrer_customer_id)
        REFERENCES public.loyalty_customer_accounts(org_id, loyalty_customer_id) ON DELETE CASCADE,
    FOREIGN KEY (org_id, referred_customer_id)
        REFERENCES public.loyalty_customer_accounts(org_id, loyalty_customer_id) ON DELETE CASCADE,
    FOREIGN KEY (org_id, qualified_purchase_event_id)
        REFERENCES public.loyalty_purchase_events(org_id, purchase_event_id),
    FOREIGN KEY (referrer_transaction_id, org_id, referrer_customer_id)
        REFERENCES public.loyalty_transactions(transaction_id, org_id, loyalty_customer_id),
    FOREIGN KEY (referred_transaction_id, org_id, referred_customer_id)
        REFERENCES public.loyalty_transactions(transaction_id, org_id, loyalty_customer_id),
    UNIQUE (org_id, referral_code),
    UNIQUE (org_id, referred_customer_id),
    CHECK (referrer_customer_id <> referred_customer_id),
    CHECK (
        (status = 'pending' AND qualified_at IS NULL)
        OR (status = 'qualified' AND qualified_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS public.loyalty_bonus_campaigns (
    bonus_campaign_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    points_multiplier NUMERIC(8, 2) NOT NULL CHECK (points_multiplier > 1),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'ended')),
    eligibility JSONB NOT NULL DEFAULT '{}'::jsonb,
    idempotency_key TEXT NOT NULL,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, bonus_campaign_id),
    UNIQUE (org_id, idempotency_key),
    CHECK (ends_at > starts_at)
);

CREATE OR REPLACE FUNCTION public.prevent_loyalty_history_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Loyalty history is append-only; use a compensating transaction.';
END;
$$;

DROP TRIGGER IF EXISTS loyalty_transactions_append_only ON public.loyalty_transactions;
CREATE TRIGGER loyalty_transactions_append_only
    BEFORE UPDATE OR DELETE ON public.loyalty_transactions
    FOR EACH ROW EXECUTE FUNCTION public.prevent_loyalty_history_mutation();

DROP TRIGGER IF EXISTS loyalty_point_allocations_append_only ON public.loyalty_point_allocations;
CREATE TRIGGER loyalty_point_allocations_append_only
    BEFORE UPDATE OR DELETE ON public.loyalty_point_allocations
    FOR EACH ROW EXECUTE FUNCTION public.prevent_loyalty_history_mutation();

CREATE INDEX IF NOT EXISTS idx_loyalty_accounts_org_tier
    ON public.loyalty_customer_accounts(org_id, current_tier);
CREATE INDEX IF NOT EXISTS idx_loyalty_identities_customer
    ON public.loyalty_customer_identities(org_id, loyalty_customer_id);
CREATE INDEX IF NOT EXISTS idx_loyalty_transactions_customer_created
    ON public.loyalty_transactions(org_id, loyalty_customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_loyalty_transactions_expiry
    ON public.loyalty_transactions(org_id, expires_at)
    WHERE transaction_type = 'earn' AND expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_loyalty_purchase_customer_time
    ON public.loyalty_purchase_events(org_id, loyalty_customer_id, purchased_at DESC);
CREATE INDEX IF NOT EXISTS idx_loyalty_referrals_pending
    ON public.loyalty_referrals(org_id, referred_customer_id)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_loyalty_bonus_campaigns_period
    ON public.loyalty_bonus_campaigns(org_id, starts_at, ends_at)
    WHERE status = 'active';

-- Initialize each tenant's configurable defaults, including tenants created later.
CREATE OR REPLACE FUNCTION public.initialize_loyalty_defaults()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    INSERT INTO public.loyalty_program_settings (org_id)
    VALUES (NEW.org_id)
    ON CONFLICT (org_id) DO NOTHING;

    INSERT INTO public.loyalty_tier_rules
        (org_id, tier, min_lifetime_points, max_lifetime_points, points_multiplier)
    VALUES
        (NEW.org_id, 'Bronze', 0, 499.99, 1),
        (NEW.org_id, 'Silver', 500, 1999.99, 1.25),
        (NEW.org_id, 'Gold', 2000, 4999.99, 1.5),
        (NEW.org_id, 'Platinum', 5000, NULL, 2)
    ON CONFLICT (org_id, tier) DO NOTHING;

    INSERT INTO public.loyalty_rewards (org_id, name, points_cost, reward_value)
    VALUES
        (NEW.org_id, 'INR 50 Reward', 500, 50),
        (NEW.org_id, 'INR 120 Reward', 1000, 120),
        (NEW.org_id, 'INR 350 Reward', 2500, 350),
        (NEW.org_id, 'INR 750 Reward', 5000, 750)
    ON CONFLICT (org_id, points_cost) DO NOTHING;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS tenants_initialize_loyalty_defaults ON public.tenants;
CREATE TRIGGER tenants_initialize_loyalty_defaults
    AFTER INSERT ON public.tenants
    FOR EACH ROW EXECUTE FUNCTION public.initialize_loyalty_defaults();

REVOKE EXECUTE ON FUNCTION public.initialize_loyalty_defaults() FROM PUBLIC;

DO $$
BEGIN
    INSERT INTO public.loyalty_program_settings (org_id)
    SELECT org_id FROM public.tenants
    ON CONFLICT (org_id) DO NOTHING;

    INSERT INTO public.loyalty_tier_rules
        (org_id, tier, min_lifetime_points, max_lifetime_points, points_multiplier)
    SELECT t.org_id, tiers.tier, tiers.min_points, tiers.max_points, tiers.multiplier
    FROM public.tenants t
    CROSS JOIN (VALUES
        ('Bronze', 0::NUMERIC, 499.99::NUMERIC, 1::NUMERIC),
        ('Silver', 500::NUMERIC, 1999.99::NUMERIC, 1.25::NUMERIC),
        ('Gold', 2000::NUMERIC, 4999.99::NUMERIC, 1.5::NUMERIC),
        ('Platinum', 5000::NUMERIC, NULL::NUMERIC, 2::NUMERIC)
    ) AS tiers(tier, min_points, max_points, multiplier)
    ON CONFLICT (org_id, tier) DO NOTHING;

    INSERT INTO public.loyalty_rewards (org_id, name, points_cost, reward_value)
    SELECT t.org_id, rewards.name, rewards.points_cost, rewards.reward_value
    FROM public.tenants t
    CROSS JOIN (VALUES
        ('INR 50 Reward', 500::NUMERIC, 50::NUMERIC),
        ('INR 120 Reward', 1000::NUMERIC, 120::NUMERIC),
        ('INR 350 Reward', 2500::NUMERIC, 350::NUMERIC),
        ('INR 750 Reward', 5000::NUMERIC, 750::NUMERIC)
    ) AS rewards(name, points_cost, reward_value)
    ON CONFLICT (org_id, points_cost) DO NOTHING;
END;
$$;

ALTER TABLE public.loyalty_program_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loyalty_tier_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loyalty_customer_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loyalty_customer_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loyalty_rewards ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loyalty_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loyalty_purchase_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loyalty_point_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loyalty_redemptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loyalty_referrals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.loyalty_bonus_campaigns ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS loyalty_program_settings_owner_policy ON public.loyalty_program_settings;
CREATE POLICY loyalty_program_settings_owner_policy ON public.loyalty_program_settings
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DROP POLICY IF EXISTS loyalty_tier_rules_owner_policy ON public.loyalty_tier_rules;
CREATE POLICY loyalty_tier_rules_owner_policy ON public.loyalty_tier_rules
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DROP POLICY IF EXISTS loyalty_customer_accounts_owner_policy ON public.loyalty_customer_accounts;
CREATE POLICY loyalty_customer_accounts_owner_policy ON public.loyalty_customer_accounts
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DROP POLICY IF EXISTS loyalty_customer_identities_owner_policy ON public.loyalty_customer_identities;
CREATE POLICY loyalty_customer_identities_owner_policy ON public.loyalty_customer_identities
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DROP POLICY IF EXISTS loyalty_rewards_owner_policy ON public.loyalty_rewards;
CREATE POLICY loyalty_rewards_owner_policy ON public.loyalty_rewards
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DROP POLICY IF EXISTS loyalty_transactions_owner_policy ON public.loyalty_transactions;
CREATE POLICY loyalty_transactions_owner_policy ON public.loyalty_transactions
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DROP POLICY IF EXISTS loyalty_purchase_events_owner_policy ON public.loyalty_purchase_events;
CREATE POLICY loyalty_purchase_events_owner_policy ON public.loyalty_purchase_events
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DROP POLICY IF EXISTS loyalty_point_allocations_owner_policy ON public.loyalty_point_allocations;
CREATE POLICY loyalty_point_allocations_owner_policy ON public.loyalty_point_allocations
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DROP POLICY IF EXISTS loyalty_redemptions_owner_policy ON public.loyalty_redemptions;
CREATE POLICY loyalty_redemptions_owner_policy ON public.loyalty_redemptions
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DROP POLICY IF EXISTS loyalty_referrals_owner_policy ON public.loyalty_referrals;
CREATE POLICY loyalty_referrals_owner_policy ON public.loyalty_referrals
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DROP POLICY IF EXISTS loyalty_bonus_campaigns_owner_policy ON public.loyalty_bonus_campaigns;
CREATE POLICY loyalty_bonus_campaigns_owner_policy ON public.loyalty_bonus_campaigns
    FOR ALL USING (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    ) WITH CHECK (
        org_id IN (SELECT org_id FROM public.tenants WHERE owner_auth_uid = auth.uid())
    );

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'loyalty_program_settings',
        'loyalty_tier_rules',
        'loyalty_customer_accounts',
        'loyalty_customer_identities',
        'loyalty_rewards',
        'loyalty_transactions',
        'loyalty_purchase_events',
        'loyalty_point_allocations',
        'loyalty_redemptions',
        'loyalty_referrals',
        'loyalty_bonus_campaigns'
    ] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', table_name);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE format('REVOKE ALL ON TABLE public.%I FROM authenticated', table_name);
        END IF;
    END LOOP;
END $$;
