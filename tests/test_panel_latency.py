"""
tests/test_panel_latency.py — PANEL_LATENCY_SPEC AC1–AC4.

The router and the seats are told to write less (output tokens are what the
time is made of), and each session now logs how every seat answered:

  AC1  router prompt states the four length limits; max_tokens <= 700
  AC2  seat output rules state the caps (350 words, 4 one-sentence items)
  AC3  SeatResult.repaired is set only when the repair call produced the result
  AC4  one [SEATS] line per session (status + reply length, no content) and the
       [SESSION] summary names repaired / degraded seats

Whether the shorter prompts really give the target times is measured live
(see the spec's Implementation Notes); these tests pin the prompt text and the
bookkeeping.

Run with:
    uv run pytest tests/test_panel_latency.py -v
"""

import asyncio
import json
import re
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.models.pipeline_health import PipelineHealth
from backend.router import (
    PANEL_ROUTER_MAX_TOKENS,
    PANEL_ROUTER_SYSTEM,
    SEAT_JSON_RULES,
    SeatResult,
    format_seats_line,
    parse_panel_plan,
    parse_seat_response,
    seat_status,
    structure_seat,
)

SEAT = parse_panel_plan(json.dumps({
    "domain_detected": "d", "decision_stakes": "low",
    "panel_seats": [
        {"assigned_model": m, "functional_title": "T", "mandate": "m", "blind_spot_guardrail": "g"}
        for m in ("chatgpt", "gemini", "grok")
    ],
})).seats["gpt"]


def _seat_json():
    return json.dumps({
        "core_assessment": "Assessment.",
        "falsifiable_claims": ["A claim."],
    })


def _reply(text):
    return SimpleNamespace(content=[SimpleNamespace(text=text)], stop_reason="end_turn")


# ── AC1 — router limits ──────────────────────────────────────────────────────

def test_router_prompt_states_each_length_limit():
    flat = " ".join(PANEL_ROUTER_SYSTEM.split())
    assert re.search(r"functional_title[^.]*at most 5 words", flat)
    assert re.search(r"mandate[^.]*at most 20 words", flat)
    assert re.search(r"blind_spot_guardrail[^.]*at most 15 words", flat)
    assert re.search(r"domain_detected[^.]*at most 5 words", flat)


def test_router_max_tokens_is_capped():
    assert PANEL_ROUTER_MAX_TOKENS <= 700
    assert PANEL_ROUTER_MAX_TOKENS >= 500  # a full four-seat plan is ~450 tokens


def test_router_still_returns_what_it_returned_before():
    # The limits are additive: the plan shape and the earlier rules stay.
    for fragment in ('"panel_seats"', '"blind_spot_guardrail"', "verbatim", "Proxy hygiene"):
        assert fragment in PANEL_ROUTER_SYSTEM


# ── AC2 — seat caps ──────────────────────────────────────────────────────────

def test_seat_rules_state_the_caps():
    flat = " ".join(SEAT_JSON_RULES.split())
    assert "at most 350 words" in flat
    assert "one sentence" in flat
    assert re.search(r"at most 4 items", flat)
    assert "at most 6 claims" in flat or "at most 6" in flat  # claims keep their cap of 6


def test_seat_rules_keep_the_json_shape():
    for key in ("core_assessment", "cross_functional_conflicts",
                "blind_spots_flagged", "falsifiable_claims"):
        assert key in SEAT_JSON_RULES


# ── AC3 — repaired flag ──────────────────────────────────────────────────────

def _structure(text, availability="primary", repair=None, error=None):
    with patch("backend.models.anthropic_client.call_claude",
               return_value=repair, side_effect=error):
        return asyncio.run(structure_seat(text, "gpt", SEAT, availability))


def test_valid_first_reply_is_not_repaired():
    r = _structure(_seat_json())
    assert not r.repaired and not r.degraded


def test_repair_that_works_is_marked_repaired():
    r = _structure("Prose answer.", repair=_reply(_seat_json()))
    assert r.repaired and not r.degraded


def test_failed_repair_is_degraded_not_repaired():
    r = _structure("Prose answer.", error=RuntimeError("down"))
    assert r.degraded and not r.repaired


def test_unavailable_seat_is_degraded_not_repaired():
    r = _structure("[Grok unavailable this session]", availability="unavailable")
    assert r.degraded and not r.repaired


def test_raw_reply_length_is_recorded():
    assert _structure(_seat_json()).raw_chars == len(_seat_json())
    assert _structure("Prose answer.", error=RuntimeError("x")).raw_chars == len("Prose answer.")
    r = _structure("Prose answer.", repair=_reply(_seat_json()))
    assert r.raw_chars == len("Prose answer.")  # the model's reply, not the repair's


# ── AC4 — [SEATS] line and health summary ────────────────────────────────────

def _results(**status):
    out = {}
    for lab, st in status.items():
        out[lab] = SeatResult(lab, "T", "text", degraded=(st == "degraded"),
                              repaired=(st == "repaired"), raw_chars=1820)
    return out


def test_seat_status_names():
    assert seat_status(SeatResult("gpt", "T", "x")) == "json"
    assert seat_status(SeatResult("gpt", "T", "x", repaired=True)) == "repaired"
    assert seat_status(SeatResult("gpt", "T", "x", degraded=True)) == "degraded"


def test_seats_line_has_all_four_labs_in_order_and_no_content():
    seats = _results(gpt="json", gemini="repaired", grok="json", claude="degraded")
    seats["gpt"].core_assessment = "SECRET ASSESSMENT TEXT"
    line = format_seats_line(seats)
    assert line.startswith("[SEATS] ")
    assert re.findall(r"(\w+)=(\w+):(\d+)ch", line) == [
        ("gpt", "json", "1820"), ("gemini", "repaired", "1820"),
        ("grok", "json", "1820"), ("claude", "degraded", "1820"),
    ]
    assert "SECRET" not in line


def test_summary_names_repaired_and_degraded_seats():
    health = PipelineHealth(panel_repaired_seats=["gemini"], panel_degraded_seats=["claude"])
    summary = health.summary()
    assert summary.startswith("Pipeline ")
    assert "repaired=gemini" in summary and "degraded=claude" in summary


def test_summary_is_unchanged_when_nothing_was_repaired():
    assert PipelineHealth().summary() == "Pipeline healthy: synthesis=primary"


def test_repaired_seats_get_an_annotation():
    lines = PipelineHealth(panel_repaired_seats=["gemini"]).to_annotation()
    assert any("Gemini" in line and "repair" in line.lower() for line in lines)


# ── AC4 end to end: one [SEATS] line per session ─────────────────────────────

def test_session_logs_one_seats_line(capsys):
    from tests.test_panel_pipeline import _good_responder
    from tests.test_privacy_pipeline import ACCEPTANCE_PROMPT, SENSITIVE, _run_session

    run = _run_session(ACCEPTANCE_PROMPT, responder=_good_responder)
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.startswith("[SEATS]")]
    assert len(lines) == 1, out
    assert all(f"{lab}=json:" in lines[0] for lab in ("gpt", "gemini", "grok", "claude"))
    for value in SENSITIVE:
        assert value not in lines[0]
    assert any(f["type"] == "session_complete" for f in run.frames)
