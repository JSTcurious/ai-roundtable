# 06 — Lessons

*What building ai-roundtable taught me about products, AI engineering, and building in public*

---

> **Note:** This document grows with the project. Lessons from v1 are complete. Lessons from v2 will be added as the build progresses. A living document is more honest than a polished retrospective.

---

## On Shipping

**Ship the concept, not the vision.**

The version of ai-roundtable I imagined in mid-2025 had intake, model tiers, cross-critique, a polished UI, and a published paper to go with it. What I shipped in 48 hours was a Streamlit app with three models and a shared transcript. Those are not the same product.

The 48-hour version validated the one thing that mattered — the shared transcript mechanic. Everything else is features. Ship the mechanic first, build the features on validated ground.

**The gap between thinking about it and building it is where ideas die.**

I thought about this for six months. I built it in 48 hours. The thinking produced a domain name and an outline. The building produced a working product, public prior art, and external validation from a GTM professional. The ratio is worth remembering.

**A shipped idea with flaws beats an unshipped idea with none.**

v1 has real limitations. Streamlit fights customization. GitHub Models hits rate limits. Sessions don't persist. No intake. No Perplexity. I documented all of it in ARCHITECTURE.md before anyone else could point it out. That transparency is not weakness — it's the evidence that I understand the product well enough to know what's missing and why it's missing.

---

## On Product Thinking

**The pain you live with is the product.**

I was experiencing the exact problem ai-roundtable solves, every day, across the platforms I was using to think about the problem. I didn't need user research. I needed to stop treating my own frustration as background noise and start treating it as a product brief.

The most honest products are built by people who needed them badly enough to build them rather than wait.

**Name the buyer before you name the product.**

I spent weeks describing ai-roundtable as "a group chat with AI models." That's a description of the mechanism, not the value. A GTM strategist I connected with on LinkedIn named the buyer in one paragraph: decision-maker mid-thought, consultant stress-testing a strategy, PM who needs three perspectives before a product call.

She described the buyer better than I had because she wasn't too close to the tool. Find people who will tell you who needs your thing, not just whether they like it.

**Your reaction to competition is product signal.**

When Microsoft shipped Critique I felt deflated for about 24 hours. Then I read the implementation details carefully and felt clarity. They built a pipeline. I was building a room. The deflation told me I cared about the idea. The clarity told me the differentiation was real. Both signals mattered.

If a competitor's launch makes you want to abandon the project, that's important information. If it makes you want to build faster, that's more important information.

**"Microsoft built a pipeline. I'm building a room."**

The framing that survives compression to a single sentence is the framing worth keeping. If you can't say what makes your product different in one sentence that a smart non-technical person immediately understands — the positioning isn't clear yet. Keep compressing until it is.

---

## On AI Engineering

**The shared transcript is infrastructure, not a feature.**

The single most important technical decision in v1 was `get_history_for_model()` — every model receives the complete verbatim conversation history on every API call. This looks like a simple implementation choice. It's actually the product.

Without it, ai-roundtable is a comparison tool. With it, the conversation compounds. The architecture decision and the product philosophy are the same thing.

**Sequential over parallel for the right reasons.**

Parallel API calls are faster and more efficient. I rejected them because parallel calls mean every model answers the same question with the same context simultaneously — no model has heard the others. That's a comparison tool, not a conversation.

The performance cost of sequential calls is real. The product benefit of the compounding transcript is worth it. Know the tradeoff you're making and be able to defend it.

**Context engineering is more valuable than prompt engineering.**

The system prompt each model receives in ai-roundtable isn't just instructions — it tells the model who else is in the room, what their strength is, that they can see the full conversation history, and not to prefix their response with their own name. Each of those details changes the output in a specific, observable way.

Good context engineering makes every prompt better automatically. Good prompt engineering helps one prompt. Build the context first.

**Agents do the building. You do the deciding.**

The v2 build uses Claude Code for backend, Cursor for frontend, Figma MCP for design handoff. Agents are excellent at scaffolding, boilerplate, API client implementations, and component generation against a spec.

Agents are not good at: knowing when sequential is better than parallel, deciding that Grok doesn't belong in the roundtable, figuring out that Perplexity should audit not opine, or choosing React + FastAPI over Chainlit for portfolio positioning reasons.

Those decisions are mine. The agent executes. I decide.

**Document what you rejected.**

ARCHITECTURE.md has a "What Was Rejected" section. Every major decision has a corresponding rejected alternative and the reason it was rejected. This is the most read section of the architecture docs for technical reviewers.

It shows product judgment — not just knowing what to build, but knowing what not to build and why. That's the scarce skill.

---

## On Building in Public

**Timestamps are prior art.**

The LinkedIn posts from Friday preceded Microsoft's releases the following week. That sequence, publicly documented, establishes that the concept was conceived independently. For a solo builder with no legal budget, public timestamps are the most accessible form of intellectual property protection available.

Post before you build. The timestamp is the patent.

**Write the decision record, not the press release.**

The journey docs in this folder are not marketing. They're a record of what was decided, what was considered and rejected, and what was learned. Written for a hiring manager who has reviewed 50 portfolios and can tell the difference between a project that was thought through and one that was assembled.

The value isn't in how impressive the decisions sound. It's in how traceable they are. Can a reader follow the reasoning from problem to product to architecture without gaps? If yes, the record is working.

