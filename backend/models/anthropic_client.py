"""
backend/models/anthropic_client.py

Claude client for ai-roundtable v2 — Anthropic direct API.

Claude's role in the roundtable:
    - Orchestrator: conducts intake, synthesizes final deliverable
    - Round 1: reasoning, synthesis, natural prose
    - Synthesis: incorporates all model responses + Perplexity audit

Tiers (v2):
    quick   — claude-sonnet-4-5
    deep    — claude-opus-4-5
    (Smart tier / advisor pattern deferred to v2.1)

Functions:
    call_claude(messages, tier, system, stream)
        — primary call function used by intake, Round 1, and synthesis
    ping()
        — smoke test: confirm API key and connectivity
"""

import os
from anthropic import Anthropic

_client = None

def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client

MODELS = {
    "quick": "claude-sonnet-4-5",
    "deep": "claude-opus-4-5",
}


def call_claude(
    messages: list,
    tier: str = "quick",
    system: str = None,
    stream: bool = False,
):
    """
    Call Claude with the given messages and tier.

    Args:
        messages: list of {"role": str, "content": str} dicts
        tier:     "quick" | "deep"
        system:   optional system prompt string
        stream:   if True, returns a streaming context manager

    Returns:
        Non-streaming: anthropic.types.Message
        Streaming:     anthropic.Stream (use as context manager)
    """
    model = MODELS.get(tier, MODELS["quick"])
    kwargs = dict(
        model=model,
        max_tokens=4096,
        messages=messages,
    )
    if system:
        kwargs["system"] = system

    if stream:
        return _get_client().messages.stream(**kwargs)
    return _get_client().messages.create(**kwargs)


def ping() -> dict:
    """
    Smoke test — sends a minimal message to confirm API key and connectivity.

    Returns:
        {"ok": True, "model": str, "response": str}
        {"ok": False, "error": str}
    """
    try:
        response = call_claude(
            messages=[{"role": "user", "content": "Say 'pong' and nothing else."}],
            tier="quick",
        )
        text = response.content[0].text.strip()
        return {"ok": True, "model": response.model, "response": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    result = ping()
    if result["ok"]:
        print(f"✓ Claude connected — {result['model']}: {result['response']!r}")
    else:
        print(f"✗ Claude connection failed: {result['error']}")
