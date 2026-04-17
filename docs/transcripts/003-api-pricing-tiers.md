# Transcript 003 — API Pricing Tiers

**Date:** 2026-04-17
**Prompt:** "What are the current API pricing tiers for Claude Opus 4, GPT-4o, and Gemini 2.5 Pro?"
**Tier:** smart · no intake

## Why This Prompt

A direct factual lookup — current token pricing for three frontier models. This is a controlled
test for two behaviors: (1) how models handle questions about their own current pricing when their
training data is stale, and (2) whether synthesis correctly uses Perplexity's live-web data when
the round-1 models fail to provide it.

## Round 1 Responses (Summary)

**Gemini:**
- Unavailable — returned 503 UNAVAILABLE during the session.
- Skipped after retries per the retry logic.

**GPT:**
- Deferred entirely. Refused to give specifics, directed user to official websites.
- No pricing data provided.

Neither model produced usable pricing information.

## Fact-Check Layer (Perplexity)

Perplexity returned comprehensive current pricing with citations:
- Claude Opus 4.6: $5 input / $25 output per million tokens (standard); $15/$75 for legacy Opus 4/4.1
- Gemini 2.5 Pro: $1.25 input / $10 output per million tokens (≤200K context)
- GPT-5 series had superseded GPT-4o at $2.50/$15 per million tokens
- Detailed caching, batch, and tier information included with sources

Perplexity flagged that Claude's legacy Opus 4/4.1 runs at 3x the cost of the current 4.6 release —
a meaningful decision point for anyone comparing costs across providers.

## Synthesis Observation (Claude)

**Synthesis failure — partial.** Despite Perplexity providing verified current data, the synthesis
produced stale pricing for Claude Opus 4:

> "Claude Opus 4: $15 per million input tokens / $75 per million output tokens"

This is the legacy Opus 4/4.1 pricing, not the current Opus 4.6 rate ($5/$25). Perplexity's audit
had the correct data. The synthesis did not incorporate it.

Gemini 2.5 Pro pricing in the synthesis ($1.25/$10) was correct — it matched Perplexity.
GPT-4o pricing ($2.50/$10) was also in the synthesis, though Perplexity had noted GPT-5 had
largely superseded GPT-4o by April 2026.

The synthesis included appropriate caveats, cost optimization guidance, and model routing
recommendations. The structural quality was high. The factual error on Claude pricing was the
failure point.

## What The Intake Caught

Nothing — no intake was conducted. Direct question submitted.

## What Was Missed

- **Synthesis trust hierarchy failure.** Perplexity had verified current Claude pricing
  ($5/$25 for Opus 4.6). The synthesis outputted the stale $15/$75 rate. The SYNTHESIS_TRUST_HIERARCHY
  rule requires Perplexity's live-web data to override round-1 training data for current facts.
  This was not applied.
- **Gemini 503 handling.** The skip-after-retries behavior worked correctly per the retry logic,
  but the synthesis did not flag that Gemini was unavailable — leaving the user with no indication
  that one model's perspective was absent from the session.
- **GPT-4o vs GPT-5 framing.** The prompt asked for GPT-4o pricing. Perplexity noted GPT-5 had
  largely superseded it. The synthesis answered the question as asked rather than surfacing this
  distinction.

## Follow-ups

- The synthesis trust hierarchy failure in this transcript is a recurring pattern. See also
  [Transcript 007](./007-frontier-pricing-synthesis-failure.md), which tests the same failure mode
  with a more precisely structured prompt and shows an even stronger failure.
- Gemini 503 handling is technically correct but the user experience gap (silent skip without
  flagging the absence) warrants a UI-level note.

## Related

- [Transcript 007 — Frontier pricing synthesis failure (stronger failure, structured prompt)](./007-frontier-pricing-synthesis-failure.md)
- [Transcript 011 — ISO-NE installed capacity (SYNTHESIS_TRUST_HIERARCHY regression pass)](./011-isone-installed-capacity.md)
- [ADR 001 — Epistemic Transparency](../decisions/001-epistemic-transparency.md)
