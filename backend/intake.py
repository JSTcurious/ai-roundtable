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
import re
from typing import Any, List, Optional, Tuple

from backend.models.anthropic_client import call_claude

# Unicode bidi overrides, directional formatting, and other invisible control characters
# that Claude occasionally embeds and that corrupt displayed text.
# Ranges covered:
#   U+200B–U+200F  zero-width/directional marks
#   U+202A–U+202E  directional embeddings and overrides
#   U+2066–U+2069  directional isolates
#   U+061C         Arabic letter mark
#   U+FEFF         BOM / zero-width no-break space
_BIDI_CONTROL_RE = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff]"
)


def sanitize_text(text: str) -> str:
    """Strip Unicode bidi overrides and invisible control characters from a string."""
    if not isinstance(text, str):
        return text
    return _BIDI_CONTROL_RE.sub("", text)


def sanitize_config(obj: Any) -> Any:
    """
    Recursively sanitize all string values in a config dict/list.
    Returns the same structure with bidi characters removed from every string.
    """
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, dict):
        return {k: sanitize_config(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_config(item) for item in obj]
    return obj


# Plain-text suffix on every gathering turn (parsed server-side, stripped from display).
INTAKE_OPTIONS_MARKER = "INTAKE_OPTIONS:"

# Legacy fenced metadata (still parsed if present).
INTAKE_UI_FENCE = "```intake-ui"

# Returned with POST /api/intake/start alongside the static opening line.
OPENING_SUGGESTED_OPTIONS: List[str] = [
    "Career, learning, or a job transition",
    "A research, product, or technical decision",
    "Strategy, planning, or a project kickoff",
    "I'll describe it in my own words below",
]

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

**Important:** Output plain ASCII/UTF-8 text only. Do not use any Unicode \
directional formatting characters, bidi overrides, or special Unicode control \
characters in your responses.

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

## Intake Options — suggested answer chips (every question turn)

At the end of every turn where you ask a question or offer a mirror \
**until** you emit the final session config, append **exactly one** line \
in this exact format:

INTAKE_OPTIONS: ["option A", "option B", "option C", "option D"]

Rules:
- The line must start with exactly `INTAKE_OPTIONS:` then a JSON array (space after colon is optional).
- Provide **3 or 4** options when possible (minimum **2**). Never skip this line.
- Each option must be a **concrete answer** a user could tap to respond to \
  **that exact question** — job titles, time ranges, tools, yes/no, etc.
- Derive labels from the topic already in the thread. \
  Never use generic menu phrases that could apply to any chat. Forbidden \
  examples (do not output these or anything similar): \
  "Provide context", "Get recommendations", "Compare roles", "See next steps", \
  "Tell me more", "Continue", "Explore options", "Learn more".
- Do **not** repeat the prose question as an option; options are **answers**, not echoes.
- On the **final** turn (when you output the session config in ```json), \
  do **not** include an INTAKE_OPTIONS line.

Good examples (wording must fit the actual question — these are patterns only):

- Asking about current role:
  INTAKE_OPTIONS: ["Software Engineer", "Data Engineer", "Product Manager", "Something else"]

- Asking about hours per week:
  INTAKE_OPTIONS: ["5-10 hrs/week", "10-15 hrs/week", "15-20 hrs/week", "20+ hrs/week"]

- Asking about target role:
  INTAKE_OPTIONS: ["AI Application Engineer", "ML Engineer", "MLOps Engineer", "Not sure yet"]

- After a mirror of a career transition:
  INTAKE_OPTIONS: ["Yes, that's right", "Mostly — a few details to add", "Not quite — I'll clarify"]

- Asking about timeline:
  INTAKE_OPTIONS: ["Within 3 months", "3–6 months", "6–12 months", "No fixed deadline"]

## Tone Throughout

Not a form. Not a checklist. Not an interrogation.
A smart colleague who has done this before — who knows
what information matters, asks only what is necessary,
and genuinely cares that the session produces something
worth the user's time.
"""


def split_intake_options_block(message: str) -> Tuple[str, Optional[List[str]]]:
    """
    Remove the last ``INTAKE_OPTIONS: [...]`` suffix and return display text plus
    2–4 option strings, or (message, None) if absent or invalid.
    """
    if INTAKE_OPTIONS_MARKER not in message:
        return message, None
    idx = message.rfind(INTAKE_OPTIONS_MARKER)
    prefix = message[:idx].rstrip()
    suffix = message[idx + len(INTAKE_OPTIONS_MARKER) :].strip()
    try:
        if not suffix.startswith("["):
            return message, None
        depth = 0
        end_i = -1
        for i, ch in enumerate(suffix):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end_i = i + 1
                    break
        if end_i < 0:
            return message, None
        parsed = json.loads(suffix[:end_i])
        if not isinstance(parsed, list):
            return message, None
        cleaned: List[str] = []
        for x in parsed:
            s = str(x).strip()
            if s:
                cleaned.append(s)
        cleaned = cleaned[:4]
        if len(cleaned) < 2:
            return message, None
        return prefix, cleaned
    except (json.JSONDecodeError, ValueError):
        return message, None


def extract_display_and_suggestions(raw: str) -> Tuple[str, Optional[List[str]]]:
    """
    Strip INTAKE_OPTIONS (preferred) and/or legacy ```intake-ui``` block; return
    display text and merged suggested options (2–4 items) or None.
    """
    d, opts_io = split_intake_options_block(raw)
    d2, opts_ui = split_intake_ui_block(d)
    opts = opts_io if opts_io is not None else opts_ui
    return d2, opts


def _merge_without_intake_ui(message: str, fence_idx: int, closing_idx: int) -> str:
    """Drop the ```intake-ui ... ``` segment; trim surrounding whitespace."""
    before = message[:fence_idx].rstrip()
    after = message[closing_idx + 3 :].lstrip()
    if before and after:
        return f"{before}\n\n{after}".strip()
    return (before or after).strip()


def split_intake_ui_block(message: str) -> Tuple[str, Optional[List[str]]]:
    """
    Remove a legacy ```intake-ui ... ``` block and return suggested option strings
    (2–4 items), or None if absent / invalid / too few.
    """
    if INTAKE_UI_FENCE not in message:
        return message, None
    try:
        idx = message.index(INTAKE_UI_FENCE)
        start = idx + len(INTAKE_UI_FENCE)
        end = message.index("```", start)
        raw = message[start:end].strip()
        meta = json.loads(raw)
        opts = meta.get("suggested_options")
        if not isinstance(opts, list):
            return _merge_without_intake_ui(message, idx, end), None
        cleaned: List[str] = []
        for x in opts:
            s = str(x).strip()
            if s:
                cleaned.append(s)
        cleaned = cleaned[:4]
        if len(cleaned) < 2:
            return _merge_without_intake_ui(message, idx, end), None
        return _merge_without_intake_ui(message, idx, end), cleaned
    except (ValueError, json.JSONDecodeError):
        return message, None


def strip_session_config_block(message: str) -> str:
    """Remove the trailing ```json ... ``` session config from display text."""
    fence = "```json"
    if fence not in message:
        return message
    try:
        i = message.index(fence)
        return message[:i].rstrip()
    except ValueError:
        return message


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
                "message": str,         # Claude text for display (fences stripped)
                "config":  dict | None,  # populated when status == "complete"
                "suggested_options": list[str] | None  # 2–4 chips when present
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
            self.session_config = sanitize_config(self.session_config)
            display, _opts = extract_display_and_suggestions(assistant_message)
            display = strip_session_config_block(display)
            return {
                "status": "complete",
                "message": display,
                "config": self.session_config,
                "suggested_options": None,
            }

        display, suggested = extract_display_and_suggestions(assistant_message)
        return {
            "status": "ongoing",
            "message": display,
            "config": None,
            "suggested_options": suggested,
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
