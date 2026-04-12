"""
backend/models/google_client.py

Gemini client for ai-roundtable v2 — Google direct API (google-genai SDK).

Gemini's role in the roundtable:
    - Round 1: deep reasoning, challenging assumptions

Tiers (v2):
    quick   — gemini-2.5-flash
    deep    — gemini-2.5-pro
    (Smart tier / advisor pattern deferred to v2.1)

Functions:
    call_gemini(messages, tier, system, stream)
        — primary call function used by Round 1
    ping()
        — smoke test: confirm API key and connectivity
"""

import os
from google import genai
from google.genai import types

_client = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client

MODELS = {
    "quick": "gemini-2.5-flash",
    "deep": "gemini-2.5-pro",
}


def call_gemini(
    messages: list,
    tier: str = "quick",
    system: str = None,
    stream: bool = False,
):
    """
    Call Gemini with the given messages and tier.

    Args:
        messages: list of {"role": str, "content": str} dicts
                  "assistant" role is normalised to "model" (Gemini convention)
        tier:     "quick" | "deep"
        system:   optional system instruction string
        stream:   if True, uses generate_content_stream

    Returns:
        Non-streaming: google.genai.types.GenerateContentResponse
        Streaming:     generator of GenerateContentResponse chunks
    """
    model_name = MODELS.get(tier, MODELS["quick"])

    # Normalise roles: Gemini uses "user" / "model"
    contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    # Gemini requires the final message to have role="user".
    # In the roundtable, Gemini is called after Claude has responded, so the
    # transcript ends with role="model". Append a minimal turn to satisfy the API.
    if contents and contents[-1].role == "model":
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text="Please provide your analysis.")],
        ))

    config = types.GenerateContentConfig(
        max_output_tokens=4096,
        system_instruction=system or None,
    )

    if stream:
        return _get_client().models.generate_content_stream(
            model=model_name,
            contents=contents,
            config=config,
        )
    return _get_client().models.generate_content(
        model=model_name,
        contents=contents,
        config=config,
    )


def ping() -> dict:
    """
    Smoke test — sends a minimal message to confirm API key and connectivity.

    Returns:
        {"ok": True, "model": str, "response": str}
        {"ok": False, "error": str}
    """
    try:
        response = call_gemini(
            messages=[{"role": "user", "content": "Say 'pong' and nothing else."}],
            tier="quick",
        )
        text = response.text.strip()
        return {"ok": True, "model": MODELS["quick"], "response": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    result = ping()
    if result["ok"]:
        print(f"✓ Gemini connected — {result['model']}: {result['response']!r}")
    else:
        print(f"✗ Gemini connection failed: {result['error']}")
