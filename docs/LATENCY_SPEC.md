# Session Latency — Faster First Draft
## ai-roundtable · JSTcurious · November 2026

**Status:** Approved 2026-11-27 with the recommended answers to all open questions (see Decisions).

---

## Problem Statement

A smart-tier session takes about 3.5 minutes from "confirm brief" to the
first synthesis draft, and the screen shows no research text for the first
minute of that.

The first session timed in production (2026-11-27, PR #55 stage logs,
pipeline healthy, no retries or fallbacks):

| Stage | Time | Running total | How it runs today |
|---|---|---|---|
| Research | 66.6s | 67s | 4 models in parallel; nothing shown until the slowest returns |
| ↳ Perplexity pre-research | 8.1s | | 1 call |
| ↳ Grok | 25.2s | | executor → advisor |
| ↳ GPT | 30.8s | | executor → advisor |
| ↳ Gemini | 40.8s | | executor → advisor |
| ↳ **Claude** | **66.6s** | | Sonnet executor → Opus advisor |
| Research emit | 0.0s | | finished text sent in 48-char chunks |
| Fact-check | 9.9s | 77s | Perplexity audit |
| Self-critique | 44.3s | 121s | 1 Sonnet call, `max_tokens=4096` |
| **Synthesis** | **84.3s** | **205s** | Sonnet executor → Opus advisor, not streamed |

Three findings in the code explain most of this:

1. **Smart-tier synthesis runs two calls, one after the other, and ignores the
   configured model.** `call_synthesis_async` (backend/main.py) sends smart
   tier to `call_claude_smart_async`, which has Sonnet write a draft and then
   Opus rewrite it. `synthesis.primary` (`SYNTHESIS_ANALYTICAL`, Opus) is used
   only on deep tier. The startup table says Opus synthesises; on smart tier
   Sonnet writes first and Opus rewrites.
2. **The Claude research seat sets the research time.** The other three seats
   finished 26–42s before Claude, and their text waited for it.
