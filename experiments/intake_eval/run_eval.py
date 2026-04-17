"""
experiments/intake_eval/run_eval.py

Intake Model Evaluation Harness — token counting and automated scoring.
========================================================================
Tests five candidate intake models across six scenarios:
  - clarification detection
  - proper noun preservation
  - tier assignment accuracy
  - two-turn consistency
  - cross-run stability

Candidates:
    - Gemini 2.5 Flash  (Google)     — current production model
    - Gemini 2.0 Flash  (Google)     — previous generation baseline
    - GPT-4o Mini       (OpenAI)     — cost-efficient cross-provider check
    - Claude Haiku 4.5  (Anthropic)  — Anthropic's cost tier
    - Qwen 2.5 72B      (OpenRouter) — open-weight cost baseline

Usage:
    cd /path/to/ai-roundtable
    python -m experiments.intake_eval.run_eval

Requirements:
    API keys in backend/.env:
        GOOGLE_API_KEY     — required for Gemini candidates
        OPENAI_API_KEY     — required for GPT-4o Mini
        ANTHROPIC_API_KEY  — required for Claude Haiku 4.5
        OPENROUTER_API_KEY — required for Qwen 2.5 72B
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# ── Load .env ─────────────────────────────────────────────────────────────────
env_path = Path(__file__).parent.parent.parent / "backend" / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

repo_root = Path(__file__).parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from experiments.intake_eval.prompts import (  # noqa: E402
    INTAKE_SYSTEM_PROMPT, INTAKE_TESTS,
)

# ── Candidate registry ────────────────────────────────────────────────────────

INTAKE_CANDIDATES = {
    "Gemini-2.5-Flash": {
        "provider":    "google",
        "model":       "gemini-2.5-flash",
        "input_rate":  0.15,
        "output_rate": 0.60,
        "label":       "Gemini 2.5 Flash (Google)",
    },
    "Gemini-2.0-Flash": {
        "provider":    "google",
        "model":       "gemini-2.0-flash",
        "input_rate":  0.10,
        "output_rate": 0.40,
        "label":       "Gemini 2.0 Flash (Google)",
    },
    "GPT-4o-Mini": {
        "provider":    "openai",
        "model":       "gpt-4o-mini",
        "input_rate":  0.15,
        "output_rate": 0.60,
        "label":       "GPT-4o Mini (OpenAI)",
    },
    "Claude-Haiku-4-5": {
        "provider":    "anthropic",
        "model":       "claude-haiku-4-5-20251001",
        "input_rate":  0.80,
        "output_rate": 4.00,
        "label":       "Claude Haiku 4.5 (Anthropic)",
    },
    "Qwen-2.5-72B": {
        "provider":    "openrouter",
        "model":       "qwen/qwen-2.5-72b-instruct",
        "input_rate":  0.40,
        "output_rate": 1.20,
        "label":       "Qwen 2.5 72B (OpenRouter)",
    },
}


def _check_availability():
    available = {}
    google_ok     = False
    openai_ok     = False
    anthropic_ok  = False
    openrouter_ok = False

    try:
        from google import genai as _g  # noqa: F401
        if os.environ.get("GOOGLE_API_KEY"):
            google_ok = True
        else:
            print("GOOGLE_API_KEY not set — skipping Gemini candidates")
    except ImportError:
        print("google-genai SDK not installed — skipping Gemini candidates")

    try:
        import openai  # noqa: F401
        if os.environ.get("OPENAI_API_KEY"):
            openai_ok = True
        else:
            print("OPENAI_API_KEY not set — skipping GPT-4o Mini")
    except ImportError:
        print("openai SDK not installed — skipping GPT-4o Mini")

    try:
        import anthropic  # noqa: F401
        if os.environ.get("ANTHROPIC_API_KEY"):
            anthropic_ok = True
        else:
            print("ANTHROPIC_API_KEY not set — skipping Claude Haiku 4.5")
    except ImportError:
        print("anthropic SDK not installed — skipping Claude Haiku 4.5")

    if os.environ.get("OPENROUTER_API_KEY"):
        openrouter_ok = True
    else:
        print("OPENROUTER_API_KEY not set — skipping Qwen 2.5 72B")

    for key, cfg in INTAKE_CANDIDATES.items():
        p = cfg["provider"]
        if p == "google" and google_ok:
            available[key] = cfg
        elif p == "openai" and openai_ok:
            available[key] = cfg
        elif p == "anthropic" and anthropic_ok:
            available[key] = cfg
        elif p == "openrouter" and openrouter_ok:
            available[key] = cfg

    return available


AVAILABLE_CANDIDATES = _check_availability()

# ── Cost helpers ──────────────────────────────────────────────────────────────

def calculate_cost(input_tokens: int, output_tokens: int,
                   input_rate: float, output_rate: float) -> float:
    return (input_tokens / 1_000_000) * input_rate + \
           (output_tokens / 1_000_000) * output_rate

# ── API call functions ─────────────────────────────────────────────────────────
# Each returns {"parsed": dict | None, "raw_text": str,
#               "input_tokens": int, "output_tokens": int}

def call_google_intake(prompt: str, model: str) -> dict:
    from google import genai
    from google.genai import types
    import json as _json

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        system_instruction=INTAKE_SYSTEM_PROMPT,
        max_output_tokens=512,
    )
    response = client.models.generate_content(
        model=model,
        contents=[types.Content(
            role="user",
            parts=[types.Part(text=prompt)]
        )],
        config=config,
    )
    raw = response.text or ""
    try:
        parsed = _json.loads(raw)
    except Exception:
        parsed = None

    usage = response.usage_metadata
    return {
        "parsed":        parsed,
        "raw_text":      raw,
        "input_tokens":  getattr(usage, "prompt_token_count", 0),
        "output_tokens": getattr(usage, "candidates_token_count", 0),
    }


def call_openai_intake(prompt: str, model: str) -> dict:
    import openai
    import json as _json

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=model,
        max_tokens=512,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": INTAKE_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    )
    raw = response.choices[0].message.content or ""
    try:
        parsed = _json.loads(raw)
    except Exception:
        parsed = None

    return {
        "parsed":        parsed,
        "raw_text":      raw,
        "input_tokens":  response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


def call_anthropic_intake(prompt: str, model: str) -> dict:
    import anthropic
    import json as _json

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    # Ask Claude to return only JSON
    system = INTAKE_SYSTEM_PROMPT + (
        "\n\nCRITICAL: Return ONLY the JSON object. "
        "No preamble, no markdown fences, no trailing text."
    )
    response = client.messages.create(
        model=model,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text or ""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = _json.loads(text.strip())
    except Exception:
        parsed = None

    return {
        "parsed":        parsed,
        "raw_text":      raw,
        "input_tokens":  response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def call_openrouter_intake(prompt: str, model: str) -> dict:
    import httpx
    import json as _json

    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": INTAKE_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
    }
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data   = response.json()
    raw    = data["choices"][0]["message"]["content"] or ""
    usage  = data.get("usage", {})
    try:
        parsed = _json.loads(raw)
    except Exception:
        parsed = None

    return {
        "parsed":        parsed,
        "raw_text":      raw,
        "input_tokens":  usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }


def call_candidate(candidate_key: str, prompt: str) -> dict:
    cfg = INTAKE_CANDIDATES[candidate_key]
    if cfg["provider"] == "google":
        return call_google_intake(prompt, cfg["model"])
    elif cfg["provider"] == "openai":
        return call_openai_intake(prompt, cfg["model"])
    elif cfg["provider"] == "anthropic":
        return call_anthropic_intake(prompt, cfg["model"])
    elif cfg["provider"] == "openrouter":
        return call_openrouter_intake(prompt, cfg["model"])
    else:
        return {"parsed": None, "raw_text": f"[Unknown provider: {cfg['provider']}]",
                "input_tokens": 0, "output_tokens": 0}

# ── Scoring ───────────────────────────────────────────────────────────────────

def score_intake_result(parsed: dict | None, assertions: list,
                        turn: int = 0) -> list[dict]:
    """
    Evaluate a parsed IntakeDecision against a list of assertion specs.
    Returns list of {name, expected, actual, pass, note}.
    """
    if parsed is None:
        # Parsing failed — all assertions fail
        return [
            {"name": a["name"], "expected": a.get("expected"), "actual": None,
             "pass": False, "note": "JSON parse error"}
            for a in assertions
            if a.get("turn", 0) == turn
        ]

    results = []
    for a in assertions:
        if a.get("turn", 0) != turn:
            continue

        field    = a["field"]
        expected = a.get("expected")
        check    = a["check"]
        actual   = parsed.get(field)
        note     = a.get("note", "")

        if check == "equals":
            passed = actual == expected
            results.append({"name": a["name"], "expected": expected,
                             "actual": actual, "pass": passed, "note": note})

        elif check == "nonempty":
            passed = isinstance(actual, str) and len(actual.strip()) > 0
            results.append({"name": a["name"], "expected": "non-empty string",
                             "actual": (actual or "")[:80], "pass": passed,
                             "note": note})

        elif check == "contains":
            passed = isinstance(actual, str) and expected in actual
            results.append({"name": a["name"], "expected": f"contains '{expected}'",
                             "actual": (actual or "")[:120], "pass": passed,
                             "note": note})

        elif check == "not_contains":
            passed = isinstance(actual, str) and expected not in actual
            results.append({"name": a["name"], "expected": f"does NOT contain '{expected}'",
                             "actual": (actual or "")[:120], "pass": passed,
                             "note": note})

        elif check == "single_question":
            # Rough check: no more than 2 question marks in the clarifying question
            cq    = actual or ""
            count = cq.count("?")
            passed = 0 < count <= 2
            results.append({"name": a["name"], "expected": "1-2 question marks",
                             "actual": f"{count} '?' found in: {cq[:80]}",
                             "pass": passed, "note": note})

    return results


def score_consistency(runs: list[dict | None]) -> dict:
    """
    Given a list of parsed results from multiple runs, check that the
    'tier' field is the same across all runs.
    Returns {stable: bool, tiers: list, majority_tier: str}.
    """
    tiers = []
    for r in runs:
        if r is not None:
            tiers.append(r.get("tier", None))
        else:
            tiers.append(None)

    unique = set(t for t in tiers if t is not None)
    stable = len(unique) == 1 and None not in tiers
    majority = max(set(tiers), key=tiers.count) if tiers else None
    return {"stable": stable, "tiers": tiers, "majority_tier": majority}

# ── Main evaluation ───────────────────────────────────────────────────────────

def run_evaluation():
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    print(f"\n{'='*60}")
    print("Intake Model Evaluation Harness — with cost analysis")
    print(f"Candidates: {len(AVAILABLE_CANDIDATES)}")
    print(f"Tests:      {len(INTAKE_TESTS)}")
    print(f"{'='*60}\n")

    if not AVAILABLE_CANDIDATES:
        print("No candidates available. Check API keys in backend/.env.")
        return

    cost_data: dict = {}
    all_results: dict = {}

    for candidate_key, cfg in AVAILABLE_CANDIDATES.items():
        print(f"\n── {cfg['label']} ──")
        candidate_dir = results_dir / candidate_key
        candidate_dir.mkdir(exist_ok=True)

        all_results[candidate_key]   = {}
        total_input_tokens  = 0
        total_output_tokens = 0
        total_cost          = 0.0
        total_assertions    = 0
        total_passes        = 0

        for test in INTAKE_TESTS:
            test_id = test["id"]
            runs_n  = test.get("runs", 1)

            print(f"  Running {test_id}...", end=" ", flush=True)

            # ── Test 6: consistency across multiple runs ──────────────────────
            if runs_n > 1:
                run_results   = []
                run_tokens_in = []
                run_tokens_out= []
                all_ok        = True
                start         = time.time()

                for run_idx in range(runs_n):
                    try:
                        r = call_candidate(candidate_key, test["prompt"])
                        run_results.append(r["parsed"])
                        run_tokens_in.append(r["input_tokens"])
                        run_tokens_out.append(r["output_tokens"])
                    except Exception as e:
                        run_results.append(None)
                        run_tokens_in.append(0)
                        run_tokens_out.append(0)
                        all_ok = False
                    if run_idx < runs_n - 1:
                        time.sleep(2)

                elapsed       = round(time.time() - start, 1)
                input_tokens  = sum(run_tokens_in)
                output_tokens = sum(run_tokens_out)
                consistency   = score_consistency(run_results)
                status        = "✓" if all_ok else "✗"

                test_cost = calculate_cost(input_tokens, output_tokens,
                                           cfg["input_rate"], cfg["output_rate"])
                total_input_tokens  += input_tokens
                total_output_tokens += output_tokens
                total_cost          += test_cost

                assertion_result = {
                    "name":      "tier_stable",
                    "expected":  "same tier on all 3 runs",
                    "actual":    str(consistency["tiers"]),
                    "pass":      consistency["stable"],
                    "note":      f"majority tier: {consistency['majority_tier']}",
                }
                total_assertions += 1
                if consistency["stable"]:
                    total_passes += 1

                print(f"{status} ({elapsed}s | {input_tokens}in+{output_tokens}out "
                      f"| ${test_cost:.5f}) — tier stable: {consistency['stable']} "
                      f"{consistency['tiers']}")

                all_results[candidate_key][test_id] = {
                    "runs":              [r for r in run_results],
                    "consistency":       consistency,
                    "assertion":         assertion_result,
                    "input_tokens":      input_tokens,
                    "output_tokens":     output_tokens,
                    "cost":              round(test_cost, 6),
                    "status":            status,
                    "elapsed":           elapsed,
                }

                # Write result file
                result_path = candidate_dir / f"{test_id}.md"
                with open(result_path, "w") as f:
                    f.write(f"# {cfg['label']} — {test['name']}\n\n")
                    f.write(f"**Generated:** {timestamp}\n")
                    f.write(f"**Elapsed:** {elapsed}s ({runs_n} runs)\n")
                    f.write(f"**Tokens:** {input_tokens} input / "
                            f"{output_tokens} output (total)\n")
                    f.write(f"**Cost:** ${test_cost:.6f}\n\n")
                    f.write("## Consistency Check\n\n")
                    icon = "✓" if consistency["stable"] else "✗"
                    f.write(f"- {icon} Tier stable across {runs_n} runs: "
                            f"{consistency['tiers']}\n")
                    f.write(f"- Majority tier: **{consistency['majority_tier']}**\n\n")
                    f.write("## Raw Outputs per Run\n\n")
                    for i, r in enumerate(run_results):
                        f.write(f"### Run {i+1}\n\n")
                        f.write("```json\n")
                        f.write(json.dumps(r, indent=2) if r else "(parse error)")
                        f.write("\n```\n\n")

                time.sleep(1)
                continue

            # ── Single-turn or two-turn tests ────────────────────────────────
            try:
                start  = time.time()
                turn0  = call_candidate(candidate_key, test["prompt"])
                elapsed = round(time.time() - start, 1)
                status  = "✓"
                input_tokens  = turn0["input_tokens"]
                output_tokens = turn0["output_tokens"]
            except Exception as e:
                turn0   = {"parsed": None, "raw_text": f"[ERROR: {e}]",
                           "input_tokens": 0, "output_tokens": 0}
                elapsed = 0.0
                status  = "✗"
                input_tokens  = 0
                output_tokens = 0

            turn1 = None
            if test.get("turn2_input") and (
                turn0["parsed"] is not None and
                turn0["parsed"].get("needs_clarification") is True
            ):
                # Build combined Turn 1 prompt (mirrors backend/intake.py)
                cq = (turn0["parsed"].get("clarifying_question") or
                      "(no question returned)")
                combined = (
                    f"Original prompt: {test['prompt']}\n"
                    f"Clarifying question asked: {cq}\n"
                    f"User's answer: {test['turn2_input']}\n\n"
                    "Now return the final IntakeDecision with "
                    "needs_clarification: false. "
                    "IMPORTANT: The optimized_prompt must preserve all proper "
                    "nouns from the original prompt exactly as written. Do not "
                    "substitute model names, product names, or version numbers."
                )
                try:
                    time.sleep(1)
                    turn1 = call_candidate(candidate_key, combined)
                    input_tokens  += turn1["input_tokens"]
                    output_tokens += turn1["output_tokens"]
                except Exception as e:
                    turn1 = {"parsed": None, "raw_text": f"[ERROR: {e}]",
                             "input_tokens": 0, "output_tokens": 0}

            test_cost = calculate_cost(input_tokens, output_tokens,
                                       cfg["input_rate"], cfg["output_rate"])
            total_input_tokens  += input_tokens
            total_output_tokens += output_tokens
            total_cost          += test_cost

            # Score assertions
            assertions = test["assertions"]
            turn0_results = score_intake_result(turn0["parsed"], assertions, turn=0)
            turn1_results = []
            if turn1 is not None:
                turn1_results = score_intake_result(
                    turn1["parsed"], assertions, turn=1
                )

            all_assertion_results = turn0_results + turn1_results
            test_passes = sum(1 for a in all_assertion_results if a["pass"])
            test_total  = len(all_assertion_results)
            total_assertions += test_total
            total_passes     += test_passes

            pct = int(test_passes / test_total * 100) if test_total else 0
            print(f"{status} ({elapsed}s | {input_tokens}in+{output_tokens}out "
                  f"| ${test_cost:.5f}) — {test_passes}/{test_total} assertions")

            all_results[candidate_key][test_id] = {
                "turn0":          turn0["parsed"],
                "turn1":          turn1["parsed"] if turn1 else None,
                "assertions":     all_assertion_results,
                "passes":         test_passes,
                "total":          test_total,
                "input_tokens":   input_tokens,
                "output_tokens":  output_tokens,
                "cost":           round(test_cost, 6),
                "status":         status,
                "elapsed":        elapsed,
            }

            # Write result file
            result_path = candidate_dir / f"{test_id}.md"
            with open(result_path, "w") as f:
                f.write(f"# {cfg['label']} — {test['name']}\n\n")
                f.write(f"**Generated:** {timestamp}\n")
                f.write(f"**Description:** {test['description']}\n")
                f.write(f"**Elapsed:** {elapsed}s\n")
                f.write(f"**Tokens:** {input_tokens} input / "
                        f"{output_tokens} output\n")
                f.write(f"**Cost:** ${test_cost:.6f}\n\n")
                f.write(f"## Assertions — {test_passes}/{test_total} passed\n\n")
                for ar in all_assertion_results:
                    icon = "✓" if ar["pass"] else "✗"
                    f.write(f"- {icon} **{ar['name']}**  \n")
                    f.write(f"  Expected: `{ar['expected']}`  \n")
                    f.write(f"  Actual: `{ar['actual']}`")
                    if ar.get("note"):
                        f.write(f"  _{ar['note']}_")
                    f.write("\n\n")
                f.write("## Turn 0 Output\n\n```json\n")
                f.write(json.dumps(turn0["parsed"], indent=2)
                        if turn0["parsed"] else turn0["raw_text"])
                f.write("\n```\n\n")
                if turn1 is not None:
                    f.write("## Turn 1 Output\n\n```json\n")
                    f.write(json.dumps(turn1["parsed"], indent=2)
                            if turn1["parsed"] else turn1["raw_text"])
                    f.write("\n```\n\n")

            time.sleep(1)

        # Per-candidate cost summary
        avg_in  = total_input_tokens  / max(len(INTAKE_TESTS), 1)
        avg_out = total_output_tokens / max(len(INTAKE_TESTS), 1)
        per_session_cost = calculate_cost(avg_in, avg_out,
                                          cfg["input_rate"], cfg["output_rate"])
        overall_pct = (total_passes / total_assertions * 100
                       if total_assertions else 0)

        cost_data[candidate_key] = {
            "label":               cfg["label"],
            "model":               cfg["model"],
            "input_rate":          cfg["input_rate"],
            "output_rate":         cfg["output_rate"],
            "total_input_tokens":  total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost_6tests":   round(total_cost, 6),
            "avg_input_tokens":    round(avg_in, 1),
            "avg_output_tokens":   round(avg_out, 1),
            "assertion_pass_pct":  round(overall_pct, 1),
            "per_session_cost":    round(per_session_cost, 7),
            "100_sessions":        round(per_session_cost * 100, 4),
            "1k_sessions":         round(per_session_cost * 1_000, 3),
            "10k_sessions":        round(per_session_cost * 10_000, 2),
        }

        print(f"  ── Totals: {total_input_tokens} in / {total_output_tokens} out "
              f"| ${total_cost:.5f} for {len(INTAKE_TESTS)} tests")
        print(f"  ── Per session: ${per_session_cost:.7f} | "
              f"1K sessions: ${cost_data[candidate_key]['1k_sessions']:.3f}")
        print(f"  ── Assertions: {total_passes}/{total_assertions} "
              f"({overall_pct:.0f}%)")

    # ── Save cost_data.json ───────────────────────────────────────────────────
    cost_json_path = results_dir / f"cost_data-{timestamp}.json"
    with open(cost_json_path, "w") as f:
        json.dump({"timestamp": timestamp, "candidates": cost_data}, f, indent=2)

    # ── Write summary markdown ────────────────────────────────────────────────
    summary_path = results_dir / f"summary-{timestamp}.md"
    with open(summary_path, "w") as f:
        f.write("# Intake Model Evaluation Summary\n\n")
        f.write(f"**Date:** {timestamp}\n")
        f.write(f"**Candidates tested:** {len(AVAILABLE_CANDIDATES)}\n\n")

        f.write("## Results Matrix\n\n")
        header = "| Candidate |"
        sep    = "|-----------|"
        for test in INTAKE_TESTS:
            header += f" {test['id']} |"
            sep    += "---------|"
        header += " Assert% | $/session | $/1K |\n"
        sep    += "---------|----------|------|\n"
        f.write(header)
        f.write(sep)

        for ck in AVAILABLE_CANDIDATES:
            row = f"| {cost_data[ck]['label']} |"
            for test in INTAKE_TESTS:
                tr = all_results[ck].get(test["id"], {})
                s  = tr.get("status", "?")
                row += f" {s} |"
            cd = cost_data[ck]
            row += (f" {cd['assertion_pass_pct']}% |"
                    f" ${cd['per_session_cost']:.6f} |"
                    f" ${cd['1k_sessions']:.3f} |\n")
            f.write(row)

        f.write("\n## Cost Analysis\n\n")
        f.write("| Candidate | $/session | 100 sessions | 1K sessions | "
                "10K sessions |\n")
        f.write("|-----------|----------|-------------|------------|"
                "-------------|\n")
        for ck, cd in cost_data.items():
            f.write(f"| {cd['label']} | ${cd['per_session_cost']:.6f} | "
                    f"${cd['100_sessions']:.4f} | "
                    f"${cd['1k_sessions']:.3f} | "
                    f"${cd['10k_sessions']:.2f} |\n")

        f.write("\n## Assertion Detail by Test\n\n")
        for test in INTAKE_TESTS:
            f.write(f"### {test['name']}\n\n")
            f.write(f"_{test['description']}_\n\n")
            for ck in AVAILABLE_CANDIDATES:
                tr = all_results[ck].get(test["id"], {})
                f.write(f"**{cost_data[ck]['label']}**\n\n")
                if "assertions" in tr:
                    for ar in tr["assertions"]:
                        icon = "✓" if ar["pass"] else "✗"
                        f.write(f"- {icon} {ar['name']}: `{ar['actual']}`\n")
                elif "consistency" in tr:
                    c = tr["consistency"]
                    icon = "✓" if c["stable"] else "✗"
                    f.write(f"- {icon} tier stable: {c['stable']} "
                            f"— {c['tiers']}\n")
                f.write("\n")

        f.write("## Next Steps\n\n")
        f.write("1. Read per-candidate result files in `results/<candidate>/`\n")
        f.write("2. Review proper noun tests — any substitution is a fail\n")
        f.write("3. Document decision in `docs/decisions/003-intake-model-"
                "selection.md`\n")
        f.write(f"\nCost data JSON: {cost_json_path}\n")

    print(f"\n{'='*60}")
    print("Evaluation complete.")
    print(f"Results:   {results_dir}")
    print(f"Summary:   {summary_path}")
    print(f"Cost JSON: {cost_json_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_evaluation()
