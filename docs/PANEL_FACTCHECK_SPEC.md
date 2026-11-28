# Dynamic Panel, Atomic Fact-Check & Dissent-Preserving Synthesis — Phase 2 Spec

Status: **APPROVED 2026-11-28** — Q1–Q7 approved as proposed (§7). Built as two PRs (Q4): PR a = tasks 1–3, PR b = tasks 4–6.
Builds on: [PRIVACY_SECURITY_SPEC.md](PRIVACY_SECURITY_SPEC.md) (Phase 1, merged in PR 63).
Out of scope: the Chair pause/resume gate and the disclosure export (Phase 3),
any new UI.

---

## 1. Problem

1. **The panel is the same four fixed personalities for every question.**
   `ROUND1_SYSTEM_PROMPTS` gives Claude the Analyst, GPT the Pragmatist, Gemini
   the Scout and Grok the Challenger whether the user asks about a product
   launch or a cloud migration. Nobody on the panel owns Finance or Legal
   unless the model happens to raise it.
2. **Research output is free prose.** There is no machine-readable list of what
   each seat claims as fact, what it thinks the panel is missing, or where it
   disagrees with another function.
3. **The fact-check summarises instead of auditing.** `audit_with_fallback`
   asks Perplexity for a prose audit of whole responses. Individual claims are
   not checked one by one, and there is no record of which claim came from
   which model, which source backed it, or how strong that source was.
4. **Nothing forces the synthesis to keep disagreement or flag unverified
   claims.** The current prompt asks for it in one line
   ("do not smooth over real disagreements"); an unverified claim can still be
   written up as fact.

## 2. What the code looks like today (map)

| Concern | Where |
|---|---|
| Fixed seat prompts | `router.py` `ROUND1_SYSTEM_PROMPTS` (+ `get_round1_system_prompt`), cognitive roles also described in `LandingPage.jsx` |
| Fan-out | `main.py` `session_websocket`: four `call_research_*_async` plus `perplexity_research`, one `asyncio.gather`; smart tier = executor then advisor (a rewrite pass) |
| Text shown to the user | each seat's finished text is chunked into `token` frames, then `model_complete`; the UI renders the string as is |
| Fact-check | `perplexity_client.audit_with_fallback`: Sonar Pro → Sonar → GPT-5.4 web search → emergency string; returns `(audit_text, provider, citations)` |
| Evidence into Claude | `build_synthesis_system` / `call_self_critique` / `call_synthesis_refinement` wrap `audit_text` and citations in `<untrusted_search_evidence>` (Phase 1) |
| Synthesis | `SYNTHESIS_SYSTEM_PROMPT`: sections THE VERDICT, THE HINGE, WHERE THE PANEL DISAGREED, ONE NEXT ACTION, then closing `?` questions |
| Frame metadata | `synthesis_draft` / `synthesis_final` already carry `privacy_audit` |

Two existing constraints shape the design:

- **CLAUDE.md fixes two things Phase 2 touches.** The cognitive roles must stay
  aligned with the landing page, and synthesis must produce the four named
  sections. §7 Q1 and Q2 ask how to handle each.
- **LATENCY_SPEC targets a first draft in ≤ 110s.** A router call before the
  fan-out adds time, and a JSON repair or a longer audit would add more.

## 3. Goals / non-goals

Goals
- G1. A router call picks 3–4 functional roles that fit the question and writes
  each seat's brief, without demographic or "coastal enterprise" defaults and
  without favouring an option.
- G2. Every seat answers in one validated JSON shape, and a seat that returns
  something unparseable never breaks the session.
- G3. Perplexity checks each distinct falsifiable claim on its own and returns
  a status, a source and a source tier per claim.
- G4. The synthesis keeps every seat's position where they clash, and no claim
  the audit could not verify is presented as fact.
- G5. `audit_metrics` is attached next to `privacy_audit`, computed in code.
- G6. Everything Phase 1 guarantees still holds (AC4).

