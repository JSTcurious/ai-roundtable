# Transcript 010 — AI Engineering Project Plan

**Date:** 2026-04-17
**PR under test:** Gemini Flash intake rewrite (commits 0dfc8fe0 → 4e8835cd)
**Prompt:** "I want to build a project plan for AI engineering"

## Why This Prompt

This is deliberately underspecified — the kind of raw input a real user types
before they've been asked the right questions. It covers two very different
use cases that require completely different session setups:

1. A **career/learning plan** — "I want to become an AI engineer"
2. A **technical build plan** — "I'm planning an AI system and need a
   project plan for building it"

This is the first real-world test of the clarifying turn in the new intake.
The previous Claude intake would have launched into a multi-turn conversation.
Gemini Flash is expected to ask exactly one question and then produce a complete
session config.

Secondary purpose: validate that a high-stakes career/roadmap question gets
tier=deep, not tier=smart.

## Intake Decision

**Turn 1 — Clarification:**

```json
{
  "needs_clarification": true,
  "clarifying_question": "Are you planning a career move into AI engineering, or do you need a project plan for building a specific AI system or product?",
  "optimized_prompt": "",
  "tier": "smart",
  "output_type": "plan",
  "reasoning": "Clarification needed — prompt covers two distinct use cases with different session structures"
}
```

**User's answer:** "Career move — I'm a backend engineer with 4 years of Python
experience and I want to transition into AI engineering. I have about 6 months
before I want to start actively interviewing."

**Turn 2 — Complete:**

```json
{
  "needs_clarification": false,
  "optimized_prompt": "Create a detailed 6-month roadmap for a backend engineer with 4 years of Python experience transitioning to an AI engineering role. The user will begin active job searching at month 6. Cover: skill gap analysis against current AI engineering job requirements, month-by-month learning milestones, hands-on projects that build a public portfolio, tools and frameworks to prioritize (RAG, agentic systems, LLM APIs, fine-tuning basics), and a Week 1 action plan. Flag where math or ML theory gaps could become interview blockers and how to address them without derailing the timeline.",
  "tier": "deep",
  "output_type": "roadmap",
  "reasoning": "Deep selected — high-stakes career transition with hard deadline; requires detailed, personalized planning with specific milestones"
}
```

**Assessment:** Both turns worked correctly.

Turn 1: The clarifying question was precise and binary — it resolved the
ambiguity in a single exchange without asking for background information the
user hadn't offered. It did not ask "what's your timeline?" or "what's your
experience level?" — correctly holding those for after the use case was
established.

Turn 2: After the user's answer, the optimized prompt incorporated all
disclosed specifics: 4 years Python, 6-month timeline, interview target.
It added scope the user omitted but that the session requires: Week 1 action
plan, math gap handling, portfolio framing. Tier escalated to deep (from
smart in the ambiguous turn-1 estimate) — correct, because a 6-month career
transition with a hard deadline is a high-stakes deliverable.

## Round 1 Responses (Summary)

**Gemini:**
- Strong month-by-month structure: Month 1-2 (foundations), Month 3-4
  (applied projects), Month 5 (portfolio hardening), Month 6 (interview prep).
- Specific tool recommendations: LangChain/LlamaIndex for RAG, LiteLLM for
  multi-provider, Weights & Biases for experiment tracking.
- Flagged math gaps explicitly: "Linear algebra and probability are tested
  in ML system design interviews more than most candidates expect."
- No confidence tags on tool recommendations, some of which may reflect
  the ecosystem as of 2024 rather than current best practices.

**GPT:**
- More conservative framing: led with what AI engineering roles actually
  require vs what bootcamp content covers.
- Called out that many "AI engineer" job posts conflate two different roles:
  application engineers (LLM API, RAG, prompting) vs ML engineers (training,
  fine-tuning, infrastructure). Recommended the user clarify which type before
  building a portfolio.
- Useful callout but could have been positioned as a clarifying question
  rather than a caveat that dilutes the roadmap.
- No tags.

