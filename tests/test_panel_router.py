"""
tests/test_panel_router.py — PANEL_FACTCHECK_SPEC AC1, AC5 (PR a).

Router plan parsing and fallback, the shared seat prompt, seat JSON parsing
and repair, and rendering. Model calls are mocked at call_claude, so these
tests prove the plumbing; whether the real router picks sensible roles is
checked live in tests/test_live_panel.py.

Run with:
    uv run pytest tests/test_panel_router.py -v
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.router import (
    PANEL_ROUTER_SYSTEM,
    TOKEN_PRESERVATION_RULE,
    PanelPlan,
    SeatResult,
    build_seat_system,
    call_panel_router,
    default_panel_plan,
    extract_json_object,
    get_round1_system_prompt,
    parse_panel_plan,
    parse_seat_response,
    render_seat,
    structure_seat,
)

LABS = ("gpt", "gemini", "grok", "claude")
ASSIGNED = {"gpt": "chatgpt", "gemini": "gemini", "grok": "grok", "claude": "claude_research"}

LAUNCH_BRIEF = "Decide on launching [ORG_1]'s new product at [AMOUNT_1 ≈ $440K] budget."
INFRA_BRIEF = "Migrate [ORG_1]'s workloads from on-prem to the cloud; budget [AMOUNT_1 ≈ $2.1M]."


def _seat(model, title, mandate="m", guard="g"):
    return {"assigned_model": model, "functional_title": title,
            "mandate": mandate, "blind_spot_guardrail": guard}


def _plan_json(titles, stakes="high", domain="product launch"):
    models = ["chatgpt", "gemini", "grok", "claude_research"]
    return json.dumps({
        "domain_detected": domain,
        "decision_stakes": stakes,
        "panel_seats": [_seat(m, t, f"mandate of {t}", f"guard of {t}")
                        for m, t in zip(models, titles)],
    })


LAUNCH_PLAN = _plan_json(
    ["VP of Product Development", "VP of Product Marketing", "VP of Finance", "Legal & Compliance Lead"]
)
INFRA_PLAN = _plan_json(
    ["Principal Infra Architect", "FinOps Lead", "Security & Compliance Officer", "Developer Experience Lead"],
    domain="cloud migration",
)


def _claude_reply(text):
    return SimpleNamespace(content=[SimpleNamespace(text=text)], stop_reason="end_turn")


def _seat_json(**over):
    data = {
        "model": "gpt", "functional_title": "VP of Finance",
        "core_assessment": "Launch only if [AMOUNT_1 ≈ $440K] covers two quarters.",
        "cross_functional_conflicts": ["Marketing wants a faster date than Finance can fund."],
        "blind_spots_flagged": ["The brief assumes one launch region."],
        "falsifiable_claims": ["CAC for B2B SaaS rose in 2025."],
    }
    data.update(over)
    return json.dumps(data)


# ── extract_json_object ──────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    'Here you go:\n{"a": 1}\nHope that helps.',
    '```\n{"a": 1}\n```',
])
def test_extract_json_object_finds_object(text):
    assert extract_json_object(text) == {"a": 1}


@pytest.mark.parametrize("text", ["", "no json here", "[1, 2]", '{"a": ', None])
def test_extract_json_object_rejects_junk(text):
    assert extract_json_object(text) is None


# ── parse_panel_plan (AC1) ───────────────────────────────────────────────────

def test_product_launch_plan_assigns_launch_functions():
    plan = parse_panel_plan(LAUNCH_PLAN)
    assert plan.domain_detected == "product launch"
    assert plan.decision_stakes == "high"
    titles = " | ".join(s.functional_title for s in plan.seats.values())
    for word in ("Product Development", "Product Marketing", "Finance", "Legal"):
        assert word in titles
    assert not plan.router_degraded and plan.defaulted == []


def test_cloud_plan_assigns_infra_functions():
    plan = parse_panel_plan(INFRA_PLAN)
    titles = " | ".join(s.functional_title for s in plan.seats.values())
    for word in ("Infra", "FinOps", "Security", "Developer Experience"):
        assert word in titles


def test_plan_maps_assigned_models_to_labs():
    plan = parse_panel_plan(LAUNCH_PLAN)
    assert set(plan.seats) == set(LABS)
    for lab, seat in plan.seats.items():
        assert seat.lab == lab and seat.assigned_model == ASSIGNED[lab]
        assert not seat.is_default


def test_three_seats_fill_the_fourth_with_a_default():
    raw = json.dumps({
        "domain_detected": "d", "decision_stakes": "low",
        "panel_seats": [_seat("chatgpt", "A"), _seat("gemini", "B"), _seat("claude_research", "C")],
    })
    plan = parse_panel_plan(raw)
    assert plan.defaulted == ["grok"]
    assert plan.seats["grok"].is_default and plan.seats["grok"].functional_title == "Challenger"
    assert plan.seats["gpt"].functional_title == "A"


@pytest.mark.parametrize("raw", [
    "not json",
    json.dumps({"domain_detected": "d", "decision_stakes": "low", "panel_seats": []}),
    json.dumps({"domain_detected": "d", "decision_stakes": "low",
                "panel_seats": [_seat("chatgpt", "A"), _seat("gemini", "B")]}),            # 2 seats
    json.dumps({"domain_detected": "d", "decision_stakes": "low",
                "panel_seats": [_seat("chatgpt", "A"), _seat("chatgpt", "B"), _seat("grok", "C")]}),  # duplicate
    json.dumps({"domain_detected": "d", "decision_stakes": "low",
                "panel_seats": [_seat("chatgpt", "A"), _seat("gemini", "B"), _seat("llama", "C")]}),  # unknown
    json.dumps({"domain_detected": "d", "decision_stakes": "extreme",
                "panel_seats": [_seat("chatgpt", "A"), _seat("gemini", "B"), _seat("grok", "C")]}),   # bad stakes
    json.dumps({"domain_detected": "d", "decision_stakes": "low",
                "panel_seats": [_seat("chatgpt", ""), _seat("gemini", "B"), _seat("grok", "C")]}),    # empty title
])
def test_invalid_plans_are_rejected(raw):
    with pytest.raises(ValueError):
        parse_panel_plan(raw)


def test_default_plan_keeps_the_four_cognitive_seats():
    plan = default_panel_plan("router timed out")
    assert plan.router_degraded and "timed out" in plan.reason
    assert {s.functional_title for s in plan.seats.values()} == {
        "Analyst", "Pragmatist", "Scout", "Challenger"}
    assert plan.seats["gpt"].functional_title == "Pragmatist"
    assert plan.seats["grok"].functional_title == "Challenger"
    assert all(s.is_default for s in plan.seats.values())
    assert sorted(plan.defaulted) == sorted(LABS)


# ── call_panel_router ────────────────────────────────────────────────────────

def _run_router(brief, reply=None, side_effect=None):
    with patch("backend.models.anthropic_client.call_claude",
               side_effect=side_effect, return_value=reply) as call:
        plan = asyncio.run(call_panel_router(brief))
    return plan, call


def test_router_returns_plan_and_sends_the_brief_unchanged():
    plan, call = _run_router(LAUNCH_BRIEF, _claude_reply(LAUNCH_PLAN))
    assert not plan.router_degraded
    kwargs = call.call_args.kwargs
    assert kwargs["messages"] == [{"role": "user", "content": LAUNCH_BRIEF}]
    assert kwargs["system"].startswith(PANEL_ROUTER_SYSTEM)
    assert kwargs["max_tokens"] <= 1500


def test_router_failure_falls_back_to_default_plan():
    plan, _ = _run_router(LAUNCH_BRIEF, side_effect=RuntimeError("boom"))
    assert plan.router_degraded and "boom" in plan.reason
    assert all(s.is_default for s in plan.seats.values())


def test_router_bad_json_falls_back_to_default_plan():
    plan, _ = _run_router(LAUNCH_BRIEF, _claude_reply("I think we should pick Finance."))
    assert plan.router_degraded


def test_router_timeout_falls_back_to_default_plan():
    async def run():
        async def never(*_a, **_k):
            await asyncio.sleep(10)
        with patch("backend.router._call_router_model", never):
            return await call_panel_router(LAUNCH_BRIEF, timeout=0.05)
    plan = asyncio.run(run())
    assert plan.router_degraded and "timed out" in plan.reason


def test_router_prompt_requirements():
    p = PANEL_ROUTER_SYSTEM
    assert "JSON" in p
    assert "[ORG_1]" in p or "placeholder" in p.lower()
    assert "verbatim" in p.lower()
    for word in ("Product", "Marketing", "Finance", "Legal", "FinOps", "Security"):
        assert word in p
    low = p.lower()
    assert "favour" in low or "favor" in low          # unanchored framing
    assert "demographic" in low and "coastal" in low  # proxy hygiene
    assert '"panel_seats"' in p and '"blind_spot_guardrail"' in p


# ── AC1 — placeholders survive into every seat prompt ───────────────────────

def test_placeholders_in_the_brief_survive_the_plan_into_seat_prompts():
    plan, call = _run_router(LAUNCH_BRIEF, _claude_reply(
        _plan_json(["VP of Product", "VP of Marketing", "VP of Finance [ORG_1] lead", "Legal"])))
    assert "[ORG_1]" in call.call_args.kwargs["messages"][0]["content"]
    assert "[ORG_1]" in plan.seats["grok"].functional_title
    for lab, seat in plan.seats.items():
        system = build_seat_system(lab, seat)
        assert TOKEN_PRESERVATION_RULE in system
    assert "[ORG_1]" in build_seat_system("grok", plan.seats["grok"])


# ── build_seat_system (Q1: layered on the cognitive stance) ─────────────────

@pytest.mark.parametrize("lab, stance", [
    ("claude", "ANALYST"), ("gpt", "PRAGMATIST"), ("gemini", "SCOUT"), ("grok", "CHALLENGER"),
])
def test_seat_system_layers_functional_role_on_the_stance(lab, stance):
    seat = parse_panel_plan(LAUNCH_PLAN).seats[lab]
    system = build_seat_system(lab, seat)
    assert f"<role>{seat.functional_title}</role>" in system
    assert f"<mandate>{seat.mandate}</mandate>" in system
    assert f"<blind_spot_check>{seat.blind_spot_guardrail}</blind_spot_check>" in system
    assert f"You are the {stance} in this roundtable." in system
    assert system.index("<role>") < system.index(stance)


def test_seat_system_has_json_rules_no_false_precision_and_token_rule():
    system = build_seat_system("gpt", parse_panel_plan(LAUNCH_PLAN).seats["gpt"])
    for key in ("core_assessment", "cross_functional_conflicts",
                "blind_spots_flagged", "falsifiable_claims"):
        assert key in system
    low = system.lower()
    assert "invent" in low and "statistic" in low
    assert "numerical score" in low or "numeric score" in low
    assert TOKEN_PRESERVATION_RULE in system
    # The JSON output rules come last so they win over "lead with your claim".
    assert system.rindex("core_assessment") > system.index("PRAGMATIST")


def test_default_seat_system_equals_stance_prompt_plus_json_rules():
    seat = default_panel_plan().seats["gemini"]
    system = build_seat_system("gemini", seat)
    assert get_round1_system_prompt("gemini") in system
    assert "<role>Scout</role>" in system


def test_get_round1_system_prompt_is_unchanged_for_existing_callers():
    assert "core_assessment" not in get_round1_system_prompt("gpt")


# ── parse_seat_response (AC5) ────────────────────────────────────────────────

def _seat_for(lab="gpt"):
    return parse_panel_plan(LAUNCH_PLAN).seats[lab]


def test_parse_valid_json():
    r = parse_seat_response(_seat_json(), "gpt", _seat_for("gpt"))
    assert isinstance(r, SeatResult) and not r.degraded
    assert r.model == "gpt" and r.functional_title == "VP of Product Development"
    assert r.core_assessment.startswith("Launch only if [AMOUNT_1")
    assert r.falsifiable_claims == ["CAC for B2B SaaS rose in 2025."]


def test_parse_fenced_json_with_chatter():
    r = parse_seat_response("Sure!\n```json\n" + _seat_json() + "\n```", "gpt", _seat_for())
    assert r is not None and not r.degraded


def test_parse_fills_missing_keys_and_coerces_lists():
    raw = json.dumps({"core_assessment": "Plain view.", "falsifiable_claims": "One claim only",
                      "blind_spots_flagged": None})
    r = parse_seat_response(raw, "gpt", _seat_for())
    assert not r.degraded
    assert r.falsifiable_claims == ["One claim only"]
    assert r.blind_spots_flagged == [] and r.cross_functional_conflicts == []


def test_parse_ignores_model_supplied_identity_and_uses_the_seat():
    r = parse_seat_response(_seat_json(model="grok", functional_title="Hacker"), "gpt", _seat_for("gpt"))
    assert r.model == "gpt" and r.functional_title == _seat_for("gpt").functional_title


def test_parse_caps_and_cleans_claims():
    claims = [f"claim {i}" for i in range(12)] + ["", "  ", 5]
    r = parse_seat_response(_seat_json(falsifiable_claims=claims), "gpt", _seat_for())
    assert r.falsifiable_claims == [f"claim {i}" for i in range(6)]


@pytest.mark.parametrize("text", ["Just prose, no JSON.", "", '{"foo": "bar"}',
                                  json.dumps({"core_assessment": ""})])
def test_parse_returns_none_when_unusable(text):
    assert parse_seat_response(text, "gpt", _seat_for()) is None


# ── structure_seat: parse → repair → degrade ─────────────────────────────────

def _structure(text, *, availability="primary", repair=None, repair_error=None):
    with patch("backend.models.anthropic_client.call_claude",
               return_value=repair, side_effect=repair_error) as call:
        result = asyncio.run(structure_seat(text, "gpt", _seat_for(), availability))
    return result, call


def test_structure_valid_json_makes_no_repair_call():
    result, call = _structure(_seat_json())
    assert not result.degraded and call.call_count == 0


def test_structure_repairs_prose_with_one_call():
    result, call = _structure("My view: launch.", repair=_claude_reply(_seat_json()))
    assert not result.degraded and call.call_count == 1
    assert "My view: launch." in call.call_args.kwargs["messages"][0]["content"]


def test_structure_degrades_when_repair_fails():
    result, call = _structure("My view: launch.", repair_error=RuntimeError("down"))
    assert result.degraded and result.core_assessment == "My view: launch."
    assert result.falsifiable_claims == [] and result.functional_title == _seat_for().functional_title


def test_structure_degrades_when_repair_returns_prose_too():
    result, _ = _structure("My view.", repair=_claude_reply("still prose"))
    assert result.degraded and result.core_assessment == "My view."


def test_structure_skips_repair_for_unavailable_seats():
    result, call = _structure("[Gemini unavailable this session]", availability="unavailable")
    assert result.degraded and call.call_count == 0
    assert result.core_assessment == "[Gemini unavailable this session]"


# ── render_seat ──────────────────────────────────────────────────────────────

def test_render_seat_shows_every_section():
    r = parse_seat_response(_seat_json(), "gpt", _seat_for())
    out = render_seat(r)
    assert out.startswith("**" + r.functional_title + "**")
    assert r.core_assessment in out
    assert "Marketing wants a faster date" in out
    assert "The brief assumes one launch region." in out
    assert "CAC for B2B SaaS rose in 2025." in out
    assert "{" not in out  # no raw JSON reaches the panel


def test_render_seat_omits_empty_sections():
    r = parse_seat_response(json.dumps({"core_assessment": "Only this."}), "gpt", _seat_for())
    assert render_seat(r) == "**" + r.functional_title + "**\n\nOnly this."


def test_render_degraded_seat_is_the_plain_text():
    result, _ = _structure("Plain prose answer.", repair_error=RuntimeError("x"))
    assert render_seat(result) == "Plain prose answer."


def test_render_keeps_placeholders():
    r = parse_seat_response(_seat_json(), "gpt", _seat_for())
    assert "[AMOUNT_1 ≈ $440K]" in render_seat(r)
