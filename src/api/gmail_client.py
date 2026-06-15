"""Gmail API wrapper — list emails, get threads, create drafts."""

import base64
import json
import re as _re
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


_STEP_START = '\x00STEPS\x00'
_STEP_END   = '\x00ENDSTEPS\x00'

_AUTO_BOLD_PATTERNS = [
    # Timeframes
    (_re.compile(r'\b(within \d[–\-]\d+ (?:business )?(?:days?|weeks?|hours?))\b', _re.I), r'**\1**'),
    (_re.compile(r'\b(\d[–\-]\d+ (?:business )?(?:days?|weeks?|hours?))\b', _re.I), r'**\1**'),
    # WhatsApp contact
    (_re.compile(r'(\+\d[\d\s\(\)\-]{6,})', _re.I), r'**\1**'),
    (_re.compile(r'\b(WhatsApp)\b'), r'**\1**'),
    # Key platforms/actions
    (_re.compile(r'\b(G2|Capterra)\b'), r'**\1**'),
    # Confirmation form action (offer letter replies)
    (_re.compile(r'(the confirmation link in your offer email)', _re.I), r'**\1**'),
    (_re.compile(r'(confirmation form)', _re.I), r'**\1**'),
    # Calendar booking
    (_re.compile(r'(https://calendar\.app\.google/\S+)'), r'**\1**'),
    # Training resources
    (_re.compile(r'(Training [Dd]eck|Quickstart [Gg]uide|training materials)', _re.I), r'**\1**'),
]


def _auto_bold_key_info(text: str) -> str:
    """Add **bold** to key info patterns only when the draft has no bold at all."""
    if '**' in text:
        return text
    for pattern, replacement in _AUTO_BOLD_PATTERNS:
        new_text = pattern.sub(replacement, text, count=1)
        if new_text != text:
            return new_text
    return text


_ABBREV_PROTECT = _re.compile(
    r'\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|e\.g|i\.e|No|Vol)\.',
    _re.IGNORECASE,
)
_SENT_BOUNDARY = _re.compile(r'(?<=[.!?])\s+(?=[A-Z])')


def _split_sentences(text: str) -> list:
    """Split text into sentences, protecting common abbreviations."""
    protected = _ABBREV_PROTECT.sub(lambda m: m.group(0).replace('.', '\x01'), text)
    parts = _SENT_BOUNDARY.split(protected)
    return [p.replace('\x01', '.') for p in parts]


def _split_long_paragraphs(text: str, max_sentences: int = 2) -> str:
    """Break paragraphs that contain more than max_sentences sentences."""
    paragraphs = text.split('\n\n')
    out = []
    for para in paragraphs:
        stripped = para.strip()
        if (not stripped
                or stripped.startswith('- ')
                or '\x00' in stripped
                or stripped.startswith('[REVIEW')
                or '\n' in stripped):
            out.append(para)
            continue
        sentences = _split_sentences(stripped)
        if len(sentences) <= max_sentences:
            out.append(para)
        else:
            chunks = []
            for i in range(0, len(sentences), max_sentences):
                chunks.append(' '.join(sentences[i:i + max_sentences]))
            out.append('\n\n'.join(chunks))
    return '\n\n'.join(out)


def _auto_bulletize_steps(text: str) -> str:
    """Detect LLM step patterns and wrap in step-block markers for styled callout rendering."""
    lines = text.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if stripped.endswith(':') and not stripped.startswith('-'):
            j = i + 1
            candidates = []
            while j < len(lines) and lines[j].strip():
                candidates.append(lines[j])
                j += 1
            if len(candidates) >= 2 and not any(c.startswith('- ') for c in candidates):
                result.append(line)
                result.append(_STEP_START)
                for c in candidates:
                    m = _re.match(r'^([A-Z][^:]{2,40}):\s+(.+)$', c)
                    if m:
                        result.append(f'- **{m.group(1)}:** {m.group(2)}')
                    else:
                        result.append(f'- {c}')
                result.append(_STEP_END)
                i = j
                continue
        result.append(line)
        i += 1
    return '\n'.join(result)


