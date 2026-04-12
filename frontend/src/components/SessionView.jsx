/**
 * Screen 3 — Live roundtable via WebSocket.
 *
 * Handshake: { session_config, prompt: sessionConfig.optimized_prompt, history: [] }
 *
 * Flow: session_started → Gemini ∥ GPT (parallel tokens) → perplexity_thinking →
 *       perplexity_complete → synthesis_thinking → synthesis tokens → synthesis_complete.
 * Claude appears only in the Synthesis panel, not in the transcript.
 *
 * Figma frame: 03-Session-View
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MODEL_HEX } from "../constants/modelColors";
import ModelBubble from "./common/ModelBubble";
import SynthesisPanel from "./SynthesisPanel";
import TakeFurther from "./TakeFurther";

const DEFAULT_HTTP = "http://localhost:8000";

/** Browser WebSocket has no configurable open timeout; guard hung connects. */
const WS_CONNECT_TIMEOUT_MS = 120_000;

/** App-level keep-alive (some proxies idle-timeout unidirectional streams). */
const WS_KEEPALIVE_INTERVAL_MS = 30_000;

/** Progress bar — Roundtable node (multi-model stage). */
const ROUNDTABLE_HEX = "#6B6B6B";

function wsUrlFromApiBase() {
  const base = process.env.REACT_APP_API_URL || DEFAULT_HTTP;
  try {
    const u = new URL(base);
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    u.pathname = "/ws/session";
    u.search = "";
    u.hash = "";
    return u.toString();
  } catch {
    return "ws://localhost:8000/ws/session";
  }
}

/** @typedef {'idle' | 'round1_parallel' | 'perplexity' | 'synthesis'} StreamPhase */

