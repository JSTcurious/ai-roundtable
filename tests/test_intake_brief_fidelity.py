"""
tests/test_intake_brief_fidelity.py

Every fact the user stated must reach the research panel.
Spec: docs/INTAKE_BRIEF_FIDELITY_SPEC.md (AC numbers below refer to it).
"""

import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

from backend.intake import IntakeSession
from backend.models.intake_decision import IntakeDecision
from backend.router import (
    BRIEF_FACT_CARRYOVER_RULE,
    ORIGINAL_PROMPT_HEADER,
    STATED_FACTS_HEADER,
    STATED_FACTS_MAX_CHARS,
    STATED_FACTS_MAX_LINES,
    STATED_FACTS_RULE,
    build_stated_facts_block,
    clean_stated_facts,
)

CONSULTANCY_PROMPT = (
    "I run a 3-person data consultancy. A client offers a $180k fixed-price "
    "contract to build a data platform in 4 months, but we've never done a "
    "fixed-price deal. Should we accept, counter with time-and-materials, or "
    "decline?"
)
FACTS = [
    "We are a 3-person data consultancy",
    "$180k fixed-price contract, 4 months",
    "We've never done a fixed-price deal",
]


def _closing_decision(**overrides) -> IntakeDecision:
    data = {
        "needs_clarification": False,
        "optimized_prompt": "Should the firm accept the contract?",
        "tier": "smart",
        "output_intent": "A clear recommendation",
        "stated_facts": FACTS,
    }
    data.update(overrides)
    return IntakeDecision(**data)


# ── AC1 — per-turn instruction carries the prompt verbatim and the rule ──────

class TestCombinedPrompt:
    def test_contains_original_prompt_verbatim_and_rule(self):
        s = IntakeSession()
        s._original_prompt = CONSULTANCY_PROMPT
        s._qa_history = [("Tell me a bit about yourself", "Co-founder, I lead delivery")]
        combined = s._build_combined_prompt()
        assert CONSULTANCY_PROMPT in combined
        assert BRIEF_FACT_CARRYOVER_RULE in combined
        assert "verbatim" in combined.split(CONSULTANCY_PROMPT)[0]

    def test_rule_names_self_stated_limits(self):
        assert "never done" in BRIEF_FACT_CARRYOVER_RULE
        assert "user's wording" in BRIEF_FACT_CARRYOVER_RULE


# ── AC2 — system prompt has the rule, the new part and the schema field ──────

class TestSystemPrompt:
    def test_system_prompt_contains_rule_and_facts_part(self):
        from backend.models.openai_client import _build_intake_system_prompt
        sp = _build_intake_system_prompt()
        assert BRIEF_FACT_CARRYOVER_RULE in sp
        assert STATED_FACTS_RULE in sp
        assert "THE FACTS AS STATED" in sp
        assert '"stated_facts": [list of strings]' in sp

    def test_all_intake_callers_share_the_prompt(self):
        # GPT fallback uses the module-level copy; it must include the rule too.
        from backend.models.openai_client import _INTAKE_SYSTEM
        assert BRIEF_FACT_CARRYOVER_RULE in _INTAKE_SYSTEM


# ── AC3 — completed config carries original_prompt and stated_facts ──────────

class TestSessionConfig:
    def test_schema_defaults_to_empty_list(self):
        d = IntakeDecision(needs_clarification=True, tier="smart")
        assert d.stated_facts == []

    def test_completed_config_has_original_prompt_and_facts(self):
        s = IntakeSession()
        s._original_prompt = CONSULTANCY_PROMPT
        s._background_answered = True
        s.questions_asked = 5  # past every domain minimum
        result = s._route_decision(_closing_decision(), context_text=CONSULTANCY_PROMPT)
        assert result["status"] == "complete"
        cfg = result["config"]
        assert cfg["original_prompt"] == CONSULTANCY_PROMPT
        assert cfg["stated_facts"] == FACTS


# ── AC4 — the facts block ─────────────────────────────────────────────────────

class TestFactsBlock:
    def test_lists_facts_under_header(self):
        block = build_stated_facts_block(FACTS, CONSULTANCY_PROMPT, "brief")
        assert STATED_FACTS_HEADER in block
        for f in FACTS:
            assert f"- {f}" in block
        assert ORIGINAL_PROMPT_HEADER not in block

    def test_falls_back_to_verbatim_prompt(self):
        block = build_stated_facts_block([], CONSULTANCY_PROMPT, "brief")
        assert ORIGINAL_PROMPT_HEADER in block
        assert CONSULTANCY_PROMPT in block

    def test_nothing_when_prompt_already_in_brief(self):
        assert build_stated_facts_block([], CONSULTANCY_PROMPT, f"x {CONSULTANCY_PROMPT} y") == ""

    def test_nothing_when_neither_present(self):
        assert build_stated_facts_block(None, "", "brief") == ""

    def test_cleaning_drops_blanks_and_caps(self):
        assert clean_stated_facts(["  a  ", "", "   ", 3, None, "b\n c"]) == ["a", "b c"]
        assert clean_stated_facts("not a list") == []
        long = clean_stated_facts(["x" * 1000] * 50)
        assert len(long) == STATED_FACTS_MAX_LINES
        assert all(len(f) == STATED_FACTS_MAX_CHARS for f in long)

    def test_enrich_prompt_appends_block(self):
        from backend.main import _enrich_prompt
        cfg = {"stated_facts": FACTS, "original_prompt": CONSULTANCY_PROMPT}
        out = _enrich_prompt("THE BRIEF", cfg)
        assert out.startswith("THE BRIEF")
        assert "We've never done a fixed-price deal" in out
        assert "never done" not in _enrich_prompt("THE BRIEF", cfg, include_facts=False)

    def test_enrich_prompt_old_config_unchanged(self):
        from backend.main import _enrich_prompt
        assert _enrich_prompt("THE BRIEF", {}) == "THE BRIEF"


