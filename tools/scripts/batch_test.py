#!/usr/bin/env python3
"""
batch_test.py — Dry-run pipeline harness for benchmarking 132 sample emails.

Runs the full 3-layer pipeline (rules_engine → BM25 → Node1 → Node2 → validators)
against sample JSONs in prompt-tester/samples/ WITHOUT any Gmail API calls.

Model: gpt-4.1-mini (hardcoded — user's production model)

Usage:
    python tools/scripts/batch_test.py
    python tools/scripts/batch_test.py --limit 10
    python tools/scripts/batch_test.py --output prompt-tester/results/new/
    python tools/scripts/batch_test.py --limit 5 --output prompt-tester/results/test/
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# ── Path setup ───────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src" / "api"))

import requests
import knowledge
import rag
import rules_engine
import validators
import scenario_contracts as sc_module

# ── Config ───────────────────────────────────────────────────────────────────
OPENAI_API_URL  = "https://api.openai.com/v1/chat/completions"
MODEL           = "gpt-4.1-mini"   # user's production model — do NOT change
SAMPLES_DIR     = PROJECT_ROOT / "prompt-tester" / "samples"
DEFAULT_OUT_DIR = PROJECT_ROOT / "prompt-tester" / "results" / "baseline"
DELAY_BETWEEN   = 0.3   # seconds between API calls to avoid rate-limiting


# ── OpenAI call ──────────────────────────────────────────────────────────────

def call_openai(api_key: str, system_prompt: str, user_prompt: str, max_tokens: int = 1200) -> dict:
    """Call OpenAI Chat Completions API with JSON mode. Returns {result, input_tokens, output_tokens}."""
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
                {"role": "user",   "content": user_prompt},
            ],
        },
        timeout=90,
    )
    resp.raise_for_status()
    body  = resp.json()
    usage = body.get("usage", {})
    choices = body.get("choices", [])
    if not choices:
        raise ValueError(f"No choices in response: {json.dumps(body)[:300]}")
    text = choices[0].get("message", {}).get("content", "").strip()
    if not text:
        raise ValueError(f"Empty content in response: {json.dumps(body)[:300]}")
    return {
        "result": json.loads(text),
        "input_tokens":  usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }


# ── Node 1 prompt builder ────────────────────────────────────────────────────

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
Route: full scenario routing (S1-S34).

"unclear": Cannot determine direction from email content alone.
Route: FM/review with reviewer_briefing explaining the ambiguity.

=== STEP 2: SCENARIO ROUTING ===

After setting intent_direction:
- inbound_pitch → scenario = "S27", sender_type = "E" (unless clearly partner/known type)
- inbound_prospect + company/recruiter → scenario = "S22", sender_type = "D"
- inbound_support → apply S1-S34 matching based on email content

=== SCENARIO QUICK REFERENCE (S1–S34) ===
Read this list before matching. Do NOT default to S8 when uncertain — use the most specific match.

S1  – Email body is NOT in English (write reply in English, politely note we use English)
S2  – Candidate thinks they must PAY to submit their interview
S3  – Flowmingo OWN candidate (Type A) requests extension, reschedule, or retake
S4  – External COMPANY candidate (Type B) requests extension, reschedule, or retake
S5  – Candidate exceeded the allowed number of interview attempts
S6  – CV/resume FILE UPLOAD problem during application (file not attaching, upload fails)
S7  – Camera or microphone DEVICE CHECK fails BEFORE the interview (permissions denied, hardware not detected)
S8  – Interview LINK does not open: 404, expired, broken link, opens in in-app browser that blocks mic
S9  – Mic or audio FAILS DURING RECORDING after link opens; cannot record or submit first question
S10 – Partner DASHBOARD is empty; referrals not showing or not being tracked
S11 – Partner program: onboarding, training materials, commission mechanics, payout, employment type, formal agreement
S12 – Partner requests social media templates or marketing content
S13 – Reference letter, employment certificate, proof of work request → always decline
S14 – Request for 1:1 call, demo, or meeting (from non-recruiter individuals)
S15 – Positive feedback / testimonial / appreciation from a real user about Flowmingo
S16 – Candidate wants to WITHDRAW from the interview process
S17 – Individual asks to JOIN FLOWMINGO as an employee (sends CV, asks about Flowmingo jobs)
S18 – Flowmingo OWN candidate (Type A) asks about their results, timeline, or interview status
S19 – WhatsApp link is wrong, full, expired, or gives an error when clicked
S20 – Technical issue STILL unresolved after T1 troubleshooting was already given in a prior reply
S21 – External COMPANY candidate (Type B) asks about results, timeline, or reminder about their interview
S22 – Recruiter or company wants to USE FLOWMINGO for their own hiring (prospect, pricing, demo)
S23 – Recruiter/company cannot access or find a candidate's report/results
S24 – Recruiter/company reports that multiple candidates face recurring tech issues
S25 – Candidate says interview already completed OR email already entered into another application
S26 – AI Development Project: gifts, consent form (A2/A5), dashboard, data contribution program
S27 – Vendor/service PITCHING to Flowmingo (marketing, lead gen, PR, media features, awards, talent sourcing)
S28 – API integration request (beta access)
S29 – Do-not-contact / unsubscribe / stop processing data / GDPR opt-out → FM/review required
S30 – Established partner/member asking about new Flowmingo roles, or received outreach by mistake
S31 – Employment type inquiry (freelance vs full-time vs contract)
S32 – Scheduling/meeting inquiry with no SOP data → multi-option draft
S33 – GDPR data DELETION request (delete profile, candidacy, or interview data)
S34 – Acceptance/offer confirmation (candidate confirms they accept, or asks about next steps after acceptance)

KEY DISAMBIGUATION:
S7 vs S9: S7 = device check BEFORE interview starts (permissions blocked). S9 = interview loaded but mic fails DURING recording.
S8 vs S9: S8 = link doesn't OPEN (404, expired). S9 = link opens, interview loads, but mic/recording fails.
S18 vs S21: S18 = Flowmingo own program candidate (Type A). S21 = external company's candidate (Type B).
S22 vs S27: S22 = they want to BUY/USE Flowmingo. S27 = they want to SELL something TO Flowmingo.
S3 vs S4: S3 = Flowmingo internal role candidate (Type A). S4 = external company's candidate (Type B).
S17 vs S22: S17 = individual wants to work AT Flowmingo. S22 = company wants to USE Flowmingo for hiring.
S15 vs S27: S15 = real user sharing authentic positive experience. S27 = company offering to sell/manage reviews.

S17 TRIGGER — classify as S17 when an INDIVIDUAL is asking to WORK at Flowmingo:
- Signals: "looking for a job", "interested in joining your team", "I'd like to apply",
  "career opportunities at Flowmingo", "open positions", submitting a CV or resume to
  Flowmingo support, asking how to apply to Flowmingo.
→ scenario = "S17", sender_type = "E", scenario_confidence = 0.90
CRITICAL S17 vs S22 distinction:
  S17 = an INDIVIDUAL who wants to WORK for Flowmingo (job seeker applying to Flowmingo)
  S22 = a COMPANY or recruiter that wants to USE Flowmingo for their own hiring
  Do NOT route individual job seekers to S22, S27, or the S22/S27 dual-option format.

S13 TRIGGER — classify as S13 for ANY of these (regardless of exact phrasing):
- Reference letter, reference check, employment certificate, work certificate,
  letter of employment, certificate of engagement, confirmation of role,
  proof of employment, work verification, any document confirming role/relationship.
→ classification_hint = FM/ready, scenario = "S13", scenario_confidence = 0.95.
  Never ask clarifying questions for S13. The answer is always a decline.

REVIEW VENDOR RULE — vendors selling reviews, reputation management, or review packages:
- Signals: "Trustpilot reviews", "Google reviews", "review package", "review service",
  "reputation management", "5-star reviews for your business", "review pricing"
→ intent_direction = "inbound_pitch", scenario = "S27"
CRITICAL: NEVER classify review vendor emails as S15. S15 is ONLY for real Flowmingo
users sharing their own authentic positive experience. A company offering to sell or
manage reviews is a vendor pitch (S27).

FM/bug signals: specific platform error, "it didn't work", image attachment with error context.

=== STEP 3: REVIEW ROUTING ===

classification_hint = FM/review when:
- scenario_confidence < 0.7
- intent_direction = "unclear"
- has_support_reply = true
- Legal/GDPR/DNC sensitivity (S29)
- Ambiguous S22 vs S27 (large HR/recruitment platform - could be either)

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


def build_node1_prompt(email: dict) -> tuple:
    has_attachments = bool(email.get("attachments"))
    attachment_note = ""
    if has_attachments:
        att_list = [a.get("filename", a.get("mimeType", "unknown")) for a in email["attachments"]]
        attachment_note = f"\nAttachments: {', '.join(att_list)}"

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
    return NODE1_CLASSIFIER_SCHEMA, user_prompt


# ── Node 2 prompt builder ────────────────────────────────────────────────────

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

5. FORMAT: The draft_body string MUST use markdown. It is converted to HTML before sending.

   BULLET LISTS ARE MANDATORY whenever you list 2 or more actions, steps, or options.
   The draft_body is a JSON string — use literal \n and "- " for bullets:

   WRONG JSON (steps as plain lines — NEVER do this):
     "draft_body": "...\n\nPlease try:\nCheck browser permissions.\nClose other apps."

   RIGHT JSON (hyphen bullets — ALWAYS required for steps):
     "draft_body": "...\n\nPlease try:\n- Check browser permissions.\n- Close other apps."

   The "- " (hyphen space) prefix is REQUIRED at the start of every list item line.
   Use **bold** for labels: "- **Browser:** Check the lock icon in the address bar."
   NEVER use # headers, * italic, backtick code blocks, or "* item" bullets.

   BOLD IS REQUIRED in every reply that contains an action or key information:
   - Contact method: "reach us via **WhatsApp at +84 989 877 953**"
   - Key link or platform: "leave a review on **Trustpilot**" or "book via **our calendar link**"
   - Key date, deadline, or status: "your results will be ready **within 1–2 weeks**"
   - Key technical term: "- **Browser permission:** check the lock icon in the address bar"
   Only purely informational replies (e.g., acknowledging withdrawal, thanking for feedback
   with no follow-up action) may omit bold if there is genuinely no key term to highlight.

6. ENDING: End with exactly once: "Let us know if you have any questions,"
   Then: "Best regards,"

7. FM/review drafts MUST still contain a full draft body (not just the review tag).
   A reviewer must be able to send it with minor edits, not start from scratch.

=== S27 (inbound_pitch) ===
The full S27 template and instructions are loaded from the SOP above (see "S27 - Vendor/Service Pitch Email" section).
Follow those instructions exactly. Key reminders:
- Do NOT open with "My name is Jessica - Customer Support Representative at Flowmingo."
- DO acknowledge their specific pitch in the first sentence.
- ALWAYS include https://flowmingo.ai?utm_source=email-support
- Do NOT agree to purchase, subscribe to, or commission anything.
- 80-120 words total.

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


def _extract_sop_section(text: str, scenario_id: str) -> str:
    import re as _re
    pattern = _re.compile(
        rf"(###\s+\*\*{_re.escape(scenario_id)}\s*[–—-].*?)(?=\n###\s+\*\*S\d|\Z)",
        _re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def build_node2_prompt(email: dict, kb_text: str, node1: dict,
                       scenarios_text: str = "") -> tuple:
    has_attachments = bool(email.get("attachments"))
    attachment_note = ""
    if has_attachments:
        att_list = [a.get("filename", a.get("mimeType", "unknown")) for a in email["attachments"]]
        attachment_note = (
            f"\nAttachments: {', '.join(att_list)}"
            "\nIMPORTANT: The sender has provided attachment(s). Do NOT ask them to share "
            "information that may already be contained in the attachment."
        )

    intent_dir   = node1.get("intent_direction", "inbound_support")
    scenario     = node1.get("scenario", "unclear")
    sender_type  = node1.get("sender_type", "E")
    conf         = node1.get("scenario_confidence", 0.5)
    hint         = node1.get("classification_hint", "FM/review")
    rev_brief    = node1.get("reviewer_briefing", "")

    routing_block = (
        f"=== ROUTING FROM NODE 1 ===\n"
        f"intent_direction: {intent_dir}\n"
        f"sender_type: {sender_type}\n"
        f"scenario: {scenario}\n"
        f"scenario_confidence: {conf:.2f}\n"
        f"classification_hint: {hint}\n"
    )
    if rev_brief:
        routing_block += f"reviewer_briefing (from Node 1): {rev_brief}\n"
    routing_block += "=== END ROUTING ===\n"

    effective_kb = kb_text
    if intent_dir == "inbound_pitch" and scenarios_text:
        s27_section = _extract_sop_section(scenarios_text, "S27")
        if s27_section and s27_section not in effective_kb:
            effective_kb = s27_section + "\n\n" + effective_kb

    system_prompt = (
        "You are a Flowmingo support email writer.\n\n"
        "=== FLOWMINGO SOP ===\n"
        f"{effective_kb}\n"
        "=== END SOP ===\n\n"
        + routing_block + "\n"
        + NODE2_DRAFT_RULES
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


# ── Determine label from validation + route ───────────────────────────────────

def _determine_label(node1: dict, validation: dict, contract: dict,
                     risk_triggers: list) -> str:
    hint     = node1.get("classification_hint", "FM/review")
    severity = validation["severity"]

    if hint == "FM/bug":
        return "FM/bug"
    if "already_replied" in risk_triggers:
        return "FM/review"
    if contract.get("force_review"):
        return "FM/review"
    if severity in ("HIGH", "MEDIUM"):
        return "FM/review"
    if float(node1.get("scenario_confidence", 0.5)) < 0.7:
        return "FM/review"
    if hint == "FM/review":
        return "FM/review"
    return "FM/ready"


# ── Process one sample ────────────────────────────────────────────────────────

def process_sample(email: dict, api_key: str, rules_text: str,
                   scenarios_text: str, contracts: list) -> dict:
    """Run full pipeline on one sample. Returns result dict (no Gmail calls)."""
    t_start = time.time()

    # For batch testing: samples were extracted AFTER processing (support already replied).
    # Override has_support_reply=False so the ALREADY_REPLIED short-circuit doesn't fire.
    # The LLM still sees thread_context so multi-turn context is preserved.
    email = dict(email)
    email["has_support_reply"] = False

    result = {
        "sample_name":      email.get("name", ""),
        "expected_scenario": email.get("expected_scenario", ""),
        "from":             email.get("from", ""),
        "subject":          email.get("subject", ""),
        "message_count":    email.get("message_count", 1),
        "has_support_reply": False,  # overridden for batch testing
    }

    # ── 1. Rules engine ───────────────────────────────────────────────────────
    route_info    = rules_engine.route(email)
    is_bug        = route_info["is_bug"]
    risk_triggers = list(route_info["risk_triggers"])
    pre_hint      = route_info["pre_route_hint"]

    result["rules_engine"] = {
        "sender_type":   route_info["sender_type"],
        "is_bug":        is_bug,
        "risk_triggers": risk_triggers,
        "pre_route_hint": pre_hint,
    }

    # Already-replied short-circuit
    if "already_replied" in risk_triggers:
        result.update({
            "skip_reason":      "ALREADY_REPLIED",
            "node1":            None,
            "scenario_correct": None,
            "draft_raw":        "[REVIEW NEEDED: already replied]",
            "draft_fixed":      "[REVIEW NEEDED: already replied]",
            "validation":       {"severity": "PASS", "issues": []},
            "label":            "FM/review",
            "input_tokens":     0,
            "output_tokens":    0,
            "duration_ms":      int((time.time() - t_start) * 1000),
        })
        return result

    # Bug path
    if is_bug:
        result.update({
            "skip_reason":      "IS_BUG",
            "node1":            None,
            "scenario_correct": None,
            "draft_raw":        "[FM/bug — bug ticket would be created]",
            "draft_fixed":      "[FM/bug — bug ticket would be created]",
            "validation":       {"severity": "PASS", "issues": []},
            "label":            "FM/bug",
            "input_tokens":     0,
            "output_tokens":    0,
            "duration_ms":      int((time.time() - t_start) * 1000),
        })
        return result

    total_in  = 0
    total_out = 0

    # ── 2. BM25 RAG ──────────────────────────────────────────────────────────
    kb_text, _ = rag.get_relevant_context_with_ids(
        rules_text=rules_text,
        scenarios_text=scenarios_text,
        email_text=email.get("latest_message", "") or email.get("subject", ""),
        top_k=5,
    )

    # ── 3. Node 1 ────────────────────────────────────────────────────────────
    n1_sys, n1_usr = build_node1_prompt(email)
    try:
        resp1     = call_openai(api_key, n1_sys, n1_usr, max_tokens=400)
        node1     = resp1["result"]
        total_in  += resp1["input_tokens"]
        total_out += resp1["output_tokens"]
    except Exception as ex:
        result.update({
            "error":            f"Node1 failed: {ex}",
            "node1":            None,
            "scenario_correct": False,
            "draft_raw":        f"[AI_ERROR: {ex}]",
            "draft_fixed":      f"[AI_ERROR: {ex}]",
            "validation":       {"severity": "HIGH", "issues": [str(ex)]},
            "label":            "FM/review",
            "input_tokens":     total_in,
            "output_tokens":    total_out,
            "duration_ms":      int((time.time() - t_start) * 1000),
        })
        return result

    model_scenario_id   = node1.get("scenario", "unclear")
    scenario_confidence = float(node1.get("scenario_confidence", 0.5))
    result["node1"] = {
        "scenario":    model_scenario_id,
        "confidence":  scenario_confidence,
        "sender_type": node1.get("sender_type", "E"),
        "intent_direction": node1.get("intent_direction", ""),
        "classification_hint": node1.get("classification_hint", "FM/review"),
        "urgency":     node1.get("urgency", "normal"),
    }
    result["scenario_correct"] = (
        model_scenario_id.upper() == email.get("expected_scenario", "").upper()
    )

    # ── 4. Contract selection ─────────────────────────────────────────────────
    contract, extra_triggers = sc_module.select(contracts, pre_hint, model_scenario_id)
    risk_triggers.extend(extra_triggers)

    # ── 5. Node 2 ────────────────────────────────────────────────────────────
    n2_sys, n2_usr = build_node2_prompt(email, kb_text, node1, scenarios_text=scenarios_text)
    try:
        resp2     = call_openai(api_key, n2_sys, n2_usr, max_tokens=2000)
        cls       = resp2["result"]
        total_in  += resp2["input_tokens"]
        total_out += resp2["output_tokens"]
    except Exception as ex:
        result.update({
            "error":         f"Node2 failed: {ex}",
            "draft_raw":     f"[AI_ERROR: {ex}]",
            "draft_fixed":   f"[AI_ERROR: {ex}]",
            "validation":    {"severity": "HIGH", "issues": [str(ex)]},
            "label":         "FM/review",
            "input_tokens":  total_in,
            "output_tokens": total_out,
            "duration_ms":   int((time.time() - t_start) * 1000),
        })
        return result

    draft_body = cls.get("draft_body", "")

    # ── 6. Validate ──────────────────────────────────────────────────────────
    validation = validators.validate(draft_body, contract, risk_triggers)

    label = _determine_label(node1, validation, contract, risk_triggers)

    result.update({
        "contract_id":   contract.get("scenario_id", "FALLBACK"),
        "draft_raw":     draft_body,
        "draft_fixed":   validation["fixed_draft"],
        "validation": {
            "severity":    validation["severity"],
            "issues":      validation["issues"],
            "score":       validation.get("validator_score", 1.0),
        },
        "label":         label,
        "input_tokens":  total_in,
        "output_tokens": total_out,
        "duration_ms":   int((time.time() - t_start) * 1000),
    })
    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Batch test pipeline on sample emails")
    parser.add_argument("--limit",  type=int, default=0, help="Max samples to run (0=all)")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUT_DIR),
                        help="Output directory for per-sample JSON results")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load KB
    print("Loading knowledge base...")
    rules_text     = knowledge.load_rules()
    scenarios_text = knowledge.load_scenarios()
    print(f"  rules: {len(rules_text):,} chars | scenarios: {len(scenarios_text):,} chars")

    # Load contracts
    print("Loading contracts...")
    contracts = sc_module.load_all()
    print(f"  {len(contracts)} contracts loaded")

    # Load samples
    sample_files = sorted(SAMPLES_DIR.glob("sample-*.json"))
    if args.limit > 0:
        sample_files = sample_files[:args.limit]
    print(f"Samples to run: {len(sample_files)}")
    print(f"Model: {MODEL}")
    print(f"Output: {out_dir}")
    print()

    # Run
    stats = {
        "total": 0, "correct": 0, "wrong": 0, "skipped": 0, "error": 0,
        "label_ready": 0, "label_review": 0, "label_bug": 0,
        "severity": {"PASS": 0, "LOW": 0, "MEDIUM": 0, "HIGH": 0},
        "total_input_tokens": 0, "total_output_tokens": 0, "total_ms": 0,
    }
    wrong_samples = []

    for i, fpath in enumerate(sample_files, 1):
        email = json.loads(fpath.read_text(encoding="utf-8"))
        expected = email.get("expected_scenario", "?")
        name     = email.get("name", fpath.stem)

        print(f"[{i:3d}/{len(sample_files)}] {name[:60]}", end=" ", flush=True)

        result = process_sample(email, api_key, rules_text, scenarios_text, contracts)

        # Save result
        out_path = out_dir / f"{fpath.stem}.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        # Update stats
        stats["total"] += 1
        stats["total_input_tokens"]  += result.get("input_tokens", 0)
        stats["total_output_tokens"] += result.get("output_tokens", 0)
        stats["total_ms"]            += result.get("duration_ms", 0)

        if result.get("skip_reason"):
            stats["skipped"] += 1
            print(f"  SKIPPED [{result['skip_reason']}]")
        elif result.get("error"):
            stats["error"] += 1
            print(f"  ERROR: {result['error'][:60]}")
        else:
            node1_scenario = result.get("node1", {}).get("scenario", "?")
            severity       = result.get("validation", {}).get("severity", "?")
            label          = result.get("label", "?")
            correct        = result.get("scenario_correct", False)

            stats["severity"].setdefault(severity, 0)
            stats["severity"][severity] += 1
            if label == "FM/ready":  stats["label_ready"]  += 1
            elif label == "FM/review": stats["label_review"] += 1
            elif label == "FM/bug":  stats["label_bug"]    += 1

            if correct:
                stats["correct"] += 1
                marker = "OK"
            else:
                stats["wrong"] += 1
                marker = "WRONG"
                wrong_samples.append({
                    "name": name,
                    "expected": expected,
                    "got": node1_scenario,
                })

            conf = result.get("node1", {}).get("confidence", 0)
            print(f"  [{marker}] {expected}->{node1_scenario} | {severity} | {label} | {conf:.0%}")

        time.sleep(DELAY_BETWEEN)

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print(f"RESULTS  ({out_dir})")
    print("=" * 70)
    ran = stats["total"] - stats["skipped"] - stats["error"]
    acc = stats["correct"] / ran * 100 if ran > 0 else 0
    print(f"  Total:       {stats['total']}  |  Ran: {ran}  |  Skipped: {stats['skipped']}  |  Error: {stats['error']}")
    print(f"  Scenario accuracy:  {stats['correct']}/{ran} = {acc:.1f}%")
    print(f"  Labels:  FM/ready={stats['label_ready']}  FM/review={stats['label_review']}  FM/bug={stats['label_bug']}")
    print(f"  Severity: PASS={stats['severity'].get('PASS',0)}  LOW={stats['severity'].get('LOW',0)}  "
          f"MEDIUM={stats['severity'].get('MEDIUM',0)}  HIGH={stats['severity'].get('HIGH',0)}")
    print(f"  Tokens:  in={stats['total_input_tokens']:,}  out={stats['total_output_tokens']:,}")
    avg_ms = stats["total_ms"] / stats["total"] if stats["total"] else 0
    print(f"  Avg latency: {avg_ms:.0f} ms/email")

    if wrong_samples:
        print(f"\n  Wrong classifications ({len(wrong_samples)}):")
        for w in wrong_samples:
            print(f"    {w['name'][:50]}  expected={w['expected']} got={w['got']}")

    # Save summary
    summary_path = out_dir / "_summary.json"
    summary_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    wrong_path = out_dir / "_wrong_scenarios.json"
    wrong_path.write_text(json.dumps(wrong_samples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Summary saved: {summary_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
