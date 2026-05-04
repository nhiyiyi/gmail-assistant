#!/usr/bin/env python3
"""
batch_test.py — Run all samples through the full pipeline and report pass/fail.

Usage:
    cd Ops/support/gmail-assistant/prompt-tester
    python batch_test.py [--limit N] [--scenario SXX] [--verbose]

Exit code: 0 if all pass, 1 if any fail.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────────────────
HERE         = Path(__file__).parent
PROJECT_ROOT = HERE.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "api"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "persistence"))
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "scripts"))

import rules_engine
import rag
import knowledge
import validators
import scenario_contracts as sc_module

from process_emails_openai import (
    call_openai,
    build_node1_prompt,
    build_node2_prompt,
    CONFIDENCE_THRESHOLD,
)

# ── Config ─────────────────────────────────────────────────────────────────────
SAMPLES_DIR = HERE / "samples"
RULES_PATH  = PROJECT_ROOT / "knowledge" / "flowmingo-rules.md"
SCEN_PATH   = PROJECT_ROOT / "knowledge" / "flowmingo-scenarios.md"

def _load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

API_KEY = _load_api_key()
if not API_KEY:
    print("ERROR: OPENAI_API_KEY not set.")
    sys.exit(1)

CONTRACTS = sc_module.load_all()

# ── Criteria checks ────────────────────────────────────────────────────────────

def check_pass(result: dict, sample: dict) -> list[str]:
    """Return list of failure strings. Empty list = all pass."""
    failures = []
    if result.get("error"):
        return [f"PIPELINE_ERROR: {result['error']}"]

    scenario = result.get("model_scenario", "")
    expected = sample.get("expected_scenario", "")
    draft    = ""
    v        = result.get("validation") or {}

    # Get final draft (fixed or original)
    node2 = result.get("node2") or {}
    draft = v.get("fixed_draft") or node2.get("draft_body") or ""

    label = result.get("label", "")

    # 1. Correct scenario (skip if expected is empty, label is FM/bug, or expected is a non-scenario value)
    SKIP_SCENARIO_CHECK = {"UNCLEAR", "SKIP", "R3", "?", ""}
    if expected and label != "FM/bug" and expected.upper() not in SKIP_SCENARIO_CHECK:
        if scenario.upper() != expected.upper():
            failures.append(f"WRONG_SCENARIO: got {scenario}, expected {expected}")

    # 2. Greeting
    if draft and not draft.strip().startswith("Dear "):
        failures.append(f"BAD_GREETING: starts with {repr(draft.strip()[:40])}")

    # 3. Closing — must have both required lines
    if draft:
        if "Let us know if you have any questions," not in draft:
            failures.append("MISSING_CLOSING_1: 'Let us know if you have any questions,' not found")
        if "Best regards," not in draft:
            failures.append("MISSING_CLOSING_2: 'Best regards,' not found")

    # 4. No raw markdown (except S27)
    if draft and scenario != "S27":
        if re.search(r'\*\*[^*]+\*\*|\*[^*]+\*|^#{1,6}\s|`[^`]+`', draft, re.MULTILINE):
            failures.append("MARKDOWN_IN_DRAFT: raw markdown symbols found")

    # 5. Validator severity PASS or LOW
    severity = v.get("severity", "PASS")
    if severity in ("MEDIUM", "HIGH"):
        issues = v.get("issues", [])
        failures.append(f"VALIDATOR_{severity}: {'; '.join(issues[:3])}")

    return failures


# ── Pipeline runner ────────────────────────────────────────────────────────────

def run_sample(sample: dict) -> dict:
    rules_text    = RULES_PATH.read_text(encoding="utf-8")
    scenarios_text = SCEN_PATH.read_text(encoding="utf-8")

    result = {
        "sample_name": sample.get("name", ""),
        "timings":     {},
        "route":       None,
        "node1":       None,
        "node2":       None,
        "validation":  None,
        "label":       "FM/review",
        "error":       None,
    }

    # Step 1: rules_engine
    try:
        route_info    = rules_engine.route(sample)
        is_bug        = route_info["is_bug"]
        risk_triggers = list(route_info["risk_triggers"])
        result["route"] = route_info
    except Exception as ex:
        result["error"] = f"rules_engine: {ex}"
        return result

    if is_bug:
        result["label"] = "FM/bug"
        return result

    if "already_replied" in risk_triggers:
        result["label"] = "FM/review"
        result["label_reason"] = "already_replied"
        return result

    # Step 2: BM25
    email_text = sample.get("latest_message", "") or sample.get("subject", "")
    try:
        kb_text, kb_ids = rag.get_relevant_context_with_ids(
            rules_text=rules_text,
            scenarios_text=scenarios_text,
            email_text=email_text,
            top_k=5,
        )
        result["kb_section_ids"] = kb_ids
    except AttributeError:
        kb_text = rag.get_relevant_context(rules_text, scenarios_text, email_text, top_k=5)
        kb_ids  = []

    # Step 3: Node 1
    n1_sys, n1_usr = build_node1_prompt(sample)
    try:
        resp1  = call_openai(API_KEY, n1_sys, n1_usr, max_tokens=400)
        node1  = resp1["result"]
        result["node1"] = {**node1, "input_tokens": resp1.get("input_tokens", 0),
                                     "output_tokens": resp1.get("output_tokens", 0)}
    except Exception as ex:
        result["error"] = f"Node1: {ex}"
        return result

    model_scenario   = node1.get("scenario", "unclear")
    scenario_conf    = float(node1.get("scenario_confidence", 0.5))
    result["model_scenario"] = model_scenario

    # Step 4: Contract
    contract, extra = sc_module.select(CONTRACTS, route_info["pre_route_hint"], model_scenario)
    risk_triggers.extend(extra)

    # Step 5: Node 2
    email_body  = sample.get("latest_message", "") or ""
    max_tokens2 = min(max(2000, len(email_body) // 3 + 600), 4000)
    n2_sys, n2_usr = build_node2_prompt(sample, kb_text, node1, scenarios_text=scenarios_text)
    try:
        resp2 = call_openai(API_KEY, n2_sys, n2_usr, max_tokens=max_tokens2)
        cls   = resp2["result"]
        result["node2"] = {**cls, "input_tokens": resp2.get("input_tokens", 0),
                                   "output_tokens": resp2.get("output_tokens", 0)}
    except Exception as ex:
        result["error"] = f"Node2: {ex}"
        return result

    # Step 6: Validate
    draft_v1 = cls.get("draft_body", "")
    try:
        v1 = validators.validate(draft_v1, contract, risk_triggers, scenario=model_scenario)
        result["validation"] = v1
    except Exception as ex:
        result["validation"] = {"error": str(ex), "severity": "UNKNOWN", "fixed_draft": draft_v1}

    # Label
    severity = (result["validation"] or {}).get("severity", "PASS")
    if scenario_conf < CONFIDENCE_THRESHOLD:
        result["label"] = "FM/review"
        result["label_reason"] = f"LOW_CONFIDENCE ({scenario_conf:.2f})"
    elif severity in ("PASS", "LOW"):
        result["label"] = "FM/ready"
    elif severity == "MEDIUM":
        result["label"] = "FM/review"
    elif severity == "HIGH":
        result["label"] = "FM/review"
    else:
        result["label"] = "FM/ready"

    if contract.get("force_review") and result["label"] == "FM/ready":
        result["label"] = "FM/review"

    result["scenario_confidence"] = scenario_conf
    result["contract_id"]         = contract.get("scenario_id", "FALLBACK")
    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit",    type=int,  default=0,  help="Max samples to run (0 = all)")
    parser.add_argument("--scenario", type=str,  default="", help="Filter by expected_scenario")
    parser.add_argument("--verbose",  action="store_true",   help="Print full result on failure")
    parser.add_argument("--delay",    type=float, default=0.3, help="Seconds between API calls")
    parser.add_argument("--force",    action="store_true",   help="Override has_support_reply to force LLM run")
    args = parser.parse_args()

    sample_files = sorted(SAMPLES_DIR.glob("*.json"))
    if args.scenario:
        sample_files = [f for f in sample_files if args.scenario.upper() in f.stem.upper()]
    if args.limit:
        sample_files = sample_files[:args.limit]

    print(f"\nBatch test: {len(sample_files)} samples | API key: ...{API_KEY[-8:]}")
    print("=" * 70)

    passed = failed = skipped = 0
    failures_by_type: dict[str, list] = {}
    total_in = total_out = 0

    for i, fpath in enumerate(sample_files, 1):
        sample = json.loads(fpath.read_text(encoding="utf-8"))
        name   = sample.get("name", fpath.stem)
        exp    = sample.get("expected_scenario", "?")

        if sample.get("skip"):
            print(f"[{i:3d}] SKIP   {name} (bad_data)")
            skipped += 1
            continue

        if args.force:
            sample = {**sample, "has_support_reply": False}

        try:
            result = run_sample(sample)
        except Exception as ex:
            print(f"[{i:3d}] CRASH  {name}: {ex}")
            failed += 1
            continue

        # Token accounting
        n1 = result.get("node1") or {}
        n2 = result.get("node2") or {}
        total_in  += n1.get("input_tokens", 0)  + n2.get("input_tokens", 0)
        total_out += n1.get("output_tokens", 0) + n2.get("output_tokens", 0)

        label    = result.get("label", "?")
        scenario = result.get("model_scenario", "?")

        # Skip already_replied (pipeline correctly short-circuits — not a test failure)
        if result.get("label_reason") == "already_replied":
            print(f"[{i:3d}] SKIP   {name} (already_replied)")
            skipped += 1
            if args.delay:
                time.sleep(args.delay)
            continue

        fs = check_pass(result, sample)
        status = "PASS" if not fs else "FAIL"

        if not fs:
            passed += 1
            print(f"[{i:3d}] PASS   {name} -> {scenario} | {label}")
        else:
            failed += 1
            failures_by_type.setdefault(fs[0].split(":")[0], []).append(name)
            print(f"[{i:3d}] FAIL   {name}")
            print(f"       expected={exp} got={scenario} | {label}")
            for f in fs:
                print(f"       FAIL: {f}")
            if args.verbose:
                v = result.get("validation") or {}
                print(f"       draft[:200]: {repr((v.get('fixed_draft') or '')[:200])}")

        if args.delay:
            time.sleep(args.delay)

    print("=" * 70)
    print(f"RESULTS: {passed} passed / {failed} failed / {skipped} skipped")
    print(f"TOKENS:  {total_in} in / {total_out} out  (~${(total_in*0.15 + total_out*0.60)/1_000_000:.3f})")

    if failures_by_type:
        print("\nFailure breakdown:")
        for ftype, names in sorted(failures_by_type.items(), key=lambda x: -len(x[1])):
            print(f"  {ftype}: {len(names)}x  -> {', '.join(names[:5])}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
