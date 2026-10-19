"use client";

import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { api } from "@/lib/api";
import OnboardingFlow from "@/components/onboarding/onboarding-flow";
import { useTenantStore } from "@/store/tenant-store";
import { Bot, Database, Edit3, Link2, Loader2, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import toast from "react-hot-toast";

const getErrorMessage = (error: unknown, fallback: string) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    return typeof detail === "string" ? detail : fallback;
  }

  return error instanceof Error ? error.message : fallback;
};

type ConnectionStatus = "pending" | "connected" | "failed" | "disabled";

interface ConnectionHealth {
  ok: boolean;
  status: ConnectionStatus;
  message: string;
  database?: string | null;
  current_user?: string | null;
  default_schema: string;
  table_count: number;
  warnings: string[];
}

interface TenantDataConnection {
  connection_id: string;
  display_name: string;
  project_url?: string | null;
  default_schema: string;
  allowed_schemas: string[];
  allowed_tables: string[];
  status: ConnectionStatus;
  last_health_check_at?: string | null;
  last_error?: string | null;
}

interface CustomerFieldCandidate {
  source_column: string;
  canonical_field: string;
  confidence: number;
  reason: string;
}

interface CustomerMapping {
  mapping_id: string;
  connection_id: string;
  schema_name: string;
  table_name: string;
  status: "draft" | "approved" | "rejected" | "superseded";
  field_map: Record<string, CustomerFieldCandidate>;
  confidence: number;
  reasoning: string;
  safe_preview: Record<string, unknown>[];
  missing_fields: string[];
}

type CustomerField =
  | "customer_id"
  | "name"
  | "email"
  | "phone"
  | "total_spend"
  | "total_orders"
  | "last_purchase"
  | "churn_risk"
  | "feedback_score";

const editableCustomerFields: { value: CustomerField; label: string }[] = [
  { value: "customer_id", label: "Customer ID" },
  { value: "name", label: "Name" },
  { value: "email", label: "Email" },
  { value: "phone", label: "Phone" },
  { value: "total_spend", label: "Total spend" },
  { value: "total_orders", label: "Total orders" },
  { value: "last_purchase", label: "Last purchase" },
  { value: "churn_risk", label: "Churn risk" },
  { value: "feedback_score", label: "Feedback score" },
];

interface SchemaColumn {
  schema: string;
  table_name: string;
  column: string;
  data_type: string;
}

interface SchemaMetadata {
  metadata_id: string;
  connection_id: string;
  entity_map: Record<string, string>;
  column_catalog: SchemaColumn[];
  join_paths: Array<Record<string, unknown>>;
  table_catalog: Array<Record<string, unknown>>;
  confidence?: number | null;
  errors: string[];
  discovered_at?: string | null;
}

