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


def _extract_json(text: str) -> str:
    """Strip markdown code fences from a model response before JSON parsing."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```\s*$', '', text)
    return text.strip()


# ── Intake opening message ────────────────────────────────────────────────────

INTAKE_OPENING_MESSAGE = (
    "I'll ask a few focused questions before briefing the "
    "research panel — the more specific your answers, the more "
    "targeted the analysis. What are you working through?"
)

# ── Minimum questions per domain ──────────────────────────────────────────────
#
# The model alone cannot be trusted to decide when intake has enough context.
# We enforce a floor on clarifying turns per detected domain before intake is
# allowed to close. The model's clarifying_question is honored when present;
# only if the model closes early do we fall back to a canned question.

MINIMUM_QUESTIONS_REQUIRED: dict[str, int] = {
    "immigration_legal": 3,   # visa type, case stage, employer confirmed
    "career_transition": 2,   # current role, what draws them
    "financial":         2,   # decision type, risk tolerance
    "general":           1,   # situation
}

# Domain-detection keywords — intentionally narrow and deliberate. Matched as
# lower-case substrings against the accumulated conversation text.
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "immigration_legal": [
        "visa", "h-1b", "h1b", "immigration", "green card",
        "i-140", "i-485", "perm", "sponsorship", "opt", "status",
    ],
    "career_transition": [
        "job", "role", "career", "company",
        "offer", "leave", "transition", "position",
    ],
}

FALLBACK_QUESTIONS: dict[str, list[dict]] = {
    "immigration_legal": [
        {
            "question": "What stage is your immigration case at?",
            "options": [
                "Initial H-1B, no green card started",
                "PERM in progress",
                "I-140 approved",
                "I-485 filed and pending",
                "Not sure",
            ],
        },
        {
            "question": "Has the new employer confirmed they can sponsor or transfer your case?",
            "options": [
                "Yes, confirmed",
                "They said yes but no details",
                "Not discussed yet",
                "They cannot sponsor",
            ],
        },
    ],
    "career_transition": [
        {
            "question": "Do you have a concrete offer or are you still exploring?",
            "options": [
                "Concrete offer in hand",
                "Active conversations",
                "Early exploration",
            ],
        },
        {
            "question": "Is there a timeline or deadline pressure?",
            "options": [
                "Offer expires soon",
                "Within 1 month",
                "No hard deadline",
            ],
        },
    ],
}


def _detect_domain(text: str) -> Optional[str]:
    """
    Return the first domain whose keywords appear in `text`, or None.

    Immigration is checked before career because an immigration-charged prompt
    that also mentions "job" or "role" should be classified as immigration_legal
    (which carries the stricter minimum of 3 clarifying questions).
    """
    if not text:
        return None
    text_lower = text.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return domain
    return None


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
    raw = _extract_json(response.content[0].text)
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
        self.questions_asked: int = 0
        self.detected_domain: Optional[str] = None
        self._asked_questions: list[str] = []
        self._qa_history: list[tuple[str, str]] = []

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
        self._original_prompt = prompt
        self.detected_domain = _detect_domain(prompt)

        decision, provider_used = call_intake(prompt)
        self._intake_provider = provider_used
        return self._route_decision(decision, context_text=prompt)

    def respond(self, answer: str) -> dict:
        """
        Process the user's answer to the most recently asked clarifying question.

        Repeats until the per-domain minimum questions are met AND the model
        signals completion. If respond() is called after the session is already
        complete, returns the existing config without another API call.
        """
        if self.complete and self.session_config:
            return {
                "status": "complete",
                "clarifying_question": None,
                "config": self.session_config,
            }

        if self._clarifying_question:
            self._qa_history.append((self._clarifying_question, answer))

        # Domain may become detectable only after the user elaborates.
        if self.detected_domain is None:
            self.detected_domain = _detect_domain(self._accumulated_context())

        combined = self._build_combined_prompt()
        decision, provider_used = call_intake(combined)
        self._intake_provider = provider_used
        return self._route_decision(decision, context_text=self._accumulated_context())

    # ── Routing ──────────────────────────────────────────────────────────────

    def _route_decision(self, decision: IntakeDecision, context_text: str) -> dict:
        """
        Apply guards and minimum-question enforcement to an IntakeDecision.

        Returns a clarifying response (with a question — model's own, guard's
        visa probe, or a domain fallback) or a complete response.
        """
        # Immigration guard: immigration context present but visa_type unresolved.
        # Kept as an explicit probe because it's highly specific and takes
        # precedence over the generic fallback flow.
        if (
            not decision.needs_clarification
            and _has_immigration_context(context_text)
            and _has_unknown_visa_type(decision)
        ):
            probing_question = (
                "What visa type are you currently on? "
                "(e.g., H-1B, L-1, O-1, F-1 OPT/STEM OPT, TN, "
                "pending green card, or other)"
            )
            if probing_question not in self._asked_questions:
                logger.info(
                    "[intake] Immigration guard fired — visa_type unresolved. "
                    "Forcing probing question before research begins."
                )
                return self._ask(
                    probing_question,
                    [
                        "H-1B", "L-1", "O-1 / EB-1A", "Pending green card",
                        "F-1 OPT / STEM OPT", "TN / Other",
                    ],
                )

        # Honor the model's clarifying question when it genuinely wants one
        # and hasn't already asked it.
        if decision.needs_clarification and decision.clarifying_question:
            if decision.clarifying_question not in self._asked_questions:
                return self._ask(
                    decision.clarifying_question,
                    decision.suggested_options or [],
                )
            # Duplicate question — fall through to minimum check / close.

        # Minimum-question enforcement: even if the model says "done", we
        # refuse to close until the per-domain floor is met.
        domain = self.detected_domain or "general"
        minimum = MINIMUM_QUESTIONS_REQUIRED.get(
            domain, MINIMUM_QUESTIONS_REQUIRED["general"]
        )

        if self.questions_asked < minimum:
            fallback = self._next_fallback_question(domain)
            if fallback is not None:
                logger.info(
                    "[intake] Minimum (%d) not met for domain=%s "
                    "(questions_asked=%d) — using fallback question.",
                    minimum, domain, self.questions_asked,
                )
                return self._ask(fallback["question"], fallback["options"])
            # No fallback available for this domain — let the session close
            # rather than loop forever. "general" has no fallback bank by design.

        # Close the session.
        self.complete = True
        self.session_config = _decision_to_config(decision)
        return {
            "status": "complete",
            "clarifying_question": None,
            "config": self.session_config,
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _ask(self, question: str, options: list) -> dict:
        """Record a clarifying question and return the clarifying response dict."""
        self._clarifying_question = question
        self._asked_questions.append(question)
        self.questions_asked += 1
        return {
            "status": "clarifying",
            "clarifying_question": question,
            "suggested_options": options,
            "config": None,
        }

    def _next_fallback_question(self, domain: str) -> Optional[dict]:
        """Return the first fallback question for `domain` not already asked, or None."""
        for fq in FALLBACK_QUESTIONS.get(domain, []):
            if fq["question"] not in self._asked_questions:
                return fq
        return None

    def _accumulated_context(self) -> str:
        """Concatenate original prompt + all Q/A pairs for domain detection + guard checks."""
        parts: list[str] = [self._original_prompt or ""]
        for q, a in self._qa_history:
            parts.append(f"Q: {q}\nA: {a}")
        return "\n".join(parts)

    def _build_combined_prompt(self) -> str:
        """Assemble the prompt sent to the intake model after one or more answers."""
        history_lines: list[str] = []
        for q, a in self._qa_history:
            history_lines.append(f"Clarifying question asked: {q}")
            history_lines.append(f"User's answer: {a}")
        history_block = "\n".join(history_lines)
        return (
            f"Original prompt: {self._original_prompt}\n"
            f"{history_block}\n\n"
            "Based on the conversation so far, return an IntakeDecision. "
            "If critical context is still missing, set needs_clarification=true "
            "with a specific next question. Otherwise set needs_clarification=false "
            "and produce the final optimized_prompt.\n\n"
            "IMPORTANT: The optimized_prompt must preserve all proper nouns from the "
            "original prompt exactly as written. Do not substitute model names, product "
            "names, or version numbers — even if you believe they are incorrect or refer "
            "to unreleased products. The research models will handle verification. "
            "Incorporate the user's clarification answers to add context and specificity, "
            "but keep the original proper nouns intact."
        )
