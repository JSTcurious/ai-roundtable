# Transcript 001 — Claude Opus 4.7 Context Window

**Date:** 2026-04-17
**PR under test:** Anti-hallucination guardrails (commits 487af69f → b8b54a2)
**Prompt:** "What's the context window of Claude Opus 4.7?"

## Why This Prompt

Claude Opus 4.7 is a recently released model. Round-1 models are likely to have
stale or missing training data about it, which is a classic setup for:

- Confident fabrication (claiming the model doesn't exist)
- Model-vs-model disagreement
- Cascading hallucination if synthesis averages the responses

This is exactly the failure mode the synthesis skepticism clause was designed
to catch.

## Round 1 Responses (Summary)

**Gemini:**
- Declared confidently that no model named "Claude Opus 4.7" exists.
- Redirected to Claude 3 Opus with a 200,000 token context window.
- No confidence qualifier tag used despite making a strong factual claim.

**GPT:**
- Hedged verbally: "I don't have specific details..."
- Recommended consulting official documentation.
- No `[DEFER]` tag despite the response being a textbook deferral.

**Grok:**
- Stated it was not aware of the model, suggested it might be a typo.
- Fell back to Claude 3 Opus with 200K tokens.
- No tag used.

## Fact-Check Layer (Perplexity)

Perplexity's real-time web search contradicted Gemini's claim directly:
- Confirmed Claude Opus 4.7 exists as a current model.
- Documented a 1 million token context window (plan-dependent).
- Flagged Gemini's 200K claim as outdated and referring to an older Opus.

This is the decisive grounding input — without it, the loop would close on
three models agreeing Opus 4.7 doesn't exist.

## Synthesis Observation (Claude)

Claude's synthesis output did three things correctly:

1. **Explicit attribution** — named Gemini and Grok as the source of the "no
   such model" claim rather than treating it as established fact.
2. **Contradiction surfaced** — called out that Perplexity confirms the model
   exists with a 1M context window.
3. **HITL handoff** — explicitly asked the user whether to keep the synthesis
   as-is or overrule, rather than silently picking a winner.

Verbatim: *"Gemini and Grok both claim there is no model named 'Claude Opus
4.7' and refer to Claude 3 Opus with 200K tokens, while Perplexity confirms
Claude Opus 4.7 exists with a 1 million token context window, so I will
clarify in the synthesis that Claude Opus 4.7 is real and has 1M tokens. Do
you want to keep this, or overrule?"*

## What The Guardrails Caught

- Cascading hallucination defense at synthesis worked as designed.
- Without the skepticism clause, a 2-of-3 "agreement" between Gemini and Grok
  would likely have produced a confident "this model does not exist" synthesis.
- The Perplexity fact-check layer provided the external grounding needed to
  break the closed loop.

## What The Guardrails Missed

- Zero confidence qualifier tags in any round-1 response.
- Gemini made a declarative false claim with no `[UNCERTAIN]` tag.
- GPT performed a textbook `[DEFER]` action without using the tag.
- Grok hedged verbally but did not use the tag convention.

Tag adoption is currently 0%. This is tracked as an open issue.

## Follow-ups

- Debug whether `CONFIDENCE_CONVENTION` is actually reaching round-1 prompts
  at runtime (tests pass, but real output suggests review).
- Consider strengthening `CONFIDENCE_CONVENTION` with an in-prompt example
  showing correct tag usage inline.
- Link back here once tag adoption is measurable and non-zero.

## Related

- [ADR 001 — Epistemic Transparency](../decisions/001-epistemic-transparency.md)
- GitHub issue: Confidence qualifier tag adoption gap (link once filed)
