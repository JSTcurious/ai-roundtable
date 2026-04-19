# Architecture — ai-roundtable

> What was built, why it was built this way, and what was deliberately left out.
> v1 decisions are complete. v2 shipped April 2026.

---

## The Product Principle Behind Every Decision

> The human stays in the chair. Always.

This is not a tagline. It is a constraint that eliminates a large class of features that would otherwise seem reasonable. Every architectural decision below was evaluated against it.

---

## Model Philosophy

ai-roundtable targets high-stakes decisions where getting it
right once is worth more than iterating cheaply. Cost is not
a design constraint. Model choices are made for quality
ceiling, not cost floor.

### Model assignments by stage
| Stage            | Model              | Rationale                              |
|------------------|--------------------|----------------------------------------|
| Intake           | Claude Sonnet      | Full intent capture drives everything downstream |
| Research (Smart) | Sonnet → Opus      | Executor/advisor split for depth       |
| YOUR TAKE chips  | Claude Sonnet      | Chip quality determines user engagement |
| Synthesis        | Claude Opus        | This is the deliverable                |
| Fact-check       | Perplexity         | Live web grounding                     |
| Fallback (intake)| GPT-4o Mini → Qwen | Resilience, not quality targets        |

---

## v1 Architecture

### Core Design Principle

Every model receives the **complete verbatim transcript** on every API call.

This is not a performance optimization — it is the product. A model joining at Prompt 4 receives everything said at Prompts 1, 2, and 3 by every other model and by the user. Perfect recall. No degradation. Better than a human meeting where a late arrival gets a verbal summary.

### Three-File Architecture

**`transcript.py` — The Source of Truth**

The `Transcript` class is a simple in-memory list of message dicts. Every message — user or model — is appended in order with a sender label and timestamp.

`get_history_for_model()` formats the full history for any model's API call. Model responses are prefixed with the sender's name so each model knows who said what:

```
assistant: Claude: Use LlamaIndex + Qdrant for your RAG stack...
assistant: Gemini: I'd add a concern about the embedding cost at scale...
```

**What this is not:** a vector store, a summarizer, a memory compressor. v1 sends raw full history every time.

**`router.py` — The @Mention Parser**

`parse_mentions()` does a simple substring scan of the lowercased prompt. Order matters — `@gpt4omini` is checked before `@gpt4o` to prevent partial matches.

`AVAILABLE_MODELS` is the single source of truth for model handles, model IDs, display names, emojis, and strength descriptions.

`get_system_prompt()` tells each model who they are, their strength, who else is in the room, and not to prefix their response with their own name.

**`main.py` — Streamlit UI**

Session state holds one `Transcript` instance per browser session. On send: user message → parse mentions → sequential model calls → each response added to transcript → UI rerenders.

### What Was Rejected in v1

**Parallel model calls (asyncio)**
Rejected. Sequential calls preserve response ordering. When Gemini responds after Claude, it has Claude's response in its history. Parallel calls break this — you'd send pre-call history to all models simultaneously, losing the compounding effect. Sequential is the correct model for a room metaphor.

**Orchestrator model**
Explored a design where one designated model drives the conversation forward. Rejected — the human is the orchestrator. Chair delegation is a future feature.

**Side-by-side comparison layout**
Rejected. Side-by-side is a comparison tool. A sequential chat transcript is a conversation. The UI choice reinforces the product philosophy.

**RAG / vector memory**
Not needed. The transcript IS the memory. Full verbatim history sent every call.

**Authentication / multi-user**
v1 is single-user local. Multi-user is a deployment concern, not a v1 build concern.

### Model Provider Choice — GitHub Models

v1 uses GitHub Models free tier. One client, one auth token, three providers. Free tier removes billing friction for contributors and early users.

**Why not direct APIs in v1?**
Speed to ship. 48 hours concept to working product. GitHub Models removes billing setup for anyone who wants to run it locally.

### What Would Break v1

- Long conversations hit GitHub Models context limits
- Concurrent users need async deployment — Streamlit is single-threaded
- Model IDs hardcoded — GitHub Models endpoint changes require a config update

### AI vs. Engineer — v1

**AI (GitHub Copilot + Claude):** Streamlit layout boilerplate, `parse_mentions()` ordering fix suggestion, system prompt language drafts.

**Engineer (Jitender Thakur):** Conceived shared transcript as core differentiator, rejected parallel calls, decided against orchestrator model, chose GitHub Models for contributor friction, defined "room not pipeline" framing.

