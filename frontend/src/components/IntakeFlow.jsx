/**
 * frontend/src/components/IntakeFlow.jsx
 *
 * Screen 2 — Gemini Flash intake (two-turn max).
 *
 * Flow:
 *   1. Mount with initialUserMessage → POST /api/intake/start
 *   2a. status "clarifying" → show inline clarifying question
 *       User answers → POST /api/intake/respond → status "complete"
 *   2b. status "complete" → show tier badge + reasoning
 *   3. User confirms tier (or overrides) → onComplete(config)
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import Header from "./common/Header";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

const TIER_LABELS = {
  quick: "⚡ Quick",
  smart: "⚖ Smart",
  deep:  "🔍 Deep",
};

const TIER_DESCRIPTIONS = {
  quick: "Single executor per model · fastest · good for gut checks and brainstorms",
  smart: "Executor + advisor per model · near-Deep quality · recommended for most sessions",
  deep:  "Flagship models throughout · maximum depth · best for reports and critical decisions",
};

/**
 * @param {Object}   props
 * @param {string}   props.initialUserMessage  — prompt from landing page
 * @param {function} props.onComplete          — (session_config) => void
 * @param {function} [props.onBack]            — optional return to landing
 */
function IntakeFlow({ initialUserMessage, onComplete, onBack }) {
  /** "analyzing" | "clarifying" | "badge" | "error" */
  const [phase, setPhase] = useState("analyzing");
  const [sessionId, setSessionId] = useState(null);
  const [clarifyingQuestion, setClarifyingQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [submittingAnswer, setSubmittingAnswer] = useState(false);
  const [config, setConfig] = useState(null);
  /** Whether the inline tier override panel is open */
  const [showOverride, setShowOverride] = useState(false);
  const [tierChoice, setTierChoice] = useState("smart");
  const [error, setError] = useState(null);
  const answerRef = useRef(null);
  const hasFiredRef = useRef(false);

  // Auto-focus clarifying answer input when it appears
  useEffect(() => {
    if (phase === "clarifying") answerRef.current?.focus();
  }, [phase]);

  // On mount: call /api/intake/start with the prompt
  useEffect(() => {
    if (hasFiredRef.current) return;
    hasFiredRef.current = true;

    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/intake/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: initialUserMessage }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        const data = await res.json();
        setSessionId(data.session_id);

        if (data.status === "clarifying") {
          setClarifyingQuestion(data.clarifying_question || "");
          setPhase("clarifying");
        } else {
          const cfg = data.config || {};
          setConfig(cfg);
          setTierChoice(cfg.tier || "smart");
          setPhase("badge");
        }
      } catch (e) {
        setError(e.message || "Intake failed — please go back and try again.");
        setPhase("error");
      }
    })();
  }, [initialUserMessage]);

  const submitAnswer = useCallback(async () => {
    const text = answer.trim();
    if (!text || !sessionId || submittingAnswer) return;
    setSubmittingAnswer(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/intake/respond`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, answer: text }),
      });
      if (!res.ok) {
        if (res.status === 404) throw new Error("Session expired — go back and try again.");
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      const cfg = data.config || {};
      setConfig(cfg);
      setTierChoice(cfg.tier || "smart");
      setPhase("badge");
    } catch (e) {
      setError(e.message || "Submit failed");
    } finally {
      setSubmittingAnswer(false);
    }
  }, [answer, sessionId, submittingAnswer]);

  const handleConfirm = useCallback(() => {
    if (!config || typeof onComplete !== "function") return;
    onComplete({ ...config, tier: tierChoice });
  }, [config, tierChoice, onComplete]);

  return (
    <div className="flex h-[100dvh] min-h-0 flex-col bg-[#0d0d0d] text-[#e8e8e8]">
      <Header
        onHome={typeof onBack === "function" ? onBack : undefined}
        onSaveExit={typeof onBack === "function" ? onBack : undefined}
      />

      <div className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center px-6">
        {/* ── Analyzing ── */}
        {phase === "analyzing" && (
          <div className="space-y-3 text-center">
            <p className="text-sm text-[#888888]">Analyzing your prompt…</p>
            <div className="mx-auto h-1 w-24 overflow-hidden rounded-full bg-[#2a2a2a]">
              <div className="h-full animate-pulse rounded-full bg-[#F5A623]" />
            </div>
          </div>
        )}

        {/* ── Clarifying question ── */}
        {phase === "clarifying" && (
          <div className="w-full space-y-5">
            {/* Prompt echo */}
            <div className="rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-3">
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-[#888888]">Your prompt</p>
              <p className="text-sm leading-relaxed text-[#e8e8e8]">{initialUserMessage}</p>
            </div>

            {/* Clarifying question */}
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-[#888888]">One question</p>
              <p className="text-[0.9375rem] leading-relaxed text-[#e8e8e8]">{clarifyingQuestion}</p>
            </div>

            {/* Answer input */}
            <form
              onSubmit={(e) => { e.preventDefault(); submitAnswer(); }}
              className="flex gap-2"
            >
              <label htmlFor="clarify-answer" className="sr-only">Your answer</label>
              <textarea
                id="clarify-answer"
                ref={answerRef}
                rows={3}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                disabled={submittingAnswer}
                placeholder="Your answer…"
                className="min-h-[2.75rem] min-w-0 flex-1 resize-y rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-2 text-sm text-[#e8e8e8] placeholder:text-[#888888] focus:border-[#6B6B6B] focus:outline-none disabled:opacity-60"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submitAnswer();
                  }
                }}
              />
              <button
                type="submit"
                disabled={submittingAnswer || !answer.trim()}
                className="inline-flex h-10 shrink-0 items-center justify-center self-start rounded-lg border border-[#6B6B6B] bg-[#1e1e1e] px-3 text-[#e8e8e8] focus:outline-none disabled:opacity-40"
                aria-label={submittingAnswer ? "Submitting" : "Submit answer"}
              >
                <span aria-hidden>{submittingAnswer ? "…" : "→"}</span>
              </button>
            </form>

            {error && <p className="text-sm text-red-400" role="alert">{error}</p>}
          </div>
        )}

        {/* ── Tier badge ── */}
        {phase === "badge" && config && (
          <div className="w-full space-y-5">
            {/* Optimized prompt */}
            <div>
              <p className="mb-1 text-xs font-medium uppercase tracking-wide text-[#888888]">Optimized prompt</p>
              <div className="max-h-[180px] overflow-y-auto rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-3 text-sm leading-relaxed text-[#e8e8e8] whitespace-pre-wrap break-words">
                {config.optimized_prompt || <span className="text-[#888888]">(no prompt)</span>}
              </div>
            </div>

            {/* Tier badge */}
            <div className="flex items-start justify-between gap-3 rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-flex items-center rounded-md px-2.5 py-0.5 text-xs font-semibold"
                    style={{ background: "#F5A623", color: "#0d0d0d" }}
                  >
                    {TIER_LABELS[tierChoice] || tierChoice}
                  </span>
                  <span className="text-sm font-medium text-[#e8e8e8]">
                    {config.output_type
                      ? config.output_type.charAt(0).toUpperCase() + config.output_type.slice(1)
                      : ""}
                  </span>
                </div>
                <p className="mt-1.5 text-sm text-[#888888]">{config.reasoning}</p>
              </div>
              <button
                type="button"
                onClick={() => setShowOverride((v) => !v)}
                className="shrink-0 text-sm text-[#888888] underline-offset-2 hover:text-[#e8e8e8] focus:outline-none"
              >
                {showOverride ? "Close" : "Change"}
              </button>
            </div>

            {/* Inline tier override */}
            {showOverride && (
              <div className="space-y-3 rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-4">
                <p className="text-xs font-medium uppercase tracking-wide text-[#888888]">Override tier</p>
                <div className="flex gap-3">
                  {["quick", "smart", "deep"].map((id) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => { setTierChoice(id); setShowOverride(false); }}
                      className={`min-w-0 flex-1 rounded-lg border px-3 py-2.5 text-center text-sm font-medium transition-colors focus:outline-none ${
                        tierChoice === id
                          ? "border-[#6B6B6B] bg-[#2a2a2a] text-[#e8e8e8]"
                          : "border-[#2a2a2a] bg-[#0d0d0d] text-[#888888] hover:border-[#6B6B6B]"
                      }`}
                    >
                      {TIER_LABELS[id]}
                    </button>
                  ))}
                </div>
                <p className="text-xs leading-relaxed text-[#666666]">
                  {TIER_DESCRIPTIONS[tierChoice]}
                </p>
              </div>
            )}

            {/* Confirm */}
            <div className="flex justify-end">
              <button
                type="button"
                onClick={handleConfirm}
                className="rounded-lg px-6 py-2.5 text-sm font-bold transition-opacity hover:opacity-90 focus:outline-none"
                style={{ background: "#F5A623", color: "#0d0d0d" }}
              >
                Start roundtable →
              </button>
            </div>
          </div>
        )}

        {/* ── Error ── */}
        {phase === "error" && (
          <div className="w-full space-y-4 text-center">
            <p className="text-sm text-red-400">{error}</p>
            {typeof onBack === "function" && (
              <button
                type="button"
                onClick={onBack}
                className="text-sm text-[#888888] hover:text-[#e8e8e8] focus:outline-none"
              >
                ← Back
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default IntakeFlow;
