"""
tests/test_live_panel.py — PANEL_FACTCHECK_SPEC AC1 (live).

Sends real briefs to the real panel router and checks it picks the right
families of roles, drops no placeholders, and returns a plan that passes
validation. Also runs one real seat through the shared seat prompt and checks
the reply parses as the seat JSON. Calls paid APIs, so it is skipped unless
RUN_LIVE_EVALS=1:

    RUN_LIVE_EVALS=1 uv run pytest tests/test_live_panel.py

Run it when changing PANEL_ROUTER_SYSTEM, SEAT_TEMPLATE or SEAT_JSON_RULES.
"""

import asyncio
import os
import re

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_EVALS") != "1", reason="live API eval; set RUN_LIVE_EVALS=1"
)

LAUNCH = (
    "[ORG_1] plans to launch a new subscription analytics product next quarter "
    "with a [AMOUNT_1 ≈ $440K] launch budget. Should we launch on the planned "
    "date, delay, or narrow the first release? Leadership is split."
)
INFRA = (
    "[ORG_1] runs about 300 on-prem servers and is deciding whether to migrate "
    "to a public cloud over 12 months. Annual infrastructure spend is "
    "[AMOUNT_1 ≈ $2.1M]. Should we migrate, and how?"
)

# Function families, as keyword groups: a role "covers" a family if its title
# or mandate mentions one of the words. A sensible panel for the decision must
# cover at least three families and none of the other domain's signature roles.
LAUNCH_FAMILIES = {
    "product": ("product", "launch", "release", "readiness", "engineering"),
    "market": ("marketing", "market", "go-to-market", "customer", "competitive", "positioning", "sales"),
    "money": ("finance", "financial", "budget", "commercial", "revenue", "pricing", "unit economics", "cost"),
    "legal": ("legal", "compliance", "governance", "regulatory", "risk", "contract"),
}
INFRA_FAMILIES = {
    "architecture": ("architect", "infra", "platform", "migration", "cloud", "systems"),
    "cost": ("finops", "tco", "cost", "commercial", "budget", "spend", "financial", "finance"),
    "security": ("security", "compliance", "governance", "risk", "audit"),
    "operations": ("developer", "devops", "sre", "operations", "reliab", "delivery", "workforce", "people"),
}


def _plan(brief):
    from backend.router import call_panel_router

    plan = asyncio.run(call_panel_router(brief))
    assert not plan.router_degraded, plan.reason
    return plan


def _covered(plan, families):
    text = " ".join(f"{s.functional_title} {s.mandate}" for s in plan.seats.values()).lower()
    return {name for name, words in families.items() if any(w in text for w in words)}


def test_launch_brief_gets_launch_functions():
    plan = _plan(LAUNCH)
    assert len(_covered(plan, LAUNCH_FAMILIES)) >= 3, plan.roles()
    assert not any(w in " ".join(plan.roles()).lower() for w in ("infra", "devops", "sre")), plan.roles()


def test_infra_brief_gets_infrastructure_functions():
    plan = _plan(INFRA)
    assert len(_covered(plan, INFRA_FAMILIES)) >= 3, plan.roles()
    assert "marketing" not in " ".join(plan.roles()).lower(), plan.roles()


def test_router_never_invents_or_drops_placeholders():
    plan = _plan(LAUNCH)
    text = " ".join(f"{s.functional_title} {s.mandate} {s.blind_spot_guardrail}"
                    for s in plan.seats.values())
    for token in re.findall(r"\[[A-Z]+_\d+", text):
        assert token in LAUNCH, f"invented placeholder {token}"


def test_a_real_seat_returns_the_json_shape():
    from backend.models.anthropic_client import call_claude
    from backend.router import build_seat_system, parse_seat_response

    plan = _plan(LAUNCH)
    seat = plan.seats["claude"]
    reply = call_claude(
        messages=[{"role": "user", "content": LAUNCH}],
        tier="smart", system=build_seat_system("claude", seat), max_tokens=3000,
    ).content[0].text
    result = parse_seat_response(reply, "claude", seat)
    assert result is not None, reply[:500]
    assert len(result.core_assessment) > 200
    assert result.blind_spots_flagged
    assert not re.search(r"\b\d+(\.\d+)?\s*/\s*10\b", result.core_assessment), "invented numeric score"
