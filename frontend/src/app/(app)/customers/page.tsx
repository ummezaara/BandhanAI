"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import {
  Search,
  Users,
  TrendingUp,
  AlertTriangle,
  Mail,
  X,
  ArrowLeft,
  Loader2,
  Calendar,
  DollarSign,
  Phone,
  MapPin,
  Smile,
  ShieldCheck,
  Eye,
  Activity,
  UserCheck,
} from "lucide-react";
import toast from "react-hot-toast";

interface Customer {
  id: string;
  name: string;
  email: string;
  phone: string;
  region: string;
  total_spend: number;
  churn_risk: number;
  feedback_score: number;
  last_purchase: string;
}

interface CampaignEmail {
  subject: string;
  body: string;
  sent_at: string;
  status: string;
  opened: boolean;
  campaign_name: string;
}

function CustomersContent() {
  const searchParams = useSearchParams();
  const initialSearch = searchParams?.get("search") || "";
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [totalCustomers, setTotalCustomers] = useState(0);
  const [searchVal, setSearchVal] = useState(initialSearch);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const s = searchParams?.get("search");
    if (s !== null && s !== undefined) {
      setSearchVal(s);
    }
  }, [searchParams]);
  
  // Pagination
  const [page, setPage] = useState(1);
  const limit = 20;

  // Selected customer for 360 view
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [campaignEmails, setCampaignEmails] = useState<CampaignEmail[]>([]);
  const [loadingDetails, setLoadingDetails] = useState(false);

  const fetchCustomers = useCallback(async () => {
    setLoading(true);
    try {
      const offset = (page - 1) * limit;
      const res = await api.get("/crm/customers", {
        params: {
          search: searchVal,
          limit,
          offset,
        },
      });
      setCustomers(res.data.customers || []);
      setTotalCustomers(res.data.total || 0);
    } catch (err) {
      console.error("Failed to load customer profiles:", err);
      toast.error("Failed to load customer profiles");
    } finally {
      setLoading(false);
    }
  }, [searchVal, page]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchCustomers();
    }, 300);
    return () => clearTimeout(timer);
  }, [fetchCustomers]);

  const loadCustomer360Details = async (customerId: string) => {
    setSelectedCustomerId(customerId);
    setLoadingDetails(true);
    try {
      const res = await api.get(`/crm/customers/${customerId}`);
      setSelectedCustomer(res.data.customer);
      setCampaignEmails(res.data.emails || []);
    } catch (err) {
      console.error("Failed to load customer details:", err);
      toast.error("Customer details not accessible.");
      setSelectedCustomerId(null);
    } finally {
      setLoadingDetails(false);
    }
  };

  const getRiskColor = (risk: number) => {
    if (risk >= 0.75) return "text-red-400 border-red-500/20 bg-red-500/10";
    if (risk >= 0.45) return "text-[#E8A020] border-[#E8A020]/20 bg-[#E8A020]/10";
    return "text-emerald-400 border-emerald-500/20 bg-emerald-500/10";
  };

  const getRiskLabel = (risk: number) => {
    if (risk >= 0.75) return "HIGH RISK";
    if (risk >= 0.45) return "MEDIUM RISK";
    return "LOW RISK";
  };

  return (
    <div className="p-6 space-y-6 max-w-[1600px] mx-auto animate-in fade-in duration-500 text-left flex h-[calc(100vh-64px)] overflow-hidden gap-6">
      
      {/* Left Pane: Customer Directory List */}
      <div className="flex-1 flex flex-col bg-[#111113]/85 backdrop-blur-md border border-[#27272A] rounded-xl overflow-hidden h-full">
        {/* Header Search Area */}
        <div className="p-5 border-b border-[#27272A] flex flex-col md:flex-row md:items-center justify-between gap-4 shrink-0 bg-[#0E0E10]">
          <div>
            <h2 className="font-display-lg text-lg font-bold text-[#e5e2e3] flex items-center gap-2">
              <Users className="h-5 w-5 text-[#E8A020]" />
              Customer 360 Directory
            </h2>
            <p className="text-xs text-[#d7c3ae]/50">Monitor customer lifecycles, spend metrics, and AI health risks</p>
          </div>

          <div className="relative w-full md:w-80">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#d7c3ae]/40" />
            <input
              type="text"
              placeholder="Search by name, email, region..."
              value={searchVal}
              onChange={(e) => {
                setSearchVal(e.target.value);
                setPage(1);
              }}
              className="w-full bg-[#09090B] border border-[#27272A] rounded-lg p-2 pl-9 text-xs text-[#e5e2e3] placeholder-[#d7c3ae]/30 focus:outline-none focus:border-[#E8A020] transition-colors"
            />
          </div>
        </div>

        {/* List Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3 opacity-60">
              <Loader2 className="h-7 w-7 animate-spin text-[#E8A020]" />
              <span className="font-data-mono text-[10px] uppercase text-[#d7c3ae]">Searching directory...</span>
            </div>
          ) : customers.length === 0 ? (
            <div className="p-12 text-center text-xs text-[#d7c3ae]/50">
              No matching customer profiles found in database.
            </div>
          ) : (
            <div className="divide-y divide-[#27272A]/30">
              {customers.map((c) => {
                const isActive = selectedCustomerId === c.id;
                return (
                  <div
                    key={c.id}
                    onClick={() => loadCustomer360Details(c.id)}
                    className={`p-4 flex items-center justify-between gap-4 cursor-pointer transition-all ${
                      isActive
                        ? "bg-[#1c1b1c] border-l-4 border-[#E8A020]"
                        : "hover:bg-[#141416]/50 border-l-4 border-transparent"
                    }`}
                  >
                    <div className="min-w-0 space-y-1">
                      <div className="flex items-center gap-2">
                        <h4 className="font-bold text-sm text-[#e5e2e3] truncate">{c.name}</h4>
                        <span className={`px-1.5 py-0.5 rounded text-[8px] font-data-mono font-bold border ${getRiskColor(c.churn_risk)}`}>
                          {getRiskLabel(c.churn_risk)}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[#d7c3ae]/60 font-body-base">
                        <span className="truncate">{c.email}</span>
                        {c.region && (
                          <span className="flex items-center gap-1">
                            <MapPin className="h-3 w-3 text-[#d7c3ae]/30" />
                            {c.region}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="text-right shrink-0 flex items-center gap-6">
                      <div className="space-y-0.5">
                        <p className="text-[10px] text-[#d7c3ae]/40 font-data-mono">TOTAL LTV</p>
                        <p className="text-xs font-bold font-data-mono text-[#e5e2e3]">₹{Math.round(c.total_spend).toLocaleString()}</p>
                      </div>
                      <button className="p-1.5 rounded-lg border border-[#27272A] hover:bg-[#2b2a2b] hover:text-[#E8A020] transition-colors">
                        <Eye className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Pagination Footer */}
        {totalCustomers > limit && (
          <div className="p-4 border-t border-[#27272A] flex items-center justify-between shrink-0 bg-[#0E0E10] font-data-mono text-xs text-[#d7c3ae]/65">
            <span>
              Showing {Math.min(totalCustomers, (page - 1) * limit + 1)} - {Math.min(totalCustomers, page * limit)} of {totalCustomers}
            </span>
            <div className="flex gap-2">
              <button
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-3 py-1 border border-[#27272A] rounded hover:bg-[#1c1b1c] disabled:opacity-30 disabled:hover:bg-transparent"
              >
                Prev
              </button>
              <button
                disabled={page * limit >= totalCustomers}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1 border border-[#27272A] rounded hover:bg-[#1c1b1c] disabled:opacity-30 disabled:hover:bg-transparent"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Right Pane: Customer 360 Detail Card */}
      {selectedCustomerId && (
        <div className="w-[450px] bg-[#0E0E10] border border-[#27272A] rounded-xl flex flex-col overflow-hidden h-full shrink-0 shadow-2xl animate-in slide-in-from-right duration-300">
          {loadingDetails ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-3 opacity-60">
              <Loader2 className="h-8 w-8 animate-spin text-[#E8A020]" />
              <span className="font-data-mono text-xs text-[#d7c3ae]">Loading Customer 360...</span>
            </div>
          ) : selectedCustomer ? (
            <>
              {/* Profile Card Header */}
              <div className="p-5 border-b border-[#27272A] bg-[#141416] flex items-start justify-between relative">
                <div className="space-y-2">
                  <div className="w-12 h-12 rounded-xl bg-[#201f20] border border-[#27272A] flex items-center justify-center font-bold text-lg text-[#E8A020]">
                    {selectedCustomer.name.substring(0, 2).toUpperCase()}
                  </div>
                  <div>
                    <h3 className="font-display-lg text-base font-bold text-[#e5e2e3]">{selectedCustomer.name}</h3>
                    <p className="text-xs text-[#d7c3ae]/50">{selectedCustomer.email}</p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedCustomerId(null)}
                  className="text-[#d7c3ae]/60 hover:text-white p-1 rounded-lg hover:bg-[#1c1b1c] transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Profile Body */}
              <div className="flex-1 overflow-y-auto p-5 space-y-6 custom-scrollbar text-xs">
                
                {/* Stats Grid */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3.5 bg-[#111113] border border-[#27272A]/70 rounded-lg space-y-1">
                    <span className="text-[10px] font-data-mono text-[#d7c3ae]/40 uppercase tracking-tight flex items-center gap-1">
                      <DollarSign className="h-3 w-3 text-[#E8A020]" />
                      Total Spend
                    </span>
                    <p className="text-sm font-bold font-data-mono text-[#e5e2e3]">₹{Math.round(selectedCustomer.total_spend).toLocaleString()}</p>
                  </div>
                  <div className="p-3.5 bg-[#111113] border border-[#27272A]/70 rounded-lg space-y-1">
                    <span className="text-[10px] font-data-mono text-[#d7c3ae]/40 uppercase tracking-tight flex items-center gap-1">
                      <Smile className="h-3 w-3 text-[#3ac2ff]" />
                      Feedback Score
                    </span>
                    <p className="text-sm font-bold font-data-mono text-[#e5e2e3]">
                      {selectedCustomer.feedback_score ? `${selectedCustomer.feedback_score}/5` : "N/A"}
                    </p>
                  </div>
                </div>

                {/* Contact & Location */}
                <div className="space-y-3 p-4 bg-[#111113] border border-[#27272A]/50 rounded-lg">
                  <h4 className="text-[10px] font-data-mono text-[#E8A020] uppercase font-bold tracking-widest border-b border-[#27272A] pb-1.5">
                    Contact & Location Details
                  </h4>
                  <div className="space-y-2 text-[#d7c3ae]/75 font-body-base">
                    {selectedCustomer.phone && (
                      <p className="flex items-center gap-2">
                        <Phone className="h-3.5 w-3.5 text-[#d7c3ae]/30" />
                        {selectedCustomer.phone}
                      </p>
                    )}
                    {selectedCustomer.region && (
                      <p className="flex items-center gap-2">
                        <MapPin className="h-3.5 w-3.5 text-[#d7c3ae]/30" />
                        {selectedCustomer.region}
                      </p>
                    )}
                    {selectedCustomer.last_purchase && (
                      <p className="flex items-center gap-2">
                        <Calendar className="h-3.5 w-3.5 text-[#d7c3ae]/30" />
                        Last Activity: {new Date(selectedCustomer.last_purchase).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                </div>

                {/* Explainable Churn Risk */}
                <div className="space-y-3 p-4 bg-[#111113] border border-[#27272A]/50 rounded-lg">
                  <div className="flex items-center justify-between border-b border-[#27272A] pb-1.5">
                    <h4 className="text-[10px] font-data-mono text-red-400 uppercase font-bold tracking-widest flex items-center gap-1">
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                      AI Churn Risk Diagnostics
                    </h4>
                    <span className="font-data-mono font-bold text-red-400">{Math.round(selectedCustomer.churn_risk * 100)}%</span>
                  </div>
                  
                  {selectedCustomer.churn_risk >= 0.45 ? (
                    <div className="space-y-1.5">
                      <p className="text-[11px] text-[#ffb4ab] font-bold leading-normal">
                        Reasons flagged by risk scorer:
                      </p>
                      <ul className="list-disc pl-4 space-y-1 text-[#d7c3ae]/70 leading-relaxed font-body-base">
                        {/* If we have reasons in risk snap, list them */}
                        {selectedCustomer.churn_risk >= 0.75 ? (
                          <li>Customer purchase cycles are severely stale (exceeds 180 days).</li>
                        ) : (
                          <li>Staleness flagged in recent activity intervals.</li>
                        )}
                        {selectedCustomer.feedback_score && selectedCustomer.feedback_score <= 3 && (
                          <li>Low NPS / negative feedback score rating alert.</li>
                        )}
                      </ul>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-emerald-400 font-body-sm italic">
                      <UserCheck className="h-4 w-4" />
                      <span>This customer shows a highly healthy profile. No risks identified.</span>
                    </div>
                  )}
                </div>

                {/* Campaigns History */}
                <div className="space-y-3">
                  <h4 className="text-[10px] font-data-mono text-[#d7c3ae]/40 uppercase tracking-widest font-bold flex items-center gap-1">
                    <Mail className="h-3.5 w-3.5" />
                    Outreach & Campaign History ({campaignEmails.length})
                  </h4>
                  {campaignEmails.length === 0 ? (
                    <p className="text-[#d7c3ae]/40 italic p-3 text-center border border-dashed border-[#27272A] rounded">
                      No outreach campaigns sent to this customer.
                    </p>
                  ) : (
                    <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1 custom-scrollbar">
                      {campaignEmails.map((email, idx) => (
                        <div key={idx} className="p-3 bg-[#111113] border border-[#27272A]/70 rounded-lg space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-data-mono text-[9px] text-[#3ac2ff] uppercase font-bold">
                              {email.campaign_name}
                            </span>
                            <span className={`px-1.5 py-0.2 bg-green-500/10 text-green-400 border border-green-500/20 text-[8px] font-bold rounded font-data-mono uppercase`}>
                              {email.status}
                            </span>
                          </div>
                          <p className="font-bold text-[#e5e2e3] truncate">{email.subject}</p>
                          <div className="flex justify-between items-center text-[10px] text-[#d7c3ae]/50 pt-1 border-t border-[#27272A]/30">
                            <span>{new Date(email.sent_at).toLocaleDateString()}</span>
                            {email.opened && (
                              <span className="text-[#E8A020] font-bold">Opened</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-[#d7c3ae]/40">
              Error fetching profile details
            </div>
          )}
        </div>
      )}

    </div>
  );
}

export default function Customers360Page() {
  return (
    <Suspense fallback={
      <div className="p-6 text-center text-xs font-data-mono text-[#d7c3ae]/40">
        Loading customer directory...
      </div>
    }>
      <CustomersContent />
    </Suspense>
  );
}
