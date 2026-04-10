#!/usr/bin/env python3
"""
process_emails_openai.py — Process Flowmingo support emails using OpenAI gpt-5.4-nano.

Validate-Repair pipeline:
  1. rules_engine.route()       — deterministic pre-routing (before LLM)
  2. rag.get_relevant_context() — per-email BM25 retrieval
  3. call_openai(v1)            — classification + draft
  4. scenario_contracts.select()— pick contract based on model scenario
  5. validators.validate()      — severity scoring + LOW auto-fix
  6. repair_v2 (if MEDIUM)      — re-classify with validation errors injected
  7. FM/ready | FM/review       — label + draft + state

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
import rules_engine
import validators
import scenario_contracts as sc_module
import state as state_module
import stats as stats_module
import sheets_client
import bug_template

# ── Config ───────────────────────────────────────────────────────────────────

OPENAI_API_URL       = "https://api.openai.com/v1/responses"
MODEL                = "gpt-5.4-nano"
SUPPORT_DOMAINS      = ["flowmingo.ai"]
CONFIDENCE_THRESHOLD = 0.7

NO_REPLY_FROM = [
    "noreply", "no-reply", "notifications@", "bounce@",
    "mailer-daemon", "donotreply", "do-not-reply", "postmaster@",
    "newsletter", "digest@", "weekly@", "daily@",
    "events@",
]
NO_REPLY_SUBJECT = [
    "verification code", "otp:", "unsubscribe", "auto-reply",
    "out of office", "delivery status notification", "mail delivery failed",
    "conference & expo", "conference expo", " summit 20", "sponsorship opportunity",
]


# ── OpenAI helper ─────────────────────────────────────────────────────────────

def call_openai(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1200,
) -> dict:
    """Call OpenAI Responses API with JSON mode. Returns parsed JSON dict."""
    resp = requests.post(
        OPENAI_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "max_output_tokens": max_tokens,
            "text": {"format": {"type": "json_object"}},
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage", {})
    # Responses API: body["output"][0]["content"][0]["text"]
    # If the model refused or returned unexpected structure, log it clearly.
    output = body.get("output", [])
    if not output:
        raise ValueError(f"Responses API returned empty output. Full body: {json.dumps(body)[:500]}")
    content = output[0].get("content", [])
    if not content:
        raise ValueError(f"Responses API output[0].content is empty. Full body: {json.dumps(body)[:500]}")
    text = content[0].get("text", "").strip()
    if not text:
        raise ValueError(f"Responses API content[0].text is empty. Full body: {json.dumps(body)[:500]}")
    return {
        "result": json.loads(text),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
    }


# ── Email batch ───────────────────────────────────────────────────────────────

def get_email_batch(max_results: int = 500) -> dict:
    emails = gmail_client.list_emails(
        max_results=min(max_results, 500),
        query="is:unread in:inbox",
    )
    if emails and isinstance(emails[0], dict) and "error" in emails[0]:
        return {"error": emails[0]["error"]}

    # Never skip unread emails based on prior processing — if it's still unread
    # it means mark_as_read failed or a draft was deleted. Re-process it.
    # Thread dedup (list_emails is newest-first; keep first occurrence per thread)
    seen_threads: dict = {}
    for e in emails:
        tid = e.get("thread_id") or e["id"]
        if tid not in seen_threads:
            seen_threads[tid] = e
    deduped = list(seen_threads.values())
    thread_dedup_count = len(emails) - len(deduped)

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
            to_process.append(normalize_thread(thread_data, e))
        except Exception as ex:
            print(f"  WARN: failed to fetch thread for {e.get('subject','')}: {ex}")

    sop_text = knowledge.load_all()
    kb_version = hashlib.sha256(sop_text.encode()).hexdigest()[:12]

    return {
        "to_process": to_process,
        "auto_skipped": auto_skipped,
        "thread_dedup_count": thread_dedup_count,
        "kb_version": kb_version,
    }


def normalize_thread(thread_data: dict, email_meta: dict) -> dict:
    """Build a normalized email dict from a raw Gmail thread + list metadata."""
    messages = thread_data.get("messages", [])
    if not messages:
        return {**email_meta, "latest_message": "", "has_support_reply": False,
                "message_count": 0, "thread_context": "", "attachments": [],
                "has_attachments": False}

    last_msg = messages[-1]
    last_labels = last_msg.get("labels", [])
    has_support_reply = (
        any(d in last_msg.get("from", "").lower() for d in SUPPORT_DOMAINS)
        and "SENT" in last_labels
        and "DRAFT" not in last_labels
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
        "has_attachments": bool(attachments),
        "thread_context": prior_context,
    }


# ── Classification prompt ─────────────────────────────────────────────────────

CLASSIFICATION_SCHEMA = """\
Respond with a JSON object ONLY — no other text. Schema:
{
  "classification": "FM/bug" | "FM/ready" | "FM/review",
  "scenario": "S8" (matched scenario code, or "unclear"),
  "scenario_confidence": 0.85,  // float 0.0-1.0. <0.5 for ambiguous, >0.8 for clear match.
  "topic": "technical" | "candidate" | "partner" | "billing" | "other",
  "urgency": "normal" | "urgent" | "critical",
  "sender_type": "A" | "B" | "C" | "D" | "E",
  "draft_body": "..." (FM/ready and FM/review only; omit or null for FM/bug),
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
- Every human email gets a reply — there is no FM/no-reply. Even disengaged statements
  ("I already have a job", "I'm not interested") get a short warm closing reply (FM/ready).
  Threads where support has already replied (has_support_reply=true) are an exception —
  those should be FM/review with reason "thread already has support reply".
- FM/bug: D4=Bug signal (platform didn't work as expected, specific error, "it didn't work",
  image attachment present). Takes priority over all SOP scenarios.
- FM/review: use when any dimension fails — D2=partial context, D3=not covered or fabrication
  risk, D5=elevated/critical, etc. MUST include exact [REVIEW NEEDED: <specific reason>] in
  review_reason AND prepend it to draft_body.
- FM/ready: question, request, brand moment, or any statement deserving a warm close —
  full context, covered by SOP, not a bug, normal sensitivity.

For FM/ready and FM/review drafts, follow SOP email structure exactly:
- "Dear <Name>," — extract name from sign-off/signature, infer from email if missing
- Address issue directly
- Include exactly once: "Let us know if you have any questions,"
- End with: "Best regards," (no name after)
- English only, no emojis
- PLAIN TEXT ONLY — absolutely no markdown. Do not use **bold**, *italic*, `code`,
  # headers, or any markdown syntax. These appear as raw symbols in email. If labelling
  a list item use plain text: "Role: ..." not "**Role**: ..."
- EVERY DRAFT MUST CONTAIN ACTUAL CONTENT — a specific answer, concrete steps, a link, or
  a clear next action. Writing only "Thanks for reaching out" or "Sorry to hear that" with
  nothing else is WRONG. If the SOP does not cover the situation, use FM/review — do not
  produce an empty acknowledgment draft.
- TROUBLESHOOTING STEPS MUST USE HYPHEN BULLETS — this is mandatory, no exceptions.
  Any list of 2+ steps or actions MUST be written as:
  - Step one here
  - Step two here
  Never write steps as plain prose sentences. A numbered or prose list is always wrong.

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


# ── Bug ticket ────────────────────────────────────────────────────────────────

def create_bug_ticket(email: dict, bug: dict) -> dict:
    """Create bug ticket + draft. Raises on failure (caller must catch)."""
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

    gmail_client.mark_as_read(email["id"])

    sheets_client.append_ticket_row({
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

    return {"ticket_id": ticket_id, "draft_id": draft_id}


def _bug_failure_draft_body(customer_name: str, issue_summary: str, error_message: str) -> str:
    return (
        f"[REVIEW NEEDED: Bug ticket creation failed — {error_message}]\n\n"
        f"Dear {customer_name or 'Customer'},\n\n"
        f"Thank you for reaching out about the issue with "
        f"{issue_summary or 'your interview'}. "
        f"We have received your report and will follow up shortly.\n\n"
        f"Let us know if you have any questions,\n\nBest regards,"
    )


# ── Log action item ───────────────────────────────────────────────────────────

def log_action_item(email: dict, review_reason: str) -> None:
    action_type = "DNC Request" if "do-not-contact" in review_reason.lower() or \
                                    "dnc" in review_reason.lower() else "Review Draft"
    priority = "High" if action_type == "DNC Request" else "Normal"
    sheets_client.append_action_row({
        "date":          datetime.now().strftime("%Y-%m-%d %H:%M"),
        "action_type":   action_type,
        "priority":      priority,
        "customer_name": "",
        "email":         email.get("from", ""),
        "subject":       email.get("subject", ""),
        "reason":        review_reason,
        "thread_id":     email.get("thread_id", ""),
    })


# ── Validate contract scenario IDs against KB ─────────────────────────────────

def _validate_contract_ids(contracts: list[dict]) -> None:
    """Cross-check contract scenario_ids against scenario KB. sys.exit(1) on mismatch."""
    scenarios_text = knowledge.load_scenarios()
    for contract in contracts:
        sid = contract["scenario_id"]
        if sid == "FALLBACK":
            continue
        # Scenario IDs appear as "### S4" or "S4 –" in KB
        if sid not in scenarios_text:
            sys.exit(f"[startup] Contract scenario_id '{sid}' not found in flowmingo-scenarios.md")


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

    # ── Startup validation ────────────────────────────────────────────────────
    print("Loading scenario contracts…")
    contracts = sc_module.load_all()
    _validate_contract_ids(contracts)
    print(f"  {len(contracts)} contracts loaded ({', '.join(c['scenario_id'] for c in contracts)})")

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
    rules_text   = knowledge.load_rules()
    scenarios_text = knowledge.load_scenarios()

    print(
        f"Batch: {len(to_process)} to process, "
        f"{len(auto_skipped)} auto-skipped, "
        f"{batch['thread_dedup_count']} thread dupes removed"
    )

    if not to_process and not auto_skipped:
        print("Nothing to process.")
        _handle_auto_skipped(auto_skipped)
        return

    # ── Process auto-skipped (no-reply senders) ───────────────────────────────
    _handle_auto_skipped(auto_skipped)

    # ── Per-email pipeline ─────────────────────────────────────────────────────
    ready_count  = 0
    review_count = 0
    bug_count    = 0
    reason_codes: list[str] = []   # for upsert_reason_frequency at end

    # Bug dedup: apply FM/bug label immediately but create tickets once
    all_bug_emails: list[dict] = []  # {email, bug (or {})}
    seen_bug_thread_ids: set = set()

    for email in to_process:
        eid  = email.get("id", "")
        subj = email.get("subject", "")
        print(f"  [{eid[:8]}] {subj[:60]}", end=" -> ", flush=True)

        # ── 1. Deterministic pre-routing ──────────────────────────────────────
        route_info    = rules_engine.route(email)
        is_bug        = route_info["is_bug"]
        risk_triggers = list(route_info["risk_triggers"])
        pre_hint      = route_info["pre_route_hint"]

        # ── ALREADY_REPLIED short-circuit ─────────────────────────────────────
        if "already_replied" in risk_triggers:
            print("FM/review [ALREADY_REPLIED]")
            _save_review(
                email=email,
                draft_body="[REVIEW NEEDED: Thread already has a support reply — verify before responding.]\n\n",
                review_reason_code="ALREADY_REPLIED",
                kb_version=kb_version,
                validator_score=None,
                repair_attempted=False,
            )
            review_count += 1
            reason_codes.append("ALREADY_REPLIED")
            continue

        # ── 2. Bug path — label immediately BEFORE ticket ─────────────────────
        if is_bug:
            print("FM/bug")
            gmail_client.apply_labels(eid, ["FM/bug"])
            tid = email.get("thread_id", eid)
            if tid not in seen_bug_thread_ids:
                seen_bug_thread_ids.add(tid)
                all_bug_emails.append({"email": email, "bug": {}})
            bug_count += 1
            continue

        # ── 3. Per-email RAG ──────────────────────────────────────────────────
        kb_text = rag.get_relevant_context(
            rules_text=rules_text,
            scenarios_text=scenarios_text,
            email_text=email.get("latest_message", "") or email.get("subject", ""),
            top_k=5,
        )

        # ── 4. OpenAI v1 call ─────────────────────────────────────────────────
        sys_p, usr_p = build_classify_prompt(email, kb_text)
        try:
            resp = call_openai(api_key, sys_p, usr_p, max_tokens=1200)
            cls  = resp["result"]
        except (json.JSONDecodeError, KeyError, Exception) as ex:
            print(f"FM/review [AI_ERROR: {ex}]")
            _save_review(
                email=email,
                draft_body=f"[REVIEW NEEDED: AI processing error — {ex}]\n\n",
                review_reason_code="AI_ERROR",
                kb_version=kb_version,
                validator_score=None,
                repair_attempted=False,
            )
            review_count += 1
            reason_codes.append("AI_ERROR")
            continue

        classification      = cls.get("classification", "FM/review")
        model_scenario_id   = cls.get("scenario", "unclear")
        scenario_confidence = float(cls.get("scenario_confidence", 0.5))

        # ── LLM-detected bug (rules_engine missed it) ─────────────────────────
        if classification == "FM/bug":
            print("FM/bug [LLM]")
            gmail_client.apply_labels(eid, ["FM/bug"])
            tid = email.get("thread_id", eid)
            if tid not in seen_bug_thread_ids:
                seen_bug_thread_ids.add(tid)
                all_bug_emails.append({"email": email, "bug": cls.get("bug", {})})
            bug_count += 1
            continue

        # ── 5. Contract selection ─────────────────────────────────────────────
        contract, extra_triggers = sc_module.select(contracts, pre_hint, model_scenario_id)
        risk_triggers.extend(extra_triggers)

        # Unknown scenario → track and fall through to validation with FALLBACK
        if "unknown_scenario" in extra_triggers:
            reason_codes.append("UNKNOWN_SCENARIO")

        # ── 6. Confidence gate ────────────────────────────────────────────────
        if scenario_confidence < CONFIDENCE_THRESHOLD:
            print(f"FM/review [LOW_CONFIDENCE {scenario_confidence:.2f}]")
            draft_body = cls.get("draft_body") or ""
            if cls.get("review_reason") and not draft_body.startswith("[REVIEW NEEDED"):
                draft_body = f"{cls['review_reason']}\n\n{draft_body}"
            _save_review(
                email=email,
                draft_body=draft_body or f"[REVIEW NEEDED: Low scenario confidence ({scenario_confidence:.2f})]\n\n",
                review_reason_code="LOW_CONFIDENCE",
                kb_version=kb_version,
                validator_score=None,
                repair_attempted=False,
                scenario=model_scenario_id,
                topic=cls.get("topic", "other"),
                urgency=cls.get("urgency", "normal"),
                sender_type=cls.get("sender_type", "E"),
                input_tokens=resp.get("input_tokens", 0),
            )
            review_count += 1
            reason_codes.append("LOW_CONFIDENCE")
            continue

        # ── 7. Validate + repair ──────────────────────────────────────────────
        draft_body_v1   = cls.get("draft_body") or ""
        v1              = validators.validate(draft_body_v1, contract, risk_triggers)
        severity        = v1["severity"]
        validator_score = v1["validator_score"]
        final_draft     = v1["fixed_draft"]
        repair_attempted = False
        review_reason_code: str | None = v1.get("review_reason_code")
        label = "FM/ready"

        if severity in ("PASS", "LOW"):
            # AUTO-FIX applied in validator, draft is clean
            label = "FM/ready"

        elif severity == "MEDIUM":
            # repair_v2: re-classify with validation errors injected
            sys_p2 = sys_p + (
                "\n\n[VALIDATION ERRORS FROM PRIOR DRAFT — you must fix all of these:]\n"
                + "\n".join(f"- {issue}" for issue in v1["issues"])
                + "\n[End of validation errors. Produce a corrected draft that avoids every violation listed above.]"
            )
            try:
                resp2 = call_openai(api_key, sys_p2, usr_p, max_tokens=2000)
                draft_v2 = resp2["result"].get("draft_body") or ""
                v2 = validators.validate(draft_v2, contract, risk_triggers)
                repair_attempted = True

                if v2["severity"] in ("PASS", "LOW"):
                    final_draft     = v2["fixed_draft"]
                    validator_score = v2["validator_score"]
                    review_reason_code = None
                    label = "FM/ready"
                else:
                    # Keep higher validator_score version
                    if v2["validator_score"] >= v1["validator_score"]:
                        final_draft     = v2["fixed_draft"]
                        validator_score = v2["validator_score"]
                        review_reason_code = v2.get("review_reason_code")
                    # else keep v1 final_draft / validator_score (already set above)
                    label = "FM/review"
            except Exception as ex:
                print(f"  WARN: repair_v2 failed: {ex}")
                repair_attempted = True
                label = "FM/review"
                # final_draft stays as v1 auto-fixed

        elif severity == "HIGH":
            final_draft = draft_body_v1  # preserve original on HIGH
            label = "FM/review"

        # For FM/review, prepend review reason if needed
        if label == "FM/review":
            if review_reason_code and not final_draft.startswith("[REVIEW NEEDED"):
                final_draft = f"[REVIEW NEEDED: {review_reason_code}]\n\n{final_draft}"
            elif cls.get("review_reason") and not final_draft.startswith("[REVIEW NEEDED"):
                final_draft = f"{cls['review_reason']}\n\n{final_draft}"

        # Special handling for force_review contracts (e.g. S29 DNC)
        if contract.get("force_review") and label == "FM/ready":
            label = "FM/review"
            if not final_draft.startswith("[REVIEW NEEDED"):
                final_draft = "[REVIEW NEEDED: Contract requires human review for this scenario.]\n\n" + final_draft

        # Safety net: if [REVIEW NEEDED] is embedded anywhere in the draft body,
        # the LLM flagged it internally — always force FM/review regardless of validator result.
        if label == "FM/ready" and "[REVIEW NEEDED" in final_draft:
            label = "FM/review"
            review_reason_code = review_reason_code or "AI_ERROR"

        print(f"{label} [{severity} score={validator_score:.2f}]")

        # ── 8. Create draft + label + state ──────────────────────────────────
        try:
            # Delete stale draft if re-processing a previously handled email
            existing = state_module.load_state().get("emails", {}).get(eid, {})
            old_draft_id = existing.get("draft_id")
            if old_draft_id:
                gmail_client.delete_draft(old_draft_id)

            dr = gmail_client.create_draft(
                to=email["from"],
                subject=subj,
                body=final_draft,
                thread_id=email.get("thread_id"),
            )
            gmail_client.apply_labels(eid, [label])
            gmail_client.mark_as_read(eid)

            state_module.save_email(
                email_id=eid,
                thread_id=email.get("thread_id", ""),
                from_addr=email.get("from", ""),
                subject=subj,
                date=email.get("date", ""),
                sender_type=cls.get("sender_type", route_info.get("sender_type", "E")),
                topic=cls.get("topic", "other"),
                scenario=model_scenario_id,
                urgency=cls.get("urgency", "normal"),
                review_status="ready" if label == "FM/ready" else "review",
                draft_id=dr.get("draft_id", ""),
                draft_message_id=dr.get("message_id", ""),
                kb_version=kb_version,
                labels_applied=[label],
                validator_score=validator_score,
                repair_attempted=repair_attempted,
                review_reason_code=review_reason_code,
            )
            stats_module.log_processing(
                email_id=eid,
                input_tokens=resp.get("input_tokens", 0),
                output_tokens=resp.get("output_tokens", 0),
                subject=subj,
                from_addr=email.get("from", ""),
                scenario=model_scenario_id,
                topic=cls.get("topic", "other"),
                urgency=cls.get("urgency", "normal"),
                review_status="ready" if label == "FM/ready" else "review",
            )
            if label == "FM/ready":
                ready_count += 1
            else:
                review_count += 1
                if review_reason_code:
                    reason_codes.append(review_reason_code)
                try:
                    log_action_item(email, final_draft[:200])
                except Exception as ex:
                    print(f"  WARN: log_action_item failed: {ex}")

        except Exception as ex:
            print(f"  ERROR creating draft: {ex}")

        time.sleep(0.3)  # rate limit guard

    # ── Bug tickets ───────────────────────────────────────────────────────────
    if all_bug_emails:
        print(f"\nCreating {len(all_bug_emails)} bug ticket(s)…")
        for item in all_bug_emails:
            email = item["email"]
            bug   = item["bug"]
            eid   = email.get("id", "")
            subj  = email.get("subject", "")
            try:
                result = create_bug_ticket(email, bug)
                print(f"  [{result['ticket_id']}] {subj[:50]}")
                state_module.save_email(
                    email_id=eid,
                    thread_id=email.get("thread_id", ""),
                    from_addr=email.get("from", ""),
                    subject=subj,
                    date=email.get("date", ""),
                    sender_type="E",
                    topic="technical",
                    scenario="bug",
                    urgency="normal",
                    review_status="bug",
                    draft_id=result.get("draft_id", ""),
                    draft_message_id="",
                    kb_version=kb_version,
                    labels_applied=["FM/bug"],
                    ticket_id=result.get("ticket_id"),
                )
            except Exception as ex:
                print(f"  ERROR creating bug ticket for {subj}: {ex}")
                # FM/bug label already applied — create fallback review draft
                error_msg = str(ex)
                fallback_body = _bug_failure_draft_body(
                    customer_name=bug.get("customer_name", ""),
                    issue_summary=bug.get("issue_summary", ""),
                    error_message=error_msg,
                )
                try:
                    dr = gmail_client.create_draft(
                        to=email["from"],
                        subject=subj,
                        body=fallback_body,
                        thread_id=email.get("thread_id"),
                    )
                    gmail_client.mark_as_read(eid)
                    state_module.save_email(
                        email_id=eid,
                        thread_id=email.get("thread_id", ""),
                        from_addr=email.get("from", ""),
                        subject=subj,
                        date=email.get("date", ""),
                        sender_type="E",
                        topic="technical",
                        scenario="bug",
                        urgency="normal",
                        review_status="bug_failed",
                        draft_id=dr.get("draft_id", ""),
                        draft_message_id="",
                        kb_version=kb_version,
                        labels_applied=["FM/bug"],
                        review_reason_code="BUG_TICKET_FAILED",
                    )
                    reason_codes.append("BUG_TICKET_FAILED")
                except Exception as ex2:
                    print(f"  ERROR creating fallback draft: {ex2}")

    # ── Export review_reason_code frequencies ─────────────────────────────────
    if reason_codes:
        from collections import Counter
        date_str = datetime.now().strftime("%Y-%m-%d")
        for code, count in Counter(reason_codes).items():
            try:
                sheets_client.upsert_reason_frequency(date_str, code, count)
            except Exception as ex:
                print(f"  WARN: upsert_reason_frequency failed for {code}: {ex}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n=== Summary ===")
    print(f"FM/ready:     {ready_count}")
    print(f"FM/review:    {review_count}")
    print(f"FM/bug:       {bug_count}")
    print(f"Auto-skipped: {len(auto_skipped)} (system/automated senders)")

    try:
        stats_data = stats_module.get_stats()
        print(f"\nToday's stats: {json.dumps(stats_data, indent=2)}")
    except Exception:
        pass

    print("\nDone.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _handle_auto_skipped(auto_skipped: list) -> None:
    for e in auto_skipped:
        try:
            gmail_client.apply_labels(e["id"], ["FM/no-reply"])
            gmail_client.mark_as_read(e["id"])
            stats_module.log_processing(
                email_id=e["id"], input_tokens=0, output_tokens=0,
                subject=e.get("subject", ""), from_addr=e.get("from", ""),
                scenario="no-reply", topic="automated", urgency="normal",
                review_status="no-reply",
            )
        except Exception as ex:
            print(f"  WARN: auto-skip failed for {e.get('subject','')}: {ex}")


def _save_review(
    email: dict,
    draft_body: str,
    review_reason_code: str,
    kb_version: str,
    validator_score: float | None,
    repair_attempted: bool,
    scenario: str = "unclear",
    topic: str = "other",
    urgency: str = "normal",
    sender_type: str = "E",
    input_tokens: int = 0,
) -> None:
    """Create FM/review draft and save state."""
    eid  = email.get("id", "")
    subj = email.get("subject", "")
    try:
        # If this email was previously processed and has a stale draft, delete it first
        existing = state_module.load_state().get("emails", {}).get(eid, {})
        old_draft_id = existing.get("draft_id")
        if old_draft_id:
            gmail_client.delete_draft(old_draft_id)

        dr = gmail_client.create_draft(
            to=email["from"],
            subject=subj,
            body=draft_body,
            thread_id=email.get("thread_id"),
        )
        gmail_client.apply_labels(eid, ["FM/review"])
        gmail_client.mark_as_read(eid)

        state_module.save_email(
            email_id=eid,
            thread_id=email.get("thread_id", ""),
            from_addr=email.get("from", ""),
            subject=subj,
            date=email.get("date", ""),
            sender_type=sender_type,
            topic=topic,
            scenario=scenario,
            urgency=urgency,
            review_status="review",
            draft_id=dr.get("draft_id", ""),
            draft_message_id=dr.get("message_id", ""),
            kb_version=kb_version,
            labels_applied=["FM/review"],
            validator_score=validator_score,
            repair_attempted=repair_attempted,
            review_reason_code=review_reason_code,
        )
        stats_module.log_processing(
            email_id=eid,
            input_tokens=input_tokens,
            output_tokens=0,
            subject=subj,
            from_addr=email.get("from", ""),
            scenario=scenario,
            topic=topic,
            urgency=urgency,
            review_status="review",
        )
        try:
            log_action_item(email, draft_body[:200])
        except Exception:
            pass
    except Exception as ex:
        print(f"  ERROR in _save_review: {ex}")


if __name__ == "__main__":
    main()
