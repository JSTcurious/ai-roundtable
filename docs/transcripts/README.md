# Test Transcripts

Real-world test transcripts demonstrating guardrail behavior in ai-roundtable.

Each transcript captures a specific test question, the round-1 responses, the
fact-check output (Perplexity), and the synthesis observation — along with an
analysis of what the guardrails caught and what they missed.

These are used for:
- Validating guardrail behavior against real model outputs
- Identifying gaps in tag adoption or synthesis skepticism
- Providing concrete examples for content (LinkedIn, agipilled.ai)
- Serving as regression benchmarks if guardrails are revised

## Index

- [001 — Claude Opus 4.7 context window (fabrication caught at synthesis)](./001-claude-opus-4-7-fabrication.md)
- [002 — Q1 2026 AI model releases (synthesis failure — CASCADING_GUARD misapplied to Perplexity)](./002-q1-2026-ai-releases.md)
- [009 — DPO vs PPO comparative analysis (intake happy path — no clarification, tier=smart)](./009-dpo-ppo-comparative-analysis.md)
- [010 — AI engineering project plan (clarifying turn — ambiguous prompt resolved in one exchange)](./010-ai-engineering-project-plan.md)
- [011 — ISO-NE installed capacity (tier=quick, SYNTHESIS_TRUST_HIERARCHY regression pass)](./011-isone-installed-capacity.md)