**The audience for building in public is not who you think.**

I posted about ai-roundtable to establish prior art and validate demand. The unexpected outcome was a substantive conversation with a GTM strategist who named my buyer, suggested a provisional patent, and offered to stay in touch for v2.

That conversation happened because I was specific about what I was building and honest about the origin story — including the gut punch and the six months of non-shipping. Sanitized success stories attract passive engagement. Honest stories attract real conversation.

**Industry validation is distribution you didn't pay for.**

Every article about Microsoft Critique explained to potential buyers why single-model AI has blind spots. Every article about GitHub's Rubber Duck explained why AI self-review is insufficient. My product is the answer to that problem in a different context — the human-in-the-chair, conversation-compounds answer.

Microsoft spent significant marketing budget educating my market. Be aware of what the large players are doing not just as competition but as free market education for your specific positioning.

---

## What I Would Do Differently

**Start building on Day 1, not Day 180.**

The six months between the idea and the build produced almost nothing useful. The 48 hours of building produced a working product. The lesson is not specific to this project — it's a general principle I've internalized and will apply to every idea going forward.

Time spent thinking without building is only valuable up to the point where you understand the core mechanic well enough to ship it. After that point, the build is the thinking.

**Write CLAUDE.md before the first line of code.**

For v1, context lived in my head. For v2, it lives in CLAUDE.md. The difference is that agents can read CLAUDE.md. The investment in writing it clearly before the first session pays back in every subsequent session that doesn't need to re-establish context.

**Design in Figma before building the frontend.**

I didn't have Figma frames for v1. The UI was figured out in real time in Streamlit. That's fine for a 48-hour prototype. For v2, designing the four key screens before any code was written means the frontend agent has a spec to build against, not a description to interpret.

**Register the domain and the repo on the same day as the first LinkedIn post.**

Not two days later. Not after the first working version. The same day. The timestamp on the repo and the domain registration are part of the prior art trail.

---

## On Understanding What the User Needs

**"Context before prompt."**

Not prompt engineering. Context extraction — the disciplined process of gathering everything the frontier models need before any of them are invoked. Good context engineering makes every prompt better automatically. Good prompt engineering helps one prompt. Build the context first.

**"The intake is not overhead. It is the product."**

Most AI tools assume the user arrives with a good prompt. ai-roundtable assumes they don't. The mirror step, the progressive questioning, the escape hatches — these aren't UX polish. They're the mechanism that closes the gap between what the user types and what they actually need.

**"Most AI tools start with your prompt. ai-roundtable starts with your situation."**

This is the one-line differentiation that survives compression. When you can say what makes your product different in one sentence that a non-technical person immediately understands, the positioning is clear.

**"Mirror before you dig."**

Reflect back what you heard before asking anything. A user who feels heard and in control will answer six questions. A user who feels interrogated will abandon after two. The mirror step is not courtesy — it is conversion.

**Garbage in, garbage out applies to frontier models too.**

The quality of the final deliverable is determined almost entirely by the quality of the opening prompt. The intake is the quality gate. Every question Claude asks is eliminating an assumption that would otherwise produce a generic answer.

---

## On Market Positioning

**"Industry validation is distribution you didn't pay for."**

Microsoft's Critique, GitHub's Rubber Duck, Anthropic's advisor strategy — each release educated the market on why single-model AI has blind spots. That's the premise of ai-roundtable, explained by three major players' PR teams to millions of people. Be aware of what large players are releasing not just as competition but as free market education for your positioning.

**"Incorporate, don't just observe."**

When Anthropic announced the advisor strategy, the right response wasn't just a LinkedIn post about it. It was incorporating the pattern into v2 as the Smart tier — across all four providers simultaneously. Observing market signals is table stakes. Incorporating them into your architecture is the differentiator.

**Ideas posted publicly are not stolen — they are protected.**

Every LinkedIn post is a timestamp. The prior art trail — LinkedIn posts, GitHub repo, domain registration, ARCHITECTURE.md decision records — is worth more than a patent application for a solo builder at this stage. The people who can build what you're building are already building their own version. Post anyway. The timestamp is what matters.

**Your moat is the decision trail, not the idea.**

The idea is not protectable. The specific implementation decisions — sequential over parallel, Perplexity as auditor not panelist, Smart tier advisor pattern across all four providers, intake mirror step before information gathering — are documented, timestamped, and traceable. That's the IP worth protecting.

---

## What's Next

This document will be updated as v2 ships and v3 is designed. The lessons from building with agentic tools — what Claude Code got right, where Cursor surprised me, what the Figma MCP integration actually felt like in practice — will be added to `05-agentic-workflow.md` in real time.

The most valuable part of any journey document is written after the thing is done. Come back then.

---

*Previous: [05 — Building v2 with Agentic Tools](05-agentic-workflow.md)*

---

## Full Journey Index

- [01 — The Origin](01-origin.md)
- [02 — Building v1 in 48 Hours](02-v1-build.md)
- [03 — The Microsoft Gut Punch](03-microsoft-gut-punch.md)
- [04 — Designing v2](04-v2-architecture.md)
- [05 — Building v2 with Agentic Tools](05-agentic-workflow.md) *(live)*
- [06 — Lessons](06-lessons.md) *(this document, growing)*
