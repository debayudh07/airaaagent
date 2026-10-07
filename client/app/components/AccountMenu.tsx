'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { Bell, ChevronDown, Lock, LogOut, Brain } from 'lucide-react';
import { useAccount } from 'wagmi';
import { apiJson } from '../../lib/auth';
import { useAuth } from './AuthProvider';
import { BTN_PRIMARY } from './ui';

const ITEM = 'flex min-h-11 items-center gap-2.5 rounded-xl px-3 text-sm font-semibold text-ink hover:bg-field';

/** Next to the wallet button: "Sign in" for a connected guest, an account menu once signed in. Hidden if the server has no accounts. */
export default function AccountMenu() {
  const { enabled, status, signIn, signOut, busy, error, clearError } = useAuth();
  const { isConnected } = useAccount();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const root = useRef<HTMLDivElement>(null);

  // Unread alert count: cheap, so poll while signed in.
  useEffect(() => {
    if (status !== 'signed-in') return;
    let stop = false;
    const load = async () => {
      try {
        const r = await apiJson<{ unread: number }>('/api/inbox/unread-count');
        if (!stop) setUnread(r.unread);
      } catch {
        /* alerts may be off; the badge simply stays hidden */
      }
    };
    void load();
    const id = setInterval(load, 60_000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [status]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !root.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', esc);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', esc);
    };
  }, [open]);

  if (!enabled || !isConnected || status === 'unknown') return null;

  if (status !== 'signed-in') {
    return (
      <div className="relative">
        <button type="button" onClick={() => void signIn()} disabled={busy} className={BTN_PRIMARY}>
          {busy ? 'Check your wallet…' : 'Sign in'}
        </button>
        {error && (
          <p role="alert" className="absolute right-0 top-full z-20 mt-2 w-64 rounded-2xl bg-[#ffe4e1] p-3 text-xs text-[#a3231a] shadow-lg">
            {error}{' '}
            <button type="button" onClick={clearError} className="font-bold underline">Dismiss</button>
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="relative" ref={root}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="relative inline-flex min-h-11 items-center gap-1.5 rounded-full bg-field px-4 text-sm font-semibold text-ink hover:bg-field-hover touch-manipulation"
      >
        Account
        <ChevronDown className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-accent px-1 text-[11px] font-bold text-ink">
            <span className="sr-only">{unread} unread alerts</span>
            <span aria-hidden="true">{unread > 9 ? '9+' : unread}</span>
          </span>
        )}
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-full z-20 mt-2 w-56 rounded-2xl border border-line bg-white p-1.5 shadow-xl">
          <Link role="menuitem" href="/memory" className={ITEM} onClick={() => setOpen(false)}><Brain className="h-4 w-4" aria-hidden="true" />Memory &amp; watchlist</Link>
          <Link role="menuitem" href="/vault" className={ITEM} onClick={() => setOpen(false)}><Lock className="h-4 w-4" aria-hidden="true" />Encrypted vault</Link>
          <Link role="menuitem" href="/alerts" className={ITEM} onClick={() => setOpen(false)}>
            <Bell className="h-4 w-4" aria-hidden="true" />Alerts &amp; inbox
            {unread > 0 && <span className="ml-auto rounded-full bg-accent px-2 text-xs font-bold">{unread}</span>}
          </Link>
          <button type="button" role="menuitem" className={`${ITEM} w-full text-left`} onClick={() => { setOpen(false); void signOut(); }}>
            <LogOut className="h-4 w-4" aria-hidden="true" />Sign out
          </button>
        </div>
      )}
    </div>
  );
}
