#!/usr/bin/env python3
"""
process_emails_openai.py — Process Flowmingo support emails using OpenAI gpt-4o-mini.

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

OPENAI_API_URL       = "https://api.openai.com/v1/chat/completions"
MODEL                = "gpt-4o-mini"
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
    """Call OpenAI Chat Completions API with JSON mode. Returns parsed JSON dict."""
    resp = requests.post(
        OPENAI_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": max_tokens,
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
    # Chat Completions: body["choices"][0]["message"]["content"]
    choices = body.get("choices", [])
    if not choices:
        raise ValueError(f"Chat API returned no choices. Full body: {json.dumps(body)[:500]}")
    text = choices[0].get("message", {}).get("content", "").strip()
    if not text:
        raise ValueError(f"Chat API choices[0].message.content is empty. Full body: {json.dumps(body)[:500]}")
    return {
        "result": json.loads(text),
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
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
        prior_msgs = messages[:-1]
        for i, msg in enumerate(prior_msgs):
            is_support = any(d in msg.get("from", "").lower() for d in SUPPORT_DOMAINS)
            sender = "Support" if is_support else msg.get("from", "").split("<")[0].strip()[:15]
            # Give the most recent Flowmingo SENT reply up to 800 chars so the next
            # model call can see what was already promised — prevents repetition and
            # contradictory multi-turn replies. Other prior messages capped at 200 chars.
            is_last_prior = (i == len(prior_msgs) - 1)
            is_sent_support = is_support and "SENT" in msg.get("labels", [])
            body_limit = 800 if (is_last_prior and is_sent_support) else 200
            snippet = (msg.get("body") or msg.get("snippet", ""))[:body_limit].replace("\n", " ")
            parts.append(f"[{msg.get('date', '')[:10]}] {sender}: {snippet}")
        prior_context = " | ".join(parts)[:2000]

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


# ── Node 1: Intent & Route Classifier ────────────────────────────────────────
# Focused LLM call with NO knowledge base — cheap, fast, determines routing only.

NODE1_CLASSIFIER_SCHEMA = """\
You are a Flowmingo email intent classifier. Your ONLY job is to determine routing.
Do NOT draft a reply. Do NOT load the SOP.

OUTPUT: JSON object ONLY — no other text.
{
  "intent_direction": "inbound_support" | "inbound_pitch" | "inbound_prospect" | "unclear",
  "sender_type": "A" | "B" | "C" | "D" | "E",
  "scenario": "S8",
  "scenario_confidence": 0.85,
  "topic": "technical" | "candidate" | "partner" | "billing" | "vendor_pitch" | "other",
  "urgency": "normal" | "urgent" | "critical",
  "classification_hint": "FM/bug" | "FM/ready" | "FM/review",
  "is_bug": false,
  "reviewer_briefing": "",
  "route_reasoning": "1-2 sentence explanation"
}

=== STEP 1: DETERMINE intent_direction FIRST ===

"inbound_pitch": Sender is offering a service, product, content, talent sourcing, PR placement,
or any commercial offer TO Flowmingo. Direction: sender wants to SELL something to Flowmingo.
Signals: "I can offer", "we provide", "we'd like to pitch", "share a candidate profile with you",
"we can help you with", "media feature", "award program", "lead generation for you",
"offer our services", "partnership opportunity", "we specialize in", "we help companies like yours".
Examples: marketing services, lead gen, HR/TA services pitched to Flowmingo, media features,
awards programs, candidate placement offers, talent sourcing services.
CRITICAL: "share a candidate profile for your review" = inbound_pitch. Flowmingo is a platform,
not a recruiter. Support never receives or processes candidate profiles on Flowmingo's behalf.
Route: ALWAYS S27 regardless of sender_type.

"inbound_prospect": Sender is a recruiter, company, or HR professional enquiring about USING
Flowmingo for their own hiring. Direction: they want to buy or try Flowmingo.
Signals: "how does Flowmingo work", "interested in using", "want to try", "set up interviews",
"pricing question", "demo request", "I want to hire using your platform".
Route: S22 (Type D).

"inbound_support": Sender has a question, issue, or request about their own Flowmingo experience.
Route: full scenario routing (S1–S34).

"unclear": Cannot determine direction from email content alone.
Route: FM/review with reviewer_briefing explaining the ambiguity.

=== STEP 2: SCENARIO ROUTING ===