Non-goals
- Interactive Chair review, pause and resume (Phase 3).
- A new UI. Seats and audit are rendered to readable text on the server, so
  the frontend and its build do not change.
- Scoring seats numerically. The prompts forbid made-up numbers and scores.

## 4. Design

### 4.1 Panel router (`router.py`, `call_panel_router`)

One Claude Sonnet call (fast tier, `max_tokens=1200`) runs after the review
gate and before the fan-out. Input is the tokenized brief; output is:

```json
{
  "domain_detected": "string",
  "decision_stakes": "low | medium | high",
  "panel_seats": [
    {"assigned_model": "chatgpt | gemini | grok | claude_research",
     "functional_title": "string", "mandate": "string",
     "blind_spot_guardrail": "string"}
  ]
}
```

`PANEL_ROUTER_SYSTEM` (router.py, like every prompt) tells it to: choose
functions from the decision itself (product launch → Product, Marketing,
Finance, Legal & Compliance; cloud migration → Infra Architect, FinOps,
Security & Compliance, Developer Experience); frame the question without
assuming a favoured option; drop demographic, educational and
coastal-enterprise assumptions the user did not state; keep every
`[TYPE_n]` placeholder verbatim; and return JSON only.

Validation (`parse_panel_plan`): known `assigned_model`, no model twice, 3 or 4
seats, non-empty strings, stakes in the allowed set. **A model with no valid
seat, or any failure of the router call or its JSON, uses a default seat**:
its existing cognitive prompt with a generic functional title (Analyst,
Pragmatist, Scout, Challenger). The session never waits on or fails because of
the router. A failure prints one `[PANEL]` log line.

### 4.2 Structured seats

`build_seat_system(model, seat)` composes, in this order: the shared XML
template (role from `functional_title` and `mandate`, the blind-spot check
from `blind_spot_guardrail`, the no-false-precision rule, the token
preservation rule, the JSON output rules), then the model's existing
cognitive stance from `ROUND1_SYSTEM_PROMPTS` (see Q1), then the existing
guardrail blocks. Seats answer in:

```json
{"model": "...", "functional_title": "...", "core_assessment": "...",
 "cross_functional_conflicts": ["..."], "blind_spots_flagged": ["..."],
 "falsifiable_claims": ["..."]}
```

`parse_seat_response(text, model, seat)`: strips code fences, parses JSON,
fills missing keys with empty values, coerces list fields, and caps
`falsifiable_claims` at 6 per seat. **If the text is not valid JSON, one cheap
repair call (Sonnet) is tried; if that also fails, the whole text becomes
`core_assessment` with empty lists** and the seat is marked `degraded` (shown
in the health log). Smart-tier advisor passes keep working: the advisor
prompt already says "output only the final response", and its output goes
through the same parser, falling back to the executor's output if the
advisor's JSON is unusable.

`render_seat(seat_result)` turns the JSON into readable markdown (title,
assessment, conflicts, blind spots, claims). That string is what is streamed
as `token` frames and handed to the synthesizer inside `wrap_model_response`.
**The frontend still receives one string per seat.**

### 4.3 Atomic claim auditor (`perplexity_client.py`)

1. `collect_claims(seat_results)` flattens `falsifiable_claims`, normalizes
   (case, whitespace, punctuation), and merges near-duplicates (exact match or
   `difflib` ratio ≥ 0.85), recording `origin_models` for each. Cap: 16 claims,
   ordered by how many seats made them.
2. One audit call per tier chain (Sonar Pro → Sonar → GPT-5.4 web search)
   sends the claim list as numbered data and asks for strict JSON:

```json
{"audited_claims": [{"claim": "...", "origin_models": ["chatgpt"],
  "status": "VERIFIED | DISPUTED | UNVERIFIED", "source_title": "...|null",
  "source_url": "...|null", "source_tier": "primary | secondary | none",
  "notes": "..."}]}
```

