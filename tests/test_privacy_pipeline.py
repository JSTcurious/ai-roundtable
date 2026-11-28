"""
tests/test_privacy_pipeline.py — PRIVACY_SECURITY_SPEC AC1, AC2, AC6.

Drives a full session through the real app — intake start → intake respond
→ /ws/session → prompt review → research → fact-check → self-critique →
streamed synthesis → one dialogue turn → finalize — with every provider SDK
replaced at its module's _get_client(). All payload-building code runs for
real; only the network is faked. The fakes record every outbound payload and
echo back the placeholders they were given, so the test can check both
directions:

  AC1  no outbound payload (Anthropic, Gemini, OpenAI, xAI, Perplexity,
       OpenRouter) contains a sensitive value, and the final answer the user
       sees has every original value restored.
  AC2  public terms (AWS, SOC 2) reach Perplexity intact.
  AC6  no frame or payload carries the token map; the vault is emptied and
       removed from the store when the session ends.

Run with:
    uv run pytest tests/test_privacy_pipeline.py -v
"""

import contextlib
import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.privacy_guard import TOKEN_PATTERN, VAULTS
from backend.router import TOKEN_PRESERVATION_RULE

ACCEPTANCE_PROMPT = (
    "Sarah Jenkins at Apex Logistics ($437,500, ID: MSA-88412) wants me to "
    "renew the contract. Should I?"
)
SENSITIVE = ["Sarah Jenkins", "Apex Logistics", "$437,500", "MSA-88412"]
DIALOGUE = "What if Sarah Jenkins drops the $437,500 offer?"


def _dump(obj) -> str:
    """Serialize SDK kwargs (incl. google-genai pydantic objects) to text."""
    def default(o):
        if hasattr(o, "model_dump"):
            return o.model_dump()
        return str(o)
    return json.dumps(obj, default=default, ensure_ascii=False)


class _Recorder:
    def __init__(self):
        self.payloads: list[tuple[str, str]] = []  # (provider, serialized kwargs)
        self.contents: list[tuple[str, str]] = []  # (provider, conversation text only)

    def record(self, provider: str, kwargs: dict) -> str:
        text = _dump(kwargs)
        self.payloads.append((provider, text))
        self.contents.append((provider, _content(kwargs)))
        return text

    def providers(self) -> set:
        return {p for p, _ in self.payloads}


def _strings(obj) -> list:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings(v)]
    if isinstance(obj, (list, tuple)):
        return [s for v in obj for s in _strings(v)]
    return []


def _content(kw: dict) -> str:
    """
    The conversation text of a call, without system prompts and without the
    placeholder rule (its examples look like real tokens).
    """
    if "contents" in kw:          # Gemini
        parts = _strings(kw["contents"])
    else:                         # Anthropic / OpenAI-compatible
        parts = _strings([m for m in kw.get("messages", []) if m.get("role") != "system"])
    return "\n".join(parts).replace(TOKEN_PRESERVATION_RULE.strip(), "")


def _echo(text_in: str) -> str:
    """A model answer that repeats every placeholder it was given."""
    tokens = list(dict.fromkeys(re.findall(TOKEN_PATTERN, text_in)))
    return (
        "THE VERDICT\nRenew with care. Parties: " + " ".join(tokens)
        + "\n\nTHE HINGE\nx\n\nWHERE THE PANEL DISAGREED\nx\n\nONE NEXT ACTION\nx"
        + "\n\n? Does this fit?"
    )


_responder = None  # set per run by _run_session(responder=...): (provider, kwargs) -> text


def _reply(provider: str, kw: dict) -> str:
    """The fake model's answer: a custom responder if the test set one, else an echo."""
    if _responder is not None:
        out = _responder(provider, kw)
        if out is not None:
            return out
    return _echo(_content(kw))


def _intake_json() -> str:
    return json.dumps({
        "needs_clarification": False,
        "tier": "smart",
        "optimized_prompt": "BRIEF",  # replaced below with echoed tokens
        "output_type": "decision",
        "output_intent": "a clear recommendation",
        "session_title": "Contract renewal",
    })


