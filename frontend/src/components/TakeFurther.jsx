/**
 * "Take this further" — after session_complete.
 *
 * Active: POST /api/export/markdown (full | synthesis).
 * Placeholders: v2.1 / v3 (commented button stubs + muted labels).
 */

import React, { useCallback, useState } from "react";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

function localDateSlug() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * @param {Object} props
 * @param {Object} props.sessionConfig — intake session_config (required by export API)
 * @param {Object} props.transcript — same shape as SessionView transcriptForExport (messages, intake_summary, …)
 */
function TakeFurther({ sessionConfig, transcript }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  const saveSessionJson = useCallback(() => {
    if (!transcript?.messages || !sessionConfig) {
      setError("Missing transcript or session configuration.");
      return;
    }
    setError(null);
    const payload = {
      session_config: sessionConfig,
      transcript: {
        messages: transcript.messages,
        intake_summary: transcript.intake_summary ?? null,
      },
    };
    const slug = localDateSlug();
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ai-roundtable-session-${slug}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [transcript, sessionConfig]);

  const downloadMarkdown = useCallback(
    async (mode) => {
      if (!transcript || !sessionConfig) {
        setError("Missing transcript or session configuration.");
        return;
      }
      setError(null);
      setBusy(mode);
      try {
        const res = await fetch(`${API_BASE}/api/export/markdown`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode,
            transcript,
            session_config: sessionConfig,
          }),
        });
        if (!res.ok) {
          let msg = `Export failed (${res.status})`;
          try {
            const j = await res.json();
            if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
          } catch {
            /* ignore */
          }
          throw new Error(msg);
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `ai-roundtable-${localDateSlug()}.md`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch (e) {
        setError(e.message || "Download failed");
      } finally {
        setBusy(null);
      }
    },
    [transcript, sessionConfig]
  );

  return (
    <section
      className="rounded-lg border border-border bg-surface px-4 py-5 text-text-primary sm:px-5"
      aria-labelledby="take-further-heading"
    >
      <h2 id="take-further-heading" className="mb-4 text-base font-semibold text-text-primary">
        Take this further
      </h2>

      {error && (
        <p className="mb-3 text-sm text-red-400" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-col gap-2">
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => downloadMarkdown("full")}
          className="w-full rounded-lg border border-border bg-surface px-4 py-3 text-left text-sm text-text-primary transition-colors hover:border-border-focus focus:border-border-focus focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy === "full" ? "Preparing…" : "📄 Download full session (.md)"}
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => downloadMarkdown("synthesis")}
          className="w-full rounded-lg border border-border bg-surface px-4 py-3 text-left text-sm text-text-primary transition-colors hover:border-border-focus focus:border-border-focus focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy === "synthesis" ? "Preparing…" : "📄 Download synthesis only (.md)"}
        </button>
        <button
          type="button"
          disabled={busy !== null}
          onClick={saveSessionJson}
          className="w-full rounded-lg border border-border bg-surface px-4 py-3 text-left text-sm text-text-primary transition-colors hover:border-border-focus focus:border-border-focus focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          💾 Save session — resume later (.json)
        </button>
      </div>

      <div className="mt-6 space-y-3 border-t border-border pt-4 text-[11px] leading-snug text-[#888888]">
        <div>
          <p>Coming in v2.1</p>
          <p>Google Drive · Claude Code</p>
        </div>
        <div>
          <p>Coming in v3</p>
          <p>PDF · Notion</p>
        </div>
      </div>
    </section>
  );
}

export default TakeFurther;
