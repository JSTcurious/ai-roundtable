"""
backend/models/google_client.py

Gemini client for ai-roundtable v2 — Google direct API (google-genai SDK).

Gemini's role in the roundtable:
    - Round 1: deep reasoning, challenging assumptions

Tiers:
    quick   — gemini-2.5-flash
    smart   — executor: gemini-2.5-flash → advisor: gemini-2.5-pro
    deep    — gemini-2.5-pro

Functions:
    call_gemini(messages, tier, system, stream)
        — primary call function used by Round 1
    call_gemini_smart(messages, system)
        — two-call executor + advisor pattern for Smart tier
    call_gemini_smart_async(messages, system)
        — async wrapper; runs call_gemini_smart in a thread pool
    ping()
        — smoke test: confirm API key and connectivity
"""

import asyncio
import os
import time
from functools import partial

from google import genai
from google.api_core.exceptions import ServiceUnavailable
from google.genai import types

from backend.models.intake_decision import IntakeDecision

_client = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client

MODELS = {
    "quick": "gemini-2.5-flash",
    "smart": "gemini-2.5-flash",   # executor model for smart tier
    "deep":  "gemini-2.5-pro",
}

# Intake uses a separate model constant so it can be pinned or overridden independently
# of the round-1 research models. Reuses GOOGLE_API_KEY — no new credentials needed.
# Fallback order: env var → preview-05-20 → gemini-2.5-flash (stable, no date suffix)
INTAKE_MODEL = os.getenv("GEMINI_INTAKE_MODEL", "gemini-2.5-flash-preview-05-20")
_INTAKE_MODEL_FALLBACK = "gemini-2.5-flash"

GEMINI_INTAKE_SYSTEM = """
You are an intake analyst for an AI research roundtable. Your job is to
analyze a user's prompt and make two decisions:

1. CLARIFICATION: Does the prompt have enough context to produce a
   high-quality research session?

   - If the user's intent is ambiguous or a critical piece of context is
     missing, set needs_clarification to true and provide ONE focused
     clarifying question. Do not ask multiple questions.
   - If the prompt is clear enough to proceed, set needs_clarification
     to false and optimize the prompt directly.

2. TIER ASSIGNMENT: What research depth does this prompt require?

   - quick : factual lookups, simple comparisons, gut checks.
             Single-dimension questions with known answers.
   - smart : analysis, recommendations, technical evaluations.
             Requires weighing tradeoffs or synthesizing multiple sources.
   - deep  : architecture decisions, strategic plans, critical reports.
             High stakes, significant ambiguity, or complex dependencies.

   Assign tier based on complexity and stakes — not prompt length.
   A short prompt can require deep research.

Always return valid JSON matching the schema exactly. No prose outside the
JSON object.
"""


_INTAKE_MAX_RETRIES = 3
_INTAKE_RETRY_BASE_SECONDS = 2


def call_gemini_intake(prompt: str) -> IntakeDecision:
    """
    Analyze a user's intake prompt with Gemini Flash and return a structured decision.

    Uses response_schema to enforce typed JSON output — no free-form parsing required.

    Retry policy:
      - 503 UNAVAILABLE only: up to _INTAKE_MAX_RETRIES attempts with exponential
        backoff starting at _INTAKE_RETRY_BASE_SECONDS (2 s → 4 s → raises).
      - Other API errors: try _INTAKE_MODEL_FALLBACK once, then propagate.
      - Schema validation errors (ValueError): re-raise immediately, no retry.

    Args:
        prompt: The user's raw prompt, or a combined clarification turn string.

    Returns:
        IntakeDecision with tier, optimized_prompt, and optional clarifying_question.

    Raises:
        ValueError:   if the API response fails schema validation.
        RuntimeError: if Gemini returns 503 on all _INTAKE_MAX_RETRIES attempts.
        Exception:    on any other API error after the fallback model also fails.
    """
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=IntakeDecision,
        system_instruction=GEMINI_INTAKE_SYSTEM,
    )
    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]

    def _call_one(model_name: str) -> IntakeDecision:
        response = _get_client().models.generate_content(
            model=model_name, contents=contents, config=config,
        )
        try:
            return IntakeDecision.model_validate_json(response.text)
        except Exception as e:
            raise ValueError(
                f"Gemini intake schema validation failed ({model_name}): {e}. "
                f"Raw response: {response.text!r}"
            )

    def _call_with_model_fallback() -> IntakeDecision:
        """Try primary model; on non-503 API error, try fallback. 503 propagates."""
        try:
            return _call_one(INTAKE_MODEL)
        except (ValueError, ServiceUnavailable):
            raise  # schema errors and 503s are handled by the caller
        except Exception:
            if INTAKE_MODEL != _INTAKE_MODEL_FALLBACK:
                return _call_one(_INTAKE_MODEL_FALLBACK)
            raise

    for attempt in range(1, _INTAKE_MAX_RETRIES + 1):
        try:
            return _call_with_model_fallback()
        except ServiceUnavailable:
            if attempt < _INTAKE_MAX_RETRIES:
                delay = _INTAKE_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                time.sleep(delay)
            else:
                raise RuntimeError(
                    "Gemini intake unavailable after 3 retries — try again in a moment."
                )

