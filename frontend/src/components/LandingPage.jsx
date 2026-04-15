/**
 * Landing — entry screen. Quick vs Refined toggle; submit runs selected path.
 */

import React, { Fragment, useCallback, useRef, useState } from "react";

function parseResumePayload(raw) {
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return { error: "That file is not valid JSON." };
  }
  if (!data || typeof data !== "object") {
    return { error: "Invalid session file." };
  }
  const session_config = data.session_config;
  const transcript = data.transcript || (Array.isArray(data.messages) ? { messages: data.messages } : null);
  if (!session_config || typeof session_config !== "object") {
    return { error: "Missing session_config in file." };
  }
  if (!transcript || !Array.isArray(transcript.messages) || transcript.messages.length === 0) {
    return { error: "Missing transcript.messages in file." };
  }
  return { session_config, transcript };
}

/**
 * @param {Object} props
 * @param {function(string)} props.onSubmitDescription — trimmed text → IntakeFlow (same as → submit)
 * @param {function(string)} props.onDirectSession — trimmed text → SessionView, skip intake
 * @param {function({ session_config: object, transcript: object })} props.onResumeSession — valid resume payload
 */
function LandingPage({ onSubmitDescription, onDirectSession, onResumeSession }) {
  const [draft, setDraft] = useState("");
  /** "refined" = intake first (default); "quick" = straight to roundtable */
  const [pathMode, setPathMode] = useState("refined");
  const [resumeHint, setResumeHint] = useState(null);
  const fileRef = useRef(null);

  const handleSubmit = useCallback(
    (e) => {
      e.preventDefault();
      const t = draft.trim();
      if (!t) return;
      if (pathMode === "quick") {
        if (typeof onDirectSession === "function") onDirectSession(t);
        return;
      }
      onSubmitDescription(t);
    },
    [draft, pathMode, onSubmitDescription, onDirectSession]
  );

  const handleFile = useCallback(
    (e) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".json")) {
        setResumeHint("Please choose a .json file.");
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const parsed = parseResumePayload(String(reader.result || ""));
        if (parsed.error) {
          setResumeHint(parsed.error);
          return;
        }
        setResumeHint(null);
        onResumeSession({ session_config: parsed.session_config, transcript: parsed.transcript });
      };
      reader.onerror = () => setResumeHint("Could not read that file.");
      reader.readAsText(file, "utf-8");
    },
    [onResumeSession]
  );

  const panelRows = [
    { key: "you", name: "You", role: "Chair", nameColor: "#F0A500" },
    { key: "claude", name: "Claude", role: "Orchestrator", nameColor: "#E8712A" },
    { key: "gemini", name: "Gemini", role: "Deep reasoner", nameColor: "#4285F4" },
    { key: "gpt", name: "GPT", role: "Structurer", nameColor: "#10A37F" },
    {
      key: "perplexity",
      name: "Perplexity",
      role: "Live researcher + fact-checker",
      nameColor: "#20808D",
    },
  ];

  const howRowBodies = [
    <span key="how-0" className="text-[#e8e8e8]">
      <span style={{ color: "#F0A500", fontWeight: "bold" }}>You</span>
      <span style={{ color: "#e8e8e8" }}>:</span>{" "}
      describe your situation, however you want
    </span>,
    <span key="how-1" className="text-[#e8e8e8]">
      <span style={{ color: "#E8712A", fontWeight: "bold" }}>Claude</span>{" "}
      <span style={{ color: "#e8e8e8" }}>↔</span>{" "}
      <span style={{ color: "#F0A500", fontWeight: "bold" }}>You</span>
      <span style={{ color: "#e8e8e8" }}>:</span>{" "}
      Intent capture via questions
    </span>,
    <span key="how-2" className="text-[#e8e8e8]">
      <span style={{ color: "#4285F4", fontWeight: "bold" }}>Gemini</span> +{" "}
      <span style={{ color: "#10A37F", fontWeight: "bold" }}>GPT</span>
      <span style={{ color: "#e8e8e8" }}>:</span>{" "}
      research independently
    </span>,
    <span key="how-3" className="text-[#e8e8e8]">
      <span style={{ color: "#20808D", fontWeight: "bold" }}>Perplexity</span>
      <span style={{ color: "#e8e8e8" }}>:</span>{" "}
      adds live web + citations
    </span>,
    <span key="how-4" className="text-[#e8e8e8]">
      <span style={{ color: "#E8712A", fontWeight: "bold" }}>Claude</span>{" "}
      <span style={{ color: "#e8e8e8" }}>↔</span>{" "}
      <span style={{ color: "#F0A500", fontWeight: "bold" }}>You</span>
      <span style={{ color: "#e8e8e8" }}>:</span>{" "}
      one expert answer
    </span>,
  ];

  return (
    <div className="min-h-screen bg-bg text-text-primary">
      <div className="mx-auto w-full max-w-[720px] px-6 py-16 pb-28 sm:py-20 sm:pb-32">
        {/* 1. Header */}
        <header className="text-center">
          <h1 className="flex items-center justify-center gap-2.5 text-3xl font-bold tracking-tight sm:text-4xl" style={{ color: "#F5A623" }}>
            <svg
              className="h-8 w-8 shrink-0 sm:h-9 sm:w-9"
              viewBox="0 0 24 24"
              aria-hidden
              focusable="false"
              style={{ transform: "rotate(90deg)" }}
            >
              <polygon fill="currentColor" points="12,1.5 21.5,7.25 21.5,16.75 12,22.5 2.5,16.75 2.5,7.25" />
            </svg>
            <span style={{ textTransform: "uppercase" }}>AI-ROUNDTABLE</span>
          </h1>
          <p className="mt-3 text-base sm:text-lg" style={{ color: "#F5A623" }}>
            You and the right experts. One room. No FOMO.
          </p>
          <div className="mx-auto mt-5 max-w-[480px] text-center" style={{ color: "#888888", fontSize: "0.85rem", lineHeight: "1.8" }}>
            <p>Multiple perspectives. One room. You decide.</p>
            <p>Gemini reasons. GPT structures. Perplexity fact-checks. Claude synthesizes.</p>
            <p>You chair the session and own the outcome.</p>
          </div>
        </header>

        {/* 2. Chat input */}
        <div className="mt-10 w-full">
          <form onSubmit={handleSubmit} className="w-full">
            <div className="relative">
              <input
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="What do you need to figure out?"
                className="w-full rounded-lg border border-border bg-surface py-3 pl-4 pr-14 text-sm text-text-primary caret-chrome placeholder:text-text-secondary focus:border-border-focus focus:outline-none"
                autoFocus
                autoComplete="off"
                aria-label="What you need to figure out"
              />
              <button
                type="submit"
                className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md border border-border text-text-primary transition-colors hover:border-accent-ui focus:border-border-focus focus:outline-none"
                aria-label={pathMode === "quick" ? "Start roundtable" : "Continue to intake"}
              >
                <span className="text-lg leading-none" aria-hidden>
                  →
                </span>
              </button>
            </div>
          </form>
          <div className="mt-4 space-y-3 text-center">
            <div className="flex justify-center">
              <div
                role="radiogroup"
                aria-label="Start mode"
                className="inline-flex rounded-full border border-[#2a2a2a] bg-[#1e1e1e] p-1"
              >
                <button
                  type="button"
                  role="radio"
                  aria-checked={pathMode === "quick"}
                  onClick={() => setPathMode("quick")}
                  className={`rounded-full px-5 py-2 text-[0.875rem] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-border-focus focus-visible:ring-offset-2 focus-visible:ring-offset-bg ${
                    pathMode === "quick"
                      ? "bg-[#2a2a2a] font-medium text-[#e8e8e8]"
                      : "bg-transparent font-normal text-[#888888]"
                  }`}
                >
                  <span aria-hidden>⚡</span>{" "}
                  AS-IS PROMPT
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-checked={pathMode === "refined"}
                  onClick={() => setPathMode("refined")}
                  className={`rounded-full px-5 py-2 text-[0.875rem] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-border-focus focus-visible:ring-offset-2 focus-visible:ring-offset-bg ${
                    pathMode === "refined"
                      ? "bg-[#2a2a2a] font-medium text-[#e8e8e8]"
                      : "bg-transparent font-normal text-[#888888]"
                  }`}
                >
                  <span aria-hidden>✨</span>{" "}
                  REFINED PROMPT
                </button>
              </div>
            </div>
            <p className="text-xs leading-relaxed text-[#888888] sm:text-sm" role="status">
              {pathMode === "quick"
                ? "Goes straight to the roundtable"
                : "Claude asks smart questions first (recommended)"}
            </p>
            <div>
              <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={handleFile} />
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="text-left text-sm text-[#888888] underline decoration-[#888888]/40 underline-offset-4 transition-colors hover:text-text-primary hover:decoration-text-primary/60"
              >
                📂 Resume a saved session
              </button>
            </div>
            {resumeHint && (
              <p className="mt-2 text-sm text-red-400" role="alert">
                {resumeHint}
              </p>
            )}
          </div>
        </div>

        {/* 3. Divider */}
        <hr className="my-12 border-0 border-t border-border" />

        {/* 4. Two columns — paired rows share min-height for horizontal alignment */}
        <div className="grid min-w-0 grid-cols-2 items-start gap-x-8 gap-y-0">
          <h2
            id="panel-heading"
            className="mb-4 text-sm font-semibold uppercase tracking-wide leading-snug text-text-primary"
          >
            THE PANEL
          </h2>
          <h2
            id="how-heading"
            className="mb-4 text-sm font-semibold uppercase tracking-wide leading-snug text-text-primary"
          >
            HOW IT WORKS
          </h2>
          {panelRows.map((row, i) => (
            <Fragment key={row.key}>
              <div className="flex min-h-[36px] flex-wrap items-center gap-x-2 text-sm leading-relaxed">
                <span className="mr-2 inline-block shrink-0 text-sm text-[#888888]" aria-hidden>
                  •
                </span>
                <span className="font-semibold" style={{ color: row.nameColor }}>
                  {row.name}
                </span>
                <span style={{ color: "#e8e8e8" }}>:</span>{" "}
                <span className="text-[#e8e8e8]">{row.role}</span>
              </div>
              <div className="flex min-h-[36px] items-center text-sm font-normal leading-normal min-w-0 overflow-x-hidden">
                <span className="mr-2 inline-block shrink-0 text-sm text-[#888888]" aria-hidden>
                  •
                </span>
                {howRowBodies[i]}
              </div>
            </Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

export default LandingPage;
