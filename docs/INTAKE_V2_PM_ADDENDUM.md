# Intake v2 — PM Review Addendum
## ai-roundtable · JSTcurious · April 2026

This addendum supplements the base Intake v2 Spec with the results
of a senior AI PM review. The base spec covers the situation. This
addendum covers the person making the decision and the intended use
of the output.

Apply this alongside the base spec — these are additions, not
replacements.

---

## What the Base Spec Got Right

The base spec is structurally sound for capturing:
- What the decision is (domain + schema fields)
- What is known vs inferred (assumptions validator)
- What must be known before research (completeness guard)

## What the Base Spec Missed

Three gaps emerged from the PM review:

1. **Output Intent** — the base spec captures the situation but
   not what the user will do with the answer. Same situation
   produces different useful deliverables depending on intent.

2. **User Context** — the base spec treats every user the same.
   Different emotional states, prior work, and leanings warrant
   different research framing. The tool should know the person,
   not just the problem.

3. **Question budget** — unlimited questions produce abandonment.
   The spec needs a ceiling and prioritization logic so intake
   feels focused, not exhaustive.

---

## New Layer — Output Intent Classifier

### Responsibility

After all domain fields are populated, capture what the user
intends to do with the analysis. Same domain, same fields,
different intent produces fundamentally different deliverables.

### When it runs

After Layer 2 (Question Generator) has populated all required
domain fields, before Layer 3 (Assumptions Validator).

### Output Intent Taxonomy

```python
OUTPUT_INTENTS = {
    "decide": {
        "label": "Help me make a decision",
        "description": "Choose between options or commit to a direction",
        "deliverable": "Decision framework with recommendation",
    },
    "learn": {
        "label": "Build a learning or study plan",
        "description": "Structured roadmap to build a skill or knowledge base",
        "deliverable": "Learning roadmap with resources, sequence, milestones",
    },
    "build": {
        "label": "Design something I want to create",
        "description": "Product, tool, content, application",
        "deliverable": "Design brief with scope, constraints, approach",
    },
    "evaluate": {
        "label": "Evaluate or assess something",
        "description": "A person, company, offer, or option",
        "deliverable": "Structured assessment with criteria and conclusions",
    },
    "negotiate": {
        "label": "Prepare for a negotiation",
        "description": "Improve a deal, salary, or outcome",
        "deliverable": "Negotiation brief with leverage points and tactics",
    },
    "convince": {
        "label": "Make a case to others",
        "description": "Persuade a manager, team, partner, or board",
        "deliverable": "Persuasion document with framing and evidence",
    },
    "plan": {
        "label": "Plan a complex set of actions",
        "description": "Sequence, schedule, or project roadmap",
        "deliverable": "Action plan with dependencies and timeline",
    },
    "understand": {
        "label": "Make sense of something complex",
        "description": "Explanation or synthesis of a topic or situation",
        "deliverable": "Structured explanation with mental models",
    },
}
```

### Intake question for output intent

Asked as a single categorical question with the labels above
as chips plus an "Other" option with a textarea:

```
"Once you have the analysis, what will you do with it?"

Chips: [Make a decision] [Build a learning plan] [Design something]
       [Evaluate an option] [Prepare to negotiate] [Make a case to others]
       [Plan next actions] [Make sense of it] [Other — I'll describe it]
```

### How output intent changes the research brief

The research panel system prompt is parameterized by both domain
AND output intent. Example differences:

**Career transition + decide:**
```
Frame the output as a decision framework. Start with a recommendation.
Include risk assessment, opportunity cost, and reversibility analysis.
```

**Career transition + learn:**
```
Do not frame as a pros/cons decision. The user has decided to
transition. Frame output as inputs to a study plan: skills required,
sequence, resources, timeline, milestones, and what good looks like.
```

**Career transition + build:**
```
The user intends to build a learning application. Frame output
around what such an application would need: content taxonomy,
feature set, technical architecture, data sources, and what makes
it differentiated from existing tools.
```

**Career transition + convince:**
```
The user needs to make a case to others. Frame output as a
persuasion document: problem framing, business case, addressing
objections, and supporting evidence. Default audience is manager
unless otherwise specified.
```

---

## New Layer — User Context Profiler

### Responsibility

