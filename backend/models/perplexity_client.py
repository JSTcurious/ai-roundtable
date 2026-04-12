"""
backend/models/perplexity_client.py

Perplexity (Sonar) client — DEFERRED TO v2.1.

In v2, all calls return a "not configured" placeholder.
No API calls are made. No key is required.

When v2.1 ships:
    - Restore full implementation from git history
    - Perplexity audits Claude, Gemini, and GPT Round 1 responses
    - Returns factual findings with citations
    - Runs after Round 1, before Claude synthesis
    - Fact-checker ONLY — never responds to user prompts directly

Tiers (v2.1):
    quick   — sonar
    deep    — sonar-pro

Functions:
    audit(model_responses, tier)  — stub, returns placeholder string
    ping()                        — stub, returns not-configured dict
"""

MODELS = {
    "quick": "sonar",
    "deep": "sonar-pro",
}

NOT_CONFIGURED = "Perplexity audit coming in v2.1."


def audit(model_responses: dict, tier: str = "quick") -> str:
    """
    Stub — Perplexity audit deferred to v2.1.
    Returns a placeholder string. No API call is made.
    Claude synthesis proceeds without audit input.
    """
    return NOT_CONFIGURED


def ping() -> dict:
    """
    Stub — returns not-configured status without attempting a connection.
    """
    return {"ok": None, "skipped": True, "reason": "deferred to v2.1"}
