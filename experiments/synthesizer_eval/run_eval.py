"""
experiments/synthesizer_eval/run_eval.py

Synthesizer Evaluation Harness v2 — token counting and cost analysis.
======================================================================
Runs three fixed test prompts through five synthesizer candidates.
Each candidate receives identical input. Outputs saved to results/.

Candidates:
    - Claude Opus 4.7  (Anthropic)  — baseline, highest quality
    - Claude Sonnet 4.6 (Anthropic) — Smart tier candidate
    - Claude Haiku 4.5 (Anthropic)  — Quick tier candidate
    - GPT-4o           (OpenAI)     — cross-provider benchmark
    - Qwen 2.5 72B     (OpenRouter) — open-weight cost baseline

Usage:
    cd /path/to/ai-roundtable
    python -m experiments.synthesizer_eval.run_eval

Requirements:
    API keys in backend/.env:
        ANTHROPIC_API_KEY  — required for Claude candidates
        OPENAI_API_KEY     — required for GPT-4o
        OPENROUTER_API_KEY — required for Qwen 2.5 72B
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

from experiments.synthesizer_eval.prompts import (  # noqa: E402
    TEST1_USER_PROMPT, TEST1_ROUND1, TEST1_PERPLEXITY,
    TEST2_USER_PROMPT, TEST2_ROUND1, TEST2_PERPLEXITY,
    TEST3_USER_PROMPT, TEST3_ROUND1, TEST3_PERPLEXITY,
    SCORING_RUBRIC,
)

# ── Candidate registry ────────────────────────────────────────────────────────
# input_rate / output_rate: USD per 1M tokens

SYNTHESIZER_CANDIDATES = {
    "Claude-Opus-4-7": {
        "provider":    "anthropic",
        "model":       "claude-opus-4-7",
        "input_rate":  5.00,
        "output_rate": 25.00,
        "label":       "Claude Opus 4.7 (Anthropic)",
    },
    "Claude-Sonnet-4-6": {
        "provider":    "anthropic",
        "model":       "claude-sonnet-4-6",
        "input_rate":  3.00,
        "output_rate": 15.00,
        "label":       "Claude Sonnet 4.6 (Anthropic)",
    },
    "Claude-Haiku-4-5": {
        "provider":    "anthropic",
        "model":       "claude-haiku-4-5-20251001",
        "input_rate":  0.80,
        "output_rate": 4.00,
        "label":       "Claude Haiku 4.5 (Anthropic)",
    },
    "GPT-4o": {
        "provider":    "openai",
        "model":       "gpt-4o",
        "input_rate":  2.50,
        "output_rate": 10.00,
        "label":       "GPT-4o (OpenAI)",
    },
    "Qwen-2.5-72B": {
        "provider":    "openrouter",
        "model":       "qwen/qwen-2.5-72b-instruct",
        "input_rate":  0.40,
        "output_rate": 1.20,
        "label":       "Qwen 2.5 72B (OpenRouter)",
    },
}

# ── Availability check ────────────────────────────────────────────────────────

def _check_availability():
    available = {}
    anthropic_ok = False
    openai_ok = False
    openrouter_ok = False

    try:
        import anthropic  # noqa: F401
        if os.environ.get("ANTHROPIC_API_KEY"):
            anthropic_ok = True
        else:
            print("ANTHROPIC_API_KEY not set — skipping Claude candidates")
    except ImportError:
        print("anthropic SDK not installed — skipping Claude candidates")

    try:
        import openai  # noqa: F401
        if os.environ.get("OPENAI_API_KEY"):
            openai_ok = True
        else:
            print("OPENAI_API_KEY not set — skipping GPT-4o")
    except ImportError:
        print("openai SDK not installed — skipping GPT-4o")

    if os.environ.get("OPENROUTER_API_KEY"):
        openrouter_ok = True
    else:
        print("OPENROUTER_API_KEY not set — skipping Qwen 2.5 72B")

    for key, cfg in SYNTHESIZER_CANDIDATES.items():
        p = cfg["provider"]
        if p == "anthropic" and anthropic_ok:
            available[key] = cfg
        elif p == "openai" and openai_ok:
            available[key] = cfg
        elif p == "openrouter" and openrouter_ok:
            available[key] = cfg

    return available

AVAILABLE_CANDIDATES = _check_availability()

# ── Cost helpers ──────────────────────────────────────────────────────────────

def calculate_cost(input_tokens: int, output_tokens: int,
                   input_rate: float, output_rate: float) -> float:
    """Return cost in USD given token counts and per-MTok rates."""
    return (input_tokens / 1_000_000) * input_rate + \
           (output_tokens / 1_000_000) * output_rate

# ── Synthesis system prompt ───────────────────────────────────────────────────

def build_synthesis_system_prompt() -> str:
    return """