_ADVISOR_PROMPT = (
    "Review this response and produce an improved final version.\n\n"
    "Original request: {request}\n"
    "Response to review: {response}\n\n"
    "Identify gaps, weak reasoning, missing considerations. "
    "Output only the improved response — no preamble, no explanation."
)


def call_gemini(
    messages: list,
    tier: str = "quick",
    system: str = None,
    stream: bool = False,
):
    """
    Call Gemini with the given messages and tier.

    Args:
        messages: list of {"role": str, "content": str} dicts
                  "assistant" role is normalised to "model" (Gemini convention)
        tier:     "quick" | "deep"
        system:   optional system instruction string
        stream:   if True, uses generate_content_stream

    Returns:
        Non-streaming: google.genai.types.GenerateContentResponse
        Streaming:     generator of GenerateContentResponse chunks
    """
    model_name = MODELS.get(tier, MODELS["quick"])

    # Normalise roles: Gemini uses "user" / "model"
    contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    # Gemini requires the final message to have role="user".
    # In the roundtable, Gemini is called after Claude has responded, so the
    # transcript ends with role="model". Append a minimal turn to satisfy the API.
    if contents and contents[-1].role == "model":
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text="Please provide your analysis.")],
        ))

    config = types.GenerateContentConfig(
        max_output_tokens=4096,
        system_instruction=system or None,
    )

    if stream:
        return _get_client().models.generate_content_stream(
            model=model_name,
            contents=contents,
            config=config,
        )
    return _get_client().models.generate_content(
        model=model_name,
        contents=contents,
        config=config,
    )


def call_gemini_smart(messages: list, system: str = None) -> dict:
    """
    Two-call executor + advisor pattern for Smart tier.

    1. gemini-2.5-flash (executor) produces an initial response.
    2. gemini-2.5-pro (advisor) reviews it and returns an improved version.

    Args:
        messages: list of {"role": str, "content": str} dicts
        system:   optional system instruction string

    Returns:
        {
            "executor_text":   str,
            "advisor_text":    str,   # use this as the final response
            "executor_tokens": int,   # prompt + candidates
            "advisor_tokens":  int,
        }
    """
    exec_resp = call_gemini(messages=messages, tier="smart", system=system)
    exec_text = exec_resp.text

    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    adv_resp = call_gemini(
        messages=[{"role": "user", "content": _ADVISOR_PROMPT.format(request=last_user, response=exec_text)}],
        tier="deep",  # gemini-2.5-pro
    )
    adv_text = adv_resp.text

    exec_meta = exec_resp.usage_metadata
    adv_meta  = adv_resp.usage_metadata

    return {
        "executor_text":   exec_text,
        "advisor_text":    adv_text,
        "executor_tokens": (getattr(exec_meta, "prompt_token_count", 0) or 0)
                           + (getattr(exec_meta, "candidates_token_count", 0) or 0),
        "advisor_tokens":  (getattr(adv_meta,  "prompt_token_count", 0) or 0)
                           + (getattr(adv_meta,  "candidates_token_count", 0) or 0),
    }


async def call_gemini_smart_async(messages: list, system=None) -> dict:
    """Async wrapper for smart tier — runs executor then advisor without blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(call_gemini_smart, messages, system=system),
    )


def ping() -> dict:
    """
    Smoke test — sends a minimal message to confirm API key and connectivity.

    Returns:
        {"ok": True, "model": str, "response": str}
        {"ok": False, "error": str}
    """
    try:
        response = call_gemini(
            messages=[{"role": "user", "content": "Say 'pong' and nothing else."}],
            tier="quick",
        )
        text = response.text.strip()
        return {"ok": True, "model": MODELS["quick"], "response": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    result = ping()
    if result["ok"]:
        print(f"✓ Gemini connected — {result['model']}: {result['response']!r}")
    else:
        print(f"✗ Gemini connection failed: {result['error']}")
