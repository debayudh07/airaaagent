/* eslint-disable */
'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { useAccount } from 'wagmi';
import { Clock, Copy, Check, Square, ArrowUp, ChevronDown, Plus, Lock, Share2 } from 'lucide-react';
import { Mark } from '../components/Logo';
import { TIME_RANGES } from '../components/AskBox';
import DataVisualization, { type VisualizationConfig } from '../components/DataVisualization';
import Markdown from '../components/Markdown';
import Logo from '../components/Logo';
import WalletButton from '../components/WalletButton';
import ChatHistory from '../components/ChatHistory';
import { useAuth } from '../components/AuthProvider';
import { useVault } from '../components/useVault';
import { LiveActivity, ActivitySummary } from '../components/AgentActivity';
import { API_BASE, streamResearch, type AgentEvent, type ChartSpec, type ToolProgress } from '../../lib/api';
import { apiFetch } from '../../lib/auth';
import { sealFile, shareConversation, text as vaultText } from '../../lib/vault';
import { splitAnswer } from '../../lib/answer';
import AgentCharts from '../components/AgentCharts';
import jsPDF from 'jspdf';
import * as XLSX from 'xlsx';



interface ResearchResult {
  success: boolean;
  data?: any;
  result?: any; // Backend returns formatted AI response in 'result' field
  error?: string;
  timestamp?: string;
  query?: string;
  address?: string;
  time_range?: string;
  session_id?: string; // Session ID for conversation tracking
  reasoning_steps?: string[];
  citations?: Array<{
    source: string;
    timestamp: string;
    query_context: string;
  }>;
  data_sources_used?: string[];
  execution_time?: number;
  query_intent?: string;
  merged_data?: any; // Structured data from backend
  data_quality_score?: number;
  tool_results?: any[];
  tool_trace?: Array<{ tool: string; success: boolean; duration_ms?: number; error?: string | null }>;
  planner?: string;
  charts?: ChartSpec[];
  personalization?: { memories?: number; watchlist?: number; snapshots?: number; documents?: number };
  knowledge_sources?: Array<{ title: string; url: string }>;
}

const SUGGESTIONS = [
  { tag: 'DeFi', text: 'Which DEXs lead on Arbitrum today, and how are their fees?', tone: 'bg-sky text-[#1e3a8a]' },
  { tag: 'Yields', text: 'Best stablecoin yields right now?', tone: 'bg-mint text-[#0f5b3a]' },
  { tag: 'Charts', text: 'Chart ETH vs SOL over the last 30 days', tone: 'bg-butter text-[#6b4e00]' },
  { tag: 'News', text: 'Why is the crypto market moving today?', tone: 'bg-peach text-[#8a3412]' },
];

interface LiveRun {
  stage: string;
  step: number;
  planner?: string;
  rationale?: string;
  tools: ToolProgress[];
  draft: string;
  charts: ChartSpec[];
}

type ChatRole = 'user' | 'assistant' | 'system';

interface ChatMessage {
  id: string;
  role: ChatRole;
  text?: string;
  timestamp: string;
  result?: ResearchResult; // When assistant returns structured data
}

interface ConversationHistory {
  success: boolean;
  session_id: string;
  messages: Array<{
    type: 'human' | 'ai';
    content: string;
    timestamp: string;
    research_data?: ResearchResult; // Research data for AI messages
  }>;
  message_count: number;
  created_at: string;
  last_activity: string;
}

const STAGE_STEP: Record<string, number> = { planning: 0, gathering: 1, synthesizing: 3 };

const SECONDARY_BTN =
  'inline-flex min-h-11 sm:min-h-10 items-center justify-center gap-1.5 rounded-full bg-field px-4 text-sm font-semibold text-ink transition-[background-color,transform] hover:bg-field-hover active:scale-95 touch-manipulation';

