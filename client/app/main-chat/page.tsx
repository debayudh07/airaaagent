/* eslint-disable */
'use client';

import { useState, useRef, useEffect } from 'react';
import { useAccount } from 'wagmi';
import { Clock, Copy, Check, Square, ArrowUp, ChevronDown, Plus } from 'lucide-react';
import DataVisualization, { type VisualizationConfig } from '../components/DataVisualization';
import Markdown from '../components/Markdown';
import Logo from '../components/Logo';
import WalletButton from '../components/WalletButton';
import { LiveActivity, ActivitySummary } from '../components/AgentActivity';
import { API_BASE, streamResearch, type AgentEvent, type ChartSpec, type ToolProgress } from '../../lib/api';
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
}

const SUGGESTIONS = [
  { tag: 'DeFi', text: 'Which DEXs lead on Arbitrum today, and how are their fees?' },
  { tag: 'Yields', text: 'Best stablecoin yields right now?' },
  { tag: 'Charts', text: 'Chart ETH vs SOL over the last 30 days' },
  { tag: 'News', text: 'Why is the crypto market moving today?' },
];

const TIME_RANGES = [
  ['1d', '24 hours'],
  ['7d', '7 days'],
  ['30d', '30 days'],
  ['90d', '90 days'],
  ['1y', '1 year'],
] as const;

