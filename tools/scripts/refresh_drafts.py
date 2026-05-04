#!/usr/bin/env python3
"""
refresh_drafts.py — Re-run all current Gmail drafts through the latest pipeline.

Fetches every draft from Gmail, re-processes the original thread through the
current rules_engine → RAG → OpenAI → validators pipeline, and updates the
draft in-place. Never creates new drafts; never sends.

Usage:
    cd Ops/support/gmail-assistant
    python tools/scripts/refresh_drafts.py [--dry-run] [--limit N] [--delay 0.5]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "api"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "persistence"))

import gmail_client
import knowledge
import rag
import rules_engine
import validators
import scenario_contracts as sc_module

from process_emails_openai import (
    call_openai,
    build_node1_prompt,
    build_node2_prompt,
    normalize_thread,
    CONFIDENCE_THRESHOLD,
)

RULES_PATH = PROJECT_ROOT / "knowledge" / "flowmingo-rules.md"
SCEN_PATH  = PROJECT_ROOT / "knowledge" / "flowmingo-scenarios.md"

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


def _extract_to_addr(draft: dict) -> str:
    """Extract plain email address from 'Name <email>' or bare 'email'."""
    to = draft.get("to", "")
    if "<" in to and ">" in to:
        return to[to.index("<") + 1: to.index(">")].strip()
    return to.strip()


def refresh_draft(draft: dict, dry_run: bool = False) -> dict:
    """Re-run pipeline on the draft's thread and update the draft body."""
    draft_id  = draft["draft_id"]
    thread_id = draft["thread_id"]
    subject   = draft.get("subject", "")
    to_addr   = _extract_to_addr(draft)

    result = {
        "draft_id":  draft_id,
        "subject":   subject,
        "to":        to_addr,
        "status":    "unknown",
        "label":     None,
        "scenario":  None,
        "error":     None,
    }

    # Step 1 — fetch thread
    try:
        thread_data = gmail_client.get_thread(thread_id)
    except Exception as ex:
        result["status"] = "skip"
        result["error"]  = f"get_thread failed: {ex}"
        return result

    # Build normalised email dict
    email_meta = {
        "id":        draft.get("message_id", ""),
        "thread_id": thread_id,
        "from":      to_addr,
        "subject":   subject,
        "date":      draft.get("date", ""),
    }
    email = normalize_thread(thread_data, email_meta)
    # Force pipeline even if thread has a support reply (we WANT to re-draft)
    email = {**email, "has_support_reply": False}

    rules_text     = RULES_PATH.read_text(encoding="utf-8")
    scenarios_text = SCEN_PATH.read_text(encoding="utf-8")

    # Step 2 — rules_engine
    try:
        route_info    = rules_engine.route(email)
        is_bug        = route_info["is_bug"]
        risk_triggers = list(route_info["risk_triggers"])
    except Exception as ex:
        result["status"] = "skip"
        result["error"]  = f"rules_engine: {ex}"
        return result

    if is_bug:
        result["status"] = "skip"
        result["error"]  = "rules_engine: is_bug — skip (bug drafts managed separately)"
        return result

    # Step 3 — BM25
    email_text = email.get("latest_message", "") or email.get("subject", "")
    try:
        kb_text, kb_ids = rag.get_relevant_context_with_ids(
            rules_text=rules_text, scenarios_text=scenarios_text,
            email_text=email_text, top_k=5,
        )
    except AttributeError:
        kb_text = rag.get_relevant_context(rules_text, scenarios_text, email_text, top_k=5)

    # Step 4 — Node 1
    n1_sys, n1_usr = build_node1_prompt(email)
    try:
        resp1 = call_openai(API_KEY, n1_sys, n1_usr, max_tokens=400)
        node1 = resp1["result"]
    except Exception as ex:
        result["status"] = "error"
        result["error"]  = f"Node1: {ex}"
        return result

    model_scenario = node1.get("scenario", "unclear")
    scenario_conf  = float(node1.get("scenario_confidence", 0.5))

    # Step 5 — Contract
    contract, extra = sc_module.select(CONTRACTS, route_info["pre_route_hint"], model_scenario)
    risk_triggers.extend(extra)

    # Step 6 — Node 2
    email_body  = email.get("latest_message", "") or ""
    max_tokens2 = min(max(2000, len(email_body) // 3 + 600), 4000)
    n2_sys, n2_usr = build_node2_prompt(email, kb_text, node1, scenarios_text=scenarios_text)
    try:
        resp2 = call_openai(API_KEY, n2_sys, n2_usr, max_tokens=max_tokens2)
        cls   = resp2["result"]
    except Exception as ex:
        result["status"] = "error"
        result["error"]  = f"Node2: {ex}"
        return result

    draft_v1 = cls.get("draft_body", "")
    if not draft_v1.strip():
        result["status"] = "error"
        result["error"]  = "Node2 returned empty draft_body"
        return result

    # Step 7 — Validate
    try:
        v1 = validators.validate(draft_v1, contract, risk_triggers, scenario=model_scenario)
    except Exception as ex:
        v1 = {"severity": "UNKNOWN", "fixed_draft": draft_v1, "issues": [str(ex)]}

    final_draft = v1.get("fixed_draft") or draft_v1
    severity    = v1.get("severity", "PASS")

    # Determine label
    if scenario_conf < CONFIDENCE_THRESHOLD:
        label = "FM/review"
    elif severity in ("PASS", "LOW"):
        label = "FM/ready"
    else:
        label = "FM/review"

    if contract.get("force_review") and label == "FM/ready":
        label = "FM/review"

    result["label"]    = label
    result["scenario"] = model_scenario

    if dry_run:
        result["status"]       = "dry_run"
        result["new_draft_preview"] = final_draft[:300]
        return result

    # Step 8 — Update draft
    upd = gmail_client.update_draft(
        draft_id=draft_id,
        to=to_addr,
        subject=subject,
        body=final_draft,
        thread_id=thread_id,
    )

    if "error" in upd:
        result["status"] = "error"
        result["error"]  = upd["error"]
    else:
        result["status"]          = "refreshed"
        result["new_draft_id"]    = upd.get("draft_id", draft_id)

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true", help="Preview without updating drafts")
    parser.add_argument("--limit",    type=int,  default=0,   help="Max drafts to process (0 = all)")
    parser.add_argument("--delay",    type=float, default=0.5, help="Seconds between API calls")
    args = parser.parse_args()

    print(f"\nFetching Gmail drafts...")
    all_drafts = gmail_client.list_drafts()
    # Skip drafts that errored during metadata fetch
    drafts = [d for d in all_drafts if "error" not in d and d.get("thread_id")]
    if args.limit:
        drafts = drafts[:args.limit]

    print(f"{'DRY RUN — ' if args.dry_run else ''}Refreshing {len(drafts)} drafts | API key: ...{API_KEY[-8:]}\n")
    print("=" * 72)

    refreshed = failed = skipped = 0

    for i, draft in enumerate(drafts, 1):
        subj = draft.get("subject", "(no subject)")[:50]
        to   = _extract_to_addr(draft)[:30]
        print(f"[{i:2d}/{len(drafts)}] {subj}")
        print(f"        to: {to}")

        r = refresh_draft(draft, dry_run=args.dry_run)

        if r["status"] == "refreshed":
            refreshed += 1
            print(f"        OK  {r['label']} | {r['scenario']}")
        elif r["status"] == "dry_run":
            refreshed += 1
            print(f"        DRY {r['label']} | {r['scenario']}")
            print(f"        preview: {repr(r.get('new_draft_preview','')[:120])}")
        elif r["status"] == "skip":
            skipped += 1
            print(f"        SKIP: {r['error']}")
        else:
            failed += 1
            print(f"        ERROR: {r['error']}")

        if args.delay:
            time.sleep(args.delay)

    print("=" * 72)
    print(f"DONE: {refreshed} refreshed / {failed} errors / {skipped} skipped")


if __name__ == "__main__":
    main()
