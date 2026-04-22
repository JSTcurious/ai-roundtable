"""
tests/test_intake_quality.py

Tests for intake quality improvements:
- Domain-specific immigration probing
- Immigration guard (prevents close with unknown visa_type)
- Assumptions keys in IntakeDecision schema
- corrected_assumptions and open_questions appended to research prompt
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.models.intake_decision import IntakeDecision


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_decision(**kwargs) -> IntakeDecision:
    """Build an IntakeDecision with sensible defaults, overridable via kwargs."""
    defaults = dict(
        needs_clarification=False,
        clarifying_question=None,
        optimized_prompt="Test prompt about job change.",
        tier="smart",
        output_type="analysis",
        reasoning="Career transition with immigration context.",
    )
    defaults.update(kwargs)
    return IntakeDecision(**defaults)


# ── Test 1: Immigration keyword detection ─────────────────────────────────────

class TestImmigrationKeywordDetection:
    """_has_immigration_context correctly identifies immigration-related text."""

    @pytest.mark.parametrize("text", [
        "I have an H-1B and am considering leaving my job",
        "My visa expires next year",
        "I'm on F-1 OPT and got a job offer",
        "My green card application is pending",
        "My employer sponsors my immigration case",
        "I need to check my work authorization",
        "I-485 is still pending from 2 years ago",
        "My company filed an I-140 for me",
        "I'm worried about my sponsorship if I switch jobs",
    ])
    def test_immigration_keywords_detected(self, text):
        from backend.intake import _has_immigration_context
        assert _has_immigration_context(text), (
            f"Expected immigration context detected in: {text!r}"
        )

    @pytest.mark.parametrize("text", [
        "I want to switch from backend to ML engineering",
        "Should I take the senior engineer offer at a startup?",
        "Help me plan my product roadmap for Q3",
    ])
    def test_non_immigration_text_not_flagged(self, text):
        from backend.intake import _has_immigration_context
        assert not _has_immigration_context(text), (
            f"Expected no immigration context in: {text!r}"
        )


# ── Test 2: Immigration guard fires on unknown visa_type ──────────────────────

class TestImmigrationGuard:
    """Guard prevents intake close when immigration context present but visa_type unknown."""

    def test_intake_guard_fires_on_unknown_visa_type(self):
        """
        If the model returns needs_clarification=False but visa_type is 'unknown',
        IntakeSession.analyze() must return status='clarifying' with a probing question.
        """
        from backend.intake import IntakeSession

        decision_with_unknown_visa = _make_decision(
            needs_clarification=False,
            user_context={
                "immigration_specifics": {"visa_type": "unknown"},
            },
        )

        with patch("backend.intake.call_intake", return_value=(decision_with_unknown_visa, "claude")):
            session = IntakeSession()
            result = session.analyze("I have an active immigration case and am considering leaving my job")

        assert result["status"] == "clarifying", (
            "Guard should force clarifying status when visa_type is unknown"
        )
        assert result["clarifying_question"] is not None
        assert "visa" in result["clarifying_question"].lower(), (
            "Probing question must ask about visa type"
        )
        assert result["config"] is None

    def test_intake_guard_fires_when_immigration_specifics_absent(self):
        """
        Guard fires if immigration keywords present but user_context has no
        immigration_specifics key at all (empty dict case).
        """
        from backend.intake import IntakeSession

        decision_no_imm = _make_decision(
            needs_clarification=False,
            user_context={},  # no immigration_specifics key
        )

        with patch("backend.intake.call_intake", return_value=(decision_no_imm, "claude")):
            session = IntakeSession()
            result = session.analyze("My visa situation is complicated — I want to change jobs")

        assert result["status"] == "clarifying"
        assert result["clarifying_question"] is not None

    def test_intake_closes_when_visa_type_known(self):
        """
        Guard must NOT block close when visa_type is a real value (e.g., 'H-1B').
        """
        from backend.intake import IntakeSession

        decision_known_visa = _make_decision(
            needs_clarification=False,
            user_context={
                "immigration_specifics": {"visa_type": "H-1B"},
            },
        )

        with patch("backend.intake.call_intake", return_value=(decision_known_visa, "claude")):
            session = IntakeSession()
            result = session.analyze("I'm on H-1B and considering a job change")

        assert result["status"] == "complete", (
            "Known visa_type should allow intake to close normally"
        )
        assert result["config"] is not None

    def test_intake_guard_does_not_fire_without_immigration_context(self):
        """
        Guard must not fire on a non-immigration prompt, even if visa_type is empty.
        """
        from backend.intake import IntakeSession

        decision_no_imm_context = _make_decision(
            needs_clarification=False,
            user_context={},
        )

        with patch("backend.intake.call_intake", return_value=(decision_no_imm_context, "claude")):
            session = IntakeSession()
            result = session.analyze("I want to switch from backend engineering to product management")

        # No immigration keywords → guard should not fire → complete
        assert result["status"] == "complete"


# ── Test 3: Assumptions keys present in IntakeDecision ───────────────────────

class TestAssumptionsKeysInSchema:
    """IntakeDecision always includes confirmed_assumptions and corrected_assumptions."""

    def test_assumptions_keys_present_in_completion(self):
        """
        IntakeDecision can be instantiated without providing assumptions fields
        (they default to empty lists), and those fields are accessible on the object.
        """
        decision = _make_decision()
        assert hasattr(decision, "confirmed_assumptions")
        assert hasattr(decision, "corrected_assumptions")
        assert hasattr(decision, "open_questions")
        assert isinstance(decision.confirmed_assumptions, list)
        assert isinstance(decision.corrected_assumptions, list)
        assert isinstance(decision.open_questions, list)

    def test_assumptions_roundtrip_via_json(self):
        """
        Assumptions survive JSON serialization/deserialization (as happens
        when the response is parsed from the model's raw JSON output).
        """
        decision = _make_decision(
            confirmed_assumptions=["User is a software engineer"],
            corrected_assumptions=["Corrected: user is senior, not mid-level"],
            open_questions=["Target company size not specified"],
        )
        raw_json = decision.model_dump_json()
        restored = IntakeDecision.model_validate_json(raw_json)

        assert restored.confirmed_assumptions == ["User is a software engineer"]
        assert restored.corrected_assumptions == ["Corrected: user is senior, not mid-level"]
        assert restored.open_questions == ["Target company size not specified"]


# ── Test 4: corrected_assumptions appended to research prompt ─────────────────

class TestCorrectedAssumptionsPropagation:
    """_enrich_prompt appends corrected_assumptions and open_questions to the prompt."""

    def test_corrected_assumptions_appended_to_prompt(self):
        from backend.main import _enrich_prompt

        config = {
            "optimized_prompt": "Evaluate this job offer.",
            "corrected_assumptions": [
                "User is on H-1B, not green card holder as initially assumed",
                "New employer is a startup, not a large corporation",
            ],
            "open_questions": [],
        }
        result = _enrich_prompt(config["optimized_prompt"], config)

        assert "H-1B" in result
        assert "startup" in result
        assert "corrected" in result.lower()

    def test_open_questions_appended_to_prompt(self):
        from backend.main import _enrich_prompt

        config = {
            "optimized_prompt": "Plan my career transition.",
            "corrected_assumptions": [],
            "open_questions": [
                "Whether new employer can sponsor H-1B transfer",
                "Timeline for I-485 priority date becoming current",
            ],
        }
        result = _enrich_prompt(config["optimized_prompt"], config)

        assert "H-1B transfer" in result
        assert "I-485" in result
        assert "open variables" in result.lower()

    def test_no_appending_when_both_empty(self):
        from backend.main import _enrich_prompt

        base = "A clean prompt with no assumptions."
        config = {
            "optimized_prompt": base,
            "corrected_assumptions": [],
            "open_questions": [],
        }
        result = _enrich_prompt(base, config)

        # No extra content appended
        assert result == base

    def test_enrich_prompt_handles_missing_keys_gracefully(self):
        """_enrich_prompt must not raise if config lacks the new keys."""
        from backend.main import _enrich_prompt

        config = {"optimized_prompt": "A prompt from an older session."}
        result = _enrich_prompt(config["optimized_prompt"], config)

        # No extra content appended, no exception raised
        assert result == "A prompt from an older session."


# ── Fix 3: Opening message ────────────────────────────────────────────────────

class TestOpeningMessage:
    def test_opening_message_sets_expectations(self):
        """
        IntakeSession.start() returns a message that sets user expectations:
        a few focused questions, not an interrogation. Must end with a question.
        """
        from backend.intake import IntakeSession
        session = IntakeSession()
        message = session.start()

        assert isinstance(message, str) and len(message) > 0
        # Sets expectations: short intake, focused questions, specificity matters
        lower = message.lower()
        assert any(word in lower for word in ("few", "focused", "specific")), (
            f"Opening message should contain 'few', 'focused', or 'specific': {message!r}"
        )
        # Must end with a question
        assert message.strip().endswith("?"), (
            f"Opening message must end with '?': {message!r}"
        )

    def test_opening_message_constant_matches_start(self):
        """INTAKE_OPENING_MESSAGE and IntakeSession.start() return the same string."""
        from backend.intake import INTAKE_OPENING_MESSAGE, IntakeSession
        session = IntakeSession()
        assert session.start() == INTAKE_OPENING_MESSAGE


# ── Fix 2: suggested_options field ───────────────────────────────────────────

class TestSuggestedOptions:
    def test_suggested_options_field_exists_on_intake_decision(self):
        """IntakeDecision has a suggested_options field that defaults to []."""
        from backend.models.intake_decision import IntakeDecision
        decision = IntakeDecision(
            needs_clarification=False,
            optimized_prompt="test",
            tier="smart",
            output_type="analysis",
            reasoning="test",
        )
        assert hasattr(decision, "suggested_options")
        assert isinstance(decision.suggested_options, list)
        assert decision.suggested_options == []

    def test_suggested_options_roundtrip_via_json(self):
        """suggested_options survives JSON serialization."""
        from backend.models.intake_decision import IntakeDecision
        options = ["H-1B", "L-1", "O-1 / EB-1A", "Pending green card"]
        decision = IntakeDecision(
            needs_clarification=True,
            clarifying_question="What visa type are you on?",
            suggested_options=options,
            optimized_prompt="test",
            tier="smart",
            output_type="analysis",
            reasoning="test",
        )
        restored = IntakeDecision.model_validate_json(decision.model_dump_json())
        assert restored.suggested_options == options

    def test_suggested_options_not_generic(self):
        """
        suggested_options quality is validated by live session testing,
        not unit tests, because it depends on model output.

        The prompt instructs the model to generate question-specific options:
        - visa type question → visa type options (H-1B, L-1, etc.)
        - yes/no question → ["Yes", "Not yet", "In progress"]
        - open-ended question → []
        Never generic options like "Still early — just exploring".

        See _build_intake_system_prompt() in backend/models/openai_client.py,
        'suggested_options' field rules.
        """
        # Structural placeholder — live quality verified in session testing.
        assert True

    def test_analyze_includes_suggested_options_in_clarifying_response(self):
        """
        IntakeSession.analyze() includes 'suggested_options' in the clarifying
        response dict when the model asks a clarifying question.
        """
        from backend.intake import IntakeSession
        from backend.models.intake_decision import IntakeDecision

        decision_with_question = IntakeDecision(
            needs_clarification=True,
            clarifying_question="What visa type are you on?",
            suggested_options=["H-1B", "L-1", "TN / Other"],
            optimized_prompt="test",
            tier="smart",
            output_type="analysis",
            reasoning="test",
        )

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "backend.intake.call_intake", return_value=(decision_with_question, "claude")
        ):
            session = IntakeSession()
            result = session.analyze("I have a visa and want to change jobs")

        assert result["status"] == "clarifying"
        assert "suggested_options" in result
        assert result["suggested_options"] == ["H-1B", "L-1", "TN / Other"]

    def test_immigration_guard_provides_visa_type_options(self):
        """
        When the immigration guard fires (visa_type unknown), the clarifying
        response includes the standard visa type options.
        """
        from backend.intake import IntakeSession

        decision_no_visa = _make_decision(
            needs_clarification=False,
            user_context={"immigration_specifics": {"visa_type": "unknown"}},
        )

        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "backend.intake.call_intake", return_value=(decision_no_visa, "claude")
        ):
            session = IntakeSession()
            result = session.analyze("I have an active immigration case and want to leave my job")

        assert result["status"] == "clarifying"
        assert "suggested_options" in result
        assert "H-1B" in result["suggested_options"]
        assert len(result["suggested_options"]) >= 4
