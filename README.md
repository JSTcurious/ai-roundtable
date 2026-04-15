# AI-ROUNDTABLE

> A thinking environment where four frontier AI models work together to produce a high-quality deliverable.

You arrive with a problem or question. You leave with something you can act on — a report, a plan, an architecture decision, a roadmap.

**The intake is not overhead. It is the product.**

Most AI tools take what you type. ai-roundtable understands what you need — Claude asks a few questions, mirrors back what it heard, and constructs an optimized prompt before any frontier model is invoked. You approve the prompt. Then the roundtable begins.

---

## The Distinction

Most AI tools take what you type. ai-roundtable understands what you need.

Every session starts with a short intake conversation — Claude asks a few questions, mirrors back what it heard, and constructs an optimized prompt before any frontier model is invoked. The intake is not overhead. It is the product.

ai-roundtable is a **thinking session with a deliverable** — four providers working together in a structured process you controlled throughout. The transcript compounds. You walk out with something you can act on.

```
You:     @claude what stack should I use for this RAG system?
Claude:  [responds with recommendation]

You:     @gemini what are the risks of that approach?
Gemini:  [responds — and has read Claude's answer]

You:     @gpt4o what would you do differently?
GPT-4o:  [responds — and has read both Claude and Gemini]

You:     @claude consolidate everything into a decision
Claude:  [synthesizes the full conversation]
```

**Pipeline:** models review in sequence, no shared awareness.  
**Room:** everyone hears everything. You decide who speaks.

---

## v1 Features

- `@mention` routing — call one, two, or all three models per prompt
- Shared persistent transcript — every model receives the full conversation history on every call
- Three providers via GitHub Models free tier — Claude Sonnet, Gemini Flash, GPT-4o
- Model-aware system prompts — each model knows who else is in the room and their relative strengths
- Streamlit UI — dark-themed chat interface with per-model color coding
- Clear roundtable — reset the conversation without restarting the app

---

## Models in v1

| Handle | Model | Strength |
|--------|-------|----------|
| `@claude` | claude-sonnet-4-5 | Reasoning, synthesis, long-form analysis |
| `@gemini` | gemini-2.0-flash | Speed, breadth, multimodal awareness |
| `@gpt4o` | gpt-4o | Code, structured output, instruction following |

All three run via the **GitHub Models free tier** — no OpenAI or Anthropic billing required for v1.

---

## Quickstart

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- GitHub account with [Models access](https://github.com/marketplace/models)
- GitHub CLI (`gh`) authenticated

### Install

```bash
git clone https://github.com/JSTcurious/ai-roundtable.git
cd ai-roundtable
uv add streamlit openai python-dotenv
```

### Configure

```bash
cp .env.example .env
```

Get your GitHub token:
```bash
gh auth token
```

Add it to `.env`:
```
GITHUB_TOKEN=your_token_here
```

### Run

```bash
cd app
streamlit run main.py
```

---

## Project Structure

```
ai-roundtable/
├── app/
│   ├── main.py          # Streamlit UI and session management
│   ├── transcript.py    # Shared conversation history
│   └── router.py        # @mention parser and model registry
├── .env.example         # Token template
├── .gitignore
├── LICENSE              # MIT
├── ARCHITECTURE.md      # Design decisions and what was rejected
├── CHANGELOG.md         # Version history
└── README.md
```

---

## v2 Quickstart

### Prerequisites

- Python 3.11+ and [uv](https://github.com/astral-sh/uv)
- Node.js 18+
- API keys: Anthropic, Google, OpenAI, Perplexity

### Configure

```bash
cp .env.example backend/.env
# Add your API keys to backend/.env
```

### Run backend

```bash
cd /path/to/ai-roundtable
uv run uvicorn backend.main:app --reload
# Runs on http://localhost:8000
```

### Run frontend

```bash
cd frontend
npm install
npm start
# Runs on http://localhost:3000
```

Open `http://localhost:3000`. Type a question, choose AS-IS PROMPT or REFINED PROMPT, and start the session.

---

## Origin

I was exploring how management thinking frameworks — the kind used to structure human group decision-making — could be applied to multi-model AI collaboration. Assign each AI agent a distinct cognitive role. Not a function. A thinking mode.

Then Microsoft announced their two-model critique concept.

But it clarified something: **Microsoft built a pipeline. I'm building a room.**

Prior art timestamped on LinkedIn:
- [Post 1 — the pain point](https://www.linkedin.com/posts/jstcurious_aiproduct-genai-jstcurious-activity-7445824161064808448-MAb0)
- [Post 2 — the market gap](https://www.linkedin.com/posts/jstcurious_aiproduct-genai-buildinginpublic-activity-7446732294222061568-aUXn)

---

## Roadmap

**v1 (current)** — GitHub Models free tier, three providers, @mention routing, shared transcript

**v2 (shipped April 2026)**
- Thorough intake — Claude understands what you need before any model is invoked; optimized prompt shown for approval
- Human-in-the-Loop synthesis — Claude surfaces 3-5 observations before synthesizing; chair keeps or overrules each
- Four providers — Claude (orchestrator) + Gemini + GPT + Perplexity (fact-checker only)
- Four-stage session progress — PROMPT → TRANSCRIPT → FACT-CHECK → SYNTHESIS with live breadcrumb
- Three export formats — full session (.md), synthesis only (.md), optimized prompt (.md)
- Session save and resume — save full transcript + config as .json, reload to continue
- WebSocket streaming — tokens arrive token-by-token; bidirectional for chair dialogue
- React + FastAPI + direct APIs — no GitHub Models, no wrappers

**v3** — CognitiveCV cognitive framework agents, PDF/Notion/Google Drive export, Render deployment, Deep mode cross-critique

---

## License

MIT — Jitender Thakur, 2026

---

*Built by [JSTcurious](https://github.com/JSTcurious) · [jstcurious.com](https://jstcurious.com)*
