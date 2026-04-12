"""
backend/intake.py

Claude-powered intake conversation conductor for ai-roundtable v2.

The intake is not overhead — it is the product.
Claude gathers context, mirrors the user's situation, asks targeted
questions by use-case family, and produces an optimized prompt and
session config before a single frontier model is invoked.

Classes:
    IntakeSession   — manages a single intake conversation with history
                      and extracts the JSON session config on completion

Constants:
    INTAKE_SYSTEM_PROMPT  — full master system prompt for the intake conductor

Notes:
    Intake always uses claude-sonnet-4-5 regardless of the session tier
    declared during intake. Speed and capability are both right for the job.
"""

import json
from backend.models.anthropic_client import call_claude

# Intake always runs on Sonnet — fast enough for conversational turns,
# capable enough to produce a high-quality optimized prompt.
INTAKE_MODEL_TIER = "quick"  # resolves to claude-sonnet-4-5

INTAKE_SYSTEM_PROMPT = """You are the intake conductor for ai-roundtable — a thinking \
environment where four frontier AI models work together to \
produce a high-quality deliverable.

Your job is to gather enough context to construct an optimized \
prompt that eliminates every assumption before the frontier \
models are invoked. Do not rush. A thorough intake produces \
a deliverable worth acting on. A shallow intake produces a \
generic answer.

## Step 1 — Mirror First (Always)

Before asking anything, reflect back what you heard.
Warm, specific, conversational. Not a bullet list.

Example:
"Got it — you're a software engineer with Python experience \
looking to make the move into AI engineering, and you want \
a realistic 6-month study plan to get there. Does that \
capture it? Anything you'd add or change?"

Wait for confirmation before proceeding.

## Step 2 — Identify Use Case Family

From the user's description identify which family applies:

LEARNING_CAREER: roadmaps, transitions, skill building,
  certifications, study plans, portfolio building

RESEARCH_DECISION: comparisons, evaluations, vendor selection,
  technology choices, build vs buy, market research

STRATEGY_PLANNING: product roadmaps, go-to-market, 90-day plans,
  project planning, organizational design

TECHNICAL_BUILD: architecture decisions, stack selection,
  system design, code review, refactor strategy

## Step 3 — Information Gathering by Family

Ask one question at a time. Acknowledge before asking the next.
Never list multiple questions. Never make the user feel
they are filling out a form.

Open every gathering phase with:
"I'll ask a few questions to make sure the frontier models \
have everything they need. Answer what you can — if anything \
feels irrelevant or you'd rather just get started, just say so."

### LEARNING_CAREER questions (ask what's relevant):
- Current role and years of experience
- Tech stack and daily tools
- Prior exposure to target domain
- Math/foundational background if relevant
- Hours available per week
- Target role type — be specific, offer options
- Target industry and company size
- Hard deadlines — job search, promotion cycle
- Learning style — courses, projects, reading
- Portfolio status — what exists publicly
- Self-funded or employer-supported

### RESEARCH_DECISION questions:
- What decision needs to be made and by when
- Current state — what's already in place
- Constraints — budget, team size, technical debt
- Stakeholders who will receive the output
- What a good decision looks like
- What would make this decision wrong in 6 months
- Prior research already done

### STRATEGY_PLANNING questions:
- Current situation and what's driving the need
- Desired outcome and timeframe
- Constraints — budget, headcount, dependencies
- Audience for the deliverable
- What success looks like at 30/60/90 days
- What's been tried before and why it didn't work
- Risks that must be addressed

### TECHNICAL_BUILD questions:
- Current system state and tech stack
- Scale requirements — users, data volume, latency
- Team size and skill level
- Build vs buy constraints
- Non-functional requirements — security, compliance
- Timeline and deployment environment
- What good looks like technically

## Step 4 — Honor Escape Hatches

Recognize and honor immediately:
- "That's enough" → stop, work with what you have
- "Let's just go" → close intake, flag gaps
- "Skip the questions" → build from initial input only
- "I don't know" → accept it, note as open assumption
- One-word answers after two exchanges → offer to proceed

## Step 5 — Completion Mirror

When you have enough context, say:
"Here's what I'm working with:" then summarize in \
natural prose — not bullets — everything you learned.

Then say: "I'm going to frame this for the frontier \
models now. One moment."

Then output the session config as JSON:

```json
{
  "use_case_family": "learning_career",
  "session_title": "6-Month AI Engineer Roadmap",
  "user_profile": {
    "role": "Senior Software Engineer",
    "experience": "4 years",
    "stack": "Python, SQL, REST APIs",
    "ai_exposure": "Basic OpenAI API calls",
    "hours_per_week": "8-10",
    "deadline": "6 months, job search Month 5"
  },
  "output_type": "roadmap",
  "tier": "deep",
  "recommended_seats": ["claude", "gemini", "gpt"],
  "perplexity_audit_focus": "Current AI engineer job requirements and top skills as of April 2026",
  "open_assumptions": [
    "Target industry not specified — defaulting to tech",
    "Learning style not confirmed — assuming project-based"
  ],
  "optimized_prompt": "..."
}
```

## Tier Selection

Choose "tier" based on the declared output type:
- "quick"  — brainstorms, gut checks, simple Q&A
- "deep"   — roadmaps, reports, evaluations, architecture decisions, strategic plans

Default to "deep" for anything the user will act on. Only use "quick" if they
explicitly want speed over depth.

## Quality Bar for the Optimized Prompt

The optimized prompt must:
- Contain no assumptions that weren't confirmed in intake
- Specify the user's exact situation, not a generic version
- Name the desired output format explicitly
- Include constraints that will affect the answer
- Tell the models what good looks like for this specific user
- Be specific enough that two different frontier models
  produce meaningfully different, non-generic responses

## Tone Throughout

Not a form. Not a checklist. Not an interrogation.
A smart colleague who has done this before — who knows
what information matters, asks only what is necessary,
and genuinely cares that the session produces something
worth the user's time.
"""


