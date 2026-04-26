/**
 * Landing — entry screen. Single prompt input; Gemini Flash handles intake automatically.
 */

import React, { useCallback, useState } from "react";

/**
 * @param {Object} props
 * @param {function(string)} props.onSubmitDescription — trimmed prompt text → IntakeFlow
 */
function LandingPage({ onSubmitDescription }) {
  const [draft, setDraft] = useState("");

  const handleSubmit = useCallback(
    (e) => {
      e.preventDefault();
      const t = draft.trim();
      if (!t) return;
      onSubmitDescription(t);
    },
    [draft, onSubmitDescription]
  );

  const panelRows = [
    { key: "claude",     name: "Claude",     archetype: "Analyst",      descriptor: "reasons from first principles", nameColor: "#E8712A" },
    { key: "gemini",     name: "Gemini",     archetype: "Scout",        descriptor: "finds angles others miss",      nameColor: "#4285F4" },
    { key: "gpt",        name: "GPT",        archetype: "Pragmatist",   descriptor: "grounds ideas in reality",      nameColor: "#10A37F" },
    { key: "grok",       name: "Grok",       archetype: "Challenger",   descriptor: "stress-tests the premise",      nameColor: "#1DA1F2" },
    { key: "perplexity", name: "Perplexity", archetype: "Fact-checker", descriptor: "verifies every claim live",     nameColor: "#20808D" },
  ];

  return (
    <div className="min-h-screen bg-bg text-text-primary">
      <div className="mx-auto w-full max-w-[720px] px-6 py-16 pb-24 sm:py-20 sm:pb-24">
        {/* 1. Header */}
        <header className="text-center">
          <h1 className="font-bold tracking-tight" style={{ color: "#F5A623", fontSize: "1.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            AI-ROUNDTABLE
          </h1>
          <p className="mt-2 text-base" style={{ color: "#F5A623" }}>
            The deliberation layer for decisions that matter.
          </p>
          {/* Philosophy block */}
          <div
            className="mx-auto mt-6 max-w-[600px] rounded-lg text-center"
            style={{ background: "#1a1a1a", padding: "16px" }}
          >
            <p style={{ color: "#cccccc", fontSize: "0.85rem", lineHeight: "1.8" }}>Four researchers. One fact-checker. You in the chair.</p>
            <p style={{ color: "#888888", fontSize: "0.85rem", lineHeight: "1.8", marginTop: "0.5rem" }}>Four frontier models research independently — no groupthink.</p>
            <p style={{ color: "#888888", fontSize: "0.85rem", lineHeight: "1.8" }}>An independent search tool fact-checks every claim against live web data.</p>
            <p style={{ color: "#888888", fontSize: "0.85rem", lineHeight: "1.8" }}>Claude synthesizes all four. You add your perspective. Then you decide.</p>
          </div>
        </header>

        {/* 2. Chat input + toggle */}
        <div className="mt-10 w-full">
          <form onSubmit={handleSubmit} className="w-full">
            <div className="relative">
              <input
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="What decision are you working through?"
                className="w-full rounded-lg bg-surface py-3 pl-4 pr-14 text-sm text-text-primary caret-chrome placeholder:text-text-secondary focus:outline-none"
                style={{ border: "1px solid #2a2a2a" }}
                autoFocus
                autoComplete="off"
                aria-label="What you need to figure out"
              />
              <button
                type="submit"
                style={{ background: "#F5A623", color: "#0d0d0d" }}
                className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md font-bold transition-opacity hover:opacity-90 focus:outline-none"
                aria-label="Continue to intake"
              >
                <span className="text-base leading-none" aria-hidden>→</span>
              </button>
            </div>
          </form>
        </div>

        {/* 3. Divider */}
        <hr className="my-12 border-0 border-t" style={{ borderColor: "#333333" }} />

        {/* 4. You + Panel in one visual unit */}
        <div className="mx-auto max-w-[380px] space-y-3">
          {/* You row */}
          <div className="flex items-center gap-x-2 text-sm leading-relaxed">
            <span className="shrink-0" style={{ color: "#555555" }} aria-hidden>•</span>
            <span className="font-semibold" style={{ color: "#e8e8e8" }}>You</span>
            <span style={{ color: "#555555" }}>·</span>
            <span style={{ color: "#888888" }}>in the chair</span>
          </div>

          {/* THE PANEL inline divider */}
          <div className="flex items-center gap-3 py-1">
            <hr className="flex-1 border-0 border-t" style={{ borderColor: "#2a2a2a" }} />
            <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#aaaaaa" }}>The Panel</span>
            <hr className="flex-1 border-0 border-t" style={{ borderColor: "#2a2a2a" }} />
          </div>

          {/* Panel rows */}
          <div className="space-y-3">
            {panelRows.map((row) => (
              <div key={row.key} className="flex items-center gap-x-2 text-sm leading-relaxed">
                <span className="shrink-0" style={{ color: "#555555" }} aria-hidden>•</span>
                <span className="font-semibold" style={{ color: row.nameColor }}>{row.name}</span>
                <span style={{ color: "#555555" }}>·</span>
                <span style={{ color: "#cccccc", fontWeight: 500 }}>{row.archetype}</span>
                <span style={{ color: "#555555" }}>·</span>
                <span style={{ color: "#888888" }}>{row.descriptor}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 5. Bottom tagline */}
        <p className="mt-16 text-center text-sm" style={{ color: "#888888" }}>
          Not a comparison tool. A team of rivals. One outcome.
        </p>
      </div>
    </div>
  );
}

export default LandingPage;
