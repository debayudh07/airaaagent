"use client";

import { ArrowRight, Activity, Layers, Wallet } from "lucide-react";

interface AnimatedAIChatProps {
  onSendMessage?: (message: string) => void;
}

const FEATURES = [
  { icon: Activity, title: "Live market data", text: "Prices, TVL, yields and DEX volume from CoinMarketCap, DefiLlama and Dune." },
  { icon: Wallet, title: "On-chain insight", text: "Analyze wallet activity and token transfers through Etherscan." },
  { icon: Layers, title: "Agent you can inspect", text: "See which sources it queried, how long each took, and the data behind every answer." },
];

export function AnimatedAIChat({ onSendMessage }: AnimatedAIChatProps) {
  return (
    <main
      className="flex min-h-dvh w-full flex-col items-center justify-center bg-[#070b14] px-5 py-16 text-white"
      style={{ backgroundImage: "radial-gradient(60rem 30rem at 50% -10%, rgba(14,165,233,0.16), transparent 60%)" }}
    >
      <div className="w-full max-w-2xl text-center">
        <div className="mx-auto mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs text-white/60">
          <span className="h-1.5 w-1.5 rounded-full bg-cyan-300" />
          AI research agent for Web3
        </div>

        <h1 className="text-balance text-4xl font-semibold tracking-tight sm:text-6xl">
          Research crypto with{" "}
          <span className="bg-gradient-to-r from-cyan-300 to-sky-400 bg-clip-text text-transparent">real data</span>
        </h1>
        <p className="mx-auto mt-5 max-w-lg text-pretty text-base leading-relaxed text-white/60 sm:text-lg">
          Ask a question in plain English. Aira picks the right data sources, queries them in parallel and writes up what it found.
        </p>

        <button
          type="button"
          onClick={() => onSendMessage?.("Start chat")}
          className="group mt-9 inline-flex items-center gap-2 rounded-xl bg-cyan-400 px-6 py-3 text-base font-medium text-slate-900 transition hover:bg-cyan-300 active:scale-[0.98]"
        >
          Start researching
          <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
        </button>
      </div>

      <ul className="mt-16 grid w-full max-w-3xl gap-3 sm:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, text }) => (
          <li key={title} className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-left">
            <Icon className="mb-3 h-5 w-5 text-cyan-300" />
            <h2 className="text-sm font-medium">{title}</h2>
            <p className="mt-1 text-sm leading-relaxed text-white/55">{text}</p>
          </li>
        ))}
      </ul>
    </main>
  );
}
