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


# ── Synthesis receives the panel and the brief ───────────────────────────────

class TestSynthesisInputs:
    def test_build_synthesis_system_includes_wrapped_round1(self):
        from backend.router import build_synthesis_system
        prompt = build_synthesis_system(
            round1_responses={"gemini": "GEMINI_TEXT", "grok": "GROK_TEXT"}
        )
        assert '<research_response source="Gemini">' in prompt
        assert '<research_response source="Grok">' in prompt
        assert "GEMINI_TEXT" in prompt and "GROK_TEXT" in prompt

    def test_refinement_gets_brief_and_full_wrapped_research(self):
        import asyncio
        from backend import router

        long_text = "x" * 5000 + "END_MARKER"
        fake = MagicMock()
        fake.content = [MagicMock(text="Revised.")]
        with patch("backend.models.anthropic_client.call_claude", return_value=fake) as mock_call:
            asyncio.run(router.call_synthesis_refinement(
                original_synthesis="Draft.",
                dialogue_history=[
                    {"role": "assistant", "content": "Draft."},
                    {"role": "user", "content": "push"},
                ],
                user_message="push",
                research_context={"gpt": long_text},
                optimized_prompt="THE BRIEF",
            ))
        kwargs = mock_call.call_args.kwargs
        assert kwargs["messages"][0] == {"role": "user", "content": "THE BRIEF"}
        assert '<research_response source="Gpt">' in kwargs["system"]
        assert "END_MARKER" in kwargs["system"]


class TestSessionSynthesisWiring:
    """Drive /ws/session with mocked models and inspect what synthesis receives."""

    BRIEF = "Career track and immigration track. TRACK PARITY REQUIRED: 2 tracks."

    def _run_session(self, refine: bool = False, audit_provider: str = "primary",
                     audit_text: str = "AUDIT"):
        from fastapi.testclient import TestClient
        from backend import main

        def r1(text):
            return AsyncMock(return_value=(text, "primary"))

        synth = AsyncMock(return_value="THE VERDICT\nbody\n\n? Does this fit?")
        refinement = AsyncMock(return_value={"content": "Revised", "closing_questions": []})
        critique = AsyncMock(return_value="- critique")
        self.critique = critique
        with patch.object(main, "call_research_gemini_async", r1("GEMINI_R1")), \
             patch.object(main, "call_research_gpt_async", r1("GPT_R1")), \
             patch.object(main, "call_research_grok_async", r1("GROK_R1")), \
             patch.object(main, "call_research_claude_async", r1("CLAUDE_R1")), \
             patch.object(main, "perplexity_research", MagicMock(return_value="pre")), \
             patch.object(main, "audit_with_fallback", MagicMock(return_value=(audit_text, audit_provider, []))), \
             patch.object(main, "call_self_critique", critique), \
             patch.object(main, "call_synthesis_async", synth), \
             patch.object(main, "call_synthesis_refinement", refinement):
            client = TestClient(main.app)
            with client.websocket_connect("/ws/session") as ws:
                ws.send_json({
                    "prompt": "raw user prompt",
                    "session_config": {"tier": "smart", "optimized_prompt": self.BRIEF},
                    "history": [],
                })
                received = []

                def until(msg_type):
                    while True:
                        received.append(ws.receive_json())
                        if received[-1]["type"] == msg_type:
                            return

                until("prompt_review")
                ws.send_json({"type": "prompt_confirmed"})
                until("synthesis_draft")
                if refine:
                    ws.send_json({"type": "user_dialogue_response", "content": "push back"})
                    until("synthesis_draft")
                ws.send_json({"type": "finalize_synthesis"})
                until("session_complete")
        self.received = received
        return synth, refinement

    def test_synthesis_gets_brief_not_raw_prompt(self):
        synth, _ = self._run_session()
        _model, messages, _system, _tier = synth.call_args.args
        assert "TRACK PARITY REQUIRED" in messages[0]["content"]
        assert "raw user prompt" not in messages[0]["content"]

    def test_synthesis_system_contains_all_four_panel_responses(self):
        synth, _ = self._run_session()
        system = synth.call_args.args[2]
        for source, text in [("Gemini", "GEMINI_R1"), ("Gpt", "GPT_R1"),
                             ("Grok", "GROK_R1"), ("Claude", "CLAUDE_R1")]:
            assert f'<research_response source="{source}">' in system
            assert text in system

    def test_refinement_gets_brief(self):
        _, refinement = self._run_session(refine=True)
        assert "TRACK PARITY REQUIRED" in refinement.call_args.kwargs["optimized_prompt"]

    def test_synthesis_uses_primary_model_even_when_audit_corrects_panel(self):
        # Vocabulary that the removed keyword router sent to GPT.
        from backend.models.model_config import SYNTHESIS_ANALYTICAL
        synth, _ = self._run_session(
            audit_text="GPT's pricing is outdated and incorrect; v5 was released as of 2026."
        )
        assert synth.call_args.args[0] == SYNTHESIS_ANALYTICAL

    def test_self_critique_gets_brief(self):
        self._run_session()
        assert "TRACK PARITY REQUIRED" in self.critique.call_args.kwargs["optimized_prompt"]

    @pytest.mark.parametrize("provider,expected_avail", [
        ("primary", "primary"), ("fallback1", "fallback"), ("emergency", "unavailable"),
    ])
    def test_factcheck_payload_reports_configured_model(self, provider, expected_avail):
        from backend.models import model_config as mc
        self._run_session(audit_provider=provider)
        payload = next(m for m in self.received if m["type"] == "perplexity_complete")
        expected_model = {
            "primary": mc.FACTCHECK_PRIMARY,
            "fallback1": mc.FACTCHECK_FALLBACK1,
            "emergency": "unavailable",
        }[provider]
        assert payload["factcheck_model_used"] == expected_model
        assert payload["factcheck_availability"] == expected_avail


