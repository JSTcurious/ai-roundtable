"""
backend/models/openai_client.py

GPT client for ai-roundtable v2 — OpenAI direct API.

GPT's role in the roundtable:
    - Round 1: structure, actionability, breadth

Tiers:
    quick   — gpt-4o
    smart   — executor: gpt-4o → advisor: gpt-4o (gpt-5 when available)
    deep    — gpt-5

Functions:
    call_gpt(messages, tier, system, stream)
        — primary call function used by Round 1
    call_gpt_smart(messages, system)
        — two-call executor + advisor pattern for Smart tier
    ping()
        — smoke test: confirm API key and connectivity
"""

import asyncio
import os
from functools import partial

from openai import OpenAI

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
