"""
backend/ping_all.py

Smoke test all four model clients.

Usage:
    python3 -m backend.ping_all

Expects backend/.env to be present with all four API keys.
Loads the .env file automatically before running pings.
Perplexity is skipped — deferred to v2.1.
"""

import os
from pathlib import Path


def load_env():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        print("⚠  backend/.env not found — falling back to environment variables")
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def main():
    load_env()

    from backend.models.anthropic_client import ping as ping_claude
    from backend.models.google_client import ping as ping_gemini
    from backend.models.openai_client import ping as ping_gpt

    print("Running pings...\n")
    all_ok = True

    for name, fn in [("Claude", ping_claude), ("Gemini", ping_gemini), ("GPT", ping_gpt)]:
        result = fn()
        if result["ok"]:
            print(f"✓ {name:<12} {result['model']}: {result['response']!r}")
        else:
            print(f"✗ {name:<12} FAILED: {result['error']}")
            all_ok = False

    print(f"⚠ {'Perplexity':<12} SKIPPED: deferred to v2.1")

    print()
    print("Three clients connected." if all_ok else "One or more clients failed.")


if __name__ == "__main__":
    main()
