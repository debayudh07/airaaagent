'use client';

import { ConnectButton } from '@rainbow-me/rainbowkit';
import { Wallet } from 'lucide-react';
import AccountMenu from './AccountMenu';

const BASE =
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-full border-[1.5px] border-ink bg-white px-4 text-sm font-semibold text-ink transition-colors hover:bg-field touch-manipulation';

/** Wallet control: "Connect wallet", or the short address once connected. */
export default function WalletButton() {
  return (
    <div className="flex items-center gap-2">
    <AccountMenu />
    <ConnectButton.Custom>
      {({ account, chain, mounted, openAccountModal, openChainModal, openConnectModal }) => {
        const connected = mounted && account && chain;
        return (
          <div aria-hidden={!mounted} className={mounted ? '' : 'pointer-events-none select-none opacity-0'}>
            {!connected ? (
              <button type="button" onClick={openConnectModal} className={`${BASE} w-11 px-0 sm:w-auto sm:px-4`} aria-label="Connect wallet">
                <Wallet className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">Connect wallet</span>
              </button>
            ) : chain.unsupported ? (
              <button type="button" onClick={openChainModal} className={`${BASE} border-down text-down`}>
                Wrong network
              </button>
            ) : (
              <button type="button" onClick={openAccountModal} className={`${BASE} tabular`} title={account.address}>
                {account.address.slice(0, 4)}…{account.address.slice(-4)}
              </button>
            )}
          </div>
        );
      }}
    </ConnectButton.Custom>
    </div>
  );
}
