"use client";

/**
 * Markdown for assistant messages: GFM (tables, lists) styled with the app
 * theme, plus highlighted financial figures ($1,234.56, 12.5%) so numbers
 * pop out of prose.
 */

import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const FIGURE = /(-?\$\s?\d[\d,]*(?:\.\d+)?|-?\b\d[\d,]*(?:\.\d+)?%)/g;

function highlight(node: ReactNode, keyPrefix = "hl"): ReactNode {
  if (typeof node === "string") {
    const pieces = node.split(FIGURE);
    if (pieces.length === 1) return node;
    return pieces.map((piece, i) =>
      i % 2 === 1 ? (
        <span
          key={`${keyPrefix}-${i}`}
          className="font-semibold text-accent tabular-nums"
        >
          {piece}
        </span>
      ) : (
        piece
      ),
    );
  }
  if (Array.isArray(node)) {
    return node.map((child, i) => highlight(child, `${keyPrefix}-${i}`));
  }
  return node;
}

export function Markdown({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed text-ink">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p>{highlight(children)}</p>,
          ul: ({ children }) => (
            <ul className="list-disc space-y-1 pl-5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal space-y-1 pl-5">{children}</ol>
          ),
          li: ({ children }) => <li>{highlight(children)}</li>,
          strong: ({ children }) => (
            <strong className="font-semibold">{highlight(children)}</strong>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-accent underline underline-offset-2"
            >
              {children}
            </a>
          ),
          code: ({ children }) => (
            <code className="rounded bg-line px-1 py-0.5 font-mono text-xs">
              {children}
            </code>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="border-b border-line text-xs font-medium uppercase tracking-wide text-ink-3">
              {children}
            </thead>
          ),
          th: ({ children }) => <th className="px-2 py-1.5">{children}</th>,
          tr: ({ children }) => (
            <tr className="border-b border-line last:border-0">{children}</tr>
          ),
          td: ({ children }) => (
            <td className="px-2 py-1.5">{highlight(children)}</td>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
