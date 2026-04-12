"""
backend/main.py

FastAPI application — REST endpoints + WebSocket for ai-roundtable v2.

Endpoints:
    POST /api/intake/start      — start a new intake conversation
    POST /api/intake/respond    — send a message to the intake conductor
    POST /api/session/run       — run a full roundtable session, return all responses
    POST /api/export/markdown   — generate markdown export
    POST /api/export/drive      — deferred to v2.1

WebSocket:
    /ws/session                 — stream tokens from each model in real time (Session 6)

Session flow (default mode):
    User prompt → Claude → Gemini → GPT (sequential, full transcript each)
    → Perplexity audit (SKIPPED in v2 — returns placeholder)
    → Claude synthesis → return to frontend

Sequential in Round 1. Always. Never parallel.
"""

import asyncio
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Optional


def _load_env():
    """Load backend/.env at import time so API keys are available regardless of how the server is started."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

_load_env()

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from backend.intake import IntakeSession
from backend.transcript import Transcript
from backend.router import (
    get_tier_config, get_round1_system_prompt, build_synthesis_prompt,
    USE_CASE_LIBRARY, get_use_case,
)
from backend.models.anthropic_client import call_claude
from backend.models.google_client import call_gemini
from backend.models.openai_client import call_gpt
from backend.models.perplexity_client import audit as perplexity_audit
from backend.exporter import Exporter

app = FastAPI(title="ai-roundtable v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store — maps session_id → IntakeSession
# Sufficient for v2 (single-user, single-server). Replace with Redis for multi-user.
_intake_sessions: dict[str, IntakeSession] = {}


# ── Request / Response models ─────────────────────────────────────────────────

class IntakeRespondRequest(BaseModel):
    session_id: str
    message: str


class SessionRunRequest(BaseModel):
    prompt: str
    session_config: dict
    history: list = []  # list of {"role", "sender", "content", ...} dicts


class ExportRequest(BaseModel):
    transcript: dict       # Transcript.to_dict() output
    session_config: dict
    mode: str = "full"     # "full" | "synthesis"


# ── Use Case Library endpoints ───────────────────────────────────────────────

@app.get("/api/use-cases")
async def list_use_cases():
    """
    Return the full Use Case Library as JSON.

    Response shape:
        {
            "learning_career":  [ {id, title, description, output, typical_tier,
                                   typical_exchanges, first_question}, ... ],
            "research_decision": [...],
            "strategy_planning": [...],
            "technical_build":   [...]
        }

    16 cards total across 4 families. Fixed for v2.
    """
    return USE_CASE_LIBRARY


@app.get("/api/use-cases/{use_case_id}")
async def get_use_case_by_id(use_case_id: str):
    """
    Return a single use case card by ID.

    Includes first_question — the frontend uses this to pre-load
    the first intake message when a user selects a card.

    Raises 404 if the ID is not found.
    """
    card = get_use_case(use_case_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Use case '{use_case_id}' not found.")
    return card


# ── Intake endpoints ──────────────────────────────────────────────────────────

@app.post("/api/intake/start")
async def intake_start():
    """
    Start a new intake conversation.

    Creates an IntakeSession, calls start(), and returns the opening message
    with a session_id the frontend uses for all subsequent /intake/respond calls.

    Returns:
        { "session_id": str, "message": str }
    """
    session_id = str(uuid.uuid4())
    session = IntakeSession()
    opening = session.start()
    _intake_sessions[session_id] = session
    return {"session_id": session_id, "message": opening}


@app.post("/api/intake/respond")
async def intake_respond(req: IntakeRespondRequest):
    """
    Send a user message to the intake conductor.

    Returns Claude's next question or the completed session config.

    Returns:
        {
            "session_id": str,
            "status":     "ongoing" | "complete",
            "message":    str,
            "config":     dict | None
        }
    """
    session = _intake_sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Intake session not found.")
    if session.complete:
        raise HTTPException(status_code=400, detail="Intake session already complete.")

    result = session.respond(req.message)
    return {"session_id": req.session_id, **result}


# ── Core session loop ─────────────────────────────────────────────────────────

@app.post("/api/session/run")
async def session_run(req: SessionRunRequest):
    """
    Run a full roundtable session and return all responses.

    Accepts the user's prompt, the session_config from intake, and any
    prior transcript history (empty list for the first turn).

    Round 1 is strictly sequential:
        Claude → Gemini → GPT
    Each model receives the full transcript including all prior responses.

    Perplexity audit is skipped in v2 — returns placeholder string.

    Claude synthesis follows, incorporating all three Round 1 responses.

    Returns:
        {
            "round1": {
                "claude":  str,
                "gemini":  str,
                "gpt":     str
            },
            "audit":     str,   # "Perplexity audit coming in v2.1."
            "synthesis": str
        }

    Raises 400 if tier is invalid, 500 on any model call failure.
    """
    config = req.session_config
    tier = config.get("tier", "deep")
    output_type = config.get("output_type", "report")

    try:
        tier_config = get_tier_config(tier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Reconstruct transcript from provided history and add the new prompt
    transcript = Transcript()
    transcript.session_config = config
    for msg in req.history:
        if msg.get("role") == "user":
            transcript.add_user_message(msg["content"])
        elif msg.get("role") == "assistant":
            transcript.add_model_message(
                sender=msg.get("sender", "Unknown"),
                content=msg["content"],
                round=msg.get("round", "round1"),
            )
    transcript.add_user_message(req.prompt)

    # ── Round 1: Claude ───────────────────────────────────────────────────────
    claude_history = transcript.get_history_for_model("claude")
    claude_response = call_claude(
        messages=claude_history,
        tier=tier,
        system=get_round1_system_prompt("claude"),
    )
    claude_text = claude_response.content[0].text
    transcript.add_model_message("Claude", claude_text, round="round1")

    # ── Round 1: Gemini ───────────────────────────────────────────────────────
    # Gemini now has Claude's response in its history
    gemini_history = transcript.get_history_for_model("gemini")
    gemini_response = call_gemini(
        messages=gemini_history,
        tier=tier,
        system=get_round1_system_prompt("gemini"),
    )
    gemini_text = gemini_response.text
    transcript.add_model_message("Gemini", gemini_text, round="round1")

    # ── Round 1: GPT ──────────────────────────────────────────────────────────
    # GPT now has Claude's and Gemini's responses in its history
    gpt_history = transcript.get_history_for_model("gpt")
    gpt_response = call_gpt(
        messages=gpt_history,
        tier=tier,
        system=get_round1_system_prompt("gpt"),
    )
    gpt_text = gpt_response.choices[0].message.content
    transcript.add_model_message("GPT", gpt_text, round="round1")

    # ── Perplexity audit (v2.1 stub) ──────────────────────────────────────────
    audit_text = perplexity_audit(transcript.get_round1_responses(), tier=tier)
    transcript.add_model_message("Perplexity", audit_text, round="audit")

    # ── Synthesis: Claude ─────────────────────────────────────────────────────
    # Claude receives the full transcript (all three Round 1 responses + audit)
    # plus the synthesis system prompt scoped to the declared output_type.
    synthesis_history = transcript.get_history_for_model("claude")
    synthesis_prompt = build_synthesis_prompt(output_type)
    synthesis_response = call_claude(
        messages=synthesis_history,
        tier=tier,
        system=synthesis_prompt,
    )
    synthesis_text = synthesis_response.content[0].text
    transcript.add_model_message("Claude", synthesis_text, round="synthesis")

    return {
        "round1": {
            "claude": claude_text,
            "gemini": gemini_text,
            "gpt":    gpt_text,
        },
        "audit":     audit_text,
        "synthesis": synthesis_text,
    }


# ── Export endpoints ──────────────────────────────────────────────────────────

@app.post("/api/export/markdown")
async def export_markdown(req: ExportRequest):
    """
    Generate a markdown export for a completed session.

    Accepts mode "full" (entire session) or "synthesis" (synthesis section only).
    Returns the markdown as a downloadable .md file.
    """
    from datetime import datetime
    transcript = Transcript()
    transcript.session_config = req.session_config
    transcript.intake_summary = req.transcript.get("intake_summary")
    for msg in req.transcript.get("messages", []):
        if msg.get("role") == "user":
            transcript.add_user_message(msg["content"])
        else:
            transcript.add_model_message(
                sender=msg.get("sender", "Unknown"),
                content=msg["content"],
                round=msg.get("round", "round1"),
            )

    exporter = Exporter()
    markdown = exporter.to_markdown(transcript, req.session_config, mode=req.mode)
    date_slug = datetime.now().strftime("%Y-%m-%d")
    filename = f"ai-roundtable-{date_slug}.md"

    return Response(
        content=markdown.encode("utf-8"),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/export/drive")
async def export_drive():
    """Google Drive export — deferred to v2.1."""
    raise HTTPException(status_code=501, detail="Google Drive export coming in v2.1.")


# ── WebSocket streaming ───────────────────────────────────────────────────────

def _build_transcript(config: dict, history: list, prompt: str) -> Transcript:
    """Reconstruct a Transcript from prior history and append the new user prompt."""
    transcript = Transcript()
    transcript.session_config = config
    for msg in history:
        if msg.get("role") == "user":
            transcript.add_user_message(msg["content"])
        elif msg.get("role") == "assistant":
            transcript.add_model_message(
                sender=msg.get("sender", "Unknown"),
                content=msg["content"],
                round=msg.get("round", "round1"),
            )
    transcript.add_user_message(prompt)
    return transcript


async def _stream_tokens(
    websocket: WebSocket,
    sender: str,
    sync_iter_factory,       # zero-arg callable that returns a sync token iterator
) -> str:
    """
    Run a synchronous streaming iterator in a thread and forward each token
    to the WebSocket as a {"type": "token", "sender": ..., "token": ...} message.

    Returns the full accumulated response text.

    Uses asyncio.Queue + loop.call_soon_threadsafe to bridge the sync iterator
    into the async WebSocket handler without blocking the event loop.
    """
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()  # sentinel

    def _run():
        try:
            for token in sync_iter_factory():
                if token:
                    loop.call_soon_threadsafe(queue.put_nowait, token)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, {"__error__": str(e)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    threading.Thread(target=_run, daemon=True).start()

    full_text = ""
    while True:
        item = await queue.get()
        if item is _DONE:
            break
        if isinstance(item, dict) and "__error__" in item:
            raise RuntimeError(f"{sender} stream error: {item['__error__']}")
        full_text += item
        await websocket.send_json({"type": "token", "sender": sender, "token": item})

    return full_text


def _claude_token_iter(messages, tier, system):
    """Yield text tokens from a streaming Claude response."""
    with call_claude(messages=messages, tier=tier, system=system, stream=True) as stream:
        yield from stream.text_stream


def _gemini_token_iter(messages, tier, system):
    """Yield text tokens from a streaming Gemini response."""
    for chunk in call_gemini(messages=messages, tier=tier, system=system, stream=True):
        if chunk.text:
            yield chunk.text


def _gpt_token_iter(messages, tier, system):
    """Yield text tokens from a streaming GPT response."""
    for chunk in call_gpt(messages=messages, tier=tier, system=system, stream=True):
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


@app.websocket("/ws/session")
async def session_websocket(websocket: WebSocket):
    """
    Stream a full roundtable session token-by-token.

    Handshake:
        Client connects, then immediately sends:
        {
            "prompt":         str,
            "session_config": dict,   # from IntakeSession.session_config
            "history":        list    # [] for first turn
        }

    Messages emitted (in order):
        { "type": "token",              "sender": "Claude"|"Gemini"|"GPT", "token": str }
        { "type": "model_complete",     "sender": "Claude"|"Gemini"|"GPT" }
        { "type": "synthesis_complete", "content": str }   # full synthesis text
        { "type": "session_complete" }
        { "type": "error",              "message": str }   # on failure

    Round 1 is sequential — Claude → Gemini → GPT. Never parallel.
    Perplexity audit is a placeholder in v2 (deferred to v2.1).
    """
    await websocket.accept()

    try:
        data = await websocket.receive_json()
    except Exception:
        await websocket.send_json({"type": "error", "message": "Invalid handshake — expected JSON with prompt and session_config."})
        await websocket.close()
        return

    prompt = data.get("prompt", "")
    config = data.get("session_config", {})
    history = data.get("history", [])
    tier = config.get("tier", "deep")
    output_type = config.get("output_type", "report")

    try:
        get_tier_config(tier)  # validate — raises ValueError on bad tier
    except ValueError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close()
        return

    transcript = _build_transcript(config, history, prompt)

    try:
        # ── Round 1: Claude ───────────────────────────────────────────────────
        claude_history = transcript.get_history_for_model("claude")
        claude_system = get_round1_system_prompt("claude")
        claude_text = await _stream_tokens(
            websocket, "Claude",
            lambda: _claude_token_iter(claude_history, tier, claude_system),
        )
        transcript.add_model_message("Claude", claude_text, round="round1")
        await websocket.send_json({"type": "model_complete", "sender": "Claude"})

        # ── Round 1: Gemini ───────────────────────────────────────────────────
        # Gemini now has Claude's response in its history
        gemini_history = transcript.get_history_for_model("gemini")
        gemini_system = get_round1_system_prompt("gemini")
        gemini_text = await _stream_tokens(
            websocket, "Gemini",
            lambda: _gemini_token_iter(gemini_history, tier, gemini_system),
        )
        transcript.add_model_message("Gemini", gemini_text, round="round1")
        await websocket.send_json({"type": "model_complete", "sender": "Gemini"})

        # ── Round 1: GPT ──────────────────────────────────────────────────────
        # GPT now has Claude's and Gemini's responses in its history
        gpt_history = transcript.get_history_for_model("gpt")
        gpt_system = get_round1_system_prompt("gpt")
        gpt_text = await _stream_tokens(
            websocket, "GPT",
            lambda: _gpt_token_iter(gpt_history, tier, gpt_system),
        )
        transcript.add_model_message("GPT", gpt_text, round="round1")
        await websocket.send_json({"type": "model_complete", "sender": "GPT"})

        # ── Perplexity audit (v2.1 stub) ──────────────────────────────────────
        audit_text = perplexity_audit(transcript.get_round1_responses(), tier=tier)
        transcript.add_model_message("Perplexity", audit_text, round="audit")

        # ── Synthesis: Claude ─────────────────────────────────────────────────
        # Full transcript now includes all three Round 1 responses + audit placeholder
        synthesis_history = transcript.get_history_for_model("claude")
        synthesis_system = build_synthesis_prompt(output_type)
        synthesis_text = await _stream_tokens(
            websocket, "Claude",
            lambda: _claude_token_iter(synthesis_history, tier, synthesis_system),
        )
        transcript.add_model_message("Claude", synthesis_text, round="synthesis")
        await websocket.send_json({"type": "synthesis_complete", "content": synthesis_text})

        await websocket.send_json({"type": "session_complete"})

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()
