/**
 * frontend/src/components/UseCaseLibrary.jsx
 *
 * Screen 1 — Use Case Library.
 *
 * Displays 16 curated cards across 4 families:
 *   - Learning & Career (4 cards)
 *   - Research & Decision (4 cards)
 *   - Strategy & Planning (4 cards)
 *   - Technical Build (4 cards)
 *
 * Each card shows:
 *   title, description, expected output type,
 *   typical tier, typical exchange count
 *
 * On card selection: pre-loads the use case family and
 * first intake question, then advances to IntakeFlow (Screen 2).
 *
 * Card data sourced from USE_CASE_LIBRARY in CLAUDE.md.
 * Fixed for v2 — no user contributions.
 *
 * Figma frame: 01-UseCase-Library
 */

import React from "react";

/**
 * @param {Object} props
 * @param {function} props.onSelect - called with the selected use case card object
 */
function UseCaseLibrary({ onSelect }) {
  // TODO: render 16 use case cards across 4 families
  return null;
}

export default UseCaseLibrary;
