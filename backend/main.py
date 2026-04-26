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
    Gemini + GPT + Grok + Claude + Perplexity pre-research run IN PARALLEL
    → Perplexity audit (uses pre-research + Gemini + GPT + Grok responses)
    → Claude synthesises everything → final deliverable

    Claude participates in Round 1 as a research seat AND synthesises at the end.
    All four models stream tokens to the frontend simultaneously (serialised sends).
"""

import asyncio
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from starlette.websockets import WebSocketDisconnect

from backend.intake import INTAKE_OPENING_MESSAGE, IntakeSession
from backend.transcript import Transcript
from backend.router import (
    get_tier_config,
    get_round1_system_prompt,
    build_synthesis_prompt,
    build_synthesis_system,
    call_synthesis_refinement,
    call_self_critique,
    parse_closing_questions,
    select_synthesis_model,
    perplexity_contradicts_round1,
    USE_CASE_LIBRARY,
    get_use_case,
)
from backend.models.anthropic_client import (
    call_claude,
    call_claude_smart,
    call_claude_smart_async,
    call_research_claude_async,
)
from backend.models.google_client import (
    call_gemini,
    call_gemini_smart,
    call_gemini_smart_async,
    call_research_gemini_async,
)
from backend.models.openai_client import (
    call_gpt, call_gpt_smart, call_gpt_smart_async, call_research_gpt_async,
)
from backend.models.grok_client import (
    call_grok, call_grok_smart, call_grok_smart_async, call_research_grok_async,
)
from backend.models.perplexity_client import (
    research as perplexity_research,
    audit_with_fallback,
)
from backend.models.pipeline_health import PipelineHealth
from backend.models.model_config import SYNTHESIS_FALLBACK
from backend.exporter import Exporter
from backend.models.model_validator import validate_model_config

app = FastAPI(title="ai-roundtable v2")

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001"
).split(",")

FRONTEND_URL = os.getenv("FRONTEND_URL", "")
if FRONTEND_URL:
    ALLOWED_ORIGINS.append(FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Validate model config on startup. Logs warnings, never crashes."""
    import asyncio
    loop = asyncio.get_event_loop()
    warnings = await loop.run_in_executor(None, validate_model_config)
    if warnings:
        print(f"⚠️  {len(warnings)} stale model ID(s) — run: python -m tools.check_models")


# In-memory session store — sufficient for v2. Replace with Redis for multi-user.
_intake_sessions: dict[str, IntakeSession] = {}


# ── Request / Response models ─────────────────────────────────────────────────

class IntakeStartRequest(BaseModel):
    prompt: str

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("prompt must not be empty")
        return v


class IntakeRespondRequest(BaseModel):
    session_id: str
    answer: str


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


@app.get("/api/model-info")
async def get_model_info():
    """
    Return current model IDs for all labs at smart and deep tiers.

    Used by IntakeFlow to render the expandable model breakdown below the
    Smart/Deep slider — so the UI always reflects model_config.py constants
    without hardcoding model names in JSX.
    """
    from backend.models.model_config import (
        RESEARCH_CLAUDE_SMART_EXECUTOR,
        RESEARCH_CLAUDE_SMART_ADVISOR,
        RESEARCH_CLAUDE_DEEP,
        RESEARCH_GEMINI_SMART_EXECUTOR,
        RESEARCH_GEMINI_SMART_ADVISOR,
        RESEARCH_GEMINI_DEEP,
        RESEARCH_GPT_SMART_EXECUTOR,
        RESEARCH_GPT_SMART_ADVISOR,
        RESEARCH_GPT_DEEP,
        RESEARCH_GROK_SMART_EXECUTOR,
        RESEARCH_GROK_SMART_ADVISOR,
        RESEARCH_GROK_DEEP,
        FACTCHECK_PRIMARY,
    )
    return {
        "smart": {
            "claude":    {"executor": RESEARCH_CLAUDE_SMART_EXECUTOR,
                          "advisor":  RESEARCH_CLAUDE_SMART_ADVISOR},
            "gemini":    {"executor": RESEARCH_GEMINI_SMART_EXECUTOR,
                          "advisor":  RESEARCH_GEMINI_SMART_ADVISOR},
            "gpt":       {"executor": RESEARCH_GPT_SMART_EXECUTOR,
                          "advisor":  RESEARCH_GPT_SMART_ADVISOR},
            "grok":      {"executor": RESEARCH_GROK_SMART_EXECUTOR,
                          "advisor":  RESEARCH_GROK_SMART_ADVISOR},
            "factcheck": FACTCHECK_PRIMARY,
        },
        "deep": {
            "claude":    RESEARCH_CLAUDE_DEEP,
            "gemini":    RESEARCH_GEMINI_DEEP,
            "gpt":       RESEARCH_GPT_DEEP,
            "grok":      RESEARCH_GROK_DEEP,
            "factcheck": FACTCHECK_PRIMARY,
        },
    }