After setting intent_direction:
- inbound_pitch → scenario = "S27", sender_type = "E" (unless clearly partner/known type)
- inbound_prospect + company/recruiter → scenario = "S22", sender_type = "D"
- inbound_support → apply S1–S34 matching based on email content

S13 TRIGGER — classify as S13 for ANY of these (regardless of exact phrasing):
- Reference letter, reference check, employment certificate, work certificate,
  letter of employment, certificate of engagement, confirmation of role,
  proof of employment, work verification, any document confirming role/relationship.
→ classification_hint = FM/ready, scenario = "S13", scenario_confidence = 0.95.
  Never ask clarifying questions for S13. The answer is always a decline.

FM/bug signals: specific platform error, "it didn't work", image attachment with error context.

=== STEP 3: REVIEW ROUTING ===

classification_hint = FM/review when:
- scenario_confidence < 0.7
- intent_direction = "unclear"
- has_support_reply = true
- Legal/GDPR/DNC sensitivity (S29)
- Ambiguous S22 vs S27 (large HR/recruitment platform — could be either)

For ALL FM/review: populate reviewer_briefing with 3 sentences:
1. What this email appears to be about.
2. Why it was flagged for review (specific reason, not just "low confidence").
3. Recommended action for the human reviewer (e.g., "Send Option A if prospect, Option B if pitch").

=== SENDER TYPE REFERENCE ===
A = Flowmingo program candidate (own internal roles)
B = External company candidate (using Flowmingo as platform)
C = Business Partner / TA Partner / Content Partner
D = Recruiter / Company user
E = Vendor / third-party / unclear
"""


def build_node1_prompt(email: dict) -> tuple[str, str]:
    """Build Node 1 (intent classifier) prompt — no KB loaded."""
    has_attachments = bool(email.get("attachments"))
    attachment_note = ""
    if has_attachments:
        att_list = [a.get("filename", a.get("mimeType", "unknown")) for a in email["attachments"]]
        attachment_note = f"\nAttachments: {', '.join(att_list)}"

    system_prompt = NODE1_CLASSIFIER_SCHEMA

    user_prompt = (
        f"From: {email['from']}\n"
        f"Subject: {email['subject']}\n"
        f"Has support reply already: {email.get('has_support_reply', False)}\n"
        f"Message count in thread: {email.get('message_count', 1)}"
        f"{attachment_note}\n\n"
        f"Customer message:\n{email.get('latest_message', '')}\n\n"
    )
    if email.get("thread_context"):
        user_prompt += f"Prior thread context:\n{email['thread_context']}\n"

    return system_prompt, user_prompt


# ── Node 2: Draft Writer ──────────────────────────────────────────────────────
# Full KB loaded. Writes the email reply based on Node 1 routing output.

NODE2_DRAFT_RULES = """\
You are a Flowmingo support email writer. Node 1 has already classified this email.
Your job is to write the reply draft only — no re-classification needed.

OUTPUT: JSON object ONLY — no other text.
{
  "draft_body": "...",
  "review_reason": "",
  "reviewer_briefing": "",
  "bug": {
    "customer_name": "...",
    "issue_summary": "...",
    "issue_summary_vi": "...",
    "main_issue_vi": "...",
    "issue_type": "...",
    "troubleshooting_steps": ["...", "..."],
    "original_message_trimmed": "..."
  }
}

reviewer_briefing and review_reason: populate only when classification_hint is FM/review.
bug: populate only when classification_hint is FM/bug.

=== DRAFT RULES ===

1. GREETING: "Dear [Name]," — extract name from sign-off, signature, or email prefix.

2. OPENING SENTENCE: Reference something specific from THIS email — their company name,
   their specific question, or their specific situation.
   Never use "Thanks for reaching out." as the complete first sentence.

3. BODY: Contain a concrete answer, step, link, or action.
   Never produce an empty acknowledgment ("Thanks for your message." alone is wrong).
   Never ask a clarifying question when the SOP already has the answer.
   Never invite the sender to share documents you will then decline to process.

4. THREAD AWARENESS: Read prior_thread_context carefully.
   - Never ask a question already answered in a prior message.
   - Never repeat information already given in a prior Flowmingo reply.
   - Never contradict a prior Flowmingo reply.

5. FORMAT: Plain text only. No markdown, no bold, no asterisks, no headers.
   Hyphen bullets ONLY for troubleshooting step lists.

6. ENDING: End with exactly once: "Let us know if you have any questions,"
   Then: "Best regards,"

