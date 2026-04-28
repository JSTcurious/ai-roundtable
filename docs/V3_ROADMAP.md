# ai-roundtable — v3 Roadmap

*Authored: April 27 2026*
*Based on: competitive analysis, three test sessions, synthesis failure pattern*

---

## The Core Problem Statement

ai-roundtable has a verification moat that no competitor has.
It has a synthesis execution problem that prevents that moat from being felt.

Every improvement in this roadmap serves one goal: make the synthesis
as good as the fact-checking.

---

## The Principle That Ties Everything Together

Every synthesis failure in v2 testing had the same root cause:
the synthesizer was making judgment calls that the architecture
should have made for it.

Track parity — judgment call.
Model accuracy weighting — judgment call.
Career track depth — judgment call.

The fix is not better instructions.
The fix is an architecture that removes the judgment calls
the synthesizer should not be making.

**Constrain the synthesizer structurally, not instructionally.**

---

## Phase 1 — Two-Call Synthesis for Multi-Track Briefs

**Status:** Not started
**Task file:** feat/two-call-synthesis-multi-track
**Depends on:** Phase 5 (eval harness must exist before merging)

### Problem
The synthesis prompt cannot enforce track parity. Instructions are
not constraints. When the synthesizer sees two competing tracks and
a strong emotional signal on one (e.g. immigration urgency), it
makes a judgment call to prioritize salience over instruction.

Three iterations of TRACK PARITY REQUIRED instructions failed to
produce a synthesis that covered both tracks proportionally.
The synthesizer read the instruction and overrode it every time.

### Fix — Two-call synthesis architecture

When TRACK PARITY REQUIRED is present in the brief:

```
STEP 1 — Detect multi-track brief
  If TRACK PARITY REQUIRED in brief: route to two-call synthesis
  If single-track brief: use existing single synthesis call

STEP 2 — Call 1: Track 1 synthesis only
  System prompt: "You are synthesizing ONLY Track 1.
  Track 2 content exists but is not your concern.
  Produce THE VERDICT, THE HINGE, ONE NEXT ACTION
  for Track 1 only."
  Input: panel responses filtered for Track 1 content

STEP 3 — Call 2: Track 2 synthesis only
  System prompt: "You are synthesizing ONLY Track 2.
  Track 1 content exists but is not your concern.
  Produce THE VERDICT, THE HINGE, ONE NEXT ACTION
  for Track 2 only."
  Input: panel responses filtered for Track 2 content

STEP 4 — Assembly call
  Combine both verdicts into the four-section format:
  THE VERDICT: [Track 1 paragraph] + [Track 2 paragraph]
  THE HINGE: the constraint that governs Track 1 (primary track)
  WHERE THE PANEL DISAGREED: across both tracks
  ONE NEXT ACTION: from Track 1 (user's primary stated intent)
```

### Why this works
The synthesizer cannot collapse tracks it never sees together.
Each call has one job and cannot trade off against the other.
Track collapse becomes architecturally impossible, not just
instructionally discouraged.

### Files to change
- backend/router.py — add two-call synthesis routing logic
- backend/main.py — detect multi-track brief, route accordingly
- tests/ — add multi-track synthesis coverage tests

---

## Phase 2 — Structured Brief Fields (Layer 1)

**Status:** Not started
**Task file:** feat/structured-brief-fields
**Depends on:** Phase 1

### Problem
The current optimized brief buries critical structure in the middle
of long paragraphs. Models weight the beginning and end of prompts
most heavily. Background context appears mid-paragraph. Track parity
appears at the end of a long block. Both get partially ignored.

### Fix — Labeled field structure

Replace the current narrative brief format with labeled fields:

