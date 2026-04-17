"""
experiments/generate_cost_report.py

Combined cost report generator.
=================================
Reads the most recent cost_data JSON from both synthesizer_eval and
intake_eval results directories, then writes a combined cost report to
experiments/cost-report-<timestamp>.md.

Run AFTER both evals have completed:
    python -m experiments.synthesizer_eval.run_eval
    python -m experiments.intake_eval.run_eval
    python -m experiments.generate_cost_report

Output: experiments/cost-report-<timestamp>.md
"""

import json
import sys
from datetime import datetime
from pathlib import Path

THIS_DIR     = Path(__file__).parent
SYNTH_DIR    = THIS_DIR / "synthesizer_eval" / "results"
INTAKE_DIR   = THIS_DIR / "intake_eval" / "results"


def _latest_cost_json(results_dir: Path) -> dict | None:
    """Return parsed contents of the most recent cost_data-*.json."""
    files = sorted(results_dir.glob("cost_data-*.json"), reverse=True)
    if not files:
        return None
    with open(files[0]) as f:
        return json.load(f)


def generate():
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_path = THIS_DIR / f"cost-report-{timestamp}.md"

    synth_data  = _latest_cost_json(SYNTH_DIR)
    intake_data = _latest_cost_json(INTAKE_DIR)

    if synth_data is None and intake_data is None:
        print("No cost_data JSON found in either results directory.")
        print("Run the evals first:")
        print("  python -m experiments.synthesizer_eval.run_eval")
        print("  python -m experiments.intake_eval.run_eval")
        sys.exit(1)

    lines = []
    lines.append("# AI Roundtable — Combined Cost Analysis Report\n")
    lines.append(f"**Generated:** {timestamp}\n")
    lines.append("\n---\n")

    # ── Section 1: Synthesizer Costs ──────────────────────────────────────────
    lines.append("## 1. Synthesizer Candidates\n")

    if synth_data:
        lines.append(f"_Eval date: {synth_data['timestamp']}_\n\n")
        lines.append("### Per-Call Token Profile (average across 3 tests)\n\n")
        lines.append("| Candidate | Avg input | Avg output | $/session | "
                     "$/1K sessions | $/10K sessions |\n")
        lines.append("|-----------|----------|-----------|----------|"
                     "--------------|----------------|\n")
        for ck, cd in synth_data["candidates"].items():
            m = cd["monthly"]
            lines.append(
                f"| {cd['label']} "
                f"| {cd['avg_input_tokens']:.0f} "
                f"| {cd['avg_output_tokens']:.0f} "
                f"| ${m['per_session']:.6f} "
                f"| ${m['1k_sessions']:.2f} "
                f"| ${m['10k_sessions']:.2f} |\n"
            )

        lines.append("\n### Automated Quality Scores\n\n")
        lines.append("| Candidate | Auto pass % | $/point |\n")
        lines.append("|-----------|------------|--------|\n")
        for ck, cd in synth_data["candidates"].items():
            pct = cd.get("auto_pass_pct", 0)
            cost_per_point = (
                cd["monthly"]["per_session"] / (pct / 100)
                if pct > 0 else float("inf")
            )
            lines.append(
                f"| {cd['label']} | {pct}% | ${cost_per_point:.6f} |\n"
            )

        # Tier-routing
        if synth_data.get("tier_routing"):
            tr = synth_data["tier_routing"]
            lines.append("\n### Tier-Routing Scenario (60% Quick / 30% Smart / 10% Deep)\n\n")
            lines.append(
                f"Blended per-session cost: **${tr['blended_per_session']:.6f}**\n\n"
            )
            lines.append("| Volume | All-Opus | All-Haiku | Tier-Routed |\n")
            lines.append("|--------|---------|---------|-------------|\n")
            # Get Opus and Haiku costs
            opus_m  = synth_data["candidates"].get(
                "Claude-Opus-4-7",  {}).get("monthly", {})
            haiku_m = synth_data["candidates"].get(
                "Claude-Haiku-4-5", {}).get("monthly", {})
            for vol, key_100, key_1k, key_10k, blend_key in [
                ("100 sessions",  "100_sessions", "100_sessions",  "100_sessions",  "blended_100"),
                ("1K sessions",   "1k_sessions",  "1k_sessions",   "1k_sessions",   "blended_1k"),
                ("10K sessions",  "10k_sessions", "10k_sessions",  "10k_sessions",  "blended_10k"),
            ]:
                o = opus_m.get(key_100 if "100" in key_100 else
                               (key_1k if "1k" in key_1k else key_10k), 0)
                h = haiku_m.get(key_100 if "100" in key_100 else
                                (key_1k if "1k" in key_1k else key_10k), 0)
                b = tr.get(blend_key, 0)
                lines.append(f"| {vol} | ${o:.3f} | ${h:.3f} | ${b:.3f} |\n")

    else:
        lines.append("_No synthesizer eval data found. Run:_\n")
        lines.append("```\npython -m experiments.synthesizer_eval.run_eval\n```\n")

    lines.append("\n---\n")

    # ── Section 2: Intake Costs ───────────────────────────────────────────────
    lines.append("## 2. Intake Candidates\n")

    if intake_data:
        lines.append(f"_Eval date: {intake_data['timestamp']}_\n\n")
        lines.append("### Per-Call Token Profile (average across 6 tests)\n\n")
        lines.append("| Candidate | Avg input | Avg output | $/session | "
                     "$/1K sessions | $/10K sessions |\n")
        lines.append("|-----------|----------|-----------|----------|"
                     "--------------|----------------|\n")
        for ck, cd in intake_data["candidates"].items():
            lines.append(
                f"| {cd['label']} "
                f"| {cd['avg_input_tokens']:.0f} "
                f"| {cd['avg_output_tokens']:.0f} "
                f"| ${cd['per_session_cost']:.6f} "
                f"| ${cd['1k_sessions']:.3f} "
                f"| ${cd['10k_sessions']:.2f} |\n"
            )

        lines.append("\n### Assertion Scores\n\n")
        lines.append("| Candidate | Assert pass % | $/1K sessions |\n")
        lines.append("|-----------|--------------|---------------|\n")
        for ck, cd in intake_data["candidates"].items():
            lines.append(
                f"| {cd['label']} "
                f"| {cd['assertion_pass_pct']}% "
                f"| ${cd['1k_sessions']:.3f} |\n"
            )
    else:
        lines.append("_No intake eval data found. Run:_\n")
        lines.append("```\npython -m experiments.intake_eval.run_eval\n```\n")

    lines.append("\n---\n")

    # ── Section 3: Combined Session Cost ─────────────────────────────────────
    lines.append("## 3. Combined Session Cost (intake + synthesis)\n\n")
    lines.append(
        "A full session = 1 intake call + 1 synthesis call. "
        "This section shows the combined cost for the current production "
        "configuration (Gemini 2.5 Flash intake + Claude Opus 4.7 synthesis) "
        "vs. optimized alternatives.\n\n"
    )

    if synth_data and intake_data:
        # Current production
        prod_intake_key  = "Gemini-2.5-Flash"
        prod_synth_key   = "Claude-Opus-4-7"
        prod_intake_cost = intake_data["candidates"].get(
            prod_intake_key, {}).get("per_session_cost", 0)
        prod_synth_cost  = synth_data["candidates"].get(
            prod_synth_key, {}).get("monthly", {}).get("per_session", 0)
        prod_total       = prod_intake_cost + prod_synth_cost

        # Optimized: Gemini 2.5 Flash + tier-routed synthesis
        tr_cost = synth_data.get("tier_routing", {}).get("blended_per_session", 0)
        opt_total = prod_intake_cost + tr_cost

        lines.append("| Configuration | Intake | Synthesis | Total/session | "
                     "$/1K sessions |\n")
        lines.append("|---------------|--------|-----------|--------------|"
                     "---------------|\n")
        lines.append(
            f"| Current (Gemini Flash + Opus 4.7) "
            f"| ${prod_intake_cost:.6f} "
            f"| ${prod_synth_cost:.6f} "
            f"| ${prod_total:.6f} "
            f"| ${prod_total * 1000:.2f} |\n"
        )
        lines.append(
            f"| Optimized (Gemini Flash + tier-routed) "
            f"| ${prod_intake_cost:.6f} "
            f"| ${tr_cost:.6f} "
            f"| ${opt_total:.6f} "
            f"| ${opt_total * 1000:.2f} |\n"
        )

        savings_pct = ((prod_total - opt_total) / prod_total * 100
                       if prod_total > 0 else 0)
        lines.append(
            f"\nTier-routing saves **{savings_pct:.1f}%** per session vs. "
            f"all-Opus.\n"
        )
    else:
        lines.append("_Requires both evals to have run._\n")

    lines.append("\n---\n")

    # ── Section 4: Prompt Caching Analysis ────────────────────────────────────
    lines.append("## 4. Prompt Caching Analysis\n\n")
    lines.append(
        "The synthesis system prompt is ~400 tokens and is identical on every "
        "call. Anthropic prompt caching charges 10% of input rate for cache "
        "hits (cached after the first call). Gemini and OpenAI have similar "
        "caching mechanisms.\n\n"
    )
    lines.append("**Potential savings at 1K sessions (synthesis only):**\n\n")

    if synth_data:
        cacheable_tokens = 400  # approx system prompt tokens
        lines.append("| Candidate | Cacheable tokens | Saving/session | "
                     "Saving/1K |\n")
        lines.append("|-----------|-----------------|---------------|"
                     "---------|\n")
        for ck, cd in synth_data["candidates"].items():
            # Saving = (90% of input_rate) * (cacheable_tokens / 1M)
            saving_per_session = (
                cd["input_rate"] * 0.90 * (cacheable_tokens / 1_000_000)
            )
            lines.append(
                f"| {cd['label']} "
                f"| {cacheable_tokens} "
                f"| ${saving_per_session:.7f} "
                f"| ${saving_per_session * 1000:.4f} |\n"
            )
    else:
        lines.append("_No synthesizer eval data._\n")

    lines.append("\n---\n")

    # ── Section 5: Recommendation Table ──────────────────────────────────────
    lines.append("## 5. Recommendation Summary\n\n")
    lines.append("| Decision | Recommendation | Rationale |\n")
    lines.append("|----------|---------------|----------|\n")
    lines.append(
        "| Production synthesizer | Claude Opus 4.7 (with tier routing) | "
        "Highest quality (89/90 v1), 'PERPLEXITY WINS' compliance |\n"
    )
    lines.append(
        "| Quick tier synthesizer | Claude Haiku 4.5 | "
        "~10x cost reduction vs Opus; acceptable for brainstorms |\n"
    )
    lines.append(
        "| Production intake | Gemini 2.5 Flash | "
        "Structured output, JSON schema enforcement, cost-efficient |\n"
    )
    lines.append(
        "| Tier-routing default | 60/30/10 Quick/Smart/Deep | "
        "Blended cost minimizes spend; deep reserved for architecture/reports |\n"
    )

    lines.append(
        "\n_See `docs/decisions/002-synthesizer-selection.md` and "
        "`docs/decisions/003-intake-model-selection.md` for full ADRs._\n"
    )

    # ── Write output ──────────────────────────────────────────────────────────
    with open(output_path, "w") as f:
        f.writelines(lines)

    print(f"\nCost report written to: {output_path}")
    return output_path


if __name__ == "__main__":
    generate()
