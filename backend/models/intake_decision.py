"""
backend/models/intake_decision.py

Pydantic schema for the structured JSON response from intake.
Used to enforce typed output from all intake providers.
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class IntakeDecision(BaseModel):
    needs_clarification: bool
    clarifying_question: Optional[str] = None  # only when needs_clarification is True
    optimized_prompt: str        # refined, context-enriched version of user's raw prompt
    tier: Literal["smart"]       # intake always returns smart; user controls via UI
    output_type: str             # e.g. "report", "plan", "decision", "brainstorm", "analysis"
    reasoning: str               # one sentence shown in UI

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

    confirmed_assumptions: list[str] = Field(default_factory=list)
    # Assumptions the user explicitly confirmed during intake

    corrected_assumptions: list[str] = Field(default_factory=list)
    # Assumptions the user corrected — propagated into the research prompt

    open_questions: list[str] = Field(default_factory=list)
    # Things the user said they don't know yet — treated as open variables by research models

    session_title: str = ""
    # Short descriptive title for the session, e.g. "H-1B Transfer — Job Change Risk Analysis"
