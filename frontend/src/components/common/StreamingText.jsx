/**
 * frontend/src/components/common/StreamingText.jsx
 *
 * Renders text that arrives token-by-token from the WebSocket stream.
 *
 * Behavior:
 *   - Renders content as it accumulates — no buffering, no wait
 *   - Shows a blinking cursor while isStreaming is true
 *   - Cursor disappears when isStreaming becomes false
 *
 * Used inside ModelBubble for all streaming model responses.
 * Production AI apps stream. This one streams.
 */

import React from "react";

/**
 * @param {Object} props
 * @param {string}  props.content     - accumulated text so far
 * @param {boolean} props.isStreaming - true while tokens are still arriving
 */
function StreamingText({ content, isStreaming }) {
  // TODO: render content with streaming cursor indicator
  return null;
}

export default StreamingText;
