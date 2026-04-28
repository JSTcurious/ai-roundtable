# ai-roundtable — Competitive Analysis

*Date: April 27 2026*
*Benchmark prompt: Career transition + H-1B immigration dual-track*
*Sessions run: 6 single-model + 3 ai-roundtable sessions*

---

## The Benchmark Prompt

```
I am a software engineer considering a move into AI engineering.
I also have an H-1B visa with an approved I-140 (priority date
June 1, 2018, backlogged). Help me plan both my career transition
and my immigration sequencing.
```

This prompt was chosen because it requires:
1. Two parallel tracks with equal depth (career + immigration)
2. Live web data to verify immigration facts (Visa Bulletin, USCIS)
3. Personalization to be useful (generic advice fails both tracks)
4. A committed recommendation, not just a framework

Every tool was evaluated against the same prompt on April 27 2026.

---

## Results — Six-Model Comparison

### ai-roundtable

**Strengths:**
- Perplexity fact-checked all four models and caught real errors:
  fabricated H-1B AI wage prioritization statistics cited by
  Gemini, GPT, and Grok; unverified premium processing fees;
  missing May 2026 Visa Bulletin data showing frozen EB categories
- Model disagreement surfaced explicitly with named resolution
- Four-section verdict format (THE VERDICT, THE HINGE,
  WHERE THE PANEL DISAGREED, ONE NEXT ACTION)
- Self-critique pre-pass audits lazy consensus before synthesis

**Weaknesses:**
- Career track absent from THE VERDICT — immigration dominated
- ONE NEXT ACTION was immigration every session
- No personalization — user treated as anonymous
- Synthesis collapsed two tracks into one despite explicit instruction

**Overall:** Strongest on verification. Weakest on career track depth.

---

### Claude.ai

**Strengths:**
- Best personalization — referenced JSTcurious brand, ISO NE MCP
  servers, CCA-F prep, IDEO cert because it had conversation history
- Career track depth was excellent — three AI Engineering profiles
  (LLM Integration, MLOps, Agentic Systems), quarterly roadmap,
  specific role title advice ("avoid ML Engineer and Data Scientist")
- Honest, committed recommendations

**Weaknesses:**
- No live web data — working from training data only
- No fact-checking — cannot catch its own errors
- No model disagreement — one perspective only
- Knowledge cutoff means Visa Bulletin and USCIS updates are missing

**Overall:** Best single-model career track. Zero verification.

---

### Ithy

**Strengths:**
- Most comprehensive — 71 sources cited, structured sections
- Covered both tracks with reasonable balance
- Strong source transparency

**Weaknesses:**
- Generic — no personalization
- No synthesis — lists of considerations, no committed position
- No independent fact-checker auditing the synthesis
- Same knowledge cutoff problem as all non-Perplexity tools
- Missed EB-1A/NIW pathway and Visa Bulletin freeze caught by
  Perplexity in ai-roundtable session

**Overall:** Best research document. No verdict.

---

### Gemini

**Strengths:**
- Best opinionated career track of any single model
- Named "AI Product Engineer" as highest salary growth + easiest
  immigration similarity match — specific and actionable
- Three-phase career roadmap (AI Layer, Infrastructure, Portfolio)
  with the correct 2026 framing: orchestration not model training
- Immediate action plan table mapping career steps to immigration
  impact — best integrated format of any response

**Weaknesses:**
- No live web data
- No fact-checking
- Immigration dates were outdated (2023 Visa Bulletin data)
- One model — no disagreement surfaced

**Overall:** Strongest opinionated career guidance. No verification.

---

### ChatGPT

