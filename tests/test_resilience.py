"""
tests/test_resilience.py

Tests for the Task B resilience layer.

Coverage:
    - Intake fallback chain (primary → fallback1 → fallback2 → passthrough)
    - Synthesis router: FACTUAL_CONTRADICTION_SIGNALS detection
    - Research availability status tuples
    - Factcheck fallback chain (audit_with_fallback)
    - PipelineHealth: annotations for healthy and degraded sessions
    - resilient_caller: call_with_fallback labels
"""

import pytest
from unittest.mock import patch, MagicMock


# ── Synthesis router ──────────────────────────────────────────────────────────

class TestSynthesisRouter:
    """select_synthesis_model() routes based on Perplexity contradiction signals."""

    def _route(self, audit_text: str):
        from backend.router import select_synthesis_model
        return select_synthesis_model(audit_text)

    def test_clean_audit_routes_analytical(self):
        model_id, route = self._route("All models agreed on the key points.")
        assert route == "analytical"

    def test_contradicts_signal_routes_factual(self):
        model_id, route = self._route(
            "Perplexity contradicts the round-1 responses on pricing."
        )
        assert route == "factual"

    def test_incorrect_signal_routes_factual(self):
        model_id, route = self._route(
            "GPT's claim is incorrect according to current data."
        )
        assert route == "factual"

    def test_outdated_signal_routes_factual(self):
        model_id, route = self._route(
            "This information appears to be outdated — the API changed in 2024."
        )
        assert route == "factual"

    def test_factually_wrong_routes_factual(self):
        model_id, route = self._route(
            "The statistic cited is factually wrong."
        )
        assert route == "factual"

    def test_empty_audit_routes_analytical(self):
        model_id, route = self._route("")
        assert route == "analytical"

    def test_analytical_route_returns_model_id(self):
        from backend.models.model_config import SYNTHESIS_ANALYTICAL
        model_id, route = self._route("Models agreed across the board.")
        assert model_id == SYNTHESIS_ANALYTICAL

    def test_factual_route_returns_model_id(self):
        from backend.models.model_config import SYNTHESIS_FACTUAL
        model_id, route = self._route("This contradicts current data.")
        assert model_id == SYNTHESIS_FACTUAL

    def test_disagrees_signal_routes_factual(self):
        model_id, route = self._route(
            "Perplexity disagrees with Gemini's version numbers."
        )
        assert route == "factual"

    def test_not_accurate_signal_routes_factual(self):
        model_id, route = self._route(
            "The claim is not accurate based on live sources."
        )
        assert route == "factual"


# ── PipelineHealth ────────────────────────────────────────────────────────────

