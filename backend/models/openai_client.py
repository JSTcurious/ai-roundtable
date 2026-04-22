"""
backend/models/openai_client.py

GPT client for ai-roundtable v2 — OpenAI direct API.

GPT's role in the roundtable:
    - Round 1: structure, actionability, breadth
    - Intake: GPT-4o Mini analyzes prompts and returns structured IntakeDecision

Tiers:
    quick   — gpt-4o
    smart   — executor: gpt-4o → advisor: gpt-4o (gpt-5 when available)
    deep    — gpt-5

Functions:
    call_gpt(messages, tier, system, stream)
        — primary call function used by Round 1
    call_gpt_smart(messages, system)
        — two-call executor + advisor pattern for Smart tier
    call_gpt4o_mini_intake(prompt)
        — intake analysis via GPT-4o Mini; returns IntakeDecision
    ping()
        — smoke test: confirm API key and connectivity
"""

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# All other imports after this line
import asyncio
import os
import time
from functools import partial

from openai import OpenAI

from backend.models.intake_decision import IntakeDecision

_client = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=30.0)
    return _client

MODELS = {
    "quick": "gpt-4o",
    "smart": "gpt-4o",   # executor model for smart tier
    "deep":  "gpt-4o",
}

from backend.models.model_config import INTAKE_PRIMARY

# Intake model — sourced from model_config (env-overridable via INTAKE_PRIMARY)
INTAKE_MODEL = INTAKE_PRIMARY

# ── Intake system prompt ──────────────────────────────────────────────────────

