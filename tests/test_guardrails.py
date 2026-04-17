"""
tests/test_guardrails.py

Verifies that every Round 1 system prompt contains the required epistemic
guardrail blocks. No real API calls are made — this tests prompt construction
only.

Run with:
    uv run pytest tests/test_guardrails.py -v
"""

import pytest

from backend.router import (
    ANTI_HALLUCINATION_BLOCK,
    CASCADING_GUARD,
    CONFIDENCE_CONVENTION,
    get_round1_system_prompt,
)

ROUND1_MODELS = ["gemini", "gpt", "grok", "claude"]

# The four tags that CONFIDENCE_CONVENTION must define.
REQUIRED_TAGS = ["[VERIFIED]", "[LIKELY]", "[UNCERTAIN]", "[DEFER]"]


# ---------------------------------------------------------------------------
# Constant integrity — verify the blocks themselves contain expected content.
# ---------------------------------------------------------------------------

def test_anti_hallucination_block_has_accuracy_header():
    assert "Response Accuracy Guidelines" in ANTI_HALLUCINATION_BLOCK


def test_cascading_guard_mentions_attribution():
    assert "independently verify" in CASCADING_GUARD


def test_confidence_convention_defines_all_tags():
    for tag in REQUIRED_TAGS:
        assert tag in CONFIDENCE_CONVENTION, f"CONFIDENCE_CONVENTION missing tag: {tag}"


# ---------------------------------------------------------------------------
# Composed prompt — every model gets all three blocks.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model", ROUND1_MODELS)
def test_anti_hallucination_block_present(model):
    prompt = get_round1_system_prompt(model)
    assert "Response Accuracy Guidelines" in prompt, (
        f"{model}: ANTI_HALLUCINATION_BLOCK not found in composed prompt"
    )


@pytest.mark.parametrize("model", ROUND1_MODELS)
def test_cascading_guard_present(model):
    prompt = get_round1_system_prompt(model)
    assert "independently verify" in prompt, (
        f"{model}: CASCADING_GUARD not found in composed prompt"
    )


@pytest.mark.parametrize("model", ROUND1_MODELS)
def test_confidence_convention_present(model):
    prompt = get_round1_system_prompt(model)
    assert "Confidence Qualifiers" in prompt, (
        f"{model}: CONFIDENCE_CONVENTION not found in composed prompt"
    )


@pytest.mark.parametrize("model", ROUND1_MODELS)
@pytest.mark.parametrize("tag", REQUIRED_TAGS)
def test_confidence_tags_present(model, tag):
    prompt = get_round1_system_prompt(model)
    assert tag in prompt, (
        f"{model}: confidence tag {tag!r} not found in composed prompt"
    )


# ---------------------------------------------------------------------------
# Block ordering — role prompt must come before guardrails.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model", ROUND1_MODELS)
def test_role_identification_precedes_guardrails(model):
    prompt = get_round1_system_prompt(model)
    role_pos = prompt.find("You are")
    guard_pos = prompt.find("Response Accuracy Guidelines")
    assert role_pos < guard_pos, (
        f"{model}: role identification must appear before ANTI_HALLUCINATION_BLOCK"
    )


@pytest.mark.parametrize("model", ROUND1_MODELS)
def test_cascading_guard_after_anti_hallucination(model):
    prompt = get_round1_system_prompt(model)
    anti_pos = prompt.find("Response Accuracy Guidelines")
    cascade_pos = prompt.find("independently verify")
    assert anti_pos < cascade_pos, (
        f"{model}: ANTI_HALLUCINATION_BLOCK must appear before CASCADING_GUARD"
    )


@pytest.mark.parametrize("model", ROUND1_MODELS)
def test_confidence_convention_after_cascading_guard(model):
    prompt = get_round1_system_prompt(model)
    cascade_pos = prompt.find("independently verify")
    confidence_pos = prompt.find("Confidence Qualifiers")
    assert cascade_pos < confidence_pos, (
        f"{model}: CASCADING_GUARD must appear before CONFIDENCE_CONVENTION"
    )


# ---------------------------------------------------------------------------
# Error handling — unknown model raises KeyError.
# ---------------------------------------------------------------------------

def test_unknown_model_raises():
    with pytest.raises(KeyError):
        get_round1_system_prompt("llama")
