/**
 * frontend/src/components/IntakeFlow.jsx
 *
 * Screen 2 — Intake conversation (Claude conductor).
 *
 * Figma frame: 02-Intake-Conversation
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

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
  const [promptEditMode, setPromptEditMode] = useState(false);
  const [tierChoice, setTierChoice] = useState("deep");
  const listEndRef = useRef(null);
  const promptTextareaRef = useRef(null);
  const autoSeedSentForSessionRef = useRef(null);

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, intakeComplete, sending]);

  useEffect(() => {
    if (!intakeComplete || !pendingConfig) return;
    const t = pendingConfig.tier === "quick" ? "quick" : "deep";
    setTierChoice(t);
  }, [intakeComplete, pendingConfig]);

  /** If local draft is empty but session_config has the framing prompt, hydrate (e.g. key mismatch). */
  useEffect(() => {
    if (!intakeComplete || !pendingConfig || promptEditMode) return;
    const fromCfg = pickOptimizedPrompt(pendingConfig);
    if (!fromCfg.trim()) return;
    if (!editedPrompt.trim()) {
      setEditedPrompt(fromCfg);
    }
  }, [intakeComplete, pendingConfig, promptEditMode, editedPrompt]);

  useEffect(() => {
    if (promptEditMode) promptTextareaRef.current?.focus();
  }, [promptEditMode]);

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
      setPromptEditMode(false);
      try {
        const res = await fetch(`${API_BASE}/api/intake/start`, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        setSessionId(data.session_id);
        const openingOpts = normalizeSuggestedOptions(data.suggested_options);
        const next = [
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
          setPromptEditMode(false);
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
    const prompt = editedPrompt.trim() || pickOptimizedPrompt(pendingConfig);
    onComplete({
      ...pendingConfig,
      tier: tierChoice,
      optimized_prompt: prompt,
    });
  }, [pendingConfig, editedPrompt, tierChoice, onComplete]);

  const framingPromptForDisplay = useMemo(() => {
    if (promptEditMode) return editedPrompt;
    const draft = typeof editedPrompt === "string" ? editedPrompt.trim() : "";
    if (draft) return editedPrompt;
    return pickOptimizedPrompt(pendingConfig);
  }, [promptEditMode, editedPrompt, pendingConfig]);

  const lastMessage = messages.length ? messages[messages.length - 1] : null;
  const awaitingReplyToAssistant =
    lastMessage?.role === "assistant" && !sending && !intakeComplete && !starting;
  const optionChips = awaitingReplyToAssistant
    ? normalizeSuggestedOptions(lastMessage.suggestedOptions)
    : [];
  const showOptionChips = optionChips.length >= 2;

  return (
    <div className="flex h-[100dvh] min-h-0 flex-col bg-[#0d0d0d] text-[#e8e8e8]">
      <div className="shrink-0 px-4 pt-4 sm:px-6">
        <div className="mx-auto max-w-3xl">
          {typeof onBack === "function" && (
            <button
              type="button"
              onClick={onBack}
              className="text-sm text-[#888888] transition-colors hover:text-[#e8e8e8]"
            >
              ← Home
            </button>
          )}
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-3xl flex-1 min-h-0 flex-col px-4 pt-3 sm:px-6">
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

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-y-contain">
          <div className="space-y-4 pb-2">
          {starting && <p className="text-sm text-[#888888]">Starting conversation…</p>}

          {messages.map((msg, i) => {
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
            {!intakeComplete && !starting && sessionId && (
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
                {!sending && (
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
              <div className="space-y-4">
                <div>
                  <h2 className="text-lg font-semibold leading-snug text-[#e8e8e8]">
                    {`Here's how I'd frame this for the frontier models`}
                  </h2>
                  <p className="mt-1.5 text-sm text-[#888888]">Review and edit if needed</p>
                </div>

                {promptEditMode ? (
                  <textarea
                    ref={promptTextareaRef}
                    rows={10}
                    value={editedPrompt}
                    onChange={(e) => setEditedPrompt(e.target.value)}
                    className="w-full resize-y rounded-lg border border-[#6B6B6B] bg-[#1e1e1e] px-3 py-3 text-sm leading-relaxed text-[#e8e8e8] focus:border-[#6B6B6B] focus:outline-none"
                  />
                ) : (
                  <div className="max-h-[min(50vh,28rem)] overflow-y-auto bg-[#0d0d0d] py-1 text-sm leading-relaxed text-[#e8e8e8] whitespace-pre-wrap">
                    {framingPromptForDisplay.trim() ? (
                      framingPromptForDisplay
                    ) : (
                      <span className="text-[#888888]">
                        No optimized_prompt in session config — try completing intake again or check the
                        API response.
                      </span>
                    )}
                  </div>
                )}

                <div>
                  <p className="mb-2 text-center text-xs font-semibold uppercase tracking-wide text-[#888888]">
                    Roundtable tier
                  </p>
                  <div className="flex flex-wrap justify-center gap-2">
                    {["quick", "deep"].map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setTierChoice(t)}
                        className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors focus:outline-none ${
                          tierChoice === t
                            ? "border-[#6B6B6B] bg-[#2a2a2a] text-[#e8e8e8]"
                            : "border-[#2a2a2a] bg-[#1e1e1e] text-[#888888] hover:border-[#6B6B6B] hover:text-[#e8e8e8]"
                        }`}
                      >
                        {t === "quick" ? "Quick" : "Deep"}
                      </button>
                    ))}
                  </div>
                  <p className="mt-2 text-center text-xs text-[#888888]">
                    {tierChoice === "quick"
                      ? "Faster · cost-effective · good for most questions"
                      : "Thorough · takes 2-3 min · best for reports and decisions"}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  {!promptEditMode ? (
                    <button
                      type="button"
                      onClick={() => {
                        setEditedPrompt((prev) =>
                          typeof prev === "string" && prev.trim()
                            ? prev
                            : pickOptimizedPrompt(pendingConfig)
                        );
                        setPromptEditMode(true);
                      }}
                      className="rounded-lg border border-[#6B6B6B] bg-transparent px-4 py-2.5 text-sm font-medium text-[#e8e8e8] transition-colors hover:border-[#888888] focus:outline-none"
                    >
                      Edit
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setEditedPrompt(pickOptimizedPrompt(pendingConfig));
                        setPromptEditMode(false);
                      }}
                      className="rounded-lg border border-[#6B6B6B] bg-transparent px-4 py-2.5 text-sm font-medium text-[#e8e8e8] transition-colors hover:border-[#888888] focus:outline-none"
                    >
                      Cancel edit
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleApprove}
                    className="rounded-lg bg-[#e8e8e8] px-5 py-2.5 text-sm font-bold text-[#0d0d0d] transition-opacity hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-[#e8e8e8] focus:ring-offset-2 focus:ring-offset-[#0d0d0d]"
                  >
                    Approve
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default IntakeFlow;
