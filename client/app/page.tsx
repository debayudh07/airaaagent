import Link from 'next/link';
import { ArrowRight, BookOpen, Layers, LineChart, Link2, Search, Wallet } from 'lucide-react';
import Logo from './components/Logo';

const CAPABILITIES = [
  {
    icon: LineChart,
    title: 'Prices and history',
    body: 'Price, market cap, volume and supply for any listed token, plus charts over days to a year.',
    example: 'Chart ETH vs SOL over the last 30 days',
  },
  {
    icon: Layers,
    title: 'DeFi metrics',
    body: 'Protocol and chain TVL, yields, stablecoin supply, DEX volume, fees and bridges.',
    example: 'Best stablecoin yields right now',
  },
  {
    icon: BookOpen,
    title: 'News and the web',
    body: 'Headlines from CoinDesk, Cointelegraph, Decrypt and The Block, plus web search, each with a link.',
    example: 'Why is the market moving today?',
  },
  {
    icon: Link2,
    title: 'Read any link',
    body: 'Paste a roadmap, blog post or docs page and ask about it. The agent reads it for you.',
    example: 'Summarise this proposal: https://…',
  },
  {
    icon: Search,
    title: 'New and small tokens',
    body: 'Liquidity, volume and FDV for tokens too new for the big trackers, by name or contract.',
    example: 'Is PEPE liquid? Show its DEX pairs',
  },
  {
    icon: Wallet,
    title: 'Your wallet',
    body: 'Connect a wallet to ask about its balance, transactions and token transfers across EVM chains.',
    example: 'What did my wallet do this week?',
  },
];

const STEPS = [
  { title: 'Plan', body: 'A fast model reads the question and picks the fewest sources that can answer it.', border: 'border-accent' },
  { title: 'Gather', body: 'Sources are queried in parallel, with timeouts and a retry when one stumbles.', border: 'border-accent/60' },
  { title: 'Check', body: 'If something failed, the agent decides whether another source could fill the gap.', border: 'border-accent/40' },
  { title: 'Answer', body: 'Charts are drawn from the fetched numbers, and the write-up cites every source.', border: 'border-accent/25' },
];

const SOURCES = [
  'CoinMarketCap', 'CoinGecko', 'DefiLlama', 'Dune', 'Etherscan', 'DEX Screener',
  'CoinDesk · Cointelegraph · Decrypt · The Block', 'Web search',
];

// Example answer figures: DefiLlama, Arbitrum DEX volume, 24h (sampled Oct 3, 2026)
const EXAMPLE_BARS = [
  { label: 'Uni V3', pct: 100 },
  { label: 'Uni V4', pct: 32 },
  { label: 'Fluid', pct: 23 },
  { label: 'Pancake', pct: 7 },
  { label: 'Camelot', pct: 4 },
];