Capture context about the person, not the situation. This layer
ensures the output is framed for this user specifically — not a
generic user in their situation.

### Fields

Not all fields are asked every session. The question budget system
(below) decides which to ask explicitly and which to infer or skip.

```python
USER_CONTEXT_FIELDS = [
    FieldDefinition(
        key="current_leaning",
        label="Be honest — are you leaning toward a particular answer, or is this genuinely open?",
        field_type="categorical",
        required=False,
        stakes_threshold="high",  # only asked for high-stakes decisions
        options=[
            "Genuinely open, no preference yet",
            "Slight lean but not committed",
            "Strong lean but want to test it",
            "Mostly decided — looking for validation",
            "Prefer not to say",
        ],
    ),
    FieldDefinition(
        key="prior_work",
        label="Have you already done research or thinking on this?",
        field_type="categorical",
        required=False,
        options=[
            "Nothing yet — starting fresh",
            "Some reading and thinking",
            "Significant prior research",
            "I have a draft I want stress-tested",
        ],
    ),
    FieldDefinition(
        key="depth_preference",
        label="How deep should the analysis go?",
        field_type="categorical",
        required=False,
        options=[
            "Concise — give me the recommendation and key reasoning",
            "Structured — balanced analysis with sections",
            "Comprehensive — thorough deep-dive",
        ],
    ),
    FieldDefinition(
        key="audience",
        label="Who is the analysis for?",
        field_type="categorical",
        required=False,
        intent_filter=["learn", "build", "convince", "plan"],  # only relevant for these intents
        options=[
            "Just me",
            "Me and a partner / co-founder",
            "My team",
            "My manager or leadership",
            "A client or customer",
            "Public audience",
        ],
    ),
    FieldDefinition(
        key="off_limits",
        label="Is anything explicitly off the table — things you will not consider?",
        field_type="open",
        required=False,
        stakes_threshold="high",
        placeholder="e.g., relocating internationally, raising more funding, quitting immediately",
    ),
    FieldDefinition(
        key="stakeholders",
        label="Who else is involved in or affected by this decision?",
        field_type="open",
        required=False,
        stakes_threshold="high",
        domains=["career_transition", "financial", "personal"],
        placeholder="e.g., partner, kids, co-founder, team, parents",
    ),
    FieldDefinition(
        key="reversibility",
        label="If this goes wrong, can you course-correct?",
        field_type="categorical",
        required=False,
        options=[
            "Fully reversible — easy to undo",
            "Mostly reversible — costly but possible",
            "Hard to reverse — significant consequences",
            "One-way door — can't go back",
        ],
    ),
]
```

### How user context changes the research brief

**High stakes + mostly decided:**
```
Note: The user indicates they are mostly decided on this question.
Do not produce a neutral analysis. Your job is to surface the
strongest counter-arguments they may have overlooked. If the
research supports their leaning, say so plainly. If it does not,
say so plainly with specific evidence.
```

**Prior work exists + looking for stress-test:**
```
Note: The user has already done significant prior research on this.
Do not duplicate introductory material. Focus on what their prior
research likely missed — counter-arguments, current data they may
not have, and stress-testing their assumptions.
```

**Deep analysis + one-way door reversibility:**
```
Note: This is a one-way door decision. Provide thorough analysis
with full risk assessment. Surface worst-case scenarios. Do not
rush to a recommendation. Recommend decision-delaying actions
if the user has not gathered enough information.
```

**Concise preference + genuinely open:**
```
Note: User wants concise output and is genuinely open. Lead with
the recommendation in 1-2 sentences. Keep the reasoning to one
paragraph per dimension. Do not exceed 400 words.
```

---

## Question Budget and Prioritization

### Principle

**Maximum 7 explicit questions per intake session.**

Research on user engagement shows sharp dropoff past 7 questions.
Not every field needs to be asked — some can be inferred from the
opening message, some can be skipped if not critical.

### Priority scoring

Each field gets a priority score based on:

