"""
backend/models/openai_client.py

GPT client for ai-roundtable v2 — OpenAI direct API.

GPT's role in the roundtable:
    - Round 1: structure, actionability, breadth

Tiers (v2):
    quick   — gpt-4o
    deep    — gpt-5
    (Smart tier / advisor pattern deferred to v2.1)

Functions:
    call_gpt(messages, tier, system, stream)
        — primary call function used by Round 1
    ping()
        — smoke test: confirm API key and connectivity
"""

import os
from openai import OpenAI

_client = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

MODELS = {
    "quick": "gpt-4o",
    "deep": "gpt-5",
}


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
        max_tokens=4096,
        messages=full_messages,
        stream=stream,
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
