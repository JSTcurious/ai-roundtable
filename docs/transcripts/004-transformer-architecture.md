# Transcript 004 — Transformer Architecture Dominance in 2026

**Date:** 2026-04-17
**Prompt:** "Is transformer architecture still dominant in frontier LLMs in 2026, or have alternatives taken over?"
**Tier:** smart · no intake

## Why This Prompt

A contemporary technical question requiring models to reason about current (April 2026) developments
that postdate training cutoffs. Tests how models handle temporal uncertainty — whether they defer,
speculate, or produce responses that are directionally correct but under-tagged.

Secondary purpose: validate that a forward-looking technical question with established fundamentals
gets smart tier rather than deep (no high-stakes decision involved, just a research question).

## Round 1 Responses (Summary)

**Gemini:**
- Strong substantive response predicting hybrid architectures (Transformer + SSM) as the 2026 norm.
- Correctly identified MoE, SSMs, and the quadratic scaling problem as the drivers of architectural
  evolution.
- Used explicit hedging ("The transformer architecture will not have been 'taken over'") but no
  confidence tags.
- Prediction framing ("by 2026... will likely...") reflected training data context — Gemini was
  reasoning forward, not reporting current state.

**GPT:**
- Used `[UNCERTAIN]` qualifier — the first confidence tag observed in any round-1 response across
  the test suite.
- Acknowledged lack of 2026-specific information and deferred.
- Structurally honest but provided no useful technical content.

## Fact-Check Layer (Perplexity)

Perplexity confirmed and extended Gemini's directional prediction with current production data:
- Hybrid architectures confirmed: Jamba, Hymba, Qwen3-Next in production
- MoE as standard: 60%+ of 2025 frontier releases used MoE; DeepSeek-V3 demonstrates the pattern
- SSM integration confirmed: Phi-4-mini-flash-reasoning ships with 75% Mamba layers
- Corrected Gemini's timing: MoE adoption accelerated faster than "gradually taking over" framing
  — by Q4 2025 it was already de facto standard
- Added material omission: Diffusion LLMs emerging (Gemini Diffusion at 1,479 tokens/second via
  parallel generation) — not mentioned by either model
- Flagged persistent challenges: "lost in the middle" problem is a geometric property of attention,
  not a training artifact; 20-30% mid-context accuracy drop persists
- Dense scaling plateau confirmed: OpenAI spent $500M+ on Orion pre-training; hit GPT-4 performance
  at 20% of training, then diminishing returns

Perplexity assessment: Gemini's core prediction was correct but understated MoE adoption speed.
GPT's `[UNCERTAIN]` tag was appropriate given training cutoff but unhelpful.

## Synthesis Observation (Claude)

Synthesis was high quality — correctly incorporated Perplexity's production details and produced
a coherent, current-state analysis. Notable observations:

1. Correctly updated Gemini's prediction framing to present-tense reporting, incorporating the
   production data from Perplexity's audit.
2. Introduced the "Densing Law" (capability per parameter doubles every 3.5 months) as the new
   competitive metric replacing raw scale.
3. Surfaced the paradigm shift clearly: "The revolution already happened. It just looked like evolution."

The synthesis synthesized correctly — it did not summarize round-1 outputs; it produced an
integrated, current-state view that would have been impossible from any single model's response.

No HITL observations were surfaced. The round-1 + audit combination produced sufficient consensus
that no competing framings required chair arbitration.

## What The Intake Caught

Nothing — no intake was conducted. Direct question submitted.

## What Was Missed

- **Tag adoption: 1 of 2 models.** GPT used `[UNCERTAIN]` appropriately. Gemini produced a
  detailed technical response with multiple uncertain claims about 2026 production state — none
  tagged. The asymmetry is notable: the model that engaged more deeply tagged less.
- **Diffusion LLMs absent from round-1.** Both models missed this emerging class entirely.
  Perplexity surfaced it. This is a pattern: post-2025 developments are underrepresented in
  training data and depend on Perplexity for coverage.

## Follow-ups

- GPT's single `[UNCERTAIN]` tag is the first confidence tag observed in the test suite (across
  transcripts 001-004). It was appropriate. The question is whether this was deliberate or
  coincidental — GPT deferred entirely, so the tag may reflect "I don't know" rather than
  calibrated epistemic labeling.
- Gemini's prediction-framing-as-current-state is a consistent pattern. When models have relevant
  training data they speculate forward without signaling the epistemic shift from "I know this"
  to "I'm predicting this."

## Related

- [Transcript 009 — DPO vs PPO (established ML research, no temporal uncertainty)](./009-dpo-ppo-comparative-analysis.md)
- [ADR 001 — Epistemic Transparency](../decisions/001-epistemic-transparency.md)
