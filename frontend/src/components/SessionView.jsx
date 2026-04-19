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
import Header from "./common/Header";
import ModelBubble from "./common/ModelBubble";
import SynthesisPanel from "./SynthesisPanel";
import TakeFurther from "./TakeFurther";

const DEFAULT_HTTP = "http://localhost:8000";

/** Browser WebSocket has no configurable open timeout; guard hung connects. */
const WS_CONNECT_TIMEOUT_MS = 120_000;

/** App-level keep-alive (some proxies idle-timeout unidirectional streams). */
const WS_KEEPALIVE_INTERVAL_MS = 30_000;

/** Max reconnect attempts before showing the terminal disconnection error. */
const WS_RECONNECT_MAX = 3;

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

/**
 * Collapsible stage header — active stages show plain label, done stages show toggle.
 */
function StageHeader({ label, summary, done, open, onToggle, active }) {
  if (!done) {
    return (
      <h2 className={`text-xs font-semibold uppercase tracking-wide text-text-secondary ${active ? "animate-pulse" : ""}`}>
        {label}
      </h2>
    );
  }
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center gap-2 text-left focus:outline-none"
      aria-expanded={open}
    >
      <span
        aria-hidden
        className="shrink-0 text-[10px] text-text-secondary"
        style={{ display: "inline-block", transform: open ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform 0.15s" }}
      >
        ▾
      </span>
      <span className="text-xs font-semibold uppercase tracking-wide text-text-secondary">{label}</span>
      {!open && summary && (
        <span className="ml-1 text-xs text-[#555555]">{summary}</span>
      )}
      <span className="ml-auto text-xs text-[#555555]" aria-hidden>✓</span>
    </button>
  );
}

function timestamp() {
  return new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function buildTranscriptDict(sessionConfig, prompt, geminiR1, gptR1, grokR1, claudeR1, perplexityContent, synthesisText) {
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
    {
      role: "assistant",
      sender: "Grok",
      content: grokR1,
      round: "round1",
      timestamp: timestamp(),
    },
    {
      role: "assistant",
      sender: "Claude",
      content: claudeR1,
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
  if (raw === "deep_thinking" || raw === "deep") return "DEEP MODE";
  if (raw === "quick") return "QUICK MODE";
  return "SMART MODE";
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

/** True when model text is a backend skip/unavailable notice, not real content. */
function isSkipNotice(text) {
  const t = (text || "").trim();
  return t.startsWith("[") && t.endsWith("]");
}

/**
 * Pre-token “thinking” row — same footprint as a model bubble; dots pulse in `color`.
 * @param {Object} props
 * @param {string} props.label
 * @param {string} props.color — seat hex
 * @param {boolean} [props.uppercase]
 */
function ThinkingDotsBubble({ label, color, uppercase = true, subtitle }) {
  return (
    <div
      className="session-thinking-bubble flex w-full min-w-0 flex-col rounded-lg border border-border bg-[#161616] p-4"
      style={{ borderLeft: `3px solid ${color}` }}
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
      {subtitle && (
        <p className="mt-1 text-xs text-text-secondary">{subtitle}</p>
      )}
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
  const [grokR1, setGrokR1] = useState("");
  const [claudeR1, setClaudeR1] = useState("");
  const [geminiR1Complete, setGeminiR1Complete] = useState(false);
  const [gptR1Complete, setGptR1Complete] = useState(false);
  const [grokR1Complete, setGrokR1Complete] = useState(false);
  const [claudeR1Complete, setClaudeR1Complete] = useState(false);
  /** Smart-tier advisor pass — shown under model bubbles until advisor_complete */
  const [geminiAdvisorReviewing, setGeminiAdvisorReviewing] = useState(false);
  const [gptAdvisorReviewing, setGptAdvisorReviewing] = useState(false);
  const [grokAdvisorReviewing, setGrokAdvisorReviewing] = useState(false);

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

  // ── Synthesis annotations — shown in Session notes panel ────────────────
  const [annotations, setAnnotations] = useState([]);
  const [annotationsOpen, setAnnotationsOpen] = useState(false);

  // ── Pipeline stage collapse/expand state ──────────────────────────────────
  // Stages auto-collapse when complete, synthesis auto-expands.
  // After auto-transition, user can toggle freely.
  const [researchOpen, setResearchOpen] = useState(true);
  const [factcheckOpen, setFactcheckOpen] = useState(true);
  const [synthesisOpen, setSynthesisOpen] = useState(false);
  // Individual model sub-panel expand state inside RESEARCH (all open by default)
  const [modelOpen, setModelOpen] = useState({ claude: true, gemini: true, gpt: true, grok: true });

  const researchAutoCollapsedRef = useRef(false);
  const factcheckAutoCollapsedRef = useRef(false);
  const synthesisAutoExpandedRef = useRef(false);

  const r1CountsRef = useRef({ Gemini: 0, GPT: 0, Grok: 0, Claude: 0 });

  const phaseRef = useRef(/** @type {StreamPhase} */ ("idle"));

  /** Bumps re-render when handlers only update `phaseRef` (streaming flags). */
  const [, setStreamPhaseMarker] = useState(0);

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
      grokR1,
      claudeR1,
      perplexityContent,
      synthesisText
    );
  }, [
    resumeTranscript,
    sessionConfig,
    displayPrompt,
    geminiR1,
    gptR1,
    grokR1,
    claudeR1,
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
      if (sender === "Grok") {
        r1CountsRef.current.Grok += token.length;
        setGrokR1((prev) => prev + token);
        return;
      }
      if (sender === "Claude") {
        r1CountsRef.current.Claude += token.length;
        setClaudeR1((prev) => prev + token);
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

  const handleModelComplete = useCallback((sender) => {
    if (sender === "Gemini") { setGeminiR1Complete(true); return; }
    if (sender === "GPT")    { setGptR1Complete(true);    return; }
    if (sender === "Grok")   { setGrokR1Complete(true);   return; }
    if (sender === "Claude") { setClaudeR1Complete(true); return; }
  }, []);

  useEffect(() => {
    const msgs = resumeTranscript?.messages;
    if (!msgs?.length || !sessionConfig) return;
    let ge = "";
    let gp = "";
    let grk = "";
    let cla = "";
    let audit = "";
    let syn = "";
    for (const m of msgs) {
      if (m.role !== "assistant") continue;
      const r = m.round;
      const s = m.sender;
      if (r === "round1") {
        if (s === "Gemini") ge  = m.content ?? "";
        if (s === "GPT")    gp  = m.content ?? "";
        if (s === "Grok")   grk = m.content ?? "";
        if (s === "Claude") cla = m.content ?? "";
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
    setGrokR1(grk);
    setClaudeR1(cla);
    setGeminiR1Complete(true);
    setGptR1Complete(true);
    setGrokR1Complete(true);
    setClaudeR1Complete(true);
    setGeminiAdvisorReviewing(false);
    setGptAdvisorReviewing(false);
    setGrokAdvisorReviewing(false);
    setSessionStarted(true);
    setPerplexityPhase(audit.trim() ? "content" : "off");
    setPerplexityContent(audit);
    setSynthesisThinking(false);
    setSynthesisText(syn);
    setSynthesisStreaming(false);
    setSynthesisFinal(!!String(syn).trim());
    setSessionComplete(true);
    phaseRef.current = "idle";
    r1CountsRef.current = { Gemini: ge.length, GPT: gp.length, Grok: grk.length, Claude: cla.length };
    // Resume: all stages complete — research/factcheck collapsed, synthesis expanded
    setResearchOpen(false);
    setFactcheckOpen(false);
    setSynthesisOpen(true);
    researchAutoCollapsedRef.current = true;
    factcheckAutoCollapsedRef.current = true;
    synthesisAutoExpandedRef.current = true;
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
    r1CountsRef.current = { Gemini: 0, GPT: 0, Grok: 0, Claude: 0 };
    setConfigError(null);
    setTransportError(null);
    setStreamError(null);
    setGeminiR1("");
    setGptR1("");
    setGrokR1("");
    setClaudeR1("");
    setGeminiR1Complete(false);
    setGptR1Complete(false);
    setGrokR1Complete(false);
    setClaudeR1Complete(false);
    setGeminiAdvisorReviewing(false);
    setGptAdvisorReviewing(false);
    setGrokAdvisorReviewing(false);
    setSessionStarted(false);
    setPerplexityPhase("off");
    setPerplexityContent("");
    setSynthesisThinking(false);
    setSynthesisText("");
    setSynthesisStreaming(false);
    setSynthesisFinal(false);
    setSessionComplete(false);
    setAnnotations([]);
    setAnnotationsOpen(false);
    setResearchOpen(true);
    setFactcheckOpen(true);
    setSynthesisOpen(false);
    setModelOpen({ claude: true, gemini: true, gpt: true, grok: true });
    researchAutoCollapsedRef.current = false;
    factcheckAutoCollapsedRef.current = false;
    synthesisAutoExpandedRef.current = false;

    const url = wsUrlFromApiBase();

    // Mutable tracking for reconnect loop — plain objects, not React state,
    // so reconnect retries don't re-trigger this effect.
    const wsHolder        = { current: /** @type {WebSocket|null} */ (null) };
    let reconnectCount    = 0;
    let pingIntervalId    = 0;
    let reconnectTimeoutId = 0;

    function connectWs() {
      if (cancelled) return;

      const ws = new WebSocket(url);
      wsHolder.current = ws;

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
          case "advisor_thinking": {
            const advSender = data.sender;
            if (advSender === "Gemini") setGeminiAdvisorReviewing(true);
            if (advSender === "GPT")    setGptAdvisorReviewing(true);
            if (advSender === "Grok")   setGrokAdvisorReviewing(true);
            break;
          }
          case "advisor_complete": {
            const advDone = data.sender;
            if (advDone === "Gemini") setGeminiAdvisorReviewing(false);
            if (advDone === "GPT")    setGptAdvisorReviewing(false);
            if (advDone === "Grok")   setGrokAdvisorReviewing(false);
            break;
          }
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
          case "synthesis_annotations":
            setAnnotations(data.annotations || []);
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
        // Clear the "Reconnecting…" banner if this is a successful retry.
        if (reconnectCount > 0) setTransportError(null);
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
        if (pingIntervalId) { window.clearInterval(pingIntervalId); pingIntervalId = 0; }
        if (cancelled || completedNormallyRef.current) return;

        if (!openedRef.current) {
          // Never connected — don't retry, just report.
          setTransportError((prev) => prev || "WebSocket connection failed.");
          return;
        }

        // Session was open and dropped mid-stream — attempt reconnect.
        if (reconnectCount < WS_RECONNECT_MAX) {
          reconnectCount += 1;
          const delay = Math.pow(2, reconnectCount - 1) * 1000; // 1s → 2s → 4s
          setTransportError(`Reconnecting… (attempt ${reconnectCount} of ${WS_RECONNECT_MAX})`);
          reconnectTimeoutId = window.setTimeout(connectWs, delay);
        } else {
          setTransportError("Session disconnected — responses may be incomplete.");
        }
      };
    }

    connectWs();

    return () => {
      cancelled = true;
      window.clearTimeout(reconnectTimeoutId);
      if (pingIntervalId) window.clearInterval(pingIntervalId);
      const ws = wsHolder.current;
      if (ws) {
        ws.onmessage = null;
        ws.onclose   = null;
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
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

  const breadcrumbState = useMemo(() => {
    // PROMPT — done as soon as session starts (or resume)
    const promptDone = isResume || sessionStarted;

    // RESEARCH — active during round1_parallel, done when perplexity starts or synthesis entered
    const transcriptDone = isResume || perplexityPhase !== "off" || synthesisPhaseEntered;
    const transcriptActive = sessionStarted && !transcriptDone;

    // FACT-CHECK — active during perplexity thinking, done when content received
    const factDone = isResume || perplexityPhase === "content" || (synthesisPhaseEntered && perplexityPhase !== "thinking");
    const factActive = perplexityPhase === "thinking";

    // SYNTHESIS — active during observations + synthesis thinking/streaming, done when final
    const sDone = isResume || synthesisFinal;
    const sActive = synthesisPhaseEntered && !synthesisFinal;
    const sLabel = synthesisThinking || synthesisStreaming ? "SYNTHESIZING..." : "SYNTHESIS";

    return { promptDone, transcriptDone, transcriptActive, factDone, factActive, sDone, sActive, sLabel };
  }, [isResume, sessionStarted, synthesisPhaseEntered, perplexityPhase, synthesisThinking, synthesisStreaming, synthesisFinal]);

  // ── Pipeline stage done flags ─────────────────────────────────────────────
  const researchStageDone = isResume || perplexityPhase !== "off" || synthesisPhaseEntered;
  const factcheckStageDone = isResume || perplexityPhase === "content" ||
    (synthesisPhaseEntered && perplexityPhase !== "thinking");
  const synthesisStageDone = isResume || synthesisFinal;

  // Auto-collapse research when complete (fires once on transition)
  useEffect(() => {
    if (researchStageDone && !researchAutoCollapsedRef.current) {
      researchAutoCollapsedRef.current = true;
      setResearchOpen(false);
    }
  }, [researchStageDone]);

  // Auto-collapse factcheck when complete (fires once on transition)
  useEffect(() => {
    if (factcheckStageDone && !factcheckAutoCollapsedRef.current) {
      factcheckAutoCollapsedRef.current = true;
      setFactcheckOpen(false);
    }
  }, [factcheckStageDone]);

  // Auto-expand synthesis when complete (fires once on transition)
  useEffect(() => {
    if (synthesisStageDone && !synthesisAutoExpandedRef.current) {
      synthesisAutoExpandedRef.current = true;
      setSynthesisOpen(true);
    }
  }, [synthesisStageDone]);

  const showTranscriptRoundtable = isResume || sessionStarted;

  const showGeminiThinking =
    transcriptLive && !configError && promptOk && sessionStarted && !geminiR1Complete && !String(geminiR1).trim();
  const showGptThinking =
    transcriptLive && !configError && promptOk && sessionStarted && !gptR1Complete && !String(gptR1).trim();
  const showGrokThinking =
    transcriptLive && !configError && promptOk && sessionStarted && !grokR1Complete && !String(grokR1).trim();
  const showClaudeR1Thinking =
    transcriptLive && !configError && promptOk && sessionStarted && !claudeR1Complete && !String(claudeR1).trim();

  const geminiR1Streaming  = sessionStarted && !geminiR1Complete  && Boolean(String(geminiR1).length);
  const gptR1Streaming     = sessionStarted && !gptR1Complete     && Boolean(String(gptR1).length);
  const grokR1Streaming    = sessionStarted && !grokR1Complete    && Boolean(String(grokR1).length);
  const claudeR1Streaming  = sessionStarted && !claudeR1Complete  && Boolean(String(claudeR1).length);

  /** Multi-column grid — only when seat has thinking, text, or finished bubble (skip notices don't count). */
  const geminiRoundActive =
    showGeminiThinking ||
    geminiR1Streaming ||
    (Boolean(String(geminiR1 || "").trim()) && !isSkipNotice(geminiR1)) ||
    (geminiR1Complete && !isSkipNotice(geminiR1));
  const gptRoundActive =
    showGptThinking ||
    gptR1Streaming ||
    (Boolean(String(gptR1 || "").trim()) && !isSkipNotice(gptR1)) ||
    (gptR1Complete && !isSkipNotice(gptR1));
  const grokRoundActive =
    showGrokThinking ||
    grokR1Streaming ||
    (Boolean(String(grokR1 || "").trim()) && !isSkipNotice(grokR1)) ||
    (grokR1Complete && !isSkipNotice(grokR1));
  const claudeR1RoundActive =
    showClaudeR1Thinking ||
    claudeR1Streaming ||
    (Boolean(String(claudeR1 || "").trim()) && !isSkipNotice(claudeR1)) ||
    (claudeR1Complete && !isSkipNotice(claudeR1));

  const round1GridClass = "flex flex-col gap-4";

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

      <Header onHome={requestHome} onSaveExit={requestSaveExit}>
        {/* Tier + breadcrumb line */}
        <div
          className="mx-auto flex max-w-3xl items-center justify-center gap-1 px-4 pb-2 pt-0.5 text-[11px] sm:px-6"
          style={{ color: "#666666" }}
        >
          <span className="font-semibold uppercase tracking-wide" style={{ color: "#F5A623" }}>
            {"<"} {formatTierBadge(sessionConfig?.tier)} {">"}
          </span>
          <span className="mx-1.5" style={{ color: "#F5A623" }}>·</span>
          <span style={{ color: breadcrumbState.promptDone ? "#F5A623" : "#666666" }}>
            {breadcrumbState.promptDone ? "✓" : "○"} PROMPT
          </span>
          <span className="mx-1" style={{ color: "#F5A623" }}>→</span>
          <span
            className={breadcrumbState.transcriptActive ? "animate-pulse" : ""}
            style={{ color: breadcrumbState.transcriptDone || breadcrumbState.transcriptActive ? "#F5A623" : "#666666" }}
          >
            {breadcrumbState.transcriptDone ? "✓" : breadcrumbState.transcriptActive ? "●" : "○"} RESEARCH
          </span>
          <span className="mx-1" style={{ color: "#F5A623" }}>→</span>
          <span
            className={breadcrumbState.factActive ? "animate-pulse" : ""}
            style={{ color: breadcrumbState.factDone || breadcrumbState.factActive ? "#F5A623" : "#666666" }}
          >
            {breadcrumbState.factDone ? "✓" : breadcrumbState.factActive ? "●" : "○"} FACT-CHECK
          </span>
          <span className="mx-1" style={{ color: "#F5A623" }}>→</span>
          <span
            className={breadcrumbState.sActive ? "animate-pulse" : ""}
            style={{ color: breadcrumbState.sDone || breadcrumbState.sActive ? "#F5A623" : "#666666" }}
          >
            {breadcrumbState.sDone ? "✓" : breadcrumbState.sActive ? "●" : "○"} {breadcrumbState.sLabel}
          </span>
        </div>
      </Header>

      <div className="mx-auto max-w-3xl space-y-4 px-4 py-6 sm:px-6">
        {configError && (
          <p className="text-sm text-red-400" role="alert">
            {configError}
          </p>
        )}

        {/* ── PROMPT — fixed, always visible ── */}
        <section aria-label="Session prompt">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Prompt
          </h2>
          <div className="bubble-scroll max-h-[200px] rounded-lg border border-border bg-surface px-4 py-3 text-sm leading-relaxed text-text-primary whitespace-pre-wrap">
            {displayPrompt || "—"}
          </div>
        </section>

        {/* ── SYNTHESIS — shown when phase entered; sits immediately below PROMPT ── */}
        {synthesisPhaseEntered && (
          <section aria-label="Synthesis" className="space-y-3">
            <StageHeader
              label={breadcrumbState.sLabel}
              summary={null}
              done={synthesisStageDone}
              open={synthesisOpen}
              onToggle={() => setSynthesisOpen((o) => !o)}
              active={!synthesisStageDone}
            />
            {/* Content: show when active OR when done+open */}
            {(!synthesisStageDone || synthesisOpen) && (
              <div className="space-y-4">
                {synthesisThinking && !synthesisFinal && !String(synthesisText).trim() && (
                  <ThinkingDotsBubble
                    label="🟠 CLAUDE"
                    color={MODEL_HEX.Claude}
                    subtitle="Synthesizing your roundtable..."
                  />
                )}
                {(synthesisStreaming || synthesisFinal || synthesisText.length > 0) && (
                  <SynthesisPanel
                    content={synthesisBody}
                    isStreaming={synthesisStreaming && !synthesisFinal}
                    complete={synthesisFinal}
                  />
                )}
                {/* Session notes — only when there are noteworthy annotations */}
                {sessionComplete && annotations.length > 0 && (
                  <div className="rounded-lg border border-border bg-[#161616]" style={{ borderLeft: "3px solid #2a2a2a" }}>
                    <button
                      type="button"
                      onClick={() => setAnnotationsOpen((o) => !o)}
                      className="flex w-full items-center gap-2 px-4 py-3 text-left text-xs text-text-secondary transition-colors hover:text-text-primary focus:outline-none"
                      aria-expanded={annotationsOpen}
                    >
                      <span aria-hidden style={{ display: "inline-block", transform: annotationsOpen ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform 0.15s" }}>▾</span>
                      Session notes
                    </button>
                    {annotationsOpen && (
                      <ul className="space-y-1.5 px-4 pb-4 pt-1">
                        {annotations.map((a, i) => (
                          <li key={i} className="flex gap-2 text-xs leading-relaxed text-text-secondary">
                            <span className="shrink-0 text-[#444444]">·</span>
                            <span>{a}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* ── FACT-CHECK — shown when Perplexity started ── */}
        {perplexityPhase !== "off" && (
          <section aria-label="Fact-check" className="space-y-3">
            <StageHeader
              label="FACT-CHECK"
              summary="Perplexity · audit complete"
              done={factcheckStageDone}
              open={factcheckOpen}
              onToggle={() => setFactcheckOpen((o) => !o)}
              active={perplexityPhase === "thinking"}
            />
            {/* Content: show when active OR when done+open */}
            {(!factcheckStageDone || factcheckOpen) && (
              <div className="space-y-2">
                {perplexityPhase === "thinking" && (
                  <ThinkingDotsBubble label="🔎 PERPLEXITY" color={MODEL_HEX.Perplexity} />
                )}
                {perplexityPhase === "content" && String(perplexityContent).trim() && (
                  <ModelBubble
                    sender="Perplexity"
                    content={perplexityContent}
                    isStreaming={false}
                    round="audit"
                    complete
                    titleOverride="🔎 PERPLEXITY"
                  />
                )}
              </div>
            )}
          </section>
        )}

        {/* ── RESEARCH — shown when session started; collapses when fact-check begins ── */}
        {showTranscriptRoundtable && (
          <section aria-label="Research" className="space-y-3">
            <StageHeader
              label="RESEARCH"
              summary="Claude · Gemini · GPT · Grok"
              done={researchStageDone}
              open={researchOpen}
              onToggle={() => setResearchOpen((o) => !o)}
              active={!researchStageDone}
            />
            {/* Content: show when active OR when done+open */}
            {(!researchStageDone || researchOpen) && (
              <div className="space-y-4">
                {/* Alphabetical order: Claude, Gemini, GPT, Grok */}

                {/* Claude */}
                {claudeR1RoundActive && (
                  <div className="min-w-0">
                    {researchStageDone && (
                      <button
                        type="button"
                        onClick={() => setModelOpen((s) => ({ ...s, claude: !s.claude }))}
                        className="mb-1 flex items-center gap-1 text-xs text-[#555555] hover:text-text-secondary focus:outline-none"
                      >
                        <span aria-hidden style={{ display: "inline-block", transform: modelOpen.claude ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform 0.15s" }}>▾</span>
                        Claude
                      </button>
                    )}
                    {(!researchStageDone || modelOpen.claude) && (
                      <div className="space-y-1">
                        {showClaudeR1Thinking ? (
                          <ThinkingDotsBubble label="🟠 CLAUDE" color={MODEL_HEX.Claude} />
                        ) : claudeR1Complete && isSkipNotice(claudeR1) ? (
                          <p className="text-xs text-[#888888]" role="status">Claude is unavailable right now — skipped this round.</p>
                        ) : (
                          <ModelBubble
                            sender="Claude"
                            titleOverride="🟠 CLAUDE"
                            content={bubbleBody(claudeR1, claudeR1Complete)}
                            isStreaming={claudeR1Streaming}
                            round="round1"
                            complete={claudeR1Complete}
                          />
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Gemini */}
                {geminiRoundActive && (
                  <div className="min-w-0">
                    {researchStageDone && (
                      <button
                        type="button"
                        onClick={() => setModelOpen((s) => ({ ...s, gemini: !s.gemini }))}
                        className="mb-1 flex items-center gap-1 text-xs text-[#555555] hover:text-text-secondary focus:outline-none"
                      >
                        <span aria-hidden style={{ display: "inline-block", transform: modelOpen.gemini ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform 0.15s" }}>▾</span>
                        Gemini
                      </button>
                    )}
                    {(!researchStageDone || modelOpen.gemini) && (
                      <div className="space-y-1">
                        {showGeminiThinking ? (
                          <ThinkingDotsBubble label="🔵 GEMINI" color={MODEL_HEX.Gemini} />
                        ) : geminiR1Complete && isSkipNotice(geminiR1) ? (
                          <p className="text-xs text-[#888888]" role="status">Gemini is unavailable right now — skipped this round.</p>
                        ) : (
                          <>
                            <ModelBubble
                              sender="Gemini"
                              titleOverride="🔵 GEMINI"
                              content={bubbleBody(geminiR1, geminiR1Complete)}
                              isStreaming={geminiR1Streaming}
                              round="round1"
                              complete={geminiR1Complete}
                            />
                            {geminiAdvisorReviewing && (
                              <p className="text-xs text-[#888888]" role="status" aria-live="polite">⚖ advisor reviewing...</p>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* GPT */}
                {gptRoundActive && (
                  <div className="min-w-0">
                    {researchStageDone && (
                      <button
                        type="button"
                        onClick={() => setModelOpen((s) => ({ ...s, gpt: !s.gpt }))}
                        className="mb-1 flex items-center gap-1 text-xs text-[#555555] hover:text-text-secondary focus:outline-none"
                      >
                        <span aria-hidden style={{ display: "inline-block", transform: modelOpen.gpt ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform 0.15s" }}>▾</span>
                        GPT
                      </button>
                    )}
                    {(!researchStageDone || modelOpen.gpt) && (
                      <div className="space-y-1">
                        {showGptThinking ? (
                          <ThinkingDotsBubble label="🟢 GPT" color={MODEL_HEX.GPT} />
                        ) : gptR1Complete && isSkipNotice(gptR1) ? (
                          <p className="text-xs text-[#888888]" role="status">GPT is unavailable right now — skipped this round.</p>
                        ) : (
                          <>
                            <ModelBubble
                              sender="GPT"
                              titleOverride="🟢 GPT"
                              content={bubbleBody(gptR1, gptR1Complete)}
                              isStreaming={gptR1Streaming}
                              round="round1"
                              complete={gptR1Complete}
                            />
                            {gptAdvisorReviewing && (
                              <p className="text-xs text-[#888888]" role="status" aria-live="polite">⚖ advisor reviewing...</p>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Grok */}
                {grokRoundActive && (
                  <div className="min-w-0">
                    {researchStageDone && (
                      <button
                        type="button"
                        onClick={() => setModelOpen((s) => ({ ...s, grok: !s.grok }))}
                        className="mb-1 flex items-center gap-1 text-xs text-[#555555] hover:text-text-secondary focus:outline-none"
                      >
                        <span aria-hidden style={{ display: "inline-block", transform: modelOpen.grok ? "rotate(0deg)" : "rotate(-90deg)", transition: "transform 0.15s" }}>▾</span>
                        Grok
                      </button>
                    )}
                    {(!researchStageDone || modelOpen.grok) && (
                      <div className="space-y-1">
                        {showGrokThinking ? (
                          <ThinkingDotsBubble label={<><span style={{ fontSize: "1.15em", lineHeight: 1, verticalAlign: "middle" }}>●</span>{" GROK"}</>} color={MODEL_HEX.Grok} />
                        ) : grokR1Complete && isSkipNotice(grokR1) ? (
                          <p className="text-xs text-[#888888]" role="status">Grok is unavailable right now — skipped this round.</p>
                        ) : (
                          <>
                            <ModelBubble
                              sender="Grok"
                              titleOverride={<><span style={{ fontSize: "1.15em", lineHeight: 1, verticalAlign: "middle" }}>●</span>{" GROK"}</>}
                              content={bubbleBody(grokR1, grokR1Complete)}
                              isStreaming={grokR1Streaming}
                              round="round1"
                              complete={grokR1Complete}
                            />
                            {grokAdvisorReviewing && (
                              <p className="text-xs text-[#888888]" role="status" aria-live="polite">⚖ advisor reviewing...</p>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {/* Alerts */}
        {inlineAlert && (
          <p
            className="max-w-[min(100%,40rem)] rounded-lg border border-red-900/50 bg-surface px-4 py-3 text-sm text-red-400"
            role="alert"
          >
            {inlineAlert}
          </p>
        )}

        {sessionComplete && (
          <TakeFurther sessionConfig={sessionConfig} transcript={transcriptForExport} />
        )}
      </div>
    </div>
  );
}

export default SessionView;
