"""Google Sheets API wrapper — bug ticket management."""

import json
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

CREDENTIALS_PATH = Path(__file__).parent.parent.parent / "credentials" / "credentials.json"
TOKEN_PATH = Path(__file__).parent.parent.parent / "credentials" / "token.json"
CONFIG_PATH = Path(__file__).parent.parent.parent / "stats" / "sheets_config.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/spreadsheets",
]

# ---------------------------------------------------------------------------
# Column indices (1-based)
# Zone 1 — Tech team (A–H, light blue header): daily ops columns
# Zone 2 — Operations (I–P, light green header): admin / system columns
# ---------------------------------------------------------------------------
COL_DATE          = 1   # A — auto (Claude)
COL_TICKET_ID     = 2   # B — auto (Claude)
COL_STATUS        = 3   # C — tech team dropdown
COL_MAIN_ISSUE    = 4   # D — auto (Claude) — 1-sentence VI summary, <10 words
COL_PRIORITY      = 5   # E — tech team dropdown
COL_SUMMARY_VI    = 6   # F — tech team editable (Vietnamese full summary)
COL_GMAIL_LINK    = 7   # G — auto (Claude) — click to open thread + attachments
COL_EMAIL         = 8   # H — auto (Claude)
COL_NOTES         = 9   # I — tech team editable (internal notes)
COL_SUMMARY_EN    = 10  # J — auto (Claude)
COL_CUSTOMER      = 11  # K — auto (Claude)
COL_SUBJECT       = 12  # L — auto (Claude)
COL_ISSUE_TYPE    = 13  # M — auto (Claude)
COL_SLACK_MESSAGE = 14  # N — auto (Claude) — copy-paste to Slack
COL_DRAFT_ID      = 15  # O — auto (Claude)
COL_THREAD_ID     = 16  # P — auto (Claude)
COL_SENT_AT       = 17  # Q — manual (fill when customer notified)

HEADERS = [
    "Date Created",        # A
    "Ticket ID",           # B
    "Status",              # C
    "Main Issue (VI)",     # D
    "Priority",            # E
    "Issue Summary (VI)",  # F
    "Gmail Link",          # G
    "Email Address",       # H
    "Notes",               # I
    "Issue Summary (EN)",  # J
    "Customer Name",       # K
    "Subject",             # L
    "Issue Type",          # M
    "Slack Message",       # N
    "Draft ID",            # O
    "Thread ID",           # P
    "Sent At",             # Q
]

BUG_TAB    = "Bug Tickets"
ACTION_TAB = "Actions Required"


def get_service():
    """Build and return an authenticated Sheets API service."""
    creds = Credentials.from_authorized_user_info(
        json.loads(TOKEN_PATH.read_text()), SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return build("sheets", "v4", credentials=creds)


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _save_config(config: dict):
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


def get_sheet_id() -> str | None:
    """Return the configured spreadsheet ID, or None if not set up yet."""
    return _load_config().get("spreadsheet_id")


def get_next_sequence(spreadsheet_id: str, date_str: str) -> int:
    """
    Count existing rows where Ticket ID (col B) starts with BUG-{date_str}.
    Returns the next sequence number (1-based).
    date_str format: YYMMDD (e.g. "260320")
    """
    try:
        service = get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{BUG_TAB}!B:B",
        ).execute()
        rows = result.get("values", [])
        prefix = f"BUG-{date_str}-"
        count = sum(1 for row in rows if row and row[0].startswith(prefix))
        return count + 1
    except HttpError:
        return 1


def append_ticket_row(ticket_data: dict) -> dict:
    """
    Append a new bug ticket row to the Bug Tickets sheet.

    ticket_data keys:
        ticket_id, date_created, customer_name, email, subject,
        issue_summary, issue_type, priority, draft_id, thread_id,
        original_message (optional)
    """
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        return {"error": "Sheet not configured. Run tools/scripts/setup_sheets.py first."}

    thread_id  = ticket_data.get("thread_id", "")
    gmail_link = f"https://mail.google.com/mail/u/0/#all/{thread_id}" if thread_id else ""

    original_msg = ticket_data.get("original_message", "")
    slack_parts = [
        f"Ticket ID: {ticket_data.get('ticket_id', '')}",
        f"Date: {ticket_data.get('date_created', '')}",
        f"Customer: {ticket_data.get('customer_name', '')}",
        f"Email: {ticket_data.get('email', '')}",
        f"Subject: {ticket_data.get('subject', '')}",
        f"Issue type: {ticket_data.get('issue_type', '')}",
        f"Issue summary: {ticket_data.get('issue_summary', '')}",
    ]
    if original_msg:
        slack_parts.append(f"Original message: {original_msg[:400]}")
    if gmail_link:
        slack_parts.append(f"Gmail: {gmail_link}")
    slack_message = "\n\n".join(slack_parts)

    row = [
        ticket_data.get("date_created", datetime.now().strftime("%Y-%m-%d %H:%M")),  # A
        ticket_data.get("ticket_id", ""),          # B
        "Reported",                                # C — initial status
        ticket_data.get("main_issue_vi", ""),      # D — Main Issue (VI): 1-sentence, <10 words
        ticket_data.get("priority", "Normal"),     # E
        ticket_data.get("issue_summary_vi", ""),   # F — Issue Summary (VI): full Vietnamese
        gmail_link,                                # G
        ticket_data.get("email", ""),              # H
        "",                                        # I — Notes: tech team fills
        ticket_data.get("issue_summary", ""),      # J — Issue Summary (EN)
        ticket_data.get("customer_name", ""),      # K
        ticket_data.get("subject", ""),            # L
        ticket_data.get("issue_type", ""),         # M
        slack_message,                             # N
        ticket_data.get("draft_id", ""),           # O
        thread_id,                                 # P
        "",                                        # Q — Sent At: manual
    ]

    try:
        service = get_service()
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{BUG_TAB}!A:Q",
            valueInputOption="USER_ENTERED",
            body={"values": [row]},
        ).execute()
        return {"appended": True, "ticket_id": ticket_data.get("ticket_id")}
    except HttpError as e:
        return {"error": f"Sheets API error: {e}"}


