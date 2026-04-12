/**
 * frontend/src/components/common/ModelBubble.jsx
 *
 * Chat bubble for a model response in the roundtable session.
 *
 * Model color mapping (from CLAUDE.md design system):
 *   Claude      — #E8712A (orange)
 *   Gemini      — #4285F4 (Google blue)
 *   GPT         — #10A37F (OpenAI green)
 *   Perplexity  — #8B5CF6 (purple)
 *
 * Shows:
 *   - Model name + color accent
 *   - Streaming text content via StreamingText
 *   - Loading indicator while model is active but hasn't produced tokens yet
 *
 * Background: #1e1e1e (surface) — never #0d0d0d
 */

import React from "react";
import StreamingText from "./StreamingText";

/**
 * @param {Object} props
 * @param {string}  props.sender      - "Claude" | "Gemini" | "GPT" | "Perplexity"
 * @param {string}  props.content     - accumulated response text (grows as tokens arrive)
 * @param {boolean} props.isStreaming - true while tokens are still arriving
 * @param {string}  props.round       - "round1" | "audit" | "critique" | "synthesis"
 */
function ModelBubble({ sender, content, isStreaming, round }) {
  // TODO: render model bubble with correct color and streaming indicator
  return null;
}

export default ModelBubble;
