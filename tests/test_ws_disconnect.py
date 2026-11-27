"""
tests/test_ws_disconnect.py

When the client disconnects while /ws/session is waiting for its next
message (prompt review gate, or the synthesis dialogue loop), the handler
must exit. A handler stuck on dialogue_queue.get() never finishes, which
blocks uvicorn's graceful shutdown/reload and leaks a task per abandoned
session.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.websockets import WebSocketDisconnect

DISCONNECT = object()


class FakeWebSocket:
    """Minimal stand-in for starlette's WebSocket, driven by an inbound queue."""

    def __init__(self, disconnect_after_type: str = None):
        self.inbound: asyncio.Queue = asyncio.Queue()
        self.sent: list = []
        self.closed = False
        self._disconnect_after_type = disconnect_after_type

    async def accept(self):
        pass

    async def receive_json(self):
        item = await self.inbound.get()
        if item is DISCONNECT:
            raise WebSocketDisconnect()
        return item

    async def send_json(self, data):
        if self.closed:
            raise RuntimeError("socket closed")
        self.sent.append(data)
        if data.get("type") == self._disconnect_after_type:
            self.inbound.put_nowait(DISCONNECT)

    async def close(self, code: int = 1000):
        self.closed = True


HANDSHAKE = {
    "prompt": "raw prompt",
    "session_config": {"tier": "smart", "optimized_prompt": "brief"},
    "history": [],
}


async def _run(ws: FakeWebSocket):
    from backend import main
    await asyncio.wait_for(main.session_websocket(ws), timeout=5)


def test_disconnect_at_prompt_review_ends_handler():
    async def scenario():
        ws = FakeWebSocket(disconnect_after_type="prompt_review")
        ws.inbound.put_nowait(HANDSHAKE)
        await _run(ws)
        types = [m["type"] for m in ws.sent]
        assert types == ["prompt_review"]
        assert ws.closed

    asyncio.run(scenario())


def test_disconnect_during_dialogue_ends_handler():
    from backend import main

    def r1(text):
        return AsyncMock(return_value=(text, "primary"))

    async def scenario():
        ws = FakeWebSocket(disconnect_after_type="synthesis_draft")
        ws.inbound.put_nowait(HANDSHAKE)
        ws.inbound.put_nowait({"type": "prompt_confirmed"})
        await _run(ws)
        types = [m["type"] for m in ws.sent]
        assert types[-1] == "synthesis_draft"
        assert "session_complete" not in types
        assert ws.closed

    with patch.object(main, "call_research_gemini_async", r1("g")), \
         patch.object(main, "call_research_gpt_async", r1("p")), \
         patch.object(main, "call_research_grok_async", r1("k")), \
         patch.object(main, "call_research_claude_async", r1("c")), \
         patch.object(main, "perplexity_research", MagicMock(return_value="pre")), \
         patch.object(main, "audit_with_fallback", MagicMock(return_value=("AUDIT", "primary", []))), \
         patch.object(main, "call_self_critique", AsyncMock(return_value="- critique")), \
         patch.object(main, "call_synthesis_async", AsyncMock(return_value="THE VERDICT\nbody")):
        asyncio.run(scenario())
