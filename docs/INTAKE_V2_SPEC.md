# Intake v2 — Architecture Specification
## ai-roundtable · JSTcurious · April 2026

---

## Problem Statement

The current intake (v1) is a single-model conversation that asks
Claude Sonnet to simultaneously conduct a natural dialogue, identify
the decision domain, enforce completeness, generate chips, and
produce a structured config. This single-model approach is fragile:
when it fails on any one responsibility, the entire downstream session
is compromised — the research panel receives a vague prompt and
produces generic advice.

Symptoms of v1 fragility:
- Compound questions (two questions in one turn)
- Generic chips unrelated to the question being asked
- Intake closing before critical fields are populated
- Domain misidentification leading to wrong probing path
- Assumptions never made explicit to the user

---

## Design Principles

1. **Separation of concerns** — each layer has one job
2. **Schema-driven completeness** — required fields are enforced
   programmatically, not by prompt instruction
3. **Chips from field type** — categorical fields generate chips
   automatically; open fields get a textarea
4. **One question per turn** — enforced by the question generator,
   not by hoping the model complies
5. **Assumptions are explicit and user-verified** — never inferred
   silently
6. **Any domain** — new domains are added by adding a schema,
   not by rewriting prompts
7. **Graceful degradation** — if any layer fails, fall back to
   the next layer down, never crash the session

---

## Three-Layer Architecture

```
User message
     ↓
Layer 1: Domain Classifier (Haiku — fast, cheap)
     ↓
Layer 2: Question Generator (Sonnet — schema-aware)
     ↓
Layer 3: Assumptions Validator (Sonnet — pre-handoff)
     ↓
Research pipeline
```

---

## Layer 1 — Domain Classifier

### Responsibility
Take the user's initial message and return the decision domain(s).
This is a pure classification task.

### Model
Claude Haiku — fast, cheap, reliable for classification.

### Input
User's opening message (raw text).

### Output
```python
@dataclass
class DomainClassification:
    primary_domain: str          # most prominent domain
    secondary_domains: list[str] # additional domains if present
    confidence: float            # 0.0 - 1.0
    reasoning: str               # one sentence explaining the classification
```

### Domain taxonomy
```python
DOMAINS = {
    "career_transition": "Job changes, role switches, offer evaluation, resignation timing",
    "immigration_legal": "Visa decisions, status changes, sponsorship, green card strategy",
    "financial":         "Investments, compensation, equity, major purchases, financial planning",
    "product_strategy":  "Build vs buy, roadmaps, market entry, pricing, go-to-market",
    "technical":         "Architecture, stack selection, system design, tooling evaluation",
    "personal":          "Relationships, health decisions, major life changes",
    "academic":          "Degree choices, research direction, publication strategy",
    "general":           "Does not fit a specific domain — use open probing",
}
```

### System prompt (Layer 1)
```
You are a decision domain classifier. Given a user's message,
identify which domain(s) their decision belongs to.

Return only valid JSON. No preamble.

{
  "primary_domain": "one of the domain keys above",
  "secondary_domains": ["any additional domains, or empty list"],
  "confidence": 0.0-1.0,
  "reasoning": "one sentence"
}

If the message spans multiple domains (e.g., career change with
immigration implications), list all relevant domains.
primary_domain is the most prominent constraint.
```

### Failure handling
If classification fails or returns unknown domain: default to
`"general"` and use open probing. Never block intake.

---

## Layer 2 — Domain Schemas

### Responsibility
Define what must be known before research can begin for each domain.
The schema is the ground truth for completeness — not the prompt.

### Schema structure
```python
@dataclass
class FieldDefinition:
    key: str
    label: str                    # human-readable question
    field_type: str               # "categorical" | "open" | "boolean" | "date"
    required: bool                # if True, intake cannot close without this
    options: list[str]            # for categorical fields — these become chips
    depends_on: dict              # conditional — only ask if another field matches
    follow_up_if: dict            # ask follow-up if this field matches a value
    placeholder: str              # textarea placeholder for open fields
```

### Domain schemas (all domains)

