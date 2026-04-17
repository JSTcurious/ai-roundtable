"""
experiments/synthesizer-eval/prompts.py

Fixed test inputs for synthesizer evaluation.
All candidates receive identical round-1 responses and Perplexity audit.
Do not vary these inputs between candidates — the point is comparability.
"""

# ── Test 1: Factual current data — the failing case ───────────────────────────
# This is the case where Claude currently fails. Perplexity has verified
# live data that contradicts stale round-1 responses.

TEST1_USER_PROMPT = (
    "What are the current API pricing tiers for Claude Opus 4.7, GPT-5, "
    "and Gemini 2.5 Pro as of April 2026?"
)

TEST1_ROUND1 = {
    "Claude": (
        "I cannot provide API pricing for April 2026 — that date is beyond "
        "my knowledge cutoff. Claude Opus 4.7 is not a model I'm aware of. "
        "GPT-5 had not been released in my training data. I recommend "
        "consulting official pricing pages."
    ),
    "Gemini": (
        "These models are speculative and unannounced. Current flagship "
        "pricing (mid-2024): Claude 3 Opus $15/$75 per MTok, GPT-4o $5/$15, "
        "Gemini 1.5 Pro $3.50/$10.50."
    ),
    "GPT": (
        "I don't have specific pricing for these models. Please visit "
        "official vendor websites for current information."
    ),
    "Grok": (
        "Claude Opus 4.7 and GPT-5 are not models I have confirmed "
        "information about. I'd recommend checking official sources."
    ),
}

TEST1_PERPLEXITY = """
## Perplexity Live Research Findings

### Facts Outdated or Incorrect in Round-1 Responses

- Claude Opus 4.7: Released April 16, 2026. Pricing $5 input / $25 output
  per 1M tokens. Model ID: claude-opus-4-7. Claude 3 Opus was retired
  January 5, 2026. The $15/$75 figures from Gemini are from a retired model.
  [Citations: Anthropic API docs, April 2026; OpenRouter provider listing]

- GPT-5: No confirmed commercial release or pricing as of April 2026.
  Most recent OpenAI flagship is GPT-4o at $2.50/$10 per 1M tokens.

- Gemini 2.5 Pro: No confirmed commercial release or pricing as of April 2026.
  Most recent Google flagship is Gemini 2.0 Flash.

### Current Confirmed Pricing (April 2026)

| Model | Input /1M | Output /1M | Status |
|-------|-----------|------------|--------|
| Claude Opus 4.7 | $5.00 | $25.00 | Active (released Apr 16, 2026) |
| Claude Sonnet 4.6 | $3.00 | $15.00 | Active |
| GPT-4o | $2.50 | $10.00 | Active |
| Gemini 2.0 Flash | $0.10 | $0.40 | Active |

Claude Opus 4.7 additional tiers:
- Cache writes (5min): $6.25/MTok
- Cache hits: $0.50/MTok (90% input discount)
- Batch API: $2.50/$12.50/MTok (50% off)
- Context window: 1M tokens
- Max output: 128K tokens
"""

# ── Test 2: Analytical synthesis — the working case ───────────────────────────
# Pure analytical question with model disagreement. No post-cutoff data.
# Tests synthesis quality where Claude is currently strong.

TEST2_USER_PROMPT = (
    "Is RLHF still the dominant alignment technique in 2026, "
    "or has it been superseded?"
)

TEST2_ROUND1 = {
    "Claude": (
        "[LIKELY] RLHF remains conceptually central but PPO-based "
        "implementation has been largely superseded by DPO and variants. "
        "70% of enterprise deployments use DPO or GRPO. Constitutional AI "
        "augments rather than replaces the RLHF philosophy."
    ),
    "Gemini": (
        "[UNCERTAIN] RLHF is foundational but the field is moving toward "
        "AI-assisted feedback. Constitutional AI, process supervision, and "
        "mechanistic interpretability are emerging as complements. "
        "[LIKELY] DPO has become the practical default."
    ),
    "GPT": (
        "[DEFER] I don't have 2026 data. As of my training, RLHF with PPO "
        "was dominant but DPO was gaining adoption rapidly due to lower "
        "compute requirements."
    ),
    "Grok": (
        "RLHF as a philosophy dominates. PPO as an implementation is "
        "declining. DPO is the pragmatic default. The real question is "
        "whether preference-based training at all can solve inner alignment "
        "— probably not, which is why interpretability research matters."
    ),
}

