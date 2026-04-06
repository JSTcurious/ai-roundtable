# ⬡ ai-roundtable

> A group chat where your contacts are AI models.

---

## The Problem

You're deep into a conversation with Claude. You've built up context over 10 prompts. Then you wonder — what would GPT-4o say about this?

So you open a new tab, re-explain everything from scratch, get a response with zero context of what you've already discussed, and manually reconcile two disconnected conversations in your head.

For personal projects and brainstorming this is a nightmare. The deeper you go into a conversation, the more expensive it becomes to get a second opinion.

## The Solution

A roundtable for AI models.

Everyone is in the room. Everyone hears everything. You @ mention who you want to speak. The conversation builds — round after round — just like a real roundtable discussion.

```
You: "@llama what stack should I use for this project?"
🟣 Llama: "I'd recommend..."

You: "@gpt4o do you agree?"
🟢 GPT-4o: "Building on what Llama said..."

You: "@gpt4omini summarize what everyone said"
🔵 GPT-4o Mini: "Llama suggested X, GPT-4o added Y..."
```

Every participant has perfect recall of everything said from the very beginning. No one misses context. No one needs to be caught up.

**You are the chair. Not the AI.**

---

## Models Available (v1)

| Mention | Model | Provider | Strength |
|---|---|---|---|
| `@llama` | Meta-Llama-3.1-405B-Instruct | Meta via GitHub Models | Open source reasoning |
| `@gpt4o` | GPT-4o | OpenAI via GitHub Models | Creative alternatives |
| `@gpt4omini` | GPT-4o Mini | OpenAI via GitHub Models | Fast concise responses |

---

## Quickstart

### 1. Clone the repo

```bash
git clone git@github.com:JSTcurious/ai-roundtable.git
cd ai-roundtable
```

### 2. Get a GitHub Personal Access Token

```
github.com → Settings → Developer Settings
→ Personal Access Tokens → Tokens (classic)
→ Generate new token → select repo scope → copy token
```

### 3. Set up environment

```bash
cp .env.example .env
# Edit .env and add your GITHUB_TOKEN
```

### 4. Install dependencies and run

```bash
uv add streamlit openai python-dotenv
export GITHUB_TOKEN=your_token_here
cd app
uv run streamlit run main.py
```

App opens at `http://localhost:8501`

---

## How To Use

- **Click model buttons** above the input to add @ mentions — no need to type them
- **@ mention multiple models** in one prompt to get all of them to respond simultaneously
- **Build the conversation** — every model reads the full transcript each round
- **Ask one model to consolidate** — it has heard everything the others said

---

## Project Structure

```
ai-roundtable/
├── app/
│   ├── main.py         # Streamlit UI and session management
│   ├── transcript.py   # Shared conversation history
│   └── router.py       # @ mention parser and model config
├── .env.example        # Environment variable template
├── .gitignore
├── LICENSE             # MIT
└── README.md
```

---

## Roadmap

- [ ] Real Claude via Anthropic API
- [ ] Real Gemini via Google AI Studio
- [ ] Export conversation transcript
- [ ] Delegate chair to a model
- [ ] Cognitive lens modes (CognitiveCV research)

---

## Why This Is Different

| Tool | What it does |
|---|---|
| Ithy, MultipleChat | Query all models → return one merged answer |
| Poe, AiZolo | Access multiple models under one subscription |
| **ai-roundtable** | Persistent group conversation — models hear each other |

The gap isn't multi-model responses. The gap is multi-model conversation.

---

## License

MIT License — see LICENSE file for details.

Built by [Jitender Thakur](https://jstcurious.com) · [@JSTcurious](https://github.com/JSTcurious)