```python
DOMAIN_SCHEMAS = {

    "career_transition": [
        FieldDefinition(
            key="current_role",
            label="What is your current role and how long have you been in it?",
            field_type="open",
            required=True,
            placeholder="e.g., Senior Data Engineer at a utility company, 4 years",
        ),
        FieldDefinition(
            key="opportunity_type",
            label="Do you have a concrete offer, or are you still exploring?",
            field_type="categorical",
            required=True,
            options=["Concrete offer in hand", "Active conversations", "Early exploration", "Internal transfer"],
        ),
        FieldDefinition(
            key="what_draws_you",
            label="What specifically draws you to this opportunity?",
            field_type="open",
            required=True,
            placeholder="e.g., closer to AI research, higher comp, better team",
        ),
        FieldDefinition(
            key="timeline",
            label="Is there a deadline or timeline pressure?",
            field_type="categorical",
            required=False,
            options=["Offer expires soon", "Within 1 month", "1-3 months", "No hard deadline"],
        ),
        FieldDefinition(
            key="reversibility",
            label="Could you return to your current role or industry if needed?",
            field_type="categorical",
            required=False,
            options=["Yes, easily", "Probably yes", "Unlikely", "One-way door"],
        ),
    ],

    "immigration_legal": [
        FieldDefinition(
            key="visa_type",
            label="What visa type are you currently on?",
            field_type="categorical",
            required=True,
            options=["H-1B", "L-1", "O-1 / EB-1A", "Pending green card (I-485)", "F-1 OPT / STEM OPT", "TN", "Other / Not sure"],
        ),
        FieldDefinition(
            key="case_stage",
            label="What stage is your case at?",
            field_type="categorical",
            required=True,
            options=["Initial H-1B period", "I-140 approved, I-485 not filed", "I-485 pending < 180 days", "I-485 pending 180+ days", "Not sure of my stage"],
            depends_on={"visa_type": ["H-1B", "Pending green card (I-485)"]},
        ),
        FieldDefinition(
            key="employer_sponsored",
            label="Is your current status employer-sponsored?",
            field_type="boolean",
            required=True,
            options=["Yes", "No", "Partially"],
        ),
        FieldDefinition(
            key="new_employer_confirmed",
            label="Has the prospective employer confirmed they can sponsor or transfer your case?",
            field_type="categorical",
            required=True,
            options=["Yes, confirmed", "They said yes but no details", "Not discussed yet", "They cannot sponsor"],
        ),
        FieldDefinition(
            key="attorney_consulted",
            label="Have you consulted an immigration attorney about this move?",
            field_type="categorical",
            required=False,
            options=["Yes, I have one on this", "Scheduled", "Not yet", "I plan to handle it myself"],
        ),
        FieldDefinition(
            key="priority_date",
            label="Do you have an approved I-140? If so, what is your priority date and country of chargeability?",
            field_type="open",
            required=False,
            placeholder="e.g., I-140 approved Dec 2022, India chargeability, priority date Nov 2019",
            depends_on={"case_stage": ["I-140 approved, I-485 not filed", "I-485 pending < 180 days", "I-485 pending 180+ days"]},
        ),
    ],

    "financial": [
        FieldDefinition(
            key="decision_type",
            label="What is the financial decision specifically?",
            field_type="open",
            required=True,
            placeholder="e.g., evaluating equity compensation vs cash, deciding whether to exercise options",
        ),
        FieldDefinition(
            key="risk_tolerance",
            label="How would you describe your risk tolerance?",
            field_type="categorical",
            required=True,
            options=["Conservative — preserve capital", "Moderate — balanced growth", "Aggressive — maximize upside", "It depends on the scenario"],
        ),
        FieldDefinition(
            key="timeline",
            label="What is the relevant time horizon for this decision?",
            field_type="categorical",
            required=True,
            options=["Immediate (< 3 months)", "Near-term (3-12 months)", "Medium-term (1-5 years)", "Long-term (5+ years)"],
        ),
        FieldDefinition(
            key="amount_at_stake",
            label="Roughly what is the magnitude of this decision?",
            field_type="categorical",
            required=False,
            options=["< $10K", "$10K - $100K", "$100K - $500K", "> $500K", "Prefer not to say"],
        ),
    ],

    "product_strategy": [
        FieldDefinition(
            key="current_state",
            label="What is the current state of the product or initiative?",
            field_type="open",
            required=True,
            placeholder="e.g., MVP shipped, 200 users, exploring whether to build native search or use Elastic",
        ),
        FieldDefinition(
            key="decision_type",
            label="What type of decision is this?",
            field_type="categorical",
            required=True,
            options=["Build vs buy", "Market entry", "Pricing strategy", "Feature prioritization", "Go-to-market approach", "Other"],
        ),
        FieldDefinition(
            key="constraints",
            label="What constraints are non-negotiable?",
            field_type="open",
            required=True,
            placeholder="e.g., must ship in 6 weeks, team is 3 engineers, no vendor lock-in",
        ),
        FieldDefinition(
            key="success_definition",
            label="What does success look like for this decision?",
            field_type="open",
            required=False,
            placeholder="e.g., 10% improvement in search relevance, <2s latency, under $5K/month infra cost",
        ),
    ],

    "technical": [
        FieldDefinition(
            key="current_stack",
            label="What is the current technical context?",
            field_type="open",
            required=True,
            placeholder="e.g., Python FastAPI backend, PostgreSQL, 50k daily requests, moving to AWS",
        ),
        FieldDefinition(
            key="decision_type",
            label="What type of technical decision is this?",
            field_type="categorical",
            required=True,
            options=["Architecture design", "Stack / framework selection", "Tooling evaluation", "Refactor strategy", "Scaling approach", "Other"],
        ),
        FieldDefinition(
            key="constraints",
            label="What are the hard constraints?",
            field_type="open",
            required=True,
            placeholder="e.g., must be Python, team has no Go experience, compliance requires data residency in US",
        ),
        FieldDefinition(
            key="scale",
            label="What is the scale this needs to handle?",
            field_type="categorical",
            required=False,
            options=["Prototype / internal", "< 10K users", "10K - 100K users", "100K - 1M users", "> 1M users"],
        ),
    ],

    "general": [
        FieldDefinition(
            key="situation",
            label="Tell me more about the situation you are navigating.",
            field_type="open",
            required=True,
            placeholder="Share as much context as you're comfortable with",
        ),
        FieldDefinition(
            key="what_you_want",
            label="What outcome are you hoping for from this analysis?",
            field_type="open",
            required=True,
            placeholder="e.g., a clear recommendation, a list of options, validation of my thinking",
        ),
        FieldDefinition(
            key="constraints",
            label="Are there any constraints or non-negotiables I should know about?",
            field_type="open",
            required=False,
            placeholder="e.g., timeline, budget, people involved, things that are off the table",
        ),
    ],
}
```

