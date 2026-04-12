"""
backend/models/__init__.py

Model client package for ai-roundtable v2.

Exposes the four provider clients:
    anthropic_client   — Claude (Anthropic direct API)
    google_client      — Gemini (Google direct API)
    openai_client      — GPT (OpenAI direct API)
    perplexity_client  — Sonar (Perplexity via OpenAI-compatible API)

No GitHub Models. No abstractions over providers.
Each client handles its own tier switching (Quick / Smart / Deep Thinking).
"""
