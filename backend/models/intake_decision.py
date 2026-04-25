"""
backend/models/intake_decision.py

Pydantic schema for the structured JSON response from intake.
Used to enforce typed output from all intake providers.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class IntakeDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    needs_clarification: bool
    clarifying_question: Optional[str] = None  # only when needs_clarification is True
    # These fields are populated when intake closes (needs_clarification=False).
    # During clarifying turns the model legitimately returns them as null.
    optimized_prompt: Optional[str] = None  # refined, context-enriched version of user's raw prompt
    tier: Literal["smart"]                  # intake always returns smart; user controls via UI
    output_type: Optional[str] = None       # e.g. "report", "plan", "decision", "brainstorm", "analysis"
    reasoning: Optional[str] = None         # one sentence shown in UI

    # Deep intake fields — populated by the new domain-specific probing prompt
    decision_domain: list[str] = Field(default_factory=list)
    # e.g. ["career_transition", "immigration_legal"]

    user_context: dict[str, Any] = Field(default_factory=dict)
    # Structured context including immigration_specifics when applicable:
    # {
    #   "current_situation": "...",
    #   "what_they_want": "...",
    #   "key_constraints": [...],
    #   "immigration_specifics": {
    #     "visa_type": "H-1B",
    #     "case_stage": "I-140 approved, I-485 not yet filed",
    #     "employer_sponsored": "true",
    #     "new_employer_can_transfer": "unconfirmed",
    #     "attorney_consulted": "not yet"
    #   },
    #   "timeline_pressure": "...",
    #   "risk_tolerance": "..."
    # }

    suggested_options: list[str] = Field(default_factory=list)
    # Short answer options for the current clarifying_question (context-specific).
    # Empty list means the question requires free text.
    # e.g. for visa type: ["H-1B", "L-1", "O-1 / EB-1A", "Pending green card",
    #                       "F-1 OPT / STEM OPT", "TN / Other"]

    confirmed_assumptions: list[str] = Field(default_factory=list)
    # Assumptions the user explicitly confirmed during intake

    corrected_assumptions: list[str] = Field(default_factory=list)
    # Assumptions the user corrected — propagated into the research prompt

    open_questions: list[str] = Field(default_factory=list)
    # Things the user said they don't know yet — treated as open variables by research models

    session_title: Optional[str] = None
    # Short descriptive title for the session, e.g. "H-1B Transfer — Job Change Risk Analysis"

    output_intent: Optional[str] = None
    # What the user wants to walk away with, e.g. "A clear recommendation — tell me what to do"
