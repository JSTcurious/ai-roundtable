"""
tests/test_model_registry.py

Acceptance criteria from docs/MODEL_REGISTRY_SPEC.md. Each test names the
criterion it covers.
"""

import copy
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.models.registry import (
    RegistryError,
    load_registry,
    resolve,
    validate_registry,
)

TODAY = date(2026, 11, 27)

# Today's model_config.py defaults (AC10), except intake.fallback1 (Decision 2).
EXPECTED_PARITY = {
    "research.claude.executor": "claude-sonnet-4-6",
    "research.claude.advisor": "claude-opus-4-6",
    "research.claude.deep": "claude-opus-4-6",
    "research.claude.fallback": "claude-haiku-4-5-20251001",
    "research.gpt.executor": "gpt-5.4-mini",
    "research.gpt.advisor": "gpt-5.4",
    "research.gpt.deep": "gpt-5.4",
    "research.gpt.fallback": "gpt-5.4-mini",
    "research.gemini.executor": "gemini-3-flash-preview",
    "research.gemini.advisor": "gemini-3.1-pro-preview",
    "research.gemini.deep": "gemini-3.1-pro-preview",
    "research.gemini.fallback": "gemini-2.5-flash",
    "research.grok.executor": "grok-4.20-0309-non-reasoning",
    "research.grok.advisor": "grok-4.20-0309-reasoning",
    "research.grok.deep": "grok-4.20-0309-reasoning",
    "research.grok.fallback": "grok-4.3",
    "factcheck.primary": "sonar-pro",
    "factcheck.fallback1": "sonar",
    "factcheck.fallback2": "gpt-5.4",
    "synthesis.primary": "claude-opus-4-6",
    "synthesis.fallback": "qwen/qwen-2.5-72b-instruct",
    "intake.primary": "claude-sonnet-4-6",
    "intake.fallback1": "gpt-5.4-mini",
    "intake.fallback2": "qwen/qwen-2.5-72b-instruct",
}


def _model(mid, vendor="openai", tier="balanced", rank=10, status="approved", caps=(), retires=None):
    return {"id": mid, "vendor": vendor, "tier": tier, "rank": rank, "status": status,
            "capabilities": list(caps), "retires_at": retires, "notes": ""}


def _registry(models, roles, buffer=30, warning=90):
    return {"retirement_buffer_days": buffer, "warning_window_days": warning,
            "models": models, "roles": roles, "discovery": {}}


def _role(vendor="openai", tiers=("balanced",), env="X_ENV", **extra):
    return {"env": env, "vendor": vendor, "tiers": list(tiers), **extra}


@pytest.fixture
def seed():
    return load_registry()


# ── AC1 ───────────────────────────────────────────────────────────────────────

MODEL_ID_LITERAL = re.compile(
    r"[\"'](?:claude-|gpt-|gemini-|grok-|sonar|qwen/|o[134]-|chatgpt)[A-Za-z0-9._/-]*[\"']"
)


def test_ac1_no_hardcoded_model_ids_in_backend_code():
    backend = Path(__file__).resolve().parent.parent / "backend"
    offenders = []
    for path in backend.rglob("*.py"):
        if path.name.startswith("test_"):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if MODEL_ID_LITERAL.search(line):
                offenders.append(f"{path.relative_to(backend)}:{lineno}: {line.strip()}")
    assert offenders == [], "model IDs belong in model_registry.json:\n" + "\n".join(offenders)


# ── Registry validation (task 1) ──────────────────────────────────────────────

def test_seed_registry_is_valid(seed):
    validate_registry(seed)


@pytest.mark.parametrize("mutate,needle", [
    (lambda r: r["models"].append(copy.deepcopy(r["models"][0])), "duplicate"),
    (lambda r: r["models"][0].update(vendor="acme"), "vendor"),
    (lambda r: r["models"][0].update(tier="huge"), "tier"),
    (lambda r: r["models"][0].update(status="maybe"), "status"),
    (lambda r: r["models"][0].update(rank=None), "rank"),
    (lambda r: r["models"][0].update(retires_at="soon"), "retires_at"),
    (lambda r: r["roles"]["research.claude.fallback"].update(distinct_from=["nope"]), "distinct_from"),
    (lambda r: r["roles"]["intake.primary"].update(tiers=[]), "tiers"),
])
def test_invalid_registry_is_rejected(seed, mutate, needle):
    bad = copy.deepcopy(seed)
    mutate(bad)
    with pytest.raises(RegistryError, match=needle):
        validate_registry(bad)


