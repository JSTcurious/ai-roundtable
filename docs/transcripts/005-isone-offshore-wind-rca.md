# Transcript 005 — ISO-NE Offshore Wind Capacity Accreditation

**Date:** 2026-04-17
**Prompt:** "What is ISO New England's current capacity accreditation methodology for offshore wind?"
**Tier:** deep · no intake

## Why This Prompt

A technical policy question in a specialized domain (ISO-NE capacity markets). The question requires
knowledge of a specific regulatory methodology — not general domain knowledge. This is a high-signal
test for two behaviors: (1) tag adoption on specific factual claims in a technical domain where
errors have real stakes, and (2) whether Perplexity's correction of a terminology error propagates
correctly into synthesis.

This is also notable as the **first transcript in the test suite where Gemini used confidence tags
throughout** — [VERIFIED], [LIKELY], [UNCERTAIN] appearing across the response without prompting.

## Round 1 Responses (Summary)

**Gemini:**
- Substantial, accurate response describing the transition from historical-performance capacity
  accreditation to a probabilistic, marginal reliability approach.
- **First observed systematic tag adoption in the test suite.** Used `[VERIFIED]`, `[LIKELY]`,
  and `[UNCERTAIN]` across substantive claims throughout the response — not just on hedging
  statements.
- Correctly described the core concept: ELCC-style marginal contribution, diminishing returns as
  offshore wind penetration grows, the multi-year transition timeline.
- Critical error: called the methodology "MRI" (Marginal Reliability Impact) — a non-standard
  acronym not used in ISO-NE documentation.

**GPT:**
- Used `[UNCERTAIN]` and deferred. No technical content provided.

## Fact-Check Layer (Perplexity)

Perplexity confirmed Gemini's conceptual accuracy while correcting the terminology error:
- **Correction:** The methodology is officially **Resource Capacity Accreditation (RCA)**, using
  a **Resource Adequacy Adjustment (RAA)** model. The calculated value is **Qualified Marginal
  Reliability Impact Capacity (QMRIC)**. Gemini's "MRI" acronym does not appear in any ISO-NE
  documentation.
- **Confirmed:** Marginal ELCC-style calculation, diminishing returns for correlated offshore
  wind fleet, 4-phase accreditation process.
- **Added:** Profile creation specifics — DNV synthetic hourly profiles (20+ years) using ERA5
  reanalysis data downscaled via NOAA HRRR 3km model to hub height; ≥5 years historical data uses
  metered history, <5 years stitches metered with synthetics.
- **Corrected timeline:** FCA 19 delayed approximately one year following November 2023 FERC
  filing; implementation timeline is later than Gemini stated.

Perplexity's overall assessment: "No major errors in Gemini's conceptual 'marginal ELCC-style'
or diminishing returns" — factual substance correct, terminology wrong.

## Synthesis Observation (Claude)

Synthesis correctly incorporated Perplexity's terminology correction and used accurate ISO-NE
nomenclature throughout:

- Used RCA, RAA, QMRIC correctly — not "MRI"
- `[VERIFIED]` tags carried into synthesis on confirmed facts
- DNV profile methodology included from Perplexity's audit
- Surfaced the stakeholder debate (NRDC's position that offshore wind deserves separate marginal
  ELCC treatment for its winter generation characteristics)

The synthesis produced a technically accurate document that would be useful for a project developer
or market participant — correctly describing the current transition, how profiles are built, and
what the implementation timeline actually is.

## What The Intake Caught

Nothing — no intake was conducted. Direct question submitted.

## What Was Missed

- **Gemini's "MRI" error was not caught in round-1.** Without Perplexity's audit, the synthesis
  would have propagated the non-standard terminology into the final output. The fact-check layer
  performed its core function here.
- **GPT's deferral left a seat empty.** A domain expert or market participant asking this question
  would have benefited from GPT's structural framing even with caveats. A single-model deferral
  ("check the official sources") provides no analytical value in a roundtable context.

## Follow-ups

- **First systematic tag adoption.** Gemini's use of `[VERIFIED]`, `[LIKELY]`, `[UNCERTAIN]`
  in this transcript is the first case where the confidence convention was applied consistently
  across a full response, not just as hedging on uncertain claims. What made this prompt different?
  The deep-tier designation, the specialized domain, or something about how the question was framed?
  Worth testing — does technical depth or high-stakes framing increase tag adoption?
- The RCA/QMRIC correction demonstrates that Perplexity's fact-check function is working for
  specialized regulatory questions. This is where web-grounded fact-checking adds the most value —
  terminology errors in official methodology names would survive any amount of reasoning but fail
  immediately against official ISO-NE documentation.

## Related

- [Transcript 011 — ISO-NE installed capacity (same domain, different question)](./011-isone-installed-capacity.md)
- [ADR 001 — Epistemic Transparency](../decisions/001-epistemic-transparency.md)
