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
from functools import partial

from google import genai
from google.genai import types

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
