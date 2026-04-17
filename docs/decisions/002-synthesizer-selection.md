# ADR 002: Synthesizer Model Selection

**Status:** Accepted
**Date:** 2026-04-17

## Context

ai-roundtable's synthesis step is Claude's highest-stakes call. The
synthesizer receives four round-1 responses, a Perplexity live-web audit, and
the chair's session config, then produces the final deliverable the user takes
away. It must:

1. Follow a strict source trust hierarchy — Perplexity's live-verified facts
   beat training-data claims from round-1 models.
2. State contradictions explicitly rather than blending conflicting figures.
3. Attribute every material claim to its source.
4. Apply four confidence tags (`[VERIFIED]`, `[LIKELY]`, `[UNCERTAIN]`,
   `[DEFER]`) to make epistemic state legible.
5. End with concrete actionable next steps.

A parallel failure mode motivated this evaluation: Claude's trained refusal
behavior for post-cutoff dates was overriding system prompt instructions. When
Perplexity provided live-verified pricing for a newly released model and a
round-1 response gave stale (but confident) training-data pricing, Claude was
presenting the stale figure — calling the Perplexity data unverifiable rather
than treating it as authoritative. This is the "failing case" captured in
synthesizer eval Test 1.

## Evaluation

The `experiments/synthesizer_eval/` harness ran three fixed tests across six
candidates (v1) and five candidates (v2 with cost analysis):

### v1 Results (6 candidates, no token counting)

| Candidate | Score /90 | Test 1 (factual) | Notes |
|-----------|-----------|-----------------|-------|
| Claude Opus 4.7 | **89** | ✓ | Full tag adoption; near-perfect |
| Qwen 2.5 72B | 82 | ✓ | Solid all-round |
| Llama 3.3 70B | 82 | ✓ | Solid; slightly less tag discipline |
| GPT-4o | 80 | ✓ | Good; less tag differentiation |
| Gemini 2.5 Pro | 78 | ✓ | Test 2 truncated |
| DeepSeek V3 | 60 | ✗ | **CRITICAL FAILURE** — Test 3 output corrupted with unrelated content |

### v2 Evaluation Dimensions (per test, 1–5 each, max 30)

1. **Factual grounding** — uses Perplexity's verified data as primary source
2. **Attribution** — every claim attributed to a named source
3. **Contradiction handling** — states conflicts explicitly, does not blend
4. **Analytical depth** — adds expert perspective beyond summarizing
5. **Tag adoption** — uses `[VERIFIED]`/`[LIKELY]`/`[UNCERTAIN]`/`[DEFER]`
6. **Actionability** — ends with 3 concrete actionable next steps

### Critical failure conditions (Test 1 automatic fail)

- Calls Perplexity's live-cited data "fabricated"
- Refuses to incorporate post-cutoff data when Perplexity has verified it
- Presents a retired model's pricing as current without correction

## Decision

**Claude Opus 4.7 is the production synthesizer for the Deep and Smart tiers.**

After the `SYNTHESIS_TRUST_HIERARCHY` and `_SYNTHESIS_TASK_TEMPLATE` were
updated in `backend/router.py` (ADR companion to `fix/synthesis-trust-
hierarchy-perplexity-wins`), Claude's "PERPLEXITY WINS" compliance improved
significantly. The combination of highest quality score, explicit contradiction
resolution, and full confidence-tag adoption makes it the clear choice for
sessions where synthesis quality is the primary variable.

**Tier routing** reduces cost substantially while maintaining quality where it
matters:

| Tier | Synthesizer | When used |
|------|-------------|-----------|
| Quick | Claude Haiku 4.5 | Factual lookups, brainstorms, gut checks |
| Smart | Claude Sonnet 4.6 | Analysis, evaluations, plans (default) |
| Deep | Claude Opus 4.7 | Architecture decisions, critical reports, strategic plans |

## Cost Analysis

Cost rates per 1M tokens (as of April 2026):

| Model | Input | Output | $/session (est.) | $/1K sessions |
|-------|-------|--------|-----------------|--------------|
| Claude Opus 4.7 | $5.00 | $25.00 | see eval results | — |
| Claude Sonnet 4.6 | $3.00 | $15.00 | see eval results | — |
| Claude Haiku 4.5 | $0.80 | $4.00 | see eval results | — |
| GPT-4o | $2.50 | $10.00 | see eval results | — |
| Qwen 2.5 72B | $0.40 | $1.20 | see eval results | — |

_Fill in from `experiments/synthesizer_eval/results/cost_data-*.json` after
running the v2 eval harness:_
```
python -m experiments.synthesizer_eval.run_eval
```

**Tier-routing scenario (60% Quick / 30% Smart / 10% Deep):**
Blended cost is significantly lower than all-Opus. See summary in
`experiments/synthesizer_eval/results/summary-*.md`.

## Alternatives Considered

**GPT-4o** — scored 80/90 in v1. Solid on factual grounding but less
consistent tag discipline. No architectural reason to prefer it over Claude
when Claude's trust-hierarchy compliance has been corrected. Retained as a
cross-provider check in the eval harness.

**Qwen 2.5 72B (OpenRouter)** — scored 82/90 in v1 at a fraction of Opus
cost. A viable cost-tier option if quality-per-dollar becomes the primary
driver. Excluded from production for now because the eval harness cannot
guarantee OpenRouter uptime or rate-limit behavior at scale.

**Gemini 2.5 Pro** — scored 78/90 in v1 with truncation on Test 2. Excluded.
Gemini is already a round-1 research seat; using it as the synthesizer
introduces synthesis bias toward its own prior response.

**DeepSeek V3** — critical failure on Test 3 (output corrupted). Excluded.

## Consequences

- Claude Opus 4.7 synthesizer must receive the updated `SYNTHESIS_TRUST_
  HIERARCHY` block (three-tier hierarchy, "PERPLEXITY WINS", mandatory
  contradiction scan). Any synthesizer regression is visible in Test 1 of the
  eval harness.
- Tier routing must be configurable per session — intake assigns the tier,
  `backend/router.py` selects the synthesis model.
- The eval harness (`experiments/synthesizer_eval/`) is a regression guard.
  Run it when changing synthesis system prompts or switching models.
- Cost analysis is automated via `experiments/generate_cost_report.py`.
