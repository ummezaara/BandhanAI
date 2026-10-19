"use client";

import React from "react";
import Link from "next/link";
import {
  Sparkles,
  ArrowRight,
  Database,
  ShieldCheck,
  Brain,
  Zap,
  Users,
  Megaphone,
  CheckCircle2,
  Lock,
  LineChart,
  Bot,
  Terminal,
  Activity,
  Layers,
  Flame,
  Globe,
  Mail,
  ChevronRight,
} from "lucide-react";

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0A0A0B] text-[#e5e2e3] font-sans selection:bg-[#E8A020]/30 selection:text-[#E8A020] overflow-x-hidden">
      
      {/* Dynamic Background Effects */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0 opacity-30">
        <div className="absolute -top-[20%] left-1/2 -translate-x-1/2 w-[1000px] h-[600px] bg-[radial-gradient(ellipse_at_center,#E8A020_0%,transparent_70%)] blur-[140px]" />
        <div className="absolute top-[40%] -left-[200px] w-[600px] h-[600px] bg-[radial-gradient(circle_at_center,#3ac2ff_0%,transparent_70%)] blur-[160px] opacity-20" />
        <div className="absolute top-[70%] -right-[200px] w-[600px] h-[600px] bg-[radial-gradient(circle_at_center,#E8A020_0%,transparent_70%)] blur-[160px] opacity-20" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f1f2315_1px,transparent_1px),linear-gradient(to_bottom,#1f1f2315_1px,transparent_1px)] bg-[size:4rem_4rem]" />
      </div>

      {/* Top Navbar */}
      <header className="sticky top-0 z-50 backdrop-blur-xl bg-[#0A0A0B]/80 border-b border-[#27272A]/70">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3 group">
            <div className="w-10 h-10 rounded-xl bg-[#E8A020]/10 border border-[#E8A020]/30 flex items-center justify-center text-[#E8A020] font-bold text-xl group-hover:scale-105 transition-transform">
              B
            </div>
            <div>
              <span className="font-display-lg text-xl font-bold text-[#e5e2e3] tracking-tight flex items-center gap-2">
                Bandhan<span className="text-[#E8A020]">AI</span>
                <span className="text-[9px] font-data-mono px-1.5 py-0.5 rounded bg-[#E8A020]/15 text-[#E8A020] border border-[#E8A020]/30 uppercase tracking-widest font-bold">v3 Enterprise</span>
              </span>
            </div>
          </Link>

          <nav className="hidden md:flex items-center gap-8 text-xs font-medium text-[#d7c3ae]/70">
            <a href="#features" className="hover:text-[#E8A020] transition-colors">Platform Capabilities</a>
            <a href="#architecture" className="hover:text-[#E8A020] transition-colors">AI Architecture</a>
            <a href="#risk-scoring" className="hover:text-[#E8A020] transition-colors">Explainable Risk</a>
            <a href="#pricing" className="hover:text-[#E8A020] transition-colors">Packages</a>
          </nav>

          <div className="flex items-center gap-4">
            <Link
              href="/login"
              className="text-xs font-bold text-[#d7c3ae] hover:text-white transition-colors px-4 py-2"
            >
              Sign In
            </Link>
            <Link
              href="/dashboard"
              className="flex items-center gap-2 text-xs font-bold bg-[#E8A020] text-[#291800] px-5 py-2.5 rounded-lg hover:brightness-110 active:scale-95 transition-all shadow-[0_0_25px_rgba(232,160,32,0.3)]"
            >
              <span>Launch Platform</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative z-10 pt-20 pb-24 max-w-7xl mx-auto px-6 text-center">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-[#1c1b1c] border border-[#E8A020]/30 text-[#E8A020] text-xs font-data-mono font-bold mb-8 animate-fade-in">
          <Sparkles className="h-3.5 w-3.5 animate-pulse text-[#E8A020]" />
          <span>Autonomous Schema Discovery & Growth Agent Platform</span>
        </div>

        <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight text-[#e5e2e3] max-w-5xl mx-auto leading-[1.1] mb-8">
          Turn Your Database Into a <br className="hidden sm:block" />
          <span className="bg-gradient-to-r from-[#E8A020] via-[#f7c26b] to-[#3ac2ff] bg-clip-text text-transparent">
            Conversational Growth Engine
          </span>
        </h1>

        <p className="text-base md:text-lg text-[#d7c3ae]/70 max-w-3xl mx-auto mb-10 leading-relaxed font-body-base">
          BandhanAI automatically discovers database schemas, scores explainable customer churn risks, and executes targeted multi-channel campaign outreach — all powered by LangGraph, FastMCP, and zero manual SQL writing.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
          <Link
            href="/dashboard"
            className="w-full sm:w-auto flex items-center justify-center gap-3 px-8 py-4 bg-[#E8A020] text-[#291800] rounded-xl font-bold text-sm hover:brightness-110 transition-all shadow-[0_0_35px_rgba(232,160,32,0.4)] active:scale-95"
          >
            <span>Open Demo Workspace</span>
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            href="/onboarding"
            className="w-full sm:w-auto flex items-center justify-center gap-2 px-8 py-4 bg-[#141416] border border-[#27272A] text-[#e5e2e3] rounded-xl font-bold text-sm hover:bg-[#1f1f23] hover:border-[#E8A020]/50 transition-all active:scale-95"
          >
            <Database className="h-4 w-4 text-[#E8A020]" />
            <span>Connect Live Supabase DB</span>
          </Link>
        </div>

        {/* Hero Visual Mockup */}
        <div className="relative max-w-5xl mx-auto rounded-2xl border border-[#27272A] bg-[#111113]/90 backdrop-blur-2xl p-4 shadow-2xl overflow-hidden group">
          <div className="absolute inset-0 bg-gradient-to-tr from-[#E8A020]/10 via-transparent to-[#3ac2ff]/10 opacity-50" />
          
          <div className="flex items-center justify-between px-4 py-3 bg-[#0A0A0B] border-b border-[#27272A] rounded-t-xl">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
              <span className="font-data-mono text-[10px] text-[#d7c3ae]/40 ml-3">bandhan-ai-workspace.internal</span>
            </div>
            <div className="flex items-center gap-2 font-data-mono text-[10px] text-[#E8A020]">
              <span className="w-2 h-2 rounded-full bg-[#E8A020] animate-ping" />
              <span>MCP Server Active</span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 p-4 text-left font-data-mono text-xs">
            {/* Live Analytics Box */}
            <div className="p-4 bg-[#0A0A0B] border border-[#27272A] rounded-xl space-y-3">
              <div className="flex items-center justify-between text-[#d7c3ae]">
                <span className="flex items-center gap-2 text-[10px] uppercase font-bold text-[#E8A020]">
                  <Terminal className="h-3.5 w-3.5" /> Natural Language SQL
                </span>
                <span className="text-[9px] text-[#3ac2ff]">Guarded Read-Only</span>
              </div>
              <div className="p-2.5 bg-[#141416] rounded border border-[#27272A] text-[11px] text-[#e5e2e3]">
                <span className="text-[#3ac2ff]">&gt;</span> &quot;Show me top 5 high spenders in Mumbai with churn risk &gt; 70%&quot;
              </div>
              <div className="p-2 bg-[#0e0e0f] rounded text-[10px] text-emerald-400 border border-emerald-500/20">
                ✓ SQL Executed (0.012s) — 5 matching records retrieved.
              </div>
            </div>

            {/* Risk Snapshot Box */}
            <div className="p-4 bg-[#0A0A0B] border border-[#27272A] rounded-xl space-y-3">
              <div className="flex items-center justify-between text-[#d7c3ae]">
                <span className="flex items-center gap-2 text-[10px] uppercase font-bold text-red-400">
                  <Activity className="h-3.5 w-3.5" /> Explainable Risk Diagnostics
                </span>
                <span className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 font-bold text-[9px]">3 HIGH RISK</span>
              </div>
              <div className="space-y-1.5 text-[10px]">
                <div className="flex justify-between p-1.5 bg-[#141416] rounded border border-[#27272A]">
                  <span>Priya Sharma</span>
                  <span className="text-red-400 font-bold">85% Churn Risk</span>
                </div>
                <div className="text-[9px] text-[#d7c3ae]/50 pl-2">
                  • Inactive &gt; 180 days • Low NPS rating (2/5)
                </div>
              </div>
            </div>

            {/* Multi-Channel Outreach Box */}
            <div className="p-4 bg-[#0A0A0B] border border-[#27272A] rounded-xl space-y-3">
              <div className="flex items-center justify-between text-[#d7c3ae]">
                <span className="flex items-center gap-2 text-[10px] uppercase font-bold text-[#3ac2ff]">
                  <Mail className="h-3.5 w-3.5" /> Gmail OAuth &amp; Resend Engine
                </span>
                <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-bold text-[9px]">LIVE READY</span>
              </div>
              <div className="p-2.5 bg-[#141416] rounded border border-[#27272A] text-[10px] text-[#e5e2e3] space-y-1">
                <p className="font-bold text-[#E8A020]">AI Campaign &quot;Re-engage Champions&quot;</p>
                <p className="text-[9px] text-[#d7c3ae]/60">HTML Email generated + sent via connected Google OAuth.</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Highlights Section */}
      <section id="features" className="relative z-10 py-20 bg-[#0E0E10] border-y border-[#27272A]/70">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center max-w-3xl mx-auto mb-16 space-y-4">
            <h2 className="font-display-lg text-3xl md:text-4xl font-bold text-[#e5e2e3]">
              Built for Real-World Database Integration
            </h2>
            <p className="text-sm text-[#d7c3ae]/60">
              Not just another static AI wrapper. BandhanAI connects directly to live PostgreSQL and Supabase databases, discovering table semantics autonomously.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            
            {/* Feature 1 */}
            <div className="p-6 rounded-xl bg-[#111113] border border-[#27272A] hover:border-[#E8A020]/50 transition-all space-y-4 group">
              <div className="w-12 h-12 rounded-lg bg-[#E8A020]/10 border border-[#E8A020]/30 flex items-center justify-center text-[#E8A020] group-hover:scale-110 transition-transform">
                <Database className="h-6 w-6" />
              </div>
              <h3 className="text-base font-bold text-[#e5e2e3]">AI Schema Discovery Agent</h3>
              <p className="text-xs text-[#d7c3ae]/60 leading-relaxed font-body-base">
                Connect your Supabase URL or upload a CSV. Our zero-shot classifier agent categorizes tables as customer, order, or product models automatically.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="p-6 rounded-xl bg-[#111113] border border-[#27272A] hover:border-[#3ac2ff]/50 transition-all space-y-4 group">
              <div className="w-12 h-12 rounded-lg bg-[#3ac2ff]/10 border border-[#3ac2ff]/30 flex items-center justify-center text-[#3ac2ff] group-hover:scale-110 transition-transform">
                <Brain className="h-6 w-6" />
              </div>
              <h3 className="text-base font-bold text-[#e5e2e3]">LangGraph State Machine</h3>
              <p className="text-xs text-[#d7c3ae]/60 leading-relaxed font-body-base">
                Powered by LangGraph multi-node workflows with persistent Postgres state checkpointing, human-in-the-loop overrides, and tool calling.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="p-6 rounded-xl bg-[#111113] border border-[#27272A] hover:border-red-500/50 transition-all space-y-4 group">
              <div className="w-12 h-12 rounded-lg bg-red-500/10 border border-red-500/30 flex items-center justify-center text-red-400 group-hover:scale-110 transition-transform">
                <Activity className="h-6 w-6" />
              </div>
              <h3 className="text-base font-bold text-[#e5e2e3]">Explainable Churn Risk Scoring</h3>
              <p className="text-xs text-[#d7c3ae]/60 leading-relaxed font-body-base">
                Every customer profile gets a dynamic risk snapshot with transparent logic: purchase staleness, feedback ratings, and spending velocity drops.
              </p>
            </div>

            {/* Feature 4 */}
            <div className="p-6 rounded-xl bg-[#111113] border border-[#27272A] hover:border-[#E8A020]/50 transition-all space-y-4 group">
              <div className="w-12 h-12 rounded-lg bg-[#E8A020]/10 border border-[#E8A020]/30 flex items-center justify-center text-[#E8A020] group-hover:scale-110 transition-transform">
                <Megaphone className="h-6 w-6" />
              </div>
              <h3 className="text-base font-bold text-[#e5e2e3]">Google Gmail OAuth &amp; Resend</h3>
              <p className="text-xs text-[#d7c3ae]/60 leading-relaxed font-body-base">
                Connect your tenant Google account for native Gmail sending with automatic OAuth token refresh, or fall back to platform Resend delivery seamlessly.
              </p>
            </div>

            {/* Feature 5 */}
            <div className="p-6 rounded-xl bg-[#111113] border border-[#27272A] hover:border-emerald-500/50 transition-all space-y-4 group">
              <div className="w-12 h-12 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 group-hover:scale-110 transition-transform">
                <ShieldCheck className="h-6 w-6" />
              </div>
              <h3 className="text-base font-bold text-[#e5e2e3]">Strict SQL Mutation Guard</h3>
              <p className="text-xs text-[#d7c3ae]/60 leading-relaxed font-body-base">
                Safety first: AI agent queries are parsed and validated by SQLGuard. Any `DROP`, `DELETE`, or `UPDATE` attempts are blocked instantly.
              </p>
            </div>

            {/* Feature 6 */}
            <div className="p-6 rounded-xl bg-[#111113] border border-[#27272A] hover:border-purple-500/50 transition-all space-y-4 group">
              <div className="w-12 h-12 rounded-lg bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400 group-hover:scale-110 transition-transform">
                <Layers className="h-6 w-6" />
              </div>
              <h3 className="text-base font-bold text-[#e5e2e3]">FastMCP Tool Servers</h3>
              <p className="text-xs text-[#d7c3ae]/60 leading-relaxed font-body-base">
                Implements Anthropic&apos;s Model Context Protocol over stdio transport for clean separation of database query tools and campaign execution servers.
              </p>
            </div>

          </div>
        </div>
      </section>

      {/* Architecture Deep Dive */}
      <section id="architecture" className="relative z-10 py-20 max-w-7xl mx-auto px-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded bg-[#1c1b1c] border border-[#27272A] text-xs font-data-mono text-[#3ac2ff]">
              <Terminal className="h-3.5 w-3.5" /> Multi-Tenant Security Model
            </div>
            <h2 className="font-display-lg text-3xl md:text-4xl font-bold text-[#e5e2e3]">
              Enterprise Security &amp; Tenant Isolation Out-of-the-Box
            </h2>
            <p className="text-sm text-[#d7c3ae]/70 leading-relaxed">
              Every data row, prompt context, and MCP server process is strictly scoped by <code className="text-[#E8A020] bg-[#1c1b1c] px-1.5 py-0.5 rounded font-data-mono text-xs">org_id</code>. All external database credentials and OAuth tokens are stored using Fernet symmetric encryption.
            </p>

            <div className="space-y-3 font-data-mono text-xs">
              <div className="flex items-center gap-3 p-3 bg-[#111113] border border-[#27272A] rounded-lg">
                <Lock className="h-4 w-4 text-[#E8A020] shrink-0" />
                <span>Fernet Encrypted Database URIs &amp; OAuth Refresh Tokens</span>
              </div>
              <div className="flex items-center gap-3 p-3 bg-[#111113] border border-[#27272A] rounded-lg">
                <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Tamper-Evident Security Audit Logs for all tenant actions</span>
              </div>
              <div className="flex items-center gap-3 p-3 bg-[#111113] border border-[#27272A] rounded-lg">
                <Zap className="h-4 w-4 text-[#3ac2ff] shrink-0" />
                <span>Async Connection Pool with read-only transaction limits</span>
              </div>
            </div>
          </div>

          <div className="p-6 bg-[#0E0E10] border border-[#27272A] rounded-2xl font-data-mono text-xs text-[#e5e2e3] space-y-4">
            <div className="flex justify-between items-center border-b border-[#27272A] pb-3 text-[#d7c3ae]/40 text-[10px]">
              <span>BANDHAN_AI_ARCHITECTURE.SYS</span>
              <span>VERIFIED STACK</span>
            </div>
            <pre className="text-[11px] leading-relaxed text-[#d7c3ae]/85 overflow-x-auto p-2 bg-[#0A0A0B] rounded border border-[#27272A]">
{`[User Browser] ──(HTTPS/WSS)──> [Next.js 16 App Router]
                                       │
                                (JWT Bearer Token)
                                       ▼
                             [FastAPI Backend Server]
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 ▼                                           ▼
      [LangGraph Workflow State]                  [FastMCP Tool Server]
                 │                                           │
  (AsyncPostgresSaver Checkpoints)              (Multi-Tenant Org Scoped)
                 │                                           │
                 ▼                                           ▼
      [PostgreSQL / Supabase]                   [Resend / Gmail OAuth]`}</pre>
          </div>
        </div>
      </section>

      {/* Pricing / Packages */}
      <section id="pricing" className="relative z-10 py-20 bg-[#0E0E10] border-t border-[#27272A]/70">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center max-w-2xl mx-auto mb-16 space-y-3">
            <h2 className="font-display-lg text-3xl font-bold text-[#e5e2e3]">Flexible Platform Packages</h2>
            <p className="text-xs text-[#d7c3ae]/60">Evaluate offline with CSV datasets or connect your enterprise database infrastructure.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {/* Free */}
            <div className="p-6 rounded-xl bg-[#111113] border border-[#27272A] space-y-6 flex flex-col justify-between">
              <div className="space-y-4">
                <h3 className="text-base font-bold text-[#e5e2e3]">Developer Free</h3>
                <div className="text-2xl font-bold text-[#E8A020] font-data-mono">₹0 <span className="text-xs text-[#d7c3ae]/50 font-normal">/ forever</span></div>
                <p className="text-xs text-[#d7c3ae]/60">For exploring offline CSV analysis and basic agent chat.</p>
                <ul className="space-y-2 text-xs text-[#d7c3ae]/80">
                  <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#E8A020]" /> CSV Ingestion &amp; Mapping</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#E8A020]" /> LangGraph AI Chat Agent</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#E8A020]" /> Up to 500 records</li>
                </ul>
              </div>
              <Link href="/dashboard" className="w-full py-2.5 bg-[#27272A] hover:bg-[#353436] text-[#e5e2e3] font-bold text-xs rounded-lg text-center transition-colors">
                Start Free Workspace
              </Link>
            </div>

            {/* Growth */}
            <div className="p-6 rounded-xl bg-[#141416] border border-[#E8A020] space-y-6 flex flex-col justify-between relative overflow-hidden shadow-2xl">
              <div className="absolute right-0 top-0 bg-[#E8A020] text-[#291800] text-[8px] font-bold font-data-mono px-3 py-1 uppercase tracking-widest">
                RECOMMENDED
              </div>
              <div className="space-y-4">
                <h3 className="text-base font-bold text-[#e5e2e3]">Growth Business</h3>
                <div className="text-2xl font-bold text-[#E8A020] font-data-mono">₹2,999 <span className="text-xs text-[#d7c3ae]/50 font-normal">/ month</span></div>
                <p className="text-xs text-[#d7c3ae]/60">Connect live Supabase databases and execute automated Gmail campaigns.</p>
                <ul className="space-y-2 text-xs text-[#d7c3ae]/90">
                  <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#E8A020]" /> Live Supabase Postgres Sync</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#E8A020]" /> Explainable Churn Diagnostics</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#E8A020]" /> Connected Gmail OAuth Delivery</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#E8A020]" /> Unlimited Campaigns</li>
                </ul>
              </div>
              <Link href="/dashboard" className="w-full py-2.5 bg-[#E8A020] text-[#291800] hover:brightness-110 font-bold text-xs rounded-lg text-center transition-all">
                Launch Growth Tier
              </Link>
            </div>

            {/* Enterprise */}
            <div className="p-6 rounded-xl bg-[#111113] border border-[#27272A] space-y-6 flex flex-col justify-between">
              <div className="space-y-4">
                <h3 className="text-base font-bold text-[#e5e2e3]">Enterprise Scale</h3>
                <div className="text-2xl font-bold text-[#E8A020] font-data-mono">Custom <span className="text-xs text-[#d7c3ae]/50 font-normal">/ annual</span></div>
                <p className="text-xs text-[#d7c3ae]/60">For large scale multi-database environments with custom agent personas.</p>
                <ul className="space-y-2 text-xs text-[#d7c3ae]/80">
                  <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#E8A020]" /> Custom RLS Policies</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#E8A020]" /> Dedicated MCP Tool Server</li>
                  <li className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#E8A020]" /> Priority SLA Support</li>
                </ul>
              </div>
              <Link href="/dashboard" className="w-full py-2.5 bg-[#27272A] hover:bg-[#353436] text-[#e5e2e3] font-bold text-xs rounded-lg text-center transition-colors">
                Contact Engineering
              </Link>
            </div>

          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-[#27272A] bg-[#0A0A0B] py-12 text-xs text-[#d7c3ae]/50">
        <div className="max-w-7xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-lg bg-[#E8A020]/10 border border-[#E8A020]/30 flex items-center justify-center text-[#E8A020] font-bold text-xs">
              B
            </div>
            <span className="font-bold text-[#e5e2e3]">BandhanAI Platform</span>
            <span>— Enterprise CRM &amp; AI Analytics</span>
          </div>

          <div className="flex items-center gap-6 text-[11px]">
            <Link href="/dashboard" className="hover:text-white transition-colors">Dashboard</Link>
            <Link href="/customers" className="hover:text-white transition-colors">Customer 360</Link>
            <Link href="/campaigns" className="hover:text-white transition-colors">Campaigns</Link>
            <Link href="/settings" className="hover:text-white transition-colors">Settings</Link>
          </div>
        </div>
      </footer>

    </div>
  );
}
