"""
backend/models/perplexity_client.py

Perplexity (Sonar) client for ai-roundtable v2 — OpenAI-compatible API.

Perplexity runs in two phases per session:

  Phase 1 — pre-research (parallel with Gemini + GPT)
      research(prompt, tier)
      Live web search on the topic. Result stored, not streamed.

  Phase 2 — audit (after Gemini + GPT complete)
      audit(model_responses, research, tier)
      Cross-checks Gemini + GPT against the live research.
      Result streamed to frontend as perplexity_complete.

Tiers:
    quick   — sonar
    deep    — sonar-pro

Functions:
    research(prompt, tier)        — Phase 1 live web pre-research
    audit(model_responses,        — Phase 2 cross-check + findings
          research, tier)
    ping()                        — smoke test
"""

import os
from openai import OpenAI

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("PERPLEXITY_API_KEY"),
            base_url="https://api.perplexity.ai",
        )
    return _client


MODELS = {
    "quick": "sonar",
    "smart": "sonar-pro",   # sonar-pro for smart tier
    "deep":  "sonar-pro",
}


def research(prompt: str, tier: str = "quick") -> str:
    """
    Phase 1 — Live web pre-research on the topic.

    Runs in parallel with Gemini and GPT Round 1 responses.
    Result is stored server-side and used by audit(); never streamed
    directly to the frontend.

    Args:
        prompt: the session's optimized_prompt (or raw prompt)
        tier:   "quick" | "deep"

    Returns:
        Findings string with citations and dates.
    """
    model = MODELS.get(tier, MODELS["quick"])

    research_prompt = (
        f"Search the current web for the most relevant, up-to-date information on:\n"
        f"{prompt}\n\n"
        f"Focus on:\n"
        f"1. What practitioners say on Reddit, Hacker News, LinkedIn right now\n"
        f"2. Current job market requirements and hiring trends\n"
        f"3. Latest tool and framework updates in the last 6 months\n"
        f"4. Recent blog posts from practitioners\n"
        f"5. Current salary and market data\n\n"
        f"Return findings with citations and dates. "
        f"Flag anything that changed significantly in the last 6 months."
    )

    response = _get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": research_prompt}],
    )
    return response.choices[0].message.content.strip()


def _build_audit_prompt(
    round1_responses: dict,
    research_text: str,
    tier: str,
) -> str:
    """Build audit prompt with depth appropriate to tier."""
    responses_block = "\n\n".join(
        f"### {model}\n{text}"
        for model, text in round1_responses.items()
    )

    base = f"""
You are fact-checking AI model responses for accuracy and currency.

## Round-1 Responses to Audit
{responses_block}

## Pre-Research Context
{research_text or '(no pre-research available)'}
"""

    if tier == "deep":
        return base + """
## Deep Audit Instructions

Be comprehensive and adversarial. Check everything.

1. Verify EVERY specific factual claim (prices, dates, model versions,
   statistics, named entities) across all four model responses.
2. Map contradictions between models explicitly — when models disagree,
   state which is correct, why, and cite a source.
3. Research current practitioner consensus from live sources.
4. Identify which round-1 models were most reliable on this topic.
5. Flag your own confidence level on each correction.

Return all four sections with full depth. Do not abbreviate.
Cite specific sources for every correction — no vague references.
"""
    else:  # smart
        return base + """
## Smart Audit Instructions

Be targeted and signal-focused. Prioritize the most impactful findings.

1. Flag clearly wrong or outdated facts — focus on the most impactful errors.
2. Surface the top 3 most important pieces of missing current information.
3. Cite specific sources for every correction.
4. Keep each section tight — synthesis needs clear signal, not volume.

Return all four sections. Prioritize accuracy and clarity over completeness.
"""


def _build_audit_request(
    round1_responses: dict,
    research_text: str,
    tier: str,
    model: str = None,
) -> dict:
    """Build the full Perplexity API request dict."""
    from backend.models.model_config import FACTCHECK_PRIMARY, get_factcheck_max_tokens
    return {
        "model": model or FACTCHECK_PRIMARY,
        "max_tokens": get_factcheck_max_tokens(tier),
        "messages": [
            {
                "role": "user",
                "content": _build_audit_prompt(round1_responses, research_text, tier),
            }
        ],
    }