# ── AC5 — review gate: user-edited facts reach all four panel models ─────────

class TestReviewGate:
    BRIEF = "Should the firm accept the contract?"

    def _run(self, review_reply: dict, config_extra: dict | None = None):
        from fastapi.testclient import TestClient
        from backend import main

        research = {
            lab: AsyncMock(return_value=(f"{lab.upper()}_R1", "primary"))
            for lab in ("gemini", "gpt", "grok", "claude")
        }
        perplexity = MagicMock(return_value="pre")
        config = {"tier": "smart", "optimized_prompt": self.BRIEF,
                  "original_prompt": CONSULTANCY_PROMPT, "stated_facts": FACTS}
        config.update(config_extra or {})
        with patch.object(main, "call_research_gemini_async", research["gemini"]), \
             patch.object(main, "call_research_gpt_async", research["gpt"]), \
             patch.object(main, "call_research_grok_async", research["grok"]), \
             patch.object(main, "call_research_claude_async", research["claude"]), \
             patch.object(main, "perplexity_research", perplexity), \
             patch.object(main, "audit_with_fallback",
                          MagicMock(return_value=("AUDIT", "primary", []))), \
             patch.object(main, "call_self_critique", AsyncMock(return_value="- c")), \
             patch.object(main, "call_synthesis_async",
                          AsyncMock(return_value="THE VERDICT\nbody")):
            client = TestClient(main.app)
            with client.websocket_connect("/ws/session") as ws:
                ws.send_json({"prompt": self.BRIEF, "session_config": config, "history": []})
                received = []

                def until(msg_type):
                    while True:
                        received.append(ws.receive_json())
                        if received[-1]["type"] == msg_type:
                            return received[-1]

                review = until("prompt_review")
                ws.send_json(review_reply)
                until("synthesis_draft")
                ws.send_json({"type": "finalize_synthesis"})
                until("session_complete")
        panel_inputs = {
            lab: mock.call_args.args[0][-1]["content"] for lab, mock in research.items()
        }
        return review, panel_inputs, perplexity.call_args.args[0]

    def test_review_message_carries_facts_and_brief_without_block(self):
        review, _, _ = self._run({"type": "prompt_confirmed"})
        assert review["stated_facts"] == FACTS
        assert STATED_FACTS_HEADER not in review["optimized_prompt"]

    def test_edited_facts_reach_all_four_models_and_perplexity(self):
        edited = ["We are a 3-person data consultancy",
                  "We've never done a fixed-price deal",
                  "The client already rejected T&M once"]
        _, panel, pplx = self._run({"type": "prompt_confirmed", "stated_facts": edited})
        for lab, text in panel.items():
            assert STATED_FACTS_HEADER in text, lab
            assert "The client already rejected T&M once" in text, lab
            assert "$180k fixed-price contract, 4 months" not in text, lab  # removed by user
        assert "The client already rejected T&M once" in pplx

    def test_old_client_keeps_intake_facts(self):
        _, panel, _ = self._run({"type": "prompt_confirmed"})
        for text in panel.values():
            assert "We've never done a fixed-price deal" in text

    def test_correction_reaches_all_four_models(self):
        # Before this change the transcript was built before the gate, so the
        # four panel models never saw a correction typed at review.
        _, panel, _ = self._run({"type": "prompt_adjusted",
                                 "adjustment": "Runway is 5 months", "stated_facts": FACTS})
        for lab, text in panel.items():
            assert "User correction: Runway is 5 months" in text, lab

    def test_no_facts_falls_back_to_verbatim_prompt(self):
        _, panel, _ = self._run({"type": "prompt_confirmed", "stated_facts": []},
                                config_extra={"stated_facts": []})
        # The verbatim prompt reaches the panel with its amount tokenized
        # (PRIVACY_SECURITY_SPEC §4.1, Q2: magnitude hint).
        tokenized = CONSULTANCY_PROMPT.replace("$180k", "[AMOUNT_1 ≈ $180K]")
        for text in panel.values():
            assert tokenized in text
            assert "$180k" not in text


# ── AC7 — the strings live only in router.py ──────────────────────────────────

class TestPromptLocation:
    def test_rule_text_not_inlined_elsewhere(self):
        root = pathlib.Path(__file__).resolve().parent.parent / "backend"
        needle = "FACT CARRY-OVER"
        hits = [p.relative_to(root).as_posix() for p in root.rglob("*.py")
                if needle in p.read_text(encoding="utf-8")]
        assert hits == ["router.py"]
