-- ============================================================================
-- Migration 008: Chat Sessions and Messages History
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.chat_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenants(org_id) ON DELETE CASCADE,
    user_auth_uid UUID NOT NULL,
    title TEXT DEFAULT 'New Chat',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.chat_messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.chat_sessions(session_id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON public.chat_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_org ON public.chat_sessions(org_id);

ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS chat_sessions_owner_policy ON public.chat_sessions;
CREATE POLICY chat_sessions_owner_policy
    ON public.chat_sessions
    FOR ALL USING (
        org_id IN (
            SELECT org_id
            FROM public.tenants
            WHERE owner_auth_uid = auth.uid()
        )
    );

DROP POLICY IF EXISTS chat_messages_owner_policy ON public.chat_messages;
CREATE POLICY chat_messages_owner_policy
    ON public.chat_messages
    FOR ALL USING (
        org_id IN (
            SELECT org_id
            FROM public.tenants
            WHERE owner_auth_uid = auth.uid()
        )
    );
