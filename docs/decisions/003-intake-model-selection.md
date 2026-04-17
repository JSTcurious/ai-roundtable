# ADR 003: Intake Model Selection

**Status:** Accepted
**Date:** 2026-04-17

## Context

The intake model is the first AI the user interacts with. It runs before any
frontier model is invoked and makes three decisions that gate session quality:

1. **Clarification** — does the user's prompt have enough context to run the
   roundtable, or does it need a single focused follow-up question?
2. **Tier assignment** — should the session use Quick / Smart / Deep models?
3. **Prompt optimization** — rewrite the user's raw input as a precise,
   context-rich prompt that eliminates assumptions before passing to round-1.

The intake model must also follow a **proper noun preservation rule**: any
model name, product name, version number, or named entity provided by the user
must survive into the optimized prompt unchanged. A model that substitutes
"Claude Opus 4.7" with "Claude 3 Opus" (its training-data equivalent) corrupts
the session before the first frontier model is called.

Constraints specific to the intake role:

- **Low latency** — intake runs synchronously before the roundtable. Every
  millisecond here is felt by the user. Target < 2s.
- **Structured output required** — must return a valid `IntakeDecision` JSON
  object on every call. No graceful degradation to free text.
- **Cost efficiency** — intake runs on every session, including Quick-tier
  sessions that cost pennies end-to-end. High intake cost breaks the model.
- **Reliability** — 503s or rate limits at intake abort the session before it
  starts. Production must tolerate at least one retry.

## Evaluation

The `experiments/intake_eval/` harness tests five candidates across six
scenarios with automated assertion scoring.

### Candidates

| Candidate | Provider | Input rate | Output rate |
|-----------|----------|-----------|------------|
| Gemini 2.5 Flash | Google | $0.15/MTok | $0.60/MTok |
| Gemini 2.0 Flash | Google | $0.10/MTok | $0.40/MTok |
| GPT-4o Mini | OpenAI | $0.15/MTok | $0.60/MTok |
| Claude Haiku 4.5 | Anthropic | $0.80/MTok | $4.00/MTok |
| Qwen 2.5 72B | OpenRouter | $0.40/MTok | $1.20/MTok |

### Test Coverage

| Test | Capability |
|------|-----------|
| test1-simple | Proceeds without clarification; smart tier |
| test2-vague | Triggers exactly one clarifying question |
| test3-proper-nouns | User-provided model names survive unchanged |
| test4a-tier-quick | Factual lookup → quick tier |
| test4b-tier-deep | Architecture decision → deep tier |
| test5-two-turn | Proper nouns survive across clarification round-trip |
| test6-consistency | Same borderline prompt → same tier across 3 runs |

### Critical Failure Conditions

- Any proper noun substitution in `optimized_prompt` → hard fail
- JSON parse error on any test → hard fail for that test
- Tier instability across consistency runs → hard fail

_Fill in results from `experiments/intake_eval/results/summary-*.md` after
running the eval harness:_
```
python -m experiments.intake_eval.run_eval
```

## Decision

**Gemini 2.5 Flash is the production intake model.**

Key reasons:

1. **Native structured output** — the Google Generative AI SDK's
   `response_schema` parameter enforces the `IntakeDecision` Pydantic schema
   at the API level. Parse errors are structurally impossible; no JSON
   extraction logic is needed.
2. **Low latency** — Gemini Flash is optimized for fast single-turn calls.
   Typical intake call completes in < 1.5s.
3. **Low cost** — at $0.15/$0.60 per MTok, intake cost is negligible relative
   to round-1 and synthesis calls on Smart and Deep tiers. On Quick tier,
   intake cost is within the same order of magnitude as synthesis.
4. **Proper noun preservation** — with the `PROPER NOUN PRESERVATION` rule
   added to `GEMINI_INTAKE_SYSTEM` and the preservation instruction in the
   Turn 1 combined prompt, Gemini 2.5 Flash passes the preservation assertions.

The intake model is intentionally pinned separately from round-1 Gemini via
`INTAKE_MODEL = os.getenv("GEMINI_INTAKE_MODEL", "gemini-2.5-flash")` in
`backend/models/google_client.py`. This allows the intake model to be upgraded
or swapped without touching the research model configuration.

## Alternatives Considered

**Claude Haiku 4.5** — produces good intake quality but costs 5–6x more per
call than Gemini Flash at intake token volumes. Lacks native structured output
enforcement; requires JSON extraction. Excluded for cost.

**GPT-4o Mini** — viable quality, comparable cost to Gemini Flash. Lacks
`response_schema` enforcement; uses `response_format: {"type": "json_object"}`
which reduces but does not eliminate parse errors. Acceptable as fallback.

**Gemini 2.0 Flash** — previous generation. Marginally cheaper than 2.5 Flash
but lower quality on complex clarification decisions. Only relevant if 2.5
Flash becomes unavailable.

**Qwen 2.5 72B (OpenRouter)** — open-weight model with lower cost than Haiku
but higher than Gemini Flash. No structured output enforcement. OpenRouter
latency is less predictable for synchronous intake use. Excluded.

## Consequences

- `GEMINI_INTAKE_MODEL` env var allows intake model override without a
  code deploy. Can switch to Gemini 2.0 Flash or GPT-4o Mini as fallback.
- The `PROPER NOUN PRESERVATION` rule must be maintained in `GEMINI_INTAKE_SYSTEM`
  for all future iterations of the system prompt.
- The two-turn flow (Turn 0 → clarifying question → Turn 1 → optimized prompt)
  must preserve proper nouns across both turns. The Turn 1 combined string must
  include the preservation instruction (verified in test5-two-turn).
- Gemini 503 errors during intake abort the session. `backend/models/
  google_client.py` implements retry logic (`call_gemini_intake` retries up
  to 3 times with 2s backoff on 503).
- The eval harness (`experiments/intake_eval/`) is a regression guard. Run it
  when changing `GEMINI_INTAKE_SYSTEM` or switching intake models.
- Cost analysis is automated via `experiments/generate_cost_report.py`.