---

## Layer 2 — Question Generator

### Responsibility
Given the domain schema and populated context, determine the next
question to ask. Generate contextual chips if the field is categorical.
Enforce one question per turn.

### Model
Claude Sonnet — needed for natural conversational phrasing.

### Algorithm
```python
def get_next_question(
    schema: list[FieldDefinition],
    populated: dict,
    domain: str
) -> NextQuestion | None:

    for field in schema:
        # Skip if already populated
        if field.key in populated:
            continue

        # Skip if depends_on condition not met
        if field.depends_on:
            parent_key, parent_values = list(field.depends_on.items())[0]
            if populated.get(parent_key) not in parent_values:
                continue

        # Found next field to ask
        return NextQuestion(
            field=field,
            chips=field.options if field.field_type == "categorical" else [],
            show_textarea=(field.field_type == "open" or field.field_type == "categorical"),
        )

    return None  # All required fields populated — proceed to assumptions
```

### Question phrasing
The field `label` is the base question. Claude Sonnet is given:
- The conversation history so far
- The field label and field type
- The previous answer (to acknowledge before asking)

Its only job: rephrase the label naturally given the conversation
context. It cannot skip fields, add new fields, or ask follow-ups
not in the schema.

### Output
```python
@dataclass
class NextQuestion:
    field: FieldDefinition
    phrased_question: str    # Claude's natural phrasing of the field label
    chips: list[str]         # empty for open fields
    show_textarea: bool      # always True
```

---

## Layer 3 — Assumptions Validator

### Responsibility
Before closing intake, generate an explicit assumptions summary
and present it to the user for confirmation. Record corrections.

### Model
Claude Sonnet.

### Trigger
All required fields in the domain schema are populated.

### Process
1. Collect all populated fields
2. Identify fields that were inferred (user gave a partial answer
   that Claude interpreted) vs explicitly stated
