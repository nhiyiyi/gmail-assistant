#!/usr/bin/env python3
"""
extract_sent_examples.py — Pull recently sent support emails as ground-truth examples.

Fetches emails from the Gmail SENT folder, pairs each with the customer message
that preceded it, and saves them as annotated JSON files in knowledge/examples/.

These examples are used to write few-shot EXAMPLE REPLY blocks in flowmingo-scenarios.md.

Usage:
    cd Ops/support/gmail-assistant
    python tools/scripts/extract_sent_examples.py [--max 50] [--after 2026-04-01]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "api"))

import gmail_client

OUTPUT_DIR = PROJECT_ROOT / "knowledge" / "examples"

# Scenarios we most want examples for (in priority order)
TARGET_SCENARIOS = ["S7", "S9", "S20", "S15", "S16", "S18", "S21", "S22", "S34", "S8"]

# Keywords to infer scenario from subject/body (rough heuristic for labelling)
SCENARIO_HINTS = {
    "S7":  ["camera", "microphone", "device check", "mic check"],
    "S9":  ["mic not", "microphone not", "cannot record", "voice not detected", "first question"],
    "S20": ["still having", "still not working", "tried everything", "ongoing", "whatsapp", "ticket"],
    "S15": ["trustpilot", "loved", "great interview", "best interview", "enjoyed the process"],
    "S16": ["withdraw", "accepted another offer", "cannot proceed", "no longer"],
    "S18": ["1-2 weeks", "timeline", "when will", "results", "type a", "flowmingo role"],
    "S21": ["results", "follow up", "heard back", "shortlisted", "external company"],
    "S22": ["recruiter", "company", "pricing", "demo", "how does flowmingo", "want to use"],
    "S34": ["accept", "confirmed", "looking forward", "I will complete", "excited to"],
    "S8":  ["link not working", "404", "expired link", "link won't open", "invalid link"],
}

SUPPORT_DOMAINS = ["flowmingo.ai"]


def infer_scenario(subject: str, body: str) -> str:
    combined = (subject + " " + body).lower()
    for scenario, keywords in SCENARIO_HINTS.items():
        if any(kw in combined for kw in keywords):
            return scenario
    return "UNKNOWN"


def has_t1_steps(prior_messages: list) -> bool:
    T1_PHRASES = ["clear browser cache", "incognito", "private mode",
                  "different browser", "clear cache", "try chrome", "try safari"]
    for msg in prior_messages:
        body = (msg.get("body") or "").lower()
        if any(p in body for p in T1_PHRASES):
            return True
    return False


def has_t2_escalation(prior_messages: list) -> bool:
    for msg in prior_messages:
        body = (msg.get("body") or "").lower()
        if "989 877 953" in body or "whatsapp" in body:
            return True
    return False


def build_thread_summary(messages: list, sent_idx: int) -> str:
    """Build a human-readable thread summary for the example."""
    parts = []
    for i, msg in enumerate(messages):
        is_support = any(d in msg.get("from", "").lower() for d in SUPPORT_DOMAINS)
        sender = "Support" if is_support else "Customer"
        label = "→ [THIS REPLY]" if i == sent_idx else ""
        date_str = msg.get("date", "")[:16]
        snippet = (msg.get("body") or msg.get("snippet", ""))[:200].replace("\n", " ").strip()
        parts.append(f"[{date_str}] {sender}: {snippet} {label}")
    return "\n".join(parts)


def extract_sent_examples(max_results: int = 50, after: str = "2026-04-01") -> list:
    print(f"\nFetching sent emails (after {after}, max {max_results})...")

    sent_emails = gmail_client.list_emails(
        max_results=max_results,
        query=f"in:sent from:support@flowmingo.ai after:{after}",
    )

    if not sent_emails:
        print("No sent emails found.")
        return []

    print(f"Found {len(sent_emails)} sent emails. Processing threads...")

    examples = []
    seen_threads = set()

    for email_meta in sent_emails:
        thread_id = email_meta.get("thread_id")
        if not thread_id or thread_id in seen_threads:
            continue
        seen_threads.add(thread_id)

        try:
            thread_data = gmail_client.get_thread(thread_id)
        except Exception as ex:
            print(f"  WARN: get_thread failed for {email_meta.get('subject','')[:40]}: {ex}")
            continue

        messages = thread_data.get("messages", [])
        if len(messages) < 2:
            continue  # Need at least customer msg + support reply

        # Find the sent support message index
        sent_idx = None
        for i, msg in enumerate(messages):
            is_support = any(d in msg.get("from", "").lower() for d in SUPPORT_DOMAINS)
            labels = msg.get("labels", [])
            if is_support and "SENT" in labels and "DRAFT" not in labels:
                sent_idx = i  # Keep updating — we want the LAST sent reply

        if sent_idx is None:
            continue  # No actual sent reply found

        sent_msg = messages[sent_idx]
        sent_body = (sent_msg.get("body") or "").strip()
        if not sent_body or len(sent_body) < 50:
            continue  # Skip trivial/empty replies

        # Customer message that preceded this reply
        prior_msgs = messages[:sent_idx]
        customer_msgs = [
            m for m in prior_msgs
            if not any(d in m.get("from", "").lower() for d in SUPPORT_DOMAINS)
        ]
        if not customer_msgs:
            continue

        last_customer_msg = customer_msgs[-1]
        customer_text = (last_customer_msg.get("body") or last_customer_msg.get("snippet", "")).strip()[:1000]

        subject = email_meta.get("subject", "")
        scenario = infer_scenario(subject, sent_body + " " + customer_text)
        t1_given = has_t1_steps(prior_msgs)
        t2_given = has_t2_escalation(prior_msgs)
        thread_summary = build_thread_summary(messages, sent_idx)

        example = {
            "scenario": scenario,
            "subject": subject,
            "message_count": len(messages),
            "has_prior_t1_steps": t1_given,
            "prior_t2_escalation": t2_given,
            "is_repeat_contact": len(messages) > 3,
            "customer_message": customer_text,
            "thread_summary": thread_summary,
            "sent_reply": sent_body,
            "thread_id": thread_id,
        }
        examples.append(example)
        safe_subject = subject[:60].encode("ascii", "replace").decode("ascii")
        print(f"  + [{scenario}] {safe_subject} (msgs={len(messages)}, t1={t1_given}, t2={t2_given})")

    return examples


def save_examples(examples: list) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Group by scenario, keep up to 2 per scenario
    by_scenario: dict[str, list] = {}
    for ex in examples:
        s = ex["scenario"]
        by_scenario.setdefault(s, []).append(ex)

    saved = 0
    for scenario, group in sorted(by_scenario.items()):
        # Prefer multi-message examples (more context variety)
        group.sort(key=lambda x: x["message_count"], reverse=True)
        for i, ex in enumerate(group[:2]):
            slug = ex["subject"][:30].lower().replace(" ", "-").replace("/", "-").replace(":", "")
            fname = OUTPUT_DIR / f"sent-{scenario.lower()}-{i+1}-{slug}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(ex, f, indent=2, ensure_ascii=False)
            saved += 1
            print(f"  Saved: {fname.name}")

    print(f"\nTotal saved: {saved} examples in {OUTPUT_DIR}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=50)
    parser.add_argument("--after", default="2026-04-01")
    args = parser.parse_args()

    examples = extract_sent_examples(max_results=args.max, after=args.after)
    if examples:
        save_examples(examples)
    else:
        print("No examples to save.")


if __name__ == "__main__":
    main()