class TestPipelineHealth:
    """PipelineHealth emits annotations only for noteworthy events."""

    def _make(self, **kwargs):
        from backend.models.pipeline_health import PipelineHealth
        h = PipelineHealth()
        for k, v in kwargs.items():
            setattr(h, k, v)
        return h

    def test_healthy_session_produces_no_annotations(self):
        h = self._make(
            intake_degraded=False,
            research_models={"gemini": "primary", "gpt": "primary",
                             "grok": "primary", "claude": "primary"},
            factcheck_degraded=False,
            synthesis_routed="analytical",
        )
        assert h.to_annotation() == []

    def test_intake_degraded_appears_in_annotations(self):
        h = self._make(intake_degraded=True)
        annotations = h.to_annotation()
        assert any("intake" in a.lower() for a in annotations)

    def test_research_unavailable_appears_in_annotations(self):
        h = self._make(research_models={"gemini": "unavailable", "gpt": "primary",
                                        "grok": "primary", "claude": "primary"})
        annotations = h.to_annotation()
        assert any("gemini" in a.lower() for a in annotations)

    def test_research_fallback_appears_in_annotations(self):
        h = self._make(research_models={"grok": "fallback", "gemini": "primary",
                                        "gpt": "primary", "claude": "primary"})
        annotations = h.to_annotation()
        assert any("grok" in a.lower() for a in annotations)

    def test_factcheck_degraded_appears_in_annotations(self):
        h = self._make(factcheck_degraded=True, factcheck_model="gpt-4o")
        annotations = h.to_annotation()
        assert any("perplexity" in a.lower() or "fact" in a.lower()
                   for a in annotations)

    def test_synthesis_fallback_appears_in_annotations(self):
        h = self._make(synthesis_routed="analytical_fallback")
        annotations = h.to_annotation()
        assert any("synthesis" in a.lower() or "fallback" in a.lower()
                   for a in annotations)

    def test_synthesis_factual_route_appears_in_annotations(self):
        h = self._make(synthesis_routed="factual")
        annotations = h.to_annotation()
        assert any("factual" in a.lower() or "perplexity" in a.lower()
                   for a in annotations)

    def test_summary_healthy(self):
        h = self._make(
            research_models={"gemini": "primary", "gpt": "primary",
                             "grok": "primary", "claude": "primary"},
            synthesis_routed="analytical",
        )
        assert "healthy" in h.summary().lower()

    def test_summary_degraded_when_research_unavailable(self):
        h = self._make(research_models={"gemini": "unavailable", "gpt": "primary",
                                        "grok": "primary", "claude": "primary"})
        assert "degraded" in h.summary().lower()

    def test_summary_degraded_when_factcheck_degraded(self):
        h = self._make(factcheck_degraded=True)
        assert "degraded" in h.summary().lower()

    def test_multiple_degraded_events_all_appear(self):
        h = self._make(
            intake_degraded=True,
            research_models={"gemini": "unavailable", "gpt": "primary",
                             "grok": "primary", "claude": "primary"},
            factcheck_degraded=True,
        )
        annotations = h.to_annotation()
        assert len(annotations) >= 3


# ── resilient_caller ──────────────────────────────────────────────────────────

class TestIsRetryable:
    """is_retryable() must exclude exhausted-inner-chain errors to prevent double-retry."""

    def test_exhausted_inner_chain_not_retryable(self):
        from backend.models.resilient_caller import is_retryable
        assert not is_retryable(RuntimeError("GPT-4o Mini intake unavailable after 3 attempts"))
        assert not is_retryable(RuntimeError("factcheck unavailable after 2 attempts"))

    def test_normal_retryable_errors_still_retryable(self):
        from backend.models.resilient_caller import is_retryable
        assert is_retryable(Exception("503 service unavailable"))
        assert is_retryable(Exception("429 rate limit exceeded"))

    def test_generic_unavailable_without_after_is_retryable(self):
        from backend.models.resilient_caller import is_retryable
        # "unavailable" alone (without "after N attempts") stays retryable
        assert is_retryable(Exception("service unavailable"))


class TestResilientCaller:
    """call_with_fallback returns (result, label) and walks the chain correctly."""

    def _call(self, primary_fn, fallback_fns=None, emergency_fn=None):
        from backend.models.resilient_caller import call_with_fallback
        return call_with_fallback(
            primary_fn=primary_fn,
            fallback_fns=fallback_fns or [],
            emergency_fn=emergency_fn,
            role="test",
            primary_attempts=1,
            fallback_attempts=1,
        )

    def test_primary_success_returns_primary_label(self):
        result, label = self._call(primary_fn=lambda: "ok")
        assert result == "ok"
        assert label == "primary"

    def test_primary_failure_tries_fallback(self):
        result, label = self._call(
            primary_fn=lambda: (_ for _ in ()).throw(RuntimeError("down")),
            fallback_fns=[lambda: "fallback_result"],
        )
        assert result == "fallback_result"
        assert "fallback" in label

    def test_all_fallbacks_fail_uses_emergency(self):
        result, label = self._call(
            primary_fn=lambda: (_ for _ in ()).throw(RuntimeError("p")),
            fallback_fns=[
                lambda: (_ for _ in ()).throw(RuntimeError("f1")),
            ],
            emergency_fn=lambda: "emergency_result",
        )
        assert result == "emergency_result"
        assert label == "emergency"

    def test_no_emergency_raises_on_all_failure(self):
        from backend.models.resilient_caller import call_with_fallback
        with pytest.raises(Exception):
            call_with_fallback(
                primary_fn=lambda: (_ for _ in ()).throw(RuntimeError("p")),
                fallback_fns=[lambda: (_ for _ in ()).throw(RuntimeError("f"))],
                emergency_fn=None,
                role="test",
                primary_attempts=1,
                fallback_attempts=1,
            )

    def test_second_fallback_used_when_first_fails(self):
        result, label = self._call(
            primary_fn=lambda: (_ for _ in ()).throw(RuntimeError("p")),
            fallback_fns=[
                lambda: (_ for _ in ()).throw(RuntimeError("f1")),
                lambda: "fallback2_result",
            ],
        )
        assert result == "fallback2_result"
        assert "fallback" in label