You are the expert chair of an AI research roundtable. You have received:
1. A user's question
2. Round-1 responses from four AI models (Claude, Gemini, GPT, Grok)
3. A Perplexity live web research audit with citations

## Source Trust Hierarchy

### Tier 1 — Perplexity Audit (GROUNDED, highest trust)
- Treat as authoritative. Retrieved via live web search with citations.
- Do NOT apply skepticism to Perplexity findings.
- When Perplexity contradicts a round-1 model on a verifiable fact,
  PERPLEXITY WINS. Always.
- Verifiable facts: prices, dates, model names, availability, deprecation status
- State contradictions explicitly. Do not blend conflicting figures.
- If Perplexity states a model is retired/deprecated: do NOT present its
  data as current. Use the successor model's data.

### Tier 2 — Round-1 model responses (UNVERIFIED)
- May be stale. Training cutoffs predate current date.
- Attribute claims to source. Apply skepticism.
- Confident prose does NOT make a claim reliable.

### Tier 3 — Your own training data (LOWEST priority)
- Use only when Perplexity has no data on a point.
- Never use to override Perplexity.

## Contradiction Resolution (mandatory)
Before writing, scan for contradictions between Perplexity and round-1 on
verifiable facts. For each: use Perplexity's figure, state the contradiction,
do not blend.

## Output Format
- Lead with Perplexity's verified data
- Attribute every claim to its source
- Use confidence tags: [VERIFIED] [LIKELY] [UNCERTAIN] [DEFER]
- Surface disagreements explicitly
- End with 3 concrete actionable next steps
"""

# ── API call functions — return {text, input_tokens, output_tokens} ───────────

def call_anthropic(user_message: str, system: str, model: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return {
        "text":          response.content[0].text,
        "input_tokens":  response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def call_openai(user_message: str, system: str, model: str) -> dict:
    import openai
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=model,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
    )
    return {
        "text":          response.choices[0].message.content,
        "input_tokens":  response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


def call_openrouter(user_message: str, system: str, model: str) -> dict:
    import httpx
    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": model,
        "max_tokens": 2000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_message},
        ],
    }
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    usage = data.get("usage", {})
    return {
        "text":          data["choices"][0]["message"]["content"],
        "input_tokens":  usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }


def call_candidate(candidate_key: str, user_message: str, system: str) -> dict:
    cfg = SYNTHESIZER_CANDIDATES[candidate_key]
    if cfg["provider"] == "anthropic":
        return call_anthropic(user_message, system, cfg["model"])
    elif cfg["provider"] == "openai":
        return call_openai(user_message, system, cfg["model"])
    elif cfg["provider"] == "openrouter":
        return call_openrouter(user_message, system, cfg["model"])
    else:
        return {"text": f"[Unknown provider: {cfg['provider']}]",
                "input_tokens": 0, "output_tokens": 0}

# ── User message builder ──────────────────────────────────────────────────────

def build_user_message(user_prompt: str, round1: dict,
                       perplexity: str) -> str:
    round1_block = "\n\n".join(
        f"### {model}\n{response}"
        for model, response in round1.items()
    )
    return f"""
## User Question
{user_prompt}

## VERIFIED LIVE RESEARCH (Perplexity — treat as authoritative)
{perplexity}

## Round-1 Model Responses (apply skepticism — may be stale)
{round1_block}

