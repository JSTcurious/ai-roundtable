/**
 * frontend/src/components/SynthesisPanel.jsx
 *
 * Screen 4 — Claude synthesis output.
 *
 * Displays the final synthesis from Claude, incorporating:
 *   - Best reasoning from each Round 1 model
 *   - Perplexity fact-check corrections
 *   - Explicit surfacing of model disagreements
 *   - Structured output matching the declared output_type
 *
 * The synthesis streams token-by-token from the WebSocket
 * (synthesis_complete message type signals end of stream).
 *
 * Below the synthesis: the TakeFurther panel is always shown.
 *
 * Figma frame: 04-Synthesis-Panel
 */

import React from "react";
import TakeFurther from "./TakeFurther";

/**
 * @param {Object} props
 * Perplexity audit section: shows "Coming in v2.1" placeholder.
 * Audit step is skipped in v2 — no Perplexity API calls are made.
 *
 * @param {Object} props
 * @param {string} props.content        - synthesis markdown content (streams in)
 * @param {boolean} props.isStreaming   - true while synthesis is still streaming
 * @param {Object} props.sessionConfig  - session_config from intake
 * @param {Object} props.transcript     - full session transcript for export
 */
function SynthesisPanel({ content, isStreaming, sessionConfig, transcript }) {
  // TODO: render synthesis content with markdown support
  // TODO: show TakeFurther panel once synthesis_complete received
  // TODO: render Perplexity audit section as "Coming in v2.1" placeholder
  return null;
}

export default SynthesisPanel;
