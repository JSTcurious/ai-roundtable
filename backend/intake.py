"""
backend/intake.py

Claude Sonnet-powered intake. Captures full user intent across 2-4 turns
before routing to the research pipeline.
Fallback: GPT-4o Mini → Qwen 2.5 72B → passthrough.

Classes:
    IntakeSession  — manages a single intake session (at most two turns)

Functions:
    call_intake_sonnet          — primary intake via Claude Sonnet (Anthropic)
    sanitize_text               — strip Unicode bidi control characters
    sanitize_config             — recursively sanitize string values in a config dict
    _has_immigration_context    — detect immigration keywords in user text
    _has_unknown_visa_type      — check if decision has unresolved visa_type
"""

import logging
import re
from typing import Any, Optional

from backend.models.intake_decision import IntakeDecision
from backend.models.resilient_caller import call_with_fallback

logger = logging.getLogger(__name__)

# ── Intake opening message ────────────────────────────────────────────────────

INTAKE_OPENING_MESSAGE = (
    "I'll ask a few focused questions before briefing the "
    "research panel — the more specific your answers, the more "
    "targeted the analysis. What are you working through?"
)

# ── Immigration guard ─────────────────────────────────────────────────────────

IMMIGRATION_KEYWORDS: frozenset[str] = frozenset({
    "immigration", "visa", "h-1b", "h1b", "h1-b", "i-485", "i485",
    "i-140", "i140", "green card", "greencard", "green-card",
    "sponsorship", "sponsored", "sponsor",
    "work authorization", "work auth", "opt", "stem opt",
    "tn visa", "tn status", "l-1", "l1", "l-1b", "l-1a",
    "o-1", "o1", "f-1", "f1", "f-1 opt",
    "petition", "ead", "employment authorization",
    "priority date", "perm", "labor certification",
    "immigration case", "immigration attorney", "immigration lawyer",
    "portability", "ac21", "cap exempt",
    "unlawful presence", "change of status",
})

# Compiled regex: matches any immigration keyword at word boundaries.
# Sorted longest-first so multi-word phrases (e.g. "green card") take precedence
# over their component words in alternation.
_IMMIGRATION_RE: re.Pattern = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(kw)
        for kw in sorted(IMMIGRATION_KEYWORDS, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)


def _has_immigration_context(text: str) -> bool:
    """
    Return True if text contains any immigration-related keyword at a word boundary.
    Word-boundary matching prevents false positives like 'ead' matching 'read'.
    """
    return bool(_IMMIGRATION_RE.search(text))


def _has_unknown_visa_type(decision: IntakeDecision) -> bool:
    """
    Return True if the decision has unresolved visa_type.
    A visa_type is considered unresolved if it is absent, empty,
    or one of the sentinel 'unknown' strings.
    """
    user_ctx = decision.user_context or {}
    imm = user_ctx.get("immigration_specifics", {}) or {}
    visa_type = (imm.get("visa_type") or "").strip().lower()
    return visa_type in ("", "unknown", "unspecified", "not stated", "n/a", "tbd")


