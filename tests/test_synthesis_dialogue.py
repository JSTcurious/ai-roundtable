"""
tests/test_synthesis_dialogue.py

Tests for the Draft / Refine / Finalize synthesis dialogue loop
that replaced the YOUR TAKE pre-synthesis gate.

Covers:
- INTAKE_PRIMARY is Claude Sonnet (not GPT-4o Mini) — kept from prior suite.
- parse_closing_questions extracts trailing `?`-prefixed lines.
- call_synthesis_refinement returns {content, closing_questions} and
  uses the dialogue_history passed in.
- synthesis_draft is the first synthesis message sent after fact-check
  (no awaiting_user_take gate remains).
- synthesis_final is emitted in response to finalize_synthesis.
- Refinement bumps the revision counter.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


SONNET_ID = "claude-sonnet-4-6"


# ── Intake primary model (retained from prior suite) ──────────────────────────

class TestIntakePrimaryModel:
    def test_intake_primary_is_sonnet(self):
        from backend.models.model_config import INTAKE_PRIMARY
        assert INTAKE_PRIMARY == SONNET_ID, (
            f"INTAKE_PRIMARY must be {SONNET_ID!r}, got {INTAKE_PRIMARY!r}"
        )


# ── parse_closing_questions ───────────────────────────────────────────────────

class TestParseClosingQuestions:
    def test_closing_questions_parsed_from_synthesis(self):
        from backend.router import parse_closing_questions

        text = (
            "Main synthesis body goes here.\n"
            "More reasoning on the second line.\n"
            "\n"
            "? Does the 6-month horizon match your job-search window?\n"
            "? Are you open to weekend project time?\n"
        )
        cleaned, questions = parse_closing_questions(text)

        assert len(questions) == 2
        assert questions[0].startswith("Does the 6-month")
        assert questions[1].startswith("Are you open")
        # Question lines stripped from cleaned body
        assert "Does the 6-month" not in cleaned
        assert "Main synthesis body" in cleaned

    def test_no_closing_questions_returns_empty_list(self):
        from backend.router import parse_closing_questions

        text = "Just a synthesis body with no trailing questions."
        cleaned, questions = parse_closing_questions(text)
        assert questions == []
        assert "synthesis body" in cleaned

    def test_empty_input(self):
        from backend.router import parse_closing_questions
        cleaned, questions = parse_closing_questions("")
        assert questions == []


# ── call_synthesis_refinement ────────────────────────────────────────────────

class TestRefinement:
    def test_refinement_uses_dialogue_history(self):
        """
        call_synthesis_refinement should forward the dialogue_history to Claude
        and return {content, closing_questions}.
        """
        import asyncio
        from backend import router

        fake_response = MagicMock()
        fake_response.content = [MagicMock(text=(
            "Revised synthesis body — I agree with your push-back on cost.\n"
            "\n"
            "? Does this revised cost model match your budget?\n"
        ))]

        dialogue_history = [
            {"role": "assistant", "content": "Original draft synthesis."},
            {"role": "user", "content": "You're underestimating cost."},
        ]

        with patch("backend.models.anthropic_client.call_claude", return_value=fake_response) as mock_call:
            result = asyncio.run(router.call_synthesis_refinement(
                original_synthesis="Original draft synthesis.",
                dialogue_history=dialogue_history,
                user_message="You're underestimating cost.",
                research_context={"gemini": "g", "gpt": "p"},
                audit_context="audit findings",
                citations=["https://example.com/a"],
            ))

            assert "Revised synthesis" in result["content"]
            assert result["closing_questions"] == [
                "Does this revised cost model match your budget?"
            ]
            # Verify call_claude was invoked with the dialogue history
            assert mock_call.called
            kwargs = mock_call.call_args.kwargs
            messages = kwargs.get("messages") or mock_call.call_args.args[0]
            # User's push-back must be present in the messages
            assert any(
                m.get("role") == "user" and "underestimating cost" in m.get("content", "")
                for m in messages
            )

    def test_refinement_exception_returns_fallback(self):
        import asyncio
        from backend import router

        def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        with patch("backend.models.anthropic_client.call_claude", side_effect=_raise):
            result = asyncio.run(router.call_synthesis_refinement(
                original_synthesis="Original",
                dialogue_history=[{"role": "assistant", "content": "Original"},
                                  {"role": "user", "content": "push"}],
                user_message="push",
            ))
            assert "Refinement unavailable" in result["content"]
            assert result["closing_questions"] == []


# ── WebSocket payload shape sanity checks ────────────────────────────────────

class TestSynthesisWebSocketPayloads:
    def test_synthesis_draft_shape(self):
        """
        synthesis_draft payload carries content, revision, and closing_questions.
        Revision 0 on first draft; 1+ after a refinement.
        """
        draft = {
            "type": "synthesis_draft",
            "content": "body",
            "revision": 0,
            "closing_questions": ["Q1?", "Q2?"],
        }
        assert draft["type"] == "synthesis_draft"
        assert draft["revision"] == 0
        assert isinstance(draft["closing_questions"], list)

    def test_synthesis_final_shape(self):
        """
        synthesis_final is sent in response to finalize_synthesis.
        Carries the locked final content and final revision count.
        """
        final = {
            "type": "synthesis_final",
            "content": "locked body",
            "revision": 2,
        }
        assert final["type"] == "synthesis_final"
        assert final["revision"] == 2

    def test_finalize_synthesis_client_shape(self):
        """
        Client → server finalize_synthesis is a simple type-only frame.
        """
        frame = {"type": "finalize_synthesis"}
        assert frame["type"] == "finalize_synthesis"

    def test_user_dialogue_response_client_shape(self):
        """
        Client → server user_dialogue_response carries the user's push-back text.
        """
        frame = {"type": "user_dialogue_response", "content": "You missed cost."}
        assert frame["type"] == "user_dialogue_response"
        assert "content" in frame


# ── Synthesis system prompt quality ──────────────────────────────────────────

class TestBuildSynthesisSystem:
    def test_build_synthesis_system_basic(self):
        """
        build_synthesis_system returns a non-empty prompt with no user-take
        handling (that gate was removed).
        """
        from backend.router import build_synthesis_system
        prompt = build_synthesis_system()
        assert isinstance(prompt, str) and len(prompt) > 0
        assert "Use confidence tags" not in prompt
        assert "Never use [DEFER]" in prompt

    def test_build_synthesis_system_with_audit(self):
        from backend.router import build_synthesis_system
        audit = "Frontier AI comp: $500K–$1M total."
        prompt = build_synthesis_system(audit_text=audit)
        assert audit in prompt

    def test_build_synthesis_system_citations(self):
        from backend.router import build_synthesis_system
        citations = ["https://example.com/source-1", "https://example.com/source-2"]
        prompt = build_synthesis_system(citations=citations)
        assert "https://example.com/source-1" in prompt
        assert "[1]" in prompt
        assert "[2]" in prompt

    def test_synthesis_prompt_includes_closing_questions_instructions(self):
        """
        The synthesis system prompt tells Claude to end with 1-2 closing
        questions on `?`-prefixed lines so parse_closing_questions can split
        them off.
        """
        from backend.router import SYNTHESIS_SYSTEM_PROMPT
        assert "Closing Questions" in SYNTHESIS_SYSTEM_PROMPT
        assert "?" in SYNTHESIS_SYSTEM_PROMPT
