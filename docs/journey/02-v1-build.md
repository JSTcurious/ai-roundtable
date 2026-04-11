# 02 — Building v1 in 48 Hours

*What I built, what I decided, and what I deliberately left out*

---

## The Constraint I Set for Myself

After posting on LinkedIn I gave myself one rule: ship something real before the posts stopped getting attention.

Not a demo. Not a prototype that only works if you squint. A working product that someone else could clone, run, and use in an actual conversation.

That constraint shaped every decision in v1. When I was tempted to add a feature, I asked: does this get me to shipped faster or slower? If slower, it went on the v2 list.

---

## Setting Up the Repo

First decision: private or public from the start?

I made it private initially. Not because I was worried about someone stealing it — the LinkedIn posts had already established the concept publicly. I wanted the first commit to be clean, not a mess of half-working experiments.

The repo structure I set up before writing a single line of logic:

```
ai-roundtable/
├── app/
│   ├── main.py          # Streamlit UI
│   ├── transcript.py    # Shared conversation history
│   └── router.py        # @mention parser
├── .env.example
├── .gitignore
├── LICENSE              # MIT, Jitender Thakur 2026
└── README.md
```

The `.gitignore` went in before anything else. One accidental push of a GitHub PAT and the whole project is compromised. That's not a lesson I needed to learn the hard way.

I chose MIT license immediately. If I want GitHub stars, I want people to be able to use the code without asking permission. Open source is the distribution strategy.

---

## The Three Files That Are the Whole Product

v1 is three files. Everything else is configuration.

### `transcript.py` — The Core Idea Made Real

This is the file that makes ai-roundtable different from every other multi-AI tool.

```python
class Transcript:
    def __init__(self):
        self.messages: List[Dict] = []

    def add_user_message(self, content: str):
        self.messages.append({
            "role": "user",
            "sender": "You",
            "content": content,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

    def add_model_message(self, sender: str, content: str):
        self.messages.append({
            "role": "assistant",
            "sender": sender,
            "content": content,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

    def get_history_for_model(self, model_name: str) -> List[Dict]:
        history = []
        for msg in self.messages:
            if msg["role"] == "user":
                history.append({
                    "role": "user",
                    "content": msg["content"]
                })
            else:
                history.append({
                    "role": "assistant",
                    "content": f"{msg['sender']}: {msg['content']}"
                })
        return history
```

The key method is `get_history_for_model()`. Every model — regardless of which one — receives the complete conversation history on every API call. Claude's responses are labeled "Claude:" in the history that Gemini receives. Gemini's responses are labeled "Gemini:" in the history that GPT-4o receives.

No model is ever operating with partial information. When GPT-4o responds at Prompt 4, it has read everything Claude and Gemini said at Prompts 1, 2, and 3. Verbatim. Perfect recall.

This is better than a human meeting. Someone who joins late gets a verbal summary — lossy, incomplete, filtered through whoever's summarizing. In ai-roundtable, a model joining at any point gets the full transcript. Zero degradation.

That's not a technical feature. That's the product.

### `router.py` — Who Gets Called and Why

The @mention parser is simpler than it sounds:

```python
AVAILABLE_MODELS = {
    "@claude": {
        "name": "Claude",
        "model_id": "claude-sonnet-4-5",
        "emoji": "🟠",
        "strength": "Reasoning, synthesis, long-form analysis"
    },
    "@gemini": {
        "name": "Gemini",
        "model_id": "gemini-2.0-flash",
        "emoji": "🔵",
        "strength": "Speed, breadth, multimodal awareness"
    },
    "@gpt4o": {
        "name": "GPT-4o",
        "model_id": "gpt-4o",
        "emoji": "🟢",
        "strength": "Code, structured output, instruction following"
    }
}

def parse_mentions(prompt: str) -> List[dict]:
    mentioned = []
    prompt_lower = prompt.lower()
    for mention, config in AVAILABLE_MODELS.items():
        if mention in prompt_lower:
            mentioned.append(config)
    return mentioned
```

One bug I caught before shipping: `@gpt4omini` would match `@gpt4o` because the substring check finds `@gpt4o` inside `@gpt4omini`. The fix was ordering — check longer strings before shorter ones, and remove matched strings from the prompt before checking the next one. Small thing, but the kind of edge case that breaks demos at the worst moment.

Each model also receives a system prompt that tells it who else is in the room:

```python
def get_system_prompt(model_name: str, all_models: List[str], strength: str) -> str:
    others = [m for m in all_models if m != model_name]
    others_str = " and ".join(others) if others else "no one else"
    return (
        f"You are {model_name}, participating in a group roundtable discussion. "
        f"Your strength is {strength}. Lead with that. "
        f"Other participants in this roundtable are: {others_str}. "
        f"You can see everything said by everyone in the conversation history. "
        f"Respond only when directly addressed. "
        f"Be direct and concise. Build on what others have said when relevant. "
        f"Do not prefix your response with your own name."
    )
```

That last line — "Do not prefix your response with your own name" — came from watching GPT-4o respond with "GPT-4o: Here's my take..." in early testing. The UI already labels who said what. The model labeling itself was redundant and made the transcript harder to read.

