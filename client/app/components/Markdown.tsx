'use client';

import type { ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const NUMERIC = /^[\s$€£¥+\-−~≈<>()0-9.,%×xKMBT]+$/;

/** True when a cell or emphasis holds only a figure, so it can be set in mono. */
function isFigure(children: ReactNode) {
  const text = Array.isArray(children) ? children.join('') : children;
  return typeof text === 'string' && /\d/.test(text) && NUMERIC.test(text);
}

/** Renders assistant answers (headings, lists, tables, code) in the AIRAA theme. */
export default function Markdown({ children, streaming = false }: { children: string; streaming?: boolean }) {
  return (
    <div className={`break-words text-[15px] leading-[1.6] text-ink-2 ${streaming ? 'stream-caret' : ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (p) => <h2 className="mb-2 mt-5 font-display text-lg font-semibold text-ink first:mt-0" {...p} />,
          h2: (p) => <h3 className="mb-1.5 mt-[22px] font-display text-[17px] font-semibold text-ink first:mt-0" {...p} />,
          h3: (p) => <h4 className="mb-1.5 mt-4 font-display text-[15px] font-semibold text-ink first:mt-0" {...p} />,
          p: (p) => <p className="my-2.5 first:mt-0 last:mb-0" {...p} />,
          ul: (p) => <ul className="my-2.5 ml-5 list-disc space-y-1.5 marker:text-subtle" {...p} />,
          ol: (p) => <ol className="my-2.5 ml-5 list-decimal space-y-1.5 marker:text-subtle" {...p} />,
          strong: ({ children, ...rest }) => (
            <strong className={isFigure(children) ? 'font-mono font-medium text-ink' : 'font-semibold text-ink'} {...rest}>{children}</strong>
          ),
          hr: () => <hr className="my-4 border-white/[0.08]" />,
          a: (p) => (
            <a className="text-accent underline decoration-accent/40 underline-offset-2 hover:text-accent-hover" target="_blank" rel="noreferrer" {...p} />
          ),
          blockquote: (p) => <blockquote className="my-2.5 border-l-2 border-accent/50 pl-3 text-muted" {...p} />,
          code: ({ className, children, ...rest }) =>
            className ? (
              <code className={`${className} font-mono text-xs`} {...rest}>{children}</code>
            ) : (
              <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[0.85em]" {...rest}>{children}</code>
            ),
          pre: (p) => <pre className="my-2.5 overflow-x-auto rounded-lg border border-line bg-black/40 p-3" {...p} />,
          table: (p) => (
            <div className="my-3.5 overflow-x-auto rounded-[10px] border border-line">
              <table className="w-full border-collapse text-left text-[13px] sm:text-sm" {...p} />
            </div>
          ),
          thead: (p) => <thead className="bg-white/[0.04] text-muted" {...p} />,
          th: ({ style, ...p }) => <th className="px-3 py-2.5 font-medium" style={style} {...p} />,
          td: ({ children, style, ...rest }) => (
            <td
              className={`border-t border-white/[0.07] px-3 py-2.5 ${isFigure(children) ? 'whitespace-nowrap text-right font-mono text-[13px]' : ''}`}
              style={style}
              {...rest}
            >
              {children}
            </td>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
