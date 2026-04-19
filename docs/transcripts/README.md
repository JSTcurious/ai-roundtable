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

## What These Transcripts Document

This directory records real session outputs from ai-roundtable as of April 2026.
Sessions 001-011 cover the first two weeks of production testing, spanning the
Gemini Flash intake rewrite (transcripts 009-011) and earlier direct-question sessions
that established the baseline for guardrail behavior. Session 012 is the first
validation transcript for the four-model round-1 architecture (Claude added as a
research seat) and the removal of the observation gate. Sessions 013-017 (April 18-19
2026) validate the smart/deep tier split, the WebSocket reconnect fix, and the
always-smart intake lock — including the first deep-tier run with a claim-by-claim
Perplexity audit.

Recurring patterns documented across the suite:
- **Tag adoption**: 0% in sessions 001-003, first adoption in session 005 (offshore wind RCA),
  extensive in sessions 006 and 008 (RLHF)
- **Synthesis trust hierarchy failures**: sessions 003 and 007 document cases where synthesis
  ignored Perplexity's live-web data in favor of its own stale training data
- **CASCADING_GUARD misapplication**: session 002 documents the specific case where synthesis
  applied epistemic skepticism to Perplexity's grounded output (wrong direction)
- **Fabrication caught**: sessions 001 and 002 document fabricated model names/specs caught
  by the synthesis and fact-check layers
- **Intake rewrite validation**: sessions 009-011 document the first real-world tests of the
  Gemini Flash intake, confirming correct clarification behavior, tier selection, and prompt
  optimization
- **Four-model round-1 validation**: session 012 is the first test of the four-model round-1
  architecture; Claude was the sole substantive contributor (Gemini 503, GPT deferred, Grok
  absent) — first use of all four confidence tags in a single round-1 response

## Index

- [001 — Claude Opus 4.7 context window (fabrication caught at synthesis)](./001-claude-opus-4-7-fabrication.md)
- [002 — Q1 2026 AI model releases (synthesis failure — CASCADING_GUARD misapplied to Perplexity)](./002-q1-2026-ai-releases-synthesis-failure.md)
- [003 — API pricing tiers (synthesis trust hierarchy failure — stale Claude pricing despite Perplexity data)](./003-api-pricing-tiers.md)
- [004 — Transformer architecture dominance in 2026 (strong synthesis — GPT first tag adoption observed)](./004-transformer-architecture.md)
- [005 — ISO-NE offshore wind RCA (first systematic tag adoption — Perplexity caught MRI→RCA terminology error)](./005-isone-offshore-wind-rca.md)
- [006 — Claude Opus 4.7 quick tier (regression pass vs. 001 — no fabrication, tag adoption improved)](./006-opus-4-7-quick-tier.md)
- [007 — Frontier model pricing (strongest synthesis trust hierarchy failure — synthesis refused Perplexity's verified data)](./007-frontier-pricing-synthesis-failure.md)
- [008 — RLHF alignment techniques (highest tag adoption in suite — synthesis trust hierarchy worked)](./008-rlhf-alignment-techniques.md)
- [009 — DPO vs PPO comparative analysis (intake happy path — no clarification, tier=smart)](./009-dpo-ppo-comparative-analysis.md)
- [010 — AI engineering project plan (clarifying turn — ambiguous prompt resolved in one exchange)](./010-ai-engineering-project-plan.md)
- [011 — ISO-NE installed capacity (tier=quick, SYNTHESIS_TRUST_HIERARCHY regression pass)](./011-isone-installed-capacity.md)
- [012 — ISO-NE offshore wind four-model round-1 validation (Claude sole contributor — all four tags used, observation gate removed)](./012-isone-offshore-wind-four-model-round1.md)
- [013-alt — ISO-NE offshore wind four-model round-1 (stray export, same prompt as 012 — alternate run)](./013-isone-offshore-wind-four-model-round1-alt.md)
- [013 — ISO-NE offshore wind smart tier smoke test (WebSocket fix confirmed working, Perplexity returned ISO-NE content correctly · smart · Apr 18 2026)](./013-isone-offshore-wind-smart-tier-smoke-test.md)
- [014 — ISO-NE offshore wind deep tier validation (comprehensive claim-by-claim audit — Gemini's FERC approval fabrication caught by synthesis · deep · Apr 19 2026)](./014-isone-offshore-wind-deep-tier-validation.md)
- [015 — MCP and agentic workflows 2026 (Perplexity confirmed 97M downloads, Linux Foundation governance shift Dec 2025, four-protocol A2A stack · smart · Apr 19 2026)](./015-mcp-agentic-workflows-2026.md)
- [016 — Open source vs private portfolio for frontier AI roles (Perplexity flagged "frontier AI companies" term confusion — FDE vs AI PE roles, deployment skills over visibility · smart · Apr 19 2026)](./016-open-source-vs-private-portfolio.md)
- [017 — AI engineering skills for data engineer transition (Perplexity surfaced AI fluency as hiring dividing line, pipeline commoditization finding · smart · Apr 19 2026)](./017-ai-engineering-skills-data-engineer-transition.md)