7. FM/review drafts MUST still contain a full draft body (not just the review tag).
   A reviewer must be able to send it with minor edits, not start from scratch.

=== S27 TEMPLATE (intent_direction = inbound_pitch) ===

This is a reversed outreach — write a sales pitch FOR Flowmingo.
Use this exact structure:

Dear [Name],

My name is Jessica — Customer Support Representative at Flowmingo.

[One sentence acknowledging their specific offering or proposal from their email.]

If you find boosting hiring efficiency by 3x for free as something you would like,
please register here: https://flowmingo.ai?utm_source=email-support

Let us know if you do register, so that I can give you dedicated 1:1 support
as a token of appreciation for reaching out.

Let us know if you have any questions,

Best regards,

Constraints: 80–120 words. The acknowledgment sentence must reference their specific email.
Do not add a second "Let us know if you have any questions," — it is already in the template.

=== S13 TEMPLATE (reference/cert request) ===

Decline immediately. Do NOT ask what wording they need. Do NOT ask for more details.
Do NOT say "reach out to the company that issued your offer" — for internal Flowmingo
roles (Talent Acquisition Business Partner, Business Partner, any Flowmingo program role),
Flowmingo IS that company. Simply decline clearly and warmly.

=== AMBIGUOUS S22 vs S27 (intent_direction = unclear) ===

Write TWO complete email options. Human reviewer deletes the one that does not apply.

review_reason = "[REVIEW NEEDED: ambiguous intent — delete one option before sending]"

draft_body format:
--- OPTION A: If this is an inbound prospect (company wanting to use Flowmingo) ---
Dear [Name],
[S22 draft]

--- OPTION B: If this is a vendor/service pitch to Flowmingo ---
Dear [Name],
[S27 draft using Jessica persona]

