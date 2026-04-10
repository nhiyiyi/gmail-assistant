"""
rules_engine.py — Deterministic pre-routing for email classification.

Runs BEFORE the LLM call. Returns a route dict used by the orchestrator
to short-circuit obvious cases and by validators.validate() as extra context.

Returns:
    {
        "sender_type": "A"|"B"|"C"|"D"|"E",  # best deterministic guess
        "is_bug":       bool,
        "risk_triggers": list[str],           # passed to validators.validate()
        "pre_route_hint": str,                # scenario ID hint or "unclear"
    }
"""

import re

# ── Sender type heuristics ────────────────────────────────────────────────────

# Type D: recruiters / company users (from non-personal domains, typical HR tools)
_RECRUITER_KEYWORDS = ["recruiter", "hr ", "talent", "hiring", "hrd", "recruitment"]
_RECRUITER_SUBJECTS = ["candidate", "hiring", "recruitment", "talent"]

# Type C: partners (Business Partner / Talent Acquisition Partner signals)
_PARTNER_KEYWORDS = ["business partner", "talent acquisition partner", "bp program",
                     "partner program", "commission", "referral link"]
_PARTNER_SUBJECTS = ["business partner", "partner program", "commission", "payout",
                     "referral", "quickstart", "onboarding"]

# Type A: Flowmingo's own roles (from flowmingo.ai/careers).
# These role names are specific to Flowmingo — confirmed Type A when present in subject/body.
_FLOWMINGO_ROLES = [
    "marketing growth business partner",
    "full-stack engineer",
    "full stack engineer",
    "growth product intern",
    "human resources executive",
    "backend engineer",
    "global management trainee",
    "finance & accounting intern",
    "finance and accounting intern",
    "qa/qc intern",
    "qc intern",
    "product intern",
    "marketing & operations intern",
    "marketing and operations intern",
    "sales growth business partner",
    "talent acquisition business partner",
    "flowmingo partner program",
    "flowmingo global management trainee",
]

# ── Bug heuristics ────────────────────────────────────────────────────────────

# Strong bug signals in message text
_BUG_TEXT_SIGNALS = [
    r'\b(error|failed|failure|crash|bug|broken|not working|doesn\'t work|cannot|can\'t)\b',
    r'\b(status\s*(failed|error)\s*\d{3})\b',          # "Status failed 400"
    r'\b(failed to load|failed to submit|failed to record)\b',
    r'\b(black screen|blank screen|infinite loop|stuck|frozen)\b',
    r'\b(\d{3,})\s*(error|status)\b',                  # "400 error", "500 status"
]
_BUG_TEXT_REGEX = re.compile("|".join(_BUG_TEXT_SIGNALS), re.IGNORECASE)

# Weaker bug signals — only count if combined with other signals or attachments
_BUG_SOFT_SIGNALS = [
    r'\b(issue|problem|trouble|difficulty|glitch)\b',
    r'\b(not\s+(?:working|loading|showing|displaying|recording))\b',
]
_BUG_SOFT_REGEX = re.compile("|".join(_BUG_SOFT_SIGNALS), re.IGNORECASE)

# Image attachment → strong bug signal (user sent screenshot)
_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"}


# ── DNC / GDPR heuristics ────────────────────────────────────────────────────

_DNC_SIGNALS = [
    r'\b(unsubscribe|stop\s+emailing|remove\s+me|do\s+not\s+contact|stop\s+contact'
    r'|opt.out|no\s+further\s+contact|stop\s+processing)\b',
    r'\b(gdpr|right\s+to\s+erasure|right\s+to\s+be\s+forgotten)\b',
]
_DNC_REGEX = re.compile("|".join(_DNC_SIGNALS), re.IGNORECASE)

_DELETION_SIGNALS = [
    r'\b(delete\s+(?:my\s+)?(?:account|data|profile|information|record))\b',
    r'\b((?:remove|erase|purge)\s+(?:my\s+)?(?:data|account|profile))\b',
    r'\b(right\s+to\s+(?:deletion|erasure))\b',
]
_DELETION_REGEX = re.compile("|".join(_DELETION_SIGNALS), re.IGNORECASE)

# ── External reschedule heuristics (S4) ──────────────────────────────────────