def _make_fakes(rec: _Recorder):
    # ── Anthropic (intake, research seat, self-critique, synthesis, refinement)
    def anthropic_create(**kw):
        rec.record("anthropic", kw)
        if "CRITICAL OUTPUT FORMAT" in (kw.get("system") or ""):
            # Intake: the brief restates what the user wrote (still tokenized).
            decision = json.loads(_intake_json())
            decision["optimized_prompt"] = "Brief: " + _content(kw)
            out = json.dumps(decision, ensure_ascii=False)
        else:
            out = _reply("anthropic", kw)
        return SimpleNamespace(
            content=[SimpleNamespace(text=out)],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            stop_reason="end_turn", model="claude-fake",
        )

    @contextlib.contextmanager
    def anthropic_stream(**kw):
        rec.record("anthropic", kw)
        out = _reply("anthropic", kw)
        # 3-char chunks: placeholders are always split across chunks.
        yield SimpleNamespace(text_stream=[out[i:i + 3] for i in range(0, len(out), 3)])

    anthropic = MagicMock()
    anthropic.messages.create.side_effect = anthropic_create
    anthropic.messages.stream.side_effect = anthropic_stream

    # ── Gemini
    def gemini_generate(**kw):
        rec.record("gemini", kw)
        out = _reply("gemini", kw)
        return SimpleNamespace(text=out, usage_metadata=SimpleNamespace(
            prompt_token_count=1, candidates_token_count=1))

    gemini = MagicMock()
    gemini.models.generate_content.side_effect = gemini_generate

    # ── OpenAI-compatible (GPT, Perplexity, OpenRouter, Grok)
    def chat(provider):
        def create(**kw):
            rec.record(provider, kw)
            out = _reply(provider, kw)
            resp = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=out))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
                model=f"{provider}-fake",
                citations=["https://example.com/source"],
            )
            return resp
        return create

    gpt = MagicMock()
    gpt.chat.completions.create.side_effect = chat("openai")
    perplexity = MagicMock()
    perplexity.chat.completions.create.side_effect = chat("perplexity")
    openrouter = MagicMock()
    openrouter.chat.completions.create.side_effect = chat("openrouter")

    grok_create = chat("xai")

    def grok_raw(**kw):
        raw = MagicMock()
        raw.headers = {"x-zero-data-retention": "true"}
        raw.parse.return_value = grok_create(**kw)
        return raw

    grok = MagicMock()
    grok.chat.completions.with_raw_response.create.side_effect = grok_raw

    return {
        "backend.models.anthropic_client": anthropic,
        "backend.models.google_client": gemini,
        "backend.models.openai_client": gpt,
        "backend.models.grok_client": grok,
        "backend.models.perplexity_client": perplexity,
        "backend.models.openrouter_client": openrouter,
    }


@contextlib.contextmanager
def _faked_providers(rec: _Recorder):
    fakes = _make_fakes(rec)
    with contextlib.ExitStack() as stack:
        for module, client in fakes.items():
            stack.enter_context(patch(f"{module}._get_client", return_value=client))
        # The fact-check GPT fallback builds its own OpenAI() client.
        stack.enter_context(patch("openai.OpenAI", return_value=fakes["backend.models.openai_client"]))
        yield


def _run_session(prompt: str, dialogue: str = DIALOGUE, responder=None):
    global _responder
    from backend import main

    _responder = responder
    try:
        return _run_session_inner(main, prompt, dialogue)
    finally:
        _responder = None


def _run_session_inner(main, prompt: str, dialogue: str):

    rec = _Recorder()
    frames: list[dict] = []
    with _faked_providers(rec):
        client = TestClient(main.app)

        # ── Intake (HTTP) — answer every question with the chip-less skip text
        r = client.post("/api/intake/start", json={"prompt": prompt})
        assert r.status_code == 200, r.text
        body = r.json()
        session_id = body["session_id"]
        vault = VAULTS.get(session_id)
        for _ in range(8):
            if body["status"] == "complete":
                break
            r = client.post("/api/intake/respond",
                            json={"session_id": session_id, "answer": "I'd prefer not to say"})
            assert r.status_code == 200, r.text
            body = r.json()
        assert body["status"] == "complete"
        config = body["config"]
        intake_bodies = [body]

        # ── Session (WebSocket) — exactly what the frontend sends
        with client.websocket_connect("/ws/session") as ws:
            ws.send_json({
                "prompt": config["optimized_prompt"],
                "session_config": config,
                "history": [],
            })

            def until(msg_type):
                while True:
                    frames.append(ws.receive_json())
                    if frames[-1]["type"] == msg_type:
                        return frames[-1]

            review = until("prompt_review")
            ws.send_json({"type": "prompt_confirmed", "stated_facts": review["stated_facts"]})
            until("synthesis_draft")
            ws.send_json({"type": "user_dialogue_response", "content": dialogue})
            until("synthesis_draft")
            ws.send_json({"type": "finalize_synthesis"})
            until("session_complete")

    return SimpleNamespace(rec=rec, frames=frames, config=config, vault=vault,
                           session_id=session_id, intake_bodies=intake_bodies)


