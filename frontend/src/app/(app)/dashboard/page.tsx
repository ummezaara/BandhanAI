"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useTenantStore } from "@/store/tenant-store";
import toast from "react-hot-toast";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Filter,
  Mail,
  RefreshCw,
  Rocket,
  Settings,
  Sparkles,
  Users,
  Zap,
  TrendingUp,
  Award,
  CircleDot,
  Smile,
  ShieldCheck,
  Lightbulb,
} from "lucide-react";
import type { CampaignRecipient } from "@/types/campaign";

interface Campaign {
  id: string;
  name: string;
  type: string;
  status: string;
  created_at: string;
  emails_sent?: number;
}

interface RiskSnapshot {
  snapshot_id: string;
  customer_label?: string | null;
  risk_level: "low" | "medium" | "high" | "unknown";
  risk_score?: number | null;
  reasons: string[];
  computed_at?: string | null;
}

interface DashboardMetrics {
  total_customers: number;
  total_spend: number;
  average_spend: number;
  at_risk_count: number;
  segments: {
    champions: number;
    loyalists: number;
    at_risk: number;
    lost: number;
    new: number;
  };
  recent_campaigns: Campaign[];
}

interface AdvisorMetric {
  value: number | null;
  available: boolean;
  reason: string | null;
}

interface BusinessAdvisorInsights {
  source: string;
  metrics: Record<string, AdvisorMetric>;
  risk_classifications: {
    available: boolean;
    scope: string;
    counts: Record<string, number> | null;
    reason: string | null;
  };
  summary: string;
  recommendations: { recommendation: string; evidence: string }[];
  unavailable_metrics: Record<string, string>;
}

const advisorMetricLabels: Record<string, string> = {
  customer_count: "Customers",
  total_recorded_spend: "Recorded customer spend",
  recorded_loyalty_purchase_spend: "Recorded loyalty purchase spend",
  average_customer_spend: "Average recorded spend per customer",
  at_risk_customer_count: "At-risk customers",
};

