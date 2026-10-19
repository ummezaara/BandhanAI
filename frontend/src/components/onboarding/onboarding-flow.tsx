"use client";

import React, { useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth-store";
import { useTenantStore } from "@/store/tenant-store";
import {
  ArrowLeft,
  Bot,
  Building2,
  CheckCircle2,
  ChevronRight,
  FileUp,
  SlidersHorizontal,
  Sparkles,
  ScrollText,
  X,
  Trash2,
  Loader2,
  AlertCircle,
  FileText,
  Database,
  ShieldCheck,
  Check,
} from "lucide-react";
import toast from "react-hot-toast";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type FileUploadStatus =
  | "pending"
  | "uploading"
  | "mapping"
  | "review"
  | "confirming"
  | "done"
  | "error";

interface UploadedFile {
  id: string;
  file: File;
  status: FileUploadStatus;
  progress: number;
  error?: string;
  uploadSessionId?: string;
  sourceType?: string;
  joinKey?: string | null;
  totalRows?: number;
  mappedColumns?: Record<string, string>;
  droppedColumns?: string[];
  reasoning?: string;
  customersInserted?: number;
  customersUpdated?: number;
  totalCustomers?: number;
}

interface DiscoveredMapping {
  mapping_id: string;
  connection_id: string;
  schema_name: string;
  table_name: string;
  confidence: number;
  reasoning: string;
  field_map: Record<string, {
    source_column: string;
    canonical_field: string;
    confidence: number;
    reason?: string;
  }>;
  safe_preview?: unknown[];
}

interface DiscoveredSchemaMetadata {
  entity_map: Record<string, string>;
  table_catalog: Array<Record<string, unknown>>;
  join_paths: Array<Record<string, unknown>>;
  confidence?: number | null;
  errors: string[];
}

const getErrorMessage = (error: unknown, fallback: string) => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    return typeof detail === "string" ? detail : fallback;
  }
  return error instanceof Error ? error.message : fallback;
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface OnboardingFlowProps {
  initialOrgName?: string;
  initialAgentName?: string;
  initialBackstory?: string;
  initialTone?: string;
  initialSchemaDef?: Record<string, any> | null;
  onComplete?: () => void;
  onCancel?: () => void;
  completeLabel?: string;
}

