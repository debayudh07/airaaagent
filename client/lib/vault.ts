import { ApiError, apiFetch, apiJson } from './auth';
import { API_BASE } from './config';
import * as C from './vaultCrypto';

/**
 * Sealed storage: the browser-side orchestration around lib/vaultCrypto.ts. The unlocked data key (DEK) lives only in
 * this module's memory: a reload, sign-out or wallet switch locks the vault again.
 */
export type { ArtifactMeta } from './vaultCrypto';

export interface VaultKeyRow {
  id: string;
  wrapper_type: C.WrapperType;
  wrapped_dek: string;
  kdf: C.Kdf;
  created_at: string;
}

export interface VaultInfo {
  initialized: boolean;
  keys: VaultKeyRow[];
  limits: { max_artifact_bytes: number };
}

export interface SealedItem {
  id: string;
  size_bytes: number;
  created_at: string;
  wrapped_cek: string;
  meta_enc: string | null;
  index_summary: string | null;
  /** Decrypted metadata; undefined if it could not be decrypted with the current key. */
  meta?: C.ArtifactMeta;
}

export interface ShareRow {
  id: string;
  resource_type: 'conversation' | 'artifact';
  resource_id: string;
  mode: 'link' | 'wallet';
  recipient_address: string | null;
  redact_research_data: boolean;
  created_at: string;
  expires_at: string | null;
  revoked_at: string | null;
}

export type SignText = (message: string) => Promise<string>;

export class VaultError extends Error {}

// ------------------------------------------------------------------ in-memory unlock state
let dek: CryptoKey | null = null;
let snapshot = { unlocked: false };
const listeners = new Set<() => void>();

function setDek(next: CryptoKey | null) {
  dek = next;
  snapshot = { unlocked: next !== null };
  listeners.forEach((fn) => fn());
}

export const subscribeVault = (fn: () => void) => {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
};
export const getVaultSnapshot = () => snapshot;
export const lockVault = () => setDek(null);

function requireDek(): CryptoKey {
  if (!dek) throw new VaultError('Unlock your vault first');
  return dek;
}

// ------------------------------------------------------------------ setup and unlock
export const fetchVault = () => apiJson<VaultInfo>('/api/vault');

const send = (method: string, payload: unknown): RequestInit => ({ method, body: JSON.stringify(payload) });

async function putKey(type: C.WrapperType, wrappedDek: Uint8Array, kdf: C.Kdf) {
  await apiJson(`/api/vault/keys/${type}`, send('PUT', { wrapped_dek: C.toB64(wrappedDek), kdf }));
}

async function addRecoveryWrapper(newDek: CryptoKey, walletId: string): Promise<string> {
  const recovery = C.newRecoveryKey();
  const kdf: C.Kdf = { v: 1, salt: C.newSalt() };
  await putKey('recovery', await C.wrapDek(newDek, await C.kekFromRecoveryKey(recovery.bytes, kdf.salt), walletId, 'recovery'), kdf);
  return recovery.display;
}

/**
 * Create the vault: a random DEK, wrapped by the wallet signature and by a recovery key (shown once), optionally
 * also by a passphrase. Returns the recovery key, which the caller must show the user before continuing.
 */
export async function setupVault(opts: {
  walletId: string; address: string; signText: SignText; passphrase?: string;
}): Promise<{ recoveryKey: string }> {
  const newDek = await C.newDek();

  const sigKdf: C.Kdf = { v: 1, salt: C.newSalt(), message: C.vaultMessage(window.location.host, opts.address) };
  const signature = await opts.signText(sigKdf.message!);
  await putKey('signature', await C.wrapDek(newDek, await C.kekFromSignature(signature, sigKdf.salt), opts.walletId, 'signature'), sigKdf);

  const recoveryKey = await addRecoveryWrapper(newDek, opts.walletId);

  if (opts.passphrase) {
    const kdf: C.Kdf = { v: 1, salt: C.newSalt(), iterations: C.PBKDF2_ITERATIONS };
    await putKey('passphrase', await C.wrapDek(newDek, await C.kekFromPassphrase(opts.passphrase, kdf.salt, kdf.iterations), opts.walletId, 'passphrase'), kdf);
  }
  setDek(newDek);
  return { recoveryKey };
}

async function keyRow(type: C.WrapperType): Promise<VaultKeyRow> {
  const row = (await fetchVault()).keys.find((k) => k.wrapper_type === type);
  if (!row) throw new VaultError(`This vault has no ${type} key`);
  return row;
}

async function unlockWith(row: VaultKeyRow, walletId: string, kek: CryptoKey) {
  try {
    setDek(await C.unwrapDek(C.fromB64(row.wrapped_dek), kek, walletId, row.wrapper_type));
  } catch {
    throw new VaultError(
      row.wrapper_type === 'signature'
        ? 'Your wallet produced a different signature than the one that created this vault (smart wallets can do this). Unlock with your passphrase or recovery key instead.'
        : row.wrapper_type === 'passphrase' ? 'Wrong passphrase' : 'That recovery key does not match this vault',
    );
  }
}

export async function unlockWithSignature(walletId: string, signText: SignText) {
  const row = await keyRow('signature');
  if (!row.kdf.message) throw new VaultError('This vault has no signature message recorded');
  await unlockWith(row, walletId, await C.kekFromSignature(await signText(row.kdf.message), row.kdf.salt));
}

export async function unlockWithPassphrase(walletId: string, passphrase: string) {
  const row = await keyRow('passphrase');
  await unlockWith(row, walletId, await C.kekFromPassphrase(passphrase, row.kdf.salt, row.kdf.iterations));
}

