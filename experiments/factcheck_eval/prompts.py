"""
experiments/factcheck_eval/prompts.py

Factcheck eval candidates, test cases, and automated scorer.

Candidates receive identical round-1 inputs. Every check is deterministic
against fixed ground truth — no model judgment involved in scoring.
"""

# ── Candidate registry ────────────────────────────────────────────────────────
# input_rate / output_rate: USD per 1M tokens

FACTCHECK_CANDIDATES = {
    "Perplexity-Sonar-Pro": {
        "provider":     "perplexity",
        "model":        "llama-3.1-sonar-large-128k-online",
        "has_live_web": True,
        "input_rate":   1.00,   # per MTok
        "output_rate":  1.00,
        "notes":        "Primary candidate — highest quality Perplexity tier",
    },
    "Perplexity-Sonar": {
        "provider":     "perplexity",
        "model":        "llama-3.1-sonar-small-128k-online",
        "has_live_web": True,
        "input_rate":   0.20,
        "output_rate":  0.20,
        "notes":        "Fallback1 candidate — cheaper Perplexity tier",
    },
    "GPT-5.4-WebSearch": {
        "provider":     "openai_websearch",
        "model":        "gpt-5.4",
        "has_live_web": True,
        "input_rate":   2.50,
        "output_rate":  10.00,
        "notes":        "Fallback2 candidate — cross-provider with web search",
    },
}

# Optional additional candidates if time permits
OPTIONAL_CANDIDATES = {
    "Gemini-3-Flash-Search": {
        "provider":     "google_search",
        "model":        "gemini-3-flash-preview",
        "has_live_web": True,
        "input_rate":   0.075,
        "output_rate":  0.30,
        "notes":        "Informational only — not in current fallback chain",
    },
}

# ── Test cases with known ground truth ───────────────────────────────────────

