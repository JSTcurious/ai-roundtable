"""
tests/test_model_config.py

Tests for the two-tier model config layer (Task A).

Coverage:
    - Binary tier (smart/deep) for all four labs
    - No quick tier
    - Env var override
    - Factcheck token limits
    - Intake tier lock (always smart)
    - Validator safety (never raises, skips OpenRouter)
"""

import os
import importlib
import pytest

from backend.models.model_config import (
    get_executor_model,
    get_advisor_model,
    get_fallback_model,
    get_all_labs,
    get_factcheck_max_tokens,
)
from backend.router import get_tier_config


# ── Binary tier: smart ────────────────────────────────────────────────────────

class TestSmartTierModels:
    def test_executor_smart_gemini_is_non_empty(self):
        assert get_executor_model("smart", "gemini") != ""

    def test_executor_smart_gpt_is_non_empty(self):
        assert get_executor_model("smart", "gpt") != ""

    def test_executor_smart_grok_is_non_empty(self):
        assert get_executor_model("smart", "grok") != ""

    def test_executor_smart_claude_is_non_empty(self):
        assert get_executor_model("smart", "claude") != ""

    def test_advisor_smart_gemini_is_non_empty(self):
        assert get_advisor_model("smart", "gemini") != ""

    def test_advisor_smart_gpt_is_non_empty(self):
        assert get_advisor_model("smart", "gpt") != ""

    def test_advisor_smart_grok_is_non_empty(self):
        assert get_advisor_model("smart", "grok") != ""

    def test_advisor_smart_claude_is_non_empty(self):
        assert get_advisor_model("smart", "claude") != ""


# ── Binary tier: deep ─────────────────────────────────────────────────────────

class TestDeepTierModels:
    @pytest.mark.parametrize("lab", ["gemini", "gpt", "grok", "claude"])
    def test_deep_executor_equals_advisor(self, lab):
        """Deep tier has no executor/advisor split — single top model."""
        assert get_executor_model("deep", lab) == get_advisor_model("deep", lab)


# ── All labs ──────────────────────────────────────────────────────────────────

class TestGetAllLabs:
    def test_returns_four_labs(self):
        assert len(get_all_labs()) == 4

    def test_returns_all_expected_labs(self):
        assert get_all_labs() == ["gemini", "gpt", "grok", "claude"]

    def test_grok_included(self):
        assert "grok" in get_all_labs()

    def test_all_labs_have_smart_executor(self):
        for lab in get_all_labs():
            assert get_executor_model("smart", lab) != ""

    def test_all_labs_have_deep_model(self):
        for lab in get_all_labs():
            assert get_advisor_model("deep", lab) != ""


# ── No quick tier ─────────────────────────────────────────────────────────────

class TestNoQuickTier:
    def test_get_tier_config_quick_falls_back_to_smart(self):
        """Unknown/quick tier must default to smart — no KeyError or ValueError."""
        result = get_tier_config("quick")
        assert isinstance(result, dict)
        # Should return the same structure as smart
        smart_result = get_tier_config("smart")
        assert result == smart_result

    def test_no_quick_constant_in_model_config(self):
        """No QUICK constant should exist in model_config."""
        import backend.models.model_config as mc
        attrs = dir(mc)
        quick_attrs = [a for a in attrs if "QUICK" in a.upper() and not a.startswith("_")]
        assert quick_attrs == [], f"Found unexpected QUICK constants: {quick_attrs}"

    def test_unknown_tier_falls_back_to_smart(self):
        """Any unrecognised tier value must silently default to smart."""
        result = get_tier_config("invalid_tier")
        smart_result = get_tier_config("smart")
        assert result == smart_result


# ── Env var override ──────────────────────────────────────────────────────────

class TestEnvVarOverride:
    def test_research_gpt_deep_override(self, monkeypatch):
        """Setting RESEARCH_GPT_DEEP in env overrides the default."""
        monkeypatch.setenv("RESEARCH_GPT_DEEP", "test-model-x")

        # Reload model_config so the os.getenv() calls re-evaluate
        import backend.models.model_config as mc
        importlib.reload(mc)

        assert mc.get_advisor_model("deep", "gpt") == "test-model-x"

        # Reload again to restore defaults
        monkeypatch.delenv("RESEARCH_GPT_DEEP", raising=False)
        importlib.reload(mc)

    def test_research_claude_smart_executor_override(self, monkeypatch):
        """Setting RESEARCH_CLAUDE_SMART_EXECUTOR overrides the executor."""
        monkeypatch.setenv("RESEARCH_CLAUDE_SMART_EXECUTOR", "test-claude-executor")

        import backend.models.model_config as mc
        importlib.reload(mc)

        assert mc.get_executor_model("smart", "claude") == "test-claude-executor"

        monkeypatch.delenv("RESEARCH_CLAUDE_SMART_EXECUTOR", raising=False)
        importlib.reload(mc)


