# 04 — Designing v2

*Every architectural decision, why it was made, and what was considered and rejected*

---

## Why v1 Wasn't Enough

v1 proved the core mechanic — shared persistent transcript, @mention routing, three models in the same conversation. That was the right thing to build first.

But v1 had real limitations that weren't acceptable for a product I wanted people to actually use:

- GitHub Models free tier meant rate limits hit fast and model IDs lagged behind direct APIs
- Streamlit UI fought every customization attempt and had no real streaming support
- No intake — users landed in a blank chat with no guidance on how to get value
- No Perplexity — no fact-checking, no citations, no real-time web awareness
- One tier — no distinction between a quick question and deep research
- Three models — no fourth seat for a genuinely different capability

v2 isn't a refactor of v1. It's a ground-up rebuild with a validated concept and a clear product philosophy.

---

## The Product Principle That Drives Everything

Before any technical decision: **the human stays in the chair.**

This isn't a tagline. It's a constraint that eliminates a large class of features that would otherwise seem reasonable.

Auto-routing prompts to the right model? Rejected — the human decides who speaks.
Auto-activating all models on every prompt? Rejected — the human selects the panel.
Orchestrator model that drives the conversation forward? Rejected — the human is the orchestrator.
Cross-critique mode running by default? Rejected — the human activates deep mode when the cost and latency are worth it.

Every feature in v2 was evaluated against this constraint. If it reduced human agency in the conversation, it didn't ship.

---

## The Four-Seat Roundtable

v1 had three models chosen for availability on GitHub Models. v2 has four models chosen for **cognitive complementarity** — each seat does something the others don't.

| Seat | Provider | Role | Why This Seat Exists |
|------|----------|------|----------------------|
| Claude | Anthropic | Intake conductor + synthesizer | Best natural prose, agentic reliability, safety — runs intake, owns final synthesis |
| Gemini | Google | Deep reasoner | Leads on complex multi-step reasoning, massive context window, multimodal |
| GPT | OpenAI | Generalist structurer | Strongest all-rounder, best for structured output and actionable recommendations |
| Perplexity | Perplexity AI | Fact-checker | Real-time web search with citations — audits the other three, doesn't opine |

The fourth seat was the hardest decision.

I initially considered Grok 4 for its real-time data access and speed. Rejected it. Grok's positioning — "uncensored, maverick, candid" — is a liability for the buyer Arpita identified: decision-makers, consultants, PMs. Those people need quality thinking, not bold personality. Grok's edge is live X/Twitter data and informal style. Neither is what my buyer needs at the moment they're stress-testing a strategy.

Perplexity is the right fourth seat for a specific reason: it doesn't have its own generative model. It routes to Claude, GPT, and others under the hood, with its own search and citation infrastructure on top. That means its value is the **capability** — real-time web research with source attribution — not the generative opinion. In a roundtable of opinionated thinkers, a dedicated fact-checker who doesn't opine is the most valuable seat of all.

One nuance worth documenting: because Perplexity routes to frontier models under the hood, there's a theoretical overlap risk — if Perplexity routes to Claude, you have two Claude-flavored responses. In practice, the search infrastructure is the differentiation, not the generation. The cross-model independence concern is real but secondary to the unique capability Perplexity brings.

---

## Two Tiers, Not One

v1 treated every prompt the same. v2 distinguishes between two modes from the start of every session:

**Regular** — fast, cost-effective, capable enough for most tasks
**Deep Thinking** — flagship models, worth the cost and the wait

| Seat | Regular | Deep Thinking |
|------|---------|---------------|
| Claude | Claude Sonnet | Claude Opus |
| Gemini | Gemini Flash | Gemini Pro |
| GPT | GPT-4o | GPT-5.4 |
| Perplexity | Sonar | Sonar Pro |

The tier is declared during intake — before any model is invoked. The user doesn't get surprised by a slow or expensive session mid-conversation. They opt in to deep thinking with full awareness of what that means.

Claude suggests the tier based on what the user declared they want:

```
Quick answer, brainstorm, gut check    → Regular
Report, research, architecture plan,
code project, strategic decision       → Deep Thinking
```

User confirms or overrides. The chair stays with the human.

The Perplexity tier maps cleanly: Sonar for fast search-augmented Q&A, Sonar Pro for deeper context, broader retrieval, and 2x more citations. Same regular/deep logic, consistent across all four seats.

---

## The Intake Flow

The biggest v2 addition is what happens before the roundtable opens.

In v1, users land in a blank chat and figure it out. That works for technical users who've read the README. It doesn't work for the consultant mid-thought who has 20 minutes before a client call.

v2 opens with a short intake conversation conducted by Claude. Three questions, conversational tone, not a form:

1. **What are you working on?** — raw description, no constraints
2. **What do you want at the end?** — report, plan, code, decision, brainstorm
3. **Regular or deep thinking?** — Claude suggests based on answer 2, user confirms

