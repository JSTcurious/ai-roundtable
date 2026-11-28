"""
tests/test_privacy_guard.py — PRIVACY_SECURITY_SPEC AC2, AC4, AC5, AC8.

Unit tests for backend/privacy_guard.py: detection rules, the public
allowlist, deterministic token reuse, re-hydration and the streaming
re-hydrator. No network, no models.

Run with:
    uv run pytest tests/test_privacy_guard.py -v
"""

import pytest

from backend.privacy_guard import (
    PrivacyVault,
    StreamRehydrator,
    VaultStore,
    rehydrate,
    rehydrate_obj,
    sanitize,
    sanitize_obj,
)

ACCEPTANCE_PROMPT = "Sarah Jenkins at Apex Logistics ($437,500, ID: MSA-88412)"
SENSITIVE = ["Sarah Jenkins", "Apex Logistics", "$437,500", "MSA-88412"]


def _sanitize(text, vault=None):
    vault = vault or PrivacyVault()
    return sanitize(text, vault), vault


# ── AC1 (unit level) — the acceptance prompt ─────────────────────────────────

def test_acceptance_prompt_redacts_all_four_values():
    result, vault = _sanitize(ACCEPTANCE_PROMPT)
    for value in SENSITIVE:
        assert value not in result.sanitized_text, value
    assert "[PERSON_1]" in result.sanitized_text
    assert "[ORG_1]" in result.sanitized_text
    assert "[AMOUNT_1" in result.sanitized_text
    assert "[ID_1]" in result.sanitized_text
    assert result.redaction_count == 4


def test_acceptance_prompt_round_trips():
    result, vault = _sanitize(ACCEPTANCE_PROMPT)
    assert rehydrate(result.sanitized_text, vault) == ACCEPTANCE_PROMPT


# ── AC2 — public allowlist ───────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "Should we move from AWS to GCP for SOC 2 and GDPR?",
    "I have an offer at Google and one at Stripe. Which should I join?",
    "Does HIPAA apply if we host on Microsoft Azure with ISO 27001?",
    "Is an H-1B transfer to Amazon risky while my I-140 is pending with USCIS?",
    "Compare Claude, GPT and Gemini for SEC filings analysis.",
])
def test_public_terms_are_not_redacted(text):
    result, _ = _sanitize(text)
    assert result.sanitized_text == text
    assert result.redaction_count == 0


# ── AC8 — detector table (positive cases) ───────────────────────────────────

@pytest.mark.parametrize("text, secret, kind", [
    ("email me at jane.doe+work@example.co.uk please", "jane.doe+work@example.co.uk", "EMAIL"),
    ("my key is sk-ant-api03-AbCdEfGhIjKlMnOpQrSt", "sk-ant-api03-AbCdEfGhIjKlMnOpQrSt", "SECRET"),
    ("token sk-proj-AbCdEfGhIjKlMnOpQrStUv12", "sk-proj-AbCdEfGhIjKlMnOpQrStUv12", "SECRET"),
    ("aws AKIAIOSFODNN7EXAMPLE leaked", "AKIAIOSFODNN7EXAMPLE", "SECRET"),
    ("gh token ghp_abcdefghijklmnopqrstuvwxyz0123", "ghp_abcdefghijklmnopqrstuvwxyz0123", "SECRET"),
    ("SSN 123-45-6789 on file", "123-45-6789", "ID"),
    ("our EIN is 12-3456789", "12-3456789", "ID"),
    ("receipt EAC2190012345 is pending", "EAC2190012345", "ID"),
    ("contract MSA-88412 renews", "MSA-88412", "ID"),
    ("Acct #99134 is overdrawn", "99134", "ID"),
    ("call me at (415) 555-0134 tomorrow", "(415) 555-0134", "PHONE"),
    ("or +44 20 7946 0958 in London", "+44 20 7946 0958", "PHONE"),
    ("a base of $437,500 plus equity", "$437,500", "AMOUNT"),
    ("they offered $185k base", "$185k", "AMOUNT"),
    ("budget of USD 1,200,000 for the year", "USD 1,200,000", "AMOUNT"),
    ("a salary of €90,000 in Berlin", "€90,000", "AMOUNT"),
    ("I work at Brightline Analytics today", "Brightline Analytics", "ORG"),
    ("we signed with Northwind Traders LLC last year", "Northwind Traders LLC", "ORG"),
    ("I got an offer from Zentrix last week", "Zentrix", "ORG"),
    ("my manager Priya Raman disagrees", "Priya Raman", "PERSON"),
    ("I met Dr. Okafor yesterday", "Okafor", "PERSON"),
    ("David Chen thinks we should wait", "David Chen", "PERSON"),
])
def test_detector_positive(text, secret, kind):
    result, vault = _sanitize(text)
    assert secret not in result.sanitized_text, result.sanitized_text
    assert f"[{kind}_1" in result.sanitized_text, result.sanitized_text
    assert rehydrate(result.sanitized_text, vault) == text


# ── AC8 — detector table (negative cases) ───────────────────────────────────

@pytest.mark.parametrize("text", [
    "I love Apple pie in May 2026.",
    "Will Smith's movie was on Netflix.",
    "A coffee costs $5 and lunch is $12.50.",
    "Revenue grew 40% to 3,000 units.",
    "We use Python and Kubernetes on Linux.",
    "The meeting is on Monday at 3pm in New York.",
    "Should I take the job? It pays well.",
    "GPT-4 and EB-1A and I-485 and COVID-19 are fine.",
])
def test_detector_negative(text):
    result, _ = _sanitize(text)
    assert result.sanitized_text == text, result.sanitized_text
    assert result.redaction_count == 0


# ── Amount magnitude hint (Q2 decision) ──────────────────────────────────────

