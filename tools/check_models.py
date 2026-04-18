#!/usr/bin/env python3
"""
tools/check_models.py

CLI tool for checking model currency against provider APIs.

Usage:
    python -m tools.check_models           # check all models
    python -m tools.check_models --fix     # show suggested .env updates

Run weekly or before any model config change.
"""

import sys
from pathlib import Path

# Load backend/.env
env_path = Path(__file__).parent.parent / "backend" / ".env"
if env_path.exists():
    import os
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from backend.models.model_validator import validate_model_config
from backend.models.model_config import (
    get_executor_model, get_advisor_model, get_all_labs
)


def run_check(show_fix: bool = False):
    print("\n" + "=" * 60)
    print("ai-roundtable — Model Currency Check")
    print("=" * 60)

    print("\nValidating configured model IDs against provider APIs...")
    warnings = validate_model_config()

    if not warnings:
        print("\n✅ All configured model IDs are current.")
    else:
        print(f"\n⚠️  {len(warnings)} stale model ID(s) found:\n")
        for w in warnings:
            print(f"  • {w}")

    # Show current tier matrix
    print("\n" + "-" * 60)
    print("Current Research Tier Matrix")
    print("-" * 60)

    for tier in ["smart", "deep"]:
        print(f"\n{tier.upper()} tier:")
        for lab in get_all_labs():
            executor = get_executor_model(tier, lab)
            advisor  = get_advisor_model(tier, lab)
            if tier == "deep" or executor == advisor:
                print(f"  {lab:8} {executor}")
            else:
                print(f"  {lab:8} executor={executor}")
                print(f"  {lab:8} advisor ={advisor}")

    if show_fix and warnings:
        print("\n" + "-" * 60)
        print("Suggested .env updates")
        print("-" * 60)
        for w in warnings:
            if "role: " in w:
                role = w.split("role: ")[1].split(")")[0]
                print(f"  {role.upper()}=<new-model-id>")

    print()


if __name__ == "__main__":
    show_fix = "--fix" in sys.argv
    run_check(show_fix=show_fix)
