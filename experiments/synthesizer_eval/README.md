# Synthesizer Evaluation

Empirical evaluation of candidate models for the ai-roundtable synthesis role.

## Why This Exists

Claude (the default synthesizer) fails on queries where Perplexity's live
web research contradicts round-1 model responses on verifiable current facts.
Claude's trained refusal behavior for post-cutoff data overrides system prompt
instructions — it treats Perplexity's cited live-web data as unreliable rather
than authoritative.

This harness tests whether alternative models handle this better while
maintaining synthesis quality on analytical questions.

## How to Run

```bash
# From repo root
cd /path/to/ai-roundtable

# Ensure API keys are in backend/.env
# Required: ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY
# Optional: OPENROUTER_API_KEY (for DeepSeek, Qwen, Llama)

python -m experiments.synthesizer-eval.run_eval
```

## How to Read Results

Results are saved to `experiments/synthesizer-eval/results/` — one folder
per candidate, one markdown file per test. A timestamped `summary-*.md`
is written with the results matrix and scoring rubric.

The three tests stress different synthesizer capabilities:

**Test 1 — Factual Current Data (the failing case)**
Perplexity has live verified data that directly contradicts stale round-1
responses. A passing synthesizer uses Perplexity's data and states the
contradiction explicitly. A failing synthesizer calls the live data
"fabricated", ignores it, or presents the retired model's pricing as current.

Key assertions:
- Claude Opus 4.7 at $5/$25 (not $15/$75 from the retired Claude 3 Opus)
- Claude 3 Opus retirement stated (Jan 5, 2026)
- Perplexity data not dismissed

**Test 2 — Analytical Synthesis (the working case)**
Pure analysis with model disagreement and no post-cutoff data gap. Tests
synthesis quality on opinions and tradeoffs — where Claude currently excels.
Used to confirm alternative models don't regress on the core task.

**Test 3 — Domain Technical (the showcase case)**
ISO-NE offshore wind capacity accreditation. Tests terminology correction
propagation: Perplexity corrects Gemini's non-standard "MRI" to the official
RCA/RAA/QMRIC terms. A good synthesizer uses correct terminology throughout
and attributes the correction.

## Scoring

Score each candidate using the rubric in `prompts.py` (also written to
`results/summary-*.md`). Six dimensions, 1-5 each, total max 30 points.

Critical failure conditions on Test 1:
- Calls Perplexity's live-cited data "fabricated"
- Refuses to incorporate post-cutoff data when Perplexity has verified it
- Presents a retired model's pricing as current

## Candidates

| Candidate | Provider | Key Required |
|-----------|----------|-------------|
| Claude Opus 4.7 | Anthropic | `ANTHROPIC_API_KEY` |
| GPT-4o | OpenAI | `OPENAI_API_KEY` |
| Gemini 2.5 Pro | Google | `GOOGLE_API_KEY` |
| DeepSeek V3 | OpenRouter | `OPENROUTER_API_KEY` |
| Qwen 2.5 72B | OpenRouter | `OPENROUTER_API_KEY` |
| Llama 3.3 70B | OpenRouter | `OPENROUTER_API_KEY` |

## Decision Record

After evaluating results, document the architectural decision in:
`docs/decisions/002-synthesizer-selection.md`
