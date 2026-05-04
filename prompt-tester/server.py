#!/usr/bin/env python3
"""
server.py — Flask prompt tester for the Gmail support pipeline.

Runs the full production pipeline (rules_engine -> BM25 -> Node1 gpt-4o-mini ->
Node2 gpt-4o-mini -> validators) against saved sample emails. Lets you edit
flowmingo-rules.md and flowmingo-scenarios.md and instantly see the effect.

Usage:
    cd Ops/support/gmail-assistant/prompt-tester
    pip install flask openai
    python server.py
    # Opens at http://localhost:3001

CRITICAL: Must be launched from the prompt-tester/ directory.
"""

import json
import os
import shutil
import sys
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

# ── Python path: import production modules from src/api/ ─────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "api"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "persistence"))
sys.path.insert(0, str(PROJECT_ROOT / "tools" / "scripts"))

print(f"Python path: {PROJECT_ROOT / 'src' / 'api'}")

import rules_engine
import rag
import knowledge
import validators
import scenario_contracts as sc_module

# Import pipeline functions from the production script
from process_emails_openai import (
    call_openai,
    build_node1_prompt,
    build_node2_prompt,
    NODE1_CLASSIFIER_SCHEMA,
    NODE2_DRAFT_RULES,
    CONFIDENCE_THRESHOLD,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
SAMPLES_DIR  = Path(__file__).parent / "samples"
RULES_PATH   = PROJECT_ROOT / "knowledge" / "flowmingo-rules.md"
SCEN_PATH    = PROJECT_ROOT / "knowledge" / "flowmingo-scenarios.md"
RULES_BAK    = Path(__file__).parent / "flowmingo-rules.bak.md"
SCEN_BAK     = Path(__file__).parent / "flowmingo-scenarios.bak.md"

# ── Create backups on first start (atomic: only if bak doesn't exist) ─────────
if not RULES_BAK.exists() and RULES_PATH.exists():
    shutil.copy2(RULES_PATH, RULES_BAK)
    print(f"Backup created: {RULES_BAK.name}")
if not SCEN_BAK.exists() and SCEN_PATH.exists():
    shutil.copy2(SCEN_PATH, SCEN_BAK)
    print(f"Backup created: {SCEN_BAK.name}")

# ── Load API key ───────────────────────────────────────────────────────────────
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
    print("ERROR: OPENAI_API_KEY not set. Add it to .env or set the env var.")
    sys.exit(1)

# ── Pre-load contracts ─────────────────────────────────────────────────────────
CONTRACTS = sc_module.load_all()
print(f"{len(CONTRACTS)} scenario contracts loaded.")

# ── mtime-based SOP reload ─────────────────────────────────────────────────────
_last_load: dict = {}

def _reload_knowledge_if_stale():
    """Reload knowledge module if either SOP file has changed since last load."""
    for path in (RULES_PATH, SCEN_PATH):
        if not path.exists():
            continue
        mtime = path.stat().st_mtime
        if _last_load.get(str(path), 0) < mtime:
            # Clear cached module so knowledge.load_rules() re-reads fresh
            for mod_name in ("knowledge",):
                if mod_name in sys.modules:
                    del sys.modules[mod_name]
            import knowledge as _k
            globals()["knowledge"] = _k
            _last_load[str(path)] = mtime
            break

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=".")
app.config["JSON_SORT_KEYS"] = False

