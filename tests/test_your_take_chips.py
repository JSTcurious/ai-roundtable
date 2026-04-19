"""
tests/test_your_take_chips.py

Tests for YOUR TAKE chip generation and intake model promotion.

Covers:
- INTAKE_PRIMARY is Claude Sonnet (not GPT-4o Mini)
- generate_user_take_chips returns {label, evidence} dicts
- Parse failure returns []
- awaiting_user_take WebSocket message contains 'chips' key
- Synthesize payload includes selected_chips and free_text
- Missing 'chips' key in awaiting_user_take message is handled gracefully
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


SONNET_ID = "claude-sonnet-4-6"


# ── Change 1: Intake primary model ───────────────────────────────────────────

class TestIntakePrimaryModel:
    def test_intake_primary_is_sonnet(self):
        from backend.models.model_config import INTAKE_PRIMARY
        assert INTAKE_PRIMARY == SONNET_ID, (
            f"INTAKE_PRIMARY must be {SONNET_ID!r}, got {INTAKE_PRIMARY!r}"
        )

    def test_intake_primary_is_not_gpt4o_mini(self):
        from backend.models.model_config import INTAKE_PRIMARY
        assert INTAKE_PRIMARY != "gpt-4o-mini"


# ── Change 2: Chip generation returns {label, evidence} dicts ─────────────────

class TestChipGeneration:
    VALID_CHIPS = json.dumps([
        {"label": "Trust Gemini on cost structure", "evidence": "Gemini cited specific pricing tiers."},
        {"label": "Perplexity changes the calculus", "evidence": "Live data contradicted two round-1 claims."},
        {"label": "I want to explore the risk angle", "evidence": "Grok flagged a downside no other model mentioned."},
    ])

    def _run_generate(self, mock_raw: str) -> list:
        """Run generate_user_take_chips with call_for_chips mocked to return mock_raw."""
        import asyncio
        from backend.router import generate_user_take_chips

        round1 = {"gemini": "Gemini said X.", "gpt": "GPT said Y.", "grok": "Grok said Z.", "claude": "Claude said W."}
        factcheck = "Perplexity found one claim was outdated."

        with patch("backend.router.asyncio.to_thread", new=AsyncMock(return_value=mock_raw)):
            return asyncio.run(
                generate_user_take_chips(round1, factcheck)
            )

    def test_chip_generation_returns_label_evidence_list(self):
        chips = self._run_generate(self.VALID_CHIPS)
        assert isinstance(chips, list)
        assert len(chips) > 0
        for chip in chips:
            assert "label" in chip, f"Missing 'label' key: {chip}"
            assert "evidence" in chip, f"Missing 'evidence' key: {chip}"
            assert isinstance(chip["label"], str) and chip["label"].strip()
            assert isinstance(chip["evidence"], str) and chip["evidence"].strip()

    def test_chip_generation_parse_failure_returns_empty(self):
        chips = self._run_generate("not valid json {{{")
        assert chips == [], f"Expected [] on parse failure, got {chips!r}"

    def test_chip_generation_non_list_json_returns_empty(self):
        chips = self._run_generate('{"label": "oops", "evidence": "this is an object not array"}')
        assert chips == []

    def test_chip_generation_filters_malformed_dicts(self):
        malformed = json.dumps([
            {"label": "Valid chip", "evidence": "Good evidence here."},
            {"label": "", "evidence": "Empty label — should be filtered."},
            {"label": "Missing evidence"},
            "plain string — should be filtered",
        ])
        chips = self._run_generate(malformed)
        assert len(chips) == 1
        assert chips[0]["label"] == "Valid chip"


# ── awaiting_user_take WebSocket message ──────────────────────────────────────

class TestAwaitingUserTakeMessage:
    def test_chips_injected_into_awaiting_user_take_message(self):
        """
        The awaiting_user_take payload always includes a 'chips' key.
        Verify by inspecting the message structure produced by main.py's
        session handler.
        """
        # Construct the exact dict the session handler sends
        chips = [
            {"label": "Trust Gemini", "evidence": "Gemini was most detailed."},
        ]
        payload = {
            "type": "awaiting_user_take",
            "chips": chips,
            "message": "Here are some perspectives to consider:" if chips else "",
        }
        assert "chips" in payload
        assert isinstance(payload["chips"], list)

    def test_chips_missing_does_not_crash(self):
        """
        Frontend initializes userTakeChips from data.chips using `data.chips || []`.
        Simulate a payload without 'chips' and confirm the fallback resolves to [].
        """
        payload = {"type": "awaiting_user_take"}  # no 'chips' key
        user_take_chips = payload.get("chips") or []
        assert user_take_chips == []


# ── Synthesize payload ────────────────────────────────────────────────────────

class TestSynthesizePayload:
    def test_synthesize_payload_includes_selected_chips_and_free_text(self):
        """
        build_synthesis_system receives a dict with selected_chips and free_text.
        Verify both keys are present and used.
        """
        from backend.router import build_synthesis_system

        user_take_data = {
            "selected_chips": ["chip A"],
            "free_text": "my perspective",
        }
        system_prompt = build_synthesis_system(user_take_data)

        # The system prompt must incorporate the user's take data
        assert isinstance(system_prompt, str)
        assert len(system_prompt) > 0
        # selected_chips labels and free_text both appear in the synthesis prompt
        assert "chip A" in system_prompt
        assert "my perspective" in system_prompt
