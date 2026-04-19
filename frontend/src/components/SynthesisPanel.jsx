/**
 * frontend/src/components/SynthesisPanel.jsx
 *
 * Screen 4 — Claude synthesis output (scroll-contained body).
 *
 * Figma frame: 04-Synthesis-Panel
 */

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * @param {Object} props
 * @param {string} props.content — synthesis markdown / plain text (streams in)
 * @param {boolean} props.isStreaming — true while synthesis tokens are still arriving
 * @param {boolean} props.complete — synthesis finished (show ✓)
 */
function SynthesisPanel({ content, isStreaming, complete }) {
  return (
    <div className="flex max-h-[400px] w-full flex-col overflow-hidden rounded-lg border border-border bg-surface px-4 py-3" style={{ borderLeft: "3px solid #E8712A" }}>
      <div className="mb-2 shrink-0 text-xs font-semibold uppercase tracking-wide text-claude">
        CLAUDE
        <span className="font-normal text-text-secondary"> - Synthesis</span>
      </div>
      <div className="synthesis-panel-scroll min-h-0 flex-1">
        <div className="markdown-session break-words text-[0.9375rem] leading-relaxed text-text-primary">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
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
