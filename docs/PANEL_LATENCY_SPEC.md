# Panel Latency — Phase 2a Follow-up Spec

Status: **APPROVED 2026-11-28** — Q1–Q5 approved as proposed (§7)
Follows: [PANEL_FACTCHECK_SPEC.md](PANEL_FACTCHECK_SPEC.md) (PR 64, merged) and
[LATENCY_SPEC.md](LATENCY_SPEC.md). Out of scope: the claim auditor and the new
synthesis (Phase 2b), streaming research text, changes to synthesis or
refinement.

---

## 1. Problem

The first production session after Phase 2a (2026-11-28, PR 64 live) took
**205s to the first draft**. The session before it, on the Phase 1 code, took
140s. LATENCY_SPEC's target is ≤ 110s.

| Stage | Phase 1 session | Phase 2a session | Change |
|---|---|---|---|
| Panel router | – | **17.6s** | new, target ≤ 8s |
| Research (slowest seat = Claude) | 62.2s | **106.5s** | +44s |
| ↳ Grok / GPT / Gemini | 42.5 / 25.2 / 41.9s | 23.6 / 33.5 / 47.4s | about the same |
| Seat parse | – | 2.4s | new (so at least one seat was repaired) |
| Fact-check | 7.6s | 7.8s | – |
| Self-critique | 17.6s | 22.9s | +5s |
| Synthesis | 52.7s | 48.2s | – |
| **First draft total** | **140.1s** | **205.4s** | **+65s** |

The two sessions used different prompts and are one run each, so the table is
indicative. The two new costs are the router and the Claude research seat.
Research time is set by its slowest seat, so Claude's extra 44s adds to the
total directly, and the router runs before research starts, so its 17.6s adds
on top.

## 2. Evidence (measured locally 2026-11-28, one call at a time, live)

A first attempt that ran nine calls at once took ~100s each. That was
throttling, not model speed, and is discarded. Sequential results:

**Router** (a 150-word brief with placeholders, 3 runs each, all plans valid):

| Variant | Median time | Output tokens |
|---|---|---|
| Current prompt (Sonnet) | **17.5s** (production: 17.6s) | 755 |
| Same + length limits (mandate ≤ 30 words, guardrail ≤ 25, title ≤ 6) | **10.4s** | 507 |
| Same limits on Haiku | **7.0s** | 527 |
| Tighter limits (mandate ≤ 20, guardrail ≤ 15, title ≤ 5, domain ≤ 5), Sonnet, 4 runs | **8.9s** (8.3–9.3) | 440 |

Time follows output tokens (about 50 tokens a second plus ~1–2s of fixed
overhead), so the lever is how much the router is asked to write. The tighter
limits still gave valid plans every time with sensible roles (Migration
Execution Lead, Cloud FinOps Analyst, Compliance & Contract Counsel, an
ecosystem/ML strategist) and a longest mandate of 19 words. Haiku saves
another ~2–3s but its titles were vaguer ("Platform Strategy & Ecosystem",
"Financial & Risk Officer"); it was only measured at the looser limits.

**Claude research seat** (Sonnet executor, then Opus advisor rewrite, the smart
tier path), old prose prompt vs the Phase 2a JSON seat prompt vs the JSON
prompt with length caps:

Two runs of each, one call at a time (executor = Sonnet, advisor = Opus):

| Variant | Run 1 total | Run 2 total | Advisor output | Words | JSON valid |
|---|---|---|---|---|---|
| Old prose prompt | 89s | 74s | 2,204 / 1,841 tok | 1,353 / 1,059 | n/a |
| JSON seat (Phase 2a, live now) | 104s | **210s** | 2,341 / 2,132 tok | 1,499 / 1,304 | yes / yes |
| JSON seat + caps (core_assessment ≤ 350 words, ≤ 4 one-sentence items per list) | **53s** | **44s** | 1,214 / 1,061 tok | 707 / 596 | yes / yes |

What this shows:
- The JSON seat writes about 1.7x more than the old prose seat in its first
  pass (2,222 and 2,009 tokens against 1,313 and 1,224), because it adds
  three lists on top of a full-length assessment. More output is more time.
- With caps the same seat finished in about half the time, in both runs, with
  valid JSON both times, and about half the words of the prose seat.
- One JSON run had a 162s Opus pass for 2,132 tokens (13 tokens a second,
  against 40+ in the other runs). That is API variance, not the prompt, and it
  is why the production Claude seat can take anywhere from 60s to 110s.
  Shorter output makes such spikes cheaper but cannot remove them; two runs
  per variant is not a median to lean on, only a clear direction.

## 3. Goals / non-goals

