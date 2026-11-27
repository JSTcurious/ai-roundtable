# Model Registry — Role-Based Model Selection
## ai-roundtable · JSTcurious · November 2026

**Status:** Approved 2026-11-27 (see Decisions); implemented on `feat/model-registry`.
**Scope:** Steps 1–3 (roles, registry + resolver, discovery). Eval-gated
promotion (step 4) is a follow-on that depends on the V3 eval harness.

---

## Problem Statement

Every model the pipeline calls is a string default in
`backend/models/model_config.py` — 24 roles, each overridable by an env var.
Nothing keeps those strings current, and nothing warns before they break:

- **Retired IDs break production silently.** `grok-4.1-fast-*` returned 404
  and the code shipped with them (fixed in #44). The startup validator only
  logs a warning that nobody sees.
- **Scheduled shutdowns go unnoticed.** OpenAI's model API reports
  `shutdown_date=2027-01-14` for `gpt-4o-mini`, which is `INTAKE_FALLBACK1`
  today. Nothing in the repo surfaces that date.
- **The panel falls behind.** Anthropic lists `claude-opus-5-5` and
  `claude-sonnet-5-5` as active; the pipeline still runs `claude-*-4-6`.
  OpenAI lists a `gpt-6-*` family. Noticing requires a person to go look.
- **The safety net is broken.** `.github/workflows/model-currency-check.yml`
  has failed every scheduled run since at least June 2026 (`uv sync` with no
  `pyproject.toml`; it passes `XAI_API_KEY` while the code reads
  `GROK_API_KEY`), and its failure step never opened an issue.
- **Changing a model is a code or env edit per role**, with no record of why
  a model was chosen or when it was last reviewed.

## Goals

1. Roles declare **requirements** (vendor, tier, capabilities), not model IDs.
2. Known models live in a **registry file** (data, reviewed via PR).
3. A **resolver** picks the model for every role at startup.
4. **Discovery** reads provider model APIs for availability and retirement
   dates, and reports new models, retiring models, and missing models.
5. The weekly CI check works again and alerts before an in-use model retires.

## Non-Goals

- **Automatic adoption of new models.** Discovered models enter the registry
  as `candidate` and are never selected until a person approves them. Making
  that promotion eval-gated is step 4, after the eval harness exists.
- **Per-request model routing** (an LLM or classifier choosing a model per
  prompt). Rejected for now: the keyword synthesis router removed in #47
  misrouted nearly every session; a classifier adds cost, latency and a new
  failure mode.
- **Cross-vendor auto-routing** (e.g. OpenRouter `auto`). The panel's value is
  one independent model per vendor; selection happens *within* each seat.
- **Re-enabling the intake smart/deep tier** — separate change.
- **Upgrading the panel to newer generations** — this spec makes that a
  one-line registry change; choosing to do it is a separate decision (see
  Open Questions).

## Design Principles

1. **Roles, not IDs.** Code asks for `research.gpt.executor`, never `gpt-5.4-mini`.
2. **Discover automatically, adopt deliberately.** Discovery can add
   candidates and update retirement dates. Only a human (later: evals) can
   approve a model.
3. **Pinned per deploy.** Resolution runs once at startup. Every session in a
   process uses the same models, and the startup log records which.
4. **Retirement is handled automatically, safely.** A model inside its
   retirement window is skipped in favour of the next *approved* model — a
   move between already-reviewed models, never to an unreviewed one.
5. **Fail safe, never fail closed.** If provider APIs are unreachable, resolve
   from registry data alone. Startup never blocks on discovery.
6. **Env overrides remain the escape hatch.** An explicit per-role env var
   wins over the resolver, so production can be pinned without a deploy.

---

## Provider Discovery Capabilities (observed 2026-11-27)

| Provider | List endpoint | Retirement data | Other useful fields |
|---|---|---|---|
| Anthropic | `models.list` | `lifecycle`, `deprecated_at`, `retires_at` | `line` (opus/sonnet/haiku), `capabilities`, `max_input_tokens` |
| OpenAI | `models.list` | `shutdown_date` | `created` only — no tier |
| xAI | `/v1/models` | — | `aliases` (incl. `-latest`), pricing, `context_length` |
| Google | `models.list` | — | `-latest` aliases, token limits, `thinking` |
| OpenRouter | `/api/v1/models` | `expiration_date` | pricing, `context_length`, `knowledge_cutoff` |
| Perplexity | none (404) | — | registry is curated by hand |

Provider APIs do not expose quality tier, and some names are opaque
(`gpt-6-astra`, `-luna`, `-sol`, `-terra`), so **tier and preference rank stay
curated in the registry**. Discovery supplies availability and dates only.

---

## Architecture

```
model_registry.json ──┐
  models + roles      │
                      ▼
provider APIs ──► discovery ──► resolver ──► resolved map ──► model_config constants
 (startup, best      (availability,   (per role,      (role → model_id,   (existing names,
  effort, timeout)    retirement)      once)           logged)             call sites unchanged)
                                                   ▲
                                         env overrides (per role)
```

### Registry file — `backend/models/model_registry.json`

```json
{
  "retirement_buffer_days": 30,
  "warning_window_days": 90,
  "models": [
    {
      "id": "claude-opus-4-6",
      "vendor": "anthropic",
      "tier": "frontier",
      "rank": 40,
      "status": "approved",
      "capabilities": ["tools", "reasoning"],
      "retires_at": null,
      "notes": "Synthesis primary since ADR 002 addendum"
    }
  ],
  "roles": {
    "research.claude.executor": {"vendor": "anthropic", "tiers": ["balanced"]},
    "research.claude.advisor":  {"vendor": "anthropic", "tiers": ["frontier"]},
    "research.claude.fallback": {"vendor": "anthropic", "tiers": ["fast", "balanced"],
                                 "distinct_from": ["research.claude.executor"]}
  }
}
```

- `vendor`: `anthropic | openai | google | xai | perplexity | openrouter`.
- `tier`: `fast | balanced | frontier`.
- `rank`: integer preference within vendor + tier; higher wins. Explicit
  because "newest" cannot be inferred from opaque names.
- `status`: `approved` (selectable) · `candidate` (discovered, never
  selected) · `disabled` (kept for history, never selected).
- `retires_at`: ISO date; written by discovery where the provider reports it,
  curated otherwise.
- Role fields: `vendor`, `tiers` (allowed, in preference order),
  `capabilities` (required, optional), `distinct_from` (roles whose resolved
  model must not be reused — guarantees a fallback differs from its primary).

### Roles (24, matching today's `model_config.py`)

| Role | Vendor | Tiers | Env override (unchanged name) |
|---|---|---|---|
| `research.{claude,gpt,gemini,grok}.executor` | lab's vendor | balanced | `RESEARCH_<LAB>_SMART_EXECUTOR` |
| `research.{lab}.advisor` | lab's vendor | frontier | `RESEARCH_<LAB>_SMART_ADVISOR` |
| `research.{lab}.deep` | lab's vendor | frontier | `RESEARCH_<LAB>_DEEP` |
| `research.{lab}.fallback` | lab's vendor | fast, balanced; distinct from executor (except GPT, see Open Question 5) | `RESEARCH_<LAB>_FALLBACK` |
| `factcheck.primary` | perplexity | frontier | `FACTCHECK_PRIMARY` |
| `factcheck.fallback1` | perplexity | balanced; distinct from primary | `FACTCHECK_FALLBACK1` |
| `factcheck.fallback2` | openai | frontier | `FACTCHECK_FALLBACK2` |
| `synthesis.primary` | anthropic | frontier | `SYNTHESIS_ANALYTICAL` |
| `synthesis.fallback` | openrouter | balanced | `SYNTHESIS_FALLBACK` |
| `intake.primary` | anthropic | balanced | `INTAKE_PRIMARY` |
| `intake.fallback1` | openai | fast | `INTAKE_FALLBACK1` |
| `intake.fallback2` | openrouter | balanced | `INTAKE_FALLBACK2` |

### Resolver — `backend/models/registry.py`

`resolve(registry, availability, overrides, today) -> Resolution`

For each role:

1. **Override.** If the role's env var is set, use it. If discovery says the
   ID is unavailable or retiring, log a warning but still use it.
2. **Eligible set.** Registry models where vendor matches, tier is in the
   role's `tiers`, `status == "approved"`, required capabilities are present,
   the model is not excluded by `distinct_from`, and (when discovery data
   exists for that vendor) the provider lists it.
3. **Retirement.** Drop models whose `retires_at` is within
   `retirement_buffer_days` of today. If that empties the set, fall back to
   the dropped-but-still-live models and log an error.
4. **Pick.** Earliest tier in the role's `tiers` list, then highest `rank`.
5. **Unresolvable.** If nothing remains, the role is unresolved: log an error,
   and callers treat that seat or stage as unavailable (the existing
   `"unavailable"` path) instead of crashing.

Roles are resolved in dependency order so `distinct_from` sees its targets.

`model_config.py` keeps its public names (`RESEARCH_GPT_SMART_EXECUTOR`,
`get_executor_model()`, `SYNTHESIS_ANALYTICAL`, …), now populated from the
resolution, so no call site changes.

### Discovery — `backend/models/discovery.py`

- Extends the listing functions in `model_validator.py` to return metadata,
  not just ID sets: availability, `retires_at` (Anthropic `retires_at`,
  OpenAI `shutdown_date`, OpenRouter `expiration_date`), and aliases.
- **At startup:** best effort, per-provider timeout (5 s), results held in
  memory and passed to the resolver. Never written to disk in production.
- **CLI** (`python -m tools.check_models`, replacing today's `--fix`):
  - `--report` (default): new provider models not in the registry; approved
    models retiring within `warning_window_days`; approved models the
    provider no longer lists; the resolved role table. Exit code 1 if any
    *resolved* model retires within `retirement_buffer_days` or is missing.
  - `--write`: add unknown provider models as `status: "candidate"` (tier and
    rank left for a person to fill in) and update `retires_at`. Never changes
    the `status` of existing entries.
- **CI:** fix `model-currency-check.yml` (`pip install -r requirements.txt`
  instead of `uv sync`; pass the key name the code reads; give the job
  `issues: write`) and run `--report` weekly; on failure, open or update one
  issue instead of one per week.

### Observability

- Startup log: one table of role → model, with source (`registry` /
  `override`) and any retirement warnings.
- `/api/model-info` reports the resolved map (it already reads
  `model_config`, so this is automatic).
- `[SESSION]` start line includes a short hash of the resolved map, so any
  export can be tied to the exact models that produced it.

---

## Acceptance Criteria

Each criterion maps to at least one automated test unless marked *(manual)*.

| ID | Criterion |
|---|---|
| AC1 | No backend Python file outside `model_registry.json` contains a hardcoded model ID default. (Test scans `backend/` for provider ID patterns.) |
| AC2 | Every one of the 24 roles resolves to an `approved` model matching its vendor, tiers and required capabilities. |
| AC3 | A role's env override wins over the registry; an override discovery reports as unavailable or retiring logs a warning and is still used. |
| AC4 | A model whose `retires_at` is within `retirement_buffer_days` is skipped for the next eligible approved model; models within `warning_window_days` log a warning. |
| AC5 | A role never resolves to the same model as any role in its `distinct_from`. |
| AC6 | `candidate` and `disabled` models are never selected. |
| AC7 | With every provider API unreachable, startup completes and resolves from registry data alone. |
| AC8 | A role with no eligible model leaves startup running, logs an error, and its seat/stage reports `unavailable` instead of raising. |
| AC9 | Resolution runs once per process; repeated calls return the same map; startup logs the full table. |
| AC10 | **Parity:** with the seed registry and no discovery data, the resolved map equals today's `model_config.py` defaults for 23 of 24 roles; `intake.fallback1` is `gpt-5.4-mini` (Decision 2). |
| AC11 | **Retirement via discovery:** when discovery reports a retirement date inside the buffer for an in-use approved model, that role moves to the next eligible approved model; with live discovery today, the resolved map equals AC10. |
| AC12 | `--report` lists new provider models, approved models retiring within the warning window, and approved models missing from the provider; it exits 1 when a resolved model retires within the buffer or is missing. |
| AC13 | `--write` adds unknown models as `candidate` and updates `retires_at`, and never changes the status of an existing entry. |
| AC14 | The weekly workflow installs dependencies, reaches every provider, and opens or updates a single issue on failure. *(manual: one `workflow_dispatch` run)* |
| AC15 | No behaviour change in the pipeline beyond AC11: `uv run pytest` passes, and one local session runs end to end. *(manual for the session)* |

---

## Seed Registry

- Every model ID in today's `model_config.py`, `status: "approved"`, with
  tiers and ranks that reproduce today's choices (AC10).
- `gpt-4o-mini` as `disabled` (shutdown 2027-01-14), so `intake.fallback1`
  resolves to `gpt-5.4-mini` immediately rather than 30 days before shutdown
  (Decision 2).
- Newer models visible in provider APIs (e.g. `claude-opus-5-5`,
  `claude-sonnet-5-5`, `gpt-6-*`, `grok-4.5+`, Gemini `-latest` aliases) as
  `status: "candidate"` — recorded, not used.

## Files

| File | Change |
|---|---|
| `backend/models/model_registry.json` | New — models, roles, windows |
| `backend/models/registry.py` | New — load, validate, resolve |
| `backend/models/discovery.py` | New — provider metadata (from `model_validator.py`) |
| `backend/models/model_config.py` | Constants populated from the resolution; env overrides kept |
| `backend/models/model_validator.py` | Thin wrapper over discovery (or removed) |
| `tools/check_models.py` | `--report` / `--write` |
| `.github/workflows/model-currency-check.yml` | Fixed install, keys, permissions, single issue |
| `tests/test_model_registry.py` | AC1–AC13 |
| `CLAUDE.md`, `backend/.env.example` | Document roles, overrides, CLI |

## Implementation Tasks

1. Registry schema, loader and validation (unknown vendor/tier, duplicate IDs,
   roles referencing missing tiers fail loudly in tests). — AC2, AC6
2. Seed registry reproducing today's defaults. — AC10
3. Resolver: overrides, eligibility, retirement window, `distinct_from`,
   unresolved roles. — AC3–AC5, AC8, AC9
4. Wire `model_config.py` to the resolution; remove hardcoded defaults. Change
   the intake OpenAI call from `max_tokens` to `max_completion_tokens`:
   `gpt-5.4-mini` rejects `max_tokens` with a 400 (verified live), which would
   break the intake fallback. — AC1, AC15
5. Discovery module with per-provider timeouts and metadata. — AC7, AC11
6. `tools/check_models` `--report` / `--write`. — AC12, AC13
7. CI workflow fix. — AC14
8. Startup log table, session hash, docs. — AC9

## Migration Plan

One feature PR on `feat/model-registry`, implemented task by task with tests
first. Rollout risk is limited by AC10: until the registry is edited, the
resolved models are identical to today's, except the `gpt-4o-mini`
replacement, which must happen before 2027-01-14 regardless.

## Estimated Effort

About 2.5 days: tasks 1–4 ≈ 1.5 days, tasks 5–6 ≈ 0.5 day, tasks 7–8 ≈ 0.5 day.

---

## Implementation Notes (deviations found while building)

- **Discovery uses the standard library for HTTP.** A clean install of
  `backend/requirements.txt` (unpinned, as Railway builds it) now pulls
  `openai` 3.x and `anthropic` 2.x, which no longer depend on `httpx`; an
  `import httpx` in discovery would have crashed app startup on the next
  Railway build.
- **Google models are listed from `v1beta`.** `google-genai` 3.x defaults to
  the `v1` API, where the Gemini seat's preview models return 404 — so a
  default listing reports them missing. Discovery lists what the client
  actually calls. The same default is the likely cause of "Gemini
  unavailable" on Railway; the client fix ships separately.
- **Already-retiring models are not added as candidates** (extends AC13):
  `claude-sonnet-4-5` and `claude-opus-4-5` were deprecated when first seen.
- **Per-vendor include/exclude filters** in the registry's `discovery` block
  keep audio, image, realtime, dated snapshots and OpenRouter variants out
  of the candidate list.
- **Seeded with `--write` against live APIs:** 64 candidates; resolution
  unchanged (fingerprint `06ae7817`).

## Decisions (2026-11-27)

All five proposals accepted:

1. Retirement buffer 30 days, warning window 90 days.
2. `intake.fallback1` successor is `gpt-5.4-mini`; `gpt-4o-mini` is seeded as
   `disabled` so the switch happens now, not 30 days before shutdown.
3. Newer generations stay `candidate` in this PR.
4. CI opens or updates a single GitHub issue.
5. The GPT research fallback keeps matching its executor for parity; a
   follow-up gives it a different model.

## Open Questions (resolved — kept for the record)

1. **Retirement buffer.** Skip a model 30 days before its retirement date, and
   warn 90 days before? (Proposed.)
2. **Successor for `intake.fallback1`.** `gpt-4o-mini` shuts down
   2027-01-14. Proposed: `gpt-5.4-mini`, already used as the GPT research
   executor and fallback. The alternative is a newer `gpt-6-*` fast model,
   which would need its own review first.
3. **Newer generations.** Leave `claude-*-5-5`, `gpt-6-*`, newer Grok and
   Gemini models as candidates in this PR (proposed), or approve some now?
   Approving changes panel behaviour, so it should come with a session
   comparison, like the earlier Railway before/after.
4. **CI alerting.** Open or update a single GitHub issue (proposed), or fail
   the workflow only?
5. **GPT research fallback.** Today `RESEARCH_GPT_FALLBACK` is the same model
   as the GPT executor (`gpt-5.4-mini`), so a GPT failure retries the model
   that just failed. This spec keeps that for parity (no `distinct_from` on
   the GPT fallback). Should a follow-up give it a different model?
