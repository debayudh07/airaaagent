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
    <div className={`break-words text-base leading-[1.65] text-ink-2 ${streaming ? 'stream-caret' : ''}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (p) => <h2 className="mb-2 mt-5 font-display text-xl font-bold text-ink first:mt-0" {...p} />,
          h2: (p) => <h3 className="mb-2 mt-[22px] font-display text-[19px] font-bold text-ink first:mt-0" {...p} />,
          h3: (p) => <h4 className="mb-1.5 mt-4 font-display text-base font-bold text-ink first:mt-0" {...p} />,
          p: (p) => <p className="my-2.5 first:mt-0 last:mb-0" {...p} />,
          ul: (p) => <ul className="my-2.5 ml-5 list-disc space-y-1.5 marker:text-muted" {...p} />,
          ol: (p) => <ol className="my-2.5 ml-5 list-decimal space-y-1.5 marker:text-muted" {...p} />,
          strong: ({ children, ...rest }) => (
            <strong className={isFigure(children) ? 'font-bold text-ink tabular' : 'font-semibold text-ink'} {...rest}>{children}</strong>
          ),
          hr: () => <hr className="my-4 border-line" />,
          a: (p) => (
            <a className="font-medium text-ink underline decoration-accent decoration-2 underline-offset-2 hover:bg-butter" target="_blank" rel="noreferrer" {...p} />
          ),
          blockquote: (p) => <blockquote className="my-2.5 border-l-2 border-accent pl-3 text-muted" {...p} />,
          code: ({ className, children, ...rest }) =>
            className ? (
              <code className={`${className} font-mono text-xs`} {...rest}>{children}</code>
            ) : (
              <code className="rounded bg-field px-1 py-0.5 font-mono text-[0.85em]" {...rest}>{children}</code>
            ),
          pre: (p) => <pre className="my-2.5 overflow-x-auto rounded-2xl bg-soft p-3" {...p} />,
          table: (p) => (
            <div className="my-3.5 overflow-x-auto rounded-[18px] bg-soft">
              <table className="w-full border-collapse text-left text-sm" {...p} />
            </div>
          ),
          thead: (p) => <thead className="text-muted" {...p} />,
          th: ({ style, ...p }) => <th className="px-4 py-3 font-semibold" style={style} {...p} />,
          td: ({ children, style, ...rest }) => (
            <td
              className={`border-t border-line px-4 py-3 ${isFigure(children) ? 'tabular whitespace-nowrap text-right font-semibold' : ''}`}
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
