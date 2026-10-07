'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import Logo from './Logo';
import WalletButton from './WalletButton';
import { useAuth } from './AuthProvider';
import { BTN_PRIMARY, NOTE_INFO } from './ui';

const NAV = [
  ['/main-chat', 'Chat'],
  ['/memory', 'Memory'],
  ['/vault', 'Vault'],
  ['/alerts', 'Alerts'],
] as const;

/** Header + centered column shared by the account pages. */
export default function PageShell({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-dvh bg-bg text-[15px] leading-normal text-ink">
      <header className="sticky top-0 z-10 border-b border-line-2 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1360px] items-center gap-3 px-4 py-2.5 sm:gap-4 sm:px-6 sm:py-3.5">
          <Logo />
          <nav aria-label="Main" className="ml-auto hidden items-center gap-1 sm:flex">
            {NAV.map(([href, label]) => (
              <Link
                key={href}
                href={href}
                aria-current={pathname === href ? 'page' : undefined}
                className={`inline-flex min-h-11 items-center rounded-full px-3.5 font-semibold transition-colors hover:bg-field ${pathname === href ? 'bg-field text-ink' : 'text-ink-3'}`}
              >
                {label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto sm:ml-0">
            <WalletButton />
          </div>
        </div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-3 pb-2 sm:hidden">
          {NAV.map(([href, label]) => (
            <Link key={href} href={href} className={`inline-flex min-h-10 shrink-0 items-center rounded-full px-3.5 text-sm font-semibold ${pathname === href ? 'bg-field text-ink' : 'text-ink-3'}`}>
              {label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-[920px] px-4 pb-20 pt-8 sm:px-6 sm:pt-12">
        <h1 className="m-0 font-display text-[30px] font-extrabold leading-tight tracking-[-1px] sm:text-[40px]">{title}</h1>
        {description && <p className="mt-2.5 max-w-[640px] text-muted">{description}</p>}
        <div className="mt-8 flex flex-col gap-6">{children}</div>
      </main>
    </div>
  );
}

/** Renders `children` only for a signed-in wallet; otherwise explains what to do. */
export function RequireSignIn({ children }: { children: ReactNode }) {
  const { enabled, status, signIn, busy, error } = useAuth();
  if (status === 'signed-in') return <>{children}</>;
  if (status === 'unknown') return <div className="shimmer-tint h-40 rounded-3xl" aria-label="Loading" />;
  if (!enabled) {
    return <p className={NOTE_INFO}>Wallet accounts are not enabled on this server, so there is nothing to manage here yet.</p>;
  }
  return (
    <div className="rounded-3xl bg-field p-6 sm:p-8">
      <h2 className="m-0 font-display text-2xl font-bold tracking-[-0.4px]">Sign in with your wallet</h2>
      <p className="mt-2 max-w-[520px] text-muted">
        Connect a wallet with the button in the corner, then sign a message to prove it is yours. It is free and does not
        authorise any transaction.
      </p>
      <button type="button" onClick={() => void signIn()} disabled={busy} className={`${BTN_PRIMARY} mt-4`}>
        {busy ? 'Waiting for signature…' : 'Sign in'}
      </button>
      {error && <p role="alert" className="mt-3 text-sm text-[#a3231a]">{error}</p>}
    </div>
  );
}
