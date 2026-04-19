# ADR 003: Intake Model Selection

**Status:** Accepted  
**Date:** 2026-04-17

## Context

ai-roundtable uses an intake stage to:

1. Detect whether a prompt needs clarification before the roundtable runs
2. Preserve user-provided proper nouns exactly as typed
3. Optimize the prompt for multi-model research
4. Assign session tier (always "smart" — deep is user opt-in via the frontend modal)

The original intake model was Claude (via `IntakeSession`). This was replaced
during development due to over-engineering for a classification task and cost.
Gemini 2.5 Flash was the interim replacement. A discovered bug then forced a
further change: intake was substituting user-provided model names with its own
training-data alternatives, corrupting sessions before the first frontier model
was called.

An empirical evaluation harness was built and run against five candidates
(see `experiments/intake_eval/`).

## The Proper Noun Bug

During production use of Gemini 2.5 Flash as the interim intake model, the
following was observed:

- User typed: "Compare Claude Opus 4.7 and GPT-5 for enterprise coding use cases"
- Gemini Flash rewrote as: "Compare Claude 3 Opus and GPT-4 for enterprise coding use cases"

The entire research session ran against models the user did not ask about.
Root cause: Gemini Flash's training data treats "Claude Opus 4.7" and "GPT-5"
as unannounced future models and substitutes the nearest known alternatives.
The `PROPER NOUN PRESERVATION` rule in the system prompt was insufficient —
training data overrode the instruction at the point of token generation.

This was confirmed in production transcript 013 and became the hard gate
criterion for the intake eval.

## Evaluation Results

Six tests with automated assertion scoring (see `experiments/intake_eval/results/`):

| Test | Capability |
|------|-----------|
| T1 — Simple | Proceeds without clarification; assigns smart tier |
| T2 — Vague | Triggers exactly one clarifying question |
| T3 — Proper nouns | User-provided model names survive into optimized_prompt unchanged |
| T4a — Tier quick | Factual lookup → quick tier |
| T4b — Tier deep | Architecture decision → deep tier |
| T5 — Two-turn | Proper nouns survive across clarification round-trip |
| T6 — Consistency | Same borderline prompt → same tier across 3 runs |

| Model | Score | Cost/session | 1K sessions | Verdict |
|-------|-------|--------------|-------------|---------|
| GPT-4o Mini | 16/16 (100%) | $0.000226 | $0.23 | ✅ PASS |
| Qwen 2.5 72B | 16/16 (100%) | $0.000583 | $0.58 | ✅ PASS |
| Claude Haiku 4.5 | 10/16 (62%) | $0.002094 | $2.09 | ⚠️ PARTIAL |
| Gemini 2.5 Flash | 4/14 (29%) | $0.000159 | $0.16 | ❌ FAIL |
| Gemini 2.0 Flash | 0/14 (0%) | $0.000000 | $0.00 | ❌ API ERROR |

Gemini 2.5 Flash returned `None` on T1, T3, T5, T6 — JSON parse failures
(structured output not enforced). It passed only T2 and T4a. Its 29% score
is not a marginal miss; it failed the proper noun test that motivated the eval.
Gemini 2.0 Flash had a complete API failure.

GPT-4o Mini and Qwen 2.5 72B both scored 16/16. The consistency test showed
GPT-4o Mini assigns `"smart"` stably across 3 runs; Claude Haiku assigned `"deep"`
stably — an overcall for the borderline prompt used.

## Decision

**Intake fallback chain with provider diversity:**

```
Primary:   GPT-4o Mini      (OpenAI)
Fallback1: Qwen 2.5 72B     (OpenRouter — different provider)
Fallback2: Claude Haiku 4.5 (Anthropic — last resort)
Emergency: Passthrough       (raw prompt, smart tier, never fails the user)
```

**Why GPT-4o Mini as primary:** 100% assertion score, stable `"smart"` tier
assignment, passes proper noun preservation, $0.23/1K sessions. Uses
`response_format: json_object` with `temperature: 0.1` for reliable structured
output. No observed training-data substitution of user-provided model names.

**Why Qwen 2.5 72B as Fallback1:** Also 100% — identical quality to primary,
on OpenRouter (different provider), $0.58/1K. If OpenAI is down, Qwen has no
shared failure mode.

**Why Claude Haiku as Fallback2:** 62% score — lower than primary candidates
but acceptable as last resort. Third distinct provider. Higher cost ($2.09/1K)
is only incurred during OpenAI+OpenRouter simultaneous failure.

**Why passthrough emergency exists:** Intake failure should never block a session.
The passthrough returns the raw user prompt at smart tier — research quality
degrades but the session runs.

**Intake always returns `tier: "smart"`:** Deep sessions require explicit user
confirmation via the frontend modal. `IntakeDecision.tier` is `Literal["smart"]`
in `backend/models/intake_decision.py` — schema enforces this at the type level,
not just the prompt level. The eval was run before this simplification (T4a/T4b
tested quick and deep tier assignment); those tests are now superseded.

## Consequences

- Intake cost: ~$0.23/1K sessions (negligible at any scale)
- Provider diversity across the fallback chain — no single provider outage
  can block intake
- Passthrough emergency ensures sessions always run even if all intake models fail
- `IntakeDecision.tier: Literal["smart"]` makes the two-tier architecture
  enforceable at the type system level, not just by convention
- The eval harness (`experiments/intake_eval/`) is the regression guard — run it
  when changing `INTAKE_SYSTEM_PROMPT` or adding intake model candidates

## Alternatives Considered

**Gemini 2.5 Flash as primary:** Was the interim primary after Claude replacement.
Rejected after eval — 29% score, failed proper noun preservation. The bug was
confirmed in production transcript 013.

**Claude Sonnet 4.6 as primary:** Considered for brand consistency. Rejected —
GPT-4o Mini scored identically (100%) at 23× lower cost. Brand consistency at
the intake layer is invisible to users; they see the optimized prompt, not which
model processed their input.

**End-to-end quality eval (intake prompt → research output quality):** Proposed
but deferred to reduce complexity. The mechanical correctness eval (100% on
GPT-4o Mini) is sufficient for the intake classification task. Measure intake
quality by research output quality only if intake becomes a bottleneck.
