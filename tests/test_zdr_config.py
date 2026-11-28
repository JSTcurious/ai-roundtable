"""
tests/test_zdr_config.py — PRIVACY_SECURITY_SPEC AC7.

Every retention control that can be set in code is set:
  - OpenAI (research, intake fallback, chips, fact-check fallback2): store=False
  - OpenRouter (Qwen intake/synthesis fallback): provider zdr + data_collection=deny
  - xAI Grok: x-zero-data-retention response header is checked; a missing or
    "false" value prints one [PRIVACY] ⚠️ line per process.
Anthropic, Gemini and Perplexity have no request-level control; their
dashboard/contract requirements are documented where each client is created.

Run with:
    uv run pytest tests/test_zdr_config.py -v
"""

import inspect
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _chat_response(text="{}"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        model="m",
    )


# ── OpenAI ───────────────────────────────────────────────────────────────────

def test_call_gpt_passes_store_false():
    from backend.models import openai_client
    client = MagicMock()
    client.chat.completions.create.return_value = _chat_response("hi")
    with patch.object(openai_client, "_get_client", return_value=client):
        openai_client.call_gpt([{"role": "user", "content": "x"}])
    assert client.chat.completions.create.call_args.kwargs["store"] is False


def test_gpt_intake_passes_store_false():
    from backend.models import openai_client
    client = MagicMock()
    client.chat.completions.create.return_value = _chat_response(
        '{"needs_clarification": false, "tier": "smart"}'
    )
    with patch.object(openai_client, "_get_client", return_value=client):
        openai_client._call_gpt4o_mini_intake_once("x")
    assert client.chat.completions.create.call_args.kwargs["store"] is False


def test_chips_pass_store_false():
    from backend.models import openai_client
    client = MagicMock()
    client.chat.completions.create.return_value = _chat_response("a")
    with patch.object(openai_client, "_get_client", return_value=client):
        openai_client.call_for_chips("p", "s")
    assert client.chat.completions.create.call_args.kwargs["store"] is False


def test_factcheck_gpt_fallback_passes_store_false():
    from backend.models import perplexity_client
    client = MagicMock()
    client.chat.completions.create.return_value = _chat_response("audit")
    with patch("openai.OpenAI", return_value=client):
        perplexity_client._call_gpt_audit_with_web_search({"gpt": "x"}, "pre", "smart")
    assert client.chat.completions.create.call_args.kwargs["store"] is False


def test_every_openai_create_call_sets_store_false():
    """Static guard: a new call site in openai_client must not forget store=False."""
    from backend.models import openai_client
    source = inspect.getsource(openai_client)
    calls = source.count("chat.completions.create(")
    assert calls >= 3
    assert len(re.findall(r"^\s+store=False,$", source, re.MULTILINE)) == calls


# ── OpenRouter ───────────────────────────────────────────────────────────────

def test_openrouter_privacy_block():
    from backend.models.openrouter_client import OPENROUTER_PRIVACY
    assert OPENROUTER_PRIVACY == {"provider": {"zdr": True, "data_collection": "deny"}}


@pytest.mark.parametrize("call", ["intake", "synthesis"])
def test_openrouter_calls_send_privacy_block(call):
    from backend.models import openrouter_client
    client = MagicMock()
    client.chat.completions.create.return_value = _chat_response(
        '{"needs_clarification": false, "tier": "smart"}'
    )
    with patch.object(openrouter_client, "_get_client", return_value=client):
        if call == "intake":
            openrouter_client.call_intake_fallback1("x")
        else:
            openrouter_client.call_synthesis_fallback([{"role": "user", "content": "x"}], "sys")
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["extra_body"] == openrouter_client.OPENROUTER_PRIVACY


# ── xAI Grok ─────────────────────────────────────────────────────────────────

def _grok_client(header_value):
    raw = MagicMock()
    raw.headers = {} if header_value is None else {"x-zero-data-retention": header_value}
    raw.parse.return_value = _chat_response("grok")
    client = MagicMock()
    client.chat.completions.with_raw_response.create.return_value = raw
    return client


@pytest.mark.parametrize("header, warns", [("true", False), ("false", True), (None, True)])
def test_grok_checks_zdr_header(header, warns, capsys):
    from backend.models import grok_client
    with patch.object(grok_client, "_get_client", return_value=_grok_client(header)), \
         patch.object(grok_client, "_zdr_warned", False):
        resp = grok_client.call_grok([{"role": "user", "content": "x"}])
        grok_client.call_grok([{"role": "user", "content": "x"}])
    assert resp.choices[0].message.content == "grok"
    out = capsys.readouterr().out
    assert out.count("[PRIVACY]") == (1 if warns else 0)


# ── Documented dashboard requirements ────────────────────────────────────────

@pytest.mark.parametrize("module", [
    "anthropic_client", "google_client", "openai_client", "grok_client",
    "perplexity_client", "openrouter_client",
])
def test_retention_note_documented(module):
    import importlib
    source = inspect.getsource(importlib.import_module(f"backend.models.{module}"))
    assert "Data retention (docs/PRIVACY_SECURITY_SPEC.md §4.2)" in source
