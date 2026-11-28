# ai-roundtable — How the Design Works
## ai-roundtable · JSTcurious · November 2026

**Status:** Describes the system as of `main` at `1526281f` (PR #58). It
documents what the code does today. It is not a proposal. Where the code
and an older comment disagree, this document follows the code (see
*Known mismatches*).

---

## 1. What the product is

A deliberation tool for high-stakes decisions, built for **one good answer in
one session**, not for quick queries. The user is "in the chair" at every
stage: they shape the brief, see what the panel is told, watch each expert
respond, read the fact-check, and then argue with the synthesis until they
finalize it.

The design goal is a roundtable you take part in, not a black box. Every stage
is visible, and the user has a decision point at the start (review) and at the
end (dialogue and Finalize).

## 2. The session at a glance

```
LANDING ──► INTAKE ──► PROMPT REVIEW ──► RESEARCH ──► FACT-CHECK ──► SELF-CRITIQUE
 prompt     multi-turn   user sees and     4 models     Perplexity     (internal,
            questions    edits brief +     in parallel  audits the     not shown)
                         facts list        + Perplexity four
                                           pre-research
                                                              │
        FINAL ANSWER ◄── DIALOGUE ◄── SYNTHESIS DRAFT ◄───────┘
        user clicks      user replies,  one streamed Claude
        Finalize         Claude revises call, starts on its own
```

| Stage | Who decides | Where |
|---|---|---|
| Intake | Claude Sonnet asks questions; the user answers | `backend/intake.py`, `POST /api/intake/*` |
| Prompt review | **The user** confirms or edits the brief and the facts list | `/ws/session`, `SessionView.jsx` |
| Research | Four labs in parallel, plus Perplexity pre-research | `/ws/session` |
| Fact-check | Perplexity (Sonar Pro) audits the four responses | `audit_with_fallback` |
| Self-critique | Claude audits round-1 quality for synthesis | `call_self_critique` in `router.py` |
| Synthesis draft | Claude, streamed; no user gate | `call_synthesis_async` |
| Dialogue | **The user** replies; Claude refines; repeat | `call_synthesis_refinement` |
| Final answer | **The user** clicks Finalize | `finalize_synthesis` message |

The browser talks to the backend over two channels: plain HTTP for intake and
export, and one WebSocket (`/ws/session`) for everything from the prompt
review onward. There is no other way to run a session.

## 3. Intake

Intake turns a rough prompt into a research brief the panel can act on.
Per-session state lives in memory in an `IntakeSession` (`_intake_sessions`
dict in `main.py`), so an intake does not survive a backend restart.

**Flow**
1. `POST /api/intake/start` creates the session and runs `analyze(prompt)`.
2. The first turn is always the **background question** ("Tell me a bit about
   yourself…"), asked before any model call. It doesn't count toward the
   minimum-question rules.
3. After the answer, the intake model is called each turn with the original
   prompt plus the full Q&A history (`_build_combined_prompt`). It returns an
   `IntakeDecision`: either a clarifying question with chip options, or a
   finished brief.
4. `POST /api/intake/respond` carries each later answer.

**Rules in code (`intake.py`)**
- Domain detection by keyword match, on the original prompt only.
- `MINIMUM_QUESTIONS_REQUIRED`: immigration 3, career 2, financial 2,
  general 1. The session cannot close below the floor, even if the model says
  it is done.
- When the floor isn't met, the model's own question is used first, then the
  `FALLBACK_QUESTIONS` bank.
- If the model already captured `output_intent`, one question is credited
  toward the floor.
- Immigration guard: if immigration context is present but the visa type is
  unresolved, a fixed visa-type question is forced.
- Duplicate questions are skipped.

**Model chain** (`call_intake`): Claude Sonnet, then GPT-4o Mini, then Qwen via
OpenRouter, then an emergency passthrough that runs the raw prompt on the smart
tier. All callers share one system prompt (`_build_intake_system_prompt()` in
`backend/models/openai_client.py`) and one schema, and output is capped at
`max_tokens=2000`.

**What intake produces** (`IntakeDecision`, `backend/models/intake_decision.py`)
- `optimized_prompt`: the research brief, in prose. Its parts are the
  decision, the facts as stated, the tension, the wrong answer, the output
  format, and the pressure. It also carries a "User background" line, and a
  TRACK PARITY instruction when the user asked for two or more parallel
  tracks.
- `stated_facts`: every explicit fact the user stated, one short line each,
  in their words.
- `output_intent`, `session_title`, `user_context`, `confirmed_assumptions`,
  `corrected_assumptions`, `open_questions`, and `tier` (always `smart`).

When intake closes, the session config also records `background_context` and
`original_prompt`. Both are sanitized of bidi and invisible control
characters.

**Chips.** Clicking a chip selects it and does not submit; the → button
submits the selected chip or the typed text. Open-ended questions show a "Skip
this question" link that submits "I'd prefer not to say".

## 4. Prompt review (the first human check)

Before any research call, the backend sends a `prompt_review` message with the
brief, the session title, the output intent, the open questions, the
confirmed assumptions, and `stated_facts`. The review screen shows:

- **What I'll research:** the brief.
- **What I'm telling the panel about your situation:** the facts as editable
  lines. The user can fix a line, remove it, or add one.
- **What you want to walk away with** and **Still unknown.**
- Two actions: *Looks good — Start Research*, or *Let me adjust something* (free
  text).

The reply is `prompt_confirmed` or `prompt_adjusted`, either one carrying the
final `stated_facts` list. The backend then builds the research input:

```
research input = brief
               + background answer, corrections, open questions, output intent  (_enrich_prompt)
               + facts block built from the user's confirmed list                (build_stated_facts_block)
               + "User correction: …"  (only if the user adjusted)
```

If the list is empty the facts block falls back to the user's original prompt,
verbatim. Only after this does the backend build the transcript the four
panel models read, so edits and corrections reach all of them.
Details: `docs/INTAKE_BRIEF_FIDELITY_SPEC.md`.

## 5. Research: four experts in parallel

All five calls start together and are timed individually:

| Seat | Role in the room | Lab |
|---|---|---|
| Claude | **Analyst**: first-principles reasoning | Anthropic |
| GPT | **Pragmatist**: practical, concrete, actionable | OpenAI |
| Gemini | **Scout**: finds angles and options the others miss | Google |
| Grok | **Challenger**: stress-tests the premise itself | xAI |
| Perplexity | pre-research with live web search, not shown as a seat | Perplexity |

- Each lab gets the same transcript but its own system prompt
  (`ROUND1_SYSTEM_PROMPTS` in `router.py`). They don't see each other's
  answers during research, so the four responses are independent.
- The smart tier pairs a faster **executor** model with a frontier **advisor**
  that reviews the executor's draft. The advisor's text is the response
  shown (for example Claude: Sonnet executes, Opus advises). Each lab has a
  fallback model.
- Every call returns an availability status: `primary`, `fallback`, or
  `unavailable`. An unavailable lab is left out of the panel, and the later
  stages are told which seats are missing.
- Responses are sent to the browser in small chunks once all four are in,
  followed by a `model_complete` message per seat showing which models were
  used.
- Perplexity's pre-research is held back and used by the fact-check.

Panel descriptions on the landing page must stay aligned with the cognitive
roles above.

## 6. Fact-check

Perplexity Sonar Pro audits the four responses against its live pre-research
(`audit_with_fallback`: Sonar Pro, then Sonar, then GPT as the last fallback).
It returns the audit text plus citations, and sends them to the browser as
`perplexity_complete`. The audit is never wrapped like a model response.

It is a single pass that always runs at full depth. It reports claims that
are wrong, important missing information, and a best-supported synthesis. The
synthesis step reads it as the trust anchor for post-training-cutoff facts.

## 7. Self-critique and synthesis

1. **Self-critique** (`call_self_critique`): a short Claude call reads the
   four responses and the audit and notes gaps and unsupported claims. It is
   capped at 1,500 tokens. The user doesn't see it. If it fails, synthesis
   continues without it.
2. **Synthesis draft**: one streamed Claude call (`SYNTHESIS_ANALYTICAL`)
   starts on its own after the fact-check. Its system prompt contains the four
   responses, each wrapped by `wrap_model_response()` so they read as untrusted
   research, plus the audit, the citations, the critique notes, and a note on
   any missing seats. The brief is the user message.
   If it fails, the fallback is Qwen via OpenRouter; if that fails too, the
   user sees an "unavailable" message. Tokens arrive as `synthesis_token`
   messages, then `synthesis_draft` with the cleaned text. A stream that
   fails partway sends `synthesis_reset` to clear what was shown.
3. **Output format**, four required sections: THE VERDICT, THE HINGE, WHERE
   THE PANEL DISAGREED, ONE NEXT ACTION. Trailing `?` lines are parsed out as
   closing questions the user can answer.

## 8. Dialogue and finalizing

The synthesis is a draft, so the user works from something to react to, not
a blank box. The loop:

- The user replies (`user_dialogue_response`). Claude revises
  (`call_synthesis_refinement`) using the research, the audit, and the
  conversation so far, streaming the new version.
- Each revision increments a counter, and the badge on the synthesis shows
  DRAFT, REVISED, or FINAL.
- The user clicks **Finalize** (`finalize_synthesis`). The backend sends
  `synthesis_final`, then `synthesis_annotations` (which models actually
  handled each stage, shown only when something was degraded), then
  `session_complete`.

After that, "Take this further" exports the full session or the synthesis as
Markdown (`POST /api/export/markdown`). The Drive export is a placeholder.

## 9. Model selection and resilience

**One source of truth.** Every model ID lives in
`backend/models/model_registry.json`, with a tier (`fast`, `balanced`,
`frontier`), a status (`approved`, `candidate`, `disabled`), and optional
retirement dates. It also defines 24 pipeline *roles* (for example
`research.gpt.advisor`). At startup `registry.py` resolves each role to one
approved model, and `model_config.py` exposes the results as constants.
Code never hardcodes a model ID, and a test enforces that.

- Per-role environment variables override the registry without a deploy.
- `python -m tools.check_models` compares the registry to the providers' live
  lists. `--write` adds new models as candidates, never approved.
- Startup logs the Python and package versions, the role-to-model table, and
  a ⚠️ line for any retiring, missing, or unresolved model.

**Failure handling.**
- `resilient_caller.py` retries 429/503-type errors with backoff and then
  falls back down the chain. Retries never stack on an inner chain that has
  already run out of attempts.
- `PipelineHealth` records which model handled each stage. Only unusual
  events reach the user.
- Gemini preview models return 503 now and then; its fallback model covers
  this.

## 10. Prompts

All prompt strings live in `backend/router.py`, and nothing is inlined in
`main.py` or a client module. The one exception is the intake system prompt,
which still lives in `openai_client.py`; moving it is a separate refactor.

| Layer | What | Where |
|---|---|---|
| 1 | The brief: prose parts including the facts carry-over rule | intake system prompt |
| 2 | Per-seat system prompts (Analyst, Pragmatist, Scout, Challenger) | `ROUND1_SYSTEM_PROMPTS` |
| 3 | Self-critique and synthesis | `SELF_CRITIQUE_SYSTEM`, `SYNTHESIS_SYSTEM_PROMPT` |

Epistemic guardrails (accuracy rules, a guard against cascading unverified
claims, and the confidence labels `[VERIFIED]`, `[LIKELY]`, `[UNCERTAIN]`)
are injected into every research prompt. The rationale is in
`docs/decisions/001-epistemic-transparency.md`.

## 11. Frontend

A React single-page app with four screens: `LandingPage`, `IntakeFlow`,
`SessionView` (review, research, fact-check, dialogue, and the progress bar),
and `TakeFurther`. `SynthesisPanel` renders the draft with its badge.
The session config produced by intake is passed through unchanged to the
WebSocket handshake. Railway serves the committed `frontend/build/`
directly, so any source change must be rebuilt and committed with it.

## 12. Timing

Each session logs a `[TIMING]` line per stage (each research seat, research,
research.emit, factcheck, self_critique, synthesis, and each refinement) plus
first-token times for synthesis and refinement, and a `first_draft` total.
Timing starts after the prompt review, so the user's thinking time isn't
counted. Latency work is tracked in `docs/LATENCY_SPEC.md`.

## 13. Deployment and operations

- Railway: a backend service and a static frontend service, deployed from
  `main`. The backend starts with `uvicorn backend.main:app` on the port Railway
  assigns (8080).
- Dependencies are fully pinned with hashes, generated from `requirements.in`
  files, and checked by CI (`docs/DEPENDENCY_PINNING_SPEC.md`). CI runs on
  every PR and push to `main`: clean install, lockfile check, and the full
  test suite, including a real-server check that WebSocket close paths leave no
  traceback.
- Secrets live in `backend/.env` locally and in Railway variables in
  production.

## 14. Known mismatches

None known. Stale comments in `transcript.py`, `synthesizer.py` and the intake
docstrings were corrected after this document was first written, and the old
REST route `POST /api/session/run` (no review gate, no facts list) was removed
because nothing called it. The session runs only through `/ws/session`.

## 15. Where to read more

| Topic | Document |
|---|---|
| Intake brief fidelity and the facts list | `docs/INTAKE_BRIEF_FIDELITY_SPEC.md` |
| Intake v2 and its PM addendum | `docs/INTAKE_V2_SPEC.md`, `docs/INTAKE_V2_PM_ADDENDUM.md` |
| Model registry | `docs/MODEL_REGISTRY_SPEC.md` |
| Latency plan | `docs/LATENCY_SPEC.md` |
| Dependency pinning and CI | `docs/DEPENDENCY_PINNING_SPEC.md` |
| Model choices and why | `docs/decisions/001` to `004` |
| Roadmap and competitors | `docs/V3_ROADMAP.md`, `docs/COMPETITIVE_ANALYSIS.md` |
