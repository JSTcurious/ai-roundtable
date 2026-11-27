# Intake Brief Fidelity — Keep Every Fact the User Stated
## ai-roundtable · JSTcurious · November 2026

**Status:** Draft, awaiting approval.

---

## Problem Statement

The intake's `optimized_prompt` (the research brief) is the only text the
four research models and Perplexity see. Any fact it drops is invisible to
every later stage.

Production session, 2026-11-27. The user asked:

> I run a 3-person data consultancy. A client offers a $180k fixed-price
> contract to build a data platform in 4 months, but we've never done a
> fixed-price deal. Should we accept, counter with time-and-materials, or
> decline?

The brief intake wrote kept the team size, the $180k, the 4 months, and the
three options. It **left out "we've never done a fixed-price deal."** The
closest it came was "has built two similar … platforms on
time-and-materials", which is not the same claim. That fact was the center of
the question: with no history of estimating fixed-price work, any fixed price
is a guess. None of the four research models or the synthesis raised it. A
competing tool built its whole answer on it.

## Cause

The original prompt does reach the intake model word for word
(`IntakeSession._build_combined_prompt()` starts with `Original prompt: …`).
The fact is lost when the brief is written:

1. **The brief template has no place for stated facts.** The
   `optimized_prompt` rules in `_build_intake_system_prompt()`
   (`backend/models/openai_client.py`) require exactly five short prose
   parts: decision, tension, wrong answer, output format, pressure. Each is one
   or two sentences. Nothing asks the model to carry over what the user said
   about their situation. Facts survive only if they happen to fit into the
   tension or the wrong answer. A limitation the user states about
   themselves ("we've never done X") is the kind of detail that gets
   compressed into a looser paraphrase.
2. **The only preservation rule covers proper nouns.** The system prompt and
   the per-turn instruction both say to keep proper nouns. Neither says to
   keep facts, numbers, or constraints.
3. **No backstop.** `_enrich_prompt()` (`backend/main.py`) appends the
   background answer, corrections, open questions and output intent, but
   never the user's original question. When the brief drops a fact, nothing
   puts it back.

## Goals

- Every explicit fact, number, constraint, and self-stated limitation in the
  user's original prompt reaches the research panel.
- The brief engages with those facts. It doesn't just list them.
- A guarantee that doesn't depend on the model following the rule.

## Non-Goals

- Moving `_build_intake_system_prompt()` into `router.py`. CLAUDE.md says all
  prompt strings live there, but moving the whole intake prompt is a separate
  refactor. New strings from this change go in `router.py`.
- The mortgage-session drift, where intake questions followed an H-1B detail
  from the background answer instead of the question asked. That is question
  selection (the immigration guard reads `_accumulated_context()`, which
  includes the background answer), not brief writing. It's a follow-up.
- Synthesis, self-critique and research timing (owned by the latency effort).
- The unused `GEMINI_INTAKE_SYSTEM` in `google_client.py`.

## Design

### 1. Carry-over rule (prompt)

A new constant `BRIEF_FACT_CARRYOVER_RULE` in `backend/router.py`, used in
two places:

- **System prompt:** `_build_intake_system_prompt()` adds a new brief part,
  **THE FACTS AS STATED**, right after THE DECISION (and after the
  `User background:` line). It is one to three sentences, close to the
  user's own wording, covering every explicit fact from the original prompt.
  The rule also says that if a stated fact is a limitation or a first-time
  condition ("never done", "only once", "no experience with"), THE TENSION
  or THE WRONG ANSWER must address it. The Quality Bar list gets a matching
  bullet.
- **Per-turn instruction:** `_build_combined_prompt()` appends the same rule
  next to the existing proper-noun rule and labels the first line
  `Original prompt (verbatim, user's own words): …`.

Draft rule text:

> FACT CARRY-OVER — CRITICAL: Every explicit fact the user stated in their
> original prompt must appear in the optimized_prompt: numbers, amounts,
> durations, team or company size, the options they named, and anything they
> said about their own experience or limits (e.g. "we've never done X",
> "only once", "first time"). Use the user's wording. Never replace a fact
> with a weaker or different paraphrase ("has done Y" is not "has never done
> X"). If a stated fact is a limitation or a first-time condition, THE
> TENSION or THE WRONG ANSWER must address it directly. Intake answers add to
> the original prompt. They never replace it.

### 2. Verbatim backstop (code)

- `IntakeSession._route_decision()` saves `original_prompt` in
  `session_config` (sanitized, like the rest of the config).
- `_enrich_prompt()` appends
  `The user's original question, in their own words: "<original_prompt>"`
  when it is present and is not already contained in the brief. This
  covers the research panel, Perplexity, and everything downstream that
  uses the enriched prompt.

The cost is about 50 extra input tokens per research call. It doesn't affect
latency.

## Acceptance Criteria

| AC | Criterion |
|---|---|
| AC1 | `_build_combined_prompt()` output contains the user's original prompt verbatim and `BRIEF_FACT_CARRYOVER_RULE`. |
| AC2 | `_build_intake_system_prompt()` contains `BRIEF_FACT_CARRYOVER_RULE` and names the THE FACTS AS STATED part. |
| AC3 | A completed `IntakeSession` config contains `original_prompt` equal to the user's prompt. |
| AC4 | `_enrich_prompt()` appends the verbatim original prompt once, and doesn't append it when the brief already contains it or the key is missing. |
| AC5 | The rule string is defined only in `router.py`. |
| AC6 | **Paid check (manual):** live Sonnet intake on 3 prompts (the consultancy prompt above plus two others with a self-stated limitation) produces briefs that state each such fact, before vs. after. |
| AC7 | `uv run pytest` passes. |

## Open Questions

1. **Include the verbatim backstop (Design §2)?** Proposed: yes. The prompt
   rule alone is probabilistic. The backstop makes the guarantee
   deterministic for about 50 tokens.
2. **Leave the intake system prompt in `openai_client.py` for now?**
   Proposed: yes, and do the move separately.
