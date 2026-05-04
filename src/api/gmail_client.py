"""Gmail API wrapper — list emails, get threads, create drafts."""

import base64
import json
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

CREDENTIALS_PATH = Path(__file__).parent.parent.parent / "credentials" / "credentials.json"
TOKEN_PATH = Path(__file__).parent.parent.parent / "credentials" / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/spreadsheets",
]


def get_service():
    """Build and return an authenticated Gmail API service."""
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {CREDENTIALS_PATH}.\n"
            "Follow the OAuth setup steps in CLAUDE.md, then run setup_oauth.py."
        )
    if not TOKEN_PATH.exists():
        raise RuntimeError(
            f"token.json not found at {TOKEN_PATH}.\n"
            "Run: python setup_oauth.py"
        )

    creds = Credentials.from_authorized_user_info(
        json.loads(TOKEN_PATH.read_text()), SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def list_emails(max_results: int = 20, query: str = "is:unread in:inbox", label_ids: list = None) -> list:
    """
    List emails matching query. Returns list of dicts with id, thread_id,
    from, subject, date, snippet.
    """
    try:
        service = get_service()
        params = {"userId": "me", "maxResults": min(max_results, 100), "q": query}
        if label_ids:
            params["labelIds"] = label_ids

        result = service.users().messages().list(**params).execute()
        messages = result.get("messages", [])

        emails = []
        for msg in messages:
            meta = service.users().messages().get(
                userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]
            ).execute()

            headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
            emails.append({
                "id": msg["id"],
                "thread_id": meta.get("threadId", ""),
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", "(no subject)"),
                "date": headers.get("Date", ""),
                "snippet": meta.get("snippet", ""),
            })

        return emails
    except HttpError as e:
        return [{"error": f"Gmail API error: {e}"}]


def get_email(email_id: str) -> dict:
    """Get full email content by message ID."""
    try:
        service = get_service()
        msg = service.users().messages().get(userId="me", id=email_id, format="full").execute()
        return _parse_message(msg)
    except HttpError as e:
        return {"error": f"Gmail API error: {e}"}


def get_thread(thread_id: str) -> dict:
    """Get full conversation thread. Returns dict with messages list."""
    try:
        service = get_service()
        thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
        messages = [_parse_message(m) for m in thread.get("messages", [])]
        return {
            "thread_id": thread_id,
            "message_count": len(messages),
            "messages": messages,
        }
    except HttpError as e:
        return {"error": f"Gmail API error: {e}"}


def create_draft(to: str, subject: str, body: str, thread_id: str = None) -> dict:
    """
    Create a Gmail draft reply. If thread_id is provided, the draft appears
    in the original thread. Returns draft id and message id.
    """
    try:
        service = get_service()

        # Get the Message-ID header from the last message in the thread for proper threading
        reply_message_id = None
        if thread_id:
            try:
                thread = service.users().threads().get(
                    userId="me", id=thread_id, format="metadata",
                    metadataHeaders=["Message-ID"]
                ).execute()
                msgs = thread.get("messages", [])
                if msgs:
                    last_msg = msgs[-1]
                    hdrs = {h["name"]: h["value"] for h in last_msg.get("payload", {}).get("headers", [])}
                    reply_message_id = hdrs.get("Message-ID")
            except HttpError:
                pass

        raw = _build_raw_message(to, subject, body, reply_message_id)

        message_body = {"raw": raw}
        if thread_id:
            message_body["threadId"] = thread_id

        draft = service.users().drafts().create(
            userId="me", body={"message": message_body}
        ).execute()

        return {
            "draft_id": draft["id"],
            "message_id": draft.get("message", {}).get("id", ""),
            "thread_id": thread_id or "",
        }
    except HttpError as e:
        return {"error": f"Gmail API error: {e}"}