PORT = int(os.environ.get("PORT", 3001))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_pipeline(sample: dict, rules_override: str = None, scenarios_override: str = None) -> dict:
    """
    Run the full production pipeline against one email sample.
    Returns a dict with: route, node1, node2, validation, timings.
    """
    start = time.time()

    # Allow caller to inject specific SOP text (for run-both)
    if rules_override is not None or scenarios_override is not None:
        rules_text    = rules_override    if rules_override    is not None else knowledge.load_rules()
        scenarios_text = scenarios_override if scenarios_override is not None else knowledge.load_scenarios()
    else:
        _reload_knowledge_if_stale()
        rules_text     = knowledge.load_rules()
        scenarios_text = knowledge.load_scenarios()

    result = {
        "sample_name": sample.get("name", ""),
        "from":        sample.get("from", ""),
        "subject":     sample.get("subject", ""),
        "expected_scenario": sample.get("expected_scenario", ""),
        "timings":     {},
        "route":       None,
        "node1":       None,
        "node2":       None,
        "validation":  None,
        "label":       "FM/review",
        "error":       None,
    }

    # ── Step 1: rules_engine.route() ──────────────────────────────────────────
    t0 = time.time()
    try:
        route_info    = rules_engine.route(sample)
        is_bug        = route_info["is_bug"]
        risk_triggers = list(route_info["risk_triggers"])
        result["route"] = route_info
    except Exception as ex:
        result["error"] = f"rules_engine failed: {ex}"
        return result
    result["timings"]["route_ms"] = round((time.time() - t0) * 1000)

    # ── Step 2: BM25 retrieval ────────────────────────────────────────────────
    t0 = time.time()
    if is_bug:
        result["label"] = "FM/bug"
        result["timings"]["total_ms"] = round((time.time() - start) * 1000)
        return result

    if "already_replied" in risk_triggers:
        result["label"] = "FM/review"
        result["timings"]["total_ms"] = round((time.time() - start) * 1000)
        return result

    email_text = sample.get("latest_message", "") or sample.get("subject", "")
    try:
        kb_text, kb_section_ids = rag.get_relevant_context_with_ids(
            rules_text=rules_text,
            scenarios_text=scenarios_text,
            email_text=email_text,
            top_k=5,
        )
        result["kb_section_ids"] = kb_section_ids
    except AttributeError:
        # Fallback: get_relevant_context_with_ids may not exist in all versions
        kb_text = rag.get_relevant_context(
            rules_text=rules_text,
            scenarios_text=scenarios_text,
            email_text=email_text,
            top_k=5,
        )
        kb_section_ids = []
        result["kb_section_ids"] = []
    result["timings"]["rag_ms"] = round((time.time() - t0) * 1000)

    # ── Step 3: Node 1 — intent classifier ───────────────────────────────────
    t0 = time.time()
    n1_sys, n1_usr = build_node1_prompt(sample)
    try:
        resp1 = call_openai(API_KEY, n1_sys, n1_usr, max_tokens=400)
        node1 = resp1["result"]
        result["node1"] = {
            **node1,
            "input_tokens":  resp1.get("input_tokens", 0),
            "output_tokens": resp1.get("output_tokens", 0),
        }
    except Exception as ex:
        result["error"] = f"Node1 API error: {ex}"
        result["label"] = "FM/review"
        result["timings"]["total_ms"] = round((time.time() - start) * 1000)
        return result
    result["timings"]["node1_ms"] = round((time.time() - t0) * 1000)

    model_scenario_id   = node1.get("scenario", "unclear")
    scenario_confidence = float(node1.get("scenario_confidence", 0.5))

    # ── Step 4: Contract selection ────────────────────────────────────────────
    contract, extra_triggers = sc_module.select(CONTRACTS, route_info["pre_route_hint"], model_scenario_id)
    risk_triggers.extend(extra_triggers)

    # ── Step 5: Node 2 — draft writer ─────────────────────────────────────────
    t0 = time.time()
    # Dynamic max_tokens: Phase 6 fix
    email_body  = sample.get("latest_message", "") or ""
    max_tokens2 = min(max(2000, len(email_body) // 3 + 600), 4000)

    n2_sys, n2_usr = build_node2_prompt(sample, kb_text, node1, scenarios_text=scenarios_text)
    try:
        resp2 = call_openai(API_KEY, n2_sys, n2_usr, max_tokens=max_tokens2)
        cls   = resp2["result"]
        result["node2"] = {
            **cls,
            "input_tokens":  resp2.get("input_tokens", 0),
            "output_tokens": resp2.get("output_tokens", 0),
            "max_tokens_used": max_tokens2,
        }
    except Exception as ex:
        result["error"] = f"Node2 API error: {ex}"
        result["label"] = "FM/review"
        result["timings"]["total_ms"] = round((time.time() - start) * 1000)
        return result
    result["timings"]["node2_ms"] = round((time.time() - t0) * 1000)

    # ── Step 6: Validators ────────────────────────────────────────────────────
    t0 = time.time()
    draft_body_v1 = cls.get("draft_body", "")
    try:
        v1 = validators.validate(draft_body_v1, contract, risk_triggers, scenario=model_scenario_id)
        result["validation"] = v1
    except Exception as ex:
        result["validation"] = {"error": str(ex), "severity": "UNKNOWN", "fixed_draft": draft_body_v1}
    result["timings"]["validate_ms"] = round((time.time() - t0) * 1000)

    # ── Determine label ───────────────────────────────────────────────────────
    severity = (result["validation"] or {}).get("severity", "PASS")
    if scenario_confidence < CONFIDENCE_THRESHOLD:
        result["label"] = "FM/review"
        result["label_reason"] = f"LOW_CONFIDENCE ({scenario_confidence:.2f})"
    elif severity in ("PASS", "LOW"):
        result["label"] = "FM/ready"
    elif severity == "MEDIUM":
        result["label"] = "FM/review"
        result["label_reason"] = f"MEDIUM validator ({'; '.join((result['validation'] or {}).get('issues', [])[:2])})"
    elif severity == "HIGH":
        result["label"] = "FM/review"
        result["label_reason"] = f"HIGH validator"
    else:
        result["label"] = "FM/ready"

    if contract.get("force_review") and result["label"] == "FM/ready":
        result["label"] = "FM/review"
        result["label_reason"] = "FORCE_REVIEW contract"

    result["timings"]["total_ms"] = round((time.time() - start) * 1000)
    result["scenario_confidence"] = scenario_confidence
    result["model_scenario"] = model_scenario_id
    result["contract_id"] = contract.get("scenario_id", "FALLBACK")

    return result


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/samples")
def list_samples():
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(f.name for f in SAMPLES_DIR.glob("*.json"))
    return jsonify({"samples": files})


@app.route("/sample/<name>")
def get_sample(name: str):
    safe = Path(name).name
    if not safe.endswith(".json"):
        return jsonify({"error": "Invalid sample name"}), 400
    path = SAMPLES_DIR / safe
    if not path.exists():
        return jsonify({"error": f"Sample not found: {safe}"}), 404
    return jsonify(json.loads(path.read_text(encoding="utf-8")))


@app.route("/prompt", methods=["GET", "POST"])
def prompt_rules():
    if request.method == "GET":
        if not RULES_PATH.exists():
            return jsonify({"error": "flowmingo-rules.md not found"}), 404
        return jsonify({"content": RULES_PATH.read_text(encoding="utf-8")})
    content = request.json.get("content")
    if not isinstance(content, str):
        return jsonify({"error": "content must be a string"}), 400
    RULES_PATH.write_text(content, encoding="utf-8")
    # Force reload on next /run call
    _last_load.pop(str(RULES_PATH), None)
    return jsonify({"ok": True})


@app.route("/prompt-bak")
def prompt_rules_bak():
    if not RULES_BAK.exists():
        return jsonify({"error": "Backup not found"}), 404
    return jsonify({"content": RULES_BAK.read_text(encoding="utf-8")})


@app.route("/prompt2", methods=["GET", "POST"])
def prompt_scenarios():
    if request.method == "GET":
        if not SCEN_PATH.exists():
            return jsonify({"error": "flowmingo-scenarios.md not found"}), 404
        return jsonify({"content": SCEN_PATH.read_text(encoding="utf-8")})
    content = request.json.get("content")
    if not isinstance(content, str):
        return jsonify({"error": "content must be a string"}), 400
    SCEN_PATH.write_text(content, encoding="utf-8")
    _last_load.pop(str(SCEN_PATH), None)
    return jsonify({"ok": True})


@app.route("/prompt2-bak")
def prompt_scenarios_bak():
    if not SCEN_BAK.exists():
        return jsonify({"error": "Backup not found"}), 404
    return jsonify({"content": SCEN_BAK.read_text(encoding="utf-8")})


@app.route("/run", methods=["POST"])
def run_pipeline():
    body = request.json or {}
    sample_name = body.get("sample_name") or body.get("sampleName")
    if not sample_name:
        return jsonify({"error": "sample_name required"}), 400

    safe = Path(sample_name).name
    if not safe.endswith(".json"):
        safe += ".json"
    path = SAMPLES_DIR / safe
    if not path.exists():
        return jsonify({"error": f"Sample not found: {safe}"}), 404

    sample = json.loads(path.read_text(encoding="utf-8"))
    result = _run_pipeline(sample)
    return jsonify(result)


@app.route("/run-both", methods=["POST"])
def run_both():
    body = request.json or {}
    sample_name = body.get("sample_name") or body.get("sampleName")
    if not sample_name:
        return jsonify({"error": "sample_name required"}), 400

    safe = Path(sample_name).name
    if not safe.endswith(".json"):
        safe += ".json"
    path = SAMPLES_DIR / safe
    if not path.exists():
        return jsonify({"error": f"Sample not found: {safe}"}), 404

    sample = json.loads(path.read_text(encoding="utf-8"))

    bak_rules    = RULES_BAK.read_text(encoding="utf-8")     if RULES_BAK.exists()  else None
    bak_scenarios = SCEN_BAK.read_text(encoding="utf-8")     if SCEN_BAK.exists()   else None
    curr_rules   = RULES_PATH.read_text(encoding="utf-8")    if RULES_PATH.exists() else ""
    curr_scenarios = SCEN_PATH.read_text(encoding="utf-8")   if SCEN_PATH.exists()  else ""

    if bak_rules is None or bak_scenarios is None:
        old_result = {"error": "Original backup not available"}
    else:
        old_result = _run_pipeline(sample, rules_override=bak_rules, scenarios_override=bak_scenarios)

    new_result = _run_pipeline(sample, rules_override=curr_rules, scenarios_override=curr_scenarios)

    return jsonify({"old": old_result, "new": new_result})


# ── Static files ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(str(Path(__file__).parent), "index.html")


@app.route("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(str(Path(__file__).parent), filename)


# ── Start ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\nFlowmingo Gmail Prompt Tester")
    print(f"Samples dir:    {SAMPLES_DIR} ({len(list(SAMPLES_DIR.glob('*.json')))} samples)")
    print(f"Rules SOP:      {RULES_PATH}")
    print(f"Scenarios SOP:  {SCEN_PATH}")
    print(f"\nRunning at http://localhost:{PORT}\n")
    app.run(host="0.0.0.0", port=PORT, debug=False)
