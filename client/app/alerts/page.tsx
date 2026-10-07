'use client';

import { useCallback, useEffect, useState } from 'react';
import { Bell, BellOff, Check, Plus, Trash2 } from 'lucide-react';
import PageShell, { RequireSignIn } from '../components/PageShell';
import Markdown from '../components/Markdown';
import { apiJson } from '../../lib/auth';
import { BTN_DANGER, BTN_PRIMARY, BTN_SECONDARY, CARD, INPUT, LABEL, NOTE_ERROR, NOTE_INFO, errorText, formatWhen } from '../components/ui';

interface Rule {
  id: string;
  name: string;
  query_text: string;
  condition_text: string | null;
  interval_minutes: number;
  enabled: boolean;
  next_run_at: string;
  last_run_at: string | null;
  last_error: string | null;
}
interface InboxItem { id: string; title: string; summary: string; created_at: string; read_at: string | null }
interface Limits { max_rules: number; min_interval_minutes: number; max_runs_per_day: number }

const INTERVALS: Array<[string, number]> = [['Every 15 minutes', 15], ['Hourly', 60], ['Every 6 hours', 360], ['Twice a day', 720], ['Daily', 1440], ['Weekly', 10080]];
const intervalLabel = (m: number) => INTERVALS.find(([, v]) => v === m)?.[0] ?? `Every ${m} min`;

export default function AlertsPage() {
  return (
    <PageShell
      title="Alerts & inbox"
      description="Ask a question once and have the agent re-run it on a schedule. Results land in your inbox, optionally only when a condition you describe is met."
    >
      <RequireSignIn>
        <Inbox />
        <Rules />
      </RequireSignIn>
    </PageShell>
  );
}