def create_draft_html(to: str, subject: str, html_body: str, thread_id: str = None) -> dict:
    """
    Create a Gmail draft using a pre-rendered HTML body (e.g. bug ticket template).
    Unlike create_draft, this sends the HTML as-is without appending the standard signature.
    Returns the same shape as create_draft.
    """
    try:
        service = get_service()

        reply_message_id = None
        if thread_id:
            try:
                thread = service.users().threads().get(
                    userId="me", id=thread_id, format="metadata",
                    metadataHeaders=["Message-ID"]
                ).execute()
                msgs = thread.get("messages", [])
                if msgs:
                    last_msg = msgs[-1]
                    hdrs = {h["name"]: h["value"] for h in last_msg.get("payload", {}).get("headers", [])}
                    reply_message_id = hdrs.get("Message-ID")
            except HttpError:
                pass

        msg = MIMEMultipart("alternative")
        msg["To"] = to
        msg["Subject"] = subject
        if reply_message_id:
            msg["In-Reply-To"] = reply_message_id
            msg["References"] = reply_message_id

        msg.attach(MIMEText(html_body, "html", "utf-8"))

        message_body = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")}
        if thread_id:
            message_body["threadId"] = thread_id

        draft = service.users().drafts().create(
            userId="me", body={"message": message_body}
        ).execute()

        return {
            "draft_id": draft["id"],
            "message_id": draft.get("message", {}).get("id", ""),
            "thread_id": thread_id or "",
        }
    except HttpError as e:
        return {"error": f"Gmail API error: {e}"}


def get_label_map() -> dict:
    """
    Ensure all FM/* labels exist in Gmail (with colors).
    Returns a dict mapping label name → Gmail label ID.
    Creates any missing labels silently.
    """
    import labels as labels_module
    try:
        service = get_service()
        result = service.users().labels().list(userId="me").execute()
        existing = {lbl["name"]: lbl["id"] for lbl in result.get("labels", [])}

        label_map = {}
        for name in labels_module.LABELS:
            if name in existing:
                label_map[name] = existing[name]
            else:
                body = {
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                }
                color = labels_module.LABEL_COLORS.get(name)
                if color:
                    body["color"] = color
                try:
                    created = service.users().labels().create(
                        userId="me", body=body
                    ).execute()
                    label_map[name] = created["id"]
                except HttpError as e:
                    if "already exists" in str(e).lower():
                        result2 = service.users().labels().list(userId="me").execute()
                        for lbl in result2.get("labels", []):
                            if lbl["name"] == name:
                                label_map[name] = lbl["id"]
                                break
                    else:
                        label_map[name] = f"ERROR:{e}"

        return label_map
    except HttpError as e:
        return {"error": f"Gmail API error: {e}"}


def mark_as_read(message_id: str) -> dict:
    """Remove the UNREAD label from a message."""
    try:
        service = get_service()
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
        return {"marked_read": True, "message_id": message_id}
    except HttpError as e:
        return {"error": f"Gmail API error: {e}"}


def apply_labels(message_id: str, label_names: list) -> dict:
    """
    Apply the given label names to a Gmail message.
    Resolves label names to IDs via get_label_map (creates missing labels).
    """
    try:
        label_map = get_label_map()
        label_ids = [
            label_map[n]
            for n in label_names
            if n in label_map and not str(label_map[n]).startswith("ERROR")
        ]
        if not label_ids:
            return {"message_id": message_id, "applied": [], "skipped": label_names}

        service = get_service()
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": label_ids},
        ).execute()

        return {"message_id": message_id, "applied": label_names}
    except HttpError as e:
        return {"error": f"Gmail API error: {e}"}


def list_drafts() -> list:
    """
    List all drafts. Returns a list of dicts with draft_id, message_id, thread_id,
    subject, to, date, snippet.
    """
    try:
        service = get_service()
        result = service.users().drafts().list(userId="me").execute()
        draft_items = result.get("drafts", [])

        drafts = []
        for item in draft_items:
            try:
                draft = service.users().drafts().get(
                    userId="me", id=item["id"], format="metadata"
                ).execute()
                msg = draft.get("message", {})
                headers = {
                    h["name"]: h["value"]
                    for h in msg.get("payload", {}).get("headers", [])
                }
                drafts.append({
                    "draft_id": item["id"],
                    "message_id": msg.get("id", ""),
                    "thread_id": msg.get("threadId", ""),
                    "subject": headers.get("Subject", "(no subject)"),
                    "to": headers.get("To", ""),
                    "date": headers.get("Date", ""),
                    "snippet": msg.get("snippet", ""),
                })
            except HttpError:
                drafts.append({"draft_id": item["id"], "error": "could not fetch metadata"})

        return drafts
    except HttpError as e:
        return [{"error": f"Gmail API error: {e}"}]


