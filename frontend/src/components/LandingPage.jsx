/**
 * Landing — entry screen. Quick vs Refined toggle; submit runs selected path.
 */

import React, { useCallback, useState } from "react";

/**
 * @param {Object} props
 * @param {function(string)} props.onSubmitDescription — trimmed text → IntakeFlow (same as → submit)
 * @param {function(string)} props.onDirectSession — trimmed text → SessionView, skip intake
 */
function LandingPage({ onSubmitDescription, onDirectSession }) {
  const [draft, setDraft] = useState("");
  /** "refined" = intake first (default); "quick" = straight to roundtable */
  const [pathMode, setPathMode] = useState("refined");
  const [directTier, setDirectTier] = useState("smart");
  const [pendingDirectText, setPendingDirectText] = useState(null);

  const handleSubmit = useCallback(
    (e) => {
      e.preventDefault();
      const t = draft.trim();
      if (!t) return;
      if (pathMode === "quick") {
        setPendingDirectText(t);
        return;
      }
      onSubmitDescription(t);
    },
    [draft, pathMode, onSubmitDescription]
  );

  const panelRows = [
    { key: "you", name: "User", role: "Chair — you decide", nameColor: "#e8e8e8" },
    { key: "claude", name: "Claude", role: "Orchestrator + synthesizer", nameColor: "#E8712A" },
    { key: "gemini", name: "Gemini", role: "Deep reasoner", nameColor: "#4285F4" },
    { key: "gpt", name: "GPT", role: "Structured thinker", nameColor: "#10A37F" },
    { key: "grok", name: "Grok", role: "Lateral thinker + live trends", nameColor: "#1DA1F2" },
    {
      key: "perplexity",
      name: "Perplexity",
      role: "Live fact-checker",
      nameColor: "#20808D",
    },
  ];

  /** Interstitial — depth selection after AS-IS submit */
  if (pendingDirectText !== null) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#0d0d0d] px-6 text-[#e8e8e8]">
        <div className="w-full max-w-md space-y-8">
          {/* Logo */}
          <div className="text-center">
            <h1 className="font-bold tracking-tight" style={{ color: "#F5A623", fontSize: "1.5rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
              AI-ROUNDTABLE
            </h1>
          </div>

          {/* Prompt preview */}
          <div className="rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-3">
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-[#888888]">Your prompt</p>
            <p className="text-sm leading-relaxed text-[#e8e8e8]">{pendingDirectText}</p>
          </div>

          {/* Tier selector */}
          <div className="space-y-3">
            <p className="text-center text-sm font-medium text-[#e8e8e8]">Choose roundtable depth</p>
            <div className="flex gap-3">
              {[
                { id: "quick", label: "⚡ Quick" },
                { id: "smart", label: "⚖ Smart" },
                { id: "deep", label: "🔍 Deep" },
              ].map(({ id, label }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setDirectTier(id)}
                  className={`min-w-0 flex-1 rounded-lg border px-4 py-2.5 text-center text-sm font-medium transition-colors focus:outline-none ${
                    directTier === id
                      ? "border-[#6B6B6B] bg-[#2a2a2a] text-[#e8e8e8]"
                      : "border-[#2a2a2a] bg-[#1e1e1e] text-[#888888] hover:border-[#6B6B6B]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="text-center text-xs leading-relaxed text-[#666666]">
              {directTier === "quick" && "Single executor per model · fastest · good for gut checks and brainstorms"}
              {directTier === "smart" && "Executor + advisor per model · near-Deep quality · recommended for most sessions"}
              {directTier === "deep" && "Flagship models throughout · maximum depth · best for reports and critical decisions"}
            </p>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => setPendingDirectText(null)}
              className="text-sm text-[#888888] transition-colors hover:text-[#e8e8e8] focus:outline-none"
            >
              ← Back
            </button>
            <button
              type="button"
              onClick={() => {
                if (typeof onDirectSession === "function") onDirectSession(pendingDirectText, directTier);
              }}
              className="flex-1 rounded-lg bg-[#e8e8e8] px-6 py-2.5 text-sm font-bold text-[#0d0d0d] transition-opacity hover:opacity-90 focus:outline-none"
            >
              Launch roundtable →
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg text-text-primary">
      <div className="mx-auto w-full max-w-[720px] px-6 py-16 pb-24 sm:py-20 sm:pb-24">
        {/* 1. Header */}
        <header className="text-center">
          <h1 className="font-bold tracking-tight" style={{ color: "#F5A623", fontSize: "1.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>
            AI-ROUNDTABLE
          </h1>
          <p className="mt-2 text-base" style={{ color: "#F5A623" }}>
            You and the right experts. One room. No FOMO.
          </p>
          {/* Philosophy block */}
          <div
            className="mx-auto mt-6 max-w-[480px] rounded-lg text-center"
            style={{ background: "#1a1a1a", padding: "16px" }}
          >
            <p style={{ color: "#cccccc", fontSize: "0.85rem", lineHeight: "1.8" }}>Five models. One perspective that&rsquo;s yours.</p>
            <p style={{ color: "#888888", fontSize: "0.85rem", lineHeight: "1.8", marginTop: "0.5rem" }}>Gemini and GPT research independently — no groupthink.</p>
            <p style={{ color: "#888888", fontSize: "0.85rem", lineHeight: "1.8" }}>Grok brings lateral thinking and real-time signals.</p>
            <p style={{ color: "#888888", fontSize: "0.85rem", lineHeight: "1.8" }}>Perplexity fact-checks everything against live web data.</p>
            <p style={{ color: "#888888", fontSize: "0.85rem", lineHeight: "1.8" }}>Claude consults you before synthesizing — you keep it or overrule it.</p>
            <p style={{ color: "#aaaaaa", fontSize: "0.85rem", lineHeight: "1.8", marginTop: "0.5rem" }}>The final answer is yours.</p>
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
                placeholder="What would you like to ask the experts?"
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
                aria-label={pathMode === "quick" ? "Start roundtable" : "Continue to intake"}
              >
                <span className="text-base leading-none" aria-hidden>→</span>
              </button>
            </div>
          </form>
          {/* Pill toggle */}
          <div className="mt-3 flex items-center justify-center gap-3 text-[0.8rem]" role="radiogroup" aria-label="Start mode">
            <span style={{ color: "#888888" }}>PROMPT CHOICE:</span>
            <div className="inline-flex rounded-full border border-[#2a2a2a] bg-[#1a1a1a] p-0.5">
              <button
                type="button"
                role="radio"
                aria-checked={pathMode === "quick"}
                onClick={() => setPathMode("quick")}
                className="rounded-full px-4 py-1.5 transition-colors focus:outline-none"
                style={
                  pathMode === "quick"
                    ? { background: "#2a2a2a", color: "#e8e8e8", fontWeight: "500" }
                    : { background: "transparent", color: "#666666" }
                }
              >
                AS-IS
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={pathMode === "refined"}
                onClick={() => setPathMode("refined")}
                className="rounded-full px-4 py-1.5 transition-colors focus:outline-none"
                style={
                  pathMode === "refined"
                    ? { background: "#2a2a2a", color: "#e8e8e8", fontWeight: "500" }
                    : { background: "transparent", color: "#666666" }
                }
              >
                REFINE
              </button>
            </div>
          </div>
          <p className="mt-2 text-center text-xs leading-relaxed" style={{ color: "#666666" }}>
            AS-IS sends your prompt directly. REFINE lets Claude sharpen it first.
          </p>
        </div>

        {/* 3. Divider */}
        <hr className="my-12 border-0 border-t" style={{ borderColor: "#333333" }} />

        {/* 4. THE PANEL — single column, centered */}
        <div className="mx-auto max-w-xs">
          <h2 className="mb-4 text-center text-sm font-semibold uppercase tracking-wide leading-snug text-text-primary">
            THE PANEL
          </h2>
          <div className="space-y-2">
            {panelRows.map((row) => (
              <div key={row.key} className="flex items-center gap-x-2 text-sm leading-relaxed">
                <span className="shrink-0 text-sm text-[#888888]" aria-hidden>
                  •
                </span>
                <span className="font-semibold" style={{ color: row.nameColor }}>
                  {row.name}
                </span>
                <span style={{ color: "#e8e8e8" }}>:</span>{" "}
                <span className="text-[#888888]">{row.role}</span>
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
