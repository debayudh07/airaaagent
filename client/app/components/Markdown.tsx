'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/** Renders assistant answers (headings, lists, tables, code) on the dark glass theme. */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm sm:text-[15px] leading-relaxed text-white/90 break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: (p) => <h2 className="text-lg font-semibold mt-4 mb-2 text-white" {...p} />,
          h2: (p) => <h3 className="text-base font-semibold mt-4 mb-2 text-cyan-300" {...p} />,
          h3: (p) => <h4 className="text-sm font-semibold mt-3 mb-1.5 text-cyan-200" {...p} />,
          p: (p) => <p className="my-2" {...p} />,
          ul: (p) => <ul className="my-2 ml-5 list-disc space-y-1 marker:text-cyan-400/70" {...p} />,
          ol: (p) => <ol className="my-2 ml-5 list-decimal space-y-1 marker:text-cyan-400/70" {...p} />,
          strong: (p) => <strong className="font-semibold text-white" {...p} />,
          hr: () => <hr className="my-4 border-white/10" />,
          a: (p) => (
            <a className="text-cyan-300 underline underline-offset-2 hover:text-cyan-200" target="_blank" rel="noreferrer" {...p} />
          ),
          blockquote: (p) => <blockquote className="my-2 border-l-2 border-cyan-400/50 pl-3 text-white/70" {...p} />,
          code: ({ className, children, ...rest }) =>
            className ? (
              <code className={`${className} font-mono text-xs`} {...rest}>{children}</code>
            ) : (
              <code className="rounded bg-white/10 px-1 py-0.5 font-mono text-[0.85em]" {...rest}>{children}</code>
            ),
          pre: (p) => <pre className="my-2 overflow-x-auto rounded-lg border border-white/10 bg-black/40 p-3" {...p} />,
          table: (p) => (
            <div className="my-3 overflow-x-auto rounded-lg border border-white/10">
              <table className="w-full text-left text-xs sm:text-sm" {...p} />
            </div>
          ),
          thead: (p) => <thead className="bg-white/[0.06] text-white/70" {...p} />,
          th: (p) => <th className="px-3 py-2 font-medium" {...p} />,
          td: (p) => <td className="border-t border-white/10 px-3 py-2" {...p} />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
