/**
 * Client-side encryption for sealed files. Pure WebCrypto: no React, no network, no wagmi, so it runs unchanged in
 * the browser and under Node (see tests/vault-crypto.test.mts).
 *
 * Key hierarchy (the server only ever sees wrapped keys and ciphertext):
 *
 *   wrapper secrets ──derive──► KEK ──wrap──► DEK (one random key per user) ──wrap──► CEK (one random key per file)
 *   signature | passphrase | recovery key                                              └─ encrypts the file + its metadata
 *
 * Why a random DEK instead of deriving the data key straight from a wallet signature: smart-contract wallets do not
 * produce repeatable signatures, so a signature-derived key could change and lock the user out. A random DEK that is
 * wrapped separately by a signature, a passphrase and a recovery key survives any single wrapper failing.
 *
 * Wire format of every encrypted blob: 12-byte random IV || AES-256-GCM ciphertext+tag.
 */

export type WrapperType = 'signature' | 'passphrase' | 'recovery';

export interface Kdf {
  v: 1;
  /** base64 HKDF/PBKDF2 salt */
  salt: string;
  /** passphrase wrapper only */
  iterations?: number;
  /** signature wrapper only: the exact text that was signed (re-signed verbatim to unlock) */
  message?: string;
}

export interface ArtifactMeta {
  title: string;
  mime: string;
  /** original file name, if any */
  name?: string;
  createdAt: string;
}

export const PBKDF2_ITERATIONS = 600_000;
const IV_BYTES = 12;
const enc = new TextEncoder();
const dec = new TextDecoder();

/** Typed-array to BufferSource: TS 5.9 distinguishes ArrayBuffer from ArrayBufferLike backing stores. */
const bs = (u: Uint8Array) => u as unknown as BufferSource;
const subtle = () => globalThis.crypto.subtle;
const random = (n: number) => globalThis.crypto.getRandomValues(new Uint8Array(n));

// ------------------------------------------------------------------ encodings
export function toB64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export function fromB64(text: string): Uint8Array {
  const binary = atob(text);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

export function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

export function fromHex(text: string): Uint8Array {
  const clean = text.trim().replace(/^0x/i, '');
  if (clean.length % 2 !== 0 || !/^[0-9a-fA-F]*$/.test(clean)) throw new Error('Not a valid hex string');
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  return out;
}

const concat = (a: Uint8Array, b: Uint8Array) => {
  const out = new Uint8Array(a.length + b.length);
  out.set(a);
  out.set(b, a.length);
  return out;
};

// ------------------------------------------------------------------ AES-GCM blobs
async function seal(key: CryptoKey, plaintext: Uint8Array, aad: string): Promise<Uint8Array> {
  const iv = random(IV_BYTES);
  const ct = new Uint8Array(await subtle().encrypt({ name: 'AES-GCM', iv: bs(iv), additionalData: bs(enc.encode(aad)) }, key, bs(plaintext)));
  return concat(iv, ct);
}

async function open(key: CryptoKey, blob: Uint8Array, aad: string): Promise<Uint8Array> {
  if (blob.length < IV_BYTES + 16) throw new Error('Encrypted data is too short');
  const iv = blob.slice(0, IV_BYTES);
  return new Uint8Array(await subtle().decrypt({ name: 'AES-GCM', iv: bs(iv), additionalData: bs(enc.encode(aad)) }, key, bs(blob.slice(IV_BYTES))));
}

async function wrap(key: CryptoKey, wrapper: CryptoKey, aad: string): Promise<Uint8Array> {
  const iv = random(IV_BYTES);
  const ct = new Uint8Array(await subtle().wrapKey('raw', key, wrapper, { name: 'AES-GCM', iv: bs(iv), additionalData: bs(enc.encode(aad)) }));
  return concat(iv, ct);
}

async function unwrap(blob: Uint8Array, wrapper: CryptoKey, aad: string, usages: KeyUsage[]): Promise<CryptoKey> {
  const iv = blob.slice(0, IV_BYTES);
  return subtle().unwrapKey(
    'raw', bs(blob.slice(IV_BYTES)), wrapper,
    { name: 'AES-GCM', iv: bs(iv), additionalData: bs(enc.encode(aad)) },
    { name: 'AES-GCM', length: 256 }, true, usages,
  );
}

// ------------------------------------------------------------------ KEKs (one per way of unlocking)
async function hkdfKek(secret: Uint8Array, salt: Uint8Array, info: string): Promise<CryptoKey> {
  const base = await subtle().importKey('raw', bs(secret), 'HKDF', false, ['deriveKey']);
  return subtle().deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt: bs(salt), info: bs(enc.encode(info)) },
    base, { name: 'AES-GCM', length: 256 }, false, ['wrapKey', 'unwrapKey'],
  );
}

/** The text a wallet signs to unlock. It names the site and wallet so a signature cannot be replayed elsewhere by accident. */
export function vaultMessage(host: string, address: string): string {
  return [
    'airaa vault key',
    '',
    `This signature unlocks your encrypted airaa files. Only sign it on ${host}. It costs no gas and authorises no transaction.`,
    '',
    `Wallet: ${address.toLowerCase()}`,
    'Version: 1',
  ].join('\n');
}

export const newSalt = () => toB64(random(16));

export function kekFromSignature(signatureHex: string, saltB64: string): Promise<CryptoKey> {
  return hkdfKek(fromHex(signatureHex), fromB64(saltB64), 'airaa-vault-kek-v1');
}