**Grok:**
- Practical and opinionated: "Skip the courses, build two public projects in
  the first 60 days."
- Project suggestions: a RAG application over a public dataset, and an
  agentic workflow using a public API.
- Less structured than Gemini but more immediately actionable.
- Flagged the 6-month timeline as "tight but achievable if you already
  ship code daily."
- No tags.

## Fact-Check Layer (Perplexity)

Perplexity confirmed:
- Current AI engineering job postings (April 2026) consistently require:
  RAG system design, LLM API integration, basic fine-tuning familiarity,
  and production deployment experience.
- GPT's two-role distinction is accurate and well-documented in current
  job market data. Application-layer AI engineer roles outnumber ML engineer
  roles by roughly 4:1 in the current posting volume.
- Gemini's tool list is current. LiteLLM and LlamaIndex remain active.
- Grok's "two projects in 60 days" framing aligns with how hiring managers
  describe filtering portfolios.
- Flagged one addition: Gemini and GPT did not mention that AI engineering
  interviews increasingly include live RAG system design components (not
  just LeetCode) — this is a recent shift that affects interview prep strategy.

## Synthesis Observation (Claude)

Three observations surfaced to the chair:

1. "GPT raised an important distinction between application AI engineers and
   ML engineers that affects how you should frame your portfolio and which
   job postings to target. I'll make this the opening framing of the roadmap.
   Do you want to keep this, or overrule?"
   — Chair: **Keep**

2. "Perplexity flagged that AI engineering interviews increasingly include
   live RAG system design rounds (not just LeetCode). I'll add a Month 5
   interview-prep block specifically for this. Do you want to keep this,
   or overrule?"
   — Chair: **Keep**

3. "Grok's 'two projects in 60 days' framing is the most actionable Week 1
   anchor. I'll lead the roadmap's opening with the two specific project
   types rather than a curriculum overview. Do you want to keep this,
   or overrule?"
   — Chair: **Keep**

The resulting synthesis incorporated all three decisions. The roadmap opened
with the application vs ML engineer distinction, used the two-project sprint
as the Month 1-2 structure, and added a dedicated RAG system design interview
prep block in Month 5. The Week 1 action plan named specific first steps
(clone a public RAG repo, set up a LiteLLM dev environment, open a public
GitHub repo for the portfolio).

This was the strongest synthesis of the three validation tests. The HITL
dialogue resolved three genuine tensions between the models' framings rather
than just surfacing redundant observations.

## What The Intake Caught

- The clarifying question correctly identified the ambiguity and resolved it
  in one turn. No second clarifying question was asked.
- The optimized prompt incorporated disclosed specifics and added scope gaps
  (Week 1 action plan, math gap handling) not present in the user's raw answer.
- Tier correctly escalated from smart (ambiguous turn-1 estimate) to deep
  (final decision after use case was confirmed).
- Maximum one clarifying turn enforced correctly.

## What Was Missed

- **Tag adoption: 0%.** Gemini's tool recommendations are dated to its
  training data and none were tagged `[LIKELY]` or `[UNCERTAIN]`. This
  is increasingly consequential in a fast-moving ecosystem.
- **GPT's dual-role callout** was structurally correct but could have been
  phrased as a session-opening decision rather than a mid-response caveat.
  The HITL dialogue corrected this, but it required human intervention.

## Follow-ups

- The clarifying turn worked correctly for this test case. Consider a test
  with a prompt that is clear enough that the intake might incorrectly ask
  a clarifying question (false positive on ambiguity detection).
- GPT's "callout that dilutes the roadmap" pattern is recurring. The round-1
  system prompt may benefit from an instruction: "if you have a structural
  observation that affects how the session should be framed, surface it as
  a framing note at the top, not a caveat in the middle."

## Related

- [Transcript 009 — DPO vs PPO (happy-path intake, no clarification)](./009-dpo-ppo-comparative-analysis.md)
- [ADR 001 — Epistemic Transparency](../decisions/001-epistemic-transparency.md)