---

## v2 Architecture

### Why v2 Is a Ground-Up Rebuild

v1 proved the core mechanic. v2 builds the product.

Streamlit fights every customization attempt. GitHub Models rate limits hit fast under multi-round loads. No intake means users arrive with vague prompts and get generic answers. No Perplexity means no fact-checking. Two tiers is too coarse. Three models is missing the dedicated research seat.

v2 is not a refactor. It is a rebuild with a validated concept.

### The Five Seats

| Seat | Provider | Role |
|------|----------|------|
| Claude | Anthropic | Orchestrator — intake conductor + synthesizer |
| Gemini | Google | Deep reasoner |
| GPT | OpenAI | Generalist structurer |
| Grok | xAI | Lateral thinker + live trends |
| Perplexity | Perplexity AI | Fact-checker only — never opines |

**Why Claude as orchestrator:**
Claude's strength in reasoning, natural prose, and agentic reliability makes it the right choice for intake (understanding what the user needs) and synthesis (producing a structured final deliverable). This is a product decision based on specific capabilities — not a claim that Claude is universally better.

**Why Perplexity as auditor not panelist:**
Perplexity doesn't have its own generative model — it routes to frontier models with search infrastructure on top. Its value is real-time web research with citations, not generative opinion. In a roundtable of opinionated thinkers, a dedicated fact-checker who doesn't opine is the most valuable seat of all.

**Why Grok:**
Grok's live X/Twitter data access and lateral thinking disposition add a research dimension that Gemini and GPT lack. As the "contrarian + lateral thinker" seat, Grok surfaces angles the other models are trained to avoid. Added in v2.1.1 as the third research seat alongside Gemini and GPT.

### Three Tiers — The Advisor Pattern

v2 replaces the binary regular/deep toggle with three tiers:

| Tier | What Runs | When |
|------|-----------|------|
| Quick | Executor model only | Brainstorms, gut checks, quick answers |
| Smart | Executor + Advisor per lab | Most sessions — balanced cost and quality |
| Deep Thinking | Advisor-level model throughout | Critical reports, architecture decisions |

**The advisor pattern** — announced by Anthropic in April 2026 — pairs a cheaper executor model running the main loop with an expensive advisor model consulted only on hard decisions. ai-roundtable applies this pattern across all four providers in the Smart tier:

| Provider | Executor | Advisor |
|----------|----------|---------|
| Anthropic | Claude Sonnet | Claude Opus |
| Google | Gemini Flash | Gemini Pro |
| OpenAI | GPT-4o | GPT-4o (GPT-5 pending API access) |
| xAI | grok-3-mini | grok-3 |
| Perplexity | Sonar | Sonar Pro |

Smart is the default recommended tier. Claude suggests it during intake based on the declared output type. User confirms or overrides.

### The Intake — Most Important Design Decision

Most AI tools assume the user arrives with a good prompt. ai-roundtable assumes they don't.

The intake is a short conversational session conducted by Claude before any frontier model is invoked:

1. **Mirror first** — Claude reflects back what it heard before asking anything. User feels understood, not interrogated.
2. **Confirm before proceeding** — User corrects or approves before information gathering begins.
3. **Progressive questioning** — One question at a time. Acknowledges before asking the next. Never a form.
4. **Escape hatches** — User can stop at any point. Claude works with what it has and flags open assumptions.
5. **Completion mirror** — Claude summarizes everything learned in natural prose before producing the optimized prompt.
6. **User approval** — Optimized prompt shown to user before any frontier model sees it. User can edit.

**What Was Rejected in the Intake Design:**

A form-based intake — rejected. Forms feel like bureaucracy. A conversation feels like a smart colleague.

Auto-proceeding after N questions — rejected. Completion is quality-gated, not count-gated.

Auto-selecting models without user confirmation — rejected. The human stays in the chair. Claude recommends. User confirms.

### The Session Loop

**Sequential in Round 1. Always.**

Gemini responds first, then GPT with Gemini's answer already in its history. The transcript compounds. Parallel calls would break this. Note: Claude is not a Round 1 respondent — it is the synthesis orchestrator only.

**Perplexity audits Gemini + GPT responses after Round 1.**

Perplexity receives the completed Gemini and GPT responses and returns fact-check findings with citations before Claude synthesizes.

**HITL Chair Dialogue — between Perplexity and synthesis.**

