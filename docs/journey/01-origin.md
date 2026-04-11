# 01 — The Origin

*How an idea that sat dormant for 6 months finally became a product*

---

## The Pain I Was Living With

I use AI every day. Multiple models, depending on what I need.

Claude for reasoning and writing. Gemini when I need deep research or something multimodal. ChatGPT when I want a generalist take or need to work with tools. Perplexity when I need something current and cited.

The problem is I was the one holding all of it together.

Every time I wanted a second opinion from a different model, I opened a new tab. Copied my question. Pasted it. Read both responses. Manually figured out where they agreed, where they diverged, and what that meant for my decision. Then did it again for the next follow-up.

The context lived in my head, not in the conversation. I was the integration layer between models that had no idea the others existed.

I got tired of being the glue.

---

## The Idea That Wouldn't Leave

Sometime in mid-2025 I started turning an idea over in my head. I was working through it in ChatGPT of all places — which in hindsight is exactly the kind of irony that makes sense only after the fact.

The framing I was using then was management thinking frameworks. I'd been reading about how human groups make better decisions when participants are assigned distinct cognitive roles — not just titles, but actual thinking modes. Devil's advocate. Optimist. Root cause analyst. The kind of structured cognitive diversity that prevents groupthink.

I started wondering what would happen if you assigned AI models those roles instead of functions.

Not "search agent" and "code agent." Something deeper — a model whose job is to find what's wrong with every idea. Another whose job is to find what's right. A third that ignores opinions entirely and just retrieves facts. An orchestrator that decides who speaks next.

I was thinking about Six Thinking Hats, Five Whys, First Principles — frameworks designed for human collaboration, mapped onto AI agents. I called it FrameworkThinking.

On December 16, 2025, I registered frameworkthinking.ai.

Then I started writing a research paper outline instead of building anything.

---

## Why It Stayed an Idea

I told myself I was being thorough. The academic route felt right — if this was a genuinely novel idea, it deserved a proper paper. Peer review. Citations. The works.

What I was actually doing was avoiding the build.

Writing a paper outline is safe. You can spend months on it and never ship anything that can be judged. I had ideas buried across ChatGPT project threads, Anthropic conversations, Gemini sessions — scattered across the same platforms I was complaining about, which in hindsight says everything.

The irony wasn't lost on me later: I was experiencing the exact pain I wanted to solve, while using that pain as research material instead of product fuel.

---

## The Gut Punch

In late March 2026, Microsoft announced two new features for Copilot Researcher — Critique and Council.

Critique: GPT drafts, Claude reviews, final report reaches the user only after that review. One model checks the other's work.

Council: GPT and Claude run simultaneously, a third judge model reads both outputs and surfaces where they agreed, diverged, and what each caught that the other missed.

On the DRACO benchmark — 100 complex research tasks — the combined system outscored every single model by nearly 14%.

I felt gutted.

Not because Microsoft had stolen my idea. They hadn't — their implementation is a pipeline, mine was always meant to be a room. But because they had shipped something, and I was still writing an outline.

The idea wasn't new to me. I'd been sitting on the core premise for 6 months. The difference between me and Microsoft wasn't the idea. It was the shipping.

A few days later GitHub shipped Rubber Duck in Copilot CLI — a second model from a different AI family that reviews the primary agent's work before it executes. Same premise. Same week.

The market was validating the concept in real time. I was watching it happen from the sidelines.

---

## The Shift

I stopped writing the paper outline.

I opened a new project and started designing the actual product. Not FrameworkThinking as an academic framework. Not a research program. A group chat where your contacts are AI models.

The product insight that finally unlocked it was simple: Microsoft built a pipeline. I wanted to build a room.

In a pipeline, the sequence is fixed. GPT drafts, Claude reviews. The human receives the output. The models collaborate but the human is a passenger.

In a room, everyone is present. Everyone hears everything. You decide who speaks. You can redirect, challenge, bring someone new in, ask for consolidation. You stay in the chair.

That distinction — human in the chair, not a model — became the product principle everything else follows from.

---

## What I Posted and Why

Before writing a line of code I posted on LinkedIn. Two posts, two days apart.

Post 1 was the pain point — the tab switching, the copy-pasting, the manual consolidation. Post 2 was the market gap — why every existing multi-AI tool is a comparison tool, not a conversation.

I wasn't trying to build an audience. I was planting a timestamp.

The LinkedIn posts are public, indexed, and dated. They establish when I conceived this and what I was thinking at the time. If someone builds something similar next month and claims the idea, I have a paper trail.

Ideas without timestamps are just ideas. Timestamps make them prior art.

---

## What Happened Next

Within 48 hours of the first post, v1 was live on GitHub.

A group chat where your participants are Claude, Gemini, and GPT-4o. Shared persistent transcript. @mention routing. Dark-themed Streamlit UI. Built on GitHub Models free tier so anyone with a GitHub account could run it without billing.

It wasn't polished. But it was real and it was shipped.

A GTM strategist I'd just connected with on LinkedIn read the posts, went through the repo, and came back with this:

> *"Everyone's building pipelines. You're building a room where the conversation compounds. That's a fundamentally different product philosophy."*

> *"Your wedge isn't developers. It's the decision-maker mid-thought. The consultant stress-testing a strategy. The PM who needs three perspectives before a product call."*

She named my buyer more precisely than I had. I was describing the tool. She described who needed it.

That feedback shaped everything about v2.

---

## What I Learned From the Origin

**Shipping is the research.** Six months of thinking produced a paper outline and a domain name. Forty-eight hours of building produced a working product, public prior art, and external validation from someone with real GTM experience. The build taught me more about the product than the outline ever did.

**The pain you live with is the product.** I was experiencing the exact problem I wanted to solve, every day, across the same platforms I was planning to connect. I didn't need user research. I needed to stop treating my own frustration as background noise and start treating it as a product brief.

**Your differentiation isn't the idea. It's the decision trail.** Microsoft shipped Critique. GitHub shipped Rubber Duck. I shipped ai-roundtable. Three products, same premise, genuinely different implementations. What makes mine distinct isn't that I thought of it first — it's that I can show exactly what I rejected and why. Sequential over parallel. Human in the chair over model orchestration. Room over pipeline. Those decisions are documented. That's the portfolio.

---

*Next: [02 — Building v1 in 48 Hours](02-v1-build.md)*
