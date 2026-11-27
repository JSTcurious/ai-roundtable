"""
backend/models/anthropic_client.py

Claude client for ai-roundtable v2 — Anthropic direct API.

Claude's role in the roundtable:
    - Orchestrator: conducts intake, synthesizes final deliverable
    - Synthesis: incorporates all model responses + Perplexity audit

Tiers (model IDs come from model_config.py):
    quick   — smart executor
    smart   — executor: RESEARCH_CLAUDE_SMART_EXECUTOR → advisor: RESEARCH_CLAUDE_SMART_ADVISOR
    deep    — RESEARCH_CLAUDE_DEEP

Functions:
    call_claude(messages, tier, system, stream)
        — primary call; intake, streaming Round 1, and synthesis
    call_claude_smart(messages, system)
        — two-call executor + advisor pattern for Smart tier
    call_claude_smart_async(messages, system)
        — async wrapper; runs call_claude_smart in a thread pool (non-blocking event loop)
    stream_claude_text(messages, system, model, on_token)
        — one streamed call; forwards each text chunk to an async callback
    ping()
        — smoke test: confirm API key and connectivity
"""

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

# All other imports after this line
import asyncio
import logging
import os
import threading
from functools import partial
from typing import Awaitable, Callable

from anthropic import Anthropic

from backend.models.model_config import get_advisor_model, get_executor_model
from backend.router import build_advisor_messages

logger = logging.getLogger(__name__)

_client = None

def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"), timeout=120.0)
    return _client

MODELS = {
    "quick": get_executor_model("smart", "claude"),
    "smart": get_executor_model("smart", "claude"),
    "deep":  get_advisor_model("deep", "claude"),
}

_ADVISOR_MODEL = get_advisor_model("smart", "claude")


def call_claude(
    messages: list,
    tier: str = "quick",
    system: str = None,
    stream: bool = False,
    model: str = None,
):
    """
    Call Claude with the given messages and tier.

    Args:
        messages: list of {"role": str, "content": str} dicts
        tier:     "quick" | "deep"
        system:   optional system prompt string
        stream:   if True, returns a streaming context manager
        model:    explicit model ID; overrides the tier lookup

    Returns:
        Non-streaming: anthropic.types.Message
        Streaming:     anthropic.Stream (use as context manager)
    """
    model = model or MODELS.get(tier, MODELS["quick"])
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

    1. The smart executor produces an initial response.
    2. The smart advisor reviews it and returns an improved version. The
       advisor gets the same system prompt and conversation as the executor.

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
    exec_resp = call_claude(messages=messages, system=system, model=MODELS["smart"])
    exec_text = exec_resp.content[0].text

    adv_resp = call_claude(
        messages=build_advisor_messages(messages, exec_text),
        system=system,
        model=_ADVISOR_MODEL,
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


class StreamFailed(RuntimeError):
    """
    The model side of a streamed call failed.

    tokens_sent tells the caller whether any text already reached on_token, so
    it can clear partial output before falling back. Errors raised by on_token
    itself (e.g. the client went away) are never wrapped in this class.
    """

    def __init__(self, cause: Exception, tokens_sent: bool):
        super().__init__(str(cause))
        self.tokens_sent = tokens_sent


async def stream_claude_text(
    messages: list,
    system: str,
    model: str,
    on_token: Callable[[str], Awaitable[None]],
) -> str:
    """
    Make one streamed Claude call, awaiting on_token(chunk) for each text chunk.

    The SDK stream is synchronous, so it runs in a thread and hands chunks to
    the event loop through a queue. If on_token raises, the thread is told to
    stop (closing the HTTP stream) and the exception propagates unchanged.

    Returns the full text. Raises StreamFailed if the model call fails.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()
    done = object()

    def _post(item) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:
            pass  # event loop already closed — nobody is listening

    def _run() -> None:
        try:
            with call_claude(messages=messages, system=system, model=model, stream=True) as stream:
                for chunk in stream.text_stream:
                    if stop.is_set():
                        return
                    if chunk:
                        _post(chunk)
        except Exception as exc:
            _post(exc)
        finally:
            _post(done)

    threading.Thread(target=_run, daemon=True).start()

    parts: list = []
    try:
        while True:
            item = await queue.get()
            if item is done:
                break
            if isinstance(item, Exception):
                raise StreamFailed(item, tokens_sent=bool(parts)) from item
            parts.append(item)
            await on_token(item)
    finally:
        stop.set()
    return "".join(parts)


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
        max_tokens=2000,
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


if __name__ == "__main__":
    result = ping()
    if result["ok"]:
        print(f"✓ Claude connected — {result['model']}: {result['response']!r}")
    else:
        print(f"✗ Claude connection failed: {result['error']}")
