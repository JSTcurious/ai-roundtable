"""
tests/test_stage_timing.py

/ws/session prints a [TIMING] line per pipeline stage and per research model,
then a first_draft summary once the synthesis draft is sent. The timer starts
after the prompt-review gate, so time the user spends reviewing is not counted.
"""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.stage_timing import StageTimer
from tests.test_ws_disconnect import HANDSHAKE, FakeWebSocket, _run

STAGES = [
    "research.gemini", "research.gpt", "research.grok", "research.claude",
    "research.perplexity_pre", "research", "research.emit",
    "factcheck", "self_critique", "synthesis",
]


def test_stage_records_time_and_marks_failure(capsys):
    timer = StageTimer()

    async def scenario():
        async with timer.stage("ok"):
            await asyncio.sleep(0.01)
        with pytest.raises(ValueError):
            async with timer.stage("boom"):
                raise ValueError("x")
        assert await timer.timed("wrapped", asyncio.sleep(0, result=7)) == 7

    asyncio.run(scenario())
    out = capsys.readouterr().out
    assert re.search(r"\[TIMING\] ok \d+\.\ds$", out, re.M)
    assert "[TIMING] boom 0.0s (failed)" in out
    assert [name for name, _ in timer.stages] == ["ok", "boom", "wrapped"]
    assert timer.summary().startswith("[TIMING] first_draft total=")


def test_session_logs_every_stage_and_first_draft_summary(capsys):
    from backend import main

    def r1(text):
        return AsyncMock(return_value=(text, "primary"))

    async def scenario():
        ws = FakeWebSocket(disconnect_after_type="synthesis_draft")
        ws.inbound.put_nowait(HANDSHAKE)
        ws.inbound.put_nowait({"type": "prompt_confirmed"})
        await _run(ws)

    with patch.object(main, "call_research_gemini_async", r1("g")), \
         patch.object(main, "call_research_gpt_async", r1("p")), \
         patch.object(main, "call_research_grok_async", r1("k")), \
         patch.object(main, "call_research_claude_async", r1("c")), \
         patch.object(main, "perplexity_research", MagicMock(return_value="pre")), \
         patch.object(main, "audit_with_fallback", MagicMock(return_value=("AUDIT", "primary", []))), \
         patch.object(main, "call_self_critique", AsyncMock(return_value="- critique")), \
         patch.object(main, "call_synthesis_async", AsyncMock(return_value="THE VERDICT\nbody")):
        asyncio.run(scenario())

    out = capsys.readouterr().out
    for stage in STAGES:
        assert re.search(rf"^\[TIMING\] {re.escape(stage)} \d+\.\ds$", out, re.M), stage
    summary = [l for l in out.splitlines() if l.startswith("[TIMING] first_draft")]
    assert len(summary) == 1
    for stage in STAGES:
        assert f"{stage}=" in summary[0]