_S4_SIGNALS = [
    r'\b(reschedule|rescheduling|extend\s+(?:the\s+)?deadline|new\s+(?:interview\s+)?link'
    r'|another\s+link|different\s+link|change\s+(?:the\s+)?deadline)\b',
]
_S4_REGEX = re.compile("|".join(_S4_SIGNALS), re.IGNORECASE)

# External company signals (Type B indicator)
_EXTERNAL_COMPANY_SIGNALS = [
    r'\b(hired|applied\s+(?:for|to)|job\s+application|interview\s+(?:for|with|at))\b',
    r'\b(hiring\s+company|recruiter\s+sent|company\s+(?:sent|gave|provided))\b',
]
_EXTERNAL_COMPANY_REGEX = re.compile("|".join(_EXTERNAL_COMPANY_SIGNALS), re.IGNORECASE)


def route(email: dict) -> dict:
    """
    Deterministic pre-routing. Returns route dict consumed by orchestrator + validators.

    Input: normalized email dict from normalize_thread() with fields:
        from, subject, latest_message, has_support_reply,
        has_attachments (bool), attachments (list), message_count
    """
    from_addr    = email.get("from", "").lower()
    subject      = email.get("subject", "").lower()
    message      = email.get("latest_message", "").lower()
    attachments  = email.get("attachments", [])
    has_attachments = bool(attachments)

    risk_triggers: list[str] = []

    # ── ALREADY_REPLIED ───────────────────────────────────────────────────────
    if email.get("has_support_reply"):
        risk_triggers.append("already_replied")

    # ── PARTIAL_CONTEXT (image attachment only) ───────────────────────────────
    # Only flag image attachments — those are typically screenshots that the LLM
    # cannot see and which may be the core of the support request (bug evidence).
    # Non-image attachments (PDFs, docs, etc.) are almost always supplementary;
    # the body text is sufficient to draft a reply.  Image attachments that
    # contain bug screenshots are also caught by the bug path below.
    attachment_mimes = {a.get("mimeType", "") for a in attachments}
    has_image_attachment = bool(attachment_mimes & _IMAGE_MIME_TYPES)
    if has_image_attachment:
        risk_triggers.append("attachment_present")

    # ── BUG DETECTION ─────────────────────────────────────────────────────────
    is_bug = False
    if has_image_attachment:
        # Image attachment = strong bug signal (screenshot)
        is_bug = True
    elif _BUG_TEXT_REGEX.search(message) or _BUG_TEXT_REGEX.search(subject):
        # Hard bug keywords in text or subject
        is_bug = True
    elif has_attachments and _BUG_SOFT_REGEX.search(message):
        # Non-image attachment + soft bug language
        is_bug = True

    # ── SENDER TYPE DETECTION ─────────────────────────────────────────────────
    sender_type = _detect_sender_type(from_addr, subject, message)

    # ── PRE-ROUTE HINT ────────────────────────────────────────────────────────
    pre_route_hint = "unclear"

    if _DNC_REGEX.search(message) or _DNC_REGEX.search(subject):
        pre_route_hint = "S29"
        risk_triggers.append("dnc_signal")

    elif _DELETION_REGEX.search(message) or _DELETION_REGEX.search(subject):
        pre_route_hint = "S33"

    elif _S4_REGEX.search(message) and (
        sender_type == "B" or _EXTERNAL_COMPANY_REGEX.search(message)
    ):
        pre_route_hint = "S4"

    return {
        "sender_type":    sender_type,
        "is_bug":         is_bug,
        "risk_triggers":  risk_triggers,
        "pre_route_hint": pre_route_hint,
    }


def _detect_sender_type(from_addr: str, subject: str, message: str) -> str:
    """
    Best-effort deterministic sender type from A/B/C/D/E.
    The LLM will refine this — this is just a pre-routing hint.
    """
    combined = f"{from_addr} {subject} {message}"

    # Type D: corporate/recruiter signals
    if any(k in combined for k in _RECRUITER_KEYWORDS):
        return "D"

    # Type C: partner signals
    if any(k in combined for k in _PARTNER_KEYWORDS) or \
       any(k in subject for k in _PARTNER_SUBJECTS):
        return "C"

    # Type A: confirmed if subject or body mentions one of Flowmingo's own role names
    combined_lower = combined.lower()
    if any(role in combined_lower for role in _FLOWMINGO_ROLES):
        return "A"

    # Type B: external company role signals
    if _EXTERNAL_COMPANY_REGEX.search(message):
        return "B"

    return "E"  # fallback: unknown / general