Goals
- G1. Router median ≤ 10s (measured 8.9s with the proposed limits; 17.5s now),
  with plans of the same quality (valid JSON, roles fit the decision,
  placeholders kept).
- G2. The research stage is no slower than before Phase 2a (slowest seat
  ≈ 60–70s).
- G3. Median first draft **≤ 150s**: the pre-router baseline (140s) plus the
  router's ~9s. Expected from the measurements: router 9s, research ≈ 55–60s
  (down from 106s), the rest unchanged, so about 145s. LATENCY_SPEC's 110s stays
  the longer-term target; this spec does not claim it.
- G4. The next production log shows, per seat, whether it answered in JSON, was
  repaired, or fell back to text, and how long its answer was.
- G5. Seat and plan quality is unchanged: `tests/test_live_panel.py` passes.

Non-goals: Haiku for seats or synthesis; parallelizing the router with research
(seats depend on its plan); fact-check or synthesis changes.

## 4. Design

### 4.1 Router output limits (`PANEL_ROUTER_SYSTEM`)

Add length limits to the router prompt: title ≤ 5 words, mandate ≤ 20 words,
guardrail ≤ 15 words, domain ≤ 5 words (measured: 8.9s, 440 tokens, plans valid
in 4 of 4 runs). The seat template already carries the
mandate and guardrail into every seat prompt, so short briefs are enough, and
the seat's own prompt does the detailed work. `PANEL_ROUTER_MAX_TOKENS` drops
from 1200 to 700 so a runaway reply cannot cost more than ~14s (the plan is
about 440 tokens).

### 4.2 Seat length limits (`SEAT_JSON_RULES`)

Add to the seat output rules: `core_assessment` at most 350 words, every list
item one sentence, `cross_functional_conflicts` and `blind_spots_flagged` at
most 4 items each. `falsifiable_claims` stays at 6 (PR b audits them). The
limits apply to all four seats, since research waits for the slowest and every
seat feeds the synthesis; shorter, focused seats also give the synthesizer less
to wade through. The Opus rewrite pass stays (§7 Q3).

### 4.3 Observability (`router.py`, `main.py`)

- `SeatResult` gains `repaired: bool` (set by `structure_seat` when the repair
  call produced the result).
- After `seat_parse`, one log line: `[SEATS] gpt=json:1820ch gemini=repaired:2410ch
  grok=json:1630ch claude=degraded:5120ch`, where the number is the length of
  the raw reply. No content is logged.
- `PipelineHealth.summary()` already reports router fallback; it also lists
  repaired seats so `[SESSION]` shows them.

## 5. Acceptance criteria

- **AC1** `PANEL_ROUTER_SYSTEM` states the four limits; `PANEL_ROUTER_MAX_TOKENS`
  ≤ 700.
- **AC2** `SEAT_JSON_RULES` states the seat limits chosen in §7 Q2.
- **AC3** `structure_seat` marks `repaired=True` only when the repair call
  produced the result; a valid first reply and a degraded seat are `False`.
- **AC4** The `[SEATS]` line appears once per session with all four labs and
  no seat content; the `[SESSION]` summary names repaired seats.
- **AC5 Live quality.** `tests/test_live_panel.py` passes, and a new check
  asserts every mandate ≤ 30 words (headroom over the prompt's 20) and a real
  seat's `core_assessment` is within the cap plus 25%. Quality is also read by
  a person: the capped and uncapped Claude seat answers to the same brief are
  put side by side in §8 so the loss, if any, is visible.
- **AC6 Measured effect.** The local scripts (`router` and `claude seat`) are
  rerun after the change (4+ sequential runs each); before/after medians go
  in §8. The router median must be ≤ 10s and the capped Claude seat's median
  must be ≤ 70s. If either misses, Q1 or Q3 is revisited before merge.
- **AC7 Production check.** After deploy, one session's `[TIMING]` and `[SEATS]`
  lines are read and recorded in §8 (G2, G3).
- **AC8** The full suite passes with `uv run pytest`.

## 6. Tasks

1. Router prompt limits and `PANEL_ROUTER_MAX_TOKENS` (tests first: AC1).
2. Seat prompt limits (AC2).
3. `SeatResult.repaired`, the `[SEATS]` log and the health summary (AC3, AC4).
4. Claude seat advisor decision from §7 Q3, if it changes code.
5. Live checks (AC5), local re-measurement (AC6), notes in §8.

## 7. Decisions (approved 2026-11-28 — all proposed answers accepted)

- **Q1. Router model and target.** *Proposed:* **keep Sonnet with the 20/15/5-word
  limits** (§4.1) and set the router target at ≤ 10s. Measured 8.9s, a second
  over the original 8s, from 17.5s now. Haiku would likely reach ~6s but
  writes vaguer roles, and the roles shape every seat's brief, so I would not
  trade role quality for 3s. The alternative is Haiku at the tighter limits (not
  yet measured) if you want the 8s target held.
- **Q2. Seat length limits.** *Proposed:* `core_assessment` ≤ 350 words, lists
  ≤ 4 one-sentence items (§4.2). This is the one change that trades depth for
  speed, so it is yours to weigh: the prose seats wrote 1,000–1,350 words and the
  capped seat 600–700. I only measured these limits, so a looser cap (for
  example 500 words) is an untested middle. If you would rather keep depth,
  say so and we use 500 and re-measure. Either way, AC5 puts the capped and
  uncapped answers side by side.
- **Q3. The Claude seat's Opus rewrite pass.** *Proposed:* **keep it.** With the
  caps it takes 20–24s, and it is where an Opus pass reviews the Sonnet draft
  against the seat's instructions (your "quality ceiling, not cost floor"
  rule). Dropping it would save about that much more (≈ 25–30s for the seat)
  and is the next lever if AC6/AC7 miss the Claude-seat target. The other
  three seats run the same two-pass path and already finish faster.
