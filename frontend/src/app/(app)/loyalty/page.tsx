"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import {
  AlertCircle,
  CalendarClock,
  Gift,
  HeartHandshake,
  LoaderCircle,
  RefreshCw,
  Star,
  TicketPercent,
  Users,
  Wallet,
} from "lucide-react";

type NumericValue = number | string;

interface LoyaltyProgram {
  purchase_amount: NumericValue;
  base_points: NumericValue;
  point_expiry_months: number;
  referrer_reward_points: NumericValue;
  referred_reward_points: NumericValue;
}

interface Tier {
  tier: string;
  min_lifetime_points: NumericValue;
  max_lifetime_points: NumericValue | null;
  points_multiplier: NumericValue;
}

interface Reward {
  reward_id: string;
  name: string;
  points_cost: NumericValue;
  reward_value: NumericValue;
  currency: string;
}

interface LoyaltyAccount {
  loyalty_customer_id: string;
  customer_label: string | null;
  email: string | null;
  current_balance: number;
  lifetime_eligible_points: number;
  tier: string;
  is_demo: boolean;
  updated_at: string | null;
}

interface LoyaltyTransaction {
  transaction_id: string;
  loyalty_customer_id: string;
  transaction_type: string;
  points_delta: number;
  lifetime_points_delta: number;
  description: string | null;
  source_reference: string | null;
  is_demo: boolean;
  expires_at: string | null;
  created_at: string | null;
}

interface Referral {
  referral_id: string;
  referral_code: string;
  referrer_name: string | null;
  referred_name: string | null;
  status: string;
  created_at: string | null;
  qualified_at: string | null;
}

interface BonusCampaign {
  bonus_campaign_id: string;
  name: string;
  description: string | null;
  points_multiplier: NumericValue;
  starts_at: string;
  ends_at: string;
  status: string;
}

interface Expiry {
  earning_transaction_id: string;
  loyalty_customer_id: string;
  customer_label: string | null;
  expires_at: string;
  points_remaining: number;
}

interface LoyaltyData {
  program: LoyaltyProgram | null;
  tiers: Tier[];
  rewards: Reward[];
  accounts: LoyaltyAccount[];
  totalAccounts: number;
  referrals: Referral[];
  campaigns: BonusCampaign[];
  expiries: Expiry[];
}

type Section = "accounts" | "rewards" | "referrals" | "campaigns" | "expiries";
type SectionErrors = Partial<Record<Section, string>>;

const initialData: LoyaltyData = {
  program: null,
  tiers: [],
  rewards: [],
  accounts: [],
  totalAccounts: 0,
  referrals: [],
  campaigns: [],
  expiries: [],
};

const pointFormat = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 2,
});

const currencyFormat = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

function formatPoints(value: NumericValue | null | undefined): string {
  const amount = Number(value);
  return Number.isFinite(amount) ? pointFormat.format(amount) : "—";
}

function formatRupees(value: NumericValue, currency = "INR"): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  return currency === "INR" ? currencyFormat.format(amount) : `${pointFormat.format(amount)} ${currency}`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(date);
}

function getErrorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = error.response;
    if (
      typeof response === "object" &&
      response !== null &&
      "data" in response &&
      typeof response.data === "object" &&
      response.data !== null &&
      "detail" in response.data &&
      typeof response.data.detail === "string"
    ) {
      return response.data.detail;
    }
  }
  return error instanceof Error ? error.message : "Unable to load this section.";
}

function SectionError({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <p className="py-8 text-center text-sm text-[#d7c3ae]/50">{children}</p>
  );
}

function SectionHeading({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof Users;
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-4 flex items-start gap-3">
      <div className="rounded-lg border border-[#E8A020]/20 bg-[#E8A020]/10 p-2 text-[#E8A020]">
        <Icon className="h-4 w-4" />
      </div>
      <div>
        <h2 className="text-sm font-semibold text-[#e5e2e3]">{title}</h2>
        {description && <p className="mt-1 text-xs text-[#d7c3ae]/50">{description}</p>}
      </div>
    </div>
  );
}

