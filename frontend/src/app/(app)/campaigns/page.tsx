"use client";

import React, { useEffect, useState } from "react";
import { api } from "@/lib/api";
import toast from "react-hot-toast";
import {
  Megaphone,
  Plus,
  Send,
  Sparkles,
  CheckCircle2,
  XCircle,
  Edit3,
  Trash2,
  Eye,
  RefreshCw,
  Mail,
  Users,
  ArrowLeft,
  AlertCircle,
  Check,
  Ban,
  Clock,
} from "lucide-react";

interface Campaign {
  id: string;
  name: string;
  type: string;
  description: string | null;
  status: string;
  created_at: string | null;
  total_recipients: number;
  sent_recipients: number;
  pending_recipients: number;
}

interface Recipient {
  recipient_id: string;
  campaign_id: string;
  customer_name: string | null;
  customer_email: string;
  subject: string | null;
  body: string | null;
  status: "pending" | "approved" | "excluded" | "sent" | "failed";
  sent_at: string | null;
  created_at: string | null;
}

const CAMPAIGN_TYPES = [
  { value: "re-engagement", label: "Re-Engagement (Win Back Inactive Customers)" },
  { value: "loyalty", label: "Loyalty (Reward High-Value VIPs)" },
  { value: "referral", label: "Referral (Encourage Customer Referrals)" },
  { value: "at risk", label: "At-Risk (Prevent Customer Churn)" },
  { value: "new customer", label: "New Customer (Welcome & Onboarding)" },
  { value: "champion", label: "Champion (Special Perks for Top Buyers)" },
  { value: "about to sleep", label: "About to Sleep (Re-activate Dropping Users)" },
  { value: "lost", label: "Lost Customer (Win Back Offer)" },
  { value: "potential loyalist", label: "Potential Loyalist (Nurture Promising Users)" },
];

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);

  // Create Campaign Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newCampaignName, setNewCampaignName] = useState("");
  const [newCampaignType, setNewCampaignType] = useState("re-engagement");
  const [newCampaignDesc, setNewCampaignDesc] = useState("");
  const [autoGenerateOnCreate, setAutoGenerateOnCreate] = useState(true);
  const [creating, setCreating] = useState(false);

  // Selected Campaign Detail / Review Canvas state
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [loadingRecipients, setLoadingRecipients] = useState(false);
  const [generatingEmails, setGeneratingEmails] = useState(false);
  const [sendingBatch, setSendingBatch] = useState(false);

  // Email Preview / Edit Modal
  const [previewRecipient, setPreviewRecipient] = useState<Recipient | null>(null);
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);

  useEffect(() => {
    fetchCampaigns();
  }, []);

  const fetchCampaigns = async () => {
    try {
      setLoading(true);
      const res = await api.get("/campaigns");
      setCampaigns(res.data.campaigns || []);
    } catch (err: any) {
      toast.error("Failed to load campaigns: " + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleCreateCampaign = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCampaignName.trim()) {
      toast.error("Campaign name is required");
      return;
    }

    try {
      setCreating(true);
      const res = await api.post("/campaigns", {
        name: newCampaignName,
        type: newCampaignType,
        description: newCampaignDesc,
      });

      const createdCampaign: Campaign = res.data;
      toast.success(`Campaign "${createdCampaign.name}" created!`);
      setShowCreateModal(false);
      setNewCampaignName("");
      setNewCampaignDesc("");

      if (autoGenerateOnCreate) {
        // Trigger AI Generation immediately
        setSelectedCampaign(createdCampaign);
        await handleGenerateEmails(createdCampaign.id);
      } else {
        fetchCampaigns();
      }
    } catch (err: any) {
      toast.error("Failed to create campaign: " + (err.response?.data?.detail || err.message));
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteCampaign = async (campaignId: string, name: string) => {
    if (!confirm(`Are you sure you want to delete campaign "${name}"?`)) return;

    try {
      await api.delete(`/campaigns/${campaignId}`);
      toast.success("Campaign deleted");
      if (selectedCampaign?.id === campaignId) {
        setSelectedCampaign(null);
      }
      fetchCampaigns();
    } catch (err: any) {
      toast.error("Failed to delete campaign: " + (err.response?.data?.detail || err.message));
    }
  };

  const fetchRecipients = async (campaignId: string) => {
    try {
      setLoadingRecipients(true);
      const res = await api.get(`/campaigns/${campaignId}/recipients`);
      setRecipients(res.data.recipients || []);
    } catch (err: any) {
      toast.error("Failed to load campaign recipients: " + (err.response?.data?.detail || err.message));
    } finally {
      setLoadingRecipients(false);
    }
  };

  const handleSelectCampaign = (campaign: Campaign) => {
    setSelectedCampaign(campaign);
    fetchRecipients(campaign.id);
  };

  const handleGenerateEmails = async (campaignId: string) => {
    try {
      setGeneratingEmails(true);
      toast.loading("AI is generating personalized customer emails...", { id: "gen-toast" });

      const res = await api.post(`/campaigns/${campaignId}/generate`, {
        limit: 20,
      });

      toast.success(`Generated ${res.data.total} personalized customer emails!`, { id: "gen-toast" });
      fetchRecipients(campaignId);
      fetchCampaigns();
    } catch (err: any) {
      toast.error("Failed to generate emails: " + (err.response?.data?.detail || err.message), { id: "gen-toast" });
    } finally {
      setGeneratingEmails(false);
    }
  };

  const handleSendBatch = async () => {
    if (!selectedCampaign) return;

    const pendingOrApproved = recipients.filter((r) => r.status === "pending" || r.status === "approved");
    if (pendingOrApproved.length === 0) {
      toast.error("No pending or approved recipients available to send.");
      return;
    }

    if (
      !confirm(
        `Are you sure you want to automatically send campaign emails to ${pendingOrApproved.length} customer(s)?`
      )
    ) {
      return;
    }

    try {
      setSendingBatch(true);
      toast.loading(`Sending ${pendingOrApproved.length} emails via Gmail API...`, { id: "send-toast" });

      const res = await api.post(`/campaigns/${selectedCampaign.id}/send`, {});

      toast.success(res.data.message || "Batch send completed!", { id: "send-toast" });
      fetchRecipients(selectedCampaign.id);
      fetchCampaigns();
    } catch (err: any) {
      toast.error("Failed to send campaign: " + (err.response?.data?.detail || err.message), { id: "send-toast" });
    } finally {
      setSendingBatch(false);
    }
  };

  const handleToggleRecipientStatus = async (recipient: Recipient, newStatus: "approved" | "excluded" | "pending") => {
    try {
      const res = await api.post(`/campaigns/recipients/${recipient.recipient_id}/status`, {
        status: newStatus,
      });
      setRecipients((prev) =>
        prev.map((r) => (r.recipient_id === recipient.recipient_id ? res.data : r))
      );
      toast.success(`Recipient status updated to ${newStatus}`);
    } catch (err: any) {
      toast.error("Failed to update status: " + (err.response?.data?.detail || err.message));
    }
  };

  const handleSaveEmailEdit = async () => {
    if (!previewRecipient) return;

    try {
      setSavingEdit(true);
      const res = await api.post(`/campaigns/recipients/${previewRecipient.recipient_id}/status`, {
        status: previewRecipient.status,
        subject: editSubject,
        body: editBody,
      });

      setRecipients((prev) =>
        prev.map((r) => (r.recipient_id === previewRecipient.recipient_id ? res.data : r))
      );
      toast.success("Email content updated!");
      setPreviewRecipient(null);
    } catch (err: any) {
      toast.error("Failed to save edits: " + (err.response?.data?.detail || err.message));
    } finally {
      setSavingEdit(false);
    }
  };

  const totalCampaignsCount = campaigns.length;
  const totalSentCount = campaigns.reduce((sum, c) => sum + c.sent_recipients, 0);
  const totalRecipientsCount = campaigns.reduce((sum, c) => sum + c.total_recipients, 0);

  return (
    <div className="p-8 max-w-7xl mx-auto text-[#e5e2e3]">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Megaphone className="h-7 w-7 text-[#E8A020]" />
            <h1 className="text-2xl font-bold font-display-lg text-[#e5e2e3]">Automated Email Campaigns</h1>
          </div>
          <p className="text-xs text-[#d7c3ae]">
            Create AI-driven personalized marketing campaigns and send emails automatically to your customers.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchCampaigns}
            className="p-2.5 rounded-lg bg-[#111113] border border-[#27272A] text-[#d7c3ae] hover:text-[#e5e2e3] transition-colors"
            title="Refresh Campaigns"
          >
            <RefreshCw className="h-4 w-4" />
          </button>

          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[#E8A020] text-[#0A0A0B] font-bold text-xs hover:bg-[#F5A623] transition-all cursor-pointer shadow-lg shadow-[#E8A020]/10"
          >
            <Plus className="h-4 w-4" />
            <span>Create New Campaign</span>
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <div className="bg-[#111113] border border-[#27272A] rounded-xl p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[#d7c3ae]">Total Campaigns</span>
            <Megaphone className="h-4 w-4 text-[#E8A020]" />
          </div>
          <p className="text-2xl font-bold mt-2 font-data-mono">{totalCampaignsCount}</p>
        </div>

        <div className="bg-[#111113] border border-[#27272A] rounded-xl p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[#d7c3ae]">Personalized Previews</span>
            <Sparkles className="h-4 w-4 text-[#E8A020]" />
          </div>
          <p className="text-2xl font-bold mt-2 font-data-mono">{totalRecipientsCount}</p>
        </div>

        <div className="bg-[#111113] border border-[#27272A] rounded-xl p-5">
          <div className="flex items-center justify-between">
            <span className="text-xs text-[#d7c3ae]">Emails Sent (Gmail API)</span>
            <Send className="h-4 w-4 text-emerald-400" />
          </div>
          <p className="text-2xl font-bold mt-2 font-data-mono text-emerald-400">{totalSentCount}</p>
        </div>
      </div>

      {/* Detail / Review Canvas or Campaigns List */}
      {selectedCampaign ? (
        <div className="space-y-6">
          {/* Selected Campaign Navigation Bar */}
          <div className="bg-[#111113] border border-[#27272A] rounded-xl p-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <button
                  onClick={() => setSelectedCampaign(null)}
                  className="flex items-center gap-2 text-xs text-[#E8A020] hover:underline mb-2 cursor-pointer"
                >
                  <ArrowLeft className="h-3.5 w-3.5" />
                  <span>Back to All Campaigns</span>
                </button>
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-[#e5e2e3]">{selectedCampaign.name}</h2>
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[#E8A020]/10 border border-[#E8A020]/30 text-[#E8A020]">
                    {selectedCampaign.type}
                  </span>
                  <span
                    className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      selectedCampaign.status === "sent"
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                        : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                    }`}
                  >
                    {selectedCampaign.status}
                  </span>
                </div>
                {selectedCampaign.description && (
                  <p className="text-xs text-[#d7c3ae] mt-1">{selectedCampaign.description}</p>
                )}
              </div>

              <div className="flex items-center gap-3 flex-wrap">
                <button
                  onClick={() => handleGenerateEmails(selectedCampaign.id)}
                  disabled={generatingEmails}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#353436] text-[#e5e2e3] border border-[#27272A] hover:bg-[#353436]/80 text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
                >
                  <Sparkles className="h-4 w-4 text-[#E8A020]" />
                  <span>{generatingEmails ? "Generating..." : "Generate AI Emails"}</span>
                </button>

                <button
                  onClick={handleSendBatch}
                  disabled={sendingBatch || recipients.length === 0}
                  className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-emerald-600 text-white font-bold text-xs hover:bg-emerald-500 transition-all cursor-pointer disabled:opacity-50 shadow-lg shadow-emerald-600/20"
                >
                  <Send className="h-4 w-4" />
                  <span>{sendingBatch ? "Sending..." : "Approve & Send Emails"}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Recipient Email Previews Table */}
          <div className="bg-[#111113] border border-[#27272A] rounded-xl overflow-hidden">
            <div className="p-5 border-b border-[#27272A] flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-[#e5e2e3]">Personalized Customer Email Previews</h3>
                <p className="text-xs text-[#d7c3ae]">
                  Review, edit, or exclude individual personalized emails before sending.
                </p>
              </div>
              <span className="text-xs font-data-mono text-[#d7c3ae]">
                Total: {recipients.length}
              </span>
            </div>

            {loadingRecipients ? (
              <div className="p-12 text-center text-xs text-[#d7c3ae]">Loading recipients...</div>
            ) : recipients.length === 0 ? (
              <div className="p-12 text-center space-y-4">
                <Mail className="h-10 w-10 text-[#d7c3ae]/30 mx-auto" />
                <p className="text-xs text-[#d7c3ae]">No email previews generated for this campaign yet.</p>
                <button
                  onClick={() => handleGenerateEmails(selectedCampaign.id)}
                  disabled={generatingEmails}
                  className="px-4 py-2 rounded-lg bg-[#E8A020] text-[#0A0A0B] font-bold text-xs hover:bg-[#F5A623] transition-all cursor-pointer"
                >
                  Generate AI Emails Now
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#0e0e0f] border-b border-[#27272A] text-[#d7c3ae] font-data-mono uppercase text-[10px] tracking-wider">
                    <tr>
                      <th className="py-3 px-4">Customer</th>
                      <th className="py-3 px-4">Subject</th>
                      <th className="py-3 px-4">Status</th>
                      <th className="py-3 px-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#27272A]/50">
                    {recipients.map((r) => (
                      <tr key={r.recipient_id} className="hover:bg-[#161619] transition-colors">
                        <td className="py-3.5 px-4">
                          <div className="font-semibold text-[#e5e2e3]">
                            {r.customer_name || "Valued Customer"}
                          </div>
                          <div className="text-[11px] text-[#d7c3ae] font-data-mono">{r.customer_email}</div>
                        </td>
                        <td className="py-3.5 px-4 max-w-xs truncate text-[#e5e2e3]">
                          {r.subject || "(No subject)"}
                        </td>
                        <td className="py-3.5 px-4">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold capitalize border ${
                              r.status === "sent"
                                ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                                : r.status === "approved"
                                ? "bg-blue-500/10 text-blue-400 border-blue-500/30"
                                : r.status === "excluded"
                                ? "bg-red-500/10 text-red-400 border-red-500/30"
                                : r.status === "failed"
                                ? "bg-red-500/20 text-red-400 border-red-500/40"
                                : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                            }`}
                          >
                            {r.status === "sent" && <CheckCircle2 className="h-3 w-3" />}
                            {r.status === "excluded" && <XCircle className="h-3 w-3" />}
                            {r.status === "pending" && <Clock className="h-3 w-3" />}
                            {r.status}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-right space-x-2">
                          <button
                            onClick={() => {
                              setPreviewRecipient(r);
                              setEditSubject(r.subject || "");
                              setEditBody(r.body || "");
                            }}
                            className="px-2.5 py-1 rounded bg-[#27272A] hover:bg-[#353436] text-[#e5e2e3] transition-colors cursor-pointer text-[11px]"
                          >
                            Preview / Edit
                          </button>

                          {r.status !== "sent" && (
                            r.status === "excluded" ? (
                              <button
                                onClick={() => handleToggleRecipientStatus(r, "pending")}
                                className="px-2 py-1 rounded bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 border border-blue-500/30 transition-colors cursor-pointer text-[11px]"
                                title="Include Recipient"
                              >
                                Include
                              </button>
                            ) : (
                              <button
                                onClick={() => handleToggleRecipientStatus(r, "excluded")}
                                className="px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/30 transition-colors cursor-pointer text-[11px]"
                                title="Exclude Recipient"
                              >
                                Exclude
                              </button>
                            )
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* All Campaigns List View */
        <div className="bg-[#111113] border border-[#27272A] rounded-xl overflow-hidden">
          <div className="p-5 border-b border-[#27272A] flex items-center justify-between">
            <h2 className="text-sm font-bold text-[#e5e2e3]">All Marketing Campaigns</h2>
            <span className="text-xs font-data-mono text-[#d7c3ae]">Total: {campaigns.length}</span>
          </div>

          {loading ? (
            <div className="p-12 text-center text-xs text-[#d7c3ae]">Loading campaigns...</div>
          ) : campaigns.length === 0 ? (
            <div className="p-12 text-center space-y-4">
              <Megaphone className="h-12 w-12 text-[#d7c3ae]/30 mx-auto" />
              <p className="text-xs text-[#d7c3ae]">No marketing campaigns created yet.</p>
              <button
                onClick={() => setShowCreateModal(true)}
                className="px-4 py-2 rounded-lg bg-[#E8A020] text-[#0A0A0B] font-bold text-xs hover:bg-[#F5A623] transition-all cursor-pointer"
              >
                Create Your First Campaign
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-[#0e0e0f] border-b border-[#27272A] text-[#d7c3ae] font-data-mono uppercase text-[10px] tracking-wider">
                  <tr>
                    <th className="py-3.5 px-4">Campaign Name</th>
                    <th className="py-3.5 px-4">Type</th>
                    <th className="py-3.5 px-4">Status</th>
                    <th className="py-3.5 px-4">Recipients</th>
                    <th className="py-3.5 px-4">Sent</th>
                    <th className="py-3.5 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#27272A]/50">
                  {campaigns.map((c) => (
                    <tr key={c.id} className="hover:bg-[#161619] transition-colors">
                      <td className="py-4 px-4">
                        <div className="font-bold text-[#e5e2e3]">{c.name}</div>
                        {c.description && (
                          <div className="text-[11px] text-[#d7c3ae] truncate max-w-xs">{c.description}</div>
                        )}
                      </td>
                      <td className="py-4 px-4">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-[#E8A020]/10 border border-[#E8A020]/30 text-[#E8A020]">
                          {c.type}
                        </span>
                      </td>
                      <td className="py-4 px-4">
                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                            c.status === "sent"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                              : "bg-zinc-800 text-zinc-400 border border-zinc-700"
                          }`}
                        >
                          {c.status}
                        </span>
                      </td>
                      <td className="py-4 px-4 font-data-mono">{c.total_recipients}</td>
                      <td className="py-4 px-4 font-data-mono text-emerald-400">{c.sent_recipients}</td>
                      <td className="py-4 px-4 text-right space-x-2">
                        <button
                          onClick={() => handleSelectCampaign(c)}
                          className="px-3 py-1.5 rounded bg-[#E8A020]/10 border border-[#E8A020]/30 text-[#E8A020] hover:bg-[#E8A020]/20 font-bold transition-all text-xs cursor-pointer"
                        >
                          Review & Send
                        </button>
                        <button
                          onClick={() => handleDeleteCampaign(c.id, c.name)}
                          className="p-1.5 rounded text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer"
                          title="Delete Campaign"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Modal 1: Create Campaign */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#111113] border border-[#27272A] rounded-2xl w-full max-w-lg p-6 space-y-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#27272A] pb-4">
              <div className="flex items-center gap-3">
                <Megaphone className="h-6 w-6 text-[#E8A020]" />
                <h2 className="text-lg font-bold text-[#e5e2e3]">Create New Campaign</h2>
              </div>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-[#d7c3ae] hover:text-[#e5e2e3] text-lg font-bold cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateCampaign} className="space-y-4 text-xs">
              <div>
                <label className="block text-[#d7c3ae] mb-1 font-semibold">Campaign Name *</label>
                <input
                  type="text"
                  value={newCampaignName}
                  onChange={(e) => setNewCampaignName(e.target.value)}
                  placeholder="e.g. Q3 Electronics Re-Engagement"
                  className="w-full bg-[#0e0e0f] border border-[#27272A] rounded-lg p-2.5 text-[#e5e2e3] focus:outline-none focus:border-[#E8A020]"
                  required
                />
              </div>

              <div>
                <label className="block text-[#d7c3ae] mb-1 font-semibold">Campaign Type *</label>
                <select
                  value={newCampaignType}
                  onChange={(e) => setNewCampaignType(e.target.value)}
                  className="w-full bg-[#0e0e0f] border border-[#27272A] rounded-lg p-2.5 text-[#e5e2e3] focus:outline-none focus:border-[#E8A020]"
                >
                  {CAMPAIGN_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[#d7c3ae] mb-1 font-semibold">
                  Campaign Objective / AI Strategy Prompt
                </label>
                <textarea
                  value={newCampaignDesc}
                  onChange={(e) => setNewCampaignDesc(e.target.value)}
                  placeholder="Describe your offer or goal (e.g. 15% discount for churn-risk customers)..."
                  className="w-full bg-[#0e0e0f] border border-[#27272A] rounded-lg p-2.5 text-[#e5e2e3] h-20 focus:outline-none focus:border-[#E8A020]"
                />
              </div>

              <div className="flex items-center gap-2 pt-2">
                <input
                  type="checkbox"
                  id="autoGen"
                  checked={autoGenerateOnCreate}
                  onChange={(e) => setAutoGenerateOnCreate(e.target.checked)}
                  className="rounded accent-[#E8A020]"
                />
                <label htmlFor="autoGen" className="text-[#e5e2e3] cursor-pointer">
                  Automatically generate personalized customer emails with AI after creating
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-[#27272A]">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 rounded-lg border border-[#27272A] text-[#d7c3ae] hover:bg-[#1e1e22]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-5 py-2 rounded-lg bg-[#E8A020] text-[#0A0A0B] font-bold hover:bg-[#F5A623] disabled:opacity-50"
                >
                  {creating ? "Creating..." : "Create Campaign"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal 2: Preview / Edit Recipient Email */}
      {previewRecipient && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-[#111113] border border-[#27272A] rounded-2xl w-full max-w-2xl p-6 space-y-6 max-h-[90vh] overflow-y-auto shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#27272A] pb-4">
              <div>
                <h3 className="text-base font-bold text-[#e5e2e3]">
                  Personalized Email for {previewRecipient.customer_name || "Customer"}
                </h3>
                <p className="text-xs text-[#d7c3ae] font-data-mono">{previewRecipient.customer_email}</p>
              </div>
              <button
                onClick={() => setPreviewRecipient(null)}
                className="text-[#d7c3ae] hover:text-[#e5e2e3] text-lg font-bold cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <label className="block text-[#d7c3ae] mb-1 font-semibold">Subject Line</label>
                <input
                  type="text"
                  value={editSubject}
                  onChange={(e) => setEditSubject(e.target.value)}
                  className="w-full bg-[#0e0e0f] border border-[#27272A] rounded-lg p-2.5 text-[#e5e2e3] focus:outline-none focus:border-[#E8A020]"
                />
              </div>

              <div>
                <label className="block text-[#d7c3ae] mb-1 font-semibold">HTML Body Preview</label>
                <div
                  className="w-full bg-[#0e0e0f] border border-[#27272A] rounded-lg p-4 max-h-60 overflow-y-auto"
                  dangerouslySetInnerHTML={{ __html: editBody }}
                />
              </div>

              <div>
                <label className="block text-[#d7c3ae] mb-1 font-semibold">Edit Raw Body (HTML)</label>
                <textarea
                  value={editBody}
                  onChange={(e) => setEditBody(e.target.value)}
                  className="w-full bg-[#0e0e0f] border border-[#27272A] rounded-lg p-2.5 text-[#e5e2e3] font-data-mono text-[11px] h-32 focus:outline-none focus:border-[#E8A020]"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-[#27272A]">
              <button
                onClick={() => setPreviewRecipient(null)}
                className="px-4 py-2 rounded-lg border border-[#27272A] text-[#d7c3ae] text-xs hover:bg-[#1e1e22]"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveEmailEdit}
                disabled={savingEdit}
                className="px-5 py-2 rounded-lg bg-[#E8A020] text-[#0A0A0B] font-bold text-xs hover:bg-[#F5A623] disabled:opacity-50"
              >
                {savingEdit ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
