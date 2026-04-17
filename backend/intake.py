"""
backend/intake.py

Gemini Flash-powered intake for ai-roundtable v2.

Analyzes the user's prompt in a single API call. Asks at most one clarifying
question. Auto-assigns tier (quick / smart / deep) and returns an optimized
prompt ready for the roundtable.

Classes:
    IntakeSession  — manages a single intake session (at most two turns)

Functions:
    sanitize_text   — strip Unicode bidi control characters
    sanitize_config — recursively sanitize string values in a config dict
"""

import re
from typing import Any, Optional

from backend.models.google_client import call_gemini_intake
from backend.models.intake_decision import IntakeDecision

# Unicode bidi overrides, directional formatting, and other invisible control characters.
# Ranges covered:
#   U+200B–U+200F  zero-width/directional marks
#   U+202A–U+202E  directional embeddings and overrides
#   U+2066–U+2069  directional isolates
#   U+061C         Arabic letter mark
#   U+FEFF         BOM / zero-width no-break space
_BIDI_CONTROL_RE = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff]"
)


def sanitize_text(text: str) -> str:
    """Strip Unicode bidi overrides and invisible control characters from a string."""
    if not isinstance(text, str):
        return text
    return _BIDI_CONTROL_RE.sub("", text)


def sanitize_config(obj: Any) -> Any:
    """
    Recursively sanitize all string values in a config dict/list.
    Returns the same structure with bidi characters removed from every string.
    """
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, dict):
        return {k: sanitize_config(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_config(item) for item in obj]
    return obj


def _decision_to_config(decision: IntakeDecision) -> dict:
    """Convert an IntakeDecision into the session config dict."""
    return sanitize_config({
        "optimized_prompt": decision.optimized_prompt,
        "tier": decision.tier,
        "output_type": decision.output_type,
        "reasoning": decision.reasoning,
    })


class IntakeSession:
    """
    Manages a single Gemini Flash intake session.

    At most two turns:
      Turn 0 — analyze(prompt):   Gemini decides whether to clarify or proceed.
      Turn 1 — respond(answer):   Only called after a clarifying question.
                                   Always completes the session.

    Usage (no clarification needed):
        session = IntakeSession()
        result = session.analyze(user_prompt)
        # result["status"] == "complete"
        config = result["config"]

    Usage (clarification needed):
        session = IntakeSession()
        result = session.analyze(user_prompt)
        # result["status"] == "clarifying"
        # send result["clarifying_question"] to frontend
        result2 = session.respond(user_answer)
        # result2["status"] == "complete"
        config = result2["config"]
    """

    def __init__(self):
        self.complete: bool = False
        self.session_config: Optional[dict] = None
        self._original_prompt: Optional[str] = None
        self._clarifying_question: Optional[str] = None

    def analyze(self, prompt: str) -> dict:
        """
        Turn 0 — analyze the user's raw prompt.

        Returns:
            {
                "status": "clarifying",
                "clarifying_question": str,
                "config": None,
            }
            or
            {
                "status": "complete",
                "clarifying_question": None,
                "config": dict,
            }
        """
        decision = call_gemini_intake(prompt)

        if decision.needs_clarification:
            self._original_prompt = prompt
            self._clarifying_question = decision.clarifying_question
            return {
                "status": "clarifying",
                "clarifying_question": decision.clarifying_question,
                "config": None,
            }

        self.complete = True
        self.session_config = _decision_to_config(decision)
        return {
            "status": "complete",
            "clarifying_question": None,
            "config": self.session_config,
        }

    def respond(self, answer: str) -> dict:
        """
        Turn 1 — process the user's answer to the clarifying question.

        Hard rule: maximum one clarifying question per session.
        If respond() is called after the session is already complete,
        return the existing config without another API call.

        Returns:
            {
                "status": "complete",
                "clarifying_question": None,
                "config": dict,
            }
        """
        if self.complete and self.session_config:
            return {
                "status": "complete",
                "clarifying_question": None,
                "config": self.session_config,
            }

        combined = (
            f"Original prompt: {self._original_prompt}\n"
            f"Clarifying question asked: {self._clarifying_question}\n"
            f"User's answer: {answer}\n\n"
            "Now return the final IntakeDecision with needs_clarification: false. "
            "Incorporate the answer into the optimized_prompt."
        )
        decision = call_gemini_intake(combined)
        self.complete = True
        self.session_config = _decision_to_config(decision)
        return {
            "status": "complete",
            "clarifying_question": None,
            "config": self.session_config,
        }
