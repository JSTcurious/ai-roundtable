"""
backend/router.py

Model selection and tier routing logic for ai-roundtable v2.

Determines which models participate in a session, which tier
each call uses, and the system prompt each model receives for Round 1.

Tiers:
    quick   — executor model only; fast + cheap; brainstorms and gut checks
    smart   — executor streams first, advisor improves silently; default recommended
    deep    — advisor-level model throughout; critical reports and architecture decisions

Constants:
    ROUND1_SYSTEM_PROMPTS   — per-model system prompts for Round 1
    SYNTHESIS_PROMPT        — Claude synthesis prompt template

Functions:
    get_tier_config(tier)              — model IDs and call strategy for a tier
    get_round1_system_prompt(model)    — Round 1 system prompt for a model
    build_synthesis_prompt(output_type) — synthesis prompt with output_type filled in
"""

from typing import Optional

from backend.models.anthropic_client import MODELS as CLAUDE_MODELS
from backend.models.google_client import MODELS as GEMINI_MODELS
from backend.models.openai_client import MODELS as GPT_MODELS
from backend.models.perplexity_client import MODELS as PERPLEXITY_MODELS
from backend.models.grok_client import MODELS as GROK_MODELS


ROUND1_SYSTEM_PROMPTS = {
    # Round 1 order: Gemini → GPT → Claude.
    # Each prompt reflects only what that model can actually see in the transcript
    # at the time it is called. Do not reference models that have not yet spoken.

    "gemini": """You are Gemini, participating in a roundtable \
discussion with GPT and Claude. Your strength is deep reasoning \
and challenging assumptions. Lead with that. You are responding \
first — no other model has spoken yet. Answer directly. \
Do not prefix your response with your name.""",

    "gpt": """You are GPT, participating in a roundtable \
discussion with Gemini, Grok, and Claude. Your strength is structure, \
actionability, and breadth. Lead with that. You have the full \
conversation history including what Gemini said before you. \
Build on it where relevant. Be direct. Do not prefix your \
response with your name.""",

    "grok": """You are Grok, participating in a roundtable \
discussion with Gemini, GPT, and Claude. Your strength is creative \
synthesis, lateral thinking, and contrarian perspectives. Lead with that. \
You have the full conversation history including what Gemini and GPT said \
before you. Challenge assumptions where warranted. Be direct. \
Do not prefix your response with your name.""",

    "claude": """You are Claude, participating in a roundtable \
discussion with Gemini, GPT, and Grok. Your strength is reasoning, \
synthesis, and natural prose. Lead with that. You have the \
full conversation history including what Gemini, GPT, and Grok said \
before you. Build on their responses where relevant — push back \
where you disagree. Be direct. Do not prefix your response with \
your name.""",
}

# v2: synthesis works without a Perplexity audit.
# The {audit_section} placeholder is populated with a v2.1 notice at runtime.
SYNTHESIS_PROMPT = """You are the expert chair of this roundtable. \
You have heard three expert perspectives and have live web research.

Gemini's analysis:
{gemini}

GPT's analysis:
{gpt}

Grok's analysis:
{grok}

Perplexity live research + audit:
{perplexity}

The user's request: {output_type}
Full context: {optimized_prompt}

Now produce ONE definitive, integrated final answer.

Rules:
- Add your own expert perspective — don't just summarize what Gemini, GPT, and Grok said
- Take the strongest insights from each and weave them into a coherent whole
- Where models disagreed, note it in ONE sentence and give your recommendation
- Correct anything Perplexity flagged as outdated
- Incorporate current information from Perplexity's live research
- End with 3 concrete next steps the user can take starting this week
- Write as THE expert giving one definitive answer, not as a moderator summarizing others
- Match output format: {output_type}
- Do NOT use comparison tables
- Do NOT list what each model said separately
"""


# Maps tier names as they may arrive from the frontend or session_config
TIER_ALIASES = {
    "quick":         "quick",
    "smart":         "smart",
    "deep":          "deep_thinking",
    "deep_thinking": "deep_thinking",
}


