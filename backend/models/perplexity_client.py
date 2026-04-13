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


def audit(model_responses: dict, research_text: str = "", tier: str = "quick") -> str:
    """
    Phase 2 — Cross-check Gemini + GPT responses against live web research.

    Args:
        model_responses: {"gemini": str, "gpt": str}
        research_text:   findings from research() (Phase 1)
        tier:            "quick" | "deep"

    Returns:
        Structured audit string with citations and dates.
    """
    model = MODELS.get(tier, MODELS["quick"])

    gemini_response = model_responses.get("gemini", "")
    gpt_response = model_responses.get("gpt", "")

    audit_prompt = (
        f"You have live web research and two AI model responses on this topic.\n\n"
        f"Live research you gathered:\n{research_text or '(no pre-research available)'}\n\n"
        f"Gemini's response:\n{gemini_response or '(not available)'}\n\n"
        f"GPT's response:\n{gpt_response or '(not available)'}\n\n"
        f"Identify:\n"
        f"1. Facts that are outdated or incorrect per current web research\n"
        f"2. Important current information neither model mentioned\n"
        f"3. Tools or courses that have changed in relevance recently\n"
        f"4. What the current practitioner community actually recommends right now\n\n"
        f"Return a structured audit with citations and dates for all sources."
    )

    response = _get_client().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": audit_prompt}],
    )
    return response.choices[0].message.content.strip()


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
