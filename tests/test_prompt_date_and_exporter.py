"""
tests/test_prompt_date_and_exporter.py

- Every pipeline stage after intake is told today's date.
- The panel-status note names unavailable models.
- The markdown export includes Grok and names the real synthesizer.
"""

import asyncio
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

FIXED = date(2026, 11, 27)
FIXED_TEXT = "November 27, 2026 (2026-11-27)"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    from backend import router
    monkeypatch.setattr(router, "_today", lambda: FIXED)


def _fake_claude(text="ok"):
    r = MagicMock()
    r.content = [MagicMock(text=text)]
    return r


class TestTodaysDate:
    @pytest.mark.parametrize("lab", ["claude", "gpt", "gemini", "grok"])
    def test_round1_prompts(self, lab):
        from backend.router import get_round1_system_prompt
        assert FIXED_TEXT in get_round1_system_prompt(lab)

    def test_synthesis_system(self):
        from backend.router import build_synthesis_system
        assert FIXED_TEXT in build_synthesis_system()

    def test_self_critique_system(self):
        from backend import router
        with patch("backend.models.anthropic_client.call_claude", return_value=_fake_claude()) as m:
            asyncio.run(router.call_self_critique({"gpt": "x"}, "audit"))
        assert FIXED_TEXT in m.call_args.kwargs["system"]

    def test_refinement_system(self):
        from backend import router
        with patch("backend.models.anthropic_client.call_claude", return_value=_fake_claude()) as m:
            asyncio.run(router.call_synthesis_refinement(
                original_synthesis="Draft.",
                dialogue_history=[{"role": "assistant", "content": "Draft."},
                                  {"role": "user", "content": "push"}],
                user_message="push",
            ))
        assert FIXED_TEXT in m.call_args.kwargs["system"]

    def test_perplexity_audit_prompt(self):
        from backend.models.perplexity_client import _build_audit_prompt
        for tier in ("smart", "deep"):
            assert FIXED_TEXT in _build_audit_prompt({"gpt": "x"}, "r", tier)

    def test_perplexity_research_prompt(self):
        from backend.models import perplexity_client
        client = MagicMock()
        client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="found"))]
        with patch.object(perplexity_client, "_get_client", return_value=client):
            perplexity_client.research("topic", tier="smart")
        prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        assert FIXED_TEXT in prompt


class TestPanelStatusNote:
    def test_names_unavailable_models(self):
        from backend.router import panel_status_note
        note = panel_status_note(["gemini", "grok"])
        assert "Unavailable this session: Gemini, Grok" in note
        assert "all four" in note

    def test_empty_when_everyone_answered(self):
        from backend.router import panel_status_note
        assert panel_status_note([]) == ""
        assert panel_status_note(None) == ""


class TestExporter:
    def _transcript(self):
        from backend.transcript import Transcript
        t = Transcript()
        t.add_user_message("prompt")
        for sender in ("Gemini", "GPT", "Grok", "Claude"):
            t.add_model_message(sender, f"{sender} round-one text", round="round1")
        t.add_model_message("Perplexity", "audit", round="audit")
        t.add_model_message("Claude", "THE VERDICT body", round="synthesis")
        return t

    def test_full_export_includes_grok(self):
        from backend.exporter import Exporter
        md = Exporter().to_markdown(self._transcript(), {}, mode="full")
        assert "### ⚫ Grok" in md
        assert "Grok round-one text" in md

    @pytest.mark.parametrize("model_id,byline", [
        ("gpt-5.4", "*GPT · incorporating all rounds*"),
        ("claude-opus-4-6", "*Claude · incorporating all rounds*"),
        ("qwen/qwen-2.5-72b-instruct", "*Qwen · incorporating all rounds*"),
        (None, "*Incorporating all rounds*"),
    ])
    @pytest.mark.parametrize("mode", ["full", "synthesis"])
    def test_synthesis_byline_names_real_model(self, model_id, byline, mode):
        from backend.exporter import Exporter
        md = Exporter().to_markdown(self._transcript(), {"synthesis_model": model_id}, mode=mode)
        assert byline in md
        if model_id and "claude" not in model_id:
            assert "Claude · incorporating" not in md
