"""
experiments/factcheck_eval/run_eval.py

Factcheck Model Evaluation Harness — 7 tests, 3 candidates.
=============================================================
Evaluates Perplexity Sonar Pro, Perplexity Sonar, and GPT-5.4 with web search
as candidates for the ai-roundtable fact-check role.

Usage:
    cd /path/to/ai-roundtable
    uv run python -m experiments.factcheck_eval.run_eval

Requirements:
    API keys in backend/.env:
        PERPLEXITY_API_KEY — required for Perplexity candidates
        OPENAI_API_KEY     — required for GPT-5.4-WebSearch
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# ── Load .env from backend/ ───────────────────────────────────────────────────
env_path = Path(__file__).parent.parent.parent / "backend" / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# ── Insert repo root for imports ──────────────────────────────────────────────
repo_root = Path(__file__).parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from experiments.factcheck_eval.prompts import (  # noqa: E402
    FACTCHECK_CANDIDATES,
    FACTCHECK_TESTS,
    score_factcheck_result,
)

# ── Availability check ────────────────────────────────────────────────────────

def _check_availability() -> dict:
    available = {}
    perplexity_ok = bool(os.environ.get("PERPLEXITY_API_KEY"))
    openai_ok = bool(os.environ.get("OPENAI_API_KEY"))

    if not perplexity_ok:
        print("PERPLEXITY_API_KEY not set — skipping Perplexity candidates")
    if not openai_ok:
        print("OPENAI_API_KEY not set — skipping GPT-5.4-WebSearch")

    for key, cfg in FACTCHECK_CANDIDATES.items():
        p = cfg["provider"]
        if p == "perplexity" and perplexity_ok:
            available[key] = cfg
        elif p == "openai_websearch" and openai_ok:
            available[key] = cfg

    return available


AVAILABLE_CANDIDATES = _check_availability()

# ── Cost helpers ──────────────────────────────────────────────────────────────

def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    input_rate: float,
    output_rate: float,
) -> float:
    """Return cost in USD given token counts and per-MTok rates."""
    return (
        (input_tokens  / 1_000_000) * input_rate +
        (output_tokens / 1_000_000) * output_rate
    )


def project_monthly(
    avg_input_tokens: float,
    avg_output_tokens: float,
    input_rate: float,
    output_rate: float,
) -> dict:
    """Project monthly factcheck cost at 100 / 1K / 10K sessions."""
    per_session = calculate_cost(
        avg_input_tokens, avg_output_tokens, input_rate, output_rate
    )
    return {
        "per_session":  per_session,
        "100_sessions":  round(per_session * 100,    4),
        "1k_sessions":   round(per_session * 1_000,  3),
        "10k_sessions":  round(per_session * 10_000, 2),
    }

# ── Audit prompt builders ─────────────────────────────────────────────────────

def _build_audit_prompt(round1_responses: dict, tier: str) -> str:
    """
    Build the factcheck audit prompt. Mirrors perplexity_client._build_audit_prompt.
    Smart: targeted/signal-focused. Deep: comprehensive/adversarial.
    No pre-research text in the eval — candidates must use live web search.
    """
    responses_block = "\n\n".join(
        f"### {model}\n{text}"
        for model, text in round1_responses.items()
    )

    base = f"""You are fact-checking AI model responses for accuracy and currency.

## Round-1 Responses to Audit
{responses_block}

## Pre-Research Context
(no pre-research available — use live web search)
"""

    if tier == "deep":
        return base + """
## Deep Audit Instructions

Be comprehensive and adversarial. Check everything.

1. Verify EVERY specific factual claim (prices, dates, model versions,
   statistics, named entities) across all model responses.
2. Map contradictions between models explicitly — when models disagree,
   state which is correct, why, and cite a source.
3. Research current practitioner consensus from live sources.
4. Identify which round-1 models were most reliable on this topic.
5. Flag your own confidence level on each correction.

Return all four sections with full depth. Do not abbreviate.
Cite specific sources for every correction — no vague references.

