"""
tests/test_synthesis_attribution.py

synthesis_model_used must name the model that wrote the current text:
the model that produced the first draft (here the Qwen fallback, after the
primary synthesis call fails), the refinement model for revisions, and
whichever wrote the last text on synthesis_final.
"""

from unittest.mock import AsyncMock, MagicMock, patch


def _run_session(refine: bool) -> list:
    from fastapi.testclient import TestClient
    from backend import main

    def r1(text):
        return AsyncMock(return_value=(text, "primary"))

    received = []
    with patch.object(main, "call_research_gemini_async", r1("g")), \
         patch.object(main, "call_research_gpt_async", r1("p")), \
         patch.object(main, "call_research_grok_async", r1("k")), \
         patch.object(main, "call_research_claude_async", r1("c")), \
         patch.object(main, "perplexity_research", MagicMock(return_value="pre")), \
         patch.object(main, "audit_with_fallback", MagicMock(return_value=("AUDIT", "primary", []))), \
         patch.object(main, "call_self_critique", AsyncMock(return_value="- critique")), \
         patch.object(main, "call_synthesis_async",
                      AsyncMock(side_effect=[RuntimeError("primary down"), "THE VERDICT\nbody"])), \
         patch.object(main, "call_synthesis_refinement",
                      AsyncMock(return_value={"content": "Revised", "closing_questions": []})):
        with TestClient(main.app).websocket_connect("/ws/session") as ws:
            ws.send_json({"prompt": "p", "session_config": {"tier": "smart"}, "history": []})

            def until(msg_type):
                while True:
                    received.append(ws.receive_json())
                    if received[-1]["type"] == msg_type:
                        return

            until("prompt_review")
            ws.send_json({"type": "prompt_confirmed"})
            until("synthesis_draft")
            if refine:
                ws.send_json({"type": "user_dialogue_response", "content": "push back"})
                until("synthesis_draft")
            ws.send_json({"type": "finalize_synthesis"})
            until("session_complete")
    return received


def _models(received, msg_type):
    return [m.get("synthesis_model_used") for m in received if m["type"] == msg_type]


def test_draft_and_final_report_the_model_that_wrote_the_draft():
    from backend.models.model_config import SYNTHESIS_FALLBACK

    received = _run_session(refine=False)
    assert _models(received, "synthesis_draft") == [SYNTHESIS_FALLBACK]
    assert _models(received, "synthesis_final") == [SYNTHESIS_FALLBACK]


def test_revision_reports_refinement_model_not_draft_model():
    from backend.models.model_config import SYNTHESIS_FALLBACK
    from backend.router import REFINEMENT_MODEL

    received = _run_session(refine=True)
    assert _models(received, "synthesis_draft") == [SYNTHESIS_FALLBACK, REFINEMENT_MODEL]
    assert _models(received, "synthesis_final") == [REFINEMENT_MODEL]
    assert REFINEMENT_MODEL.startswith("claude")
