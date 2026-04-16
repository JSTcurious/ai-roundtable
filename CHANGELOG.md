# Changelog

All notable changes to ai-roundtable are documented here.

---

## [v2.1.1] — April 15, 2026

### Grok integration, landing page polish

**Grok added as fifth seat**
- xAI Grok joins Gemini and GPT as a RESEARCH stage model
- Role: lateral thinker + live trends — contrarian perspective the other models avoid
- Models: `grok-3-mini` (quick/smart executor), `grok-3` (smart advisor + deep)
- OpenAI-compatible API client (`backend/models/grok_client.py`) at `https://api.x.ai/v1`
- Color: `#1DA1F2` — xAI/Twitter blue
- Requires `GROK_API_KEY` in `.env`
- Added to `router.py` system prompts and synthesis prompt; `main.py` Round 1 gather

**Breadcrumb: TRANSCRIPT → RESEARCH**
- Stage 2 renamed from TRANSCRIPT to RESEARCH to better reflect what's happening
- All references updated in SessionView.jsx and IntakeFlow.jsx header

**CHAIR DECISIONS block**
- Static summary of all HITL observations + chair decisions renders above SynthesisPanel
- Gold left border (`#F5A623`), observation text truncated at 120 chars
- KEPT (green) / OVERRULED (gold) with overrule text in muted grey

**Landing page polish**
- HOW IT WORKS column removed — single-column centered THE PANEL
- THE PANEL descriptions updated: Chair — you decide / Orchestrator + synthesizer / Deep reasoner / Structured thinker / Lateral thinker + live trends / Live fact-checker
- User bullet color changed from orange to `#e8e8e8` — User is not an AI model
- Input placeholder: "What would you like to ask the experts?"
- Submit button: gold background (`#F5A623`), dark text (`#0d0d0d`)
- PROMPT CHOICE explanation line added below toggle (muted, `#666666`)
- Upload prompt link removed
- Philosophy box copy updated: five-model framing with color hierarchy
- JSON download removed from Take This Further panel

---

## [v2.1.0] — April 15, 2026 · commit dac96e6c

### HITL synthesis dialogue, gold design system, four-stage breadcrumb

**Human-in-the-Loop synthesis (new)**
- Claude generates 3-5 synthesis observations before writing the final answer
- Chair sees each observation with Keep / Overrule choice
- Overrule requires text — chair specifies what to change
- All decisions sent via `chair_decision` WebSocket frame; overrules incorporated verbatim into synthesis system prompt
- Observation generation fails silently (returns `[]`) — synthesis always proceeds

**New WebSocket message types**
- `synthesis_observation` — server → client: `{ text, index, total }`
- `chair_decision` — client → server: `{ decision: "keep" | "overrule", overrule_text? }`
- `synthesis_thinking` — server → client: chair dialogue complete, synthesis beginning
- WebSocket is now bidirectional (previously server-to-client only)

**Gold design system**
- `#F5A623` gold as primary UI accent — logo, header nav, breadcrumb active/complete states, Home link, Save & Exit
- Claude orange (`#E8712A`) reserved exclusively for Claude-model elements (bubble border, label, stream cursor)
- Logo hexagon rotated 90° clockwise everywhere (landing page + session header)
- `AI-ROUNDTABLE` uppercase gold in landing page h1 and session header

**Four-stage session breadcrumb**
- PROMPT → TRANSCRIPT → FACT-CHECK → SYNTHESIS replaces Intake → Roundtable → Synthesis
- Phase-driven: each stage activates and completes based on actual WebSocket state
- Active stage pulses with `animate-pulse`; active SYNTHESIS shows `SYNTHESIZING...`
- Tier badge shown as `< SMART MODE >` before breadcrumb row

**Landing page updates**
- Philosophy tagline block added below subtitle
- Mode toggle renamed: Quick → AS-IS PROMPT, Refined → REFINED PROMPT; toggle group centered

**Session header cleanup**
- Single top bar: Home (gold) | AI-ROUNDTABLE (gold) | Save & Exit (gold text, no border)
- Session title removed from header
- Sticky header: top bar + breadcrumb row

**Export additions**
- 📋 Download prompt (.md) — exports `optimized_prompt` from session config; client-side, no API call
- Prompt download markdown format: `# ai-roundtable — Optimized Prompt` + session title + date

**Skip notice handling**
- Gemini/GPT `[...]` backend error strings render as muted inline text instead of full ModelBubble
- When a model is skipped, column grid collapses — active model goes full width

**ModelBubble scrollability**
- All model bubbles: `max-h-[320px] overflow-y-auto`

**SynthesisPanel**
- Section header: `SYNTHESIS` (uppercase, matches other section headers)
- Label: `Claude + Chair · final deliverable`

---

## [v2.0.0] — April 2026

### Core product shipped

**Intake**
- Use case library — 16 curated starting points across four families
- Claude conducts intake conversation — mirrors back, confirms, gathers context progressively
- Escape hatches — user can stop anytime, Claude flags open assumptions
- Optimized prompt shown to user for approval; Adjust flow for inline refinement

**Four seats**
- Claude (Anthropic) — orchestrator, intake conductor, synthesizer (not a Round 1 respondent)
- Gemini (Google) — deep reasoner, Round 1 seat 1
- GPT (OpenAI) — generalist structurer, Round 1 seat 2
- Perplexity — fact-checker only, audits Gemini + GPT responses, never opines

**Session flow**
- Sequential Round 1 — Gemini responds, then GPT with Gemini's answer in context
- Perplexity audits Gemini + GPT responses
- Claude synthesizes all responses + audit
- Full session exportable as markdown or JSON

**Tech stack**
- React + Tailwind frontend
- FastAPI + WebSocket backend (streaming)
- Direct APIs — Anthropic, Google, OpenAI, Perplexity (no GitHub Models, no wrappers)

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