def test_candidate_may_omit_tier_and_rank(seed):
    reg = copy.deepcopy(seed)
    reg["models"].append(_model("gpt-9", tier=None, rank=None, status="candidate"))
    validate_registry(reg)


# ── AC2 / AC10 ────────────────────────────────────────────────────────────────

def test_ac10_seed_reproduces_current_defaults(seed):
    result = resolve(seed, today=TODAY)
    assert result.models == EXPECTED_PARITY
    assert result.errors == []


def test_ac2_every_role_resolves_to_a_matching_approved_model(seed):
    result = resolve(seed, today=TODAY)
    by_id = {m["id"]: m for m in seed["models"]}
    assert set(result.models) == set(seed["roles"])
    for role, model_id in result.models.items():
        spec, model = seed["roles"][role], by_id[model_id]
        assert model["status"] == "approved", role
        assert model["vendor"] == spec["vendor"], role
        assert model["tier"] in spec["tiers"], role
        assert set(spec.get("capabilities", [])) <= set(model["capabilities"]), role
        assert result.sources[role] == "registry"


def test_ac2_required_capabilities_are_enforced():
    reg = _registry(
        [_model("a", rank=50), _model("b", rank=10, caps=["tools"])],
        {"r": _role(capabilities=["tools"])},
    )
    assert resolve(reg, today=TODAY).models["r"] == "b"


# ── AC3 ───────────────────────────────────────────────────────────────────────

def test_ac3_override_wins_over_registry(seed):
    result = resolve(seed, overrides={"research.gpt.deep": "test-model-x"}, today=TODAY)
    assert result.models["research.gpt.deep"] == "test-model-x"
    assert result.sources["research.gpt.deep"] == "override"


def test_ac3_override_unavailable_or_retiring_warns_but_is_used():
    reg = _registry([_model("a")], {"r": _role(env="R")})
    availability = {"openai": {"available": {"a"}, "retires": {"old": TODAY + timedelta(days=5)}}}
    result = resolve(reg, availability=availability, overrides={"r": "ghost"}, today=TODAY)
    assert result.models["r"] == "ghost"
    assert any("ghost" in w and "not listed" in w for w in result.warnings)

    result = resolve(reg, availability=availability, overrides={"r": "old"}, today=TODAY)
    assert result.models["r"] == "old"
    assert any("old" in w and "retires" in w for w in result.warnings)


# ── AC4 / AC11 ────────────────────────────────────────────────────────────────

def test_ac4_model_inside_retirement_buffer_is_skipped():
    reg = _registry(
        [_model("new", rank=50, retires=(TODAY + timedelta(days=10)).isoformat()), _model("old", rank=10)],
        {"r": _role()},
    )
    result = resolve(reg, today=TODAY)
    assert result.models["r"] == "old"


def test_ac4_model_inside_warning_window_is_used_with_warning():
    reg = _registry([_model("a", retires=(TODAY + timedelta(days=60)).isoformat())], {"r": _role()})
    result = resolve(reg, today=TODAY)
    assert result.models["r"] == "a"
    assert any("a" in w and "retires" in w for w in result.warnings)


def test_ac4_only_retiring_models_left_uses_them_and_logs_error():
    reg = _registry([_model("a", retires=(TODAY + timedelta(days=3)).isoformat())], {"r": _role()})
    result = resolve(reg, today=TODAY)
    assert result.models["r"] == "a"
    assert result.errors


def test_ac11_discovered_retirement_moves_role_to_next_approved(seed):
    reg = copy.deepcopy(seed)
    reg["models"].append(_model("claude-opus-next", vendor="anthropic", tier="frontier", rank=20))
    availability = {"anthropic": {
        "available": {m["id"] for m in reg["models"] if m["vendor"] == "anthropic"},
        "retires": {"claude-opus-4-6": TODAY + timedelta(days=12)},
    }}
    result = resolve(reg, availability=availability, today=TODAY)
    assert result.models["synthesis.primary"] == "claude-opus-next"
    assert result.models["research.claude.advisor"] == "claude-opus-next"


def test_ac11_vendor_not_listing_a_model_skips_it():
    reg = _registry([_model("a", rank=50), _model("b", rank=10)], {"r": _role()})
    availability = {"openai": {"available": {"b"}, "retires": {}}}
    result = resolve(reg, availability=availability, today=TODAY)
    assert result.models["r"] == "b"
    assert any("'a'" in w for w in result.warnings)