Sections required:
1. Facts That Are Outdated or Incorrect
2. Important Current Information Missing from Round-1
3. Tools or Frameworks Worth Highlighting
4. Current Practitioner Consensus
"""
    else:  # smart
        return base + """
## Smart Audit Instructions

Be targeted and signal-focused. Prioritize the most impactful findings.

1. Flag clearly wrong or outdated facts — focus on the most impactful errors.
2. Surface the top 3 most important pieces of missing current information.
3. Cite specific sources for every correction.
4. Keep each section tight — synthesis needs clear signal, not volume.

Return all four sections. Prioritize accuracy and clarity over completeness.

Sections required:
1. Facts That Are Outdated or Incorrect
2. Important Current Information Missing from Round-1
3. Tools or Frameworks Worth Highlighting
4. Current Practitioner Consensus
"""

# ── API call functions ────────────────────────────────────────────────────────

def call_perplexity(prompt: str, model: str, max_tokens: int) -> dict:
    """
    Call Perplexity Sonar API. Returns {text, input_tokens, output_tokens, actual_cost}.

    actual_cost: pulled from usage.cost['total_cost'] when available, which includes
    Perplexity's per-request search fee ($0.005-0.006) on top of token costs.
    Falls back to token-based calculation if not present.
    """
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["PERPLEXITY_API_KEY"],
        base_url="https://api.perplexity.ai",
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    usage = response.usage
    # Perplexity returns cost breakdown including search fee in usage.cost
    actual_cost = None
    if usage and hasattr(usage, "cost") and isinstance(usage.cost, dict):
        actual_cost = usage.cost.get("total_cost")
    return {
        "text":          response.choices[0].message.content.strip(),
        "input_tokens":  usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
        "actual_cost":   actual_cost,
    }


def call_openai_websearch(prompt: str, model: str, max_tokens: int) -> dict:
    """
    Call OpenAI GPT with a web-grounding instruction in the prompt.

    gpt-5.4 requires max_completion_tokens (not max_tokens) and does not
    support the web_search_preview tool type via Chat Completions.
    The grounding instruction in the prompt is consistent with how
    backend/models/perplexity_client.py handles the GPT fallback.

    Returns {text, input_tokens, output_tokens, actual_cost}.
    """
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Append web-grounding instruction (mirrors perplexity_client._call_gpt_audit_with_web_search)
    grounded_prompt = (
        prompt +
        "\n\nNote: You are acting as fact-checker. Search the web to verify claims."
    )

    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=max_tokens,   # gpt-5.4 requires max_completion_tokens
        messages=[{"role": "user", "content": grounded_prompt}],
    )

    usage = response.usage
    content = (response.choices[0].message.content or "").strip()

    return {
        "text":          content,
        "input_tokens":  usage.prompt_tokens if usage else 0,
        "output_tokens": usage.completion_tokens if usage else 0,
        "actual_cost":   None,   # OpenAI does not return cost in usage
    }


def call_candidate(
    candidate_key: str,
    round1_claims: dict,
    tier: str,
) -> dict:
    """
    Call a factcheck candidate with the given round-1 claims at the given tier.
    Returns {text, input_tokens, output_tokens}.
    """
    cfg = FACTCHECK_CANDIDATES[candidate_key]
    prompt = _build_audit_prompt(round1_claims, tier)

    # Token budget: mirrors model_config.py
    max_tokens = 800 if tier == "smart" else 2000

    if cfg["provider"] == "perplexity":
        return call_perplexity(prompt, cfg["model"], max_tokens)
    elif cfg["provider"] == "openai_websearch":
        return call_openai_websearch(prompt, cfg["model"], max_tokens)
    else:
        return {"text": f"[Unknown provider: {cfg['provider']}]",
                "input_tokens": 0, "output_tokens": 0}

# ── Test runner ───────────────────────────────────────────────────────────────

def run_single_test(
    candidate_key: str,
    test: dict,
    candidate_dir: Path,
    timestamp: str,
    tier: str = "smart",
    tier_suffix: str = "",
) -> dict:
    """
    Run one test case for one candidate. Returns result metadata dict.
    Writes per-test markdown to candidate_dir.
    """
    cfg = FACTCHECK_CANDIDATES[candidate_key]
    test_id = test["id"] + (f"-{tier_suffix}" if tier_suffix else "")

    print(f"  {test_id} [{tier}]...", end=" ", flush=True)

    try:
        start   = time.time()
        result  = call_candidate(candidate_key, test["round1_claims"], tier)
        elapsed = round(time.time() - start, 2)
        output        = result["text"]
        input_tokens  = result["input_tokens"]
        output_tokens = result["output_tokens"]
        actual_cost   = result.get("actual_cost")
        status = "✓"
    except Exception as e:
        output        = f"[ERROR: {e}]"
        elapsed       = 0.0
        input_tokens  = 0
        output_tokens = 0
        actual_cost   = None
        status        = "✗"

    score_result = score_factcheck_result(test, output, elapsed, tier)
    # Use actual_cost when available (Perplexity includes per-request search fee);
    # fall back to token-based calculation for OpenAI candidates.
    test_cost = actual_cost if actual_cost is not None else calculate_cost(
        input_tokens, output_tokens, cfg["input_rate"], cfg["output_rate"]
    )

    score_pct = score_result["score"]
    print(
        f"{status} {score_pct:.0f}% ({elapsed}s | "
        f"{input_tokens}in+{output_tokens}out | ${test_cost:.5f})"
        + (" ⚠ HARD GATE FAILURE" if score_result["is_hard_gate_failure"] else "")
    )

    # Write per-test markdown
    result_path = candidate_dir / f"{test_id}.md"
    with open(result_path, "w") as f:
        f.write(f"# {cfg['notes'].split('—')[0].strip()} — {test['name']}\n\n")
        f.write(f"**Candidate:** {candidate_key}\n")
        f.write(f"**Tier:** {tier}\n")
        f.write(f"**Generated:** {timestamp}\n")
        f.write(f"**Elapsed:** {elapsed}s\n")
        f.write(f"**Tokens:** {input_tokens} input / {output_tokens} output\n")
        f.write(f"**Cost:** ${test_cost:.6f}\n")
        f.write(f"**Score:** {score_result['passed']}/{score_result['total']} "
                f"({score_pct:.0f}%)\n")
        if score_result["is_hard_gate_failure"]:
            f.write(f"\n> ⚠️ **HARD GATE FAILURE** — "
                    f"disqualifies candidate as primary\n")
        f.write("\n## Automated Check Results\n\n")
        for failure in score_result["failures"]:
            f.write(f"- ✗ {failure}\n")
        if not score_result["failures"]:
            f.write("- ✓ All checks passed\n")
        f.write("\n## Description\n\n")
        f.write(f"{test['description']}\n")
        f.write("\n## Known Ground Truth\n\n")
        gt = test["known_ground_truth"]
        f.write(f"**Correct:** {gt['correct']}\n")
        if gt.get("error_type"):
            f.write(f"**Error type:** {gt['error_type']}\n")
        f.write("\n## Output\n\n")
        f.write(output)

    return {
        "test_id":      test["id"],
        "tier":         tier,
        "status":       status,
        "output":       output,
        "elapsed":      elapsed,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "cost":         round(test_cost, 6),
        "score":        score_result,
    }

# ── Main evaluation ───────────────────────────────────────────────────────────

def run_evaluation():
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    all_results: dict = {}

    print(f"\n{'='*60}")
    print("Factcheck Model Evaluation Harness")
    print(f"Candidates: {len(AVAILABLE_CANDIDATES)}")
    print(f"Tests:      {len(FACTCHECK_TESTS)} (test7 runs twice: Smart + Deep)")
    print(f"{'='*60}\n")

    if not AVAILABLE_CANDIDATES:
        print("No candidates available. Check API keys in backend/.env.")
        return

    cost_data: dict = {}

    for candidate_key, cfg in AVAILABLE_CANDIDATES.items():
        print(f"\n── {candidate_key} ──")
        candidate_dir = results_dir / candidate_key
        candidate_dir.mkdir(exist_ok=True)

        all_results[candidate_key] = {}
        total_input_tokens  = 0
        total_output_tokens = 0
        total_cost_smart    = 0.0
        total_cost_deep     = 0.0
        hard_gate_failures  = []
        scores_by_test: dict = {}

        for test in FACTCHECK_TESTS:
            # test7 runs at both tiers; everything else uses the tier from test or "smart"
            if test.get("run_both_tiers"):
                for tier in ("smart", "deep"):
                    res = run_single_test(
                        candidate_key, test, candidate_dir, timestamp,
                        tier=tier, tier_suffix=tier,
                    )
                    all_results[candidate_key][f"{test['id']}-{tier}"] = res
                    total_input_tokens  += res["input_tokens"]
                    total_output_tokens += res["output_tokens"]
                    if tier == "smart":
                        total_cost_smart += res["cost"]
                        scores_by_test[test["id"] + "-smart"] = res["score"]["score"]
                    else:
                        total_cost_deep += res["cost"]
                    if res["score"]["is_hard_gate_failure"]:
                        hard_gate_failures.append(test["id"])
                    time.sleep(1)
            else:
                tier = test.get("audit_tier", "smart")
                res = run_single_test(
                    candidate_key, test, candidate_dir, timestamp, tier=tier
                )
                all_results[candidate_key][test["id"]] = res
                total_input_tokens  += res["input_tokens"]
                total_output_tokens += res["output_tokens"]
                total_cost_smart += res["cost"]
                scores_by_test[test["id"]] = res["score"]["score"]
                if res["score"]["is_hard_gate_failure"]:
                    hard_gate_failures.append(test["id"])
                time.sleep(1)

        # Approximate per-call token averages (Smart only for monthly projection)
        smart_tests = [t for t in FACTCHECK_TESTS if not t.get("run_both_tiers")]
        n_smart = max(len(smart_tests), 1)
        avg_in_smart  = total_input_tokens  / (n_smart + len(FACTCHECK_TESTS))
        avg_out_smart = total_output_tokens / (n_smart + len(FACTCHECK_TESTS))
        monthly_smart = project_monthly(
            avg_in_smart, avg_out_smart, cfg["input_rate"], cfg["output_rate"]
        )

        # Deep tier: estimate from test7-deep tokens
        deep_res_key = "test7-depth-comparison-smart-vs-deep-deep"
        deep_res = all_results[candidate_key].get(deep_res_key, {})
        avg_in_deep  = deep_res.get("input_tokens", 0)
        avg_out_deep = deep_res.get("output_tokens", 0)
        monthly_deep = project_monthly(
            avg_in_deep, avg_out_deep, cfg["input_rate"], cfg["output_rate"]
        )

        avg_score = (
            sum(scores_by_test.values()) / len(scores_by_test)
            if scores_by_test else 0
        )

        cost_data[candidate_key] = {
            "label":                candidate_key,
            "model":                cfg["model"],
            "notes":                cfg["notes"],
            "input_rate":           cfg["input_rate"],
            "output_rate":          cfg["output_rate"],
            "total_input_tokens":   total_input_tokens,
            "total_output_tokens":  total_output_tokens,
            "total_cost_smart":     round(total_cost_smart, 6),
            "total_cost_deep":      round(total_cost_deep,  6),
            "avg_score":            round(avg_score, 1),
            "scores_by_test":       {k: round(v, 1) for k, v in scores_by_test.items()},
            "hard_gate_failures":   hard_gate_failures,
            "monthly_smart":        monthly_smart,
            "monthly_deep":         monthly_deep,
        }

        hg_str = f" ⚠ {len(hard_gate_failures)} hard gate failure(s)" if hard_gate_failures else ""
        print(f"  ── Avg score: {avg_score:.0f}%{hg_str}")
        print(f"  ── Smart/session: ${monthly_smart['per_session']:.6f} | "
              f"Deep/session: ${monthly_deep['per_session']:.6f}")
        print(f"  ── 1K Smart: ${monthly_smart['1k_sessions']:.2f} | "
              f"1K Deep: ${monthly_deep['1k_sessions']:.2f}")

    # ── Save cost_data.json ───────────────────────────────────────────────────
    cost_json_path = results_dir / f"cost_data-{timestamp}.json"
    with open(cost_json_path, "w") as f:
        json.dump({
            "timestamp":  timestamp,
            "candidates": cost_data,
        }, f, indent=2)

    # ── Generate decision matrix ──────────────────────────────────────────────
    _write_decision_matrix(results_dir, timestamp, cost_data, all_results)

    print(f"\n{'='*60}")
    print("Evaluation complete.")
    print(f"Results:  {results_dir}")
    print(f"{'='*60}\n")


# ── Decision matrix ───────────────────────────────────────────────────────────

def _write_decision_matrix(
    results_dir: Path,
    timestamp: str,
    cost_data: dict,
    all_results: dict,
) -> None:
    matrix_path = results_dir / f"decision-matrix-{timestamp}.md"

    # Determine recommendation order: highest avg_score among those passing hard gate
    def _rank(ck):
        cd = cost_data[ck]
        hard_gate_pass = not cd["hard_gate_failures"]
        return (hard_gate_pass, cd["avg_score"])

    ranked = sorted(cost_data.keys(), key=_rank, reverse=True)

    test_ids_short = [
        "T1", "T2", "T3", "T4", "T5", "T6", "T7s"
    ]
    ordered_test_keys = [
        "test1-catch-retired-model",
        "test2-confirm-correct-terminology",
        "test3-catch-wrong-statistic",
        "test4-structured-output-four-sections",
        "test5-citation-specificity",
        "test6-latency-smart",
        "test7-depth-comparison-smart-vs-deep-smart",
    ]

    with open(matrix_path, "w") as f:
        f.write("# Factcheck Model Selection Decision Matrix\n\n")
        f.write(f"Generated: {timestamp}\n\n")

        # ── Hard gate results ─────────────────────────────────────────────────
        f.write("## Hard Gate Results (must pass to qualify as primary)\n\n")
        f.write("**Test 1** — Catch retired model as current (Claude 3 Opus):\n\n")
        for ck in cost_data:
            cd = cost_data[ck]
            hg_fail = "test1-catch-retired-model" in cd["hard_gate_failures"]
            icon = "❌ FAIL" if hg_fail else "✅ PASS"
            f.write(f"- {ck}: {icon}\n")
        f.write("\n")

        # ── Score summary ─────────────────────────────────────────────────────
        f.write("## Score Summary\n\n")

        # Header
        header = f"{'Candidate':<26} "
        header += "  ".join(f"{t:<4}" for t in test_ids_short)
        header += f"  {'Avg':>4}  {'$/Smart':>9}  {'$/Deep':>9}\n"
        f.write(header)
        f.write("─" * len(header.rstrip()) + "\n")

        for ck in cost_data:
            cd = cost_data[ck]
            scores = cd["scores_by_test"]
            row = f"{ck:<26} "
            for tk in ordered_test_keys:
                s = scores.get(tk)
                row += f"{(str(int(s))+'%') if s is not None else 'n/a':<6}"
            row += (
                f"  {cd['avg_score']:.0f}%"
                f"  ${cd['monthly_smart']['per_session']:.5f}"
                f"  ${cd['monthly_deep']['per_session']:.5f}"
            )
            f.write(row + "\n")
        f.write("\n")

        # ── Monthly projections ───────────────────────────────────────────────
        f.write("## Monthly Cost Projection (1K sessions)\n\n")
        f.write(f"{'Candidate':<26}  {'Smart':>8}  {'Deep':>8}\n")
        f.write("─" * 50 + "\n")
        for ck in cost_data:
            cd = cost_data[ck]
            f.write(
                f"{ck:<26}  "
                f"${cd['monthly_smart']['1k_sessions']:>7.2f}  "
                f"${cd['monthly_deep']['1k_sessions']:>7.2f}\n"
            )
        f.write("\n")

        # ── Smart vs Deep depth comparison (Test 7) ───────────────────────────
        f.write("## Smart vs Deep Depth Comparison (Test 7)\n\n")
        f.write(f"{'Candidate':<26}  {'Smart tokens':>13}  "
                f"{'Deep tokens':>12}  Quality difference\n")
        f.write("─" * 80 + "\n")
        for ck in all_results:
            cd = cost_data[ck]
            smart_r = all_results[ck].get(
                "test7-depth-comparison-smart-vs-deep-smart", {}
            )
            deep_r  = all_results[ck].get(
                "test7-depth-comparison-smart-vs-deep-deep", {}
            )
            smart_tok = smart_r.get("output_tokens", "n/a")
            deep_tok  = deep_r.get("output_tokens", "n/a")
            checks = {}
            # Check automated constraints
            if isinstance(smart_tok, int) and isinstance(deep_tok, int):
                smart_ok = smart_tok <= 800
                deep_ok  = deep_tok >= 400
                notes = []
                if smart_ok:
                    notes.append("Smart concise ✓")
                else:
                    notes.append(f"Smart over budget ({smart_tok}>800) ✗")
                if deep_ok:
                    notes.append("Deep thorough ✓")
                else:
                    notes.append(f"Deep too short ({deep_tok}<400) ✗")
                quality = ", ".join(notes) + " [human judgment needed]"
            else:
                quality = "[human judgment needed]"
            f.write(
                f"{ck:<26}  {str(smart_tok):>13}  {str(deep_tok):>12}  {quality}\n"
            )
        f.write("\n")

        # ── Recommendation ────────────────────────────────────────────────────
        f.write("## Recommendation\n\n")
        if len(ranked) >= 1:
            primary = ranked[0]
            primary_model = cost_data[primary]["model"]
            hg_warn = (
                " ⚠️ WARNING: no candidate passed hard gate"
                if cost_data[primary]["hard_gate_failures"]
                else ""
            )
            f.write(f"```\nFACTCHECK_PRIMARY:   {primary} ({primary_model})"
                    f"{hg_warn}\n")
        if len(ranked) >= 2:
            fb1 = ranked[1]
            fb1_model = cost_data[fb1]["model"]
            f.write(f"FACTCHECK_FALLBACK1: {fb1} ({fb1_model})\n")
        if len(ranked) >= 3:
            fb2 = ranked[2]
            fb2_model = cost_data[fb2]["model"]
            f.write(f"FACTCHECK_FALLBACK2: {fb2} ({fb2_model})\n")
        f.write("```\n\n")

        # ── model_config.py update instructions ───────────────────────────────
        f.write("## Update model_config.py\n\n")
        f.write("```python\n")
        if len(ranked) >= 1:
            m = cost_data[ranked[0]]["model"]
            f.write(f'FACTCHECK_PRIMARY   = os.getenv("FACTCHECK_PRIMARY",   "{m}")\n')
        if len(ranked) >= 2:
            m = cost_data[ranked[1]]["model"]
            f.write(f'FACTCHECK_FALLBACK1 = os.getenv("FACTCHECK_FALLBACK1", "{m}")\n')
        if len(ranked) >= 3:
            m = cost_data[ranked[2]]["model"]
            f.write(f'FACTCHECK_FALLBACK2 = os.getenv("FACTCHECK_FALLBACK2", "{m}")\n')
        f.write("```\n\n")

        # ── ADR reminder ──────────────────────────────────────────────────────
        f.write("## Next Steps\n\n")
        f.write("1. Read Test 7 outputs manually — "
                "token count is a proxy; read for quality\n")
        f.write("2. Update `backend/models/model_config.py` "
                "using the snippet above\n")
        f.write("3. Create `docs/decisions/004-factcheck-model-selection.md` "
                "documenting the ADR\n")

    print(f"\nDecision matrix: {matrix_path}")


if __name__ == "__main__":
    run_evaluation()
