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
    Gemini + GPT + Perplexity pre-research run IN PARALLEL
    → Perplexity audit (uses pre-research + Gemini + GPT responses)
    → Claude synthesises everything → final deliverable

    Claude does NOT respond in Round 1. Claude only synthesises at the end.
    Gemini and GPT stream tokens to the frontend simultaneously (serialised sends).
"""

import asyncio
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional


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

from anthropic import APIStatusError as AnthropicAPIStatusError
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect

from backend.intake import IntakeSession, OPENING_SUGGESTED_OPTIONS
from backend.transcript import Transcript
from backend.router import (
    get_tier_config,
    get_round1_system_prompt,
    build_synthesis_prompt,
    USE_CASE_LIBRARY,
    get_use_case,
)
from backend.models.anthropic_client import (
    call_claude,
    call_claude_smart,
    call_claude_smart_async,
)
from backend.models.google_client import (
    call_gemini,
    call_gemini_smart,
    call_gemini_smart_async,
)
from backend.models.openai_client import call_gpt, call_gpt_smart, call_gpt_smart_async
from backend.models.perplexity_client import (
    research as perplexity_research,
    audit as perplexity_audit,
)
from backend.exporter import Exporter

app = FastAPI(title="ai-roundtable v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store — sufficient for v2. Replace with Redis for multi-user.
_intake_sessions: dict[str, IntakeSession] = {}


# ── Request / Response models ─────────────────────────────────────────────────

class IntakeRespondRequest(BaseModel):
    session_id: str
    message: str


class IntakeRefineRequest(BaseModel):
    session_id: str
    message: Optional[str] = None  # legacy: same as user_feedback or probe_answer
    current_prompt: Optional[str] = None
    user_feedback: Optional[str] = None
    probe_answer: Optional[str] = None


class IntakeRefineCancelRequest(BaseModel):
    session_id: str


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
    return {
        "session_id": session_id,
        "message": opening,
        "suggested_options": list(OPENING_SUGGESTED_OPTIONS),
    }


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
            "config":     dict | None,
            "suggested_options": list[str] | None,  # 2–4 chips when Claude included intake-ui
        }
    """
    session = _intake_sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Intake session not found.")

    try:
        result = session.respond(req.message)
    except AnthropicAPIStatusError as e:
        if e.status_code == 529:
            raise HTTPException(status_code=503, detail="Claude is temporarily overloaded — please wait a moment and try again.")
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {e.message}")
    return {"session_id": req.session_id, **result}


# ── Prompt refinement (post-intake) ───────────────────────────────────────────

@app.post("/api/intake/refine")
async def intake_refine(req: IntakeRefineRequest):
    """
    Refine the optimized prompt after intake completes.

    First ``message`` starts a probe (``status``: ``probing``). The next message
    completes the rewrite (``status``: ``refined``) and returns the full
    ``session_config`` with an updated ``optimized_prompt``.
    """
    session = _intake_sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Intake session not found.")
    if not session.complete or not session.session_config:
        raise HTTPException(status_code=400, detail="Complete intake before refining the prompt.")
    pa = (req.probe_answer or "").strip() if req.probe_answer else ""
    fb = (req.user_feedback or "").strip() if req.user_feedback else ""
    legacy = (req.message or "").strip() if req.message else ""
    if pa:
        payload = pa
    elif fb:
        payload = fb
    elif legacy:
        payload = legacy
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide probe_answer, user_feedback, or message.",
        )
    cp = (req.current_prompt or "").strip() if req.current_prompt else None
    try:
        result = await asyncio.to_thread(session.refine, payload, cp)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"session_id": req.session_id, **result}


@app.post("/api/intake/refine/cancel")
async def intake_refine_cancel(req: IntakeRefineCancelRequest):
    """Drop an in-progress refine so a new cycle can start from a clean state."""
    session = _intake_sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Intake session not found.")
    session.clear_refine()
    return {"session_id": req.session_id, "ok": True}


