/**
 * frontend/src/components/TakeFurther.jsx
 *
 * "Take this further" panel — shown after every synthesis. Always visible.
 *
 * v2 ships (active buttons):
 *   - Download markdown (full session)
 *   - Download markdown (synthesis only)
 *
 * v2.1 (commented out placeholders — do not wire up):
 *   - Save to Google Drive
 *   - Open in Claude Code
 *   - Continue in Perplexity
 *
 * v3 (commented out placeholders — do not build):
 *   - Convert to PDF
 *   - Export to Notion
 *
 * Markdown is the universal intermediary — portable, convertible downstream.
 *
 * API calls:
 *   POST /api/export/markdown    — download
 *   POST /api/export/drive       — Google Drive
 */

import React from "react";

/**
 * @param {Object} props
 * @param {Object} props.sessionConfig  - session_config from intake
 * @param {Object} props.transcript     - full session transcript
 */
function TakeFurther({ sessionConfig, transcript }) {
  // TODO: implement two active download actions (POST /api/export/markdown)
  //
  // Commented out placeholders for v2.1:
  // - Save to Google Drive   (POST /api/export/drive)
  // - Open in Claude Code    (copy markdown + instruction)
  // - Continue in Perplexity (paste synthesis + suggested prompt)
  return null;
}

export default TakeFurther;
