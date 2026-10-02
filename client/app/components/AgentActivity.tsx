'use client';

import { useState } from 'react';
import { CheckCircle2, ChevronDown, Loader2, XCircle } from 'lucide-react';
import { toolLabel, type ToolProgress } from '../../lib/api';

const fmtMs = (ms?: number) => (ms == null ? '' : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`);

function ToolRow({ t }: { t: ToolProgress }) {
  return (
    <li className="flex items-center gap-2 text-xs sm:text-sm">
      {t.status === 'running' && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-cyan-300" />}
      {t.status === 'done' && <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400" />}
      {t.status === 'failed' && <XCircle className="h-3.5 w-3.5 shrink-0 text-red-400" />}
      <span className={t.status === 'failed' ? 'text-red-300' : 'text-white/80'}>{toolLabel(t.tool)}</span>
      <span className="ml-auto font-mono text-[11px] text-white/40">{fmtMs(t.duration_ms)}</span>
      {t.status === 'failed' && t.error && (
        <span className="max-w-[40%] truncate text-[11px] text-red-300/70" title={t.error}>{t.error}</span>
      )}
    </li>
  );
}

/** Live view of what the agent is doing while a query runs. */
export function LiveActivity({
  stage,
  planner,
  rationale,
  tools,
}: {
  stage: string;
  planner?: string;
  rationale?: string;
  tools: ToolProgress[];
}) {
  return (
    <div className="space-y-2.5 rounded-xl border border-white/10 bg-black/20 p-3">
      <div className="flex items-center gap-2 text-xs text-white/60">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-300" />
        <span>{stage}</span>
      </div>
      {rationale && (
        <p className="text-xs italic text-white/50">
          {planner === 'llm' ? 'Plan' : 'Fallback plan'}: {rationale}
        </p>
      )}
      {tools.length > 0 && <ul className="space-y-1.5">{tools.map((t) => <ToolRow key={t.tool} t={t} />)}</ul>}
    </div>
  );
}

/** Collapsed summary of a finished run: which tools ran, how long, and why. */
export function ActivitySummary({
  trace,
  steps,
  sources,
  seconds,
  planner,
}: {
  trace?: Array<{ tool: string; success: boolean; duration_ms?: number; error?: string | null }>;
  steps?: string[];
  sources?: string[];
  seconds?: number;
  planner?: string;
}) {
  const [open, setOpen] = useState(false);
  if (!trace?.length && !steps?.length) return null;

  const ok = trace?.filter((t) => t.success).length ?? 0;
  const total = trace?.length ?? 0;

  return (
    <div className="rounded-xl border border-white/10 bg-black/20">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-white/60 hover:text-white/80"
        aria-expanded={open}
      >
        <span className="font-medium text-white/80">Agent activity</span>
        {total > 0 && <span>· {ok}/{total} sources</span>}
        {seconds != null && <span>· {seconds.toFixed(1)}s</span>}
        {planner && <span className="hidden sm:inline">· {planner === 'llm' ? 'LLM-planned' : 'rule-planned'}</span>}
        <ChevronDown className={`ml-auto h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="space-y-3 border-t border-white/10 px-3 py-3">
          {trace && trace.length > 0 && (
            <ul className="space-y-1.5">
              {trace.map((t, i) => (
                <ToolRow
                  key={`${t.tool}-${i}`}
                  t={{ tool: t.tool, status: t.success ? 'done' : 'failed', duration_ms: t.duration_ms, error: t.error }}
                />
              ))}
            </ul>
          )}
          {steps && steps.length > 0 && (
            <ol className="list-decimal space-y-1 pl-5 text-xs text-white/60 marker:text-white/30">
              {steps.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          )}
          {sources && sources.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {sources.map((s) => (
                <span key={s} className="rounded-full border border-white/15 px-2 py-0.5 text-[11px] text-white/60">{s}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