3. `normalize_audit(raw, claims, citations)` enforces the rules in code, not
   by trusting the model:
   - Every collected claim appears exactly once; missing ones become
     `UNVERIFIED`.
   - `VERIFIED` with no `source_url` is downgraded to `UNVERIFIED`.
   - `source_tier` is computed from the URL's domain (`primary`: `.gov`,
     `.edu`, `.mil`, `.int`, official regulator and standards-body domains and
     a vendor's own documentation domain; `secondary`: anything else;
     `none`: no URL). Perplexity's label is advisory only.
4. If the whole chain fails (the emergency step), every claim is `UNVERIFIED`
   with a note saying the fact-check was unavailable. That is the honest
   result, and the existing degraded-pipeline note still appears.
5. The existing prose pre-research (`perplexity_pre`) is kept for context: it
   goes to synthesis as a second `<untrusted_search_evidence
   source="perplexity_research">` block, since the claim audit only checks what
   the panel said and would otherwise drop what the panel missed.

The serialized audit is wrapped by `wrap_untrusted_evidence` exactly as in
Phase 1. Citation numbering for inline `[n]` markers is unchanged.

### 4.4 Dissent-preserving synthesis

The prompt keeps all the Phase 1 safeguards and changes the output format
(see Q2 for which sections stay):

1. **Executive Consensus** — conclusions supported by `VERIFIED` claims.
2. **Cross-Functional Trade-Offs & Council Dissent** — where seats' mandates
   clashed, who said what, whether the audit settled it. Never averaged.
3. **Bias, Proxy & Blind-Spot Audit** — the union of `blind_spots_flagged`, plus
   any framing assumption the router removed.
4. **Source & Claim Verification Ledger.**

The ledger is **built in code** (`render_claim_ledger`) from the normalized
audit and appended to the synthesis text, because a prompt cannot guarantee
that an unverified claim is flagged (Q3). The model is told the ledger will be
appended, must not reproduce it, and must treat every `UNVERIFIED` or
`DISPUTED` claim as unestablished everywhere else in its text. The refinement
prompt gets the same rules, and the ledger is re-appended after every
revision, so a user push-back cannot drop it.

### 4.5 `audit_metrics`

Computed in `main.py` from the plan and the normalized audit, attached to
`synthesis_draft` and `synthesis_final` beside `privacy_audit`:

```json
{"claims_verified": 5, "claims_unverified_or_disputed": 2,
 "panel_roles_assigned": ["VP of Product", "..."]}
```

`pii_tokens_redacted` stays in `privacy_audit` (Phase 1), so the two objects
carry the combined shape in the brief without moving existing fields.
`panel_roles_assigned` strings pass through the Phase 1 re-hydration like every
other frame.

### 4.6 Privacy and injection boundaries (unchanged guarantees)

- The router, seats, claim list, audit prompt and ledger only ever see
  placeholders. Re-hydration still happens only at the socket edge.
- Seat output is model text, still wrapped with `wrap_model_response` before
  synthesis. Claims are passed to Perplexity as numbered data inside delimiters.
- A claim about a private entity (`[ORG_1] pays …`) can't be found on the web,
  so it comes back `UNVERIFIED`, which is the correct label.

## 5. Acceptance criteria

- **AC1 Panel routing.** The router is mocked with a model that follows the
  prompt: a product-launch brief yields Product / Marketing / Finance / Legal
  seats; a cloud-infrastructure brief yields Infra / Security / FinOps seats;
  all `[TYPE_n]` placeholders in the brief survive into every seat's system
  prompt. A bad router reply (invalid JSON, duplicate model, 2 seats) falls
  back to the default seats and the session completes. A **live** test sends
  both briefs to the real router and checks the same role families.
- **AC2 Atomic audit and unverified flag.** A seat invents "73% of SaaS buyers
  switch within 6 months"; Perplexity is mocked to return `UNVERIFIED`. The
  claim appears in the audit with `origin_models`, the audit carries
  `<untrusted_search_evidence>` with closing tags escaped, and **the synthesis
  output contains the claim marked unverified in the ledger** (code-built) and
  `audit_metrics.claims_unverified_or_disputed == 1`. A `VERIFIED` result with
  no URL is downgraded. A **live** test checks the model's prose does not state
  the claim as fact.
