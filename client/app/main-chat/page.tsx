/* eslint-disable */
'use client';

import { useState, useRef, useEffect } from 'react';
import { ConnectButton } from '@rainbow-me/rainbowkit';
import { useAccount } from 'wagmi';
import DataVisualization, { type VisualizationConfig } from '../components/DataVisualization';
import LoadingSpinner from '../components/LoadingSpinner';
import { WavyBackground } from '../../components/ui/wavy-background';



interface ResearchResult {
  success: boolean;
  data?: any;
  result?: any; // Backend returns data in 'result' field
  error?: string;
  timestamp?: string;
  query?: string;
  address?: string;
  time_range?: string;
  reasoning_steps?: string[];
  citations?: Array<{
    source: string;
    timestamp: string;
    query_context: string;
  }>;
  data_sources_used?: string[];
  execution_time?: number;
  query_intent?: string;
  merged_data?: any;
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

export default function MainChat() {
  const { address: connectedAddress, isConnected } = useAccount();
  const [query, setQuery] = useState('');
  const [address, setAddress] = useState('');
  const [timeRange, setTimeRange] = useState('7d');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      text: 'Hi! I\'m your AIRAA Research Agent. Ask me anything about Web3, DeFi, or on-chain analytics. Your connected wallet address is automatically used for personalized analysis.',
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

  const checkApiHealth = async () => {
    try {
      const response = await fetch('https://airaaagent.onrender.com/api/health');
      const data = await response.json();
      setApiStats(prev => ({ ...prev, isOnline: data.status === 'ok' }));
    } catch (error) {
      setApiStats(prev => ({ ...prev, isOnline: false }));
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
        }),
      });

      const data = await response.json();
      const responseTime = Date.now() - startTime;

      const normalized: ResearchResult = {
        ...data,
        data: data.result || data.data,
        timestamp: new Date().toISOString(),
        query: trimmed,
        address: address || undefined,
        time_range: timeRange,
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

      setMessages(prev => [...prev, assistantMessage]);

      setApiStats(prev => ({
        totalQueries: prev.totalQueries + 1,
        successfulQueries: prev.successfulQueries + (data.success ? 1 : 0),
        avgResponseTime:
          (prev.avgResponseTime * prev.totalQueries + responseTime) /
          (prev.totalQueries + 1),
        isOnline: true,
      }));
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

  const downloadResult = (res: ResearchResult, format: 'json' | 'csv') => {
    if (!res?.data) return;

    let content: string;
    let filename: string;
    let mimeType: string;

    if (format === 'json') {
      content = JSON.stringify(res, null, 2);
      filename = `research-${Date.now()}.json`;
      mimeType = 'application/json';
    } else {
      const flatData = flattenObject(res.data);
      const headers = Object.keys(flatData).join(',');
      const values = Object.values(flatData).map(v => `"${v}"`).join(',');
      content = `${headers}\n${values}`;
      filename = `research-${Date.now()}.csv`;
      mimeType = 'text/csv';
    }

    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
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

  const exampleQueries = [
    "Analyze Bitcoin price trends and market sentiment",
    "What is the TVL and performance of Uniswap protocol?",
    "Show me Ethereum network health and gas fees",
    "Compare DeFi yields across different protocols",
    "Research Solana ecosystem growth metrics"
  ];

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
      <header className="relative z-20 max-w-5xl mx-auto px-4 pt-8 pb-4">
        <div className="flex justify-between items-center">
          <h1 className="text-3xl md:text-4xl font-bold bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent">
            AIRAA Research Agent
          </h1>
          <ConnectButton />
        </div>
      </header>

      {!isConnected ? (
        // Wallet Connection Required Screen
        <main className="relative z-10 max-w-3xl mx-auto px-4 py-16">
          <div className="text-center space-y-6">
            <div className="rounded-3xl border border-white/[0.15] hover:border-blue-500/40 transition-colors duration-300 backdrop-blur-2xl bg-white/[0.05] hover:bg-white/[0.06] shadow-2xl p-8" style={{
              background: 'linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.03) 100%)',
              boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.15)'
            }}>
              <div className="w-16 h-16 mx-auto mb-6 rounded-full border border-white/20 flex items-center justify-center bg-white/5">
                <svg className="w-8 h-8 text-white/60" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <h2 className="text-2xl font-semibold mb-3">Connect Your Wallet</h2>
              <p className="text-white/70 mb-6 leading-relaxed">
                To access AIRAA's research capabilities and personalized on-chain analytics, 
                please connect your wallet using the button above.
              </p>
              <div className="text-sm text-white/50">
                🔒 Your wallet connection is secure and only used for address-based analytics
              </div>
            </div>
          </div>
        </main>
      ) : (
        // Chat Interface (only shown when wallet is connected)
      <main className="relative z-10 max-w-5xl mx-auto px-4 py-8">
        <div className="rounded-3xl border border-white/[0.15] hover:border-blue-500/40 transition-colors duration-300 backdrop-blur-2xl bg-white/[0.05] hover:bg-white/[0.06] shadow-2xl p-6 md:p-8" style={{
          background: 'linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.03) 100%)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.15)'
        }}>
          {/* Quick Examples */}
          <div className="mb-4 flex flex-wrap gap-2">
            {exampleQueries.map((ex, idx) => (
                <button
                key={idx}
                onClick={() => setQuery(ex)}
                className="px-5 py-2.5 rounded-xl border border-white/[0.1] backdrop-blur-sm bg-white/[0.03] text-sm md:text-base hover:bg-white/[0.08] hover:border-white/[0.2] transition-all duration-200 text-white/80 hover:text-white"
              >
                {ex}
                </button>
              ))}
          </div>

          {/* Messages */}
          <div
            className={`overflow-y-auto pr-1 space-y-4 transition-[height] duration-500 ease-out`}
            style={{ height: hasUserMessage ? '70vh' : '60vh' }}
            id="chat-scroll"
          >
            {messages.map((m) => (
              <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`relative max-w-[85%] rounded-2xl border backdrop-blur-xl shadow-lg p-4 ${
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
                  <div className="text-sm text-white/50 mb-1">
                    {m.role === 'user' ? 'You' : 'AIRAA'} • {new Date(m.timestamp).toLocaleTimeString()}
                  </div>
                  {m.text && (
                    <div className={`whitespace-pre-wrap leading-relaxed text-[15px] md:text-base ${m.role === 'user' ? '' : 'font-[var(--font-jp)]'}`}>{m.text}</div>
                  )}

                  {m.result && (
                    <div className="mt-3 space-y-3">
                      {/* Status tag */}
                      <div className={`inline-block text-sm px-2.5 py-1.5 rounded border ${
                        m.result.success
                          ? 'border-green-400 text-green-300'
                          : 'border-red-400 text-red-300'
                      }`}>
                        {m.result.success ? 'Success' : 'Error'}
            </div>

                      {/* Visualization */}
                      {m.result.success && m.result.data ? (
                        <div className="rounded-xl border border-white/20 p-3 comic-inner">
                          <DataVisualization
                            data={m.result.data}
                            title="Research Results"
                            config={vizConfigs[m.id]}
                            onConfigChange={(cfg) => setVizConfigs(prev => ({ ...prev, [m.id]: cfg }))}
                          />
                        </div>
                      ) : m.result.error ? (
                        <pre className="text-xs text-red-300 whitespace-pre-wrap border border-red-400/30 rounded-xl p-3 bg-red-900/10">{m.result.error}</pre>
                      ) : null}

                      {/* Metadata grid */}
                      {(m.result.reasoning_steps || m.result.citations) && (
                        <div className="grid md:grid-cols-2 gap-3">
                          {m.result.reasoning_steps && m.result.reasoning_steps.length > 0 && (
                            <div className="rounded-xl border border-white/20 p-3">
                              <div className="text-base md:text-lg font-semibold mb-2">Reasoning Steps</div>
                              <div className="space-y-1">
                                {m.result.reasoning_steps.map((s, i) => (
                                  <div key={i} className="text-sm text-white/80">{i + 1}. {s}</div>
                              ))}
                            </div>
                          </div>
                        )}
                          {m.result.citations && m.result.citations.length > 0 && (
                            <div className="rounded-xl border border-white/20 p-3">
                              <div className="text-base md:text-lg font-semibold mb-2">Data Sources</div>
                              <div className="space-y-1">
                                {m.result.citations.map((c: any, i: number) => (
                                  <div key={i} className="text-sm text-white/80">
                                    <span className="font-medium">{c.source}</span>
                                    <div className="text-white/50">{c.timestamp}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                      {/* Actions */}
                      {m.result && m.result.success && m.result.data && (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => downloadResult(m.result!, 'json')}
                            className="px-3.5 py-1.5 rounded-lg border border-white/30 text-sm hover:border-white"
                          >
                            📄 Download JSON
                          </button>
                          <button
                            onClick={() => downloadResult(m.result!, 'csv')}
                            className="px-3.5 py-1.5 rounded-lg border border-white/30 text-sm hover:border-white"
                          >
                            📊 Download CSV
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
                <div className="relative max-w-[85%] rounded-2xl border border-white/[0.15] backdrop-blur-xl bg-white/[0.05] p-4 shadow-lg"
                  style={{
                    background: 'linear-gradient(135deg, rgba(255,255,255,0.08) 0%, rgba(255,255,255,0.04) 100%)',
                    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)'
                  }}>
                  <div className="text-sm text-white/60 mb-1">AIRAA • thinking…</div>
                  <LoadingSpinner size="sm" text="Researching..." />
                </div>
              </div>
            )}

            <div ref={endOfChatRef} />
          </div>

          {/* Advanced options toggle */}
          <div className="flex items-center justify-between mt-4">
            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-sm px-3.5 py-1.5 rounded-full border border-white/30 hover:border-white"
            >
              {showAdvanced ? 'Hide settings' : 'Show settings'}
            </button>
            <div className="text-sm text-white/60">Time Range: {timeRange}{address ? ` • Address: ${address.slice(0, 6)}...${address.slice(-4)}` : ''}</div>
          </div>

          {showAdvanced && (
            <div className="mt-3 grid md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm text-white/70 mb-1">Connected Wallet Address</label>
                <input
                  type="text"
                  value={address}
                  readOnly
                  placeholder="Connected wallet address"
                  className="w-full bg-white/5 border-2 border-white/20 rounded-xl px-3 py-2 text-white/80 cursor-not-allowed"
                />
                <div className="text-sm text-white/60 mt-1">
                  ✅ Automatically populated from connected wallet
                </div>
              </div>
              <div>
                <label className="block text-sm text-white/70 mb-1">Time Range</label>
                <select
                  value={timeRange}
                  onChange={(e) => setTimeRange(e.target.value)}
                  className="w-full bg-transparent border-2 border-white/20 rounded-xl px-3 py-2 focus:outline-none focus:border-white"
                >
                  <option className="bg-black" value="1d">Last 24 Hours</option>
                  <option className="bg-black" value="7d">Last 7 Days</option>
                  <option className="bg-black" value="30d">Last 30 Days</option>
                  <option className="bg-black" value="90d">Last 90 Days</option>
                  <option className="bg-black" value="1y">Last Year</option>
                </select>
              </div>
            </div>
          )}

          {/* Input */}
          <div className="mt-6 flex items-end gap-3">
            <div className="flex-1 relative">
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask anything about Web3, DeFi, on-chain data..."
                className={`w-full ${hasUserMessage ? 'h-28 md:h-32' : 'h-24 md:h-28'} bg-white/[0.05] backdrop-blur-sm border border-white/[0.15] rounded-2xl px-4 py-3 placeholder-white/40 focus:outline-none focus:border-white/[0.3] focus:bg-white/[0.08] resize-none text-white text-base md:text-lg transition-[height] duration-500 ease-out`}
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
            </div>
            <button
              onClick={handleSend}
              disabled={loading || !query.trim()}
              className={`h-12 px-6 rounded-xl backdrop-blur-sm border transition-all duration-200 font-medium text-base ${
                loading || !query.trim()
                  ? 'border-white/[0.1] bg-white/[0.03] text-white/30 cursor-not-allowed'
                  : 'border-white/[0.2] bg-white/[0.08] text-white hover:bg-white/[0.15] hover:border-white/[0.3] shadow-lg'
              }`}
              style={!(loading || !query.trim()) ? {
                background: 'linear-gradient(135deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.06) 100%)',
                boxShadow: '0 4px 16px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.15)'
              } : {}}
            >
              {loading ? '...' : 'Send'}
            </button>
          </div>
        </div>

      </main>
      )}
    </div>
  );
}
