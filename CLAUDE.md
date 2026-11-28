# ai-roundtable — Claude Code Project Instructions

## What this project is
A deliberation tool for high-stakes decisions. Not a query tool.
The architecture exists to get the answer right in one session.
Users submit a prompt, go through a structured intake, receive
research from multiple frontier models, see a fact-check audit,
then engage in a synthesis dialogue before finalizing the answer.

## Model philosophy
Cost is not a design constraint. Model choices are made for
quality ceiling, not cost floor.

| Stage | Model | Notes |
|---|---|---|
| Intake | Claude Sonnet (primary) | GPT-4o-mini fallback, Qwen fallback |
| Research | Sonnet executor + Opus advisor | Smart tier |
| Fact-check | Perplexity Sonar Pro | Always deep |
| Synthesis | Claude (SYNTHESIS_ANALYTICAL) | One streamed call on every tier (LATENCY_SPEC L1), Qwen fallback; GPT route removed (ADR 002 addendum) |
| Chips/Direction | Claude Sonnet | Fast tier |

## Pipeline flow
INTAKE (multi-turn, minimum questions enforced per domain)
→ RESEARCH (parallel: Claude + Gemini + GPT + Grok)
→ FACT-CHECK (Perplexity)
→ SYNTHESIS DRAFT (auto-triggers, no user gate)
→ DIALOGUE (user responds, Claude refines)
→ FINAL ANSWER (user clicks Finalize)

YOUR TAKE gate was removed. Synthesis auto-triggers after
fact-check. User engages with the draft, not a blank textarea.

## Intake architecture
- Multi-turn conversation with minimum questions enforced per domain
- Domain detection via keyword matching
- MINIMUM_QUESTIONS_REQUIRED: immigration=3, career=2, financial=2, general=1
- FALLBACK_QUESTIONS bank used when model closes early
- Model question used before fallback bank
- Assumptions summary presented before handoff to research
- Persona: Archetype 3 — Thoughtful Analyst (see system prompt)
- JSON output enforced with explicit format constraints
- max_tokens=2000 on all intake callers
- Chip UX: clicking a chip selects it (highlighted), does not submit;
  → button submits selected chip or free-form textarea text
- Open-ended questions (no chips) show a "Skip this question" link
  that submits "I'd prefer not to say" so user is never forced to type

## Key files
- backend/main.py — FastAPI app, WebSocket session handler
- backend/intake.py — IntakeSession, multi-turn logic, minimum enforcement
- backend/router.py — synthesis system prompt, refinement, closing questions
- backend/models/openai_client.py — _build_intake_system_prompt()
- backend/models/anthropic_client.py — Claude API client
- backend/models/model_registry.json — every model ID, its tier/rank/status, and
  the 24 pipeline roles (single source of truth; spec: docs/MODEL_REGISTRY_SPEC.md)
- backend/models/registry.py — resolves each role to a model at startup
- backend/models/model_config.py — resolved constants used by call sites
- backend/models/intake_decision.py — IntakeDecision Pydantic schema
- frontend/src/components/LandingPage.jsx — landing page; panel member descriptions
  must stay aligned with cognitive roles in ROUND1_SYSTEM_PROMPTS (router.py)
- frontend/src/components/IntakeFlow.jsx — intake UI, multi-turn handling
- frontend/src/components/SessionView.jsx — session UI, dialogue loop
- frontend/src/components/SynthesisPanel.jsx — DRAFT/REVISED/FINAL badges

## Prompt architecture

All prompt strings live in backend/router.py.
Never inline prompts in main.py or any client module.
Never redefine wrap_model_response() outside router.py.

### Layer 1 — Optimized Brief
Location: backend/models/openai_client.py → _build_intake_system_prompt()
Purpose: Converts intake session config into a structured
research brief for the four-model panel.
Template variables: {problem}, {output_intent},
{user_context}, {timeline}, {stakes}

### Layer 2 — Per-Model System Prompts
Variable: ROUND1_SYSTEM_PROMPTS in backend/router.py
Keys: "claude", "gpt", "gemini", "grok"

