"""
backend/models/model_config.py

Resolved model IDs for every pipeline role. IDs are not written here: they
live in model_registry.json and are chosen at import time by
registry.resolve() — see docs/MODEL_REGISTRY_SPEC.md.

Resolution runs once per process:
    1. Load and validate model_registry.json.
    2. Unless MODEL_DISCOVERY=0, read provider model lists (availability,
       retirement dates) — best effort, never blocks startup.
    3. Apply per-role env overrides (RESEARCH_GPT_DEEP, SYNTHESIS_ANALYTICAL, …),
       which always win.

The constants below keep their historical names so call sites are unchanged.
A role with no eligible model resolves to None; callers' existing error paths
then report that seat or stage as unavailable.

Smart tier uses Executor + Advisor; Deep uses one top model per lab.
Factcheck always uses deep audit depth (~2000 tokens) — see ADR 004 addendum.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from backend.models import discovery
from backend.models.registry import env_overrides, load_registry, resolve

logger = logging.getLogger(__name__)

REGISTRY = load_registry()
DISCOVERY = discovery.discover() if os.getenv("MODEL_DISCOVERY", "1") != "0" else {}
RESOLUTION = resolve(REGISTRY, availability=DISCOVERY, overrides=env_overrides(REGISTRY))
_M = RESOLUTION.models

# ── Research ──────────────────────────────────────────────────────────────────

RESEARCH_GEMINI_SMART_EXECUTOR = _M["research.gemini.executor"]
RESEARCH_GEMINI_SMART_ADVISOR  = _M["research.gemini.advisor"]
RESEARCH_GEMINI_DEEP           = _M["research.gemini.deep"]
RESEARCH_GEMINI_FALLBACK       = _M["research.gemini.fallback"]

RESEARCH_GPT_SMART_EXECUTOR = _M["research.gpt.executor"]
RESEARCH_GPT_SMART_ADVISOR  = _M["research.gpt.advisor"]
RESEARCH_GPT_DEEP           = _M["research.gpt.deep"]
RESEARCH_GPT_FALLBACK       = _M["research.gpt.fallback"]

RESEARCH_GROK_SMART_EXECUTOR = _M["research.grok.executor"]
RESEARCH_GROK_SMART_ADVISOR  = _M["research.grok.advisor"]
RESEARCH_GROK_DEEP           = _M["research.grok.deep"]
RESEARCH_GROK_FALLBACK       = _M["research.grok.fallback"]

RESEARCH_CLAUDE_SMART_EXECUTOR = _M["research.claude.executor"]
RESEARCH_CLAUDE_SMART_ADVISOR  = _M["research.claude.advisor"]
RESEARCH_CLAUDE_DEEP           = _M["research.claude.deep"]
RESEARCH_CLAUDE_FALLBACK       = _M["research.claude.fallback"]

# ── Fact-check ────────────────────────────────────────────────────────────────
# Perplexity primary (search-native, live citations); fallback1 stays within
# Perplexity; fallback2 crosses to OpenAI only on a full Perplexity outage.

FACTCHECK_PRIMARY   = _M["factcheck.primary"]
FACTCHECK_FALLBACK1 = _M["factcheck.fallback1"]
FACTCHECK_FALLBACK2 = _M["factcheck.fallback2"]

FACTCHECK_SMART_MAX_TOKENS = int(os.getenv("FACTCHECK_SMART_MAX_TOKENS", "800"))
FACTCHECK_DEEP_MAX_TOKENS  = int(os.getenv("FACTCHECK_DEEP_MAX_TOKENS",  "2000"))

# ── Synthesis ─────────────────────────────────────────────────────────────────
# Claude primary (ADR 002 addendum); open-weight fallback on a different provider.

SYNTHESIS_ANALYTICAL = _M["synthesis.primary"]
SYNTHESIS_FALLBACK   = _M["synthesis.fallback"]

# ── Intake ────────────────────────────────────────────────────────────────────
# Provider diversity across the chain: Anthropic → OpenAI → OpenRouter → passthrough.

INTAKE_PRIMARY   = _M["intake.primary"]
INTAKE_FALLBACK1 = _M["intake.fallback1"]
INTAKE_FALLBACK2 = _M["intake.fallback2"]


# ── Tier helper functions ─────────────────────────────────────────────────────

def get_executor_model(tier: str, lab: str) -> str:
    """
    Return the executor model ID for a lab at a given tier.

    For Deep tier, executor == advisor (no split — single top model).
    For Smart tier, returns the cost-effective executor model.

    Args:
        tier: "smart" | "deep"
        lab:  "gemini" | "gpt" | "grok" | "claude"

    Returns:
        Model ID string.
    """
    if tier == "deep":
        return get_advisor_model("deep", lab)

    executors = {
        "gemini": RESEARCH_GEMINI_SMART_EXECUTOR,
        "gpt":    RESEARCH_GPT_SMART_EXECUTOR,
        "grok":   RESEARCH_GROK_SMART_EXECUTOR,
        "claude": RESEARCH_CLAUDE_SMART_EXECUTOR,
    }
    return executors[lab]


def get_advisor_model(tier: str, lab: str) -> str:
    """
    Return the advisor model ID for a lab at a given tier.

    For Deep tier, the advisor IS the research model (no executor split).
    For Smart tier, returns the more capable advisor model.

    Args:
        tier: "smart" | "deep"
        lab:  "gemini" | "gpt" | "grok" | "claude"

    Returns:
        Model ID string.
    """
    if tier == "deep":
        deep_models = {
            "gemini": RESEARCH_GEMINI_DEEP,
            "gpt":    RESEARCH_GPT_DEEP,
            "grok":   RESEARCH_GROK_DEEP,
            "claude": RESEARCH_CLAUDE_DEEP,
        }
        return deep_models[lab]

    advisors = {
        "gemini": RESEARCH_GEMINI_SMART_ADVISOR,
        "gpt":    RESEARCH_GPT_SMART_ADVISOR,
        "grok":   RESEARCH_GROK_SMART_ADVISOR,
        "claude": RESEARCH_CLAUDE_SMART_ADVISOR,
    }
    return advisors[lab]


def get_fallback_model(lab: str) -> str:
    """Return the fallback model ID for a lab (used when primary fails)."""
    fallbacks = {
        "gemini": RESEARCH_GEMINI_FALLBACK,
        "gpt":    RESEARCH_GPT_FALLBACK,
        "grok":   RESEARCH_GROK_FALLBACK,
        "claude": RESEARCH_CLAUDE_FALLBACK,
    }
    return fallbacks[lab]


def get_all_labs() -> list:
    """Return all participating labs. All labs participate in both tiers."""
    return ["gemini", "gpt", "grok", "claude"]


def get_factcheck_max_tokens(tier: str) -> int:
    """
    Always use deep audit depth regardless of session tier.

    Rationale: fact-check is the grounding layer for synthesis.
    Shallow fact-check produces shallow grounding regardless of
    research tier. The cost difference (~$0.0008/session) is
    negligible. Latency addition (~10-15s) is acceptable for a
    tool positioned as serious deliberation.

    The tier parameter is kept for future flexibility but is
    intentionally ignored.
    """
    return FACTCHECK_DEEP_MAX_TOKENS  # always 2000 tokens