# ── Core session loop ─────────────────────────────────────────────────────────

@app.post("/api/session/run")
async def session_run(req: SessionRunRequest):
    """
    Run a full roundtable session and return all responses.

    Accepts the user's prompt, the session_config from intake, and any
    prior transcript history (empty list for the first turn).

    Gemini, GPT, and Perplexity Phase 1 pre-research run in parallel; transcript
    records Gemini then GPT. Perplexity Phase 2 audits Gemini + GPT. Claude
    synthesises only (no Round 1 Claude response).

    Returns:
        {
            "round1":    {"gemini": str, "gpt": str},
            "research":  str,   # Perplexity Phase 1 pre-research
            "audit":     str,   # Perplexity Phase 2 audit
            "synthesis": str
        }

    Gemini, GPT, and Perplexity pre-research run in parallel.
    Claude does NOT participate in Round 1 — synthesises only.
    Each skipped provider is noted; session continues regardless.
    Raises 400 if tier is invalid.
    """
    config = req.session_config
    tier = config.get("tier", "smart"); print(f"[SESSION] tier={tier}", flush=True)
    output_type = config.get("output_type", "report")
    optimized_prompt = config.get("optimized_prompt", req.prompt)

    try:
        tier_config = get_tier_config(tier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    mode = tier_config.get("mode", "single")

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

    def _skip(sender: str, exc: Exception) -> str:
        return f"[{sender} unavailable — skipped after retries: {exc}]"

    gemini_history = transcript.get_history_for_model("gemini")
    gpt_history    = transcript.get_history_for_model("gpt")
    gemini_system  = get_round1_system_prompt("gemini")
    gpt_system     = get_round1_system_prompt("gpt")

    # ── Parallel: Gemini + GPT + Perplexity pre-research ─────────────────────
    if mode == "smart":
        async def _gemini_task() -> str:
            try:
                result = await _call_with_retry_async(
                    lambda: call_gemini_smart_async(gemini_history, gemini_system),
                    "Gemini-smart",
                )
                return result["advisor_text"]
            except Exception as exc:
                return _skip("Gemini", exc)

        async def _gpt_task() -> str:
            try:
                result = await _call_with_retry_async(
                    lambda: call_gpt_smart_async(gpt_history, gpt_system),
                    "GPT-smart",
                )
                return result["advisor_text"]
            except Exception as exc:
                return _skip("GPT", exc)
    else:
        async def _gemini_task() -> str:
            try:
                r = await asyncio.to_thread(
                    _call_with_retry,
                    lambda: call_gemini(messages=gemini_history, tier=tier, system=gemini_system),
                    "Gemini",
                )
                return r.text
            except Exception as exc:
                return _skip("Gemini", exc)

        async def _gpt_task() -> str:
            try:
                r = await asyncio.to_thread(
                    _call_with_retry,
                    lambda: call_gpt(messages=gpt_history, tier=tier, system=gpt_system),
                    "GPT",
                )
                return r.choices[0].message.content
            except Exception as exc:
                return _skip("GPT", exc)

    async def _research_task() -> str:
        try:
            return await asyncio.to_thread(
                _call_with_retry,
                lambda: perplexity_research(optimized_prompt, tier=tier),
                "Perplexity-research",
            )
        except Exception as exc:
            return f"[Perplexity pre-research unavailable: {exc}]"

    gemini_text, gpt_text, perplexity_pre = await asyncio.gather(
        _gemini_task(), _gpt_task(), _research_task(),
    )

    transcript.add_model_message("Gemini", gemini_text, round="round1")
    transcript.add_model_message("GPT",    gpt_text,    round="round1")

    # ── Perplexity audit (Phase 2) ────────────────────────────────────────────
    try:
        audit_text = await asyncio.to_thread(
            _call_with_retry,
            lambda: perplexity_audit(
                {"gemini": gemini_text, "gpt": gpt_text},
                research_text=perplexity_pre,
                tier=tier,
            ),
            "Perplexity-audit",
        )
    except Exception as exc:
        audit_text = f"[Perplexity audit unavailable: {exc}]"
    transcript.add_model_message("Perplexity", audit_text, round="audit")

    # ── Synthesis: Claude (smart: executor → advisor; else: single call) ──────
    synthesis_system = build_synthesis_prompt(
        output_type=output_type,
        gemini=gemini_text,
        gpt=gpt_text,
        perplexity=audit_text,
        optimized_prompt=optimized_prompt,
    )
    if mode == "smart":
        result = await _call_with_retry_async(
            lambda: call_claude_smart_async(
                [{"role": "user", "content": req.prompt}],
                synthesis_system,
            ),
            "Claude-smart",
        )
        synthesis_text = result["advisor_text"]
    else:
        synthesis_response = call_claude(
            messages=[{"role": "user", "content": req.prompt}],
            tier=tier,
            system=synthesis_system,
        )
        synthesis_text = synthesis_response.content[0].text
    transcript.add_model_message("Claude", synthesis_text, round="synthesis")

    return {
        "round1": {
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
    sync_iter_factory,                          # zero-arg callable → sync token iterator
    send_lock: Optional[asyncio.Lock] = None,   # shared lock for parallel streams
) -> str:
    """
    Run a synchronous streaming iterator in a thread and forward each token
    to the WebSocket as a {"type": "token", "sender": ..., "token": ...} message.

    Returns the full accumulated response text.

    send_lock — when two streams run concurrently (asyncio.gather), pass a shared
    asyncio.Lock so WebSocket sends are serialised and frames are not interleaved.
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
        msg = {"type": "token", "sender": sender, "token": item}
        if send_lock:
            async with send_lock:
                await websocket.send_json(msg)
        else:
            await websocket.send_json(msg)

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


# ── Smart tier advisor helpers ────────────────────────────────────────────────
#
# These run AFTER the executor has already streamed its tokens to the frontend.
# Each helper calls the advisor model (pro/opus/gpt-5) with the executor's output
# and returns the improved final text.  Called via asyncio.to_thread in the WS handler.

_ADVISOR_PROMPT = (
    "Review this response and produce an improved final version.\n\n"
    "Original request: {request}\n"
    "Response to review: {response}\n\n"
    "Identify gaps, weak reasoning, missing considerations. "
    "Output only the improved response — no preamble, no explanation."
)


def _gemini_advisor(executor_text: str, request: str) -> str:
    resp = call_gemini(
        messages=[{"role": "user", "content": _ADVISOR_PROMPT.format(request=request, response=executor_text)}],
        tier="deep",  # gemini-2.5-pro
    )
    return resp.text


def _gpt_advisor(executor_text: str, request: str) -> str:
    resp = call_gpt(
        messages=[{"role": "user", "content": _ADVISOR_PROMPT.format(request=request, response=executor_text)}],
        tier="deep",  # gpt-5 (or fallback to gpt-4o via call_gpt)
    )
    return resp.choices[0].message.content


def _claude_advisor(executor_text: str, request: str) -> str:
    resp = call_claude(
        messages=[{"role": "user", "content": _ADVISOR_PROMPT.format(request=request, response=executor_text)}],
        tier="deep",  # claude-opus-4-5
    )
    return resp.content[0].text


# ── Retry helpers ─────────────────────────────────────────────────────────────

# Delay sequence for up to 3 retries: 5s → 10s → 20s
_RETRY_DELAYS = [5, 10, 20]


def _is_retryable(exc: Exception) -> bool:
    """Return True for transient 503 / 429 / rate-limit errors from any provider."""
    msg = str(exc).lower()
    return any(k in msg for k in (
        "503", "429", "rate limit", "rate_limit",
        "unavailable", "overloaded", "too many requests",
    ))


def _retrying_iter(inner_factory, sender: str):
    """
    Wrap a sync token-iterator factory with retry-on-transient-error logic.

    Retries up to 3 times (5s → 10s → 20s) when the iterator raises a
    retryable error (503 / 429 / rate-limit) AND no tokens have been yielded
    yet.  Once tokens are flowing, retrying would send duplicates to the
    frontend — so mid-stream errors are always re-raised immediately.
    Non-retryable errors are re-raised on the first attempt.
    """
    last_exc = None
    for attempt in range(len(_RETRY_DELAYS) + 1):
        if attempt > 0:
            delay = _RETRY_DELAYS[attempt - 1]
            print(f"[retry] {sender}: attempt {attempt}/{len(_RETRY_DELAYS)}, waiting {delay}s — {last_exc}")
            time.sleep(delay)
        started = False
        try:
            for token in inner_factory():
                started = True
                yield token
            return  # clean completion
        except Exception as e:
            if not _is_retryable(e) or started:
                raise  # non-retryable or mid-stream — do not retry
            last_exc = e
    raise last_exc  # all retries exhausted


def _call_with_retry(fn, sender: str):
    """
    Call fn() with up to 3 retries on retryable errors (503 / 429 / rate-limit).
    Delays: 5s → 10s → 20s.  Raises the last exception if all retries fail.
    Used by the non-streaming REST endpoint.
    """
    last_exc = None
    for attempt in range(len(_RETRY_DELAYS) + 1):
        if attempt > 0:
            delay = _RETRY_DELAYS[attempt - 1]
            print(f"[retry] {sender}: attempt {attempt}/{len(_RETRY_DELAYS)}, waiting {delay}s — {last_exc}")
            time.sleep(delay)
        try:
            return fn()
        except Exception as e:
            if not _is_retryable(e):
                raise
            last_exc = e
    raise last_exc


async def _call_with_retry_async(coro_factory, sender: str):
    """
    Await coro_factory() with up to 3 retries on retryable errors (503 / 429 / rate-limit).
    Same backoff as _call_with_retry but without blocking the event loop on sleep.
    """
    last_exc = None
    for attempt in range(len(_RETRY_DELAYS) + 1):
        if attempt > 0:
            delay = _RETRY_DELAYS[attempt - 1]
            print(f"[retry] {sender}: attempt {attempt}/{len(_RETRY_DELAYS)}, waiting {delay}s — {last_exc}")
            await asyncio.sleep(delay)
        try:
            coro = coro_factory()
            return await coro
        except Exception as e:
            if not _is_retryable(e):
                raise
            last_exc = e
    raise last_exc


async def _stream_model(
    websocket: WebSocket,
    sender: str,
    iter_factory,
    transcript: Optional["Transcript"] = None,
    send_lock: Optional[asyncio.Lock] = None,
    *,
    commit_to_transcript: bool = True,
) -> str:
    """
    Stream one Round 1 model response with retry + graceful skip.

    Wraps _stream_tokens with _retrying_iter so transient errors trigger
    automatic backoff retries.  If all retries are exhausted the model is
    skipped: an error frame is sent to the frontend, a skip note is added to
    the transcript, and the session continues with the remaining models.

    send_lock — pass a shared asyncio.Lock when running multiple models in
    parallel via asyncio.gather() to serialise WebSocket sends.

    Always sends model_complete before returning.
    Returns the accumulated response text (or skip-note string on failure).
    """
    async def _send(msg: dict) -> None:
        if send_lock:
            async with send_lock:
                await websocket.send_json(msg)
        else:
            await websocket.send_json(msg)

    try:
        text = await _stream_tokens(
            websocket, sender,
            lambda: _retrying_iter(iter_factory, sender),
            send_lock=send_lock,
        )
    except RuntimeError as exc:
        text = f"[{sender} unavailable — skipped after retries]"
        await _send({
            "type": "error",
            "message": f"{sender} unavailable after retries — continuing session without it.",
        })
    if commit_to_transcript and transcript is not None:
        transcript.add_model_message(sender, text, round="round1")
    await _send({"type": "model_complete", "sender": sender})
    return text


async def _drain_client_pings(websocket: WebSocket) -> None:
    """
    Read client JSON while the session runs; answer keep-alive pings so inbound
    frames are not mistaken for session payloads.
    """
    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        raise
    except Exception:
        return


async def _generate_observations(
    prompt: str,
    gemini: str,
    gpt: str,
    perplexity: str,
    tier: str,
) -> list:
    """
    Ask Claude to identify 3–5 key observations from the Round 1 responses.

    Returns a list of observation strings ready to surface to the chair.
    Falls back to [] on any error so the session continues straight to synthesis.
    Each observation is already phrased to inform a keep/overrule decision.
    """
    system = (
        "You are analyzing two AI model responses to identify key observations for synthesis. "
        "Respond ONLY with valid JSON in this exact format with no other text:\n"
        "{\"observations\": [\"...\", \"...\"]}\n\n"
        "Each observation must be a single self-contained sentence that:\n"
        "- States what Gemini and/or GPT said (a point of agreement, disagreement, or key decision)\n"
        "- States what you intend to do in the final synthesis\n"
        "- Ends with: 'Do you want to keep this, or overrule?'\n"
        "Identify exactly 3 to 5 observations. No preamble, no markdown, only the JSON object."
    )
    obs_prompt = (
        f"User's request: {prompt}\n\n"
        f"Gemini's response:\n{gemini[:2500]}\n\n"
        f"GPT's response:\n{gpt[:2500]}\n\n"
        f"Perplexity fact-check:\n{perplexity[:1000]}"
    )
    try:
        resp = await asyncio.to_thread(
            call_claude,
            messages=[{"role": "user", "content": obs_prompt}],
            tier="quick",
            system=system,
        )
        raw = resp.content[0].text.strip()
        # Strip markdown fences if Claude wrapped the JSON
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
        data = json.loads(raw)
        obs = data.get("observations", [])
        if isinstance(obs, list) and obs:
            return [str(o).strip() for o in obs[:5] if str(o).strip()]
    except Exception as exc:
        print(f"[observations] skipping chair dialogue: {exc}", flush=True)
    return []


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
        Any number of {"type": "ping", ...} messages may precede the handshake; each is
        answered with {"type": "pong"}. During streaming, pings are handled in parallel.

    Messages emitted (in order):
        {"type": "session_started"}
        {"type": "token",              "sender": "Gemini"|"GPT", "token": str}  # parallel
        {"type": "model_complete",     "sender": "Gemini"}
        {"type": "model_complete",     "sender": "GPT"}
        {"type": "advisor_thinking",   "sender": "Gemini"|"GPT"}   # optional Smart tier
        {"type": "advisor_complete",   "sender": "Gemini"|"GPT"}
        {"type": "error",              "message": str}   # skipped model (non-fatal)
        {"type": "perplexity_thinking"}
        {"type": "perplexity_complete", "content": str}
        {"type": "synthesis_thinking"}
        {"type": "token",              "sender": "Claude", "token": str}
        {"type": "synthesis_complete", "content": str}
        {"type": "session_complete"}
        {"type": "error",              "message": str}   # fatal session error

    Gemini and GPT stream simultaneously (asyncio.gather + shared send_lock).
    Perplexity pre-research runs silently in the same gather.
    Claude does NOT respond in Round 1 — synthesises only.
    Each provider retries up to 3× (5s/10s/20s) on 503/429.
    """
    await websocket.accept()

    while True:
        try:
            data = await websocket.receive_json()
        except WebSocketDisconnect:
            await websocket.close()
            return
        except Exception:
            await websocket.send_json({"type": "error", "message": "Invalid handshake — expected JSON with prompt and session_config."})
            await websocket.close()
            return
        if isinstance(data, dict) and data.get("type") == "ping":
            await websocket.send_json({"type": "pong"})
            continue
        break

    prompt = data.get("prompt", "")
    config = data.get("session_config", {})
    history = data.get("history", [])
    tier = config.get("tier", "smart"); print(f"[SESSION] tier={tier}", flush=True)
    output_type = config.get("output_type", "report")

    try:
        tier_config = get_tier_config(tier)
    except ValueError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close()
        return

    mode = tier_config.get("mode", "single")
    optimized_prompt = config.get("optimized_prompt", prompt)
    transcript = _build_transcript(config, history, prompt)

    ping_task = asyncio.create_task(_drain_client_pings(websocket))
    try:
        await websocket.send_json({"type": "session_started"})

        # ── Round 1 + Perplexity pre-research ───────────────────────────────────
        # quick/deep: stream Gemini + GPT in parallel. smart: async smart clients
        # (executor + advisor) off the event loop, then chunk-emit advisor text.
        gemini_history = transcript.get_history_for_model("gemini")
        gpt_history    = transcript.get_history_for_model("gpt")
        gemini_system  = get_round1_system_prompt("gemini")
        gpt_system     = get_round1_system_prompt("gpt")
        send_lock      = asyncio.Lock()

        async def _research_task() -> str:
            try:
                return await asyncio.to_thread(
                    _call_with_retry,
                    lambda: perplexity_research(optimized_prompt, tier=tier),
                    "Perplexity-research",
                )
            except Exception as exc:
                return f"[Perplexity pre-research unavailable: {exc}]"

        def _smart_round1_body(res, sender_name: str) -> str:
            if isinstance(res, Exception):
                return f"[{sender_name} unavailable — skipped after retries: {res}]"
            if isinstance(res, dict) and res.get("advisor_text") is not None:
                return str(res["advisor_text"])
            return f"[{sender_name} unavailable]"

        if mode == "smart":
            r1_results = await asyncio.gather(
                _research_task(),
                _call_with_retry_async(
                    lambda: call_gemini_smart_async(gemini_history, gemini_system),
                    "Gemini-smart",
                ),
                _call_with_retry_async(
                    lambda: call_gpt_smart_async(gpt_history, gpt_system),
                    "GPT-smart",
                ),
                return_exceptions=True,
            )
            perplexity_pre = r1_results[0] if isinstance(r1_results[0], str) else ""
            gem_res = r1_results[1]
            gpt_res = r1_results[2]
            gemini_text_body = _smart_round1_body(gem_res, "Gemini")
            gpt_text_body = _smart_round1_body(gpt_res, "GPT")

            async def _emit_model_tokens(sender: str, text: str) -> None:
                body = text or ""
                step = 48
                for i in range(0, len(body), step):
                    piece = body[i : i + step]
                    async with send_lock:
                        await websocket.send_json({"type": "token", "sender": sender, "token": piece})
                async with send_lock:
                    await websocket.send_json({"type": "model_complete", "sender": sender})

            await asyncio.gather(
                _emit_model_tokens("Gemini", gemini_text_body),
                _emit_model_tokens("GPT", gpt_text_body),
            )
            gemini_text = gemini_text_body
            gpt_text = gpt_text_body
        else:
            results = await asyncio.gather(
                _stream_model(
                    websocket, "Gemini",
                    lambda: _gemini_token_iter(gemini_history, tier, gemini_system),
                    transcript=None,
                    send_lock=send_lock,
                    commit_to_transcript=False,
                ),
                _stream_model(
                    websocket, "GPT",
                    lambda: _gpt_token_iter(gpt_history, tier, gpt_system),
                    transcript=None,
                    send_lock=send_lock,
                    commit_to_transcript=False,
                ),
                _research_task(),
                return_exceptions=True,
            )
            gemini_exec = results[0] if isinstance(results[0], str) else f"[Gemini error: {results[0]}]"
            gpt_exec = results[1] if isinstance(results[1], str) else f"[GPT error: {results[1]}]"
            perplexity_pre = results[2] if isinstance(results[2], str) else ""
            gemini_text = gemini_exec
            gpt_text = gpt_exec

        transcript.add_model_message("Gemini", gemini_text, round="round1")
        transcript.add_model_message("GPT",    gpt_text,    round="round1")

        # ── Perplexity audit (Phase 2) ────────────────────────────────────────
        await websocket.send_json({"type": "perplexity_thinking"})
        try:
            audit_text = await asyncio.to_thread(
                _call_with_retry,
                lambda: perplexity_audit(
                    {"gemini": gemini_text, "gpt": gpt_text},
                    research_text=perplexity_pre,
                    tier=tier,
                ),
                "Perplexity-audit",
            )
        except Exception as exc:
            audit_text = f"[Perplexity audit unavailable: {exc}]"
        transcript.add_model_message("Perplexity", audit_text, round="audit")
        await websocket.send_json({"type": "perplexity_complete", "content": audit_text})

        # ── Chair dialogue — surface observations one at a time ───────────────
        # Generate 3–5 observations; skip silently on any error.
        observations = await _generate_observations(
            prompt=optimized_prompt,
            gemini=gemini_text,
            gpt=gpt_text,
            perplexity=audit_text,
            tier=tier,
        )
        chair_decisions: list = []

        if observations:
            # Pause the ping drain so we can receive chair_decision messages here.
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass

            for idx, obs_text in enumerate(observations):
                await websocket.send_json({
                    "type": "synthesis_observation",
                    "observation_text": obs_text,
                    "observation_index": idx + 1,
                    "total_observations": len(observations),
                })
                # Await chair decision; handle keep-alive pings inline.
                while True:
                    try:
                        msg = await websocket.receive_json()
                    except Exception:
                        break  # disconnected — bail out of dialogue
                    if isinstance(msg, dict) and msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                        continue
                    if isinstance(msg, dict) and msg.get("type") == "chair_decision":
                        chair_decisions.append(msg)
                        break
                    # Ignore any other client frames.

        # ── Synthesis: Claude executor → (smart) advisor ─────────────────────
        await websocket.send_json({"type": "synthesis_thinking"})
        synthesis_system = build_synthesis_prompt(
            output_type=output_type,
            gemini=gemini_text,
            gpt=gpt_text,
            perplexity=audit_text,
            optimized_prompt=optimized_prompt,
        )
        # Incorporate any chair overrules into the synthesis prompt.
        overrules = [
            d for d in chair_decisions
            if d.get("decision") == "overrule" and str(d.get("overrule_text", "")).strip()
        ]
        if overrules:
            synthesis_system += "\n\n## Chair Decisions — incorporate exactly\n"
            for i, d in enumerate(overrules, 1):
                synthesis_system += f"\n{i}. {str(d['overrule_text']).strip()}"
        if mode == "smart":
            try:
                pack = await _call_with_retry_async(
                    lambda: call_claude_smart_async(
                        [{"role": "user", "content": prompt}],
                        synthesis_system,
                    ),
                    "Claude-smart",
                )
                synthesis_text = str(pack.get("advisor_text", ""))
            except Exception:
                synthesis_text = ""
            step = 48
            for i in range(0, len(synthesis_text), step):
                piece = synthesis_text[i : i + step]
                async with send_lock:
                    await websocket.send_json({"type": "token", "sender": "Claude", "token": piece})
        else:
            synthesis_text = await _stream_tokens(
                websocket, "Claude",
                lambda: _claude_token_iter(
                    [{"role": "user", "content": prompt}], tier, synthesis_system
                ),
                send_lock=send_lock,
            )

        transcript.add_model_message("Claude", synthesis_text, round="synthesis")
        await websocket.send_json({"type": "synthesis_complete", "content": synthesis_text})
        await websocket.send_json({"type": "session_complete"})

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
        await websocket.close()