# ── AC5 / AC6 ─────────────────────────────────────────────────────────────────

def test_ac5_distinct_from_is_respected():
    reg = _registry(
        [_model("best", rank=50), _model("second", rank=10)],
        {"primary": _role(), "fallback": _role(distinct_from=["primary"])},
    )
    result = resolve(reg, today=TODAY)
    assert result.models == {"primary": "best", "fallback": "second"}


def test_ac5_seed_fallbacks_differ_from_their_primaries(seed):
    result = resolve(seed, today=TODAY)
    for role, spec in seed["roles"].items():
        for other in spec.get("distinct_from", []):
            assert result.models[role] != result.models[other], role


@pytest.mark.parametrize("status", ["candidate", "disabled"])
def test_ac6_non_approved_models_are_never_selected(status):
    reg = _registry([_model("shiny", rank=99, status=status), _model("ok", rank=1)], {"r": _role()})
    assert resolve(reg, today=TODAY).models["r"] == "ok"


def test_tier_order_beats_rank():
    reg = _registry(
        [_model("fast-one", tier="fast", rank=1), _model("big", tier="balanced", rank=99)],
        {"r": _role(tiers=["fast", "balanced"])},
    )
    assert resolve(reg, today=TODAY).models["r"] == "fast-one"


# ── AC8 ───────────────────────────────────────────────────────────────────────

def test_ac8_unresolvable_role_is_none_with_error_and_does_not_raise():
    reg = _registry([_model("a", vendor="anthropic")], {"r": _role(vendor="openai")})
    result = resolve(reg, today=TODAY)
    assert result.models["r"] is None
    assert result.sources["r"] == "unresolved"
    assert any("r" in e for e in result.errors)


# ── AC9 ───────────────────────────────────────────────────────────────────────

def test_ac9_resolution_is_deterministic_and_fingerprinted(seed):
    a, b = resolve(seed, today=TODAY), resolve(seed, today=TODAY)
    assert a.models == b.models
    assert a.fingerprint() == b.fingerprint()
    changed = resolve(seed, overrides={"intake.primary": "x"}, today=TODAY)
    assert changed.fingerprint() != a.fingerprint()


def test_ac9_table_lists_every_role(seed):
    table = resolve(seed, today=TODAY).format_table()
    for role in seed["roles"]:
        assert role in table


def test_ac9_model_config_resolves_once_per_process():
    import backend.models.model_config as mc
    import backend.models.model_config as again
    assert mc.RESOLUTION is again.RESOLUTION
    assert mc.get_advisor_model("deep", "claude") == mc.RESOLUTION.models["research.claude.deep"]
    assert mc.SYNTHESIS_ANALYTICAL == mc.RESOLUTION.models["synthesis.primary"]


# ── Task 4: intake call works with GPT-5-family models ───────────────────────

def test_intake_openai_call_uses_max_completion_tokens():
    # gpt-5.4-mini rejects max_tokens with a 400 (verified live 2026-11-27).
    from unittest.mock import MagicMock, patch
    from backend.models import openai_client

    client = MagicMock()
    client.chat.completions.create.return_value.choices = [MagicMock(message=MagicMock(content="{}"))]
    with patch.object(openai_client, "_get_client", return_value=client):
        try:
            openai_client._call_gpt4o_mini_intake_once("prompt")
        except Exception:
            pass  # schema validation of "{}" may fail; only the request matters here
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "max_tokens" not in kwargs
    assert kwargs["max_completion_tokens"] == 2000
    assert kwargs["model"] == openai_client.INTAKE_MODEL


# ── AC7 ───────────────────────────────────────────────────────────────────────

def test_ac7_discovery_survives_failing_and_hanging_providers():
    import time
    from backend.models.discovery import discover

    def boom(timeout):
        raise RuntimeError("provider down")

    def hang(timeout):
        time.sleep(30)

    def ok(timeout):
        return {"m1": {"retires_at": TODAY, "aliases": ["m1-latest"]}}

    start = time.monotonic()
    result = discover(timeout=0.5, fetchers={"anthropic": boom, "xai": hang, "openai": ok})
    assert time.monotonic() - start < 3
    assert set(result) == {"openai"}
    assert result["openai"]["available"] == {"m1", "m1-latest"}
    assert result["openai"]["retires"] == {"m1": TODAY}


def test_ac7_no_discovery_data_resolves_from_registry_alone(seed):
    assert resolve(seed, availability={}, today=TODAY).models == EXPECTED_PARITY


