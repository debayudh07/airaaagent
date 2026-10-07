// Run with: npm run test:crypto   (Node 22.6+; uses Node's real WebCrypto, the same API the browser uses)
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { ArtifactMeta } from '../lib/vaultCrypto.ts';
import {
  PBKDF2_ITERATIONS, decryptFile, decryptMeta, encryptFile, fromB64, fromHex, kekFromPassphrase,
  kekFromRecoveryKey, kekFromSignature, makeShare, newDek, newRecoveryKey, newSalt, openShared, parseRecoveryKey,
  toB64, toHex, unwrapDek, utf8, vaultMessage, wrapDek,
} from '../lib/vaultCrypto.ts';

const WALLET = '11111111-1111-4111-8111-111111111111';
const ART = '22222222-2222-4222-8222-222222222222';
const META: ArtifactMeta = { title: 'Aave risk notes', mime: 'text/markdown', name: 'aave.md', createdAt: '2026-10-07T00:00:00.000Z' };
const SIG_A = '0x' + 'ab'.repeat(65);
const SIG_B = '0x' + 'cd'.repeat(65);

/** Two DEKs are the same key iff one decrypts what the other encrypted. */
async function sameDek(a: CryptoKey, b: CryptoKey) {
  const sealed = await encryptFile(a, ART, utf8.encode('probe'), META);
  return utf8.decode(await decryptFile(b, ART, sealed.ciphertext, sealed.wrappedCek)) === 'probe';
}

test('base64 and hex roundtrip, including large buffers', () => {
  const big = new Uint8Array(1_500_000).map((_, i) => i % 251);
  assert.deepEqual(fromB64(toB64(big)), big);
  assert.deepEqual(fromHex(toHex(big.subarray(0, 100))), big.subarray(0, 100));
  assert.throws(() => fromHex('xyz'));
  assert.throws(() => fromHex('abc'));
});

test('a file survives encrypt -> decrypt and the server-visible parts reveal nothing', async () => {
  const dek = await newDek();
  const secret = 'TOP SECRET: portfolio is 80% ETH';
  const sealed = await encryptFile(dek, ART, utf8.encode(secret), META);

  assert.equal(utf8.decode(await decryptFile(dek, ART, sealed.ciphertext, sealed.wrappedCek)), secret);
  assert.deepEqual(await decryptMeta(dek, ART, sealed.wrappedCek, sealed.metaEnc), META);

  const everythingTheServerSees = utf8.decode(sealed.ciphertext) + utf8.decode(sealed.wrappedCek) + utf8.decode(sealed.metaEnc);
  assert.ok(!everythingTheServerSees.includes('SECRET') && !everythingTheServerSees.includes('Aave'));
  assert.ok(sealed.ciphertext.length >= 29 && sealed.ciphertext.length === 12 + secret.length + 16);   // IV + data + tag
});

test('every encryption uses a fresh key and nonce', async () => {
  const dek = await newDek();
  const a = await encryptFile(dek, ART, utf8.encode('same'), META);
  const b = await encryptFile(dek, ART, utf8.encode('same'), META);
  assert.notDeepEqual(a.ciphertext, b.ciphertext);
  assert.notDeepEqual(a.wrappedCek, b.wrappedCek);
});

test('tampering, the wrong artifact id and the wrong key are all detected', async () => {
  const dek = await newDek();
  const sealed = await encryptFile(dek, ART, utf8.encode('payload'), META);

  const flipped = sealed.ciphertext.slice();
  flipped[20] ^= 1;
  await assert.rejects(decryptFile(dek, ART, flipped, sealed.wrappedCek));
  await assert.rejects(decryptFile(dek, ART.replace('2', '3'), sealed.ciphertext, sealed.wrappedCek));   // bound to its artifact
  await assert.rejects(decryptFile(await newDek(), ART, sealed.ciphertext, sealed.wrappedCek));
  await assert.rejects(decryptFile(dek, ART, sealed.ciphertext.slice(0, 20), sealed.wrappedCek));        // truncated
  await assert.rejects(decryptMeta(dek, ART, sealed.wrappedCek, sealed.metaEnc.slice(0, -1)));
});

test('large files (5 MB) round trip', async () => {
  const dek = await newDek();
  const data = new Uint8Array(5 * 1024 * 1024);
  for (let i = 0; i < data.length; i += 65536) globalThis.crypto.getRandomValues(data.subarray(i, i + 65536));
  const sealed = await encryptFile(dek, ART, data, META);
  assert.deepEqual(await decryptFile(dek, ART, sealed.ciphertext, sealed.wrappedCek), data);
});

test('the signature wrapper unlocks with the same signature and fails with another', async () => {
  const dek = await newDek();
  const salt = newSalt();
  const wrapped = await wrapDek(dek, await kekFromSignature(SIG_A, salt), WALLET, 'signature');

  assert.ok(await sameDek(dek, await unwrapDek(wrapped, await kekFromSignature(SIG_A, salt), WALLET, 'signature')));
  await assert.rejects(unwrapDek(wrapped, await kekFromSignature(SIG_B, salt), WALLET, 'signature'));   // a smart wallet's different signature
  await assert.rejects(unwrapDek(wrapped, await kekFromSignature(SIG_A, newSalt()), WALLET, 'signature'));
});

