"""
backend/models/model_validator.py

Startup validation and CLI freshness checker for model IDs.

validate_model_config():
    Called on app startup. Checks all configured model IDs against
    provider APIs. Logs warnings for stale IDs. Never raises — fail open.

check_model_currency():
    Called by tools/check_models.py CLI. Shows tier matrix and flags
    stale IDs with suggested updates.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _list_anthropic_models() -> set:
    try:
        import anthropic
        client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY", "")
        )
        models = client.models.list()
        return {m.id for m in models.data}
    except Exception as e:
        logger.warning(f"Could not fetch Anthropic model list: {e}")
        return set()


def _list_openai_models() -> set:
    try:
        import openai
        client = openai.OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", "")
        )
        models = client.models.list()
        return {m.id for m in models.data}
    except Exception as e:
        logger.warning(f"Could not fetch OpenAI model list: {e}")
        return set()


def _list_google_models() -> set:
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", ""))
        models = genai.list_models()
        return {
            m.name.replace("models/", "")
            for m in models
            if "generateContent" in m.supported_generation_methods
        }
    except Exception as e:
        logger.warning(f"Could not fetch Google model list: {e}")
        return set()


def _list_xai_models() -> set:
    try:
        import httpx
        response = httpx.get(
            "https://api.x.ai/v1/models",
            headers={
                "Authorization": f"Bearer {os.environ.get('XAI_API_KEY', '')}"
            },
            timeout=10,
        )
        if response.status_code == 200:
            return {m["id"] for m in response.json().get("data", [])}
    except Exception as e:
        logger.warning(f"Could not fetch xAI model list: {e}")
    return set()


PROVIDER_FETCHERS = {
    "anthropic": _list_anthropic_models,
    "openai":    _list_openai_models,
    "google":    _list_google_models,
    "xai":       _list_xai_models,
}

MODEL_PREFIX_TO_PROVIDER = {
    "claude":  "anthropic",
    "gpt":     "openai",
    "gemini":  "google",
    "grok":    "xai",
    "llama":   None,   # Perplexity — no standard list API
}


def _infer_provider(model_id: str) -> Optional[str]:
    model_lower = model_id.lower()
    for prefix, provider in MODEL_PREFIX_TO_PROVIDER.items():
        if model_lower.startswith(prefix):
            return provider
    return None


def validate_model_config() -> list:
    """
    Startup validation. Check all configured model IDs against provider APIs.
    Logs warnings for stale IDs. Never raises. Returns list of warning strings.
    """
    from backend.models.model_config import (
        RESEARCH_GEMINI_SMART_EXECUTOR, RESEARCH_GEMINI_SMART_ADVISOR,
        RESEARCH_GEMINI_DEEP, RESEARCH_GEMINI_FALLBACK,
        RESEARCH_GPT_SMART_EXECUTOR, RESEARCH_GPT_SMART_ADVISOR,
        RESEARCH_GPT_DEEP, RESEARCH_GPT_FALLBACK,
        RESEARCH_GROK_SMART_EXECUTOR, RESEARCH_GROK_SMART_ADVISOR,
        RESEARCH_GROK_DEEP, RESEARCH_GROK_FALLBACK,
        RESEARCH_CLAUDE_SMART_EXECUTOR, RESEARCH_CLAUDE_SMART_ADVISOR,
        RESEARCH_CLAUDE_DEEP, RESEARCH_CLAUDE_FALLBACK,
        FACTCHECK_PRIMARY, FACTCHECK_FALLBACK1, FACTCHECK_FALLBACK2,
        SYNTHESIS_ANALYTICAL, SYNTHESIS_FACTUAL,
        INTAKE_PRIMARY, INTAKE_FALLBACK2,
    )

    models_to_check = {
        "gemini_smart_executor":  RESEARCH_GEMINI_SMART_EXECUTOR,
        "gemini_smart_advisor":   RESEARCH_GEMINI_SMART_ADVISOR,
        "gemini_deep":            RESEARCH_GEMINI_DEEP,
        "gemini_fallback":        RESEARCH_GEMINI_FALLBACK,
        "gpt_smart_executor":     RESEARCH_GPT_SMART_EXECUTOR,
        "gpt_smart_advisor":      RESEARCH_GPT_SMART_ADVISOR,
        "gpt_deep":               RESEARCH_GPT_DEEP,
        "gpt_fallback":           RESEARCH_GPT_FALLBACK,
        "grok_smart_executor":    RESEARCH_GROK_SMART_EXECUTOR,
        "grok_smart_advisor":     RESEARCH_GROK_SMART_ADVISOR,
        "grok_deep":              RESEARCH_GROK_DEEP,
        "grok_fallback":          RESEARCH_GROK_FALLBACK,
        "claude_smart_executor":  RESEARCH_CLAUDE_SMART_EXECUTOR,
        "claude_smart_advisor":   RESEARCH_CLAUDE_SMART_ADVISOR,
        "claude_deep":            RESEARCH_CLAUDE_DEEP,
        "claude_fallback":        RESEARCH_CLAUDE_FALLBACK,
        "factcheck_primary":      FACTCHECK_PRIMARY,
        "factcheck_fallback2":    FACTCHECK_FALLBACK2,
        "synthesis_analytical":   SYNTHESIS_ANALYTICAL,
        "synthesis_factual":      SYNTHESIS_FACTUAL,
        "intake_primary":         INTAKE_PRIMARY,
        "intake_fallback2":       INTAKE_FALLBACK2,
    }

    provider_models: dict[str, set] = {}
    warnings = []

    for role, model_id in models_to_check.items():
        if not model_id or "/" in model_id:
            # Skip OpenRouter models — no standard list API
            continue

        provider = _infer_provider(model_id)
        if provider is None:
            continue

        if provider not in provider_models:
            provider_models[provider] = PROVIDER_FETCHERS[provider]()

        available = provider_models[provider]
        if available and model_id not in available:
            msg = (
                f"Stale model ID: '{model_id}' (role: {role}) "
                f"not found in {provider} model list. "
                f"Update {role.upper()} in .env or model_config.py."
            )
            logger.warning(msg)
            warnings.append(msg)

    if warnings:
        logger.warning(
            f"{len(warnings)} stale model ID(s) found. "
            "Run: python -m tools.check_models --fix"
        )
    else:
        logger.info("Model config validation passed — all IDs current.")

    return warnings
