#!/usr/bin/env python3
"""
process_emails_openai.py — Process Flowmingo support emails using OpenAI gpt-5-mini.

Replicates the /process-emails skill workflow without the Anthropic Claude CLI.
Runs as a standalone script in CI (GitHub Actions) or locally.

Usage:
    python tools/scripts/process_emails_openai.py

Requires:
    OPENAI_API_KEY environment variable
    Google credentials at credentials/credentials.json + credentials/token.json
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Path setup ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "api"))
sys.path.insert(0, str(PROJECT_ROOT / "src" / "persistence"))

import requests
import gmail_client
import knowledge
import rag
import state as state_module
import stats as stats_module
import sheets_client
import bug_template

# ── Config ───────────────────────────────────────────────────────────────────

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-4o-mini"
SUPPORT_DOMAINS = ["flowmingo.ai"]

NO_REPLY_FROM = [
    "noreply", "no-reply", "notifications@", "bounce@",
    "mailer-daemon", "donotreply", "do-not-reply", "postmaster@",
]
NO_REPLY_SUBJECT = [
    "verification code", "otp:", "unsubscribe", "auto-reply",
    "out of office", "delivery status notification", "mail delivery failed",
]


# ── OpenAI helper ────────────────────────────────────────────────────────────

def call_openai(api_key: str, system_prompt: str, user_prompt: str) -> dict:
    """Call OpenAI chat completions with JSON mode. Returns parsed JSON dict."""
    resp = requests.post(
        OPENAI_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage", {})
    text = body["choices"][0]["message"]["content"].strip()
    return {
        "result": json.loads(text),
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }


# ── Email batch (replicates _handle_get_email_batch from server.py) ──────────

def get_email_batch(max_results: int = 500) -> dict:
    emails = gmail_client.list_emails(
        max_results=min(max_results, 500),
        query="is:unread in:inbox",
    )
    if emails and isinstance(emails[0], dict) and "error" in emails[0]:
        return {"error": emails[0]["error"]}

    processed_ids = set(state_module.load_state().get("emails", {}).keys())
    already_count = sum(1 for e in emails if e.get("id") in processed_ids)
    new_emails = [e for e in emails if e.get("id") not in processed_ids]

    # Thread dedup (list_emails is newest-first; keep first occurrence)
    seen_threads: dict = {}
    for e in new_emails:
        tid = e.get("thread_id") or e["id"]
        if tid not in seen_threads:
            seen_threads[tid] = e
    deduped = list(seen_threads.values())
    thread_dedup_count = len(new_emails) - len(deduped)

    to_fetch, auto_skipped = [], []
    for e in deduped:
        from_lower = e.get("from", "").lower()
        subj_lower = e.get("subject", "").lower()
        if any(p in from_lower for p in NO_REPLY_FROM) or \
           any(p in subj_lower for p in NO_REPLY_SUBJECT):
            auto_skipped.append(e)
        else:
            to_fetch.append(e)

    to_process = []
    for e in to_fetch:
        try:
            thread_data = gmail_client.get_thread(e["thread_id"])
            to_process.append(_compact_summary(thread_data, e))
        except Exception as ex:
            print(f"  WARN: failed to fetch thread for {e.get('subject','')}: {ex}")

    sop_text = knowledge.load_all()
    kb_version = hashlib.sha256(sop_text.encode()).hexdigest()[:12]

    return {
        "to_process": to_process,
        "auto_skipped": auto_skipped,
        "already_processed_count": already_count,
        "thread_dedup_count": thread_dedup_count,
        "kb_version": kb_version,
    }


def _compact_summary(thread_data: dict, email_meta: dict) -> dict:
    messages = thread_data.get("messages", [])
    if not messages:
        return {**email_meta, "latest_message": "", "has_support_reply": False,
                "message_count": 0, "thread_context": "", "attachments": []}

    last_msg = messages[-1]
    has_support_reply = (
        any(d in last_msg.get("from", "").lower() for d in SUPPORT_DOMAINS)
        and "DRAFT" not in last_msg.get("labels", [])
    )
    latest_body = (last_msg.get("body") or last_msg.get("snippet", ""))[:1000]
    attachments = last_msg.get("attachments", [])

    prior_context = ""
    if len(messages) > 1:
        parts = []
        for msg in messages[:-1]:
            is_support = any(d in msg.get("from", "").lower() for d in SUPPORT_DOMAINS)
            sender = "Support" if is_support else msg.get("from", "").split("<")[0].strip()[:15]
            snippet = (msg.get("body") or msg.get("snippet", ""))[:100].replace("\n", " ")
            parts.append(f"[{msg.get('date', '')[:10]}] {sender}: {snippet}")
        prior_context = " | ".join(parts)[:500]

    return {
        "id": email_meta["id"],
        "thread_id": email_meta["thread_id"],
        "from": email_meta["from"],
        "subject": email_meta["subject"],
        "date": email_meta["date"],
        "message_count": len(messages),
        "has_support_reply": has_support_reply,
        "latest_message": latest_body,
        "attachments": attachments,
        "thread_context": prior_context,
    }


# ── Classification prompt ─────────────────────────────────────────────────────

CLASSIFICATION_SCHEMA = """\
Respond with a JSON object ONLY — no other text. Schema:
{
  "classification": "FM/no-reply" | "FM/bug" | "FM/ready" | "FM/review",
  "scenario": "S8" (matched scenario code, or "unclear"),
  "topic": "technical" | "candidate" | "partner" | "billing" | "other",
  "urgency": "normal" | "urgent" | "critical",
  "sender_type": "A" | "B" | "C" | "D" | "E",
  "draft_body": "..." (FM/ready and FM/review only; omit or null for FM/no-reply and FM/bug),
  "review_reason": "..." (FM/review only — exact [REVIEW NEEDED: ...] string; omit otherwise),
  "bug": {
    "customer_name": "...",
    "issue_summary": "...",
    "issue_summary_vi": "...",
    "main_issue_vi": "...",
    "issue_type": "...",
    "troubleshooting_steps": ["...", "..."],
    "original_message_trimmed": "..."
  }  // FM/bug only; omit otherwise
}

