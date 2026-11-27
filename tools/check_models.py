#!/usr/bin/env python3
"""
tools/check_models.py

Model registry report against live provider model lists.

Usage:
    python -m tools.check_models           # report; exit 1 if an in-use model is
                                           # retiring within the buffer, missing, or a role is unresolved
    python -m tools.check_models --write   # also add new provider models as candidates
                                           # and update retirement dates in model_registry.json

Run weekly (CI does) and before any registry change. Spec: docs/MODEL_REGISTRY_SPEC.md.
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / "backend" / ".env", override=False)

from backend.models.discovery import discover
from backend.models.registry import (
    REGISTRY_PATH,
    env_overrides,
    load_registry,
    parse_date,
    resolve,
    validate_registry,
)


def _matches(filters: dict, model_id: str) -> bool:
    return (any(re.search(p, model_id) for p in filters.get("include", []))
            and not any(re.search(p, model_id) for p in filters.get("exclude", [])))


def new_models(registry: dict, discovered: dict, today: date = None) -> dict:
    """{vendor: [ids]} listed by a provider, matching its filters, absent from the
    registry, and not already retiring within the warning window."""
    today = today or date.today()
    known = {m["id"] for m in registry["models"]}
    out = {}
    for vendor, data in discovered.items():
        filters = registry.get("discovery", {}).get(vendor)
        if not filters:
            continue
        def dying(mid):
            when = data["retires"].get(mid)
            return when is not None and (when - today).days <= registry["warning_window_days"]
        ids = sorted(mid for mid in data["models"]
                     if mid not in known and _matches(filters, mid) and not dying(mid))
        if ids:
            out[vendor] = ids
    return out


def _retires(model: dict, discovered: dict):
    dates = [parse_date(model.get("retires_at")),
             (discovered.get(model["vendor"]) or {}).get("retires", {}).get(model["id"])]
    dates = [d for d in dates if d]
    return min(dates) if dates else None


def build_report(registry: dict, discovered: dict, resolution, today: date = None):
    """Return (report text, exit code)."""
    today = today or date.today()
    buffer_days = registry["retirement_buffer_days"]
    warning_days = registry["warning_window_days"]
    in_use = {mid for mid in resolution.models.values() if mid}
    approved = [m for m in registry["models"] if m["status"] == "approved"]
    problems = []
    lines = [resolution.format_table(), ""]

    checked = sorted(discovered)
    lines.append(f"Provider lists checked: {', '.join(checked) or 'none'}")
    lines.append("")

    retiring = []
    for m in approved:
        when = _retires(m, discovered)
        if when and (when - today).days <= warning_days:
            days = (when - today).days
            retiring.append(f"  {m['id']} ({m['vendor']}) retires {when.isoformat()} — {days} days"
                            + (" — IN USE" if m["id"] in in_use else ""))
            if m["id"] in in_use and days <= buffer_days:
                problems.append(f"{m['id']} is in use and retires in {days} days")
    lines.append(f"Approved models retiring within {warning_days} days:")
    lines += retiring or ["  none"]
    lines.append("")

    missing = []
    for m in approved:
        data = discovered.get(m["vendor"])
        if data and m["id"] not in data["available"]:
            missing.append(f"  {m['id']} ({m['vendor']})" + (" — IN USE" if m["id"] in in_use else ""))
            if m["id"] in in_use:
                problems.append(f"{m['id']} is in use and missing from {m['vendor']}'s model list")
    lines.append("Approved models missing from provider lists:")
    lines += missing or ["  none"]
    lines.append("")

    fresh = new_models(registry, discovered, today)
    lines.append("New provider models not in the registry (add as candidates with --write):")
    lines += [f"  {vendor}: {', '.join(ids)}" for vendor, ids in sorted(fresh.items())] or ["  none"]

    problems += resolution.errors
    if resolution.warnings:
        lines += ["", "Resolver warnings:"] + [f"  {w}" for w in resolution.warnings]
    if problems:
        lines += ["", "PROBLEMS:"] + [f"  {p}" for p in problems]
    return "\n".join(lines), (1 if problems else 0)


def update_registry(registry: dict, discovered: dict, today: date = None):
    """Add new provider models as candidates and refresh retirement dates.
    Never changes the status of an existing entry. Returns (registry, changes)."""
    today = today or date.today()
    changes = []
    for m in registry["models"]:
        found = (discovered.get(m["vendor"]) or {}).get("retires", {}).get(m["id"])
        if found and found.isoformat() != m.get("retires_at"):
            changes.append(f"{m['id']}: retires_at {m.get('retires_at')} -> {found.isoformat()}")
            m["retires_at"] = found.isoformat()
    for vendor, ids in sorted(new_models(registry, discovered, today).items()):
        for mid in ids:
            when = discovered[vendor]["retires"].get(mid)
            registry["models"].append({
                "id": mid, "vendor": vendor, "tier": None, "rank": None,
                "status": "candidate", "capabilities": [],
                "retires_at": when.isoformat() if when else None,
                "notes": f"discovered {today.isoformat()}",
            })
            changes.append(f"{mid}: added as candidate ({vendor})")
    return registry, changes


def dump_registry(registry: dict) -> str:
    """Serialize with one model / role / vendor filter per line, so diffs stay readable."""
    def block(items, open_, close, fmt):
        return f"{open_}\n" + ",\n".join(fmt(i) for i in items) + f"\n  {close}"

    out = [
        "{",
        f'  "retirement_buffer_days": {json.dumps(registry["retirement_buffer_days"])},',
        f'  "warning_window_days": {json.dumps(registry["warning_window_days"])},',
        '  "models": ' + block(registry["models"], "[", "]",
                               lambda m: "    " + json.dumps(m, ensure_ascii=False)) + ",",
        '  "roles": ' + block(registry["roles"].items(), "{", "}",
                              lambda kv: f"    {json.dumps(kv[0])}: {json.dumps(kv[1])}") + ",",
        '  "discovery": ' + block(registry["discovery"].items(), "{", "}",
                                  lambda kv: f"    {json.dumps(kv[0])}: {json.dumps(kv[1])}"),
        "}",
    ]
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    registry = load_registry()
    discovered = discover(timeout=15)
    if "--write" in argv:
        registry, changes = update_registry(registry, discovered)
        validate_registry(registry)
        REGISTRY_PATH.write_text(dump_registry(registry))
        print("Registry updated:" if changes else "Registry already up to date.")
        for change in changes:
            print(f"  {change}")
        print()
    resolution = resolve(registry, availability=discovered, overrides=env_overrides(registry))
    text, code = build_report(registry, discovered, resolution)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
