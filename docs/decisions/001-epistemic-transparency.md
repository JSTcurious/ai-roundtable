# ADR 001: Epistemic Transparency over Epistemic Suppression

**Status:** Accepted
**Date:** 2026-04-17

## Context

ai-roundtable is a multi-provider roundtable where five AI models share a
persistent transcript. Three models (Gemini, GPT, Grok) respond sequentially in
Round 1 — each receiving the full prior transcript including what previous models
said. This creates cascading hallucination risk: a fabrication from one model can
be treated as established context by subsequent models, which may repeat or build
on it with additional confidence.

Two competing approaches exist:

1. **Epistemic suppression** — restrict models to a grounding corpus (RAG) and
   forbid outside knowledge.
2. **Epistemic transparency** — allow open-world reasoning but require models
   to tag confidence and attribute claims to their source.

## Decision

We chose epistemic transparency.

The value proposition of a multi-provider roundtable is models drawing on
independent knowledge bases to produce useful disagreement. A grounding
restriction would reduce the app to parallel RAG — the disagreement would
disappear, and tools that already have a real corpus (Perplexity, NotebookLM)
already do that better.

The guardrail implementation in `backend/router.py` injects three blocks into
every Round 1 system prompt:

- `ANTI_HALLUCINATION_BLOCK` — baseline accuracy instructions (no fabrication,
  acknowledge gaps, distinguish fact from inference)
- `CASCADING_GUARD` — explicit instruction not to treat a prior model's claim as
  verified simply because it appeared in the shared transcript; attribute and
  flag independently
- `CONFIDENCE_CONVENTION` — four inline tags (`[VERIFIED]`, `[LIKELY]`,
  `[UNCERTAIN]`, `[DEFER]`) to make uncertainty legible in the transcript

These blocks are composed in `get_round1_system_prompt()` after the base role
prompt, before any task-specific instructions.

## Consequences

- Hallucinations remain possible but should be tagged `[UNCERTAIN]`.
- Perplexity's fact-check audit runs after Round 1 and surfaces factual gaps
  across all three research responses — a second line of defense.
- Downstream consumers of transcripts must understand the confidence tag
  convention.
- Future eval work (Ragas-style) can filter on `[UNCERTAIN]` tags rather than
  parsing free text for hedging language.

## Alternatives Considered

- **RAG grounding clause in system prompt** — rejected. Kills the disagreement
  that makes the roundtable useful. ai-roundtable's differentiation is
  independent open-world reasoning across five providers, not grounded retrieval.
- **Post-hoc judge model to flag contradictions** — deferred. Worth revisiting
  once the tag convention is adopted and labeled transcripts exist for evals.
- **Suppressing the transcript from subsequent models** — rejected. Sequential
  transcript access is the core product differentiator (the "compounding
  transcript effect"). Breaking this to prevent cascading hallucinations would
  remove the product's primary value.