export default function HomePage() {
  return (
    <div className="min-h-dvh bg-bg text-base leading-[1.55] text-ink">
      <header className="border-b border-white/[0.08]">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-[18px] sm:px-6">
          <Logo size="lg" />
          <nav aria-label="Main" className="ml-auto hidden gap-6 text-[15px] md:flex">
            <a href="#capabilities" className="text-muted transition-colors hover:text-ink">What it answers</a>
            <a href="#how" className="text-muted transition-colors hover:text-ink">How it works</a>
            <a href="#sources" className="text-muted transition-colors hover:text-ink">Data sources</a>
          </nav>
          <Link
            href="/main-chat"
            className="ml-auto inline-flex min-h-11 items-center rounded-[10px] bg-accent px-[18px] font-semibold text-on-accent transition-colors hover:bg-accent-hover md:ml-0"
          >
            Open the app
          </Link>
        </div>
      </header>

      <main>
        <section id="top" className="mx-auto flex max-w-[1200px] flex-wrap items-center gap-14 px-4 pb-16 pt-14 sm:px-6 md:pb-[72px] md:pt-[88px]">
          <div className="min-w-0 flex-[1_1_460px]">
            <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/[0.12] px-3 py-1.5 text-[13px] text-muted">
              <span className="h-[7px] w-[7px] rounded-full bg-ok" />
              AI research agent for Web3
            </p>
            <h1 className="font-display text-[40px] font-bold leading-[1.06] tracking-[-1px] sm:text-5xl lg:text-[60px] lg:leading-[1.04] lg:tracking-[-1.5px]">
              Ask about any token, protocol or wallet. Get answers from live data.
            </h1>
            <p className="mt-6 max-w-[520px] text-lg text-muted">
              AIRAA plans which sources to query, pulls market, DeFi, on-chain and news data in parallel, checks what it
              found, and writes an answer with charts and links you can verify.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Link
                href="/main-chat"
                className="inline-flex min-h-[52px] items-center gap-2.5 rounded-xl bg-accent px-6 text-[17px] font-semibold text-on-accent transition-colors hover:bg-accent-hover"
              >
                Start researching
                <ArrowRight className="h-[18px] w-[18px]" strokeWidth={2.2} aria-hidden="true" />
              </Link>
              <a
                href="#how"
                className="inline-flex min-h-[52px] items-center rounded-xl border border-white/[0.16] px-[22px] text-[17px] font-medium text-ink transition-colors hover:border-white/30"
              >
                See how it works
              </a>
            </div>
            <p className="mt-5 text-[13px] text-subtle">Free to use. No wallet needed; connect one only for on-chain questions about it.</p>
          </div>

          <figure aria-label="Example answer" className="m-0 flex min-w-0 flex-[1_1_420px] flex-col gap-4 rounded-[18px] border border-line bg-surface p-5">
            <div className="max-w-[85%] self-end rounded-[14px_14px_4px_14px] bg-accent/[0.12] px-3.5 py-2.5 text-sm">
              Which DEXs lead on Arbitrum today?
            </div>
            <div className="flex flex-wrap gap-1.5 text-xs">
              <span className="rounded-full bg-ok/[0.12] px-2.5 py-1 text-emerald-300">DefiLlama · 1.9s</span>
              <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-muted">LLM-planned</span>
            </div>
            <div className="rounded-xl border border-white/[0.08] p-3.5">
              <div className="mb-3 flex items-baseline justify-between gap-2">
                <span className="text-[13px] font-medium">DEX volume by protocol, 24h on Arbitrum</span>
                <span className="text-[11px] text-subtle">DefiLlama</span>
              </div>
              <div className="flex h-[150px] items-end gap-2.5 border-b border-white/[0.08]" aria-hidden="true">
                {EXAMPLE_BARS.map((b) => (
                  <div key={b.label} className="flex-1 rounded-t-[5px] bg-accent" style={{ height: `${b.pct}%` }} />
                ))}
              </div>
              <div className="mt-1.5 flex gap-2.5 text-center text-[10px] text-subtle">
                {EXAMPLE_BARS.map((b) => <span key={b.label} className="flex-1">{b.label}</span>)}
              </div>
            </div>
            <p className="m-0 text-sm text-ink-3">
              Uniswap V3 leads with <strong className="font-mono font-medium text-ink">$100,391,193</strong> of the{' '}
              <strong className="font-mono font-medium text-ink">$173,117,857</strong> traded on Arbitrum DEXs in the last 24h (DefiLlama)…
            </p>
          </figure>
        </section>

        <section id="capabilities" className="mx-auto max-w-[1200px] scroll-mt-6 px-4 py-12 sm:px-6">
          <h2 className="mb-2 font-display text-[28px] font-bold tracking-[-0.6px] sm:text-4xl">What you can ask</h2>
          <p className="mb-8 max-w-[640px] text-muted">One question can pull from several sources. The agent picks them; you see which ones answered.</p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {CAPABILITIES.map(({ icon: Icon, title, body, example }) => (
              <article key={title} className="min-w-0 rounded-2xl border border-line bg-surface p-6">
                <Icon className="h-6 w-6 text-accent" strokeWidth={2} aria-hidden="true" />
                <h3 className="mb-1.5 mt-3.5 font-display text-xl font-bold">{title}</h3>
                <p className="m-0 text-[15px] text-muted">{body}</p>
                <p className="mt-3.5 text-[13px] text-subtle">“{example}”</p>
              </article>
            ))}
          </div>
        </section>

        <section id="how" className="mx-auto max-w-[1200px] scroll-mt-6 px-4 py-12 sm:px-6">
          <h2 className="mb-8 font-display text-[28px] font-bold tracking-[-0.6px] sm:text-4xl">How an answer is made</h2>
          <ol className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((s, i) => (
              <li key={s.title} className={`min-w-0 border-t-2 pt-4 ${s.border}`}>
                <span className="font-mono text-[13px] text-accent">{String(i + 1).padStart(2, '0')}</span>
                <h3 className="my-1.5 font-display text-[19px] font-bold">{s.title}</h3>
                <p className="m-0 text-[15px] text-muted">{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section id="sources" className="mx-auto max-w-[1200px] scroll-mt-6 px-4 pb-[88px] pt-12 sm:px-6">
          <h2 className="mb-5 font-display text-[28px] font-bold tracking-[-0.6px] sm:text-4xl">Data sources</h2>
          <ul aria-label="Data sources" className="m-0 flex list-none flex-wrap gap-2.5 p-0">
            {SOURCES.map((s) => (
              <li key={s} className="rounded-[10px] border border-white/10 px-4 py-2.5 text-ink-3">{s}</li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="border-t border-white/[0.08]">
        <div className="mx-auto flex max-w-[1200px] flex-wrap justify-between gap-3 px-4 py-6 text-[13px] text-subtle sm:px-6">
          <span>AIRAA · AI research, not financial advice.</span>
          <span>Answers can be wrong. Check the linked sources before acting.</span>
        </div>
      </footer>
    </div>
  );
}
