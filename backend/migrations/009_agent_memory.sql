-- ============================================================================
-- Migration 009: Agent Memories System
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.agent_memories (
    memory_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL DEFAULT 'default',
    scope TEXT NOT NULL CHECK (scope IN ('tenant', 'user', 'agent')),
    memory_type TEXT NOT NULL CHECK (memory_type IN (
        'preference', 'fact', 'strategy', 'decision',
        'campaign_learning', 'schema_learning'
    )),
    content TEXT NOT NULL,
    data JSONB DEFAULT '{}'::jsonb,
    importance INT DEFAULT 5 CHECK (importance BETWEEN 1 AND 10),
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_memories_org ON public.agent_memories(org_id, scope);
ALTER TABLE public.agent_memories ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_memories_owner_policy ON public.agent_memories;
CREATE POLICY agent_memories_owner_policy
    ON public.agent_memories
    FOR ALL USING (
        org_id IN (
            SELECT org_id
            FROM public.tenants
            WHERE owner_auth_uid = auth.uid()
        )
    );
