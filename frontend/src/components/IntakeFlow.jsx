/**
 * frontend/src/components/IntakeFlow.jsx
 *
 * Screen 2 — Intake analysis (two-turn max).
 *
 * Flow:
 *   1. Mount with initialUserMessage → POST /api/intake/start
 *   2a. status "clarifying" → show inline clarifying question
 *       User answers → POST /api/intake/respond → status "complete"
 *   2b. status "complete" → show tier badge + reasoning
 *   3. User confirms tier → onComplete(config)
 *
 * Tier logic:
 *   - Intake assigns "smart" or "deep" based on prompt complexity.
 *   - If intake assigns deep: no slider, badge shows "🔭 Deep · Auto-selected",
 *     user cannot downgrade.
 *   - If intake assigns smart: pill slider shown, user can upgrade to deep
 *     (one-directional — once deep is selected, no return to smart).
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import Header from "./common/Header";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

/** Progressive loading messages — shown in order during the analyzing phase. */
const LOADING_MESSAGES = [
  "Analyzing your prompt...",
  "Optimizing for research...",
  "Almost ready...",
];

/** Delays (ms) before switching to each subsequent message. Index 0 fires at 2s, index 1 at 5s. */
const LOADING_DELAYS = [2000, 5000];

/** After this many ms, show the "taking longer" fallback with a cancel option. */
const TIMEOUT_MS = 15000;

/**
 * Quick-reply chips shown above the clarifying answer textarea.
 * Clicking a chip fills the textarea so the user can submit as-is or edit.
 */
const QUICK_CHIPS = [
  "Still early — just exploring",
  "Need a decision soon",
  "No hard constraints",
  "Let me give more context",
];

/**
 * @param {Object}   props
 * @param {string}   props.initialUserMessage  — prompt from landing page
 * @param {function} props.onComplete          — (session_config) => void
 * @param {function} [props.onBack]            — optional return to landing
 */
function IntakeFlow({ initialUserMessage, onComplete, onBack }) {
  /** "analyzing" | "clarifying" | "error" — badge phase removed; intake calls onComplete directly */
  const [phase, setPhase] = useState("analyzing");
  const [sessionId, setSessionId] = useState(null);
  const [clarifyingQuestion, setClarifyingQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [submittingAnswer, setSubmittingAnswer] = useState(false);
  const [error, setError] = useState(null);
  /** Index into LOADING_MESSAGES — advances on a schedule while analyzing. */
  const [loadingMsgIdx, setLoadingMsgIdx] = useState(0);
  /** True when intake has exceeded TIMEOUT_MS with no response. */
  const [timedOut, setTimedOut] = useState(false);
  const answerRef = useRef(null);
  const hasFiredRef = useRef(false);

  // Auto-focus clarifying answer input when it appears
  useEffect(() => {
    if (phase === "clarifying") answerRef.current?.focus();
  }, [phase]);

  // Progressive loading messages — advance through LOADING_MESSAGES while analyzing.
  // Timers are cleared as soon as phase changes (intake returned or error).
  useEffect(() => {
    if (phase !== "analyzing") return;

    const ids = [];
    let cumulative = 0;
    for (let i = 1; i < LOADING_MESSAGES.length; i++) {
      cumulative += LOADING_DELAYS[i - 1];
      const idx = i; // capture
      const id = setTimeout(() => {
        // Only advance if still analyzing (guard against race with fast intake)
        setLoadingMsgIdx((prev) => Math.max(prev, idx));
      }, cumulative);
      ids.push(id);
    }

    // Timeout sentinel — if intake hasn't returned in TIMEOUT_MS, show fallback.
    const timeoutId = setTimeout(() => setTimedOut(true), TIMEOUT_MS);
    ids.push(timeoutId);

    return () => ids.forEach(clearTimeout);
  }, [phase]);

  // On mount: call /api/intake/start with the prompt.
  // On success, call onComplete directly — no badge confirmation screen.
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
          // Fix 3: transition immediately — don't wait for user to confirm badge screen.
          if (typeof onComplete === "function") {
            onComplete({ ...(data.config || {}), tier: "smart" });
          }
        }
      } catch (e) {
        setError(e.message || "Intake failed — please go back and try again.");
        setPhase("error");
      }
    })();
  }, [initialUserMessage, onComplete]);

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
      // Fix 3: immediate transition after clarifying answer too.
      if (typeof onComplete === "function") {
        onComplete({ ...(data.config || {}), tier: "smart" });
      }
    } catch (e) {
      setError(e.message || "Submit failed");
    } finally {
      setSubmittingAnswer(false);
    }
  }, [answer, sessionId, submittingAnswer, onComplete]);

  return (
    <div className="flex h-[100dvh] min-h-0 flex-col bg-[#0d0d0d] text-[#e8e8e8]">
      <Header
        onHome={typeof onBack === "function" ? onBack : undefined}
        onSaveExit={typeof onBack === "function" ? onBack : undefined}
      />

      <div className="mx-auto flex w-full max-w-xl flex-1 flex-col items-center justify-center px-6">
        {/* ── Analyzing ── */}
        {phase === "analyzing" && (
          <div className="space-y-4 text-center">
            {timedOut ? (
              /* Fix 2: timeout fallback */
              <div className="space-y-4">
                <p className="text-sm text-[#888888]">Taking longer than usual...</p>
                {typeof onBack === "function" && (
                  <button
                    type="button"
                    onClick={onBack}
                    className="rounded-lg border border-[#444444] px-5 py-2 text-sm text-[#e8e8e8] transition-colors hover:border-[#F5A623] hover:text-[#F5A623] focus:outline-none"
                  >
                    Cancel and try again
                  </button>
                )}
              </div>
            ) : (
              /* Fix 1: progressive messages */
              <>
                <div>
                  <p className="text-sm text-[#e8e8e8]">{LOADING_MESSAGES[loadingMsgIdx]}</p>
                  <p className="mt-1 text-xs text-[#555555]">This usually takes 3-5 seconds</p>
                </div>
                <div className="mx-auto h-1 w-24 overflow-hidden rounded-full bg-[#2a2a2a]">
                  <div className="h-full animate-pulse rounded-full bg-[#F5A623]" />
                </div>
              </>
            )}
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

            {/* Quick-reply chips */}
            <div className="flex flex-wrap gap-2">
              {QUICK_CHIPS.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  disabled={submittingAnswer}
                  onClick={() => {
                    setAnswer(chip);
                    answerRef.current?.focus();
                  }}
                  className="rounded-full border border-[#3a3a3a] bg-[#1e1e1e] px-3 py-1 text-xs text-[#aaaaaa] transition-colors hover:border-[#F5A623] hover:text-[#F5A623] focus:outline-none disabled:opacity-40"
                >
                  {chip}
                </button>
              ))}
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
                style={{ background: "#F5A623", color: "#0d0d0d" }}
                className="inline-flex h-10 w-10 shrink-0 items-center justify-center self-start rounded-lg font-bold transition-opacity hover:opacity-90 focus:outline-none disabled:opacity-40"
                aria-label={submittingAnswer ? "Submitting" : "Submit answer"}
              >
                <span aria-hidden>{submittingAnswer ? "…" : "→"}</span>
              </button>
            </form>

            {error && <p className="text-sm text-red-400" role="alert">{error}</p>}
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