Cognitive roles:
- claude  → ANALYST (first principles reasoning)
- gpt     → PRAGMATIST (practical, concrete, actionable)
- gemini  → SCOUT (finds angles and options others miss)
- grok    → CHALLENGER (stress-tests the premise itself)

All four model responses must be wrapped with
wrap_model_response() before synthesis injection.
Do not apply wrapper to Perplexity output.

### Layer 3 — Synthesis
Variables: SELF_CRITIQUE_SYSTEM, SYNTHESIS_SYSTEM_PROMPT
Location: backend/router.py

Pipeline order (two separate API calls):
  Step 1: Self-critique (intermediate Claude call)
  Step 2: Synthesis (final Claude call)

Synthesis output format — four required sections:
  THE VERDICT
  THE HINGE
  WHERE THE PANEL DISAGREED
  ONE NEXT ACTION

### Prompt rules
- Never rename prompt variables without updating all call sites
- Template variables use {curly_brace} syntax
- wrap_model_response() defined in router.py only
- Never hardcode model IDs — they live only in model_registry.json; code uses
  model_config.py constants (tests/test_model_registry.py AC1 enforces this)

## Spec-driven development process
- **Non-trivial changes** (new features, architectural changes, multi-file refactors, or synthesis/intake logic updates):
  1. Draft or update the specification in `docs/` first.
  2. Pause for explicit user approval of the spec before writing tests or implementation code.
  3. Write failing tests first, then implement code until the suite passes.
- **Trivial changes** (typos, single-line bug fixes, documentation tweaks): Proceed directly to implementation and tests without a formal spec.

## Git & PR workflow
- **Default division of labor:**
  - **Terminal (User):** Branch creation and `git push`.
  - **Claude Code:** File changes, local validation gates, local commits, and opening PRs via `gh pr create` **only after explicit user OK**.
  - **GitHub (User):** PR review and merge.
- **Explicit override exception:** Do **not** run `git push` or `gh pr merge` unless explicitly instructed by the user in the current turn. Even when explicitly instructed to merge, **wait for all GitHub CI checks to pass first**, and use standard merge commits (never squash/rebase unless requested). Never treat a one-off instruction as standing permission for future turns.
- **Branch & worktree hygiene:**
  - Use Git worktrees branched cleanly from `main` for isolated feature/fix work (except when debugging live backend issues—see *What not to do*).
  - Avoid stacked PRs; keep each branch and PR scoped to a single logical unit of work branched from `main`.
  - Always specify branch name explicitly — never use `claude/` prefix.

## Branch naming
feat/description — new features
fix/description — bug fixes
docs/description — documentation only

## Testing
uv run pytest — always run before committing (never bare pytest)
RUN_LIVE_EVALS=1 uv run pytest tests/test_live_synthesis_post_cutoff.py —
  paid live check; run when changing synthesis models or prompts
CI (.github/workflows/tests.yml) runs on every PR and push to main: clean
  pinned install, lockfile-in-sync check, full suite. No secrets needed
tests/test_ws_close_paths.py runs the app on a real uvicorn server and fails
  on any server traceback when a WebSocket session ends (six close paths)
381 passed, 2 skipped as of November 2026

## Environment
- Python 3.13 (pinned via .python-version)
- uv for package management
- Local setup (makes .venv match the lockfiles exactly, removes extras):
    uv pip sync backend/requirements.txt backend/requirements-dev.txt

## Dependencies
Spec: docs/DEPENDENCY_PINNING_SPEC.md
- backend/requirements.in — direct dependencies, lower bounds only (edit this)
- backend/requirements.txt — every package ==pinned with hashes, generated
  (Railway installs this with pip install -r backend/requirements.txt)
- requirements.txt at the repo root — comments only, never delete: Railpack
  needs it to detect Python (without it the deploy crash-loops on
  "uvicorn: command not found")
