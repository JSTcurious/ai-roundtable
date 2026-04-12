/**
 * frontend/src/App.jsx
 *
 * Root application component for ai-roundtable v2.
 *
 * The four screens (in order):
 *   1. UseCaseLibrary   — 16 curated cards across 4 families
 *   2. IntakeFlow       — Claude-powered intake conversation
 *   3. SessionView      — live roundtable with streaming model responses
 *   4. SynthesisPanel   — Claude synthesis + Take This Further handoffs
 *
 * State:
 *   screen          — which of the four screens is active
 *   sessionConfig   — populated after intake completes
 *   transcript      — session message history for display
 *
 * Design system: see tailwind.config.js
 * Background: #0d0d0d — inputs always use #1e1e1e (surface), never bg
 * Caret: #E8712A — always
 */

import React from "react";

function App() {
  // TODO: implement screen routing and session state
  return null;
}

export default App;