export async function unlockWithRecoveryKey(walletId: string, recoveryKey: string) {
  const row = await keyRow('recovery');
  let bytes: Uint8Array;
  try {
    bytes = C.parseRecoveryKey(recoveryKey);
  } catch (e) {
    throw new VaultError((e as Error).message);
  }
  await unlockWith(row, walletId, await C.kekFromRecoveryKey(bytes, row.kdf.salt));
}

/** While unlocked: add or replace the passphrase wrapper. */
export async function setPassphrase(walletId: string, passphrase: string) {
  const kdf: C.Kdf = { v: 1, salt: C.newSalt(), iterations: C.PBKDF2_ITERATIONS };
  await putKey('passphrase', await C.wrapDek(requireDek(), await C.kekFromPassphrase(passphrase, kdf.salt, kdf.iterations), walletId, 'passphrase'), kdf);
}

/** While unlocked: replace the recovery key (the old one stops working). Returns the new one to show once. */
export const rotateRecoveryKey = (walletId: string) => addRecoveryWrapper(requireDek(), walletId);

// ------------------------------------------------------------------ files
async function toItem(row: Omit<SealedItem, 'meta'>): Promise<SealedItem> {
  if (!row.meta_enc) return row;
  try {
    return { ...row, meta: await C.decryptMeta(requireDek(), row.id, C.fromB64(row.wrapped_cek), C.fromB64(row.meta_enc)) };
  } catch {
    return row;
  }
}

export async function listArtifacts(): Promise<SealedItem[]> {
  const { artifacts } = await apiJson<{ artifacts: Omit<SealedItem, 'meta'>[] }>('/api/artifacts');
  return Promise.all(artifacts.map(toItem));
}

/** Encrypt in the browser and upload. `indexSummary` is OPT-IN plaintext that lets the server search this file. */
export async function sealFile(data: Uint8Array, meta: Omit<C.ArtifactMeta, 'createdAt'>, indexSummary?: string): Promise<string> {
  const id = crypto.randomUUID();
  const sealed = await C.encryptFile(requireDek(), id, data, { ...meta, createdAt: new Date().toISOString() });
  await apiJson('/api/artifacts', send('POST', {
    id,
    ciphertext: C.toB64(sealed.ciphertext),
    wrapped_cek: C.toB64(sealed.wrappedCek),
    meta_enc: C.toB64(sealed.metaEnc),
    ...(indexSummary?.trim() ? { index_summary: indexSummary.trim() } : {}),
  }));
  return id;
}

export async function openArtifact(item: SealedItem): Promise<Uint8Array> {
  const res = await apiFetch(`/api/artifacts/${item.id}/blob`);
  if (!res.ok) throw new ApiError(`Could not download the file (HTTP ${res.status})`, res.status);
  const ciphertext = new Uint8Array(await res.arrayBuffer());
  return C.decryptFile(requireDek(), item.id, ciphertext, C.fromB64(item.wrapped_cek));
}

export const deleteArtifact = (id: string) => apiJson(`/api/artifacts/${id}`, { method: 'DELETE' });

// ------------------------------------------------------------------ sharing
export const listShares = () => apiJson<{ shares: ShareRow[] }>('/api/shares').then((r) => r.shares);
export const revokeShare = (id: string) => apiJson(`/api/shares/${id}`, { method: 'DELETE' });

/** A link that opens the file for anyone who has it. The decryption secret is in the #fragment, which browsers never send. */
export async function shareArtifact(item: SealedItem, ttlHours: number): Promise<string> {
  const { wrappedKey, secretHex } = await C.makeShare(requireDek(), item.id, C.fromB64(item.wrapped_cek));
  const { share } = await apiJson<{ share: { token: string } }>('/api/shares', send('POST', {
    resource_type: 'artifact', resource_id: item.id, mode: 'link', wrapped_key: C.toB64(wrappedKey), ttl_hours: ttlHours,
  }));
  return `${window.location.origin}/s/${share.token}#${secretHex}`;
}

export async function shareConversation(sessionId: string, redactResearchData: boolean, ttlHours?: number): Promise<string> {
  const { share } = await apiJson<{ share: { token: string } }>('/api/shares', send('POST', {
    resource_type: 'conversation', resource_id: sessionId, mode: 'link',
    redact_research_data: redactResearchData, ...(ttlHours ? { ttl_hours: ttlHours } : {}),
  }));
  return `${window.location.origin}/s/${share.token}`;
}

export interface SharedArtifact {
  type: 'artifact';
  id: string;
  plaintext: Uint8Array;
  meta?: C.ArtifactMeta;
}

export interface SharedConversation {
  type: 'conversation';
  messages: Array<{ type: 'human' | 'ai'; content: string; timestamp: string }>;
  created_at: string;
}

/** Open a link share without being signed in: fetch, then decrypt locally with the secret from the URL fragment. */
export async function openSharedLink(token: string, secretHex: string): Promise<SharedArtifact | SharedConversation> {
  const res = await fetch(`${API_BASE}/api/share/${encodeURIComponent(token)}`);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(body?.error || `HTTP ${res.status}`, res.status);
  if (body.type === 'conversation') return body as SharedConversation;
  if (!secretHex) throw new VaultError('This link is missing its decryption key (the part after the #). Ask for the full link.');
  try {
    const opened = await C.openShared(
      body.id, C.fromB64(body.wrapped_key), secretHex, C.fromB64(body.ciphertext), body.meta_enc ? C.fromB64(body.meta_enc) : undefined,
    );
    return { type: 'artifact', id: body.id, ...opened };
  } catch {
    throw new VaultError('This link\'s key does not match the file. Check that you copied the whole link.');
  }
}

export const text = C.utf8;