def update_draft(draft_id: str, to: str, subject: str, body: str, thread_id: str = None) -> dict:
    """
    Replace the body of an existing draft. Preserves threading headers.
    Returns the same shape as create_draft.
    """
    try:
        service = get_service()

        # Resolve thread_id from the existing draft if not provided
        if not thread_id:
            try:
                current = service.users().drafts().get(userId="me", id=draft_id).execute()
                thread_id = current.get("message", {}).get("threadId")
            except HttpError:
                pass

        # Get the last message's Message-ID for proper In-Reply-To threading
        reply_message_id = None
        if thread_id:
            try:
                thread = service.users().threads().get(
                    userId="me", id=thread_id, format="metadata",
                    metadataHeaders=["Message-ID"],
                ).execute()
                msgs = thread.get("messages", [])
                if msgs:
                    hdrs = {
                        h["name"]: h["value"]
                        for h in msgs[-1].get("payload", {}).get("headers", [])
                    }
                    reply_message_id = hdrs.get("Message-ID")
            except HttpError:
                pass

        raw = _build_raw_message(to, subject, body, reply_message_id)
        message_body = {"raw": raw}
        if thread_id:
            message_body["threadId"] = thread_id

        updated = service.users().drafts().update(
            userId="me",
            id=draft_id,
            body={"message": message_body},
        ).execute()

        return {
            "draft_id": updated["id"],
            "message_id": updated.get("message", {}).get("id", ""),
            "thread_id": thread_id or "",
        }
    except HttpError as e:
        return {"error": f"Gmail API error: {e}"}


def delete_draft(draft_id: str) -> dict:
    """Permanently delete a draft. Returns {"deleted": True} or an error dict."""
    try:
        service = get_service()
        service.users().drafts().delete(userId="me", id=draft_id).execute()
        return {"deleted": True, "draft_id": draft_id}
    except HttpError as e:
        return {"error": f"Gmail API error: {e}"}


def find_sent_reply(thread_id: str, after_epoch_ms: int) -> dict | None:
    """
    Return the first SENT (non-DRAFT) message in the thread whose internalDate
    is after after_epoch_ms, or None if no such message exists.

    Used by the feedback loop to match a sent email back to the original draft.
    When a Gmail draft is sent, it transitions from DRAFT to SENT in the same thread.

    Args:
        thread_id:      Gmail thread ID of the original customer email.
        after_epoch_ms: Draft creation time in epoch milliseconds (inclusive lower bound).

    Returns:
        Parsed message dict (same shape as get_email) with an extra 'internalDate' key,
        or None if no sent reply found yet, or an error dict if the API call fails.
    """
    try:
        service = get_service()
        thread = service.users().threads().get(
            userId="me", id=thread_id, format="full"
        ).execute()

        for msg in thread.get("messages", []):
            label_ids = msg.get("labelIds", [])
            internal_date = int(msg.get("internalDate", 0))
            if "SENT" in label_ids and "DRAFT" not in label_ids and internal_date > after_epoch_ms:
                parsed = _parse_message(msg)
                parsed["internalDate"] = str(internal_date)
                return parsed

        return None
    except HttpError as e:
        return {"error": f"Gmail API error: {e}"}


def _parse_message(msg: dict) -> dict:
    """Extract headers and body from a Gmail message resource."""
    payload = msg.get("payload", {})
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
    body = _decode_body(payload)
    attachments = _extract_attachments(payload)

    return {
        "id": msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "subject": headers.get("Subject", "(no subject)"),
        "date": headers.get("Date", ""),
        "message_id_header": headers.get("Message-ID", ""),
        "labels": msg.get("labelIds", []),
        "snippet": msg.get("snippet", ""),
        "body": body,
        "attachments": attachments,
    }


def _decode_body(payload: dict) -> str:
    """Recursively walk MIME payload to extract plain text body."""
    mime_type = payload.get("mimeType", "")

    # Direct body data
    body_data = payload.get("body", {}).get("data", "")
    if body_data and mime_type == "text/plain":
        return _b64decode(body_data)

    # Recurse into parts
    parts = payload.get("parts", [])
    for part in parts:
        result = _decode_body(part)
        if result:
            return result

    # Fall back to HTML if no plain text found
    if body_data and mime_type == "text/html":
        html = _b64decode(body_data)
        # Very simple tag strip
        import re
        return re.sub(r"<[^>]+>", " ", html).strip()

    return ""


def _extract_attachments(payload: dict) -> list[dict]:
    """Recursively walk MIME payload and collect attachment filenames and types."""
    results = []
    filename = payload.get("filename", "")
    mime_type = payload.get("mimeType", "")
    # A part is an attachment if it has a filename and is not inline text/html
    if filename and mime_type not in ("text/plain", "text/html"):
        results.append({"filename": filename, "mime_type": mime_type})
    for part in payload.get("parts", []):
        results.extend(_extract_attachments(part))
    return results


