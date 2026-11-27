"""
tests/test_live_synthesis_post_cutoff.py

Live regression check for ADR 002's original failure: the synthesizer
refusing Perplexity's post-training-cutoff data. Runs ADR 002's T1 fixture
through the production synthesis path. Calls paid APIs, so it is skipped
unless RUN_LIVE_EVALS=1 — run it when changing synthesis models or prompts:

    RUN_LIVE_EVALS=1 uv run pytest tests/test_live_synthesis_post_cutoff.py
"""

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_EVALS") != "1", reason="live API eval; set RUN_LIVE_EVALS=1"
)


def test_synthesis_accepts_post_cutoff_perplexity_data():
    from backend.main import call_synthesis_async
    from backend.models.model_config import SYNTHESIS_ANALYTICAL
    from backend.router import build_synthesis_system
    from experiments.synthesizer_eval.prompts import (
        TEST1_PERPLEXITY, TEST1_ROUND1, TEST1_USER_PROMPT,
    )

    system = build_synthesis_system(
        round1_responses={k.lower(): v for k, v in TEST1_ROUND1.items()},
        audit_text=TEST1_PERPLEXITY,
    )
    text = asyncio.run(call_synthesis_async(
        SYNTHESIS_ANALYTICAL,
        [{"role": "user", "content": TEST1_USER_PROMPT}],
        system,
        "smart",
    ))
    low = text.lower()

    assert "$5" in text and "25" in text, "Opus 4.7 $5/$25 pricing missing"
    assert "retire" in low or "deprecat" in low, "Claude 3 Opus retirement missing"
    assert "fabricat" not in low, "synthesis called Perplexity data fabricated"
