/* eslint-disable */
'use client';

import { useState, useRef, useEffect } from 'react';
import { ConnectButton } from '@rainbow-me/rainbowkit';
import { useAccount } from 'wagmi';
import { FileDown, FileSpreadsheet, FileText, Clock, Copy, Check, Square, ArrowUp, ChevronDown, Sparkles, Plus } from 'lucide-react';
import DataVisualization, { type VisualizationConfig } from '../components/DataVisualization';
import Markdown from '../components/Markdown';
import { LiveActivity, ActivitySummary } from '../components/AgentActivity';
import { API_BASE, streamResearch, type AgentEvent, type ChartSpec, type ToolProgress } from '../../lib/api';
import AgentCharts from '../components/AgentCharts';
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';
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
  'Chart ETH vs SOL over the last 30 days',
  'Why is the crypto market moving today?',
  'Best stablecoin yields right now',
  'Aave TVL history and fees',
];

interface LiveRun {
  stage: string;
  planner?: string;
  rationale?: string;
  tools: ToolProgress[];
  draft: string;
  charts: ChartSpec[];
}

interface ApiStats {
  totalQueries: number;
  successfulQueries: number;
  avgResponseTime: number;
  isOnline: boolean;
}

type ChatRole = 'user' | 'assistant' | 'system';

interface ChatMessage {
  id: string;
  role: ChatRole;
  text?: string;
  timestamp: string;
  result?: ResearchResult; // When assistant returns structured data
}

