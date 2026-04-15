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
    RefineSession   — two-step prompt refinement loop (probe → confirm)

Constants:
    INTAKE_SYSTEM_PROMPT      — full master system prompt for intake
    REFINEMENT_SYSTEM_PROMPT  — system prompt template for prompt refinement

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

**Engineering background** — always ask this first, as two questions in sequence:

Q1: "What best describes your current engineering background?"
INTAKE_OPTIONS: ["Data/Software engineer, Python + SQL stack", \
"Backend engineer, Java/Node/Go", \
"Full-stack engineer, web + APIs", \
"DevOps/Platform engineer"]

Q2: "How long have you been working in this role?"
INTAKE_OPTIONS: ["0-2 years", "3-5 years", "6-10 years", "10+ years"]

These two questions together give you: role type, current tech stack, \
and experience level — everything needed to calibrate the optimized prompt. \
Never collapse them into one vague question like "What's your background?"

**Remaining questions (ask what's relevant):**
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
  "tier": "smart",
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
- "quick"  — brainstorms, gut checks, simple Q&A (fast, cheap)
- "smart"  — most work: research, plans, evaluations, decisions. \
Near-Deep quality. **Recommended default.**
- "deep"   — critical reports, architecture reviews, strategic plans \
where maximum depth is worth the extra time and cost

Default to "smart" for most sessions. \
Use "deep" only when the user explicitly needs maximum depth. \
Use "quick" only if they explicitly want speed over depth.

## The Specificity Principle

**Specific questions produce specific prompts. Generic questions produce generic prompts.**

Every question you ask must be specific enough that the answer \
directly changes what goes into the optimized prompt. \
If the answer wouldn't change the prompt, don't ask the question.

Bad: "Tell me about your background." \
Good: "What best describes your current engineering background?" \
      (with options that name actual role types and stacks)

Bad: "What are your goals?" \
Good: "What role are you targeting — AI Application Engineer, \
ML Engineer, MLOps, or something else?"

The user's exact situation must appear in the optimized prompt — \
not a generic paraphrase of it.

## Quality Bar for the Optimized Prompt

The optimized prompt must:
- Contain no assumptions that weren't confirmed in intake
- Name the user's specific role type, stack, and experience level — \
  not "an engineer" or "someone with some experience"
- Specify the desired output format explicitly
- Include constraints that will directly affect the answer \
  (hours/week, deadline, learning style, budget)
- Tell the models what good looks like for this specific user
- Be specific enough that two different frontier models \
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

- Asking about engineering background (Q1):
  INTAKE_OPTIONS: ["Data/Software engineer, Python + SQL stack", \
"Backend engineer, Java/Node/Go", \
"Full-stack engineer, web + APIs", \
"DevOps/Platform engineer"]

- Asking about years in role (Q2):
  INTAKE_OPTIONS: ["0-2 years", "3-5 years", "6-10 years", "10+ years"]

- Asking about target role:
  INTAKE_OPTIONS: ["AI Application Engineer", "ML Engineer", "MLOps Engineer", "Not sure yet"]

- Asking about hours per week:
  INTAKE_OPTIONS: ["5-10 hrs/week", "10-15 hrs/week", "15-20 hrs/week", "20+ hrs/week"]

- After a mirror of a career transition:
  INTAKE_OPTIONS: ["Yes, that's right", "Mostly — a few details to add", "Not quite — I'll clarify"]

- Asking about timeline:
  INTAKE_OPTIONS: ["Within 3 months", "3-6 months", "6-12 months", "No fixed deadline"]

- Asking about learning style:
  INTAKE_OPTIONS: ["Hands-on projects", "Structured courses", "Reading docs + papers", "Mix of all three"]

- Asking about decision deadline (RESEARCH_DECISION):
  INTAKE_OPTIONS: ["This week", "This month", "Next quarter", "No hard deadline"]

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
        self.active_refine: Optional["RefineSession"] = None

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
        # Allow re-entry after completion (user chose to add more information).
        self.complete = False
        self.session_config = None

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

        Preserve "smart" for the approval UI; backend maps smart → deep-capable
        models at session time until the advisor pattern is fully wired.

        Mapping:
            "quick"  → "quick"
            "smart"  → "smart"
            "deep" / "deep_thinking" → "deep"
            anything else → "deep"
        """
        TIER_MAP = {"quick": "quick", "deep": "deep", "deep_thinking": "deep", "smart": "smart"}
        current = config.get("tier", "deep")
        config["tier"] = TIER_MAP.get(current, "deep")

    def refine(self, user_message: str, current_prompt_override: Optional[str] = None) -> dict:
        """
        Post-intake prompt refinement (POST /api/intake/refine).

        First call while ``active_refine`` is None: starts :class:`RefineSession`
        and returns a probing question + optional chip options.

        Second call: passes the user's answer to ``confirm()`` and merges the
        rewritten ``optimized_prompt`` into ``session_config``.

        ``current_prompt_override`` (optional): when starting a new refine, use
        this text as the baseline prompt instead of ``session_config`` only.

        Returns:
            {
                "status": "probing" | "refined",
                "message": str,
                "suggested_options": list[str] | None,
                "config": dict | None,
            }
        """
        if not self.session_config:
            raise ValueError("Intake session has no config — refine only after intake completes.")
        prompt = self.session_config.get("optimized_prompt")
        if prompt is None:
            prompt = self.session_config.get("optimizedPrompt")
        if not isinstance(prompt, str) or not str(prompt).strip():
            raise ValueError("session_config is missing optimized_prompt.")

        msg = (user_message or "").strip()
        if not msg:
            raise ValueError("Message must not be empty.")

        if self.active_refine is None:
            base_prompt = str(prompt).strip()
            if (
                current_prompt_override
                and isinstance(current_prompt_override, str)
                and current_prompt_override.strip()
            ):
                base_prompt = current_prompt_override.strip()
            self.active_refine = RefineSession(base_prompt, msg)
            pr = self.active_refine.probe()
            opts = pr.get("suggested_options")
            if isinstance(opts, list):
                opts = [sanitize_text(str(x).strip()) for x in opts if str(x).strip()]
                if len(opts) < 2:
                    opts = None
            else:
                opts = None
            return {
                "status": "probing",
                "message": sanitize_text(pr.get("question") or ""),
                "suggested_options": opts,
                "config": None,
            }

        cr = self.active_refine.confirm(msg)
        self.active_refine = None
        new_prompt = cr.get("updated_prompt") or ""
        if isinstance(new_prompt, str) and new_prompt.strip():
            merged = dict(self.session_config)
            merged["optimized_prompt"] = new_prompt.strip()
            self.session_config = sanitize_config(merged)
        opts = cr.get("suggested_options")
        if isinstance(opts, list):
            opts = [sanitize_text(str(x).strip()) for x in opts if str(x).strip()]
            if len(opts) < 2:
                opts = None
        else:
            opts = None
        return {
            "status": "refined",
            "message": sanitize_text(cr.get("question") or ""),
            "suggested_options": opts,
            "config": self.session_config,
        }

    def clear_refine(self) -> None:
        """Discard an in-progress RefineSession (e.g. user left the refine flow)."""
        self.active_refine = None

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


# ── Prompt refinement loop ────────────────────────────────────────────────────

REFINEMENT_SYSTEM_PROMPT = """\
You are refining an optimized prompt for a roundtable discussion \
with frontier AI models.

The current prompt is:
{current_prompt}

The user wants to adjust or add something.
Your job:
1. Ask ONE probing question to fully understand their intent — \
   do not just append their feedback, understand what they actually need.
2. When you have the answer, rewrite the entire prompt holistically — \
   not appending, fully restructuring to incorporate the new context.

The refined prompt must:
- Preserve all the context from the original intake
- Incorporate the new information naturally
- Remain specific, not generic
- Be better than the original

Always end by asking if they are satisfied or want to refine further.

**Important:** Output plain ASCII/UTF-8 text only. \
No Unicode directional formatting characters or bidi overrides.
"""

_REFINED_PROMPT_FENCE = "```refined-prompt"


def _strip_refined_prompt_block(message: str) -> str:
    """Remove a ```refined-prompt ... ``` block from display text."""
    if _REFINED_PROMPT_FENCE not in message:
        return message
    try:
        i   = message.index(_REFINED_PROMPT_FENCE)
        end = message.index("```", i + len(_REFINED_PROMPT_FENCE))
        before = message[:i].rstrip()
        after  = message[end + 3:].lstrip()
        if before and after:
            return f"{before}\n\n{after}".strip()
        return (before or after).strip()
    except ValueError:
        return message


def _extract_refined_prompt(message: str) -> Optional[str]:
    """
    Extract the refined optimized prompt from a ```refined-prompt ... ``` block.
    Returns None if the block is absent or unparseable.
    """
    if _REFINED_PROMPT_FENCE not in message:
        return None
    try:
        start = message.index(_REFINED_PROMPT_FENCE) + len(_REFINED_PROMPT_FENCE)
        end   = message.index("```", start)
        return message[start:end].strip() or None
    except ValueError:
        return None


class RefineSession:
    """
    Two-step prompt refinement loop.

    Step 1 — probe():
        Claude reads the current optimized prompt and the user's feedback,
        then asks ONE probing question to understand the intent behind the request.

    Step 2 — confirm(probe_answer):
        Claude rewrites the entire optimized prompt holistically, incorporating
        the new context. Returns the updated prompt and a confirmation question.

    Usage:
        session = RefineSession(current_prompt, user_feedback)
        result  = session.probe()
        # result["status"] == "probing"
        # send result["question"] + result["suggested_options"] to frontend

        result2 = session.confirm(probe_answer)
        # result2["status"] == "refined"
        # result2["updated_prompt"] is the new complete optimized prompt
    """

    def __init__(self, current_prompt: str, user_feedback: str):
        self.current_prompt = current_prompt
        self.user_feedback  = user_feedback
        self.history: List[dict] = []

    def _system(self, extra: str = "") -> str:
        base = REFINEMENT_SYSTEM_PROMPT.format(current_prompt=self.current_prompt)
        return f"{base}\n{extra}".strip() if extra else base

    def probe(self) -> dict:
        """
        Step 1 — ask one probing question.

        Returns:
            {
                "status":           "probing",
                "question":         str,
                "suggested_options": list[str] | None,
                "updated_prompt":   None,
            }
        """
        user_msg = (
            f"The user wants to adjust: {self.user_feedback}\n\n"
            "Ask your ONE probing question to understand their intent fully. "
            "End with INTAKE_OPTIONS: [\"option A\", \"option B\", \"option C\"]"
        )
        self.history.append({"role": "user", "content": user_msg})

        response = call_claude(
            messages=self.history,
            tier=INTAKE_MODEL_TIER,
            system=self._system(),
        )
        assistant_text = response.content[0].text
        self.history.append({"role": "assistant", "content": assistant_text})

        display, options = extract_display_and_suggestions(assistant_text)
        display = sanitize_text(display)

        return {
            "status":            "probing",
            "question":          display,
            "suggested_options": options,
            "updated_prompt":    None,
        }

    def confirm(self, probe_answer: str) -> dict:
        """
        Step 2 — rewrite the optimized prompt based on the probe answer.

        Args:
            probe_answer: the user's answer to the probing question

        Returns:
            {
                "status":           "refined",
                "updated_prompt":   str,   # new complete optimized prompt
                "question":         str,   # confirmation question for the user
                "suggested_options": ["Yes — looks good",
                                      "I'd like to adjust something else"],
            }
        """
        if not self.history:
            raise RuntimeError("confirm() called before probe() — no conversation history.")

        self.history.append({"role": "user", "content": probe_answer})

        extra_instructions = (
            "Now rewrite the full optimized prompt holistically. "
            "Output it inside a ```refined-prompt ... ``` fenced block. "
            "After the block, ask a short confirmation question. "
            "End with: "
            'INTAKE_OPTIONS: ["Yes — looks good", "Adjust something else"]'
        )

        response = call_claude(
            messages=self.history,
            tier=INTAKE_MODEL_TIER,
            system=self._system(extra_instructions),
        )
        assistant_text = response.content[0].text
        self.history.append({"role": "assistant", "content": assistant_text})

        updated_prompt = _extract_refined_prompt(assistant_text)
        display, options = extract_display_and_suggestions(assistant_text)
        display = sanitize_text(_strip_refined_prompt_block(display))

        if options is None:
            options = ["Yes — looks good", "Adjust something else"]

        return {
            "status":            "refined",
            "updated_prompt":    sanitize_text(updated_prompt or self.current_prompt),
            "question":          display or "Does this capture it now, or would you like to refine further?",
            "suggested_options": options,
        }