### `main.py` — The UI That Holds It Together

I used Streamlit for v1. Dark themed, chat bubble layout, per-model color coding. It worked well enough to validate the concept.

The send flow is simple:
1. User message added to transcript
2. `parse_mentions()` extracts which models to call
3. Each model called sequentially with full transcript history
4. Each response added to transcript immediately
5. UI rerenders the full conversation

Sequential, not parallel. This was a deliberate decision I want to document clearly because it looks like a performance compromise but it isn't.

---

## The Decisions That Defined v1

### Sequential Over Parallel

The obvious implementation is to call all three models simultaneously with `asyncio`. Faster. More efficient. Standard pattern for multi-model apps.

I rejected it.

Here's why: if I call Claude, Gemini, and GPT-4o in parallel, they all receive the same transcript state — the state *before* any of them responded. When Gemini responds, it hasn't heard Claude. When GPT-4o responds, it hasn't heard either.

That's a comparison tool. Three models answering the same question independently and simultaneously.

What I wanted was a conversation. When Gemini responds *after* Claude in sequential mode, it has Claude's response in its history. It can build on it, challenge it, or take a different angle — with full awareness of what Claude said.

The compounding effect only works with sequential calls. Parallel calls break the room metaphor entirely.

### No Orchestrator Model

I explored a design where one model was designated as the orchestrator — it would read all responses and decide what the next action should be. Route the conversation forward automatically.

Rejected for v1. The human is the orchestrator. That's the entire product philosophy. An AI orchestrator turns ai-roundtable into a slightly friendlier version of what Microsoft shipped.

Chair delegation — letting a model drive the conversation while you observe — is a v2 feature, and even then it's something the human activates and can revoke. The default is always human in control.

### GitHub Models Free Tier

I used GitHub Models instead of direct Anthropic, Google, and OpenAI APIs. One client, one auth token, three providers. Zero billing friction.

The tradeoff: rate limits, no Perplexity, model IDs that lag behind direct APIs. Acceptable for v1. Not acceptable for v2.

The reasoning: if someone finds the repo and wants to try it, I want the setup to be "get a GitHub account" not "set up billing with three separate AI providers." Lowering the barrier to first run matters for GitHub stars.

### Streamlit for the UI

Streamlit is a prototyping tool. I knew that going in. I used it anyway because v1 needed to ship in 48 hours and Streamlit lets you build a functional chat UI in hours not days.

The customization limits are real. The session state quirks are annoying. The deployment story is mediocre.

None of that matters for v1. What matters is that it works well enough to show the concept to another person and have them understand it immediately.

v2 gets React + FastAPI. v1 got shipped.

---

## What I Left Out Intentionally

**Authentication** — v1 is single user, local. Streamlit session state handles isolation for one browser session. Multi-user is a deployment problem, not a v1 build problem.

**Conversation persistence** — sessions don't survive a page refresh. The transcript is in-memory. Acceptable for a concept validation tool.

**Error handling** — basic try/catch around API calls, nothing more. Rate limit errors surface as warning messages in the UI. Good enough for v1.

**Perplexity** — no search-augmented fact-checking in v1. The concept needed validation before adding a fourth provider.

**Deep mode / cross-critique** — the multi-round critique architecture I designed for v2 would have taken a week to build and test properly. v1 proves the shared transcript mechanic. v2 proves the roundtable intelligence mechanic.

Every item on that list is a deliberate omission, not an oversight. The ARCHITECTURE.md in the repo documents each one and why.

---

## Making It Public

Once v1 was working end-to-end — intake to response to shared transcript — I made the repo public and added a comment to my second LinkedIn post:

> "v1 is live — github.com/JSTcurious/ai-roundtable"

That was it. No launch post. No Product Hunt. Just a comment on a post that already had context.

The repo went public on a Sunday. The first post had gone up Friday. 48 hours from concept to shipped product.

---

## What Building v1 Taught Me

**The README is the product for GitHub.** Before anyone runs your code they read your README. I spent almost as long on the README as I did on the transcript implementation. The chat example in the middle — showing how the conversation compounds across prompts — does more to explain the product than any description paragraph.

**Document what you rejected.** ARCHITECTURE.md has a "What Was Rejected" section. Parallel calls, orchestrator model, RAG memory, authentication — each one with a reason. That section gets more attention from technical reviewers than the implementation details. It shows product judgment, not just coding ability.

**Ship the concept, not the vision.** v1 is not ai-roundtable as I imagined it. It's missing intake, model tiers, Perplexity fact-checking, cross-critique, and a real UI. What it has is the shared transcript — the one thing that makes everything else possible. Ship the concept first. Build the vision second.

**48 hours is enough to validate an idea.** Not to finish a product. Not to build something production-ready. But to find out if the core mechanic works, if someone else can understand it immediately, and if the problem you're solving is real enough to keep building. All three answered yes.

---

*Previous: [01 — The Origin](01-origin.md)*
*Next: [03 — The Microsoft Gut Punch](03-microsoft-gut-punch.md)*
