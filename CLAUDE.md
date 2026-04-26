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
| Synthesis | Claude Opus | Analytical routing |
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

## Key files
- backend/main.py — FastAPI app, WebSocket session handler
- backend/intake.py — IntakeSession, multi-turn logic, minimum enforcement
- backend/router.py — synthesis system prompt, refinement, closing questions
- backend/models/openai_client.py — _build_intake_system_prompt()
- backend/models/anthropic_client.py — Claude API client
- backend/models/model_config.py — all model IDs (single source of truth)
- backend/models/intake_decision.py — IntakeDecision Pydantic schema
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
- Never hardcode model IDs — always use model_config.py constants

## Git workflow
- Terminal: branch creation and pushing
- Claude Code: file changes and commits
- GitHub: PR review and merge
- Always specify branch name explicitly — never use claude/ prefix

## Branch naming
feat/description — new features
fix/description — bug fixes
docs/description — documentation only

## Testing
uv run pytest — always run before committing
250 tests passing as of April 2026

## Environment
- Python 3.13 (pinned via .python-version)
- uv for package management
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
run a local build and commit the artifacts before pushing to main:

  cd frontend
  npm run build
  cd ..
  git add frontend/build/
  git commit -m "chore: rebuild frontend for production"
  git push origin main

Never push frontend code changes without a matching build commit.
The two must travel together in the same push or Railway will serve
stale UI.

## Known issues and notes
- Gemini 503s intermittently (upstream capacity on preview models)
- Grok API key confirmed loading correctly (PR #35)
- Grok stale model ID warnings on startup are cosmetic —
  model aliases resolve correctly at runtime
- Intake max 7 questions not yet enforced (v2 spec in docs/)
- Intake v2 architecture spec: docs/INTAKE_V2_SPEC.md
- Intake v2 PM addendum: docs/INTAKE_V2_PM_ADDENDUM.md

## What not to do
- Never use claude/ prefixed branch names
- Never merge PRs without review
- Never hardcode model IDs — always use model_config.py constants
- Never commit backend/.env
- Never use worktree mode when debugging live backend issues
- Never run bare pytest — always use uv run pytest
