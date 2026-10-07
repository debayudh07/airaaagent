'use client';

import { useCallback, useSyncExternalStore } from 'react';
import { useSignMessage } from 'wagmi';
import {
  getVaultSnapshot, setPassphrase, setupVault, subscribeVault, unlockWithPassphrase, unlockWithRecoveryKey, unlockWithSignature,
  rotateRecoveryKey,
} from '../../lib/vault';
import { useAuth } from './AuthProvider';

/** Vault lock state plus the wallet-aware actions that change it. Everything needs a signed-in wallet. */
export function useVault() {
  const { wallet } = useAuth();
  const { signMessageAsync } = useSignMessage();
  const { unlocked } = useSyncExternalStore(subscribeVault, getVaultSnapshot, getVaultSnapshot);

  const signText = useCallback((message: string) => signMessageAsync({ message }), [signMessageAsync]);
  const need = () => {
    if (!wallet) throw new Error('Sign in first');
    return wallet;
  };

  return {
    unlocked,
    setup: (passphrase?: string) => setupVault({ walletId: need().id, address: need().address, signText, passphrase }),
    unlockWithWallet: () => unlockWithSignature(need().id, signText),
    unlockWithPassphrase: (passphrase: string) => unlockWithPassphrase(need().id, passphrase),
    unlockWithRecoveryKey: (key: string) => unlockWithRecoveryKey(need().id, key),
    setPassphrase: (passphrase: string) => setPassphrase(need().id, passphrase),
    rotateRecoveryKey: () => rotateRecoveryKey(need().id),
  };
}