function Inbox() {
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setItems((await apiJson<{ items: InboxItem[] }>('/api/inbox')).items); setError(null); }
    catch (e) { setError(errorText(e)); setItems((c) => c ?? []); }
  }, []);
  useEffect(() => {
    void load();
    const id = setInterval(load, 60_000);
    return () => clearInterval(id);
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => { try { await fn(); await load(); } catch (e) { setError(errorText(e)); } };
  const unread = items?.filter((i) => !i.read_at).length ?? 0;

  return (
    <section className={CARD} aria-labelledby="inbox-h">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="inbox-h" className="m-0 font-display text-2xl font-bold tracking-[-0.4px]">Inbox {unread > 0 && <span className="rounded-full bg-accent px-2.5 py-0.5 align-middle text-sm">{unread} new</span>}</h2>
        {unread > 0 && <button type="button" onClick={() => act(() => apiJson('/api/inbox/read', { method: 'POST', body: JSON.stringify({}) }))} className={`${BTN_SECONDARY} ml-auto`}><Check className="h-4 w-4" aria-hidden="true" />Mark all read</button>}
      </div>
      {error && <p role="alert" className={`${NOTE_ERROR} mt-3`}>{error}</p>}
      <ul className="mt-4 flex list-none flex-col gap-2.5 p-0">
        {items === null && [0, 1].map((i) => <li key={i} className="shimmer-tint h-16 rounded-2xl" />)}
        {items?.length === 0 && <li className="text-sm text-muted">Nothing yet. Alert results show up here.</li>}
        {items?.map((item) => {
          const expanded = open === item.id;
          return (
            <li key={item.id} className={`rounded-2xl p-3.5 ${item.read_at ? 'bg-soft' : 'bg-butter/60'}`}>
              <div className="flex items-start gap-2">
                <button type="button" aria-expanded={expanded} className="min-w-0 flex-1 text-left"
                  onClick={() => { setOpen(expanded ? null : item.id); if (!item.read_at) void act(() => apiJson('/api/inbox/read', { method: 'POST', body: JSON.stringify({ id: item.id }) })); }}>
                  <span className="block font-semibold">{item.title}</span>
                  <span className="block text-xs text-muted">{formatWhen(item.created_at)}{item.read_at ? '' : ' · new'}</span>
                </button>
                <button type="button" aria-label={`Delete ${item.title}`} title="Delete" onClick={() => act(() => apiJson(`/api/inbox/${item.id}`, { method: 'DELETE' }))}
                  className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink-3 hover:bg-field-hover sm:h-9 sm:w-9"><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
              </div>
              {expanded && <div className="mt-3 border-t border-line pt-3"><Markdown>{item.summary}</Markdown></div>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Rules() {
  const [rules, setRules] = useState<Rule[] | null>(null);
  const [limits, setLimits] = useState<Limits | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: '', query: '', condition: '', interval: 1440 });

  const load = useCallback(async () => {
    try {
      const r = await apiJson<{ alerts: Rule[]; limits: Limits }>('/api/alerts');
      setRules(r.alerts); setLimits(r.limits); setError(null);
    } catch (e) { setError(errorText(e)); setRules((c) => c ?? []); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); await load(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  const full = !!limits && (rules?.length ?? 0) >= limits.max_rules;

  return (
    <section className={CARD} aria-labelledby="rules-h">
      <h2 id="rules-h" className="m-0 font-display text-2xl font-bold tracking-[-0.4px]">Scheduled research</h2>
      <p className="mt-1.5 text-sm text-muted">{limits ? `Up to ${limits.max_rules} alerts, each at most ${limits.max_runs_per_day} runs a day.` : ' '} Runs happen in the background, even when you are away.</p>
      {error && <p role="alert" className={`${NOTE_ERROR} mt-3`}>{error}</p>}

      <form className="mt-5 grid gap-3 sm:grid-cols-2" onSubmit={(e) => {
        e.preventDefault();
        void act(async () => {
          await apiJson('/api/alerts', { method: 'POST', body: JSON.stringify({ name: form.name, query_text: form.query, condition_text: form.condition || undefined, interval_minutes: form.interval }) });
          setForm({ name: '', query: '', condition: '', interval: form.interval });
        });
      }}>
        <div><label className={LABEL} htmlFor="a-name">Name</label>
          <input id="a-name" required maxLength={80} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Aave TVL check" className={INPUT} /></div>
        <div><label className={LABEL} htmlFor="a-int">How often</label>
          <select id="a-int" value={form.interval} onChange={(e) => setForm({ ...form, interval: Number(e.target.value) })} className={INPUT}>{INTERVALS.map(([l, v]) => <option key={v} value={v}>{l}</option>)}</select></div>
        <div className="sm:col-span-2"><label className={LABEL} htmlFor="a-q">Question to ask</label>
          <input id="a-q" required maxLength={1000} value={form.query} onChange={(e) => setForm({ ...form, query: e.target.value })} placeholder="How has Aave TVL changed in the last 7 days?" className={INPUT} /></div>
        <div className="sm:col-span-2"><label className={LABEL} htmlFor="a-c">Only notify me when… <span className="font-normal text-muted">(optional)</span></label>
          <input id="a-c" maxLength={300} value={form.condition} onChange={(e) => setForm({ ...form, condition: e.target.value })} placeholder="TVL dropped by more than 10%" className={INPUT} />
          <p className="mt-1 text-xs text-muted">Leave empty to get every result. Otherwise the agent checks your condition against each result and stays quiet when it is not met.</p></div>
        <div className="sm:col-span-2"><button type="submit" disabled={busy || full || !form.name.trim() || !form.query.trim()} className={BTN_PRIMARY}><Plus className="h-4 w-4" aria-hidden="true" />Create alert</button>
          {full && <span className="ml-3 text-sm text-muted">You have reached the limit.</span>}</div>
      </form>

      <ul className="mt-6 flex list-none flex-col gap-2.5 p-0">
        {rules === null && <li className="shimmer-tint h-16 rounded-2xl" />}
        {rules?.length === 0 && <li className="text-sm text-muted">No alerts yet.</li>}
        {rules?.map((r) => (
          <li key={r.id} className={`rounded-2xl bg-soft p-3.5 ${r.enabled ? '' : 'opacity-70'}`}>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
              <div className="min-w-0 flex-1">
                <p className="m-0 font-semibold">{r.name} <span className="text-xs font-normal text-muted">· {intervalLabel(r.interval_minutes)}</span></p>
                <p className="m-0 mt-0.5 break-words text-sm">{r.query_text}</p>
                {r.condition_text && <p className="m-0 mt-0.5 text-sm text-muted">Notify when: {r.condition_text}</p>}
                <p className="m-0 mt-1 text-xs text-muted">Last run {r.last_run_at ? formatWhen(r.last_run_at) : 'never'}{r.enabled ? ` · next ${formatWhen(r.next_run_at)}` : ' · paused'}</p>
                {r.last_error && <p className="m-0 mt-1 text-xs text-[#a3231a]">Last run failed: {r.last_error}</p>}
              </div>
              <div className="flex shrink-0 gap-1.5">
                <button type="button" disabled={busy} className={BTN_SECONDARY} onClick={() => act(() => apiJson(`/api/alerts/${r.id}`, { method: 'PATCH', body: JSON.stringify({ enabled: !r.enabled }) }))}>
                  {r.enabled ? <BellOff className="h-4 w-4" aria-hidden="true" /> : <Bell className="h-4 w-4" aria-hidden="true" />}{r.enabled ? 'Pause' : 'Resume'}
                </button>
                <button type="button" disabled={busy} className={BTN_DANGER} aria-label={`Delete ${r.name}`} onClick={() => window.confirm(`Delete the alert “${r.name}”?`) && act(() => apiJson(`/api/alerts/${r.id}`, { method: 'DELETE' }))}><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
              </div>
            </div>
          </li>
        ))}
      </ul>
      {rules && rules.length > 0 && <p className={`${NOTE_INFO} mt-4`}>Alerts run on the server’s schedule, so a result can arrive a few minutes after its time.</p>}
    </section>
  );
}