test('passphrase and recovery wrappers open the same DEK as the signature wrapper', async () => {
  const dek = await newDek();
  const sigSalt = newSalt(), passSalt = newSalt(), recSalt = newSalt();
  const recovery = newRecoveryKey();

  const bySig = await wrapDek(dek, await kekFromSignature(SIG_A, sigSalt), WALLET, 'signature');
  const byPass = await wrapDek(dek, await kekFromPassphrase('correct horse battery staple', passSalt), WALLET, 'passphrase');
  const byRec = await wrapDek(dek, await kekFromRecoveryKey(recovery.bytes, recSalt), WALLET, 'recovery');

  const viaPass = await unwrapDek(byPass, await kekFromPassphrase('correct horse battery staple', passSalt), WALLET, 'passphrase');
  const viaRec = await unwrapDek(byRec, await kekFromRecoveryKey(parseRecoveryKey(recovery.display), recSalt), WALLET, 'recovery');
  const viaSig = await unwrapDek(bySig, await kekFromSignature(SIG_A, sigSalt), WALLET, 'signature');
  assert.ok(await sameDek(viaPass, viaRec) && await sameDek(viaRec, viaSig) && await sameDek(viaSig, dek));

  await assert.rejects(unwrapDek(byPass, await kekFromPassphrase('wrong passphrase', passSalt), WALLET, 'passphrase'));
});

test('wrapped keys are bound to their wallet and wrapper type', async () => {
  const dek = await newDek();
  const salt = newSalt();
  const kek = await kekFromSignature(SIG_A, salt);
  const wrapped = await wrapDek(dek, kek, WALLET, 'signature');
  await assert.rejects(unwrapDek(wrapped, kek, WALLET.replace('1', '9'), 'signature'));   // moved to another account
  await assert.rejects(unwrapDek(wrapped, kek, WALLET, 'passphrase'));                    // presented as another wrapper
});

test('passphrases are unicode-normalised and use the documented work factor', async () => {
  assert.equal(PBKDF2_ITERATIONS, 600_000);
  const dek = await newDek();
  const salt = newSalt();
  const wrapped = await wrapDek(dek, await kekFromPassphrase('café', salt), WALLET, 'passphrase');   // precomposed é
  const viaDecomposed = await unwrapDek(wrapped, await kekFromPassphrase('café', salt), WALLET, 'passphrase');
  assert.ok(await sameDek(dek, viaDecomposed));
});

test('recovery keys are 64 hex characters and validated', () => {
  const key = newRecoveryKey();
  assert.match(key.display, /^([0-9a-f]{8}-){7}[0-9a-f]{8}$/);
  assert.deepEqual(parseRecoveryKey(key.display.toUpperCase()), key.bytes);
  assert.deepEqual(parseRecoveryKey(key.display.replace(/-/g, ' ')), key.bytes);
  assert.throws(() => parseRecoveryKey('abcd'));
  assert.throws(() => parseRecoveryKey('zz'.repeat(32)));
  assert.notEqual(newRecoveryKey().display, key.display);
});

test('the vault message names the site and wallet', () => {
  const message = vaultMessage('app.example.com', '0xABCDEF0123456789ABCDEF0123456789ABCDEF01');
  assert.ok(message.includes('app.example.com') && message.includes('0xabcdef0123456789abcdef0123456789abcdef01'));
});

test('a link share opens with the secret, for someone without the vault', async () => {
  const dek = await newDek();
  const sealed = await encryptFile(dek, ART, utf8.encode('shared research'), META);
  const share = await makeShare(dek, ART, sealed.wrappedCek);

  assert.match(share.secretHex, /^[0-9a-f]{64}$/);
  const opened = await openShared(ART, share.wrappedKey, share.secretHex, sealed.ciphertext, sealed.metaEnc);
  assert.equal(utf8.decode(opened.plaintext), 'shared research');
  assert.deepEqual(opened.meta, META);

  const wrongSecret = toHex(globalThis.crypto.getRandomValues(new Uint8Array(32)));
  await assert.rejects(openShared(ART, share.wrappedKey, wrongSecret, sealed.ciphertext));
  await assert.rejects(openShared(ART.replace('2', '5'), share.wrappedKey, share.secretHex, sealed.ciphertext));   // bound to the artifact
  // the server-stored wrapped key alone (without the URL fragment) is useless, and it is not the vault's DEK
  await assert.rejects(decryptFile(dek, ART, sealed.ciphertext, share.wrappedKey));
});

test('sharing one file does not expose another', async () => {
  const dek = await newDek();
  const other = '33333333-3333-4333-8333-333333333333';
  const a = await encryptFile(dek, ART, utf8.encode('file A'), META);
  const b = await encryptFile(dek, other, utf8.encode('file B'), META);
  const share = await makeShare(dek, ART, a.wrappedCek);
  await assert.rejects(openShared(other, share.wrappedKey, share.secretHex, b.ciphertext));
});
