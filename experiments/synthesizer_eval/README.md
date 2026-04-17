# Synthesizer Evaluation

Empirical evaluation of candidate models for the ai-roundtable synthesis role.

## Why This Exists

Claude (the default synthesizer) has a failure mode on queries where
Perplexity's live web research contradicts round-1 model responses on
verifiable current facts. Claude's trained refusal behavior for post-cutoff
data was overriding system prompt instructions — it treated Perplexity's
cited live-web data as unreliable rather than authoritative.

This harness tests whether the updated trust hierarchy (three-tier, "PERPLEXITY
WINS") resolves the failure, and benchmarks alternative synthesizer candidates
for cost and quality comparison.

## How to Run

```bash
# From repo root
cd /path/to/ai-roundtable

# Ensure API keys are in backend/.env
# Required: ANTHROPIC_API_KEY (Claude candidates), OPENAI_API_KEY (GPT-4o)
# Optional: OPENROUTER_API_KEY (Qwen 2.5 72B)

python -m experiments.synthesizer_eval.run_eval
```

## How to Read Results

Results are saved to `experiments/synthesizer_eval/results/` (gitignored) —
one folder per candidate, one markdown file per test. A timestamped
`summary-*.md` and `cost_data-*.json` are written.

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
synthesis quality on opinions and tradeoffs — where all models generally
perform well. Used to confirm no regression on the core task.

**Test 3 — Domain Technical (the showcase case)**
ISO-NE offshore wind capacity accreditation. Tests terminology correction
propagation: Perplexity corrects Gemini's non-standard "MRI" to the official
RCA/RAA/QMRIC terms. A good synthesizer uses correct terminology throughout
and attributes the correction.

## Scoring

Six dimensions, 1–5 each, total max 30 points per test (90 total):

1. **Factual grounding** — uses Perplexity's verified data as primary source
2. **Attribution** — every claim attributed to a named source
3. **Contradiction handling** — states conflicts explicitly, does not blend
4. **Analytical depth** — adds expert perspective beyond summarizing
5. **Tag adoption** — uses `[VERIFIED]`/`[LIKELY]`/`[UNCERTAIN]`/`[DEFER]`
6. **Actionability** — ends with 3 concrete actionable next steps

Critical failure conditions on Test 1:
- Calls Perplexity's live-cited data "fabricated"
- Refuses to incorporate post-cutoff data when Perplexity has verified it
- Presents a retired model's pricing as current

## Candidates (v2)

| Candidate | Provider | Key Required | Role |
|-----------|----------|-------------|------|
| Claude Opus 4.7 | Anthropic | `ANTHROPIC_API_KEY` | Deep tier baseline |
| Claude Sonnet 4.6 | Anthropic | `ANTHROPIC_API_KEY` | Smart tier candidate |
| Claude Haiku 4.5 | Anthropic | `ANTHROPIC_API_KEY` | Quick tier candidate |
| GPT-4o | OpenAI | `OPENAI_API_KEY` | Cross-provider benchmark |
| Qwen 2.5 72B | OpenRouter | `OPENROUTER_API_KEY` | Open-weight cost baseline |

## Cost Analysis

Token counts and costs are recorded per call. The summary includes:
- Per-candidate token profile (avg input / output tokens)
- Monthly projection at 100 / 1K / 10K sessions
- Tier-routing scenario (60% Quick / 30% Smart / 10% Deep)
- Automated pass criteria check percentage

To generate the combined cost report (requires both synthesizer and intake
evals to have run):
```bash
python -m experiments.generate_cost_report
```

## Decision Record

After evaluating results, document the architectural decision in:
`docs/decisions/002-synthesizer-selection.md`
