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
    synthesis_routed:    str  = "primary"  # primary | fallback
    panel_fallback:      bool = False      # router failed → default four seats
    panel_degraded_seats: list = field(default_factory=list)
    panel_repaired_seats: list = field(default_factory=list)
    # labs whose seat was valid only after the repair call
    # labs whose seat answered but not in the JSON shape (kept as plain text)

    def summary(self) -> str:
        """One-line summary for logging."""
        degraded = []
        if self.intake_degraded:
            degraded.append("intake")
        if self.factcheck_degraded:
            degraded.append("factcheck")
        if self.panel_fallback:
            degraded.append("panel_router")
        unavailable = [
            lab for lab, status in self.research_models.items()
            if status == "unavailable"
        ]
        if unavailable:
            degraded.append(f"research({','.join(unavailable)})")
        status = "degraded" if degraded else "healthy"
        line = f"Pipeline {status}: synthesis={self.synthesis_routed}"
        if self.panel_repaired_seats:
            line += f" repaired={','.join(self.panel_repaired_seats)}"
        if self.panel_degraded_seats:
            line += f" degraded={','.join(self.panel_degraded_seats)}"
        return line

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
        if self.panel_fallback:
            lines.append("ℹ️ Panel router unavailable — used the default four seats")
        for lab in self.panel_repaired_seats:
            lines.append(f"ℹ️ {lab.capitalize()} needed a format repair — shown as normal")
        for lab in self.panel_degraded_seats:
            lines.append(f"ℹ️ {lab.capitalize()} did not return structured output — shown as plain text")
        if self.factcheck_degraded:
            lines.append(f"⚠️ Perplexity unavailable — used {self.factcheck_model}")
        if self.synthesis_routed == "fallback":
            lines.append("⚠️ Synthesis used fallback model")
        return lines