## Your Task
Synthesize the above into a comprehensive response to the user's question.
Follow the Source Trust Hierarchy in your system prompt exactly.
"""

# ── Automated pass criteria check ─────────────────────────────────────────────

def auto_check_criteria(output: str, criteria: list[str]) -> list[dict]:
    """
    Rough automated check: look for key phrases from each criterion in output.
    NOT a substitute for the full rubric — used for quick cost-report estimates.
    """
    results = []
    output_lower = output.lower()
    for criterion in criteria:
        # Extract key nouns/phrases from criterion for keyword matching
        # Heuristic: look for quoted strings or specific terms
        keywords = []
        if "$5" in criterion or "$5/$25" in criterion:
            keywords = ["$5", "5/25", "5 / 25"]
        elif "$15/$75" in criterion or "15/75" in criterion:
            # Must NOT appear as current — check inverse
            found = "$15" in output or "15/75" in output.replace(" ", "")
            results.append({"criterion": criterion[:80], "pass": not found,
                            "note": "inverse check"})
            continue
        elif "retirement" in criterion.lower() or "retire" in criterion.lower():
            keywords = ["retire", "deprecat", "jan 5, 2026", "january 5"]
        elif "fabricat" in criterion.lower():
            # Must NOT call Perplexity fabricated
            found = "fabricat" in output_lower
            results.append({"criterion": criterion[:80], "pass": not found,
                            "note": "inverse check"})
            continue
        elif "dpo" in criterion.lower():
            keywords = ["dpo"]
        elif "attribut" in criterion.lower():
            keywords = ["according to", "claude said", "gemini said",
                        "gpt said", "notes that", "suggests"]
        elif "actionable" in criterion.lower() or "next step" in criterion.lower():
            keywords = ["next step", "action", "recommend", "start with"]
        elif "rca" in criterion.lower() or "raa" in criterion.lower():
            keywords = ["rca", "raa", "qmric"]
        elif "mri" in criterion.lower() and "gemini" in criterion.lower():
            keywords = ["gemini", "mri", "incorrect", "incorrect term",
                        "wrong", "standard"]
        elif "dnv" in criterion.lower():
            keywords = ["dnv"]
        elif "phase" in criterion.lower():
            keywords = ["phase 1", "phase 2"]
        else:
            # Generic: look for any significant word (>5 chars) from criterion
            words = [w.lower() for w in criterion.split()
                     if len(w) > 5 and w.isalpha()]
            keywords = words[:3]

        if keywords:
            found = any(kw.lower() in output_lower for kw in keywords)
            results.append({"criterion": criterion[:80], "pass": found,
                            "note": "keyword: " + ", ".join(keywords[:2])})
        else:
            results.append({"criterion": criterion[:80], "pass": None,
                            "note": "no keywords extracted"})
    return results

# ── Test definitions ──────────────────────────────────────────────────────────

TESTS = [
    {
        "id":   "test1-factual",
        "name": "Factual Current Data (the failing case)",
        "user_prompt": TEST1_USER_PROMPT,
        "round1":      TEST1_ROUND1,
        "perplexity":  TEST1_PERPLEXITY,
        "pass_criteria": [
            "Must present Claude Opus 4.7 at $5/$25",
            "Must mention Claude 3 Opus retirement (Jan 5, 2026)",
            "Must NOT present $15/$75 as current pricing",
            "Must NOT call Perplexity data fabricated or unverifiable",
        ],
    },
    {
        "id":   "test2-analytical",
        "name": "Analytical Synthesis (the working case)",
        "user_prompt": TEST2_USER_PROMPT,
        "round1":      TEST2_ROUND1,
        "perplexity":  TEST2_PERPLEXITY,
        "pass_criteria": [
            "Must mention DPO as the practical default",
            "Must attribute claims to specific round-1 models",
            "Must include expert perspective beyond summarizing",
            "Must end with concrete actionable next steps",
        ],
    },
    {
        "id":   "test3-domain",
        "name": "Domain Technical (the showcase case)",
        "user_prompt": TEST3_USER_PROMPT,
        "round1":      TEST3_ROUND1,
        "perplexity":  TEST3_PERPLEXITY,
        "pass_criteria": [
            "Must use RCA/RAA/QMRIC terminology (not MRI)",
            "Must note that Gemini's MRI terminology was incorrect",
            "Must mention DNV synthetic profiles",
            "Must mention Phase 1/Phase 2 implementation timeline",
        ],
    },
]

# ── Monthly cost projection ───────────────────────────────────────────────────

def project_monthly(avg_input_tokens: float, avg_output_tokens: float,
                    input_rate: float, output_rate: float) -> dict:
    """Project monthly synthesis cost at 100 / 1K / 10K sessions."""
    per_session = calculate_cost(avg_input_tokens, avg_output_tokens,
                                  input_rate, output_rate)
    return {
        "per_session": per_session,
        "100_sessions":    round(per_session * 100,    4),
        "1k_sessions":     round(per_session * 1_000,  3),
        "10k_sessions":    round(per_session * 10_000, 2),
    }

# ── Tier-routing scenario ─────────────────────────────────────────────────────

def compute_tier_routing(candidate_costs: dict) -> dict:
    """
    Blended cost for recommended tier-routing strategy:
      60% Quick  → Haiku 4.5
      30% Smart  → Sonnet 4.6
      10% Deep   → Opus 4.7

    candidate_costs: {candidate_key: {"per_session": float}}
    Returns per-session blended cost and monthly projections.
    """
    haiku  = candidate_costs.get("Claude-Haiku-4-5",  {}).get("per_session", 0)
    sonnet = candidate_costs.get("Claude-Sonnet-4-6", {}).get("per_session", 0)
    opus   = candidate_costs.get("Claude-Opus-4-7",   {}).get("per_session", 0)

    blended = 0.60 * haiku + 0.30 * sonnet + 0.10 * opus
    return {
        "haiku_weight":  0.60,
        "sonnet_weight": 0.30,
        "opus_weight":   0.10,
        "haiku_per_session":  round(haiku,   6),
        "sonnet_per_session": round(sonnet,  6),
        "opus_per_session":   round(opus,    6),
        "blended_per_session": round(blended, 6),
        "blended_100":   round(blended * 100,    4),
        "blended_1k":    round(blended * 1_000,  3),
        "blended_10k":   round(blended * 10_000, 2),
    }

# ── Main evaluation ───────────────────────────────────────────────────────────

def run_evaluation():
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    system    = build_synthesis_system_prompt()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    all_results: dict = {}

    print(f"\n{'='*60}")
    print("Synthesizer Evaluation Harness v2 — with cost analysis")
    print(f"Candidates: {len(AVAILABLE_CANDIDATES)}")
    print(f"Tests:      {len(TESTS)}")
    print(f"{'='*60}\n")

    if not AVAILABLE_CANDIDATES:
        print("No candidates available. Check API keys in backend/.env.")
        return

    cost_data: dict = {}  # candidate_key → cost metadata

    for candidate_key, cfg in AVAILABLE_CANDIDATES.items():
        print(f"\n── {cfg['label']} ──")
        safe_name     = candidate_key
        candidate_dir = results_dir / safe_name
        candidate_dir.mkdir(exist_ok=True)

        all_results[candidate_key] = {}
        total_input_tokens  = 0
        total_output_tokens = 0
        total_cost          = 0.0
        auto_passes         = 0
        auto_total          = 0

        for test in TESTS:
            print(f"  Running {test['id']}...", end=" ", flush=True)
            user_message = build_user_message(
                test["user_prompt"],
                test["round1"],
                test["perplexity"],
            )

            try:
                start  = time.time()
                result = call_candidate(candidate_key, user_message, system)
                elapsed = round(time.time() - start, 1)
                status  = "✓"
                output         = result["text"]
                input_tokens   = result["input_tokens"]
                output_tokens  = result["output_tokens"]
            except Exception as e:
                output        = f"[ERROR: {e}]"
                elapsed       = 0.0
                status        = "✗"
                input_tokens  = 0
                output_tokens = 0

            test_cost = calculate_cost(
                input_tokens, output_tokens,
                cfg["input_rate"], cfg["output_rate"]
            )
            total_input_tokens  += input_tokens
            total_output_tokens += output_tokens
            total_cost          += test_cost

            # Automated criteria check
            criteria_results = auto_check_criteria(output, test["pass_criteria"])
            test_passes  = sum(1 for c in criteria_results if c["pass"] is True)
            test_checks  = sum(1 for c in criteria_results if c["pass"] is not None)
            auto_passes += test_passes
            auto_total  += test_checks

            print(f"{status} ({elapsed}s | {input_tokens}in+{output_tokens}out "
                  f"tokens | ${test_cost:.5f})")

            # Write per-test markdown
            result_path = candidate_dir / f"{test['id']}.md"
            with open(result_path, "w") as f:
                f.write(f"# {cfg['label']} — {test['name']}\n\n")
                f.write(f"**Generated:** {timestamp}\n")
                f.write(f"**Elapsed:** {elapsed}s\n")
                f.write(f"**Tokens:** {input_tokens} input / "
                        f"{output_tokens} output\n")
                f.write(f"**Cost:** ${test_cost:.6f}\n\n")
                f.write("## Pass Criteria\n\n")
                for criterion in test["pass_criteria"]:
                    f.write(f"- [ ] {criterion}\n")
                f.write("\n## Automated Checks\n\n")
                for c in criteria_results:
                    icon = "✓" if c["pass"] else ("✗" if c["pass"] is False
                                                  else "?")
                    f.write(f"- {icon} {c['criterion']} "
                            f"*({c['note']})*\n")
                f.write("\n## Output\n\n")
                f.write(output)

            all_results[candidate_key][test["id"]] = {
                "output":        output,
                "elapsed":       elapsed,
                "status":        status,
                "input_tokens":  input_tokens,
                "output_tokens": output_tokens,
                "cost":          round(test_cost, 6),
                "criteria":      criteria_results,
            }

            time.sleep(1)

        # Per-candidate cost summary
        avg_in  = total_input_tokens  / len(TESTS)
        avg_out = total_output_tokens / len(TESTS)
        monthly = project_monthly(avg_in, avg_out,
                                   cfg["input_rate"], cfg["output_rate"])
        auto_pct = (auto_passes / auto_total * 100) if auto_total else 0

        cost_data[candidate_key] = {
            "label":                cfg["label"],
            "model":                cfg["model"],
            "input_rate":           cfg["input_rate"],
            "output_rate":          cfg["output_rate"],
            "total_input_tokens":   total_input_tokens,
            "total_output_tokens":  total_output_tokens,
            "total_cost_3tests":    round(total_cost, 6),
            "avg_input_tokens":     round(avg_in, 1),
            "avg_output_tokens":    round(avg_out, 1),
            "auto_pass_pct":        round(auto_pct, 1),
            "monthly":              monthly,
        }

        print(f"  ── Totals: {total_input_tokens} in / {total_output_tokens} out "
              f"tokens | ${total_cost:.5f} for 3 tests")
        print(f"  ── Per session: ${monthly['per_session']:.6f} | "
              f"1K sessions: ${monthly['1k_sessions']:.2f}")
        print(f"  ── Auto criteria: {auto_passes}/{auto_total} "
              f"({auto_pct:.0f}%)")

    # ── Tier-routing scenario ─────────────────────────────────────────────────
    monthly_by_candidate = {k: v["monthly"] for k, v in cost_data.items()}
    tier_routing = compute_tier_routing(monthly_by_candidate)

    # ── Save cost_data.json ───────────────────────────────────────────────────
    cost_json_path = results_dir / f"cost_data-{timestamp}.json"
    with open(cost_json_path, "w") as f:
        json.dump({
            "timestamp":    timestamp,
            "candidates":   cost_data,
            "tier_routing": tier_routing,
        }, f, indent=2)

    # ── Write summary markdown ────────────────────────────────────────────────
    summary_path = results_dir / f"summary-{timestamp}.md"
    with open(summary_path, "w") as f:
        f.write("# Synthesizer Evaluation Summary v2\n\n")
        f.write(f"**Date:** {timestamp}\n")
        f.write(f"**Candidates tested:** {len(AVAILABLE_CANDIDATES)}\n\n")

        f.write("## Results Matrix\n\n")
        f.write("| Candidate | Test 1 | Test 2 | Test 3 | Auto% | "
                "$/session | $/1K sessions |\n")
        f.write("|-----------|--------|--------|--------|-------|"
                "----------|---------------|\n")
        for ck in AVAILABLE_CANDIDATES:
            r    = all_results[ck]
            cd   = cost_data[ck]
            row  = f"| {cd['label']} |"
            for test in TESTS:
                tr = r[test["id"]]
                row += f" {tr['status']} ({tr['elapsed']}s) |"
            row += (f" {cd['auto_pass_pct']}% |"
                    f" ${cd['monthly']['per_session']:.5f} |"
                    f" ${cd['monthly']['1k_sessions']:.2f} |")
            f.write(row + "\n")

        f.write("\n## Cost Analysis\n\n")
        f.write("### Per-Candidate Token Counts (3-test total)\n\n")
        f.write("| Candidate | Input tokens | Output tokens | 3-test cost |\n")
        f.write("|-----------|-------------|--------------|-------------|\n")
        for ck, cd in cost_data.items():
            f.write(f"| {cd['label']} | {cd['total_input_tokens']:,} | "
                    f"{cd['total_output_tokens']:,} | "
                    f"${cd['total_cost_3tests']:.5f} |\n")

        f.write("\n### Monthly Projections (synthesis calls only)\n\n")
        f.write("| Candidate | 100 sessions | 1K sessions | 10K sessions |\n")
        f.write("|-----------|-------------|------------|-------------|\n")
        for ck, cd in cost_data.items():
            m = cd["monthly"]
            f.write(f"| {cd['label']} | ${m['100_sessions']:.3f} | "
                    f"${m['1k_sessions']:.2f} | "
                    f"${m['10k_sessions']:.2f} |\n")

        f.write("\n### Tier-Routing Scenario (60% Quick / 30% Smart / 10% Deep)\n\n")
        tr = tier_routing
        f.write(f"Blended cost per session: **${tr['blended_per_session']:.6f}**\n\n")
        f.write("| Volume | Uniform Opus | Uniform Haiku | Tier-Routed |\n")
        f.write("|--------|-------------|--------------|-------------|\n")
        opus_100  = cost_data.get("Claude-Opus-4-7",  {}).get("monthly", {}).get("100_sessions",  0)
        haiku_100 = cost_data.get("Claude-Haiku-4-5", {}).get("monthly", {}).get("100_sessions",  0)
        opus_1k   = cost_data.get("Claude-Opus-4-7",  {}).get("monthly", {}).get("1k_sessions",   0)
        haiku_1k  = cost_data.get("Claude-Haiku-4-5", {}).get("monthly", {}).get("1k_sessions",   0)
        opus_10k  = cost_data.get("Claude-Opus-4-7",  {}).get("monthly", {}).get("10k_sessions",  0)
        haiku_10k = cost_data.get("Claude-Haiku-4-5", {}).get("monthly", {}).get("10k_sessions",  0)
        f.write(f"| 100 sessions   | ${opus_100:.3f}  | ${haiku_100:.3f}   | "
                f"${tr['blended_100']:.3f} |\n")
        f.write(f"| 1K sessions    | ${opus_1k:.2f}   | ${haiku_1k:.2f}    | "
                f"${tr['blended_1k']:.2f} |\n")
        f.write(f"| 10K sessions   | ${opus_10k:.2f}  | ${haiku_10k:.2f}   | "
                f"${tr['blended_10k']:.2f} |\n")

        f.write("\n## Scoring Rubric\n\n")
        f.write(SCORING_RUBRIC)
        f.write("\n\n## Next Steps\n\n")
        f.write("1. Read each candidate's output in `results/<candidate-name>/`\n")
        f.write("2. Score each on the 6-dimension rubric (1-5 per dim, max 30/test)\n")
        f.write("3. Pay special attention to Test 1 — the failing case\n")
        f.write("4. Record quality scores in `docs/decisions/002-synthesizer-"
                "selection.md`\n")
        f.write("5. Use quality-per-dollar (cost / score) to compare candidates\n")
        f.write(f"\nCost data JSON: {cost_json_path}\n")

    print(f"\n{'='*60}")
    print("Evaluation complete.")
    print(f"Results:   {results_dir}")
    print(f"Summary:   {summary_path}")
    print(f"Cost JSON: {cost_json_path}")
    if tier_routing.get("blended_per_session"):
        print(f"\nTier-routing blended cost: "
              f"${tier_routing['blended_per_session']:.6f}/session")
        print(f"  1K sessions: ${tier_routing['blended_1k']:.2f}")
        print(f"  10K sessions: ${tier_routing['blended_10k']:.2f}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_evaluation()
