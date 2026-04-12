/**
 * frontend/src/components/SessionView.jsx
 *
 * Screen 3 — Live roundtable session.
 *
 * Connects to the WebSocket at ws://localhost:8000/ws/session
 * and streams token-by-token responses from each model.
 *
 * Round 1 is sequential: Claude → Gemini → GPT.
 * Each model's response appears in its own ModelBubble as tokens arrive.
 * After Round 1, the Perplexity audit is displayed.
 * After the audit, Claude synthesis streams into SynthesisPanel.
 *
 * WebSocket message types:
 *   { type: "token",              sender: str, token: str }
 *   { type: "model_complete",     sender: str }
 *   { type: "audit_complete",     content: str }
 *   { type: "synthesis_complete", content: str }
 *
 * Never wait for a complete response before displaying.
 * Tokens stream as they arrive.
 *
 * Deep mode (opt-in): adds cross-critique and revision rounds
 * after Perplexity audit. User must explicitly activate.
 *
 * Figma frame: 03-Session-View
 */

import React from "react";

/**
 * @param {Object} props
 * @param {Object} props.sessionConfig  - completed intake session_config
 * @param {function} props.onSynthesisComplete - called when synthesis is ready
 */
function SessionView({ sessionConfig, onSynthesisComplete }) {
  // TODO: implement WebSocket connection and streaming model bubbles
  return null;
}

export default SessionView;