# ── Advisor sees the executor's full context ─────────────────────────────────

def _fake_response(text):
    r = MagicMock()
    r.content = [MagicMock(text=text)]
    r.choices = [MagicMock(message=MagicMock(content=text))]
    r.text = text
    return r


class TestAdvisorContext:
    @pytest.mark.parametrize("module,fn,smart", [
        ("backend.models.anthropic_client", "call_claude", "call_claude_smart"),
        ("backend.models.openai_client",    "call_gpt",    "call_gpt_smart"),
        ("backend.models.grok_client",      "call_grok",   "call_grok_smart"),
        ("backend.models.google_client",    "call_gemini", "call_gemini_smart"),
    ])
    def test_advisor_gets_system_prompt_and_full_conversation(self, module, fn, smart):
        import importlib
        from backend.router import ADVISOR_REVIEW_PROMPT

        client = importlib.import_module(module)
        messages = [
            {"role": "user", "content": "earlier turn"},
            {"role": "assistant", "content": "earlier reply"},
            {"role": "user", "content": "THE BRIEF"},
        ]
        responses = [_fake_response("DRAFT"), _fake_response("FINAL")]
        with patch(f"{module}.{fn}", side_effect=responses) as mocked:
            result = getattr(client, smart)(messages, system="ROLE AND FORMAT RULES")

        assert result["advisor_text"] == "FINAL"
        advisor_call = mocked.call_args_list[1].kwargs
        assert advisor_call["system"] == "ROLE AND FORMAT RULES"
        assert advisor_call["model"] == client._ADVISOR_MODEL
        assert advisor_call["messages"] == messages + [
            {"role": "assistant", "content": "DRAFT"},
            {"role": "user", "content": ADVISOR_REVIEW_PROMPT},
        ]


class TestSelfCritiqueContext:
    def test_brief_reaches_the_critique_prompt(self):
        import asyncio
        from backend import router

        fake = MagicMock()
        fake.content = [MagicMock(text="UNSUPPORTED CLAIMS\nNone.")]
        with patch("backend.models.anthropic_client.call_claude", return_value=fake) as mock_call:
            asyncio.run(router.call_self_critique(
                round1_responses={"gpt": "answer"},
                perplexity_findings="audit",
                optimized_prompt="TRACK PARITY REQUIRED: two tracks",
            ))
        content = mock_call.call_args.kwargs["messages"][0]["content"]
        assert "TRACK PARITY REQUIRED: two tracks" in content
        assert '<research_response source="Gpt">' in content