def call_intake_sonnet(prompt: str) -> IntakeDecision:
    """
    Primary intake via Claude Sonnet (Anthropic direct API).

    Uses the same system prompt and JSON schema as all other intake providers.
    Sonnet is the quality ceiling for intake — full intent capture drives
    everything downstream.

    Raises:
        ValueError:   if response fails IntakeDecision schema validation.
        Exception:    on any Anthropic API error (raised immediately; retried
                      by call_with_fallback via call_with_retry).
    """
    from backend.models.anthropic_client import _get_client
    from backend.models.model_config import INTAKE_PRIMARY
    from backend.models.openai_client import _build_intake_system_prompt

    system_prompt = _build_intake_system_prompt().strip()
    response = _get_client().messages.create(
        model=INTAKE_PRIMARY,
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if Claude wrapped the JSON
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
    try:
        return IntakeDecision.model_validate_json(raw)
    except Exception as e:
        raise ValueError(
            f"Claude Sonnet intake schema validation failed: {e}. Raw: {raw!r}"
        )

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


def _intake_passthrough(prompt: str) -> IntakeDecision:
    """
    Emergency passthrough — all intake models failed.
    Returns raw prompt with smart tier defaults.
    Never raises. Logs warning for monitoring.
    """
    logger.warning(
        "Intake passthrough triggered — all models unavailable. "
        "Session will run with unoptimized prompt at smart tier."
    )
    return IntakeDecision(
        needs_clarification=False,
        clarifying_question=None,
        optimized_prompt=prompt,
        tier="smart",
        output_type="analysis",
        reasoning="Intake service temporarily unavailable — running with smart tier default.",
    )


def call_intake(prompt: str) -> tuple:
    """
    Run intake with fallback chain. Returns (IntakeDecision, provider_used).

    Chain:
        Primary:   Claude Sonnet  (call_intake_sonnet — quality ceiling)
        Fallback1: GPT-4o Mini    (call_gpt4o_mini_intake — fast, reliable)
        Fallback2: Qwen 2.5 72B   (OpenRouter — third-provider diversity)
        Emergency: Passthrough    (smart tier defaults, never fails)
    """
    from backend.models.openai_client import call_gpt4o_mini_intake
    from backend.models.openrouter_client import call_intake_fallback1

    return call_with_fallback(
        primary_fn=lambda: call_intake_sonnet(prompt),
        fallback_fns=[
            lambda: call_gpt4o_mini_intake(prompt),
            lambda: call_intake_fallback1(prompt),
        ],
        emergency_fn=lambda: _intake_passthrough(prompt),
        role="intake",
    )


def _decision_to_config(decision: IntakeDecision) -> dict:
    """Convert an IntakeDecision into the session config dict."""
    return sanitize_config({
        "optimized_prompt": decision.optimized_prompt,
        "tier": decision.tier,
        "output_type": decision.output_type,
        "reasoning": decision.reasoning,
        "decision_domain": decision.decision_domain,
        "user_context": decision.user_context,
        "confirmed_assumptions": decision.confirmed_assumptions,
        "corrected_assumptions": decision.corrected_assumptions,
        "open_questions": decision.open_questions,
        "session_title": decision.session_title,
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
        self._intake_provider: str = "unknown"

    def start(self) -> str:
        """
        Return the intake opening message shown before the user submits their prompt.

        Sets expectations: a few focused questions, not an interrogation.
        """
        return INTAKE_OPENING_MESSAGE

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
        decision, provider_used = call_intake(prompt)
        self._intake_provider = provider_used

        # Immigration guard: if the user mentioned immigration context but the
        # intake model closed without resolving visa_type, force a probing question.
        # This is a belt-and-suspenders check — the new system prompt already
        # instructs the model to ask, but the guard ensures it fires even if
        # the model completes too eagerly.
        if (
            not decision.needs_clarification
            and _has_immigration_context(prompt)
            and _has_unknown_visa_type(decision)
        ):
            logger.info(
                "[intake] Immigration guard fired — visa_type unresolved. "
                "Forcing probing question before research begins."
            )
            probing_question = (
                "What visa type are you currently on? "
                "(e.g., H-1B, L-1, O-1, F-1 OPT/STEM OPT, TN, "
                "pending green card, or other)"
            )
            self._original_prompt = prompt
            self._clarifying_question = probing_question
            return {
                "status": "clarifying",
                "clarifying_question": probing_question,
                "suggested_options": [
                    "H-1B", "L-1", "O-1 / EB-1A", "Pending green card",
                    "F-1 OPT / STEM OPT", "TN / Other",
                ],
                "config": None,
            }

        if decision.needs_clarification:
            self._original_prompt = prompt
            self._clarifying_question = decision.clarifying_question
            return {
                "status": "clarifying",
                "clarifying_question": decision.clarifying_question,
                "suggested_options": decision.suggested_options,
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
            "IMPORTANT: The optimized_prompt must preserve all proper nouns from the "
            "original prompt exactly as written. Do not substitute model names, product "
            "names, or version numbers — even if you believe they are incorrect or refer "
            "to unreleased products. The research models will handle verification. "
            "Incorporate the user's clarification answer to add context and specificity, "
            "but keep the original proper nouns intact."
        )
        decision, provider_used = call_intake(combined)
        self._intake_provider = provider_used
        self.complete = True
        self.session_config = _decision_to_config(decision)
        return {
            "status": "complete",
            "clarifying_question": None,
            "config": self.session_config,
        }