Classification rules summary:
- FM/no-reply: thread already has support reply (has_support_reply=true), OR disengaged statement with no request, OR automated/no-reply sender.
- FM/bug: D4=Bug signal (platform didn't work as expected, specific error, "it didn't work", image attachment present). Takes priority over all SOP scenarios.
- FM/review: use when any single dimension fails — D2=partial context, D3=not covered or fabrication risk, D5=elevated/critical, etc. MUST include exact [REVIEW NEEDED: <specific reason>] in review_reason AND prepend it to draft_body.
- FM/ready: all dimensions pass — question/brand moment, full context, fully covered, not a bug, normal sensitivity, no prior support reply.

For FM/ready and FM/review drafts, follow SOP email structure exactly:
- "Dear <Name>," — extract name from sign-off/signature, infer from email if missing
- Address issue directly
- Include exactly once: "Let us know if you have any questions,"
- End with: "Best regards," (no name after)
- English only, no emojis, no markdown

For FM/bug, set bug.main_issue_vi to a single Vietnamese sentence strictly under 10 words starting with the affected subject.
"""


def build_classify_prompt(email: dict, kb_text: str) -> tuple[str, str]:
    has_attachments = bool(email.get("attachments"))
    attachment_note = ""
    if has_attachments:
        att_list = [a.get("filename", a.get("mimeType", "unknown")) for a in email["attachments"]]
        attachment_note = f"\nAttachments: {', '.join(att_list)}"

    system_prompt = (
        "You are a Flowmingo customer support AI. "
        "Use the SOP below to classify and respond to support emails.\n\n"
        "=== FLOWMINGO SOP ===\n"
        f"{kb_text}\n"
        "=== END SOP ===\n\n"
        + CLASSIFICATION_SCHEMA
    )

    user_prompt = (
        f"Email ID: {email['id']}\n"
        f"From: {email['from']}\n"
        f"Subject: {email['subject']}\n"
        f"Date: {email.get('date', '')}\n"
        f"Has support reply already: {email.get('has_support_reply', False)}\n"
        f"Message count in thread: {email.get('message_count', 1)}"
        f"{attachment_note}\n\n"
        f"Customer message:\n{email.get('latest_message', '')}\n\n"
    )
    if email.get("thread_context"):
        user_prompt += f"Prior thread context:\n{email['thread_context']}\n"

    return system_prompt, user_prompt


# ── Submit drafts (replicates _handle_submit_drafts from server.py) ───────────

def submit_drafts(drafts: list, no_reply_items: list) -> dict:
    results = {"created": [], "no_reply_processed": 0, "failed": []}

    for item in no_reply_items:
        try:
            gmail_client.apply_labels(item["id"], ["FM/no-reply"])
            gmail_client.mark_as_read(item["id"])
            stats_module.log_processing(
                email_id=item["id"], input_tokens=0, output_tokens=0,
                subject=item.get("subject", ""), from_addr=item.get("from", ""),
                scenario="no-reply", topic="automated", urgency="normal",
                review_status="no-reply",
            )
            results["no_reply_processed"] += 1
        except Exception as ex:
            results["failed"].append({"id": item["id"], "error": str(ex)})

    for draft in drafts:
        eid = draft.get("email_id", "")
        try:
            dr = gmail_client.create_draft(
                to=draft["to"],
                subject=draft["subject"],
                body=draft.get("body", ""),
                thread_id=draft.get("thread_id"),
            )
            label = draft.get("label", "FM/ready")
            gmail_client.apply_labels(eid, [label])
            gmail_client.mark_as_read(eid)

            body_len = len(draft.get("body", ""))
            state_module.save_email(
                email_id=eid,
                thread_id=draft.get("thread_id", ""),
                from_addr=draft.get("from_addr", ""),
                subject=draft.get("subject", ""),
                date=draft.get("date", ""),
                sender_type=draft.get("sender_type", ""),
                topic=draft.get("topic", ""),
                scenario=draft.get("scenario", ""),
                urgency=draft.get("urgency", "normal"),
                review_status=draft.get("review_status", "ready"),
                draft_id=dr.get("draft_id", ""),
                draft_message_id=dr.get("message_id", ""),
                kb_version=draft.get("kb_version", ""),
                labels_applied=[label],
            )
            stats_module.log_processing(
                email_id=eid,
                input_tokens=draft.get("estimated_input_tokens", 500),
                output_tokens=max(body_len // 4, 50),
                subject=draft.get("subject", ""),
                from_addr=draft.get("from_addr", ""),
                scenario=draft.get("scenario", ""),
                topic=draft.get("topic", ""),
                urgency=draft.get("urgency", "normal"),
                review_status=draft.get("review_status", "ready"),
            )
            results["created"].append({"id": eid, "draft_id": dr.get("draft_id"), "label": label})
        except Exception as ex:
            results["failed"].append({"id": eid, "error": str(ex)})

    return results


# ── Bug ticket (replicates _handle_create_bug_ticket from server.py) ──────────

def create_bug_ticket(email: dict, bug: dict) -> dict:
    date_str = datetime.now().strftime("%y%m%d")
    sheet_id = sheets_client.get_sheet_id()
    seq = sheets_client.get_next_sequence(sheet_id, date_str) if sheet_id else 1
    ticket_id = f"BUG-{date_str}-{seq:03d}"
    submitted_at = datetime.now().strftime("%B %d, %Y %H:%M")

    html = bug_template.render_acknowledgment(
        ticket_code=ticket_id,
        customer_name=bug.get("customer_name", ""),
        issue_type=bug.get("issue_type", "Bug Report"),
        submitted_at=submitted_at,
        issue_summary=bug.get("issue_summary", ""),
        troubleshooting_steps=bug.get("troubleshooting_steps", []),
        original_message=bug.get("original_message_trimmed", ""),
    )

    draft_result = gmail_client.create_draft_html(
        to=email["from"],
        subject=email["subject"],
        html_body=html,
        thread_id=email["thread_id"],
    )
    draft_id = draft_result.get("draft_id", "")

    gmail_client.apply_labels(email["id"], ["FM/bug"])
    gmail_client.mark_as_read(email["id"])

    sheet_result = sheets_client.append_ticket_row({
        "ticket_id":        ticket_id,
        "date_created":     datetime.now().strftime("%Y-%m-%d %H:%M"),
        "customer_name":    bug.get("customer_name", ""),
        "email":            email["from"],
        "subject":          email["subject"],
        "issue_summary":    bug.get("issue_summary", ""),
        "issue_summary_vi": bug.get("issue_summary_vi", ""),
        "main_issue_vi":    bug.get("main_issue_vi", ""),
        "issue_type":       bug.get("issue_type", "Bug Report"),
        "draft_id":         draft_id,
        "thread_id":        email["thread_id"],
        "original_message": bug.get("original_message_trimmed", ""),
    })

    return {"ticket_id": ticket_id, "draft_id": draft_id, "sheet": sheet_result}


# ── Log action item (for FM/review) ──────────────────────────────────────────

def log_action_item(email: dict, cls: dict) -> None:
    review_reason = cls.get("review_reason", "")
    action_type = "DNC Request" if "do-not-contact" in review_reason.lower() or \
                                    "dnc" in review_reason.lower() else "Review Draft"
    priority = "High" if action_type == "DNC Request" else "Normal"
    sheets_client.append_action_row({
        "date":          datetime.now().strftime("%Y-%m-%d %H:%M"),
        "action_type":   action_type,
        "priority":      priority,
        "customer_name": cls.get("customer_name", ""),
        "email":         email.get("from", ""),
        "subject":       email.get("subject", ""),
        "reason":        review_reason,
        "thread_id":     email.get("thread_id", ""),
    })


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Load API key
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found.")
        sys.exit(1)

    # Ensure Gmail labels exist
    print("Setting up Gmail labels…")
    gmail_client.get_label_map()

    # Fetch email batch
    print("Fetching email batch…")
    batch = get_email_batch()
    if "error" in batch:
        print(f"ERROR fetching emails: {batch['error']}")
        sys.exit(1)

    to_process   = batch["to_process"]
    auto_skipped = batch["auto_skipped"]
    kb_version   = batch["kb_version"]

    print(
        f"Batch: {len(to_process)} to process, "
        f"{len(auto_skipped)} auto-skipped, "
        f"{batch['already_processed_count']} already processed, "
        f"{batch['thread_dedup_count']} thread dupes removed"
    )

    if not to_process and not auto_skipped:
        print("Nothing to process.")
        return

    # Load KB rules (base rules — used as foundation for all groups)
    rules_text     = knowledge.load_rules()
    scenarios_text = knowledge.load_scenarios()

    # Process in groups of 8
    GROUP_SIZE = 8
    all_drafts:     list = []
    all_no_reply:   list = []
    all_bug_emails: list = []
    first_group = True

    for group_start in range(0, len(to_process), GROUP_SIZE):
        group = to_process[group_start: group_start + GROUP_SIZE]
        print(f"\nGroup {group_start // GROUP_SIZE + 1}: {len(group)} emails")

        # Get relevant KB for this group
        group_query = "\n".join(
            f"{e.get('subject', '')}: {e.get('latest_message', '')[:200]}"
            for e in group
        )
        kb_text = rag.get_relevant_context(
            rules_text=rules_text,
            scenarios_text=scenarios_text,
            email_text=group_query,
            top_k=5,
        )

        group_drafts:   list = []
        group_no_reply: list = []

        for email in group:
            subj = email.get("subject", "")
            eid  = email.get("id", "")
            print(f"  [{eid[:8]}] {subj[:60]}", end=" → ", flush=True)

            try:
                sys_prompt, usr_prompt = build_classify_prompt(email, kb_text)
                resp = call_openai(api_key, sys_prompt, usr_prompt)
                cls  = resp["result"]
                inp  = resp["input_tokens"]
                out  = resp["output_tokens"]

                classification = cls.get("classification", "FM/review")
                print(classification, flush=True)

                if classification == "FM/no-reply":
                    group_no_reply.append({
                        "id":      eid,
                        "from":    email.get("from", ""),
                        "subject": subj,
                    })

                elif classification == "FM/bug":
                    bug = cls.get("bug", {})
                    all_bug_emails.append({"email": email, "bug": bug})

                elif classification in ("FM/ready", "FM/review"):
                    body = cls.get("draft_body") or ""
                    if classification == "FM/review" and cls.get("review_reason"):
                        # Ensure review reason prepended
                        reason = cls["review_reason"]
                        if not body.startswith("[REVIEW NEEDED"):
                            body = f"{reason}\n\n{body}"

                    review_status = "ready" if classification == "FM/ready" else "review"
                    group_drafts.append({
                        "email_id":               eid,
                        "thread_id":              email.get("thread_id", ""),
                        "to":                     email.get("from", ""),
                        "subject":                subj,
                        "body":                   body,
                        "label":                  classification,
                        "scenario":               cls.get("scenario", "unclear"),
                        "topic":                  cls.get("topic", "other"),
                        "urgency":                cls.get("urgency", "normal"),
                        "review_status":          review_status,
                        "sender_type":            cls.get("sender_type", "E"),
                        "from_addr":              email.get("from", ""),
                        "date":                   email.get("date", ""),
                        "kb_version":             kb_version,
                        "estimated_input_tokens": inp,
                        "review_reason":          cls.get("review_reason"),
                    })

                else:
                    print(f"  WARN: unknown classification '{classification}' — treating as FM/review")
                    group_drafts.append({
                        "email_id": eid, "thread_id": email.get("thread_id", ""),
                        "to": email.get("from", ""), "subject": subj,
                        "body": f"[REVIEW NEEDED: AI returned unknown classification '{classification}']\n\n",
                        "label": "FM/review", "scenario": "unclear", "topic": "other",
                        "urgency": "normal", "review_status": "review",
                        "sender_type": "E", "from_addr": email.get("from", ""),
                        "date": email.get("date", ""), "kb_version": kb_version,
                        "estimated_input_tokens": inp,
                    })

            except Exception as ex:
                print(f"ERROR: {ex}")
                # On failure, create a review draft so the email isn't silently lost
                group_drafts.append({
                    "email_id": eid, "thread_id": email.get("thread_id", ""),
                    "to": email.get("from", ""), "subject": subj,
                    "body": f"[REVIEW NEEDED: AI processing error — {ex}]\n\n",
                    "label": "FM/review", "scenario": "unclear", "topic": "other",
                    "urgency": "normal", "review_status": "review",
                    "sender_type": "E", "from_addr": email.get("from", ""),
                    "date": email.get("date", ""), "kb_version": kb_version,
                    "estimated_input_tokens": 0,
                })

            time.sleep(0.3)  # rate limit guard

        # Submit this group
        no_reply_to_submit = group_no_reply[:]
        if first_group:
            no_reply_to_submit += [
                {"id": e["id"], "from": e.get("from", ""), "subject": e.get("subject", "")}
                for e in auto_skipped
            ]
            first_group = False

        submit_result = submit_drafts(group_drafts, no_reply_to_submit)
        print(f"  Submitted: {len(submit_result['created'])} drafts, "
              f"{submit_result['no_reply_processed']} no-reply")
        if submit_result.get("failed"):
            for f in submit_result["failed"]:
                print(f"  FAIL: {f}")

        # Log action items for FM/review
        for draft in group_drafts:
            if draft.get("review_status") == "review":
                email_obj = next(
                    (e for e in group if e["id"] == draft["email_id"]), {}
                )
                try:
                    log_action_item(email_obj, draft)
                except Exception as ex:
                    print(f"  WARN: log_action_item failed: {ex}")

        all_drafts.extend(group_drafts)
        all_no_reply.extend(no_reply_to_submit)

    # Bug tickets
    if all_bug_emails:
        print(f"\nCreating {len(all_bug_emails)} bug ticket(s)…")
        for item in all_bug_emails:
            email = item["email"]
            bug   = item["bug"]
            try:
                result = create_bug_ticket(email, bug)
                print(f"  [{result['ticket_id']}] {email.get('subject', '')[:50]}")
            except Exception as ex:
                print(f"  ERROR creating bug ticket for {email.get('subject', '')}: {ex}")

    # Report
    print("\n=== Summary ===")
    ready_count   = sum(1 for d in all_drafts if d.get("review_status") == "ready")
    review_count  = sum(1 for d in all_drafts if d.get("review_status") == "review")
    no_reply_count = len([i for i in all_no_reply if i.get("id")])
    bug_count     = len(all_bug_emails)
    print(f"FM/ready:    {ready_count}")
    print(f"FM/review:   {review_count}")
    print(f"FM/bug:      {bug_count}")
    print(f"FM/no-reply: {no_reply_count}")

    try:
        stats_data = stats_module.get_stats()
        print(f"\nToday's stats: {json.dumps(stats_data, indent=2)}")
    except Exception:
        pass

    print("\nDone.")


if __name__ == "__main__":
    main()
