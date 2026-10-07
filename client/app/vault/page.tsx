'use client';

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Copy, Download, KeyRound, Link2, Lock, LockOpen, ShieldCheck, Trash2, Upload } from 'lucide-react';
import PageShell, { RequireSignIn } from '../components/PageShell';
import { useAuth } from '../components/AuthProvider';
import { useVault } from '../components/useVault';
import {
  deleteArtifact, fetchVault, getVaultSnapshot, listArtifacts, listShares, lockVault, openArtifact, revokeShare, sealFile, shareArtifact,
  subscribeVault, type SealedItem, type ShareRow, type VaultInfo,
} from '../../lib/vault';
import { BTN_DANGER, BTN_PRIMARY, BTN_SECONDARY, CARD, INPUT, LABEL, NOTE_ERROR, NOTE_INFO, NOTE_OK, errorText, formatBytes, formatWhen } from '../components/ui';

const OVERHEAD_BYTES = 28; // 12-byte IV + 16-byte GCM tag
const TTLS: Array<[string, number]> = [['1 hour', 1], ['1 day', 24], ['7 days', 168], ['30 days', 720]];

export default function VaultPage() {
  return (
    <PageShell
      title="Encrypted vault"
      description="Keep research, reports and notes where only you can read them. Files are encrypted in your browser before upload; the server stores scrambled bytes and cannot open them, search them or hand them to anyone."
    >
      <RequireSignIn>
        <VaultBody />
      </RequireSignIn>
    </PageShell>
  );
}

function VaultBody() {
  const { wallet } = useAuth();
  const vault = useVault();
  const { unlocked } = useSyncExternalStore(subscribeVault, getVaultSnapshot, getVaultSnapshot);
  const [info, setInfo] = useState<VaultInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try { setInfo(await fetchVault()); setError(null); } catch (e) { setError(errorText(e)); }
  }, []);
  useEffect(() => { void reload(); }, [reload, wallet?.id]);

  if (error && !info) return <p role="alert" className={NOTE_ERROR}>{error}</p>;
  if (!info) return <div className="shimmer-tint h-48 rounded-3xl" aria-label="Loading vault" />;

  // The recovery key is shown exactly once, before anything else.
  if (recovery) return <RecoveryKeyCard recoveryKey={recovery} onDone={() => { setRecovery(null); void reload(); }} />;
  if (!info.initialized) return <SetupCard onCreated={(key) => setRecovery(key)} setup={vault.setup} />;
  if (!unlocked) return <UnlockCard info={info} vault={vault} />;
  return <Unlocked info={info} reloadInfo={reload} vault={vault} />;
}

// ------------------------------------------------------------------ setup
function SetupCard({ setup, onCreated }: { setup: (passphrase?: string) => Promise<{ recoveryKey: string }>; onCreated: (key: string) => void }) {
  const [pass, setPass] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tooShort = pass.length > 0 && pass.length < 10;

  const create = async () => {
    setBusy(true);
    setError(null);
    try { onCreated((await setup(pass || undefined)).recoveryKey); } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  return (
    <section className={CARD} aria-labelledby="setup-h">
      <h2 id="setup-h" className="m-0 flex items-center gap-2 font-display text-2xl font-bold tracking-[-0.4px]"><ShieldCheck className="h-6 w-6" aria-hidden="true" />Set up your vault</h2>
      <p className="mt-2 text-muted">Your wallet will sign one message (free, no transaction) to protect the vault key, and you will get a recovery key to keep somewhere safe.</p>
      <label htmlFor="setup-pass" className={`${LABEL} mt-4`}>Passphrase <span className="font-normal text-muted">(optional but recommended)</span></label>
      <input id="setup-pass" type="password" autoComplete="new-password" value={pass} onChange={(e) => setPass(e.target.value)} className={`${INPUT} max-w-md`} />
      <p className="mt-1.5 text-xs text-muted">A second way in, useful if your wallet ever signs differently (some smart wallets do). At least 10 characters.</p>
      {tooShort && <p className="mt-1 text-xs text-[#a3231a]">Use at least 10 characters, or leave it empty.</p>}
      {error && <p role="alert" className={`${NOTE_ERROR} mt-3`}>{error}</p>}
      <button type="button" onClick={create} disabled={busy || tooShort} className={`${BTN_PRIMARY} mt-4`}>{busy ? 'Waiting for your wallet…' : 'Create vault'}</button>
    </section>
  );
}

function RecoveryKeyCard({ recoveryKey, onDone }: { recoveryKey: string; onDone: () => void }) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const copy = async () => { try { await navigator.clipboard.writeText(recoveryKey); setCopied(true); } catch { /* clipboard blocked */ } };
  const download = () => {
    const url = URL.createObjectURL(new Blob([`airaa vault recovery key\n\n${recoveryKey}\n\nKeep this secret. Anyone with it and access to your account can read your vault.\n`], { type: 'text/plain' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: 'airaa-recovery-key.txt' });
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };
  return (
    <section className={`${CARD} border-ink`} aria-labelledby="rk-h">
      <h2 id="rk-h" className="m-0 flex items-center gap-2 font-display text-2xl font-bold tracking-[-0.4px]"><KeyRound className="h-6 w-6" aria-hidden="true" />Save your recovery key</h2>
      <p className="mt-2 text-muted">If you lose access to your wallet signature and passphrase, this is the only way to open your files. <strong className="text-ink">It is shown once and cannot be recovered.</strong></p>
      <p className="tabular mt-4 select-all break-all rounded-2xl bg-butter px-4 py-4 font-mono text-[15px] font-semibold leading-relaxed text-[#6b4e00]" data-testid="recovery-key">{recoveryKey}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={copy} className={BTN_SECONDARY}><Copy className="h-4 w-4" aria-hidden="true" />{copied ? 'Copied' : 'Copy'}</button>
        <button type="button" onClick={download} className={BTN_SECONDARY}><Download className="h-4 w-4" aria-hidden="true" />Download .txt</button>
      </div>
      <label className="mt-5 flex min-h-11 cursor-pointer items-start gap-3 text-sm font-semibold">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} className="mt-0.5 h-5 w-5 accent-[#0b0d12]" />
        I have saved my recovery key somewhere safe (a password manager or printed copy)
      </label>
      <button type="button" onClick={onDone} disabled={!saved} className={`${BTN_PRIMARY} mt-3`}>Continue to my vault</button>
    </section>
  );
}