```python
def field_priority(field, context):
    score = 0

    # Required fields always score high
    if field.required:
        score += 100

    # Fields that change the research brief meaningfully
    if field.key in BRIEF_SHAPING_FIELDS:
        score += 50

    # Stakes-based adjustment
    if context.stakes == "high" and field.stakes_threshold == "high":
        score += 30

    # Domain relevance
    if context.domain in (field.domains or []):
        score += 20

    # Intent relevance
    if context.intent in (field.intent_filter or []):
        score += 20

    # Penalize if inferrable from opening message
    if can_infer(field.key, context.opening_message):
        score -= 40

    return score
```

BRIEF_SHAPING_FIELDS (these genuinely change the research output):
- output_intent
- current_leaning
- depth_preference
- reversibility
- prior_work

### Question selection algorithm

```python
def select_questions_for_session(
    domain: str,
    opening_message: str,
    max_questions: int = 7
) -> list[FieldDefinition]:

    # 1. Infer stakes from opening message
    stakes = infer_stakes(opening_message)  # "low" | "medium" | "high"

    # 2. Collect all candidate fields for this domain
    candidates = DOMAIN_SCHEMAS[domain] + USER_CONTEXT_FIELDS

    # 3. Filter out fields already inferrable
    inferrable = {
        f.key for f in candidates
        if can_infer(f.key, opening_message)
    }
    candidates = [f for f in candidates if f.key not in inferrable]

    # 4. Always include output_intent (critical for framing)
    ensure_in_list(candidates, OUTPUT_INTENT_FIELD)

    # 5. Score and sort
    scored = sorted(
        candidates,
        key=lambda f: field_priority(f, context),
        reverse=True
    )

    # 6. Take top N within budget
    # Required fields cannot be dropped even if budget exceeded
    required = [f for f in scored if f.required]
    optional = [f for f in scored if not f.required]

    selected = required[:]
    remaining_budget = max_questions - len(required)
    selected += optional[:remaining_budget]

    return selected
```

### Inference rules

Fields that can often be inferred without asking:

| Field | Inference rule |
|---|---|
| current_role | Extracted from opening message if job title mentioned |
| what_draws_you | Inferred if user explicitly stated motivation |
| prior_work | Inferred from specificity and jargon in opening message |
| stakes | Inferred from financial magnitude, immigration mentions, timeline urgency |
| depth_preference | Default to "structured" unless user signals otherwise |
| audience | Default to "just me" unless specified or intent requires otherwise |

If confidence in inference is below 0.7, the field is asked explicitly.
If above 0.7, the field is populated and flagged as `inferred: true` so
the assumptions summary shows it for user verification.

---

## Updated Intake Flow

```
User opening message
         ↓
┌─────────────────────────────────────┐
│ Layer 1: Domain Classifier (Haiku) │
│ - Identifies primary + secondary   │
│ - Infers stakes level               │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ Pre-processing (deterministic)      │
│ - Run inference rules on opening    │
│ - Score + select question set (≤7)  │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ Layer 2: Question Generator         │
│ - Ask selected fields sequentially  │
│ - One question per turn             │
│ - Chips from field type             │
│ - Includes output_intent question   │
│ - Includes user_context questions   │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ Layer 3: Assumptions Validator      │
│ - Present confirmed + inferred      │
│ - Include output intent + user ctx  │
│ - Wait for user confirmation        │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│ Prompt Builder (deterministic)      │
│ - Template by domain + intent       │
│ - Insert user context as guidance   │
│ - Append corrections + unknowns     │
└─────────────────────────────────────┘
         ↓
    Research pipeline
```

---

## Updated Context Object

```python
@dataclass
class IntakeContextV2:
    # Classification (Layer 1)
    primary_domain: str
    secondary_domains: list[str]
    stakes: str  # "low" | "medium" | "high"

    # Domain fields (Layer 2)
    domain_fields: dict[str, str]

    # Output intent (new layer)
    output_intent: str
    deliverable_format: str  # derived from intent

    # User context (new layer)
    user_context: dict[str, str]  # any of the USER_CONTEXT_FIELDS

    # Inferred vs stated tracking
    inferred_fields: list[str]  # populated without explicit ask

    # Assumptions (Layer 3)
    confirmed_assumptions: list[str]
    corrected_assumptions: list[str]
    open_questions: list[str]

    # Research handoff
    optimized_prompt: str
    session_title: str
    tier: str
```

---

## Updated Prompt Templates

Prompt templates now take three parameters: domain, intent, user_context.

