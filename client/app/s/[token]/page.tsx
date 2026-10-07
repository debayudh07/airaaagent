'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Download, Lock } from 'lucide-react';
import Link from 'next/link';
import Logo from '../../components/Logo';
import Markdown from '../../components/Markdown';
import { openSharedLink, text, type SharedArtifact, type SharedConversation } from '../../../lib/vault';
import { BTN_PRIMARY, NOTE_ERROR, errorText, formatWhen } from '../../components/ui';

type Loaded = SharedArtifact | SharedConversation;

/** Public viewer for a share link. Decryption of sealed files happens here, with the key from the URL fragment. */
export default function SharedPage() {
  const { token } = useParams<{ token: string }>();
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const secret = window.location.hash.replace(/^#/, '');
    let cancelled = false;
    openSharedLink(token, secret)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(errorText(e)));
    return () => { cancelled = true; };
  }, [token]);

  return (
    <div className="min-h-dvh bg-bg text-[15px] leading-normal text-ink">
      <header className="border-b border-line-2">
        <div className="mx-auto flex max-w-[780px] items-center gap-3 px-4 py-3 sm:px-6"><Logo /><span className="ml-auto text-sm text-muted">Shared with you</span></div>
      </header>
      <main className="mx-auto max-w-[780px] px-4 pb-20 pt-8 sm:px-6 sm:pt-12">
        {error && <p role="alert" className={NOTE_ERROR}>{error}</p>}
        {!error && !data && <div className="shimmer-tint h-40 rounded-3xl" aria-label="Loading" />}
        {data?.type === 'conversation' && <Conversation data={data} />}
        {data?.type === 'artifact' && <Artifact data={data} />}
        <p className="mt-10 text-center text-[13px] text-muted">AI-generated research, not financial advice. <Link href="/" className="font-semibold underline">Try airaa</Link></p>
      </main>
    </div>
  );
}

function Conversation({ data }: { data: SharedConversation }) {
  return (
    <>
      <h1 className="m-0 font-display text-[28px] font-extrabold tracking-[-0.8px] sm:text-[36px]">A shared conversation</h1>
      <p className="mt-1.5 text-sm text-muted">Started {formatWhen(data.created_at)}. Read-only.</p>
      <div className="mt-8 flex flex-col gap-6">
        {data.messages.map((m, i) => m.type === 'human' ? (
          <div key={i} className="max-w-[85%] self-end whitespace-pre-wrap rounded-[24px_24px_6px_24px] bg-ink px-[18px] py-3 text-base text-white">{m.content}</div>
        ) : (
          <div key={i}><Markdown>{m.content}</Markdown></div>
        ))}
      </div>
    </>
  );
}

function Artifact({ data }: { data: SharedArtifact }) {
  const mime = data.meta?.mime ?? 'application/octet-stream';
  const readable = /^text\/|json$/.test(mime);
  const body = readable ? text.decode(data.plaintext) : null;
  const download = () => {
    const url = URL.createObjectURL(new Blob([data.plaintext as unknown as BlobPart], { type: mime }));
    const a = Object.assign(document.createElement('a'), { href: url, download: data.meta?.name ?? data.meta?.title ?? 'shared-file' });
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };
  return (
    <>
      <p className="m-0 inline-flex items-center gap-1.5 rounded-full bg-mint px-3 py-1 text-xs font-bold text-[#0f5b3a]"><Lock className="h-3.5 w-3.5" aria-hidden="true" />Decrypted in your browser</p>
      <h1 className="m-0 mt-3 font-display text-[28px] font-extrabold tracking-[-0.8px] sm:text-[36px]">{data.meta?.title ?? 'Shared file'}</h1>
      {data.meta && <p className="mt-1.5 text-sm text-muted">{mime} · saved {formatWhen(data.meta.createdAt)}</p>}
      <button type="button" onClick={download} className={`${BTN_PRIMARY} mt-4`}><Download className="h-4 w-4" aria-hidden="true" />Download</button>
      {body !== null && (
        <div className="mt-6 rounded-3xl border border-line p-5 sm:p-6">
          {mime.includes('markdown') ? <Markdown>{body}</Markdown> : <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-words text-sm">{body}</pre>}
        </div>
      )}
    </>
  );
}