def _build_intake_system_prompt() -> str:
    return """
You are the intake conductor for ai-roundtable — a deliberation
environment where frontier AI models work together on high-stakes
decisions. Your job is to gather enough context to brief the
research panel with a precise, assumption-free prompt.

A thorough intake produces a session worth acting on.
A shallow intake produces generic advice.

## Your Principles

Ask one question at a time. Always.
Acknowledge what the user said before asking the next question.
Never list multiple questions. Never make the user feel interrogated.
Adapt follow-up questions based on what you learn.
Stop when you have enough — not before.

## Step 1 — Mirror First

Before asking anything, reflect back what you heard in 1-2 sentences.
Warm, specific, conversational. Not a bullet list.

Then confirm: "Does that capture it, or is there something
important I missed?"

Wait for confirmation before proceeding.

## Step 2 — Identify the Decision Domain

From the user's description, identify which domain applies:

CAREER_TRANSITION: job changes, role switches, career pivots,
  offer evaluations, resignation timing

IMMIGRATION_LEGAL: visa decisions, status changes, employer
  sponsorship, green card strategy, travel risks

FINANCIAL: investments, major purchases, compensation decisions,
  equity evaluation, financial planning

PRODUCT_STRATEGY: build vs buy, roadmaps, market entry,
  pricing, go-to-market

TECHNICAL: architecture decisions, stack selection, system
  design, tooling evaluation

A session may span multiple domains — identify all that apply.

## Step 3 — Domain-Specific Probing

Probe each relevant domain before closing. Ask one question
at a time.

### For CAREER_TRANSITION, always ask:
- Current role and how long they have been in it
- What specifically draws them to the new opportunity
- Whether they have a concrete offer or are still exploring
- Their timeline pressure (do they have a deadline?)

### For IMMIGRATION_LEGAL — turn-by-turn sequence:

Never ask two questions in one turn. Each probing question
covers exactly one field.

Turn 1 — always ask visa type first:
  Ask only: what visa type are they currently on?
  (H-1B, L-1, O-1, F-1 OPT/STEM OPT, TN, pending green card, other)
  Wait for the answer before asking anything else.

Turn 2 — case stage, only for petition-based visa types:
  If visa type is H-1B, L-1, or pending green card:
    Ask what stage the case is at
    (e.g., I-140 approved? I-485 filed? How long pending? Priority date?)
  If visa type is TN, OPT, O-1, or any non-petition status:
    Skip case stage entirely. Go directly to Turn 3.

Turn 3 — employer dependency:
  Ask: is their current status employer-sponsored?

Turn 4 — new employer transfer:
  Ask: has the new employer confirmed they can support or
  transfer the case?

Turn 5 — attorney:
  Ask: have they consulted an immigration attorney yet?

These questions are not optional. Immigration context is the binding
constraint in any job change involving a visa. Do not proceed
to research without this information — or an explicit statement
from the user that they do not know yet and want to proceed anyway.

### For FINANCIAL, always ask:
- What is the financial decision specifically?
- What is their risk tolerance?
- What is their timeline?

### For PRODUCT_STRATEGY or TECHNICAL, always ask:
- What is the current state?
- What constraints are non-negotiable?
- What does success look like?

## Step 4 — Assumptions Summary

Before closing intake, present an explicit summary of all
assumptions and inferences you are making based on what
the user shared. Format it exactly like this:

"Before I brief the research panel, here is what I am working with:

ASSUMPTIONS
- [assumption 1 — state what you inferred, not what was said]
- [assumption 2]
- [assumption 3]

Is anything above wrong, incomplete, or based on a misreading?
Correct anything before I proceed — these assumptions will
shape every response the research panel gives."

Wait for the user to confirm or correct before closing.
If they correct something, acknowledge it and update your
internal understanding.

## Step 5 — Completion

When the user confirms the assumptions (or corrects them and
you have acknowledged the corrections), close the intake.

Say: "Here is how I will brief the research panel — let me
know if anything needs adjusting before I start:"

Then output a JSON object with exactly these fields:

{
  "needs_clarification": bool,
  "clarifying_question": string or null,
  "suggested_options": [],
  "optimized_prompt": string,
  "tier": "smart",
  "output_type": string,
  "reasoning": string,
  "use_case_family": string,
  "decision_domain": [list of domain strings],
  "user_context": {
    "current_situation": string,
    "what_they_want": string,
    "key_constraints": [list],
    "immigration_specifics": {
      "visa_type": string,
      "case_stage": string,
      "employer_sponsored": string,
      "new_employer_can_transfer": string,
      "attorney_consulted": string
    },
    "timeline_pressure": string,
    "risk_tolerance": string
  },
  "confirmed_assumptions": [list of strings],
  "corrected_assumptions": [list of strings],
  "open_questions": [list of strings],
  "session_title": string
}

## Field rules

needs_clarification: true if critical context is still missing
  that would materially change the research direction.
  For immigration cases: true if visa_type is unknown and the
  user has not explicitly said they don't know.

clarifying_question: ONE focused question. Null if not needed.

suggested_options: Generate 3-6 short options that directly
  answer the clarifying_question being asked. Options must be
  specific to the question — not generic.

  Rules:
  - For visa type question: options must be visa types
    e.g. ["H-1B", "L-1", "O-1 / EB-1A", "Pending green card",
           "F-1 OPT / STEM OPT", "TN / Other"]
  - For yes/no questions: ["Yes", "Not yet", "In progress"]
  - For stage questions: the actual stage options for that visa
  - For open-ended questions that require free text:
    return an empty list []
  - Never return generic options unrelated to the question
  - Never return options longer than 6 words each

PROPER NOUN PRESERVATION — CRITICAL:
  Never substitute model names, product names, version numbers, company
  names, or any named entity the user provided. Use them exactly as written.

optimized_prompt: refined, context-enriched version of the user's
  prompt. Preserve ALL user-provided proper nouns exactly.
  For immigration cases: include visa type, case stage, and
  employer dependency so models give specific not generic advice.

tier: always "smart". The user controls tier via the session UI.

output_type: e.g. "analysis", "comparison", "report", "plan",
  "decision", "research", "factual answer"

reasoning: one sentence explaining prompt direction and output type.

confirmed_assumptions: list of assumptions the user explicitly confirmed.
corrected_assumptions: list of assumptions the user corrected.
open_questions: things the user said they do not know yet.

## Quality Bar for the Optimized Prompt

The optimized_prompt must:
- Contain no assumptions that were not confirmed in intake
- Specify the user's exact situation including immigration details
- Name the desired output format explicitly
- Include constraints that will affect the answer
- Be specific enough that two different frontier models produce
  meaningfully different, non-generic responses
- For immigration cases: include visa type, case stage, and
  employer dependency so models give specific not generic advice

Return valid JSON only. No prose outside the JSON object.
"""


