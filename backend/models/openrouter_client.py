"""
backend/models/openrouter_client.py

OpenRouter client for ai-roundtable v2.

Provides access to open-weight models (Qwen, DeepSeek, Llama) via
OpenRouter's OpenAI-compatible API. Used for:

  - Intake fallback1: Qwen 2.5 72B (INTAKE_FALLBACK1)
  - Synthesis fallback: Qwen 2.5 72B (SYNTHESIS_FALLBACK)

All model IDs sourced from model_config — never hardcoded here.
"""

import os
import re

from openai import OpenAI

_client = None


def _extract_json(text: str) -> str:
    """Strip markdown code fences from a model response before JSON parsing."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```\s*$', '', text)
    return text.strip()


# ── Data retention (docs/PRIVACY_SECURITY_SPEC.md §4.2) ──────────────────────
# Every request routes only to endpoints that keep no data and do not train:
#   zdr=True              → Zero Data Retention endpoints only
#   data_collection=deny  → exclude providers that store or train on prompts
# If no endpoint qualifies, OpenRouter errors instead of falling back to one
# that logs (verified 2026-11-28: qwen/qwen-2.5-72b-instruct has a ZDR
# endpoint, GET https://openrouter.ai/api/v1/endpoints/zdr). The same default
# can also be set account-wide in OpenRouter → Settings → Privacy.
OPENROUTER_PRIVACY = {"provider": {"zdr": True, "data_collection": "deny"}}


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            timeout=30.0,
            default_headers={
                "HTTP-Referer": "https://github.com/JSTcurious/ai-roundtable",
                "X-Title": "ai-roundtable",
            },
        )
    return _client


def call_intake_fallback1(prompt: str):
    """
    Intake fallback1 — Qwen 2.5 72B via OpenRouter as secondary intake model.

    Uses INTAKE_FALLBACK1 model ID from model_config.
    Same IntakeDecision schema and system prompt as primary.

    Args:
        prompt: The user's raw prompt, or combined clarification turn string.

    Returns:
        IntakeDecision

    Raises:
        ValueError:   if response fails schema validation.
        RuntimeError: on API failure.
    """
    from backend.models.intake_decision import IntakeDecision
    from backend.models.model_config import INTAKE_FALLBACK1
    from backend.models.openai_client import _build_intake_system_prompt

    system_prompt = _build_intake_system_prompt().strip()
    response = _get_client().chat.completions.create(
        model=INTAKE_FALLBACK1,
        max_tokens=2000,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": prompt},
        ],
        extra_body=OPENROUTER_PRIVACY,
    )
    raw = _extract_json(response.choices[0].message.content or "")
    try:
        return IntakeDecision.model_validate_json(raw)
    except Exception as e:
        raise ValueError(
            f"Qwen intake schema validation failed: {e}. Raw: {raw!r}"
        )


def call_synthesis_fallback(
    messages: list,
    system: str,
) -> str:
    """
    Synthesis fallback — Qwen 2.5 72B via OpenRouter.

    Used when SYNTHESIS_ANALYTICAL (Claude) fails. Open-weight model,
    different provider, 100% eval score on synthesis.

    Args:
        messages: list of {"role": str, "content": str} dicts
        system:   synthesis system prompt string

    Returns:
        Synthesis text string.
    """
    from backend.models.model_config import SYNTHESIS_FALLBACK

    full_messages = [{"role": "system", "content": system}] + messages
    response = _get_client().chat.completions.create(
        model=SYNTHESIS_FALLBACK,
        max_tokens=4096,
        messages=full_messages,
        extra_body=OPENROUTER_PRIVACY,
    )
    return response.choices[0].message.content or ""
