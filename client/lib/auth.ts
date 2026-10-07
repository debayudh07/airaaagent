import { createSiweMessage } from 'viem/siwe';
import { API_BASE } from './config';

/**
 * Wallet session state, kept outside React so every component and fetch helper shares it.
 *
 * The access token lives only in memory (never localStorage: an XSS bug could read it). Reloading the page restores the
 * session from the httpOnly refresh cookie, which the browser sends and scripts cannot read.
 */
export interface AuthWallet {
  id: string;
  address: string;
  settings?: { memory_enabled?: boolean };
}

export interface AuthSnapshot {
  /** `unknown` until the first restore attempt finishes. */
  status: 'unknown' | 'guest' | 'signed-in';
  wallet: AuthWallet | null;
}

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) {
    super(message);
  }
}

let token: string | null = null;
let expiresAt = 0;
let snapshot: AuthSnapshot = { status: 'unknown', wallet: null };
const listeners = new Set<() => void>();
let inflightRefresh: Promise<boolean> | null = null;

function publish(next: AuthSnapshot) {
  snapshot = next;
  listeners.forEach((fn) => fn());
}

export const subscribeAuth = (fn: () => void) => {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
};
export const getAuthSnapshot = () => snapshot;

interface LoginResponse {
  access_token: string;
  expires_in: number;
  wallet: AuthWallet;
}

function adopt(data: LoginResponse) {
  token = data.access_token;
  expiresAt = Date.now() + data.expires_in * 1000;
  publish({ status: 'signed-in', wallet: data.wallet });
}

function clearLocal() {
  token = null;
  expiresAt = 0;
  publish({ status: 'guest', wallet: null });
}

async function errorFrom(res: Response): Promise<ApiError> {
  let message = `HTTP ${res.status}`;
  let code: string | undefined;
  try {
    const body = await res.json();
    if (body?.error) message = body.error;
    code = body?.code;
  } catch {
    /* keep the status text */
  }
  return new ApiError(message, res.status, code);
}

/** Exchange the refresh cookie for a new access token. Concurrent callers share one request (the token rotates). */
export function refreshSession(): Promise<boolean> {
  if (!inflightRefresh) {
    inflightRefresh = (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/auth/refresh`, { method: 'POST', credentials: 'include' });
        if (!res.ok) {
          clearLocal();
          return false;
        }
        adopt(await res.json());
        return true;
      } catch {
        // Network trouble is not a logout: keep whatever we have and let the caller's own request fail visibly.
        if (snapshot.status === 'unknown') publish({ status: 'guest', wallet: null });
        return false;
      } finally {
        inflightRefresh = null;
      }
    })();
  }
  return inflightRefresh;
}

/** Try to resume a session after a page load. Safe to call when sign-in is not enabled on the server. */
export async function restoreSession(): Promise<void> {
  if (snapshot.status !== 'unknown') return;
  await refreshSession();
  if (snapshot.status === 'unknown') publish({ status: 'guest', wallet: null });
}

/** A valid access token (refreshing it shortly before expiry), or null for a guest. */
export async function getAccessToken(): Promise<string | null> {
  if (!token) return null;
  if (Date.now() > expiresAt - 30_000) await refreshSession();
  return token;
}

/** fetch() against the API that attaches the session and retries once after a silent refresh. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = async () => {
    const headers = new Headers(init.headers);
    const t = await getAccessToken();
    if (t) headers.set('Authorization', `Bearer ${t}`);
    if (init.body && typeof init.body === 'string' && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    return fetch(`${API_BASE}${path}`, { ...init, headers });
  };
  const res = await send();
  if (res.status === 401 && token && (await refreshSession())) return send();
  return res;
}

/** apiFetch + JSON, throwing ApiError (with the server's message) on any non-2xx response. */
export async function apiJson<T = Record<string, unknown>>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) throw await errorFrom(res);
  return res.json();
}

export const jsonBody = (value: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(value) });

// ------------------------------------------------------------------ sign in / out
const STATEMENT = 'Sign in to airaa. This costs no gas and authorises no transaction.';

/**
 * Sign-In with Ethereum: fetch a nonce, have the wallet sign an EIP-4361 message for this site, and exchange it
 * for a session. `signMessage` is wagmi's `signMessageAsync` (works for browser wallets and smart wallets alike).
 */
export async function signInWithWallet(
  address: `0x${string}`,
  chainId: number,
  signMessage: (args: { message: string }) => Promise<string>,
): Promise<AuthWallet> {
  const nonceRes = await fetch(`${API_BASE}/api/auth/nonce`);
  if (!nonceRes.ok) throw await errorFrom(nonceRes);
  const { nonce } = await nonceRes.json();

  const message = createSiweMessage({
    address,
    chainId,
    domain: window.location.host,
    nonce,
    uri: window.location.origin,
    version: '1',
    statement: STATEMENT,
  });
  const signature = await signMessage({ message });

  const res = await fetch(`${API_BASE}/api/auth/verify`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, signature }),
  });
  if (!res.ok) throw await errorFrom(res);
  const data: LoginResponse = await res.json();
  adopt(data);
  return data.wallet;
}

export async function signOut(): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/auth/logout`, { method: 'POST', credentials: 'include' });
  } catch {
    /* the local session is cleared regardless */
  }
  clearLocal();
}

/** Used by wallet-switch handling: drop the local session without a server round trip. */
export const forgetSessionLocally = clearLocal;
