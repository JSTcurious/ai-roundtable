"""
backend/models/model_config.py

Single source of truth for all model IDs in ai-roundtable.
All values are env-overridable — change any model with a single .env change.
No model names appear in variable names — only roles.

Architecture:
    Two tiers only: smart (default) and deep (user opt-in).
    No quick tier — ai-roundtable is for serious deliberation.

Smart tier uses Executor + Advisor pattern:
    Each lab runs a cost-effective executor model first (streamed to user),
    then a more capable advisor model reviews and improves silently.

Deep tier uses top models throughout:
    Each lab runs its most capable model with full thinking budget.
    No executor/advisor split — single high-quality pass.

Grok participates in both Smart and Deep.
Deep sessions are assigned by intake for high-stakes questions, or upgraded by user.

Factcheck always uses deep audit depth (~2000 tokens output).
The Smart/Deep audit prompt distinction is preserved in perplexity_client.py
for future flexibility, but get_factcheck_max_tokens() always returns
FACTCHECK_DEEP_MAX_TOKENS. See ADR 004 addendum.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=False)


# ── Research — Gemini (Google) ────────────────────────────────────────────────
# All currently Preview — validate at startup via model_validator.py

# Smart executor: fast, cost-effective
RESEARCH_GEMINI_SMART_EXECUTOR = os.getenv(
    "RESEARCH_GEMINI_SMART_EXECUTOR", "gemini-3-flash-preview"
)
# Smart advisor / Deep: most capable
RESEARCH_GEMINI_SMART_ADVISOR = os.getenv(
    "RESEARCH_GEMINI_SMART_ADVISOR", "gemini-3.1-pro-preview"
)
RESEARCH_GEMINI_DEEP = os.getenv(
    "RESEARCH_GEMINI_DEEP", "gemini-3.1-pro-preview"
)
# Fallback: stable non-preview model
RESEARCH_GEMINI_FALLBACK = os.getenv(
    "RESEARCH_GEMINI_FALLBACK", "gemini-2.5-flash"
)

# ── Research — GPT (OpenAI) ───────────────────────────────────────────────────

RESEARCH_GPT_SMART_EXECUTOR = os.getenv(
    "RESEARCH_GPT_SMART_EXECUTOR", "gpt-5.4-mini"
)
RESEARCH_GPT_SMART_ADVISOR = os.getenv(
    "RESEARCH_GPT_SMART_ADVISOR", "gpt-5.4"
)
RESEARCH_GPT_DEEP = os.getenv(
    "RESEARCH_GPT_DEEP", "gpt-5.4"
)
RESEARCH_GPT_FALLBACK = os.getenv(
    "RESEARCH_GPT_FALLBACK", "gpt-5.4-mini"
)

# ── Research — Grok (xAI) ────────────────────────────────────────────────────
# Grok participates in both Smart and Deep.
# Smart executor: Grok 4.1 Fast reasoning ($0.20/M, 2M context)
# Deep: Grok 4.20 reasoning ($2.00/M)

RESEARCH_GROK_SMART_EXECUTOR = os.getenv(
    "RESEARCH_GROK_SMART_EXECUTOR", "grok-4.1-fast-reasoning"
)
RESEARCH_GROK_SMART_ADVISOR = os.getenv(
    "RESEARCH_GROK_SMART_ADVISOR", "grok-4.20-0309-reasoning"
)
RESEARCH_GROK_DEEP = os.getenv(
    "RESEARCH_GROK_DEEP", "grok-4.20-0309-reasoning"
)
RESEARCH_GROK_FALLBACK = os.getenv(
    "RESEARCH_GROK_FALLBACK", "grok-4.1-fast-non-reasoning"
)

# ── Research — Claude (Anthropic) ────────────────────────────────────────────
# Confirmed model IDs from platform.claude.com/docs/en/about-claude/models/overview
# Opus 4.7:  $5/$25 per MTok, 1M context, Jan 2026 knowledge cutoff
# Sonnet 4.6: $3/$15 per MTok, 1M context, Aug 2025 knowledge cutoff
# Haiku 4.5:  $1/$5 per MTok,  200K context, Feb 2025 knowledge cutoff

RESEARCH_CLAUDE_SMART_EXECUTOR = os.getenv(
    "RESEARCH_CLAUDE_SMART_EXECUTOR", "claude-sonnet-4-6"
)
RESEARCH_CLAUDE_SMART_ADVISOR = os.getenv(
    "RESEARCH_CLAUDE_SMART_ADVISOR", "claude-opus-4-7"
)
RESEARCH_CLAUDE_DEEP = os.getenv(
    "RESEARCH_CLAUDE_DEEP", "claude-opus-4-7"
)
RESEARCH_CLAUDE_FALLBACK = os.getenv(
    "RESEARCH_CLAUDE_FALLBACK", "claude-haiku-4-5-20251001"
)

# ── Fact-check ────────────────────────────────────────────────────────────────
# Perplexity is the primary fact-checker — search-native, live citations,
# structurally independent from all four round-1 providers.
#
# Fallback1 stays within Perplexity (cheaper Sonar tier).
# A cheaper Perplexity model is still structurally better for fact-checking
# than cross-provider web search — same grounding architecture, lower cost.
# Fallback2 crosses to OpenAI web search only on full Perplexity outage.
#
# Audit depth is controlled by prompt, not model:
#   Smart: targeted, signal-focused (~800 token output)
#   Deep:  comprehensive, adversarial (~2000 token output)

FACTCHECK_PRIMARY   = os.getenv(
    "FACTCHECK_PRIMARY",   "sonar-pro"  # Perplexity Sonar Pro — confirmed working Apr 2026
)
FACTCHECK_FALLBACK1 = os.getenv(
    "FACTCHECK_FALLBACK1", "sonar"      # Perplexity Sonar — cheaper tier, same grounding
)
FACTCHECK_FALLBACK2 = os.getenv(
    "FACTCHECK_FALLBACK2", "gpt-5.4"   # cross-provider last resort with web search
)

# Audit depth token limits — enforced at API level
FACTCHECK_SMART_MAX_TOKENS = int(os.getenv("FACTCHECK_SMART_MAX_TOKENS", "800"))
FACTCHECK_DEEP_MAX_TOKENS  = int(os.getenv("FACTCHECK_DEEP_MAX_TOKENS",  "2000"))

# ── Synthesis ─────────────────────────────────────────────────────────────────
# Analytical queries (RLHF, architecture, domain knowledge):
#   Claude Opus 4.7 — leads on reasoning, attribution, narrative synthesis
# Post-cutoff factual queries (pricing, model releases, current events):
#   GPT-5.4 — handles Perplexity grounded data without trained refusal
# Fallback (any synthesis failure):
#   Qwen 2.5 72B — open-weight, 100% eval score, different provider

SYNTHESIS_ANALYTICAL = os.getenv("SYNTHESIS_ANALYTICAL", "claude-opus-4-7")
SYNTHESIS_FACTUAL    = os.getenv("SYNTHESIS_FACTUAL",    "gpt-5.4")
SYNTHESIS_FALLBACK   = os.getenv("SYNTHESIS_FALLBACK",   "qwen/qwen-2.5-72b-instruct")

# ── Intake ────────────────────────────────────────────────────────────────────
# Intake assigns "smart" or "deep" based on prompt complexity.
# Deep is assigned for architecture decisions, build/buy, strategic choices,
# and high-stakes questions. Smart is the default for most sessions.
# If intake assigns deep, deep runs — user cannot downgrade. See ADR 003 addendum.
#
# Fallback chain uses provider diversity:
#   Primary:   GPT-4o Mini  (OpenAI — 16/16 eval, $0.23/1K sessions)
#   Primary:   Claude Sonnet (Anthropic — quality ceiling, full intent capture)
#   Fallback1: GPT-4o Mini  (OpenAI — fast, reliable second choice)
#   Fallback2: Qwen 2.5 72B (OpenRouter — third provider for diversity)
#   Emergency: Passthrough  (smart tier defaults, never fails user)

INTAKE_PRIMARY   = os.getenv("INTAKE_PRIMARY",   "claude-sonnet-4-6")
INTAKE_FALLBACK1 = os.getenv("INTAKE_FALLBACK1", "gpt-4o-mini")
INTAKE_FALLBACK2 = os.getenv("INTAKE_FALLBACK2", "qwen/qwen-2.5-72b-instruct")


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
