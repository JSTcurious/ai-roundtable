/**
 * frontend/src/components/IntakeFlow.jsx
 *
 * Screen 2 — Intake conversation (Claude conductor).
 *
 * Figma frame: 02-Intake-Conversation
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Header from "./common/Header";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

/** Force LTR rendering on Claude bubble (guards against inherited bidi / transforms). */
const CLAUDE_BUBBLE_TEXT_GUARD_STYLE = {
  transform: "none",
  direction: "ltr",
  unicodeBidi: "normal",
};

/**
 * Remove Unicode directional / bidi control characters (e.g. U+202E RLO) that can
 * make Latin text appear reversed without any CSS transform.
 */
function stripBidiFormattingControls(text) {
  if (!text) return "";
  let s = text.replace(/^\uFEFF+|\uFEFF+$/g, "");
  // U+202A–U+202E embedding & overrides; U+2066–U+2069 isolates; U+200E–U+200F marks; U+061C ALM
  s = s.replace(/[\u202A-\u202E\u2066-\u2069\u200E\u200F\u061C]/g, "");
  return s;
}

function stripIntakeUiBlock(text) {
  if (!text) return "";
  const fence = "```intake-ui";
  const i = text.indexOf(fence);
  if (i === -1) return text;
  const start = i + fence.length;
  const end = text.indexOf("```", start);
  if (end === -1) return text.slice(0, i).trimEnd();
  const before = text.slice(0, i).trimEnd();
  const after = text.slice(end + 3).trimStart();
  if (before && after) return `${before}\n\n${after}`.trim();
  return (before || after).trim();
}

const INTAKE_OPTIONS_MARKER = "INTAKE_OPTIONS:";

/** Strip trailing `INTAKE_OPTIONS: [...]` from displayed assistant text. */
function stripIntakeOptionsBlock(text) {
  if (!text) return "";
  const idx = text.lastIndexOf(INTAKE_OPTIONS_MARKER);
  if (idx === -1) return text;
  return text.slice(0, idx).trimEnd();
}

/** Parse options from raw assistant text (fallback if API omitted suggested_options). */
function parseIntakeOptionsFromMessage(text) {
  if (!text || !text.includes(INTAKE_OPTIONS_MARKER)) return [];
  const idx = text.lastIndexOf(INTAKE_OPTIONS_MARKER);
  const suffix = text.slice(idx + INTAKE_OPTIONS_MARKER.length).trim();
  if (!suffix.startsWith("[")) return [];
  let depth = 0;
  let endI = -1;
  for (let i = 0; i < suffix.length; i++) {
    const ch = suffix[i];
    if (ch === "[") depth += 1;
    else if (ch === "]") {
      depth -= 1;
      if (depth === 0) {
        endI = i + 1;
        break;
      }
    }
  }
  if (endI < 0) return [];
  try {
    const arr = JSON.parse(suffix.slice(0, endI));
    if (!Array.isArray(arr)) return [];
    return arr.map((x) => String(x).trim()).filter(Boolean);
  } catch {
    return [];
  }
}

/** Keep only 2–4 options for chip UI; otherwise return []. */
function normalizeSuggestedOptions(raw) {
  if (!Array.isArray(raw)) return [];
  const out = raw.map((x) => String(x).trim()).filter(Boolean).slice(0, 4);
  return out.length >= 2 ? out : [];
}

function displayAssistantText(raw) {
  let t = stripBidiFormattingControls(
    stripIntakeOptionsBlock(stripIntakeUiBlock(raw || ""))
  );
  const fence = "```json";
  const i = t.indexOf(fence);
  if (i === -1) return t;
  return t.slice(0, i).trimEnd();
}

/**
 * Read optimized_prompt from intake session_config (API snake_case or rare camelCase).
 */
function pickOptimizedPrompt(sessionConfig) {
  if (!sessionConfig || typeof sessionConfig !== "object") return "";
  const raw =
    sessionConfig.optimized_prompt ??
    sessionConfig.optimizedPrompt ??
    sessionConfig["optimized-prompt"];
  if (typeof raw === "string") return raw;
  if (raw == null) return "";
  return String(raw);
}

