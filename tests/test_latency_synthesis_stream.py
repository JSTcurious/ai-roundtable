"""
tests/test_latency_synthesis_stream.py

docs/LATENCY_SPEC.md, PR 1 (L1 + L2): synthesis and refinement each make one
streamed Claude call.

AC1  smart-tier synthesis = one call to SYNTHESIS_ANALYTICAL, no executor+advisor
AC2  synthesis_token frames stream before synthesis_draft; draft = parsed raw text
AC3  failure before first token → Qwen fallback, no tokens; after → synthesis_reset first
AC4  refinement streams the same way; mid-stream failure → reset + unavailable draft
AC10 client gone mid-stream → handler exits, no fallback call
AC12 [TIMING] synthesis.first_token and refinement.N.first_token
"""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

from backend.router import REFINEMENT_MODEL, parse_closing_questions
from backend.models.model_config import SYNTHESIS_ANALYTICAL, SYNTHESIS_FALLBACK
from tests.test_ws_disconnect import HANDSHAKE, FakeWebSocket

DRAFT_CHUNKS = ["THE VERDICT\n", "Keep the cash. ", "\n\n? Does this fit?"]
REFINED_CHUNKS = ["THE VERDICT\n", "Revised: pay down half."]


class FakeStream:
    """Stands in for call_claude(..., stream=True): a context manager with text_stream."""

    def __init__(self, chunks, fail_after=None):
        self.chunks, self.fail_after = chunks, fail_after

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        for i, chunk in enumerate(self.chunks):
            if self.fail_after is not None and i == self.fail_after:
                raise RuntimeError("model boom")
            yield chunk
        if self.fail_after is not None and self.fail_after >= len(self.chunks):
            raise RuntimeError("model boom")


class FakeClaude:
    """Records every call_claude call; serves one FakeStream per streamed call."""

    def __init__(self, *streams):
        self.streams = list(streams)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if not kwargs.get("stream"):
            raise AssertionError("expected a streamed call")
        return self.streams.pop(0)


class DialogueSocket(FakeWebSocket):
    """Replies once to the first draft, then finalizes after the revision."""

    def __init__(self, reply=True, fail_on_type=None):
        super().__init__()
        self.reply = reply
        self.fail_on_type = fail_on_type

    async def send_json(self, data):
        if data.get("type") == self.fail_on_type:
            self.closed = True
            raise RuntimeError('Cannot call "send" once a close message has been sent.')
        await super().send_json(data)
        if data.get("type") == "synthesis_draft":
            if data["revision"] == 0 and self.reply:
                self.inbound.put_nowait({"type": "user_dialogue_response", "content": "push back"})
            else:
                self.inbound.put_nowait({"type": "finalize_synthesis"})


def _run_session(ws, claude, qwen=None):
    from backend import main

    def r1(text):
        return AsyncMock(return_value=(text, "primary"))

    qwen = qwen or MagicMock(return_value="QWEN VERDICT")

    async def scenario():
        ws.inbound.put_nowait(HANDSHAKE)
        ws.inbound.put_nowait({"type": "prompt_confirmed"})
        await asyncio.wait_for(main.session_websocket(ws), timeout=5)

    with patch.object(main, "call_research_gemini_async", r1("g")), \
         patch.object(main, "call_research_gpt_async", r1("p")), \
         patch.object(main, "call_research_grok_async", r1("k")), \
         patch.object(main, "call_research_claude_async", r1("c")), \
         patch.object(main, "perplexity_research", MagicMock(return_value="pre")), \
         patch.object(main, "audit_with_fallback", MagicMock(return_value=("AUDIT", "primary", []))), \
         patch.object(main, "call_self_critique", AsyncMock(return_value="- critique")), \
         patch.object(main, "call_claude_smart_async", AsyncMock(side_effect=AssertionError("executor+advisor used"))), \
         patch("backend.models.anthropic_client.call_claude", claude), \
         patch("backend.models.openrouter_client.call_synthesis_fallback", qwen):
        asyncio.run(scenario())
    return qwen


def _types(ws):
    return [m["type"] for m in ws.sent]


def _tokens_between(ws, start, end):
    return "".join(m["token"] for m in ws.sent[start:end] if m["type"] == "synthesis_token")


def _draft_indexes(ws):
    return [i for i, m in enumerate(ws.sent) if m["type"] == "synthesis_draft"]


# ── AC1 ───────────────────────────────────────────────────────────────────────

def test_ac1_smart_synthesis_is_one_call_to_synthesis_analytical():
    from backend import main

    response = MagicMock()
    response.content = [MagicMock(text="THE VERDICT\nbody")]
    with patch.object(main, "call_claude", MagicMock(return_value=response)) as call, \
         patch.object(main, "call_claude_smart_async", AsyncMock()) as smart:
        text = asyncio.run(main.call_synthesis_async(
            SYNTHESIS_ANALYTICAL, [{"role": "user", "content": "q"}], "sys", "smart"
        ))
    assert text == "THE VERDICT\nbody"
    assert call.call_count == 1
    assert call.call_args.kwargs["model"] == SYNTHESIS_ANALYTICAL
    smart.assert_not_called()


