"""
tests/test_panel_pipeline.py — PANEL_FACTCHECK_SPEC AC1 (end to end) and AC4 (PR a).

The full mocked session from test_privacy_pipeline, but the fake models now
speak the Phase 2 protocol: the router returns a panel plan and every seat
returns JSON. Checks that:
  - each seat's system prompt carries its router-assigned role,
  - the panels the user sees are the readable rendering (title + analysis),
    never raw JSON, with the original names restored,
  - Phase 1 still holds: no sensitive value reaches any provider,
  - bad router / bad seat output degrades without breaking the session.

Run with:
    uv run pytest tests/test_panel_pipeline.py -v
"""

import json
import re

import pytest

from tests.test_privacy_pipeline import (
    ACCEPTANCE_PROMPT, SENSITIVE, _content, _echo, _run_session,
)

TITLES = {
    "chatgpt": "VP of Product Development",
    "gemini": "VP of Product Marketing",
    "grok": "VP of Finance",
    "claude_research": "Legal & Compliance Lead",
}
LAB_OF = {"chatgpt": "openai", "gemini": "gemini", "grok": "xai", "claude_research": "anthropic"}
SENDER_OF = {"chatgpt": "GPT", "gemini": "Gemini", "grok": "Grok", "claude_research": "Claude"}


def _system_of(kw) -> str:
    """The system prompt wherever the provider SDK puts it."""
    if isinstance(kw.get("system"), str):
        return kw["system"]
    for m in kw.get("messages") or []:
        if isinstance(m, dict) and m.get("role") == "system":
            return str(m.get("content"))
    return str(kw.get("config") or "")  # google-genai


def _plan() -> str:
    return json.dumps({
        "domain_detected": "contract renewal",
        "decision_stakes": "high",
        "panel_seats": [
            {"assigned_model": m, "functional_title": t,
             "mandate": f"mandate of {t}", "blind_spot_guardrail": f"guard of {t}"}
            for m, t in TITLES.items()
        ],
    })


def _seat_reply(kw) -> str:
    system = _system_of(kw)
    title = re.search(r"<role>(.*?)</role>", system)
    role = title.group(1) if title else "unknown"
    seen = " ".join(dict.fromkeys(re.findall(r"\[[A-Z]+_\d+(?: ≈ [^\]]+)?\]", _content(kw))))
    return json.dumps({
        "model": "m", "functional_title": role,
        "core_assessment": f"{role} view on {seen}",
        "cross_functional_conflicts": [f"{role} vs Finance"],
        "blind_spots_flagged": ["Assumes a single region."],
        "falsifiable_claims": [f"{role}: notice periods are 30 days."],
    }, ensure_ascii=False)


def _good_responder(provider, kw):
    system = _system_of(kw)
    if system.startswith("You assemble the expert panel"):
        return _plan()
    if "<panel_seat" in system:
        return _seat_reply(kw)
    return None  # everything else (intake, fact-check, synthesis…) echoes as before


def _panel_text(frames, sender):
    return "".join(f["token"] for f in frames
                   if f["type"] == "token" and f.get("sender") == sender)


@pytest.fixture(scope="module")
def run():
    return _run_session(ACCEPTANCE_PROMPT, responder=_good_responder)


# ── AC1 — routed seats reach the models ──────────────────────────────────────

def test_router_saw_the_tokenized_brief(run):
    router_calls = [t for p, t in run.rec.payloads
                    if p == "anthropic" and "You assemble the expert panel" in t]
    assert len(router_calls) == 1
    assert "[PERSON_1]" in router_calls[0] or "[ORG_1]" in router_calls[0]


@pytest.mark.parametrize("assigned, title", list(TITLES.items()))
def test_each_seat_prompt_carries_its_assigned_role(run, assigned, title):
    provider = LAB_OF[assigned]
    seat_payloads = [t for p, t in run.rec.payloads if p == provider and "<panel_seat" in t]
    assert seat_payloads, provider
    assert any(f"<role>{title}</role>" in t for t in seat_payloads)


def test_cognitive_stances_still_layered_under_the_roles(run):
    payloads = " ".join(t for p, t in run.rec.payloads if "<panel_seat" in t)
    for stance in ("ANALYST", "PRAGMATIST", "SCOUT", "CHALLENGER"):
        assert stance in payloads


# ── What the user sees ───────────────────────────────────────────────────────

@pytest.mark.parametrize("assigned, title", list(TITLES.items()))
def test_panel_shows_rendered_seat_not_json(run, assigned, title):
    text = _panel_text(run.frames, SENDER_OF[assigned])
    assert text.startswith(f"**{title}**")
    assert "Blind spots flagged" in text and "Claims that can be fact-checked" in text
    assert "{" not in text and '"core_assessment"' not in text


def test_panel_text_has_original_values_not_placeholders(run):
    text = " ".join(_panel_text(run.frames, s) for s in SENDER_OF.values())
    assert "Sarah Jenkins" in text
    assert not re.search(r"\[(?:PERSON|ORG|AMOUNT|ID)_\d+", text)


# ── AC4 — Phase 1 compatibility ──────────────────────────────────────────────

@pytest.mark.parametrize("value", SENSITIVE)
def test_no_sensitive_value_reaches_any_provider(run, value):
    assert not [p for p, t in run.rec.payloads if value in t]


def test_final_answer_still_rehydrated(run):
    final = next(f for f in run.frames if f["type"] == "synthesis_final")
    for value in SENSITIVE:
        assert value in final["content"]


def test_synthesis_received_rendered_seats_wrapped_as_data(run):
    synth = [t for p, t in run.rec.payloads
             if p == "anthropic" and "research_response" in t and "untrusted_search_evidence" in t]
    assert synth
    assert 'source=\\"Gpt\\"' in synth[0]   # json-escaped <research_response source="Gpt">
    assert "VP of Product Development" in synth[0]


# ── Degradation ──────────────────────────────────────────────────────────────

def test_bad_router_falls_back_to_default_seats_and_session_completes():
    def responder(provider, kw):
        if _system_of(kw).startswith("You assemble the expert panel"):
            return "I would pick finance."
        return _good_responder(provider, kw)

    run = _run_session(ACCEPTANCE_PROMPT, responder=responder)
    assert any(f["type"] == "session_complete" for f in run.frames)
    seat_payloads = " ".join(t for p, t in run.rec.payloads if "<panel_seat" in t)
    for title in ("Analyst", "Pragmatist", "Scout", "Challenger"):
        assert f"<role>{title}</role>" in seat_payloads
    ann = next(f for f in run.frames if f["type"] == "synthesis_annotations")
    assert any("Panel router unavailable" in line for line in ann["annotations"])


def test_seats_answering_in_prose_still_complete_and_are_flagged():
    def responder(provider, kw):
        if _system_of(kw).startswith("You assemble the expert panel"):
            return _plan()
        return None  # seats echo prose, not JSON

    run = _run_session(ACCEPTANCE_PROMPT, responder=responder)
    assert any(f["type"] == "session_complete" for f in run.frames)
    text = _panel_text(run.frames, "GPT")
    assert text and "Sarah Jenkins" in text and not text.startswith("**")
    ann = next(f for f in run.frames if f["type"] == "synthesis_annotations")
    assert any("did not return structured output" in line for line in ann["annotations"])