export async function kekFromPassphrase(passphrase: string, saltB64: string, iterations = PBKDF2_ITERATIONS): Promise<CryptoKey> {
  const base = await subtle().importKey('raw', bs(enc.encode(passphrase.normalize('NFKC'))), 'PBKDF2', false, ['deriveKey']);
  return subtle().deriveKey(
    { name: 'PBKDF2', hash: 'SHA-256', salt: bs(fromB64(saltB64)), iterations },
    base, { name: 'AES-GCM', length: 256 }, false, ['wrapKey', 'unwrapKey'],
  );
}

export function kekFromRecoveryKey(recoveryBytes: Uint8Array, saltB64: string): Promise<CryptoKey> {
  return hkdfKek(recoveryBytes, fromB64(saltB64), 'airaa-vault-recovery-v1');
}

/** 256 random bits shown as 8 groups of 8 hex characters: easy to copy, print or read aloud. */
export function newRecoveryKey(): { bytes: Uint8Array; display: string } {
  const bytes = random(32);
  return { bytes, display: toHex(bytes).match(/.{8}/g)!.join('-') };
}

export function parseRecoveryKey(text: string): Uint8Array {
  const clean = text.replace(/[\s-]/g, '');
  if (!/^[0-9a-fA-F]{64}$/.test(clean)) {
    throw new Error('That does not look like a recovery key: it is 64 characters (0-9 and a-f), usually shown in groups with dashes');
  }
  return fromHex(clean);
}

// ------------------------------------------------------------------ DEK
export function newDek(): Promise<CryptoKey> {
  return subtle().generateKey({ name: 'AES-GCM', length: 256 }, true, ['wrapKey', 'unwrapKey']);
}

const dekAad = (walletId: string, type: WrapperType) => `dek:${walletId}:${type}`;

export const wrapDek = (dek: CryptoKey, kek: CryptoKey, walletId: string, type: WrapperType) => wrap(dek, kek, dekAad(walletId, type));

export const unwrapDek = (blob: Uint8Array, kek: CryptoKey, walletId: string, type: WrapperType) =>
  unwrap(blob, kek, dekAad(walletId, type), ['wrapKey', 'unwrapKey']);

// ------------------------------------------------------------------ files
const cekAad = (artifactId: string) => `cek:${artifactId}`;
const metaAad = (artifactId: string) => `meta:${artifactId}`;
// The content is bound to its artifact id (not the wallet id) so a shared copy can be decrypted by a recipient
// who knows neither the owner nor the vault.
const dataAad = (artifactId: string) => `data:${artifactId}`;

export interface SealedFile {
  ciphertext: Uint8Array;
  wrappedCek: Uint8Array;
  metaEnc: Uint8Array;
}

/** Encrypt a file with a fresh content key, wrap that key with the DEK, and encrypt its metadata with the same key. */
export async function encryptFile(dek: CryptoKey, artifactId: string, plaintext: Uint8Array, meta: ArtifactMeta): Promise<SealedFile> {
  const cek = await subtle().generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt', 'decrypt']);
  return {
    ciphertext: await seal(cek, plaintext, dataAad(artifactId)),
    wrappedCek: await wrap(cek, dek, cekAad(artifactId)),
    metaEnc: await seal(cek, enc.encode(JSON.stringify(meta)), metaAad(artifactId)),
  };
}

const unwrapCek = (dek: CryptoKey, artifactId: string, wrappedCek: Uint8Array) =>
  unwrap(wrappedCek, dek, cekAad(artifactId), ['encrypt', 'decrypt']);

export async function decryptFile(dek: CryptoKey, artifactId: string, ciphertext: Uint8Array, wrappedCek: Uint8Array): Promise<Uint8Array> {
  return open(await unwrapCek(dek, artifactId, wrappedCek), ciphertext, dataAad(artifactId));
}

export async function decryptMeta(dek: CryptoKey, artifactId: string, wrappedCek: Uint8Array, metaEnc: Uint8Array): Promise<ArtifactMeta> {
  const cek = await unwrapCek(dek, artifactId, wrappedCek);
  return JSON.parse(dec.decode(await open(cek, metaEnc, metaAad(artifactId))));
}

// ------------------------------------------------------------------ link sharing
// A link carries a random secret in the URL fragment (never sent to any server). The file's content key is re-wrapped
// with a key derived from that secret; the server stores only the wrapped key and ciphertext.
const shareKek = (secret: Uint8Array) => hkdfKek(secret, new Uint8Array(0), 'airaa-share-v1');
const shareAad = (artifactId: string) => `share:${artifactId}`;

export async function makeShare(dek: CryptoKey, artifactId: string, wrappedCek: Uint8Array): Promise<{ wrappedKey: Uint8Array; secretHex: string }> {
  const cek = await unwrapCek(dek, artifactId, wrappedCek);
  const secret = random(32);
  return { wrappedKey: await wrap(cek, await shareKek(secret), shareAad(artifactId)), secretHex: toHex(secret) };
}

export async function openShared(
  artifactId: string, wrappedKey: Uint8Array, secretHex: string, ciphertext: Uint8Array, metaEnc?: Uint8Array,
): Promise<{ plaintext: Uint8Array; meta?: ArtifactMeta }> {
  const cek = await unwrap(wrappedKey, await shareKek(fromHex(secretHex)), shareAad(artifactId), ['encrypt', 'decrypt']);
  const plaintext = await open(cek, ciphertext, dataAad(artifactId));
  const meta = metaEnc ? (JSON.parse(dec.decode(await open(cek, metaEnc, metaAad(artifactId)))) as ArtifactMeta) : undefined;
  return { plaintext, meta };
}

export const utf8 = { encode: (s: string) => enc.encode(s), decode: (b: Uint8Array) => dec.decode(b) };
