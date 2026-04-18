"""
backend/models/resilient_caller.py

Generic retry + fallback wrapper for all model calls.
All function names are role-based — no model names in signatures.
"""

import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

RETRYABLE_PATTERNS = [
    "503", "429", "rate limit", "unavailable",
    "overloaded", "capacity", "too many requests",
]


def is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(pattern in msg for pattern in RETRYABLE_PATTERNS)


def call_with_retry(
    fn: Callable,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    role: str = "unknown",
) -> Any:
    """
    Call fn with exponential backoff retry on retryable errors.
    Raises last exception after max_attempts exhausted.
    Non-retryable errors raise immediately.
    """
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            if is_retryable(exc):
                last_exc = exc
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"{role}: attempt {attempt + 1}/{max_attempts} failed "
                    f"({exc.__class__.__name__}: {exc}). "
                    f"Retrying in {delay}s..."
                )
                if attempt < max_attempts - 1:
                    time.sleep(delay)
                continue
            raise  # Non-retryable — raise immediately
    raise RuntimeError(
        f"{role}: unavailable after {max_attempts} attempts"
    ) from last_exc


def call_with_fallback(
    primary_fn: Callable,
    fallback_fns: list,
    emergency_fn: Optional[Callable] = None,
    role: str = "unknown",
    primary_attempts: int = 3,
    fallback_attempts: int = 2,
) -> Any:
    """
    Try primary_fn with retries, then each fallback_fn with retries.
    If all fail and emergency_fn provided, call it (no retry, never raises).
    If all fail and no emergency_fn, raise last exception.

    Returns (result, label) where label is "primary", "fallback1", etc.
    """
    fns_and_labels = (
        [(primary_fn, "primary")] +
        [(fn, f"fallback{i+1}") for i, fn in enumerate(fallback_fns)]
    )

    last_exc = None
    for fn, label in fns_and_labels:
        attempts = primary_attempts if label == "primary" else fallback_attempts
        try:
            result = call_with_retry(fn, max_attempts=attempts, role=f"{role}/{label}")
            if label != "primary":
                logger.info(f"{role}: succeeded on {label}")
            return result, label  # Return result AND which label was used
        except Exception as exc:
            logger.warning(f"{role}: {label} exhausted — {exc}")
            last_exc = exc
            continue

    if emergency_fn:
        logger.warning(f"{role}: all providers failed — using emergency fallback")
        return emergency_fn(), "emergency"

    raise RuntimeError(f"{role}: all providers failed") from last_exc
