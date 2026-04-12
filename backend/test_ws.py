"""
backend/test_ws.py

WebSocket smoke test for ai-roundtable v2.

Connects to ws://localhost:8000/ws/session, sends a short prompt,
and prints each message as it arrives — confirming tokens stream
in real time from each model.

Usage (server must be running):
    # Terminal 1 — start server:
    python3 -m uvicorn backend.main:app --reload

    # Terminal 2 — run test:
    python3 -m backend.test_ws
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import websockets


def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


SESSION_CONFIG = {
    "use_case_family": "learning_career",
    "session_title": "WS Test",
    "output_type": "roadmap",
    "tier": "quick",
    "recommended_seats": ["claude", "gemini", "gpt"],
    "open_assumptions": [],
}

PROMPT = (
    "In exactly two sentences each, what is the single most important "
    "skill for an AI engineer to have in 2025? Be direct."
)


async def run():
    load_env()
    uri = "ws://localhost:8000/ws/session"

    print(f"Connecting to {uri} ...\n")

    token_counts = {"Claude": 0, "Gemini": 0, "GPT": 0}
    current_sender = None
    t_start = time.monotonic()

    async with websockets.connect(uri) as ws:
        # Send handshake
        await ws.send(json.dumps({
            "prompt": PROMPT,
            "session_config": SESSION_CONFIG,
            "history": [],
        }))

        print(f"Prompt sent. Waiting for tokens...\n")
        print("─" * 60)

        async for raw in ws:
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "session_started":
                print("[session_started]")

            elif mtype == "perplexity_thinking":
                print("[perplexity_thinking]")

            elif mtype == "perplexity_complete":
                print(f"[perplexity_complete] {len(msg.get('content') or '')} chars")

            elif mtype == "synthesis_thinking":
                print("[synthesis_thinking]")

            elif mtype == "token":
                sender = msg["sender"]
                token = msg["token"]
                if sender != current_sender:
                    if current_sender is not None:
                        print()  # newline between models
                    print(f"\n[{sender}] ", end="", flush=True)
                    current_sender = sender
                print(token, end="", flush=True)
                token_counts[sender] = token_counts.get(sender, 0) + 1

            elif mtype == "model_complete":
                print(f"\n── {msg['sender']} complete ──")

            elif mtype == "synthesis_complete":
                elapsed = time.monotonic() - t_start
                print(f"\n\n{'─'*60}")
                print(f"[synthesis_complete] {len(msg['content'])} chars")
                print(f"Elapsed: {elapsed:.1f}s")

            elif mtype == "session_complete":
                print(f"\n[session_complete]")
                print(f"\nToken counts: {token_counts}")
                break

            elif mtype == "error":
                print(f"\n[ERROR] {msg['message']}", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
