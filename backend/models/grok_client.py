"""
backend/models/grok_client.py

Grok client for ai-roundtable v2 — xAI direct API (OpenAI-compatible).

Grok's role in the roundtable:
    - Round 1: creative synthesis, lateral thinking, contrarian perspective

Tiers:
    quick   — grok-3-mini
    smart   — executor: grok-3-mini → advisor: grok-3
    deep    — grok-3

Functions:
    call_grok(messages, tier, system, stream)
        — primary call function used by Round 1
    call_grok_smart(messages, system)
        — two-call executor + advisor pattern for Smart tier
    call_grok_smart_async(messages, system)
        — async wrapper for smart tier
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
        _client = OpenAI(
            api_key=os.getenv("GROK_API_KEY"),
            base_url="https://api.x.ai/v1",
        )
    return _client


MODELS = {
    "quick": "grok-3-mini",
    "smart": "grok-3-mini",   # executor model for smart tier
    "deep":  "grok-3",
}

_ADVISOR_MODEL = "grok-3"

_ADVISOR_PROMPT = (
    "Review this response and produce an improved final version.\n\n"
    "Original request: {request}\n"
    "Response to review: {response}\n\n"
    "Identify gaps, weak reasoning, missing considerations. "
    "Output only the improved response — no preamble, no explanation."
)


def call_grok(
    messages: list,
    tier: str = "quick",
    system: str = None,
    stream: bool = False,
):
    """
    Call Grok with the given messages and tier.

    Args:
        messages: list of {"role": str, "content": str} dicts
        tier:     "quick" | "smart" | "deep"
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


def call_grok_smart(messages: list, system: str = None) -> dict:
    """
    Two-call executor + advisor pattern for Smart tier.

    1. grok-3-mini (executor) produces an initial response.
    2. grok-3 (advisor) reviews it and returns an improved version.

    Returns:
        {
            "executor_text":   str,
            "advisor_text":    str,   # use this as the final response
            "executor_tokens": int,
            "advisor_tokens":  int,
        }
    """
    exec_resp = call_grok(messages=messages, tier="smart", system=system)
    exec_text = exec_resp.choices[0].message.content

    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    advisor_messages = [{
        "role": "user",
        "content": _ADVISOR_PROMPT.format(request=last_user, response=exec_text),
    }]

    adv_resp = _get_client().chat.completions.create(
        model=_ADVISOR_MODEL,
        max_completion_tokens=4096,
        messages=advisor_messages,
    )
    adv_text = adv_resp.choices[0].message.content

    return {
        "executor_text":   exec_text,
        "advisor_text":    adv_text,
        "executor_tokens": exec_resp.usage.prompt_tokens + exec_resp.usage.completion_tokens,
        "advisor_tokens":  adv_resp.usage.prompt_tokens + adv_resp.usage.completion_tokens,
    }


async def call_grok_smart_async(messages: list, system=None) -> dict:
    """Async wrapper for smart tier — runs executor then advisor without blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(call_grok_smart, messages, system=system),
    )


async def call_research_grok_async(
    history: list, system: str, tier: str
) -> tuple:
    """
    Call Grok for research with fallback to stable model.
    Returns (response_text, availability_status).
    availability_status: "primary" | "fallback" | "unavailable"

    Grok participates in both Smart and Deep tiers.
    """
    loop = asyncio.get_event_loop()

    try:
        if tier == "smart":
            result = await loop.run_in_executor(
                None, partial(call_grok_smart, history, system=system)
            )
            return result["advisor_text"], "primary"
        else:
            result = await loop.run_in_executor(
                None, partial(call_grok, messages=history, tier="deep", system=system)
            )
            return result.choices[0].message.content, "primary"
    except Exception:
        try:
            result = await loop.run_in_executor(
                None, partial(call_grok, messages=history, tier="smart", system=system)
            )
            return result.choices[0].message.content, "fallback"
        except Exception:
            return "[Grok unavailable this session]", "unavailable"


def ping() -> dict:
    """
    Smoke test — sends a minimal message to confirm API key and connectivity.

    Returns:
        {"ok": True, "model": str, "response": str}
        {"ok": False, "error": str}
    """
    try:
        response = call_grok(
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
        print(f"✓ Grok connected — {result['model']}: {result['response']!r}")
    else:
        print(f"✗ Grok connection failed: {result['error']}")