TEST2_PERPLEXITY = """
## Perplexity Live Research Findings

### Current State (April 2026)

- DPO is the de facto default for alignment fine-tuning: 70% of enterprise
  LLM deployments use DPO, KTO, GRPO, or DAPO rather than PPO-based RLHF.
  [arXiv 2026 survey]

- PPO-based RLHF persists only at frontier labs (OpenAI, Anthropic, DeepMind)
  where maximum quality justifies the compute cost.

- Constitutional AI shows 40% better generalization than pure RLHF.
  [Anthropic 2026 research]

- DeepMind 2026: Iterative distillation achieves 92% safety gains with 60%
  less data than traditional RLHF.

- Inner alignment remains unsolved — preference-based methods address outer
  alignment only.

### Practitioner Consensus

Start with DPO. Use KTO for noisy/binary feedback. RLHF/PPO only for
frontier-scale work. Understanding the full pipeline is non-optional.
"""

# ── Test 3: Domain technical — the showcase case ──────────────────────────────
# Energy domain question. Tests terminology correction and whether synthesizer
# correctly propagates Perplexity's correction into output.

TEST3_USER_PROMPT = (
    "What is ISO New England's current capacity accreditation methodology "
    "for offshore wind?"
)

TEST3_ROUND1 = {
    "Claude": (
        "[LIKELY] ISO-NE uses a marginal ELCC approach for offshore wind, "
        "calculating how much each incremental MW reduces capacity shortfall "
        "probability. [UNCERTAIN] Accreditation values likely 15-35% of "
        "nameplate. [DEFER] Check FCA qualification materials for current values."
    ),
    "Gemini": (
        "ISO-NE uses Marginal Reliability Impact (MRI) methodology. "
        "Offshore wind capacity value is dynamic and declines as penetration "
        "increases due to correlated generation patterns."
    ),
    "GPT": (
        "[DEFER] I don't have detailed current information on ISO-NE's "
        "offshore wind accreditation methodology. Check official publications."
    ),
    "Grok": (
        "ISO-NE is transitioning from historical-performance ICAP to "
        "probabilistic accreditation. The key challenge is that offshore "
        "wind projects in New England have correlated output — when one "
        "project is becalmed, they all tend to be."
    ),
}

TEST3_PERPLEXITY = """
## Perplexity Live Research Findings

### Terminology Correction

Gemini used "MRI" (Marginal Reliability Impact) — this is NOT the official
ISO-NE terminology. The correct official terms are:

- **Methodology**: Resource Capacity Accreditation (RCA)
- **Model**: Resource Adequacy Adjustment (RAA)
- **Output metric**: Qualified Marginal Reliability Impact Capacity (QMRIC)

The term "MRI" does not appear in ISO-NE official documentation.

### Current Methodology Details (as of April 2026)

- Offshore wind (>10 MW): Uses DNV synthetic hourly profiles (20+ years)
- Data source: ERA5 reanalysis downscaled via NOAA HRRR 3km model
- Projects <5 years operational: synthetic profiles stitched to historical
- Class-average rMRI used (not project-specific) to protect data privacy
- Offshore wind NOT distinguished from onshore in current methodology

### Implementation Timeline

- Phase 1 (Sept 2024): Resources can challenge tech type/winter capability
- Phase 2 (ongoing): Individual QMRIC calculated for high-need hours
- FCA 19: First auction using RCA (2028-2029 delivery period)

### Stakeholder Issues

NRDC argues methodology undervalues offshore wind vs onshore, and that
gas performance should be adjusted for forced outages in winter stress events.
Latest memo: September 3, 2025 (no changes since October 2025).
"""

# ── Scoring rubric ────────────────────────────────────────────────────────────

SCORING_RUBRIC = """
## Synthesizer Evaluation Rubric

Score each candidate 1-5 on each dimension. Total max: 30 points.

| Dimension | 1 (Poor) | 3 (Adequate) | 5 (Excellent) |
|-----------|----------|--------------|---------------|
| Factual grounding | Refuses Perplexity data or ignores it | Partially incorporates | Leads with Perplexity data, explicitly overrides stale round-1 |
| Attribution | Blends all sources, no attribution | Some attribution | Every claim attributed to its source |
| Contradiction handling | Ignores contradictions | Notes some | Explicitly resolves every contradiction, states which source wins |
| Analytical depth | Pure summary | Some synthesis | Adds expert perspective beyond round-1 content |
| Tag adoption | No tags | Some tags | [VERIFIED]/[LIKELY]/[UNCERTAIN]/[DEFER] used correctly inline |
| Actionability | No next steps | Generic advice | 3 concrete, specific next steps |

## Critical Failure Conditions (automatic 0 on factual grounding)

- Calls Perplexity's live-cited data "fabricated"
- Refuses to incorporate post-cutoff data when Perplexity has verified it
- Presents a retired/deprecated model's pricing as current after Perplexity
  has stated the retirement explicitly
"""
