import os

import pytest

# Model discovery calls provider APIs at import time; tests must stay offline.
os.environ["MODEL_DISCOVERY"] = "0"


@pytest.fixture(autouse=True)
def _no_real_anthropic_calls(monkeypatch):
    """
    The panel router and the seat repair call Claude on every session, so a
    test that drives the session with only the research seats mocked would
    reach the network. Make the shared client fail fast instead (the router and
    repair both degrade gracefully). Tests that patch call_claude or _get_client
    themselves are unaffected; live evals (RUN_LIVE_EVALS=1) keep the real client.
    """
    if os.getenv("RUN_LIVE_EVALS") == "1":
        return

    def _offline():
        raise RuntimeError("Anthropic client disabled in tests (see conftest.py)")

    monkeypatch.setattr("backend.models.anthropic_client._get_client", _offline)
