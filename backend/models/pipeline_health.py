"""
backend/models/pipeline_health.py

PipelineHealth — tracks which model handled each pipeline stage in a session.

Accumulated throughout a session and sent to the frontend as
synthesis_annotations after session_complete. Only noteworthy events
are shown — healthy sessions produce no annotations.
"""

from dataclasses import dataclass, field


@dataclass
class PipelineHealth:
    """Tracks which model handled each pipeline stage in a session."""
    intake_model:        str  = "unknown"
    intake_degraded:     bool = False
    research_models:     dict = field(default_factory=dict)
    # {"gemini": "primary"|"fallback"|"unavailable", ...}
    factcheck_model:     str  = "unknown"
    factcheck_degraded:  bool = False
    synthesis_model:     str  = "unknown"
    synthesis_routed:    str  = "analytical"  # analytical | factual | *_fallback

    def summary(self) -> str:
        """One-line summary for logging."""
        degraded = []
        if self.intake_degraded:
            degraded.append("intake")
        if self.factcheck_degraded:
            degraded.append("factcheck")
        unavailable = [
            lab for lab, status in self.research_models.items()
            if status == "unavailable"
        ]
        if unavailable:
            degraded.append(f"research({','.join(unavailable)})")
        status = "degraded" if degraded else "healthy"
        return f"Pipeline {status}: synthesis={self.synthesis_routed}"

    def to_annotation(self) -> list:
        """
        Format as annotation lines for the read-only UI panel.
        Only shows noteworthy events — healthy sessions show nothing.
        """
        lines = []
        if self.intake_degraded:
            lines.append("⚠️ Intake fell back from primary model")
        for lab, status in self.research_models.items():
            if status == "unavailable":
                lines.append(f"⚠️ {lab.capitalize()} was unavailable this session")
            elif status == "fallback":
                lines.append(f"ℹ️ {lab.capitalize()} used fallback model")
        if self.factcheck_degraded:
            lines.append(f"⚠️ Perplexity unavailable — used {self.factcheck_model}")
        if "fallback" in self.synthesis_routed:
            lines.append("⚠️ Synthesis used fallback model")
        elif self.synthesis_routed == "factual":
            lines.append(
                "ℹ️ Synthesis routed to factual model — "
                "Perplexity data contradicted round-1 responses"
            )
        return lines
