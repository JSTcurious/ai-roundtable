# Transcript 011 — ISO-NE Installed Capacity

**Date:** 2026-04-17
**PR under test:** Gemini Flash intake rewrite + SYNTHESIS_TRUST_HIERARCHY (commits 0dfc8fe0 → 4e8835cd)
**Prompt:** "What is the current installed capacity for ISO New England?"

## Why This Prompt

ISO New England (ISO-NE) is the grid operator for the six-state New England
electricity market. Installed capacity figures are published quarterly and
change as plants enter and retire. This prompt is designed to test three things:

1. **Intake tier classification** — a specific factual lookup with a known
   authoritative source (ISO-NE's published data) should get tier=quick,
   not smart. The system should not over-tier a factual question.

2. **Stale training data vs live research** — installed capacity figures
   change. Round-1 models will cite figures from their training data, which
   may be 12-24 months stale. Perplexity should have current data. This is
   a direct regression test for `SYNTHESIS_TRUST_HIERARCHY` — introduced
   after transcript 002 revealed that `CASCADING_GUARD` was incorrectly
   applied to Perplexity's grounded outputs.

3. **Model hallucination surface** — specific numerical claims (MW figures,
   resource mix percentages) are exactly the kind of content where models
   fabricate plausible-sounding but incorrect values without flagging uncertainty.

## Intake Decision

**Status:** complete (no clarification needed)

**Intake JSON:**
```json
{
  "needs_clarification": false,
  "optimized_prompt": "What is ISO New England's current total installed capacity? Include a breakdown by resource type (natural gas, nuclear, renewables, oil/coal, imports, demand response), note any significant recent capacity additions or retirements, and compare against peak demand figures. Cite the data source and date so the user can verify currency.",
  "tier": "quick",
  "output_type": "analysis",
  "reasoning": "Quick selected — specific factual lookup with a known authoritative data source; single-dimension question with published answer"
}
```

**Assessment:** Correct. Tier=quick is right for a factual lookup with a
known authoritative source. The optimized prompt improved the raw question
by adding: resource type breakdown, change context (additions/retirements),
peak demand comparison, and an explicit source/date citation request. The
citation request is particularly important here — it gives Perplexity's
live findings a clear structural slot in the final output.

## Round 1 Responses (Summary)

**Gemini:**
- Cited total installed capacity of approximately 34,000 MW.
- Gave a resource mix breakdown: ~40% natural gas, ~30% nuclear, ~15%
  renewables, ~10% oil, ~5% other/imports.
- Described the 2024 capacity auction results as the most recent data.
- No `[LIKELY]` or `[UNCERTAIN]` tags on any of these figures despite
  the inherent recency risk of capacity data. Stated the figures as fact.

**GPT:**
- Cited ~31,000 MW total installed capacity.
- Different resource mix: higher renewables share (~20%), lower gas (~35%).
- Noted offshore wind additions as a growing factor.
- Correctly flagged: "These figures are from my training data and may not
  reflect recent plant retirements or the 2025-2026 capacity auction results."
- This verbal hedge is the right behavior — but it used no `[LIKELY]` tag
  despite being a textbook `[LIKELY]` situation.

**Grok:**
- Cited ~33,500 MW, consistent with Gemini's range.
- Described the grid's ongoing transition from oil/coal baseload to gas
  peakers and offshore wind.
- Mentioned Millstone Nuclear (Connecticut) as the only remaining nuclear
  plant in New England — this is accurate.
- Noted that capacity figures shift significantly year-over-year due to
  retirements and new interconnections.
- No confidence tags.

**Discrepancy note:** Gemini (~34,000 MW) and Grok (~33,500 MW) are
consistent. GPT's ~31,000 MW figure is an outlier — likely citing an
earlier data vintage. This is a direct test of whether the synthesis
correctly handles a factual numerical disagreement between round-1 models.

## Fact-Check Layer (Perplexity)

Perplexity retrieved ISO-NE's published capacity data:

- **Total installed capacity as of Q1 2026: approximately 35,200 MW**
  (source: ISO-NE 2026 Capacity, Energy, Loads, and Transmission report)
- **Resource mix (Q1 2026):** Natural gas ~38%, Nuclear ~30%, Renewables
  ~18% (wind + solar), Oil ~8%, Imports/Hydro ~6%
- **Recent changes:** Three oil-fired peakers retired in late 2025 (total
  ~800 MW removed). Vineyard Wind Phase 1 (800 MW offshore) came online in
  early 2026, largely offsetting the retirements in installed capacity terms.
- **Peak demand (2025 summer):** 24,900 MW — reserve margin above 40% at
  current installed capacity.

**Discrepancy resolution:** Gemini and Grok were closer to the correct
figure; GPT's ~31,000 MW appears to cite 2023-era data. None of the
round-1 figures are current.

## Synthesis Observation (Claude)

Two observations surfaced to the chair:

1. "Perplexity has the current ISO-NE figure: 35,200 MW as of Q1 2026,
   with Vineyard Wind Phase 1 recently online. GPT's 31,000 MW figure
   appears to be 2023 data. I'll lead the synthesis with Perplexity's
   verified number and attribute the round-1 figures as prior estimates.
   Do you want to keep this, or overrule?"
   — Chair: **Keep**

2. "None of the round-1 models mentioned that Vineyard Wind Phase 1 came
   online in early 2026 — this is a significant recent development that
   changes the resource mix. Perplexity confirmed it. I'll include it as
   a headline finding. Do you want to keep this, or overrule?"
   — Chair: **Keep**

Critically: `SYNTHESIS_TRUST_HIERARCHY` worked as designed. Claude used
Perplexity's 35,200 MW figure as the authoritative answer and explicitly
stated that the round-1 figures were training-data estimates. It did not
apply `CASCADING_GUARD` skepticism to Perplexity's cited data. This is the
direct regression fix for transcript 002's failure mode.

## What The Intake Caught

- Tier=quick correctly assigned. The system did not over-tier a factual
  lookup into a smart session.
- The optimized prompt's explicit citation request gave Perplexity's live
  data a structural anchor in the final output, making the trust hierarchy
  easier to apply correctly.

## What The Guardrails Caught

- `SYNTHESIS_TRUST_HIERARCHY` worked: Perplexity's Q1 2026 data was used
  as the lead finding, not treated as a fourth unverified assertion.
- The numerical discrepancy between GPT (~31,000 MW) and the others was
  surfaced and resolved using Perplexity's authoritative source — rather
  than averaging the models or picking Gemini/Grok by majority.

## What Was Missed

- **Tag adoption: 0%.** Gemini stated specific MW figures and a resource
  mix percentage as fact, with no `[LIKELY]` tag. GPT's verbal hedge
  ("may not reflect recent data") was semantically correct behavior but
  not formalized into the tag convention. Grok cited Millstone as the only
  remaining nuclear plant — correct, but stated without a `[VERIFIED]` tag.
- The resource mix percentages from Gemini and GPT differed by ~5 percentage
  points (renewables: 15% vs 20%) with no model flagging the discrepancy
  or noting data vintage. An explicit instruction to flag when round-1 models
  disagree on specific numerical claims would surface this earlier.

## Follow-ups

- This is the cleanest confirmation that `SYNTHESIS_TRUST_HIERARCHY` resolves
  transcript 002's failure mode. The numerical discrepancy use case — where
  Perplexity has current data and round-1 models have stale data — is now
  handled correctly.
- Consider a test where Perplexity's live data is absent or inconclusive
  and round-1 models disagree. The current trust hierarchy handles the
  "Perplexity has it" case; the "nobody has current data" case has not been
  tested.
- Tag adoption at 0% is a recurring finding across all three intake PR
  validation tests (009, 010, 011). The `CONFIDENCE_CONVENTION` examples
  are present in the system prompt but have not changed model behavior.
  This warrants a separate investigation into whether the guardrail text
  is being read or is buried under the system prompt length.

## Related

- [Transcript 002 — Q1 2026 AI releases (the failure this test validates the fix for)](./002-q1-2026-ai-releases.md)
- [Transcript 009 — DPO vs PPO (happy-path intake)](./009-dpo-ppo-comparative-analysis.md)
- [Transcript 010 — AI engineering project plan (clarifying turn test)](./010-ai-engineering-project-plan.md)
- [ADR 001 — Epistemic Transparency](../decisions/001-epistemic-transparency.md)
