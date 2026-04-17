"""
experiments/intake_eval/prompts.py

Fixed test inputs for intake model evaluation.
All candidates receive identical prompts and are scored against
the same assertions. Do not vary these inputs between candidates.

Tests cover:
    Test 1 — Simple one-shot: clear research question, no clarification needed
    Test 2 — Vague prompt: clarification required
    Test 3 — Proper noun preservation: user-provided model names must survive
    Test 4a — Tier assignment quick: factual lookup
    Test 4b — Tier assignment deep: strategic decision with complexity
    Test 5 — Two-turn: clarification then proper noun preservation in final prompt
    Test 6 — Consistency: same prompt, 3 runs, tier must be stable
"""

# ── Shared intake system prompt ───────────────────────────────────────────────
# Identical to backend/models/google_client.py — GEMINI_INTAKE_SYSTEM.
# Copied here so intake_eval is self-contained (no backend imports required).

INTAKE_SYSTEM_PROMPT = """
You are an intake analyst for an AI research roundtable. Your job is to
analyze a user's prompt and make two decisions:

1. CLARIFICATION: Does the prompt have enough context to produce a
   high-quality research session?

   - If the user's intent is ambiguous or a critical piece of context is
     missing, set needs_clarification to true and provide ONE focused
     clarifying question. Do not ask multiple questions.
   - If the prompt is clear enough to proceed, set needs_clarification
     to false and optimize the prompt directly.

2. PROPER NOUN PRESERVATION (critical rule):

   When the user provides specific proper nouns — model names, product
   names, version numbers, company names, or any named entity — treat
   them as correct and authoritative. Never substitute your own examples
   or alternatives.

   WRONG: User says "Claude Opus 4.7" → you ask "do you mean Claude 3 Opus?"
   RIGHT: User says "Claude Opus 4.7" → you use "Claude Opus 4.7" exactly

   WRONG: User says "GPT-5" → your clarifying question lists "GPT-4" as
          an example of what they might mean
   RIGHT: User says "GPT-5" → you use "GPT-5" exactly in all outputs

   If you are uncertain whether a named entity exists, do NOT ask the user
   to confirm using your own alternatives. Instead, ask about their INTENT
   or SCOPE only — never suggest replacement names.

3. TIER ASSIGNMENT: What research depth does this prompt require?

   - quick : factual lookups, simple comparisons, gut checks.
             Single-dimension questions with known answers.
   - smart : analysis, recommendations, technical evaluations.
             Requires weighing tradeoffs or synthesizing multiple sources.
   - deep  : architecture decisions, strategic plans, critical reports.
             High stakes, significant ambiguity, or complex dependencies.

   Assign tier based on complexity and stakes — not prompt length.
   A short prompt can require deep research.

Always return valid JSON matching the schema exactly. No prose outside the
JSON object.

Required JSON schema:
{
  "needs_clarification": bool,
  "clarifying_question": string or null,
  "optimized_prompt": string,
  "tier": "quick" | "smart" | "deep",
  "output_type": string,
  "reasoning": string
}
"""

# ── Test definitions ──────────────────────────────────────────────────────────

