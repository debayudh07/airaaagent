export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || 'https://airaaagent.onrender.com'
).replace(/\/$/, '');

export type ToolStatus = 'running' | 'done' | 'failed';

export interface ToolProgress {
  tool: string;
  status: ToolStatus;
  duration_ms?: number;
  error?: string | null;
}

export type AgentEvent =
  | { type: 'status'; stage: string; message: string }
  | { type: 'plan'; tools: string[]; rationale?: string; planner?: string }
  | { type: 'tool_start'; tool: string }
  | { type: 'tool_retry'; tool: string; error?: string | null }
  | { type: 'followup'; tools: string[]; reason?: string }
  | { type: 'tool_end'; tool: string; success: boolean; duration_ms: number; error?: string | null }
  | { type: 'token'; text: string }
  | { type: 'result'; result: unknown }
  | { type: 'error'; error: string };

export const TOOL_LABELS: Record<string, string> = {
  coinmarketcap_tool: 'CoinMarketCap',
  defillama_tool: 'DefiLlama',
  dune_analytics_tool: 'Dune Analytics',
  etherscan_tool: 'Etherscan',
};

export const toolLabel = (name: string) => TOOL_LABELS[name] ?? name;

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
  const response = await fetch(`${API_BASE}/api/research/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

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
