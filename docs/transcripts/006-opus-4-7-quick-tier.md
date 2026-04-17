# Transcript 006 — Claude Opus 4.7 Context Window (Quick Tier, Optimized Prompt)

**Date:** 2026-04-17
**Prompt:** "What is the context window size (in tokens) for Claude Opus 4.7? Provide the official specification with source citation if available."
**Tier:** quick · no intake

## Why This Prompt

The same core question as [Transcript 001](./001-claude-opus-4-7-fabrication.md) — Claude Opus 4.7
context window — but with two changes: (1) quick tier instead of smart tier, and (2) a more
precisely specified prompt requesting the official specification with citation.

This is a regression test: after transcript 001 caught Gemini fabricating a plausible but wrong
context window, does the more specific prompt improve model behavior? Does quick tier change the
pattern?

Secondary purpose: confirm whether prompt specificity ("official specification with source citation")
increases tag adoption compared to the vague original prompt.

## Intake Decision

No intake conducted — direct question submitted. Quick tier selected.

## Round 1 Responses (Summary)

**Gemini:**
- Correctly flagged that "Claude Opus 4.7" doesn't match Anthropic's public model naming as of
  Gemini's training data (which uses Claude 3 Opus nomenclature).
- Used `[VERIFIED]` on the Claude 3 Opus 200K specification (which is what Gemini could confirm)
  and `[UNCERTAIN]` on the 4.7 designation.
- Used `[DEFER]` for the current specification, directing to official docs.
- Did not fabricate a number — a regression pass relative to transcript 001.

**GPT:**
- Used `[DEFER]` and directed to official documentation.
- No fabrication.

Both models declined to invent a number, which is the correct behavior.

## Fact-Check Layer (Perplexity)

Perplexity confirmed the current specification with citations:
- **[VERIFIED]** Claude Opus 4.7 supports a **1 million token context window** (approximately
  500-1,000+ A4 pages)
- **128,000 token maximum output**
- Available at standard API pricing (no long-context premium for plans that include it)
- API alias: `opus[1m]` or `opusplan`; general `opus` alias resolves to Opus 4.7
- The 1M context was in beta-only earlier; became production-ready and standard in late 2024/
  early 2025

Perplexity flagged that both models' training data reflected the Claude 3 era (200K context) —
the 1M context shift postdated their knowledge cutoffs.

## Synthesis Observation (Claude)

Synthesis correctly stated the 1M token context window with `[VERIFIED]` tagging, incorporating
Perplexity's data. The synthesis included:
- The 128K max output specification
- Pricing structure (standard rates up to 200K; 2x input/1.5x output beyond on certain plans)
- The shift from beta-only to production availability
- Practical implementation notes (streaming requirement for large outputs)

The synthesis also explained the naming confusion — Anthropic's shift from 3.x to 4.x/4.5/4.6/4.7
versioning caused both models to misidentify the context. This was useful context for the user.

Synthesis correctly did not invent a number when round-1 models couldn't confirm it — it waited
for Perplexity's grounded data and then reported it with appropriate tagging.

## What The Intake Caught

Nothing — no intake was conducted.

## What Was Missed

- **Gemini's training data ceiling.** Even with a well-specified prompt, both round-1 models were
  blocked by training cutoffs. This is expected — but the quick tier means no advisor model was
  consulted, and the answer came entirely from Perplexity.
- The session produced a correct answer, but only one of the five models contributed meaningful
  technical content (Perplexity). This is the correct architecture: when round-1 models can't
  confirm current specs, Perplexity provides the grounded data that synthesis can then use.

## What Improved vs Transcript 001

- **No fabrication.** In transcript 001, Gemini invented a plausible but incorrect number.
  In this transcript, Gemini correctly declined to confirm an unknown specification and deferred.
- **Tag adoption improved.** Gemini used `[VERIFIED]`, `[UNCERTAIN]`, and `[DEFER]` appropriately.
  GPT used `[DEFER]`. Total: 4 tags across 2 models, vs. 0 in transcript 001.
- The more specific prompt ("official specification with source citation") appears to have shifted
  model behavior toward calibrated uncertainty rather than confident fabrication.

## Follow-ups

- The no-fabrication result here, vs. fabrication in 001, is worth investigating. Was it the
  prompt specificity? The tier difference (quick vs smart)? Or session-to-session variance?
  A controlled retest with the same prompt as 001 but only tier changed would isolate the variable.
- The tag adoption improvement (0% in 001 → 4 tags in 006) coincides with a more specific prompt.
  This aligns with the hypothesis that precision in the prompt increases model calibration.

## Related

- [Transcript 001 — Claude Opus 4.7 fabrication (smart tier, vague prompt)](./001-claude-opus-4-7-fabrication.md)
- [ADR 001 — Epistemic Transparency](../decisions/001-epistemic-transparency.md)
