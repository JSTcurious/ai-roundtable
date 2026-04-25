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
243 tests passing as of April 2026

## Environment
- Python 3.13 (pinned via .python-version)
- uv for package management
- backend/.env — all API keys (never commit)
- load_dotenv at top of all client modules before SDK imports
- override=True to handle empty shell variables

## Deployment
- Backend: Railway (ai-roundtable-production-5555.up.railway.app)
- Frontend: Railway (genuine-clarity-production-6840.up.railway.app)
- Port: 8080 (set in Railway networking settings)
- FRONTEND_URL env var set in Railway backend for CORS

## Known issues and notes
- Gemini 503s intermittently (upstream capacity on preview models)
- Grok API key not configured (xAI Bearer warning on startup is harmless)
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