```
DECISION: Should [user] do [action]?

TENSION: [Competing consideration 1] vs [Competing consideration 2]

WRONG ANSWER: An answer that [specific failure mode]

USER BACKGROUND: [Two sentences. Role, what they are building,
what they already know.]

OUTPUT FORMAT: [One sentence. What the user asked for.]

TIMELINE: [One sentence. Urgency level and why it matters.]

TRACK PARITY REQUIRED: [Track names and panel instruction — last,
where model attention is highest.]
```

### Files to change
- backend/models/openai_client.py — _build_intake_system_prompt()
- tests/ — update brief format assertions

---

## Phase 3 — Panel Accuracy Injection and Grok Fix (Layer 2)

**Status:** Not started
**Task file:** fix/panel-accuracy-weighting
**Depends on:** Phase 1

### Problem 1 — Accuracy scores not used
Perplexity produces accuracy ratings for each model after the
fact-check. These ratings are never injected into the synthesis
context. In competitive testing, Grok scored 80% accuracy but
contributed nothing to the synthesis verdict. Claude scored 85%
and was over-weighted. The synthesizer had no instruction to use
the accuracy scores.

### Fix 1 — Inject accuracy scores before synthesis

After Perplexity produces ratings, inject into synthesis context:

```
PANEL ACCURACY RATINGS (from Perplexity fact-check):
Claude:  85% — weight accordingly
Grok:    80% — weight accordingly
Gemini:  70% — weight accordingly
GPT:     55% — weight accordingly

Synthesize primarily from the highest-rated models.
If you rely on a lower-rated model, explain why.
```

### Problem 2 — Grok under-utilized on career track
Grok's CHALLENGER role stress-tests the premise but defaults to
immigration framing when both tracks are present. Career track
challenges are left to Claude (ANALYST) who also dominates immigration.

### Fix 2 — Add career mandate to Grok system prompt

Add to Grok's ROUND1_SYSTEM_PROMPTS entry:

```
If the brief has a career transition track, your primary
value is identifying what the other models missed about
the career move — not just the immigration constraints.
Career conventional wisdom is as worthy of challenge
as immigration conventional wisdom.
```

### Files to change
- backend/router.py — ROUND1_SYSTEM_PROMPTS (Grok entry)
- backend/router.py — synthesis context assembly
- backend/main.py — accuracy score extraction and injection

---

## Phase 4 — Intake Question Expansion

**Status:** Not started
**Task file:** feat/intake-domain-question-expansion
**Depends on:** None (independent)

### Three missing questions identified in competitive testing

**Question 1 — I-485 filing status (immigration domain)**

ChatGPT identified this as the single variable that changes the
entire immigration strategy. It must be asked before any
immigration sequencing advice is given.

```
Question: "Has your I-485 (Adjustment of Status) been filed?"
Chips: Not filed yet
       Filed — pending under 180 days
       Filed — pending 180+ days
       Not sure
```

**Question 2 — Target employer type (career domain)**

Determines H-1B sponsorship likelihood and shapes career advice.

```
Question: "What type of employer are you targeting?"
Chips: Large tech company (FAANG-tier)
       Series B+ startup
       Consulting or staffing firm
       Still exploring — no preference yet
```

**Question 3 — Current ML/AI work proof (career domain)**

Claude's panel response correctly identified this as the first
step in the career track. The intake should capture it upfront.

```
Question: "Do you currently have any ML or AI work you can point to?"
Chips: Yes — deployed in production
       Yes — personal or portfolio projects
       No — starting fresh
       Building now
```

### Files to change
- backend/intake.py — add three questions to domain banks
- tests/ — update minimum question enforcement tests

---

## Phase 5 — Synthesis Eval Harness

**Status:** Not started
**Task file:** feat/synthesis-eval-harness
**Depends on:** None (should be built before Phase 1 merges)
**Priority:** Build alongside Phase 1

### Problem
There is no automated test that verifies synthesis quality.
The only way to catch a synthesis track collapse is to run a
manual session and read the output. This is not scalable.

### Fix — Eval harness with pass criteria