/**
 * @param {Object} props
 * @param {string | null} [props.initialUserMessage] — from landing; sent as first user message after start
 * @param {Object | null} [props.selectedUseCase] — optional `first_question` after opening
 * @param {function} props.onComplete - `(session_config) => void` after user approves optimized prompt
 * @param {function} [props.onBack] - optional return to landing
 */
function IntakeFlow({ initialUserMessage, selectedUseCase, onComplete, onBack }) {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [bootError, setBootError] = useState(null);
  const [sendError, setSendError] = useState(null);
  const [starting, setStarting] = useState(true);
  const [sending, setSending] = useState(false);
  const [intakeComplete, setIntakeComplete] = useState(false);
  const [pendingConfig, setPendingConfig] = useState(null);
  const [editedPrompt, setEditedPrompt] = useState("");
  const [tierChoice, setTierChoice] = useState("smart");
  /** null = intake Q&A · then review → refine_input → refine_chat → tier (final Approve) */
  const [approvalPhase, setApprovalPhase] = useState(null);
  const [refineDraft, setRefineDraft] = useState("");
  const [refineSending, setRefineSending] = useState(false);
  const [refineError, setRefineError] = useState(null);
  const [refineThread, setRefineThread] = useState([]);
  /** True until the first real /api/intake/refine call completes — guards probe_answer vs user_feedback. */
  const [refineIsFirstMessage, setRefineIsFirstMessage] = useState(true);
  /** After a full refine (probe → rewrite), show confirmation chips from API. */
  const [postRefineReview, setPostRefineReview] = useState(false);
  const [postRefineMeta, setPostRefineMeta] = useState(null);
  const listEndRef = useRef(null);
  const refineInputRef = useRef(null);
  const autoSeedSentForSessionRef = useRef(null);
  const cancelOnLeaveRef = useRef({ sessionId: null, phase: null });

  useEffect(() => {
    cancelOnLeaveRef.current = { sessionId, phase: approvalPhase };
  }, [sessionId, approvalPhase]);

  useEffect(() => {
    return () => {
      const { sessionId: sid, phase } = cancelOnLeaveRef.current;
      if (!sid) return;
      if (phase === "refine_input" || phase === "refine_chat") {
        fetch(`${API_BASE}/api/intake/refine/cancel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sid }),
          keepalive: true,
        }).catch(() => {});
      }
    };
  }, []);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, intakeComplete, sending, approvalPhase, refineThread, postRefineReview]);

  useEffect(() => {
    if (!intakeComplete || !pendingConfig) return;
    const raw = (pendingConfig.tier ?? "smart").toString().toLowerCase().replace(/-/g, "_");
    if (raw === "quick") setTierChoice("quick");
    else if (raw === "smart") setTierChoice("smart");
    else if (raw === "deep" || raw === "deep_thinking") setTierChoice("deep");
    else setTierChoice("smart");
  }, [intakeComplete, pendingConfig]);

  /** If local draft is empty but session_config has the framing prompt, hydrate (e.g. key mismatch). */
  useEffect(() => {
    if (!intakeComplete || !pendingConfig) return;
    const fromCfg = pickOptimizedPrompt(pendingConfig);
    if (!fromCfg.trim()) return;
    if (!editedPrompt.trim()) {
      setEditedPrompt(fromCfg);
    }
  }, [intakeComplete, pendingConfig, editedPrompt]);

  useEffect(() => {
    if (approvalPhase === "refine_input") refineInputRef.current?.focus();
  }, [approvalPhase]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setStarting(true);
      setBootError(null);
      setMessages([]);
      setSessionId(null);
      setIntakeComplete(false);
      setPendingConfig(null);
      setEditedPrompt("");
      setApprovalPhase(null);
      setRefineDraft("");
      setRefineError(null);
      setRefineThread([]);
      setPostRefineReview(false);
      setPostRefineMeta(null);
      try {
        const res = await fetch(`${API_BASE}/api/intake/start`, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        setSessionId(data.session_id);
        const openingOpts = normalizeSuggestedOptions(data.suggested_options);
        // If initialUserMessage is present the auto-seed will fire immediately —
        // skip the generic opener so the chat starts with the user's own message.
        const next = initialUserMessage?.trim()
          ? []
          : [
              {
                role: "assistant",
                content: data.message || "",
                ...(openingOpts.length >= 2 ? { suggestedOptions: openingOpts } : {}),
              },
            ];
        const fq = selectedUseCase?.first_question;
        if (fq) {
          next.push({
            role: "assistant",
            content: fq,
            variant: "use_case",
          });
        }
        setMessages(next);
      } catch (e) {
        if (!cancelled) setBootError(e.message || "Could not start intake");
      } finally {
        if (!cancelled) setStarting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedUseCase]);

  const submitIntakeText = useCallback(
    async (rawText, { restoreInputOnFailure } = { restoreInputOnFailure: false }) => {
      const text = rawText.trim();
      if (!text || !sessionId || sending || intakeComplete) return;
      setSendError(null);
      setSending(true);
      setMessages((m) => [...m, { role: "user", content: text }]);
      try {
        const res = await fetch(`${API_BASE}/api/intake/respond`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, message: text }),
        });
        if (!res.ok) {
          if (res.status === 404) throw new Error("Intake session expired. Go back and try again.");
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.detail || `HTTP ${res.status}`);
        }
        const data = await res.json();
        const rawMsg = data.message || "";
        let opts = normalizeSuggestedOptions(data.suggested_options);
        if (opts.length < 2) {
          opts = normalizeSuggestedOptions(parseIntakeOptionsFromMessage(rawMsg));
        }
        const bubbleContent = stripIntakeOptionsBlock(stripIntakeUiBlock(rawMsg));
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content: bubbleContent,
            ...(opts.length >= 2 ? { suggestedOptions: opts } : {}),
          },
        ]);
        if (data.status === "complete") {
          setIntakeComplete(true);
          const cfg = data.config && typeof data.config === "object" ? data.config : {};
          setPendingConfig(cfg);
          setEditedPrompt(pickOptimizedPrompt(cfg));
          setApprovalPhase("review");
          setRefineDraft("");
          setRefineError(null);
          setRefineThread([]);
          setPostRefineReview(false);
          setPostRefineMeta(null);
        }
      } catch (e) {
        setSendError(e.message || "Send failed");
        setMessages((m) => {
          const copy = [...m];
          const last = copy[copy.length - 1];
          if (last?.role === "user" && last.content === text) copy.pop();
          return copy;
        });
        if (restoreInputOnFailure) setInput(text);
      } finally {
        setSending(false);
      }
    },
    [sessionId, sending, intakeComplete]
  );

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    await submitIntakeText(text, { restoreInputOnFailure: true });
  }, [input, submitIntakeText]);

  useEffect(() => {
    if (!sessionId || starting || intakeComplete) return;
    const seed = initialUserMessage?.trim();
    if (!seed) return;
    if (autoSeedSentForSessionRef.current === sessionId) return;
    autoSeedSentForSessionRef.current = sessionId;
    submitIntakeText(seed, { restoreInputOnFailure: false });
  }, [sessionId, starting, intakeComplete, initialUserMessage, submitIntakeText]);

  const handleApprove = useCallback(() => {
    if (!pendingConfig || typeof onComplete !== "function") return;
    if (approvalPhase !== "tier") return;
    const prompt = editedPrompt.trim() || pickOptimizedPrompt(pendingConfig);
    onComplete({
      ...pendingConfig,
      tier: tierChoice,
      optimized_prompt: prompt,
    });
  }, [pendingConfig, editedPrompt, tierChoice, onComplete, approvalPhase]);

  /** Read-only prompt: session_config.optimized_prompt via pendingConfig (intake API `config`). */
  const framingPromptForDisplay = useMemo(() => {
    const draft = typeof editedPrompt === "string" ? editedPrompt.trim() : "";
    if (draft) return editedPrompt;
    return pickOptimizedPrompt(pendingConfig);
  }, [editedPrompt, pendingConfig]);

  /** Post–refine confirmation: API chips or default Yes / Adjust pair. */
  const postRefineChipLabels = useMemo(() => {
    if (!postRefineReview || !postRefineMeta) return null;
    const o = normalizeSuggestedOptions(postRefineMeta.suggestedOptions);
    return o.length >= 2 ? o : ["Yes — looks good", "Adjust something else"];
  }, [postRefineReview, postRefineMeta]);

  const goToTierSelection = useCallback(async () => {
    setPostRefineReview(false);
    setPostRefineMeta(null);
    if (!sessionId) {
      setApprovalPhase("tier");
      return;
    }
    try {
      await fetch(`${API_BASE}/api/intake/refine/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
    } catch {
      /* non-fatal */
    }
    setApprovalPhase("tier");
  }, [sessionId]);

  const handlePostRefineOption = useCallback(
    (label) => {
      const lower = String(label).toLowerCase();
      const affirms =
        (lower.includes("yes") && (lower.includes("good") || lower.includes("looks"))) ||
        lower.includes("✓");
      if (affirms) {
        void goToTierSelection();
        return;
      }
      setPostRefineReview(false);
      setPostRefineMeta(null);
      setRefineThread([]);
      setRefineError(null);
      setRefineIsFirstMessage(true);
      setApprovalPhase("refine_input");
    },
    [goToTierSelection]
  );

  const handleBack = useCallback(async () => {
    if (
      sessionId &&
      (approvalPhase === "refine_input" || approvalPhase === "refine_chat")
    ) {
      try {
        await fetch(`${API_BASE}/api/intake/refine/cancel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }),
        });
      } catch {
        /* non-fatal */
      }
    }
    if (typeof onBack === "function") onBack();
  }, [sessionId, approvalPhase, onBack]);

  const sendRefinementMessage = useCallback(
    async (rawText) => {
      const text = rawText.trim();
      if (!text || !sessionId || refineSending) return;
      setRefineError(null);
      setRefineSending(true);
      const isProbeRound = !refineIsFirstMessage;
      const promptText = (editedPrompt.trim() || pickOptimizedPrompt(pendingConfig)).trim();
      const body = isProbeRound
        ? { session_id: sessionId, probe_answer: text }
        : { session_id: sessionId, current_prompt: promptText, user_feedback: text };
      setRefineIsFirstMessage(false);
      try {
        const res = await fetch(`${API_BASE}/api/intake/refine`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const errBody = await res.json().catch(() => ({}));
          throw new Error(errBody.detail || `HTTP ${res.status}`);
        }
        const data = await res.json();
        if (data.status === "probing") {
          let opts = normalizeSuggestedOptions(data.suggested_options);
          if (opts.length < 2) {
            opts = normalizeSuggestedOptions(parseIntakeOptionsFromMessage(data.message || ""));
          }
          setRefineThread((prev) => [
            ...prev,
            { role: "user", content: text },
            {
              role: "assistant",
              content: displayAssistantText(data.message || ""),
              ...(opts.length >= 2 ? { suggestedOptions: opts } : {}),
            },
          ]);
          setApprovalPhase("refine_chat");
          setRefineDraft("");
        } else if (data.status === "refined") {
          const cfg = data.config && typeof data.config === "object" ? data.config : {};
          if (Object.keys(cfg).length) {
            setPendingConfig(cfg);
            setEditedPrompt(pickOptimizedPrompt(cfg));
          }
          setRefineThread([]);
          setApprovalPhase("review");
          let opts = normalizeSuggestedOptions(data.suggested_options);
          if (opts.length < 2) {
            opts = normalizeSuggestedOptions(parseIntakeOptionsFromMessage(data.message || ""));
          }
          setPostRefineReview(true);
          setPostRefineMeta({
            message: data.message || "",
            suggestedOptions: opts.length >= 2 ? opts : null,
          });
        } else {
          throw new Error("Unexpected refine response");
        }
      } catch (e) {
        setRefineError(e.message || "Refine failed");
      } finally {
        setRefineSending(false);
      }
    },
    [sessionId, refineSending, refineIsFirstMessage, editedPrompt, pendingConfig]
  );

  const lastMessage = messages.length ? messages[messages.length - 1] : null;
  const awaitingReplyToAssistant =
    lastMessage?.role === "assistant" && !sending && !intakeComplete && !starting;
  const optionChips = awaitingReplyToAssistant
    ? normalizeSuggestedOptions(lastMessage.suggestedOptions)
    : [];
  const showOptionChips = optionChips.length >= 2;

  return (
    <div className="flex h-[100dvh] min-h-0 flex-col bg-[#0d0d0d] text-[#e8e8e8]">
      <Header onHome={handleBack} onSaveExit={typeof onBack === "function" ? handleBack : undefined} />

      <div className="mx-auto flex w-full max-w-3xl flex-1 min-h-0 flex-col px-4 pt-4 sm:px-6 lg:max-w-5xl">
        {(bootError || sendError) && (
          <div className="shrink-0 space-y-2 pb-2" role="region" aria-label="Errors">
            {bootError && (
              <p className="text-sm text-red-400" role="alert">
                {bootError}
              </p>
            )}
            {sendError && (
              <p className="text-sm text-red-400" role="alert">
                {sendError}
              </p>
            )}
          </div>
        )}

        <div className="intake-scroll min-h-0 flex-1 overflow-y-auto overscroll-y-contain">
          <div className="space-y-4 pb-2">
          {starting && <p className="text-sm text-[#888888]">Starting conversation…</p>}

          {!intakeComplete &&
            messages.map((msg, i) => {
            if (intakeComplete && msg.role === "assistant" && i === messages.length - 1) {
              return null;
            }
            const isUser = msg.role === "user";
            const bubble = isUser ? (
              <div
                key={i}
                dir="ltr"
                className="ml-auto max-w-[min(100%,36rem)] rounded-lg bg-[#2a2a2a] px-4 py-3 text-[0.9375rem] leading-relaxed text-[#e8e8e8]"
                style={{ unicodeBidi: "isolate" }}
              >
                {stripBidiFormattingControls(msg.content)}
              </div>
            ) : (
              <div key={i} className="mr-auto w-full max-w-[min(100%,36rem)]">
                <div className="mb-2 flex items-center gap-2">
                  <span className="h-2 w-2 shrink-0 rounded-full bg-claude" aria-hidden />
                  <span className="text-sm font-medium text-[#e8e8e8]">Claude</span>
                </div>
                <div
                  dir="ltr"
                  className="rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-3 text-[0.9375rem] leading-relaxed text-[#e8e8e8]"
                  style={CLAUDE_BUBBLE_TEXT_GUARD_STYLE}
                >
                  {msg.variant === "use_case" && (
                    <p
                      className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#888888]"
                      dir="ltr"
                      style={CLAUDE_BUBBLE_TEXT_GUARD_STYLE}
                    >
                      For this use case
                    </p>
                  )}
                  <div
                    className="whitespace-pre-wrap"
                    dir="ltr"
                    style={CLAUDE_BUBBLE_TEXT_GUARD_STYLE}
                  >
                    {msg.role === "assistant"
                      ? displayAssistantText(msg.content)
                      : stripBidiFormattingControls(msg.content)}
                  </div>
                </div>
              </div>
            );
            return bubble;
          })}

          {intakeComplete && approvalPhase === "refine_chat" && refineThread.length > 0 && (
            <div className="space-y-3 border-t border-[#2a2a2a] pt-4">
              {refineThread.map((msg, i) => {
                const isUser = msg.role === "user";
                if (isUser) {
                  return (
                    <div
                      key={`rf-u-${i}`}
                      dir="ltr"
                      className="ml-auto max-w-[min(100%,36rem)] rounded-lg bg-[#2a2a2a] px-4 py-3 text-[0.9375rem] leading-relaxed text-[#e8e8e8]"
                      style={{ unicodeBidi: "isolate" }}
                    >
                      {stripBidiFormattingControls(msg.content)}
                    </div>
                  );
                }
                const opts = normalizeSuggestedOptions(msg.suggestedOptions);
                return (
                  <div key={`rf-a-${i}`} className="mr-auto w-full max-w-[min(100%,36rem)]">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="h-2 w-2 shrink-0 rounded-full bg-[#E8712A]" aria-hidden />
                      <span className="text-sm font-medium text-[#e8e8e8]">Claude</span>
                    </div>
                    <div
                      dir="ltr"
                      className="rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-3 text-[0.9375rem] leading-relaxed text-[#e8e8e8]"
                      style={CLAUDE_BUBBLE_TEXT_GUARD_STYLE}
                    >
                      <div className="whitespace-pre-wrap" dir="ltr" style={CLAUDE_BUBBLE_TEXT_GUARD_STYLE}>
                        {displayAssistantText(msg.content)}
                      </div>
                      {msg.promptBlock && (
                        <div className="mt-3 max-h-[200px] overflow-y-auto rounded-lg border border-[#2a2a2a] bg-[#0d0d0d] px-3 py-2 text-sm leading-relaxed text-[#e8e8e8] whitespace-pre-wrap break-words">
                          {msg.promptBlock}
                        </div>
                      )}
                    </div>
                    {opts.length >= 2 && (
                      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {opts.map((label, j) => (
                          <button
                            key={`${j}-${label.slice(0, 24)}`}
                            type="button"
                            disabled={refineSending}
                            onClick={() => sendRefinementMessage(label)}
                            className="rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-2.5 text-left text-sm leading-snug text-[#e8e8e8] transition-colors hover:border-[#6B6B6B] focus:border-[#6B6B6B] focus:outline-none disabled:opacity-50"
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {intakeComplete && approvalPhase === "refine_chat" && refineThread.length > 0 && !refineSending && (
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                sendRefinementMessage(refineDraft);
                setRefineDraft("");
              }}
            >
              <label htmlFor="refine-reply" className="sr-only">
                Reply to Claude
              </label>
              <textarea
                id="refine-reply"
                rows={2}
                value={refineDraft}
                onChange={(e) => setRefineDraft(e.target.value)}
                placeholder="Your answer…"
                className="min-h-[2.5rem] min-w-0 flex-1 resize-y rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-2 text-sm text-[#e8e8e8] placeholder:text-[#888888] focus:border-[#6B6B6B] focus:outline-none"
              />
              <button
                type="submit"
                disabled={refineSending || !refineDraft.trim()}
                className="inline-flex h-10 shrink-0 items-center justify-center self-start rounded-lg border border-[#6B6B6B] bg-[#1e1e1e] px-3 text-sm text-[#e8e8e8] focus:outline-none disabled:opacity-40"
                aria-label="Send"
              >
                <span aria-hidden>→</span>
              </button>
            </form>
          )}

          {sending && !intakeComplete && sessionId && (
            <div
              className="mr-auto w-full max-w-[min(100%,36rem)]"
              role="status"
              aria-live="polite"
              aria-label="Claude is typing"
            >
              <div className="mb-2 flex items-center gap-2">
                <span className="h-2 w-2 shrink-0 rounded-full bg-claude" aria-hidden />
                <span className="text-sm font-medium text-[#e8e8e8]">Claude</span>
              </div>
              <div
                dir="ltr"
                className="rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-3"
                style={CLAUDE_BUBBLE_TEXT_GUARD_STYLE}
              >
                <div className="intake-typing-indicator flex items-center gap-1.5 py-0.5" aria-hidden>
                  <span className="dot" />
                  <span className="dot" />
                  <span className="dot" />
                </div>
              </div>
            </div>
          )}

          <div ref={listEndRef} />
          </div>
        </div>

        {((!intakeComplete && !starting && sessionId) || intakeComplete) && (
          <div className="shrink-0 border-t border-[#2a2a2a] bg-[#0d0d0d] pt-4 pb-[max(1.5rem,env(safe-area-inset-bottom,0px))]">
            {!intakeComplete && !starting && sessionId && approvalPhase === null && (
              <div className="space-y-3">
                {showOptionChips && (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {optionChips.map((label, idx) => (
                      <button
                        key={`${idx}-${label.slice(0, 24)}`}
                        type="button"
                        disabled={sending}
                        onClick={() => submitIntakeText(label, { restoreInputOnFailure: false })}
                        className="rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-2.5 text-left text-sm leading-snug text-[#e8e8e8] transition-colors hover:border-[#6B6B6B] focus:border-[#6B6B6B] focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )}
                {approvalPhase === null && !sending && (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      sendMessage();
                    }}
                    className="flex gap-2"
                  >
                    <label htmlFor="intake-reply" className="sr-only">
                      Your message
                    </label>
                    <textarea
                      id="intake-reply"
                      rows={showOptionChips ? 2 : 3}
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      disabled={sending}
                      placeholder={showOptionChips ? "Something else..." : "Reply to Claude…"}
                      className="min-h-[2.75rem] min-w-0 flex-1 resize-y rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-2 text-sm text-[#e8e8e8] placeholder:text-[#888888] focus:border-[#6B6B6B] focus:outline-none disabled:opacity-60"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          sendMessage();
                        }
                      }}
                    />
                    <button
                      type="submit"
                      disabled={sending || !input.trim()}
                      className="mt-0 inline-flex h-10 w-10 shrink-0 items-center justify-center self-start rounded-lg border border-[#6B6B6B] bg-[#1e1e1e] text-[#e8e8e8] transition-colors hover:border-[#6B6B6B] focus:border-[#6B6B6B] focus:outline-none disabled:cursor-not-allowed disabled:opacity-40"
                      aria-label={sending ? "Sending" : "Send message"}
                    >
                      <span className="text-lg leading-none" aria-hidden>
                        {sending ? "…" : "→"}
                      </span>
                    </button>
                  </form>
                )}
              </div>
            )}

            {intakeComplete && (
              <div className="space-y-5">
                {approvalPhase === "refine_input" && (
                  <div className="space-y-3">
                    <div className="mr-auto w-full max-w-[min(100%,36rem)]">
                      <div className="mb-2 flex items-center gap-2">
                        <span className="h-2 w-2 shrink-0 rounded-full bg-[#E8712A]" aria-hidden />
                        <span className="text-sm font-medium text-[#e8e8e8]">Claude</span>
                      </div>
                      <div
                        dir="ltr"
                        className="rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-4 py-3 text-[0.9375rem] leading-relaxed text-[#e8e8e8]"
                        style={CLAUDE_BUBBLE_TEXT_GUARD_STYLE}
                      >
                        <div className="whitespace-pre-wrap" dir="ltr" style={CLAUDE_BUBBLE_TEXT_GUARD_STYLE}>
                          What would you like to adjust?
                        </div>
                      </div>
                    </div>
                    <form
                      className="flex gap-2"
                      onSubmit={(e) => {
                        e.preventDefault();
                        sendRefinementMessage(refineDraft);
                        setRefineDraft("");
                      }}
                    >
                      <label htmlFor="refine-adjust" className="sr-only">
                        What to change
                      </label>
                      <textarea
                        ref={refineInputRef}
                        id="refine-adjust"
                        rows={2}
                        value={refineDraft}
                        onChange={(e) => setRefineDraft(e.target.value)}
                        disabled={refineSending}
                        placeholder="Your answer…"
                        className="min-h-[2.5rem] min-w-0 flex-1 resize-y rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-2 text-sm text-[#e8e8e8] placeholder:text-[#888888] focus:border-[#6B6B6B] focus:outline-none disabled:opacity-60"
                      />
                      <button
                        type="submit"
                        disabled={refineSending || !refineDraft.trim()}
                        className="inline-flex h-10 shrink-0 items-center justify-center self-start rounded-lg border border-[#6B6B6B] bg-[#1e1e1e] px-3 text-sm text-[#e8e8e8] focus:outline-none disabled:opacity-40"
                        aria-label="Send"
                      >
                        {refineSending ? "…" : "→"}
                      </button>
                    </form>
                  </div>
                )}

                {approvalPhase === "review" && (
                  <div className="space-y-4">
                    <div>
                      <h2 className="text-lg font-semibold leading-snug text-[#e8e8e8]">
                        Your optimized prompt
                      </h2>
                      <p className="mt-1.5 text-sm text-[#888888]">Review before sending to the roundtable</p>
                    </div>

                    <div className="max-h-[280px] w-full overflow-y-auto overflow-x-hidden rounded-lg border border-[#2a2a2a] bg-[#0d0d0d] px-3 py-2 text-sm leading-relaxed text-[#e8e8e8] whitespace-pre-wrap break-words">
                      {framingPromptForDisplay.trim() ? (
                        framingPromptForDisplay
                      ) : (
                        <span className="text-[#888888]">
                          No optimized_prompt in session config — try completing intake again or check the API
                          response.
                        </span>
                      )}
                    </div>

                    <hr className="border-[#2a2a2a]" />

                    {postRefineChipLabels ? (
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {postRefineChipLabels.map((label, j) => (
                          <button
                            key={`${j}-${label.slice(0, 32)}`}
                            type="button"
                            disabled={refineSending}
                            onClick={() => handlePostRefineOption(label)}
                            className="rounded-lg border border-[#2a2a2a] bg-[#1e1e1e] px-3 py-2.5 text-left text-sm leading-snug text-[#e8e8e8] transition-colors hover:border-[#6B6B6B] focus:border-[#6B6B6B] focus:outline-none disabled:opacity-50"
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="flex flex-wrap items-center gap-3">
                        <button
                          type="button"
                          onClick={goToTierSelection}
                          className="rounded-lg bg-[#e8e8e8] px-5 py-2.5 text-sm font-bold text-[#0d0d0d] transition-opacity hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-[#e8e8e8] focus:ring-offset-2 focus:ring-offset-[#0d0d0d]"
                        >
                          Approve →
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setRefineThread([
                              { role: "user", content: "I'd like to adjust the prompt" },
                              { role: "assistant", content: "Of course — what would you like to change?" },
                            ]);
                            setRefineIsFirstMessage(true);
                            setRefineError(null);
                            setRefineDraft("");
                            setApprovalPhase("refine_chat");
                          }}
                          className="rounded-lg border border-[#6B6B6B] bg-transparent px-4 py-2.5 text-sm font-medium text-[#e8e8e8] transition-colors hover:border-[#888888] focus:outline-none"
                        >
                          Adjust
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {approvalPhase === "tier" && (
                  <div className="space-y-4 border-t border-[#2a2a2a] pt-5">
                    <p className="text-center text-sm font-medium text-[#e8e8e8]">Choose roundtable depth</p>
                    <div className="w-full min-w-0">
                      <p className="mb-2 text-center text-sm text-[#888888]">How deep should the roundtable go?</p>
                      <div className="flex min-w-0 gap-3">
                        {[
                          { id: "quick", label: "⚡ Quick" },
                          { id: "smart", label: "⚖ Smart" },
                          { id: "deep", label: "🔍 Deep" },
                        ].map(({ id, label }) => (
                          <button
                            key={id}
                            type="button"
                            onClick={() => setTierChoice(id)}
                            className={`min-w-0 flex-1 rounded-lg border px-4 py-2.5 text-center text-sm font-medium transition-colors focus:outline-none ${
                              tierChoice === id
                                ? "border-[#6B6B6B] bg-[#2a2a2a] text-[#e8e8e8]"
                                : "border-[#2a2a2a] bg-[#1e1e1e] text-[#888888] hover:border-[#6B6B6B]"
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                      <p className="mx-auto mt-2 w-full min-w-0 px-1 text-center text-xs leading-relaxed text-[#888888] break-words">
                        {tierChoice === "quick" &&
                          "Single executor per model · fastest · good for gut checks and brainstorms"}
                        {tierChoice === "smart" &&
                          "Executor + advisor per model · near-Deep quality · recommended for most sessions"}
                        {tierChoice === "deep" &&
                          "Flagship models throughout · maximum depth · best for reports and critical decisions"}
                      </p>
                    </div>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        onClick={handleApprove}
                        className="rounded-lg bg-[#e8e8e8] px-6 py-2.5 text-sm font-bold text-[#0d0d0d] transition-opacity hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-[#e8e8e8] focus:ring-offset-2 focus:ring-offset-[#0d0d0d]"
                      >
                        Approve →
                      </button>
                    </div>
                  </div>
                )}

                {refineError && (
                  <p className="text-sm text-red-400" role="alert">
                    {refineError}
                  </p>
                )}

                {refineSending && (approvalPhase === "refine_chat" || approvalPhase === "refine_input") && (
                  <p className="text-sm text-[#888888]" role="status">
                    Claude is thinking…
                  </p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default IntakeFlow;
