# ADR 004: Factcheck Model Selection

**Status:** Accepted  
**Date:** 2026-04-18  
**Eval harness:** `experiments/factcheck_eval/` (7 tests, 4 candidates)

---

## Context

The ai-roundtable fact-check stage sits on the critical path between Round 1 and
synthesis. Its structural requirement is live web search grounding that is
**independent of all four Round 1 providers** (Gemini, GPT, Grok, Claude).
Perplexity was pre-selected as primary on product principles:

- Search-native architecture — every response is grounded in real-time web results
- Provider independence — structurally separate from all four Round 1 labs
- Inline citations — gives synthesis a verifiable grounding signal, not just claims

This eval quantitatively confirms which Perplexity tier to use as primary, validates
the GPT-5.4 fallback, and adds Gemini 2.5 Flash with Google Search grounding as a
fourth data point.

---

## Model IDs — Retired vs Current

Perplexity retired the legacy `llama-3.1-sonar-*-128k-online` model IDs in early 2026.
The eval confirmed these return `400 Invalid model`. The correct current IDs:

| Legacy (retired — 400 error) | Current |
|------------------------------|---------|
| `llama-3.1-sonar-large-128k-online` | `sonar-pro` |
| `llama-3.1-sonar-small-128k-online` | `sonar` |

`model_config.py` has been updated from the legacy IDs to `sonar-pro` / `sonar`.

---

## Candidates Evaluated

| Candidate | Model | Provider | $/MTok in | $/MTok out |
|-----------|-------|----------|-----------|------------|
| Perplexity-Sonar-Pro | `sonar-pro` | Perplexity | $1.00 | $1.00 |
| Perplexity-Sonar | `sonar` | Perplexity | $0.20 | $0.20 |
| GPT-5.4-WebSearch | `gpt-5.4` | OpenAI | $2.50 | $10.00 |
| Gemini-2.5-Flash-Search | `gemini-2.5-flash` | Google | $0.075 | $0.30 |

Perplexity pricing includes a per-request search fee (~$0.006) captured in
`usage.cost['total_cost']` — token-only calculations understate actual cost.

---

## Test Results

**7 tests, smart tier. Hard gate: Test 1 (catch retired model as current).**

| Test | Sonar Pro | Sonar | GPT-5.4 | Gemini Flash |
|------|-----------|-------|---------|--------------|
| T1 — Catch retired model (hard gate) | 88%* | 88%* | 25% | 0% |
| T2 — Confirm correct terminology | 0% | 0% | 33% | 100% |
| T3 — Catch wrong statistic | 100% | 33% | 33% | 0% |
| T4 — Structured output (4 sections) | 100% | 100% | 50% | 25% |
| T5 — Citation specificity | 100% | 100% | 100% | 100% |
| T6 — Latency (≤15s) | 100% | 100% | 100% | 100% |
| T7s — Smart vs Deep (smart side) | 0%† | 0%† | 0%† | 0%† |
| **Avg (T1–T6, T7s)** | **70%** | **60%** | **49%** | **46%** |
| Hard gate failures | ⚠ T1* | ⚠ T1* | ⚠ T1 | ⚠ T1 |

\* See "Test 1 Hard Gate Analysis" below — scorer miscalibration, not model failure.  
† T7 has no automated checks; 0% reflects no scored assertions, not quality.

---

## Test 1 Hard Gate Analysis

All four candidates triggered the hard gate on Test 1. The root cause differs
significantly between candidates — the hard gate result is **not uniform failure**.

**Sonar Pro — 7/8, single word miss (scorer issue):**

Sonar Pro's actual output correctly:
- Flagged `$15/$75` and `Claude 3 Opus` as wrong ✓
- Identified `Claude Opus 4.6/4.7` as the current flagship ✓
- Cited correct `$5/$25` pricing with inline citations ✓
- Used `"legacy/deprecated"` throughout

It failed one check: `must_mention: "retired"`. The scorer required the literal word
`"retired"` but Sonar Pro wrote `"legacy/deprecated"` — semantically identical. The
model's output is correct; the scorer was overconstrained.

**Sonar — same pattern:** Also wrote `"deprecated"`, missed `"retired"`. Quality
similar to Sonar Pro, slightly less detailed.

**GPT-5.4 — genuine quality gap:** Scored 25% on T1 — failed multiple checks
including missing correct current pricing. Output hit the 800-token `max_completion_tokens`
cap on every smart-tier test (suggesting truncation), which likely hurt structured output
quality across tests. The `web_search_preview` tool type is not valid for Chat
Completions; this candidate uses a prompt-embedded grounding instruction instead,
which may be less effective than Perplexity's native search architecture.