```python
EVAL_PROMPTS = [
    {
        "name": "dual_track_career_immigration",
        "prompt": "I am a software engineer considering a move into
                   AI engineering. I also have an H-1B visa with an
                   approved I-140.",
        "intake_answers": {
            "background": "Software/Data Engineer transitioning to AI",
            "output_intent": "A step-by-step action plan"
        },
        "expected_tracks": [
            "career_transition",
            "immigration_sequencing"
        ],
        "pass_criteria": {
            "verdict_contains_track_1": True,
            "verdict_contains_track_2": True,
            "one_next_action_is_career_not_immigration": True,
            "perplexity_caught_at_least_one_error": True,
            "synthesis_references_accuracy_scores": True
        }
    },
    {
        "name": "single_track_career",
        "prompt": "Help me transition from data engineering to AI
                   engineering. I want a skill-building roadmap.",
        "expected_tracks": ["career_transition"],
        "pass_criteria": {
            "verdict_commits_to_position": True,
            "one_next_action_is_specific": True
        }
    }
]
```

Run this eval before every merge that touches Layer 1, 2, or 3
prompts. A synthesis that fails track parity blocks the PR.

### Files to change
- tests/eval/ — new eval harness module
- Makefile or CI config — run evals on prompt-layer changes

---

## Phase 6 — Evidence Panel UI

**Status:** Not started
**Task file:** feat/synthesis-evidence-panel
**Depends on:** Phase 3 (accuracy scores must exist in backend)

### Problem
The product's moat is invisible. The user sees a synthesis but
does not see that Perplexity caught a fabricated statistic, or
that Grok scored highest and influenced the verdict, or that
Claude made an error that was corrected. The verification
evidence exists but is never surfaced.

### Fix — Evidence panel in synthesis UI

Add a collapsible section below the synthesis output:

```
VERIFIED BY PERPLEXITY
✓ AC21 portability rules — confirmed
✗ Premium processing fee ($2,805) — not verified in current sources
✗ H-1B AI wage prioritization — fabricated statistic, no source

PANEL ACCURACY (this session)
Claude  ████████░░ 85%
Grok    ████████░░ 80%
Gemini  ███████░░░ 70%
GPT     █████░░░░░ 55%
```

This makes the value visible and defensible. A user comparing
ai-roundtable to a single model now has concrete evidence of
what the roundtable caught that a single model would have missed.

### Files to change
- frontend/src/components/SynthesisPanel.jsx — add evidence section
- backend/router.py — expose accuracy scores and fact-check flags
  in the synthesis response payload
- backend/main.py — pass evidence data through WebSocket

---

## Build Order

```
Phase 5 — Eval harness          ← build first, run before every merge
Phase 1 — Two-call synthesis    ← core fix, validate with Phase 5
Phase 2 — Structured brief      ← Layer 1 cleanup
Phase 3 — Panel accuracy        ← model weighting
Phase 4 — Intake expansion      ← I-485, employer type, ML proof
Phase 6 — Evidence panel UI     ← surface the moat
```

Phase 5 and Phase 1 ship together.
Phase 4 is independent and can run in parallel with any phase.

---

## Success Criteria for v3

A v3 session on the career + immigration dual-track prompt must:

1. Show THE VERDICT with two labeled paragraphs — one per track
2. Show ONE NEXT ACTION that serves the career track, not immigration
3. Show Perplexity accuracy ratings that influenced the verdict
4. Show an evidence panel with verified and unverified claims
5. Pass the eval harness automatically before merge

When all five are true, v3 is done.

---

## Known Issues Carried Forward from v2

- Grok stale model ID warnings on startup (cosmetic — aliases resolve)
- Frontend build must be committed manually after JSX changes
- No CI pipeline — all tests run manually with uv run pytest
- Intake max 7 questions not yet enforced

---

*See also:*
*docs/COMPETITIVE_ANALYSIS.md — six-model benchmark, April 27 2026*
*LESSONS.md — three failure post-mortems from v2 development*