```python
def build_optimized_prompt(context: IntakeContextV2) -> str:

    # Base template for domain
    template = PROMPT_TEMPLATES[context.primary_domain]
    base = template.format(**context.domain_fields)

    # Intent framing
    intent_framing = INTENT_FRAMING[context.output_intent]

    # User context guidance
    user_guidance = build_user_context_guidance(context.user_context)

    # Assemble
    parts = [base, intent_framing]
    if user_guidance:
        parts.append(user_guidance)
    if context.corrected_assumptions:
        parts.append(f"Note: The user corrected: {'; '.join(context.corrected_assumptions)}")
    if context.open_questions:
        parts.append(f"Note: These remain unknown — treat as open variables: {'; '.join(context.open_questions)}")

    return "\n\n".join(parts)
```

### Example assembled prompt

Domain: `immigration_legal` + `career_transition`
Intent: `decide`
User context: `current_leaning: strong lean, reversibility: one-way door, depth: structured`

```
The user is navigating a job change with an active immigration case.

Visa type: H-1B
Case stage: I-140 approved, I-485 not filed
Employer-sponsored: Yes
New employer immigration support: They said yes but no details
Attorney consulted: Scheduled

Provide specific analysis covering: portability eligibility and timing
risks for H-1B at I-140 approved stage, what to confirm with the new
employer before accepting, sequencing of legal steps, and the key
questions to ask their immigration attorney.

Do NOT give generic H-1B advice. The visa type is H-1B and the stage
is I-140 approved — tailor advice to this exact situation.

## Output Framing

Frame the output as a decision framework. Start with a recommendation.
Include risk assessment, opportunity cost, and reversibility analysis.

## User Context

- The user has a strong lean but wants to test it. Your job is to
  surface the strongest counter-arguments they may have overlooked.
  If the research supports their leaning, say so plainly. If it
  does not, say so plainly with specific evidence.

- This is a one-way door decision. Provide thorough risk assessment.
  Surface worst-case scenarios. Recommend decision-delaying actions
  if the user has not gathered enough information.

- Target depth: structured analysis with balanced sections. Not
  concise, not comprehensive deep-dive.
```

---

## Updated File Structure

```
backend/
  intake_v2/
    __init__.py
    classifier.py              # Layer 1
    stakes.py                  # Stakes inference from opening message
    inference.py               # Field inference rules
    schemas.py                 # Domain schemas
    user_context_fields.py     # User context field definitions
    output_intents.py          # Output intent taxonomy + framings
    question_selector.py       # Priority scoring + 7-question budget
    question_generator.py      # Layer 2 — natural phrasing
    completeness.py            # Required field guard
    assumptions.py             # Layer 3
    prompt_builder.py          # Domain + intent + user_context composition
    templates.py               # PROMPT_TEMPLATES per domain
    intent_framings.py         # INTENT_FRAMING per intent
    session.py                 # IntakeSessionV2 orchestration
```

---

## Updated Build Effort

| Component | Effort |
|---|---|
| Base spec components (from original) | 7 days |
| Output intent layer + framings | 1 day |
| User context fields + framings | 1 day |
| Question selection + budget + inference | 2 days |
| Additional templates and integration | 1 day |
| Additional tests | 1 day |
| **Total** | **~13 days** |

This is roughly two weeks of focused work. The additional week over
the base spec is worth it — the difference between "captures the
problem" and "frames the output for this person" is the difference
between a tool users abandon and one they return to.

---

## Summary — What the PM Review Added

1. **Output intent** — same situation produces different deliverables
   depending on what the user will do with the answer
2. **User context profiler** — leaning, prior work, depth preference,
   audience, off-limits, stakeholders, reversibility
3. **Stakes-aware prioritization** — high-stakes sessions warrant
   more user context questions
4. **7-question budget** — intake stays focused, never exhaustive
5. **Inference rules** — fields populated from opening message
   rather than always asked
6. **Intent-based prompt framing** — research brief changes format
   based on what the user will do with the output
7. **User context guidance in prompts** — research panel knows how
   to frame output for this specific user

The intake is no longer just capturing *the problem*. It is capturing
*the decision, the intended use, and the person* — all three required
to produce an output the user actually acts on.