interface ConversationSession {
  session_id: string;
  message_count: number;
  created_at: string;
  last_activity: string;
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

export default function MainChat() {
  const { address: connectedAddress, isConnected } = useAccount();
  const [query, setQuery] = useState('');
  const [address, setAddress] = useState('');
  const [timeRange, setTimeRange] = useState('7d');
  const [loading, setLoading] = useState(false);
  
  // Session management state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [conversationHistory, setConversationHistory] = useState<ConversationHistory | null>(null);
  const [showSessionInfo, setShowSessionInfo] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: 'Hi! I\'m your AIRAA Research Agent. I have conversation memory - I\'ll remember our previous discussions! Ask me anything about Web3, DeFi, or on-chain analytics.',
      timestamp: new Date().toISOString(),
    },
  ]);
  const [apiStats, setApiStats] = useState<ApiStats>({
    totalQueries: 0,
    successfulQueries: 0,
    avgResponseTime: 0,
    isOnline: false,
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [live, setLive] = useState<LiveRun | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endOfChatRef = useRef<HTMLDivElement>(null);
  const hasUserMessage = messages.some((m) => m.role === 'user');
  const [vizConfigs, setVizConfigs] = useState<Record<string, VisualizationConfig>>({});
  const [openViz, setOpenViz] = useState<Record<string, boolean>>({});

  const latestAssistantMsg = messages
    .slice()
    .reverse()
    .find(m => m.role === 'assistant' && m.result && m.result.success && m.result.data);





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
    endOfChatRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Initialize or restore session
  const initializeSession = () => {
    // Check if there's a session in localStorage
    const storedSessionId = localStorage.getItem('airaa-session-id');
    if (storedSessionId) {
      console.log(`Restoring session: ${storedSessionId}`);
      setSessionId(storedSessionId);
      // Load conversation history with a small delay to ensure state is set
      setTimeout(() => loadConversationHistory(storedSessionId, false, true), 500);
    } else {
      // Generate new session ID
      const newSessionId = `web-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      console.log(`Creating new session: ${newSessionId}`);
      setSessionId(newSessionId);
      localStorage.setItem('airaa-session-id', newSessionId);
    }
  };

  // Load conversation history from backend
  const loadConversationHistory = async (sessionId: string, showLoading: boolean = true, replaceMessages: boolean = true) => {
    if (showLoading) setLoadingHistory(true);
    
    try {
      const response = await fetch(`${API_BASE}/api/conversation/${sessionId}`);
      if (response.ok) {
        const history: ConversationHistory = await response.json();
        setConversationHistory(history);
        
        // Only replace messages if explicitly requested (e.g., on initial load)
        if (replaceMessages && history.messages && history.messages.length > 0) {
          // Keep the welcome message and add restored conversation
          const restoredMessages: ChatMessage[] = history.messages.map((msg, index) => {
            if (msg.type === 'human') {
              return {
                id: `restored-${sessionId}-${index}`,
                role: 'user' as ChatRole,
                text: msg.content,
                timestamp: msg.timestamp,
              };
            } else {
              // For AI messages, use research_data if available, otherwise treat as greeting
              let aiText = msg.content;
              let result: ResearchResult | undefined = undefined;

              if (msg.research_data) {
                // Use the stored research data to recreate the full result
                result = {
                  ...msg.research_data,
                  timestamp: msg.timestamp,
                  session_id: sessionId
                };
                
                // Check if this is a greeting response (no API calls, greeting intent)
                const isGreeting = result.success && 
                                  result.query_intent === 'greeting' && 
                                  (!result.data_sources_used || result.data_sources_used.length === 0);
                
                if (!isGreeting) {
                  aiText = 'Here are the insights I found. You can explore the visualization below or download the data.';
                }
              } else {
                // No research data available - this is likely a greeting or simple response
                result = undefined;
              }

              return {
                id: `restored-${sessionId}-${index}`,
                role: 'assistant' as ChatRole,
                text: aiText,
                timestamp: msg.timestamp,
                result: result
              };
            }
          });
          
          // Replace messages with welcome + restored conversation
          setMessages([
            {
              id: 'welcome-restored',
              role: 'assistant',
              text: `Hi! I\'m your AIRAA Research Agent. I found our previous conversation with ${Math.floor(history.messages.length / 2)} exchanges. I have conversation memory - I\'ll remember our previous discussions! Ask me anything about Web3, DeFi, or on-chain analytics.`,
              timestamp: new Date().toISOString(),
            },
            ...restoredMessages
          ]);
          
          console.log(`Restored ${history.messages.length} messages from session ${sessionId}`);
          console.log('Restored messages:', restoredMessages.map(m => ({ role: m.role, text: m.text?.slice(0, 50) + '...' })));
        } else if (replaceMessages && (!history.messages || history.messages.length === 0)) {
          // No previous messages, just update welcome message
          setMessages([{
            id: 'welcome',
            role: 'assistant',
            text: 'Hi! I\'m your AIRAA Research Agent. I have conversation memory - I\'ll remember our previous discussions! Ask me anything about Web3, DeFi, or on-chain analytics.',
            timestamp: new Date().toISOString(),
          }]);
        }
      } else if (response.status === 404) {
        // Session not found, that's okay for new sessions
        console.log(`Session ${sessionId} not found - this is a new session`);
      }
    } catch (error) {
      console.warn('Could not load conversation history:', error);
    } finally {
      if (showLoading) setLoadingHistory(false);
    }
  };

  const checkApiHealth = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/health`);
      const data = await response.json();
      setApiStats(prev => ({ ...prev, isOnline: data.status === 'ok' }));
    } catch (error) {
      setApiStats(prev => ({ ...prev, isOnline: false }));
    }
  };

  // Start new conversation session
  const startNewSession = () => {
    const newSessionId = `web-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    setSessionId(newSessionId);
    localStorage.setItem('airaa-session-id', newSessionId);
    setConversationHistory(null);
    
    // Clear current conversation (keep only welcome message)
    setMessages([{
      id: 'welcome',
      role: 'assistant',
      text: 'Hi! I\'m your AIRAA Research Agent. I have conversation memory - I\'ll remember our previous discussions! Ask me anything about Web3, DeFi, or on-chain analytics.',
      timestamp: new Date().toISOString(),
    }]);
  };

  // Refresh conversation history
  const refreshConversationHistory = (showLoading: boolean = true, replaceMessages: boolean = false) => {
    if (sessionId) {
      loadConversationHistory(sessionId, showLoading, replaceMessages);
    }
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
    const startTime = Date.now();
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
      const responseTime = Date.now() - startTime;

      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id);
        localStorage.setItem('airaa-session-id', data.session_id);
      }

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

      setApiStats(prev => ({
        totalQueries: prev.totalQueries + 1,
        successfulQueries: prev.successfulQueries + (data.success ? 1 : 0),
        avgResponseTime:
          (prev.avgResponseTime * prev.totalQueries + responseTime) /
          (prev.totalQueries + 1),
        isOnline: true,
      }));

      // Refresh session metadata only; messages are already on screen
      if (data.success && sessionId) {
        setTimeout(() => {
          fetch(`${API_BASE}/api/conversation/${sessionId}`)
            .then(response => response.json())
            .then((history: ConversationHistory) => setConversationHistory(history))
            .catch(error => console.warn('Could not update conversation history:', error));
        }, 1000);
      }
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
      if (!aborted) setApiStats(prev => ({ ...prev, isOnline: false }));
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

  const flattenObject = (obj: any, prefix = ''): Record<string, any> => {
    let flattened: Record<string, any> = {};
    
    for (const key in obj) {
      if (obj.hasOwnProperty(key)) {
        const newKey = prefix ? `${prefix}.${key}` : key;
        
        if (typeof obj[key] === 'object' && obj[key] !== null && !Array.isArray(obj[key])) {
          Object.assign(flattened, flattenObject(obj[key], newKey));
        } else {
          flattened[newKey] = obj[key];
        }
      }
    }
    
    return flattened;
  };



  // Removed URL query parameter handling

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-[#070b14] text-white"
      style={{ backgroundImage: 'radial-gradient(60rem 30rem at 50% -10%, rgba(14,165,233,0.12), transparent 60%)' }}>
      {/* Header */}
      <header className="shrink-0 border-b border-white/[0.07] bg-[#070b14]/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 w-full max-w-3xl items-center gap-3 px-3 sm:px-4">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-400/15 text-cyan-300">
              <Sparkles className="h-4 w-4" />
            </span>
            <h1 className="text-base font-semibold tracking-tight">AIRAA</h1>
            <span
              className={`h-1.5 w-1.5 rounded-full ${apiStats.isOnline ? 'bg-emerald-400' : 'bg-white/25'}`}
              title={apiStats.isOnline ? 'Agent online' : 'Agent offline'}
            />
          </div>
          <div className="ml-auto flex items-center gap-2">
            {hasUserMessage && (
              <button
                onClick={startNewSession}
                className="flex items-center gap-1.5 rounded-lg border border-white/15 px-2.5 py-1.5 text-xs text-white/70 transition hover:border-white/40 hover:text-white touch-manipulation"
                title="Start a new conversation"
              >
                <Plus className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">New chat</span>
              </button>
            )}
            <ConnectButton showBalance={false} chainStatus="icon" accountStatus={{ smallScreen: 'avatar', largeScreen: 'address' }} />
          </div>
        </div>
      </header>

      <main className="mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col px-3 sm:px-4">
          {/* Messages */}
          <div
            className="min-h-0 flex-1 space-y-5 overflow-y-auto py-4 pr-1"
            id="chat-scroll"
            aria-live="polite"
          >
            {messages.map((m) => {
              const isUser = m.role === 'user';
              const res = m.result;
              const canExport = !!res && res.success && !!(res.data || res.result || res.merged_data);
              const hasStructured = !!res?.success && !!res.merged_data && typeof res.merged_data === 'object' && Object.keys(res.merged_data).length > 0;

              return (
                <div key={m.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`group relative ${
                      isUser
                        ? 'max-w-[85%] rounded-2xl rounded-br-md bg-cyan-400/[0.12] px-4 py-2.5'
                        : 'w-full'
                    }`}
                  >
                    {!isUser && m.text && (
                      <button
                        onClick={() => copyMessage(m.id, m.text!)}
                        className="absolute -top-1 right-0 rounded p-1 text-white/35 transition hover:bg-white/10 hover:text-white sm:opacity-0 sm:group-hover:opacity-100 focus:opacity-100"
                        aria-label="Copy answer"
                        title="Copy answer"
                      >
                        {copiedId === m.id ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                      </button>
                    )}

                    {m.text && (isUser
                      ? <div className="whitespace-pre-wrap leading-relaxed text-sm sm:text-[15px]">{m.text}</div>
                      : res && !res.success
                        ? <div className="text-sm text-red-200">{m.text}</div>
                        : <Markdown>{m.text}</Markdown>
                    )}

                    {res && (
                      <div className="mt-3 space-y-3">
                        {!res.success && res.error && (
                          <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl border border-red-400/30 bg-red-900/10 p-3 text-xs text-red-300">{res.error}</pre>
                        )}

                        {res.success && <AgentCharts charts={res.charts} />}

                        {res.success && (
                          <ActivitySummary
                            trace={res.tool_trace}
                            steps={res.reasoning_steps}
                            sources={res.data_sources_used}
                            seconds={res.execution_time}
                            planner={res.planner}
                          />
                        )}

                        {hasStructured && (
                          <div className="rounded-xl border border-white/10 bg-black/20">
                            <button
                              onClick={() => setOpenViz(prev => ({ ...prev, [m.id]: !prev[m.id] }))}
                              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-white/60 hover:text-white/80"
                              aria-expanded={!!openViz[m.id]}
                            >
                              <span className="font-medium text-white/80">Explore the data</span>
                              <span>· tables, charts, raw JSON</span>
                              <ChevronDown className={`ml-auto h-4 w-4 transition-transform ${openViz[m.id] ? 'rotate-180' : ''}`} />
                            </button>
                            {openViz[m.id] && (
                              <div className="border-t border-white/10 p-2 sm:p-3">
                                <DataVisualization
                                  data={res.merged_data}
                                  title="Research Data"
                                  config={vizConfigs[m.id]}
                                  onConfigChange={(cfg) => setVizConfigs(prev => ({ ...prev, [m.id]: cfg }))}
                                />
                              </div>
                            )}
                          </div>
                        )}

                        {canExport && (
                          <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                            {([
                              ['json', 'JSON', FileDown],
                              ['excel', 'Excel', FileSpreadsheet],
                              ['pdf', 'PDF', FileText],
                            ] as const).map(([fmt, label, Icon]) => (
                              <button
                                key={fmt}
                                onClick={() => downloadResult(res, fmt)}
                                className="flex items-center gap-1.5 rounded-lg border border-white/20 px-2.5 py-1.5 text-xs text-white/70 transition-colors hover:border-white/50 hover:text-white touch-manipulation"
                              >
                                <Icon className="h-3.5 w-3.5" />
                                {label}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {!hasUserMessage && !loading && (
              <div className="pt-2">
                <div className="mb-2 flex items-center gap-1.5 text-xs text-white/50">
                  <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
                  Try asking
                </div>
                <div className="flex flex-wrap gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => handleSend(s)}
                      className="rounded-full border border-white/20 bg-white/[0.04] px-3 py-1.5 text-xs sm:text-sm text-white/75 transition-colors hover:border-cyan-300/50 hover:bg-cyan-300/10 hover:text-white touch-manipulation"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {loading && live && (
              <div className="flex justify-start">
                <div className="w-full space-y-3">
                  <LiveActivity stage={live.stage} planner={live.planner} rationale={live.rationale} tools={live.tools} />
                  <AgentCharts charts={live.charts} />
                  {live.draft && <Markdown>{live.draft}</Markdown>}
                </div>
              </div>
            )}

            <div ref={endOfChatRef} />
          </div>

          {/* Composer */}
          <div className="shrink-0 pb-3 pt-2 sm:pb-4">
            <div className="rounded-2xl border border-white/[0.12] bg-white/[0.05] p-2 transition-colors focus-within:border-cyan-300/40 focus-within:bg-white/[0.07]">
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                rows={1}
                placeholder="Ask about a token, protocol, wallet or market…"
                aria-label="Message"
                className="max-h-40 min-h-[2.5rem] w-full resize-none bg-transparent px-2 py-1.5 text-sm text-white placeholder-white/35 focus:outline-none sm:text-base"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
              />
              <div className="flex items-center gap-2 pt-1">
                <label className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-white/55 transition hover:bg-white/[0.06] hover:text-white/80">
                  <Clock className="h-3.5 w-3.5" />
                  <select
                    value={timeRange}
                    onChange={(e) => setTimeRange(e.target.value)}
                    className="cursor-pointer bg-transparent focus:outline-none"
                    aria-label="Time range"
                  >
                    <option className="bg-slate-900" value="1d">24 hours</option>
                    <option className="bg-slate-900" value="7d">7 days</option>
                    <option className="bg-slate-900" value="30d">30 days</option>
                    <option className="bg-slate-900" value="90d">90 days</option>
                    <option className="bg-slate-900" value="1y">1 year</option>
                  </select>
                </label>
                {!address && (
                  <span className="hidden text-[11px] text-white/35 sm:inline">Connect a wallet for on-chain analysis</span>
                )}
                {address && (
                  <span className="hidden items-center gap-1.5 rounded-lg px-2 py-1 font-mono text-[11px] text-white/40 sm:flex" title={address}>
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/70" />
                    {address.slice(0, 6)}…{address.slice(-4)}
                  </span>
                )}
                {loading ? (
                  <button
                    onClick={stopGenerating}
                    className="ml-auto flex h-9 w-9 items-center justify-center rounded-xl border border-red-400/40 bg-red-500/10 text-red-200 transition hover:bg-red-500/20 touch-manipulation"
                    aria-label="Stop"
                    title="Stop"
                  >
                    <Square className="h-4 w-4 fill-current" />
                  </button>
                ) : (
                  <button
                    onClick={() => handleSend()}
                    disabled={!query.trim()}
                    className="ml-auto flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-400 text-slate-900 transition hover:bg-cyan-300 active:scale-95 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-white/30 touch-manipulation"
                    aria-label="Send"
                    title="Send (Enter)"
                  >
                    <ArrowUp className="h-5 w-5" />
                  </button>
                )}
              </div>
            </div>
            <div className="mt-1.5 text-center text-[11px] text-white/30">
              AI-generated research, not financial advice
            </div>
          </div>
      </main>
    </div>
  );
}