def _b64decode(data: str) -> str:
    """Decode base64url-encoded string with padding fix."""
    data += "=" * (4 - len(data) % 4)
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


_PLAIN_SIGNATURE = (
    "\n\n--\n"
    "Jessica from Flowmingo Customer Support Team\n"
    "Mobile / WhatsApp (Support Hotline): (+84) 989 877 953\n\n"
    "CONFIDENTIALITY NOTICE: The information contained herein, and any documents, "
    "files or email messages provided with it, may contain confidential, proprietary "
    "and/or trade secret information that is legally privileged. If you are not the "
    "intended recipient, or the person responsible for delivering these materials to "
    "the intended recipient, you are hereby on notice of its status. Any disclosure, "
    "copying, distribution or use of any information contained in or attached to this "
    "transmission is STRICTLY PROHIBITED. If you have received this transmission in "
    "error, please destroy all records of the transmission and any attachments thereto "
    "without reading or saving in any manner. Thank you."
)

_HTML_SIGNATURE = """\
<div><strong>Jessica from Flowmingo Customer Support Team</strong></div>
<div><font color="#000000"><u>Mobile / WhatsApp (Support Hotline)</u>: (+84) 989 877 953</font></div>
<div><br></div>
<div><i><span style="color:rgb(34,34,34);font-size:x-small;">
CONFIDENTIALITY NOTICE: The information contained herein, and any documents, files or
email messages provided with it, may contain confidential, proprietary and/or trade secret
information that is legally privileged. If you are not the intended recipient, or the person
responsible for delivering these materials to the intended recipient, you are hereby on notice
of its status. Any disclosure, copying, distribution or use of any information contained in or
attached to this transmission is STRICTLY PROHIBITED. If you have received this transmission
in error, please destroy all records of the transmission and any attachments thereto without
reading or saving in any manner. Thank you.
</span></i></div>"""


def _markdown_to_html(text: str) -> str:
    """Convert a plain-text draft body to HTML with light markdown support.

    Supported syntax:
    - [REVIEW NEEDED: reason]  →  styled amber banner (reviewer-visible warning)
    - **bold text**            →  <strong>bold text</strong>
    - Emoji characters         →  pass through unchanged
    - \\n line breaks           →  <br> tags
    """
    # Escape HTML entities first so user content cannot inject tags
    out = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # [REVIEW NEEDED: ...] → amber banner
    def _review_banner(m: re.Match) -> str:
        reason = m.group(1).strip()
        return (
            '<div style="background:#fff8e1;border-left:4px solid #f59e0b;'
            'padding:10px 16px;margin:0 0 20px 0;border-radius:3px;'
            'font-size:13px;line-height:1.5;color:#7c4f00;">'
            '<strong>&#9888;&#65039; REVIEW NEEDED</strong> &mdash; '
            + reason +
            '</div>'
        )
    out = re.sub(r'\[REVIEW NEEDED: (.*?)\]', _review_banner, out, flags=re.DOTALL)

    # **bold** → <strong>bold</strong>
    out = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', out)

    # Normalise and convert newlines
    out = out.replace("\r\n", "\n").replace("\r", "\n")
    out = "<br>\n".join(out.split("\n"))

    return out


def _build_raw_message(to: str, subject: str, body: str, reply_message_id: str = None) -> str:
    """Build and base64url-encode a multipart RFC 2822 email with signature."""
    if not subject.startswith("Re: "):
        subject = "Re: " + subject

    msg = MIMEMultipart("alternative")
    msg["To"] = to
    msg["Subject"] = subject

    if reply_message_id:
        msg["In-Reply-To"] = reply_message_id
        msg["References"] = reply_message_id

    # Plain text part (unchanged — keeps raw body + plain signature)
    plain = body + _PLAIN_SIGNATURE
    msg.attach(MIMEText(plain, "plain", "utf-8"))

    # HTML part — render with markdown support, clean container, styled signature
    html_content = _markdown_to_html(body)
    html = (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;'
        'line-height:1.7;color:#1a1a1a;max-width:640px;">\n'
        + html_content
        + "\n</div>\n<br>\n"
        + _HTML_SIGNATURE
    )
    msg.attach(MIMEText(html, "html", "utf-8"))

    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