export default function SettingsPage() {
  const {
    orgName,
    agentName,
    backstory,
    toneInstructions,
    schemaDef,
    integrations,
    fetchTenantSettings,
  } = useTenantStore();

  const [showPersonaEditor, setShowPersonaEditor] = useState(false);
  const [connections, setConnections] = useState<TenantDataConnection[]>([]);
  const [connectionsLoading, setConnectionsLoading] = useState(true);
  const [connectionName, setConnectionName] = useState("Primary Supabase");
  const [projectUrl, setProjectUrl] = useState("");
  const [readonlyUri, setReadonlyUri] = useState("");
  const [defaultSchema, setDefaultSchema] = useState("public");
  const [testingConnection, setTestingConnection] = useState(false);
  const [savingConnection, setSavingConnection] = useState(false);
  const [health, setHealth] = useState<ConnectionHealth | null>(null);
  const [discoveringConnectionId, setDiscoveringConnectionId] = useState<string | null>(null);
  const [customerMappings, setCustomerMappings] = useState<Record<string, CustomerMapping | null>>({});
  const [schemaMetadata, setSchemaMetadata] = useState<Record<string, SchemaMetadata | null>>({});
  const [mappingFieldAssignments, setMappingFieldAssignments] = useState<
    Record<string, Record<string, CustomerField | null>>
  >({});
  const [savingFieldMappingId, setSavingFieldMappingId] = useState<string | null>(null);

  const [billingStatus, setBillingStatus] = useState<any>(null);
  const [loadingBilling, setLoadingBilling] = useState(true);
  const [upgradingTier, setUpgradingTier] = useState<string | null>(null);

  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(true);

  const fetchAuditLogs = useCallback(async () => {
    try {
      setLoadingAudit(true);
      const res = await api.get("/audit");
      setAuditLogs(res.data.logs || []);
    } catch (e) {
      console.error("Failed to load audit logs:", e);
    } finally {
      setLoadingAudit(false);
    }
  }, []);

  const fetchBillingStatus = useCallback(async () => {
    try {
      setLoadingBilling(true);
      const res = await api.get("/billing/status");
      setBillingStatus(res.data);
    } catch (e) {
      console.error("Failed to load billing status:", e);
    } finally {
      setLoadingBilling(false);
    }
  }, []);

  const handleUpgrade = async (tier: string) => {
    setUpgradingTier(tier);
    try {
      const res = await api.post("/billing/upgrade", { tier });
      if (res.data.success) {
        toast.success(`Plan successfully upgraded to ${tier}!`);
        await fetchBillingStatus();
      }
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to upgrade subscription tier"));
    } finally {
      setUpgradingTier(null);
    }
  };

  const fetchCustomerMapping = useCallback(async (connectionId: string) => {
    try {
      const res = await api.get<{ mapping: CustomerMapping | null }>(
        `/connections/${connectionId}/customer-mapping`
      );
      setCustomerMappings((prev) => ({
        ...prev,
        [connectionId]: res.data.mapping,
      }));
    } catch (e) {
      console.error("Failed to fetch customer mapping:", e);
    }
  }, []);

  const fetchSchemaMetadata = useCallback(async (connectionId: string) => {
    try {
      const res = await api.get<{ metadata: SchemaMetadata | null }>(
        `/connections/${connectionId}/schema-metadata`
      );
      setSchemaMetadata((prev) => ({
        ...prev,
        [connectionId]: res.data.metadata,
      }));
    } catch (e) {
      console.error("Failed to fetch schema metadata:", e);
    }
  }, []);

  const fetchConnections = useCallback(async () => {
    setConnectionsLoading(true);
    try {
      const res = await api.get<{ connections: TenantDataConnection[] }>("/connections");
      setConnections(res.data.connections);
      for (const connection of res.data.connections) {
        void fetchCustomerMapping(connection.connection_id);
        void fetchSchemaMetadata(connection.connection_id);
      }
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Failed to load Supabase connections."));
    } finally {
      setConnectionsLoading(false);
    }
  }, [fetchCustomerMapping, fetchSchemaMetadata]);

  useEffect(() => {
    fetchTenantSettings();
    queueMicrotask(() => {
      void fetchConnections();
      void fetchBillingStatus();
      void fetchAuditLogs();
    });
  }, [fetchTenantSettings, fetchConnections, fetchBillingStatus, fetchAuditLogs]);

  const handleConnectGmail = async () => {
    try {
      toast.loading("Initiating Google Secure Connect...", { id: "oauth" });
      const res = await api.get("/auth/gmail/connect");
      toast.success("Redirecting to Google authorization...", { id: "oauth" });
      window.location.href = res.data.auth_url;
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Failed to trigger Gmail OAuth connection."), {
        id: "oauth",
      });
    }
  };

  const handleConnectSlack = async () => {
    try {
      toast.loading("Initiating Slack App Connect...", { id: "oauth" });
      const res = await api.get("/auth/slack/connect");
      toast.success("Redirecting to Slack authorization...", { id: "oauth" });
      window.location.href = res.data.auth_url;
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Failed to trigger Slack OAuth connection."), {
        id: "oauth",
      });
    }
  };

  const handlePersonaComplete = async () => {
    setShowPersonaEditor(false);
    await fetchTenantSettings();
  };

  const handleTestSupabase = async () => {
    if (!readonlyUri.trim()) {
      toast.error("Paste a read-only Supabase Postgres connection string first.");
      return;
    }

    setTestingConnection(true);
    setHealth(null);
    try {
      const res = await api.post<ConnectionHealth>("/connections/supabase/test", {
        readonly_uri: readonlyUri.trim(),
        default_schema: defaultSchema.trim() || "public",
      });
      setHealth(res.data);
      if (res.data.ok) {
        toast.success("Supabase connection verified.");
      } else {
        toast.error(res.data.message || "Connection test failed.");
      }
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Connection test failed."));
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSaveSupabase = async () => {
    if (!connectionName.trim() || !readonlyUri.trim()) {
      toast.error("Connection name and read-only URI are required.");
      return;
    }

    setSavingConnection(true);
    try {
      const res = await api.post<{ connection: TenantDataConnection; health: ConnectionHealth }>(
        "/connections/supabase",
        {
          display_name: connectionName.trim(),
          readonly_uri: readonlyUri.trim(),
          project_url: projectUrl.trim() || null,
          default_schema: defaultSchema.trim() || "public",
          allowed_schemas: [defaultSchema.trim() || "public"],
          allowed_tables: [],
        }
      );
      setHealth(res.data.health);
      setReadonlyUri("");
      await fetchConnections();
      toast.success("Supabase connection saved.");
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Failed to save Supabase connection."));
    } finally {
      setSavingConnection(false);
    }
  };

  const handleHealthCheck = async (connectionId: string) => {
    try {
      const res = await api.post<ConnectionHealth>(
        `/connections/${connectionId}/health-check`
      );
      setHealth(res.data);
      await fetchConnections();
      toast.success(res.data.ok ? "Connection is healthy." : "Connection check completed.");
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Health check failed."));
    }
  };

  const handleDeleteConnection = async (connectionId: string) => {
    try {
      await api.delete(`/connections/${connectionId}`);
      await fetchConnections();
      toast.success("Supabase connection removed.");
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Failed to remove connection."));
    }
  };

  const handleDiscoverCustomers = async (connectionId: string) => {
    setDiscoveringConnectionId(connectionId);
    try {
      const res = await api.post<{ mapping: CustomerMapping | null; candidates: CustomerMapping[] }>(
        `/connections/${connectionId}/discover/customers`
      );
      setCustomerMappings((prev) => ({
        ...prev,
        [connectionId]: res.data.mapping,
      }));
      if (res.data.mapping) {
        toast.success("Customer table candidate found.");
      } else {
        toast.error("No strong customer table candidate found.");
      }
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Customer discovery failed."));
    } finally {
      setDiscoveringConnectionId(null);
    }
  };

  const handleDiscoverSchema = async (connectionId: string) => {
    setDiscoveringConnectionId(connectionId);
    try {
      const res = await api.post<{ metadata: SchemaMetadata | null }>(
        `/connections/${connectionId}/discover/schema`
      );
      setSchemaMetadata((prev) => ({
        ...prev,
        [connectionId]: res.data.metadata,
      }));
      if (res.data.metadata) {
        const entityCount = Object.keys(res.data.metadata.entity_map || {}).length;
        toast.success(`Schema discovery complete. ${entityCount} entities mapped.`);
      } else {
        toast.error("Schema discovery completed without metadata.");
      }
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Schema discovery failed."));
    } finally {
      setDiscoveringConnectionId(null);
    }
  };

  const handleMappingDecision = async (
    connectionId: string,
    mappingId: string,
    action: "approve" | "reject"
  ) => {
    try {
      const res = await api.post<{ mapping: CustomerMapping }>(
        `/connections/customer-mappings/${mappingId}/${action}`
      );
      setCustomerMappings((prev) => ({
        ...prev,
        [connectionId]: res.data.mapping,
      }));
      toast.success(action === "approve" ? "Customer mapping approved." : "Customer mapping rejected.");
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, `Failed to ${action} mapping.`));
    }
  };

  const handleSaveFieldAssignments = async (connectionId: string, mappingId: string) => {
    const fieldAssignments = mappingFieldAssignments[mappingId] || {};
    if (Object.keys(fieldAssignments).length === 0) return;
    setSavingFieldMappingId(mappingId);
    try {
      const res = await api.put<{ mapping: CustomerMapping }>(
        `/connections/customer-mappings/${mappingId}/fields`,
        { field_assignments: fieldAssignments }
      );
      setCustomerMappings((prev) => ({
        ...prev,
        [connectionId]: res.data.mapping,
      }));
      setMappingFieldAssignments((prev) => {
        const next = { ...prev };
        delete next[mappingId];
        return next;
      });
      toast.success("Customer risk field assignments saved.");
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Failed to save customer field assignments."));
    } finally {
      setSavingFieldMappingId(null);
    }
  };

  return (
    <>
      <div className="p-6 pb-12 max-w-4xl mx-auto space-y-8 animate-in fade-in duration-500">
        <div>
          <h2 className="font-display-lg text-2xl font-bold text-[#e5e2e3]">
            Workspace Settings
          </h2>
          <p className="text-xs text-[#d7c3ae]/70 mt-1">
            Manage your agent persona, customer schema, and external communication tools.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6">
          <section className="bg-[#111113] border border-[#27272A] rounded-xl p-6">
            <h3 className="font-headline-md text-sm font-bold text-[#e5e2e3] mb-2 flex items-center gap-2">
              <Database className="h-4 w-4 text-[#E8A020]" />
              Tenant Supabase Data
            </h3>
            <p className="text-xs text-[#d7c3ae]/50 mb-6">
              Connect a dedicated read-only Supabase Postgres role. Credentials are encrypted and only safe metadata is shown here.
            </p>

            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="block font-label-caps text-label-caps text-[#d7c3ae] uppercase">
                    Connection Name
                  </label>
                  <input
                    value={connectionName}
                    onChange={(e) => setConnectionName(e.target.value)}
                    className="w-full bg-[#09090B] border border-[#27272A] rounded p-3 text-sm focus:outline-none focus:border-[#E8A020]"
                    placeholder="Primary Supabase"
                  />
                </div>
                <div className="space-y-2">
                  <label className="block font-label-caps text-label-caps text-[#d7c3ae] uppercase">
                    Default Schema
                  </label>
                  <input
                    value={defaultSchema}
                    onChange={(e) => setDefaultSchema(e.target.value)}
                    className="w-full bg-[#09090B] border border-[#27272A] rounded p-3 text-sm focus:outline-none focus:border-[#E8A020]"
                    placeholder="public"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="block font-label-caps text-label-caps text-[#d7c3ae] uppercase">
                  Project URL
                </label>
                <input
                  value={projectUrl}
                  onChange={(e) => setProjectUrl(e.target.value)}
                  className="w-full bg-[#09090B] border border-[#27272A] rounded p-3 text-sm focus:outline-none focus:border-[#E8A020]"
                  placeholder="https://your-project.supabase.co"
                />
              </div>

              <div className="space-y-2">
                <label className="block font-label-caps text-label-caps text-[#d7c3ae] uppercase">
                  Read-Only Postgres URI
                </label>
                <input
                  value={readonlyUri}
                  onChange={(e) => setReadonlyUri(e.target.value)}
                  className="w-full bg-[#09090B] border border-[#27272A] rounded p-3 text-sm focus:outline-none focus:border-[#E8A020]"
                  placeholder="postgresql://readonly_user:password@host:5432/postgres"
                  type="password"
                />
              </div>

              {health && (
                <div className={`border rounded-lg p-4 ${
                  health.ok
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-red-500/30 bg-red-500/5"
                }`}>
                  <div className="flex items-center gap-2">
                    <ShieldCheck className={`h-4 w-4 ${health.ok ? "text-emerald-400" : "text-red-400"}`} />
                    <p className="text-sm font-semibold text-[#e5e2e3]">{health.message}</p>
                  </div>
                  <div className="mt-2 text-xs text-[#d7c3ae]/70 font-data-mono">
                    {health.database && <span>DB: {health.database} </span>}
                    {health.current_user && <span>User: {health.current_user} </span>}
                    <span>Tables: {health.table_count}</span>
                  </div>
                  {health.warnings.length > 0 && (
                    <div className="mt-3 space-y-1">
                      {health.warnings.map((warning) => (
                        <p key={warning} className="text-xs text-[#E8A020]">{warning}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="flex flex-wrap gap-3">
                <button
                  onClick={handleTestSupabase}
                  disabled={testingConnection || savingConnection}
                  className="px-4 py-2 border border-[#27272A] text-[#e5e2e3] rounded font-bold hover:bg-[#353436]/50 active:scale-[0.98] transition-all text-xs cursor-pointer disabled:opacity-50 flex items-center gap-2"
                  type="button"
                >
                  {testingConnection && <Loader2 className="h-4 w-4 animate-spin" />}
                  Test connection
                </button>
                <button
                  onClick={handleSaveSupabase}
                  disabled={testingConnection || savingConnection}
                  className="px-4 py-2 bg-[#E8A020] text-[#291800] rounded font-bold hover:brightness-110 active:scale-[0.98] transition-all text-xs cursor-pointer disabled:opacity-50 flex items-center gap-2"
                  type="button"
                >
                  {savingConnection && <Loader2 className="h-4 w-4 animate-spin" />}
                  Save encrypted connection
                </button>
              </div>

              <div className="pt-4 border-t border-[#27272A]/50">
                <div className="flex items-center justify-between mb-3">
                  <p className="font-label-caps text-label-caps text-[#d7c3ae]/70 uppercase">
                    Saved Connections
                  </p>
                  <button
                    onClick={fetchConnections}
                    className="h-8 w-8 border border-[#27272A] rounded hover:bg-[#353436]/50 transition-colors flex items-center justify-center"
                    type="button"
                    aria-label="Refresh Supabase connections"
                  >
                    <RefreshCw className="h-4 w-4" />
                  </button>
                </div>

                {connectionsLoading ? (
                  <p className="text-xs text-[#d7c3ae]/50">Loading connections...</p>
                ) : connections.length === 0 ? (
                  <p className="text-xs text-[#d7c3ae]/50">
                    No tenant Supabase connection saved yet.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {connections.map((connection) => (
                      <div
                        key={connection.connection_id}
                        className="bg-[#0e0e0f] border border-[#27272A] p-4 rounded-lg space-y-4"
                      >
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="font-bold text-[#e5e2e3]">{connection.display_name}</h4>
                              <span className={`px-2 py-0.5 rounded text-[9px] font-data-mono uppercase font-bold border ${
                                connection.status === "connected"
                                  ? "bg-green-500/10 text-green-400 border-green-500/20"
                                  : connection.status === "failed"
                                  ? "bg-red-500/10 text-red-400 border-red-500/20"
                                  : "bg-[#2a2a2b] text-[#d7c3ae]/60 border-[#27272A]"
                              }`}>
                                {connection.status}
                              </span>
                            </div>
                            <p className="text-xs text-[#d7c3ae]/60 mt-1">
                              Schema: {connection.default_schema}
                              {connection.last_health_check_at
                                ? ` | Last check: ${new Date(connection.last_health_check_at).toLocaleString()}`
                                : ""}
                            </p>
                            {connection.last_error && (
                              <p className="text-xs text-red-400/80 mt-1">{connection.last_error}</p>
                            )}
                          </div>
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleDiscoverSchema(connection.connection_id)}
                              className="px-3 h-9 bg-[#E8A020] text-[#291800] rounded hover:brightness-110 transition-colors flex items-center justify-center text-xs font-bold gap-2"
                              type="button"
                              disabled={discoveringConnectionId === connection.connection_id}
                            >
                              {discoveringConnectionId === connection.connection_id && (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              )}
                              Discover schema
                            </button>
                            <button
                              onClick={() => handleDiscoverCustomers(connection.connection_id)}
                              className="px-3 h-9 border border-[#27272A] rounded hover:bg-[#353436]/50 transition-colors flex items-center justify-center text-xs font-bold gap-2"
                              type="button"
                            >
                              {discoveringConnectionId === connection.connection_id && (
                                <Loader2 className="h-4 w-4 animate-spin" />
                              )}
                              Discover customers
                            </button>
                            <button
                              onClick={() => handleHealthCheck(connection.connection_id)}
                              className="h-9 w-9 border border-[#27272A] rounded hover:bg-[#353436]/50 transition-colors flex items-center justify-center"
                              type="button"
                              aria-label={`Health check ${connection.display_name}`}
                            >
                              <RefreshCw className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => handleDeleteConnection(connection.connection_id)}
                              className="h-9 w-9 border border-[#27272A] rounded hover:bg-red-500/10 hover:text-red-400 transition-colors flex items-center justify-center"
                              type="button"
                              aria-label={`Delete ${connection.display_name}`}
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </div>

                        {schemaMetadata[connection.connection_id] && (
                          <div className="border border-[#27272A] rounded bg-[#09090B] p-4 space-y-3">
                            {(() => {
                              const metadata = schemaMetadata[connection.connection_id]!;
                              const entities = Object.entries(metadata.entity_map || {});
                              return (
                                <>
                                  <div className="flex items-start justify-between gap-4">
                                    <div>
                                      <p className="text-sm font-bold text-[#e5e2e3]">
                                        Multi-table schema cache
                                      </p>
                                      <p className="text-xs text-[#d7c3ae]/60 mt-1">
                                        Confidence: {metadata.confidence == null ? "--" : `${Math.round(metadata.confidence * 100)}%`}
                                        {metadata.discovered_at ? ` | ${new Date(metadata.discovered_at).toLocaleString()}` : ""}
                                      </p>
                                    </div>
                                    <span className="px-2 py-0.5 rounded text-[9px] font-data-mono uppercase font-bold border bg-[#3ac2ff]/10 text-[#3ac2ff] border-[#3ac2ff]/20">
                                      analytics ready
                                    </span>
                                  </div>

                                  {metadata.errors.length > 0 && (
                                    <div className="space-y-1">
                                      {metadata.errors.map((error) => (
                                        <p key={error} className="text-xs text-[#E8A020]">{error}</p>
                                      ))}
                                    </div>
                                  )}

                                  {entities.length > 0 && (
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                      {entities.map(([entity, table]) => (
                                        <div key={entity} className="border border-[#27272A] rounded p-3">
                                          <p className="text-[10px] text-[#d7c3ae]/50 uppercase font-data-mono">{entity}</p>
                                          <p className="text-xs font-bold text-[#E8A020]">{table}</p>
                                        </div>
                                      ))}
                                    </div>
                                  )}

                                  <details>
                                    <summary className="text-xs text-[#d7c3ae]/60 cursor-pointer hover:text-[#E8A020]">
                                      View table and join catalog
                                    </summary>
                                    <pre className="mt-2 max-h-56 overflow-auto bg-[#0e0e0f] border border-[#27272A] rounded p-3 text-[10px] text-[#d7c3ae]">
                                      {JSON.stringify(
                                        {
                                          tables: metadata.table_catalog,
                                          joins: metadata.join_paths,
                                        },
                                        null,
                                        2
                                      )}
                                    </pre>
                                  </details>
                                </>
                              );
                            })()}
                          </div>
                        )}

                        {customerMappings[connection.connection_id] && (
                          <div className="border border-[#27272A] rounded bg-[#09090B] p-4">
                            {(() => {
                              const mapping = customerMappings[connection.connection_id]!;
                              const customerColumns = (schemaMetadata[connection.connection_id]?.column_catalog || [])
                                .filter(
                                  (column) =>
                                    column.schema === mapping.schema_name &&
                                    column.table_name === mapping.table_name
                                );
                              const pendingAssignments = mappingFieldAssignments[mapping.mapping_id] || {};
                              return (
                                <div className="space-y-4">
                                  <div className="flex items-start justify-between gap-4">
                                    <div>
                                      <div className="flex items-center gap-2">
                                        <p className="text-sm font-bold text-[#e5e2e3]">
                                          {mapping.schema_name}.{mapping.table_name}
                                        </p>
                                        <span className={`px-2 py-0.5 rounded text-[9px] font-data-mono uppercase font-bold border ${
                                          mapping.status === "approved"
                                            ? "bg-green-500/10 text-green-400 border-green-500/20"
                                            : mapping.status === "rejected"
                                            ? "bg-red-500/10 text-red-400 border-red-500/20"
                                            : "bg-[#E8A020]/10 text-[#E8A020] border-[#E8A020]/20"
                                        }`}>
                                          {mapping.status}
                                        </span>
                                      </div>
                                      <p className="text-xs text-[#d7c3ae]/60 mt-1">
                                        Confidence: {Math.round(mapping.confidence * 100)}% | {mapping.reasoning}
                                      </p>
                                      {mapping.missing_fields.length > 0 && (
                                        <p className="text-xs text-[#E8A020] mt-1">
                                          Missing useful fields: {mapping.missing_fields.join(", ")}
                                        </p>
                                      )}
                                    </div>
                                    {mapping.status === "draft" && (
                                      <div className="flex gap-2">
                                        <button
                                          onClick={() =>
                                            handleMappingDecision(
                                              connection.connection_id,
                                              mapping.mapping_id,
                                              "approve"
                                            )
                                          }
                                          className="px-3 py-2 bg-[#E8A020] text-[#291800] rounded font-bold text-xs"
                                          type="button"
                                        >
                                          Approve
                                        </button>
                                        <button
                                          onClick={() =>
                                            handleMappingDecision(
                                              connection.connection_id,
                                              mapping.mapping_id,
                                              "reject"
                                            )
                                          }
                                          className="px-3 py-2 border border-[#27272A] rounded font-bold text-xs hover:bg-red-500/10 hover:text-red-400"
                                          type="button"
                                        >
                                          Reject
                                        </button>
                                      </div>
                                    )}
                                  </div>

                                  {customerColumns.length > 0 ? (
                                    <div className="space-y-3">
                                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                        {customerColumns.map((column) => {
                                          const currentField = mapping.field_map[column.column];
                                          const hasPendingAssignment = Object.prototype.hasOwnProperty.call(
                                            pendingAssignments,
                                            column.column
                                          );
                                          const pendingField = pendingAssignments[column.column];
                                          const selectedField = hasPendingAssignment
                                            ? pendingField || ""
                                            : editableCustomerFields.some(
                                                (field) => field.value === currentField?.canonical_field
                                              )
                                              ? currentField.canonical_field
                                              : "";
                                          const normalizedColumn = column.column
                                            .trim()
                                            .toLowerCase()
                                            .replace(/[- ]/g, "_");
                                          return (
                                            <div key={column.column} className="border border-[#27272A] rounded p-3">
                                              <div className="flex items-center justify-between gap-2">
                                                <p className="text-xs font-bold text-[#e5e2e3]">{column.column}</p>
                                                <span className={`text-[9px] uppercase font-bold ${
                                                  currentField
                                                    ? "text-[#E8A020]"
                                                    : "text-[#d7c3ae]/50"
                                                }`}>
                                                  {currentField
                                                    ? `Mapped: ${currentField.canonical_field}`
                                                    : "Unmapped"}
                                                </span>
                                              </div>
                                              <p className="text-[10px] text-[#d7c3ae]/50 mt-1">{column.data_type}</p>
                                              <label className="block text-[10px] text-[#d7c3ae]/60 mt-3">
                                                CRM field
                                                <select
                                                  value={selectedField}
                                                  onChange={(event) => {
                                                    const selected = event.target.value as CustomerField | "";
                                                    setMappingFieldAssignments((prev) => {
                                                      const assignments = {
                                                        ...(prev[mapping.mapping_id] || {}),
                                                      };
                                                      if (selected) {
                                                        for (const otherColumn of customerColumns) {
                                                          if (otherColumn.column === column.column) continue;
                                                          const existingField =
                                                            assignments[otherColumn.column] !== undefined
                                                              ? assignments[otherColumn.column]
                                                              : mapping.field_map[otherColumn.column]
                                                                  ?.canonical_field;
                                                          if (existingField === selected) {
                                                            assignments[otherColumn.column] = null;
                                                          }
                                                        }
                                                      }
                                                      assignments[column.column] = selected || null;
                                                      return {
                                                        ...prev,
                                                        [mapping.mapping_id]: assignments,
                                                      };
                                                    });
                                                  }}
                                                  className="mt-1 w-full h-9 rounded border border-[#27272A] bg-[#141416] px-2 text-xs text-[#e5e2e3]"
                                                >
                                                  <option value="">Unmapped</option>
                                                  {editableCustomerFields
                                                    .filter(
                                                      (field) =>
                                                        field.value !== "last_purchase" ||
                                                        (normalizedColumn !== "created_at" &&
                                                          normalizedColumn !== "updated_at")
                                                    )
                                                    .map((field) => (
                                                      <option key={field.value} value={field.value}>
                                                        {field.label}
                                                      </option>
                                                    ))}
                                                </select>
                                              </label>
                                            </div>
                                          );
                                        })}
                                      </div>
                                      <div className="flex items-center justify-between gap-3">
                                        <p className="text-[10px] text-[#d7c3ae]/50">
                                          Risk fields must reflect real source data. Created/updated timestamps are not last-purchase dates.
                                        </p>
                                        {Object.keys(pendingAssignments).length > 0 && (
                                          <button
                                            onClick={() =>
                                              handleSaveFieldAssignments(connection.connection_id, mapping.mapping_id)
                                            }
                                            disabled={savingFieldMappingId === mapping.mapping_id}
                                            className="shrink-0 px-3 py-2 bg-[#E8A020] text-[#291800] rounded font-bold text-xs disabled:opacity-50"
                                            type="button"
                                          >
                                            {savingFieldMappingId === mapping.mapping_id ? "Saving..." : "Save field assignments"}
                                          </button>
                                        )}
                                      </div>
                                    </div>
                                  ) : (
                                    <p className="text-xs text-[#d7c3ae]/60">
                                      Column details are not cached yet. Run “Discover schema” to load all columns for this table.
                                    </p>
                                  )}

                                  {mapping.safe_preview.length > 0 && (
                                    <details>
                                      <summary className="text-xs text-[#d7c3ae]/60 cursor-pointer hover:text-[#E8A020]">
                                        View masked preview
                                      </summary>
                                      <pre className="mt-2 max-h-48 overflow-auto bg-[#0e0e0f] border border-[#27272A] rounded p-3 text-[10px] text-[#d7c3ae]">
                                        {JSON.stringify(mapping.safe_preview, null, 2)}
                                      </pre>
                                    </details>
                                  )}
                                </div>
                              );
                            })()}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>

          <section className="bg-[#111113] border border-[#27272A] rounded-xl p-6">
            <div className="flex items-start justify-between gap-6">
              <div>
                <h3 className="font-headline-md text-sm font-bold text-[#e5e2e3] mb-2 flex items-center gap-2">
                  <Bot className="h-4 w-4 text-[#E8A020]" />
                  Agent Persona
                </h3>
                <p className="text-xs text-[#d7c3ae]/60 max-w-xl">
                  {agentName} is configured as the active growth partner for {orgName}.
                </p>
                {backstory && (
                  <p className="text-xs text-[#d7c3ae]/70 mt-3 line-clamp-2">{backstory}</p>
                )}
              </div>
              <button
                onClick={() => setShowPersonaEditor(true)}
                className="shrink-0 bg-[#E8A020] text-[#291800] px-5 py-2.5 rounded font-bold hover:brightness-110 active:scale-[0.98] transition-all text-xs cursor-pointer flex items-center gap-2"
                type="button"
              >
                <Edit3 className="h-4 w-4" />
                Edit agent persona
              </button>
            </div>

            <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-[#0e0e0f] border border-[#27272A] rounded p-4">
                <p className="font-label-caps text-label-caps text-[#d7c3ae]/70 uppercase">
                  Agent Name
                </p>
                <p className="text-sm font-bold text-[#e5e2e3] mt-1">{agentName}</p>
              </div>
              <div className="bg-[#0e0e0f] border border-[#27272A] rounded p-4">
                <p className="font-label-caps text-label-caps text-[#d7c3ae]/70 uppercase">
                  Tone Guidelines
                </p>
                <p className="text-sm text-[#e5e2e3] mt-1">
                  {toneInstructions || "Not configured"}
                </p>
              </div>
            </div>
          </section>

          <section className="bg-[#111113] border border-[#27272A] rounded-xl p-6">
            <h3 className="font-headline-md text-sm font-bold text-[#e5e2e3] mb-2 flex items-center gap-2">
              <Link2 className="h-4 w-4 text-[#E8A020]" />
              Tools & Integrations
            </h3>
            <p className="text-xs text-[#d7c3ae]/50 mb-6">
              Authorized accounts are securely encrypted at rest.
            </p>

            <div className="space-y-4">
              <div className="bg-[#0e0e0f] border border-[#27272A] p-4 flex items-center justify-between hover:bg-[#353436]/10 transition-colors rounded-lg gap-4">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded bg-[#1c1b1c] border border-[#27272A] flex items-center justify-center font-bold text-[#E8A020]">
                    G
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="font-bold text-[#e5e2e3]">Google Gmail Integration</h4>
                      {integrations.gmail ? (
                        <span className="bg-green-500/10 text-green-400 px-2 py-0.5 rounded text-[9px] font-data-mono uppercase font-bold border border-green-500/20">
                          Connected
                        </span>
                      ) : (
                        <span className="bg-[#2a2a2b] text-[#d7c3ae]/50 px-2 py-0.5 rounded text-[9px] font-data-mono uppercase font-bold border border-[#27272A]">
                          Disconnected
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[#d7c3ae]/70 mt-1">
                      Allows {agentName} to compose and dispatch campaign sequences via Gmail.
                    </p>
                  </div>
                </div>
                {integrations.gmail ? (
                  <button
                    disabled
                    className="px-4 py-2 border border-[#27272A] text-green-400/40 rounded text-xs font-semibold"
                    type="button"
                  >
                    Linked
                  </button>
                ) : (
                  <button
                    onClick={handleConnectGmail}
                    className="px-4 py-2 bg-[#E8A020] text-[#291800] rounded font-bold hover:brightness-110 active:scale-[0.98] transition-all text-xs cursor-pointer"
                    type="button"
                  >
                    Connect
                  </button>
                )}
              </div>

              <div className="bg-[#0e0e0f] border border-[#27272A] p-4 flex items-center justify-between hover:bg-[#353436]/10 transition-colors rounded-lg gap-4">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded bg-[#1c1b1c] border border-[#27272A] flex items-center justify-center font-bold text-[#E8A020]">
                    S
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="font-bold text-[#e5e2e3]">Slack Workspace Bot</h4>
                      {integrations.slack ? (
                        <span className="bg-green-500/10 text-green-400 px-2 py-0.5 rounded text-[9px] font-data-mono uppercase font-bold border border-green-500/20">
                          Connected
                        </span>
                      ) : (
                        <span className="bg-[#2a2a2b] text-[#d7c3ae]/50 px-2 py-0.5 rounded text-[9px] font-data-mono uppercase font-bold border border-[#27272A]">
                          Disconnected
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[#d7c3ae]/70 mt-1">
                      Allows {agentName} to push campaign alerts and summaries into Slack.
                    </p>
                  </div>
                </div>
                {integrations.slack ? (
                  <button
                    disabled
                    className="px-4 py-2 border border-[#27272A] text-green-400/40 rounded text-xs font-semibold"
                    type="button"
                  >
                    Linked
                  </button>
                ) : (
                  <button
                    onClick={handleConnectSlack}
                    className="px-4 py-2 bg-[#E8A020] text-[#291800] rounded font-bold hover:brightness-110 active:scale-[0.98] transition-all text-xs cursor-pointer"
                    type="button"
                  >
                    Connect
                  </button>
                )}
              </div>
            </div>
          </section>

          {/* Security Audit Logs Section */}
          <section className="bg-[#111113] border border-[#27272A] rounded-xl p-6 space-y-4">
            <div>
              <h3 className="font-headline-md text-sm font-bold text-[#e5e2e3] mb-1 flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-red-400" />
                Security Audit Log
              </h3>
              <p className="text-xs text-[#d7c3ae]/50">
                A tamper-evident ledger of all database schema alterations, campaign sends, and credential connections.
              </p>
            </div>

            {loadingAudit ? (
              <div className="flex items-center gap-2 text-xs font-data-mono text-[#d7c3ae]/40">
                <Loader2 className="h-4 w-4 animate-spin text-[#E8A020]" />
                <span>Loading security logs...</span>
              </div>
            ) : auditLogs.length === 0 ? (
              <p className="text-xs text-[#d7c3ae]/40 italic p-3 text-center border border-dashed border-[#27272A] rounded">
                No security actions recorded yet.
              </p>
            ) : (
              <div className="border border-[#27272A] rounded-lg overflow-hidden max-h-60 overflow-y-auto custom-scrollbar bg-[#0E0E10]">
                <table className="w-full text-left border-collapse text-[11px]">
                  <thead className="bg-[#141416] border-b border-[#27272A]/85 text-[#d7c3ae]/40 font-data-mono uppercase">
                    <tr>
                      <th className="p-2.5">Time</th>
                      <th className="p-2.5">Actor</th>
                      <th className="p-2.5">Action</th>
                      <th className="p-2.5">Details</th>
                    </tr>
                  </thead>
                  <tbody className="font-data-mono text-[#e5e2e3] divide-y divide-[#27272A]/40">
                    {auditLogs.map((log) => (
                      <tr key={log.log_id} className="hover:bg-[#18181A]/40">
                        <td className="p-2.5 text-[#d7c3ae]/55 shrink-0 whitespace-nowrap">
                          {new Date(log.created_at).toLocaleString()}
                        </td>
                        <td className="p-2.5 shrink-0">
                          <span className={`px-1.5 py-0.5 rounded font-bold text-[9px] uppercase ${
                            log.actor === "agent" ? "bg-[#3ac2ff]/10 text-[#3ac2ff]" : "bg-[#E8A020]/10 text-[#E8A020]"
                          }`}>
                            {log.actor}
                          </span>
                        </td>
                        <td className="p-2.5 font-bold shrink-0">{log.action}</td>
                        <td className="p-2.5 text-[#d7c3ae]/75 font-body-base leading-relaxed break-all">
                          {JSON.stringify(log.details)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {schemaDef && (
            <section className="bg-[#111113] border border-[#27272A] rounded-xl p-6">
              <h3 className="font-headline-md text-sm font-bold text-[#e5e2e3] mb-4 flex items-center gap-2">
                <Database className="h-4 w-4 text-[#E8A020]" />
                CRM Database Schema
              </h3>

              <div className="bg-[#0e0e0f] border border-[#27272A] rounded overflow-hidden">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-[#201f20]">
                    <tr className="border-b border-[#27272A]">
                      <th className="p-3 font-label-caps text-[#d7c3ae] uppercase">
                        Spreadsheet Header
                      </th>
                      <th className="p-3 font-label-caps text-[#d7c3ae] uppercase">
                        Mapped Semantic Type
                      </th>
                      <th className="p-3 font-label-caps text-[#d7c3ae] uppercase">
                        AI Column Purpose
                      </th>
                    </tr>
                  </thead>
                  <tbody className="font-data-mono text-[11px] text-[#e5e2e3] divide-y divide-[#27272A]/50">
                    {Object.entries(schemaDef).map(([col, field]) => (
                      <tr key={col}>
                        <td className="p-3 font-bold">{col}</td>
                        <td className="p-3">
                          <span className="px-2 py-0.5 bg-[#E8A020]/15 text-[#E8A020] rounded border border-[#E8A020]/30 font-bold uppercase text-[10px]">
                            {field.canonical_type}
                          </span>
                        </td>
                        <td className="p-3 text-[#d7c3ae]/70">{field.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </div>
      </div>

      {showPersonaEditor && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-start justify-center overflow-y-auto p-6">
          <div className="w-full min-h-full flex items-center justify-center py-8">
            <OnboardingFlow
              initialOrgName={orgName}
              initialAgentName={agentName}
              initialBackstory={backstory}
              initialTone={toneInstructions || "Professional, helpful, and data-driven."}
              initialSchemaDef={schemaDef}
              onCancel={() => setShowPersonaEditor(false)}
              onComplete={handlePersonaComplete}
              completeLabel="Save setup"
            />
          </div>
        </div>
      )}
    </>
  );
}
