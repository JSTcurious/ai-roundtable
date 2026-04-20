"""
backend/models/anthropic_client.py

Claude client for ai-roundtable v2 — Anthropic direct API.

Claude's role in the roundtable:
    - Orchestrator: conducts intake, synthesizes final deliverable
    - Synthesis: incorporates all model responses + Perplexity audit

Tiers:
    quick   — claude-sonnet-4-5
    smart   — executor: claude-sonnet-4-5 → advisor: claude-opus-4-5
    deep    — claude-opus-4-5

Functions:
    call_claude(messages, tier, system, stream)
        — primary call; intake, streaming Round 1, and synthesis
    call_claude_smart(messages, system)
        — two-call executor + advisor pattern for Smart tier
    call_claude_smart_async(messages, system)
        — async wrapper; runs call_claude_smart in a thread pool (non-blocking event loop)
    ping()
        — smoke test: confirm API key and connectivity
"""

import asyncio
import logging
import os
from functools import partial
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

from anthropic import Anthropic

logger = logging.getLogger(__name__)

_client = None

def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), timeout=30.0)
    return _client

MODELS = {
    "quick": "claude-sonnet-4-5",
    "smart": "claude-sonnet-4-5",   # executor model for smart tier
    "deep":  "claude-opus-4-5",
}

_ADVISOR_MODEL = "claude-opus-4-5"

_ADVISOR_PROMPT = (
    "Review this response and produce an improved final version.\n\n"
    "Original request: {request}\n"
    "Response to review: {response}\n\n"
    "Identify gaps, weak reasoning, missing considerations. "
    "Output only the improved response — no preamble, no explanation."
)


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


def call_claude_smart(messages: list, system: str = None) -> dict:
    """
    Two-call executor + advisor pattern for Smart tier.

    1. claude-sonnet-4-5 (executor) produces an initial response.
    2. claude-opus-4-5 (advisor) reviews it and returns an improved version.

    Args:
        messages: list of {"role": str, "content": str} dicts
        system:   optional system prompt string

    Returns:
        {
            "executor_text":   str,
            "advisor_text":    str,   # use this as the final response
            "executor_tokens": int,   # input + output
            "advisor_tokens":  int,
        }
    """
    client = _get_client()
    kwargs = dict(model=MODELS["smart"], max_tokens=4096, messages=messages)
    if system:
        kwargs["system"] = system
    exec_resp = client.messages.create(**kwargs)
    exec_text = exec_resp.content[0].text

    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    adv_resp = client.messages.create(
        model=_ADVISOR_MODEL,
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": _ADVISOR_PROMPT.format(request=last_user, response=exec_text),
        }],
    )
    adv_text = adv_resp.content[0].text

    return {
        "executor_text":   exec_text,
        "advisor_text":    adv_text,
        "executor_tokens": exec_resp.usage.input_tokens + exec_resp.usage.output_tokens,
        "advisor_tokens":  adv_resp.usage.input_tokens + adv_resp.usage.output_tokens,
    }


async def call_claude_smart_async(messages: list, system=None) -> dict:
    """Async wrapper for smart tier — runs executor then advisor without blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(call_claude_smart, messages, system=system),
    )


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


# ── Intake fallback2 ─────────────────────────────────────────────────────────

async def call_research_claude_async(
    history: list, system: str, tier: str
) -> tuple:
    """
    Call Claude for research with fallback to stable model.
    Returns (response_text, availability_status).
    availability_status: "primary" | "fallback" | "unavailable"
    """
    loop = asyncio.get_event_loop()

    try:
        if tier == "smart":
            result = await call_claude_smart_async(history, system)
            return result["advisor_text"], "primary"
        else:
            result = await loop.run_in_executor(
                None, partial(call_claude, messages=history, tier="deep", system=system)
            )
            return result.content[0].text, "primary"
    except Exception as exc:
        logger.error("[claude-r1] Primary call failed: %s: %s", type(exc).__name__, exc)
        try:
            result = await loop.run_in_executor(
                None, partial(call_claude, messages=history, tier="smart", system=system)
            )
            return result.content[0].text, "fallback"
        except Exception as exc:
            logger.error("[claude-r1] Research call failed: %s: %s", type(exc).__name__, exc)
            return "[Claude unavailable this session]", "unavailable"


def call_intake_fallback2(prompt: str):
    """
    Intake fallback2 — Claude Haiku (Anthropic) as last-resort intake model.

    Uses INTAKE_FALLBACK2 model ID from model_config.
    Same IntakeDecision schema and system prompt as primary.

    Args:
        prompt: The user's raw prompt, or combined clarification turn string.

    Returns:
        IntakeDecision

    Raises:
        ValueError:   if response fails schema validation.
        RuntimeError: on API failure.
    """
    import json
    from backend.models.intake_decision import IntakeDecision
    from backend.models.model_config import INTAKE_FALLBACK2
    from backend.models.openai_client import _build_intake_system_prompt

    system_prompt = _build_intake_system_prompt().strip()
    response = _get_client().messages.create(
        model=INTAKE_FALLBACK2,
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
    try:
        return IntakeDecision.model_validate_json(raw)
    except Exception as e:
        raise ValueError(
            f"Claude Haiku intake schema validation failed: {e}. Raw: {raw!r}"
        )


def call_for_chips(prompt: str, system: str, max_tokens: int = 200) -> str:
    """
    Call Claude Sonnet with a custom prompt/system and return raw text.

    Used by generate_user_take_chips() in router.py for YOUR TAKE chip
    generation. Same signature as openai_client.call_for_chips so router.py
    can swap the import without changing call sites.

    No retry — chip generation is best-effort; failures return empty list
    (fail-open) via the caller's except block.
    """
    from backend.models.model_config import INTAKE_PRIMARY

    response = _get_client().messages.create(
        model=INTAKE_PRIMARY,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text or ""


if __name__ == "__main__":
    result = ping()
    if result["ok"]:
        print(f"✓ Claude connected — {result['model']}: {result['response']!r}")
    else:
        print(f"✗ Claude connection failed: {result['error']}")