interface LiveRun {
  stage: string;
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

const SECONDARY_BTN =
  'inline-flex min-h-11 sm:min-h-10 items-center justify-center gap-1.5 rounded-[10px] border border-line-strong bg-transparent px-3 text-[13px] text-ink-3 transition-colors hover:border-white/30 hover:text-ink touch-manipulation';

export default function MainChat() {
  const { address: connectedAddress } = useAccount();
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
  const endOfChatRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const hasConversation = messages.length > 0;
  const [vizConfigs, setVizConfigs] = useState<Record<string, VisualizationConfig>>({});
  const [openViz, setOpenViz] = useState<Record<string, boolean>>({});

  // Check API health on component mount
  useEffect(() => {
    checkApiHealth();
    initializeSession();
  }, []);

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
      const response = await fetch(`${API_BASE}/api/conversation/${id}`);
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
    setLive({ stage: 'Starting…', tools: [], draft: '', charts: [] });
    const controller = new AbortController();
    abortRef.current = controller;

    let finalResult: any = null;
    let streamError: string | null = null;

    const onEvent = (event: AgentEvent) => {
      switch (event.type) {
        case 'status':
          setLive(prev => prev && { ...prev, stage: event.message });
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

  const renderAssistant = (m: ChatMessage) => {
    const res = m.result;
    const failed = !!res && !res.success;
    const canExport = !!res && res.success && !!(res.data || res.result || res.merged_data);
    const hasStructured = !!res?.success && !!res.merged_data && typeof res.merged_data === 'object' && Object.keys(res.merged_data).length > 0;
    const parts = m.text && !failed ? splitAnswer(m.text) : null;

    return (
      <article className="flex flex-col gap-4">
        {res?.success && <AgentCharts charts={res.charts} />}

        {failed ? (
          <div className="rounded-xl border border-red-400/30 bg-red-500/[0.08] px-3.5 py-3 text-sm text-red-200" role="alert">
            {m.text}
          </div>
        ) : parts && (
          <div>
            <Markdown>{parts.body}</Markdown>
            {parts.next.length > 0 && (
              <>
                <h3 className="mb-2 mt-[22px] font-display text-base font-semibold text-ink sm:text-[17px]">Next questions</h3>
                <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                  {parts.next.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => handleSend(q)}
                      disabled={loading}
                      className="min-h-11 rounded-xl border border-line-strong bg-transparent px-3.5 text-left text-sm text-ink-3 transition-colors hover:border-accent/50 hover:bg-accent/[0.06] hover:text-ink disabled:opacity-50 sm:min-h-10 sm:rounded-full touch-manipulation"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </>
            )}
            {parts.footer.length > 0 && (
              <div className="mt-5 border-t border-white/[0.08] pt-3 text-xs italic text-muted sm:text-[13px]">
                {parts.footer.map((line) => <p key={line} className="m-0">{line}</p>)}
              </div>
            )}
          </div>
        )}

        {res?.success && (
          <ActivitySummary trace={res.tool_trace} steps={res.reasoning_steps} seconds={res.execution_time} planner={res.planner} />
        )}

        {(canExport || (!res && m.text)) && (
          <div className="flex gap-2 sm:flex-wrap">
            {hasStructured && (
              <button
                type="button"
                onClick={() => setOpenViz(prev => ({ ...prev, [m.id]: !prev[m.id] }))}
                aria-expanded={!!openViz[m.id]}
                className={`${SECONDARY_BTN} hidden sm:inline-flex`}
              >
                Explore the data
                <ChevronDown className={`h-3.5 w-3.5 transition-transform ${openViz[m.id] ? 'rotate-180' : ''}`} aria-hidden="true" />
              </button>
            )}
            {m.text && (
              <button type="button" onClick={() => copyMessage(m.id, m.text!)} className={`${SECONDARY_BTN} flex-1 sm:flex-none`}>
                {copiedId === m.id ? <Check className="h-3.5 w-3.5 text-ok" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
                {copiedId === m.id ? 'Copied' : 'Copy'}
              </button>
            )}
            {canExport && (
              <>
                <button type="button" onClick={() => downloadResult(res!, 'pdf')} className={`${SECONDARY_BTN} flex-1 sm:flex-none`}>
                  <span className="sm:hidden">PDF</span><span className="hidden sm:inline">Export PDF</span>
                </button>
                <button type="button" onClick={() => downloadResult(res!, 'excel')} className={`${SECONDARY_BTN} hidden sm:inline-flex`}>Excel</button>
                <button type="button" onClick={() => downloadResult(res!, 'json')} className={`${SECONDARY_BTN} flex-1 sm:flex-none`}>
                  <span className="sm:hidden">Data</span><span className="hidden sm:inline">JSON</span>
                </button>
              </>
            )}
          </div>
        )}

        {hasStructured && openViz[m.id] && (
          <div className="hidden rounded-xl border border-line bg-black/20 p-2 sm:block sm:p-3">
            <DataVisualization
              data={res!.merged_data}
              title="Research Data"
              config={vizConfigs[m.id]}
              onConfigChange={(cfg) => setVizConfigs(prev => ({ ...prev, [m.id]: cfg }))}
            />
          </div>
        )}
      </article>
    );
  };

  const statusLabel = isOnline === null ? 'Connecting' : isOnline ? 'Online' : 'Offline';

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-bg text-[15px] leading-[1.6] text-ink">
      {/* Header */}
      <header className="shrink-0 border-b border-white/[0.07]">
        <div className="mx-auto flex h-14 w-full max-w-[820px] items-center gap-3 px-4 sm:h-[60px]">
          <Logo />
          <span className="inline-flex items-center gap-1.5 text-xs text-subtle" title={`Agent ${statusLabel.toLowerCase()}`}>
            <span className={`h-[7px] w-[7px] rounded-full ${isOnline ? 'bg-ok' : isOnline === false ? 'bg-danger' : 'bg-white/25'}`} />
            <span className="hidden sm:inline">{statusLabel}</span>
            <span className="sr-only sm:hidden">{statusLabel}</span>
          </span>
          <div className="ml-auto flex items-center gap-2">
            {hasConversation && (
              <button
                type="button"
                onClick={startNewSession}
                className="inline-flex h-11 w-11 items-center justify-center rounded-[10px] border border-line-strong text-sm font-medium text-ink-3 transition-colors hover:border-white/30 hover:text-ink sm:h-auto sm:min-h-10 sm:w-auto sm:px-3 touch-manipulation"
                aria-label="New chat"
              >
                <Plus className="h-[18px] w-[18px] sm:hidden" aria-hidden="true" />
                <span className="hidden sm:inline">New chat</span>
              </button>
            )}
            <WalletButton />
          </div>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-y-auto" id="chat-scroll">
        {!hasConversation && !loading ? (
          <div className="mx-auto flex max-w-[820px] flex-col gap-7 px-4 pb-6 pt-10 sm:pt-[72px]">
            <div>
              <h1 className="m-0 font-display text-[28px] font-semibold leading-tight tracking-[-0.6px] sm:text-[34px]">
                What do you want to research?
              </h1>
              <p className="mt-2.5 max-w-[560px] text-muted">
                Prices, DeFi metrics, news, links and wallets. Every answer shows its sources, and charts come from the fetched numbers.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.text}
                  type="button"
                  onClick={() => handleSend(s.text)}
                  className="flex min-w-0 flex-col gap-1.5 rounded-[14px] border border-white/10 bg-surface px-[18px] py-4 text-left text-ink transition-colors hover:border-accent/40 hover:bg-[#101a2b] touch-manipulation"
                >
                  <span className="text-xs font-medium text-accent">{s.tag}</span>
                  <span className="font-medium">{s.text}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto flex max-w-[820px] flex-col gap-[22px] px-4 py-[18px] sm:py-7" aria-live="polite">
            {messages.map((m) => m.role === 'user' ? (
              <div key={m.id} className="max-w-[88%] self-end whitespace-pre-wrap rounded-[16px_16px_4px_16px] bg-accent/[0.12] px-3.5 py-2.5 sm:max-w-[85%] sm:px-4">
                {m.text}
              </div>
            ) : (
              <div key={m.id}>{renderAssistant(m)}</div>
            ))}

            {loading && live && (
              <div className="flex flex-col gap-4 sm:gap-[22px]">
                <LiveActivity stage={live.stage} planner={live.planner} rationale={live.rationale} tools={live.tools} />
                <AgentCharts charts={live.charts} />
                {live.draft && <Markdown streaming>{live.draft}</Markdown>}
              </div>
            )}

            <div ref={endOfChatRef} />
          </div>
        )}
      </main>

      {/* Composer */}
      <footer className="shrink-0">
        <form
          className="mx-auto max-w-[820px] px-3 pb-3.5 pt-2 sm:px-4 sm:pb-4"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <div
            className={`rounded-2xl border bg-surface p-1.5 pl-3 transition-colors focus-within:border-accent/45 sm:rounded-[18px] sm:p-2.5 sm:pb-2 ${
              hasConversation ? 'border-white/[0.12]' : 'border-accent/35'
            }`}
          >
            <div className="flex items-end gap-2 sm:block">
              <label htmlFor="composer" className="sr-only">Your question</label>
              <textarea
                id="composer"
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                rows={hasConversation ? 1 : 2}
                placeholder={hasConversation ? 'Ask a follow-up…' : 'Ask about a token, protocol, wallet, link or market…'}
                className="max-h-40 min-h-11 w-full flex-1 resize-none border-0 bg-transparent py-2.5 text-base text-ink placeholder:text-subtle focus:outline-none sm:px-2 sm:py-1.5"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
              />
              <div className="sm:hidden">{renderSendButton()}</div>
            </div>
            <div className="hidden items-center gap-2 sm:flex">
              <label className="inline-flex min-h-9 items-center gap-1.5 rounded-[9px] bg-white/[0.05] px-2.5 text-[13px] text-muted">
                <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                <select
                  value={timeRange}
                  onChange={(e) => setTimeRange(e.target.value)}
                  className="cursor-pointer border-0 bg-transparent text-ink-3 focus:outline-none"
                  aria-label="Time range"
                >
                  {TIME_RANGES.map(([value, label]) => (
                    <option key={value} className="bg-surface" value={value}>{label}</option>
                  ))}
                </select>
              </label>
              {!loading && (address ? (
                <span className="inline-flex items-center gap-1.5 font-mono text-xs text-subtle" title={address}>
                  <span className="h-1.5 w-1.5 rounded-full bg-ok/70" />
                  {address.slice(0, 6)}…{address.slice(-4)}
                </span>
              ) : (
                <span className="text-xs text-subtle">Connect a wallet for on-chain questions</span>
              ))}
              <div className="ml-auto">{renderSendButton()}</div>
            </div>
          </div>
          <p className="mt-2 hidden text-center text-xs text-subtle sm:block">AI-generated research, not financial advice.</p>
        </form>
      </footer>
    </div>
  );

  function renderSendButton() {
    return loading ? (
      <button
        type="button"
        onClick={stopGenerating}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-red-400/45 bg-red-400/[0.12] text-red-300 transition-colors hover:bg-red-400/20 touch-manipulation"
        aria-label="Stop"
        title="Stop"
      >
        <Square className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
      </button>
    ) : (
      <button
        type="submit"
        disabled={!query.trim()}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent text-on-accent transition-colors hover:bg-accent-hover active:scale-95 disabled:cursor-not-allowed disabled:bg-white/[0.08] disabled:text-subtle touch-manipulation"
        aria-label="Send"
        title="Send (Enter)"
      >
        <ArrowUp className="h-5 w-5" strokeWidth={2.4} aria-hidden="true" />
      </button>
    );
  }
}
