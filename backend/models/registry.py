"""
backend/models/registry.py

Role-based model selection. Roles declare requirements (vendor, tiers,
capabilities); model IDs live in model_registry.json. resolve() picks one
approved model per role. Spec: docs/MODEL_REGISTRY_SPEC.md.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path(__file__).with_name("model_registry.json")

VENDORS = ("anthropic", "openai", "google", "xai", "perplexity", "openrouter")
TIERS = ("fast", "balanced", "frontier")
STATUSES = ("approved", "candidate", "disabled")


class RegistryError(ValueError):
    pass


def parse_date(value) -> Optional[date]:
    """Accept None, a date, a datetime, or an ISO date/datetime string."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    data = json.loads(Path(path).read_text())
    validate_registry(data)
    return data


def validate_registry(data: dict) -> None:
    """Raise RegistryError listing every problem found."""
    errors = []
    for key in ("retirement_buffer_days", "warning_window_days"):
        if not isinstance(data.get(key), int):
            errors.append(f"{key} must be an integer")

    seen = set()
    for m in data.get("models", []):
        mid = m.get("id")
        if not mid:
            errors.append(f"model without id: {m}")
            continue
        if mid in seen:
            errors.append(f"duplicate model id {mid!r}")
        seen.add(mid)
        if m.get("vendor") not in VENDORS:
            errors.append(f"{mid}: unknown vendor {m.get('vendor')!r}")
        if m.get("status") not in STATUSES:
            errors.append(f"{mid}: unknown status {m.get('status')!r}")
        if m.get("tier") is not None and m.get("tier") not in TIERS:
            errors.append(f"{mid}: unknown tier {m.get('tier')!r}")
        if m.get("status") == "approved":
            if m.get("tier") is None:
                errors.append(f"{mid}: approved models need a tier")
            if not isinstance(m.get("rank"), int):
                errors.append(f"{mid}: approved models need an integer rank")
        try:
            parse_date(m.get("retires_at"))
        except ValueError:
            errors.append(f"{mid}: retires_at is not an ISO date: {m.get('retires_at')!r}")

    roles = data.get("roles", {})
    for name, spec in roles.items():
        if spec.get("vendor") not in VENDORS:
            errors.append(f"role {name}: unknown vendor {spec.get('vendor')!r}")
        tiers = spec.get("tiers") or []
        if not tiers or any(t not in TIERS for t in tiers):
            errors.append(f"role {name}: tiers must be a non-empty list of {TIERS}")
        if not spec.get("env"):
            errors.append(f"role {name}: missing env override name")
        for other in spec.get("distinct_from", []):
            if other not in roles:
                errors.append(f"role {name}: distinct_from references unknown role {other!r}")
    try:
        _resolution_order(roles)
    except RegistryError as exc:
        errors.append(str(exc))

    if errors:
        raise RegistryError("; ".join(errors))


def _resolution_order(roles: dict) -> list:
    """Roles ordered so every distinct_from target resolves first."""
    order, done = [], set()
    pending = list(roles)
    while pending:
        progressed = False
        for name in list(pending):
            deps = [d for d in roles[name].get("distinct_from", []) if d in roles]
            if all(d in done for d in deps):
                order.append(name)
                done.add(name)
                pending.remove(name)
                progressed = True
        if not progressed:
            raise RegistryError(f"distinct_from cycle among roles {sorted(pending)}")
    return order


def env_overrides(registry: dict, environ=os.environ) -> dict:
    """Per-role env overrides that are set and non-blank."""
    overrides = {}
    for name, spec in registry["roles"].items():
        value = (environ.get(spec["env"]) or "").strip()
        if value:
            overrides[name] = value
    return overrides


@dataclass
class Resolution:
    models: dict = field(default_factory=dict)    # role -> model id, or None if unresolved
    sources: dict = field(default_factory=dict)   # role -> "registry" | "override" | "unresolved"
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def fingerprint(self) -> str:
        """Short stable hash of the role → model map, for tying sessions to models."""
        payload = json.dumps(sorted(self.models.items()), default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:8]

    def format_table(self) -> str:
        width = max((len(r) for r in self.models), default=10)
        lines = [f"Model registry resolution [{self.fingerprint()}]"]
        for role in sorted(self.models):
            lines.append(f"  {role:<{width}}  {self.models[role] or '—':<32} {self.sources[role]}")
        return "\n".join(lines)


def resolve(
    registry: dict,
    availability: Optional[dict] = None,
    overrides: Optional[dict] = None,
    today: Optional[date] = None,
) -> Resolution:
    """
    Pick one model per role.

    availability: {vendor: {"available": set(ids), "retires": {id: date}}} from
        discovery. A vendor absent from the dict is treated as unknown — its
        models are not filtered by availability.
    overrides: {role: model_id}; an override always wins.
    """
    availability = availability or {}
    overrides = overrides or {}
    today = today or date.today()
    buffer_days = registry["retirement_buffer_days"]
    warning_days = registry["warning_window_days"]
    result = Resolution()

    def retires_on(model_id: str, vendor: str, curated) -> Optional[date]:
        dates = [parse_date(curated)]
        dates.append((availability.get(vendor) or {}).get("retires", {}).get(model_id))
        dates = [d for d in dates if d]
        return min(dates) if dates else None

    def days_left(d: Optional[date]) -> Optional[int]:
        return None if d is None else (d - today).days

    by_id = {m["id"]: m for m in registry["models"]}
    roles = registry["roles"]
    for name in _resolution_order(roles):
        spec = roles[name]
        vendor = spec["vendor"]
        known = availability.get(vendor)

        if name in overrides:
            model_id = overrides[name]
            if known and model_id not in known["available"]:
                result.warnings.append(f"{name}: override {model_id!r} is not listed by {vendor}")
            left = days_left(retires_on(model_id, vendor, (by_id.get(model_id) or {}).get("retires_at")))
            if left is not None and left <= warning_days:
                result.warnings.append(f"{name}: override {model_id!r} retires in {left} days")
            result.models[name], result.sources[name] = model_id, "override"
            continue

        excluded = {result.models.get(other) for other in spec.get("distinct_from", [])}
        required = set(spec.get("capabilities", []))
        eligible, retiring = [], []
        for m in registry["models"]:
            if (m["vendor"] != vendor or m["status"] != "approved"
                    or m["tier"] not in spec["tiers"] or m["id"] in excluded
                    or not required <= set(m.get("capabilities", []))):
                continue
            if known and m["id"] not in known["available"]:
                result.warnings.append(f"{name}: approved model {m['id']!r} is not listed by {vendor}; skipped")
                continue
            left = days_left(retires_on(m["id"], vendor, m.get("retires_at")))
            (retiring if left is not None and left <= buffer_days else eligible).append((m, left))

        pool = eligible
        if not pool and retiring:
            pool = retiring
            result.errors.append(
                f"{name}: only models inside the {buffer_days}-day retirement buffer remain; "
                f"using one until the registry is updated"
            )
        if not pool:
            result.models[name], result.sources[name] = None, "unresolved"
            result.errors.append(f"{name}: no approved {vendor} model in tiers {spec['tiers']}")
            continue

        model, left = min(pool, key=lambda pair: (spec["tiers"].index(pair[0]["tier"]), -pair[0]["rank"]))
        if left is not None and left <= warning_days:
            result.warnings.append(f"{name}: {model['id']!r} retires in {left} days")
        result.models[name], result.sources[name] = model["id"], "registry"

    for message in result.errors:
        logger.error("[registry] %s", message)
    for message in result.warnings:
        logger.warning("[registry] %s", message)
    return result
