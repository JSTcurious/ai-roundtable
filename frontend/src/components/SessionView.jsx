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
const DEFAULT_HTTP = "http://localhost:8000";
const API_BASE = process.env.REACT_APP_API_URL || DEFAULT_HTTP;

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
 * Build the display string for a model bubble header, incorporating model
 * transparency metadata received from the backend.
 *
 * @param {string} _lab        — "claude" | "gemini" | "gpt" | "grok"
 * @param {string} emoji       — emoji prefix, e.g. "🟠"
 * @param {string} name        — display name, e.g. "CLAUDE"
 * @param {Object|undefined} meta — modelMeta entry for this lab
 * @param {string|undefined} [tier] — session tier from sessionConfig
 * @returns {string}
 */
function buildModelHeader(_lab, emoji, name, meta, tier) {
  if (!meta || !meta.model_used) return `${emoji} ${name}`;
  const execId = meta.model_used;
  const advisorId = meta.advisor_model || "";
  const metaTier = meta.tier || tier || "smart";
  const avail = meta.availability || "primary";

  // Strip any vendor prefix (e.g. "anthropic/claude-sonnet-4-6" → "claude-sonnet-4-6")
  const shortExec   = execId.split("/").pop();
  const shortAdvisor = advisorId.split("/").pop();

  let header = `${emoji} ${name} · ${shortExec}`;
  if (metaTier === "smart" && shortAdvisor && shortAdvisor !== shortExec) {
    header += ` → ${shortAdvisor}`;
  }
  header += ` · ${metaTier.charAt(0).toUpperCase() + metaTier.slice(1)}`;
  if (avail !== "primary") {
    header += " ⚠ Fallback";
  }
  return header;
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

  // ── Perplexity citations — shown below FINAL ANSWER ─────────────────────
  const [citations, setCitations] = useState([]);

  // ── Philosophy B: YOUR TAKE HITL step ────────────────────────────────────
  /** True after fact-check completes — YOUR TAKE step is visible */
  const [awaitingUserTake, setAwaitingUserTake] = useState(false);
  /** User's optional perspective text */
  const [userTake, setUserTake] = useState("");
  /** True after user clicks Synthesize — input becomes read-only */
  const [synthesisRequested, setSynthesisRequested] = useState(false);

  // ── Model transparency — metadata received with model_complete ───────────
  /** { claude: {model_used, advisor_model, tier, availability}, gemini: {...}, ... } */
  const [modelMeta, setModelMeta] = useState({});

  // ── Live WS ref — used by Synthesize button to send submit_user_take ─────
  const wsRef = useRef(/** @type {WebSocket|null} */ (null));

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
    setCitations([]);
    // Resume: all stages complete
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
    setCitations([]);
    setAwaitingUserTake(false);
    setUserTake("");
    setSynthesisRequested(false);
    setModelMeta({});

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
      wsRef.current = ws;

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
            if (data.model_used) {
              setModelMeta((prev) => ({
                ...prev,
                [data.sender.toLowerCase()]: {
                  model_used:    data.model_used    || "",
                  advisor_model: data.advisor_model || "",
                  tier:          data.tier          || "",
                  availability:  data.availability  || "primary",
                },
              }));
            }
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
            setCitations(data.citations || []);
            setPerplexityPhase("content");
            break;
          case "awaiting_user_take":
            setAwaitingUserTake(true);
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
      wsRef.current = null;
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

  const downloadSessionMarkdown = useCallback(async () => {
    if (!transcriptForExport || !sessionConfig) return;
    try {
      const res = await fetch(`${API_BASE}/api/export/markdown`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: "full", transcript: transcriptForExport, session_config: sessionConfig }),
      });
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ai-roundtable-${new Date().toISOString().slice(0, 10)}.md`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch { /* navigate home regardless */ }
  }, [transcriptForExport, sessionConfig]);

  const downloadFinalAnswerTxt = useCallback(() => {
    if (!synthesisText) return;
    const ts = new Date().toISOString().slice(0, 16).replace("T", "-").replace(":", "");
    const blob = new Blob([synthesisText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `final-answer-${ts}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [synthesisText]);

  const handleSynthesize = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    setSynthesisRequested(true);
    setAwaitingUserTake(false);
    ws.send(JSON.stringify({ type: "submit_user_take", user_take: userTake }));
  }, [userTake]);

  const requestHome = useCallback(() => {
    if (!onNavigateHome) return;
    if (sessionSettled) onNavigateHome();
    else setLeaveIntent("home");
  }, [onNavigateHome, sessionSettled]);

  const requestSaveExit = useCallback(async () => {
    if (!onNavigateHome) return;
    if (sessionSettled) {
      await downloadSessionMarkdown();
      onNavigateHome();
    } else {
      setLeaveIntent("save-exit");
    }
  }, [onNavigateHome, sessionSettled, downloadSessionMarkdown]);

  const confirmLeave = useCallback(async () => {
    const intent = leaveIntent;
    setLeaveIntent(null);
    if (!onNavigateHome) return;
    if (intent === "save-exit") {
      await downloadSessionMarkdown();
    }
    onNavigateHome();
  }, [leaveIntent, onNavigateHome, downloadSessionMarkdown]);

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

    // YOUR TAKE — active when awaiting user input, done when user clicks Synthesize
    const yourTakeDone = isResume || synthesisRequested || synthesisFinal;
    const yourTakeActive = awaitingUserTake && !synthesisRequested;

    // SYNTHESIS — active during synthesis thinking/streaming, done when final
    const sDone = isResume || synthesisFinal;
    const sActive = synthesisPhaseEntered && !synthesisFinal;
    const sLabel = synthesisThinking || synthesisStreaming ? "SYNTHESIZING..." : "FINAL ANSWER";

    return { promptDone, transcriptDone, transcriptActive, factDone, factActive, yourTakeDone, yourTakeActive, sDone, sActive, sLabel };
  }, [isResume, sessionStarted, synthesisPhaseEntered, perplexityPhase, synthesisThinking, synthesisStreaming, synthesisFinal, awaitingUserTake, synthesisRequested]);

  // ── Pipeline stage done flags ─────────────────────────────────────────────
  const researchStageDone = isResume || perplexityPhase !== "off" || synthesisPhaseEntered;
  const factcheckStageDone = isResume || perplexityPhase === "content" ||
    (synthesisPhaseEntered && perplexityPhase !== "thinking");
  const synthesisStageDone = isResume || synthesisFinal;

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
              {leaveIntent === "save-exit" ? "Save session and exit?" : "Leave session?"}
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">
              {leaveIntent === "save-exit"
                ? "Session in progress — your responses will be lost unless you save. Download a full session .md file and go home?"
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
            className={breadcrumbState.yourTakeActive ? "animate-pulse" : ""}
            style={{ color: breadcrumbState.yourTakeDone || breadcrumbState.yourTakeActive ? "#F5A623" : "#666666" }}
          >
            {breadcrumbState.yourTakeDone ? "✓" : breadcrumbState.yourTakeActive ? "●" : "○"} YOUR TAKE
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
            Optimized Prompt
          </h2>
          <div className="bubble-scroll max-h-[6rem] overflow-y-auto rounded-lg border border-border bg-surface px-4 py-3 text-sm leading-relaxed text-text-primary whitespace-pre-wrap">
            {displayPrompt || "—"}
          </div>
        </section>

        {/* ── RESEARCH — shown when session started ── */}
        {showTranscriptRoundtable && (
          <section aria-label="Research" className="space-y-3">
            <h2 className={`text-xs font-semibold uppercase tracking-wide text-text-secondary${!researchStageDone ? " animate-pulse" : ""}`}>
              Research
            </h2>
            {/* Alphabetical order: Claude, Gemini, GPT, Grok */}
            <div className="space-y-4">

              {/* Claude */}
              {claudeR1RoundActive && (
                <div className="min-w-0 space-y-1">
                  {showClaudeR1Thinking ? (
                    <ThinkingDotsBubble label="🟠 CLAUDE" color={MODEL_HEX.Claude} />
                  ) : claudeR1Complete && isSkipNotice(claudeR1) ? (
                    <p className="text-xs text-[#888888]" role="status">Claude is unavailable right now — skipped this round.</p>
                  ) : (
                    <ModelBubble
                      sender="Claude"
                      titleOverride={buildModelHeader("claude", "🟠", "CLAUDE", modelMeta.claude, sessionConfig?.tier)}
                      content={bubbleBody(claudeR1, claudeR1Complete)}
                      isStreaming={claudeR1Streaming}
                      round="round1"
                      complete={claudeR1Complete}
                      contentMaxHeight="200px"
                    />
                  )}
                </div>
              )}

              {/* Gemini */}
              {geminiRoundActive && (
                <div className="min-w-0 space-y-1">
                  {showGeminiThinking ? (
                    <ThinkingDotsBubble label="🔵 GEMINI" color={MODEL_HEX.Gemini} />
                  ) : geminiR1Complete && isSkipNotice(geminiR1) ? (
                    <p className="text-xs text-[#888888]" role="status">Gemini is unavailable right now — skipped this round.</p>
                  ) : (
                    <>
                      <ModelBubble
                        sender="Gemini"
                        titleOverride={buildModelHeader("gemini", "🔵", "GEMINI", modelMeta.gemini, sessionConfig?.tier)}
                        content={bubbleBody(geminiR1, geminiR1Complete)}
                        isStreaming={geminiR1Streaming}
                        round="round1"
                        complete={geminiR1Complete}
                        contentMaxHeight="200px"
                      />
                      {geminiAdvisorReviewing && (
                        <p className="text-xs text-[#888888]" role="status" aria-live="polite">⚖ advisor reviewing...</p>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* GPT */}
              {gptRoundActive && (
                <div className="min-w-0 space-y-1">
                  {showGptThinking ? (
                    <ThinkingDotsBubble label="🟢 GPT" color={MODEL_HEX.GPT} />
                  ) : gptR1Complete && isSkipNotice(gptR1) ? (
                    <p className="text-xs text-[#888888]" role="status">GPT is unavailable right now — skipped this round.</p>
                  ) : (
                    <>
                      <ModelBubble
                        sender="GPT"
                        titleOverride={buildModelHeader("gpt", "🟢", "GPT", modelMeta.gpt, sessionConfig?.tier)}
                        content={bubbleBody(gptR1, gptR1Complete)}
                        isStreaming={gptR1Streaming}
                        round="round1"
                        complete={gptR1Complete}
                        contentMaxHeight="200px"
                      />
                      {gptAdvisorReviewing && (
                        <p className="text-xs text-[#888888]" role="status" aria-live="polite">⚖ advisor reviewing...</p>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Grok */}
              {grokRoundActive && (
                <div className="min-w-0 space-y-1">
                  {showGrokThinking ? (
                    <ThinkingDotsBubble label="● GROK" color={MODEL_HEX.Grok} />
                  ) : grokR1Complete && isSkipNotice(grokR1) ? (
                    <p className="text-xs text-[#888888]" role="status">Grok is unavailable right now — skipped this round.</p>
                  ) : (
                    <>
                      <ModelBubble
                        sender="Grok"
                        titleOverride={buildModelHeader("grok", "●", "GROK", modelMeta.grok, sessionConfig?.tier)}
                        content={bubbleBody(grokR1, grokR1Complete)}
                        isStreaming={grokR1Streaming}
                        round="round1"
                        complete={grokR1Complete}
                        contentMaxHeight="200px"
                      />
                      {grokAdvisorReviewing && (
                        <p className="text-xs text-[#888888]" role="status" aria-live="polite">⚖ advisor reviewing...</p>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          </section>
        )}

        {/* ── FACT-CHECK — shown when Perplexity started ── */}
        {perplexityPhase !== "off" && (
          <section aria-label="Fact-check" className="space-y-3">
            <h2 className={`text-xs font-semibold uppercase tracking-wide text-text-secondary${perplexityPhase === "thinking" ? " animate-pulse" : ""}`}>
              Fact-Check
            </h2>
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
                  titleOverride="🔎 PERPLEXITY · Sonar Pro"
                  contentMaxHeight="300px"
                />
              )}
            </div>
          </section>
        )}

        {/* ── YOUR TAKE — shown after fact-check completes ── */}
        {awaitingUserTake && (
          <section aria-label="Your take" className="space-y-3">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-text-secondary animate-pulse">
              Your Take
            </h2>
            <div className="rounded-lg border border-border bg-surface px-4 py-4 space-y-3">
              <label htmlFor="user-take-input" className="sr-only">
                Your perspective (optional)
              </label>
              <textarea
                id="user-take-input"
                rows={3}
                value={userTake}
                onChange={(e) => setUserTake(e.target.value)}
                disabled={synthesisRequested}
                placeholder="What's your read on this? Any model you trust more? Anything you want weighted differently? (optional)"
                className="w-full resize-y rounded-md border border-border bg-bg px-3 py-2 text-sm leading-relaxed text-text-primary placeholder:text-text-secondary focus:border-border-focus focus:outline-none disabled:opacity-50"
              />
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleSynthesize}
                  disabled={synthesisRequested}
                  className="rounded-lg px-5 py-2 text-sm font-bold transition-opacity hover:opacity-90 focus:outline-none disabled:opacity-40"
                  style={{ background: "#F5A623", color: "#0d0d0d" }}
                >
                  {synthesisRequested ? "Synthesizing…" : "Synthesize →"}
                </button>
              </div>
            </div>
          </section>
        )}

        {/* ── FINAL ANSWER — shown after user clicks Synthesize ── */}
        {synthesisPhaseEntered && (
          <section aria-label="Final answer" className="space-y-3">
            <div className="flex items-center gap-3">
              <h2 className={`text-xs font-semibold uppercase tracking-wide text-text-secondary${!synthesisStageDone ? " animate-pulse" : ""}`}>
                {breadcrumbState.sLabel}
              </h2>
              {synthesisFinal && (
                <button
                  type="button"
                  onClick={downloadFinalAnswerTxt}
                  className="text-xs text-[#555555] hover:text-text-secondary transition-colors focus:outline-none"
                  aria-label="Save final answer as text file"
                >
                  save
                </button>
              )}
            </div>
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
              {/* Sources — citations from Perplexity fact-check */}
              {sessionComplete && citations.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-semibold uppercase tracking-wide text-text-secondary">Sources</p>
                  <ol className="space-y-1">
                    {citations.map((url, i) => (
                      <li key={i} className="flex gap-2 text-xs text-[#888888]">
                        <span className="shrink-0 text-[#555555]">[{i + 1}]</span>
                        <a
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="break-all hover:text-text-secondary transition-colors"
                        >
                          {url}
                        </a>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
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

      </div>
    </div>
  );
}

export default SessionView;
