'use client';

import { useEffect, useState } from 'react';
import { CheckCircle2, ChevronDown, Loader2, XCircle } from 'lucide-react';
import { toolLabel, type ToolProgress } from '../../lib/api';

const fmtMs = (ms?: number) => (ms == null ? '' : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`);

function ToolRow({ t }: { t: ToolProgress }) {
  return (
    <li className="flex items-center gap-2.5">
      {t.status === 'running' && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-accent" aria-label="Running" />}
      {t.status === 'done' && <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" aria-label="Done" />}
      {t.status === 'failed' && <XCircle className="h-4 w-4 shrink-0 text-danger" aria-label="Failed" />}
      <span className={t.status === 'failed' ? 'text-red-300' : 'text-ink'}>{toolLabel(t.tool)}</span>
      {t.status === 'failed' && t.error && (
        <span className="min-w-0 truncate text-xs text-red-300/70" title={t.error}>{t.error}</span>
      )}
      <span className="ml-auto shrink-0 font-mono text-xs text-subtle">{fmtMs(t.duration_ms)}</span>
    </li>
  );
}

function useElapsed() {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(start);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(id);
  }, []);
  return ((now - start) / 1000).toFixed(1);
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
  const elapsed = useElapsed();
  return (
    <section
      aria-label="Agent progress"
      className="flex flex-col gap-2.5 rounded-[14px] border border-line bg-surface px-3.5 py-3 text-[13px] sm:px-4 sm:py-3.5"
    >
      <div className="flex items-center gap-2.5 text-ink-3">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-accent" aria-hidden="true" />
        <span className="font-medium" aria-live="polite">{stage}</span>
        <span className="ml-auto font-mono text-xs text-subtle">{elapsed}s</span>
      </div>
      {rationale && (
        <p className="m-0 hidden text-muted sm:block">
          <span className="text-subtle">{planner === 'llm' ? 'Plan' : 'Fallback plan'}:</span> {rationale}
        </p>
      )}
      {tools.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0 text-[13px] sm:text-sm">
          {tools.map((t) => <ToolRow key={t.tool} t={t} />)}
        </ul>
      )}
    </section>
  );
}

/** Collapsed summary of a finished run: which tools ran, how long, and why. */
export function ActivitySummary({
  trace,
  steps,
  seconds,
  planner,
}: {
  trace?: Array<{ tool: string; success: boolean; duration_ms?: number; error?: string | null }>;
  steps?: string[];
  seconds?: number;
  planner?: string;
}) {
  const [open, setOpen] = useState(false);
  if (!trace?.length && !steps?.length) return null;

  const ok = trace?.filter((t) => t.success).length ?? 0;
  const total = trace?.length ?? 0;

  return (
    <section aria-label="Agent activity" className="rounded-xl border border-line bg-black/20">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-11 w-full items-center gap-2 px-3.5 text-left text-[13px] text-muted transition-colors hover:text-ink-3"
        aria-expanded={open}
      >
        <span className="font-medium text-ink">Agent activity</span>
        {total > 0 && <span>· {ok}/{total}<span className="hidden sm:inline"> sources</span></span>}
        {seconds != null && <span>· {seconds.toFixed(1)}s</span>}
        {planner && <span className="hidden sm:inline">· {planner === 'llm' ? 'LLM-planned' : 'rule-planned'}</span>}
        <ChevronDown className={`ml-auto h-4 w-4 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {open && (
        <div className="flex flex-col gap-2.5 border-t border-white/[0.08] px-3.5 py-3 text-[13px]">
          {trace && trace.length > 0 && (
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
              {trace.map((t, i) => (
                <ToolRow
                  key={`${t.tool}-${i}`}
                  t={{ tool: t.tool, status: t.success ? 'done' : 'failed', duration_ms: t.duration_ms, error: t.error }}
                />
              ))}
            </ul>
          )}
          {steps && steps.length > 0 && (
            <ol className="m-0 flex list-decimal flex-col gap-[3px] pl-5 text-muted marker:text-subtle">
              {steps.map((s, i) => <li key={i}>{s}</li>)}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
