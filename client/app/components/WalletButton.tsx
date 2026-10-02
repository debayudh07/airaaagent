'use client';

import { ConnectButton } from '@rainbow-me/rainbowkit';
import { Wallet } from 'lucide-react';

const BASE =
  'inline-flex min-h-11 sm:min-h-10 items-center gap-2 rounded-[10px] border border-white/[0.16] bg-transparent px-3 text-sm font-medium text-ink-3 transition-colors hover:border-white/30 hover:text-ink touch-manipulation';

/** Wallet control in the chat header: "Connect wallet", or the short address once connected. */
export default function WalletButton() {
  return (
    <ConnectButton.Custom>
      {({ account, chain, mounted, openAccountModal, openChainModal, openConnectModal }) => {
        const ready = mounted;
        const connected = ready && account && chain;
        return (
          <div aria-hidden={!ready} className={ready ? '' : 'pointer-events-none select-none opacity-0'}>
            {!connected ? (
              <button type="button" onClick={openConnectModal} className={`${BASE} text-ink`} aria-label="Connect wallet">
                <Wallet className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">Connect wallet</span>
              </button>
            ) : chain.unsupported ? (
              <button type="button" onClick={openChainModal} className={`${BASE} border-red-400/45 text-red-300`}>
                Wrong network
              </button>
            ) : (
              <button type="button" onClick={openAccountModal} className={`${BASE} font-mono`} title={account.address}>
                {account.address.slice(0, 4)}…{account.address.slice(-4)}
              </button>
            )}
          </div>
        );
      }}
    </ConnectButton.Custom>
  );
}
