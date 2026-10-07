'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { useAccount, useChainId, useSignMessage } from 'wagmi';
import {
  forgetSessionLocally, getAuthSnapshot, restoreSession, signInWithWallet, signOut as signOutRequest, subscribeAuth,
  type AuthWallet,
} from '../../lib/auth';
import { API_BASE } from '../../lib/config';
import { lockVault } from '../../lib/vault';

interface AuthContextValue {
  /** The server has wallet sign-in switched on (otherwise the app is guest-only and nothing here shows). */
  enabled: boolean;
  status: 'unknown' | 'guest' | 'signed-in';
  wallet: AuthWallet | null;
  busy: boolean;
  error: string | null;
  signIn: () => Promise<boolean>;
  signOut: () => Promise<void>;
  clearError: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const useAuth = (): AuthContextValue => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
};

const friendly = (e: unknown) => {
  const message = e instanceof Error ? e.message : String(e);
  if (/user rejected|denied|rejected the request/i.test(message)) return 'Signature request was cancelled';
  return message.length > 200 ? `${message.slice(0, 200)}…` : message;
};

export default function AuthProvider({ children }: { children: ReactNode }) {
  const snap = useSyncExternalStore(subscribeAuth, getAuthSnapshot, getAuthSnapshot);
  const { address, status: accountStatus } = useAccount();
  const chainId = useChainId();
  const { signMessageAsync } = useSignMessage();
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wasConnected = useRef(false);

  // Is sign-in enabled on this server? If so, resume any session from the refresh cookie.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/health`);
        const features = (await res.json())?.features;
        if (cancelled) return;
        const on = !!features?.wallet_auth;
        setEnabled(on);
        if (on) await restoreSession();
        else forgetSessionLocally();
      } catch {
        if (!cancelled) forgetSessionLocally();   // backend unreachable: behave as a guest
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const signOut = useCallback(async () => {
    lockVault();
    await signOutRequest();
  }, []);

  // A session belongs to one wallet. Switching or disconnecting the wallet ends it.
  useEffect(() => {
    if (accountStatus === 'connected') wasConnected.current = true;
    if (snap.status !== 'signed-in' || !snap.wallet) return;
    const switched = accountStatus === 'connected' && address && address.toLowerCase() !== snap.wallet.address.toLowerCase();
    const disconnected = accountStatus === 'disconnected' && wasConnected.current;
    if (switched || disconnected) void signOut();
  }, [accountStatus, address, snap.status, snap.wallet, signOut]);

  const signIn = useCallback(async () => {
    if (!address) {
      setError('Connect your wallet first');
      return false;
    }
    setBusy(true);
    setError(null);
    try {
      await signInWithWallet(address, chainId, ({ message }) => signMessageAsync({ message }));
      return true;
    } catch (e) {
      setError(friendly(e));
      return false;
    } finally {
      setBusy(false);
    }
  }, [address, chainId, signMessageAsync]);

  const value = useMemo<AuthContextValue>(
    () => ({ enabled, status: snap.status, wallet: snap.wallet, busy, error, signIn, signOut, clearError: () => setError(null) }),
    [enabled, snap.status, snap.wallet, busy, error, signIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
