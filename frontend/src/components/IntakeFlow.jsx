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

/** Max progress segments shown — reflects typical minimum question count. */
const MAX_QUESTIONS = 3;

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
  const [suggestedOptions, setSuggestedOptions] = useState([]);
  const [openingMessage, setOpeningMessage] = useState("");
  const [answer, setAnswer] = useState("");
  const [submittingAnswer, setSubmittingAnswer] = useState(false);
  const [error, setError] = useState(null);
  /** Index into LOADING_MESSAGES — advances on a schedule while analyzing. */
  const [loadingMsgIdx, setLoadingMsgIdx] = useState(0);
  /** True when intake has exceeded TIMEOUT_MS with no response. */
  const [timedOut, setTimedOut] = useState(false);
  const [questionCount, setQuestionCount] = useState(0);
  /** Chip value being submitted — drives loading state on that row. */
  const [selectedChip, setSelectedChip] = useState(null);
  const answerRef = useRef(null);
  const hasFiredRef = useRef(false);

  // Auto-focus custom answer textarea when clarifying phase loads
  useEffect(() => {
    if (phase === "clarifying") answerRef.current?.focus();
  }, [phase]);

  // Progressive loading messages — advance through LOADING_MESSAGES while analyzing.
  useEffect(() => {
    if (phase !== "analyzing") return;

    const ids = [];
    let cumulative = 0;
    for (let i = 1; i < LOADING_MESSAGES.length; i++) {
      cumulative += LOADING_DELAYS[i - 1];
      const idx = i;
      const id = setTimeout(() => {
        setLoadingMsgIdx((prev) => Math.max(prev, idx));
      }, cumulative);
      ids.push(id);
    }

    const timeoutId = setTimeout(() => setTimedOut(true), TIMEOUT_MS);
    ids.push(timeoutId);

    return () => ids.forEach(clearTimeout);
  }, [phase]);

  // On mount: call /api/intake/start with the prompt.
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

        if (data.opening_message) setOpeningMessage(data.opening_message);

        if (data.status === "clarifying") {
          setClarifyingQuestion(data.clarifying_question || "");
          setSuggestedOptions(data.suggested_options || []);
          setQuestionCount((prev) => prev + 1);
          setPhase("clarifying");
        } else {
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

  /**
   * Submit an answer. Accepts an optional overrideValue for direct chip submits
   * so we don't depend on async state settling.
   */
  const submitAnswer = useCallback(async (overrideValue) => {
    const text = (overrideValue !== undefined ? overrideValue : answer).trim();
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
      if (data.status === "complete") {
        if (typeof onComplete === "function") {
          onComplete({ ...(data.config || {}), tier: "smart" });
        }
      } else if (data.status === "clarifying") {
        setAnswer("");
        setSelectedChip(null);
        setClarifyingQuestion(data.clarifying_question || "");
        setSuggestedOptions(data.suggested_options || []);
        setQuestionCount((prev) => prev + 1);
        setPhase("clarifying");
      }
    } catch (e) {
      setError(e.message || "Submit failed");
      setSelectedChip(null);
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

      {/* YOUR PROMPT — persistent strip always visible above the Q&A */}
      <div className="shrink-0 border-b border-[#1a1a1a] px-6 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-[#555555]">Your prompt</p>
        <p className="mt-0.5 truncate text-sm text-[#888888]">{initialUserMessage}</p>
      </div>

      {/* Scrollable content area */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-xl px-6">

          {/* ── Analyzing ── */}
          {phase === "analyzing" && (
            <div className="flex min-h-full items-center justify-center py-20">
              <div className="space-y-4 text-center">
                {timedOut ? (
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
                  <>
                    <div>
                      <p className="text-sm text-[#e8e8e8]">{LOADING_MESSAGES[loadingMsgIdx]}</p>
                      <p className="mt-1 text-xs text-[#555555]">This usually takes 3–5 seconds</p>
                    </div>
                    <div className="mx-auto h-1 w-24 overflow-hidden rounded-full bg-[#2a2a2a]">
                      <div className="h-full animate-pulse rounded-full bg-[#F5A623]" />
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* ── Clarifying question ── */}
          {phase === "clarifying" && (
            <div className="space-y-6 py-10">

              {/* Progress segments */}
              <div className="flex items-center gap-1.5">
                {Array.from({ length: MAX_QUESTIONS }).map((_, i) => (
                  <div
                    key={i}
                    className={`h-1 w-8 rounded-full transition-colors duration-300 ${
                      i < questionCount - 1
                        ? "bg-[#F5A623]"
                        : i === questionCount - 1
                        ? "bg-[#F5A623] opacity-50"
                        : "bg-[#2a2a2a]"
                    }`}
                  />
                ))}
                <span className="ml-1 text-xs text-[#888888]">Question {questionCount}</span>
              </div>

              {/* Opening framing — shown when server provides it */}
              {openingMessage && (
                <p className="text-sm leading-relaxed text-[#aaaaaa]">{openingMessage}</p>
              )}

              {/* Clarifying question — primary text */}
              <p className="text-[1.0625rem] font-medium leading-relaxed text-[#e8e8e8]">
                {clarifyingQuestion}
              </p>

              {/* Answer option rows — each chip is a direct submit */}
              {suggestedOptions.length > 0 && (
                <div className="space-y-2">
                  {suggestedOptions.map((chip) => {
                    const isSubmitting = chip === selectedChip && submittingAnswer;
                    return (
                      <button
                        key={chip}
                        type="button"
                        disabled={submittingAnswer}
                        onClick={() => {
                          setSelectedChip(chip);
                          submitAnswer(chip);
                        }}
                        className={`w-full rounded-lg border px-4 py-3 text-left text-sm transition-all focus:outline-none disabled:cursor-not-allowed ${
                          chip === selectedChip
                            ? "border-[#F5A623] bg-[#1e1a12] text-[#F5A623]"
                            : "border-[#2a2a2a] bg-[#141414] text-[#cccccc] hover:border-[#3a3a3a] hover:bg-[#1a1a1a] hover:text-[#e8e8e8]"
                        }`}
                      >
                        <span className="flex items-center justify-between">
                          {chip}
                          {isSubmitting && (
                            <span className="text-xs text-[#F5A623] opacity-70">...</span>
                          )}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Divider — separates option rows from free-form textarea */}
              <div className="flex items-center gap-3">
                <hr className="flex-1 border-0 border-t border-[#2a2a2a]" />
                <span className="text-xs text-[#777777]">
                  {suggestedOptions.length > 0 ? "or type your own" : "type your answer"}
                </span>
                <hr className="flex-1 border-0 border-t border-[#2a2a2a]" />
              </div>

              {/* Free-form answer */}
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
                  placeholder={suggestedOptions.length > 0 ? "Add detail or type a different answer…" : "Your answer…"}
                  className="min-h-[2.75rem] min-w-0 flex-1 resize-y rounded-lg border border-[#2a2a2a] bg-[#141414] px-3 py-2 text-sm text-[#e8e8e8] placeholder:text-[#444444] focus:border-[#6B6B6B] focus:outline-none disabled:opacity-60"
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
                  <span aria-hidden>{submittingAnswer && !selectedChip ? "…" : "→"}</span>
                </button>
              </form>

              {error && <p className="text-sm text-red-400" role="alert">{error}</p>}
            </div>
          )}

          {/* ── Error ── */}
          {phase === "error" && (
            <div className="flex min-h-full items-center justify-center py-20">
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
            </div>
          )}

        </div>
      </div>
    </div>
  );
}

export default IntakeFlow;
