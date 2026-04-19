"""
backend/models/intake_decision.py

Pydantic schema for the structured JSON response from Gemini Flash intake.
Used as the response_schema in call_gemini_intake() to enforce typed output.
"""

from typing import Literal, Optional

from pydantic import BaseModel


class IntakeDecision(BaseModel):
    needs_clarification: bool
    clarifying_question: Optional[str] = None  # only when needs_clarification is True
    optimized_prompt: str        # refined, context-enriched version of user's raw prompt
    tier: Literal["smart"]           # intake always returns smart; user controls via UI
    output_type: str             # e.g. "report", "plan", "decision", "brainstorm", "analysis"
    reasoning: str               # one sentence shown in UI:
                                 # "Deep selected — architecture decision with significant tradeoffs"