After the Perplexity audit completes, Claude generates 3-5 observations about the session (quick tier, structured JSON). Each observation is sent to the frontend via `synthesis_observation`. The WebSocket pauses synthesis and waits for a `chair_decision` frame for each observation:

```
{ type: "chair_decision", decision: "keep" | "overrule", overrule_text?: string }
```

All overrule decisions are appended to the Claude synthesis system prompt verbatim before the synthesis call. If observation generation fails, the loop is skipped silently and synthesis proceeds.

**Claude synthesizes last — with everything.**

Claude's synthesis receives Gemini + GPT Round 1 responses, the Perplexity audit, and any chair overrule decisions. The synthesis is not a summary — it incorporates the strongest reasoning, corrects factual errors, surfaces model disagreements, and produces a structured answer matching the declared output type.

**WebSocket is bidirectional.**

Server → client: `token`, `model_complete`, `perplexity_thinking`, `perplexity_complete`, `synthesis_observation`, `synthesis_thinking`, `synthesis_token`, `synthesis_complete`, `session_complete`, `error`, `pong`.

Client → server: `chair_decision`, `ping`.

### The Export — Markdown as Universal Intermediary

Every session produces a markdown file. Markdown is portable, readable everywhere, and convertible to any downstream format.

The export serves two purposes:
1. **Deliverable** — the user's report, plan, or decision record
2. **Downstream input** — context for Claude Code, Perplexity, or future tools

The "Take This Further" panel after every synthesis offers: download markdown, save to Google Drive, open in Claude Code, continue in Perplexity.

### Tech Stack — Why React + FastAPI Over Streamlit

Streamlit is a prototyping tool. It fights customization, has no real streaming support, and signals prototype to any technical reviewer.

ai-roundtable v2 is a portfolio centerpiece for an AI Product Engineer role. The UI is part of the product. React + FastAPI signals product. The stack choice is a positioning decision as much as a technical one.

WebSocket streaming matters: tokens stream to the UI as they arrive. Production AI apps stream. v2 streams.

### Competitive Positioning

| Product | Approach | Human Role |
|---------|----------|------------|
| ithy.com | Multi-model aggregator, polished article output, black box synthesis | Passenger |
| Microsoft Critique | GPT drafts, Claude reviews, fixed sequence | Passenger |
| Microsoft Council | Parallel outputs, judge model synthesizes | Passenger |
| GitHub Rubber Duck | Second model reviews agent before execution | Passive |
| Anthropic Advisor Strategy | Executor + advisor within single API call | Infrastructure pattern |
| **ai-roundtable** | Five providers, thorough intake, shared transcript, fact-checked, full journey visible | **In the chair** |

**The ithy distinction specifically:**
ithy gives you a better answer. ai-roundtable gives you one you can trust — because you can see exactly how it was reached, what was assumed, where models disagreed, and what was fact-checked before the synthesis reached you.

### What Was Rejected in v2

**Auto-activating all models on every prompt** — rejected. Human confirms which seats are active.

**Orchestrator model driving conversation** — rejected. Claude synthesizes — it does not route or decide what happens next.

**Voice input/output** — v3 consideration.

**Saved sessions** — transcript doesn't persist beyond browser session. v3 problem.

**Mobile-first UI** — the intake flow and four-model session view need screen real estate. Desktop-first for v2.

**API key management UI** — users set keys in `.env`. No in-app secrets management.

**Model picker beyond four seats** — opinionated by design. Arbitrary model selection turns ai-roundtable into a comparison tool.

### What Would Break v2

- Long conversations will hit context limits — v3: sliding window or summarization
- Advisor strategy beta status — if Anthropic's API changes, Smart tier falls back to Deep Thinking models
- GPT advisor tier uses `gpt-4o` — update to `gpt-5` when API access confirmed
- Google Drive export not yet implemented — v3
- Concurrent users at scale need Redis for session state
- No Render deployment yet — v3

### AI vs. Engineer — v2

**AI (Claude Code + Cursor):** Scaffolding, boilerplate, API client implementations, React component generation against Figma specs, Playwright test generation.

**Engineer (Jitender Thakur):** Conceived intake mirror step, rejected parallel calls for compounding effect, decided Perplexity audits rather than opines, applied advisor pattern across all four providers not just Anthropic, chose sequential synthesis to preserve transcript integrity, designed Smart tier as default, defined downstream handoff pattern via markdown intermediary.

---

*Last updated: April 15, 2026 · v1.0 complete · v2.1.1 shipped*
