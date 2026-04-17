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
    SYNTHESIS_SKEPTICISM,
    SYNTHESIS_TRUST_HIERARCHY,
    build_synthesis_prompt,
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


def test_confidence_convention_has_examples_section():
    assert "## Examples" in CONFIDENCE_CONVENTION


def test_confidence_convention_has_fabrication_example():
    assert "Bad (do not do this)" in CONFIDENCE_CONVENTION
    assert "[UNCERTAIN] I'm not aware of Claude Opus 4.7" in CONFIDENCE_CONVENTION


def test_confidence_convention_has_defer_example():
    assert "[DEFER] I don't have reliable data on this" in CONFIDENCE_CONVENTION


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


# ---------------------------------------------------------------------------
# SYNTHESIS_SKEPTICISM — present in synthesis prompt, absent from round-1.
# ---------------------------------------------------------------------------

_SYNTHESIS_MARKER = "Synthesizing Other Models' Responses"

# Helper — a synthesis prompt with dummy inputs for structure testing.
_SAMPLE_SYNTHESIS = build_synthesis_prompt(
    output_type="report",
    perplexity_findings="perplexity live research content",
    round1_responses={
        "gemini": "gemini response",
        "gpt": "gpt response",
        "grok": "grok response",
    },
    optimized_prompt="user prompt",
)


def test_synthesis_skepticism_constant_has_marker():
    assert _SYNTHESIS_MARKER in SYNTHESIS_SKEPTICISM


def test_synthesis_prompt_contains_skepticism():
    assert _SYNTHESIS_MARKER in _SAMPLE_SYNTHESIS


@pytest.mark.parametrize("model", ROUND1_MODELS)
def test_synthesis_skepticism_absent_from_round1(model):
    prompt = get_round1_system_prompt(model)
    assert _SYNTHESIS_MARKER not in prompt, (
        f"{model}: SYNTHESIS_SKEPTICISM must not appear in round-1 prompts"
    )


# ---------------------------------------------------------------------------
# SYNTHESIS_TRUST_HIERARCHY — present in synthesis prompt, absent from round-1.
# ---------------------------------------------------------------------------

_TRUST_HIERARCHY_MARKER = "Source Trust Hierarchy"


def test_synthesis_trust_hierarchy_constant_has_marker():
    assert _TRUST_HIERARCHY_MARKER in SYNTHESIS_TRUST_HIERARCHY


def test_synthesis_prompt_contains_trust_hierarchy():
    assert _TRUST_HIERARCHY_MARKER in _SAMPLE_SYNTHESIS


@pytest.mark.parametrize("model", ROUND1_MODELS)
def test_synthesis_trust_hierarchy_absent_from_round1(model):
    prompt = get_round1_system_prompt(model)
    assert _TRUST_HIERARCHY_MARKER not in prompt, (
        f"{model}: SYNTHESIS_TRUST_HIERARCHY must not appear in round-1 prompts"
    )


# ---------------------------------------------------------------------------
# Synthesis prompt block ordering:
# role → ANTI_HALLUCINATION_BLOCK → CASCADING_GUARD →
# CONFIDENCE_CONVENTION → SYNTHESIS_SKEPTICISM → SYNTHESIS_TRUST_HIERARCHY
# → task instructions
# ---------------------------------------------------------------------------

def test_synthesis_role_precedes_anti_hallucination():
    role_pos = _SAMPLE_SYNTHESIS.find("You are the expert chair")
    guard_pos = _SAMPLE_SYNTHESIS.find("Response Accuracy Guidelines")
    assert 0 <= role_pos < guard_pos, "role must precede ANTI_HALLUCINATION_BLOCK"


def test_synthesis_anti_hallucination_precedes_cascading_guard():
    anti_pos = _SAMPLE_SYNTHESIS.find("Response Accuracy Guidelines")
    cascade_pos = _SAMPLE_SYNTHESIS.find("independently verify")
    assert anti_pos < cascade_pos, "ANTI_HALLUCINATION_BLOCK must precede CASCADING_GUARD"


def test_synthesis_cascading_guard_precedes_confidence_convention():
    cascade_pos = _SAMPLE_SYNTHESIS.find("independently verify")
    confidence_pos = _SAMPLE_SYNTHESIS.find("Confidence Qualifiers")
    assert cascade_pos < confidence_pos, "CASCADING_GUARD must precede CONFIDENCE_CONVENTION"


def test_synthesis_confidence_convention_precedes_skepticism():
    confidence_pos = _SAMPLE_SYNTHESIS.find("Confidence Qualifiers")
    skepticism_pos = _SAMPLE_SYNTHESIS.find(_SYNTHESIS_MARKER)
    assert confidence_pos < skepticism_pos, "CONFIDENCE_CONVENTION must precede SYNTHESIS_SKEPTICISM"


def test_synthesis_skepticism_precedes_trust_hierarchy():
    skepticism_pos = _SAMPLE_SYNTHESIS.find(_SYNTHESIS_MARKER)
    trust_pos = _SAMPLE_SYNTHESIS.find(_TRUST_HIERARCHY_MARKER)
    assert skepticism_pos < trust_pos, "SYNTHESIS_SKEPTICISM must precede SYNTHESIS_TRUST_HIERARCHY"


def test_synthesis_trust_hierarchy_precedes_task_instructions():
    trust_pos = _SAMPLE_SYNTHESIS.find(_TRUST_HIERARCHY_MARKER)
    task_pos = _SAMPLE_SYNTHESIS.find("VERIFIED LIVE RESEARCH")
    assert trust_pos < task_pos, "SYNTHESIS_TRUST_HIERARCHY must precede task instructions"


# ---------------------------------------------------------------------------
# Structural separation — Perplexity block precedes round-1 block in task.
# ---------------------------------------------------------------------------

def test_synthesis_task_has_verified_live_research_header():
    assert "VERIFIED LIVE RESEARCH" in _SAMPLE_SYNTHESIS


def test_synthesis_task_has_round1_header():
    assert "Round-1 Model Responses (apply CASCADING_GUARD to these)" in _SAMPLE_SYNTHESIS


def test_synthesis_perplexity_block_precedes_round1_block():
    perplexity_pos = _SAMPLE_SYNTHESIS.find("VERIFIED LIVE RESEARCH")
    round1_pos = _SAMPLE_SYNTHESIS.find("Round-1 Model Responses")
    assert perplexity_pos < round1_pos, (
        "VERIFIED LIVE RESEARCH block must appear before Round-1 Model Responses block"
    )


def test_synthesis_perplexity_content_in_verified_block():
    """Perplexity findings land inside the VERIFIED block, before the round-1 block."""
    perplexity_pos = _SAMPLE_SYNTHESIS.find("perplexity live research content")
    round1_pos = _SAMPLE_SYNTHESIS.find("Round-1 Model Responses")
    assert 0 < perplexity_pos < round1_pos, (
        "Perplexity findings must appear inside VERIFIED LIVE RESEARCH, before round-1 responses"
    )


def test_synthesis_round1_content_after_round1_header():
    """Round-1 model responses land after their header, not in the Perplexity block."""
    round1_pos = _SAMPLE_SYNTHESIS.find("Round-1 Model Responses")
    gemini_pos = _SAMPLE_SYNTHESIS.find("gemini response")
    assert round1_pos < gemini_pos, (
        "Round-1 model response text must appear after Round-1 Model Responses header"
    )