export default function OnboardingFlow({
  initialOrgName = "BandhanAI",
  initialAgentName = "Ralph",
  initialBackstory = "",
  initialTone = "Professional, helpful, and data-driven.",
  initialSchemaDef = null,
  onComplete,
  onCancel,
  completeLabel = "Complete Onboarding",
}: OnboardingFlowProps) {
  const router = useRouter();
  const setOrgId = useAuthStore((state) => state.setOrgId);
  const setSettings = useTenantStore((state) => state.setSettings);

  const [step, setStep] = useState(1);
  const [dataMode, setDataMode] = useState<"csv" | "supabase" | null>(null);

  // Step 1: Agent Persona
  const [orgName, setOrgName] = useState(initialOrgName);
  const [agentName, setAgentName] = useState(initialAgentName);
  const [backstory, setBackstory] = useState(initialBackstory);
  const [tone, setTone] = useState(initialTone);
  const [saving, setSaving] = useState(false);

  // Step 3 (CSV Mode): Multi-File CSV Upload
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Step 3 (Supabase Mode): Connection Details & Agentic Mapping
  const [supabaseDisplayName, setSupabaseDisplayName] = useState("Production Database");
  const [supabaseReadOnlyUri, setSupabaseReadOnlyUri] = useState("");
  const [supabaseProjectUrl, setSupabaseProjectUrl] = useState("");
  const [supabaseDefaultSchema, setSupabaseDefaultSchema] = useState("public");
  
  const [testingConnection, setTestingConnection] = useState(false);
  const [savingConnection, setSavingConnection] = useState(false);
  const [discoveringSchema, setDiscoveringSchema] = useState(false);
  const [discoveredMapping, setDiscoveredMapping] = useState<DiscoveredMapping | null>(null);
  const [discoveredMetadata, setDiscoveredMetadata] = useState<DiscoveredSchemaMetadata | null>(null);
  const [approvingMapping, setApprovingMapping] = useState(false);

  // Check if any file completed successfully
  const hasSuccessfulUpload = uploadedFiles.some((f) => f.status === "done");
  const isAnyProcessing = uploadedFiles.some((f) =>
    ["uploading", "mapping", "confirming"].includes(f.status)
  );

  // ------- Step 1: Agent Persona -------
  const handleStep1Submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orgName.trim() || !agentName.trim()) {
      toast.error("Organization name and agent name are required.");
      return;
    }

    setSaving(true);
    try {
      toast.loading("Configuring your agent workspace...", { id: "onboarding-step1" });
      const res = await api.post("/auth/register-tenant", {
        org_name: orgName,
        agent_name: agentName,
        backstory,
        tone_instructions: tone,
      });

      toast.success("Agent persona saved.", { id: "onboarding-step1" });
      setOrgId(res.data.org_id);
      setSettings({
        orgName,
        agentName,
        backstory,
        toneInstructions: tone,
      });
      setStep(2);
    } catch (e: unknown) {
      toast.error(getErrorMessage(e, "Setup failed. Please try again."), {
        id: "onboarding-step1",
      });
    } finally {
      setSaving(false);
    }
  };

  // ------- Step 2: Choose Data Mode -------
  const handleSelectMode = (mode: "csv" | "supabase") => {
    setDataMode(mode);
    setStep(3);
  };

  // ------- Step 3 (CSV): Ingestion Helpers -------
  const updateFile = useCallback(
    (id: string, updates: Partial<UploadedFile>) => {
      setUploadedFiles((prev) =>
        prev.map((f) => (f.id === id ? { ...f, ...updates } : f))
      );
    },
    []
  );

  const processFile = useCallback(
    async (uploadEntry: UploadedFile) => {
      const { id, file } = uploadEntry;
      updateFile(id, { status: "uploading", progress: 20 });

      try {
        const formData = new FormData();
        formData.append("file", file);

        updateFile(id, { status: "mapping", progress: 50 });

        const uploadRes = await api.post("/csv/upload", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        });

        const {
          upload_session_id,
          source_type,
          join_key,
          total_rows,
          mapped_columns,
          dropped_columns,
          reasoning,
        } = uploadRes.data;

        updateFile(id, {
          status: "review",
          progress: 0,
          uploadSessionId: upload_session_id,
          sourceType: source_type,
          joinKey: join_key,
          totalRows: total_rows,
          mappedColumns: mapped_columns,
          droppedColumns: dropped_columns,
          reasoning: reasoning,
        });

        toast.success(`${file.name} is ready for mapping review.`);
      } catch (err: unknown) {
        const msg = getErrorMessage(err, `Failed to process ${file.name}`);
        updateFile(id, { status: "error", progress: 0, error: msg });
        toast.error(msg);
      }
    },
    [updateFile]
  );

  const confirmFileImport = useCallback(
    async (entry: UploadedFile) => {
      if (!entry.uploadSessionId) {
        toast.error("Upload session is missing. Please re-upload the CSV.");
        return;
      }

      updateFile(entry.id, { status: "confirming", progress: 75 });

      try {
        const confirmRes = await api.post("/csv/confirm", {
          upload_session_id: entry.uploadSessionId,
        });

        updateFile(entry.id, {
          status: "done",
          progress: 100,
          customersInserted: confirmRes.data.customers_inserted,
          customersUpdated: confirmRes.data.customers_updated,
          totalCustomers: confirmRes.data.total_customers,
        });

        toast.success(`${entry.file.name} imported successfully.`);
      } catch (err: unknown) {
        const msg = getErrorMessage(err, `Failed to import ${entry.file.name}`);
        updateFile(entry.id, { status: "error", progress: 0, error: msg });
        toast.error(msg);
      }
    },
    [updateFile]
  );

  const addFiles = useCallback(
    (files: FileList | File[]) => {
      const newEntries: UploadedFile[] = [];

      for (const file of Array.from(files)) {
        if (!file.name.toLowerCase().endsWith(".csv")) {
          toast.error(`${file.name} is not a CSV file. Skipped.`);
          continue;
        }

        const alreadyAdded = uploadedFiles.some(
          (f) => f.file.name === file.name && f.status !== "error"
        );
        if (alreadyAdded) {
          toast.error(`${file.name} is already added.`);
          continue;
        }

        const entry: UploadedFile = {
          id: crypto.randomUUID(),
          file,
          status: "pending",
          progress: 0,
        };

        newEntries.push(entry);
      }

      if (newEntries.length === 0) return;

      setUploadedFiles((prev) => [...prev, ...newEntries]);

      for (const entry of newEntries) {
        processFile(entry);
      }
    },
    [uploadedFiles, processFile]
  );

  const removeFile = useCallback((id: string) => {
    setUploadedFiles((prev) => prev.filter((f) => f.id !== id));
  }, []);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(e.type === "dragenter" || e.type === "dragover");
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    if (e.dataTransfer.files?.length) {
      addFiles(e.dataTransfer.files);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) {
      addFiles(e.target.files);
      e.target.value = "";
    }
  };

  const handleCompleteSetup = () => {
    toast.success("Agent setup complete.");
    if (onComplete) {
      onComplete();
      return;
    }
    router.push("/dashboard");
  };

  // ------- Step 3 (Supabase): Connect Helpers -------
  const handleTestSupabaseConnection = async () => {
    if (!supabaseReadOnlyUri.trim()) {
      toast.error("Please enter your postgres read-only connection URI");
      return;
    }
    setTestingConnection(true);
    try {
      const res = await api.post("/connections/supabase/test", {
        readonly_uri: supabaseReadOnlyUri,
        default_schema: supabaseDefaultSchema,
      });
      if (res.data.ok) {
        toast.success(`Success! Connected to database. Found ${res.data.table_count} tables.`);
      } else {
        toast.error(`Connection failed: ${res.data.message || "Unknown error"}`);
      }
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to connect to database"));
    } finally {
      setTestingConnection(false);
    }
  };

  const handleConnectSupabase = async () => {
    if (!supabaseReadOnlyUri.trim()) {
      toast.error("Connection URI is required.");
      return;
    }

    setSavingConnection(true);
    try {
      toast.loading("Encrypting credentials and saving connection...", { id: "supabase-connect" });
      const res = await api.post("/connections/supabase", {
        display_name: supabaseDisplayName,
        readonly_uri: supabaseReadOnlyUri,
        project_url: supabaseProjectUrl || null,
        default_schema: supabaseDefaultSchema,
        allowed_schemas: ["public"],
        allowed_tables: [],
      });
      const connectionId = res.data.connection.connection_id;
      toast.success("Connection saved securely.", { id: "supabase-connect" });

      // Trigger full schema discovery for the analytics agent, then legacy customer mapping.
      setDiscoveringSchema(true);
      toast.loading("Analyzing tables and running schema discovery agent...", { id: "supabase-discover" });
      const schemaRes = await api.post<{ metadata: DiscoveredSchemaMetadata | null }>(
        `/connections/${connectionId}/discover/schema`
      );
      if (schemaRes.data.metadata) {
        setDiscoveredMetadata(schemaRes.data.metadata);
      }

      const discoverRes = await api.post(`/connections/${connectionId}/discover/customers`);
      const mapping = discoverRes.data.mapping;
      
      if (mapping) {
        setDiscoveredMapping(mapping);
        toast.success("Schema discovery completed. Customer table resolved.", { id: "supabase-discover" });
      } else if (schemaRes.data.metadata) {
        toast.success("Schema discovery completed. Analytics chat is ready.", { id: "supabase-discover" });
      } else {
        toast.error("Schema discovery failed. No usable tables identified.", { id: "supabase-discover" });
      }
    } catch (err) {
      toast.error(getErrorMessage(err, "Supabase connection setup failed"), { id: "supabase-connect" });
    } finally {
      setSavingConnection(false);
      setDiscoveringSchema(false);
    }
  };

  const handleApproveMapping = async () => {
    if (!discoveredMapping) return;
    setApprovingMapping(true);
    try {
      toast.loading("Registering schema configuration...", { id: "approve-mapping" });
      await api.post(`/connections/customer-mappings/${discoveredMapping.mapping_id}/approve`);
      toast.success("Customer schema map approved successfully!", { id: "approve-mapping" });
      handleCompleteSetup();
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to approve schema mapping"), { id: "approve-mapping" });
    } finally {
      setApprovingMapping(false);
    }
  };

  const handleFinishWithSchemaMetadata = () => {
    toast.success("Schema metadata saved. Analytics chat is ready.");
    handleCompleteSetup();
  };

  // ------- Status helpers -------
  const statusLabel = (status: FileUploadStatus): string => {
    switch (status) {
      case "pending": return "Queued";
      case "uploading": return "Uploading...";
      case "mapping": return "AI mapping columns...";
      case "review": return "Review mapping";
      case "confirming": return "Importing data...";
      case "done": return "Imported";
      case "error": return "Failed";
    }
  };

  const statusColor = (status: FileUploadStatus): string => {
    switch (status) {
      case "done": return "text-emerald-400";
      case "error": return "text-red-400";
      case "review": return "text-[#3ac2ff]";
      default: return "text-[#E8A020]";
    }
  };

  return (
    <div className="w-full max-w-[800px] z-10 space-y-6">
      <div>
        <div className="flex items-center justify-between mb-4 gap-4">
          <div className="flex flex-col">
            <span className="font-label-caps text-label-caps text-[#E8A020] mb-1 uppercase tracking-widest">
              {step === 1 ? "Step 1: Configuration" : step === 2 ? "Step 2: Onboarding Mode" : "Step 3: Data Integration"}
            </span>
            <h1 className="font-display-lg text-2xl font-bold">
              {step === 1 ? "Agent Persona" : step === 2 ? "Choose Onboarding Mode" : dataMode === "csv" ? "Import Customers File" : "Connect Live Database"}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-data-mono text-data-mono text-[#d7c3ae]/70">
              STEP 0{step} / 03
            </span>
            {onCancel && (
              <button
                onClick={onCancel}
                className="text-[#d7c3ae]/70 hover:text-[#e5e2e3] transition-colors"
                type="button"
                aria-label="Close onboarding setup"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>
        </div>
        <div className="h-1 w-full bg-[#353436] rounded-full overflow-hidden">
          <div
            className="h-full bg-[#E8A020] transition-all duration-500 ease-in-out"
            style={{ width: step === 1 ? "33%" : step === 2 ? "66%" : "100%" }}
          />
        </div>
      </div>

      <div className="bg-[#111113]/85 backdrop-blur-md border border-[#27272A] rounded-xl p-8 flex flex-col min-h-[500px]">
        
        {/* Step 1: Agent Settings */}
        {step === 1 && (
          <form onSubmit={handleStep1Submit} className="flex-1 flex flex-col gap-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="block font-label-caps text-label-caps text-[#d7c3ae] uppercase">
                  Organization Name
                </label>
                <div className="relative">
                  <Building2 className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#E8A020]" />
                  <input
                    type="text"
                    required
                    placeholder="e.g. Mumbai Spices"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    className="w-full bg-[#09090B] border border-[#27272A] rounded p-3 pl-10 text-sm focus:outline-none focus:border-[#E8A020] focus:ring-1 focus:ring-[#E8A020] transition-all"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <label className="block font-label-caps text-label-caps text-[#d7c3ae] uppercase">
                  Agent Persona Name
                </label>
                <div className="relative">
                  <Bot className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#E8A020]" />
                  <input
                    type="text"
                    required
                    placeholder="e.g. Rohan"
                    value={agentName}
                    onChange={(e) => setAgentName(e.target.value)}
                    className="w-full bg-[#09090B] border border-[#27272A] rounded p-3 pl-10 text-sm focus:outline-none focus:border-[#E8A020] focus:ring-1 focus:ring-[#E8A020] transition-all"
                  />
                </div>
              </div>
            </div>

            <div className="space-y-2 flex-grow flex flex-col">
              <label className="flex items-center gap-2 font-label-caps text-label-caps text-[#d7c3ae] uppercase">
                <ScrollText className="h-3.5 w-3.5 text-[#E8A020]" />
                Backstory & Domain Context
              </label>
              <div className="relative flex-grow flex">
                <Sparkles className="absolute left-4 top-4 h-4 w-4 text-[#E8A020]" />
                <textarea
                  required
                  placeholder="Describe the agent's personality, domain expertise, and backstory context."
                  value={backstory}
                  onChange={(e) => setBackstory(e.target.value)}
                  className="w-full flex-grow bg-[#09090B] border border-[#27272A] rounded p-4 pl-11 text-sm focus:outline-none focus:border-[#E8A020] focus:ring-1 focus:ring-[#E8A020] transition-all resize-none min-h-[160px]"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="flex items-center gap-2 font-label-caps text-label-caps text-[#d7c3ae] uppercase">
                <SlidersHorizontal className="h-3.5 w-3.5 text-[#E8A020]" />
                Agent Tone Guidelines
              </label>
              <div className="relative">
                <SlidersHorizontal className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#E8A020]" />
                <input
                  type="text"
                  required
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  className="w-full bg-[#09090B] border border-[#27272A] rounded p-3 pl-10 text-sm focus:outline-none focus:border-[#E8A020] focus:ring-1 focus:ring-[#E8A020] transition-all"
                />
              </div>
            </div>

            <div className="flex justify-end pt-4 border-t border-[#27272A]/50">
              <button
                type="submit"
                disabled={saving}
                className="bg-[#E8A020] text-[#291800] px-8 py-3 rounded font-bold hover:brightness-110 active:scale-[0.98] transition-all flex items-center gap-2 cursor-pointer disabled:opacity-60"
              >
                <span>{saving ? "Saving..." : "Save & Continue"}</span>
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </form>
        )}

        {/* Step 2: Choose Data Mode */}
        {step === 2 && (
          <div className="flex-1 flex flex-col justify-center gap-6">
            <h3 className="text-sm font-semibold text-[#d7c3ae] uppercase tracking-wider text-center">
              Select how you want to load your customer CRM data
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-2xl mx-auto w-full">
              {/* Dynamic Database Mode */}
              <div
                onClick={() => handleSelectMode("supabase")}
                className="group border border-[#27272A] rounded-xl p-6 bg-[#0E0E10] hover:border-[#E8A020] hover:bg-[#E8A020]/5 transition-all duration-300 cursor-pointer flex flex-col text-left justify-between h-56 relative overflow-hidden"
              >
                <div className="absolute right-2 top-2 bg-[#E8A020]/15 text-[#E8A020] text-[8px] font-data-mono tracking-widest px-2 py-0.5 rounded border border-[#E8A020]/25">
                  RECOMMENDED
                </div>
                <div className="space-y-3">
                  <div className="h-10 w-10 bg-[#E8A020]/10 border border-[#E8A020]/20 rounded flex items-center justify-center text-[#E8A020]">
                    <Database className="h-5 w-5" />
                  </div>
                  <h4 className="font-bold text-sm text-[#e5e2e3]">Connect Supabase DB</h4>
                  <p className="text-xs text-[#d7c3ae]/60 leading-relaxed">
                    Connect your live Supabase project directly. Our AI agent dynamically discovers tables, indexes customer attributes, and auto-syncs schemas.
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-[#d7c3ae]/50 group-hover:translate-x-1 transition-transform self-end" />
              </div>

              {/* Static CSV Mode */}
              <div
                onClick={() => handleSelectMode("csv")}
                className="group border border-[#27272A] rounded-xl p-6 bg-[#0E0E10] hover:border-[#E8A020] hover:bg-[#E8A020]/5 transition-all duration-300 cursor-pointer flex flex-col text-left justify-between h-56"
              >
                <div className="space-y-3">
                  <div className="h-10 w-10 bg-[#3ac2ff]/10 border border-[#3ac2ff]/20 rounded flex items-center justify-center text-[#3ac2ff]">
                    <FileText className="h-5 w-5" />
                  </div>
                  <h4 className="font-bold text-sm text-[#e5e2e3]">Upload Customer CSVs</h4>
                  <p className="text-xs text-[#d7c3ae]/60 leading-relaxed">
                    Import static customer logs from standard spreadsheets. You will review and manually configure the columns matching.
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-[#d7c3ae]/50 group-hover:translate-x-1 transition-transform self-end" />
              </div>
            </div>

            <div className="flex justify-start pt-6 border-t border-[#27272A]/50">
              <button
                onClick={() => setStep(1)}
                className="text-[#d7c3ae] hover:text-[#e5e2e3] font-bold text-xs uppercase flex items-center gap-2 cursor-pointer"
                type="button"
              >
                <ArrowLeft className="h-4 w-4" />
                Back
              </button>
            </div>
          </div>
        )}

        {/* Step 3: CSV File Ingestion Panel */}
        {step === 3 && dataMode === "csv" && (
          <div className="flex-1 flex flex-col gap-5">
            <div
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-xl p-6 flex flex-col items-center justify-center bg-[#0e0e0f] cursor-pointer transition-all duration-300 group ${
                uploadedFiles.length > 0 ? "min-h-[140px]" : "min-h-[200px]"
              } ${
                isDragActive
                  ? "border-[#E8A020] bg-[#E8A020]/10"
                  : "border-[#27272A] hover:border-[#E8A020] hover:bg-[#E8A020]/5"
              } ${isAnyProcessing ? "pointer-events-none opacity-70" : ""}`}
            >
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept=".csv"
                multiple
                onChange={handleFileSelect}
              />
              <div className="mb-2 flex h-10 w-10 items-center justify-center rounded bg-[#2a2a2b] border border-[#27272A] text-[#E8A020] transition-colors group-hover:border-[#E8A020]/50 group-hover:bg-[#E8A020]/10">
                <FileUp className="h-5 w-5" />
              </div>
              <p className="font-headline-md text-sm text-[#d7c3ae] group-hover:text-[#e5e2e3]">
                {uploadedFiles.length > 0 ? "Add more CSV files" : "Upload CSV files"}
              </p>
              <p className="text-xs text-[#d7c3ae]/50 mt-1">
                Drag & drop or click to select — multiple files supported
              </p>
            </div>

            {uploadedFiles.length > 0 && (
              <div className="space-y-3 max-h-[320px] overflow-y-auto pr-1 custom-scrollbar">
                {uploadedFiles.map((entry) => (
                  <div
                    key={entry.id}
                    className={`bg-[#0e0e0f] border rounded-lg p-4 transition-all duration-300 ${
                      entry.status === "done"
                        ? "border-emerald-500/30"
                        : entry.status === "error"
                        ? "border-red-500/30"
                        : "border-[#27272A]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <div
                          className={`flex-shrink-0 h-9 w-9 rounded flex items-center justify-center ${
                            entry.status === "done"
                              ? "bg-emerald-500/10 text-emerald-400"
                              : entry.status === "error"
                              ? "bg-red-500/10 text-red-400"
                              : "bg-[#2a2a2b] text-[#E8A020]"
                          }`}
                        >
                          {entry.status === "done" ? (
                            <CheckCircle2 className="h-4 w-4" />
                          ) : entry.status === "error" ? (
                            <AlertCircle className="h-4 w-4" />
                          ) : entry.status === "pending" || entry.status === "review" ? (
                            <FileText className="h-4 w-4" />
                          ) : (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-[#e5e2e3] truncate">
                            {entry.file.name}
                          </p>
                          <p className={`text-xs font-mono ${statusColor(entry.status)}`}>
                            {statusLabel(entry.status)}
                            {entry.totalRows != null && entry.status !== "error" && (
                              <span className="text-[#d7c3ae]/50 ml-2">
                                {entry.totalRows.toLocaleString()} rows
                              </span>
                            )}
                          </p>
                        </div>
                      </div>

                      {(entry.status === "review" || entry.status === "done" || entry.status === "error") && (
                        <button
                          onClick={() => removeFile(entry.id)}
                          className="text-[#d7c3ae]/40 hover:text-red-400 transition-colors flex-shrink-0 cursor-pointer"
                          type="button"
                          aria-label={`Remove ${entry.file.name}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      )}
                    </div>

                    {entry.status !== "done" && entry.status !== "error" && entry.progress > 0 && (
                      <div className="mt-3">
                        <div className="h-1 w-full bg-[#353436] rounded-full overflow-hidden">
                          <div
                            className="bg-[#E8A020] h-full transition-all duration-500 ease-out"
                            style={{ width: `${entry.progress}%` }}
                          />
                        </div>
                      </div>
                    )}

                    {entry.status === "error" && entry.error && (
                      <p className="mt-2 text-xs text-red-400/80 font-mono">{entry.error}</p>
                    )}

                    {entry.status === "done" && (
                      <div className="mt-3 flex items-center gap-4 text-xs font-mono text-[#d7c3ae]/70">
                        {entry.customersInserted != null && (
                          <span>
                            <span className="text-emerald-400 font-bold">
                              {entry.customersInserted}
                            </span>{" "}
                            inserted
                          </span>
                        )}
                        {(entry.customersUpdated ?? 0) > 0 && (
                          <span>
                            <span className="text-[#E8A020] font-bold">
                              {entry.customersUpdated}
                            </span>{" "}
                            updated
                          </span>
                        )}
                        {entry.totalCustomers != null && (
                          <span className="ml-auto text-[#d7c3ae]/50">
                            Total: {entry.totalCustomers.toLocaleString()}
                          </span>
                        )}
                      </div>
                    )}

                    {(entry.status === "review" || entry.status === "done") && entry.mappedColumns && (
                      <details className="mt-3 group/detail" open={entry.status === "review"}>
                        <summary className="text-xs text-[#d7c3ae]/50 cursor-pointer hover:text-[#E8A020] transition-colors select-none">
                          {entry.status === "review" ? "Review" : "View"} column mapping ({Object.keys(entry.mappedColumns).length} fields)
                        </summary>
                        <div className="mt-2 bg-[#111113] border border-[#27272A] rounded overflow-hidden">
                          <table className="w-full text-left border-collapse">
                            <thead>
                              <tr className="bg-[#201f20] border-b border-[#27272A]">
                                <th className="p-2 font-label-caps text-[10px] text-[#d7c3ae] uppercase">
                                  Source Column
                                </th>
                                <th className="p-2 font-label-caps text-[10px] text-[#d7c3ae] uppercase">
                                  Mapped To
                                </th>
                              </tr>
                            </thead>
                            <tbody className="font-data-mono text-xs text-[#e5e2e3]">
                              {Object.entries(entry.mappedColumns).map(([orig, semantic]) => (
                                <tr
                                  key={orig}
                                  className="border-b border-[#27272A]/30 hover:bg-[#353436]/20"
                                >
                                  <td className="p-2 text-[#d7c3ae]">{orig}</td>
                                  <td className="p-2">
                                    <span className="px-1.5 py-0.5 bg-[#2a2a2b] border border-[#27272A] rounded text-[#E8A020] text-[10px] font-bold">
                                      {semantic}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {entry.reasoning && (
                          <p className="mt-2 text-xs text-[#d7c3ae]/60">{entry.reasoning}</p>
                        )}
                        {entry.droppedColumns && entry.droppedColumns.length > 0 && (
                          <p className="mt-2 text-xs text-[#d7c3ae]/50">
                            Dropped: {entry.droppedColumns.join(", ")}
                          </p>
                        )}
                        {entry.status === "review" && (
                          <div className="mt-3 flex justify-end">
                            <button
                              onClick={() => confirmFileImport(entry)}
                              className="bg-[#E8A020] text-[#291800] px-4 py-2 rounded font-bold hover:brightness-110 active:scale-[0.98] transition-all text-xs cursor-pointer flex items-center gap-2"
                              type="button"
                            >
                              Confirm import
                              <CheckCircle2 className="h-4 w-4" />
                            </button>
                          </div>
                        )}
                      </details>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="mt-auto pt-5 border-t border-[#27272A]/50 flex justify-between items-center">
              <button
                onClick={() => setStep(2)}
                className="text-[#d7c3ae] hover:text-[#e5e2e3] font-bold text-xs uppercase flex items-center gap-2 cursor-pointer"
                type="button"
              >
                <ArrowLeft className="h-4 w-4" />
                Back
              </button>

              <button
                onClick={handleCompleteSetup}
                disabled={!hasSuccessfulUpload || isAnyProcessing}
                className="bg-[#E8A020] text-[#291800] px-8 py-3 rounded font-bold hover:brightness-110 active:scale-[0.98] transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                type="button"
              >
                <span>{isAnyProcessing ? "Processing..." : completeLabel}</span>
                {isAnyProcessing ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Supabase Connect Database Panel */}
        {step === 3 && dataMode === "supabase" && (
          <div className="flex-1 flex flex-col gap-5 text-left">
            {!discoveredMapping && !discoveredMetadata ? (
              // Connection details form
              <div className="space-y-4 flex-grow flex flex-col">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="block font-label-caps text-label-caps text-[#d7c3ae] uppercase text-[10px]">
                      Database Label
                    </label>
                    <input
                      type="text"
                      value={supabaseDisplayName}
                      onChange={(e) => setSupabaseDisplayName(e.target.value)}
                      placeholder="e.g. Production Database"
                      className="w-full bg-[#09090B] border border-[#27272A] rounded p-2.5 text-xs text-[#e5e2e3] focus:outline-none focus:border-[#E8A020] focus:ring-1 focus:ring-[#E8A020]"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="block font-label-caps text-label-caps text-[#d7c3ae] uppercase text-[10px]">
                      Default Schema
                    </label>
                    <input
                      type="text"
                      value={supabaseDefaultSchema}
                      onChange={(e) => setSupabaseDefaultSchema(e.target.value)}
                      placeholder="public"
                      className="w-full bg-[#09090B] border border-[#27272A] rounded p-2.5 text-xs text-[#e5e2e3] focus:outline-none focus:border-[#E8A020] focus:ring-1 focus:ring-[#E8A020]"
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <label className="block font-label-caps text-label-caps text-[#d7c3ae] uppercase text-[10px]">
                    Supabase Read-Only URI (Connection String)
                  </label>
                  <input
                    type="text"
                    value={supabaseReadOnlyUri}
                    onChange={(e) => setSupabaseReadOnlyUri(e.target.value)}
                    placeholder="postgresql://bandhan_readonly:password@db-host:6543/postgres"
                    className="w-full bg-[#09090B] border border-[#27272A] rounded p-2.5 font-data-mono text-xs text-[#6A9E6A] focus:outline-none focus:border-[#E8A020] focus:ring-1 focus:ring-[#E8A020]"
                  />
                  <p className="text-[10px] text-[#d7c3ae]/40 leading-relaxed">
                    Always use a read-only role connection string for security. Do not provide superuser credentials.
                  </p>
                </div>

                {/* SQL snippet box */}
                <div className="p-4 bg-[#111113] border border-[#27272A] rounded-lg space-y-2">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-[#E8A020]" />
                    <span className="text-[11px] font-bold text-[#e5e2e3] uppercase font-data-mono">
                      Recommended: Restricted Read-Only SQL Setup
                    </span>
                  </div>
                  <p className="text-[11px] text-[#d7c3ae]/75 leading-relaxed">
                    Run this script in your Supabase **SQL Editor** to create a secure, restricted role for BandhanAI:
                  </p>
                  <pre className="p-3 bg-[#09090B] border border-[#27272A]/70 rounded font-data-mono text-[10px] text-[#E8A020]/90 overflow-x-auto select-all max-h-[110px] custom-scrollbar">
                    {`CREATE ROLE bandhan_readonly WITH LOGIN PASSWORD 'your_secure_password';\nGRANT USAGE ON SCHEMA public TO bandhan_readonly;\nGRANT SELECT ON ALL TABLES IN SCHEMA public TO bandhan_readonly;\nALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO bandhan_readonly;`}
                  </pre>
                </div>

                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    disabled={testingConnection || savingConnection || discoveringSchema}
                    onClick={handleTestSupabaseConnection}
                    className="px-4 py-2 border border-[#27272A] hover:bg-[#1c1b1c] text-[#d7c3ae] text-xs font-semibold rounded transition-colors disabled:opacity-50"
                  >
                    {testingConnection ? "Testing..." : "Test Connection"}
                  </button>
                  <button
                    type="button"
                    disabled={testingConnection || savingConnection || discoveringSchema}
                    onClick={handleConnectSupabase}
                    className="bg-[#E8A020] text-[#291800] px-5 py-2 text-xs font-bold rounded hover:brightness-110 active:scale-[0.98] transition-all flex items-center gap-1 disabled:opacity-50"
                  >
                    {savingConnection || discoveringSchema ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Discovering Schema...</span>
                      </>
                    ) : (
                      <>
                        <Database className="h-3.5 w-3.5" />
                        <span>Validate & Discover Schema</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            ) : (
              // Discovery review panel
              <div className="space-y-4 flex-grow flex flex-col">
                <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg flex items-start gap-3">
                  <Check className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <h4 className="text-xs font-bold text-emerald-400 uppercase tracking-wider font-data-mono">
                      Database Analysis Successful
                    </h4>
                    <p className="text-xs text-[#d7c3ae]/75 leading-relaxed">
                      {discoveredMapping ? (
                        <>
                          Customer mapping completed for table: <strong className="text-[#e5e2e3] font-data-mono font-bold">{discoveredMapping.schema_name}.{discoveredMapping.table_name}</strong> (Confidence: <strong className="text-[#E8A020] font-bold">{(discoveredMapping.confidence * 100).toFixed(0)}%</strong>)
                        </>
                      ) : (
                        <>
                          Multi-table schema metadata is saved. Analytics chat can now answer questions across discovered tables.
                        </>
                      )}
                    </p>
                  </div>
                </div>

                {discoveredMapping ? (
                  <div className="bg-[#0e0e0f] border border-[#27272A] rounded-lg overflow-hidden flex-grow flex flex-col max-h-[300px]">
                    <div className="bg-[#1c1b1c] p-2.5 border-b border-[#27272A]">
                      <span className="font-label-caps text-label-caps text-[#d7c3ae] uppercase text-[10px] tracking-widest font-bold">
                        Discovered Customer Column Mapping
                      </span>
                    </div>
                    <div className="overflow-y-auto flex-1 custom-scrollbar">
                      <table className="w-full text-left border-collapse">
                        <thead>
                          <tr className="bg-[#141416] border-b border-[#27272A]/50 font-data-mono text-[10px] text-[#d7c3ae]/50">
                            <th className="p-2.5">Source Database Column</th>
                            <th className="p-2.5">Mapped CRM Canonical Field</th>
                            <th className="p-2.5">Confidence</th>
                          </tr>
                        </thead>
                        <tbody className="font-data-mono text-xs text-[#e5e2e3]">
                          {Object.entries(discoveredMapping.field_map).map(([col, details]) => (
                            <tr key={col} className="border-b border-[#27272A]/30 hover:bg-[#18181A]/50">
                              <td className="p-2.5 font-bold">{col}</td>
                              <td className="p-2.5">
                                <span className="px-2 py-0.5 bg-[#E8A020]/10 border border-[#E8A020]/20 rounded text-[#E8A020] text-[10px] font-bold">
                                  {details.canonical_field}
                                </span>
                              </td>
                              <td className="p-2.5 text-[#d7c3ae]/60">{(details.confidence * 100).toFixed(0)}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : discoveredMetadata ? (
                  <div className="bg-[#0e0e0f] border border-[#27272A] rounded-lg overflow-hidden flex-grow flex flex-col max-h-[300px]">
                    <div className="bg-[#1c1b1c] p-2.5 border-b border-[#27272A]">
                      <span className="font-label-caps text-label-caps text-[#d7c3ae] uppercase text-[10px] tracking-widest font-bold">
                        Discovered Business Entities
                      </span>
                    </div>
                    <div className="overflow-y-auto flex-1 custom-scrollbar p-3 grid grid-cols-1 md:grid-cols-2 gap-2">
                      {Object.entries(discoveredMetadata.entity_map || {}).map(([entity, table]) => (
                        <div key={entity} className="border border-[#27272A] rounded p-3">
                          <p className="text-[10px] text-[#d7c3ae]/50 uppercase font-data-mono">{entity}</p>
                          <p className="text-xs font-bold text-[#E8A020]">{table}</p>
                        </div>
                      ))}
                      {Object.keys(discoveredMetadata.entity_map || {}).length === 0 && (
                        <p className="text-xs text-[#d7c3ae]/60">
                          Tables were discovered, but no CRM entities were classified confidently yet.
                        </p>
                      )}
                    </div>
                  </div>
                ) : null}

                {discoveredMapping?.reasoning && (
                  <p className="text-xs text-[#d7c3ae]/60 italic font-body-base leading-relaxed bg-[#141416] p-3 border border-[#27272A] rounded">
                    &quot;{discoveredMapping.reasoning}&quot;
                  </p>
                )}

                <div className="flex justify-between items-center pt-4 border-t border-[#27272A]/50">
                  <button
                    type="button"
                    onClick={() => {
                      setDiscoveredMapping(null);
                      setDiscoveredMetadata(null);
                    }}
                    className="text-xs text-[#ffb4ab] hover:underline flex items-center gap-1 cursor-pointer font-semibold"
                  >
                    Reset and Re-connect
                  </button>
                  
                  <button
                    type="button"
                    disabled={approvingMapping}
                    onClick={discoveredMapping ? handleApproveMapping : handleFinishWithSchemaMetadata}
                    className="bg-[#E8A020] text-[#291800] px-6 py-2.5 text-xs font-bold rounded hover:brightness-110 active:scale-[0.98] transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                  >
                    {approvingMapping ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4" />
                    )}
                    <span>{discoveredMapping ? "Approve Schema Map & Finish" : "Finish Setup"}</span>
                  </button>
                </div>
              </div>
            )}

            {!discoveredMapping && !discoveredMetadata && (
              <div className="mt-auto pt-5 border-t border-[#27272A]/50 flex justify-between items-center">
                <button
                  onClick={() => setStep(2)}
                  className="text-[#d7c3ae] hover:text-[#e5e2e3] font-bold text-xs uppercase flex items-center gap-2 cursor-pointer"
                  type="button"
                >
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </button>
              </div>
            )}
          </div>
        )}

      </div>

      <div className="flex items-center gap-4 p-4 border-l-2 border-[#E8A020] bg-[#0e0e0f]/50 rounded-r">
        <Sparkles className="h-5 w-5 shrink-0 text-[#E8A020]" />
        <p className="font-body-sm text-xs text-[#d7c3ae] italic">
          &quot;I will calibrate your dynamic CRM schemas and construct your agent persona using these
          inputs.&quot; <span className="text-[#E8A020] font-bold">{agentName}AI</span>
        </p>
      </div>
    </div>
  );
}