- backend/requirements-dev.in / requirements-dev.txt — pytest, httpx (for
  starlette's TestClient), constrained by requirements.txt
- Never hand-edit the .txt files. Regenerate both after any .in change:
    uv pip compile backend/requirements.in -o backend/requirements.txt --python-version 3.13 --generate-hashes
    uv pip compile backend/requirements-dev.in -c backend/requirements.txt -o backend/requirements-dev.txt --python-version 3.13 --generate-hashes
  CI fails if a lockfile is out of sync with its .in file
- Never import httpx in backend code — the SDKs no longer install it, so it
  exists only in the dev lock (tests/test_dependency_pinning.py enforces this)
- Upgrades are deliberate PRs (no Dependabot):
  1. Add --upgrade-package <name> (or --upgrade for all) to the compile
     command, then regenerate the dev lock
  2. CI must pass (clean install + tests + close paths)
  3. SDK or server-stack changes (anthropic, openai, google-genai, fastapi,
     starlette, uvicorn, websockets): run the paid live check above and one
     full live session before merging
  4. After deploy, check the [STARTUP] Python … version line in the Railway
     log shows the new versions
- backend/.env — all API keys (never commit)
- load_dotenv at top of all client modules before SDK imports
- override=True to handle empty shell variables

## Deployment
- Backend: Railway (ai-roundtable-bk-production.up.railway.app)
- Frontend: Railway (ai-roundtable-frnt-production.up.railway.app)
- Port: 8080 (set in Railway networking settings)
- FRONTEND_URL env var set in Railway backend for CORS

## Frontend build
Railway serves frontend/build/ as a static site — it does NOT
rebuild from source on deploy. After any frontend JSX/CSS change,
run a local build and commit the artifacts on your feature/fix branch
before pushing and opening a PR:

  cd frontend && npm run build && cd ..
  git add frontend/build/
  git commit -m "chore: rebuild frontend for production"

Never push frontend code changes without a matching build commit.
The two must travel together in the same branch/PR or Railway will serve
stale UI.

## Known issues and notes
- Gemini 503s intermittently (upstream capacity on preview models)
- Grok API key confirmed loading correctly (PR #35)
- Startup prints a [STARTUP] line with Python and key package versions, then
  the role → model table; ⚠️ lines after it are real (retiring,
  missing or unresolved models). Fix them in model_registry.json
- Each session logs a [TIMING] line per stage (research.<model>, research,
  research.emit, factcheck, self_critique, synthesis, refinement.N, plus
  synthesis.first_token / refinement.N.first_token) and a
  [TIMING] first_draft total=… summary. Timing starts after prompt review,
  so user wait is excluded (backend/stage_timing.py)
- python -m tools.check_models reports against live provider lists;
  --write adds new provider models as candidates (never approved) and
  refreshes retirement dates. Approving a model = editing its status in a PR
- Per-role env vars (RESEARCH_GPT_DEEP, SYNTHESIS_ANALYTICAL, …) still override
  the registry — use them to pin production without a deploy
- MODEL_DISCOVERY=0 skips provider API calls at startup (tests set this)
- Provider clients must read model IDs from model_config.py — never add
  a local MODELS dict (tests/test_model_config.py enforces this)
- Intake max 7 questions not yet enforced (v2 spec in docs/)
- Synthesis and refinement stream to the client as synthesis_token frames,
  then a synthesis_draft with the cleaned text; synthesis_reset clears a
  stream that failed mid-way. Latency plan: docs/LATENCY_SPEC.md
- Intake returns stated_facts (the user's own facts, one per line). The review
  screen lets the user edit them; the confirmed list is appended to the brief
  for all research models (falls back to the verbatim original prompt).
  Spec: docs/INTAKE_BRIEF_FIDELITY_SPEC.md
- Intake v2 architecture spec: docs/INTAKE_V2_SPEC.md
- Intake v2 PM addendum: docs/INTAKE_V2_PM_ADDENDUM.md

## What not to do
- Never use claude/ prefixed branch names
- Never create stacked PRs
- Never merge PRs without review and passing CI
- Never push or merge without explicit user instruction in the current turn
- Never hardcode model IDs — add them to model_registry.json
- Never commit backend/.env
- Never use worktree mode when debugging live backend issues
- Never run bare pytest — always use uv run pytest