export default function MainChat() {
  const { address: connectedAddress } = useAccount();
  const auth = useAuth();
  const vault = useVault();
  const [notice, setNotice] = useState<{ ok: boolean; text: string; href?: string } | null>(null);
  const lastAuthStatus = useRef(auth.status);
  const [query, setQuery] = useState('');
  const [address, setAddress] = useState('');
  const [timeRange, setTimeRange] = useState('7d');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isOnline, setIsOnline] = useState<boolean | null>(null);
  const [live, setLive] = useState<LiveRun | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const pendingAsk = useRef<string | null>(null);
  const [openActivity, setOpenActivity] = useState<Record<string, boolean>>({});
  const endOfChatRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const hasConversation = messages.length > 0;
  const [vizConfigs, setVizConfigs] = useState<Record<string, VisualizationConfig>>({});
  const [openViz, setOpenViz] = useState<Record<string, boolean>>({});

  // Check API health on component mount
  useEffect(() => {
    checkApiHealth();

    // Arriving from the home ask box or a pin: open the chat and ask straight away
    const params = new URLSearchParams(window.location.search);
    const q = params.get('q')?.trim();
    if (q) {
      const range = params.get('range');
      if (range && TIME_RANGES.some(([v]) => v === range)) setTimeRange(range);
      window.history.replaceState(null, '', '/main-chat');
      persistSession(newSessionId());
      setMessages([]);
      pendingAsk.current = q;
    } else {
      initializeSession();
    }
  }, []);

  // Send the question carried in the URL once the session id is in state
  useEffect(() => {
    if (pendingAsk.current && sessionId) {
      const q = pendingAsk.current;
      pendingAsk.current = null;
      handleSend(q);
    }
  }, [sessionId]);

  // Signing in: the conversation in use becomes the wallet's. Signing out: wallet conversations are private, so start fresh.
  useEffect(() => {
    const previous = lastAuthStatus.current;
    lastAuthStatus.current = auth.status;
    if (auth.status === 'signed-in' && previous !== 'signed-in' && sessionId) {
      apiFetch('/api/conversations/claim', { method: 'POST', body: JSON.stringify({ session_id: sessionId }) }).catch(() => undefined);
    }
    if (auth.status === 'guest' && previous === 'signed-in') {
      persistSession(newSessionId());
      setMessages([]);
    }
  }, [auth.status]);

  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(null), 7000);
    return () => clearTimeout(id);
  }, [notice]);

  // Sync connected wallet address
  useEffect(() => {
    setAddress(connectedAddress ?? '');
  }, [connectedAddress]);

  // Auto-scroll to the newest message
  useEffect(() => {
    endOfChatRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, loading]);

  // Grow the composer with its content, up to max-height
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [query]);

  // Initialize or restore session
  const initializeSession = () => {
    let storedSessionId: string | null = null;
    try {
      storedSessionId = localStorage.getItem('airaa-session-id');
    } catch {
      /* storage unavailable */
    }
    if (storedSessionId) {
      setSessionId(storedSessionId);
      loadConversationHistory(storedSessionId);
    } else {
      persistSession(newSessionId());
    }
  };

  const newSessionId = () => `web-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;

  const persistSession = (id: string) => {
    setSessionId(id);
    try {
      localStorage.setItem('airaa-session-id', id);
    } catch {
      /* storage unavailable */
    }
  };

  // Restore an earlier conversation from the backend
  const loadConversationHistory = async (id: string) => {
    try {
      const response = await apiFetch(`/api/conversation/${id}`);
      if (!response.ok) return; // 404 means a new session
      const history: ConversationHistory = await response.json();
      if (!history.messages?.length) return;

      setMessages(history.messages.map((msg, index) => {
        const base = { id: `restored-${id}-${index}`, timestamp: msg.timestamp };
        if (msg.type === 'human') return { ...base, role: 'user' as ChatRole, text: msg.content };

        const result: ResearchResult | undefined = msg.research_data
          ? { ...msg.research_data, timestamp: msg.timestamp, session_id: id }
          : undefined;
        // Greetings carry no research data, so render them as plain chat
        const isGreeting = !!result && result.success && result.query_intent === 'greeting' &&
          (!result.data_sources_used || result.data_sources_used.length === 0);
        return { ...base, role: 'assistant' as ChatRole, text: msg.content, result: isGreeting ? undefined : result };
      }));
    } catch (error) {
      console.warn('Could not load conversation history:', error);
    }
  };

  const checkApiHealth = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/health`);
      const data = await response.json();
      setIsOnline(data.status === 'ok');
    } catch (error) {
      setIsOnline(false);
    }
  };

  // Start new conversation session
  const startNewSession = () => {
    abortRef.current?.abort();
    persistSession(newSessionId());
    setMessages([]);
    setOpenViz({});
    inputRef.current?.focus();
  };

  const stopGenerating = () => abortRef.current?.abort();

  const openConversation = (id: string) => {
    abortRef.current?.abort();
    persistSession(id);
    setMessages([]);
    setOpenViz({});
    loadConversationHistory(id);
  };

  const saveToVault = async (m: ChatMessage) => {
    const question = [...messages].reverse().find((x) => x.role === 'user' && x.timestamp <= m.timestamp)?.text ?? 'Research answer';
    try {
      if (!vault.unlocked) {
        setNotice({ ok: true, text: 'Confirm in your wallet to unlock the vault…' });
        await vault.unlockWithWallet();
      }
      const slug = question.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'answer';
      await sealFile(vaultText.encode(`# ${question}\n\n${m.text ?? ''}\n`), { title: question.slice(0, 80), name: `${slug}.md`, mime: 'text/markdown' });
      setNotice({ ok: true, text: 'Saved to your encrypted vault.', href: '/vault' });
    } catch (e: any) {
      const msg = String(e?.message ?? e);
      setNotice(/no signature key|has no|not initialized|Not found/i.test(msg)
        ? { ok: false, text: 'Set up your vault first.', href: '/vault' }
        : { ok: false, text: msg.length > 160 ? `${msg.slice(0, 160)}…` : msg, href: '/vault' });
    }
  };

  const shareChat = async () => {
    if (!sessionId) return;
    try {
      await apiFetch('/api/conversations/claim', { method: 'POST', body: JSON.stringify({ session_id: sessionId }) }).catch(() => undefined);
      const url = await shareConversation(sessionId, true);
      try { await navigator.clipboard.writeText(url); } catch { /* clipboard blocked: the notice still shows the outcome */ }
      setNotice({ ok: true, text: 'Link copied. Anyone with it can read this chat (the underlying data is hidden). Manage links in your vault.', href: '/vault' });
    } catch (e: any) {
      setNotice({ ok: false, text: String(e?.message ?? e) });
    }
  };

  const copyMessage = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId((cur) => (cur === id ? null : cur)), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  const handleSend = async (override?: string) => {
    const trimmed = (override ?? query).trim();
    if (!trimmed || loading) return;

    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      text: trimmed,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMessage]);
    setQuery('');

    setLoading(true);
    setLive({ stage: 'Starting…', step: 0, tools: [], draft: '', charts: [] });
    const controller = new AbortController();
    abortRef.current = controller;

    let finalResult: any = null;
    let streamError: string | null = null;

    const onEvent = (event: AgentEvent) => {
      switch (event.type) {
        case 'status':
          setLive(prev => prev && { ...prev, stage: event.message, step: STAGE_STEP[event.stage] ?? prev.step });
          break;
        case 'plan':
          setLive(prev => prev && {
            ...prev,
            planner: event.planner,
            rationale: event.rationale,
            stage: 'Gathering data',
            tools: event.tools.map(tool => ({ tool, status: 'running' as const })),
          });
          break;
        case 'tool_end':
          setLive(prev => prev && {
            ...prev,
            tools: prev.tools.map(t => t.tool === event.tool
              ? { tool: t.tool, status: event.success ? 'done' as const : 'failed' as const, duration_ms: event.duration_ms, error: event.error }
              : t),
          });
          break;
        case 'chart':
          setLive(prev => prev && { ...prev, charts: [...prev.charts, event.chart] });
          break;
        case 'followup':
          setLive(prev => prev && { ...prev, step: 2, stage: 'Filling gaps in the data' });
          break;
        case 'tool_start':
          setLive(prev => prev && (prev.tools.some(t => t.tool === event.tool)
            ? prev
            : { ...prev, tools: [...prev.tools, { tool: event.tool, status: 'running' as const }] }));
          break;
        case 'token':
          setLive(prev => prev && { ...prev, draft: prev.draft + event.text });
          break;
        case 'result':
          finalResult = event.result;
          break;
        case 'error':
          streamError = event.error;
          break;
      }
    };

    try {
      await streamResearch(
        {
          query: trimmed,
          address: address.trim() || undefined,
          time_range: timeRange,
          session_id: sessionId,
        },
        onEvent,
        controller.signal,
      );

      if (!finalResult) throw new Error(streamError || 'The agent ended without returning a result');

      const data = finalResult;

      if (data.session_id && data.session_id !== sessionId) persistSession(data.session_id);

      const normalized: ResearchResult = {
        ...data,
        data: data.result || data.data,
        timestamp: new Date().toISOString(),
        query: trimmed,
        address: address || undefined,
        time_range: timeRange,
        session_id: data.session_id || sessionId,
      };

      // Greetings carry no research data, so render them as plain chat
      const isGreeting = normalized.success &&
                        normalized.query_intent === 'greeting' &&
                        (!normalized.data_sources_used || normalized.data_sources_used.length === 0);

      setMessages(prev => [...prev, {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: normalized.success
          ? (normalized.result || normalized.data || 'Research completed successfully.')
          : 'There was an issue completing the research.',
        timestamp: new Date().toISOString(),
        result: isGreeting ? undefined : normalized,
      }]);
      setIsOnline(true);
    } catch (error: any) {
      const aborted = error?.name === 'AbortError';
      const message = aborted
        ? 'Stopped. Ask again whenever you are ready.'
        : `Could not complete the request: ${error?.message || 'unknown error'}`;
      setMessages(prev => [...prev, {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: message,
        timestamp: new Date().toISOString(),
        result: aborted ? undefined : {
          success: false,
          error: message,
          timestamp: new Date().toISOString(),
          query: trimmed,
        },
      }]);
      if (!aborted) setIsOnline(false);
    } finally {
      abortRef.current = null;
      setLive(null);
      setLoading(false);
    }
  };

  const downloadResult = (res: ResearchResult, format: 'json' | 'excel' | 'pdf') => {
    if (!res) return;

    const timestamp = new Date().toISOString().split('T')[0];
    const filename = `airaa-research-${timestamp}`;

    if (format === 'json') {
      const content = JSON.stringify(res, null, 2);
      const blob = new Blob([content], { type: 'application/json' });
      downloadBlob(blob, `${filename}.json`);
    } else if (format === 'excel') {
      downloadExcel(res, filename);
    } else if (format === 'pdf') {
      downloadPDF(res, filename);
    }
  };

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const downloadExcel = (res: ResearchResult, filename: string) => {
    const workbook = XLSX.utils.book_new();

    // AI Response sheet - Main formatted response
    const aiResponseData = [{
      'AI Analysis': res.result || res.data || 'No analysis available'
    }];
    const aiResponseSheet = XLSX.utils.json_to_sheet(aiResponseData);
    XLSX.utils.book_append_sheet(workbook, aiResponseSheet, 'AI Analysis');

    // Structured data sheet (if available)
    if (res.merged_data) {
      try {
        const flatData = flattenObjectForExcel(res.merged_data);
        if (Object.keys(flatData).length > 0) {
          const structuredSheet = XLSX.utils.json_to_sheet([flatData]);
          XLSX.utils.book_append_sheet(workbook, structuredSheet, 'Structured Data');
        }
      } catch (error) {
        console.warn('Could not process structured data for Excel:', error);
      }
    }

    // Raw data sheet (if different from merged_data)
    if (res.data && res.data !== res.merged_data) {
      try {
        const rawFlatData = flattenObjectForExcel(res.data);
        if (Object.keys(rawFlatData).length > 0) {
          const rawDataSheet = XLSX.utils.json_to_sheet([rawFlatData]);
          XLSX.utils.book_append_sheet(workbook, rawDataSheet, 'Raw Data');
        }
      } catch (error) {
        console.warn('Could not process raw data for Excel:', error);
      }
    }

    // Metadata sheet
    const metadata = {
      Query: res.query || '',
      Address: res.address || '',
      'Time Range': res.time_range || '',
      Timestamp: res.timestamp || '',
      'Execution Time': res.execution_time ? `${res.execution_time}ms` : '',
      'Data Quality Score': res.data_quality_score || '',
      'Query Intent': res.query_intent || ''
    };
    const metadataSheet = XLSX.utils.json_to_sheet([metadata]);
    XLSX.utils.book_append_sheet(workbook, metadataSheet, 'Metadata');

    // Reasoning steps sheet
    if (res.reasoning_steps && res.reasoning_steps.length > 0) {
      const reasoningData = res.reasoning_steps.map((step, index) => ({
        Step: index + 1,
        Description: step
      }));
      const reasoningSheet = XLSX.utils.json_to_sheet(reasoningData);
      XLSX.utils.book_append_sheet(workbook, reasoningSheet, 'Reasoning Steps');
    }

    // Citations sheet
    if (res.citations && res.citations.length > 0) {
      const citationsSheet = XLSX.utils.json_to_sheet(res.citations);
      XLSX.utils.book_append_sheet(workbook, citationsSheet, 'Citations');
    }

    // Data sources sheet
    if (res.data_sources_used && res.data_sources_used.length > 0) {
      const sourcesData = res.data_sources_used.map((source, index) => ({
        Index: index + 1,
        'Data Source': source
      }));
      const sourcesSheet = XLSX.utils.json_to_sheet(sourcesData);
      XLSX.utils.book_append_sheet(workbook, sourcesSheet, 'Data Sources');
    }

    XLSX.writeFile(workbook, `${filename}.xlsx`);
  };

  const downloadPDF = async (res: ResearchResult, filename: string) => {
    const pdf = new jsPDF();
    const pageWidth = pdf.internal.pageSize.getWidth();
    const margin = 20;
    let yPosition = margin;

    // Helper function to add text with word wrap
    const addText = (text: string, fontSize = 12, fontStyle: 'normal' | 'bold' = 'normal') => {
      if (!text) return;

      pdf.setFontSize(fontSize);
      pdf.setFont('helvetica', fontStyle);
      const lines = pdf.splitTextToSize(text.toString(), pageWidth - 2 * margin);
      pdf.text(lines, margin, yPosition);
      yPosition += lines.length * (fontSize * 0.4) + 5;

      // Check if we need a new page
      if (yPosition > pdf.internal.pageSize.getHeight() - margin) {
        pdf.addPage();
        yPosition = margin;
      }
    };

    // Title
    addText('AIRAA Research Report', 20, 'bold');
    yPosition += 10;

    // Metadata
    addText('Query Details', 16, 'bold');
    addText(`Query: ${res.query || 'N/A'}`);
    addText(`Address: ${res.address || 'N/A'}`);
    addText(`Time Range: ${res.time_range || 'N/A'}`);
    addText(`Timestamp: ${res.timestamp || 'N/A'}`);
    if (res.execution_time) addText(`Execution Time: ${res.execution_time}ms`);
    if (res.data_quality_score) addText(`Data Quality Score: ${res.data_quality_score}%`);
    if (res.query_intent) addText(`Query Intent: ${res.query_intent}`);
    yPosition += 10;

    // Main AI Analysis
    const aiResponse = res.result || res.data;
    if (aiResponse) {
      addText('AI Analysis & Insights', 16, 'bold');

      // Handle both string and object responses
      if (typeof aiResponse === 'string') {
        addText(aiResponse, 11);
      } else if (typeof aiResponse === 'object') {
        addText(JSON.stringify(aiResponse, null, 2), 10);
      }
      yPosition += 10;
    }

    // Reasoning Steps
    if (res.reasoning_steps && res.reasoning_steps.length > 0) {
      addText('Reasoning Steps', 16, 'bold');
      res.reasoning_steps.forEach((step, index) => {
        addText(`${index + 1}. ${step}`, 11);
      });
      yPosition += 10;
    }

    // Data Sources Used
    if (res.data_sources_used && res.data_sources_used.length > 0) {
      addText('Data Sources Used', 16, 'bold');
      res.data_sources_used.forEach((source, index) => {
        addText(`${index + 1}. ${source.replace('_', ' ').toUpperCase()}`, 11);
      });
      yPosition += 10;
    }

    // Citations
    if (res.citations && res.citations.length > 0) {
      addText('Citations & References', 16, 'bold');
      res.citations.forEach((citation, index) => {
        addText(`${index + 1}. ${citation.source} (${citation.timestamp})`, 11);
        if (citation.query_context) {
          addText(`   Context: ${citation.query_context}`, 10);
        }
      });
      yPosition += 10;
    }

    // Structured Data Summary (if available)
    if (res.merged_data) {
      try {
        addText('Structured Data Summary', 16, 'bold');
        const flatData = flattenObjectForExcel(res.merged_data);
        const dataEntries = Object.entries(flatData).slice(0, 20); // Limit to first 20 entries

        if (dataEntries.length > 0) {
          dataEntries.forEach(([key, value]) => {
            const displayKey = key.replace(/_/g, ' ').replace(/([A-Z])/g, ' $1').trim();
            const displayValue = Array.isArray(value) ? value.join(', ') : String(value);
            addText(`${displayKey}: ${displayValue.slice(0, 100)}${displayValue.length > 100 ? '...' : ''}`, 10);
          });

          if (Object.keys(flatData).length > 20) {
            addText('... and more data available in structured format', 10);
          }
        }
      } catch (error) {
        console.warn('Could not process structured data for PDF:', error);
        addText('Structured data available but could not be processed for PDF format.', 10);
      }
    }

    pdf.save(`${filename}.pdf`);
  };

  const flattenObjectForExcel = (obj: any, prefix = ''): Record<string, any> => {
    let flattened: Record<string, any> = {};

    for (const key in obj) {
      if (obj.hasOwnProperty(key)) {
        const newKey = prefix ? `${prefix}_${key}` : key;

        if (typeof obj[key] === 'object' && obj[key] !== null && !Array.isArray(obj[key])) {
          Object.assign(flattened, flattenObjectForExcel(obj[key], newKey));
        } else if (Array.isArray(obj[key])) {
          flattened[newKey] = obj[key].join('; ');
        } else {
          flattened[newKey] = obj[key];
        }
      }
    }

    return flattened;
  };

  const AssistantRow = ({ children, meta }: { children: React.ReactNode; meta?: React.ReactNode }) => (
    <div className="flex items-start gap-3 sm:gap-3.5">
      <span className="hidden sm:block"><Mark size={36} /></span>
      <span className="sm:hidden"><Mark size={30} /></span>
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="flex min-h-9 flex-wrap items-center gap-2">
          <span className="font-bold">airaa</span>
          {meta}
        </div>
        {children}
      </div>
    </div>
  );

  const renderAssistant = (m: ChatMessage) => {
    const res = m.result;
    const failed = !!res && !res.success;
    const canExport = !!res && res.success && !!(res.data || res.result || res.merged_data);
    const hasStructured = !!res?.success && !!res.merged_data && typeof res.merged_data === 'object' && Object.keys(res.merged_data).length > 0;
    const hasActivity = !!res?.success && !!(res.tool_trace?.length || res.reasoning_steps?.length);
    const parts = m.text && !failed ? splitAnswer(m.text) : null;
    const sources = res?.data_sources_used?.length ?? 0;

    const meta = res?.success ? (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-[#e3f5ec] px-2.5 py-1 text-xs font-semibold text-[#075e3a]">
        <Check className="h-3 w-3" strokeWidth={3} aria-hidden="true" />
        {res.execution_time != null ? `Answered in ${Number(res.execution_time).toFixed(1)}s` : 'Answered'}
        {sources > 0 && <span className="hidden sm:inline"> · {sources} {sources === 1 ? 'source' : 'sources'}</span>}
      </span>
    ) : undefined;

    return (
      <AssistantRow meta={meta}>
        {res?.success && <AgentCharts charts={res.charts} />}

        {failed ? (
          <div className="rounded-[22px] bg-[#ffe4e1] px-[18px] py-3.5 text-sm text-[#a3231a]" role="alert">{m.text}</div>
        ) : parts && (
          <div>
            <Markdown>{parts.body}</Markdown>
            {parts.footer.length > 0 && (
              <div className="mt-4 text-[13px] text-muted">
                {parts.footer.map((line) => <p key={line} className="m-0">{line}</p>)}
              </div>
            )}
            {res?.knowledge_sources && res.knowledge_sources.length > 0 && (
              <p className="m-0 mt-3 text-[13px] text-muted">
                Docs used:{' '}
                {res.knowledge_sources.map((k, i) => (
                  <span key={k.url}>{i > 0 && ', '}<a href={k.url} target="_blank" rel="noopener noreferrer" className="font-semibold text-ink-3 underline">{k.title}</a></span>
                ))}
              </p>
            )}
            {res?.personalization && Object.values(res.personalization).some((n) => (n ?? 0) > 0) && (
              <p className="m-0 mt-1 text-[13px] text-muted">
                Personalised with {[
                  res.personalization.memories ? `${res.personalization.memories} saved ${res.personalization.memories === 1 ? 'note' : 'notes'}` : '',
                  res.personalization.watchlist ? 'your watchlist' : '',
                  res.personalization.snapshots ? 'your portfolio snapshot' : '',
                ].filter(Boolean).join(', ') || 'what I know about you'}. <Link href="/memory" className="font-semibold text-ink-3 underline">Manage</Link>
              </p>
            )}
          </div>
        )}

        {canExport && (
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => copyMessage(m.id, m.text!)} className={SECONDARY_BTN}>
              {copiedId === m.id ? <Check className="h-3.5 w-3.5 text-up" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
              {copiedId === m.id ? 'Copied' : 'Copy'}
            </button>
            <button type="button" onClick={() => downloadResult(res!, 'pdf')} className={SECONDARY_BTN}>Export PDF</button>
            <button type="button" onClick={() => downloadResult(res!, 'excel')} className={`${SECONDARY_BTN} hidden sm:inline-flex`}>Excel</button>
            <button type="button" onClick={() => downloadResult(res!, 'json')} className={SECONDARY_BTN}>JSON</button>
            {auth.status === 'signed-in' && (
              <button type="button" onClick={() => saveToVault(m)} className={SECONDARY_BTN} title="Encrypt this answer in your browser and save it to your vault">
                <Lock className="h-3.5 w-3.5" aria-hidden="true" />Save to vault
              </button>
            )}
            {hasStructured && (
              <button
                type="button"
                onClick={() => setOpenViz(prev => ({ ...prev, [m.id]: !prev[m.id] }))}
                aria-expanded={!!openViz[m.id]}
                className={`${SECONDARY_BTN} hidden sm:inline-flex`}
              >
                Explore the data
              </button>
            )}
            {hasActivity && (
              <button
                type="button"
                onClick={() => setOpenActivity(prev => ({ ...prev, [m.id]: !prev[m.id] }))}
                aria-expanded={!!openActivity[m.id]}
                className={SECONDARY_BTN}
              >
                How I got here
                <ChevronDown className={`h-4 w-4 transition-transform ${openActivity[m.id] ? 'rotate-180' : ''}`} aria-hidden="true" />
              </button>
            )}
          </div>
        )}

        {res?.success && (
          <ActivitySummary
            open={!!openActivity[m.id]}
            trace={res.tool_trace}
            steps={res.reasoning_steps}
            seconds={res.execution_time}
            planner={res.planner}
          />
        )}

        {hasStructured && openViz[m.id] && (
          <div className="hidden rounded-3xl bg-ink p-3 text-white sm:block">
            <DataVisualization
              data={res!.merged_data}
              title="Research Data"
              config={vizConfigs[m.id]}
              onConfigChange={(cfg) => setVizConfigs(prev => ({ ...prev, [m.id]: cfg }))}
            />
          </div>
        )}

        {parts && parts.next.length > 0 && (
          <div className="grid gap-2.5 sm:grid-cols-3">
            {parts.next.slice(0, 3).map((q, i) => (
              <button
                key={q}
                type="button"
                onClick={() => handleSend(q)}
                disabled={loading}
                className={`pin rounded-[20px] px-[18px] py-4 text-left disabled:opacity-50 touch-manipulation ${['bg-ink text-white', 'bg-butter text-ink', 'bg-sky text-ink'][i]}`}
              >
                <span className={`block text-xs font-bold ${['text-[#ff8a5c]', 'text-[#6b4e00]', 'text-[#1e3a8a]'][i]}`}>Ask next</span>
                <span className="mt-1.5 block font-display text-[17px] font-bold leading-[1.2]">{q}</span>
              </button>
            ))}
          </div>
        )}
      </AssistantRow>
    );
  };

  const statusLabel = isOnline === null ? 'Connecting' : isOnline ? 'Online' : 'Offline';
  const title = messages.find((m) => m.role === 'user')?.text;

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-bg text-[15px] leading-[1.55] text-ink">
      {notice && (
        <div role="status" className={`fixed bottom-28 left-1/2 z-30 flex max-w-[min(32rem,calc(100vw-1.5rem))] -translate-x-1/2 items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold shadow-xl ${notice.ok ? 'bg-ink text-white' : 'bg-[#ffe4e1] text-[#a3231a]'}`}>
          <span>{notice.text}</span>
          {notice.href && <Link href={notice.href} className="shrink-0 underline">Open vault</Link>}
          <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss" className="shrink-0 opacity-70 hover:opacity-100">✕</button>
        </div>
      )}
      <header className="shrink-0 border-b border-line-2">
        <div className="mx-auto flex max-w-[1360px] items-center gap-3 px-3 py-2 sm:gap-3.5 sm:px-6 sm:py-3">
          <Logo />
          <span className="hidden h-[22px] w-px bg-line sm:block" />
          <span className="hidden min-w-0 truncate font-semibold text-ink-3 sm:block">{title ?? 'New chat'}</span>
          <span className="inline-flex items-center gap-1.5 text-xs text-muted" title={`Agent ${statusLabel.toLowerCase()}`}>
            <span className={`h-[7px] w-[7px] rounded-full ${isOnline ? 'bg-up' : isOnline === false ? 'bg-down' : 'bg-[#d5d7dd]'}`} />
            <span className="sr-only">{statusLabel}</span>
          </span>
          <div className="ml-auto flex items-center gap-2">
            {auth.status === 'signed-in' && <ChatHistory activeId={sessionId} onSelect={openConversation} />}
            {auth.status === 'signed-in' && hasConversation && (
              <button
                type="button"
                onClick={shareChat}
                className="inline-flex h-11 w-11 items-center justify-center gap-1.5 rounded-full bg-field text-sm font-semibold text-ink transition-colors hover:bg-field-hover sm:w-auto sm:px-4 touch-manipulation"
                aria-label="Share this chat"
              >
                <Share2 className="h-[18px] w-[18px] sm:h-4 sm:w-4" aria-hidden="true" />
                <span className="hidden sm:inline">Share</span>
              </button>
            )}
            {hasConversation && (
              <button
                type="button"
                onClick={startNewSession}
                className="inline-flex h-11 w-11 items-center justify-center gap-1.5 rounded-full bg-field text-sm font-semibold text-ink transition-colors hover:bg-field-hover sm:w-auto sm:px-4 touch-manipulation"
                aria-label="New chat"
              >
                <Plus className="h-[18px] w-[18px] sm:h-4 sm:w-4" aria-hidden="true" />
                <span className="hidden sm:inline">New chat</span>
              </button>
            )}
            <WalletButton />
          </div>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto" id="chat-scroll">
        {!hasConversation && !loading ? (
          <div className="mx-auto flex max-w-[780px] flex-col gap-7 px-4 pb-6 pt-10 sm:px-6 sm:pt-[72px]">
            <div className="anim-rise">
              <h1 className="m-0 font-display text-[30px] font-extrabold leading-tight tracking-[-1px] sm:text-[40px]">What do you want to research?</h1>
              <p className="mt-2.5 max-w-[560px] text-muted">
                Prices, DeFi metrics, news, links and wallets. Every answer shows its sources, and charts come from the fetched numbers.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {SUGGESTIONS.map((s, i) => (
                <button
                  key={s.text}
                  type="button"
                  onClick={() => handleSend(s.text)}
                  className={`pin anim-rise flex min-w-0 flex-col gap-1.5 rounded-3xl px-5 py-[18px] text-left touch-manipulation ${s.tone}`}
                  style={{ animationDelay: `${(i + 1) * 70}ms` }}
                >
                  <span className="text-xs font-bold uppercase tracking-[0.6px]">{s.tag}</span>
                  <span className="font-display text-xl font-bold leading-[1.15] tracking-[-0.3px] text-ink">{s.text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto flex max-w-[780px] flex-col gap-7 px-3 py-6 sm:px-6 sm:py-8" aria-live="polite">
            {messages.map((m) => m.role === 'user' ? (
              <div key={m.id} className="anim-rise max-w-[85%] self-end whitespace-pre-wrap rounded-[24px_24px_6px_24px] bg-ink px-[18px] py-3 text-base text-white sm:max-w-[80%]">
                {m.text}
              </div>
            ) : (
              <div key={m.id} className="anim-rise">{renderAssistant(m)}</div>
            ))}

            {loading && live && (
              <AssistantRow>
                <LiveActivity stage={live.stage} step={live.step} planner={live.planner} rationale={live.rationale} tools={live.tools} />
                {live.charts.length > 0 ? <AgentCharts charts={live.charts} /> : live.step >= 1 && (
                  <div className="shimmer-tint h-[200px] rounded-3xl bg-mint" aria-label="Waiting for data" />
                )}
                {live.draft && <Markdown streaming>{live.draft}</Markdown>}
              </AssistantRow>
            )}

            <div ref={endOfChatRef} />
          </div>
        )}
      </main>

      <footer className="anim-dock shrink-0 bg-gradient-to-t from-white from-70% to-transparent">
        <form
          className="mx-auto max-w-[780px] px-3 pb-3.5 pt-2 sm:px-6 sm:pb-[18px]"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <div className="askbox flex items-center gap-2 rounded-[30px] border border-[#dcdde2] bg-white py-1.5 pl-[18px] pr-1.5 sm:gap-2.5 sm:pl-[22px]">
            <label htmlFor="composer" className="sr-only">Message airaa</label>
            <textarea
              id="composer"
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={1}
              placeholder={hasConversation ? 'Ask a follow-up' : 'Ask about a token, protocol, wallet, link or market'}
              className="max-h-40 min-h-11 min-w-0 flex-1 resize-none border-0 bg-transparent py-[11px] text-base text-ink placeholder:text-muted focus:outline-none sm:text-[17px]"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />
            <label className="hidden min-h-9 items-center gap-1.5 rounded-full bg-field px-3 text-[13px] font-semibold text-ink-3 sm:inline-flex">
              <Clock className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="sr-only">Time range</span>
              <select value={timeRange} onChange={(e) => setTimeRange(e.target.value)} className="cursor-pointer border-0 bg-transparent font-semibold focus:outline-none">
                {TIME_RANGES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            {loading ? (
              <button
                type="button"
                onClick={stopGenerating}
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#ffe4e1] text-[#a3231a] transition-transform active:scale-90 touch-manipulation"
                aria-label="Stop"
                title="Stop"
              >
                <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!query.trim()}
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-ink text-white transition-[transform,background-color,color] hover:bg-accent hover:text-ink active:scale-90 disabled:cursor-not-allowed disabled:bg-field disabled:text-muted touch-manipulation"
                aria-label="Send"
                title="Send (Enter)"
              >
                <ArrowUp className="h-5 w-5" strokeWidth={2.4} aria-hidden="true" />
              </button>
            )}
          </div>
          <p className="mt-2 text-center text-xs text-muted">
            {address ? <span className="tabular">Wallet {address.slice(0, 6)}…{address.slice(-4)} · </span> : null}
            AI-generated research, not financial advice.
          </p>
        </form>
      </footer>
    </div>
  );
}
