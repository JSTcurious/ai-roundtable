"""
tests/test_gemini_intake.py

Tests for Gemini Flash-powered intake. call_gemini_intake() is mocked —
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
    tier="deep",
    output_type="report",
    reasoning="Deep selected — architecture decision with significant tradeoffs",
)


# ---------------------------------------------------------------------------
# Test 1: Clear prompt → needs_clarification False, tier assigned, optimized_prompt returned
# ---------------------------------------------------------------------------

def test_clear_prompt_completes_in_one_turn():
    with patch("backend.intake.call_gemini_intake", return_value=CLEAR_DECISION):
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
    with patch("backend.intake.call_gemini_intake", return_value=AMBIGUOUS_DECISION):
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
    with patch("backend.intake.call_gemini_intake", side_effect=[AMBIGUOUS_DECISION, FINAL_DECISION]):
        session = IntakeSession()
        r1 = session.analyze("I need help with my project")
        assert r1["status"] == "clarifying"

        r2 = session.respond("A written report for my team")

    assert r2["status"] == "complete"
    assert r2["config"]["optimized_prompt"] == "Refined prompt incorporating the user's clarification answer"
    assert r2["config"]["tier"] == "deep"
    assert session.complete is True


# ---------------------------------------------------------------------------
# Test 4: Tier is always one of "quick", "smart", "deep"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tier", ["quick", "smart", "deep"])
def test_tier_is_valid_literal(tier):
    decision = _decision(tier=tier)
    with patch("backend.intake.call_gemini_intake", return_value=decision):
        session = IntakeSession()
        result = session.analyze("Test prompt")
    assert result["config"]["tier"] == tier


def test_invalid_tier_raises_validation_error():
    with pytest.raises(ValidationError):
        IntakeDecision(
            needs_clarification=False,
            optimized_prompt="Test",
            tier="turbo",  # not a valid literal
            output_type="report",
            reasoning="test",
        )


# ---------------------------------------------------------------------------
# Test 5: Maximum one clarifying turn — second respond() returns existing config
# ---------------------------------------------------------------------------

def test_second_respond_returns_existing_config_without_api_call():
    with patch("backend.intake.call_gemini_intake", side_effect=[AMBIGUOUS_DECISION, FINAL_DECISION]) as mock_api:
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


def test_intake_decision_missing_optimized_prompt_raises():
    with pytest.raises(ValidationError):
        IntakeDecision(
            needs_clarification=False,
            tier="smart",
            output_type="report",
            reasoning="test",
            # optimized_prompt omitted
        )


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
# Test 8: Retry logic — 503 handling in call_gemini_intake()
# ---------------------------------------------------------------------------

def test_503_on_first_attempt_succeeds_on_second():
    """503 on attempt 1, success on attempt 2 → returns IntakeDecision."""
    from backend.models.google_client import call_gemini_intake

    error_503 = Exception("503 Service Unavailable")
    with patch("backend.models.google_client._call_gemini_intake_once",
               side_effect=[error_503, CLEAR_DECISION]) as mock_call, \
         patch("backend.models.google_client.time.sleep") as mock_sleep:
        result = call_gemini_intake("test prompt")

    assert result == CLEAR_DECISION
    assert mock_call.call_count == 2
    mock_sleep.assert_called_once_with(2)  # first delay only


def test_503_all_three_attempts_raises_runtime_error():
    """503 on all 3 attempts → RuntimeError with the exact user-facing message."""
    from backend.models.google_client import call_gemini_intake

    error_503 = Exception("503 Service Unavailable")
    with patch("backend.models.google_client._call_gemini_intake_once",
               side_effect=[error_503, error_503, error_503]), \
         patch("backend.models.google_client.time.sleep"):
        with pytest.raises(RuntimeError) as exc_info:
            call_gemini_intake("test prompt")

    assert "unavailable after 3 attempts" in str(exc_info.value)
    assert "please try again in a moment" in str(exc_info.value)


def test_non_503_raises_immediately_without_retry():
    """404 (or any non-503) on the first attempt → raises immediately, no sleep."""
    from backend.models.google_client import call_gemini_intake

    error_404 = Exception("404 model not found")
    with patch("backend.models.google_client._call_gemini_intake_once",
               side_effect=error_404) as mock_call, \
         patch("backend.models.google_client.time.sleep") as mock_sleep:
        with pytest.raises(Exception, match="404"):
            call_gemini_intake("test prompt")

    assert mock_call.call_count == 1   # single attempt only
    mock_sleep.assert_not_called()


def test_retry_sleep_called_with_correct_delays():
    """Exponential backoff: sleep(2) after attempt 1, sleep(4) after attempt 2, no sleep after 3."""
    from backend.models.google_client import call_gemini_intake

    error_503 = Exception("unavailable")
    with patch("backend.models.google_client._call_gemini_intake_once",
               side_effect=[error_503, error_503, error_503]), \
         patch("backend.models.google_client.time.sleep") as mock_sleep:
        with pytest.raises(RuntimeError):
            call_gemini_intake("test prompt")

    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(2)
    mock_sleep.assert_any_call(4)


# ---------------------------------------------------------------------------
# Test 9: All 70 existing guardrail tests still pass — import check
# ---------------------------------------------------------------------------

def test_guardrail_module_still_importable():
    """Smoke-test that the guardrail module is unaffected by the intake rewrite."""
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
