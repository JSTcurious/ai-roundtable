/**
 * frontend/src/components/SynthesisPanel.jsx
 *
 * Screen 4 — Claude synthesis output (scroll-contained body).
 *
 * Figma frame: 04-Synthesis-Panel
 */

import React, { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * @param {Object}   props
 * @param {string}   props.content      — synthesis markdown / plain text (streams in)
 * @param {boolean}  props.isStreaming  — true while synthesis tokens are still arriving
 * @param {boolean}  props.complete     — synthesis finished (show ✓)
 * @param {string[]} props.citations    — ordered source URLs from Perplexity fact-check
 * @param {string}   props.variant      — "draft" | "revised" | "final" (border color)
 * @param {number}   props.revision     — 0 for draft, >0 for revised
 */
function SynthesisPanel({ content, isStreaming, complete, citations = [], variant = "draft", revision = 0 }) {
  const borderColor = variant === "final" ? "#22c55e" : "#E8712A";
  const badgeLabel =
    variant === "final"
      ? "FINAL ANSWER"
      : variant === "revised"
        ? `REVISED · round ${revision}`
        : "DRAFT";
  const badgeColor = variant === "final" ? "#22c55e" : "#F5A623";
  // Convert [n] citation markers to markdown links using a custom citation://n
  // protocol so ReactMarkdown doesn't need to parse raw HTML inside link labels.
  // The components.a override below detects this protocol and renders a proper
  // <sup> element. Markers without a matching URL are left as-is.
  const processedContent = useMemo(() => {
    if (!citations.length) return content;
    return content.replace(/\[(\d+)\]/g, (match, n) => {
      const url = citations[parseInt(n, 10) - 1];
      return url ? `[${n}](citation://${n})` : match;
    });
  }, [content, citations]);

  return (
    <div className="flex max-h-[400px] w-full flex-col overflow-hidden rounded-lg border border-border bg-surface px-4 py-3" style={{ borderLeft: `3px solid ${borderColor}` }}>
      <div className="mb-2 flex shrink-0 items-center gap-2 text-xs font-semibold uppercase tracking-wide text-claude">
        <span>CLAUDE</span>
        <span className="font-normal text-text-secondary">- Synthesis</span>
        <span
          className="ml-auto rounded px-1.5 py-0.5 text-[0.65rem] font-semibold tracking-wider"
          style={{ color: badgeColor, border: `1px solid ${badgeColor}` }}
        >
          {badgeLabel}
        </span>
      </div>
      <div className="synthesis-panel-scroll min-h-0 flex-1">
        <div className="markdown-session break-words text-[0.9375rem] leading-relaxed text-text-primary">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => {
                // Citation superscript: [n](citation://n) → <a href="url"><sup>n</sup></a>
                if (href?.startsWith("citation://")) {
                  const idx = parseInt(href.replace("citation://", ""), 10) - 1;
                  const url = citations[idx];
                  if (url) {
                    return (
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[#F5A623] hover:opacity-80 no-underline"
                      >
                        <sup>{children}</sup>
                      </a>
                    );
                  }
                  // citation://n with no matching URL — render plain superscript,
                  // no broken anchor pointing to a dead protocol
                  return <sup>{children}</sup>;
                }
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#F5A623] hover:opacity-80 no-underline"
                  >
                    {children}
                  </a>
                );
              },
            }}
          >
            {processedContent}
          </ReactMarkdown>
          {isStreaming && !complete ? (
            <span
              className="ml-0.5 inline-block h-[1em] w-2 animate-pulse align-[-0.125em] bg-claude"
              aria-hidden
            />
          ) : null}
          {complete ? (
            <span className="ml-2 text-xs text-text-secondary" aria-label="Complete">
              ✓
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default SynthesisPanel;