# ── Factcheck token limits — always deep ─────────────────────────────────────

class TestFactcheckTokenLimits:
    def test_smart_tier_returns_deep_max_tokens(self):
        """Smart tier now uses deep audit depth — fact-check is always deep."""
        from backend.models.model_config import FACTCHECK_DEEP_MAX_TOKENS
        assert get_factcheck_max_tokens("smart") == FACTCHECK_DEEP_MAX_TOKENS

    def test_deep_tier_returns_deep_max_tokens(self):
        from backend.models.model_config import FACTCHECK_DEEP_MAX_TOKENS
        assert get_factcheck_max_tokens("deep") == FACTCHECK_DEEP_MAX_TOKENS

    def test_unknown_tier_returns_deep_max_tokens(self):
        """Any tier value (incl. unknown) returns the deep limit — always 2000."""
        from backend.models.model_config import FACTCHECK_DEEP_MAX_TOKENS
        assert get_factcheck_max_tokens("quick") == FACTCHECK_DEEP_MAX_TOKENS
        assert get_factcheck_max_tokens("unknown") == FACTCHECK_DEEP_MAX_TOKENS

    def test_always_deep_value_is_2000(self):
        """The always-deep token budget must be 2000."""
        assert get_factcheck_max_tokens("smart") == 2000
        assert get_factcheck_max_tokens("deep") == 2000


# ── Intake tier lock (always smart) ──────────────────────────────────────────

class TestIntakeTierAssignment:
    def test_intake_system_prompt_states_always_smart(self):
        """Intake system prompt must instruct the model to always return smart."""
        from backend.models.openai_client import _build_intake_system_prompt
        prompt = _build_intake_system_prompt()
        assert "always return" in prompt.lower() and "smart" in prompt

    def test_intake_system_prompt_user_controls_tier(self):
        """Intake system prompt must state that the user controls tier via the session UI."""
        from backend.models.openai_client import _build_intake_system_prompt
        prompt = _build_intake_system_prompt()
        assert "user controls tier" in prompt.lower() or "session ui" in prompt.lower()

    def test_intake_system_prompt_no_deep_tier_option(self):
        """Intake system prompt must not offer deep as a tier option."""
        from backend.models.openai_client import _build_intake_system_prompt
        prompt = _build_intake_system_prompt()
        # "deep" must not appear as a tier choice (may appear in output_type examples)
        assert '"deep"' not in prompt and "'deep'" not in prompt

    def test_intake_system_prompt_no_quick_tier(self):
        """Intake system prompt must not reference quick tier as an option."""
        from backend.models.openai_client import _build_intake_system_prompt
        prompt = _build_intake_system_prompt()
        assert "quick" not in prompt.lower()

    def test_intake_decision_tier_literal_is_smart_only(self):
        """IntakeDecision.tier must be Literal["smart"] — deep is invalid."""
        from backend.models.intake_decision import IntakeDecision
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            IntakeDecision(
                needs_clarification=False,
                optimized_prompt="Test",
                tier="deep",
                output_type="analysis",
                reasoning="test",
            )


# ── Validator safety ──────────────────────────────────────────────────────────

