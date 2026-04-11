# Changelog

All notable changes to ai-roundtable are documented here.

---

## [v2.0.0] — in build

### The full product

**Intake**
- Use case library — 16 curated starting points across four families
- Claude conducts intake conversation — mirrors back, confirms, gathers context progressively
- Escape hatches — user can stop anytime, Claude flags open assumptions
- Optimized prompt shown to user for approval before any frontier model is invoked

**Four seats**
- Claude (Anthropic) — orchestrator, intake conductor, synthesizer
- Gemini (Google) — deep reasoner
- GPT (OpenAI) — generalist structurer
- Perplexity — fact-checker only, never opines, runs parallel to Round 1

**Three tiers**
- Quick — executor model only, fast and cheap
- Smart (default) — executor + advisor per lab via Anthropic advisor pattern, applied across all four providers
- Deep Thinking — advisor-level model throughout, user-activated

**Session flow**
- Sequential Round 1 — each model hears what came before
- Perplexity audit runs parallel to Round 1
- Claude synthesizes all responses + audit into structured final answer
- Deep mode: cross-critique round with specialized lenses per model

**Export + downstream**
- Markdown export — full session or synthesis only
- Google Drive integration
- Claude Code handoff — file + suggested command
- Perplexity handoff — context + suggested follow-up prompt
- "Take This Further" panel after every synthesis

**Tech stack**
- React + Tailwind frontend
- FastAPI + WebSocket backend
- Direct APIs — Anthropic, Google, OpenAI, Perplexity
- Deployed on Render

---

## [v1.0.0] — 2026

### First public release

Concept to working product in 48 hours (Friday post → Sunday v1 live).

#### Added
- Shared persistent transcript — every model receives full conversation history on every call
- `@mention` routing — `@claude`, `@gemini`, `@gpt4o` selective addressing per prompt
- Three providers via GitHub Models free tier — Claude Sonnet, Gemini Flash, GPT-4o
- Model-aware system prompts — each model knows who else is in the room and their relative strengths
- Streamlit dark-themed chat UI with per-model color coding and emoji labels
- Clear roundtable button — reset conversation without app restart
- MIT license

#### Architecture
- `transcript.py` — in-memory shared conversation history
- `router.py` — @mention parser and model registry (`AVAILABLE_MODELS`)
- `main.py` — Streamlit UI and session management

#### Design decisions
- Sequential model calls (not parallel) — preserves compounding context effect
- Human stays in the chair — no orchestrator model in v1
- GitHub Models free tier — removes billing friction for contributors
- Full verbatim history per call — no summarization, no retrieval, no compression

---

## Upcoming

### [v1.1.0] — planned
- Direct Anthropic API integration (native Claude SDK)
- Direct Google AI Studio integration (native Gemini SDK)
- Remove GitHub Models dependency for production use

### [v2.0.0] — planned
- Chair delegation — hand control to a model, take it back anytime
- Export transcript (Markdown, JSON)
- Model-specific cognitive modes (thinking mode hints per @mention)
- Session persistence

### [v3.0.0] — planned
- CognitiveCV framework — agents assigned by thinking mode, not provider
- Six Thinking Hats agent personalities
- Five Whys, First Principles, SCAMPER agent types
- Judge model scoring and cross-validation