@pytest.mark.parametrize("text, hint", [
    ("$437,500", "$440K"),
    ("$1,234,567", "$1.2M"),
    ("$185k", "$190K"),
    ("€90,000", "€90K"),
    ("USD 2,500,000,000", "USD 2.5B"),
])
def test_amount_token_carries_magnitude_hint(text, hint):
    result, _ = _sanitize(f"value {text} here")
    assert f"[AMOUNT_1 ≈ {hint}]" in result.sanitized_text


def test_amount_under_threshold_not_tokenized():
    result, _ = _sanitize("fee is $950")
    assert result.sanitized_text == "fee is $950"


# ── AC5 — determinism and re-entry ───────────────────────────────────────────

def test_same_value_reuses_token_within_session():
    vault = PrivacyVault()
    first = sanitize("Sarah Jenkins called.", vault).sanitized_text
    second = sanitize("I told Sarah Jenkins no.", vault).sanitized_text
    assert "[PERSON_1]" in first and "[PERSON_1]" in second
    assert "[PERSON_2]" not in second


def test_new_value_gets_next_token():
    vault = PrivacyVault()
    sanitize("Sarah Jenkins called.", vault)
    second = sanitize("Then Marcus Bell replied.", vault).sanitized_text
    assert "[PERSON_2]" in second


def test_rehydrated_text_resanitizes_to_same_tokens():
    vault = PrivacyVault()
    tokenized = sanitize(ACCEPTANCE_PROMPT, vault).sanitized_text
    shown = rehydrate(tokenized, vault)
    assert sanitize(shown, vault).sanitized_text == tokenized


def test_known_value_reused_even_without_cue():
    vault = PrivacyVault()
    sanitize("I work at Zentrix.", vault)
    # No employment cue this time — still replaced because it is known.
    assert "Zentrix" not in sanitize("Zentrix is growing.", vault).sanitized_text


def test_tokens_in_input_are_not_retokenized():
    vault = PrivacyVault()
    text = sanitize(ACCEPTANCE_PROMPT, vault).sanitized_text
    again = sanitize(text, vault)
    assert again.sanitized_text == text


# ── Re-hydration ─────────────────────────────────────────────────────────────

def test_rehydrate_accepts_amount_token_without_hint():
    vault = PrivacyVault()
    sanitize("base $437,500", vault)
    assert rehydrate("about [AMOUNT_1] total", vault) == "about $437,500 total"


def test_rehydrate_leaves_unknown_tokens():
    assert rehydrate("[PERSON_9] and [VERIFIED]", PrivacyVault()) == "[PERSON_9] and [VERIFIED]"


def test_obj_helpers_are_recursive_and_copy():
    vault = PrivacyVault()
    obj = {"a": ["Sarah Jenkins at Apex Logistics"], "n": 3, "b": {"c": "$437,500"}}
    clean = sanitize_obj(obj, vault)
    assert "Sarah" not in str(clean) and clean["n"] == 3
    assert obj["a"][0] == "Sarah Jenkins at Apex Logistics"  # input untouched
    assert rehydrate_obj(clean, vault) == obj


def test_sanitize_obj_skips_named_keys():
    vault = PrivacyVault()
    clean = sanitize_obj({"privacy_ref": "MSA-12345", "x": "MSA-12345"}, vault,
                         skip_keys={"privacy_ref"})
    assert clean["privacy_ref"] == "MSA-12345"
    assert clean["x"] == "[ID_1]"


def test_audit_counts_by_type():
    vault = PrivacyVault()
    sanitize(ACCEPTANCE_PROMPT, vault)
    audit = vault.audit()
    assert audit["pii_tokens_redacted"] == 4
    assert audit["by_type"] == {"PERSON": 1, "ORG": 1, "AMOUNT": 1, "ID": 1}
    assert "Sarah" not in str(audit)


# ── AC4 — streaming re-hydration ─────────────────────────────────────────────

def _vault_with_org():
    vault = PrivacyVault()
    sanitize("I work at Apex Logistics", vault)
    return vault


def test_stream_rehydrator_joins_split_token():
    stream = StreamRehydrator(_vault_with_org())
    out = stream.feed("[OR") + stream.feed("G_1] wins") + stream.flush()
    assert out == "Apex Logistics wins"


def test_stream_rehydrator_split_inside_amount_hint():
    vault = PrivacyVault()
    sanitize("base $437,500", vault)
    stream = StreamRehydrator(vault)
    out = stream.feed("pay [AMOUNT_1 ≈ $4") + stream.feed("40K] now") + stream.flush()
    assert out == "pay $437,500 now"


def test_stream_rehydrator_flushes_unclosed_bracket():
    stream = StreamRehydrator(_vault_with_org())
    out = stream.feed("a [") + stream.flush()
    assert out == "a ["


def test_stream_rehydrator_does_not_hold_normal_brackets():
    stream = StreamRehydrator(_vault_with_org())
    assert stream.feed("see [1] and [VERIFIED] ") == "see [1] and [VERIFIED] "


# ── Vault store (Q1 decision) ────────────────────────────────────────────────

def test_vault_store_take_removes_and_ttl_expires():
    now = [1000.0]
    store = VaultStore(ttl_seconds=60, clock=lambda: now[0])
    vault = PrivacyVault()
    store.put("ref-1", vault)
    assert store.get("ref-1") is vault
    assert store.take("ref-1") is vault
    assert store.take("ref-1") is None

    store.put("ref-2", PrivacyVault())
    now[0] += 61
    assert store.get("ref-2") is None


def test_vault_repr_never_shows_values():
    vault = PrivacyVault()
    sanitize(ACCEPTANCE_PROMPT, vault)
    assert "Sarah" not in repr(vault)