export default function LoyaltyPage() {
  const [data, setData] = useState<LoyaltyData>(initialData);
  const [sectionErrors, setSectionErrors] = useState<SectionErrors>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [accountDetails, setAccountDetails] = useState<{
    account: LoyaltyAccount & { identities?: { source_type: string; source_namespace: string; source_customer_key: string }[] };
    transactions: LoyaltyTransaction[];
    total: number;
  } | null>(null);
  const [accountDetailsLoading, setAccountDetailsLoading] = useState(false);
  const [accountDetailsError, setAccountDetailsError] = useState<string | null>(null);
  const [adjustmentOpen, setAdjustmentOpen] = useState(false);
  const [adjustmentAccountId, setAdjustmentAccountId] = useState("");
  const [adjustmentDelta, setAdjustmentDelta] = useState("");
  const [adjustmentReason, setAdjustmentReason] = useState("");
  const [adjustmentKey, setAdjustmentKey] = useState("");
  const [adjustmentLoading, setAdjustmentLoading] = useState(false);
  const [adjustmentError, setAdjustmentError] = useState<string | null>(null);
  const [redemption, setRedemption] = useState<{ reward: Reward; accountId: string; idempotencyKey: string } | null>(null);
  const [redemptionLoading, setRedemptionLoading] = useState(false);
  const [redemptionError, setRedemptionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setLoadError(null);
      setSectionErrors({});

      const [summary, accounts, rewards, referrals, campaigns, expiries] =
        await Promise.allSettled([
          api.get<{ program: LoyaltyProgram; tiers: Tier[]; rewards: Reward[] }>(
            "/loyalty/summary",
          ),
          api.get<{ accounts: LoyaltyAccount[]; total: number }>(
            "/loyalty/accounts?limit=50&offset=0&include_demo=true",
          ),
          api.get<{ rewards: Reward[] }>("/loyalty/rewards"),
          api.get<{ referrals: Referral[] }>("/loyalty/referrals"),
          api.get<{ campaigns: BonusCampaign[] }>("/loyalty/bonus-campaigns"),
          api.get<{ expiries: Expiry[] }>("/loyalty/expiry/upcoming?days=30"),
        ]);

      if (cancelled) return;

      const errors: SectionErrors = {};
      if (summary.status === "rejected") {
        setLoadError(getErrorMessage(summary.reason));
      }
      if (accounts.status === "rejected") errors.accounts = getErrorMessage(accounts.reason);
      if (rewards.status === "rejected") errors.rewards = getErrorMessage(rewards.reason);
      if (referrals.status === "rejected") errors.referrals = getErrorMessage(referrals.reason);
      if (campaigns.status === "rejected") errors.campaigns = getErrorMessage(campaigns.reason);
      if (expiries.status === "rejected") errors.expiries = getErrorMessage(expiries.reason);

      setData({
        program: summary.status === "fulfilled" ? summary.value.data.program : null,
        tiers: summary.status === "fulfilled" ? summary.value.data.tiers : [],
        rewards: rewards.status === "fulfilled"
          ? rewards.value.data.rewards
          : summary.status === "fulfilled"
            ? summary.value.data.rewards
            : [],
        accounts: accounts.status === "fulfilled" ? accounts.value.data.accounts : [],
        totalAccounts: accounts.status === "fulfilled" ? accounts.value.data.total : 0,
        referrals: referrals.status === "fulfilled" ? referrals.value.data.referrals : [],
        campaigns: campaigns.status === "fulfilled" ? campaigns.value.data.campaigns : [],
        expiries: expiries.status === "fulfilled" ? expiries.value.data.expiries : [],
      });
      setSectionErrors(errors);
      setLoading(false);
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const program = data.program;

  const newIdempotencyKey = () => `loyalty-ui:${crypto.randomUUID()}`;

  const handleViewAccount = async (accountId: string) => {
    setAccountDetails(null);
    setAccountDetailsError(null);
    setAccountDetailsLoading(true);
    try {
      const response = await api.get<{
        account: LoyaltyAccount & { identities?: { source_type: string; source_namespace: string; source_customer_key: string }[] };
        transactions: LoyaltyTransaction[];
        total: number;
      }>(`/loyalty/accounts/${encodeURIComponent(accountId)}`);
      setAccountDetails(response.data);
    } catch (error) {
      setAccountDetailsError(getErrorMessage(error));
    } finally {
      setAccountDetailsLoading(false);
    }
  };

  const openAdjustment = (accountId = "") => {
    setAdjustmentAccountId(accountId);
    setAdjustmentDelta("");
    setAdjustmentReason("");
    setAdjustmentKey(newIdempotencyKey());
    setAdjustmentError(null);
    setAdjustmentOpen(true);
  };

  const handleAdjustmentSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const pointsDelta = Number(adjustmentDelta);
    if (!adjustmentAccountId || !Number.isFinite(pointsDelta) || pointsDelta === 0 || adjustmentReason.trim().length < 3) {
      setAdjustmentError("Select an account, enter a non-zero point amount, and provide a reason of at least 3 characters.");
      return;
    }
    setAdjustmentLoading(true);
    setAdjustmentError(null);
    try {
      await api.post("/loyalty/adjustments", {
        loyalty_customer_id: adjustmentAccountId,
        points_delta: pointsDelta,
        reason: adjustmentReason.trim(),
        idempotency_key: adjustmentKey,
      });
      setAdjustmentOpen(false);
      setRefreshKey((key) => key + 1);
    } catch (error) {
      setAdjustmentError(getErrorMessage(error));
    } finally {
      setAdjustmentLoading(false);
    }
  };

  const openRedemption = (reward: Reward) => {
    setRedemption({
      reward,
      accountId: "",
      idempotencyKey: newIdempotencyKey(),
    });
    setRedemptionError(null);
  };

  const handleRedemptionSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!redemption?.accountId) {
      setRedemptionError("Select a customer account to continue.");
      return;
    }
    setRedemptionLoading(true);
    setRedemptionError(null);
    try {
      await api.post(
        `/loyalty/accounts/${encodeURIComponent(redemption.accountId)}/redemptions`,
        {
          reward_id: redemption.reward.reward_id,
          idempotency_key: redemption.idempotencyKey,
        },
      );
      setRedemption(null);
      setRefreshKey((key) => key + 1);
    } catch (error) {
      setRedemptionError(getErrorMessage(error));
    } finally {
      setRedemptionLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1600px] space-y-6 p-6 text-left animate-in fade-in duration-500">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="mb-1 font-data-mono text-[10px] uppercase tracking-[0.2em] text-[#E8A020]">
            Customer retention
          </p>
          <h1 className="font-display-lg text-2xl font-bold text-[#e5e2e3]">
            Loyalty &amp; Rewards
          </h1>
          <p className="mt-1 text-sm text-[#d7c3ae]/55">
            Program performance, member tiers, rewards, and upcoming point expiries.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setRefreshKey((key) => key + 1)}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-[#27272A] bg-[#111113] px-4 py-2 text-xs font-semibold text-[#e5e2e3] transition hover:border-[#E8A020]/40 hover:text-[#E8A020] disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </header>

      {loadError && <SectionError message={`Unable to load loyalty program settings: ${loadError}`} />}

      {loading ? (
        <div className="flex min-h-64 flex-col items-center justify-center gap-3 rounded-xl border border-[#27272A] bg-[#111113]/85 text-sm text-[#d7c3ae]/60">
          <LoaderCircle className="h-6 w-6 animate-spin text-[#E8A020]" />
          Loading loyalty data…
        </div>
      ) : (
        <>
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-[#27272A] bg-[#111113] p-5">
              <div className="mb-3 flex items-center justify-between text-xs text-[#d7c3ae]/60">
                Live loyalty members <Users className="h-4 w-4 text-[#E8A020]" />
              </div>
              <p className="font-data-mono text-2xl font-bold text-[#e5e2e3]">
                {sectionErrors.accounts ? "—" : pointFormat.format(data.totalAccounts)}
              </p>
              <p className="mt-1 text-[11px] text-[#d7c3ae]/40">Excludes demo accounts</p>
            </div>
            <div className="rounded-xl border border-[#27272A] bg-[#111113] p-5">
              <div className="mb-3 flex items-center justify-between text-xs text-[#d7c3ae]/60">
                Base earn rate <Star className="h-4 w-4 text-[#E8A020]" />
              </div>
              <p className="font-data-mono text-2xl font-bold text-[#e5e2e3]">
                {program ? `${formatPoints(program.base_points)} pts` : "—"}
              </p>
              <p className="mt-1 text-[11px] text-[#d7c3ae]/40">
                {program ? `Per ${formatRupees(program.purchase_amount)} spent` : "Program settings unavailable"}
              </p>
            </div>
            <div className="rounded-xl border border-[#27272A] bg-[#111113] p-5">
              <div className="mb-3 flex items-center justify-between text-xs text-[#d7c3ae]/60">
                Point validity <CalendarClock className="h-4 w-4 text-[#E8A020]" />
              </div>
              <p className="font-data-mono text-2xl font-bold text-[#e5e2e3]">
                {program ? `${program.point_expiry_months} months` : "—"}
              </p>
              <p className="mt-1 text-[11px] text-[#d7c3ae]/40">From each earning date</p>
            </div>
            <div className="rounded-xl border border-[#27272A] bg-[#111113] p-5">
              <div className="mb-3 flex items-center justify-between text-xs text-[#d7c3ae]/60">
                Referral awards <HeartHandshake className="h-4 w-4 text-[#E8A020]" />
              </div>
              <p className="font-data-mono text-lg font-bold text-[#e5e2e3]">
                {program
                  ? `${formatPoints(program.referrer_reward_points)} / ${formatPoints(program.referred_reward_points)} pts`
                  : "—"}
              </p>
              <p className="mt-1 text-[11px] text-[#d7c3ae]/40">Referrer / referred customer</p>
            </div>
          </section>

          <section className="rounded-xl border border-[#27272A] bg-[#111113]/85 p-5">
            <SectionHeading icon={Star} title="Membership tiers" description="Qualification thresholds and earn multipliers configured for this program." />
            {data.tiers.length === 0 ? (
              <EmptyState>No tier rules are available.</EmptyState>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {data.tiers.map((tier) => (
                  <div key={tier.tier} className="rounded-lg border border-[#27272A] bg-[#0A0A0B]/70 p-4">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-[#e5e2e3]">{tier.tier}</h3>
                      <span className="rounded-full border border-[#E8A020]/20 bg-[#E8A020]/10 px-2 py-1 font-data-mono text-[10px] text-[#E8A020]">
                        {formatPoints(tier.points_multiplier)}×
                      </span>
                    </div>
                    <p className="mt-3 text-xs text-[#d7c3ae]/60">
                      {formatPoints(tier.min_lifetime_points)} – {tier.max_lifetime_points == null ? "No limit" : formatPoints(tier.max_lifetime_points)} lifetime points
                    </p>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-[#27272A] bg-[#111113]/85 p-5">
            <SectionHeading icon={Users} title="Customer loyalty accounts" description="The latest 50 live accounts; use the total to see the full member count." />
            {sectionErrors.accounts ? <SectionError message={sectionErrors.accounts} /> : data.accounts.length === 0 ? (
              <EmptyState>No live loyalty accounts yet.</EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[850px] text-left text-xs">
                  <thead className="border-b border-[#27272A] text-[10px] uppercase tracking-wider text-[#d7c3ae]/45">
                    <tr>
                      <th className="px-3 py-3 font-medium">Customer</th>
                      <th className="px-3 py-3 font-medium">Tier</th>
                      <th className="px-3 py-3 text-right font-medium">Available points</th>
                      <th className="px-3 py-3 text-right font-medium">Lifetime eligible</th>
                      <th className="px-3 py-3 text-right font-medium">Updated</th>
                      <th className="px-3 py-3 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#27272A]/70">
                    {data.accounts.map((account) => (
                      <tr key={account.loyalty_customer_id} className="hover:bg-white/[0.02]">
                        <td className="px-3 py-3">
                          <p className="font-medium text-[#e5e2e3]">{account.customer_label || "Unnamed customer"}</p>
                          <p className="mt-1 text-[11px] text-[#d7c3ae]/45">{account.email || "No email"}</p>
                        </td>
                        <td className="px-3 py-3">
                          <span className="rounded-full border border-[#E8A020]/20 bg-[#E8A020]/10 px-2 py-1 text-[10px] text-[#E8A020]">{account.tier}</span>
                        </td>
                        <td className="px-3 py-3 text-right font-data-mono text-[#e5e2e3]">{formatPoints(account.current_balance)}</td>
                        <td className="px-3 py-3 text-right font-data-mono text-[#d7c3ae]/70">{formatPoints(account.lifetime_eligible_points)}</td>
                        <td className="px-3 py-3 text-right text-[#d7c3ae]/50">{formatDate(account.updated_at)}</td>
                        <td className="px-3 py-3 text-right">
                          <div className="flex justify-end gap-2">
                            <button type="button" onClick={() => void handleViewAccount(account.loyalty_customer_id)} className="rounded border border-[#27272A] px-2 py-1 text-[10px] text-[#d7c3ae] hover:border-[#E8A020]/40 hover:text-[#E8A020]">
                              View
                            </button>
                            <button type="button" onClick={() => openAdjustment(account.loyalty_customer_id)} className="rounded border border-[#27272A] px-2 py-1 text-[10px] text-[#d7c3ae] hover:border-[#E8A020]/40 hover:text-[#E8A020]">
                              Adjust
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <section className="rounded-xl border border-[#27272A] bg-[#111113]/85 p-5">
              <SectionHeading icon={Gift} title="Rewards" description="Active rewards and their configured points cost." />
              {sectionErrors.rewards ? <SectionError message={sectionErrors.rewards} /> : data.rewards.length === 0 ? (
                <EmptyState>No active rewards are configured.</EmptyState>
              ) : (
                <div className="space-y-3">
                  {data.rewards.map((reward) => (
                    <div key={reward.reward_id} className="flex items-center justify-between gap-4 rounded-lg border border-[#27272A] bg-[#0A0A0B]/60 p-4">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-[#e5e2e3]">{reward.name}</p>
                        <p className="mt-1 text-xs text-[#d7c3ae]/50">{formatRupees(reward.reward_value, reward.currency)} reward value</p>
                      </div>
                      <div className="shrink-0 rounded-lg bg-[#E8A020]/10 px-3 py-2 text-right">
                        <p className="font-data-mono text-sm font-bold text-[#E8A020]">{formatPoints(reward.points_cost)}</p>
                        <p className="text-[9px] uppercase text-[#d7c3ae]/45">points</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => openRedemption(reward)}
                        disabled={data.accounts.length === 0 || sectionErrors.accounts !== undefined}
                        className="shrink-0 rounded-lg border border-[#E8A020]/30 px-3 py-2 text-[10px] font-semibold text-[#E8A020] hover:bg-[#E8A020]/10 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Redeem
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-xl border border-[#27272A] bg-[#111113]/85 p-5">
              <SectionHeading icon={HeartHandshake} title="Referrals" description="Referral status updates when the referred customer makes their first verified purchase." />
              {sectionErrors.referrals ? <SectionError message={sectionErrors.referrals} /> : data.referrals.length === 0 ? (
                <EmptyState>No referrals have been recorded.</EmptyState>
              ) : (
                <div className="space-y-3">
                  {data.referrals.map((referral) => (
                    <div key={referral.referral_id} className="flex items-center justify-between gap-3 rounded-lg border border-[#27272A] bg-[#0A0A0B]/60 p-4">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-[#e5e2e3]">
                          {referral.referrer_name || "Unknown referrer"} <span className="text-[#d7c3ae]/40">→</span> {referral.referred_name || "Unknown customer"}
                        </p>
                        <p className="mt-1 text-[11px] text-[#d7c3ae]/45">Code {referral.referral_code} · {formatDate(referral.created_at)}</p>
                        {referral.qualified_at && <p className="mt-1 text-[10px] text-[#d7c3ae]/40">Qualified {formatDate(referral.qualified_at)}</p>}
                      </div>
                      <span className={`shrink-0 rounded-full px-2 py-1 text-[10px] capitalize ${referral.status === "qualified" ? "bg-emerald-500/10 text-emerald-400" : "bg-[#E8A020]/10 text-[#E8A020]"}`}>
                        {referral.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <section className="rounded-xl border border-[#27272A] bg-[#111113]/85 p-5">
            <SectionHeading icon={TicketPercent} title="Bonus campaigns" description="Configured loyalty multipliers and their active periods." />
            {sectionErrors.campaigns ? <SectionError message={sectionErrors.campaigns} /> : data.campaigns.length === 0 ? (
              <EmptyState>No bonus campaigns are configured.</EmptyState>
            ) : (
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {data.campaigns.map((campaign) => (
                  <div key={campaign.bonus_campaign_id} className="rounded-lg border border-[#27272A] bg-[#0A0A0B]/60 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-medium text-[#e5e2e3]">{campaign.name}</h3>
                        {campaign.description && <p className="mt-1 text-xs text-[#d7c3ae]/50">{campaign.description}</p>}
                      </div>
                      <span className="shrink-0 rounded-full border border-[#E8A020]/20 bg-[#E8A020]/10 px-2 py-1 font-data-mono text-[10px] text-[#E8A020]">{formatPoints(campaign.points_multiplier)}×</span>
                    </div>
                    <div className="mt-4 flex items-center justify-between gap-2 text-[11px] text-[#d7c3ae]/50">
                      <span>{formatDate(campaign.starts_at)} – {formatDate(campaign.ends_at)}</span>
                      <span className="capitalize">{campaign.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-[#27272A] bg-[#111113]/85 p-5">
            <SectionHeading icon={Wallet} title="Upcoming point expiries" description="Unspent live points expiring in the next 30 days." />
            {sectionErrors.expiries ? <SectionError message={sectionErrors.expiries} /> : data.expiries.length === 0 ? (
              <EmptyState>No points are scheduled to expire in the next 30 days.</EmptyState>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-xs">
                  <thead className="border-b border-[#27272A] text-[10px] uppercase tracking-wider text-[#d7c3ae]/45">
                    <tr>
                      <th className="px-3 py-3 font-medium">Customer</th>
                      <th className="px-3 py-3 text-right font-medium">Points expiring</th>
                      <th className="px-3 py-3 text-right font-medium">Expiry date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#27272A]/70">
                    {data.expiries.map((expiry) => (
                      <tr key={expiry.earning_transaction_id} className="hover:bg-white/[0.02]">
                        <td className="px-3 py-3 text-[#e5e2e3]">{expiry.customer_label || expiry.loyalty_customer_id}</td>
                        <td className="px-3 py-3 text-right font-data-mono text-[#E8A020]">{formatPoints(expiry.points_remaining)}</td>
                        <td className="px-3 py-3 text-right text-[#d7c3ae]/60">{formatDate(expiry.expires_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {(accountDetailsLoading || accountDetailsError || accountDetails) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !accountDetailsLoading) {
            setAccountDetails(null);
            setAccountDetailsError(null);
          }
        }}>
          <section role="dialog" aria-modal="true" aria-labelledby="loyalty-account-title" className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-[#27272A] bg-[#111113] p-5 shadow-2xl">
            <div className="mb-5 flex items-start justify-between gap-4">
              <div>
                <h2 id="loyalty-account-title" className="text-lg font-semibold text-[#e5e2e3]">Customer account</h2>
                <p className="mt-1 text-xs text-[#d7c3ae]/50">Account information and loyalty ledger history.</p>
              </div>
              <button type="button" onClick={() => { setAccountDetails(null); setAccountDetailsError(null); }} aria-label="Close account details" className="rounded border border-[#27272A] px-3 py-1 text-xs text-[#d7c3ae] hover:text-[#E8A020]">Close</button>
            </div>
            {accountDetailsLoading ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-[#d7c3ae]/60">
                <LoaderCircle className="h-5 w-5 animate-spin text-[#E8A020]" /> Loading account…
              </div>
            ) : accountDetailsError ? (
              <SectionError message={accountDetailsError} />
            ) : accountDetails ? (
              <>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {[
                    ["Customer", accountDetails.account.customer_label || "Unnamed customer"],
                    ["Tier", accountDetails.account.tier],
                    ["Available points", formatPoints(accountDetails.account.current_balance)],
                    ["Lifetime eligible", formatPoints(accountDetails.account.lifetime_eligible_points)],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-lg border border-[#27272A] bg-[#0A0A0B]/70 p-3">
                      <p className="text-[10px] uppercase tracking-wide text-[#d7c3ae]/45">{label}</p>
                      <p className="mt-1 break-words text-sm font-medium text-[#e5e2e3]">{value}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-3 text-xs text-[#d7c3ae]/55">{accountDetails.account.email || "No email"} · {accountDetails.total} transactions</p>
                <h3 className="mb-2 mt-6 text-sm font-semibold text-[#e5e2e3]">Transaction history</h3>
                {accountDetails.transactions.length === 0 ? (
                  <EmptyState>No transactions recorded for this account.</EmptyState>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[560px] text-left text-xs">
                      <thead className="border-b border-[#27272A] text-[10px] uppercase tracking-wider text-[#d7c3ae]/45">
                        <tr>
                          <th className="px-3 py-2 font-medium">Type / description</th>
                          <th className="px-3 py-2 text-right font-medium">Points</th>
                          <th className="px-3 py-2 text-right font-medium">Date</th>
                          <th className="px-3 py-2 text-right font-medium">Expires</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#27272A]/70">
                        {accountDetails.transactions.map((transaction) => (
                          <tr key={transaction.transaction_id}>
                            <td className="px-3 py-3">
                              <p className="capitalize text-[#e5e2e3]">{transaction.transaction_type.replaceAll("_", " ")}</p>
                              {transaction.description && <p className="mt-1 text-[10px] text-[#d7c3ae]/45">{transaction.description}</p>}
                            </td>
                            <td className={`px-3 py-3 text-right font-data-mono ${transaction.points_delta < 0 ? "text-red-300" : "text-emerald-300"}`}>
                              {transaction.points_delta > 0 ? "+" : ""}{formatPoints(transaction.points_delta)}
                            </td>
                            <td className="px-3 py-3 text-right text-[#d7c3ae]/60">{formatDate(transaction.created_at)}</td>
                            <td className="px-3 py-3 text-right text-[#d7c3ae]/60">{formatDate(transaction.expires_at)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            ) : null}
          </section>
        </div>
      )}

      {adjustmentOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <form onSubmit={handleAdjustmentSubmit} className="w-full max-w-lg space-y-4 rounded-xl border border-[#27272A] bg-[#111113] p-5 shadow-2xl">
            <div>
              <h2 className="text-lg font-semibold text-[#e5e2e3]">Adjust loyalty points</h2>
              <p className="mt-1 text-xs text-[#d7c3ae]/50">Adjustments are recorded as permanent ledger transactions.</p>
            </div>
            {adjustmentError && <SectionError message={adjustmentError} />}
            <label className="block space-y-1 text-xs text-[#d7c3ae]/70">
              Customer account
              <select required value={adjustmentAccountId} onChange={(event) => setAdjustmentAccountId(event.target.value)} className="w-full rounded-lg border border-[#27272A] bg-[#0A0A0B] p-2.5 text-sm text-[#e5e2e3]">
                <option value="">Select account</option>
                {data.accounts.map((account) => <option key={account.loyalty_customer_id} value={account.loyalty_customer_id}>{account.customer_label || account.email || account.loyalty_customer_id}</option>)}
              </select>
            </label>
            <label className="block space-y-1 text-xs text-[#d7c3ae]/70">
              Points delta
              <input required type="number" step="0.01" value={adjustmentDelta} onChange={(event) => setAdjustmentDelta(event.target.value)} className="w-full rounded-lg border border-[#27272A] bg-[#0A0A0B] p-2.5 text-sm text-[#e5e2e3]" placeholder="Positive to award; negative to correct" />
            </label>
            <label className="block space-y-1 text-xs text-[#d7c3ae]/70">
              Reason
              <textarea required minLength={3} maxLength={1000} value={adjustmentReason} onChange={(event) => setAdjustmentReason(event.target.value)} className="min-h-20 w-full rounded-lg border border-[#27272A] bg-[#0A0A0B] p-2.5 text-sm text-[#e5e2e3]" />
            </label>
            <label className="block space-y-1 text-xs text-[#d7c3ae]/70">
              Idempotency key
              <input readOnly required minLength={8} maxLength={300} value={adjustmentKey} className="w-full rounded-lg border border-[#27272A] bg-[#0A0A0B] p-2.5 font-mono text-xs text-[#d7c3ae]/60" />
            </label>
            <div className="flex justify-end gap-2">
              <button type="button" disabled={adjustmentLoading} onClick={() => setAdjustmentOpen(false)} className="rounded-lg border border-[#27272A] px-4 py-2 text-xs text-[#d7c3ae] hover:bg-white/5 disabled:opacity-50">Cancel</button>
              <button type="submit" disabled={adjustmentLoading || data.accounts.length === 0} className="inline-flex items-center gap-2 rounded-lg bg-[#E8A020] px-4 py-2 text-xs font-bold text-[#291800] disabled:opacity-50">
                {adjustmentLoading && <LoaderCircle className="h-4 w-4 animate-spin" />} Save adjustment
              </button>
            </div>
          </form>
        </div>
      )}

      {redemption && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <form onSubmit={handleRedemptionSubmit} className="w-full max-w-lg space-y-4 rounded-xl border border-[#27272A] bg-[#111113] p-5 shadow-2xl">
            <div>
              <h2 className="text-lg font-semibold text-[#e5e2e3]">Confirm reward redemption</h2>
              <p className="mt-1 text-xs text-[#d7c3ae]/55">{redemption.reward.name} · {formatPoints(redemption.reward.points_cost)} points · {formatRupees(redemption.reward.reward_value, redemption.reward.currency)} value</p>
            </div>
            {redemptionError && <SectionError message={redemptionError} />}
            <label className="block space-y-1 text-xs text-[#d7c3ae]/70">
              Customer account
              <select required value={redemption.accountId} onChange={(event) => setRedemption((current) => current ? { ...current, accountId: event.target.value } : current)} className="w-full rounded-lg border border-[#27272A] bg-[#0A0A0B] p-2.5 text-sm text-[#e5e2e3]">
                <option value="">Select account</option>
                {data.accounts.map((account) => <option key={account.loyalty_customer_id} value={account.loyalty_customer_id}>{account.customer_label || account.email || account.loyalty_customer_id} · {formatPoints(account.current_balance)} pts</option>)}
              </select>
            </label>
            <p className="text-[11px] text-[#d7c3ae]/45">The server verifies the available balance before redeeming.</p>
            <p className="break-all rounded-lg border border-[#27272A] bg-[#0A0A0B] p-2.5 font-mono text-[10px] text-[#d7c3ae]/50">Idempotency key: {redemption.idempotencyKey}</p>
            <div className="flex justify-end gap-2">
              <button type="button" disabled={redemptionLoading} onClick={() => setRedemption(null)} className="rounded-lg border border-[#27272A] px-4 py-2 text-xs text-[#d7c3ae] hover:bg-white/5 disabled:opacity-50">Cancel</button>
              <button type="submit" disabled={redemptionLoading || data.accounts.length === 0} className="inline-flex items-center gap-2 rounded-lg bg-[#E8A020] px-4 py-2 text-xs font-bold text-[#291800] disabled:opacity-50">
                {redemptionLoading && <LoaderCircle className="h-4 w-4 animate-spin" />} Confirm redemption
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