From those three answers Claude produces a structured session config:

```python
{
    "problem": "Evaluating three cloud providers for a startup",
    "output_type": "comparison_report",
    "tier": "regular",
    "recommended_seats": ["claude", "gemini", "gpt"],
    "opening_prompt": "..."
}
```

Claude also generates an **opening prompt** — a reframed, sharpened version of what the user described, optimized to get the best first-round responses from all three models. The user sees it before it's sent and can edit or approve.

This is where Claude's strength in natural prose and context understanding does real work. A vague "I'm thinking about cloud providers" becomes a specific, well-framed research question before any model sees it.

The intake is the product differentiator that doesn't show up in any benchmark.

---

## The Default Mode Loop

Once the session opens, the default flow for every prompt:

```
User submits prompt
        ↓
Claude + Gemini + GPT respond sequentially
(each with full transcript history)
        ↓
Perplexity audits all three simultaneously
(fact-checks, flags missing sources, notes currency gaps)
        ↓
Claude synthesizes:
  — strongest reasoning from each model
  — factual corrections from Perplexity
  — where models disagreed and why it matters
  — clear recommendation or conclusion
        ↓
User receives one clean final answer
```

Sequential in Round 1 — same reasoning as v1. When GPT responds after Claude and Gemini, it has their responses in its history. The transcript compounds. Parallel calls would break this.

Perplexity runs in parallel to Round 1 — it's not responding to the prompt, it's auditing the responses. It can start as soon as the first model responds and run concurrently with the remaining models. This minimizes the latency hit of adding a fourth API call.

Claude's synthesis prompt includes all three model responses and Perplexity's full audit. The user gets one answer, not four competing ones. But that one answer has been fact-checked and synthesized before it reached them.

---

## Deep Mode — The Cross-Critique Architecture

Cross-critique is the feature I'm most excited about and the one I'm most cautious about shipping wrong.

When the user activates deep mode, the loop extends:

```
Round 1: Claude + Gemini + GPT respond
        ↓
Perplexity audits
        ↓
Round 2: Each model critiques the others
using a specialized lens
        ↓
Round 3: Each model revises based on critique
        ↓
Claude synthesizes all rounds + Perplexity audit
```

The critique lenses are assigned, not generic:

| Model | Critique Lens |
|-------|--------------|
| Claude | Clarity, completeness, logical gaps |
| Gemini | Reasoning depth, unchallenged assumptions |
| GPT | Structure, actionability, missing angles |
| Perplexity | Factual accuracy, source currency, what's missing from the web |

Generic "critique the other models" instructions produce generic feedback. Assigned lenses produce specific, non-overlapping critique that actually improves the final synthesis.

The cost: in deep mode a single prompt generates approximately 13 API calls before synthesis. This is slow and expensive. That's why it's opt-in, clearly labeled, and only suggested for the output types that warrant it — reports, strategic decisions, architecture reviews.

Cross-critique is what makes ai-roundtable genuinely different from Microsoft's Critique. Their system is linear — one model reviews one other model in one direction. Mine is symmetric — every model reviews every other model, including Claude reviewing GPT and Gemini reviewing Claude. No model is exempt from scrutiny. That's the roundtable.

---

## Why Direct APIs Over GitHub Models

v1 used GitHub Models free tier — one client, one auth token, three providers. It was the right call for a 48-hour build.

v2 uses direct APIs for four reasons:

**Rate limits.** A single deep mode session is 13+ API calls. GitHub Models free tier hits rate limits fast under that load. Direct APIs have higher limits and predictable pricing.

**Perplexity isn't on GitHub Models.** The fourth seat requires a direct Perplexity API integration regardless. Once you're managing one direct API key, the incremental cost of managing four is low.

**Model currency.** GitHub Models model IDs lag behind direct APIs. I want to control exactly which model version is running in each tier, not depend on GitHub Models' update schedule.

**Tier control.** Switching between Claude Sonnet and Claude Opus based on the user's tier selection requires direct API access to specify model IDs precisely.

The Perplexity integration is OpenAI-compatible — same client, different base URL and API key. Low lift.

```python
# All four providers, direct APIs
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
google_client = genai.GenerativeModel(...)
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
perplexity_client = OpenAI(
    api_key=os.getenv("PERPLEXITY_API_KEY"),
    base_url="https://api.perplexity.ai"
)
```

---

## Why React + FastAPI Over Streamlit

Streamlit served v1. It cannot serve v2.

The UI is part of the product. The intake conversation, the four-model session view, the streaming transcript, the synthesis panel — these require control over layout, interaction, and real-time behavior that Streamlit's component model fights at every turn.

