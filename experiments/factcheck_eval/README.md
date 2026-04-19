# Factcheck Model Evaluation

Empirical evaluation of candidates for the ai-roundtable fact-check role.

## Why This Exists

Perplexity is confirmed as primary fact-checker based on product principles
(search-native, live citations, provider independence). This eval:

1. Confirms whether Sonar Pro or Sonar is the better primary tier
2. Validates GPT-5.4 web search as the cross-provider fallback quality
3. Measures whether Smart/Deep audit depth produces meaningfully different output
4. Establishes latency baselines for both tiers

## How to Run

```bash
uv run python -m experiments.factcheck_eval.run_eval
```

## Test Design

Tests use fixed round-1 inputs with known ground truth:

- **Test 1** — Hard gate. Must catch retired model pricing. Failure here
  disqualifies a candidate as primary.
- **Test 2** — False positive rate. Must confirm correct terminology.
- **Test 3** — Partial error. Must correct wrong statistic with citation.
- **Test 4** — Structured output. All four sections must be present.
- **Test 5** — Citation quality. No vague references allowed.
- **Test 6** — Latency. Smart audit must complete within 15 seconds.
- **Test 7** — Smart vs Deep comparison. Same input, both depths.

## After Running

1. Read decision matrix in `results/decision-matrix-*.md`
2. Check Test 7 outputs manually — token count is proxy, read for quality
3. Update `backend/models/model_config.py`:
   ```python
   FACTCHECK_PRIMARY   = os.getenv("FACTCHECK_PRIMARY",   "<winner>")
   FACTCHECK_FALLBACK1 = os.getenv("FACTCHECK_FALLBACK1", "<second>")
   FACTCHECK_FALLBACK2 = os.getenv("FACTCHECK_FALLBACK2", "<third>")
   ```
4. Create `docs/decisions/004-factcheck-model-selection.md`

## Candidates

| Candidate | Model | Provider | $/MTok in | $/MTok out | Role |
|-----------|-------|----------|-----------|------------|------|
| Perplexity-Sonar-Pro | sonar-pro | Perplexity | $1.00 | $1.00 | Primary |
| Perplexity-Sonar | sonar | Perplexity | $0.20 | $0.20 | Fallback1 |
| GPT-5.4-WebSearch | gpt-5.4 | OpenAI | $2.50 | $10.00 | Fallback2 |

## Results Directory

```
results/
  <CandidateName>/
    test1-catch-retired-model.md
    test2-confirm-correct-terminology.md
    test3-catch-wrong-statistic.md
    test4-structured-output-four-sections.md
    test5-citation-specificity.md
    test6-latency-smart.md
    test7-depth-comparison-smart-vs-deep-smart.md
    test7-depth-comparison-smart-vs-deep-deep.md
  cost_data-<timestamp>.json
  decision-matrix-<timestamp>.md
```

Results are gitignored — run locally and share the decision matrix manually.