3. Generate assumptions summary in this exact format:

```
Before I brief the research panel, here is what I am working with:

CONFIRMED
• You are on an H-1B in your initial period (explicitly stated)
• You have an offer in hand at a frontier AI company (stated)
• The prospective employer has not confirmed immigration support (stated)

INFERRED (please correct if wrong)
• Your primary concern is immigration risk, not compensation (inferred
  from emphasis in your messages)
• You are India-born, given the I-140 priority date question
  (inferred — you may want to clarify)

UNKNOWN (I will flag these for the research panel)
• Whether you have an approved I-140
• Your priority date and chargeability country

Is anything above wrong or missing? Correct anything before I proceed.
```

4. Wait for user confirmation or corrections
5. If corrections received: update the context object and re-present
   the corrected summary
6. If confirmed: close intake and hand off to research

### Output additions to session config
```python
confirmed_fields: dict          # all populated fields
confirmed_assumptions: list[str]
corrected_assumptions: list[str]
open_questions: list[str]       # unknown fields — passed to research panel
```

---

## Completeness Guard

### Responsibility
Programmatically enforce that required fields are populated before
intake can close. This is separate from the conversation logic.

### Implementation
```python
def check_completeness(
    schema: list[FieldDefinition],
    populated: dict
) -> CompletenessResult:

    missing_required = []
    missing_recommended = []

    for field in schema:
        # Check depends_on before requiring
        if field.depends_on:
            parent_key, parent_values = list(field.depends_on.items())[0]
            if populated.get(parent_key) not in parent_values:
                continue  # Skip conditional field

        if field.key not in populated:
            if field.required:
                missing_required.append(field)
            else:
                missing_recommended.append(field)

    return CompletenessResult(
        complete=len(missing_required) == 0,
        missing_required=missing_required,
        missing_recommended=missing_recommended,
    )
```

If `complete=False`, intake CANNOT close regardless of what the
model outputs. The question generator is called again with the
first missing required field.

---

## Context Object (Output of Intake v2)

```python
@dataclass
class IntakeContextV2:
    # Classification
    primary_domain: str
    secondary_domains: list[str]

    # Populated fields (schema-driven)
    fields: dict[str, str]          # key → user's answer

    # Assumptions (from Layer 3)
    confirmed_assumptions: list[str]
    corrected_assumptions: list[str]
    open_questions: list[str]

    # Research handoff
    optimized_prompt: str           # constructed from fields, not free-text
    session_title: str
    output_type: str                # decision | analysis | plan | comparison
    tier: str                       # always "smart" for now
```

### Optimized prompt construction
The optimized_prompt is constructed programmatically from populated
fields — not generated by Claude free-text. This eliminates the
risk of the model hallucinating context that wasn't in the conversation.

```python
def build_optimized_prompt(
    domain: str,
    fields: dict,
    open_questions: list[str],
    corrected_assumptions: list[str]
) -> str:
    prompt_parts = []

    # Domain-specific prompt template
    template = PROMPT_TEMPLATES[domain]
    prompt_parts.append(template.format(**fields))

    # Corrections
    if corrected_assumptions:
        prompt_parts.append(
            f"Note: The user corrected the following during intake: "
            f"{'; '.join(corrected_assumptions)}"
        )

    # Open questions
    if open_questions:
        prompt_parts.append(
            f"Note: The following remain unknown — treat as open variables: "
            f"{'; '.join(open_questions)}"
        )

    return "\n\n".join(prompt_parts)
```

---

## Prompt Templates (per domain)

These are filled with populated field values to construct the
optimized_prompt programmatically.

