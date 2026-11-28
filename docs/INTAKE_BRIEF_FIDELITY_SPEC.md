# Intake Brief Fidelity — Keep Every Fact the User Stated
## ai-roundtable · JSTcurious · November 2026

**Status:** Approved 2026-11-27: carry-over rule plus an editable stated-facts list at prompt review, in one PR (see Decisions).

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

### 2. Stated facts the user can see and edit (the human check)

The product is a roundtable the user takes part in, not a black box. The
review gate already shows the brief before research, but as one dense
paragraph, and a fact that was dropped or reworded is easy to miss there. So
the facts become a list the user checks.

- **Schema:** `IntakeDecision.stated_facts: list[str]`. The system prompt
  asks for one short line per explicit fact from the original prompt and the
  intake answers, in the user's own words.
- **Config:** `_decision_to_config()` carries `stated_facts`.
  `IntakeSession._route_decision()` adds `original_prompt`.
- **Review gate (`prompt_review`):** sends `stated_facts` next to the brief.
  The review screen shows them under "What I'm telling the panel about your
  situation". The user can edit any line, remove it, or add a missing one.
  "Start Research" and "Submit Adjustment" send the final list back as
  `stated_facts` on `prompt_confirmed` / `prompt_adjusted`.
- **Research input:** after the gate, the brief gets a facts block built by
  `build_stated_facts_block()` in `router.py`:
  - If the user's list (or, from an older client, the intake's list) is
    non-empty, the block lists those facts under a header that says the user
    confirmed them.
  - Otherwise the block falls back to the original prompt verbatim (unless the
    brief already contains it).

  The facts the user saw are the facts the panel gets, word for word.
  Incoming lines are sanitized, stripped, and capped at 20 lines of 300
  characters each.
- The REST path (`/api/session/run`) had no review gate and used the same
  block from the config. It was removed later because nothing called it, so
  the review gate is the only way to start research.

### 3. Fix: corrections at review never reached the four panel models

`ws_session` builds the research transcript *before* the review gate, and the
four research models read their input from that transcript. A "User
correction" typed at review only changed the local `optimized_prompt` string,
which reaches Perplexity and synthesis but not Claude, GPT, Gemini or Grok.
The transcript is now built after the gate, so the corrections and the edited
facts reach all of them.

## Acceptance Criteria

| AC | Criterion |
|---|---|
| AC1 | `_build_combined_prompt()` output contains the user's original prompt verbatim and `BRIEF_FACT_CARRYOVER_RULE`. |
| AC2 | `_build_intake_system_prompt()` contains `BRIEF_FACT_CARRYOVER_RULE`, names THE FACTS AS STATED, and lists `stated_facts` in the JSON schema. |
| AC3 | A completed `IntakeSession` config contains `original_prompt` and `stated_facts`. |
| AC4 | `build_stated_facts_block()`: lists facts when present; falls back to the verbatim prompt when no facts are present; adds nothing when neither is present or the brief already contains the prompt; drops blank lines and enforces the caps. |
| AC5 | Review gate: `prompt_review` carries `stated_facts`. The research transcript for the four panel models contains the facts the user sent back and any `User correction`. |
| AC6 | Review screen shows the facts as editable lines (edit, remove, add) and sends them on confirm and adjust. Frontend build is committed. |
| AC7 | Prompt strings live only in `router.py`. |
| AC8 | **Paid check (manual):** live Sonnet intake on 3 prompts with a self-stated limitation (including the consultancy prompt above) produces a brief and `stated_facts` that state each such fact, before vs. after. |
| AC9 | `uv run pytest` passes. |

## Decisions

1. Both parts ship in one PR: the prompt rule and the editable facts list.
   The verbatim prompt is kept as the fallback when there are no facts.
2. The intake system prompt stays in `openai_client.py` for now. New strings
   go in `router.py`.

## Paid Check Results (AC8, 2026-11-27)

Live Sonnet (`INTAKE_PRIMARY`), closing turn, 3 prompts × 2 runs, old prompt
(`aa524b72`) vs. new. Each session had the background answer, two domain
answers, the output intent, and an assumptions confirmation.

| Prompt (self-stated limit) | Old: fact in brief | New: fact in brief | New: fact in `stated_facts` |
|---|---|---|---|
| Consultancy ("never done a fixed-price deal") | 2/2 | 2/2 | 2/2 |
| Engineer → manager ("never managed anyone") | 2/2 | 2/2 | 2/2 |
| SaaS fundraise ("neither of us has ever raised") | 2/2 | 2/2 | 2/2 |

The new prompt produced 8–11 `stated_facts` per run, each in the user's
wording. These short synthetic sessions **did not reproduce** the production
drop: the old prompt kept the fact in every run. In one old run it survived
only inside the `User background:` line, which is where the production
session reworded it. So this check does not show that the prompt rule alone
fixes the drop. The guarantee comes from the stated-facts list the user
checks at review and the block added to the research input, both covered by
`tests/test_intake_brief_fidelity.py`.