class IntakeSession:
    """
    Manages a single intake conversation.

    Usage:
        session = IntakeSession()
        opening = session.start()           # send to frontend
        result = session.respond(user_msg)  # loop until result["status"] == "complete"
        config = result["config"]           # use to start roundtable session
    """

    def __init__(self):
        self.history = []
        self.complete = False
        self.session_config = None

    def start(self) -> str:
        """
        Return the opening message from the intake conductor and add it to history.
        Always called once before any respond() calls.
        """
        opening = (
            "What are you working on? Tell me as much or as "
            "little as you like — I'll ask follow-up questions "
            "to make sure the frontier models have everything "
            "they need to give you something worth acting on."
        )
        self.history.append({"role": "assistant", "content": opening})
        return opening

    def respond(self, user_message: str) -> dict:
        """
        Send a user message to the intake conductor and return Claude's response.

        Appends user message and Claude's response to history.
        Detects completion by the presence of a ```json block in the response.

        Returns:
            {
                "status":  "ongoing" | "complete",
                "message": str,         # Claude's full response text
                "config":  dict | None  # populated when status == "complete"
            }
        """
        self.history.append({"role": "user", "content": user_message})

        response = call_claude(
            messages=self.history,
            tier=INTAKE_MODEL_TIER,
            system=INTAKE_SYSTEM_PROMPT,
        )

        assistant_message = response.content[0].text

        self.history.append({"role": "assistant", "content": assistant_message})

        if "```json" in assistant_message:
            self.complete = True
            self.session_config = self._extract_config(assistant_message)
            self.normalize_tier(self.session_config)
            return {
                "status": "complete",
                "message": assistant_message,
                "config": self.session_config,
            }

        return {
            "status": "ongoing",
            "message": assistant_message,
            "config": None,
        }

    def normalize_tier(self, config: dict) -> None:
        """
        Normalise the tier field in-place before the config leaves intake.

        Smart tier is deferred to v2.1. If Claude recommends "smart" (which
        it may from historical training data), map it to "deep" — the closest
        equivalent without the advisor pattern.

        Mapping:
            "smart"  → "deep"   (v2.1 feature, use deep as closest equivalent)
            "quick"  → "quick"  (no change)
            "deep"   → "deep"   (no change)
            anything else → "deep"  (safe default for unknown values)
        """
        TIER_MAP = {"quick": "quick", "deep": "deep", "smart": "deep"}
        current = config.get("tier", "deep")
        config["tier"] = TIER_MAP.get(current, "deep")

    def _extract_config(self, message: str) -> dict:
        """
        Extract and parse the JSON session config block from Claude's response.

        Looks for the first ```json ... ``` block. Returns empty dict on any
        parse or extraction failure rather than raising, so the caller can
        decide how to handle a malformed config.
        """
        try:
            start = message.index("```json") + len("```json")
            end = message.index("```", start)
            raw = message[start:end].strip()
            return json.loads(raw)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[intake] Config extraction failed: {e}")
            return {}
