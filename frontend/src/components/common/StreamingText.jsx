/**
 * Renders streamed model text; supports multi-character chunks (e.g. Gemini).
 * Streaming pulse is orange only for Claude (Claude progress node).
 */

import React from "react";

function StreamingText({ content, isStreaming, sender }) {
  const pulseClass =
    sender === "Claude" ? "bg-claude" : "bg-accent-ui";

  return (
    <div className="whitespace-pre-wrap break-words text-[0.9375rem] leading-relaxed text-text-primary">
      {content}
      {isStreaming ? (
        <span
          className={`ml-0.5 inline-block h-[1em] w-2 animate-pulse align-[-0.125em] ${pulseClass}`}
          aria-hidden
        />
      ) : null}
    </div>
  );
}

export default StreamingText;