# ── AC12 / AC13: tools/check_models ───────────────────────────────────────────

def _discovered(vendor, ids, retires=None, aliases=None):
    models = {i: {"retires_at": (retires or {}).get(i), "aliases": (aliases or {}).get(i, [])} for i in ids}
    available = set(ids) | {a for v in (aliases or {}).values() for a in v}
    return {vendor: {"available": available,
                     "retires": {i: d for i, d in (retires or {}).items()},
                     "models": models}}


def _seed_vendor_ids(seed, vendor):
    return [m["id"] for m in seed["models"] if m["vendor"] == vendor and m["status"] == "approved"]


def test_ac12_report_lists_new_retiring_and_missing_models(seed):
    from tools.check_models import build_report
    discovered = {}
    discovered.update(_discovered(
        "anthropic",
        _seed_vendor_ids(seed, "anthropic") + ["claude-opus-9"],
        retires={"claude-sonnet-4-6": TODAY + timedelta(days=60)},
    ))
    discovered.update(_discovered(
        "openai",
        [i for i in _seed_vendor_ids(seed, "openai") if i != "gpt-5.4"] + ["gpt-7", "gpt-7-2027-01-01", "gpt-7-audio"],
    ))
    resolution = resolve(seed, availability=discovered, today=TODAY)
    text, code = build_report(seed, discovered, resolution, today=TODAY)

    assert "claude-opus-9" in text and "gpt-7" in text
    assert "gpt-7-2027-01-01" not in text and "gpt-7-audio" not in text   # filtered snapshots/audio
    assert "claude-sonnet-4-6" in text and "60 days" in text              # retiring, warning window
    assert "gpt-5.4" in text and "missing" in text.lower()                # approved, not listed
    assert code == 1   # in-use gpt-5.4 is missing from OpenAI's list


def test_ac12_report_exits_0_when_healthy_and_1_inside_buffer(seed):
    from tools.check_models import build_report
    healthy = _discovered("anthropic", _seed_vendor_ids(seed, "anthropic"))
    _, code = build_report(seed, healthy, resolve(seed, availability=healthy, today=TODAY), today=TODAY)
    assert code == 0

    soon = _discovered("anthropic", _seed_vendor_ids(seed, "anthropic"),
                       retires={"claude-opus-4-6": TODAY + timedelta(days=10)})
    _, code = build_report(seed, soon, resolve(seed, availability=soon, today=TODAY), today=TODAY)
    assert code == 1


def test_ac13_write_adds_candidates_updates_dates_never_changes_status(seed):
    from tools.check_models import update_registry
    discovered = {}
    discovered.update(_discovered("anthropic", _seed_vendor_ids(seed, "anthropic") + ["claude-opus-9"],
                                  retires={"claude-sonnet-4-6": date(2027, 3, 1)}))
    discovered.update(_discovered("openai", ["gpt-4o-mini", "gpt-7"], retires={"gpt-4o-mini": date(2027, 1, 14)}))
    before = {m["id"]: m["status"] for m in seed["models"]}

    updated, changes = update_registry(copy.deepcopy(seed), discovered, today=TODAY)
    by_id = {m["id"]: m for m in updated["models"]}

    assert by_id["claude-opus-9"]["status"] == "candidate"
    assert by_id["claude-opus-9"]["tier"] is None and by_id["claude-opus-9"]["rank"] is None
    assert by_id["gpt-7"]["status"] == "candidate"
    assert by_id["claude-sonnet-4-6"]["retires_at"] == "2027-03-01"
    for mid, status in before.items():
        assert by_id[mid]["status"] == status
    validate_registry(updated)
    assert changes


def test_registry_dump_round_trips_in_one_model_per_line_format(seed):
    import json
    from tools.check_models import dump_registry
    from backend.models.registry import REGISTRY_PATH
    text = dump_registry(seed)
    assert json.loads(text) == seed
    assert text == REGISTRY_PATH.read_text()


def test_ac13_models_already_retiring_are_not_added_as_candidates(seed):
    from tools.check_models import update_registry
    discovered = _discovered("anthropic", _seed_vendor_ids(seed, "anthropic") + ["claude-old", "claude-new"],
                             retires={"claude-old": TODAY + timedelta(days=3)})
    updated, _ = update_registry(copy.deepcopy(seed), discovered, today=TODAY)
    ids = {m["id"] for m in updated["models"]}
    assert "claude-new" in ids and "claude-old" not in ids