export default function DashboardPage() {
  const { agentName, integrations, fetchTenantSettings } = useTenantStore();
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [riskSnapshots, setRiskSnapshots] = useState<RiskSnapshot[]>([]);
  const [loadingMetrics, setLoadingMetrics] = useState(true);
  const [loadingRisk, setLoadingRisk] = useState(true);
  const [advisorInsights, setAdvisorInsights] = useState<BusinessAdvisorInsights | null>(null);
  const [loadingAdvisorInsights, setLoadingAdvisorInsights] = useState(true);
  const [advisorInsightsError, setAdvisorInsightsError] = useState<string | null>(null);
  const [refreshingRisk, setRefreshingRisk] = useState(false);
  const [riskRefreshError, setRiskRefreshError] = useState<string | null>(null);
  const [expandedCampaignId, setExpandedCampaignId] = useState<string | null>(null);
  const [campaignRecipients, setCampaignRecipients] = useState<Record<string, CampaignRecipient[]>>({});
  const [loadingRecipients, setLoadingRecipients] = useState<string | null>(null);
  const displayName = useMemo(() => (agentName || "Agent").trim(), [agentName]);
  const initials = useMemo(
    () => displayName.split(" ").map((part) => part[0]).join("").slice(0, 2).toUpperCase() || "AI",
    [displayName]
  );

  const fetchDashboardMetrics = useCallback(async () => {
    try {
      setLoadingMetrics(true);
      const res = await api.get("/crm/dashboard/metrics");
      setMetrics(res.data);
    } catch (e) {
      console.error("Failed to load dashboard metrics:", e);
    } finally {
      setLoadingMetrics(false);
    }
  }, []);

  const fetchRiskSnapshots = useCallback(async () => {
    try {
      const res = await api.get<{ snapshots: RiskSnapshot[]; total: number }>(
        "/crm/risk/customers"
      );
      setRiskSnapshots(res.data.snapshots);
    } catch (e) {
      console.error("Failed to load risk snapshots:", e);
    } finally {
      setLoadingRisk(false);
    }
  }, []);

  const fetchAdvisorInsights = useCallback(async () => {
    try {
      setLoadingAdvisorInsights(true);
      setAdvisorInsightsError(null);
      const res = await api.get<BusinessAdvisorInsights>("/crm/business-advisor/insights");
      setAdvisorInsights(res.data);
    } catch (error) {
      console.error("Failed to load Business Advisor insights:", error);
      setAdvisorInsightsError("Business Advisor insights could not be loaded.");
    } finally {
      setLoadingAdvisorInsights(false);
    }
  }, []);

  useEffect(() => {
    fetchTenantSettings();
    queueMicrotask(() => {
      void fetchDashboardMetrics();
      void fetchRiskSnapshots();
      void fetchAdvisorInsights();
    });
  }, [fetchTenantSettings, fetchDashboardMetrics, fetchRiskSnapshots, fetchAdvisorInsights]);

  const handleSyncNow = async () => {
    setRefreshingRisk(true);
    setRiskRefreshError(null);
    try {
      const res = await api.post("/crm/risk/refresh", { limit: 500 });
      await fetchRiskSnapshots();
      await fetchDashboardMetrics();
      await fetchAdvisorInsights();
      toast.success(`Dashboard refreshed! Scored risk for ${res.data.total_scored} customers.`);
    } catch (e: unknown) {
      console.error("Risk refresh failed:", e);
      let message = "Risk refresh failed. Please try again.";
      if (typeof e === "object" && e !== null && "response" in e) {
        const response = e.response;
        if (typeof response === "object" && response !== null && "data" in response) {
          const data = response.data;
          if (typeof data === "object" && data !== null && "detail" in data) {
            if (typeof data.detail === "string") message = data.detail;
          }
        }
      }
      setRiskRefreshError(message);
      toast.error(message);
    } finally {
      setRefreshingRisk(false);
    }
  };

  const toggleCampaignRecipients = async (campaignId: string) => {
    if (expandedCampaignId === campaignId) {
      setExpandedCampaignId(null);
      return;
    }

    setExpandedCampaignId(campaignId);
    if (campaignRecipients[campaignId]) return;

    setLoadingRecipients(campaignId);
    try {
      const res = await api.get<{ recipients: CampaignRecipient[]; total: number }>(
        `/campaigns/${campaignId}/recipients`
      );
      setCampaignRecipients((prev) => ({
        ...prev,
        [campaignId]: res.data.recipients,
      }));
    } catch (e) {
      console.error("Failed to load campaign recipients:", e);
      toast.error("Failed to load campaign recipient previews.");
    } finally {
      setLoadingRecipients(null);
    }
  };

  const highRiskCount = riskSnapshots.filter((item) => item.risk_level === "high").length;
  const scoredRisk = riskSnapshots.filter((item) => item.risk_score != null);
  const avgRisk =
    scoredRisk.length > 0
      ? Math.round(
          (scoredRisk.reduce((sum, item) => sum + (item.risk_score ?? 0), 0) /
            scoredRisk.length) *
            100
        )
      : null;

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 text-left">
      
      {/* Agent Persona Hero Card */}
      <section className="bg-[#111113] border border-[#27272A] rounded-xl p-6 relative overflow-hidden group">
        <div className="absolute top-0 left-0 w-1 h-full bg-[#E8A020]" />
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-center gap-6">
            <div className="w-20 h-20 rounded-2xl bg-[#18181B] border border-[#27272A] flex items-center justify-center text-3xl font-bold text-[#E8A020] transition-transform duration-500 group-hover:scale-105 shadow-[0_0_15px_rgba(232,160,32,0.15)]">
              {initials}
            </div>
            <div>
              <h2 className="font-display-lg text-xl font-semibold text-[#e5e2e3]">
                {displayName} Active Workspace
              </h2>
              <div className="flex items-center gap-4 mt-2">
                <div className="flex items-center gap-1.5 px-2 py-0.5 bg-green-500/10 rounded border border-green-500/20">
                  <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                  <span className="font-data-mono text-[10px] text-green-400 uppercase font-bold tracking-tight">
                    Online
                  </span>
                </div>
                <div className="flex items-center gap-2 text-xs text-[#d7c3ae]/70">
                  <span className="font-data-mono">
                    Gmail {integrations.gmail ? <span className="text-[#E8A020]">✓</span> : <span className="opacity-50">✗</span>}
                  </span>
                  <span className="text-[#27272A]">|</span>
                  <span className="font-data-mono">
                    Slack {integrations.slack ? <span className="text-[#E8A020]">✓</span> : <span className="opacity-50">✗</span>}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={handleSyncNow}
              disabled={refreshingRisk}
              className="bg-[#E8A020] text-[#291800] h-10 w-10 rounded-lg font-bold hover:brightness-110 active:scale-[0.98] transition-all flex items-center justify-center text-sm cursor-pointer disabled:opacity-50"
              title="Recalculate Churn Risk & Sync"
            >
              {refreshingRisk ? <RefreshCw className="h-5 w-5 animate-spin" /> : <Zap className="h-5 w-5" />}
            </button>
            <Link
              href="/settings"
              className="border border-[#27272A] text-[#e5e2e3] h-10 w-10 rounded-lg font-medium hover:bg-[#353436]/50 transition-all text-sm flex items-center justify-center"
              title="Edit Persona"
            >
              <Settings className="h-5 w-5" />
            </Link>
          </div>
        </div>
      </section>

      {/* Proactive Churn Risk Banner */}
      {metrics && metrics.at_risk_count > 0 && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 animate-in slide-in-from-top-2 duration-300">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-red-500/20 flex items-center justify-center text-red-400 shrink-0">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <h4 className="font-bold text-sm text-[#e5e2e3]">Proactive Churn Risk Alert</h4>
              <p className="text-xs text-[#d7c3ae]/70 mt-0.5">
                {metrics.at_risk_count} customers have been flagged with a high churn risk rating. Rohan suggests starting a re-engagement marketing campaign.
              </p>
            </div>
          </div>
          <Link
            href="/chat"
            className="bg-red-500/25 hover:bg-red-500/35 text-red-400 border border-red-500/30 px-4 py-2 rounded text-xs font-bold font-data-mono tracking-wide transition-all uppercase shrink-0"
          >
            Draft Campaign in Chat
          </Link>
        </div>
      )}

      {/* Stats Row */}
      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-[#111113] border border-[#27272A] rounded-xl p-5 hover:bg-[#353436]/20 transition-all">
          <div className="flex items-center justify-between mb-3">
            <span className="font-label-caps text-label-caps text-[#d7c3ae]/70 uppercase text-xs">Total Customers</span>
            <Users className="h-5 w-5 text-[#E8A020]/50" />
          </div>
          <div className="font-data-mono text-2xl font-bold text-[#e5e2e3]">
            {loadingMetrics ? "..." : metrics?.total_customers ?? "0"}
          </div>
          <div className="mt-2 flex items-center gap-1 min-h-[16px]">
            <span className="text-emerald-400 text-[10px] font-data-mono">
              {metrics?.segments?.champions ?? 0} Champions
            </span>
            <span className="text-[#d7c3ae]/40 text-[10px]">active in database</span>
          </div>
        </div>

        <div className="bg-[#111113] border border-[#27272A] rounded-xl p-5 hover:bg-[#353436]/20 transition-all">
          <div className="flex items-center justify-between mb-3">
            <span className="font-label-caps text-label-caps text-[#d7c3ae]/70 uppercase text-xs">Total Customer spend</span>
            <TrendingUp className="h-5 w-5 text-[#E8A020]/50" />
          </div>
          <div className="font-data-mono text-2xl font-bold text-[#e5e2e3]">
            {loadingMetrics ? "..." : `₹${(metrics?.total_spend ?? 0).toLocaleString()}`}
          </div>
          <div className="mt-2 flex items-center gap-1 min-h-[16px]">
            <span className="text-[#E8A020] text-[10px] font-data-mono">
              Avg: ₹{Math.round(metrics?.average_spend ?? 0).toLocaleString()}
            </span>
            <span className="text-[#d7c3ae]/40 text-[10px]">per customer LTV</span>
          </div>
        </div>

        <div className="bg-[#111113] border border-[#27272A] rounded-xl p-5 hover:bg-[#353436]/20 transition-all">
          <div className="flex items-center justify-between mb-3">
            <span className="font-label-caps text-label-caps text-[#d7c3ae]/70 uppercase text-xs">At Churn Risk</span>
            <AlertTriangle className="h-5 w-5 text-[#E8A020]/50" />
          </div>
          <div className="font-data-mono text-2xl font-bold text-[#ffb4ab]">
            {loadingMetrics ? "..." : metrics?.at_risk_count ?? "0"}
          </div>
          <div className="mt-2 flex items-center gap-1 min-h-[16px]">
            <span className="text-red-400 text-[10px] font-data-mono">
              {metrics?.segments?.lost ?? 0} Lost
            </span>
            <span className="text-[#d7c3ae]/40 text-[10px]">requiring re-engagement</span>
          </div>
        </div>

        <div className="bg-[#111113] border border-[#27272A] rounded-xl p-5 hover:bg-[#353436]/20 transition-all">
          <div className="flex items-center justify-between mb-3">
            <span className="font-label-caps text-label-caps text-[#d7c3ae]/70 uppercase text-xs">Average Churn Score</span>
            <CircleDot className="h-5 w-5 text-[#E8A020]/50" />
          </div>
          <div className="font-data-mono text-2xl font-bold text-[#E8A020]">
            {loadingRisk ? "..." : avgRisk == null ? "0%" : `${avgRisk}%`}
          </div>
          <div className="mt-2 flex items-center gap-1 min-h-[16px]">
            <span className="text-[#E8A020] text-[10px] font-data-mono">
              {scoredRisk.length} Analyzed
            </span>
            <span className="text-[#d7c3ae]/40 text-[10px]">explainable scoring</span>
          </div>
        </div>
      </section>

      {/* Main Grid: Segments + At-Risk List */}
      <section className="bg-[#111113] border border-[#27272A] rounded-xl overflow-hidden">
        <div className="p-6 border-b border-[#27272A] flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Lightbulb className="h-5 w-5 text-[#E8A020]" />
            <div>
              <h3 className="font-headline-md text-base text-[#e5e2e3]">Business Advisor</h3>
              <p className="text-xs text-[#d7c3ae]/50">Insights based on available tenant customer data</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleSyncNow}
            disabled={refreshingRisk}
            className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg bg-[#E8A020] px-3 text-xs font-bold text-[#291800] transition-all hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshingRisk ? "animate-spin" : ""}`} />
            {refreshingRisk ? "Refreshing..." : "Refresh Risk"}
          </button>
        </div>
        {riskRefreshError && (
          <p role="alert" className="px-6 pt-4 text-xs text-red-300">
            {riskRefreshError}
          </p>
        )}
        {loadingAdvisorInsights ? (
          <div className="p-8 text-center text-xs font-data-mono text-[#d7c3ae]/40">
            Loading Business Advisor insights...
          </div>
        ) : advisorInsightsError ? (
          <div className="p-6 flex items-center justify-between gap-4">
            <p role="alert" className="text-sm text-red-300">{advisorInsightsError}</p>
            <button
              type="button"
              onClick={() => void fetchAdvisorInsights()}
              className="rounded-lg border border-[#27272A] px-3 py-2 text-xs text-[#E8A020] hover:bg-[#353436]/40"
            >
              Try again
            </button>
          </div>
        ) : advisorInsights ? (
          <div className="space-y-5 p-6">
            <p className="text-sm leading-relaxed text-[#e5e2e3]">{advisorInsights.summary}</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {Object.entries(advisorInsights.metrics).map(([key, metric]) => (
                <div key={key} className="rounded-lg border border-[#27272A] bg-[#0A0A0B]/60 p-3">
                  <p className="text-[10px] uppercase tracking-wide text-[#d7c3ae]/50">
                    {advisorMetricLabels[key] || key.replaceAll("_", " ")}
                  </p>
                  {metric.available && metric.value !== null ? (
                    <p className="mt-1 text-sm font-semibold text-[#e5e2e3]">
                      {key.includes("spend")
                        ? `₹${metric.value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`
                        : metric.value}
                    </p>
                  ) : (
                    <p className="mt-1 text-xs text-[#d7c3ae]/50">
                      Unavailable{metric.reason ? `: ${metric.reason}` : metric.value === null ? ": No value was returned." : ""}
                    </p>
                  )}
                </div>
              ))}
            </div>
            {advisorInsights.risk_classifications.available && advisorInsights.risk_classifications.counts ? (
              <p className="text-xs text-[#d7c3ae]/60">
                Persisted risk classifications: {Object.entries(advisorInsights.risk_classifications.counts)
                  .map(([level, count]) => `${level}: ${count}`)
                  .join(" · ")}
              </p>
            ) : advisorInsights.risk_classifications.reason ? (
              <p className="text-xs text-[#d7c3ae]/50">
                Risk classifications unavailable: {advisorInsights.risk_classifications.reason}
              </p>
            ) : null}
            {advisorInsights.recommendations.length > 0 ? (
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#d7c3ae]/65">
                  Recommendations
                </h4>
                <ul className="space-y-3">
                  {advisorInsights.recommendations.map((item, index) => (
                    <li key={`${item.recommendation}-${index}`} className="border-l-2 border-[#E8A020]/50 pl-3">
                      <p className="text-sm text-[#e5e2e3]">{item.recommendation}</p>
                      <p className="mt-1 text-xs text-[#d7c3ae]/50">Evidence: {item.evidence}</p>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="text-xs text-[#d7c3ae]/50">No evidence-supported recommendations are available.</p>
            )}
            {Object.keys(advisorInsights.unavailable_metrics).length > 0 && (
              <div className="border-t border-[#27272A] pt-3">
                <p className="mb-2 text-[10px] uppercase tracking-wide text-[#d7c3ae]/45">
                  Other metrics unavailable
                </p>
                <ul className="space-y-1">
                  {Object.entries(advisorInsights.unavailable_metrics).map(([metric, reason]) => (
                    <li key={metric} className="text-xs text-[#d7c3ae]/50">
                      {advisorMetricLabels[metric] || metric.replaceAll("_", " ")}: {reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <p className="p-6 text-sm text-[#d7c3ae]/50">No advisor insights are available.</p>
        )}
      </section>

      {/* Main Grid: Segments + At-Risk List */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* RFM Customer Segments Splits */}
        <section className="bg-[#111113] border border-[#27272A] rounded-xl p-6 space-y-6 lg:col-span-1">
          <div>
            <h3 className="font-headline-md text-base text-[#e5e2e3]">Customer Segmentation</h3>
            <p className="text-xs text-[#d7c3ae]/50">Automatic categorizations based on spending and churn profiles</p>
          </div>

          {loadingMetrics ? (
            <div className="h-48 flex items-center justify-center text-xs font-data-mono text-[#d7c3ae]/40">
              Loading segments distribution...
            </div>
          ) : (
            <div className="space-y-4">
              {/* Champions */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-emerald-400 font-bold">
                    <Award className="h-3.5 w-3.5" />
                    Champions
                  </span>
                  <span className="font-data-mono text-[#e5e2e3]">{metrics?.segments?.champions ?? 0}</span>
                </div>
                <div className="h-2 bg-[#1c1b1c] rounded-full overflow-hidden">
                  <div
                    className="bg-emerald-400 h-full rounded-full"
                    style={{ width: `${((metrics?.segments?.champions ?? 0) / (metrics?.total_customers || 1)) * 100}%` }}
                  />
                </div>
              </div>

              {/* Loyalists */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-[#3ac2ff] font-bold">
                    <Smile className="h-3.5 w-3.5" />
                    Loyal Customers
                  </span>
                  <span className="font-data-mono text-[#e5e2e3]">{metrics?.segments?.loyalists ?? 0}</span>
                </div>
                <div className="h-2 bg-[#1c1b1c] rounded-full overflow-hidden">
                  <div
                    className="bg-[#3ac2ff] h-full rounded-full"
                    style={{ width: `${((metrics?.segments?.loyalists ?? 0) / (metrics?.total_customers || 1)) * 100}%` }}
                  />
                </div>
              </div>

              {/* New Customers */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-[#d7c3ae] font-bold">
                    <Users className="h-3.5 w-3.5" />
                    New / General
                  </span>
                  <span className="font-data-mono text-[#e5e2e3]">{metrics?.segments?.new ?? 0}</span>
                </div>
                <div className="h-2 bg-[#1c1b1c] rounded-full overflow-hidden">
                  <div
                    className="bg-[#d7c3ae] h-full rounded-full"
                    style={{ width: `${((metrics?.segments?.new ?? 0) / (metrics?.total_customers || 1)) * 100}%` }}
                  />
                </div>
              </div>

              {/* At-Risk */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-[#E8A020] font-bold">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    At Churn Risk
                  </span>
                  <span className="font-data-mono text-[#e5e2e3]">{metrics?.segments?.at_risk ?? 0}</span>
                </div>
                <div className="h-2 bg-[#1c1b1c] rounded-full overflow-hidden">
                  <div
                    className="bg-[#E8A020] h-full rounded-full"
                    style={{ width: `${((metrics?.segments?.at_risk ?? 0) / (metrics?.total_customers || 1)) * 100}%` }}
                  />
                </div>
              </div>

              {/* Lost */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-red-400 font-bold">
                    <CircleDot className="h-3.5 w-3.5" />
                    Lost Customers
                  </span>
                  <span className="font-data-mono text-[#e5e2e3]">{metrics?.segments?.lost ?? 0}</span>
                </div>
                <div className="h-2 bg-[#1c1b1c] rounded-full overflow-hidden">
                  <div
                    className="bg-red-400 h-full rounded-full"
                    style={{ width: `${((metrics?.segments?.lost ?? 0) / (metrics?.total_customers || 1)) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          )}
        </section>

        {/* At-Risk Customers List */}
        <section className="bg-[#111113] border border-[#27272A] rounded-xl overflow-hidden lg:col-span-2">
          <div className="p-6 border-b border-[#27272A] flex items-center justify-between">
            <div>
              <h3 className="font-headline-md text-base text-[#e5e2e3]">At-Risk Profiles</h3>
              <p className="text-xs text-[#d7c3ae]/50">Explainable at-risk customers resolved from database scans</p>
            </div>
            <Link
              href="/customers"
              className="text-xs text-[#E8A020] hover:underline font-semibold font-data-mono uppercase tracking-wider"
            >
              View All Customer Profiles
            </Link>
          </div>

          {loadingRisk ? (
            <div className="p-12 text-center text-xs font-data-mono text-[#d7c3ae]/40">
              Loading risk snapshots...
            </div>
          ) : riskSnapshots.length === 0 ? (
            <div className="p-12 text-center text-xs text-[#d7c3ae]/50">
              No risk snapshots available. Ensure you connect Supabase or upload customer spreadsheets.
            </div>
          ) : (
            <div className="divide-y divide-[#27272A]/40 max-h-[360px] overflow-y-auto custom-scrollbar">
              {riskSnapshots.slice(0, 10).map((snapshot) => (
                <div key={snapshot.snapshot_id} className="p-4 flex items-start justify-between gap-4 hover:bg-[#141416]/40 transition-colors">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-bold text-[#e5e2e3]">
                        {snapshot.customer_label || "Unknown customer"}
                      </p>
                      <span className={`px-2 py-0.5 rounded text-[9px] font-data-mono uppercase font-bold border ${
                        snapshot.risk_level === "high"
                          ? "bg-red-500/10 text-red-400 border-red-500/20"
                          : snapshot.risk_level === "medium"
                          ? "bg-[#E8A020]/10 text-[#E8A020] border-[#E8A020]/20"
                          : "bg-[#2a2a2b] text-[#d7c3ae]/60 border-[#27272A]"
                      }`}>
                        {snapshot.risk_level}
                      </span>
                    </div>
                    <p className="text-xs text-[#d7c3ae]/60 leading-relaxed max-w-xl">
                      {snapshot.reasons.join(" ")}
                    </p>
                  </div>
                  <div className="font-data-mono text-sm font-bold text-[#E8A020] shrink-0">
                    {snapshot.risk_score == null ? "--" : `${Math.round(snapshot.risk_score * 100)}%`}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

      </div>

      {/* Campaigns History */}
      <section className="bg-[#111113] border border-[#27272A] rounded-xl overflow-hidden">
        <div className="p-6 border-b border-[#27272A]">
          <h3 className="font-headline-md text-base text-[#e5e2e3]">Recent Outreach Campaigns</h3>
          <p className="text-xs text-[#d7c3ae]/50">Status and execution statistics of campaign communications</p>
        </div>

        {loadingMetrics ? (
          <div className="p-12 text-center text-xs font-data-mono text-[#d7c3ae]/40">
            Loading campaign statistics...
          </div>
        ) : !metrics?.recent_campaigns || metrics.recent_campaigns.length === 0 ? (
          <div className="p-12 text-center text-xs text-[#d7c3ae]/50">
            No marketing campaigns executed yet. Chat with your agent in the **Chat** panel to generate email sequences!
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-[#161618] border-b border-[#27272A]/80 font-data-mono text-[10px] text-[#d7c3ae]/50">
                  <th className="p-4">Campaign Name</th>
                  <th className="p-4">Type</th>
                  <th className="p-4">Status</th>
                  <th className="p-4">Date Created</th>
                  <th className="p-4 text-right">Recipients</th>
                </tr>
              </thead>
              <tbody className="text-xs">
                {metrics.recent_campaigns.map((camp) => (
                  <React.Fragment key={camp.id}>
                    <tr className="border-b border-[#27272A]/40 hover:bg-[#141416]/40 transition-colors">
                      <td className="p-4 font-bold text-[#e5e2e3]">{camp.name}</td>
                      <td className="p-4 font-data-mono uppercase tracking-tight text-[#3ac2ff]">{camp.type}</td>
                      <td className="p-4">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase font-data-mono ${
                          camp.status === "completed" || camp.status === "sent"
                            ? "bg-green-500/10 text-green-400 border border-green-500/20"
                            : camp.status === "draft"
                            ? "bg-[#E8A020]/10 text-[#E8A020] border border-[#E8A020]/20"
                            : "bg-[#2a2a2b] text-[#d7c3ae]/50"
                        }`}>
                          {camp.status}
                        </span>
                      </td>
                      <td className="p-4 text-[#d7c3ae]/60 font-data-mono">
                        {camp.created_at ? new Date(camp.created_at).toLocaleDateString() : "--"}
                      </td>
                      <td className="p-4 text-right">
                        <button
                          onClick={() => toggleCampaignRecipients(camp.id)}
                          className="px-3 py-1.5 border border-[#27272A] rounded text-[#e5e2e3] hover:bg-[#353436]/50 text-[10px] font-bold uppercase font-data-mono inline-flex items-center gap-2"
                          type="button"
                        >
                          {loadingRecipients === camp.id ? (
                            <RefreshCw className="h-3 w-3 animate-spin" />
                          ) : (
                            <Mail className="h-3 w-3" />
                          )}
                          Review
                        </button>
                      </td>
                    </tr>
                    {expandedCampaignId === camp.id && (
                      <tr className="border-b border-[#27272A]/60 bg-[#0d0d0e]">
                        <td colSpan={5} className="p-4">
                          {loadingRecipients === camp.id ? (
                            <p className="text-xs font-data-mono text-[#d7c3ae]/40">Loading recipient previews...</p>
                          ) : !campaignRecipients[camp.id] || campaignRecipients[camp.id].length === 0 ? (
                            <p className="text-xs text-[#d7c3ae]/50">
                              No campaign recipient previews saved yet.
                            </p>
                          ) : (
                            <div className="space-y-3">
                              {campaignRecipients[camp.id].slice(0, 5).map((recipient) => (
                                <div key={recipient.recipient_id} className="border border-[#27272A] rounded-lg p-3 bg-[#111113]">
                                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                                    <div>
                                      <p className="text-sm font-bold text-[#e5e2e3]">
                                        {recipient.customer_name || recipient.customer_email}
                                      </p>
                                      <p className="text-xs text-[#d7c3ae]/60">{recipient.customer_email}</p>
                                    </div>
                                    <span className={`px-2 py-0.5 rounded text-[9px] font-data-mono uppercase font-bold border w-fit ${
                                      recipient.status === "sent"
                                        ? "bg-green-500/10 text-green-400 border-green-500/20"
                                        : recipient.status === "failed"
                                        ? "bg-red-500/10 text-red-400 border-red-500/20"
                                        : "bg-[#E8A020]/10 text-[#E8A020] border-[#E8A020]/20"
                                    }`}>
                                      {recipient.status}
                                    </span>
                                  </div>
                                  {recipient.subject && (
                                    <p className="mt-2 text-xs font-semibold text-[#E8A020]">{recipient.subject}</p>
                                  )}
                                  {recipient.body && (
                                    <p className="mt-1 text-xs text-[#d7c3ae]/65 line-clamp-2">
                                      {recipient.body.replace(/<[^>]*>/g, " ")}
                                    </p>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

    </div>
  );
}
