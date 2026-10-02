'use client';

import Link from 'next/link';
import { useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { Link2, Search, Wallet } from 'lucide-react';
import { askHref, fetchFeed, type FeedMarket, type FeedNews, type FeedSections } from '../../lib/api';
import { RollingNumber, Sparkline } from './motion';

type Category = 'markets' | 'defi' | 'yields' | 'news' | 'ideas';

const FILTERS: Array<[Category | 'all', string]> = [
  ['all', 'For you'], ['markets', 'Markets'], ['defi', 'DeFi'], ['yields', 'Yields'], ['news', 'News'], ['ideas', 'Ideas to ask'],
];
const REFRESH_MS = 60_000;

// ------------------------------------------------------------------ formatting
export function compactUsd(v: number | null | undefined) {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  if (a >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `$${(v / 1e9).toFixed(a >= 1e11 ? 1 : 2)}B`;
  if (a >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}

function price(v: number | null) {
  if (v == null) return '—';
  if (v >= 10_000) return `$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
  if (v >= 1) return `$${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return `$${v.toPrecision(4)}`;
}

function Change({ value, suffix }: { value: number | null; suffix?: string }) {
  if (value == null) return null;
  const up = value >= 0;
  return (
    <span className={`font-semibold ${up ? 'text-up' : 'text-down'}`}>
      {up ? '▲' : '▼'} {Math.abs(value).toFixed(2)}%{suffix && <span className="font-normal text-muted"> {suffix}</span>}
    </span>
  );
}

const shortDate = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '';

// ------------------------------------------------------------------ pin shell
function Pin({ href, className = '', style, children, ask = true }: {
  href: string; className?: string; style?: CSSProperties; children: ReactNode; ask?: boolean;
}) {
  return (
    <Link href={href} className={`pin anim-rise relative mb-2.5 block rounded-[20px] p-4 text-ink no-underline sm:mb-4 sm:rounded-3xl sm:p-5 ${className}`} style={style}>
      {ask && (
        <span className="pin-ask absolute right-3.5 top-3.5 rounded-full bg-ink px-3.5 py-1.5 text-[13px] font-semibold text-white">Ask</span>
      )}
      {children}
    </Link>
  );
}

const Eyebrow = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <span className={`text-xs font-bold uppercase tracking-[0.6px] ${className}`}>{children}</span>
);

const AVATAR: Record<string, string> = {
  BTC: 'bg-[#ffe3bf] text-[#8a4b00]', ETH: 'bg-[#e3e6fb] text-[#2e3a8c]', SOL: 'bg-[#ddf1ec] text-[#0f5b4c]',
};

// ------------------------------------------------------------------ pins
function PricePin({ m, style }: { m: FeedMarket; style: CSSProperties }) {
  return (
    <Pin href={askHref(`How has ${m.name} (${m.symbol}) moved this week, and why?`)} className="border border-line bg-white" style={style}>
      <div className="flex items-center gap-2.5">
        <span className={`flex h-[38px] w-[38px] items-center justify-center rounded-full font-bold ${AVATAR[m.symbol] ?? 'bg-field text-ink'}`}>
          {m.symbol.slice(0, 1)}
        </span>
        <span className="flex flex-col leading-tight">
          <span className="font-semibold">{m.name}</span>
          <span className="text-[13px] text-muted">{m.symbol}</span>
        </span>
      </div>
      <div className="mt-3 font-display text-[24px] font-bold tracking-[-0.6px] sm:mt-4 sm:text-[32px] sm:tracking-[-0.8px]">
        <RollingNumber value={m.price ?? 0} text={price(m.price)} />
      </div>
      <div className="mt-2 text-sm"><Change value={m.change_24h} suffix="today" /></div>
      <div className="mt-3.5">
        <Sparkline points={m.sparkline_7d} label={`${m.name} price over the last 7 days`} />
      </div>
      <div className="mt-2.5 flex justify-between text-xs text-muted">
        <span>7d <Change value={m.change_7d} /></span>
        <span>CoinGecko</span>
      </div>
    </Pin>
  );
}

function YieldsPin({ rows, style }: { rows: NonNullable<FeedSections['yields']>; style: CSSProperties }) {
  const top = rows.slice(0, 4);
  const max = Math.max(...top.map((r) => r.apy), 1);
  return (
    <Pin href={askHref('Best stablecoin yields right now?')} className="bg-mint" style={style}>
      <Eyebrow className="text-[#0f5b3a]">Yields</Eyebrow>
      <h3 className="mb-4 mt-1.5 font-display text-2xl font-bold leading-[1.1] tracking-[-0.5px]">Best stablecoin yields right now</h3>
      <div className="flex flex-col gap-2.5 text-[13px]">
        {top.map((r, i) => (
          <div key={`${r.project}-${r.symbol}-${i}`}>
            <div className="flex justify-between gap-2">
              <span className="truncate">{r.symbol} · {r.project}</span>
              <span className="tabular font-bold">{r.apy.toFixed(2)}%</span>
            </div>
            <div className="mt-1 h-2 rounded-full bg-ink/[0.08]">
              <div className="anim-grow-x h-full rounded-full bg-ink" style={{ width: `${(r.apy / max) * 100}%`, animationDelay: `${0.5 + i * 0.1}s` }} />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-3.5 text-xs text-[#2f4a3c]">DefiLlama · pools with at least $5M locked</p>
    </Pin>
  );
}

function DexPin({ dex, style }: { dex: NonNullable<FeedSections['dex']>; style: CSSProperties }) {
  const top = dex.top.slice(0, 5);
  const max = Math.max(...top.map((p) => p.total24h ?? 0), 1);
  return (
    <Pin href={askHref(`Which DEXs lead on ${dex.chain} today, and how are their fees?`)} className="bg-sky" style={style}>
      <Eyebrow className="text-[#1e3a8a]">{dex.chain} · 24h</Eyebrow>
      <div className="tabular mt-1.5 font-display text-[34px] font-extrabold tracking-[-1px]">{compactUsd(dex.total24h)}</div>
      <p className="mb-3.5 text-sm text-[#2a3a66]">DEX volume, led by {top[0]?.name}</p>
      <div className="flex h-[120px] items-end gap-2" aria-hidden="true">
        {top.map((p, i) => (
          <div key={p.name} className="anim-grow-y flex-1 rounded-t-lg rounded-b-[3px] bg-[#2448c8]"
            style={{ height: `${Math.max(3, ((p.total24h ?? 0) / max) * 100)}%`, animationDelay: `${0.5 + i * 0.08}s` }} />
        ))}
      </div>
      <div className="mt-1.5 flex gap-2 text-center text-[11px] text-[#2a3a66]">
        {top.map((p) => <span key={p.name} className="flex-1 truncate">{p.name.replace(/ (DEX|Exchange)$/i, '')}</span>)}
      </div>
    </Pin>
  );
}

function StablesPin({ rows, style }: { rows: NonNullable<FeedSections['stablecoins']>; style: CSSProperties }) {
  const [a, b] = rows;
  const total = rows.reduce((s, r) => s + r.circulating_usd, 0) || 1;
  return (
    <Pin href={askHref('How is stablecoin supply split between USDT and USDC, and how is it changing?')} className="bg-lilac" style={style}>
      <Eyebrow className="text-[#4b2c9e]">Stablecoin supply</Eyebrow>
      <div className="mt-3.5 flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-2"><span className="font-semibold">{a.symbol}</span><span className="tabular font-display text-2xl font-bold">{compactUsd(a.circulating_usd)}</span></div>
        <div className="flex h-2.5 overflow-hidden rounded-full bg-ink/[0.08]">
          <div className="anim-grow-x h-full bg-ink" style={{ width: `${(a.circulating_usd / total) * 100}%`, animationDelay: '0.6s' }} />
          {b && <div className="anim-grow-x h-full bg-[#7c5ce0]" style={{ width: `${(b.circulating_usd / total) * 100}%`, animationDelay: '0.8s' }} />}
        </div>
        {b && <div className="flex items-baseline justify-between gap-2"><span className="font-semibold">{b.symbol}</span><span className="tabular font-display text-2xl font-bold">{compactUsd(b.circulating_usd)}</span></div>}
      </div>
      <p className="mt-3 text-xs text-[#3e2f66]">Share of the top {rows.length} stablecoins · DefiLlama</p>
    </Pin>
  );
}

function TvlPin({ rows, style }: { rows: NonNullable<FeedSections['protocols']>; style: CSSProperties }) {
  const max = Math.max(...rows.map((r) => r.tvl_usd), 1);
  const colors = ['bg-ink', 'bg-accent'];
  return (
    <Pin href={askHref(`Compare ${rows.map((r) => r.name).join(' and ')} TVL and fees`)} className="bg-butter" style={style}>
      <Eyebrow className="text-[#6b4e00]">Protocol TVL</Eyebrow>
      <div className="mt-3.5 flex h-[130px] items-end gap-3.5" aria-hidden="true">
        {rows.map((r, i) => (
          <div key={r.slug} className="flex h-full flex-1 flex-col justify-end gap-1.5">
            <span className="tabular text-[15px] font-bold">{compactUsd(r.tvl_usd)}</span>
            <div className={`anim-grow-y rounded-t-[10px] rounded-b ${colors[i % 2]}`} style={{ height: `${(r.tvl_usd / max) * 86}%`, animationDelay: `${0.5 + i * 0.12}s` }} />
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-3.5 text-[13px] font-semibold">
        {rows.map((r) => <span key={r.slug} className="flex-1">{r.name}</span>)}
      </div>
    </Pin>
  );
}

function FeesPin({ fees, style }: { fees: NonNullable<FeedSections['fees']>; style: CSSProperties }) {
  return (
    <Pin href={askHref(`Which protocols earn the most fees on ${fees.chain}?`)} className="border border-line bg-white" style={style}>
      <Eyebrow className="text-muted">Fees · {fees.chain} 24h</Eyebrow>
      <ol className="mt-3 flex flex-col gap-2.5">
        {fees.top.slice(0, 4).map((p, i) => (
          <li key={p.name} className={`flex justify-between gap-2 ${i ? 'border-t border-line-2 pt-2.5' : ''}`}>
            <span className="truncate">{p.name}</span>
            <span className="tabular font-bold">{compactUsd(p.total24h)}</span>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-muted">DefiLlama</p>
    </Pin>
  );
}

const NEWS_TONES = [
  { bg: 'bg-peach', meta: 'text-[#8a3412]', body: 'text-[#4a3328]' },
  { bg: 'border border-line bg-white', meta: 'text-muted', body: 'text-ink-3' },
  { bg: 'bg-field', meta: 'text-muted', body: 'text-ink-3' },
  { bg: 'bg-sky', meta: 'text-[#1e3a8a]', body: 'text-[#2a3a66]' },
];

function NewsPin({ n, tone, style }: { n: FeedNews; tone: number; style: CSSProperties }) {
  const t = NEWS_TONES[tone % NEWS_TONES.length];
  return (
    <Pin href={askHref(`Summarise this article and what it means for crypto markets: ${n.url}`)} className={t.bg} style={style}>
      <span className={`text-xs font-bold ${t.meta}`}>{n.source}{n.published ? ` · ${shortDate(n.published)}` : ''}</span>
      <h3 className="mt-2.5 font-display text-[20px] font-bold leading-[1.2] tracking-[-0.3px]">{n.title}</h3>
      {tone === 0 && n.summary && <p className={`mt-2.5 line-clamp-3 text-sm ${t.body}`}>{n.summary}</p>}
    </Pin>
  );
}

const IDEAS = [
  { q: 'Is PEPE liquid? Show its DEX pairs', note: 'DEX Screener finds tokens too new for the big trackers.', icon: Search, tone: 'ink' },
  { q: 'Summarise https://ethereum.org/en/roadmap/', title: 'Paste a link. The agent reads it.', icon: Link2, tone: 'orange' },
  { q: 'What did my wallet do this week?', note: 'Connect a wallet to ask about balances and transfers.', icon: Wallet, tone: 'ink' },
] as const;

function IdeaPin({ idea, style }: { idea: (typeof IDEAS)[number]; style: CSSProperties }) {
  const ink = idea.tone === 'ink';
  const Icon = idea.icon;
  return (
    <Pin href={askHref(idea.q)} ask={false} className={ink ? 'bg-ink text-white' : 'bg-accent'} style={{ ...style, color: ink ? '#fff' : undefined }}>
      <Icon className={`h-[22px] w-[22px] ${ink ? 'text-accent' : 'text-ink'}`} strokeWidth={2.2} aria-hidden="true" />
      <h3 className="mt-3.5 font-display text-[24px] font-bold leading-[1.12] tracking-[-0.5px]">{'title' in idea ? idea.title : idea.q}</h3>
      {'note' in idea && <p className="mt-2.5 text-sm text-[#b7bcc7]">{idea.note}</p>}
      {'title' in idea && <p className="mt-2.5 text-sm text-[#2b1205]">“{idea.q}”</p>}
      {ink && <span className="mt-4 inline-flex rounded-full bg-white px-3.5 py-2 text-[13px] font-semibold text-ink">Ask this</span>}
    </Pin>
  );
}

function SkeletonPins() {
  const heights = [220, 300, 160, 260, 200, 140, 280, 180];
  return (
    <>
      {heights.map((h, i) => (
        <div key={i} className="shimmer mb-2.5 rounded-3xl sm:mb-4" style={{ height: h, breakInside: 'avoid' }} aria-hidden="true" />
      ))}
    </>
  );
}

// ------------------------------------------------------------------ board
export default function Board() {
  const [sections, setSections] = useState<FeedSections | null>(null);
  const [failed, setFailed] = useState(false);
  const [filter, setFilter] = useState<Category | 'all'>('all');

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    const load = () =>
      fetchFeed(controller.signal)
        .then((f) => { if (alive) { setSections(f.sections); setFailed(!f.success); } })
        .catch(() => { if (alive) setFailed(true); });
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => { alive = false; controller.abort(); clearInterval(id); };
  }, []);

  const s = sections ?? {};
  const pins: Array<{ cat: Category; key: string; render: (style: CSSProperties) => ReactNode }> = [];
  const markets = s.markets ?? [];
  const news = s.news ?? [];

  if (markets[0]) pins.push({ cat: 'markets', key: markets[0].id, render: (st) => <PricePin m={markets[0]} style={st} /> });
  if (s.yields?.length) pins.push({ cat: 'yields', key: 'yields', render: (st) => <YieldsPin rows={s.yields!} style={st} /> });
  if (news[0]) pins.push({ cat: 'news', key: news[0].url, render: (st) => <NewsPin n={news[0]} tone={0} style={st} /> });
  if (s.dex) pins.push({ cat: 'defi', key: 'dex', render: (st) => <DexPin dex={s.dex!} style={st} /> });
  pins.push({ cat: 'ideas', key: 'idea-0', render: (st) => <IdeaPin idea={IDEAS[0]} style={st} /> });
  if (markets[1]) pins.push({ cat: 'markets', key: markets[1].id, render: (st) => <PricePin m={markets[1]} style={st} /> });
  if (s.stablecoins?.length) pins.push({ cat: 'defi', key: 'stables', render: (st) => <StablesPin rows={s.stablecoins!} style={st} /> });
  if (news[1]) pins.push({ cat: 'news', key: news[1].url, render: (st) => <NewsPin n={news[1]} tone={1} style={st} /> });
  if (markets[2]) pins.push({ cat: 'markets', key: markets[2].id, render: (st) => <PricePin m={markets[2]} style={st} /> });
  if (s.protocols?.length) pins.push({ cat: 'defi', key: 'tvl', render: (st) => <TvlPin rows={s.protocols!} style={st} /> });
  pins.push({ cat: 'ideas', key: 'idea-1', render: (st) => <IdeaPin idea={IDEAS[1]} style={st} /> });
  if (news[2]) pins.push({ cat: 'news', key: news[2].url, render: (st) => <NewsPin n={news[2]} tone={2} style={st} /> });
  if (s.fees) pins.push({ cat: 'defi', key: 'fees', render: (st) => <FeesPin fees={s.fees!} style={st} /> });
  pins.push({ cat: 'ideas', key: 'idea-2', render: (st) => <IdeaPin idea={IDEAS[2]} style={st} /> });
  news.slice(3, 5).forEach((n, i) => pins.push({ cat: 'news', key: n.url, render: (st) => <NewsPin n={n} tone={3 + i} style={st} /> }));

  const visible = pins.filter((p) => filter === 'all' || p.cat === filter || (filter === 'defi' && p.cat === 'yields'));

  return (
    <section aria-labelledby="board-title">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <h2 id="board-title" className="font-display text-[22px] font-bold tracking-[-0.5px] sm:text-[28px]">On the board today</h2>
        <span className="inline-flex items-center gap-2 text-[13px] font-semibold text-ink-3">
          <span className={`h-2 w-2 rounded-full ${failed ? 'bg-muted' : 'anim-live bg-accent'}`} />
          {failed && !sections ? 'Live data is unavailable right now' : 'Live data · tap a pin to ask about it'}
        </span>
      </div>

      <nav aria-label="Filter pins" className="-mx-4 mb-6 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:px-0">
        {FILTERS.map(([id, label]) => (
          <button
            key={id}
            type="button"
            aria-pressed={filter === id}
            onClick={() => setFilter(id)}
            className={`min-h-11 shrink-0 rounded-full px-[18px] text-sm font-semibold transition-colors touch-manipulation ${
              filter === id ? 'bg-ink text-white' : 'bg-field text-ink hover:bg-field-hover'
            }`}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="columns-2 gap-2.5 sm:columns-[232px] sm:gap-4" aria-busy={!sections && !failed}>
        {!sections && !failed
          ? <SkeletonPins />
          : visible.map((p, i) => <div key={p.key} className="break-inside-avoid">{p.render({ animationDelay: `${Math.min(i, 10) * 60}ms` })}</div>)}
      </div>
      {sections && visible.length === 0 && (
        <p className="py-10 text-center text-muted">Nothing in this filter right now.</p>
      )}
    </section>
  );
}
