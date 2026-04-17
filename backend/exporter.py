"""
backend/exporter.py

Session export for ai-roundtable v2.

Every session produces a markdown file. Always.
Markdown is the universal intermediary — portable, convertible downstream.

v2 ships:
    - to_markdown()  — full session or synthesis-only markdown string
    - download()     — UTF-8 bytes for browser download

Deferred to v2.1:
    - save_to_drive()           — Google Drive export
    - prepare_for_claude_code() — Claude Code handoff
    - prepare_for_perplexity()  — Perplexity handoff

v3 adds: PDF, Notion, Slack

Classes:
    Exporter — markdown generation and download
"""

from datetime import datetime

from backend.transcript import Transcript


class Exporter:
    """Generates markdown exports for completed roundtable sessions."""

    # ── Public API ────────────────────────────────────────────────────────────

    def to_markdown(self, transcript: Transcript, config: dict, mode: str = "full") -> str:
        """
        Generate a markdown string for the session.

        Args:
            transcript: the completed session Transcript
            config:     session_config dict from IntakeSession
            mode:       "full"      — entire session
                        "synthesis" — session title, prompt, synthesis, footer only
                        "prompt"    — optimized prompt only

        Returns a markdown string ready for download or display.
        """
        if mode == "synthesis":
            return self._synthesis_doc(transcript, config)
        if mode == "prompt":
            return self._prompt_doc(transcript, config)
        return self._full_doc(transcript, config)

    def download(self, markdown: str, filename: str) -> bytes:
        """Return markdown as UTF-8 bytes for a browser download response."""
        return markdown.encode("utf-8")

    # ── Deferred to v2.1 ─────────────────────────────────────────────────────

    def save_to_drive(self, markdown: str, filename: str, access_token: str) -> str:
        """Google Drive export — deferred to v2.1."""
        raise NotImplementedError("Google Drive export coming in v2.1.")

    def prepare_for_claude_code(self, markdown: str) -> dict:
        """Claude Code handoff — deferred to v2.1."""
        raise NotImplementedError("Claude Code handoff coming in v2.1.")

    def prepare_for_perplexity(self, markdown: str) -> dict:
        """Perplexity handoff — deferred to v2.1."""
        raise NotImplementedError("Perplexity handoff coming in v2.1.")

    # ── Private builders ──────────────────────────────────────────────────────

    def _full_doc(self, transcript: Transcript, config: dict) -> str:
        """Build the full-session markdown document."""
        date = datetime.now().strftime("%B %d, %Y")
        title = config.get("session_title", "ai-roundtable Session")
        output_type = config.get("output_type", "report")
        tier = config.get("tier", "quick")
        intake_summary = config.get("intake_summary") or transcript.intake_summary or ""
        open_assumptions = config.get("open_assumptions", [])
        optimized_prompt = config.get("optimized_prompt", "")

        round1 = {
            m["sender"].lower(): m["content"]
            for m in transcript.messages
            if m.get("round") == "round1" and m["role"] == "assistant"
        }
        synthesis_msgs = [
            m for m in transcript.messages
            if m.get("round") == "synthesis" and m["role"] == "assistant"
        ]
        synthesis_text = synthesis_msgs[-1]["content"] if synthesis_msgs else ""

        lines = []

        # ── Header ────────────────────────────────────────────────────────────
        lines += [
            "# ai-roundtable — Full Session",
            f"*{title}*",
            f"*{output_type} · {tier} · {date}*",
            "",
            "---",
            "",
        ]

        # ── Your Situation ────────────────────────────────────────────────────
        if intake_summary:
            lines += [
                "## Your Situation",
                "",
                intake_summary,
                "",
            ]

        # ── Open Assumptions ──────────────────────────────────────────────────
        if open_assumptions:
            lines += ["## Open Assumptions", ""]
            for assumption in open_assumptions:
                lines.append(f"- {assumption}")
            lines.append("")

        # ── Opening Prompt ────────────────────────────────────────────────────
        if optimized_prompt:
            lines += [
                "## Opening Prompt",
                "",
                optimized_prompt,
                "",
                "---",
                "",
            ]

        # ── Round 1 Responses ─────────────────────────────────────────────────
        lines += ["## Round 1 Responses", ""]

        if round1.get("claude"):
            lines += ["### 🟠 Claude", "", round1["claude"], ""]
        if round1.get("gemini"):
            lines += ["### 🔵 Gemini", "", round1["gemini"], ""]
        if round1.get("gpt"):
            lines += ["### 🟢 GPT", "", round1["gpt"], ""]

        lines += ["---", ""]

        # ── Perplexity Audit ──────────────────────────────────────────────────
        audit_msgs = [
            m for m in transcript.messages
            if m.get("round") == "audit" and m.get("role") == "assistant" and m.get("sender") == "Perplexity"
        ]
        audit_text = (audit_msgs[-1].get("content") or "").strip() if audit_msgs else ""
        lines += [
            "## Perplexity Audit",
            "*Fact-check findings — live web*",
            "",
        ]
        if audit_text:
            lines += [audit_text, ""]
        else:
            lines += ["*No Perplexity audit in this transcript.*", ""]
        lines += ["---", ""]

        # ── Synthesis ─────────────────────────────────────────────────────────
        if synthesis_text:
            lines += [
                "## Synthesis",
                "*Claude · incorporating all rounds*",
                "",
                self._strip_headings(synthesis_text),
                "",
                "---",
                "",
            ]

        # ── Footer ────────────────────────────────────────────────────────────
        lines += self._footer()

        return "\n".join(lines)

    def _synthesis_doc(self, transcript: Transcript, config: dict) -> str:
        """Build the synthesis-only markdown document."""
        date = datetime.now().strftime("%B %d, %Y")
        title = config.get("session_title", "ai-roundtable Session")
        optimized_prompt = config.get("optimized_prompt", "")

        synthesis_msgs = [
            m for m in transcript.messages
            if m.get("round") == "synthesis" and m["role"] == "assistant"
        ]
        synthesis_text = synthesis_msgs[-1]["content"] if synthesis_msgs else ""

        lines = []

        # ── Header ────────────────────────────────────────────────────────────
        lines += [
            "# ai-roundtable — Synthesis",
            f"*{title}*",
            f"*{date}*",
            "",
            "---",
            "",
        ]

        # ── Opening Prompt ────────────────────────────────────────────────────
        if optimized_prompt:
            lines += [
                "## Opening Prompt",
                "",
                optimized_prompt,
                "",
                "---",
                "",
            ]

        # ── Synthesis ─────────────────────────────────────────────────────────
        if synthesis_text:
            lines += [
                "## Synthesis",
                "*Claude · incorporating Claude, Gemini, and GPT*",
                "",
                self._strip_headings(synthesis_text),
                "",
                "---",
                "",
            ]

        # ── Footer ────────────────────────────────────────────────────────────
        lines += self._footer()

        return "\n".join(lines)

    def _prompt_doc(self, transcript: Transcript, config: dict) -> str:
        """Build the optimized-prompt-only markdown document."""
        date = datetime.now().strftime("%B %d, %Y")
        title = config.get("session_title", "ai-roundtable Session")
        optimized_prompt = config.get("optimized_prompt", "")

        lines = [
            "# ai-roundtable — Optimized Prompt",
            f"*{title}*",
            f"*{date}*",
            "",
            "---",
            "",
            optimized_prompt,
            "",
            "---",
            "",
        ]
        lines += self._footer()
        return "\n".join(lines)

    def _strip_headings(self, text: str) -> str:
        """
        Remove leading markdown heading lines (starting with #) from model output.
        Prevents double-heading when Claude opens its synthesis with its own ## header.
        """
        return "\n".join(
            line for line in text.split("\n") if not line.startswith("#")
        ).strip()

    def _footer(self) -> list:
        return [
            "*Generated by ai-roundtable*",
            "*Putting the best frontier minds to work.*",
            "*github.com/JSTcurious/ai-roundtable*",
        ]
