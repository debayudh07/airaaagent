/* eslint-disable */
'use client';

import { useState, useRef, useEffect } from 'react';
import { ConnectButton } from '@rainbow-me/rainbowkit';
import { useAccount } from 'wagmi';
import { FileDown, FileSpreadsheet, FileText, Lock, CheckCircle, Settings, Eye, EyeOff, MessageSquare, Clock, Users } from 'lucide-react';
import DataVisualization, { type VisualizationConfig } from '../components/DataVisualization';
import LoadingSpinner from '../components/LoadingSpinner';
import { WavyBackground } from '../../components/ui/wavy-background';
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
  const endOfChatRef = useRef<HTMLDivElement>(null);
  const hasUserMessage = messages.some((m) => m.role === 'user');
  const [vizConfigs, setVizConfigs] = useState<Record<string, VisualizationConfig>>({});

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
    if (connectedAddress) {
      setAddress(connectedAddress);
    }
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
      const response = await fetch(`https://airaaagent.onrender.com/api/conversation/${sessionId}`);
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
              // For AI messages, show the actual content directly without result wrapper
              return {
                id: `restored-${sessionId}-${index}`,
                role: 'assistant' as ChatRole,
                text: msg.content,
                timestamp: msg.timestamp,
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
      const response = await fetch('https://airaaagent.onrender.com/api/health');
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

  const handleSend = async () => {
    const trimmed = query.trim();
    if (!trimmed) return;

    // Push user message
    const userMessage: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      text: trimmed,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMessage]);
    setQuery('');

    setLoading(true);
    const startTime = Date.now();

    try {
      const response = await fetch('https://airaaagent.onrender.com/api/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: trimmed,
          address: address.trim() || undefined,
          time_range: timeRange,
          session_id: sessionId,
        }),
      });

      const data = await response.json();
      const responseTime = Date.now() - startTime;

      // Update session ID if returned from backend
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

      const assistantMessage: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: normalized.success
          ? 'Here are the insights I found. You can explore the visualization below or download the data.'
          : `There was an issue completing the research.`,
        timestamp: new Date().toISOString(),
        result: normalized,
      };

      // Add the new message to the existing messages (don't reload history)
      setMessages(prev => [...prev, assistantMessage]);

      setApiStats(prev => ({
        totalQueries: prev.totalQueries + 1,
        successfulQueries: prev.successfulQueries + (data.success ? 1 : 0),
        avgResponseTime:
          (prev.avgResponseTime * prev.totalQueries + responseTime) /
          (prev.totalQueries + 1),
        isOnline: true,
      }));

      // Update conversation history stats but don't reload messages (to avoid overwriting new responses)
      if (data.success && sessionId) {
        setTimeout(() => {
          // Only update the conversation history metadata, not the messages
          fetch(`https://airaaagent.onrender.com/api/conversation/${sessionId}`)
            .then(response => response.json())
            .then((history: ConversationHistory) => {
              setConversationHistory(history);
            })
            .catch(error => console.warn('Could not update conversation history:', error));
        }, 1000);
      }
    } catch (error: any) {
      const assistantErrorMessage: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        text: `Network error: ${error?.message || 'Unknown error'}`,
        timestamp: new Date().toISOString(),
        result: {
        success: false,
        error: `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        timestamp: new Date().toISOString(),
          query: trimmed,
        },
      };
      setMessages(prev => [...prev, assistantErrorMessage]);
      setApiStats(prev => ({ ...prev, isOnline: false }));
    } finally {
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
    <div className="relative min-h-screen bg-[#0a0f1a] text-white overflow-x-hidden">
      <WavyBackground
        containerClassName="absolute inset-0 z-0"
        backgroundFill="#0a0f1a"
        colors={["#0B1220", "#0F172A", "#1E293B", "#1D4ED8", "#0EA5E9"]}
        waveWidth={80}
        blur={6}
        speed="slow"
        waveOpacity={0.8}
      />
      {/* Header with Connect Button */}
      <header className="relative z-20 max-w-5xl mx-auto px-3 sm:px-4 pt-4 sm:pt-6 md:pt-8 pb-3 sm:pb-4">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 sm:gap-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-4 w-full sm:w-auto">
            <h1 className="text-xl sm:text-2xl md:text-3xl lg:text-4xl font-bold bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent leading-tight">
              AIRAA Research Agent
            </h1>
            {sessionId && (
              <button
                onClick={() => setShowSessionInfo(!showSessionInfo)}
                className="text-xs sm:text-sm px-2.5 sm:px-3 py-1 sm:py-1.5 rounded-full border border-white/30 hover:border-white/50 flex items-center gap-1.5 sm:gap-2 transition-colors touch-manipulation"
                title="Session Information"
              >
                <MessageSquare className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                <span className="sm:hidden">Active</span>
                <span className="hidden sm:inline md:hidden">Session</span>
                <span className="hidden md:inline">Session Active</span>
              </button>
            )}
          </div>
          <div className="w-full sm:w-auto flex justify-end">
            <ConnectButton />
          </div>
        </div>
        
        {/* Session Information Panel */}
        {showSessionInfo && sessionId && (
          <div className="mt-3 sm:mt-4 rounded-2xl border border-white/20 backdrop-blur-xl bg-white/5 p-3 sm:p-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
              <h3 className="text-base sm:text-lg font-semibold flex items-center gap-2">
                <MessageSquare className="w-4 h-4 sm:w-5 sm:h-5" />
                <span className="hidden sm:inline">Conversation Session</span>
                <span className="sm:hidden">Session</span>
                {loadingHistory && <div className="text-xs text-white/60">(Loading...)</div>}
              </h3>
              <button
                onClick={startNewSession}
                className="text-xs sm:text-sm px-2.5 sm:px-3 py-1.5 rounded-lg border border-white/30 hover:border-white/50 transition-colors touch-manipulation self-start sm:self-auto"
              >
                New Session
              </button>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4 text-sm">
              <div className="sm:col-span-2 md:col-span-1">
                <div className="text-white/60 mb-1 text-xs sm:text-sm">Session ID</div>
                <div className="font-mono text-xs sm:text-sm text-white/80 break-all bg-white/5 rounded-lg p-2">{sessionId}</div>
              </div>
              
              {conversationHistory && (
                <>
                  <div>
                    <div className="text-white/60 mb-1 flex items-center gap-1 text-xs sm:text-sm">
                      <Clock className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                      Messages
                    </div>
                    <div className="text-white/80 text-sm">{conversationHistory.message_count} messages</div>
                  </div>
                  
                  <div className="sm:col-span-2 md:col-span-1">
                    <div className="text-white/60 mb-1 text-xs sm:text-sm">Created</div>
                    <div className="text-white/80 text-xs sm:text-sm">{new Date(conversationHistory.created_at).toLocaleString()}</div>
                  </div>
                  
                  <div className="sm:col-span-2 md:col-span-1">
                    <div className="text-white/60 mb-1 text-xs sm:text-sm">Last Activity</div>
                    <div className="text-white/80 text-xs sm:text-sm">{new Date(conversationHistory.last_activity).toLocaleString()}</div>
                  </div>
                </>
              )}
            </div>
            
            <div className="mt-3 pt-3 border-t border-white/10">
              <div className="text-xs sm:text-sm text-white/50 flex flex-col sm:flex-row sm:items-center gap-2">
                <div className="flex items-center gap-2">
                  <CheckCircle className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                  <span>Memory active</span>
                </div>
                {conversationHistory && conversationHistory.message_count > 0 && (
                  <span className="text-green-400 text-xs">({conversationHistory.message_count} messages loaded)</span>
                )}
              </div>
            </div>
          </div>
        )}
      </header>

      {!isConnected ? (
        // Wallet Connection Required Screen
        <main className="relative z-10 max-w-3xl mx-auto px-3 sm:px-4 py-8 sm:py-12 md:py-16">
          <div className="text-center space-y-4 sm:space-y-6">
            <div className="rounded-2xl sm:rounded-3xl border border-white/[0.15] hover:border-blue-500/40 transition-colors duration-300 backdrop-blur-2xl bg-white/[0.05] hover:bg-white/[0.06] shadow-2xl p-6 sm:p-8" style={{
              background: 'linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.03) 100%)',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.15)'
            }}>
              <div className="w-12 h-12 sm:w-16 sm:h-16 mx-auto mb-4 sm:mb-6 rounded-full border border-white/20 flex items-center justify-center bg-white/5">
                <Lock className="w-6 h-6 sm:w-8 sm:h-8 text-white/60" />
              </div>
              <h2 className="text-xl sm:text-2xl font-semibold mb-2 sm:mb-3">Connect Your Wallet</h2>
              <p className="text-sm sm:text-base text-white/70 mb-4 sm:mb-6 leading-relaxed px-2">
                To access AIRAA's research capabilities and personalized on-chain analytics, 
                please connect your wallet using the button above.
              </p>
              <div className="text-xs sm:text-sm text-white/50 flex flex-col sm:flex-row items-center justify-center gap-2">
                <Lock className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                <span className="text-center">Your wallet connection is secure and only used for address-based analytics</span>
              </div>
            </div>
          </div>
        </main>
      ) : (
        // Chat Interface (only shown when wallet is connected)
      <main className="relative z-10 max-w-5xl mx-auto px-3 sm:px-4 py-4 sm:py-6 md:py-8">
        <div className="rounded-2xl sm:rounded-3xl border border-white/[0.15] hover:border-blue-500/40 transition-colors duration-300 backdrop-blur-2xl bg-white/[0.05] hover:bg-white/[0.06] shadow-2xl p-4 sm:p-6 md:p-8" style={{
          background: 'linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.03) 100%)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.15)'
        }}>


          {/* Messages */}
          <div
            className={`overflow-y-auto pr-0.5 sm:pr-1 space-y-3 sm:space-y-4 transition-[height] duration-500 ease-out`}
            style={{ height: hasUserMessage ? '65vh' : '55vh' }}
            id="chat-scroll"
          >
            {messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`relative max-w-[92%] sm:max-w-[85%] rounded-xl sm:rounded-2xl border backdrop-blur-xl shadow-lg p-3 sm:p-4 ${
                    m.role === 'user'
                      ? 'border-white/[0.2] bg-white/[0.08]'
                      : 'border-white/[0.15] bg-white/[0.05]'
                  }`}
                  style={{
                    background: m.role === 'user' 
                      ? 'linear-gradient(135deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.06) 100%)'
                      : 'linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.04) 100%)',
                    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)'
                  }}
                >
                  <div className="text-xs sm:text-sm text-white/50 mb-1 sm:mb-2">
                    {m.role === 'user' ? 'You' : 'AIRAA'} • {new Date(m.timestamp).toLocaleTimeString()}
                  </div>
                  {m.text && (
                    <div className={`whitespace-pre-wrap leading-relaxed text-sm sm:text-[15px] md:text-base ${m.role === 'user' ? '' : 'font-[var(--font-jp)]'}`}>{m.text}</div>
                  )}

                  {m.result && (
                    <div className="mt-2 sm:mt-3 space-y-2 sm:space-y-3">
                      {/* Status and context tags */}
                      <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                        <div className={`inline-block text-xs sm:text-sm px-2 sm:px-2.5 py-1 sm:py-1.5 rounded border ${
                          m.result.success
                            ? 'border-green-400 text-green-300'
                            : 'border-red-400 text-red-300'
                        }`}>
                          {m.result.success ? 'Success' : 'Error'}
                        </div>
                        
                        {/* Show session context if available */}
                        {m.result.session_id && (
                          <div className="inline-block text-xs sm:text-sm px-2 sm:px-2.5 py-1 sm:py-1.5 rounded border border-blue-400/50 text-blue-300">
                            <MessageSquare className="w-3 h-3 inline mr-1" />
                            <span className="hidden sm:inline">Memory Active</span>
                            <span className="sm:hidden">Memory</span>
                          </div>
                        )}
                        
                        {/* Show conversation history count if available */}
                        {conversationHistory && conversationHistory.message_count > 0 && (
                          <div className="inline-block text-xs sm:text-sm px-2 sm:px-2.5 py-1 sm:py-1.5 rounded border border-purple-400/50 text-purple-300">
                            <Clock className="w-3 h-3 inline mr-1" />
                            <span className="hidden sm:inline">{conversationHistory.message_count} msgs</span>
                            <span className="sm:hidden">{conversationHistory.message_count}</span>
                          </div>
                        )}
                      </div>

                      {/* Visualization */}
                      {m.result.success && m.result.data ? (
                        <div className="rounded-lg sm:rounded-xl border border-white/20 p-2 sm:p-3 comic-inner">
                          <DataVisualization
                            data={m.result.data}
                            title="Research Results"
                            config={vizConfigs[m.id]}
                            onConfigChange={(cfg) => setVizConfigs(prev => ({ ...prev, [m.id]: cfg }))}
                          />
                        </div>
                      ) : m.result.error ? (
                        <pre className="text-xs sm:text-sm text-red-300 whitespace-pre-wrap border border-red-400/30 rounded-lg sm:rounded-xl p-2 sm:p-3 bg-red-900/10 overflow-x-auto">{m.result.error}</pre>
                      ) : null}

                      {/* Metadata grid */}
                      {(m.result.reasoning_steps || m.result.citations) && (
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 sm:gap-3">
                          {m.result.reasoning_steps && m.result.reasoning_steps.length > 0 && (
                            <div className="rounded-lg sm:rounded-xl border border-white/20 p-2 sm:p-3">
                              <div className="text-sm sm:text-base md:text-lg font-semibold mb-2">
                                <span className="hidden sm:inline">Reasoning Steps</span>
                                <span className="sm:hidden">Steps</span>
                              </div>
                              <div className="space-y-1">
                                {m.result.reasoning_steps.map((s, i) => (
                                  <div key={i} className="text-xs sm:text-sm text-white/80 leading-relaxed">{i + 1}. {s}</div>
                              ))}
                            </div>
                          </div>
                        )}
                          {m.result.citations && m.result.citations.length > 0 && (
                            <div className="rounded-lg sm:rounded-xl border border-white/20 p-2 sm:p-3">
                              <div className="text-sm sm:text-base md:text-lg font-semibold mb-2">
                                <span className="hidden sm:inline">Data Sources</span>
                                <span className="sm:hidden">Sources</span>
                              </div>
                              <div className="space-y-1">
                                {m.result.citations.map((c: any, i: number) => (
                                  <div key={i} className="text-xs sm:text-sm text-white/80">
                                    <span className="font-medium break-words">{c.source}</span>
                                    <div className="text-white/50 text-xs">{c.timestamp}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                      {/* Actions */}
                      {m.result && m.result.success && (m.result.data || m.result.result || m.result.merged_data) && (
                        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                          <button
                            onClick={() => downloadResult(m.result!, 'json')}
                            className="px-2.5 sm:px-3.5 py-1.5 rounded-lg border border-white/30 text-xs sm:text-sm hover:border-white flex items-center gap-1.5 sm:gap-2 transition-colors touch-manipulation"
                          >
                            <FileDown className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                            <span className="hidden xs:inline">JSON</span>
                            <span className="xs:hidden">J</span>
                          </button>
                          <button
                            onClick={() => downloadResult(m.result!, 'excel')}
                            className="px-2.5 sm:px-3.5 py-1.5 rounded-lg border border-white/30 text-xs sm:text-sm hover:border-white flex items-center gap-1.5 sm:gap-2 transition-colors touch-manipulation"
                          >
                            <FileSpreadsheet className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                            <span className="hidden xs:inline">Excel</span>
                            <span className="xs:hidden">XL</span>
                          </button>
                          <button
                            onClick={() => downloadResult(m.result!, 'pdf')}
                            className="px-2.5 sm:px-3.5 py-1.5 rounded-lg border border-white/30 text-xs sm:text-sm hover:border-white flex items-center gap-1.5 sm:gap-2 transition-colors touch-manipulation"
                          >
                            <FileText className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                            <span className="hidden xs:inline">PDF</span>
                            <span className="xs:hidden">P</span>
                          </button>
                  </div>
                      )}
                  </div>
                )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="relative max-w-[92%] sm:max-w-[85%] rounded-xl sm:rounded-2xl border border-white/[0.15] backdrop-blur-xl bg-white/[0.05] p-3 sm:p-4 shadow-lg"
                  style={{
                    background: 'linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.04) 100%)',
                    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)'
                  }}>
                  <div className="text-xs sm:text-sm text-white/60 mb-1 sm:mb-2">AIRAA • thinking…</div>
                  <LoadingSpinner size="sm" text="Researching..." />
                </div>
              </div>
            )}

            <div ref={endOfChatRef} />
          </div>

          {/* Advanced options toggle */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mt-3 sm:mt-4 gap-2 sm:gap-4">
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-xs sm:text-sm px-3 sm:px-3.5 py-1.5 rounded-full border border-white/30 hover:border-white flex items-center gap-1.5 sm:gap-2 touch-manipulation"
            >
              {showAdvanced ? <EyeOff className="w-3.5 h-3.5 sm:w-4 sm:h-4" /> : <Eye className="w-3.5 h-3.5 sm:w-4 sm:h-4" />}
              <span className="hidden sm:inline">{showAdvanced ? 'Hide settings' : 'Show settings'}</span>
              <span className="sm:hidden">{showAdvanced ? 'Hide' : 'Settings'}</span>
            </button>
            <div className="text-xs sm:text-sm text-white/60 space-y-1 sm:space-y-0">
              <div className="sm:hidden">
                <div>Range: {timeRange}</div>
                {address && <div>Address: {address.slice(0, 6)}...{address.slice(-4)}</div>}
                {sessionId && <div>Session: {sessionId.slice(-8)}</div>}
              </div>
              <div className="hidden sm:block">
                Time Range: {timeRange}
                {address ? ` • Address: ${address.slice(0, 6)}...${address.slice(-4)}` : ''}
                {sessionId ? ` • Session: ${sessionId.slice(-8)}` : ''}
              </div>
            </div>
          </div>

          {showAdvanced && (
            <div className="mt-3 space-y-3 sm:space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs sm:text-sm text-white/70 mb-1 sm:mb-2">Connected Wallet Address</label>
                  <input
                    type="text"
                    value={address}
                    readOnly
                    placeholder="Connected wallet address"
                    className="w-full bg-white/5 border-2 border-white/20 rounded-lg sm:rounded-xl px-3 py-2 text-xs sm:text-sm text-white/80 cursor-not-allowed"
                  />
                  <div className="text-xs sm:text-sm text-white/60 mt-1 sm:mt-2 flex items-center gap-2">
                    <CheckCircle className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                    <span className="hidden sm:inline">Automatically populated from connected wallet</span>
                    <span className="sm:hidden">Auto-populated from wallet</span>
                  </div>
                </div>
                <div>
                  <label className="block text-xs sm:text-sm text-white/70 mb-1 sm:mb-2">Time Range</label>
                  <select
                    value={timeRange}
                    onChange={(e) => setTimeRange(e.target.value)}
                    className="w-full bg-transparent border-2 border-white/20 rounded-lg sm:rounded-xl px-3 py-2 text-xs sm:text-sm focus:outline-none focus:border-white touch-manipulation"
                  >
                    <option className="bg-black" value="1d">Last 24 Hours</option>
                    <option className="bg-black" value="7d">Last 7 Days</option>
                    <option className="bg-black" value="30d">Last 30 Days</option>
                    <option className="bg-black" value="90d">Last 90 Days</option>
                    <option className="bg-black" value="1y">Last Year</option>
                  </select>
                </div>
              </div>
              
              {/* Session Management */}
              <div className="border-t border-white/10 pt-3 sm:pt-4">
                <label className="block text-xs sm:text-sm text-white/70 mb-2">Conversation Memory</label>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <div className="text-xs sm:text-sm text-white/60 mb-1 sm:mb-2">Current Session</div>
                    <div className="font-mono text-xs text-white/80 bg-white/5 rounded-lg p-2 break-all">
                      {sessionId || 'No session active'}
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row md:flex-col gap-2">
                    <button
                      onClick={startNewSession}
                      className="px-3 py-2 text-xs sm:text-sm rounded-lg border border-white/30 hover:border-white/50 transition-colors flex items-center gap-2 touch-manipulation justify-center sm:justify-start"
                    >
                      <MessageSquare className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                      <span className="hidden sm:inline">New Conversation</span>
                      <span className="sm:hidden">New Chat</span>
                    </button>
                    <button
                      onClick={() => refreshConversationHistory()}
                      className="px-3 py-2 text-xs sm:text-sm rounded-lg border border-white/30 hover:border-white/50 transition-colors flex items-center gap-2 touch-manipulation justify-center sm:justify-start"
                      disabled={!sessionId}
                    >
                      <Clock className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                      <span className="hidden sm:inline">Refresh History</span>
                      <span className="sm:hidden">Refresh</span>
                    </button>
                  </div>
                </div>
                
                {conversationHistory && (
                  <div className="mt-3 text-xs sm:text-sm">
                    <div className="text-white/60 mb-1 sm:mb-2 text-xs sm:text-sm">Session Statistics</div>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4 text-xs">
                      <div>
                        <div className="text-white/50">Messages</div>
                        <div className="text-white/80 flex items-center gap-1">
                          {conversationHistory.message_count}
                          {conversationHistory.message_count > 0 && <CheckCircle className="w-3 h-3 text-green-400" />}
                        </div>
                      </div>
                      <div>
                        <div className="text-white/50">Created</div>
                        <div className="text-white/80 text-xs">{new Date(conversationHistory.created_at).toLocaleDateString()}</div>
                      </div>
                      <div className="col-span-2 md:col-span-1">
                        <div className="text-white/50">Last Active</div>
                        <div className="text-white/80 text-xs">{new Date(conversationHistory.last_activity).toLocaleDateString()}</div>
                      </div>
                    </div>
                    {conversationHistory.message_count > 0 && (
                      <div className="mt-2 text-xs text-green-400 flex items-center gap-1">
                        <MessageSquare className="w-3 h-3" />
                        <span className="hidden sm:inline">Previous conversation loaded - context is preserved</span>
                        <span className="sm:hidden">Context preserved</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Input */}
          <div className="mt-4 sm:mt-6 flex items-end gap-2 sm:gap-3">
            <div className="flex-1 relative">
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask anything about Web3, DeFi, on-chain data..."
                className={`w-full ${hasUserMessage ? 'h-20 sm:h-24 md:h-28 lg:h-32' : 'h-16 sm:h-20 md:h-24 lg:h-28'} bg-white/[0.05] backdrop-blur-sm border border-white/[0.15] rounded-xl sm:rounded-2xl px-3 sm:px-4 py-2 sm:py-3 placeholder-white/40 focus:outline-none focus:border-white/[0.3] focus:bg-white/[0.08] resize-none text-white text-sm sm:text-base md:text-lg transition-[height] duration-500 ease-out`}
                style={{
                  background: 'linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.04) 100%)',
                  boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.1)'
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
              />
              {/* Mobile keyboard hint */}
              <div className="absolute bottom-1 right-2 text-xs text-white/30 pointer-events-none sm:hidden">
                Enter to send
              </div>
            </div>
            <button
              onClick={handleSend}
              disabled={loading || !query.trim()}
              className={`h-10 sm:h-12 px-4 sm:px-6 rounded-lg sm:rounded-xl backdrop-blur-sm border transition-all duration-200 font-medium text-sm sm:text-base touch-manipulation ${
                loading || !query.trim()
                  ? 'border-white/[0.1] bg-white/[0.03] text-white/30 cursor-not-allowed'
                  : 'border-white/[0.2] bg-white/[0.08] text-white hover:bg-white/[0.15] hover:border-white/[0.3] shadow-lg active:scale-95'
              }`}
              style={!(loading || !query.trim()) ? {
                background: 'linear-gradient(135deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.06) 100%)',
                boxShadow: '0 4px 16px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.15)'
              } : {}}
            >
              {loading ? (
                <span className="flex items-center gap-1">
                  <span className="hidden sm:inline">...</span>
                  <span className="sm:hidden">•••</span>
                </span>
              ) : (
                'Send'
              )}
            </button>
          </div>
        </div>

      </main>
      )}
    </div>
  );
}
