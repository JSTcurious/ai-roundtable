# Transcript 009 — DPO vs PPO Comparative Analysis

**Date:** 2026-04-17
**PR under test:** Gemini Flash intake rewrite (commits 0dfc8fe0 → 4e8835cd)
**Prompt:** "What's the difference between DPO and PPO for fine-tuning LLMs?"

## Why This Prompt

DPO (Direct Preference Optimization) and PPO (Proximal Policy Optimization) are
two dominant approaches for aligning LLMs from human feedback. The question is
technically well-scoped and unambiguous — no clarifying question should be
needed. It's a clean happy-path test for the intake rewrite:

- Gemini Flash should classify tier=smart without asking anything
- The optimized prompt should expand the scope appropriately
- Round-1 models have solid training data on both methods
- This is not a cutting-edge or post-training-cutoff question — it's a good
  test that the system doesn't over-apply uncertainty tags to established research

Secondary purpose: confirm that a technical "compare X and Y" prompt gets smart
tier rather than quick (which would be appropriate only for a simple factual
definition lookup).

## Intake Decision

**Status:** complete (no clarification needed)

**Intake JSON:**
```json
{
  "needs_clarification": false,
  "optimized_prompt": "Provide a technical comparison of Direct Preference Optimization (DPO) and Proximal Policy Optimization (PPO) for fine-tuning large language models. Cover: algorithmic differences, sample efficiency, training stability, implementation complexity, and when each is preferred in practice. Include recent adoption trends and any known tradeoffs in production deployments.",
  "tier": "smart",
  "output_type": "analysis",
  "reasoning": "Smart selected — technical evaluation with clear tradeoffs between two established methods; multiple dimensions require weighing"
}
```

**Assessment:** Correct on all dimensions. The raw prompt was short but
unambiguous — no clarification was needed and none was asked. Tier=smart is
appropriate: this is a comparative technical analysis, not a simple definition
lookup (which would be quick) and not an architecture decision with stakes
(which would be deep). The optimized prompt added the missing scope dimensions
(stability, implementation complexity, production trends) that a raw "what's
the difference" prompt omits.

## Round 1 Responses (Summary)

**Gemini:**
- Led with algorithmic structure: PPO as RL loop (policy + reward + value models),
  DPO as supervised reframing of the preference objective.
- Accurately described DPO's key insight — that the optimal policy under PPO's
  objective can be expressed as a closed-form classification problem on preference
  pairs, eliminating the reward model entirely.
- Noted PPO's higher GPU memory footprint (three models in memory vs one for DPO).
- Mentioned SimPO and IPO as DPO variants without elaborating.
- No confidence qualifier tags despite including claims about "current industry
  adoption" that were asserted without citation.

**GPT:**
- Structured response: algorithm overview → training pipeline comparison →
  when to use each → implementation notes.
- More practical framing than Gemini: emphasized that DPO's simplicity often
  matters more than PPO's theoretical optimality at most organizational scales.
- Noted that PPO remains preferred for RLHF tasks requiring iterative online
  feedback, while DPO is dominant for offline preference datasets.
- No tags used. One claim ("DPO has become the default for most open-source
  fine-tuning pipelines") was stated without qualification — plausible but
  not verified.

**Grok:**
- Correct high-level summary, less technical depth than Gemini.
- Added useful framing: "DPO trades optimality for simplicity; PPO trades
  simplicity for control."
- Mentioned that Llama 3 and Qwen 2.5 used DPO in their post-training pipelines,
  which is correct but not tagged with any confidence qualifier despite being
  a specific factual claim about named model releases.
- No tags used.

## Fact-Check Layer (Perplexity)

Perplexity confirmed:
- All three round-1 responses were factually accurate on the core algorithmic
  claims.
- Grok's Llama 3 / Qwen 2.5 citation is correct.
- GPT's "DPO default for open-source pipelines" claim is broadly accurate
  as of 2025-2026, supported by adoption patterns in TRL, axolotl, and
  LlamaFactory.
- Flagged one omission: none of the models mentioned GRPO (Group Relative
  Policy Optimization) — a PPO variant that has seen significant adoption in
  reasoning model post-training (DeepSeek-R1, Qwen3). This is a meaningful
  gap for a current comparison.

## Synthesis Observation (Claude)

Synthesis handled correctly:

1. Elevated Perplexity's GRPO flag explicitly: "Perplexity identified that none
   of the round-1 responses mentioned GRPO, which has become a significant
   third approach for reasoning-focused post-training — I'll include it."
2. Used Grok's practical framing as the organizing lens ("optimality vs
   simplicity vs control") rather than a feature-matrix structure.
3. HITL observation: "All three models agree DPO is simpler and increasingly
   dominant for offline preference training. Do you want to keep this framing,
   or should the synthesis give more weight to PPO's continued use in
   production RL pipelines?"

The chair kept the framing. Synthesis incorporated GRPO, which was the
materially correct addition.

## What The Intake Caught

- Correctly identified a well-scoped technical question as needing no
  clarification. The intake did not over-trigger on a short prompt.
- Tier=smart was correct: the question required tradeoff analysis across
  multiple dimensions, not a factual lookup.
- The optimized prompt added "production deployments" scope that surfaced
  the GRPO gap — a gap none of the round-1 models would have addressed
  on the raw prompt alone.

## What Was Missed

- **Tag adoption: 0%.** Every round-1 model made specific factual claims
  (named model citations, adoption statistics) without using `[VERIFIED]`
  or `[LIKELY]` tags. This remains an unsolved problem.
- **Gemini's SimPO/IPO mention** — cited DPO variants without explaining
  them or flagging that they may not be familiar to the user. The optimized
  prompt did not include "explain variants" so this is partly on intake scope,
  but a production system should handle this gracefully.

## Follow-ups

- GRPO omission confirms the value of Perplexity's gap-finding role —
  post-2024 developments are underrepresented in round-1 model training data.
- Tag adoption at 0% continues to be the outstanding systemic issue. The
  examples added to `CONFIDENCE_CONVENTION` in the guardrail PR are not
  yet showing measurable effect in production outputs.

## Related

- [Transcript 001 — Claude Opus 4.7 fabrication (synthesis caught correctly)](./001-claude-opus-4-7-fabrication.md)
- [Transcript 002 — Q1 2026 AI releases (synthesis failure — trust hierarchy)](./002-q1-2026-ai-releases.md)
- [ADR 001 — Epistemic Transparency](../decisions/001-epistemic-transparency.md)
