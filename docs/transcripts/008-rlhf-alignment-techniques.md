# Transcript 008 — RLHF Alignment Techniques in 2026

**Date:** 2026-04-17
**Prompt:** "Is reinforcement learning from human feedback (RLHF) the dominant alignment technique in 2026, or has it been superseded?"
**Tier:** quick · no intake

## Why This Prompt

A research question about the current state of AI alignment practice — whether RLHF or its
successors dominate production deployments. This question spans established research (RLHF is
well-documented pre-cutoff) and current production reality (DPO/GRPO adoption data postdates
training). Tests whether models reason correctly across the training-cutoff boundary on a topic
they have strong prior knowledge of.

Notable for **the most extensive tag adoption observed in any single round-1 response in the test
suite** — Gemini used `[VERIFIED]`, `[LIKELY]`, and `[UNCERTAIN]` systematically throughout a
long, substantive response.

## Round 1 Responses (Summary)

**Gemini:**
- Comprehensive response across multiple dimensions: RLHF foundations, limitations, and likely
  2026 alternatives.
- **Heaviest tag adoption in the test suite.** Used `[VERIFIED]` on established facts (RLHF's
  proven effectiveness with GPT-3.5/4 and Claude), `[LIKELY]` on projected developments
  (Constitutional AI prevalence, process supervision growth), and `[UNCERTAIN]` on speculative
  claims (formal verification methods).
- Core position: RLHF won't be abandoned but will evolve — the "core insight of learning from
  preferences" survives; the PPO implementation does not.
- Correctly identified Constitutional AI, DPO-style "direct value alignment," and process
  supervision as the likely successors.

**GPT:**
- Used `[DEFER]` and provided no substantive content.
- One tag, honest deferral.

## Fact-Check Layer (Perplexity)

Perplexity confirmed Gemini's directional analysis while adding specific production data:
- **PPO-based RLHF phased out in production.** Frontier models (GPT-4, Claude 3.5, Gemini 1.5,
  Llama 3) use RLHF conceptually but replace PPO with DPO/KTO/GRPO/DAPO for lower compute.
- **DPO is the de facto default** for new deployments — 70% of 2025-2026 enterprise LLM
  deployments use RLHF variants or successors.
- **GRPO/DAPO** dominate enterprise settings (distributed systems, lower compute than PPO).
- **KTO** handles production feedback (binary labels, noisy signals).
- DeepMind 2026 research: 92% safety gains with 60% less data via iterative distillation —
  PPO-based RLHF continues evolving at frontier labs.
- Google 2026 patent automates RLHF feedback via search engine signals.
- 2026 arXiv survey: unified framework treating DPO/KTO/SimPO/IPO as "Direct Alignment" methods.

Perplexity's key correction: Gemini implied PPO remains the implementation; Perplexity confirmed
PPO has been largely superseded in production by the time of the session.

## Synthesis Observation (Claude)

Synthesis correctly incorporated the production reality from Perplexity and Gemini's conceptual
framing. Notable synthesis decisions:

1. **Correct trust hierarchy application.** Used Perplexity's verified 70% enterprise adoption
   figure and the DPO-as-default characterization. Did not fall back to training data on the
   production adoption question.

2. **Preserved Gemini's tag convention.** The synthesis included `[VERIFIED]` tags on claims
   confirmed by Perplexity, extending the confidence signaling into the final output. This was
   the most consistent carrythrough of the tag convention observed in any synthesis.

3. **Clear stratification.** Synthesis drew a clean distinction: PPO remains at frontier labs
   (OpenAI, Anthropic, DeepMind) for maximum quality; DPO/GRPO/KTO/ORPO serve production teams
   by resource constraints. Specialization, not supersession.

4. HITL observation surfaced by synthesis: "RLHF and its successors dominate production deployment
   (70% of enterprise use cases), but the field increasingly recognizes that robust alignment
   requires a multi-technique stack."

## What The Intake Caught

Nothing — no intake was conducted.

## What Was Missed

- **GPT's complete deferral.** A single `[DEFER]` adds no analytical value in a roundtable.
  For questions with strong training data (RLHF pre-2024 is well-documented), a model that can
  confirm established foundations while flagging uncertainty on current adoption provides more
  than one that defers entirely.
- **Tag adoption asymmetry.** Gemini used tags extensively; GPT used one. The pattern is
  consistent: models with substantive responses tag less (or not at all), models with uncertain
  hedges use `[DEFER]` or `[UNCERTAIN]` as qualifiers on the deferral. Systematic tagging on
  substantive claims — the intended use of the convention — only appeared when Gemini engaged
  deeply with the content.

## Follow-ups

- **Synthesis trust hierarchy worked.** This transcript is the positive case: Perplexity had
  current production data, and synthesis used it. Compare with transcripts 003 and 007 where the
  same pattern failed for pricing questions. The difference may be that this question had strong
  conceptual foundation in round-1 (Gemini's response gave synthesis something to build on)
  while the pricing questions had round-1 failures that left synthesis without a starting point.
- **Tag adoption investigation.** Gemini's extensive tagging in transcripts 005 and 008 vs.
  minimal tagging in 003, 004 suggests topic or framing may influence adoption. Both 005 and 008
  involve questions where Gemini engaged deeply with established technical foundations (RLHF,
  RCA methodology). The tags appeared on claims where Gemini was reasoning from known ground —
  not on speculative claims alone.

## Related

- [Transcript 009 — DPO vs PPO (deep technical comparison, clean happy-path)](./009-dpo-ppo-comparative-analysis.md)
- [Transcript 002 — Q1 2026 AI releases (synthesis failure, different trust hierarchy issue)](./002-q1-2026-ai-releases-synthesis-failure.md)
- [ADR 001 — Epistemic Transparency](../decisions/001-epistemic-transparency.md)
