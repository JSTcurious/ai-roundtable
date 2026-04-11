# 05 — Building v2 with Agentic Tools

*A field report on using Claude Code, Cursor, and Figma MCP to build a production AI product*

---

> **Note:** This document is live. The planning section below was written before the v2 build started. Field notes are added in real time during the build. The gap between plan and reality is the most honest part of this doc.

---

## The Premise

v1 was built by hand — every file written line by line, every decision made in the moment. That's the right approach for a 48-hour concept validation.

v2 is different. The architecture is specified. The product decisions are made. The work is largely implementation — and implementation is exactly what agentic coding tools are built for.

The goal: use agents to do the building, use my judgment for the deciding. Minimize the time I spend writing boilerplate. Maximize the time I spend on product decisions that agents can't make.

---

## The Tool Stack

| Tool | Role | Why |
|------|------|-----|
| Claude Code | Primary backend builder | Agentic, file-aware, runs tests, multi-file refactors |
| Cursor | Frontend React components | In-editor AI, best for component generation against a design |
| Figma MCP | Design → code handoff | Gives Cursor direct access to design specs without manual translation |
| Playwright MCP | End-to-end testing | Automated QA after each phase |
| GitHub Copilot CLI | Terminal tasks, git ops | Supporting role, quick scripts |

---

## CLAUDE.md — The Most Important File

Before any agent writes a line of code, CLAUDE.md goes in the repo root. This is the persistent context file Claude Code reads at the start of every session. Without it, every session starts cold.

```markdown
# ai-roundtable v2 — CLAUDE.md

## Project
Group chat where participants are AI models.
Human stays in the chair. Models respond when addressed.

## Architecture
- Backend: FastAPI + WebSockets
- Frontend: React + Tailwind CSS
- APIs: Anthropic, Google, OpenAI, Perplexity (direct)
- Deploy: Render

## Model Tiers
Regular: Claude Sonnet, Gemini Flash, GPT-4o, Sonar
Deep: Claude Opus, Gemini Pro, GPT-5.4, Sonar Pro

## Core Loop (Default Mode)
1. Intake — Claude conducts 3-question conversation
2. User declares output type + tier
3. Claude recommends seats, user confirms
4. Round 1 — Claude + Gemini + GPT respond sequentially
   (each receives full transcript history)
5. Perplexity audits all three simultaneously
6. Claude synthesizes with Perplexity audit factored in

## Deep Mode (User Activated)
Round 1 → Perplexity audit → Cross-critique round →
Revision round → Claude synthesis

## Key Decisions — Do Not Override
- Sequential responses in Round 1 (not parallel)
  Parallel breaks the compounding transcript effect
- Human confirms all model activation — never auto-activate
- Perplexity is fact-checker only — does not respond to prompts
- No orchestrator model — human is the chair
- Cross-critique is opt-in — cost and latency are real

## File Structure
backend/
  main.py
  intake.py
  transcript.py
  router.py
  models/
    anthropic.py
    google.py
    openai_client.py
    perplexity.py
frontend/
  src/
    components/
      IntakeFlow.jsx
      SessionView.jsx
      TranscriptPanel.jsx
      SynthesisPanel.jsx
    App.jsx
    index.js
```

---

## Planned Build Sequence

### Phase 0 — Design in Figma (Before Any Code)
Design four frames before any agent writes anything:
- Intake conversation flow
- Session view — four seats, tier selector, mode toggle
- Transcript panel — streaming chat bubbles, per-model color coding
- Synthesis panel — Claude's final answer, Perplexity citations

Figma MCP connects the design directly to Cursor. Agents build what they can see.

### Phase 1 — Backend with Claude Code

```bash
# Session 1 — Scaffold
claude "Read CLAUDE.md. Scaffold the full v2 backend 
structure. Create all files with stubs and docstrings. 
No implementation yet. Confirm structure before proceeding."

# Session 2 — API integrations
claude "Implement all four model clients in backend/models/.
Use direct APIs per CLAUDE.md. Include tier switching logic.
Test each client with a single ping call before moving on."

# Session 3 — Transcript + Router
claude "Implement transcript.py and router.py.
Transcript must format history correctly for each 
provider's API message format. Include tests."

# Session 4 — Intake flow
claude "Implement intake.py. Claude conducts a 3-question 
intake. Returns structured session config with problem, 
output_type, tier, recommended_seats, opening_prompt."

# Session 5 — Core loop
claude "Implement default mode core loop in main.py.
Round 1 sequential, Perplexity audit parallel,
Claude synthesis with audit. Wire to FastAPI endpoints."

# Session 6 — WebSocket streaming
claude "Add WebSocket support. Stream tokens from each 
model as they arrive. Endpoint: ws://localhost:8000/ws/session"
```

### Phase 2 — Frontend with Cursor + Figma MCP
- Point Cursor at Figma frame URLs via MCP
- Generate each component against the design spec
- Wire WebSocket connection to FastAPI backend

### Phase 3 — Integration
End-to-end test with a real session prompt. Fix integration errors.

### Phase 4 — QA with Playwright MCP
Automated tests for intake flow, API connections, transcript accumulation, synthesis, deep mode toggle.

### Phase 5 — Deploy
Render deployment with environment variable configuration.

---

## Field Notes

*This section is updated in real time during the v2 build.*

---

### Before Starting

*What I expect will be hard:*
- Figma MCP locally — I have it on claude.ai, need to replicate in Claude Code and Cursor
- WebSocket streaming — first time building this pattern
- Claude synthesis prompt — getting the right tone and structure for the final answer

*What I expect agents to handle well:*
- Boilerplate scaffolding
- API client implementations — all four follow similar patterns
- React component structure from Figma specs
- Playwright test generation

---

### During the Build

*(Field notes added here as each phase completes)*

**Phase 0 — Figma Design**


**Phase 1 — Backend**


**Phase 2 — Frontend**


**Phase 3 — Integration**


**Phase 4 — QA**


**Phase 5 — Deploy**


---

### After the Build

*(Honest post-mortem added here when v2 ships)*

*What the agents got right:*

*Where I had to intervene:*

*What I would do differently:*

*The gap between the plan above and what actually happened:*

---

*Previous: [04 — Designing v2](04-v2-architecture.md)*
*Next: [06 — Lessons](06-lessons.md)*