FACTCHECK_TESTS = [
    {
        "id": "test1-catch-retired-model",
        "name": "Catch a retired model presented as current",
        "description": (
            "Critical test. Round-1 states Claude 3 Opus as current flagship. "
            "Must catch retirement and provide correct current pricing."
        ),
        "round1_claims": {
            "Gemini": (
                "Claude 3 Opus is Anthropic's flagship model at $15 per million "
                "input tokens and $75 per million output tokens with a 200K "
                "token context window."
            ),
            "GPT": (
                "The current Claude flagship is Claude 3 Opus, priced at "
                "$15/$75 per million tokens for input/output respectively."
            ),
            "Grok": (
                "Anthropic's most capable model is Claude 3 Opus at "
                "$15 input / $75 output per million tokens."
            ),
            "Claude": (
                "Claude 3 Opus at $15/$75 per MTok remains the benchmark "
                "for complex reasoning tasks."
            ),
        },
        "known_ground_truth": {
            "correct": (
                "Claude 3 Opus was retired January 5, 2026. "
                "Current flagship: Claude Opus 4.7 at $5/$25 per MTok, "
                "1M token context window."
            ),
            "error_type": "stale_pricing_retired_model",
        },
        "automated_checks": {
            "must_flag":          ["$15", "$75", "Claude 3 Opus"],
            "must_mention":       ["retired", "deprecated", "4.7", "$5", "$25"],
            "must_have_citation": True,
            "hard_gate":          True,  # failing this disqualifies for primary
        },
    },
    {
        "id": "test2-confirm-correct-terminology",
        "name": "Confirm correct technical terminology",
        "description": (
            "False positive test. Round-1 uses correct ISO-NE terminology. "
            "Must confirm without incorrectly flagging as wrong."
        ),
        "round1_claims": {
            "Claude": (
                "ISO New England uses Resource Capacity Accreditation (RCA) "
                "methodology with a Resource Adequacy Adjustment (RAA) model "
                "to calculate Qualified Marginal Reliability Impact Capacity "
                "(QMRIC) for offshore wind resources."
            ),
            "Gemini": (
                "ISO-NE's offshore wind capacity accreditation methodology "
                "uses marginal reliability impact calculations phased in "
                "for Forward Capacity Auction 19."
            ),
        },
        "known_ground_truth": {
            "correct":    "RCA/RAA/QMRIC terminology is correct per ISO-NE documentation.",
            "error_type": None,
        },
        "automated_checks": {
            "must_not_flag_as_wrong": ["RCA", "RAA", "QMRIC"],
            "false_positive_check":   True,
            "hard_gate":              False,
        },
    },
    {
        "id": "test3-catch-wrong-statistic",
        "name": "Catch a partially correct claim with wrong number",
        "description": (
            "Round-1 gets the direction right but the number wrong. "
            "Must correct the specific figure and cite source."
        ),
        "round1_claims": {
            "GPT": (
                "DPO has become the standard alignment technique, used in "
                "approximately 50% of enterprise LLM deployments in 2026."
            ),
            "Grok": (
                "Direct Preference Optimization now dominates with about "
                "half of production systems using it over PPO-based RLHF."
            ),
        },
        "known_ground_truth": {
            "correct": (
                "DPO and variants (GRPO, DAPO, KTO) are used in ~70% "
                "of enterprise deployments, not 50%."
            ),
            "error_type": "incorrect_statistic",
        },
        "automated_checks": {
            "must_flag_number":        "50%",
            "must_provide_correction": ["70", "70%"],
            "must_have_citation":      True,
            "hard_gate":               False,
        },
    },
    {
        "id": "test4-structured-output-four-sections",
        "name": "Structured output — all four sections present",
        "description": (
            "Tests whether output matches required four-section audit format. "
            "Synthesis depends on this structure being parseable."
        ),
        "round1_claims": {
            "Gemini": (
                "The transformer architecture remains dominant in 2026. "
                "Mixture of Experts models are becoming standard."
            ),
            "Claude": (
                "Transformers are still dominant but hybrid architectures "
                "combining attention with SSM layers are emerging in production."
            ),
        },
        "known_ground_truth": {
            "correct":    "Both claims are broadly correct.",
            "error_type": None,
        },
        "automated_checks": {
            "must_have_sections": [
                "Facts That Are Outdated",
                "Important Current Information",
                "Tools or Frameworks",
                "Current Practitioner",
            ],
            "section_count": 4,
            "hard_gate":     False,
        },
    },
    {
        "id": "test5-citation-specificity",
        "name": "Citation quality — specific vs vague",
        "description": (
            "Tests whether citations are specific (URL, date, publication) "
            "or vague ('official sources', 'check their website'). "
            "Vague citations provide no grounding value for synthesis."
        ),
        "round1_claims": {
            "Gemini": (
                "GPT-4o is OpenAI's current flagship model at $5 per million "
                "input tokens and $15 per million output tokens."
            ),
        },
        "known_ground_truth": {
            "correct": (
                "GPT-4o was retired from ChatGPT February 13, 2026. "
                "Current flagship is GPT-5.4."
            ),
            "error_type": "retired_model_as_current",
        },
        "automated_checks": {
            "must_flag_as_outdated":      True,
            "citation_must_not_be_vague": [
                "official sources", "official website",
                "check their website", "visit the page",
            ],
            "hard_gate": False,
        },
    },
    {
        "id": "test6-latency-smart",
        "name": "Latency — Smart tier audit",
        "description": (
            "Factcheck is on the critical path. Smart tier must complete "
            "within 15 seconds. Measures real-world latency per candidate."
        ),
        "round1_claims": {
            "Claude": (
                "ISO New England's total installed generating capacity is "
                "approximately 28,900 MW from nearly 400 dispatchable generators."
            ),
        },
        "known_ground_truth": {
            "correct":    "~28,900 MW is consistent with recent ISO-NE reporting.",
            "error_type": None,
        },
        "audit_tier": "smart",
        "automated_checks": {
            "max_latency_seconds": 15,
            "hard_gate":           False,
        },
    },
    {
        "id": "test7-depth-comparison-smart-vs-deep",
        "name": "Smart vs Deep audit depth comparison",
        "description": (
            "Same round-1 input, two audit depths. "
            "Measures whether Deep produces meaningfully more thorough output "
            "and whether Smart stays appropriately concise."
        ),
        "round1_claims": {
            "Gemini": (
                "ISO-NE's Forward Capacity Market has historically cleared "
                "enough capacity to meet reliability requirements. The market "
                "uses an Installed Capacity Requirement (ICR) to ensure "
                "sufficient resources are available during peak demand."
            ),
            "Claude": (
                "ISO New England uses a Forward Capacity Auction to procure "
                "resources three years in advance. The most recent auction "
                "cleared approximately 31,000 MW for the 2028-2029 delivery period."
            ),
        },
        "known_ground_truth": {
            "correct":    "Both claims are broadly accurate.",
            "error_type": None,
        },
        "run_both_tiers": True,   # run Smart AND Deep, compare output
        "automated_checks": {
            "smart_max_tokens": 800,
            "deep_min_tokens":  400,  # deep should be more thorough
            "hard_gate":        False,
        },
    },
]


