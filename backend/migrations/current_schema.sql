-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.tenants (
  org_id uuid NOT NULL DEFAULT gen_random_uuid(),
  owner_email text NOT NULL UNIQUE,
  owner_auth_uid uuid NOT NULL UNIQUE,
  org_name text NOT NULL,
  agent_name text DEFAULT 'Ralph'::text,
  backstory text,
  tone_instructions text,
  schema_def jsonb,
  created_at timestamp without time zone DEFAULT now(),
  stripe_customer_id text,
  subscription_status text DEFAULT 'active'::text,
  subscription_tier text DEFAULT 'growth'::text,
  CONSTRAINT tenants_pkey PRIMARY KEY (org_id)
);
CREATE TABLE public.integrations (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL UNIQUE,
  gmail_access_token text,
  gmail_refresh_token text,
  gmail_token_expiry timestamp without time zone,
  slack_bot_token text,
  slack_team_id text,
  connected_at timestamp without time zone DEFAULT now(),
  CONSTRAINT integrations_pkey PRIMARY KEY (id),
  CONSTRAINT integrations_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.customers (
  customer_id bigint NOT NULL DEFAULT nextval('customers_customer_id_seq'::regclass),
  org_id uuid NOT NULL,
  email text,
  data jsonb NOT NULL,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT customers_pkey PRIMARY KEY (customer_id),
  CONSTRAINT customers_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.marketing_campaigns (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  type text CHECK (type = ANY (ARRAY['loyalty'::text, 'referral'::text, 're-engagement'::text, 'at risk'::text, 'new customer'::text, 'champion'::text, 'about to sleep'::text, 'lost'::text, 'potential loyalist'::text])),
  description text,
  status text DEFAULT 'draft'::text,
  created_at timestamp without time zone DEFAULT now(),
  org_id uuid NOT NULL,
  CONSTRAINT marketing_campaigns_pkey PRIMARY KEY (id),
  CONSTRAINT marketing_campaigns_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.campaigning_emails (
  id bigint NOT NULL DEFAULT nextval('campaigning_emails_id_seq'::regclass),
  campaign_id uuid NOT NULL,
  customer_id bigint NOT NULL,
  email text NOT NULL,
  subject text NOT NULL,
  body text NOT NULL,
  sent_at timestamp without time zone DEFAULT now(),
  status text DEFAULT 'sent'::text,
  opened boolean NOT NULL DEFAULT false,
  org_id uuid NOT NULL,
  CONSTRAINT campaigning_emails_pkey PRIMARY KEY (id),
  CONSTRAINT campaigning_emails_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.marketing_campaigns(id),
  CONSTRAINT campaigning_emails_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.data_sources (
  source_id uuid NOT NULL DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  file_name text NOT NULL,
  source_type text,
  row_count integer,
  status text DEFAULT 'processing'::text,
  error_message text,
  uploaded_at timestamp without time zone DEFAULT now(),
  CONSTRAINT data_sources_pkey PRIMARY KEY (source_id),
  CONSTRAINT data_sources_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.schema_mappings (
  mapping_id uuid NOT NULL DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL,
  org_id uuid NOT NULL,
  original_columns jsonb NOT NULL,
  mapped_columns jsonb NOT NULL,
  join_key text,
  dropped_columns jsonb,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT schema_mappings_pkey PRIMARY KEY (mapping_id),
  CONSTRAINT schema_mappings_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.data_sources(source_id),
  CONSTRAINT schema_mappings_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.checkpoint_migrations (
  v integer NOT NULL,
  CONSTRAINT checkpoint_migrations_pkey PRIMARY KEY (v)
);
CREATE TABLE public.checkpoints (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT ''::text,
  checkpoint_id text NOT NULL,
  parent_checkpoint_id text,
  type text,
  checkpoint jsonb NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT checkpoints_pkey PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
CREATE TABLE public.checkpoint_blobs (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT ''::text,
  channel text NOT NULL,
  version text NOT NULL,
  type text NOT NULL,
  blob bytea,
  CONSTRAINT checkpoint_blobs_pkey PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);
CREATE TABLE public.checkpoint_writes (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT ''::text,
  checkpoint_id text NOT NULL,
  task_id text NOT NULL,
  idx integer NOT NULL,
  channel text NOT NULL,
  type text,
  blob bytea NOT NULL,
  task_path text NOT NULL DEFAULT ''::text,
  CONSTRAINT checkpoint_writes_pkey PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
CREATE TABLE public.chat_sessions (
  session_id uuid NOT NULL DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  user_auth_uid uuid NOT NULL,
  title text DEFAULT 'New Chat'::text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT chat_sessions_pkey PRIMARY KEY (session_id),
  CONSTRAINT chat_sessions_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.chat_messages (
  message_id uuid NOT NULL DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL,
  org_id uuid NOT NULL,
  role text NOT NULL CHECK (role = ANY (ARRAY['user'::text, 'assistant'::text, 'system'::text, 'tool'::text])),
  content text NOT NULL,
  metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT chat_messages_pkey PRIMARY KEY (message_id),
  CONSTRAINT chat_messages_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.chat_sessions(session_id)
);
CREATE TABLE public.agent_memories (
  memory_id uuid NOT NULL DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  agent_id text NOT NULL DEFAULT 'default'::text,
  scope text NOT NULL CHECK (scope = ANY (ARRAY['tenant'::text, 'user'::text, 'agent'::text])),
  memory_type text NOT NULL CHECK (memory_type = ANY (ARRAY['preference'::text, 'fact'::text, 'strategy'::text, 'decision'::text, 'campaign_learning'::text, 'schema_learning'::text])),
  content text NOT NULL,
  data jsonb DEFAULT '{}'::jsonb,
  importance integer DEFAULT 5 CHECK (importance >= 1 AND importance <= 10),
  source text,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT agent_memories_pkey PRIMARY KEY (memory_id),
  CONSTRAINT agent_memories_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.audit_logs (
  log_id uuid NOT NULL DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  actor text NOT NULL,
  action text NOT NULL,
  details jsonb,
  created_at timestamp without time zone DEFAULT now(),
  CONSTRAINT audit_logs_pkey PRIMARY KEY (log_id),
  CONSTRAINT audit_logs_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.crm (
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
  products ARRAY,
  org_id uuid NOT NULL,
  CONSTRAINT crm_pkey PRIMARY KEY (customer_id),
  CONSTRAINT crm_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.tenant_data_connections (
  connection_id uuid NOT NULL DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  provider text NOT NULL DEFAULT 'supabase'::text,
  display_name text NOT NULL,
  project_url text,
  encrypted_readonly_uri text NOT NULL,
  default_schema text NOT NULL DEFAULT 'public'::text,
  allowed_schemas jsonb NOT NULL DEFAULT '["public"]'::jsonb,
  allowed_tables jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'pending'::text CHECK (status = ANY (ARRAY['pending'::text, 'connected'::text, 'failed'::text, 'disabled'::text])),
  last_health_check_at timestamp without time zone,
  last_error text,
  created_at timestamp without time zone DEFAULT now(),
  updated_at timestamp without time zone DEFAULT now(),
  CONSTRAINT tenant_data_connections_pkey PRIMARY KEY (connection_id),
  CONSTRAINT tenant_data_connections_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
CREATE TABLE public.crm_customer_mappings (
  mapping_id uuid NOT NULL DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  connection_id uuid NOT NULL,
  schema_name text NOT NULL,
  table_name text NOT NULL,
  status text NOT NULL DEFAULT 'draft'::text CHECK (status = ANY (ARRAY['draft'::text, 'approved'::text, 'rejected'::text, 'superseded'::text])),
  field_map jsonb NOT NULL,
  confidence numeric,
  reasoning text,
  safe_preview jsonb NOT NULL DEFAULT '[]'::jsonb,
  missing_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
  approved_by uuid,
  approved_at timestamp without time zone,
  created_at timestamp without time zone DEFAULT now(),
  updated_at timestamp without time zone DEFAULT now(),
  CONSTRAINT crm_customer_mappings_pkey PRIMARY KEY (mapping_id),
  CONSTRAINT crm_customer_mappings_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id),
  CONSTRAINT crm_customer_mappings_connection_id_fkey FOREIGN KEY (connection_id) REFERENCES public.tenant_data_connections(connection_id)
);
CREATE TABLE public.customer_risk_snapshots (
  snapshot_id uuid NOT NULL DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  connection_id uuid NOT NULL,
  mapping_id uuid NOT NULL,
  external_customer_id text,
  customer_label text,
  risk_level text NOT NULL CHECK (risk_level = ANY (ARRAY['low'::text, 'medium'::text, 'high'::text, 'unknown'::text])),
  risk_score numeric,
  reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  source_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
  computed_at timestamp without time zone DEFAULT now(),
  CONSTRAINT customer_risk_snapshots_pkey PRIMARY KEY (snapshot_id),
  CONSTRAINT customer_risk_snapshots_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id),
  CONSTRAINT customer_risk_snapshots_connection_id_fkey FOREIGN KEY (connection_id) REFERENCES public.tenant_data_connections(connection_id),
  CONSTRAINT customer_risk_snapshots_mapping_id_fkey FOREIGN KEY (mapping_id) REFERENCES public.crm_customer_mappings(mapping_id)
);
CREATE TABLE public.schema_metadata_cache (
  metadata_id uuid NOT NULL DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL,
  connection_id uuid NOT NULL,
  entity_map jsonb NOT NULL DEFAULT '{}'::jsonb,
  column_catalog jsonb NOT NULL DEFAULT '[]'::jsonb,
  join_paths jsonb NOT NULL DEFAULT '[]'::jsonb,
  table_catalog jsonb NOT NULL DEFAULT '[]'::jsonb,
  confidence numeric,
  errors jsonb NOT NULL DEFAULT '[]'::jsonb,
  discovered_at timestamp with time zone DEFAULT now(),
  CONSTRAINT schema_metadata_cache_pkey PRIMARY KEY (metadata_id),
  CONSTRAINT schema_metadata_cache_org_connection_key UNIQUE (org_id, connection_id),
  CONSTRAINT schema_metadata_cache_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id),
  CONSTRAINT schema_metadata_cache_connection_id_fkey FOREIGN KEY (connection_id) REFERENCES public.tenant_data_connections(connection_id)
);
CREATE TABLE public.campaign_recipients (
  recipient_id uuid NOT NULL DEFAULT gen_random_uuid(),
  campaign_id uuid NOT NULL,
  org_id uuid NOT NULL,
  customer_name text,
  customer_email text NOT NULL,
  subject text,
  body text,
  recommended_products jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text DEFAULT 'pending'::text CHECK (status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text])),
  sent_at timestamp with time zone,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT campaign_recipients_pkey PRIMARY KEY (recipient_id),
  CONSTRAINT campaign_recipients_campaign_id_fkey FOREIGN KEY (campaign_id) REFERENCES public.marketing_campaigns(id),
  CONSTRAINT campaign_recipients_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.tenants(org_id)
);