@pytest.fixture(scope="module")
def session():
    return _run_session(ACCEPTANCE_PROMPT)


# ── AC1 — zero leakage ───────────────────────────────────────────────────────

def test_all_five_providers_were_called(session):
    # OpenRouter is only a fallback; the five primary providers must all be hit.
    assert {"anthropic", "gemini", "openai", "xai", "perplexity"} <= session.rec.providers()


@pytest.mark.parametrize("value", SENSITIVE)
def test_no_outbound_payload_contains_sensitive_value(session, value):
    leaks = [p for p, text in session.rec.payloads if value in text]
    assert not leaks, f"{value!r} sent to {sorted(set(leaks))}"


def test_payloads_carry_placeholders(session):
    research = [t for p, t in session.rec.payloads if p in ("gemini", "openai", "xai")]
    assert research and all("[PERSON_1]" in t and "[ORG_1]" in t for t in research)


@pytest.mark.parametrize("value", SENSITIVE)
def test_final_answer_restores_value(session, value):
    final = next(f for f in session.frames if f["type"] == "synthesis_final")
    assert value in final["content"]


def test_no_placeholder_reaches_the_user(session):
    for frame in session.frames:
        assert not re.search(r"\[(?:PERSON|ORG|AMOUNT|ID)_\d+", json.dumps(frame, ensure_ascii=False)), frame
    for body in session.intake_bodies:
        assert "[PERSON_" not in json.dumps(body)


def test_streamed_synthesis_rehydrated_across_chunk_splits(session):
    first_draft_at = next(i for i, f in enumerate(session.frames) if f["type"] == "synthesis_draft")
    streamed = "".join(
        f["token"] for f in session.frames[:first_draft_at] if f["type"] == "synthesis_token"
    )
    for value in SENSITIVE:
        assert value in streamed


def test_research_panels_rehydrated(session):
    for sender in ("Gemini", "GPT", "Grok", "Claude"):
        text = "".join(f["token"] for f in session.frames
                       if f["type"] == "token" and f.get("sender") == sender)
        assert "Sarah Jenkins" in text, sender


def test_privacy_audit_attached_with_counts_only(session):
    final = next(f for f in session.frames if f["type"] == "synthesis_final")
    audit = final["privacy_audit"]
    assert audit["pii_tokens_redacted"] >= 4
    assert {"PERSON", "ORG", "AMOUNT", "ID"} <= set(audit["by_type"])
    assert "Sarah" not in json.dumps(audit)


def test_dialogue_turn_reuses_tokens(session):
    refinement = [t for p, t in session.rec.payloads if p == "anthropic" and "drops the" in t]
    assert refinement, "refinement payload not found"
    assert "[PERSON_1] drops the [AMOUNT_1" in refinement[-1]
    assert "[PERSON_2]" not in refinement[-1]


# ── AC6 — no map leakage, vault discarded ────────────────────────────────────

def test_token_map_never_serialized(session):
    for _, text in session.rec.payloads:
        assert "token_map" not in text and '"[PERSON_1]": ' not in text
    for frame in session.frames:
        assert "token_map" not in json.dumps(frame)


def test_vault_removed_and_cleared_after_session(session):
    assert VAULTS.get(session.session_id) is None
    assert session.vault is not None and session.vault.token_map == {}


def test_privacy_ref_given_to_client(session):
    assert session.config["privacy_ref"] == session.session_id


# ── AC2 — public terms reach Perplexity intact ───────────────────────────────

def test_public_terms_reach_perplexity():
    run = _run_session(
        "Should we move from AWS to GCP for SOC 2 and GDPR?",
        dialogue="Does SOC 2 change the answer?",
    )
    perplexity = [t for p, t in run.rec.payloads if p == "perplexity"]
    assert perplexity
    # The web-research call carries the user's question verbatim.
    research = perplexity[0]
    assert "Search the current web" in research
    assert "AWS" in research and "SOC 2" in research and "GDPR" in research
    # Nothing was tokenized anywhere. Only the conversation is checked: the
    # system prompts legitimately mention example placeholders.
    for provider, content in run.rec.contents:
        assert not re.search(r"\[(?:PERSON|ORG|AMOUNT|ID)_\d+", content), provider
    final = next(f for f in run.frames if f["type"] == "synthesis_final")
    assert final["privacy_audit"]["pii_tokens_redacted"] == 0
