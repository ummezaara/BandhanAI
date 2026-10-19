-- ============================================================================
-- Migration 014: Update campaign_recipients status constraint
-- ============================================================================

DO $$
BEGIN
    -- Drop existing check constraint if present
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'campaign_recipients_status_check'
          AND table_name = 'campaign_recipients'
    ) THEN
        ALTER TABLE public.campaign_recipients DROP CONSTRAINT campaign_recipients_status_check;
    END IF;
END $$;

-- Re-add constraint with expanded statuses
ALTER TABLE public.campaign_recipients
    ADD CONSTRAINT campaign_recipients_status_check
    CHECK (status IN ('pending', 'approved', 'excluded', 'sent', 'failed'));
