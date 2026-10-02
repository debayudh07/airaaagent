'use client';

import { useEffect, useState } from 'react';
import { Check, Loader2, X } from 'lucide-react';
import { toolLabel, type ToolProgress } from '../../lib/api';

const fmtMs = (ms?: number) => (ms == null ? '' : ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`);

export const STEPS = ['Plan', 'Gather', 'Check', 'Write'] as const;

function ToolRow({ t }: { t: ToolProgress }) {
  return (
    <li className="flex items-center gap-2.5 text-sm">
      {t.status === 'running' && <span className="anim-pulse h-2 w-2 shrink-0 rounded-full bg-accent" aria-label="Running" />}
      {t.status === 'done' && <span className="h-2 w-2 shrink-0 rounded-full bg-up" aria-label="Done" />}
      {t.status === 'failed' && <X className="h-3.5 w-3.5 shrink-0 text-down" aria-label="Failed" />}
      <span className={`font-semibold ${t.status === 'failed' ? 'text-down' : ''}`}>{toolLabel(t.tool)}</span>
      {t.status === 'failed' && t.error && <span className="min-w-0 truncate text-xs text-muted" title={t.error}>{t.error}</span>}
      <span className="tabular ml-auto shrink-0 text-muted">{fmtMs(t.duration_ms)}</span>
    </li>
  );
}

function Stepper({ step }: { step: number }) {
  return (
    <ol aria-label="Agent progress" className="m-0 flex list-none items-start p-0">
      {STEPS.map((label, i) => {
        const done = i < step;
        const active = i === step;
        return (
          <li key={label} className={`flex items-start ${i < STEPS.length - 1 ? 'flex-1' : ''}`}>
            <span className="flex shrink-0 flex-col items-center gap-1.5">
              {done ? (
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-ink"><Check className="h-3.5 w-3.5 text-white" strokeWidth={3} aria-label="Done" /></span>
              ) : active ? (
                <span className="anim-pulse flex h-7 w-7 items-center justify-center rounded-full bg-accent"><Loader2 className="h-3.5 w-3.5 animate-spin text-ink" strokeWidth={3} aria-label="In progress" /></span>
              ) : (
                <span className="h-7 w-7 rounded-full border-2 border-[#d5d7dd] bg-white" />
              )}
              <span className={`text-[13px] ${done || active ? 'font-bold' : 'font-medium text-muted'}`}>{label}</span>
            </span>
            {i < STEPS.length - 1 && (
              <span className="mx-2 mt-3 h-[3px] flex-1 overflow-hidden rounded-full bg-[#e1e2e7]">
                <span className="block h-full rounded-full bg-ink transition-[width] duration-500" style={{ width: done ? '100%' : '0%' }} />
              </span>
            )}
          </li>
        );
      })}
    </ol>
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
  step,
  planner,
  rationale,
  tools,
}: {
  stage: string;
  step: number;
  planner?: string;
  rationale?: string;
  tools: ToolProgress[];
}) {
  const elapsed = useElapsed();
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2.5 text-sm">
        <span className="typing inline-flex gap-1" aria-hidden="true"><span /><span /><span /></span>
        <span className="text-muted" aria-live="polite">{stage}</span>
        <span className="tabular ml-auto text-[13px] text-muted">{elapsed}s</span>
      </div>
      <div className="flex flex-col gap-3.5 rounded-[22px] bg-soft px-[18px] py-4">
        <Stepper step={step} />
        {(tools.length > 0 || rationale) && (
          <div className="flex flex-col gap-2.5 border-t border-line pt-3">
            {rationale && (
              <p className="m-0 hidden text-[13px] text-muted sm:block">
                <span className="font-semibold text-ink-3">{planner === 'llm' ? 'Plan' : 'Fallback plan'}:</span> {rationale}
              </p>
            )}
            {tools.length > 0 && <ul className="m-0 flex list-none flex-col gap-2 p-0">{tools.map((t) => <ToolRow key={t.tool} t={t} />)}</ul>}
          </div>
        )}
      </div>
    </div>
  );
}

/** Expandable record of a finished run: which tools ran, how long, and why. */
export function ActivitySummary({
  trace,
  steps,
  seconds,
  planner,
  open,
}: {
  trace?: Array<{ tool: string; success: boolean; duration_ms?: number; error?: string | null }>;
  steps?: string[];
  seconds?: number;
  planner?: string;
  open: boolean;
}) {
  if (!open || (!trace?.length && !steps?.length)) return null;
  return (
    <section aria-label="How I got here" className="anim-rise flex flex-col gap-3 rounded-[22px] bg-soft px-[18px] py-4 text-sm">
      {trace && trace.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {trace.map((t, i) => (
            <ToolRow key={`${t.tool}-${i}`} t={{ tool: t.tool, status: t.success ? 'done' : 'failed', duration_ms: t.duration_ms, error: t.error }} />
          ))}
        </ul>
      )}
      {steps && steps.length > 0 && (
        <ol className="m-0 flex list-none flex-col gap-3 border-t border-line p-0 pt-3">
          {steps.map((s, i) => (
            <li key={i} className="flex gap-3">
              <span className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-ink text-xs font-bold text-white">{i + 1}</span>
              <span className="pt-0.5">{s}</span>
            </li>
          ))}
        </ol>
      )}
      <p className="m-0 text-xs text-muted">
        {seconds != null && <>Answered in {seconds.toFixed(1)}s</>}
        {planner && <> · {planner === 'llm' ? 'LLM-planned' : 'rule-planned'}</>}
      </p>
    </section>
  );
}