- **AC3 Dissent preserved.** ChatGPT's seat says launch now; Grok's flags
  negative unit economics. Both positions are present in the council material
  given to synthesis, and the synthesis prompt requires the dissent section.
  A **live** test checks both positions appear in the section.
- **AC4 Phase 1 compatibility.** `tests/test_privacy_pipeline.py` is extended
  with JSON-speaking fakes: zero leakage to all five providers, sandboxing
  intact, original values restored in every frame including the ledger and
  `audit_metrics`; the existing 488 tests still pass.
- **AC5 Seat parsing.** Fenced JSON, missing keys, a list where a string is
  expected, prose instead of JSON (repair succeeds / repair fails), over-long
  claim lists.
- **AC6 Claim collection.** Exact and near-duplicate merging keeps all
  `origin_models`; cap and ordering; empty input produces an empty audit
  without a model call.
- **AC7 Source tiers.** A table of URLs → tier (`.gov`, `.edu`, vendor docs,
  blog, missing).
- **AC8 Latency.** The router call is logged as `[TIMING] panel_router`; target
  ≤ 8s and the first-draft total stays within LATENCY_SPEC's budget (checked in
  the live session, not in unit tests).
- **AC9** The full suite passes with `uv run pytest`.

## 6. Tasks

1. `router.py`: `PANEL_ROUTER_SYSTEM`, `call_panel_router`, `parse_panel_plan`,
   default seats, `build_seat_system`, seat JSON rules.
2. `router.py`: `parse_seat_response`, `render_seat`, repair call.
3. `main.py`: router call before fan-out, per-seat prompts, parse and render,
   health fields (`panel_degraded`).
4. `perplexity_client.py`: claim collection, claim-audit prompt and JSON,
   `normalize_audit`, source tiers, fallback chain with the new shape.
5. `router.py`: synthesis and refinement prompt changes, `render_claim_ledger`,
   pre-research as a second evidence block.
6. `main.py`: ledger append for draft and refinement, `audit_metrics` on frames.
7. Tests for AC1–AC9; live tests in a new `tests/test_live_panel.py`.
8. Update CLAUDE.md (pipeline, prompt architecture, key files) and
   LandingPage text if Q1 changes any role; record Implementation Notes here.

## 7. Decisions (approved 2026-11-28 — all proposed answers accepted)

- **Q1. What happens to the fixed cognitive roles?** CLAUDE.md says the
  Analyst / Pragmatist / Scout / Challenger descriptions must stay aligned with
  the landing page. *Proposed:* **layer, don't replace.** The router's
  functional title and mandate sit on top of each model's existing stance, so a
  seat reads "Finance Lead, arguing as the Challenger". That keeps independence
  between models, keeps the landing page true, and means the default seats
  (router failure) are the old behaviour. The alternative is to drop the
  stances; the landing page and CLAUDE.md would then change too.
- **Q2. Which synthesis sections?** CLAUDE.md requires THE VERDICT, THE HINGE,
  WHERE THE PANEL DISAGREED, ONE NEXT ACTION, and you chose "a clear
  recommendation" in intake, which depends on a verdict and a next action.
  *Proposed:* keep **THE VERDICT**, **THE HINGE** and **ONE NEXT ACTION**, and
  split the rest into the three Phase 2 sections, in this order: THE VERDICT,
  THE HINGE, COUNCIL DISSENT & CROSS-FUNCTIONAL TRADE-OFFS (replaces WHERE THE
  PANEL DISAGREED), BIAS, PROXY & BLIND-SPOT AUDIT, ONE NEXT ACTION, then the
  code-built SOURCE & CLAIM VERIFICATION LEDGER. "Executive Consensus" becomes
  the verdict's evidence, not a section of its own. I'll check that the
  frontend does not parse section headers before building (the synthesis panel
  has a test file).