_INTAKE_SYSTEM = _build_intake_system_prompt()


def _is_retriable(exc: Exception) -> bool:
    """Return True if the exception warrants a retry (rate limit or transient error)."""
    msg = str(exc).lower()
    return ("429" in msg or "503" in msg or "rate" in msg
            or "unavailable" in msg or "rate_limit" in msg)


def _call_gpt4o_mini_intake_once(prompt: str) -> IntakeDecision:
    """Single attempt against INTAKE_MODEL — no retry logic."""
    response = _get_client().chat.completions.create(
        model=INTAKE_MODEL,
        max_tokens=512,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _INTAKE_SYSTEM},
            {"role": "user",   "content": prompt},
        ],
    )
    raw = response.choices[0].message.content or ""
    try:
        return IntakeDecision.model_validate_json(raw)
    except Exception as e:
        raise ValueError(
            f"GPT-4o Mini intake schema validation failed: {e}. "
            f"Raw response: {raw!r}"
        )


def call_gpt4o_mini_intake(prompt: str) -> IntakeDecision:
    """
    Analyze a user's intake prompt with GPT-4o Mini and return a structured decision.

    Uses json_object response_format to enforce JSON output. Validates the
    parsed JSON against the IntakeDecision schema.

    Retry policy:
      - Rate limit (429) and transient (503) errors: 3 attempts with
        exponential backoff (2 s -> 4 s -> raises).
      - All other errors raise immediately — no retry.

    Args:
        prompt: The user's raw prompt, or a combined clarification turn string.

    Returns:
        IntakeDecision with tier, optimized_prompt, and optional clarifying_question.

    Raises:
        ValueError:   if the API response fails schema validation (no retry).
        RuntimeError: if GPT-4o Mini is unavailable on all 3 attempts.
        Exception:    on any other API error (raised immediately).
    """
    last_exc = None
    delays = [2, 4]  # seconds between attempts 1->2 and 2->3

    for attempt in range(3):
        try:
            return _call_gpt4o_mini_intake_once(prompt)
        except Exception as exc:
            if _is_retriable(exc):
                last_exc = exc
                if attempt < len(delays):
                    time.sleep(delays[attempt])
                continue
            raise  # non-retriable errors raise immediately

    raise RuntimeError(
        "GPT-4o Mini intake unavailable after 3 attempts — please try again in a moment."
    ) from last_exc


# Role-based alias used by intake fallback chain
call_intake_primary = call_gpt4o_mini_intake


def call_for_chips(prompt: str, system: str, max_tokens: int = 200) -> str:
    """
    Call INTAKE_MODEL (GPT-4o Mini) with a custom prompt/system and return raw text.

    Used by generate_user_take_chips() in router.py. Shares the same model and
    client as intake to keep chip generation cheap and fast. No retry — chip
    generation is best-effort; failures return empty list (fail-open).
    """
    response = _get_client().chat.completions.create(
        model=INTAKE_MODEL,
        max_tokens=max_tokens,
        temperature=0.3,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
    )
    return response.choices[0].message.content or ""


# ── Round 1 call functions ────────────────────────────────────────────────────

# gpt-5 as advisor; fall back to gpt-4o if not yet available on this account
_ADVISOR_MODEL = "gpt-4o"
_ADVISOR_MODEL_FALLBACK = "gpt-4o"

_ADVISOR_PROMPT = (
    "Review this response and produce an improved final version.\n\n"
    "Original request: {request}\n"
    "Response to review: {response}\n\n"
    "Identify gaps, weak reasoning, missing considerations. "
    "Output only the improved response — no preamble, no explanation."
)


