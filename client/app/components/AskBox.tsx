'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowUp, Clock, Search } from 'lucide-react';
import { askHref } from '../../lib/api';

export const TIME_RANGES = [
  ['7d', '7 days'],
  ['1d', '24 hours'],
  ['30d', '30 days'],
  ['90d', '90 days'],
  ['1y', '1 year'],
] as const;

const HINTS = [
  'Ask about a token, protocol, wallet or link',
  'Which DEXs lead on Arbitrum today?',
  'Summarise https://ethereum.org/en/roadmap/',
  'Is PEPE liquid? Show its DEX pairs',
];

/** The centered home ask box: submitting opens a chat that asks the question right away. */
export default function AskBox() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [range, setRange] = useState('7d');
  const [hint, setHint] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setHint((h) => (h + 1) % HINTS.length), 3200);
    return () => clearInterval(id);
  }, []);

  const submit = () => {
    const q = query.trim();
    if (q) router.push(askHref(q, range));
  };

  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
      className="askbox flex w-full max-w-[720px] flex-col gap-1.5 rounded-[29px] border border-[#dcdde2] bg-white p-[5px] pl-[18px] text-left sm:rounded-[32px] sm:p-2.5 sm:pl-6"
    >
      <div className="flex min-h-12 items-center gap-3 sm:min-h-[52px]">
        <Search className="h-5 w-5 shrink-0 text-muted sm:h-[22px] sm:w-[22px]" aria-hidden="true" />
        <label htmlFor="ask" className="sr-only">Ask a question</label>
        <input
          id="ask"
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={HINTS[hint]}
          autoComplete="off"
          className="min-w-0 flex-1 border-0 bg-transparent text-base text-ink placeholder:text-muted focus:outline-none sm:text-[19px]"
        />
        <button
          type="submit"
          aria-label="Ask"
          disabled={!query.trim()}
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-ink text-white transition-[transform,background-color,color] hover:bg-accent hover:text-ink active:scale-90 disabled:cursor-not-allowed disabled:bg-field disabled:text-muted sm:h-[52px] sm:w-[52px] touch-manipulation"
        >
          <ArrowUp className="h-[22px] w-[22px]" strokeWidth={2.4} aria-hidden="true" />
        </button>
      </div>
      <div className="hidden flex-wrap items-center gap-2 pb-1 pl-[34px] sm:flex">
        <label className="inline-flex min-h-9 items-center gap-1.5 rounded-full bg-field px-3 text-[13px] font-semibold text-ink-3">
          <Clock className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="sr-only">Time range</span>
          <select value={range} onChange={(e) => setRange(e.target.value)} className="cursor-pointer border-0 bg-transparent font-semibold focus:outline-none">
            {TIME_RANGES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </label>
        <span className="text-[13px] text-muted">Paste a link or connect a wallet for on-chain questions</span>
      </div>
    </form>
  );
}