def _step_blocks_to_callout(text: str) -> str:
    """Convert step-block markers into a styled blue callout box for Gmail."""
    def _make_callout(m):
        inner = m.group(1)
        items_html = ''
        for line in inner.split('\n'):
            line = line.strip()
            if line.startswith('- '):
                items_html += f'<li style="margin:5px 0">{line[2:]}</li>'
        return (
            '<div style="background:#EBF5FB;border-left:4px solid #2E86C1;'
            'border-radius:0 4px 4px 0;padding:12px 16px;margin:12px 0">'
            '<div style="font-weight:700;color:#1A5276;margin-bottom:8px;font-size:13px">'
            '&#128736; Try these steps</div>'
            f'<ul style="margin:0;padding-left:20px;color:#1a1a1a">{items_html}</ul>'
            '</div>'
        )
    return _re.sub(
        _re.escape(_STEP_START) + r'(.*?)' + _re.escape(_STEP_END),
        _make_callout,
        text,
        flags=_re.DOTALL,
    )


def _markdown_to_html(text: str) -> str:
    """Convert LLM markdown output to HTML for Gmail rendering.

    Handles:
    - Auto-detection of unlabelled step lists → styled blue callout box
    - HTML entity escaping (& < >)
    - **bold** → <strong>bold</strong>
    - Consecutive hyphen-bullet lines → <ul><li>...</li></ul>
    - [REVIEW NEEDED: msg] → amber banner <div>
    - Paragraph breaks (blank line) → <br><br>
    - Remaining newlines → <br>
    """
    # 0a. Break paragraphs longer than 2 sentences
    text = _split_long_paragraphs(text, max_sentences=2)
    # 0b. Auto-bold key info if LLM produced no bold
    text = _auto_bold_key_info(text)
    # 0c. Auto-detect step patterns and wrap in step-block markers
    text = _auto_bulletize_steps(text)

    # 1. Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 2. HTML-escape entities (step markers use \x00 so they survive unescaped)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 3. [REVIEW NEEDED: msg] → amber banner
    text = _re.sub(
        r'\[REVIEW NEEDED:\s*([^\]]*)\]',
        r'<div style="background:#FFF3CD;padding:8px 12px;border-left:4px solid #FFC107;'
        r'margin:8px 0;font-family:sans-serif">'
        r'&#9888; \1</div>',
        text,
        flags=_re.IGNORECASE,
    )

    # 4. **bold** → <strong>bold</strong> (runs inside step blocks too)
    text = _re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', text)

    # 5. Step blocks → styled blue callout (before generic bullet conversion)
    text = _step_blocks_to_callout(text)

    # 6. Remaining "- item" lines → plain <ul>
    def _bullets_to_ul(m):
        lines = m.group(0).split("\n")
        items = "".join(
            f"<li>{line.lstrip('- ').strip()}</li>"
            for line in lines if line.strip()
        )
        return f"<ul style='margin:6px 0;padding-left:20px'>{items}</ul>"

    text = _re.sub(
        r'(?:^[ \t]*-[ \t]+.+\n?)+',
        _bullets_to_ul,
        text,
        flags=_re.MULTILINE,
    )

    # 7. Blank lines → paragraph break
    text = _re.sub(r'\n{2,}', "<br><br>\n", text)

    # 8. Remaining single newlines → <br>
    text = text.replace("\n", "<br>\n")

    return text


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

    # Plain text part (keep raw body as-is for text/plain)
    plain = body + _PLAIN_SIGNATURE
    msg.attach(MIMEText(plain, "plain", "utf-8"))

    # HTML part — convert markdown → HTML, then append HTML signature
    html_body = _markdown_to_html(body)
    html = f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#222">{html_body}</div>\n<br>\n{_HTML_SIGNATURE}'
    msg.attach(MIMEText(html, "html", "utf-8"))

    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