# ── AC1 + AC2 ─────────────────────────────────────────────────────────────────

def test_ac2_session_synthesis_streams_then_sends_parsed_draft():
    ws = DialogueSocket(reply=False)
    claude = FakeClaude(FakeStream(DRAFT_CHUNKS))
    _run_session(ws, claude)

    assert len(claude.calls) == 1
    assert claude.calls[0]["model"] == SYNTHESIS_ANALYTICAL

    first_draft = _draft_indexes(ws)[0]
    raw = "".join(DRAFT_CHUNKS)
    assert _tokens_between(ws, 0, first_draft) == raw
    content, questions = parse_closing_questions(raw)
    draft = ws.sent[first_draft]
    assert draft["content"] == content
    assert draft["closing_questions"] == questions
    assert draft["synthesis_route"] == "primary"
    assert draft["synthesis_model_used"] == SYNTHESIS_ANALYTICAL
    assert "synthesis_reset" not in _types(ws)


# ── AC3 ───────────────────────────────────────────────────────────────────────

def test_ac3_failure_before_first_token_falls_back_without_tokens():
    ws = DialogueSocket(reply=False)
    qwen = _run_session(ws, FakeClaude(FakeStream(DRAFT_CHUNKS, fail_after=0)))

    qwen.assert_called_once()
    types = _types(ws)
    assert "synthesis_token" not in types
    assert "synthesis_reset" not in types
    draft = ws.sent[_draft_indexes(ws)[0]]
    assert draft["synthesis_route"] == "fallback"
    assert draft["synthesis_model_used"] == SYNTHESIS_FALLBACK


def test_ac3_failure_after_tokens_resets_before_fallback_draft():
    ws = DialogueSocket(reply=False)
    qwen = _run_session(ws, FakeClaude(FakeStream(DRAFT_CHUNKS, fail_after=2)))

    qwen.assert_called_once()
    types = _types(ws)
    last_token = max(i for i, t in enumerate(types) if t == "synthesis_token")
    reset = types.index("synthesis_reset")
    assert last_token < reset < _draft_indexes(ws)[0]
    assert ws.sent[_draft_indexes(ws)[0]]["synthesis_route"] == "fallback"


# ── AC4 ───────────────────────────────────────────────────────────────────────

def test_ac4_refinement_streams_and_increments_revision():
    ws = DialogueSocket()
    claude = FakeClaude(FakeStream(DRAFT_CHUNKS), FakeStream(REFINED_CHUNKS))
    _run_session(ws, claude)

    assert [c["model"] for c in claude.calls] == [SYNTHESIS_ANALYTICAL, REFINEMENT_MODEL]
    first, second = _draft_indexes(ws)
    assert _tokens_between(ws, first, second) == "".join(REFINED_CHUNKS)
    revised = ws.sent[second]
    assert revised["revision"] == 1
    assert revised["content"] == parse_closing_questions("".join(REFINED_CHUNKS))[0]
    assert revised["synthesis_model_used"] == REFINEMENT_MODEL
    assert "synthesis_final" in _types(ws)


def test_ac4_refinement_failure_mid_stream_resets_then_unavailable_draft():
    ws = DialogueSocket()
    claude = FakeClaude(FakeStream(DRAFT_CHUNKS), FakeStream(REFINED_CHUNKS, fail_after=1))
    _run_session(ws, claude)

    first, second = _draft_indexes(ws)
    between = _types(ws)[first:second]
    assert "synthesis_token" in between
    assert between.index("synthesis_reset") > between.index("synthesis_token")
    assert ws.sent[second]["content"].startswith("[Refinement unavailable")
    assert ws.sent[second]["revision"] == 1


# ── AC10 ──────────────────────────────────────────────────────────────────────

def test_ac10_client_gone_mid_stream_exits_without_fallback():
    ws = DialogueSocket(fail_on_type="synthesis_token")
    qwen = _run_session(ws, FakeClaude(FakeStream(DRAFT_CHUNKS)))

    qwen.assert_not_called()
    assert "synthesis_draft" not in _types(ws)
    assert ws.closed


# ── AC12 ──────────────────────────────────────────────────────────────────────

def test_ac12_first_token_timing_lines(capsys):
    ws = DialogueSocket()
    _run_session(ws, FakeClaude(FakeStream(DRAFT_CHUNKS), FakeStream(REFINED_CHUNKS)))

    out = capsys.readouterr().out
    for stage in ("synthesis.first_token", "refinement.1.first_token", "synthesis", "refinement.1"):
        assert re.search(rf"^\[TIMING\] {re.escape(stage)} \d+\.\ds$", out, re.M), stage
