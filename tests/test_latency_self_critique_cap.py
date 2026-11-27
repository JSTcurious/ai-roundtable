"""
tests/test_latency_self_critique_cap.py

docs/LATENCY_SPEC.md L5 / AC8: the self-critique prompt carries a length rule
and still names all six sections; the call gets a 1,500-token safety cap while
every other call_claude caller keeps 4,096. Output that hits the cap is still
used, marked as truncated.
"""

import asyncio
from unittest.mock import MagicMock, patch

from backend import router


def _response(text, stop_reason="end_turn"):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.stop_reason = stop_reason
    return resp


def _critique(response):
    with patch("backend.models.anthropic_client.call_claude", return_value=response) as call:
        notes = asyncio.run(router.call_self_critique(
            round1_responses={"gpt": "answer"},
            perplexity_findings="audit",
            optimized_prompt="brief",
        ))
    return notes, call


SECTIONS = (
    "UNSUPPORTED CLAIMS", "LAZY CONSENSUS", "PREMISE CHALLENGES",
    "GAPS", "TRACK COLLAPSE", "PERPLEXITY CONFLICTS",
)


def test_self_critique_has_1500_token_safety_cap():
    notes, call = _critique(_response("GAPS\n- none"))
    assert router.SELF_CRITIQUE_MAX_TOKENS == 1500
    assert call.call_args.kwargs["max_tokens"] == 1500
    assert notes == "GAPS\n- none"


def test_prompt_has_length_rule_and_all_sections():
    _, call = _critique(_response("GAPS\n- none"))
    system = call.call_args.kwargs["system"]
    flat = " ".join(system.split())  # ignore line wrapping
    assert "at most 3 bullets per section" in flat
    assert "Every section must appear" in flat
    for section in SECTIONS:
        assert f"\n{section}\n" in system, section


def test_truncated_critique_is_kept_and_marked():
    notes, _ = _critique(_response("GAPS\n- one\n- tw", stop_reason="max_tokens"))
    assert notes.startswith("GAPS\n- one\n- tw")
    assert notes.endswith(router.SELF_CRITIQUE_TRUNCATED_NOTE)


def test_call_claude_defaults_to_4096_and_accepts_override():
    from backend.models import anthropic_client

    client = MagicMock()
    with patch.object(anthropic_client, "_get_client", return_value=client):
        anthropic_client.call_claude(messages=[{"role": "user", "content": "q"}])
        anthropic_client.call_claude(messages=[{"role": "user", "content": "q"}], max_tokens=1200)
        anthropic_client.call_claude(messages=[{"role": "user", "content": "q"}], stream=True)

    create_calls = client.messages.create.call_args_list
    assert create_calls[0].kwargs["max_tokens"] == 4096
    assert create_calls[1].kwargs["max_tokens"] == 1200
    assert client.messages.stream.call_args.kwargs["max_tokens"] == 4096
