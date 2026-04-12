/**
 * frontend/src/components/IntakeFlow.jsx
 *
 * Screen 2 — Intake conversation.
 *
 * Hosts the conversational intake conducted by Claude.
 * The intake is not overhead — it is the product.
 *
 * Flow:
 *   1. Opens with IntakeSession.start() opening message
 *   2. User types; each message is sent to POST /api/intake/respond
 *   3. Displays Claude's responses as chat bubbles
 *   4. When status == "complete", extracts session_config
 *      and advances to SessionView (Screen 3)
 *
 * The user can always escape early ("let's just go", "skip the questions").
 * Claude honors all escape hatches — do not block or override them in the UI.
 *
 * Input rules (from CLAUDE.md):
 *   background-color: #1e1e1e  (surface — NEVER #0d0d0d)
 *   caret-color:      #E8712A
 *   border-focus:     #E8712A
 *
 * Figma frame: 02-Intake-Conversation
 */

import React from "react";

/**
 * @param {Object} props
 * @param {Object} props.selectedUseCase - use case card from UseCaseLibrary (may be null)
 * @param {function} props.onComplete    - called with session_config when intake completes
 */
function IntakeFlow({ selectedUseCase, onComplete }) {
  // TODO: implement intake conversation UI and API integration
  return null;
}

export default IntakeFlow;
