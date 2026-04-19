# ADR 002: Synthesizer Model Selection

**Status:** Accepted  
**Date:** 2026-04-17

## Context

ai-roundtable uses a single model to synthesize round-1 research responses from
four labs (Gemini, GPT, Grok, Claude) plus a Perplexity fact-check audit into a
final deliverable.

Two failure modes were observed during development:

1. **Post-cutoff refusal** — Claude refused to incorporate Perplexity's
   live-cited data about post-training-cutoff events (model releases, pricing,
   deprecations), calling verified data "fabricated information."

2. **Cascading hallucination** — Without explicit skepticism rules, synthesis
   would treat round-1 model claims as established facts rather than unverified
   assertions requiring attribution.

An empirical evaluation harness was built and run against six candidates
(see `experiments/synthesizer_eval/`): Claude Opus 4.7, Claude Sonnet 4.6,
Claude Haiku 4.5, GPT-4o, Qwen 2.5 72B, and Llama 3.3 70B.

## Evaluation Results

Tests used fixed inputs — identical round-1 responses and Perplexity audit —
across all candidates. Three tests:

- **T1 — Factual (post-cutoff pricing):** The failure case. Perplexity data
  contradicts round-1 stale pricing. Synthesis must defer to Perplexity.
- **T2 — Analytical (RLHF alignment):** The working case. No post-cutoff data
  conflict. Tests attribution, depth, and confidence tag adoption.
- **T3 — Domain technical (ISO-NE offshore wind):** The showcase case. Dense
  domain knowledge with no factual contradictions. Tests synthesis narrative quality.

Six scoring dimensions per test (1–5 each, max 30/test, max 90 total):
factual grounding, attribution, contradiction handling, analytical depth,
tag adoption (`[VERIFIED]`/`[LIKELY]`/`[UNCERTAIN]`/`[DEFER]`), actionability.

### v1 Eval (6 candidates, human scoring /90)

| Rank | Model | T1 | T2 | T3 | Total | Verdict |
|------|-------|----|----|----|-------|---------|
| 1 | Claude Opus 4.7 | 29 | 30 | 30 | 89/90 | PASS |
| 2 | Qwen 2.5 72B | 26 | 28 | 28 | 82/90 | PASS |
| 2T | Llama 3.3 70B | 26 | 28 | 28 | 82/90 | PASS |
| 4 | GPT-4o | 25 | 27 | 28 | 80/90 | PASS |
| 5 | Gemini 2.5 Pro | 26 | 24 | 28 | 78/90 | TRUNCATED |
| 6 | DeepSeek V3 | 23 | 28 | 9 | 60/90 | FAIL |

### v2 Eval (5 candidates, automated scoring with cost)

Sonnet 4.6 and Haiku 4.5 added. Quick tier removed — Smart/Deep only.
Automated scoring: 12 programmatic assertions (structural, attribution, tag presence).

| Model | Auto Score | Cost/session | 1K sessions |
|-------|------------|--------------|-------------|
| Claude Haiku 4.5 | 83.3% | $0.00558 | $5.58 |
| GPT-4o | 83.3% | $0.00730 | $7.30 |
| Qwen 2.5 72B | 83.3% | $0.00131 | $1.31 |
| Claude Opus 4.7 | 75.0% | $0.04357 | $43.57 |
| Claude Sonnet 4.6 | 75.0% | $0.02343 | $23.43 |

The auto/human scoring inversion (Haiku 83% auto vs Opus 89/90 human) reflects
what automated checks cannot capture: analytical depth, narrative structure, and
the quality of uncertainty attribution. Auto scoring measures structure;
human scoring measures substance.

## Decision

**Two-model synthesis routing based on query type.**

**Analytical queries** (RLHF, architecture, domain knowledge, expert opinion):
→ Claude Opus 4.7 (`SYNTHESIS_ANALYTICAL`)

Claude leads on analytical depth (30/30 on T2 and T3), attribution quality,
confidence tag adoption, and narrative coherence. No other candidate matched
this across all three test dimensions.

**Post-cutoff factual queries** (pricing, model releases, deprecations, current
events where Perplexity contradicts round-1):
→ GPT-5.4 (`SYNTHESIS_FACTUAL`)

Claude's trained refusal behavior fires on post-cutoff data regardless of system
prompt instructions — confirmed across 8 sessions and 4 prompt variants.
GPT-5.4 incorporates Perplexity grounded data without trained refusal.

**Routing logic** (`perplexity_contradicts_round1()` in `backend/router.py`):
If the Perplexity audit contains signals such as "retired", "deprecated",
"incorrect", "as of 2026", "current pricing", or direct contradiction markers,
route to `SYNTHESIS_FACTUAL`. Otherwise route to `SYNTHESIS_ANALYTICAL`.

**Fallback** (any synthesis failure):
→ Qwen 2.5 72B (`SYNTHESIS_FALLBACK`)

Scored 82/90 human, 83.3% automated, $1.31/1K sessions. Viable open-weight
fallback on a different provider with no shared failure mode with the primary chain.

## Consequences

- Synthesis routing adds one classification step per session — negligible latency
- Claude Opus 4.7 handles the majority of sessions; GPT-5.4 handles the specific
  failure class where Claude's training data refusal would otherwise surface
- `PipelineHealth` tracks which model handled synthesis and the routing reason,
  surfaced as read-only annotations in the frontend after synthesis completes
- DeepSeek V3 excluded — pivoted to Chinese-language RAM content mid-synthesis on
  T3 (domain-technical prompt); root cause unknown, excluded without further investigation
- Gemini 2.5 Pro excluded — T2 output truncated, context limit suspected; also
  introduces synthesis bias since Gemini already holds a round-1 research seat
- Llama 3.3 70B not included in production chain — performance tied Qwen at 82/90
  but Qwen was selected as fallback for broader language coverage and consistent
  OpenRouter availability
- The eval harness (`experiments/synthesizer_eval/`) is the regression guard —
  run it when changing synthesis system prompts or switching models

## Alternatives Considered

**Single synthesizer (Claude only):** Rejected. Claude's trained refusal on
post-cutoff data is a structural limitation that prompt engineering cannot override.
Confirmed empirically across 8 sessions and 4 prompt variants — the refusal is not
a prompt problem, it is a training problem.

**Single synthesizer (GPT-5.4):** Rejected. GPT-4o scored 80/90 human vs Claude's
89/90. The analytical quality gap is real and user-visible on complex domain
questions. Optimal synthesis on the majority case should not be sacrificed to handle
the edge case.

**Perplexity as synthesizer:** Deferred. Search-native design may produce
citation-heavy but narratively weak synthesis. Not tested in this eval — worth
revisiting if routing complexity becomes a maintenance burden.

**Tier-specific synthesizer (Haiku for Smart, Opus for Deep):** Rejected. Cost
optimization at the synthesis layer is premature — synthesis is called once per
session and is not the dominant cost driver. Haiku's 83.3% automated score
conceals structural deficiencies that human scoring would likely catch at T2 depth.

## Evidence

Transcripts in `docs/transcripts/` document synthesis behavior across 15 real
sessions including failure cases (sessions 007, 008, 013) and successful cases
(003, 005, 006, 009, 010, 011, 012). Session 013 is the index case for Claude's
post-cutoff refusal on live Perplexity pricing data.