3. **Self-critique is labelled a quick pre-flight check** ("Bullet points only…
   This is a pre-flight check") but has a 4,096-token output budget and took 44s.

Refinement (`call_synthesis_refinement`) is already a single Opus call, but it
isn't streamed. Its time hasn't been measured yet, because the timed session
finalized without a dialogue turn.

---

## Goals

- Cut median time to first draft (`[TIMING] first_draft total=`) on smart tier
  from 205s to **≤ 110s**.
- First research text on screen within **≤ 35s** of confirming the brief.
- First synthesis words on screen within **≤ 15s** of synthesis starting, for
  the initial draft and for every refinement.
- No loss of synthesis quality: the paid live check
  (`tests/test_live_synthesis_post_cutoff.py`) passes, and the four required
  sections are always present.

## Non-Goals

- Deep tier. It already uses single Opus calls. Changes here must not
  slow it down.
- Model selection. The registry roles keep their current models. This spec
  changes how many calls a stage makes and when its output is shown, not
  which models run.
- Intake latency (about 8s per answer, acceptable).
- Making the fact-check faster (10s).
- Retry and backoff policy for Gemini 503s. They didn't affect this session.
  That's a separate change if the timing logs later show them costing time.

---

## Design

Changes are listed in order of measured gain. Each one can ship and be
measured on its own.

### L1 — Synthesis: one streamed call (est. −35 to −45s, first words in seconds)

- Smart-tier synthesis makes **one** call to `SYNTHESIS_ANALYTICAL`, the same
  as deep tier. The Sonnet→Opus pattern is removed from the synthesis path only
  (research seats keep their own, see L3).
- The call is streamed. Each text chunk goes to the client as
  `{"type": "synthesis_token", "token": "..."}`.
- When the stream ends, the backend runs `parse_closing_questions()` on the
  full text and sends the existing `synthesis_draft` frame with the cleaned
  content. The frontend replaces the streamed text with it. The draft content
  and closing questions are exactly what the client gets today.
- **Failure handling:**
  - Fails before the first token: same as today. Fall back to
    `SYNTHESIS_FALLBACK` (Qwen, not streamed).
  - Fails after tokens were sent: send `{"type": "synthesis_reset"}` so the
    client clears the partial text, then fall back to Qwen.
  - Client disconnects mid-stream: the stream is closed and the handler exits
    (close paths must stay clean, see AC10).
- The Anthropic client already supports `stream=True`
  (`call_claude(..., stream=True)` returns the SDK stream). The streaming
  iterator runs in a thread, like `_stream_tokens` in main.py.
- **Evidence for quality:** ADR 002's addendum re-ran its post-cutoff fixture
  T1 as a single Opus call: 3/3 correct, 0 refusals, matching the smart path's
  9/9. One fixture is thin, so AC9 adds the live check before merge.

### L2 — Refinement: streamed (first words in seconds)

- `call_synthesis_refinement` keeps its single Opus call but streams it, using
  the same `synthesis_token` / `synthesis_draft` / `synthesis_reset` frames as L1.
- Refinement failure keeps today's behaviour (`[Refinement unavailable: …]`).
  If it fails after tokens were sent, a `synthesis_reset` goes out first.

### L3 — Research: show each seat when it finishes (first text at ~25s)

- Each research seat's text is sent (`token` chunks, then `model_complete`)
  as soon as its own call returns, instead of after all four return.
  Implementation: each gathered coroutine sends its own text before it
  returns. The shared `send_lock` keeps frames from interleaving.
- Transcript order stays fixed (Gemini, GPT, Grok, Claude), so synthesis
  input doesn't depend on which model finished first.
- The frontend already handles `token` and `model_complete` per sender
  (SessionView.jsx), so no frontend change is expected. AC6 checks it.
- The total research time doesn't change. The `research.emit` timing line is
  removed, since sending now happens inside each seat's own time.

### L4 — Claude research seat: one call (est. −25s, research then ends with Gemini at ~41s)

- **Needs a decision (Q1).** The Claude seat uses Sonnet executor → Opus
  advisor today. Proposal: smart-tier Claude research makes one call to
  `research.claude.advisor` (Opus), the same model the deep tier already uses
  for this seat.
- The other three seats keep executor → advisor. They aren't on the critical
  path once Claude is faster: Gemini at ~41s becomes the slowest.

### L5 — Self-critique: short and capped (est. −25 to −35s)

- Give the self-critique call its own output cap of **1,200 tokens**, instead
  of the 4,096 shared with every `call_claude` caller. The prompt already asks
  for "bullet points only"; the cap enforces it.
- `call_claude` gains an optional `max_tokens` parameter. It defaults to 4096,
  so other callers are unchanged.
- If the cap cuts the output short, the truncated notes are still injected,
  followed by a line saying they were truncated.
- **Not proposed:** running self-critique alongside the fact-check. It reads
  the audit, so it would need the pre-research text instead. That's a bigger
  prompt change for at most 10s. Revisit if L5 isn't enough (Q3).

### Timing additions

- `synthesis.first_token` and `refinement.N.first_token`: seconds from the
  call starting to the first chunk sent to the client.
- `research.<seat>.shown`: when each seat's text finished sending.
- The `first_draft` summary line stays, so before/after numbers can be
  compared from the logs.

### Expected result

| Stage | Today | After L1–L5 |
|---|---|---|
| Research | 66.6s | ~41s (Gemini) |
| Fact-check | 9.9s | ~10s |
| Self-critique | 44.3s | ~12s |
| Synthesis | 84.3s | ~40–50s, first words in < 15s |
| **First draft** | **205s** | **~105–115s** |

These are estimates from one session. The goal is checked against the
median of the first five production sessions after deploy (AC11).

---

## Acceptance Criteria

All run under `uv run pytest` with mocked providers, except AC9 and AC11.

- **AC1** Smart-tier synthesis makes exactly one Anthropic call, with model
  `SYNTHESIS_ANALYTICAL`, and doesn't call `call_claude_smart`/`_async`.
- **AC2** Synthesis streams: at least one `synthesis_token` frame arrives
  before `synthesis_draft`. The concatenated tokens equal the model's raw
  text. `synthesis_draft.content` and `closing_questions` equal
  `parse_closing_questions(raw)`.
- **AC3** Synthesis fails before the first token: no `synthesis_token`
  frames, Qwen fallback is called, and `synthesis_draft` arrives with
  `synthesis_route="fallback"`.
  Synthesis fails after tokens were sent: `synthesis_reset` comes before the
  fallback's `synthesis_draft`.
- **AC4** Refinement streams: `synthesis_token` frames come before the
  revised `synthesis_draft`, and the revision number increments. Mid-stream
  failure sends `synthesis_reset`, then the `[Refinement unavailable: …]` draft.
- **AC5** With research mocks returning at 0.0s (Grok) and 0.3s (Claude),
  Grok's `model_complete` is sent before Claude's call returns. The transcript
  order is still Gemini, GPT, Grok, Claude.
- **AC6** The frontend renders a seat's text when its `model_complete`
  arrives, even if the other seats are still pending (checked in the browser
  pane on a local session with mocked delays). It shows streamed synthesis
  text, then swaps in the cleaned draft, with the DRAFT/REVISED badge
  unchanged. It clears the text on `synthesis_reset`.
- **AC7** (if Q1 is approved) Smart-tier Claude research makes one call with
  model `research.claude.advisor`. Deep tier is unchanged.
- **AC8** Self-critique calls `call_claude` with `max_tokens=1200`. Every
  other caller still gets 4096. Output that hits the cap is still injected,
  marked as truncated.
- **AC9** Paid live check passes:
  `RUN_LIVE_EVALS=1 uv run pytest tests/test_live_synthesis_post_cutoff.py`.
  The test is updated to exercise the new single-call smart path.
- **AC10** `tests/test_ws_close_paths.py` passes, plus a new close path:
  the client disconnects during a synthesis stream. No server traceback, and
  the handler exits.
- **AC11** After deploy, the median `first_draft total` across the next five
  production sessions is ≤ 110s, and every session shows
  `synthesis.first_token` ≤ 15s. Measured from the Railway logs and recorded
  in this spec's Implementation Notes.
- **AC12** `[TIMING]` lines include `synthesis.first_token`,
  `refinement.N.first_token` and `research.<seat>.shown`. `research.emit` is
  gone.

---

## Implementation Tasks

Each can be its own PR, in this order, and each is measured after deploy
before the next one ships.

1. **L1 + L2 + timing:** streamed single-call synthesis and refinement,
   `synthesis_token`/`synthesis_reset` frames, SynthesisPanel streaming
   render, frontend rebuild committed. ACs 1–4, 6 (synthesis part), 9, 10, 12.
2. **L3:** per-seat emit. ACs 5, 6 (research part), 12.
3. **L5:** self-critique cap. AC8.
4. **L4:** Claude research seat single call (only if Q1 is approved), with a
   paid live session before merge. AC7.
5. Record before/after numbers (AC11).

## Estimated Effort

PR 1 is the largest: about a day including frontend streaming and close-path
tests. PRs 2–4 are a few hours each.

---

## Decisions (2026-11-27)

- **Q1:** Yes. Smart-tier Claude research makes one call to
  `research.claude.advisor` (L4, PR 4).
- **Q2:** Yes. Smart and deep tier both make one synthesis call; the tiers
  still differ in research.
- **Q3:** The self-critique cap starts at 1,200 tokens. If AC11 isn't met,
  next is running self-critique alongside the fact-check.
- **Q4:** Four PRs, in the order under Implementation Tasks. This spec lands
  with PR 1.

## Implementation Notes

### PR 1 — L1 + L2 + timing (2026-11-27)

- `stream_claude_text()` (anthropic_client.py) makes one streamed call and
  awaits an `on_token` callback per chunk. Model errors are raised as
  `StreamFailed(tokens_sent=…)`; an exception from `on_token` propagates
  unchanged and stops the SDK stream.
- `call_synthesis_async()` makes one call to the given Claude model on every
  tier, streamed when `on_token` is passed. `_call_with_retry_async()` never
  retries a `StreamFailed` that already sent text.
- `call_synthesis_refinement()` takes an optional `on_token`; a failed model
  call returns the unavailable dict with `"error": True`.
- In the session, `_SynthesisStream` sends `synthesis_token` frames and logs
  `<stage>.first_token`. A failed send raises `ClientGone`, which ends the
  session quietly without trying the Qwen fallback.
- Frontend: `synthesisStreamText` holds streamed text. While it's non-empty,
  SynthesisPanel shows it with the streaming cursor (a refinement shows as the
  next REVISED round). `synthesis_draft`, `synthesis_final` and
  `synthesis_reset` clear it.
- Existing tests that mock `call_synthesis_async` / `call_synthesis_refinement`
  keep working: the mocks accept the new `on_token` keyword and simply don't
  stream.

**Verification:**
- `tests/test_latency_synthesis_stream.py` covers AC1–AC4, AC10 and AC12
  (8 tests). `tests/test_ws_close_paths.py` path 7 covers a client that closes
  or drops TCP mid-stream on a real uvicorn server.
- `uv run pytest`: 358 passed, 1 skipped.
- AC6 (synthesis part), checked in the browser against a local mock backend
  with staggered delays: the draft and refinement stream in with the cursor
  and the REVISED badge, and a refinement failing mid-stream clears the
  partial text before the unavailable notice.
- Still to do: AC9 (paid live check) and AC11 (production medians after
  deploy).

## Open Questions (resolved, kept for the record)

- **Q1 — Claude research seat: one Opus call instead of Sonnet → Opus?**
  Recommended: yes. It's the critical path (66.6s vs 40.8s for the next
  seat), and deep tier already runs this seat as a single Opus call. Risk:
  the Analyst seat's output may differ. Check by comparing one live
  session's Claude seat before and after.
- **Q2 — Should smart and deep tier still differ for synthesis?** After L1,
  both make one `SYNTHESIS_ANALYTICAL` call. Recommended: accept that. The
  tiers still differ in research (deep uses single deep-model calls for every
  seat). Alternative: deep tier keeps something extra, such as a higher
  output budget.
- **Q3 — Self-critique cap value.** 1,200 tokens is proposed from the prompt's
  four bullet sections. If AC11 isn't met after L5, the next step is running
  self-critique alongside the fact-check on the pre-research text instead of
  the audit.
- **Q4 — One PR or four?** Recommended: four, in the order above, so each
  change is measured on its own with the `[TIMING]` lines.