- **Q4. Target.** *Proposed:* the interim target is **≤ 150s** (the 140s
  pre-router baseline plus the router's ~9s), not LATENCY_SPEC's 110s. The
  router is a deliberate new stage and 110s was set before it existed.
  Reaching 110s would need further levers (for example the self-critique at
  23s, or dropping an Opus rewrite pass), which can be a separate spec. Say so
  if you want 110s held.
- **Q5. How to verify.** *Proposed:* the local scripts for the numbers (cheap,
  repeatable, sequential, at least 4 runs per variant because Claude's speed
  varies a lot between calls) plus one production session after deploy for the
  real-world total. A single production run is too noisy to prove anything on
  its own.

## 8. Implementation Notes

Built 2026-11-28 on `fix/panel-latency`. The design is as in §4; no deviations.

### Measured effect (AC6), real code, one call at a time

| | Before (Phase 2a) | After | Target |
|---|---|---|---|
| Router, median of 5 | 17.5s (production 17.6s) | **7.5s** (7.2–7.9s, all plans valid) | ≤ 10s ✅ (also under the original 8s) |
| Claude seat, Sonnet + Opus rewrite, JSON, uncapped, 2 runs | 96s, 90s (earlier session: 104s, 210s) | – | – |
| Claude seat, same, **capped**, 4 runs | – | **53s, 42s, 56s, 53s** (median 53s) | ≤ 70s ✅ |
| Seat output (core_assessment) | 795–823 words | **313–343 words** | ≤ 350 |

The router roles stayed consistent run to run (a migration lead, a strategy
or ecosystem analyst, a commercial or FinOps analyst, a compliance and
contract risk officer). All six capped and uncapped seat replies were valid
JSON. Estimated first draft with these numbers: router 7.5s + research ≈ 55s +
seat parse 2.4s + fact-check 8s + self-critique 23s + synthesis 48s ≈ **145s**
(target ≤ 150s). This is an estimate from stage times; AC7 (one production
session after deploy) gives the real figure.

### Quality read (AC5): capped vs uncapped, same brief

The compliance seat for the cloud-migration brief, same router seat, same
Sonnet-then-Opus path:

- **Both** reach the same strongest claim: the migration window, not the
  destination cloud, is the compliance risk, under the client's contract.
  Both cite the HIPAA business-associate rule, both note that an SOC 2 Type II
  observation period can overlap the migration, and both flag that the brief
  does not state the client's jurisdiction and that the contract may carry a
  change-approval clause.
- **The capped answer drops** the uncapped answer's numbered walk through the
  hybrid period (BAA coverage gaps while both clouds are live, a log rule
  routing PHI to an uncovered environment, differences in BAA scope and
  indemnification between providers) and one claim and one blind spot. It adds
  the savings-erosion point (egress fees and dual-running costs against the
  25% threshold).
- Net: the cap loses worked examples and some detail, not the conclusion or
  the main blind spots. That is the trade Q2 asked you to weigh. If the loss
  matters in real sessions, the next step is a 500-word cap (untested), then
  re-measure.

### Not yet done

- **AC7:** one production session after deploy, to read the real `[TIMING]`,
  `[PANEL]` and `[SEATS]` lines and the first-draft total. Record it here.
- Claude's speed varies a lot between calls (one earlier Opus pass took 162s
  for 2,100 tokens). Caps make such spikes shorter but cannot remove them, so
  one slow production session does not by itself mean the fix failed.