function timestamp() {
  return new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function buildTranscriptDict(sessionConfig, prompt, geminiR1, gptR1, perplexityContent, synthesisText) {
  const messages = [
    { role: "user", sender: "You", content: prompt, timestamp: timestamp() },
    {
      role: "assistant",
      sender: "Gemini",
      content: geminiR1,
      round: "round1",
      timestamp: timestamp(),
    },
    {
      role: "assistant",
      sender: "GPT",
      content: gptR1,
      round: "round1",
      timestamp: timestamp(),
    },
  ];
  if (String(perplexityContent || "").trim()) {
    messages.push({
      role: "assistant",
      sender: "Perplexity",
      content: perplexityContent,
      round: "audit",
      timestamp: timestamp(),
    });
  }
  messages.push({
    role: "assistant",
    sender: "Claude",
    content: synthesisText,
    round: "synthesis",
    timestamp: timestamp(),
  });
  return {
    messages,
    session_config: sessionConfig,
    intake_summary: sessionConfig?.intake_summary ?? null,
  };
}

function downloadJsonFile(payload, filename) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function formatTierBadge(tier) {
  const raw = (tier || "smart").toString().toLowerCase().replace(/-/g, "_");
  if (raw === "deep_thinking" || raw === "deep") return "Deep";
  if (raw === "quick") return "Quick";
  return "Smart";
}

const WAIT_HEX = "#888888";

/**
 * @param {Object} props
 * @param {{ id: string, label: string, color: string, done: boolean, active: boolean }[]} props.stages
 */
function SessionProgressBar({ stages }) {
  return (
    <nav
      className="mx-auto max-w-3xl overflow-x-auto pb-0.5 pt-1"
      aria-label="Session progress"
    >
      <div className="flex min-w-min flex-wrap items-center gap-x-1 gap-y-1 text-[11px] leading-tight sm:text-xs">
        {stages.map((s, i) => {
          const state = s.done ? "done" : s.active ? "active" : "wait";
          const sym = state === "done" ? "✓" : state === "active" ? "●" : "○";
          const fg = state === "wait" ? WAIT_HEX : s.color;
          return (
            <React.Fragment key={s.id}>
              {i > 0 ? (
                <span className="shrink-0 px-0.5 text-text-secondary" aria-hidden>
                  →
                </span>
              ) : null}
              <span
                className={`inline-flex shrink-0 items-baseline gap-0.5 whitespace-nowrap ${
                  state === "active" ? "session-progress-node-active" : ""
                }`}
                style={{ color: fg }}
                aria-current={state === "active" ? "step" : undefined}
              >
                <span className="font-mono tabular-nums" aria-hidden>
                  {sym}
                </span>
                <span>{s.label}</span>
              </span>
            </React.Fragment>
          );
        })}
      </div>
    </nav>
  );
}

/** Shown when model_complete arrived but no tokens were received (typical: dropped connection). */
function bubbleBody(text, modelComplete) {
  if (modelComplete && !(text || "").trim()) {
    return "Response interrupted — connection lost";
  }
  return text;
}

/**
 * Pre-token “thinking” row — same footprint as a model bubble; dots pulse in `color`.
 * @param {Object} props
 * @param {string} props.label
 * @param {string} props.color — seat hex
 * @param {boolean} [props.uppercase]
 */
function ThinkingDotsBubble({ label, color, uppercase = true }) {
  return (
    <div
      className="session-thinking-bubble flex max-h-[280px] max-w-[min(100%,40rem)] flex-col overflow-hidden rounded-lg border border-border bg-[#161616] px-4 py-3"
      style={{ borderLeftWidth: 3, borderLeftStyle: "solid", borderLeftColor: color }}
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={`${label} is thinking`}
    >
      <div
        className={`mb-2 text-xs font-semibold ${uppercase ? "uppercase tracking-wide" : "leading-snug"}`}
        style={{ color }}
      >
        {label}
      </div>
      <div className="session-thinking-dots flex min-h-[2rem] items-center gap-1.5 py-1" aria-hidden>
        <span className="session-thinking-dot" style={{ backgroundColor: color }} />
        <span className="session-thinking-dot" style={{ backgroundColor: color }} />
        <span className="session-thinking-dot" style={{ backgroundColor: color }} />
      </div>
    </div>
  );
}

/**
 * @param {Object} props
 * @param {Object} props.sessionConfig
 * @param {Object | null} [props.resumeTranscript] — saved `{ messages, intake_summary? }`; skips WebSocket and shows static session + export
 * @param {function} [props.onSynthesisComplete] — (synthesisMarkdown: string) => void
 * @param {function} [props.onNavigateHome] — return to landing (optional)
 */
function SessionView({ sessionConfig, resumeTranscript = null, onSynthesisComplete, onNavigateHome }) {
  const onSynthesisCompleteRef = useRef(onSynthesisComplete);
  useEffect(() => {
    onSynthesisCompleteRef.current = onSynthesisComplete;
  }, [onSynthesisComplete]);

  const [configError, setConfigError] = useState(null);
  const [transportError, setTransportError] = useState(null);
  const [streamError, setStreamError] = useState(null);

  const [geminiR1, setGeminiR1] = useState("");
  const [gptR1, setGptR1] = useState("");
  const [geminiR1Complete, setGeminiR1Complete] = useState(false);
  const [gptR1Complete, setGptR1Complete] = useState(false);

  const [sessionStarted, setSessionStarted] = useState(false);
  /** off | thinking | content */
  const [perplexityPhase, setPerplexityPhase] = useState(/** @type {"off" | "thinking" | "content"} */ ("off"));
  const [perplexityContent, setPerplexityContent] = useState("");

  const [synthesisThinking, setSynthesisThinking] = useState(false);
  const [synthesisText, setSynthesisText] = useState("");
  const [synthesisStreaming, setSynthesisStreaming] = useState(false);
  const [synthesisFinal, setSynthesisFinal] = useState(false);

  const [sessionComplete, setSessionComplete] = useState(false);

  const [leaveIntent, setLeaveIntent] = useState(null);

  const r1CountsRef = useRef({ Gemini: 0, GPT: 0 });

  const phaseRef = useRef(/** @type {StreamPhase} */ ("idle"));

  /** Bumps re-render when handlers only update `phaseRef` (streaming flags). */
  const [, setStreamPhaseMarker] = useState(0);

  const bubbleScrollRefs = useRef(
    /** @type {{ Gemini: HTMLDivElement | null; GPT: HTMLDivElement | null }} */ ({
      Gemini: null,
      GPT: null,
    })
  );

  const scrollR1BubbleToTop = useCallback((sender) => {
    if (sender !== "Gemini" && sender !== "GPT") return;
    const run = () => {
      const el = bubbleScrollRefs.current[sender];
      if (el) el.scrollTop = 0;
    };
    requestAnimationFrame(() => {
      requestAnimationFrame(run);
    });
  }, []);

  const displayPrompt = useMemo(() => {
    const fromConfig = sessionConfig?.optimized_prompt?.trim();
    if (fromConfig) return sessionConfig.optimized_prompt;
    const u = resumeTranscript?.messages?.find((m) => m.role === "user");
    return u?.content || "";
  }, [sessionConfig, resumeTranscript]);

  const isResume = Boolean(resumeTranscript?.messages?.length);

  const transcriptForExport = useMemo(() => {
    if (resumeTranscript?.messages?.length) {
      return {
        messages: resumeTranscript.messages,
        session_config: sessionConfig,
        intake_summary: resumeTranscript.intake_summary ?? sessionConfig?.intake_summary ?? null,
      };
    }
    return buildTranscriptDict(
      sessionConfig,
      displayPrompt,
      geminiR1,
      gptR1,
      perplexityContent,
      synthesisText
    );
  }, [
    resumeTranscript,
    sessionConfig,
    displayPrompt,
    geminiR1,
    gptR1,
    perplexityContent,
    synthesisText,
  ]);

  const appendToken = useCallback((sender, token) => {
    const phase = phaseRef.current;
    if (!token) return;

    if (phase === "round1_parallel") {
      if (sender === "Gemini") {
        r1CountsRef.current.Gemini += token.length;
        setGeminiR1((prev) => prev + token);
        return;
      }
      if (sender === "GPT") {
        r1CountsRef.current.GPT += token.length;
        setGptR1((prev) => prev + token);
        return;
      }
      return;
    }
    if (phase === "synthesis" && sender === "Claude") {
      setSynthesisText((prev) => prev + token);
      setSynthesisStreaming(true);
      setSynthesisThinking(false);
    }
  }, []);

  const handleModelComplete = useCallback(
    (sender) => {
      if (sender === "Gemini") {
        setGeminiR1Complete(true);
        scrollR1BubbleToTop("Gemini");
        return;
      }
      if (sender === "GPT") {
        setGptR1Complete(true);
        scrollR1BubbleToTop("GPT");
      }
    },
    [scrollR1BubbleToTop]
  );

  useEffect(() => {
    const msgs = resumeTranscript?.messages;
    if (!msgs?.length || !sessionConfig) return;
    let ge = "";
    let gp = "";
    let audit = "";
    let syn = "";
    for (const m of msgs) {
      if (m.role !== "assistant") continue;
      const r = m.round;
      const s = m.sender;
      if (r === "round1") {
        if (s === "Gemini") ge = m.content ?? "";
        if (s === "GPT") gp = m.content ?? "";
      }
      if ((r === "audit" || r === "round1") && s === "Perplexity") {
        audit = m.content ?? audit;
      }
      if (r === "synthesis" && s === "Claude") syn = m.content ?? "";
    }
    setConfigError(null);
    setTransportError(null);
    setStreamError(null);
    setGeminiR1(ge);
    setGptR1(gp);
    setGeminiR1Complete(true);
    setGptR1Complete(true);
    setSessionStarted(true);
    setPerplexityPhase(audit.trim() ? "content" : "off");
    setPerplexityContent(audit);
    setSynthesisThinking(false);
    setSynthesisText(syn);
    setSynthesisStreaming(false);
    setSynthesisFinal(!!String(syn).trim());
    setSessionComplete(true);
    phaseRef.current = "idle";
    r1CountsRef.current = { Gemini: ge.length, GPT: gp.length };
  }, [resumeTranscript, sessionConfig]);

  useEffect(() => {
    if (resumeTranscript?.messages?.length) {
      return undefined;
    }
    if (!sessionConfig || typeof displayPrompt !== "string" || !displayPrompt.trim()) {
      setConfigError("Missing session configuration or optimized prompt.");
      return undefined;
    }

    let cancelled = false;
    const openedRef = { current: false };
    const completedNormallyRef = { current: false };

    phaseRef.current = "idle";
    setStreamPhaseMarker((x) => x + 1);
    r1CountsRef.current = { Gemini: 0, GPT: 0 };
    setConfigError(null);
    setTransportError(null);
    setStreamError(null);
    setGeminiR1("");
    setGptR1("");
    setGeminiR1Complete(false);
    setGptR1Complete(false);
    setSessionStarted(false);
    setPerplexityPhase("off");
    setPerplexityContent("");
    setSynthesisThinking(false);
    setSynthesisText("");
    setSynthesisStreaming(false);
    setSynthesisFinal(false);
    setSessionComplete(false);

    const url = wsUrlFromApiBase();
    const ws = new WebSocket(url);

    let pingIntervalId = 0;

    const connectTimeoutId = window.setTimeout(() => {
      if (cancelled) return;
      if (ws.readyState !== WebSocket.OPEN) {
        try {
          ws.close();
        } catch {
          /* ignore */
        }
        setTransportError("Could not connect — timed out waiting for the server.");
      }
    }, WS_CONNECT_TIMEOUT_MS);

    ws.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }

      switch (data.type) {
        case "ping":
        case "pong":
          break;
        case "session_started":
          setSessionStarted(true);
          phaseRef.current = "round1_parallel";
          setStreamPhaseMarker((n) => n + 1);
          break;
        case "token":
          appendToken(data.sender, data.token);
          break;
        case "model_complete":
          handleModelComplete(data.sender);
          break;
        case "perplexity_thinking":
          phaseRef.current = "perplexity";
          setPerplexityPhase("thinking");
          setStreamPhaseMarker((n) => n + 1);
          break;
        case "perplexity_complete":
          setPerplexityContent(data.content ?? "");
          setPerplexityPhase("content");
          break;
        case "synthesis_thinking":
          setSynthesisThinking(true);
          phaseRef.current = "synthesis";
          setStreamPhaseMarker((n) => n + 1);
          break;
        case "synthesis_complete":
          setSynthesisText(data.content ?? "");
          setSynthesisStreaming(false);
          setSynthesisFinal(true);
          setSynthesisThinking(false);
          phaseRef.current = "idle";
          setStreamPhaseMarker((n) => n + 1);
          onSynthesisCompleteRef.current?.(data.content ?? "");
          break;
        case "session_complete":
          completedNormallyRef.current = true;
          setSessionComplete(true);
          break;
        case "error":
          setStreamError(data.message || "Session error");
          break;
        default:
          break;
      }
    };

    ws.onopen = () => {
      openedRef.current = true;
      window.clearTimeout(connectTimeoutId);
      ws.send(
        JSON.stringify({
          session_config: sessionConfig,
          prompt: displayPrompt,
          history: [],
        })
      );
      pingIntervalId = window.setInterval(() => {
        if (cancelled || ws.readyState !== WebSocket.OPEN) return;
        try {
          ws.send(JSON.stringify({ type: "ping", t: Date.now() }));
        } catch {
          /* ignore */
        }
      }, WS_KEEPALIVE_INTERVAL_MS);
    };

    ws.onerror = () => {
      /* Browser gives no details; onclose handles messaging. */
    };

    ws.onclose = () => {
      window.clearTimeout(connectTimeoutId);
      if (pingIntervalId) window.clearInterval(pingIntervalId);
      if (cancelled || completedNormallyRef.current) return;
      if (!openedRef.current) {
        setTransportError((prev) => prev || "WebSocket connection failed.");
      } else {
        setTransportError("Session disconnected — responses may be incomplete.");
      }
    };

    return () => {
      cancelled = true;
      window.clearTimeout(connectTimeoutId);
      if (pingIntervalId) window.clearInterval(pingIntervalId);
      ws.onmessage = null;
      ws.onclose = null;
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, [sessionConfig, displayPrompt, resumeTranscript, appendToken, handleModelComplete]);

  const sessionSettled = synthesisFinal;

  const downloadResumePayload = useCallback(() => {
    const transcript = {
      messages: transcriptForExport.messages,
      intake_summary: transcriptForExport.intake_summary ?? null,
    };
    const slug = new Date().toISOString().slice(0, 10);
    downloadJsonFile({ session_config: sessionConfig, transcript }, `ai-roundtable-session-${slug}.json`);
  }, [sessionConfig, transcriptForExport]);

  const requestHome = useCallback(() => {
    if (!onNavigateHome) return;
    if (sessionSettled) onNavigateHome();
    else setLeaveIntent("home");
  }, [onNavigateHome, sessionSettled]);

  const requestSaveExit = useCallback(() => {
    if (!onNavigateHome) return;
    if (sessionSettled) {
      downloadResumePayload();
      onNavigateHome();
    } else {
      setLeaveIntent("save-exit");
    }
  }, [onNavigateHome, sessionSettled, downloadResumePayload]);

  const confirmLeave = useCallback(() => {
    const intent = leaveIntent;
    setLeaveIntent(null);
    if (!onNavigateHome) return;
    if (intent === "save-exit") {
      downloadResumePayload();
    }
    onNavigateHome();
  }, [leaveIntent, onNavigateHome, downloadResumePayload]);

  const inlineAlert = streamError || transportError;
  const synthesisBody =
    synthesisFinal && !synthesisText.trim()
      ? "Response interrupted — connection lost"
      : synthesisText;

  const transcriptLive = !resumeTranscript?.messages?.length;
  const promptOk = Boolean(String(displayPrompt || "").trim());

  const synthesisPhaseEntered = useMemo(() => {
    return (
      synthesisThinking ||
      synthesisStreaming ||
      synthesisFinal ||
      Boolean(String(synthesisText || "").trim())
    );
  }, [synthesisThinking, synthesisStreaming, synthesisFinal, synthesisText]);

  const progressStagesFixed = useMemo(() => {
    const intakeDone = true;
    const roundtableDone = isResume ? true : synthesisPhaseEntered;
    const roundtableWait = transcriptLive && !isResume && !sessionStarted && promptOk && !configError;
    const roundtableActive =
      transcriptLive && !isResume && sessionStarted && !synthesisPhaseEntered && !roundtableWait;

    const synthesisDone = synthesisFinal;
    const synthesisActive = synthesisPhaseEntered && !synthesisFinal;

    return [
      { id: "intake", label: "Intake", color: MODEL_HEX.Claude, done: intakeDone, active: false },
      {
        id: "roundtable",
        label: "Roundtable",
        color: ROUNDTABLE_HEX,
        done: roundtableDone,
        active: roundtableActive,
      },
      {
        id: "synthesis",
        label: "Synthesis",
        color: MODEL_HEX.Claude,
        done: synthesisDone,
        active: synthesisActive,
      },
    ];
  }, [
    isResume,
    transcriptLive,
    sessionStarted,
    synthesisPhaseEntered,
    synthesisFinal,
    promptOk,
    configError,
  ]);

  const showTranscriptRoundtable = isResume || sessionStarted;

  const showGeminiThinking =
    transcriptLive && !configError && promptOk && sessionStarted && !geminiR1Complete && !String(geminiR1).trim();
  const showGptThinking =
    transcriptLive && !configError && promptOk && sessionStarted && !gptR1Complete && !String(gptR1).trim();

  const geminiR1Streaming = sessionStarted && !geminiR1Complete && Boolean(String(geminiR1).length);
  const gptR1Streaming = sessionStarted && !gptR1Complete && Boolean(String(gptR1).length);

  return (
    <div className="min-h-screen bg-bg text-text-primary">
      {leaveIntent && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="leave-dialog-title"
        >
          <div className="w-full max-w-md rounded-lg border border-border bg-surface px-5 py-5 shadow-lg">
            <h2 id="leave-dialog-title" className="text-base font-semibold text-text-primary">
              {leaveIntent === "save-exit" ? "Save and exit?" : "Leave session?"}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">
              {leaveIntent === "save-exit"
                ? "Session in progress — your responses will be lost unless you save. Save a session .json file and go home?"
                : "Session in progress — your responses will be lost. Go home anyway?"}
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setLeaveIntent(null)}
                className="rounded-lg border border-border px-4 py-2 text-sm text-text-primary transition-colors hover:border-border-focus focus:border-border-focus focus:outline-none"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmLeave}
                className="rounded-lg border border-border-focus bg-surface px-4 py-2 text-sm font-medium text-text-primary transition-colors hover:border-claude focus:outline-none"
              >
                {leaveIntent === "save-exit" ? "Save & exit" : "Go home"}
              </button>
            </div>
          </div>
        </div>
      )}

      <header className="border-b border-border px-4 py-3 sm:px-6">
        <div className="mx-auto flex max-w-3xl items-center gap-3">
          <button
            type="button"
            onClick={requestHome}
            className="shrink-0 rounded-lg px-2 py-1.5 text-left text-sm text-text-primary transition-colors hover:text-claude focus:outline-none focus:ring-1 focus:ring-border-focus"
          >
            ← Home
          </button>
          <div className="flex min-w-0 flex-1 items-center justify-center gap-2">
            <span className="truncate text-sm font-semibold text-text-primary">⬡ ai-roundtable</span>
            <span className="shrink-0 rounded border border-border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-secondary">
              {formatTierBadge(sessionConfig?.tier)}
            </span>
          </div>
          <button
            type="button"
            onClick={requestSaveExit}
            className="shrink-0 rounded-lg px-2 py-1.5 text-sm text-text-primary transition-colors hover:text-claude focus:outline-none focus:ring-1 focus:ring-border-focus"
          >
            💾 Save & Exit
          </button>
        </div>
        <SessionProgressBar stages={progressStagesFixed} />
        {sessionConfig?.session_title && (
          <p className="mx-auto mt-1 max-w-3xl truncate text-center text-xs text-text-secondary">{sessionConfig.session_title}</p>
        )}
      </header>

      <div className="mx-auto max-w-3xl space-y-6 px-4 py-6 sm:px-6">
        {configError && (
          <p className="text-sm text-red-400" role="alert">
            {configError}
          </p>
        )}

        <section aria-label="Session prompt">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Your prompt
          </h2>
          <div className="rounded-lg border border-border bg-surface px-4 py-3 text-sm leading-relaxed text-text-primary whitespace-pre-wrap">
            {displayPrompt || "—"}
          </div>
        </section>

        <section aria-label="Model responses" className="space-y-4">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Transcript
          </h2>

          {showTranscriptRoundtable && (
            <>
              <div className="space-y-4">
                {showGeminiThinking ? (
                  <ThinkingDotsBubble label="GEMINI" color={MODEL_HEX.Gemini} />
                ) : (
                  <ModelBubble
                    sender="Gemini"
                    content={bubbleBody(geminiR1, geminiR1Complete)}
                    isStreaming={geminiR1Streaming}
                    round="round1"
                    complete={geminiR1Complete}
                    scrollContainerRef={(el) => {
                      bubbleScrollRefs.current.Gemini = el;
                    }}
                  />
                )}

                {showGptThinking ? (
                  <ThinkingDotsBubble label="GPT" color={MODEL_HEX.GPT} />
                ) : (
                  <ModelBubble
                    sender="GPT"
                    content={bubbleBody(gptR1, gptR1Complete)}
                    isStreaming={gptR1Streaming}
                    round="round1"
                    complete={gptR1Complete}
                    scrollContainerRef={(el) => {
                      bubbleScrollRefs.current.GPT = el;
                    }}
                  />
                )}
              </div>

              {perplexityPhase === "thinking" && (
                <ThinkingDotsBubble
                  label="🔎 PERPLEXITY · auditing + live research"
                  color={MODEL_HEX.Perplexity}
                  uppercase={false}
                />
              )}

              {perplexityPhase === "content" && String(perplexityContent).trim() && (
                <ModelBubble
                  sender="Perplexity"
                  content={perplexityContent}
                  isStreaming={false}
                  round="audit"
                  complete
                  titleOverride="🔎 PERPLEXITY · fact-check"
                  scrollContainerRef={undefined}
                />
              )}
            </>
          )}

          {inlineAlert && (
            <p
              className="max-w-[min(100%,40rem)] rounded-lg border border-red-900/50 bg-surface px-4 py-3 text-sm text-red-400"
              role="alert"
            >
              {inlineAlert}
            </p>
          )}
        </section>

        {(synthesisThinking ||
          synthesisStreaming ||
          synthesisFinal ||
          synthesisText.length > 0) && (
          <section aria-label="Synthesis" className="space-y-4">
            {synthesisThinking && !synthesisFinal && !String(synthesisText).trim() && (
              <ThinkingDotsBubble
                label="🟠 CLAUDE · synthesizing"
                color={MODEL_HEX.Claude}
                uppercase={false}
              />
            )}
            {(synthesisStreaming || synthesisFinal || synthesisText.length > 0) && (
              <SynthesisPanel
                content={synthesisBody}
                isStreaming={synthesisStreaming && !synthesisFinal}
                complete={synthesisFinal}
              />
            )}
          </section>
        )}

        {sessionComplete && (
          <TakeFurther sessionConfig={sessionConfig} transcript={transcriptForExport} />
        )}
      </div>
    </div>
  );
}

export default SessionView;
