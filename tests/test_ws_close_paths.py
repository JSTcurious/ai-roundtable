"""
tests/test_ws_close_paths.py — DEPENDENCY_PINNING_SPEC AC3.

Runs the real app on a real uvicorn server (in this process, background
thread, free port) and drives /ws/session through the six ways a session
ends. Any server-side traceback or ERROR log fails the test.

Why a real server: starlette's TestClient never exercises uvicorn's WebSocket
protocol implementation, which is where close/disconnect semantics changed
between uvicorn 0.32 (legacy websockets protocol, the April
``transfer_data_task`` crash) and 0.54 (sans-I/O, reports a gone client as
``WebSocketDisconnect``). Those changes only show up here.

Model calls are patched on backend.main exactly like the
TestSessionSynthesisWiring harness, so no provider is called even though
backend/.env loads real keys.
"""

import asyncio
import contextlib
import json
import logging
import socket
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import uvicorn
from websockets.asyncio.client import connect

HANDSHAKE = {
    "prompt": "raw user prompt",
    "session_config": {"tier": "smart", "optimized_prompt": "brief"},
    "history": [],
}
TIMEOUT = 10


class _ErrorCollector(logging.Handler):
    """Collects every ERROR record, or any record carrying a traceback."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: dict[int, logging.LogRecord] = {}

    def emit(self, record):
        if record.levelno >= logging.ERROR or record.exc_info:
            self.records[id(record)] = record

    def report(self) -> list[str]:
        return [
            f"{r.name}: {r.getMessage()}\n{self.format(r) if r.exc_info else ''}"
            for r in self.records.values()
        ]


# uvicorn's loggers may have propagate=False if something configured them, so
# attach to each one directly as well as to the root logger.
_WATCHED_LOGGERS = ("", "uvicorn", "uvicorn.error", "uvicorn.asgi", "asyncio")


@contextlib.contextmanager
def _patched_models():
    from backend import main

    def r1(text):
        return AsyncMock(return_value=(text, "primary"))

    with patch.object(main, "call_research_gemini_async", r1("GEMINI_R1")), \
         patch.object(main, "call_research_gpt_async", r1("GPT_R1")), \
         patch.object(main, "call_research_grok_async", r1("GROK_R1")), \
         patch.object(main, "call_research_claude_async", r1("CLAUDE_R1")), \
         patch.object(main, "perplexity_research", MagicMock(return_value="pre")), \
         patch.object(main, "audit_with_fallback", MagicMock(return_value=("AUDIT", "primary", []))), \
         patch.object(main, "call_self_critique", AsyncMock(return_value="- critique")), \
         patch.object(main, "call_synthesis_async",
                      AsyncMock(return_value="THE VERDICT\nbody\n\n? Does this fit?")), \
         patch.object(main, "call_synthesis_refinement",
                      AsyncMock(return_value={"content": "Revised", "closing_questions": []})):
        yield


class LiveServer:
    """The app on a real uvicorn server, run like production (default ws impl)."""

    def __init__(self):
        from backend import main

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.url = f"ws://127.0.0.1:{self.port}/ws/session"
        config = uvicorn.Config(main.app, log_config=None, lifespan="on",
                                timeout_graceful_shutdown=TIMEOUT)
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [self.sock]}, daemon=True
        )

    def start(self):
        self.thread.start()
        deadline = time.monotonic() + TIMEOUT
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("uvicorn did not start")
            time.sleep(0.02)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(TIMEOUT)
        assert not self.thread.is_alive(), "uvicorn did not shut down"


@pytest.fixture
def live_server():
    """Yields a started server; the test stops it before asserting on errors."""
    collector = _ErrorCollector()
    loggers = [logging.getLogger(name) for name in _WATCHED_LOGGERS]
    for lg in loggers:
        lg.addHandler(collector)
    server = LiveServer()
    try:
        with _patched_models():
            server.start()
            server.errors = collector
            yield server
            if server.thread.is_alive():
                server.stop()
    finally:
        for lg in loggers:
            lg.removeHandler(collector)
        server.sock.close()


async def _recv_until(ws, msg_type):
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), TIMEOUT))
        if msg["type"] == msg_type:
            return msg


def _run(coro):
    asyncio.run(asyncio.wait_for(coro, TIMEOUT * 2))


def _assert_no_server_errors(server):
    server.stop()  # graceful shutdown waits for every handler to finish
    assert server.errors.report() == []


def test_close_path_1_client_leaves_at_prompt_review(live_server):
    async def scenario():
        async with connect(live_server.url) as ws:
            await ws.send(json.dumps(HANDSHAKE))
            await _recv_until(ws, "prompt_review")
    _run(scenario())
    _assert_no_server_errors(live_server)


def test_close_path_2_server_closes_after_non_json_handshake(live_server):
    async def scenario():
        async with connect(live_server.url) as ws:
            await ws.send("this is not json")
            msg = json.loads(await asyncio.wait_for(ws.recv(), TIMEOUT))
            assert msg["type"] == "error"
            await asyncio.wait_for(ws.wait_closed(), TIMEOUT)
    _run(scenario())
    _assert_no_server_errors(live_server)


def test_close_path_3_server_closes_after_completed_session(live_server):
    async def scenario():
        async with connect(live_server.url) as ws:
            await ws.send(json.dumps(HANDSHAKE))
            await _recv_until(ws, "prompt_review")
            await ws.send(json.dumps({"type": "prompt_confirmed"}))
            await _recv_until(ws, "synthesis_draft")
            await ws.send(json.dumps({"type": "finalize_synthesis"}))
            await _recv_until(ws, "session_complete")
            await asyncio.wait_for(ws.wait_closed(), TIMEOUT)
    _run(scenario())
    _assert_no_server_errors(live_server)


def test_close_path_4_client_closes_before_handshake(live_server):
    async def scenario():
        async with connect(live_server.url):
            pass
    _run(scenario())
    _assert_no_server_errors(live_server)


def test_close_path_5_client_aborts_tcp_transport(live_server):
    async def scenario():
        ws = await connect(live_server.url)
        await ws.send(json.dumps(HANDSHAKE))
        await _recv_until(ws, "prompt_review")
        ws.transport.abort()  # no close frame: the TCP connection just drops
        await asyncio.sleep(0.2)
    _run(scenario())
    _assert_no_server_errors(live_server)


def test_close_path_6_server_shuts_down_with_session_open(live_server):
    # What a Railway redeploy does to a user sitting at prompt review.
    async def scenario():
        async with connect(live_server.url) as ws:
            await ws.send(json.dumps(HANDSHAKE))
            await _recv_until(ws, "prompt_review")
            live_server.server.should_exit = True
            await asyncio.wait_for(ws.wait_closed(), TIMEOUT)
    _run(scenario())
    _assert_no_server_errors(live_server)