**Gemini Flash — genuine failure:** Scored 0% on T1 — produced only 67 output tokens
(vs 400–600 for Perplexity candidates). The response was too terse to pass any checks.
Low output volume was consistent across tests (67–249 tokens vs 390–630 for Sonar Pro),
suggesting the 800-token budget is generous for this model's default verbosity.

**Revised T1 interpretation:** Sonar Pro and Sonar pass T1 on substance; the hard gate
should use `must_mention_any: [["retired", "deprecated"]]` rather than requiring
the exact word `"retired"`. GPT-5.4 and Gemini Flash have genuine T1 quality gaps.

---

## Cost Comparison

**Per-session cost (Smart tier, including Perplexity search fee):**

| Candidate | Per session | 1K sessions/mo | 10K sessions/mo |
|-----------|-------------|-----------------|-----------------|
| Sonar Pro | $0.00051 | $0.51 | $5.10 |
| Sonar | $0.00011 | $0.11 | $1.10 |
| GPT-5.4 | $0.00624 | $6.24 | $62.40 |
| Gemini Flash | $0.000045 | $0.04 | $0.45 |

Sonar Pro costs ~4.6× more than Sonar per session but delivers meaningfully
higher quality (70% vs 60% avg, better structured output, more complete corrections).
GPT-5.4 is 12× more expensive than Sonar Pro with lower quality — appropriate only
as a cross-provider last resort.

---

## Decision

**Primary: `sonar-pro` (Perplexity Sonar Pro)**

Highest quality across the eval (70% avg). Correctly catches factual errors,
produces well-structured four-section output, cites specific sources. The T1 hard
gate failure is a scorer artifact — the model's actual output on T1 was correct.
At $0.51/1K sessions, cost is negligible relative to value.

**Fallback 1: `sonar` (Perplexity Sonar)**

Structurally identical to Sonar Pro (same search grounding, same citation format),
60% avg quality. Stays within the Perplexity grounding architecture — a cheaper
Perplexity model is a better factcheck fallback than cross-provider web search.
Triggered only on full Sonar Pro failure.

**Fallback 2: `gpt-5.4` (OpenAI GPT-5.4 with web search)**

Cross-provider diversity. 49% avg quality in this eval, with output length capped
at `max_completion_tokens`. Appropriate as a last-resort when the entire Perplexity
API is down. Not recommended for normal operation.

**Not selected: Gemini 2.5 Flash with Google Search**

46% avg, consistently terse output (67–249 tokens), genuine T1 failure. Not
currently competitive for the factcheck role. May be worth re-evaluating if
Google improves structured grounding response length.

---

## model_config.py Update

```python
FACTCHECK_PRIMARY   = os.getenv("FACTCHECK_PRIMARY",   "sonar-pro")
FACTCHECK_FALLBACK1 = os.getenv("FACTCHECK_FALLBACK1", "sonar")
FACTCHECK_FALLBACK2 = os.getenv("FACTCHECK_FALLBACK2", "gpt-5.4")
```

---

## Addendum — April 19, 2026: Always Deep Fact-Check

**Decision:** Fact-check audit depth is always Deep (2000 tokens)
regardless of session tier (Smart or Deep).

**Rationale:**
- Fact-check is the grounding layer for synthesis. Shallow grounding
  produces lower quality synthesis regardless of research tier depth.
- Cost difference: ~$0.0008/session — negligible at any usage scale.
- Latency addition: ~10-15 seconds — acceptable for a deliberation tool.
- The Smart/Deep audit prompt distinction is preserved in code for
  future flexibility, but `get_factcheck_max_tokens()` always returns
  `FACTCHECK_DEEP_MAX_TOKENS` (2000).

This decision aligns with the product tagline:
"The best answer possible, with the best tools available."

---

## Follow-up Items

1. **Fix T1 scorer:** Change `must_mention: ["retired"]` to
   `must_mention_any: [["retired", "deprecated"]]` so semantically equivalent
   terms both pass. This removes the false hard gate failure for Sonar Pro/Sonar.

2. **Investigate Gemini output length:** Gemini Flash consistently produced
   very short responses under the 800-token budget. Check whether
   `max_output_tokens` is being applied correctly or if the model needs a
   stronger prompt to produce the full four-section format.

3. **GPT-5.4 truncation:** All smart-tier GPT-5.4 outputs hit exactly 800 tokens,
   suggesting consistent truncation. Consider whether the audit prompt needs
   restructuring to fit the budget, or raise the smart-tier token cap for this model.