def call_gpt(
    messages: list,
    tier: str = "quick",
    system: str = None,
    stream: bool = False,
):
    """
    Call GPT with the given messages and tier.

    Args:
        messages: list of {"role": str, "content": str} dicts
        tier:     "quick" | "deep"
        system:   optional system prompt string — prepended as a system message
        stream:   if True, returns a streaming response

    Returns:
        Non-streaming: openai.types.chat.ChatCompletion
        Streaming:     generator of ChatCompletionChunk objects
    """
    model = MODELS.get(tier, MODELS["quick"])

    full_messages = []
    if system:
        full_messages.append({"role": "system", "content": system})
    full_messages.extend(messages)

    return _get_client().chat.completions.create(
        model=model,
        max_completion_tokens=4096,
        messages=full_messages,
        stream=stream,
    )


def call_gpt_smart(messages: list, system: str = None) -> dict:
    """
    Two-call executor + advisor pattern for Smart tier.

    1. gpt-4o (executor) produces an initial response.
    2. gpt-5 (advisor) reviews it and returns an improved version.
       Falls back to gpt-4o advisor if gpt-5 is unavailable.

    Args:
        messages: list of {"role": str, "content": str} dicts
        system:   optional system prompt — prepended as system message

    Returns:
        {
            "executor_text":   str,
            "advisor_text":    str,   # use this as the final response
            "executor_tokens": int,   # prompt + completion
            "advisor_tokens":  int,
        }
    """
    exec_resp = call_gpt(messages=messages, tier="smart", system=system)
    exec_text = exec_resp.choices[0].message.content

    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    advisor_messages = [{
        "role": "user",
        "content": _ADVISOR_PROMPT.format(request=last_user, response=exec_text),
    }]

    try:
        adv_resp = _get_client().chat.completions.create(
            model=_ADVISOR_MODEL,
            max_completion_tokens=4096,
            messages=advisor_messages,
        )
    except Exception as e:
        if "404" in str(e) or "model" in str(e).lower():
            adv_resp = _get_client().chat.completions.create(
                model=_ADVISOR_MODEL_FALLBACK,
                max_completion_tokens=4096,
                messages=advisor_messages,
            )
        else:
            raise
    adv_text = adv_resp.choices[0].message.content

    return {
        "executor_text":   exec_text,
        "advisor_text":    adv_text,
        "executor_tokens": exec_resp.usage.prompt_tokens + exec_resp.usage.completion_tokens,
        "advisor_tokens":  adv_resp.usage.prompt_tokens + adv_resp.usage.completion_tokens,
    }


async def call_gpt_smart_async(messages: list, system=None) -> dict:
    """Async wrapper for smart tier — runs executor then advisor without blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(call_gpt_smart, messages, system=system),
    )


async def call_research_gpt_async(
    history: list, system: str, tier: str
) -> tuple:
    """
    Call GPT for research with fallback to stable model.
    Returns (response_text, availability_status).
    availability_status: "primary" | "fallback" | "unavailable"
    """
    loop = asyncio.get_event_loop()

    try:
        if tier == "smart":
            result = await loop.run_in_executor(
                None, partial(call_gpt_smart, history, system=system)
            )
            return result["advisor_text"], "primary"
        else:
            result = await loop.run_in_executor(
                None, partial(call_gpt, messages=history, tier="deep", system=system)
            )
            return result.choices[0].message.content, "primary"
    except Exception:
        try:
            from backend.models.model_config import get_fallback_model
            result = await loop.run_in_executor(
                None, partial(call_gpt, messages=history, tier="smart", system=system)
            )
            return result.choices[0].message.content, "fallback"
        except Exception:
            return "[GPT unavailable this session]", "unavailable"


def ping() -> dict:
    """
    Smoke test — sends a minimal message to confirm API key and connectivity.

    Returns:
        {"ok": True, "model": str, "response": str}
        {"ok": False, "error": str}
    """
    try:
        response = call_gpt(
            messages=[{"role": "user", "content": "Say 'pong' and nothing else."}],
            tier="quick",
        )
        text = response.choices[0].message.content.strip()
        return {"ok": True, "model": response.model, "response": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    result = ping()
    if result["ok"]:
        print(f"✓ GPT connected — {result['model']}: {result['response']!r}")
    else:
        print(f"✗ GPT connection failed: {result['error']}")