def _call_perplexity_audit(
    round1_responses: dict,
    research_text: str,
    tier: str,
    model: str = None,
) -> str:
    """Call Perplexity audit API with the given model."""
    req = _build_audit_request(round1_responses, research_text, tier, model=model)
    response = _get_client().chat.completions.create(**req)
    return response.choices[0].message.content.strip()


def _call_gpt_audit_with_web_search(
    round1_responses: dict,
    research_text: str,
    tier: str,
) -> str:
    """
    GPT fallback audit with web search tool — used only when Perplexity is down.
    Cross-provider last resort: different grounding architecture, lower reliability.
    """
    from openai import OpenAI
    from backend.models.model_config import FACTCHECK_FALLBACK2, get_factcheck_max_tokens
    import os

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = _build_audit_prompt(round1_responses, research_text, tier)
    prompt += "\n\nNote: You are acting as fact-checker. Search the web to verify claims."

    response = client.chat.completions.create(
        model=FACTCHECK_FALLBACK2,
        max_tokens=get_factcheck_max_tokens(tier),
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


def audit_with_fallback(
    round1_responses: dict,
    research_text: str,
    tier: str,
) -> tuple:
    """
    Run Perplexity audit with fallback chain.
    Returns (audit_text, provider_used).

    Chain:
        Primary:   Perplexity Sonar Pro  (FACTCHECK_PRIMARY)
        Fallback1: Perplexity Sonar      (FACTCHECK_FALLBACK1, same grounding)
        Fallback2: GPT-5.4 + web search  (FACTCHECK_FALLBACK2, cross-provider)
        Emergency: Degraded notice string (never raises)

    Both Perplexity tiers use the same Smart/Deep audit prompt.
    """
    from backend.models.resilient_caller import call_with_fallback as _call_with_fallback
    from backend.models.model_config import FACTCHECK_PRIMARY, FACTCHECK_FALLBACK1

    def _emergency_factcheck() -> str:
        return (
            "[Fact-check unavailable — all fact-check providers failed. "
            "Synthesis is based on round-1 model responses only. "
            "Apply additional skepticism to all factual claims. "
            "Verify key facts against official sources before acting.]"
        )

    return _call_with_fallback(
        primary_fn=lambda: _call_perplexity_audit(
            round1_responses, research_text, tier,
            model=FACTCHECK_PRIMARY,
        ),
        fallback_fns=[
            lambda: _call_perplexity_audit(
                round1_responses, research_text, tier,
                model=FACTCHECK_FALLBACK1,
            ),
            lambda: _call_gpt_audit_with_web_search(
                round1_responses, research_text, tier,
            ),
        ],
        emergency_fn=_emergency_factcheck,
        role="factcheck",
    )


def audit(model_responses: dict, research_text: str = "", tier: str = "smart") -> str:
    """
    Phase 2 — Cross-check model responses against live web research.
    Legacy single-call interface — use audit_with_fallback() for resilience.

    Args:
        model_responses: {"gemini": str, "gpt": str, "grok": str, ...}
        research_text:   findings from research() (Phase 1)
        tier:            "smart" | "deep"

    Returns:
        Structured audit string with citations and dates.
    """
    from backend.models.model_config import FACTCHECK_PRIMARY
    return _call_perplexity_audit(model_responses, research_text, tier, model=FACTCHECK_PRIMARY)


def ping() -> dict:
    """
    Smoke test — sends a minimal message to confirm API key and connectivity.

    Returns:
        {"ok": True, "model": str, "response": str}
        {"ok": False, "error": str}
    """
    try:
        response = _get_client().chat.completions.create(
            model=MODELS["quick"],
            messages=[{"role": "user", "content": "Say 'pong' and nothing else."}],
        )
        text = response.choices[0].message.content.strip()
        return {"ok": True, "model": response.model, "response": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    result = ping()
    if result["ok"]:
        print(f"✓ Perplexity connected — {result['model']}: {result['response']!r}")
    else:
        print(f"✗ Perplexity connection failed: {result['error']}")
