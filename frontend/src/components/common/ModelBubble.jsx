/**
 * Roundtable model bubble — design colors from CLAUDE.md.
 * Perplexity color defined for future use (not streamed in v2 WS).
 */

import React from "react";
import ReactMarkdown from "react-markdown";
import { MODEL_HEX } from "../../constants/modelColors";

export { MODEL_HEX };

/**
 * @param {Object} props
 * @param {string} props.sender
 * @param {string} props.content
 * @param {boolean} props.isStreaming
 * @param {string} props.round
 * @param {boolean} [props.complete] — show subtle ✓ after model_complete
 * @param {string} [props.subtitle] — e.g. "Synthesis"
 * @param {string} [props.titleOverride] — full header line (replaces sender · subtitle)
 * @param {string} [props.contentMaxHeight] — override inner content max-height (default "320px")
 */
function ModelBubble({ sender, content, isStreaming, round, complete, subtitle, titleOverride, contentMaxHeight }) {
  const hex = MODEL_HEX[sender] || "#e8e8e8";

  return (
    <div
      data-round={round}
      className="flex w-full min-w-0 flex-col rounded-lg border border-border bg-[#161616] p-4"
      style={{ borderLeft: `3px solid ${hex}` }}
    >
      <div className="mb-2 flex shrink-0 items-baseline gap-2">
        {titleOverride ? (
          <span className="text-xs font-semibold leading-snug" style={{ color: hex }}>
            {titleOverride}
          </span>
        ) : (
          <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: hex }}>
            {sender}
            {subtitle ? ` · ${subtitle}` : ""}
          </span>
        )}
        {complete && !isStreaming ? (
          <span className="text-xs text-text-secondary" aria-label="Complete">
            ✓
          </span>
        ) : null}
      </div>
      <div className="bubble-scroll markdown-session break-words text-[0.9375rem] leading-relaxed text-text-primary" style={{ maxHeight: contentMaxHeight || "320px" }}>
        <ReactMarkdown>{content}</ReactMarkdown>
        {isStreaming ? (
          <span
            className={`ml-0.5 inline-block h-[1em] w-2 animate-pulse align-[-0.125em] ${
              sender === "Claude" ? "bg-claude" : "bg-accent-ui"
            }`}
            aria-hidden
          />
        ) : null}
      </div>
    </div>
  );
}

export default ModelBubble;