# ── Intake endpoints ──────────────────────────────────────────────────────────

@app.post("/api/intake/start")
async def intake_start(req: IntakeStartRequest):
    """
    Start a new intake session and immediately analyze the user's prompt.

    Gemini Flash classifies the prompt, assigns a tier, and either:
    - returns a clarifying question (status: "clarifying"), or
    - returns a complete session config (status: "complete")

    Returns:
        {
            "session_id":          str,
            "status":              "clarifying" | "complete",
            "clarifying_question": str | None,
            "config":              dict | None,
        }
    """
    session_id = str(uuid.uuid4())
    session = IntakeSession()
    _intake_sessions[session_id] = session
    try:
        result = await asyncio.to_thread(session.analyze, req.prompt)
    except RuntimeError as e:
        if "unavailable after 3 attempts" in str(e):
            raise HTTPException(
                status_code=503,
                detail="Intake service temporarily unavailable — please try again in a moment.",
            )
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini intake error: {e}")
    return {"session_id": session_id, "opening_message": INTAKE_OPENING_MESSAGE, **result}


@app.post("/api/intake/respond")
async def intake_respond(req: IntakeRespondRequest):
    """
    Send the user's answer to the clarifying question.

    This endpoint is only called after status: "clarifying". Turn 1 always
    completes the session — no further questions are asked.

    Returns:
        {
            "session_id": str,
            "status":     "complete",
            "config":     dict,
        }
    """
    session = _intake_sessions.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Intake session not found.")
    try:
        result = await asyncio.to_thread(session.respond, req.answer)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini intake error: {e}")
    return {"session_id": req.session_id, **result}



# ── Prompt enrichment ────────────────────────────────────────────────────────