More importantly: ai-roundtable is a portfolio centerpiece for an AI Product Engineer role. A Streamlit UI signals prototype. A React + FastAPI stack signals product. The tech choice is a positioning decision as much as a technical one.

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | React + Tailwind | Full UI control, streaming chat, production feel |
| Backend | FastAPI | Async-native, WebSocket support, clean API design |
| Streaming | WebSockets | Tokens stream as they arrive — UI reflects that |
| State | In-memory (v2) → Redis (v3) | Simple now, scalable later |
| Deploy | Render or Railway | One-command deploy, free tier available |

The streaming decision matters more than it looks. When you wait for a complete response before displaying anything, the UI feels slow even if the model is fast. When tokens stream to the UI as they arrive, the experience feels alive. Production AI products stream. v2 streams.

---

## What I Decided Not to Build in v2

**Voice input/output** — technically interesting, not core to the roundtable mechanic. v3 consideration.

**Saved sessions** — transcripts don't persist beyond the browser session. The complexity of session storage, retrieval, and privacy is a v3 problem. v2 users export if they want to keep something.

**Mobile-first UI** — the intake flow and four-model session view need screen real estate. Desktop-first for v2.

**API key management UI** — users set keys in `.env`. No in-app key management. Keeps the codebase simple and avoids building a secrets management system.

**Model picker beyond four seats** — the four-seat architecture is opinionated by design. Letting users swap in arbitrary models would turn ai-roundtable into a model comparison tool. That's not what this is.

---

## What This Architecture Is Actually Saying

Every decision in v2 architecture is a product statement.

Sequential calls say: the conversation compounds, that's the product.
Intake before session says: knowing what you want matters more than fast access to models.
Perplexity as auditor not panelist says: fact-checking and opining are different jobs.
Two tiers say: cost and latency are real, users deserve to opt in knowingly.
Cross-critique as opt-in says: depth has a price, the human decides when it's worth paying.
Direct APIs say: this is production, not a prototype.
React + FastAPI says: the UI is part of the product, not an afterthought.

None of these are the only reasonable choice. All of them are defensible. That's what architecture decisions are — defensible tradeoffs, documented clearly enough that someone else can understand why you made them and argue with you if they disagree.

---

---

## v2 Build Scope — April 11, 2026

*What shipped in v2, what was deferred, and why each decision was made.*

### What's In v2

| Feature | Status |
|---------|--------|
| Intake conversation — Claude mirrors, gathers context, optimizes prompt | ✅ |
| Use case library — 16 curated starting points | ✅ |
| Four providers — Claude, Gemini, GPT, Perplexity | ✅ |
| Quick and Deep tiers — declared during intake | ✅ |
| Sequential Round 1 — Claude, Gemini, GPT | ✅ |
| Perplexity audit — parallel to Round 1 | ✅ |
| Claude synthesis — incorporates audit, structured by output type | ✅ |
| Markdown export — full session or synthesis only, download | ✅ |
| WebSocket streaming — tokens stream as they arrive | ✅ |
| React + Tailwind frontend — production feel, dark theme | ✅ |
| FastAPI backend | ✅ |
| Deploy to Render | ✅ |

### What's Deferred to v2.1

**Deep mode cross-critique**
The symmetric cross-critique architecture — every model critiques every other with specialized lenses — is designed and documented. Deferred because it adds ~8 API calls per prompt and significant complexity to the session loop. v2 validates the default mode loop first.

**Smart tier — advisor pattern**
Anthropic announced the advisor strategy on April 11, 2026 — the same day v2 build started. The pattern is incorporated into CLAUDE.md and ARCHITECTURE.md. Deferred from v2 build because the API is in beta and the pattern needs stability before production use. v2 ships Quick and Deep tiers only.

**Google Drive export**
The markdown file is the universal intermediary — download covers the core use case. Drive integration adds OAuth complexity that would delay shipping. Deferred cleanly — the exporter architecture supports it as an add-on.

**Claude Code handoff button**
The downstream handoff pattern is designed — markdown file plus suggested command. Deferred because it requires stable deployment before the UX makes sense.

**Perplexity handoff button**
Same reasoning as Claude Code handoff. Deferred to v2.1.

**Figma MCP frontend design**
Originally planned — four frames designed in Figma, Cursor reads via MCP, builds components against design spec. Deferred in favor of shipping today. v2 frontend built directly from the design system spec in CLAUDE.md. Figma comes in v2.1 when there's a live product to refine.

### The Scoping Principle

Ship the core loop. Validate it works. Add depth in v2.1.

The features deferred are all enhancements to a working product. The features shipped are what make it a product in the first place. Every deferred feature has a documented design — when v2.1 starts, the spec is already written.

---

*Previous: [03 — The Microsoft Gut Punch](03-microsoft-gut-punch.md)*
*Next: [05 — Building v2 with Agentic Tools](05-agentic-workflow.md)*