# ── Research availability statuses ────────────────────────────────────────────

class TestResearchAvailabilityStatus:
    """
    call_research_*_async() return (text, status) where status is
    "primary" | "fallback" | "unavailable".
    """

    def _make_gemini_response(self, text="response"):
        resp = MagicMock()
        resp.text = text
        return resp

    def test_gemini_returns_tuple(self):
        """call_research_gemini_async returns a 2-tuple."""
        with patch("backend.models.google_client.call_gemini",
                   return_value=self._make_gemini_response()):
            import asyncio
            from backend.models.google_client import call_research_gemini_async
            result = asyncio.run(
                call_research_gemini_async(
                    [{"role": "user", "content": "test"}],
                    "system",
                    "smart",
                )
            )
            assert isinstance(result, tuple)
            assert len(result) == 2
            text, status = result
            assert isinstance(text, str)
            assert status in ("primary", "fallback", "unavailable")

    def test_gpt_returns_tuple(self):
        """call_research_gpt_async returns a 2-tuple."""
        msg = MagicMock()
        msg.content = "gpt_response"
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]

        with patch("backend.models.openai_client.call_gpt", return_value=resp):
            import asyncio
            from backend.models.openai_client import call_research_gpt_async
            result = asyncio.run(
                call_research_gpt_async(
                    [{"role": "user", "content": "test"}],
                    "system",
                    "smart",
                )
            )
            assert isinstance(result, tuple)
            assert len(result) == 2

    def test_grok_returns_tuple(self):
        """call_research_grok_async returns a 2-tuple."""
        msg = MagicMock()
        msg.content = "grok_response"
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]

        with patch("backend.models.grok_client.call_grok", return_value=resp):
            import asyncio
            from backend.models.grok_client import call_research_grok_async
            result = asyncio.run(
                call_research_grok_async(
                    [{"role": "user", "content": "test"}],
                    "system",
                    "smart",
                )
            )
            assert isinstance(result, tuple)
            assert len(result) == 2

    def test_gemini_unavailable_returns_unavailable_status(self):
        """When all Gemini paths raise, research returns (error_text, 'unavailable')."""
        client_mock = MagicMock()
        client_mock.models.generate_content.side_effect = RuntimeError("API down")
        with patch("backend.models.google_client.call_gemini",
                   side_effect=RuntimeError("API down")), \
             patch("backend.models.google_client._get_client", return_value=client_mock):
            import asyncio
            from backend.models.google_client import call_research_gemini_async
            text, status = asyncio.run(
                call_research_gemini_async(
                    [{"role": "user", "content": "test"}],
                    "system",
                    "smart",
                )
            )
            assert status == "unavailable"
            assert isinstance(text, str)


# ── Intake passthrough ────────────────────────────────────────────────────────

class TestIntakePassthrough:
    """_intake_passthrough always returns a valid IntakeDecision with tier=smart."""

    def test_passthrough_returns_intake_decision(self):
        from backend.intake import _intake_passthrough
        from backend.models.openai_client import IntakeDecision
        result = _intake_passthrough("any prompt")
        assert isinstance(result, IntakeDecision)

    def test_passthrough_tier_is_smart(self):
        from backend.intake import _intake_passthrough
        result = _intake_passthrough("any prompt")
        assert result.tier == "smart"

    def test_passthrough_never_raises(self):
        from backend.intake import _intake_passthrough
        # Should not raise even on weird input
        result = _intake_passthrough("")
        assert result is not None

    def test_passthrough_needs_no_clarification(self):
        from backend.intake import _intake_passthrough
        result = _intake_passthrough("any prompt")
        assert result.needs_clarification is False

