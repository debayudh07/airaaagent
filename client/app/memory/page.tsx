'use client';

import { useCallback, useEffect, useState } from 'react';
import { Check, Download, Pencil, Pin, PinOff, Plus, RefreshCw, Trash2, X } from 'lucide-react';
import PageShell, { RequireSignIn } from '../components/PageShell';
import { useAuth } from '../components/AuthProvider';
import { apiFetch, apiJson } from '../../lib/auth';
import { BTN_DANGER, BTN_PRIMARY, BTN_SECONDARY, CARD, INPUT, LABEL, NOTE_ERROR, NOTE_INFO, errorText, formatWhen } from '../components/ui';

type Kind = 'fact' | 'preference' | 'finding' | 'summary';
interface Memory {
  id: string;
  kind: Kind;
  content: string;
  importance: number;
  pinned: boolean;
  created_at: string;
  last_accessed: string | null;
  access_count: number;
}
interface WatchItem { id: string; entity_type: 'token' | 'protocol' | 'chain'; entity_id: string; note: string | null }
interface Snapshot { id: string; chain: string; fetched_at: string; summary: string }
interface Me { wallet: { address: string; settings: { memory_enabled?: boolean } }; counts: Record<string, number> }

const KINDS: Kind[] = ['fact', 'preference', 'finding', 'summary'];
const KIND_TONE: Record<Kind, string> = { fact: 'bg-sky text-[#1e3a8a]', preference: 'bg-butter text-[#6b4e00]', finding: 'bg-mint text-[#0f5b3a]', summary: 'bg-lilac text-[#3b2a7a]' };
const CHAINS = ['ethereum', 'base', 'arbitrum', 'optimism', 'polygon', 'bsc', 'avalanche', 'linea'];

export default function MemoryPage() {
  return (
    <PageShell
      title="Memory & watchlist"
      description="What the agent remembers about you, the assets you follow, and the data held for your wallet. You can edit or erase any of it."
    >
      <RequireSignIn>
        <MemorySection />
        <WatchlistSection />
        <PortfolioSection />
        <DataSection />
      </RequireSignIn>
    </PageShell>
  );
}

