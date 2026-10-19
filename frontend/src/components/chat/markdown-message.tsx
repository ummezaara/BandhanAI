import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownMessageProps {
  content: string;
}

export function MarkdownMessage({ content }: MarkdownMessageProps) {
  return (
    <div className="prose prose-invert max-w-none font-body-base text-sm leading-relaxed text-[#e5e2e3] space-y-2">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="text-base font-bold text-[#E8A020] mt-4 mb-2">{children}</h1>,
          h2: ({ children }) => <h2 className="text-sm font-bold text-[#E8A020] mt-3 mb-1.5">{children}</h2>,
          h3: ({ children }) => <h3 className="text-xs font-bold text-[#E8A020] mt-2 mb-1">{children}</h3>,
          p: ({ children }) => <p className="mb-2 leading-relaxed whitespace-pre-line">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-[#E8A020]">{children}</strong>,
          em: ({ children }) => <em className="italic text-[#d7c3ae]">{children}</em>,
          ul: ({ children }) => <ul className="list-disc pl-5 mb-2.5 space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 mb-2.5 space-y-1">{children}</ol>,
          li: ({ children }) => <li className="text-[#e5e2e3]">{children}</li>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#3ac2ff] hover:underline"
            >
              {children}
            </a>
          ),
          code: ({ className, children }) => {
            const isInline = !className;
            return isInline ? (
              <code className="px-1.5 py-0.5 rounded bg-[#1c1b1c] border border-[#27272A] font-data-mono text-[11px] text-[#6A9E6A]">
                {children}
              </code>
            ) : (
              <pre className="p-3 my-2 rounded bg-[#0A0A0B] border border-[#27272A] font-data-mono text-xs text-[#6A9E6A] overflow-x-auto max-w-full">
                <code className="bg-transparent p-0 border-none font-inherit text-inherit">
                  {children}
                </code>
              </pre>
            );
          },
          table: ({ children }) => (
            <div className="overflow-x-auto my-3 border border-[#27272A] rounded-lg">
              <table className="w-full text-left border-collapse text-xs font-body-base">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-[#111113] border-b border-[#27272A] font-bold text-[#d7c3ae]">{children}</thead>,
          tbody: ({ children }) => <tbody className="divide-y divide-[#27272A] bg-[#0c0c0d]">{children}</tbody>,
          tr: ({ children }) => <tr className="hover:bg-[#141415] transition-colors">{children}</tr>,
          th: ({ children }) => <th className="px-4 py-2.5 font-semibold">{children}</th>,
          td: ({ children }) => <td className="px-4 py-2.5 text-[#e5e2e3] font-normal leading-relaxed">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