```python
PROMPT_TEMPLATES = {
    "career_transition": """
The user is evaluating a career transition decision.

Current situation: {current_role}
Opportunity type: {opportunity_type}
What draws them: {what_draws_you}
Timeline pressure: {timeline}
Reversibility: {reversibility}

Provide a structured decision framework covering: career trajectory
implications, risk assessment, negotiation leverage, and a recommended
action sequence given their specific situation.
""",

    "immigration_legal": """
The user is navigating a job change with an active immigration case.

Visa type: {visa_type}
Case stage: {case_stage}
Employer-sponsored: {employer_sponsored}
New employer immigration support: {new_employer_confirmed}
Attorney consulted: {attorney_consulted}
Priority date / I-140 details: {priority_date}

Provide specific analysis covering: portability eligibility and timing
risks for their visa type and stage, what to confirm with the new
employer before accepting, sequencing of legal steps, and the key
questions to ask their immigration attorney.

Do NOT give generic H-1B advice. The visa type is {visa_type} and
the stage is {case_stage} — tailor advice to this exact situation.
""",

    "financial": """
The user is evaluating a financial decision.

Decision: {decision_type}
Risk tolerance: {risk_tolerance}
Time horizon: {timeline}
Magnitude: {amount_at_stake}

Provide analysis covering: the key variables that determine the
right choice, risk-adjusted scenarios, and a recommended approach
given their risk tolerance and timeline.
""",

    "product_strategy": """
The user is making a product strategy decision.

Current state: {current_state}
Decision type: {decision_type}
Non-negotiable constraints: {constraints}
Success definition: {success_definition}

Provide analysis covering: the tradeoffs of the main options,
which option best fits the stated constraints, the key risks
in each path, and a recommended approach with rationale.
""",

    "technical": """
The user is making a technical architecture decision.

Current stack and context: {current_stack}
Decision type: {decision_type}
Hard constraints: {constraints}
Scale: {scale}

Provide analysis covering: the technical tradeoffs of the main
options given the stated constraints and scale, implementation
complexity and risk, and a recommended approach with rationale.
""",

    "general": """
The user is working through the following situation:

{situation}

What they are hoping for: {what_you_want}
Constraints: {constraints}

Provide structured analysis covering the key decision dimensions,
relevant tradeoffs, and a recommended approach.
""",
}
```

---

## WebSocket Message Sequence (Intake v2)

```
Client → {type: "intake_start", message: user_text}
Server → {type: "domain_classified", domain: "immigration_legal", 
          secondary: ["career_transition"]}
Server → {type: "intake_question", question: "What visa type are you on?",
          chips: ["H-1B", "L-1", ...], field_key: "visa_type"}
Client → {type: "intake_response", field_key: "visa_type", value: "H-1B"}
Server → {type: "intake_question", question: "What stage is your H-1B at?",
          chips: [...], field_key: "case_stage"}
...
[All required fields populated]
Server → {type: "intake_assumptions", 
          confirmed: [...], inferred: [...], unknown: [...]}
Client → {type: "intake_confirm"} | {type: "intake_correction", corrections: [...]}
Server → {type: "intake_complete", session_config: {...}, optimized_prompt: "..."}
```

---

## File Structure

```
backend/
  intake_v2/
    __init__.py
    classifier.py          # Layer 1 — domain classification
    schemas.py             # Domain schemas and FieldDefinition
    question_generator.py  # Layer 2 — next question selection + phrasing
    completeness.py        # Required field guard
    assumptions.py         # Layer 3 — assumptions summary + validation
    prompt_builder.py      # Optimized prompt construction from fields
    session.py             # IntakeSessionV2 — orchestrates all layers
    templates.py           # PROMPT_TEMPLATES per domain
```

---

## Migration Plan

1. Build intake_v2/ as a parallel implementation
2. Feature flag: `INTAKE_VERSION=v1|v2` in env
3. Run both versions in parallel for 1 week — compare outputs
4. If v2 produces better optimized_prompts (measured by research
   panel specificity): cut over
5. Delete v1 code

The feature flag approach means zero risk to production during development.

---

## What Intake v2 Does NOT Do

- Does not replace the research pipeline — only the intake step
- Does not add new domains automatically — each domain requires
  a human-written schema
- Does not use RAG or external knowledge — pure structured conversation
- Does not support branching dialogue trees — linear schema traversal only
- Does not infer domain from session history — classification is on
  the opening message only

---

## Estimated Build Effort

| Component | Effort |
|---|---|
| Domain classifier + schemas | 1 day |
| Question generator | 1 day |
| Completeness guard | 0.5 day |
| Assumptions validator | 1 day |
| Prompt builder + templates | 1 day |
| WebSocket integration | 1 day |
| Tests | 1 day |
| Feature flag + migration | 0.5 day |
| **Total** | **~7 days** |

This is a week of focused work. The output is a production-grade
intake that works reliably for any domain and can be extended by
adding a schema — no prompt rewriting required.
