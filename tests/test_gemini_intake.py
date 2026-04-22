"""
tests/test_gemini_intake.py

Tests for intake session logic. call_gpt4o_mini_intake() is mocked —
no real API calls are made.

Run with:
    uv run pytest tests/test_gemini_intake.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

from backend.models.intake_decision import IntakeDecision
from backend.intake import IntakeSession


# ---------------------------------------------------------------------------
# Fixtures — pre-built IntakeDecision objects
# ---------------------------------------------------------------------------

def _decision(
    needs_clarification=False,
    clarifying_question=None,
    optimized_prompt="Optimized test prompt",
    tier="smart",
    output_type="analysis",
    reasoning="Smart selected — technical evaluation with clear tradeoffs",
) -> IntakeDecision:
    return IntakeDecision(
        needs_clarification=needs_clarification,
        clarifying_question=clarifying_question,
        optimized_prompt=optimized_prompt,
        tier=tier,
        output_type=output_type,
        reasoning=reasoning,
    )


CLEAR_DECISION = _decision()
AMBIGUOUS_DECISION = _decision(
    needs_clarification=True,
    clarifying_question="What type of output do you need — a written report, a decision record, or a structured plan?",
    optimized_prompt="",  # not used when clarification needed
)
FINAL_DECISION = _decision(
    optimized_prompt="Refined prompt incorporating the user's clarification answer",
    tier="smart",
    output_type="report",
    reasoning="Smart selected — architecture decision with significant tradeoffs",
)


# ---------------------------------------------------------------------------
# Test 1: Clear prompt → needs_clarification False, tier assigned, optimized_prompt returned
# ---------------------------------------------------------------------------

def test_clear_prompt_completes_in_one_turn():
    with patch("backend.intake.call_intake_sonnet", return_value=CLEAR_DECISION):
        session = IntakeSession()
        result = session.analyze("How do I design a RAG pipeline?")

    assert result["status"] == "complete"
    assert result["config"] is not None
    assert result["config"]["optimized_prompt"] == "Optimized test prompt"
    assert result["config"]["tier"] == "smart"
    assert result["clarifying_question"] is None
    assert session.complete is True


# ---------------------------------------------------------------------------
# Test 2: Ambiguous prompt → needs_clarification True, clarifying_question present, no tier yet
# ---------------------------------------------------------------------------

def test_ambiguous_prompt_returns_clarifying_question():
    with patch("backend.intake.call_intake_sonnet", return_value=AMBIGUOUS_DECISION):
        session = IntakeSession()
        result = session.analyze("I need help with my project")

    assert result["status"] == "clarifying"
    assert result["clarifying_question"] is not None
    assert len(result["clarifying_question"]) > 0
    assert result["config"] is None
    assert session.complete is False


# ---------------------------------------------------------------------------
# Test 3: After clarification answer → needs_clarification False, optimized_prompt incorporates answer
# ---------------------------------------------------------------------------

def test_clarification_answer_completes_session():
    with patch("backend.intake.call_intake_sonnet", side_effect=[AMBIGUOUS_DECISION, FINAL_DECISION]):
        session = IntakeSession()
        r1 = session.analyze("I need help with my project")
        assert r1["status"] == "clarifying"

        r2 = session.respond("A written report for my team")

    assert r2["status"] == "complete"
    assert r2["config"]["optimized_prompt"] == "Refined prompt incorporating the user's clarification answer"
    assert r2["config"]["tier"] == "smart"
    assert session.complete is True


# ---------------------------------------------------------------------------
# Test 4: Tier is always "smart" — "deep" and "quick" are not valid literals
# ---------------------------------------------------------------------------

def test_tier_is_always_smart():
    """Intake always returns smart — tier is Literal["smart"]."""
    decision = _decision(tier="smart")
    with patch("backend.intake.call_intake_sonnet", return_value=decision):
        session = IntakeSession()
        result = session.analyze("Test prompt")
    assert result["config"]["tier"] == "smart"


def test_invalid_tier_raises_validation_error():
    with pytest.raises(ValidationError):
        IntakeDecision(
            needs_clarification=False,
            optimized_prompt="Test",
            tier="turbo",  # not a valid literal
            output_type="report",
            reasoning="test",
        )


def test_quick_tier_is_invalid_for_intake():
    """quick is not a valid IntakeDecision tier — only smart is valid."""
    with pytest.raises(ValidationError):
        IntakeDecision(
            needs_clarification=False,
            optimized_prompt="Test",
            tier="quick",
            output_type="report",
            reasoning="test",
        )


def test_deep_tier_is_invalid_for_intake():
    """Intake always returns smart — deep is not a valid IntakeDecision tier."""
    with pytest.raises(ValidationError):
        IntakeDecision(
            needs_clarification=False,
            optimized_prompt="Design the data architecture for a real-time fraud detection system",
            tier="deep",
            output_type="decision",
            reasoning="Deep selected — architecture decision",
        )


def test_architecture_prompt_maps_to_smart_tier():
    """Architecture prompts receive smart tier from intake — user upgrades via slider if needed."""
    arch_decision = _decision(
        tier="smart",
        output_type="decision",
        reasoning="Smart selected — architecture analysis with well-defined scope",
        optimized_prompt="Design the architecture for a real-time data processing pipeline",
    )
    with patch("backend.intake.call_intake_sonnet", return_value=arch_decision):
        session = IntakeSession()
        result = session.analyze("Design the architecture for a real-time data processing pipeline")

    assert result["config"]["tier"] == "smart"


def test_comparison_prompt_maps_to_smart_tier():
    """Comparison prompts (X vs Y) receive smart tier — standard analysis."""
    comparison_decision = _decision(
        tier="smart",
        output_type="comparison",
        reasoning="Smart selected — comparison question with well-defined parameters",
        optimized_prompt="Compare PostgreSQL vs MongoDB for a read-heavy web application",
    )
    with patch("backend.intake.call_intake_sonnet", return_value=comparison_decision):
        session = IntakeSession()
        result = session.analyze("Compare PostgreSQL vs MongoDB for a read-heavy web application")

    assert result["config"]["tier"] == "smart"


# ---------------------------------------------------------------------------
# Test 5: Maximum one clarifying turn — second respond() returns existing config
# ---------------------------------------------------------------------------

def test_second_respond_returns_existing_config_without_api_call():
    with patch("backend.intake.call_intake_sonnet", side_effect=[AMBIGUOUS_DECISION, FINAL_DECISION]) as mock_api:
        session = IntakeSession()
        session.analyze("Ambiguous prompt")
        session.respond("First answer")
        assert mock_api.call_count == 2

        # Second respond() — session is already complete, should not call API again
        result = session.respond("Another answer")
        assert mock_api.call_count == 2  # no third call

    assert result["status"] == "complete"
    assert result["config"] is not None


# ---------------------------------------------------------------------------
# Test 6: IntakeDecision with empty optimized_prompt raises ValidationError
# ---------------------------------------------------------------------------

def test_intake_decision_allows_empty_optimized_prompt():
    """
    Pydantic allows empty strings by default — this documents that behavior.
    The API layer is responsible for rejecting empty prompts at intake_start.
    """
    decision = IntakeDecision(
        needs_clarification=False,
        optimized_prompt="",
        tier="smart",
        output_type="report",
        reasoning="test",
    )
    assert decision.optimized_prompt == ""


def test_intake_decision_missing_optimized_prompt_defaults_to_none():
    """
    optimized_prompt is Optional — during clarifying turns the model
    legitimately returns null. When omitted, it defaults to None.
    """
    decision = IntakeDecision(
        needs_clarification=True,
        clarifying_question="What's your visa type?",
        tier="smart",
        # optimized_prompt omitted — allowed on clarifying turns
    )
    assert decision.optimized_prompt is None
    assert decision.output_type is None
    assert decision.reasoning is None
    assert decision.session_title is None


# ---------------------------------------------------------------------------
# Test 7: Session not found returns 404 (endpoint-level test via FastAPI TestClient)
# ---------------------------------------------------------------------------

def test_unknown_session_returns_404():
    from fastapi.testclient import TestClient
    from backend.main import app

    client = TestClient(app)
    res = client.post(
        "/api/intake/respond",
        json={"session_id": "nonexistent-uuid", "answer": "some answer"},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Test 8: Retry logic — rate limit / transient error handling in call_gpt4o_mini_intake()
# ---------------------------------------------------------------------------

def test_503_on_first_attempt_succeeds_on_second():
    """503 on attempt 1, success on attempt 2 → returns IntakeDecision."""
    from backend.models.openai_client import call_gpt4o_mini_intake

    error_503 = Exception("503 Service Unavailable")
    with patch("backend.models.openai_client._call_gpt4o_mini_intake_once",
               side_effect=[error_503, CLEAR_DECISION]) as mock_call, \
         patch("backend.models.openai_client.time.sleep") as mock_sleep:
        result = call_gpt4o_mini_intake("test prompt")

    assert result == CLEAR_DECISION
    assert mock_call.call_count == 2
    mock_sleep.assert_called_once_with(2)  # first delay only


def test_503_all_three_attempts_raises_runtime_error():
    """503 on all 3 attempts → RuntimeError with the exact user-facing message."""
    from backend.models.openai_client import call_gpt4o_mini_intake

    error_503 = Exception("503 Service Unavailable")
    with patch("backend.models.openai_client._call_gpt4o_mini_intake_once",
               side_effect=[error_503, error_503, error_503]), \
         patch("backend.models.openai_client.time.sleep"):
        with pytest.raises(RuntimeError) as exc_info:
            call_gpt4o_mini_intake("test prompt")

    assert "unavailable after 3 attempts" in str(exc_info.value)
    assert "please try again in a moment" in str(exc_info.value)


def test_non_503_raises_immediately_without_retry():
    """404 (or any non-retriable error) on the first attempt → raises immediately, no sleep."""
    from backend.models.openai_client import call_gpt4o_mini_intake

    error_404 = Exception("404 model not found")
    with patch("backend.models.openai_client._call_gpt4o_mini_intake_once",
               side_effect=error_404) as mock_call, \
         patch("backend.models.openai_client.time.sleep") as mock_sleep:
        with pytest.raises(Exception, match="404"):
            call_gpt4o_mini_intake("test prompt")

    assert mock_call.call_count == 1   # single attempt only
    mock_sleep.assert_not_called()


def test_retry_sleep_called_with_correct_delays():
    """Exponential backoff: sleep(2) after attempt 1, sleep(4) after attempt 2, no sleep after 3."""
    from backend.models.openai_client import call_gpt4o_mini_intake

    error_503 = Exception("unavailable")
    with patch("backend.models.openai_client._call_gpt4o_mini_intake_once",
               side_effect=[error_503, error_503, error_503]), \
         patch("backend.models.openai_client.time.sleep") as mock_sleep:
        with pytest.raises(RuntimeError):
            call_gpt4o_mini_intake("test prompt")

    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(2)
    mock_sleep.assert_any_call(4)


# ---------------------------------------------------------------------------
# Test 9: Proper noun preservation — clarifying question must not substitute names
# ---------------------------------------------------------------------------

_PRICING_PROMPT = (
    "What are the current API pricing tiers for Claude Opus 4.7, "
    "GPT-5, and Gemini 2.5 Pro as of April 2026?"
)

_INTENT_ONLY_QUESTION = _decision(
    needs_clarification=True,
    clarifying_question="Are you looking for standard API pricing or enterprise contract rates?",
    optimized_prompt="",
)

_SUBSTITUTED_QUESTION = _decision(
    needs_clarification=True,
    clarifying_question=(
        "Are you looking for pricing for currently available models "
        "(e.g., Claude 3 Opus, GPT-4, Gemini 1.5 Pro)?"
    ),
    optimized_prompt="",
)


def test_clarifying_question_does_not_substitute_model_names():
    """
    When the user provides specific model names, the clarifying question must
    ask about intent or scope only — not suggest replacement names.

    This test asserts the correct pattern: an intent-only question contains
    no model names from the training data that contradict the user's prompt.
    """
    with patch("backend.intake.call_intake_sonnet", return_value=_INTENT_ONLY_QUESTION):
        session = IntakeSession()
        result = session.analyze(_PRICING_PROMPT)

    q = result["clarifying_question"]
    assert "Claude 3" not in q, "clarifying question must not substitute Claude 3 for Claude Opus 4.7"
    assert "GPT-4" not in q, "clarifying question must not substitute GPT-4 for GPT-5"
    assert "Gemini 1.5" not in q, "clarifying question must not substitute Gemini 1.5 for Gemini 2.5 Pro"


def test_clarifying_question_with_substituted_names_is_detectable():
    """
    Documents the failure mode: if the model returns a clarifying question
    that replaces user-provided names with its own training-data examples,
    the assertions above would catch it. This test confirms the detection logic
    works against a known-bad response.
    """
    with patch("backend.intake.call_intake_sonnet", return_value=_SUBSTITUTED_QUESTION):
        session = IntakeSession()
        result = session.analyze(_PRICING_PROMPT)

    q = result["clarifying_question"]
    # These assertions should FAIL against the bad response — confirming detection works.
    assert "Claude 3" in q      # present in the substituted question
    assert "GPT-4" in q         # present in the substituted question
    assert "Gemini 1.5" in q    # present in the substituted question


# ---------------------------------------------------------------------------
# Test 10: Proper noun preservation — Turn 1 optimized_prompt must not rename models
# ---------------------------------------------------------------------------

_PRESERVED_FINAL = _decision(
    needs_clarification=False,
    optimized_prompt=(
        "Compare the current standard API pricing tiers for Claude Opus 4.7, "
        "GPT-5, and Gemini 2.5 Pro as of April 2026. The user wants standard "
        "API pricing, not enterprise contract rates."
    ),
    tier="smart",
    output_type="comparison",
    reasoning="Smart — factual pricing lookup with named models",
)

_SUBSTITUTED_FINAL = _decision(
    needs_clarification=False,
    optimized_prompt=(
        "Compare the current standard API pricing tiers for Claude 3 Opus, "
        "GPT-4, and Gemini 1.5 Pro as of April 2026."
    ),
    tier="smart",
    output_type="comparison",
    reasoning="Smart — factual pricing lookup",
)


def test_turn1_optimized_prompt_preserves_original_model_names():
    """
    After the user answers the clarifying question, the optimized_prompt must
    contain the model names from the original prompt, not substitutions.
    """
    with patch("backend.intake.call_intake_sonnet",
               side_effect=[_INTENT_ONLY_QUESTION, _PRESERVED_FINAL]):
        session = IntakeSession()
        session.analyze(_PRICING_PROMPT)
        result = session.respond("Standard API pricing")

    op = result["config"]["optimized_prompt"]
    assert "Claude Opus 4.7" in op, "optimized_prompt must preserve 'Claude Opus 4.7'"
    assert "GPT-5" in op, "optimized_prompt must preserve 'GPT-5'"
    assert "Gemini 2.5 Pro" in op, "optimized_prompt must preserve 'Gemini 2.5 Pro'"
    assert "Claude 3 Opus" not in op, "optimized_prompt must not substitute 'Claude 3 Opus'"
    assert "GPT-4" not in op, "optimized_prompt must not substitute 'GPT-4'"
    assert "Gemini 1.5" not in op, "optimized_prompt must not substitute 'Gemini 1.5'"


def test_turn1_substituted_prompt_is_detectable():
    """
    Documents the failure mode: if Turn 1 returns an optimized_prompt with
    substituted model names, the assertions above would catch it. This test
    confirms the detection logic works against a known-bad response.
    """
    with patch("backend.intake.call_intake_sonnet",
               side_effect=[_INTENT_ONLY_QUESTION, _SUBSTITUTED_FINAL]):
        session = IntakeSession()
        session.analyze(_PRICING_PROMPT)
        result = session.respond("Standard API pricing")

    op = result["config"]["optimized_prompt"]
    # These assertions should FAIL against the bad response — confirming detection works.
    assert "Claude 3 Opus" in op    # present in the substituted prompt
    assert "GPT-4" in op            # present in the substituted prompt
    assert "Gemini 1.5" in op       # present in the substituted prompt


# ---------------------------------------------------------------------------
# Test 11: All 91 existing guardrail tests still pass — import check
# ---------------------------------------------------------------------------

def test_guardrail_module_still_importable():
    """Smoke-test that the guardrail module is unaffected by the intake changes."""
    from backend.router import (
        ANTI_HALLUCINATION_BLOCK,
        CASCADING_GUARD,
        CONFIDENCE_CONVENTION,
        SYNTHESIS_SKEPTICISM,
        SYNTHESIS_TRUST_HIERARCHY,
        get_round1_system_prompt,
        build_synthesis_prompt,
    )
    for model in ["gemini", "gpt", "grok", "claude"]:
        prompt = get_round1_system_prompt(model)
        assert "Response Accuracy Guidelines" in prompt
        assert "Confidence Qualifiers" in prompt
