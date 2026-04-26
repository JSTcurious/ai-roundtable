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
const DEFAULT_WS   = "ws://localhost:8000";
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
  if (process.env.REACT_APP_WS_URL) {
    return process.env.REACT_APP_WS_URL + "/ws/session";
  }
  const base = process.env.REACT_APP_API_URL || DEFAULT_HTTP;
  try {
    const u = new URL(base);
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    u.pathname = "/ws/session";
    u.search = "";
    u.hash = "";
    return u.toString();
  } catch {
    return DEFAULT_WS + "/ws/session";
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
  const [copiedAnswer, setCopiedAnswer] = useState(false);

  // ── Perplexity citations — shown below FINAL ANSWER ─────────────────────
  const [citations, setCitations] = useState([]);

  // ── Synthesis dialogue loop ──────────────────────────────────────────────
  /** Current synthesis content (draft or final, without closing questions). */
  const [synthesisDraft, setSynthesisDraft] = useState(null);
  /** Revision counter — 0 for initial draft, increments on each refinement. */
  const [synthesisRevision, setSynthesisRevision] = useState(0);
  /** Array of closing-question strings surfaced with the current draft. */
  const [closingQuestions, setClosingQuestions] = useState([]);
  /** User's in-progress dialogue input. */
  const [dialogueInput, setDialogueInput] = useState("");
  /** Append-only dialogue history for display/debugging (optional UI use). */
  const [dialogueHistory, setDialogueHistory] = useState([]);
  /** True while waiting for the backend refinement response. */
  const [refinementPending, setRefinementPending] = useState(false);

  // ── Model transparency — metadata received with model_complete ───────────
  /** { claude: {model_used, advisor_model, tier, availability}, gemini: {...}, ... } */
  const [modelMeta, setModelMeta] = useState({});

  // ── Prompt review gate — shown before research starts ────────────────────
  /** null = no review pending; object = review data from backend */
  const [promptReviewData, setPromptReviewData] = useState(null);
  const [reviewAdjusting, setReviewAdjusting] = useState(false);
  const [reviewAdjustText, setReviewAdjustText] = useState("");

  // ── Live WS ref — used by dialogue buttons to send refinement/finalize ───
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
    setSynthesisDraft(syn || null);
    setSynthesisRevision(0);
    setClosingQuestions([]);
    setDialogueInput("");
    setDialogueHistory([]);
    setRefinementPending(false);
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
    setSynthesisDraft(null);
    setSynthesisRevision(0);
    setClosingQuestions([]);
    setDialogueInput("");
    setDialogueHistory([]);
    setRefinementPending(false);
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
          case "prompt_review":
            setPromptReviewData(data);
            break;
          case "session_started":
            setPromptReviewData(null);
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
          case "synthesis_thinking":
            setSynthesisThinking(true);
            setRefinementPending(true);
            phaseRef.current = "synthesis";
            setStreamPhaseMarker((n) => n + 1);
            break;
          case "synthesis_draft": {
            const content = data.content ?? "";
            setSynthesisDraft(content);
            setSynthesisText(content);
            setSynthesisRevision(Number(data.revision) || 0);
            setClosingQuestions(Array.isArray(data.closing_questions) ? data.closing_questions : []);
            setSynthesisStreaming(false);
            setSynthesisThinking(false);
            setSynthesisFinal(false);
            setRefinementPending(false);
            phaseRef.current = "idle";
            setStreamPhaseMarker((n) => n + 1);
            break;
          }
          case "synthesis_final": {
            const content = data.content ?? "";
            setSynthesisDraft(content);
            setSynthesisText(content);
            setSynthesisRevision(Number(data.revision) || 0);
            setClosingQuestions([]);
            setSynthesisStreaming(false);
            setSynthesisThinking(false);
            setSynthesisFinal(true);
            setRefinementPending(false);
            phaseRef.current = "idle";
            setStreamPhaseMarker((n) => n + 1);
            onSynthesisCompleteRef.current?.(content);
            break;
          }
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

  const copyFinalAnswer = useCallback(() => {
    if (!synthesisText || copiedAnswer) return;
    // Strip confidence tags and markdown before copying to clipboard
    const plain = synthesisText
      .replace(/\[VERIFIED\]|\[LIKELY\]|\[UNCERTAIN\]|\[DEFER\]/g, "")
      .replace(/#{1,6}\s+/gm, "")
      .replace(/\*\*(.+?)\*\*/g, "$1")
      .replace(/\*(.+?)\*/g, "$1")
      .replace(/`(.+?)`/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/^\s*[-*+]\s+/gm, "")
      .replace(/^\s*\d+\.\s+/gm, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    navigator.clipboard.writeText(plain).then(() => {
      setCopiedAnswer(true);
      setTimeout(() => setCopiedAnswer(false), 1500);
    });
  }, [synthesisText, copiedAnswer]);

  const handleRespond = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (refinementPending || synthesisFinal) return;
    const text = dialogueInput.trim();
    if (!text) return;
    ws.send(JSON.stringify({
      type: "user_dialogue_response",
      content: text,
    }));
    setDialogueHistory((prev) => [...prev, { role: "user", content: text }]);
    setDialogueInput("");
    setRefinementPending(true);
  }, [dialogueInput, refinementPending, synthesisFinal]);

  const handleReviewConfirm = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "prompt_confirmed" }));
  }, []);

  const handleReviewAdjust = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const text = reviewAdjustText.trim();
    if (!text) return;
    ws.send(JSON.stringify({ type: "prompt_adjusted", adjustment: text }));
    setReviewAdjusting(false);
    setReviewAdjustText("");
  }, [reviewAdjustText]);

  const handleFinalize = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (synthesisFinal) return;
    ws.send(JSON.stringify({ type: "finalize_synthesis" }));
    setSynthesisFinal(true);
  }, [synthesisFinal]);

  const requestHome = useCallback(() => {
    if (!onNavigateHome) return;
    if (sessionSettled) onNavigateHome();
    else setLeaveIntent("home");
  }, [onNavigateHome, sessionSettled]);

  const requestSaveExit = useCallback(async () => {
    if (!onNavigateHome) return;
    if (sessionSettled) {
      await downloadSessionMarkdown();
      // Stay on page — user keeps their session visible after saving
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
      // Stay on page — download without navigating away
      return;
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
      synthesisFinal ||
      Boolean(synthesisDraft) ||
      Boolean(String(synthesisText || "").trim())
    );
  }, [synthesisThinking, synthesisFinal, synthesisDraft, synthesisText]);

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
    const promptDone = isResume || sessionStarted || Boolean(promptReviewData);

    // REVIEW — active while waiting for user confirmation; done when session_started
    const reviewDone = isResume || sessionStarted;
    const reviewActive = Boolean(promptReviewData) && !sessionStarted;

    // RESEARCH — active during round1_parallel, done when perplexity starts or synthesis entered
    const transcriptDone = isResume || perplexityPhase !== "off" || synthesisPhaseEntered;
    const transcriptActive = sessionStarted && !transcriptDone;

    // FACT-CHECK — active during perplexity thinking, done when content received
    const factDone = isResume || perplexityPhase === "content" || (synthesisPhaseEntered && perplexityPhase !== "thinking");
    const factActive = perplexityPhase === "thinking";

    // DIALOGUE — active while a draft is open for push-back, done on finalize
    const dialogueDone = isResume || synthesisFinal;
    const dialogueActive = Boolean(synthesisDraft) && !synthesisFinal;

    // SYNTHESIS / FINAL ANSWER — lit while refinement in flight; done on finalize
    const sDone = isResume || synthesisFinal;
    const sActive = (synthesisThinking || refinementPending) && !synthesisFinal;
    const sLabel = synthesisFinal
      ? "FINAL ANSWER"
      : (synthesisThinking || refinementPending)
        ? "SYNTHESIZING..."
        : "FINAL ANSWER";

    return { promptDone, reviewDone, reviewActive, transcriptDone, transcriptActive, factDone, factActive, dialogueDone, dialogueActive, sDone, sActive, sLabel };
  }, [isResume, sessionStarted, promptReviewData, synthesisPhaseEntered, perplexityPhase, synthesisThinking, synthesisFinal, synthesisDraft, refinementPending]);

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
            className={breadcrumbState.reviewActive ? "animate-pulse" : ""}
            style={{ color: breadcrumbState.reviewDone || breadcrumbState.reviewActive ? "#F5A623" : "#666666" }}
          >
            {breadcrumbState.reviewDone ? "✓" : breadcrumbState.reviewActive ? "●" : "○"} REVIEW
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
            className={breadcrumbState.dialogueActive ? "animate-pulse" : ""}
            style={{ color: breadcrumbState.dialogueDone || breadcrumbState.dialogueActive ? "#F5A623" : "#666666" }}
          >
            {breadcrumbState.dialogueDone ? "✓" : breadcrumbState.dialogueActive ? "●" : "○"} DIALOGUE
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

      {/* ── Prompt review gate — shown before research starts ── */}
      {promptReviewData && !sessionStarted && (
        <div className="mx-auto max-w-2xl space-y-5 px-4 py-8 sm:px-6">
          {/* Title */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-[#888888]">Here's how I'm briefing the research panel</p>
            {promptReviewData.session_title && (
              <h2 className="mt-1 text-lg font-semibold" style={{ color: "#F5A623" }}>
                {promptReviewData.session_title}
              </h2>
            )}
          </div>

          {/* What I'll research — capped so buttons stay in view */}
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#888888]">What I'll research</p>
            <div className="max-h-40 overflow-y-auto rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-3 text-sm leading-relaxed text-[#e8e8e8]">
              {promptReviewData.optimized_prompt}
            </div>
          </div>

          {/* What you want to walk away with */}
          {promptReviewData.output_intent && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#888888]">What you want to walk away with</p>
              <div className="rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-3 text-sm text-[#e8e8e8]">
                {promptReviewData.output_intent}
              </div>
            </div>
          )}

          {/* Adjustment textarea */}
          {reviewAdjusting && (
            <div className="space-y-2">
              <label htmlFor="review-adjust" className="text-xs font-semibold uppercase tracking-wide text-[#888888]">
                What should I change about this brief?
              </label>
              <textarea
                id="review-adjust"
                rows={3}
                value={reviewAdjustText}
                onChange={(e) => setReviewAdjustText(e.target.value)}
                placeholder="Describe what to change…"
                className="w-full resize-y rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-2 text-sm text-[#e8e8e8] placeholder:text-[#888888] focus:border-[#6B6B6B] focus:outline-none"
              />
              <button
                type="button"
                disabled={!reviewAdjustText.trim()}
                onClick={handleReviewAdjust}
                style={{ background: "#F5A623", color: "#0d0d0d" }}
                className="rounded-lg px-5 py-2 text-sm font-semibold transition-opacity hover:opacity-90 focus:outline-none disabled:opacity-40"
              >
                Submit Adjustment →
              </button>
            </div>
          )}

          {/* Action buttons — placed before supplementary details so they're always in view */}
          {!reviewAdjusting && (
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={handleReviewConfirm}
                style={{ background: "#F5A623", color: "#0d0d0d" }}
                className="rounded-lg px-5 py-2 text-sm font-semibold transition-opacity hover:opacity-90 focus:outline-none"
              >
                Looks good — Start Research →
              </button>
              <button
                type="button"
                onClick={() => setReviewAdjusting(true)}
                className="rounded-lg border border-[#3a3a3a] px-5 py-2 text-sm text-[#888888] transition-colors hover:border-[#F5A623] hover:text-[#F5A623] focus:outline-none"
              >
                Let me adjust something
              </button>
            </div>
          )}

          {/* Still unknown — supplementary, below CTA */}
          {Array.isArray(promptReviewData.open_questions) && promptReviewData.open_questions.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#888888]">Still unknown</p>
              <ul className="space-y-1">
                {promptReviewData.open_questions.map((q, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-[#888888]">
                    <span className="mt-0.5 shrink-0">⚠</span>
                    <span>{q}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-xs text-[#555555]">The research panel will treat these as open variables.</p>
            </div>
          )}

          {/* What I confirmed — supplementary, below CTA */}
          {Array.isArray(promptReviewData.confirmed_assumptions) && promptReviewData.confirmed_assumptions.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#888888]">What I confirmed with you</p>
              <ul className="space-y-1">
                {promptReviewData.confirmed_assumptions.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-[#888888]">
                    <span className="mt-0.5 shrink-0 text-[#F5A623]">✓</span>
                    <span>{a}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="mx-auto max-w-3xl space-y-4 px-4 py-6 sm:px-6" style={{ display: promptReviewData && !sessionStarted ? "none" : undefined }}>
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

        {/* ── SYNTHESIS DIALOGUE — draft / refine / finalize ── */}
        {synthesisPhaseEntered && (
          <section aria-label="Synthesis" className="space-y-3">
            <div className="flex items-center gap-3">
              <h2 className={`text-xs font-semibold uppercase tracking-wide text-text-secondary${!synthesisFinal ? " animate-pulse" : ""}`}>
                {synthesisFinal
                  ? "FINAL ANSWER"
                  : synthesisRevision > 0
                    ? `REVISED · round ${synthesisRevision}`
                    : synthesisDraft
                      ? "DRAFT"
                      : breadcrumbState.sLabel}
              </h2>
              {synthesisFinal && (
                <button
                  type="button"
                  onClick={copyFinalAnswer}
                  className="text-xs text-[#555555] hover:text-text-secondary transition-colors focus:outline-none"
                  aria-label="Copy final answer to clipboard"
                  title="Copy to clipboard"
                >
                  {copiedAnswer ? "Copied ✓" : "copy"}
                </button>
              )}
            </div>
            {!synthesisFinal && synthesisDraft && (
              <p className="text-xs text-text-secondary">
                {synthesisRevision > 0
                  ? "Updated based on your input."
                  : "Review this and push back on anything that doesn't match your situation."}
              </p>
            )}
            <div className="space-y-4">
              {(synthesisThinking || refinementPending) && !synthesisDraft && (
                <ThinkingDotsBubble
                  label="🟠 CLAUDE"
                  color={MODEL_HEX.Claude}
                  subtitle="Synthesizing your roundtable..."
                />
              )}
              {synthesisDraft && (
                <SynthesisPanel
                  content={synthesisBody}
                  isStreaming={false}
                  complete={synthesisFinal}
                  citations={citations}
                  variant={synthesisFinal ? "final" : synthesisRevision > 0 ? "revised" : "draft"}
                  revision={synthesisRevision}
                />
              )}

              {/* Closing questions — shown above dialogue input while not final */}
              {!synthesisFinal && closingQuestions.length > 0 && (
                <div className="space-y-2">
                  {closingQuestions.map((q, i) => (
                    <div
                      key={i}
                      className="rounded-md border px-3 py-2 text-sm leading-relaxed"
                      style={{
                        borderColor: "#2a2a2a",
                        borderLeft: "3px solid #F5A623",
                        background: "#161616",
                        color: "#e8e8e8",
                      }}
                    >
                      <span style={{ color: "#F5A623", marginRight: "0.4rem" }}>?</span>
                      {q}
                    </div>
                  ))}
                </div>
              )}

              {/* Dialogue input — hidden once finalized */}
              {!synthesisFinal && synthesisDraft && (
                <div className="space-y-2">
                  <label htmlFor="dialogue-input" className="sr-only">
                    Respond to the synthesis
                  </label>
                  <textarea
                    id="dialogue-input"
                    rows={3}
                    value={dialogueInput}
                    onChange={(e) => setDialogueInput(e.target.value)}
                    disabled={refinementPending}
                    placeholder="Push back, add context, or ask Claude to reconsider any part of this..."
                    className="w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-sm leading-relaxed text-text-primary placeholder:text-text-secondary focus:border-border-focus focus:outline-none disabled:opacity-50"
                  />
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={handleRespond}
                      disabled={refinementPending || !dialogueInput.trim()}
                      className="rounded-lg px-4 py-2 text-sm font-semibold transition-opacity hover:opacity-90 focus:outline-none disabled:opacity-40"
                      style={{ background: "#F5A623", color: "#0d0d0d" }}
                    >
                      {refinementPending ? "Refining…" : "Respond →"}
                    </button>
                    <button
                      type="button"
                      onClick={handleFinalize}
                      disabled={refinementPending}
                      className="rounded-lg border px-4 py-2 text-sm font-semibold transition-colors focus:outline-none disabled:opacity-40"
                      style={{ borderColor: "#22c55e", color: "#22c55e", background: "transparent" }}
                    >
                      Finalize ✓
                    </button>
                  </div>
                  <p className="text-right text-xs text-text-secondary">
                    Finalize locks the answer. Respond continues the dialogue.
                  </p>
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