INTAKE_TESTS = [
    {
        "id":   "test1-simple",
        "name": "Simple Research Question",
        "description": (
            "Clear, well-scoped research question. Should proceed without "
            "clarification and assign smart tier."
        ),
        "prompt": (
            "What are the main tradeoffs between PostgreSQL and MongoDB "
            "for a mid-sized SaaS product with 100k users and a small "
            "engineering team?"
        ),
        "turn2_input": None,  # single-turn test
        "assertions": [
            {
                "name": "needs_clarification_false",
                "field": "needs_clarification",
                "expected": False,
                "check": "equals",
            },
            {
                "name": "tier_smart",
                "field": "tier",
                "expected": "smart",
                "check": "equals",
            },
            {
                "name": "optimized_prompt_nonempty",
                "field": "optimized_prompt",
                "expected": "",
                "check": "nonempty",
            },
        ],
    },
    {
        "id":   "test2-vague",
        "name": "Vague Prompt (clarification required)",
        "description": (
            "Underspecified prompt — missing scope, domain, and context. "
            "Should trigger clarification."
        ),
        "prompt": "How do I improve performance?",
        "turn2_input": None,
        "assertions": [
            {
                "name": "needs_clarification_true",
                "field": "needs_clarification",
                "expected": True,
                "check": "equals",
            },
            {
                "name": "clarifying_question_present",
                "field": "clarifying_question",
                "expected": "",
                "check": "nonempty",
            },
            {
                "name": "clarifying_question_single",
                "field": "clarifying_question",
                "expected": "?",
                "check": "single_question",
                "note": "Must ask exactly one question (one '?' or at most two closely related)",
            },
        ],
    },
    {
        "id":   "test3-proper-nouns",
        "name": "Proper Noun Preservation",
        "description": (
            "User provides specific model names that may not exist in the "
            "model's training data. They must survive into the optimized_prompt "
            "unchanged."
        ),
        "prompt": (
            "Compare Claude Opus 4.7 and GPT-5 for enterprise coding assistant "
            "use cases. Which handles multi-file refactoring better?"
        ),
        "turn2_input": None,
        "assertions": [
            {
                "name": "needs_clarification_false",
                "field": "needs_clarification",
                "expected": False,
                "check": "equals",
            },
            {
                "name": "preserves_claude_opus_47",
                "field": "optimized_prompt",
                "expected": "Claude Opus 4.7",
                "check": "contains",
            },
            {
                "name": "preserves_gpt5",
                "field": "optimized_prompt",
                "expected": "GPT-5",
                "check": "contains",
            },
            {
                "name": "no_substitution_gpt4",
                "field": "optimized_prompt",
                "expected": "GPT-4",
                "check": "not_contains",
                "note": "Must not substitute GPT-4 for GPT-5",
            },
        ],
    },
    {
        "id":   "test4a-tier-quick",
        "name": "Tier Assignment — Quick",
        "description": (
            "Single-dimension factual lookup. Should assign quick tier."
        ),
        "prompt": (
            "What is the current context window size for Gemini 2.5 Pro?"
        ),
        "turn2_input": None,
        "assertions": [
            {
                "name": "tier_quick",
                "field": "tier",
                "expected": "quick",
                "check": "equals",
            },
        ],
    },
    {
        "id":   "test4b-tier-deep",
        "name": "Tier Assignment — Deep",
        "description": (
            "High-stakes architecture decision with complexity and time pressure. "
            "Should assign deep tier."
        ),
        "prompt": (
            "I need a comprehensive architecture decision record for migrating "
            "our monolith to microservices. We have 200k daily users, a team of "
            "15 engineers, 4 years of technical debt, and a board presentation "
            "in 6 weeks. The decision affects our next 3 years of infrastructure."
        ),
        "turn2_input": None,
        "assertions": [
            {
                "name": "tier_deep",
                "field": "tier",
                "expected": "deep",
                "check": "equals",
            },
        ],
    },
    {
        "id":   "test5-two-turn",
        "name": "Two-Turn: Proper Noun Preservation After Clarification",
        "description": (
            "Vague prompt triggers clarification. After user answers, the "
            "optimized_prompt must preserve the original proper noun 'Claude "
            "Opus 4.7' from the initial prompt."
        ),
        "prompt": (
            "Help me evaluate Anthropic's Claude Opus 4.7 for our product. "
            "We're not sure what use case fits best."
        ),
        "turn2_input": (
            "We're building a coding assistant for mid-market software teams, "
            "about 50 developers, writing mostly Python and TypeScript."
        ),
        "assertions": [
            # Turn 0 assertions
            {
                "name": "t0_needs_clarification_true",
                "field": "needs_clarification",
                "expected": True,
                "check": "equals",
                "turn": 0,
            },
            # Turn 1 assertions (applied to turn2_result)
            {
                "name": "t1_needs_clarification_false",
                "field": "needs_clarification",
                "expected": False,
                "check": "equals",
                "turn": 1,
            },
            {
                "name": "t1_preserves_claude_opus_47",
                "field": "optimized_prompt",
                "expected": "Claude Opus 4.7",
                "check": "contains",
                "turn": 1,
            },
        ],
    },
    {
        "id":   "test6-consistency",
        "name": "Tier Consistency (run 3x)",
        "description": (
            "Run the same borderline prompt three times. Tier assignment "
            "must be stable — same value on all three runs."
        ),
        "prompt": (
            "We're deciding whether to build our own RAG pipeline or buy a "
            "vendor solution. Budget is $50k/year, team of 5 engineers, "
            "need to go live in 3 months."
        ),
        "turn2_input": None,
        "runs": 3,
        "assertions": [
            {
                "name": "tier_stable",
                "field": "tier",
                "expected": None,   # filled after first run
                "check": "consistent",
                "note": "All 3 runs must return same tier",
            },
        ],
    },
]