// ------------------------------------------------------------------ unlock
function UnlockCard({ info, vault }: { info: VaultInfo; vault: ReturnType<typeof useVault> }) {
  const types = new Set(info.keys.map((k) => k.wrapper_type));
  const [pass, setPass] = useState('');
  const [rec, setRec] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const attempt = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };

  return (
    <section className={CARD} aria-labelledby="unlock-h">
      <h2 id="unlock-h" className="m-0 flex items-center gap-2 font-display text-2xl font-bold tracking-[-0.4px]"><Lock className="h-6 w-6" aria-hidden="true" />Your vault is locked</h2>
      <p className="mt-2 text-muted">It locks whenever you reload the page or sign out. Pick any way to open it.</p>
      {error && <p role="alert" className={`${NOTE_ERROR} mt-3`}>{error}</p>}
      <div className="mt-5 flex flex-col gap-6">
        {types.has('signature') && (
          <div>
            <button type="button" onClick={() => attempt(vault.unlockWithWallet)} disabled={busy} className={BTN_PRIMARY}><LockOpen className="h-4 w-4" aria-hidden="true" />{busy ? 'Check your wallet…' : 'Unlock with my wallet'}</button>
            <p className="mt-1.5 text-xs text-muted">Signs a free message. Nothing is sent on-chain.</p>
          </div>
        )}
        {types.has('passphrase') && (
          <form onSubmit={(e) => { e.preventDefault(); if (pass) void attempt(() => vault.unlockWithPassphrase(pass)); }}>
            <label htmlFor="unlock-pass" className={LABEL}>Passphrase</label>
            <div className="flex flex-wrap gap-2">
              <input id="unlock-pass" type="password" autoComplete="current-password" value={pass} onChange={(e) => setPass(e.target.value)} className={`${INPUT} max-w-sm`} />
              <button type="submit" disabled={busy || !pass} className={BTN_SECONDARY}>Unlock</button>
            </div>
          </form>
        )}
        {types.has('recovery') && (
          <form onSubmit={(e) => { e.preventDefault(); if (rec.trim()) void attempt(() => vault.unlockWithRecoveryKey(rec)); }}>
            <label htmlFor="unlock-rec" className={LABEL}>Recovery key</label>
            <div className="flex flex-wrap gap-2">
              <input id="unlock-rec" value={rec} onChange={(e) => setRec(e.target.value)} autoComplete="off" spellCheck={false} placeholder="xxxxxxxx-xxxxxxxx-…" className={`${INPUT} max-w-lg font-mono text-sm`} />
              <button type="submit" disabled={busy || !rec.trim()} className={BTN_SECONDARY}>Unlock</button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ unlocked
function Unlocked({ info, reloadInfo, vault }: { info: VaultInfo; reloadInfo: () => Promise<void>; vault: ReturnType<typeof useVault> }) {
  const [items, setItems] = useState<SealedItem[] | null>(null);
  const [shares, setShares] = useState<ShareRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [link, setLink] = useState<{ id: string; url: string } | null>(null);
  const [ttl, setTtl] = useState(24);
  const [summary, setSummary] = useState('');
  const file = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const [list, sh] = await Promise.all([listArtifacts(), listShares()]);
      setItems(list);
      setShares(sh.filter((s) => s.resource_type === 'artifact' && !s.revoked_at));
      setError(null);
    } catch (e) { setError(errorText(e)); setItems((c) => c ?? []); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const work = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    try { await fn(); } catch (e) { setError(errorText(e)); } finally { setBusy(null); }
  };

  const upload = (f: File | undefined) => {
    if (!f) return;
    void work('upload', async () => {
      if (f.size + OVERHEAD_BYTES > info.limits.max_artifact_bytes) throw new Error(`Files can be at most ${formatBytes(info.limits.max_artifact_bytes - OVERHEAD_BYTES)}`);
      await sealFile(new Uint8Array(await f.arrayBuffer()), { title: f.name, name: f.name, mime: f.type || 'application/octet-stream' }, summary || undefined);
      setSummary('');
      if (file.current) file.current.value = '';
      await load();
    });
  };

  const download = (item: SealedItem) => work(item.id, async () => {
    const bytes = await openArtifact(item);
    const url = URL.createObjectURL(new Blob([bytes as unknown as BlobPart], { type: item.meta?.mime ?? 'application/octet-stream' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: item.meta?.name ?? item.meta?.title ?? `${item.id}.bin` });
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  });

  const share = (item: SealedItem) => work(item.id, async () => {
    setLink({ id: item.id, url: await shareArtifact(item, ttl) });
    await load();
  });

  const remove = (item: SealedItem) => {
    if (!window.confirm(`Delete “${item.meta?.title ?? 'this file'}” permanently? Anyone with a share link will lose access too.`)) return;
    void work(item.id, async () => { await deleteArtifact(item.id); await load(); });
  };

  return (
    <>
      <section className={`${NOTE_OK} flex flex-wrap items-center gap-3`}>
        <span className="inline-flex items-center gap-2 font-semibold"><LockOpen className="h-4 w-4" aria-hidden="true" />Vault unlocked for this tab</span>
        <button type="button" onClick={lockVault} className={`${BTN_SECONDARY} ml-auto`}>Lock now</button>
      </section>
      {error && <p role="alert" className={NOTE_ERROR}>{error}</p>}

      <section className={CARD} aria-labelledby="up-h">
        <h2 id="up-h" className="m-0 font-display text-2xl font-bold tracking-[-0.4px]">Add a file</h2>
        <p className="mt-1.5 text-sm text-muted">Up to {formatBytes(info.limits.max_artifact_bytes - OVERHEAD_BYTES)}. It is encrypted here, then uploaded. You can also save any chat answer to the vault from the chat page.</p>
        <label htmlFor="up-sum" className={`${LABEL} mt-4`}>Search blurb <span className="font-normal text-muted">(optional)</span></label>
        <input id="up-sum" value={summary} onChange={(e) => setSummary(e.target.value)} maxLength={600} placeholder="A short description so you can find this by meaning later" className={INPUT} />
        <p className="mt-1 text-xs text-muted">Only this blurb is readable by the server (to make the file searchable). Leave it empty to keep the file fully opaque.</p>
        <input ref={file} id="up-file" type="file" className="sr-only" onChange={(e) => upload(e.target.files?.[0])} disabled={busy === 'upload'} />
        <label htmlFor="up-file" className={`${BTN_PRIMARY} mt-4 cursor-pointer ${busy === 'upload' ? 'pointer-events-none opacity-50' : ''}`}>
          <Upload className="h-4 w-4" aria-hidden="true" />{busy === 'upload' ? 'Encrypting…' : 'Choose a file'}
        </label>
      </section>

      <section className={CARD} aria-labelledby="files-h">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="files-h" className="m-0 font-display text-2xl font-bold tracking-[-0.4px]">Your files</h2>
          <label className="ml-auto inline-flex items-center gap-2 text-sm font-semibold">Share links last
            <select value={ttl} onChange={(e) => setTtl(Number(e.target.value))} className="min-h-10 rounded-full bg-field px-3 font-semibold">
              {TTLS.map(([label, h]) => <option key={h} value={h}>{label}</option>)}
            </select>
          </label>
        </div>
        {link && (
          <div className={`${NOTE_INFO} mt-4`}>
            <p className="m-0 font-semibold">Share link (copy it now: the decryption key is in the part after the #, which we never see)</p>
            <p className="mt-2 select-all break-all font-mono text-xs" data-testid="share-link">{link.url}</p>
            <button type="button" className={`${BTN_SECONDARY} mt-2`} onClick={() => void navigator.clipboard.writeText(link.url)}><Copy className="h-4 w-4" aria-hidden="true" />Copy link</button>
          </div>
        )}
        <ul className="mt-4 flex list-none flex-col gap-2.5 p-0">
          {items === null && [0, 1].map((i) => <li key={i} className="shimmer-tint h-16 rounded-2xl" />)}
          {items?.length === 0 && <li className="text-sm text-muted">No files yet.</li>}
          {items?.map((item) => {
            const live = shares.filter((s) => s.resource_id === item.id);
            return (
              <li key={item.id} className="rounded-2xl bg-soft p-3.5">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <p className="m-0 truncate font-semibold">{item.meta?.title ?? 'Unreadable with this key'}</p>
                    <p className="m-0 mt-0.5 text-xs text-muted">{formatBytes(item.size_bytes)} · {formatWhen(item.created_at)}{item.index_summary ? ' · searchable' : ''}{live.length ? ` · ${live.length} active link${live.length > 1 ? 's' : ''}` : ''}</p>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <button type="button" onClick={() => download(item)} disabled={busy === item.id || !item.meta} className={BTN_SECONDARY}><Download className="h-4 w-4" aria-hidden="true" />Download</button>
                    <button type="button" onClick={() => share(item)} disabled={busy === item.id || !item.meta} className={BTN_SECONDARY}><Link2 className="h-4 w-4" aria-hidden="true" />Share</button>
                    <button type="button" onClick={() => remove(item)} disabled={busy === item.id} className={BTN_DANGER} aria-label={`Delete ${item.meta?.title ?? 'file'}`}><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
                  </div>
                </div>
                {live.map((s) => (
                  <p key={s.id} className="m-0 mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                    Link created {formatWhen(s.created_at)}, expires {formatWhen(s.expires_at)}
                    <button type="button" className="font-bold text-[#a3231a] underline" onClick={() => work(s.id, async () => { await revokeShare(s.id); await load(); })}>Revoke</button>
                  </p>
                ))}
              </li>
            );
          })}
        </ul>
        <p className="mt-4 text-xs text-muted">Revoking a link stops it working, but someone who already opened it keeps what they saw.</p>
      </section>

      <Security walletReload={reloadInfo} vault={vault} hasPassphrase={info.keys.some((k) => k.wrapper_type === 'passphrase')} />
    </>
  );
}

function Security({ vault, hasPassphrase, walletReload }: { vault: ReturnType<typeof useVault>; hasPassphrase: boolean; walletReload: () => Promise<void> }) {
  const [pass, setPass] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMsg(null);
    try { await fn(); await walletReload(); } catch (e) { setMsg({ ok: false, text: errorText(e) }); } finally { setBusy(false); }
  };

  return (
    <section className={CARD} aria-labelledby="sec-h">
      <h2 id="sec-h" className="m-0 font-display text-2xl font-bold tracking-[-0.4px]">Ways to unlock</h2>
      <form className="mt-4" onSubmit={(e) => { e.preventDefault(); if (pass.length >= 10) void run(async () => { await vault.setPassphrase(pass); setPass(''); setMsg({ ok: true, text: 'Passphrase saved.' }); }); }}>
        <label htmlFor="sec-pass" className={LABEL}>{hasPassphrase ? 'Change passphrase' : 'Add a passphrase'} <span className="font-normal text-muted">(at least 10 characters)</span></label>
        <div className="flex flex-wrap gap-2">
          <input id="sec-pass" type="password" autoComplete="new-password" value={pass} onChange={(e) => setPass(e.target.value)} className={`${INPUT} max-w-sm`} />
          <button type="submit" disabled={busy || pass.length < 10} className={BTN_SECONDARY}>Save</button>
        </div>
      </form>
      <div className="mt-5">
        <button type="button" disabled={busy} className={BTN_SECONDARY} onClick={() => run(async () => { setNewKey(await vault.rotateRecoveryKey()); })}><KeyRound className="h-4 w-4" aria-hidden="true" />Create a new recovery key</button>
        <p className="mt-1.5 text-xs text-muted">The old recovery key stops working.</p>
      </div>
      {newKey && (
        <div className="mt-3 rounded-2xl bg-butter p-4">
          <p className="m-0 text-sm font-semibold text-[#6b4e00]">Your new recovery key (shown once)</p>
          <p className="tabular mt-2 select-all break-all font-mono text-sm font-semibold" data-testid="recovery-key">{newKey}</p>
          <button type="button" className={`${BTN_SECONDARY} mt-2`} onClick={() => setNewKey(null)}>I saved it</button>
        </div>
      )}
      {msg && <p role={msg.ok ? 'status' : 'alert'} className={`${msg.ok ? NOTE_OK : NOTE_ERROR} mt-3`}>{msg.text}</p>}
    </section>
  );
}
