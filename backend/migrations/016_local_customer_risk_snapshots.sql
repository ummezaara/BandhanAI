-- Allow risk snapshots sourced from tenant-local customer records.
ALTER TABLE public.customer_risk_snapshots
    ALTER COLUMN connection_id DROP NOT NULL,
    ALTER COLUMN mapping_id DROP NOT NULL;

ALTER TABLE public.customer_risk_snapshots
    ADD COLUMN source_type TEXT NOT NULL DEFAULT 'connected';

ALTER TABLE public.customer_risk_snapshots
    ADD CONSTRAINT customer_risk_snapshots_source_type_check
    CHECK (
        (source_type = 'connected' AND connection_id IS NOT NULL AND mapping_id IS NOT NULL)
        OR
        (source_type = 'local' AND connection_id IS NULL AND mapping_id IS NULL)
    );
