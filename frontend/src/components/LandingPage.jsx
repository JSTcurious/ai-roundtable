/**
 * Landing — entry screen. No use-case library; submit opens intake.
 */

import React, { useCallback, useRef, useState } from "react";

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

function roomDotStyle(backgroundColor) {
  return {
    width: 12,
    height: 12,
    borderRadius: "50%",
    flexShrink: 0,
    backgroundColor,
  };
}

/**
 * @param {Object} props
 * @param {function(string)} props.onSubmitDescription — trimmed text → navigate to IntakeFlow
 * @param {function({ session_config: object, transcript: object })} props.onResumeSession — valid resume payload
 */
function LandingPage({ onSubmitDescription, onResumeSession }) {
  const [draft, setDraft] = useState("");
  const [resumeHint, setResumeHint] = useState(null);
  const fileRef = useRef(null);

  const handleSubmit = useCallback(
    (e) => {
      e.preventDefault();
      const t = draft.trim();
      if (!t) return;
      onSubmitDescription(t);
    },
    [draft, onSubmitDescription]
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

  return (
    <div className="min-h-screen bg-bg text-text-primary">
      <div className="mx-auto w-full max-w-[720px] px-6 py-16 pb-28 sm:py-20 sm:pb-32">
        {/* 1. Header */}
        <header className="text-center">
          <h1 className="flex items-center justify-center gap-2.5 text-3xl font-bold tracking-tight text-text-primary sm:text-4xl">
            <svg
              className="h-8 w-8 shrink-0 text-text-primary sm:h-9 sm:w-9"
              viewBox="0 0 24 24"
              aria-hidden
              focusable="false"
            >
              <polygon fill="currentColor" points="12,1.5 21.5,7.25 21.5,16.75 12,22.5 2.5,16.75 2.5,7.25" />
            </svg>
            <span>ai-roundtable</span>
          </h1>
          <p className="mt-3 text-base text-text-secondary sm:text-lg">
            Putting the best frontier minds to work.
          </p>
        </header>

        {/* 2. Chat input */}
        <div className="mt-10 w-full">
          <form onSubmit={handleSubmit} className="w-full">
            <div className="relative">
              <input
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Describe what you're working on..."
                className="w-full rounded-lg border border-border bg-surface py-3 pl-4 pr-14 text-sm text-text-primary caret-chrome placeholder:text-text-secondary focus:border-border-focus focus:outline-none"
                autoComplete="off"
                aria-label="Describe what you are working on"
              />
              <button
                type="submit"
                className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md border border-border text-text-primary transition-colors hover:border-accent-ui focus:border-border-focus focus:outline-none"
                aria-label="Continue to intake"
              >
                <span className="text-lg leading-none" aria-hidden>
                  →
                </span>
              </button>
            </div>
          </form>
          <div className="mt-3 text-left">
            <input ref={fileRef} type="file" accept=".json,application/json" className="hidden" onChange={handleFile} />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="text-left text-sm text-text-secondary underline decoration-text-secondary/40 underline-offset-4 transition-colors hover:text-text-primary hover:decoration-text-primary/60"
            >
              📂 Resume a saved session
            </button>
            {resumeHint && (
              <p className="mt-2 text-sm text-red-400" role="alert">
                {resumeHint}
              </p>
            )}
          </div>
        </div>

        {/* 3. Divider */}
        <hr className="my-12 border-0 border-t border-border" />

        {/* 4. Two columns */}
        <div className="grid gap-10 sm:grid-cols-2 sm:gap-8">
          <section aria-labelledby="room-heading">
            <h2 id="room-heading" className="mb-4 text-sm font-semibold uppercase tracking-wide text-text-primary">
              THE ROOM
            </h2>
            <div className="space-y-3 text-sm leading-relaxed">
              <div className="flex flex-wrap items-center gap-x-2">
                <span className="shrink-0 rounded-full" style={roomDotStyle("#E8712A")} aria-hidden />
                <span className="font-semibold text-text-primary">Claude</span>
                <span className="text-[#888888]">Orchestrator</span>
              </div>
              <div className="flex flex-wrap items-center gap-x-2">
                <span className="shrink-0 rounded-full" style={roomDotStyle("#4285F4")} aria-hidden />
                <span className="font-semibold text-text-primary">Gemini</span>
                <span className="text-[#888888]">Deep reasoner</span>
              </div>
              <div className="flex flex-wrap items-center gap-x-2">
                <span className="shrink-0 rounded-full" style={roomDotStyle("#10A37F")} aria-hidden />
                <span className="font-semibold text-text-primary">GPT</span>
                <span className="text-[#888888]">Structurer</span>
              </div>
              <div className="flex flex-wrap items-center gap-x-2">
                <span className="shrink-0 rounded-full" style={roomDotStyle("#20808D")} aria-hidden />
                <span className="font-semibold text-text-primary">Perplexity</span>
                <span className="text-[#888888]">Live researcher + fact-checker</span>
              </div>
            </div>
          </section>

          <section aria-labelledby="how-heading" className="min-w-0 overflow-x-hidden">
            <h2 id="how-heading" className="mb-4 text-sm font-normal uppercase tracking-wide text-[#e8e8e8]">
              HOW IT WORKS
            </h2>
            <ul className="list-none space-y-3 p-0 text-sm font-normal leading-normal text-[#e8e8e8]">
              <li>
                <span className="mr-2 inline-block text-sm text-[#888888]">•</span>
                <span className="text-[#e8e8e8]">You describe your situation</span>
              </li>
              <li>
                <span className="mr-2 inline-block text-sm text-[#888888]">•</span>
                <span className="text-[#e8e8e8]">
                  <span style={{ color: "#E8712A", fontWeight: "bold" }}>Claude</span> clarifies your intent through probing
                </span>
              </li>
              <li>
                <span className="mr-2 inline-block text-sm text-[#888888]">•</span>
                <span className="text-[#e8e8e8]">
                  <span style={{ color: "#4285F4", fontWeight: "bold" }}>Gemini</span> +{" "}
                  <span style={{ color: "#10A37F", fontWeight: "bold" }}>GPT</span> research independently
                </span>
              </li>
              <li>
                <span className="mr-2 inline-block text-sm text-[#888888]">•</span>
                <span className="text-[#e8e8e8]">
                  <span style={{ color: "#20808D", fontWeight: "bold" }}>Perplexity</span> adds live web + citations
                </span>
              </li>
              <li>
                <span className="mr-2 inline-block text-sm text-[#888888]">•</span>
                <span className="text-[#e8e8e8]">
                  <span style={{ color: "#E8712A", fontWeight: "bold" }}>Claude</span> synthesizes — one deliverable
                </span>
              </li>
            </ul>
          </section>
        </div>

        {/* 5. Divider */}
        <hr className="my-12 border-0 border-t border-border" />

        {/* 6. Bottom tagline */}
        <p className="mt-2 text-center text-sm leading-relaxed text-[#888888]">
          All the right experts. One room. No FOMO.
        </p>
      </div>
    </div>
  );
}

export default LandingPage;
