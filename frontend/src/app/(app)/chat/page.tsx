"use client";

import React, { useState, useEffect, useRef } from "react";
import { useChat } from "@/hooks/use-chat";
import { useChatStore } from "@/store/chat-store";
import { useTenantStore } from "@/store/tenant-store";
import { api } from "@/lib/api";
import {
  Ban,
  CheckCircle2,
  Database,
  Edit3,
  MessageSquareText,
  Paperclip,
  Send,
  ShieldCheck,
  X,
  Plus,
  Trash2,
  Loader2,
  FolderOpen,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  Sparkles,
  Bot,
  Terminal,
  Check,
  PanelLeftClose,
  PanelLeftOpen
} from "lucide-react";
import toast from "react-hot-toast";
import { MarkdownMessage } from "@/components/chat/markdown-message";

interface ChatSession {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

function ToolCallCard({ msg }: { msg: any }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  
  const handleCopy = () => {
    const rawText = msg.args?.sql || (typeof msg.args === 'string' ? msg.args : JSON.stringify(msg.args, null, 2));
    navigator.clipboard.writeText(rawText);
    setCopied(true);
    toast.success("Query copied");
    setTimeout(() => setCopied(false), 2000);
  };
  
  return (
    <div className="flex justify-start ml-12 my-3 max-w-[85%] animate-slide-in">
      <div className="w-full bg-[#111113]/80 backdrop-blur-sm border border-[#27272A] rounded-xl overflow-hidden shadow-lg transition-all duration-300 hover:border-[#3e3e42]">
        <div 
          onClick={() => setExpanded(!expanded)}
          className="bg-[#1c1b1c]/80 px-4 py-3 flex items-center justify-between border-b border-[#27272A]/60 cursor-pointer select-none transition-colors hover:bg-[#201f20]"
        >
          <div className="flex items-center gap-3">
            <div className="w-6 h-6 rounded-lg bg-[#E8A020]/10 border border-[#E8A020]/20 flex items-center justify-center">
              <Database className="h-3.5 w-3.5 text-[#E8A020]" />
            </div>
            <span className="font-data-mono text-[10px] uppercase tracking-wider font-bold text-[#e5e2e3]">
              CRM Action: {msg.toolName}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-data-mono text-[9px] text-[#d7c3ae]/40 uppercase tracking-widest">
              {expanded ? "Hide Code" : "Show Code"}
            </span>
            {expanded ? (
              <ChevronUp className="h-4 w-4 text-[#d7c3ae]/60" />
            ) : (
              <ChevronDown className="h-4 w-4 text-[#d7c3ae]/60" />
            )}
          </div>
        </div>
        
        {expanded && msg.args && (
          <div className="p-4 bg-[#0A0A0B]/90 border-t border-[#27272A]/50">
            <div className="flex justify-between items-center mb-2">
              <span className="text-[10px] font-label-caps text-[#d7c3ae]/60 tracking-wider flex items-center gap-1.5">
                <Terminal className="h-3.5 w-3.5 text-[#6A9E6A]" /> Query Context
              </span>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  handleCopy();
                }}
                className="text-[10px] text-[#3ac2ff] hover:underline flex items-center gap-1 font-data-mono cursor-pointer"
              >
                {copied ? <Check className="h-3 w-3" /> : null}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <pre className="font-data-mono text-[11px] text-[#6A9E6A] overflow-x-auto whitespace-pre-wrap leading-relaxed bg-[#0c0c0d] p-3 rounded-lg border border-[#27272A]/40 max-h-[220px]">
              {msg.args?.sql || JSON.stringify(msg.args, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { messages, typing, activeApproval, clearMessages, setActiveApproval, setMessages } = useChatStore();
  const { agentName } = useTenantStore();

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const { sendMessage, sendApprovalResponse, isStreaming } = useChat(activeSessionId);

  const [inputVal, setInputVal] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Approval modal states
  const [isEditing, setIsEditing] = useState(false);
  const [editDataStr, setEditDataStr] = useState("");
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState("");

  const suggestions = [
    { label: "Who are my top customers?", prompt: "Who are my top customers?" },
    { label: "Draft a loyalty campaign", prompt: "Suggest a loyalty campaign structure for my high-value clients" },
    { label: "List at-risk customers", prompt: "Who are my most at-risk customers right now?" },
    { label: "Verify database schema", prompt: "Identify the columns and structure of the customer CRM database" }
  ];

  // Load list of chat sessions
  const loadSessions = async (selectFirst = false) => {
    try {
      setIsLoadingSessions(true);
      const res = await api.get("/api/chat/sessions");
      const sessionList = res.data.sessions || [];
      setSessions(sessionList);
      
      if (selectFirst && sessionList.length > 0) {
        handleSelectSession(sessionList[0].session_id);
      } else if (sessionList.length === 0) {
        // No sessions, start a new one automatically
        handleNewChat();
      }
    } catch (err: any) {
      console.error("Failed to load chat sessions:", err);
      toast.error("Failed to load chat sessions");
    } finally {
      setIsLoadingSessions(false);
    }
  };

  useEffect(() => {
    loadSessions(true);
  }, []);

  // Scroll to bottom when messages or typing changes
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typing]);

  const handleSelectSession = async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setIsLoadingMessages(true);
    try {
      const res = await api.get(`/api/chat/sessions/${sessionId}/messages`);
      const rawMsgs = res.data.messages || [];
      // Map API messages (role, content) to Store ChatMessage structure
      const formattedMsgs = rawMsgs.map((m: any) => ({
        id: m.message_id,
        type: m.role === "user" ? "user_message" : "message",
        content: m.content,
        sender: m.role === "user" ? "user" : "agent",
        timestamp: m.created_at,
        metadata: m.metadata,
      }));
      setMessages(formattedMsgs);
    } catch (err) {
      console.error("Failed to load messages:", err);
      toast.error("Failed to load chat history");
    } finally {
      setIsLoadingMessages(false);
    }
  };

  const handleNewChat = async () => {
    try {
      const res = await api.post("/api/chat/sessions", { title: "New Chat" });
      const newSession = res.data;
      setSessions((prev) => [newSession, ...prev]);
      setActiveSessionId(newSession.session_id);
      clearMessages();
    } catch (err) {
      console.error("Failed to create new session:", err);
      toast.error("Failed to start new chat");
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this conversation?")) return;
    
    try {
      await api.delete(`/api/chat/sessions/${sessionId}`);
      toast.success("Chat deleted");
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
      
      if (activeSessionId === sessionId) {
        const remaining = sessions.filter((s) => s.session_id !== sessionId);
        if (remaining.length > 0) {
          handleSelectSession(remaining[0].session_id);
        } else {
          handleNewChat();
        }
      }
    } catch (err) {
      console.error("Failed to delete session:", err);
      toast.error("Failed to delete chat");
    }
  };

  const handleSend = (e?: React.FormEvent, customVal?: string) => {
    if (e) e.preventDefault();
    const finalVal = customVal || inputVal;
    if (!finalVal.trim() || isStreaming) return;

    // Send via REST streaming
    sendMessage(finalVal);
    
    // Optimistically update session title if it was default
    const active = sessions.find((s) => s.session_id === activeSessionId);
    if (active && active.title === "New Chat") {
      setSessions((prev) =>
        prev.map((s) =>
          s.session_id === activeSessionId
            ? { ...s, title: finalVal.substring(0, 30) }
            : s
        )
      );
    }
    
    setInputVal("");
  };

  const handleApprove = () => {
    sendApprovalResponse("continue");
    setActiveApproval(null);
  };

  const handleOpenEdit = () => {
    if (activeApproval && activeApproval.data) {
      setEditDataStr(JSON.stringify(activeApproval.data.tool_call?.args || {}, null, 2));
      setIsEditing(true);
    }
  };

  const handleSaveEdit = () => {
    try {
      JSON.parse(editDataStr);
      sendApprovalResponse("update", editDataStr);
      setIsEditing(false);
      setActiveApproval(null);
    } catch {
      alert("Invalid JSON format. Please check syntax.");
    }
  };

  const handleRejectSubmit = () => {
    if (!rejectFeedback.trim()) return;
    sendApprovalResponse("feedback", rejectFeedback);
    setRejectFeedback("");
    setShowRejectForm(false);
    setActiveApproval(null);
  };

  return (
    <div className="flex h-[calc(100vh-64px)] bg-[#0A0A0B] overflow-hidden">
      
      {/* 1. Collapsible Chat History Sidebar */}
      <div 
        className={`border-r border-[#27272A]/70 bg-[#09090A]/95 transition-all duration-300 ease-in-out flex flex-col shrink-0 overflow-hidden ${
          sidebarOpen ? "w-[260px]" : "w-0 border-r-0"
        }`}
      >
        <div className="p-4 border-b border-[#27272A]/75 flex items-center justify-between">
          <span className="font-label-caps text-[10px] text-[#d7c3ae]/60 font-bold tracking-widest">
            Recent Chats
          </span>
          <button
            onClick={handleNewChat}
            className="flex items-center justify-center p-1.5 rounded-lg bg-[#E8A020] hover:brightness-110 text-[#291800] transition-all cursor-pointer"
            title="New Chat"
          >
            <Plus className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
          {isLoadingSessions ? (
            <div className="flex flex-col items-center justify-center py-8 gap-2 opacity-50">
              <Loader2 className="h-4 w-4 animate-spin text-[#E8A020]" />
              <span className="text-[9px] font-data-mono text-[#d7c3ae]">Loading...</span>
            </div>
          ) : sessions.length === 0 ? (
            <div className="text-center py-8 text-xs text-[#d7c3ae]/35 font-body-base">
              No recent conversations
            </div>
          ) : (
            sessions.map((session) => {
              const isActive = session.session_id === activeSessionId;
              return (
                <div
                  key={session.session_id}
                  onClick={() => handleSelectSession(session.session_id)}
                  className={`group relative flex items-center justify-between p-2.5 rounded-lg cursor-pointer transition-all ${
                    isActive
                      ? "bg-[#1c1b1c]/80 border border-[#27272A]"
                      : "hover:bg-[#141415] border border-transparent"
                  }`}
                >
                  <div className="flex items-center gap-2 overflow-hidden pr-6">
                    <MessageSquareText
                      className={`h-4 w-4 shrink-0 ${
                        isActive ? "text-[#E8A020]" : "text-[#d7c3ae]/40"
                      }`}
                    />
                    <span
                      className={`text-xs truncate font-body-base leading-none ${
                        isActive ? "text-[#e5e2e3] font-semibold" : "text-[#d7c3ae]/75"
                      }`}
                    >
                      {session.title}
                    </span>
                  </div>
                  <button
                    onClick={(e) => handleDeleteSession(e, session.session_id)}
                    className="absolute right-2 opacity-0 group-hover:opacity-100 text-[#ffb4ab]/60 hover:text-[#ffb4ab] p-1 rounded transition-opacity cursor-pointer"
                    title="Delete Chat"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 2. Main Chat Panel */}
      <div className="flex-1 flex flex-col bg-[#0A0A0B] relative overflow-hidden">
        
        {/* Sub Header */}
        <div className="h-12 bg-[#09090A]/90 border-b border-[#27272A]/70 flex justify-between items-center px-4 shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="p-1.5 rounded-lg hover:bg-[#1c1b1c] text-[#d7c3ae] hover:text-[#e5e2e3] transition-colors cursor-pointer"
              title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
            >
              {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}
            </button>
            <div className="h-4 w-[1px] bg-[#27272A]" />
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 bg-[#E8A020] rounded-full animate-pulse" />
              <span className="font-data-mono text-[9px] text-[#d7c3ae] uppercase font-bold tracking-wider">
                ID: {activeSessionId.substring(0, 8).toUpperCase() || "NEW"}
              </span>
            </div>
          </div>
          
          <div className="flex items-center gap-2 px-2 py-0.5 rounded-full bg-[#1c1b1c]/80 border border-[#27272A]/40">
            <Bot className="h-3.5 w-3.5 text-[#3ac2ff]" />
            <span className="font-data-mono text-[9px] text-[#3ac2ff] uppercase tracking-wider font-bold">
              {agentName}
            </span>
          </div>
        </div>

        {/* Timeline Thread View */}
        <div className="flex-grow overflow-y-auto px-6 py-8 space-y-6 w-full custom-scrollbar">
          {isLoadingMessages ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 opacity-60">
              <Loader2 className="h-7 w-7 animate-spin text-[#E8A020]" />
              <p className="font-data-mono text-xs text-[#d7c3ae]">
                Loading conversation logs...
              </p>
            </div>
          ) : messages.length === 0 ? (
            /* Welcome / Onboarding Empty State */
            <div className="flex flex-col items-center justify-center h-full max-w-2xl mx-auto text-center space-y-6 animate-fade-in">
              <div className="relative">
                <div className="w-16 h-16 rounded-2xl bg-[#E8A020]/10 border border-[#E8A020]/20 flex items-center justify-center">
                  <Bot className="h-8 w-8 text-[#E8A020] animate-bounce" />
                </div>
                <div className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-[#3ac2ff] flex items-center justify-center text-[8px] font-bold text-[#0A0A0B]">
                  AI
                </div>
              </div>
              
              <div className="space-y-2">
                <h3 className="font-display-lg text-lg font-bold text-[#e5e2e3]">
                  I am {agentName}, your CRM copilot
                </h3>
                <p className="text-sm text-[#d7c3ae]/70 font-body-base leading-relaxed">
                  I can run read-only database analysis, draft personalized outreach email segments, and configure automated loyalty campaigns.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 w-full max-w-xl pt-4">
                {suggestions.map((s, idx) => (
                  <div
                    key={idx}
                    onClick={() => handleSend(undefined, s.prompt)}
                    className="p-3 bg-[#111113]/60 hover:bg-[#1c1b1c] border border-[#27272A]/70 rounded-xl cursor-pointer transition-all duration-200 hover:scale-[1.01] hover:border-[#E8A020]/30 text-left group"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-data-mono text-[9px] text-[#E8A020]/75 uppercase font-bold tracking-wider">
                        Action Proposal
                      </span>
                      <Sparkles className="h-3 w-3 text-[#E8A020]/40 group-hover:text-[#E8A020] transition-colors" />
                    </div>
                    <p className="text-xs font-semibold text-[#e5e2e3] group-hover:text-[#ffb834] transition-colors">
                      {s.label}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            /* Messages list */
            <div className="max-w-4xl mx-auto space-y-6 w-full">
              {messages.map((msg, i) => {
                if (msg.type === "tool_call") {
                  return <ToolCallCard key={i} msg={msg} />;
                }

                const isUser = msg.sender === "user";
                return (
                  <div
                    key={i}
                    className={`flex gap-4 max-w-[85%] animate-slide-in ${
                      isUser ? "flex-row-reverse ml-auto" : ""
                    }`}
                  >
                    {/* Avatar */}
                    <div
                      className={`w-9 h-9 rounded-xl shrink-0 flex items-center justify-center font-bold text-xs shadow-md border ${
                        isUser
                          ? "bg-[#E8A020]/15 border-[#E8A020]/30 text-[#E8A020]"
                          : "bg-[#3ac2ff]/15 border-[#3ac2ff]/30 text-[#3ac2ff]"
                      }`}
                    >
                      {isUser ? "ME" : agentName.substring(0, 1).toUpperCase()}
                    </div>

                    {/* Bubble Content */}
                    <div className="space-y-1 w-full">
                      <div className={`text-[10px] font-label-caps text-[#d7c3ae]/50 ${isUser ? "text-right" : ""}`}>
                        {isUser ? "Owner" : `Agent Ralph`}
                      </div>
                      
                      <div
                        className={`p-4 rounded-2xl shadow-lg border leading-relaxed transition-all duration-300 ${
                          isUser
                            ? "bg-[#1c1b1c] border-[#27272A] border-r-4 border-r-[#E8A020] rounded-tr-sm"
                            : "bg-[#111113] border-[#27272A] border-l-4 border-l-[#3ac2ff] rounded-tl-sm"
                        }`}
                      >
                        {isUser ? (
                          <p className="whitespace-pre-line text-[#e5e2e3] text-sm font-body-base">
                            {msg.content}
                          </p>
                        ) : (
                          <MarkdownMessage content={msg.content} />
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Typing Indicator */}
          {typing && (
            <div className="flex gap-4 max-w-[85%] max-w-4xl mx-auto w-full animate-pulse">
              <div className="w-9 h-9 rounded-xl bg-[#3ac2ff]/15 border border-[#3ac2ff]/30 flex items-center justify-center text-[#3ac2ff] font-bold text-xs shrink-0 shadow-md">
                {agentName.substring(0, 1).toUpperCase()}
              </div>
              <div className="bg-[#111113] px-4 py-3 rounded-2xl border border-[#27272A] flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-[#3ac2ff] rounded-full animate-bounce delay-75" />
                <span className="w-1.5 h-1.5 bg-[#3ac2ff] rounded-full animate-bounce delay-150" />
                <span className="w-1.5 h-1.5 bg-[#3ac2ff] rounded-full animate-bounce delay-300" />
              </div>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Input Bar Form */}
        <div className="p-4 border-t border-[#27272A]/70 bg-[#0c0c0d]/90 backdrop-blur-md shrink-0">
          <form onSubmit={(e) => handleSend(e)} className="max-w-4xl mx-auto w-full">
            <div className="bg-[#111113] border border-[#27272A] rounded-xl flex items-center px-4 py-3 focus-within:border-[#E8A020] focus-within:ring-2 focus-within:ring-[#E8A020]/15 transition-all shadow-inner">
              <button
                type="button"
                className="mr-3 text-[#d7c3ae]/40 hover:text-[#E8A020] transition-colors cursor-pointer"
                aria-label="Attach file"
              >
                <Paperclip className="h-4.5 w-4.5" />
              </button>
              
              <input
                className="flex-1 bg-transparent border-none focus:ring-0 text-sm text-[#e5e2e3] placeholder-[#d7c3ae]/30 focus:outline-none"
                placeholder={isStreaming ? "Generating outreach response..." : `Ask ${agentName} a question or write a task...`}
                type="text"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                disabled={isStreaming || isLoadingMessages}
              />
              
              <button
                type="submit"
                disabled={isStreaming || !inputVal.trim() || isLoadingMessages}
                className={`p-2 rounded-xl flex items-center justify-center cursor-pointer transition-all duration-200 ${
                  isStreaming || !inputVal.trim() || isLoadingMessages
                    ? "bg-[#27272A]/40 text-[#d7c3ae]/20"
                    : "bg-[#E8A020] text-[#291800] hover:brightness-110 active:scale-[0.95] shadow-md"
                }`}
                aria-label="Send message"
              >
                {isStreaming ? (
                  <Loader2 className="h-4.5 w-4.5 animate-spin" />
                ) : (
                  <Send className="h-4.5 w-4.5" />
                )}
              </button>
            </div>
            <div className="text-[10px] text-center text-[#d7c3ae]/30 mt-2 font-data-mono tracking-wide uppercase">
              BandhanAI agent can execute campaigns. verify parameters before approval.
            </div>
          </form>
        </div>

        {/* HUMAN APPROVAL MODAL OVERLAY */}
        {activeApproval && activeApproval.data && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm px-4">
            <div className="w-full max-w-[640px] bg-[#0e0e0f] border border-[#27272A] shadow-2xl rounded-2xl overflow-hidden flex flex-col max-h-[85vh] animate-slide-in">
              
              <div className="px-6 py-4 border-b border-[#27272A] flex items-center justify-between bg-[#1c1b1c]">
                <div className="flex items-center gap-3">
                  <span className="w-2.5 h-2.5 bg-[#E8A020] rounded-full animate-ping" />
                  <h2 className="font-bold text-[#e5e2e3] font-body-base">Review Outreach Campaign Action</h2>
                </div>
                <button
                  onClick={() => setActiveApproval(null)}
                  className="text-[#d7c3ae] hover:text-[#e5e2e3] transition-colors cursor-pointer"
                  type="button"
                  aria-label="Close approval modal"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="flex-grow overflow-y-auto p-6 space-y-5 custom-scrollbar bg-[#0a0a0b]">
                <div className="flex items-center gap-2">
                  <span className="font-data-mono text-[9px] px-2 py-0.5 bg-[#E8A020]/15 text-[#E8A020] border border-[#E8A020]/25 rounded font-bold">
                    ACTION: {activeApproval.data.tool_call?.name.toUpperCase()}
                  </span>
                  <span className="font-data-mono text-[9px] px-2 py-0.5 bg-[#27272A] text-[#d7c3ae] border border-[#3e3e42]/50 rounded">
                    INTERRUPT ID: {activeApproval.interruptId?.substring(0, 8).toUpperCase()}
                  </span>
                </div>

                {isEditing ? (
                  <div className="space-y-2">
                    <label className="block font-label-caps text-label-caps text-[#d7c3ae] uppercase text-[10px]">
                      Edit Parameters payload JSON
                    </label>
                    <textarea
                      className="w-full bg-[#0c0c0d] border border-[#27272A] rounded-xl p-4 font-data-mono text-xs text-[#6A9E6A] focus:outline-none focus:border-[#E8A020] focus:ring-1 focus:ring-[#E8A020] resize-none h-[220px] shadow-inner"
                      value={editDataStr}
                      onChange={(e) => setEditDataStr(e.target.value)}
                    />
                    <div className="flex justify-end gap-2 pt-2">
                      <button
                        onClick={() => setIsEditing(false)}
                        className="px-3 py-1.5 border border-[#27272A] text-xs font-semibold rounded-lg hover:bg-[#1c1b1c] text-[#e5e2e3] cursor-pointer"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSaveEdit}
                        className="px-4 py-1.5 bg-[#E8A020] text-[#291800] text-xs font-bold rounded-lg hover:brightness-110 cursor-pointer shadow-md"
                      >
                        Save Changes
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {activeApproval.data.tool_call?.args?.subject && (
                      <div className="space-y-1">
                        <label className="block font-label-caps text-label-caps text-[#d7c3ae]/75 uppercase text-[10px] tracking-wider">
                          Outreach Subject Line
                        </label>
                        <div className="p-3 bg-[#111113] border border-[#27272A]/75 rounded-xl text-sm text-[#e5e2e3] font-semibold">
                          {activeApproval.data.tool_call.args.subject}
                        </div>
                      </div>
                    )}

                    {activeApproval.data.tool_call?.args?.body && (
                      <div className="space-y-1">
                        <label className="block font-label-caps text-label-caps text-[#d7c3ae]/75 uppercase text-[10px] tracking-wider">
                          Outreach Email HTML Preview
                        </label>
                        <div className="border border-[#27272A] rounded-xl overflow-hidden bg-[#18181B] shadow-inner">
                          <div className="h-8 bg-[#111113] border-b border-[#27272A] flex items-center px-3 gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500/50" />
                            <span className="w-1.5 h-1.5 rounded-full bg-yellow-500/50" />
                            <span className="w-1.5 h-1.5 rounded-full bg-green-500/50" />
                          </div>
                          <div className="h-[200px] overflow-y-auto p-4 bg-white text-gray-800 text-xs custom-scrollbar">
                            <div
                              dangerouslySetInnerHTML={{
                                __html: activeApproval.data.tool_call.args.body,
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    )}

                    {!activeApproval.data.tool_call?.args?.body && (
                      <div className="space-y-1">
                        <label className="block font-label-caps text-label-caps text-[#d7c3ae]/75 uppercase text-[10px] tracking-wider">
                          Proposed Action parameters
                        </label>
                        <pre className="p-4 bg-[#111113] border border-[#27272A] rounded-xl font-data-mono text-xs text-[#6A9E6A] overflow-x-auto max-h-[220px] shadow-inner leading-relaxed">
                          {JSON.stringify(activeApproval.data.tool_call?.args, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}

                {showRejectForm ? (
                  <div className="bg-[#1c1b1c]/80 p-4 border border-[#27272A] rounded-xl space-y-3 animate-in slide-in-from-top-2 duration-300">
                    <label className="block font-label-caps text-label-caps text-[#ffb4ab] uppercase text-[10px]">
                      Reason for Rejection (sent to agent feedback loop)
                    </label>
                    <textarea
                      required
                      placeholder="Comment e.g. 'Update target criteria to spend > 1000' or 'Use a friendlier tone'"
                      className="w-full bg-[#0A0A0B] border border-[#27272A] rounded-lg p-3 text-xs text-[#e5e2e3] focus:outline-none focus:border-[#ffb4ab] focus:ring-1 focus:ring-[#ffb4ab]/25 resize-none h-20"
                      value={rejectFeedback}
                      onChange={(e) => setRejectFeedback(e.target.value)}
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setShowRejectForm(false)}
                        className="px-3 py-1.5 border border-[#27272A] text-xs font-semibold text-[#d7c3ae] rounded-lg cursor-pointer hover:bg-[#111113]"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleRejectSubmit}
                        className="px-4 py-1.5 bg-red-500/20 text-[#ffb4ab] border border-red-500/40 text-xs font-bold rounded-lg hover:bg-red-500/30 cursor-pointer shadow-md"
                      >
                        Send Feedback
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex gap-3 p-3 bg-[#111113] border-l-2 border-[#E8A020] rounded-r-lg">
                    <ShieldCheck className="h-4 w-4 shrink-0 text-[#E8A020]" />
                    <p className="text-xs text-[#d7c3ae] leading-relaxed">
                      This action connects to external nodes (Gmail / Campaigns). Please inspect variables before confirming execution.
                    </p>
                  </div>
                )}
              </div>

              {!isEditing && !showRejectForm && (
                <div className="px-6 py-4 bg-[#1c1b1c] border-t border-[#27272A] flex justify-end gap-3 shrink-0">
                  <button
                    onClick={() => setShowRejectForm(true)}
                    className="px-4 py-2 border border-[#27272A] text-[#ffb4ab] font-medium hover:bg-red-500/10 transition-all rounded-lg text-xs flex items-center gap-2 cursor-pointer"
                  >
                    <Ban className="h-4 w-4" />
                    Reject Action
                  </button>
                  <button
                    onClick={handleOpenEdit}
                    className="px-4 py-2 border border-[#27272A] text-[#e5e2e3] font-medium hover:bg-[#353436] transition-all rounded-lg text-xs flex items-center gap-2 cursor-pointer"
                  >
                    <Edit3 className="h-4 w-4" />
                    Modify JSON
                  </button>
                  <button
                    onClick={handleApprove}
                    className="px-6 py-2 bg-[#E8A020] text-[#291800] font-bold hover:brightness-110 transition-all rounded-lg text-xs flex items-center gap-2 cursor-pointer shadow-md"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    Approve & Run
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
