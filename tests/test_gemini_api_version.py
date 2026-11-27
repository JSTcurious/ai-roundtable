"""
tests/test_gemini_api_version.py

The Gemini seat uses preview models, which Google serves only on the v1beta
API. google-genai 3.x defaults to v1, where they return 404 — so the client
must pin v1beta explicitly rather than rely on the SDK default.
"""

from unittest.mock import patch


def test_gemini_client_pins_v1beta_api():
    from backend.models import google_client

    with patch.object(google_client, "_client", None), \
         patch.object(google_client.genai, "Client") as client_cls:
        google_client._get_client()

    http_options = client_cls.call_args.kwargs.get("http_options") or {}
    assert http_options.get("api_version") == "v1beta"