def _enrich_prompt(base_prompt: str, config: dict) -> str:
    """
    Append corrected_assumptions and open_questions from intake config
    to the optimized prompt so research models have full context.

    corrected_assumptions: things the user corrected during intake —
      research models need to know the user's actual situation, not intake's
      initial inference.

    open_questions: things the user said they don't know yet — models
      should treat these as open variables, not assume defaults.
    """
    prompt = base_prompt
    corrected = config.get("corrected_assumptions") or []
    open_qs = config.get("open_questions") or []
    if corrected:
        prompt += (
            "\n\nNote: The user corrected the following during intake:\n"
            + "\n".join(f"- {a}" for a in corrected)
        )
    if open_qs:
        prompt += (
            "\n\nNote: The following remain unknown — treat as open variables:\n"
            + "\n".join(f"- {q}" for q in open_qs)
        )
    output_intent = config.get("output_intent")
    if output_intent:
        prompt += f"\n\nOutput format requested by user: {output_intent}"
    return prompt


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
    optimized_prompt = _enrich_prompt(config.get("optimized_prompt", req.prompt), config)
    health = PipelineHealth()

    # Tier must be "smart" or "deep" — anything else defaults to smart
    if tier not in ("smart", "deep"):
        tier = "smart"

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

    gemini_history = transcript.get_history_for_model("gemini")
    gpt_history    = transcript.get_history_for_model("gpt")
    grok_history   = transcript.get_history_for_model("grok")
    claude_history = transcript.get_history_for_model("claude")
    gemini_system  = get_round1_system_prompt("gemini")
    gpt_system     = get_round1_system_prompt("gpt")
    grok_system    = get_round1_system_prompt("grok")
    claude_system  = get_round1_system_prompt("claude")

    # ── Parallel: Gemini + GPT + Grok + Claude + Perplexity pre-research ─────
    async def _research_task() -> str:
        try:
            return await asyncio.to_thread(
                _call_with_retry,
                lambda: perplexity_research(optimized_prompt, tier=tier),
                "Perplexity-research",
            )
        except Exception as exc:
            return f"[Perplexity pre-research unavailable: {exc}]"

    results = await asyncio.gather(
        call_research_gemini_async(gemini_history, gemini_system, tier),
        call_research_gpt_async(gpt_history, gpt_system, tier),
        call_research_grok_async(grok_history, grok_system, tier),
        call_research_claude_async(claude_history, claude_system, tier),
        _research_task(),
        return_exceptions=True,
    )

    def _unpack(result, lab: str) -> tuple:
        if isinstance(result, Exception):
            return f"[{lab.capitalize()} unavailable — {result}]", "unavailable"
        if isinstance(result, tuple):
            return result
        return str(result), "primary"

    gemini_text,    gemini_avail    = _unpack(results[0], "gemini")
    gpt_text,       gpt_avail       = _unpack(results[1], "gpt")
    grok_text,      grok_avail      = _unpack(results[2], "grok")
    claude_r1_text, claude_avail    = _unpack(results[3], "claude")
    perplexity_pre = results[4] if isinstance(results[4], str) else ""

    health.research_models = {
        "gemini": gemini_avail,
        "gpt":    gpt_avail,
        "grok":   grok_avail,
        "claude": claude_avail,
    }

    transcript.add_model_message("Gemini", gemini_text,    round="round1")
    transcript.add_model_message("GPT",    gpt_text,       round="round1")
    transcript.add_model_message("Grok",   grok_text,      round="round1")
    transcript.add_model_message("Claude", claude_r1_text, round="round1")

    # ── Perplexity audit (Phase 2) with fallback ──────────────────────────────
    try:
        audit_text, factcheck_provider, _ = await asyncio.to_thread(
            audit_with_fallback,
            {"gemini": gemini_text, "gpt": gpt_text,
             "grok": grok_text, "claude": claude_r1_text},
            perplexity_pre,
            tier,
        )
    except Exception as exc:
        audit_text = f"[Perplexity audit unavailable: {exc}]"
        factcheck_provider = "emergency"
    health.factcheck_model = factcheck_provider
    health.factcheck_degraded = (factcheck_provider != "primary")
    transcript.add_model_message("Perplexity", audit_text, round="audit")

    # ── Synthesis: route to analytical or factual model based on audit ────────
    synthesis_model_id, synthesis_route = select_synthesis_model(audit_text)
    synthesis_system = build_synthesis_prompt(
        output_type=output_type,
        perplexity_findings=audit_text,
        round1_responses={
            "gemini": gemini_text,
            "gpt":    gpt_text,
            "grok":   grok_text,
            "claude": claude_r1_text,
        },
        optimized_prompt=optimized_prompt,
    )
    synthesis_messages = [{"role": "user", "content": req.prompt}]
    try:
        synthesis_text = await call_synthesis_async(
            synthesis_model_id, synthesis_messages, synthesis_system, tier
        )
        health.synthesis_model = synthesis_model_id
        health.synthesis_routed = synthesis_route
    except Exception as exc:
        print(f"[synthesis] primary failed ({exc}) — using fallback", flush=True)
        try:
            synthesis_text = await call_synthesis_async(
                SYNTHESIS_FALLBACK, synthesis_messages, synthesis_system, tier
            )
            health.synthesis_model = SYNTHESIS_FALLBACK
            health.synthesis_routed = f"{synthesis_route}_fallback"
        except Exception as exc2:
            synthesis_text = f"[Synthesis unavailable: {exc2}]"
            health.synthesis_model = "emergency"
            health.synthesis_routed = f"{synthesis_route}_fallback"

    transcript.add_model_message("Claude", synthesis_text, round="synthesis")
    print(f"[SESSION] {health.summary()}", flush=True)

    return {
        "round1": {
            "gemini": gemini_text,
            "gpt":    gpt_text,
            "grok":   grok_text,
            "claude": claude_r1_text,
        },
        "audit":             audit_text,
        "synthesis":         synthesis_text,
        "pipeline_health":   health.summary(),
        "annotations":       health.to_annotation(),
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

async def safe_close(ws):
    """Close a WebSocket, silently ignoring errors if already closed.

    websocket.close() raises RuntimeError when called after the client has
    already disconnected (e.g. inside a WebSocketDisconnect handler) or when
    a prior close frame was already sent.  Swallowing it here lets every
    call site use a uniform close pattern without try/except boilerplate.
    """
    try:
        await ws.close()
    except RuntimeError:
        pass  # Already closed by client or a prior handler


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


def _grok_token_iter(messages, tier, system):
    """Yield text tokens from a streaming Grok response."""
    for chunk in call_grok(messages=messages, tier=tier, system=system, stream=True):
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


def _grok_advisor(executor_text: str, request: str) -> str:
    resp = call_grok(
        messages=[{"role": "user", "content": _ADVISOR_PROMPT.format(request=request, response=executor_text)}],
        tier="deep",  # grok-3
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


async def call_synthesis_async(
    model: str,
    messages: list,
    system: str,
    tier: str,
) -> str:
    """
    Dispatch synthesis to the correct provider based on model ID prefix.

    claude/* → Anthropic (smart: executor+advisor; deep: single opus call)
    gpt/*    → OpenAI
    qwen/*   → OpenRouter
    """
    if model.startswith("claude"):
        if tier == "smart":
            result = await _call_with_retry_async(
                lambda: call_claude_smart_async(messages, system),
                "Claude-synthesis-smart",
            )
            return result["advisor_text"]
        else:
            result = await asyncio.to_thread(
                call_claude, messages=messages, tier="deep", system=system
            )
            return result.content[0].text
    elif model.startswith("gpt"):
        result = await asyncio.to_thread(
            call_gpt, messages=messages, tier="deep", system=system
        )
        return result.choices[0].message.content
    else:
        # OpenRouter fallback (Qwen or other)
        from backend.models.openrouter_client import call_synthesis_fallback
        return await asyncio.to_thread(call_synthesis_fallback, messages, system)


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


async def _drain_client_messages(
    websocket: WebSocket,
    dialogue_queue: "asyncio.Queue | None" = None,
) -> None:
    """
    Read client JSON while the session runs; answer keep-alive pings so inbound
    frames are not mistaken for session payloads.

    If dialogue_queue is provided, routes ``user_dialogue_response`` and
    ``finalize_synthesis`` messages into it so the session handler can drive
    the synthesis refinement loop.
    """
    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif (
                dialogue_queue is not None
                and isinstance(data, dict)
                and data.get("type") in (
                    "user_dialogue_response", "finalize_synthesis",
                    "prompt_confirmed", "prompt_adjusted",
                )
            ):
                await dialogue_queue.put(data)
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
    grok: str,
    claude: str,
    perplexity: str,
    tier: str,
) -> list:
    """
    Ask Claude to identify 3–5 key observations from the Round 1 responses.

    Returns a list of observation strings surfaced as read-only annotations
    after synthesis completes. Falls back to [] on any error.
    """
    system = (
        "You are analyzing four AI model responses to identify key observations for synthesis. "
        "Respond ONLY with valid JSON in this exact format with no other text:\n"
        "{\"observations\": [\"...\", \"...\"]}\n\n"
        "Each observation must be a single self-contained sentence that:\n"
        "- States what Gemini, GPT, Grok, and/or Claude said (a point of agreement, "
        "disagreement, or key decision)\n"
        "- States how you resolved it in the final synthesis\n"
        "Identify exactly 3 to 5 observations. No preamble, no markdown, only the JSON object."
    )
    obs_prompt = (
        f"User's request: {prompt}\n\n"
        f"Gemini's response:\n{gemini[:2000]}\n\n"
        f"GPT's response:\n{gpt[:2000]}\n\n"
        f"Grok's response:\n{grok[:2000]}\n\n"
        f"Claude's response:\n{claude[:2000]}\n\n"
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
        {"type": "token",                "sender": "Gemini"|"GPT"|"Grok"|"Claude", "token": str}  # parallel
        {"type": "model_complete",       "sender": "Gemini"|"GPT"|"Grok"|"Claude"}
        {"type": "error",                "message": str}   # skipped model (non-fatal)
        {"type": "perplexity_thinking"}
        {"type": "perplexity_complete",  "content": str}
        {"type": "synthesis_thinking"}
        {"type": "token",                "sender": "Claude", "token": str}   # synthesis tokens
        {"type": "synthesis_complete",   "content": str}
        {"type": "synthesis_annotations", "annotations": [str, ...]}   # read-only, optional
        {"type": "session_complete"}
        {"type": "error",                "message": str}   # fatal session error

    All four models (Gemini, GPT, Grok, Claude) stream simultaneously in Round 1.
    Perplexity pre-research runs silently in the same gather.
    Claude also synthesises at the end (separate call with full context).
    Each provider retries up to 3× (5s/10s/20s) on 503/429.
    """
    await websocket.accept()

    while True:
        try:
            data = await websocket.receive_json()
        except WebSocketDisconnect:
            await safe_close(websocket)
            return
        except Exception:
            await websocket.send_json({"type": "error", "message": "Invalid handshake — expected JSON with prompt and session_config."})
            await safe_close(websocket)
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
        await safe_close(websocket)
        return

    # Tier must be "smart" or "deep" — anything else defaults to smart
    if tier not in ("smart", "deep"):
        tier = "smart"
    health = PipelineHealth()
    optimized_prompt = _enrich_prompt(config.get("optimized_prompt", prompt), config)
    transcript = _build_transcript(config, history, prompt)

    dialogue_queue: asyncio.Queue = asyncio.Queue()
    ping_task = asyncio.create_task(_drain_client_messages(websocket, dialogue_queue))
    try:
        # ── Prompt review gate — user confirms or adjusts before research starts ─
        await websocket.send_json({
            "type": "prompt_review",
            "optimized_prompt": optimized_prompt,
            "session_title": config.get("session_title", ""),
            "output_intent": config.get("output_intent", ""),
            "open_questions": config.get("open_questions", []),
            "confirmed_assumptions": config.get("confirmed_assumptions", []),
        })
        review_msg = await dialogue_queue.get()
        if review_msg.get("type") == "prompt_adjusted":
            adjustment = (review_msg.get("adjustment") or "").strip()
            if adjustment:
                optimized_prompt += f"\n\nUser correction: {adjustment}"

        await websocket.send_json({"type": "session_started"})

        # ── Round 1: all four labs + Perplexity pre-research ─────────────────
        gemini_history = transcript.get_history_for_model("gemini")
        gpt_history    = transcript.get_history_for_model("gpt")
        grok_history   = transcript.get_history_for_model("grok")
        claude_history = transcript.get_history_for_model("claude")
        gemini_system  = get_round1_system_prompt("gemini")
        gpt_system     = get_round1_system_prompt("gpt")
        grok_system    = get_round1_system_prompt("grok")
        claude_system  = get_round1_system_prompt("claude")
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

        results = await asyncio.gather(
            call_research_gemini_async(gemini_history, gemini_system, tier),
            call_research_gpt_async(gpt_history, gpt_system, tier),
            call_research_grok_async(grok_history, grok_system, tier),
            call_research_claude_async(claude_history, claude_system, tier),
            _research_task(),
            return_exceptions=True,
        )

        def _unpack(result, lab: str) -> tuple:
            if isinstance(result, Exception):
                return f"[{lab.capitalize()} unavailable — {result}]", "unavailable"
            if isinstance(result, tuple):
                return result
            return str(result), "primary"

        gemini_text,    gemini_avail    = _unpack(results[0], "gemini")
        gpt_text,       gpt_avail       = _unpack(results[1], "gpt")
        grok_text,      grok_avail      = _unpack(results[2], "grok")
        claude_r1_text, claude_avail    = _unpack(results[3], "claude")
        perplexity_pre = results[4] if isinstance(results[4], str) else ""

        health.research_models = {
            "gemini": gemini_avail,
            "gpt":    gpt_avail,
            "grok":   grok_avail,
            "claude": claude_avail,
        }

        async def _emit_model_tokens(
            sender: str,
            text: str,
            model_used: str = "",
            advisor_model: str = "",
            availability: str = "primary",
        ) -> None:
            body = text or ""
            step = 48
            for i in range(0, len(body), step):
                piece = body[i : i + step]
                async with send_lock:
                    await websocket.send_json({"type": "token", "sender": sender, "token": piece})
            async with send_lock:
                await websocket.send_json({
                    "type": "model_complete",
                    "sender": sender,
                    "model_used": model_used,
                    "advisor_model": advisor_model,
                    "tier": tier,
                    "availability": availability,
                })

        await asyncio.gather(
            _emit_model_tokens(
                "Gemini", gemini_text,
                model_used=tier_config["gemini"]["executor"],
                advisor_model=tier_config["gemini"]["advisor"],
                availability=gemini_avail,
            ),
            _emit_model_tokens(
                "GPT", gpt_text,
                model_used=tier_config["gpt"]["executor"],
                advisor_model=tier_config["gpt"]["advisor"],
                availability=gpt_avail,
            ),
            _emit_model_tokens(
                "Grok", grok_text,
                model_used=tier_config["grok"]["executor"],
                advisor_model=tier_config["grok"]["advisor"],
                availability=grok_avail,
            ),
            _emit_model_tokens(
                "Claude", claude_r1_text,
                model_used=tier_config["claude"]["executor"],
                advisor_model=tier_config["claude"]["advisor"],
                availability=claude_avail,
            ),
        )

        transcript.add_model_message("Gemini", gemini_text,    round="round1")
        transcript.add_model_message("GPT",    gpt_text,       round="round1")
        transcript.add_model_message("Grok",   grok_text,      round="round1")
        transcript.add_model_message("Claude", claude_r1_text, round="round1")

        # ── Perplexity audit (Phase 2) with fallback ──────────────────────────
        await websocket.send_json({"type": "perplexity_thinking"})
        try:
            audit_text, factcheck_provider, citations = await asyncio.to_thread(
                audit_with_fallback,
                {"gemini": gemini_text, "gpt": gpt_text,
                 "grok": grok_text, "claude": claude_r1_text},
                perplexity_pre,
                tier,
            )
        except Exception as exc:
            audit_text = f"[Perplexity audit unavailable: {exc}]"
            factcheck_provider = "emergency"
            citations = []
        health.factcheck_model = factcheck_provider
        health.factcheck_degraded = (factcheck_provider != "primary")
        transcript.add_model_message("Perplexity", audit_text, round="audit")

        # Determine factcheck display info for frontend transparency
        _factcheck_display = {
            "primary":   ("sonar-pro",  "primary"),
            "fallback1": ("sonar",      "fallback"),
            "fallback2": ("gpt-5.4",    "fallback2"),
        }
        _fc_model, _fc_avail = _factcheck_display.get(
            factcheck_provider, ("sonar-pro", "primary")
        )
        await websocket.send_json({
            "type": "perplexity_complete",
            "content": audit_text,
            "citations": citations,
            "factcheck_model_used": _fc_model,
            "factcheck_availability": _fc_avail,
        })

        # ── Self-critique pre-flight ──────────────────────────────────────────
        # A fast Sonnet call audits round-1 quality before synthesis begins.
        # The critique notes are injected into the synthesis system prompt so
        # Claude addresses flagged gaps and unsupported claims in its verdict.
        try:
            round1_for_critique = {
                "gemini": gemini_text,
                "gpt":    gpt_text,
                "grok":   grok_text,
                "claude": claude_r1_text,
            }
            critique_notes = await call_self_critique(
                round1_responses=round1_for_critique,
                perplexity_findings=audit_text,
                contradiction_flag=perplexity_contradicts_round1(audit_text),
            )
        except Exception as exc:
            print(f"[self-critique] failed ({exc}) — continuing without", flush=True)
            critique_notes = None

        # ── Synthesis draft — fires automatically after fact-check ────────────
        # No user gate. The user refines via the dialogue loop below.
        synthesis_model_id, synthesis_route = select_synthesis_model(audit_text)
        synthesis_system = build_synthesis_system(
            citations=citations, audit_text=audit_text, critique_notes=critique_notes
        )
        synthesis_messages = [{"role": "user", "content": prompt}]

        await websocket.send_json({"type": "synthesis_thinking"})
        try:
            raw_synthesis = await call_synthesis_async(
                synthesis_model_id, synthesis_messages, synthesis_system, tier
            )
            health.synthesis_model = synthesis_model_id
            health.synthesis_routed = synthesis_route
        except Exception as exc:
            print(f"[synthesis] primary failed ({exc}) — using fallback", flush=True)
            try:
                raw_synthesis = await call_synthesis_async(
                    SYNTHESIS_FALLBACK, synthesis_messages, synthesis_system, tier
                )
                health.synthesis_model = SYNTHESIS_FALLBACK
                health.synthesis_routed = f"{synthesis_route}_fallback"
            except Exception as exc2:
                raw_synthesis = f"[Synthesis unavailable: {exc2}]"
                health.synthesis_model = "emergency"
                health.synthesis_routed = f"{synthesis_route}_fallback"

        current_synthesis, closing_questions = parse_closing_questions(raw_synthesis)
        revision_count = 0
        dialogue_history = [{"role": "assistant", "content": current_synthesis}]
        research_context = {
            "gemini": gemini_text,
            "gpt":    gpt_text,
            "grok":   grok_text,
            "claude": claude_r1_text,
        }

        await websocket.send_json({
            "type": "synthesis_draft",
            "content": current_synthesis,
            "revision": revision_count,
            "closing_questions": closing_questions,
            "synthesis_model_used": health.synthesis_model or synthesis_model_id,
            "synthesis_route": health.synthesis_routed or synthesis_route,
        })

        # ── Dialogue loop: refine on user_dialogue_response, exit on finalize ──
        finalized = False
        while not finalized:
            msg = await dialogue_queue.get()
            msg_type = msg.get("type")

            if msg_type == "finalize_synthesis":
                finalized = True
                transcript.add_model_message(
                    "Claude", current_synthesis, round="synthesis"
                )
                await websocket.send_json({
                    "type": "synthesis_final",
                    "content": current_synthesis,
                    "revision": revision_count,
                })
                break

            if msg_type == "user_dialogue_response":
                user_text = (msg.get("content") or "").strip()
                if not user_text:
                    continue
                dialogue_history.append({"role": "user", "content": user_text})

                await websocket.send_json({"type": "synthesis_thinking"})
                try:
                    refined = await call_synthesis_refinement(
                        original_synthesis=current_synthesis,
                        dialogue_history=dialogue_history,
                        user_message=user_text,
                        research_context=research_context,
                        audit_context=audit_text,
                        citations=citations,
                    )
                except Exception as exc:
                    refined = {
                        "content": f"[Refinement unavailable: {exc}]",
                        "closing_questions": [],
                    }

                current_synthesis = refined["content"]
                closing_questions = refined["closing_questions"]
                revision_count += 1

                dialogue_history.append({
                    "role": "assistant",
                    "content": current_synthesis,
                })

                await websocket.send_json({
                    "type": "synthesis_draft",
                    "content": current_synthesis,
                    "revision": revision_count,
                    "closing_questions": closing_questions,
                    "synthesis_model_used": health.synthesis_model or synthesis_model_id,
                    "synthesis_route": health.synthesis_routed or synthesis_route,
                })

        print(f"[SESSION] {health.summary()}", flush=True)

        # Send pipeline health annotations (read-only, after synthesis_final).
        await websocket.send_json({
            "type": "synthesis_annotations",
            "annotations": health.to_annotation(),
            "pipeline_health": health.summary(),
        })
        await websocket.send_json({"type": "session_complete"})

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
        await safe_close(websocket)