# ── Automated scorer ──────────────────────────────────────────────────────────

def score_factcheck_result(
    test: dict,
    output: str,
    elapsed: float,
    tier: str = "smart",
) -> dict:
    """
    Score a factcheck result against known ground truth.
    Returns {"passed": int, "total": int, "failures": list, "score": float}
    """
    checks = test.get("automated_checks", {})
    output_lower = output.lower()
    failures = []
    passed = 0
    total = 0

    # must_mention: all terms must appear
    for term in checks.get("must_mention", []):
        total += 1
        if term.lower() in output_lower:
            passed += 1
        else:
            failures.append(f"missing: '{term}'")

    # must_flag: these claims should be flagged as wrong/outdated
    for term in checks.get("must_flag", []):
        total += 1
        # Check if output says something negative about this term
        idx = output_lower.find(term.lower())
        if idx == -1:
            failures.append(f"term not mentioned: '{term}'")
            continue
        window = output_lower[max(0, idx - 150):idx + len(term) + 150]
        flagged = any(
            w in window
            for w in ["outdated", "incorrect", "wrong", "retired",
                      "deprecated", "superseded", "inaccurate", "error"]
        )
        if flagged:
            passed += 1
        else:
            failures.append(f"not flagged as wrong: '{term}'")

    # must_not_flag_as_wrong: correct terms should not be flagged
    for term in checks.get("must_not_flag_as_wrong", []):
        total += 1
        idx = output_lower.find(term.lower())
        if idx == -1:
            passed += 1  # Not mentioned = not incorrectly flagged
            continue
        window = output_lower[max(0, idx - 150):idx + len(term) + 150]
        false_positive = any(
            w in window
            for w in ["incorrect", "wrong", "outdated", "false", "error"]
        )
        if not false_positive:
            passed += 1
        else:
            failures.append(f"false positive — incorrectly flagged: '{term}'")

    # must_provide_correction: correction terms should appear
    for term in checks.get("must_provide_correction", []):
        total += 1
        if term.lower() in output_lower:
            passed += 1
        else:
            failures.append(f"correction missing: '{term}'")

    # must_have_sections: structural check
    for section in checks.get("must_have_sections", []):
        total += 1
        if section.lower() in output_lower:
            passed += 1
        else:
            failures.append(f"missing section: '{section}'")

    # citation_must_not_be_vague
    vague = checks.get("citation_must_not_be_vague", [])
    if vague:
        total += 1
        found = [p for p in vague if p.lower() in output_lower]
        if not found:
            passed += 1
        else:
            failures.append(f"vague citations: {found}")

    # must_flag_as_outdated
    if checks.get("must_flag_as_outdated"):
        total += 1
        if any(w in output_lower for w in ["outdated", "retired", "deprecated", "wrong"]):
            passed += 1
        else:
            failures.append("did not flag claim as outdated")

    # must_flag_number
    flag_num = checks.get("must_flag_number")
    if flag_num:
        total += 1
        idx = output_lower.find(flag_num.lower())
        if idx == -1:
            failures.append(f"number '{flag_num}' not mentioned")
        else:
            window = output_lower[max(0, idx - 100):idx + len(flag_num) + 100]
            if any(w in window for w in ["incorrect", "wrong", "actually", "should be"]):
                passed += 1
            else:
                failures.append(f"number '{flag_num}' mentioned but not corrected")

    # Latency check
    max_lat = checks.get("max_latency_seconds")
    if max_lat is not None:
        total += 1
        if elapsed <= max_lat:
            passed += 1
        else:
            failures.append(f"too slow: {elapsed:.1f}s > {max_lat}s")

    score = (passed / total * 100) if total > 0 else 0
    return {
        "passed":               passed,
        "total":                total,
        "failures":             failures,
        "score":                score,
        "elapsed":              elapsed,
        "is_hard_gate_failure": (checks.get("hard_gate") and bool(failures)),
    }