=== FOR FM/BUG ===
Set bug.main_issue_vi to a single Vietnamese sentence under 10 words starting with the affected subject.
"""


def build_node2_prompt(
    email: dict,
    kb_text: str,
    node1: dict,
    validation_errors: list[str] | None = None,
) -> tuple[str, str]:
    """Build Node 2 (draft writer) prompt with full KB and Node 1 routing context."""
    has_attachments = bool(email.get("attachments"))
    attachment_note = ""
    if has_attachments:
        att_list = [a.get("filename", a.get("mimeType", "unknown")) for a in email["attachments"]]
        attachment_note = f"\nAttachments: {', '.join(att_list)}"

    intent_dir      = node1.get("intent_direction", "inbound_support")
    scenario        = node1.get("scenario", "unclear")
    sender_type     = node1.get("sender_type", "E")
    conf            = node1.get("scenario_confidence", 0.5)
    hint            = node1.get("classification_hint", "FM/review")
    reviewer_brief  = node1.get("reviewer_briefing", "")

    routing_block = (
        f"=== ROUTING FROM NODE 1 ===\n"
        f"intent_direction: {intent_dir}\n"
        f"sender_type: {sender_type}\n"
        f"scenario: {scenario}\n"
        f"scenario_confidence: {conf:.2f}\n"
        f"classification_hint: {hint}\n"
    )
    if reviewer_brief:
        routing_block += f"reviewer_briefing (from Node 1): {reviewer_brief}\n"
    routing_block += "=== END ROUTING ===\n"

    system_prompt = (
        "You are a Flowmingo support email writer.\n\n"
        "=== FLOWMINGO SOP ===\n"
        f"{kb_text}\n"
        "=== END SOP ===\n\n"
        + routing_block + "\n"
        + NODE2_DRAFT_RULES
    )

    if validation_errors:
        system_prompt += (
            "\n\n[VALIDATION ERRORS FROM PRIOR DRAFT — fix all of these:]\n"
            + "\n".join(f"- {e}" for e in validation_errors)
            + "\n[End of validation errors. Produce a corrected draft avoiding every violation above.]"
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


def _prepend_reviewer_block(draft_body: str, reviewer_briefing: str, review_reason: str) -> str:
    """Prepend the REVIEWER BRIEFING block to an FM/review draft."""
    parts = []
    if reviewer_briefing and reviewer_briefing.strip():
        parts.append(
            "--- REVIEWER BRIEFING ---\n"
            + reviewer_briefing.strip()
            + "\n--- END BRIEFING ---"
        )
    if review_reason and not draft_body.startswith("[REVIEW NEEDED"):
        parts.append(review_reason)
    if parts:
        return "\n\n".join(parts) + "\n\n" + draft_body
    return draft_body


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

        # ── 4. Node 1: Intent & Route Classifier (no KB, fast) ────────────────
        n1_sys, n1_usr = build_node1_prompt(email)
        try:
            resp1  = call_openai(api_key, n1_sys, n1_usr, max_tokens=400)
            node1  = resp1["result"]
        except (json.JSONDecodeError, KeyError, Exception) as ex:
            print(f"FM/review [AI_ERROR node1: {ex}]")
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

        model_scenario_id   = node1.get("scenario", "unclear")
        scenario_confidence = float(node1.get("scenario_confidence", 0.5))
        intent_direction    = node1.get("intent_direction", "inbound_support")

        # ── Node 1 bug detection ──────────────────────────────────────────────
        if node1.get("classification_hint") == "FM/bug" or node1.get("is_bug"):
            print("FM/bug [Node1]")
            gmail_client.apply_labels(eid, ["FM/bug"])
            tid = email.get("thread_id", eid)
            if tid not in seen_bug_thread_ids:
                seen_bug_thread_ids.add(tid)
                all_bug_emails.append({"email": email, "bug": {}})
            bug_count += 1
            continue

        # ── 5. Contract selection (using Node 1 scenario) ─────────────────────
        contract, extra_triggers = sc_module.select(contracts, pre_hint, model_scenario_id)
        risk_triggers.extend(extra_triggers)

        if "unknown_scenario" in extra_triggers:
            reason_codes.append("UNKNOWN_SCENARIO")

        # ── 6. Node 2: Draft Writer (full KB) ────────────────────────────────
        n2_sys, n2_usr = build_node2_prompt(email, kb_text, node1)
        try:
            resp2  = call_openai(api_key, n2_sys, n2_usr, max_tokens=2000)
            cls    = resp2["result"]
        except (json.JSONDecodeError, KeyError, Exception) as ex:
            print(f"FM/review [AI_ERROR node2: {ex}]")
            _save_review(
                email=email,
                draft_body=f"[REVIEW NEEDED: AI draft error — {ex}]\n\n",
                review_reason_code="AI_ERROR",
                kb_version=kb_version,
                validator_score=None,
                repair_attempted=False,
                scenario=model_scenario_id,
                topic=node1.get("topic", "other"),
                urgency=node1.get("urgency", "normal"),
                sender_type=node1.get("sender_type", "E"),
                input_tokens=resp1.get("input_tokens", 0),
            )
            review_count += 1
            reason_codes.append("AI_ERROR")
            continue

        total_input_tokens  = resp1.get("input_tokens", 0) + resp2.get("input_tokens", 0)
        total_output_tokens = resp1.get("output_tokens", 0) + resp2.get("output_tokens", 0)

        # ── LLM-detected bug (Node 2 found it) ───────────────────────────────
        if cls.get("bug") and cls["bug"].get("issue_summary"):
            print("FM/bug [Node2]")
            gmail_client.apply_labels(eid, ["FM/bug"])
            tid = email.get("thread_id", eid)
            if tid not in seen_bug_thread_ids:
                seen_bug_thread_ids.add(tid)
                all_bug_emails.append({"email": email, "bug": cls.get("bug", {})})
            bug_count += 1
            continue

        # ── 7. Confidence gate ────────────────────────────────────────────────
        if scenario_confidence < CONFIDENCE_THRESHOLD:
            print(f"FM/review [LOW_CONFIDENCE {scenario_confidence:.2f}]")
            draft_body = cls.get("draft_body") or ""
            reviewer_briefing = node1.get("reviewer_briefing") or cls.get("reviewer_briefing") or ""
            review_reason = (
                cls.get("review_reason")
                or f"[REVIEW NEEDED: Low scenario confidence ({scenario_confidence:.2f}) — scenario: {model_scenario_id}]"
            )
            # Enforce non-empty draft — if draft is empty or too short, generate a fallback
            if len(draft_body.strip()) < 60:
                draft_body = (
                    f"[REVIEW NEEDED: Low confidence — please write or approve a reply.]\n\n"
                    f"[Draft not generated due to very low scenario confidence ({scenario_confidence:.2f}). "
                    f"Email appears to be: {reviewer_briefing or 'unknown intent'}]"
                )
            final_draft = _prepend_reviewer_block(draft_body, reviewer_briefing, review_reason)
            _save_review(
                email=email,
                draft_body=final_draft,
                review_reason_code="LOW_CONFIDENCE",
                kb_version=kb_version,
                validator_score=None,
                repair_attempted=False,
                scenario=model_scenario_id,
                topic=node1.get("topic", "other"),
                urgency=node1.get("urgency", "normal"),
                sender_type=node1.get("sender_type", "E"),
                input_tokens=total_input_tokens,
            )
            review_count += 1
            reason_codes.append("LOW_CONFIDENCE")
            continue

        # ── 8. Validate + repair ──────────────────────────────────────────────
        draft_body_v1    = cls.get("draft_body") or ""
        v1               = validators.validate(draft_body_v1, contract, risk_triggers)
        severity         = v1["severity"]
        validator_score  = v1["validator_score"]
        final_draft      = v1["fixed_draft"]
        repair_attempted = False
        review_reason_code: str | None = v1.get("review_reason_code")
        label = "FM/ready"

        if severity in ("PASS", "LOW"):
            label = "FM/ready"

        elif severity == "MEDIUM":
            # repair_v2: re-run Node 2 with validation errors injected
            n2_sys_repair, _ = build_node2_prompt(email, kb_text, node1, validation_errors=v1["issues"])
            try:
                resp_r   = call_openai(api_key, n2_sys_repair, n2_usr, max_tokens=2000)
                draft_v2 = resp_r["result"].get("draft_body") or ""
                v2 = validators.validate(draft_v2, contract, risk_triggers)
                repair_attempted = True
                total_input_tokens  += resp_r.get("input_tokens", 0)
                total_output_tokens += resp_r.get("output_tokens", 0)

                if v2["severity"] in ("PASS", "LOW"):
                    final_draft     = v2["fixed_draft"]
                    validator_score = v2["validator_score"]
                    review_reason_code = None
                    label = "FM/ready"
                else:
                    if v2["validator_score"] >= v1["validator_score"]:
                        final_draft     = v2["fixed_draft"]
                        validator_score = v2["validator_score"]
                        review_reason_code = v2.get("review_reason_code")
                    label = "FM/review"
            except Exception as ex:
                print(f"  WARN: repair_v2 failed: {ex}")
                repair_attempted = True
                label = "FM/review"

        elif severity == "HIGH":
            final_draft = draft_body_v1
            label = "FM/review"

        # For FM/review: prepend REVIEWER BRIEFING block
        if label == "FM/review":
            reviewer_briefing = node1.get("reviewer_briefing") or cls.get("reviewer_briefing") or ""
            review_reason = (
                f"[REVIEW NEEDED: {review_reason_code}]" if review_reason_code
                else (cls.get("review_reason") or "[REVIEW NEEDED]")
            )
            if not final_draft.startswith("--- REVIEWER BRIEFING"):
                final_draft = _prepend_reviewer_block(final_draft, reviewer_briefing, review_reason)

        # Enforce non-empty FM/review draft
        if label == "FM/review":
            stripped = final_draft.replace("--- REVIEWER BRIEFING ---", "").replace("--- END BRIEFING ---", "")
            stripped = stripped.replace("[REVIEW NEEDED", "").strip()
            if len(stripped) < 60:
                final_draft += (
                    "\n\n[Draft body was empty or too short. Please write a reply manually "
                    f"based on the reviewer briefing above. Scenario: {model_scenario_id}]"
                )

        # Special handling for force_review contracts (e.g. S29 DNC)
        if contract.get("force_review") and label == "FM/ready":
            label = "FM/review"
            if "--- REVIEWER BRIEFING" not in final_draft and "[REVIEW NEEDED" not in final_draft:
                final_draft = "[REVIEW NEEDED: Contract requires human review for this scenario.]\n\n" + final_draft

        # Safety net: embedded [REVIEW NEEDED] in draft body forces FM/review
        if label == "FM/ready" and "[REVIEW NEEDED" in final_draft:
            label = "FM/review"
            review_reason_code = review_reason_code or "AI_ERROR"

        print(f"{label} [{severity} score={validator_score:.2f}]")

        # ── 9. Create draft + label + state ──────────────────────────────────
        try:
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
                sender_type=node1.get("sender_type", route_info.get("sender_type", "E")),
                topic=node1.get("topic", "other"),
                scenario=model_scenario_id,
                urgency=node1.get("urgency", "normal"),
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
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                subject=subj,
                from_addr=email.get("from", ""),
                scenario=model_scenario_id,
                topic=node1.get("topic", "other"),
                urgency=node1.get("urgency", "normal"),
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