class TestValidatorSafety:
    def test_validate_returns_list(self):
        """validate_model_config() must return a list regardless of outcome."""
        from backend.models.model_validator import validate_model_config
        result = validate_model_config()
        assert isinstance(result, list)

    def test_validate_never_raises_with_missing_keys(self, monkeypatch):
        """validate_model_config() must not raise even with bad/missing API keys."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        monkeypatch.setenv("OPENAI_API_KEY", "")
        monkeypatch.setenv("GOOGLE_API_KEY", "")
        monkeypatch.setenv("XAI_API_KEY", "")

        from backend.models.model_validator import validate_model_config
        try:
            result = validate_model_config()
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"validate_model_config() raised unexpectedly: {e}")

    def test_validate_skips_openrouter_models(self):
        """Models containing '/' (OpenRouter) must be skipped without error."""
        from backend.models.model_validator import validate_model_config
        # qwen/qwen-2.5-72b-instruct is an OpenRouter model — must not cause lookup
        # This should complete without raising even if xAI/OpenAI APIs are down
        result = validate_model_config()
        assert isinstance(result, list)
        # No warning should reference OpenRouter model IDs
        openrouter_warnings = [w for w in result if "/" in w.split("'")[1] if "'" in w]
        assert openrouter_warnings == []


# ── Router tier config structure ──────────────────────────────────────────────

class TestRouterTierConfig:
    def test_smart_config_has_all_labs(self):
        result = get_tier_config("smart")
        for lab in get_all_labs():
            assert lab in result

    def test_smart_config_has_executor_advisor_fallback(self):
        result = get_tier_config("smart")
        for lab in get_all_labs():
            assert "executor" in result[lab]
            assert "advisor" in result[lab]
            assert "fallback" in result[lab]

    def test_deep_config_executor_equals_advisor(self):
        result = get_tier_config("deep")
        for lab in get_all_labs():
            assert result[lab]["executor"] == result[lab]["advisor"]

    def test_grok_in_smart_config(self):
        result = get_tier_config("smart")
        assert "grok" in result

    def test_grok_in_deep_config(self):
        result = get_tier_config("deep")
        assert "grok" in result


# ── /api/model-info response structure ───────────────────────────────────────

class TestModelInfoEndpoint:
    """
    get_model_info() returns the correct structure for all four labs
    at both smart and deep tiers.
    """

    def _call(self) -> dict:
        """Call get_model_info() directly (no HTTP round-trip needed)."""
        import asyncio
        from backend.main import get_model_info
        return asyncio.run(get_model_info())

    def test_returns_smart_and_deep_keys(self):
        result = self._call()
        assert "smart" in result
        assert "deep" in result

    def test_smart_has_all_four_labs(self):
        result = self._call()
        for lab in ["claude", "gemini", "gpt", "grok"]:
            assert lab in result["smart"], f"smart missing lab: {lab}"

    def test_deep_has_all_four_labs(self):
        result = self._call()
        for lab in ["claude", "gemini", "gpt", "grok"]:
            assert lab in result["deep"], f"deep missing lab: {lab}"

    def test_smart_lab_has_executor_and_advisor(self):
        result = self._call()
        for lab in ["claude", "gemini", "gpt", "grok"]:
            entry = result["smart"][lab]
            assert "executor" in entry, f"smart.{lab} missing executor"
            assert "advisor" in entry, f"smart.{lab} missing advisor"

    def test_smart_executor_differs_from_advisor(self):
        """Smart tier uses executor + advisor split — they must be different models."""
        result = self._call()
        for lab in ["claude", "gemini", "gpt", "grok"]:
            entry = result["smart"][lab]
            assert entry["executor"] != entry["advisor"], (
                f"smart.{lab}: executor and advisor must differ, both are {entry['executor']!r}"
            )

    def test_deep_values_are_strings(self):
        """Deep tier values are plain model ID strings (not dicts)."""
        result = self._call()
        for lab in ["claude", "gemini", "gpt", "grok"]:
            val = result["deep"][lab]
            assert isinstance(val, str), f"deep.{lab} should be str, got {type(val)}"

    def test_smart_has_factcheck(self):
        result = self._call()
        assert "factcheck" in result["smart"]
        assert isinstance(result["smart"]["factcheck"], str)

    def test_deep_has_factcheck(self):
        result = self._call()
        assert "factcheck" in result["deep"]
        assert isinstance(result["deep"]["factcheck"], str)

    def test_smart_executor_equals_deep_for_no_split_lab(self):
        """
        Deep model for each lab should match the smart advisor (same top model).
        This validates that deep tier uses advisor-grade models throughout.
        """
        result = self._call()
        for lab in ["claude", "gemini", "gpt", "grok"]:
            smart_advisor = result["smart"][lab]["advisor"]
            deep_model    = result["deep"][lab]
            assert smart_advisor == deep_model, (
                f"{lab}: expected deep model {deep_model!r} to equal "
                f"smart advisor {smart_advisor!r}"
            )
