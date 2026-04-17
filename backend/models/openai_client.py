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
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

MODELS = {
    "quick": "gpt-4o",
    "smart": "gpt-4o",   # executor model for smart tier
    "deep":  "gpt-4o",
}

# Intake model — pinned separately from round-1 so it can be changed independently
INTAKE_MODEL = os.getenv("INTAKE_MODEL", "gpt-4o-mini")

# ── Intake system prompt ──────────────────────────────────────────────────────
# Mirrors backend/models/google_client.py GEMINI_INTAKE_SYSTEM — kept here to
# avoid importing from google_client when the Google SDK may not be installed.

_INTAKE_SYSTEM = """
You are an intake analyst for an AI research roundtable. Your job is to
analyze a user's prompt and make two decisions:

1. CLARIFICATION: Does the prompt have enough context to produce a
   high-quality research session?

   - If the user's intent is ambiguous or a critical piece of context is
     missing, set needs_clarification to true and provide ONE focused
     clarifying question. Do not ask multiple questions.
   - If the prompt is clear enough to proceed, set needs_clarification
     to false and optimize the prompt directly.

2. PROPER NOUN PRESERVATION (critical rule):

   When the user provides specific proper nouns — model names, product
   names, version numbers, company names, or any named entity — treat
   them as correct and authoritative. Never substitute your own examples
   or alternatives.

   WRONG: User says "Claude Opus 4.7" -> you ask "do you mean Claude 3 Opus?"
   RIGHT: User says "Claude Opus 4.7" -> you use "Claude Opus 4.7" exactly

   WRONG: User says "GPT-5" -> your clarifying question lists "GPT-4" as
          an example of what they might mean
   RIGHT: User says "GPT-5" -> you use "GPT-5" exactly in all outputs

   If you are uncertain whether a named entity exists, do NOT ask the user
   to confirm using your own alternatives. Instead, ask about their INTENT
   or SCOPE only — never suggest replacement names.

3. TIER ASSIGNMENT: What research depth does this prompt require?

   - quick : factual lookups, simple comparisons, gut checks.
             Single-dimension questions with known answers.
   - smart : analysis, recommendations, technical evaluations.
             Requires weighing tradeoffs or synthesizing multiple sources.
   - deep  : architecture decisions, strategic plans, critical reports.
             High stakes, significant ambiguity, or complex dependencies.

   Assign tier based on complexity and stakes — not prompt length.
   A short prompt can require deep research.

Always return valid JSON matching the schema exactly. No prose outside the
JSON object. Required fields:
  needs_clarification (bool), clarifying_question (string or null),
  optimized_prompt (string), tier ("quick"|"smart"|"deep"),
  output_type (string), reasoning (string)
"""


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
