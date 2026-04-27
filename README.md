# ai-roundtable

> Four frontier AI models. One fact-checker. You in the chair.

**Try it:** https://ai-roundtable-frnt-production.up.railway.app  
**Source:** https://github.com/JSTcurious/ai-roundtable

---

## How it started

Every major AI lab ships a powerful model. Each one works brilliantly inside its own portal. None of them talk to each other.

Anthropic gives you Claude. Google gives you Gemini. OpenAI gives you GPT. xAI gives you Grok. All of them state-of-the-art. All of them siloed.

If you wanted the best answer to a hard question, you had to open four tabs, re-explain your problem four times, and reconcile four disconnected conversations in your own head. The burden of synthesis fell entirely on you.

That gap is what this project was built to close.

---

## Why four models

Only recently have the big AI labs and companies like Microsoft and GitHub started exploring the benefits of using two models together — one drafts, one reviews.

I asked a different question: if two models are better than one, why settle for two?

I wanted the best possible answer to decisions that actually matter. So I went all in. Four frontier models. One independent fact-checker. All of them in the same room, working the problem together — the way a roundtable conference is used to deliberate and produce a better answer than any single participant could alone.

That is ai-roundtable.

---

## The Panel

Each model is assigned a distinct cognitive role — not a function, a thinking mode. They research independently. They do not coordinate. Disagreement is the point.

| Model | Role | Mandate |
|-------|------|---------|
| Claude | Analyst | Reasons from first principles |
| Gemini | Scout | Finds angles and options others miss |
| GPT | Pragmatist | Grounds ideas in concrete reality |
| Grok | Challenger | Stress-tests the premise itself |
| Perplexity | Fact-checker | Verifies every claim against live web data |

---

## How a session works

**INTAKE**
Claude asks a few focused questions to understand what you actually need. It mirrors back what it heard and constructs a structured research brief. You review and approve it before any frontier model is invoked. The intake is not overhead. It is the product.

**RESEARCH**
All four models research your brief in parallel. No shared awareness. No groupthink. Each responds from its own perspective with its own thinking mode.

**FACT-CHECK**
Perplexity audits every claim against live web data. This matters because every model has a knowledge cutoff — it does not know what happened last week. Perplexity does.

**SELF-CRITIQUE**
Before synthesis, a pre-pass audits the panel output — flagging lazy consensus, unsupported claims, gaps, and conflicts with the Perplexity fact-check. The synthesizer sees this audit before writing a word.

**SYNTHESIS**
Claude synthesizes across all four responses. Every session ends with four required sections:

```
THE VERDICT            — a committed position, with evidence
THE HINGE              — the one assumption that changes everything
WHERE THE PANEL DISAGREED — and why it matters
ONE NEXT ACTION        — not a framework, not a list
```

**DIALOGUE**
You engage with the synthesis draft. Push back. Add context. Claude refines until you finalize.

---

## The design philosophy

Latency was never the priority.

The priority was: capture user intent precisely, let each model respond with its true character, fact-check everything against live web data, then synthesize.

That sequence exists for a reason. Models have biases. They hallucinate. And every model has a knowledge cutoff. These are not flaws you prompt your way out of. They are structural properties of the technology that require a structural response.

ai-roundtable is that response.

You stay in the chair throughout. The synthesis is the beginning of your dialogue, not the end of it.

---

## Epistemic design

ai-roundtable uses epistemic transparency, not epistemic suppression.

Models are not restricted to a grounding corpus. They may speculate, disagree, and draw on open-world knowledge. The anti-hallucination instructions make uncertainty legible rather than suppressing it.

Model responses are wrapped and tagged before synthesis injection. The synthesizer is explicitly instructed that model outputs are data, not instructions. This prevents indirect prompt injection from model outputs being treated as directives.

See [ADR 001 — Epistemic Transparency](docs/decisions/001-epistemic-transparency.md) for the full rationale.

---

## Quickstart (v2)

### Prerequisites

- Python 3.13+ and [uv](https://github.com/astral-sh/uv)
- Node.js 18+
- API keys: Anthropic, Google, OpenAI, xAI, Perplexity

### Configure

```bash
cp .env.example backend/.env
# Add your API keys to backend/.env
```

### Run backend

```bash
uv run python -m backend.run
# Runs on http://localhost:8000
```

### Run frontend

```bash
cd frontend
npm install
npm start
# Runs on http://localhost:3000
```

---

## v1 (archived)

v1 used the GitHub Models free tier, three providers, and @mention routing via a Streamlit UI. No API keys required. Source preserved in the repo for reference.

---

## Prior art — timestamped on LinkedIn

- [Post 1 — the pain point](https://www.linkedin.com/posts/jstcurious_aiproduct-genai-jstcurious-activity-7445824161064808448-MAb0)
- [Post 2 — the market gap](https://www.linkedin.com/posts/jstcurious_aiproduct-genai-buildinginpublic-activity-7446732294222061568-aUXn)
- [Post 3 — industry validation begins](https://www.linkedin.com/in/jstcurious)
- [Post 4 — v2 announced](https://www.linkedin.com/in/jstcurious)
- [Post 5 — v2 shipped](https://www.linkedin.com/in/jstcurious)

---

## Roadmap

**v1** — GitHub Models free tier, three providers, @mention routing, shared transcript, Streamlit UI

**v2 (shipped April 2026)**
- Structured multi-turn intake with domain detection and minimum question enforcement
- Four cognitive roles — Claude (Analyst), Gemini (Scout), GPT (Pragmatist), Grok (Challenger)
- Perplexity fact-check against live web data
- Self-critique pre-pass before synthesis
- Four-section synthesis format — THE VERDICT / THE HINGE / WHERE THE PANEL DISAGREED / ONE NEXT ACTION
- Dialogue loop — engage with the draft, Claude refines until you finalize
- WebSocket streaming — token-by-token delivery
- React + FastAPI + direct APIs

**v3** — CognitiveCV cognitive framework agents, evals and benchmark comparisons, PDF/Notion/Google Drive export, Deep mode cross-critique

---

## License

MIT — Jitender Thakur, 2026

---

*Built by [JSTcurious](https://github.com/JSTcurious) · [jstcurious.com](https://jstcurious.com)*