// ------------------------------------------------------------------ memories
function MemorySection() {
  const [items, setItems] = useState<Memory[] | null>(null);
  const [total, setTotal] = useState(0);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [kind, setKind] = useState<Kind>('fact');
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [list, me] = await Promise.all([
        apiJson<{ memories: Memory[]; total: number }>('/api/memories'),
        apiJson<Me>('/api/me'),
      ]);
      setItems(list.memories);
      setTotal(list.total);
      setEnabled(me.wallet.settings.memory_enabled !== false);
      setError(null);
    } catch (e) {
      setError(errorText(e));
      setItems((cur) => cur ?? []);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const toggle = () => run(async () => {
    const r = await apiJson<{ settings: { memory_enabled: boolean } }>('/api/me/settings', { method: 'PATCH', body: JSON.stringify({ memory_enabled: !enabled }) });
    setEnabled(r.settings.memory_enabled);
  });
  const add = () => run(async () => {
    await apiJson('/api/memories', { method: 'POST', body: JSON.stringify({ kind, content: draft, pinned: true }) });
    setDraft('');
  });
  const save = () => run(async () => {
    if (!editing) return;
    await apiJson(`/api/memories/${editing.id}`, { method: 'PATCH', body: JSON.stringify({ content: editing.text }) });
    setEditing(null);
  });
  const pin = (m: Memory) => run(() => apiJson(`/api/memories/${m.id}`, { method: 'PATCH', body: JSON.stringify({ pinned: !m.pinned }) }));
  const remove = (m: Memory) => run(() => apiJson(`/api/memories/${m.id}`, { method: 'DELETE' }));
  const forgetAll = () => {
    if (window.confirm('Forget everything the agent remembers about you? This cannot be undone.')) {
      void run(() => apiJson('/api/memories', { method: 'DELETE', body: JSON.stringify({ confirm: true }) }));
    }
  };

  return (
    <section className={CARD} aria-labelledby="memory-h">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="memory-h" className="m-0 font-display text-2xl font-bold tracking-[-0.4px]">What I remember <span className="text-muted">({total})</span></h2>
        <label className="ml-auto inline-flex min-h-11 cursor-pointer items-center gap-2.5 text-sm font-semibold">
          <input type="checkbox" role="switch" checked={enabled ?? true} disabled={enabled === null || busy} onChange={toggle} className="h-5 w-5 accent-[#0b0d12]" />
          Learn from my chats
        </label>
      </div>
      <p className="mt-1.5 text-sm text-muted">
        After you chat, the agent keeps short notes (never prices or secrets) so later answers fit you. Turn this off to stop new notes; existing ones stay until you delete them.
      </p>
      {enabled === false && <p className={`${NOTE_INFO} mt-3`}>Memory is paused: nothing is recalled in answers or saved from chats.</p>}
      {error && <p role="alert" className={`${NOTE_ERROR} mt-3`}>{error}</p>}

      <form className="mt-5 flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) void add(); }}>
        <label className="sr-only" htmlFor="mem-kind">Kind</label>
        <select id="mem-kind" value={kind} onChange={(e) => setKind(e.target.value as Kind)} className={`${INPUT} sm:w-36`}>
          {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
        </select>
        <label className="sr-only" htmlFor="mem-text">Something to remember</label>
        <input id="mem-text" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={2000} placeholder="Tell me something to remember, e.g. “I mostly use Arbitrum”" className={INPUT} />
        <button type="submit" disabled={busy || !draft.trim()} className={BTN_PRIMARY}><Plus className="h-4 w-4" aria-hidden="true" />Add</button>
      </form>

      <ul className="mt-5 flex list-none flex-col gap-2.5 p-0">
        {items === null && [0, 1, 2].map((i) => <li key={i} className="shimmer-tint h-16 rounded-2xl" />)}
        {items?.length === 0 && <li className="text-sm text-muted">Nothing remembered yet. Chat for a while, or add a note above.</li>}
        {items?.map((m) => (
          <li key={m.id} className="flex flex-col gap-2 rounded-2xl bg-soft p-3.5 sm:flex-row sm:items-start">
            <span className={`w-fit shrink-0 rounded-full px-2.5 py-0.5 text-xs font-bold ${KIND_TONE[m.kind]}`}>{m.kind}</span>
            <div className="min-w-0 flex-1">
              {editing?.id === m.id ? (
                <input autoFocus value={editing.text} onChange={(e) => setEditing({ id: m.id, text: e.target.value })} maxLength={2000} className={INPUT}
                  onKeyDown={(e) => { if (e.key === 'Enter') void save(); if (e.key === 'Escape') setEditing(null); }} aria-label="Edit memory" />
              ) : (
                <p className="m-0 break-words">{m.content}</p>
              )}
              <p className="m-0 mt-1 text-xs text-muted">
                Saved {formatWhen(m.created_at)} · used {m.access_count}×{m.pinned ? ' · pinned' : ''}
              </p>
            </div>
            <div className="flex shrink-0 gap-1">
              {editing?.id === m.id ? (
                <>
                  <IconBtn label="Save" onClick={save} disabled={busy || !editing.text.trim()}><Check className="h-4 w-4" /></IconBtn>
                  <IconBtn label="Cancel" onClick={() => setEditing(null)}><X className="h-4 w-4" /></IconBtn>
                </>
              ) : (
                <>
                  <IconBtn label={m.pinned ? 'Unpin' : 'Pin (always prefer this)'} onClick={() => pin(m)} disabled={busy}>{m.pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}</IconBtn>
                  <IconBtn label="Edit" onClick={() => setEditing({ id: m.id, text: m.content })}><Pencil className="h-4 w-4" /></IconBtn>
                  <IconBtn label="Delete" onClick={() => remove(m)} disabled={busy}><Trash2 className="h-4 w-4" /></IconBtn>
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
      {total > 0 && <button type="button" onClick={forgetAll} disabled={busy} className={`${BTN_DANGER} mt-4`}>Forget everything</button>}
    </section>
  );
}

function IconBtn({ label, onClick, disabled, children }: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label}
      className="inline-flex h-11 w-11 items-center justify-center rounded-full text-ink-3 hover:bg-field-hover disabled:opacity-40 sm:h-9 sm:w-9">
      {children}
    </button>
  );
}

// ------------------------------------------------------------------ watchlist
function WatchlistSection() {
  const [items, setItems] = useState<WatchItem[] | null>(null);
  const [type, setType] = useState<WatchItem['entity_type']>('token');
  const [id, setId] = useState('');
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems((await apiJson<{ items: WatchItem[] }>('/api/watchlist')).items);
      setError(null);
    } catch (e) {
      setError(errorText(e));
      setItems((cur) => cur ?? []);
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try { await fn(); await load(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  return (
    <section className={CARD} aria-labelledby="watch-h">
      <h2 id="watch-h" className="m-0 font-display text-2xl font-bold tracking-[-0.4px]">Watchlist</h2>
      <p className="mt-1.5 text-sm text-muted">Tokens, protocols and chains you follow. Answers take them into account, and notes help the agent understand why you care.</p>
      {error && <p role="alert" className={`${NOTE_ERROR} mt-3`}>{error}</p>}
      <form className="mt-5 grid gap-2 sm:grid-cols-[9rem_1fr_1.4fr_auto]" onSubmit={(e) => {
        e.preventDefault();
        if (id.trim()) void act(async () => {
          await apiJson('/api/watchlist', { method: 'POST', body: JSON.stringify({ entity_type: type, entity_id: id, note: note || undefined }) });
          setId(''); setNote('');
        });
      }}>
        <div><label className="sr-only" htmlFor="w-type">Type</label>
          <select id="w-type" value={type} onChange={(e) => setType(e.target.value as WatchItem['entity_type'])} className={INPUT}>
            <option value="token">token</option><option value="protocol">protocol</option><option value="chain">chain</option>
          </select></div>
        <div><label className="sr-only" htmlFor="w-id">Symbol, slug or chain</label>
          <input id="w-id" value={id} onChange={(e) => setId(e.target.value)} maxLength={80} placeholder={type === 'token' ? 'ETH' : type === 'protocol' ? 'aave' : 'arbitrum'} className={INPUT} /></div>
        <div><label className="sr-only" htmlFor="w-note">Note</label>
          <input id="w-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder="Why? (optional)" className={INPUT} /></div>
        <button type="submit" disabled={busy || !id.trim()} className={BTN_PRIMARY}><Plus className="h-4 w-4" aria-hidden="true" />Add</button>
      </form>
      <ul className="mt-4 flex list-none flex-wrap gap-2 p-0">
        {items === null && <li className="shimmer-tint h-10 w-40 rounded-full" />}
        {items?.length === 0 && <li className="text-sm text-muted">Nothing on your watchlist yet.</li>}
        {items?.map((w) => (
          <li key={w.id} className="inline-flex items-center gap-1 rounded-full bg-field py-1 pl-3.5 pr-1 text-sm" title={w.note ?? undefined}>
            <span className="font-semibold">{w.entity_type === 'token' ? w.entity_id.toUpperCase() : w.entity_id}</span>
            <span className="text-xs text-muted">{w.entity_type}</span>
            {w.note && <span className="hidden max-w-[16rem] truncate text-xs text-muted sm:inline">· {w.note}</span>}
            <IconBtn label={`Remove ${w.entity_id}`} onClick={() => act(() => apiJson(`/api/watchlist/${w.id}`, { method: 'DELETE' }))} disabled={busy}><X className="h-4 w-4" /></IconBtn>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ------------------------------------------------------------------ portfolio
function PortfolioSection() {
  const { wallet } = useAuth();
  const [snaps, setSnaps] = useState<Snapshot[] | null>(null);
  const [chain, setChain] = useState('ethereum');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setSnaps((await apiJson<{ snapshots: Snapshot[] }>('/api/portfolio')).snapshots); } catch (e) { setError(errorText(e)); setSnaps((c) => c ?? []); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const refresh = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiJson('/api/portfolio/refresh', { method: 'POST', body: JSON.stringify({ chain }) });
      await load();
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  return (
    <section className={CARD} aria-labelledby="pf-h">
      <h2 id="pf-h" className="m-0 font-display text-2xl font-bold tracking-[-0.4px]">Portfolio snapshot</h2>
      <p className="mt-1.5 text-sm text-muted">
        Reads the public on-chain activity of <span className="tabular font-semibold">{wallet?.address.slice(0, 6)}…{wallet?.address.slice(-4)}</span> so answers can refer to what you hold.
        It is a snapshot, not a live balance, and only you and the agent see it.
      </p>
      {error && <p role="alert" className={`${NOTE_ERROR} mt-3`}>{error}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="pf-chain">Chain</label>
        <select id="pf-chain" value={chain} onChange={(e) => setChain(e.target.value)} className={`${INPUT} w-44`}>{CHAINS.map((c) => <option key={c}>{c}</option>)}</select>
        <button type="button" onClick={refresh} disabled={busy} className={BTN_SECONDARY}><RefreshCw className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} aria-hidden="true" />{busy ? 'Reading chain…' : 'Take snapshot'}</button>
      </div>
      <ul className="mt-4 flex list-none flex-col gap-2.5 p-0">
        {snaps?.length === 0 && <li className="text-sm text-muted">No snapshot yet.</li>}
        {snaps?.map((s) => (
          <li key={s.id} className="rounded-2xl bg-soft p-3.5 text-sm">
            <p className="m-0 break-words">{s.summary}</p>
            <p className="m-0 mt-1 text-xs text-muted">{s.chain} · {formatWhen(s.fetched_at)}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ------------------------------------------------------------------ export & erase
function DataSection() {
  const { signOut } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState('');
  const [open, setOpen] = useState(false);

  const download = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch('/api/me/export');
      if (!res.ok) throw new Error(`Export failed (HTTP ${res.status})`);
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement('a'), { href: url, download: 'airaa-export.json' });
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  const erase = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiJson('/api/me', { method: 'DELETE', body: JSON.stringify({ confirm: 'DELETE' }) });
      await signOut();
      window.location.href = '/';
    } catch (e) { setError(errorText(e)); setBusy(false); }
  };

  return (
    <section className={CARD} aria-labelledby="data-h">
      <h2 id="data-h" className="m-0 font-display text-2xl font-bold tracking-[-0.4px]">Your data</h2>
      <p className="mt-1.5 text-sm text-muted">Download everything held about your wallet, or erase your account. Encrypted vault files are exported as metadata only (they stay encrypted).</p>
      {error && <p role="alert" className={`${NOTE_ERROR} mt-3`}>{error}</p>}
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" onClick={download} disabled={busy} className={BTN_SECONDARY}><Download className="h-4 w-4" aria-hidden="true" />Export my data</button>
        <button type="button" onClick={() => setOpen((o) => !o)} className={BTN_DANGER}>Erase my account…</button>
      </div>
      {open && (
        <div className="mt-4 rounded-2xl bg-[#fff3f1] p-4">
          <p className="m-0 text-sm"><strong>This permanently deletes</strong> your conversations, memories, watchlist, snapshots, alerts, shares and encrypted files. It cannot be undone.</p>
          <label htmlFor="erase" className={`${LABEL} mt-3`}>Type DELETE to confirm</label>
          <div className="flex flex-wrap gap-2">
            <input id="erase" value={confirm} onChange={(e) => setConfirm(e.target.value)} className={`${INPUT} max-w-[14rem]`} autoComplete="off" />
            <button type="button" onClick={erase} disabled={busy || confirm !== 'DELETE'} className={BTN_DANGER}>Erase everything</button>
          </div>
        </div>
      )}
    </section>
  );
}