**Strengths:**
- Most practical career track — resume positioning section was
  the best of any response ("Built LLM-powered chatbot using
  FastAPI" vs "Learning AI")
- Most conservative on immigration — appropriate given stakes
- Asked the right clarifying question: "Has your I-485 been filed?"
  This is the single variable that changes the entire immigration
  strategy. No other tool asked it.
- Inferred user context from prompt without requiring intake

**Weaknesses:**
- No live web data
- No fact-checking
- Conservative immigration advice may be too cautious for users
  who have already passed key milestones

**Overall:** Best resume positioning. Best clarifying question.
No verification.

---

### Grok

**Strengths:**
- Most complete response — covered both tracks proportionally
- Named actual salary ranges ($140K-$250K+)
- Referenced Providence/Boston area from context — location-aware
  without requiring intake
- Most honest about its own limitations — explicit knowledge cutoff
  disclaimer: "Immigration rules change frequently. Consult USCIS."
- Offered to generate personalized roadmap, target job titles,
  and H-1B decision tree if user provided more context

**Weaknesses:**
- No live web data
- No fact-checking
- Used 2023 Visa Bulletin data
- No model disagreement

**Overall:** Most complete single-model response. Best self-awareness.
No verification.

---

### Perplexity (standalone)

**Strengths:**
- Best citation density — every paragraph linked to immigration
  law firm sources (hinshawlaw, rnlawgroup, immilaw, tryalma)
- Most conservative and responsibly sourced immigration guidance
- Best two-track framing: "Career track: build AI proof.
  Immigration track: preserve I-140, maintain H-1B."
- Offered to personalize with month-by-month plan and
  H-1B/I-140 decision tree

**Weaknesses:**
- Moderate career track depth — solid but not as specific as
  Gemini or ChatGPT
- No model disagreement — one perspective with citations
- No synthesis verdict — structured guidance, not a committed position

**Overall:** Best sourced single-model response. No verdict.
Note: Perplexity inside ai-roundtable caught errors that
standalone Perplexity did not surface because it had four
model responses to audit against.

---

## Full Comparison Matrix

| Dimension | ai-roundtable | Claude.ai | Ithy | Gemini | ChatGPT | Grok | Perplexity |
|---|---|---|---|---|---|---|---|
| Career track depth | Weak | Strong, personalized | Generic | Strong, opinionated | Strong, practical | Strongest, complete | Moderate |
| Immigration accuracy | Best — live fact-check | Good | Standard | Good | Conservative | Good + disclaimer | Best sourced |
| Live web data | Yes — Perplexity | No | Yes | No | No | No | Yes — cited |
| Personalization | None (v2) | High | None | None | Inferred | Location inferred | None |
| Track parity | Failing (v2) | Balanced | Balanced | Balanced | Balanced | Best | Best framed |
| Disagreement surfaced | Yes | No | No | No | No | No | No |
| Committed position | Partial | Yes | No | Yes | Yes | Yes | Moderate |
| Asked clarifying Q | No | No | No | No | Yes | No — offered | No — offered |
| Resume positioning | Absent | Absent | Absent | Partial | Best | Good | Absent |
| Self-aware of cutoff | No | No | No | No | No | Yes | Partial |
| Salary data | No | No | Yes | No | No | Yes | No |
| Source citations | Perplexity | None | 71 listed | 1 link | None | None | Per paragraph |

---

## Where ai-roundtable Wins

**Verification** — Perplexity audited all four models and caught:
- Fabricated H-1B AI wage prioritization statistics (Gemini, GPT, Grok)
- Unverified premium processing fee ($2,805) cited by Claude
- Missing May 2026 Visa Bulletin data (frozen EB categories)
- EB-1A/NIW pathway for AI professionals that all models omitted

No single-model tool can catch its own errors. ai-roundtable
caught errors in four models simultaneously.

**Disagreement** — WHERE THE PANEL DISAGREED named:
- Gemini vs Perplexity on H-1B transfer risk
- Grok vs Perplexity on Visa Bulletin dates
- Claude's 180-day error corrected by Perplexity

**Verdict format** — THE VERDICT / THE HINGE / WHERE THE PANEL
DISAGREED / ONE NEXT ACTION produces a committed position that
Ithy and Perplexity standalone do not attempt.

---

## Where ai-roundtable Loses (v2)

**Career track depth** — all six single models produced better
career track output. Root cause: every user is treated as anonymous.
Claude.ai has conversation history. Grok infers from context.
ai-roundtable had no mechanism to capture who the user is.

*Fixed in v2.43 (PR #43): background context intake question.*
*Remaining gap: career track in synthesis still collapses to
immigration when emotional urgency asymmetry is present.*

**Track parity** — three iterations of TRACK PARITY REQUIRED
instructions failed to produce a synthesis that covered both
tracks proportionally. The synthesizer overrides the instruction
when it perceives one track as more urgent.

*Partial fix shipped in v2 (PRs #42, then track parity enforcement).*
*Full fix requires two-call synthesis architecture — v3 Phase 1.*

**Personalization** — background context question (PR #43)
closes this gap for future sessions.

---

## What No Competitor Has

The combination that ai-roundtable alone provides:

1. Live fact-checking against current web data (Perplexity)
2. Four independent model perspectives in one session
3. Model disagreement surfaced explicitly with resolution
4. Errors caught before they reach the user
5. A committed verdict, not just comprehensive coverage

No single model has all five. The combination is the product.

---

## Eval Baseline — Run This Quarterly

Use the benchmark prompt above. Pass criteria:

1. THE VERDICT contains labeled paragraphs for each track
2. ONE NEXT ACTION serves Track 1 (career), not Track 2 (immigration)
3. Perplexity catches at least one factual error from the panel
4. Accuracy ratings from Perplexity influence the synthesis weighting
5. Session outperforms best single-model on career track depth

When all five pass, the eval is green.

---

## Key Insight for Product Direction

Perplexity as a standalone product is quite good. As a fact-checker
inside ai-roundtable, it is exceptional because it has four model
responses to audit against — errors that are invisible in a single
model conversation become visible when four models all cite the same
wrong figure.

The product's defensible value is the combination.
The product's current execution gap is the synthesis.
The v3 roadmap closes the synthesis gap.

---

*See also:*
*docs/V3_ROADMAP.md — six-phase improvement plan*
*LESSONS.md — failure post-mortems from v2 development*
