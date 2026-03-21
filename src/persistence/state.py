"""Per-email state tracking — stores rich metadata for every processed email."""

import json
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path(__file__).parent.parent.parent / "stats" / "email_state.json"


def _empty_state() -> dict:
    return {"emails": {}}


def load_state() -> dict:
    if not STATE_PATH.exists():
        return _empty_state()
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _empty_state()


def save_state(data: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_email(
    email_id: str,
    thread_id: str,
    from_addr: str,
    subject: str,
    date: str,
    sender_type: str,
    topic: str,
    scenario: str,
    urgency: str,
    review_status: str,
    draft_id: str,
    draft_message_id: str,
    kb_version: str,
    labels_applied: list,
    ticket_id: str = None,
) -> dict:
    """Save state for a processed email. Returns the saved entry."""
    data = load_state()
    entry = {
        "thread_id": thread_id,
        "from": from_addr,
        "subject": subject,
        "date": date,
        "sender_type": sender_type,
        "topic": topic,
        "scenario": scenario,
        "urgency": urgency,
        "review_status": review_status,
        "draft_id": draft_id,
        "draft_message_id": draft_message_id,
        "kb_version": kb_version,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "labels_applied": labels_applied,
        "ticket_id": ticket_id,
    }
    data["emails"][email_id] = entry
    save_state(data)
    return entry


def update_draft_info(
    email_id: str,
    new_draft_id: str,
    new_draft_message_id: str,
    new_kb_version: str,
) -> dict:
    """Update draft metadata after a refresh. Returns the updated entry or an error dict."""
    data = load_state()
    if email_id not in data["emails"]:
        return {"error": f"Email {email_id} not found in state"}
    data["emails"][email_id]["draft_id"] = new_draft_id
    data["emails"][email_id]["draft_message_id"] = new_draft_message_id
    data["emails"][email_id]["kb_version"] = new_kb_version
    data["emails"][email_id]["refreshed_at"] = datetime.now(timezone.utc).isoformat()
    save_state(data)
    return data["emails"][email_id]


def get_emails(filter_by: str = None, date_str: str = None) -> dict:
    """
    Return email state entries.

    filter_by:
        "stale"  — only entries whose draft was built with an older kb_version
                   (requires the current kb_version to be passed as date_str when used
                    this way; see get_stale_drafts for the cleaner interface)
    date_str:
        "YYYY-MM-DD" — only entries processed on that date
    """
    data = load_state()
    emails = data.get("emails", {})

    if date_str:
        emails = {
            eid: e for eid, e in emails.items()
            if e.get("processed_at", "").startswith(date_str)
        }

    return emails


def get_stale_drafts(current_kb_version: str) -> list:
    """Return list of email state entries whose draft was built with an older KB version."""
    data = load_state()
    stale = []
    for email_id, entry in data["emails"].items():
        if entry.get("kb_version") != current_kb_version and entry.get("draft_id"):
            stale.append({"email_id": email_id, **entry})
    return stale


def get_report(date_str: str = None) -> dict:
    """
    Generate a breakdown report.

    date_str: optional "YYYY-MM-DD" filter. Omit for all-time.
    Returns counts and percentages grouped by topic, sender_type, urgency, and status.
    """
    emails = get_emails(date_str=date_str)
    total = len(emails)

    def _breakdown(key: str) -> dict:
        counts: dict = {}
        for entry in emails.values():
            val = entry.get(key, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return {
            k: {"count": v, "pct": round(v / total * 100, 1) if total else 0}
            for k, v in sorted(counts.items(), key=lambda x: -x[1])
        }

    return {
        "date_filter": date_str or "all time",
        "total_emails": total,
        "by_topic": _breakdown("topic"),
        "by_sender_type": _breakdown("sender_type"),
        "by_urgency": _breakdown("urgency"),
        "by_status": _breakdown("review_status"),
    }
