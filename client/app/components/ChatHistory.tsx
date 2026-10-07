'use client';

import { useEffect, useRef, useState } from 'react';
import { History } from 'lucide-react';
import { apiJson } from '../../lib/auth';
import { errorText, formatWhen } from './ui';

interface Row { id: string; title: string | null; message_count: number; last_activity: string }

/** Dropdown of the signed-in wallet's earlier conversations; picking one asks the chat to open it. */
export default function ChatHistory({ activeId, onSelect }: { activeId: string | null; onSelect: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    apiJson<{ conversations: Row[] }>('/api/conversations').then((r) => setRows(r.conversations)).catch((e) => { setError(errorText(e)); setRows([]); });
    const close = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  return (
    <div className="relative" ref={root}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="Conversation history"
        className="inline-flex h-11 w-11 items-center justify-center gap-1.5 rounded-full bg-field text-sm font-semibold text-ink transition-colors hover:bg-field-hover sm:w-auto sm:px-4 touch-manipulation"
      >
        <History className="h-[18px] w-[18px] sm:h-4 sm:w-4" aria-hidden="true" />
        <span className="hidden sm:inline">History</span>
      </button>
      {open && (
        <div className="absolute right-0 top-full z-20 mt-2 max-h-[60vh] w-[min(22rem,calc(100vw-1.5rem))] overflow-y-auto rounded-2xl border border-line bg-white p-1.5 shadow-xl">
          {rows === null && <p className="m-0 p-3 text-sm text-muted">Loading…</p>}
          {error && <p role="alert" className="m-0 p-3 text-sm text-[#a3231a]">{error}</p>}
          {rows?.length === 0 && !error && <p className="m-0 p-3 text-sm text-muted">No saved conversations yet.</p>}
          {rows?.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => { setOpen(false); onSelect(r.id); }}
              aria-current={r.id === activeId ? 'true' : undefined}
              className={`flex min-h-11 w-full flex-col items-start rounded-xl px-3 py-2 text-left hover:bg-field ${r.id === activeId ? 'bg-field' : ''}`}
            >
              <span className="line-clamp-1 w-full text-sm font-semibold">{r.title ?? 'Untitled chat'}</span>
              <span className="text-xs text-muted">{formatWhen(r.last_activity)} · {r.message_count} messages</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