def get_tier_config(tier: str) -> dict:
    """
    Return the model IDs and calling strategy for a given tier.

    Args:
        tier: "quick" | "smart" | "deep" | "deep_thinking"

    Returns (quick / deep_thinking):
        {
            "mode":       "single",
            "claude":     str,
            "gemini":     str,
            "gpt":        str,
            "perplexity": str,
            "strategy":   str,
        }

    Returns (smart):
        {
            "mode":            "smart",
            "claude_executor": str,
            "claude_advisor":  str,
            "gemini_executor": str,
            "gemini_advisor":  str,
            "gpt_executor":    str,
            "gpt_advisor":     str,
            "perplexity":      str,
            "strategy":        "smart",
        }

    Raises ValueError for unrecognised tier names.
    """
    normalised = TIER_ALIASES.get(tier)
    if normalised is None:
        raise ValueError(
            f"Unknown tier: {tier!r}. Expected 'quick', 'smart', 'deep', or 'deep_thinking'."
        )

    if normalised == "quick":
        return {
            "mode":       "single",
            "claude":     CLAUDE_MODELS["quick"],
            "gemini":     GEMINI_MODELS["quick"],
            "gpt":        GPT_MODELS["quick"],
            "grok":       GROK_MODELS["quick"],
            "perplexity": PERPLEXITY_MODELS["quick"],
            "strategy":   "quick",
        }

    if normalised == "smart":
        return {
            "mode":            "smart",
            "claude_executor": CLAUDE_MODELS["smart"],
            "claude_advisor":  CLAUDE_MODELS["deep"],
            "gemini_executor": GEMINI_MODELS["smart"],
            "gemini_advisor":  GEMINI_MODELS["deep"],
            "gpt_executor":    GPT_MODELS["smart"],
            "gpt_advisor":     GPT_MODELS["deep"],
            "grok_executor":   GROK_MODELS["smart"],
            "grok_advisor":    GROK_MODELS["deep"],
            "perplexity":      PERPLEXITY_MODELS["smart"],
            "strategy":        "smart",
        }

    # deep_thinking
    return {
        "mode":       "single",
        "claude":     CLAUDE_MODELS["deep"],
        "gemini":     GEMINI_MODELS["deep"],
        "gpt":        GPT_MODELS["deep"],
        "grok":       GROK_MODELS["deep"],
        "perplexity": PERPLEXITY_MODELS["deep"],
        "strategy":   "deep_thinking",
    }


def get_round1_system_prompt(model_name: str) -> str:
    """
    Return the Round 1 system prompt for a given model.

    Args:
        model_name: "claude" | "gemini" | "gpt"

    Raises KeyError for unrecognised model names.
    """
    prompt = ROUND1_SYSTEM_PROMPTS.get(model_name.lower())
    if prompt is None:
        raise KeyError(f"No Round 1 system prompt for model: {model_name!r}")
    return prompt


