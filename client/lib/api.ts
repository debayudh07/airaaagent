import { getAccessToken, refreshSession } from './auth';
import { API_BASE } from './config';

export { API_BASE };

export type ToolStatus = 'running' | 'done' | 'failed';

export interface ToolProgress {
  tool: string;
  status: ToolStatus;
  duration_ms?: number;
  error?: string | null;
}

export interface ChartSpec {
  id: string;
  kind: 'line' | 'area' | 'bar';
  title: string;
  subtitle?: string;
  x_key: string;
  series: Array<{ key: string; label: string }>;
  data: Array<Record<string, string | number | null>>;
  y_format: 'usd' | 'percent' | 'number';
}

export type AgentEvent =
  | { type: 'status'; stage: string; message: string }
  | { type: 'plan'; tools: string[]; rationale?: string; planner?: string }
  | { type: 'tool_start'; tool: string }
  | { type: 'tool_retry'; tool: string; error?: string | null }
  | { type: 'followup'; tools: string[]; reason?: string }
  | { type: 'tool_end'; tool: string; success: boolean; duration_ms: number; error?: string | null }
  | { type: 'chart'; chart: ChartSpec }
  | { type: 'token'; text: string }
  | { type: 'result'; result: unknown }
  | { type: 'error'; error: string };

export const TOOL_LABELS: Record<string, string> = {
  coinmarketcap_tool: 'CoinMarketCap',
  coingecko_tool: 'CoinGecko',
  defillama_tool: 'DefiLlama',
  dune_analytics_tool: 'Dune Analytics',
  etherscan_tool: 'Etherscan',
  dexscreener_tool: 'DEX Screener',
  news_tool: 'News',
  web_search_tool: 'Web search',
  read_url_tool: 'Reading pages',
};

export const toolLabel = (name: string) => TOOL_LABELS[name] ?? name;

// ------------------------------------------------------------------ home board feed
export interface FeedMarket {
  id: string;
  symbol: string;
  name: string;
  price: number | null;
  change_24h: number | null;
  change_7d: number | null;
  change_30d: number | null;
  sparkline_7d: number[];
}

export interface FeedNews {
  title: string;
  url: string;
  source: string;
  published: string | null;
  summary: string;
}

export interface FeedVolume {
  chain: string;
  total24h: number | null;
  top: Array<{ name: string; total24h: number | null }>;
}

export interface FeedSections {
  markets?: FeedMarket[];
  yields?: Array<{ project: string; chain: string; symbol: string; apy: number; tvl_usd: number }>;
  stablecoins?: Array<{ symbol: string; name: string; circulating_usd: number }>;
  dex?: FeedVolume;
  fees?: FeedVolume;
  protocols?: Array<{ slug: string; name: string; tvl_usd: number }>;
  news?: FeedNews[];
}

export interface Feed {
  success: boolean;
  generated_at: string;
  sections: FeedSections;
}

export async function fetchFeed(signal?: AbortSignal): Promise<Feed> {
  const response = await fetch(`${API_BASE}/api/feed`, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

/** Link that opens a chat and asks `question` straight away. */
export const askHref = (question: string, range?: string) =>
  `/main-chat?q=${encodeURIComponent(question)}${range ? `&range=${encodeURIComponent(range)}` : ''}`;

/**
 * POSTs a research query and invokes `onEvent` for every Server-Sent Event the
 * agent emits (plan, tool progress, answer tokens, final result).
 * Resolves once the stream ends; rejects on network errors or abort.
 */
export async function streamResearch(
  body: Record<string, unknown>,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const open = async () => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = await getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;   // signed in: the conversation belongs to the wallet
    return fetch(`${API_BASE}/api/research/stream`, { method: 'POST', headers, body: JSON.stringify(body), signal });
  };
  let response = await open();
  if (response.status === 401 && (await refreshSession())) response = await open();

  if (!response.ok || !response.body) {
    let detail = `HTTP ${response.status}`;
    try {
      const data = await response.json();
      if (data?.error) detail = data.error;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE messages are separated by a blank line
    let boundary: number;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = raw
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trim())
        .join('');
      if (!data) continue; // keep-alive comment
      try {
        onEvent(JSON.parse(data) as AgentEvent);
      } catch {
        /* ignore malformed frame */
      }
    }
  }
}