def append_action_row(action_data: dict) -> dict:
    """
    Append a row to the Actions Required tab.

    action_data keys:
        action_type, priority, customer_name, email, subject, reason, thread_id
    """
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        return {"error": "Sheet not configured. Run tools/scripts/setup_sheets.py first."}

    thread_id  = action_data.get("thread_id", "")
    gmail_link = f"https://mail.google.com/mail/u/0/#all/{thread_id}" if thread_id else ""

    row = [
        action_data.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),  # A
        action_data.get("action_type", ""),    # B
        action_data.get("priority", "Normal"), # C
        action_data.get("customer_name", ""),  # D
        action_data.get("email", ""),          # E
        action_data.get("subject", ""),        # F
        action_data.get("reason", ""),         # G
        gmail_link,                            # H
        "Pending",                             # I — Status
        "",                                    # J — Handled By
        "",                                    # K — Handled At
    ]

    try:
        service = get_service()
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{ACTION_TAB}!A:K",
            valueInputOption="USER_ENTERED",
            body={"values": [row]},
        ).execute()
        return {"appended": True}
    except HttpError as e:
        return {"error": f"Sheets API error: {e}"}


def get_tickets(status_filter: str = None) -> list:
    """Return all bug ticket rows as a list of dicts. Optionally filter by status."""
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        return [{"error": "Sheet not configured. Run tools/scripts/setup_sheets.py first."}]

    try:
        service = get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{BUG_TAB}!A:Q",
        ).execute()
        rows = result.get("values", [])
        if not rows or len(rows) < 2:
            return []

        tickets = []
        for row in rows[1:]:  # skip header
            row = row + [""] * (17 - len(row))  # pad to 17
            ticket = {
                "date_created":     row[0],
                "ticket_id":        row[1],
                "status":           row[2],
                "main_issue_vi":    row[3],
                "priority":         row[4],
                "issue_summary_vi": row[5],
                "gmail_link":       row[6],
                "email":            row[7],
                "notes":            row[8],
                "issue_summary":    row[9],    # EN
                "customer_name":    row[10],
                "subject":          row[11],
                "issue_type":       row[12],
                "slack_message":    row[13],
                "draft_id":         row[14],
                "thread_id":        row[15],
                "sent_at":          row[16],
            }
            if status_filter is None or ticket["status"].lower() == status_filter.lower():
                tickets.append(ticket)
        return tickets
    except HttpError as e:
        return [{"error": f"Sheets API error: {e}"}]


def update_ticket(ticket_id: str, status: str = None, notes: str = None) -> dict:
    """Find the row with the given ticket_id and update status and/or notes."""
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        return {"error": "Sheet not configured. Run tools/scripts/setup_sheets.py first."}

    try:
        service = get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{BUG_TAB}!B:B",  # Ticket ID is now col B
        ).execute()
        rows = result.get("values", [])

        row_index = None
        for i, row in enumerate(rows):
            if row and row[0] == ticket_id:
                row_index = i + 1  # 1-based
                break

        if row_index is None:
            return {"error": f"Ticket {ticket_id} not found in sheet."}

        updates = []
        if status is not None:
            updates.append({
                "range": f"{BUG_TAB}!C{row_index}",  # Status = col C
                "values": [[status]],
            })
        if notes is not None:
            updates.append({
                "range": f"{BUG_TAB}!H{row_index}",  # Notes = col H
                "values": [[notes]],
            })

        if updates:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": updates},
            ).execute()

        return {"updated": True, "ticket_id": ticket_id, "row": row_index}
    except HttpError as e:
        return {"error": f"Sheets API error: {e}"}
