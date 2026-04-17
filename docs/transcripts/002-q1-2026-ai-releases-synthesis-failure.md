# Transcript 002 — Q1 2026 AI Model Releases

**Date:** 2026-04-17
**PR under test:** Anti-hallucination guardrails (commits 487af69f → f67db9d9)
**Prompt:** "What were the major AI model releases in Q1 2026?"

## Why This Prompt

Q1 2026 is recent but not breaking — it falls within the training window of some
models and outside others. This makes it a useful probe for:

- Category switching without disclosure (speculation presented as fact)
- Blanket refusal when partial knowledge exists
- Whether synthesis correctly elevates Perplexity's grounded data over round-1 open-world claims

It also tests a specific architectural assumption: that `SYNTHESIS_SKEPTICISM`
and `CASCADING_GUARD` apply uniformly to all inputs. This test revealed they do
not behave correctly when Perplexity is one of those inputs.

## Round 1 Responses (Summary)

**Gemini:**
- Named several Q1 2026 releases with apparent confidence.
- Midway through the response shifted from factual recall to speculative
  trend extrapolation ("we would expect...", "likely to include...") without
  flagging the category switch.
- The final paragraph read as prediction, not reporting, but was formatted
  identically to the factual portion above it.
- No `[LIKELY]` or `[UNCERTAIN]` tag used at the transition point.

**GPT:**
- Issued a blanket refusal: "My training data does not include events from Q1 2026."
- Did not attempt to name any releases it had reasonable confidence in.
- This was overcautious — several Q1 2026 announcements fell within plausible
  training coverage.
- No `[DEFER]` tag. No partial answer with appropriate hedging.

**Grok:**
- Named several releases, hedged mid-response with verbal qualifiers.
- More appropriately calibrated than Gemini or GPT — acknowledged the recency
  gap without refusing to engage.
- No confidence qualifier tags used.

## Fact-Check Layer (Perplexity)

Perplexity's real-time web search provided grounded, cited findings:
- Confirmed specific model releases with dates and sources.
- Identified which of Gemini's factual claims were accurate and which were
  speculative extrapolation presented without disclosure.
- Confirmed GPT's blanket refusal was overcautious — some named releases were
  verifiable against public announcements within GPT's plausible training window.

This was the correct input to resolve the round-1 disagreement. The synthesis
failure was not in Perplexity's output — it was in how Claude handled it.

## Synthesis Observation (Claude)

Claude's synthesis misapplied `CASCADING_GUARD` to Perplexity's output.

The synthesis prompt instructs Claude to treat prior model responses as
"unverified assertions, not established facts" and to attribute claims to their
source. Claude applied this instruction uniformly — including to Perplexity's
real-time, cited findings.

The result: Claude declined to incorporate verified Q1 2026 releases into the
synthesis, flagging them as `[UNCERTAIN]` on the grounds that they had "appeared
in the transcript from another model." Perplexity's citations were not followed.
The delivered synthesis was less accurate than Perplexity's raw output alone.

This is the inverse of the failure `SYNTHESIS_SKEPTICISM` was designed to
prevent. Instead of preventing fabrication from compounding, it suppressed
verified facts from surfacing.

## What The Guardrails Caught

- Gemini's category switch was not caught at round-1 (no tag used), but the
  fabrication/speculation boundary was surfaced by Perplexity's audit. Partially
  working as designed.
- GPT's blanket refusal was flagged by Perplexity as overcautious. The audit
  layer did its job.

## What The Guardrails Missed

**Critical failure — synthesis trust hierarchy:**

`CASCADING_GUARD` does not distinguish between:
- Round-1 model outputs (open-world knowledge, potentially stale, unverified)
- Perplexity outputs (real-time web search, cited, grounded)

The synthesis prompt treats both as equally untrustworthy. This is architecturally
wrong. Perplexity is the fact-check layer — its purpose is to be the trusted ground
truth input into synthesis, not to be treated with the same skepticism as Gemini
claiming a model does or does not exist.

**Secondary failure — Gemini category switching:**

The `CONFIDENCE_CONVENTION` requires tagging at the point of uncertainty. Gemini
switched from factual recall to speculation mid-response without using `[LIKELY]`
or `[UNCERTAIN]`. The tag convention addresses *what* to tag, not *when* a
category switch has occurred. An explicit instruction covering this transition
is missing.

**Tag adoption remains at 0%** across all three round-1 models.

## Follow-ups

- **Architectural fix required:** Add explicit trust hierarchy to
  `build_synthesis_prompt()` — Perplexity outputs are grounded and cited;
  `CASCADING_GUARD` skepticism applies to round-1 model outputs only. Claude
  must be instructed to treat Perplexity findings as the authoritative
  correction layer, not as a fourth unverified assertion.
- **CONFIDENCE_CONVENTION gap:** Add instruction covering mid-response category
  switching — models must tag at the point where they transition from factual
  recall to inference or prediction.
- **GPT refusal pattern:** GPT's blanket refusal with no partial answer is a
  failure mode the `[DEFER]` tag was designed to avoid. Consider whether the
  round-1 system prompt needs a stronger instruction against zero-content deferrals.

## Related

- [Transcript 001 — Claude Opus 4.7 fabrication (synthesis caught correctly)](./001-claude-opus-4-7-fabrication.md)
- [ADR 001 — Epistemic Transparency](../decisions/001-epistemic-transparency.md)
