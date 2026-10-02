import Link from 'next/link';
import AskBox from './components/AskBox';
import Board from './components/Board';
import Logo from './components/Logo';
import WalletButton from './components/WalletButton';
import { askHref } from '../lib/api';

const QUICK = [
  ['Chart ETH vs SOL, 30 days', 'Chart ETH vs SOL over the last 30 days'],
  ['Why is the market moving?', 'Why is the crypto market moving today?'],
  ['Best stablecoin yields', 'Best stablecoin yields right now?'],
  ['Aave TVL and fees', 'Aave TVL history and fees'],
] as const;

export default function HomePage() {
  return (
    <div className="min-h-dvh bg-bg text-[15px] leading-normal text-ink">
      <header className="sticky top-0 z-10 border-b border-line-2 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1360px] items-center gap-3 px-4 py-2.5 sm:gap-4 sm:px-6 sm:py-3.5">
          <Logo />
          <nav aria-label="Main" className="ml-auto">
            <Link href="/main-chat" className="inline-flex min-h-11 items-center rounded-full px-3.5 font-semibold text-ink-3 transition-colors hover:bg-field">
              Your chat
            </Link>
          </nav>
          <WalletButton />
        </div>
      </header>

      <main className="mx-auto max-w-[1360px] px-3 pb-16 sm:px-6">
        <section className="flex min-h-[460px] flex-col items-center justify-center px-1 pb-10 pt-12 text-center sm:min-h-[520px] sm:pb-16 sm:pt-14">
          <h1 className="anim-rise font-display text-[38px] font-extrabold leading-none tracking-[-1.2px] sm:text-[60px] sm:tracking-[-2px]">
            Ask crypto anything
          </h1>
          <p className="anim-rise mt-3 max-w-[560px] text-[15px] text-muted sm:mt-3.5 sm:text-[17px]" style={{ animationDelay: '80ms' }}>
            Live market, DeFi, on-chain and news data, answered in a chat with charts and sources.
          </p>
          <div className="anim-rise mt-6 flex w-full justify-center sm:mt-8" style={{ animationDelay: '160ms' }}>
            <AskBox />
          </div>
          <div className="anim-rise mt-4 flex max-w-[760px] flex-wrap justify-center gap-2 sm:mt-5" style={{ animationDelay: '240ms' }}>
            {QUICK.map(([label, q]) => (
              <Link
                key={label}
                href={askHref(q)}
                className="inline-flex min-h-11 items-center rounded-full bg-field px-4 text-[13px] font-semibold text-ink transition-[transform,background-color] hover:-translate-y-0.5 hover:bg-field-hover sm:text-sm"
              >
                {label}
              </Link>
            ))}
          </div>
        </section>

        <Board />

        <p className="mt-8 text-center text-[13px] text-muted">AI-generated research, not financial advice.</p>
      </main>
    </div>
  );
}
