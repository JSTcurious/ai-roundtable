"""
backend/models/model_validator.py

Startup model check. Discovery and resolution happen once, when
model_config is imported (see registry.py and discovery.py); this returns
that resolution's errors and warnings without calling provider APIs again.
For the full report against live provider lists: python -m tools.check_models
"""


def validate_model_config() -> list:
    """Registry resolution errors and warnings, as strings. Never raises."""
    from backend.models.model_config import RESOLUTION
    return list(RESOLUTION.errors) + list(RESOLUTION.warnings)
