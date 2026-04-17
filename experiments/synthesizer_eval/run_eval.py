"""
experiments/synthesizer-eval/run_eval.py

Synthesizer Evaluation Harness
================================
Runs three fixed test prompts through multiple synthesizer candidates.
Each candidate receives identical input. Outputs saved to results/.

Usage:
    cd /path/to/ai-roundtable
    python -m experiments.synthesizer-eval.run_eval

Requirements:
    API keys in backend/.env for each candidate you want to test.
    OPENROUTER_API_KEY required for open-weight models.

Candidates tested:
    - Claude Opus 4.7 (Anthropic)
    - GPT-4o (OpenAI)
    - Gemini 2.5 Pro (Google)
    - DeepSeek V3 (via OpenRouter, if key available)
    - Qwen 2.5 72B (via OpenRouter, if key available)
    - Llama 3.3 70B (via OpenRouter, if key available)
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Load .env from backend/
env_path = Path(__file__).parent.parent.parent / "backend" / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# Insert repo root so `from backend.` imports work when run as a module
repo_root = Path(__file__).parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from experiments.synthesizer_eval.prompts import (  # noqa: E402
    TEST1_USER_PROMPT, TEST1_ROUND1, TEST1_PERPLEXITY,
    TEST2_USER_PROMPT, TEST2_ROUND1, TEST2_PERPLEXITY,
    TEST3_USER_PROMPT, TEST3_ROUND1, TEST3_PERPLEXITY,
    SCORING_RUBRIC,
)

# ── Discover available candidates ─────────────────────────────────────────────

AVAILABLE_CANDIDATES = {}

try:
    import anthropic  # noqa: F401
    if os.environ.get("ANTHROPIC_API_KEY"):
        AVAILABLE_CANDIDATES["Claude (claude-opus-4-7)"] = "anthropic"
    else:
        print("ANTHROPIC_API_KEY not set — skipping Claude")
except ImportError:
    print("anthropic SDK not installed — skipping Claude")

try:
    import openai  # noqa: F401
    if os.environ.get("OPENAI_API_KEY"):
        AVAILABLE_CANDIDATES["GPT-4o (openai)"] = "openai"
    else:
        print("OPENAI_API_KEY not set — skipping GPT-4o")
except ImportError:
    print("openai SDK not installed — skipping GPT-4o")

try:
    from google import genai as _genai  # noqa: F401
    if os.environ.get("GOOGLE_API_KEY"):
        AVAILABLE_CANDIDATES["Gemini 2.5 Pro (google)"] = "google"
    else:
        print("GOOGLE_API_KEY not set — skipping Gemini")
except ImportError:
    print("google-genai SDK not installed — skipping Gemini")

if os.environ.get("OPENROUTER_API_KEY"):
    AVAILABLE_CANDIDATES["DeepSeek-V3 (openrouter)"] = "openrouter_deepseek"
    AVAILABLE_CANDIDATES["Qwen2.5-72B (openrouter)"] = "openrouter_qwen"
    AVAILABLE_CANDIDATES["Llama-3.3-70B (openrouter)"] = "openrouter_llama"
else:
    print("OPENROUTER_API_KEY not set — skipping DeepSeek, Qwen, Llama")
    print("Add OPENROUTER_API_KEY to backend/.env to include open-weight models")

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

# ── Call functions per provider ───────────────────────────────────────────────

def call_anthropic(user_message: str, system: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def call_openai(user_message: str, system: str) -> str:
    import openai
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=2000,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content


def call_google(user_message: str, system: str) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=[types.Content(role="user", parts=[types.Part(text=user_message)])],
        config=types.GenerateContentConfig(
            max_output_tokens=2000,
            system_instruction=system,
        ),
    )
    return response.text


OPENROUTER_MODEL_IDS = {
    "openrouter_deepseek": "deepseek/deepseek-chat-v3-0324",
    "openrouter_qwen":     "qwen/qwen-2.5-72b-instruct",
    "openrouter_llama":    "meta-llama/llama-3.3-70b-instruct",
}


def call_openrouter(user_message: str, system: str, model_id: str) -> str:
    import httpx
    headers = {
        "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "max_tokens": 2000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ],
    }
    response = httpx.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def call_candidate(candidate_key: str, user_message: str, system: str) -> str:
    provider = AVAILABLE_CANDIDATES[candidate_key]
    if provider == "anthropic":
        return call_anthropic(user_message, system)
    elif provider == "openai":
        return call_openai(user_message, system)
    elif provider == "google":
        return call_google(user_message, system)
    elif provider.startswith("openrouter_"):
        model_id = OPENROUTER_MODEL_IDS[provider]
        return call_openrouter(user_message, system, model_id)
    else:
        return f"[Unknown provider: {provider}]"

# ── Build user message for synthesis ─────────────────────────────────────────

def build_user_message(user_prompt: str, round1: dict, perplexity: str) -> str:
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

# ── Test definitions ──────────────────────────────────────────────────────────

TESTS = [
    {
        "id": "test1-factual",
        "name": "Factual Current Data (the failing case)",
        "user_prompt": TEST1_USER_PROMPT,
        "round1": TEST1_ROUND1,
        "perplexity": TEST1_PERPLEXITY,
        "pass_criteria": [
            "Must present Claude Opus 4.7 at $5/$25",
            "Must mention Claude 3 Opus retirement (Jan 5, 2026)",
            "Must NOT present $15/$75 as current pricing",
            "Must NOT call Perplexity data fabricated or unverifiable",
        ],
    },
    {
        "id": "test2-analytical",
        "name": "Analytical Synthesis (the working case)",
        "user_prompt": TEST2_USER_PROMPT,
        "round1": TEST2_ROUND1,
        "perplexity": TEST2_PERPLEXITY,
        "pass_criteria": [
            "Must mention DPO as the practical default",
            "Must attribute claims to specific round-1 models",
            "Must include expert perspective beyond summarizing",
            "Must end with concrete actionable next steps",
        ],
    },
    {
        "id": "test3-domain",
        "name": "Domain Technical (the showcase case)",
        "user_prompt": TEST3_USER_PROMPT,
        "round1": TEST3_ROUND1,
        "perplexity": TEST3_PERPLEXITY,
        "pass_criteria": [
            "Must use RCA/RAA/QMRIC terminology (not MRI)",
            "Must note that Gemini's MRI terminology was incorrect",
            "Must mention DNV synthetic profiles",
            "Must mention Phase 1/Phase 2 implementation timeline",
        ],
    },
]

# ── Run evaluation ────────────────────────────────────────────────────────────

def run_evaluation():
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    system = build_synthesis_system_prompt()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    all_results = {}

    print(f"\n{'='*60}")
    print("Synthesizer Evaluation Harness")
    print(f"Candidates: {len(AVAILABLE_CANDIDATES)}")
    print(f"Tests:      {len(TESTS)}")
    print(f"{'='*60}\n")

    if not AVAILABLE_CANDIDATES:
        print("No candidates available. Check API keys in backend/.env.")
        return

    for candidate_key in AVAILABLE_CANDIDATES:
        print(f"\n── {candidate_key} ──")
        safe_name = candidate_key.replace(" ", "-").replace("/", "-").replace("(", "").replace(")", "")
        candidate_dir = results_dir / safe_name
        candidate_dir.mkdir(exist_ok=True)
        all_results[candidate_key] = {}

        for test in TESTS:
            print(f"  Running {test['id']}...", end=" ", flush=True)
            user_message = build_user_message(
                test["user_prompt"],
                test["round1"],
                test["perplexity"],
            )

            try:
                start = time.time()
                output = call_candidate(candidate_key, user_message, system)
                elapsed = round(time.time() - start, 1)
                status = "✓"
            except Exception as e:
                output = f"[ERROR: {e}]"
                elapsed = 0.0
                status = "✗"

            print(f"{status} ({elapsed}s)")

            result_path = candidate_dir / f"{test['id']}.md"
            with open(result_path, "w") as f:
                f.write(f"# {candidate_key} — {test['name']}\n\n")
                f.write(f"**Generated:** {timestamp}\n")
                f.write(f"**Elapsed:** {elapsed}s\n\n")
                f.write("## Pass Criteria\n\n")
                for criterion in test["pass_criteria"]:
                    f.write(f"- [ ] {criterion}\n")
                f.write("\n## Output\n\n")
                f.write(output)

            all_results[candidate_key][test["id"]] = {
                "output": output,
                "elapsed": elapsed,
                "status": status,
            }

            time.sleep(1)  # rate limit buffer

    # Write summary
    summary_path = results_dir / f"summary-{timestamp}.md"
    with open(summary_path, "w") as f:
        f.write("# Synthesizer Evaluation Summary\n\n")
        f.write(f"**Date:** {timestamp}\n")
        f.write(f"**Candidates tested:** {len(AVAILABLE_CANDIDATES)}\n\n")
        f.write("## Results Matrix\n\n")
        f.write("| Candidate | Test 1 Factual | Test 2 Analytical | Test 3 Domain |\n")
        f.write("|-----------|---------------|------------------|---------------|\n")
        for candidate_key in AVAILABLE_CANDIDATES:
            row = f"| {candidate_key} |"
            for test in TESTS:
                r = all_results[candidate_key][test["id"]]
                row += f" {r['status']} ({r['elapsed']}s) |"
            row += "\n"
            f.write(row)
        f.write("\n## Scoring Rubric\n\n")
        f.write(SCORING_RUBRIC)
        f.write("\n\n## Next Steps\n\n")
        f.write("1. Read each candidate's output in `results/<candidate-name>/`\n")
        f.write("2. Score each on the rubric above\n")
        f.write("3. Pay special attention to Test 1 — the failing case\n")
        f.write("4. Any candidate that calls Perplexity data 'fabricated' fails Test 1\n")
        f.write("5. Document decision in `docs/decisions/002-synthesizer-selection.md`\n")

    print(f"\n{'='*60}")
    print("Evaluation complete.")
    print(f"Results: {results_dir}")
    print(f"Summary: {summary_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    run_evaluation()