- **Q3. Build the ledger in code?** *Proposed:* yes (§4.4). A prompt-only
  version could be tested only with mocks that echo the prompt, which proves
  nothing about unverified claims being flagged.
- **Q4. One PR or two?** CLAUDE.md allows no stacked PRs. *Proposed:* **two
  sequential PRs, each branched from `main`:** (a) router + structured seats +
  rendering (tasks 1–3); (b) claim audit + synthesis + metrics (tasks 4–6).
  Phase 2 touches every research seat, the fact-check and the synthesis; a
  smaller diff is easier to review and to revert. The catch: (a) runs live with
  the old prose audit until (b) lands, which is harmless.
- **Q5. How should seats be forced into JSON?** *Proposed:* prompt-enforced
  JSON plus the tolerant parser and one repair call, not each provider's native
  JSON mode. The four providers' modes differ and some conflict with
  reasoning models; one parser works for all.
- **Q6. Per-claim calls or one call?** *Proposed:* one call carrying all claims
  (≤ 16), with the code guaranteeing every claim gets exactly one entry. One
  call per claim would add 16 searches to a stage that takes about 8s today.
- **Q7. Deduplication method.** *Proposed:* normalization plus `difflib`
  similarity, not an LLM. A claim worded very differently by two seats may be
  audited twice, which is harmless.

## 8. Implementation Notes

### PR a — router, structured seats, rendering (built 2026-11-28, `feat/dynamic-panel-router`)

- **Seat prompt order.** `build_seat_system` is: seat template, then the
  model's stance and guardrails (`get_round1_system_prompt`), then the JSON
  rules last. The spec listed the JSON rules before the stance; they go last
  so "lead with your strongest claim" and "never start with your own name"
  cannot override the output format.
- **Advisor fallback dropped.** The spec said a bad advisor reply would fall
  back to the executor's JSON. `call_research_*_async` returns only the
  advisor text, so that needs a change in all four clients. A seat whose
  reply is not valid JSON gets the one repair call, then plain text. Revisit
  if repairs turn out to be frequent in the logs.
- **Repair skipped for unavailable seats** (their text is a notice, not an
  answer), and the repair keeps placeholders verbatim.
- **`seat_results` and `panel_plan`** are kept in `session_websocket` for PR b
  (claim collection). Nothing reads them yet.
- **Health.** `PipelineHealth` gained `panel_fallback` and
  `panel_degraded_seats`; they appear in `synthesis_annotations`.
- **Seat names are not model IDs.** The `chatgpt` seat name tripped
  `tests/test_model_registry.py` AC1 (a hardcoded-model-ID scan), so the
  mapping in `router.py` is built from lab keys.
- **Offline test fixture.** Every session now calls Claude twice-plus (router,
  seat repairs), so `conftest.py` makes the Anthropic client fail fast in
  tests (live evals excepted); the router and repair then degrade as designed.
  `FakeClaude` in `test_latency_synthesis_stream.py` records those calls
  separately, and `test_privacy_pipeline.py` gained a responder hook and
  checks conversation text only for placeholders (system prompts contain
  example placeholders).
- **Live results (2026-11-28).** `tests/test_live_panel.py` passed 4/4. Real
  plans: launch brief → Launch Execution Lead, Market & Competitive Timing
  Analyst, Commercial & Budget Red-Team, Risk, Governance & Scope Counsel;
  cloud brief → Migration Architecture Lead, Market & Vendor Ecosystem
  Analyst, Financial & Commercial Red-Team Analyst, Governance, Compliance &
  Contract Advisor. The router picks equivalents of the example titles, not
  the examples verbatim, so the live checks test role families, not names. A
  real seat returned parseable JSON on the first try.
- **Mutation check.** With seat structuring disabled, the pipeline test fails
  (the panel starts with raw JSON).
- **Not yet measured:** the router's added latency in a real session
  (`[TIMING] panel_router`, target ≤ 8s). Check it in the first live session.
