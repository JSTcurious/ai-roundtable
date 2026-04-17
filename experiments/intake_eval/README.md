# Intake Model Evaluation

Empirical evaluation of candidate models for the ai-roundtable intake role.

## Why This Exists

The intake model does three things that directly affect session quality:

1. **Clarification detection** — decides whether the user's prompt needs a
   follow-up question before the roundtable runs. False negatives waste
   frontier model budget on under-specified prompts.
2. **Tier assignment** — routes the session to quick / smart / deep. Wrong
   routing either wastes money (too high) or degrades output quality (too low).
3. **Proper noun preservation** — must carry the user's exact model names,
   product names, and version numbers into the optimized prompt unchanged.
   Substituting "Claude Opus 4.7" with "Claude 3 Opus" corrupts the session.

This harness tests all three across five candidate models and produces per-call
token counts, automated assertion scores, and monthly cost projections.

## How to Run

```bash
# From repo root
cd /path/to/ai-roundtable

# Ensure API keys are in backend/.env
python -m experiments.intake_eval.run_eval
```

## Tests

| ID | Name | What It Tests |
|----|------|---------------|
| test1-simple | Simple Research Question | Proceeds without clarification, smart tier |
| test2-vague | Vague Prompt | Triggers exactly one clarifying question |
| test3-proper-nouns | Proper Noun Preservation | User-provided model names survive into optimized_prompt |
| test4a-tier-quick | Tier Assignment — Quick | Factual lookup → quick |
| test4b-tier-deep | Tier Assignment — Deep | Architecture decision → deep |
| test5-two-turn | Two-Turn Proper Noun Preservation | Proper nouns survive across clarification round-trip |
| test6-consistency | Tier Consistency (3 runs) | Same borderline prompt → same tier every time |

## Candidates

| Candidate | Provider | Key Required |
|-----------|----------|-------------|
| Gemini 2.5 Flash | Google | `GOOGLE_API_KEY` |
| Gemini 2.0 Flash | Google | `GOOGLE_API_KEY` |
| GPT-4o Mini | OpenAI | `OPENAI_API_KEY` |
| Claude Haiku 4.5 | Anthropic | `ANTHROPIC_API_KEY` |
| Qwen 2.5 72B | OpenRouter | `OPENROUTER_API_KEY` |

## Scoring

Each test has 1–4 assertions checked automatically:

- `equals` — field must equal exact expected value
- `nonempty` — field must be a non-empty string
- `contains` — field must contain the expected substring
- `not_contains` — field must NOT contain the expected substring
- `single_question` — clarifying_question must have 1–2 question marks
- `consistent` — tier must be the same across all 3 consistency runs

Results are expressed as a percentage of assertions passed.

**Critical failures:**
- Any proper noun substitution in `optimized_prompt` is a hard fail
- Tier instability across consistency runs is a hard fail
- JSON parse error on any test is a hard fail for that test

## Decision Record

After evaluating results, document the architectural decision in:
`docs/decisions/003-intake-model-selection.md`