USE_CASE_LIBRARY = {
    "learning_career": [
        {
            "id": "transition_roadmap",
            "title": "Career Transition Roadmap",
            "description": "Engineers moving into a new domain or role type",
            "output": "Month-by-month roadmap with milestones",
            "typical_tier": "deep_thinking",
            "typical_exchanges": "6-8",
            "first_question": "Tell me about your current role and where you want to go — as specifically as you can.",
        },
        {
            "id": "certification_path",
            "title": "Certification Path",
            "description": "Choosing and preparing for a specific certification",
            "output": "Study plan with timeline and resources",
            "typical_tier": "quick",
            "typical_exchanges": "4-6",
            "first_question": "Which certification are you targeting, and what's your timeline?",
        },
        {
            "id": "study_plan",
            "title": "Self-Study Plan",
            "description": "Learning a skill with a hard deadline",
            "output": "Week-by-week study schedule",
            "typical_tier": "quick",
            "typical_exchanges": "4-5",
            "first_question": "What are you trying to learn and when do you need to know it?",
        },
        {
            "id": "portfolio_strategy",
            "title": "Portfolio Building Strategy",
            "description": "Building a public portfolio for a job search",
            "output": "Project list with priorities and execution order",
            "typical_tier": "deep_thinking",
            "typical_exchanges": "5-7",
            "first_question": "What role are you targeting and what do you have in your portfolio today?",
        },
    ],
    "research_decision": [
        {
            "id": "vendor_evaluation",
            "title": "Technology or Vendor Evaluation",
            "description": "Choosing between tools, platforms, or vendors",
            "output": "Comparison report with recommendation",
            "typical_tier": "deep_thinking",
            "typical_exchanges": "5-7",
            "first_question": "What are you evaluating and what does the decision need to achieve?",
        },
        {
            "id": "build_vs_buy",
            "title": "Build vs Buy Analysis",
            "description": "Deciding whether to build internally or buy a solution",
            "output": "Decision record with recommendation",
            "typical_tier": "deep_thinking",
            "typical_exchanges": "6-8",
            "first_question": "What problem are you solving and what options are you weighing?",
        },
        {
            "id": "market_research",
            "title": "Market Landscape Research",
            "description": "Understanding a market, competitors, or trends",
            "output": "Research report with cited sources",
            "typical_tier": "deep_thinking",
            "typical_exchanges": "4-6",
            "first_question": "What market or space are you researching and what do you need to understand about it?",
        },
        {
            "id": "competitive_analysis",
            "title": "Competitive Analysis",
            "description": "Understanding how you compare to competitors",
            "output": "Competitive landscape report",
            "typical_tier": "deep_thinking",
            "typical_exchanges": "5-7",
            "first_question": "What product or service are you analyzing and who are the competitors?",
        },
    ],
    "strategy_planning": [
        {
            "id": "product_roadmap",
            "title": "Product Roadmap",
            "description": "Planning features and priorities for a product",
            "output": "Phased roadmap with rationale",
            "typical_tier": "deep_thinking",
            "typical_exchanges": "6-8",
            "first_question": "Tell me about the product and what you're trying to accomplish with the roadmap.",
        },
        {
            "id": "go_to_market",
            "title": "Go-to-Market Strategy",
            "description": "Planning how to launch or expand a product",
            "output": "GTM plan with channels and timeline",
            "typical_tier": "deep_thinking",
            "typical_exchanges": "6-8",
            "first_question": "What are you launching and who are you trying to reach?",
        },
        {
            "id": "90_day_plan",
            "title": "90-Day Plan",
            "description": "Planning priorities for a new role or project",
            "output": "Month-by-month action plan",
            "typical_tier": "quick",
            "typical_exchanges": "4-6",
            "first_question": "What's the new role or situation, and what does success look like at 90 days?",
        },
        {
            "id": "project_planning",
            "title": "Project Planning",
            "description": "Breaking down a project with constraints",
            "output": "Project plan with phases and milestones",
            "typical_tier": "quick",
            "typical_exchanges": "5-7",
            "first_question": "Describe the project — what needs to happen, by when, and with what constraints?",
        },
    ],
    "technical_build": [
        {
            "id": "architecture_decision",
            "title": "Architecture Decision",
            "description": "Deciding on a technical architecture with tradeoffs",
            "output": "Architecture decision record",
            "typical_tier": "deep_thinking",
            "typical_exchanges": "6-8",
            "first_question": "What are you building and what architectural decision do you need to make?",
        },
        {
            "id": "stack_selection",
            "title": "Stack Selection",
            "description": "Choosing languages, frameworks, and tools",
            "output": "Stack recommendation with rationale",
            "typical_tier": "quick",
            "typical_exchanges": "4-6",
            "first_question": "What are you building and what constraints are you working within?",
        },
        {
            "id": "system_design",
            "title": "System Design Review",
            "description": "Reviewing or designing a system end to end",
            "output": "System design document with recommendations",
            "typical_tier": "deep_thinking",
            "typical_exchanges": "6-8",
            "first_question": "Describe the system you're designing or reviewing — purpose, scale, and current state.",
        },
        {
            "id": "refactor_strategy",
            "title": "Code Refactor Strategy",
            "description": "Planning a refactor or modernization effort",
            "output": "Phased refactor plan with priorities",
            "typical_tier": "quick",
            "typical_exchanges": "5-7",
            "first_question": "What are you refactoring and what's driving the need?",
        },
    ],
}


def get_use_case(use_case_id: str) -> Optional[dict]:
    """
    Look up a single use case card by ID across all families.
    Returns the card dict (including first_question) or None if not found.
    """
    for cards in USE_CASE_LIBRARY.values():
        for card in cards:
            if card["id"] == use_case_id:
                return card
    return None


def build_synthesis_prompt(
    output_type: str,
    gemini: str = "",
    gpt: str = "",
    grok: str = "",
    perplexity: str = "",
    optimized_prompt: str = "",
) -> str:
    """
    Return the Claude synthesis system prompt with all inputs injected.

    Claude does not participate in Round 1 — it synthesises from Gemini,
    GPT, Grok, and Perplexity's live research + audit.

    Args:
        output_type:       e.g. "roadmap", "report", "decision", "plan", "brainstorm"
        gemini:            Gemini's Round 1 response text
        gpt:               GPT's Round 1 response text
        grok:              Grok's Round 1 response text
        perplexity:        Perplexity Phase 2 audit text (includes Phase 1 research)
        optimized_prompt:  the full optimized prompt from intake
    """
    return SYNTHESIS_PROMPT.format(
        output_type=output_type,
        gemini=gemini or "(not available)",
        gpt=gpt or "(not available)",
        grok=grok or "(not available)",
        perplexity=perplexity or "(not available)",
        optimized_prompt=optimized_prompt or "(not available)",
    )
