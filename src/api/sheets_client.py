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

BUG_TAB         = "Bug Tickets"
ACTION_TAB      = "Actions Required"
DAILY_REPORT_TAB  = "Daily Report"
DR_SUMMARY_TAB    = "Daily_Report_Summary"
CONFIG_TAB        = "Config"

# 29-column Daily Report header order
DR_HEADERS = [
    "source_id", "date", "time_gmt7", "source", "ticket_id", "source_link",
    "screenshot_url", "original_content", "email", "candidate_name",
    "topic_raw", "stage", "category", "interview_position", "interview_company",
    "submission_id", "browser", "os", "device",
    "assessment", "confidence", "assessment_notes",
    "human_verdict", "human_notes", "include_in_report", "report_bucket",
    "approval_status", "reviewed_by", "reviewed_at",
]
# 0-based column index helpers
DR_COL = {h: i for i, h in enumerate(DR_HEADERS)}

DR_SUMMARY_HEADERS = [
    "date", "total_slack", "total_email_bugs", "total_included", "total_excluded",
    "total_borderline", "total_user_error", "total_platform_bug",
    "stage1", "stage2", "stage3", "other_company", "other_candidate",
    "total_completed", "total_started", "pct_completed", "pct_started",
    "completion_status", "dm_sent_at",
]


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
            range=f"{BUG_TAB}!A:U",
        ).execute()
        rows = result.get("values", [])
        if not rows or len(rows) < 2:
            return []

        tickets = []
        for row in rows[1:]:  # skip header
            row = row + [""] * (21 - len(row))  # pad to 21 (A:U)
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
                "screenshot_url":   row[17],   # R — Drive share link or HTTPS
                "in_report":        row[18],   # S
                "report_date":      row[19],   # T
                "attachment_urls":  row[20],   # U — comma-separated
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


# ── Daily Report functions ────────────────────────────────────────────────────

def get_daily_report_rows(date_str: str) -> list:
    """Return all Daily Report rows for a given date (YYYY-MM-DD) as dicts."""
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        return [{"error": "Sheet not configured."}]
    try:
        service = get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{DAILY_REPORT_TAB}'!A:AC",
        ).execute()
        rows = result.get("values", [])
        if len(rows) <= 1:
            return []
        out = []
        for i, row in enumerate(rows[1:], start=2):
            row = row + [""] * (len(DR_HEADERS) - len(row))
            entry = {h: row[DR_COL[h]] for h in DR_HEADERS}
            entry["_row"] = i
            if entry.get("date", "") == date_str:
                out.append(entry)
        return out
    except HttpError as e:
        return [{"error": f"Sheets API error: {e}"}]


def upsert_daily_report_rows(rows: list) -> dict:
    """
    Safe idempotent upsert for Daily Report rows.
    - Reads existing rows for each date present in `rows`.
    - Approved rows (approval_status='approved') are NEVER deleted or overwritten.
    - Non-approved rows for the date are deleted, then fresh rows are appended.
    - Rows whose source_id already exists as approved are skipped.
    """
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        return {"error": "Sheet not configured."}
    if not rows:
        return {"appended": 0, "skipped": 0}

    try:
        service = get_service()

        # Read all existing rows once
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{DAILY_REPORT_TAB}'!A:AC",
        ).execute()
        existing = result.get("values", [])

        # Get sheet ID for deleteDimension
        meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_id = next(
            s["properties"]["sheetId"]
            for s in meta["sheets"]
            if s["properties"]["title"] == DAILY_REPORT_TAB
        )

        # Build lookup: source_id -> {row_index (0-based), approval_status}
        existing_map = {}  # source_id -> {idx, approval_status}
        for i, row in enumerate(existing[1:], start=1):  # 0-based, skip header
            row_padded = row + [""] * (len(DR_HEADERS) - len(row))
            sid = row_padded[DR_COL["source_id"]]
            status = row_padded[DR_COL["approval_status"]]
            if sid:
                existing_map[sid] = {"idx": i, "approval_status": status}

        # Determine which dates are being pushed
        dates_in_push = {r.get("date", "") for r in rows if r.get("date")}

        # Collect non-approved row indices to delete (for dates we're pushing)
        rows_to_delete = []
        for sid, info in existing_map.items():
            # Find the date for this existing row
            row_data = existing[info["idx"]]
            row_padded = row_data + [""] * (len(DR_HEADERS) - len(row_data))
            row_date = row_padded[DR_COL["date"]]
            if row_date in dates_in_push and info["approval_status"] != "approved":
                rows_to_delete.append(info["idx"])

        # Delete non-approved rows in reverse order
        if rows_to_delete:
            requests = [
                {"deleteDimension": {"range": {
                    "sheetId": sheet_id, "dimension": "ROWS",
                    "startIndex": r, "endIndex": r + 1,
                }}}
                for r in sorted(rows_to_delete, reverse=True)
            ]
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": requests}
            ).execute()

        # Build set of locked source_ids (approved, not deleted)
        locked_ids = {
            sid for sid, info in existing_map.items()
            if info["approval_status"] == "approved"
        }

        # Filter new rows — skip those already locked
        new_rows = [r for r in rows if r.get("source_id", "") not in locked_ids]
        skipped = len(rows) - len(new_rows)

        if not new_rows:
            return {"appended": 0, "skipped": skipped}

        # Re-read last row index after deletions
        result2 = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{DAILY_REPORT_TAB}'!A:A",
        ).execute()
        next_row = len(result2.get("values", [])) + 1

        values = []
        for r in new_rows:
            values.append([r.get(h, "") for h in DR_HEADERS])

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{DAILY_REPORT_TAB}'!A{next_row}",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

        return {"appended": len(new_rows), "skipped": skipped}
    except HttpError as e:
        return {"error": f"Sheets API error: {e}"}


def check_report_complete(date_str: str) -> dict:
    """
    Check whether all Daily Report rows for a date have been reviewed/approved.
    Returns: {total, pending, reviewed, approved, excluded, complete}
    """
    rows = get_daily_report_rows(date_str)
    if rows and "error" in rows[0]:
        return rows[0]

    total = len(rows)
    counts = {"new": 0, "reviewed": 0, "approved": 0, "excluded": 0}
    for r in rows:
        s = r.get("approval_status", "new") or "new"
        counts[s] = counts.get(s, 0) + 1

    pending = counts["new"]
    complete = total > 0 and pending == 0 and counts["approved"] > 0

    return {
        "date": date_str,
        "total": total,
        "pending": pending,
        "reviewed": counts["reviewed"],
        "approved": counts["approved"],
        "excluded": counts["excluded"],
        "complete": complete,
    }


def get_daily_summary(date_str: str) -> dict:
    """
    Compute aggregated counts for the boss DM from approved+included rows.
    Only counts rows where approval_status='approved' AND include_in_report='Yes'.
    Excluded rows are tallied separately.
    """
    rows = get_daily_report_rows(date_str)
    if rows and "error" in rows[0]:
        return rows[0]

    totals = {
        "stage1": 0, "stage2": 0, "stage3": 0,
        "other_company": 0, "other_candidate": 0,
        "total_platform_bug": 0, "total_user_error": 0, "total_borderline": 0,
        "total_included": 0, "total_excluded": 0,
        "total_slack": 0, "total_email_bugs": 0,
    }
    for r in rows:
        if r.get("source") == "Slack":
            totals["total_slack"] += 1
        else:
            totals["total_email_bugs"] += 1

        approved = r.get("approval_status", "") == "approved"
        include = r.get("include_in_report", "?")
        verdict = r.get("human_verdict", "") or r.get("assessment", "")

        if r.get("stage") == "EXCLUDED" or include == "No" or (approved and include != "Yes"):
            totals["total_excluded"] += 1
            continue

        if not approved:
            continue

        totals["total_included"] += 1
        bucket = r.get("report_bucket", "")
        if bucket == "stage1":
            totals["stage1"] += 1
        elif bucket == "stage2":
            totals["stage2"] += 1
        elif bucket == "stage3":
            totals["stage3"] += 1
        elif bucket == "other_company":
            totals["other_company"] += 1
        elif bucket == "other_candidate":
            totals["other_candidate"] += 1

        if "platform bug" in verdict.lower():
            totals["total_platform_bug"] += 1
        elif "user error" in verdict.lower():
            totals["total_user_error"] += 1
        elif "borderline" in verdict.lower():
            totals["total_borderline"] += 1

    return {"date": date_str, **totals}


def get_report_config(date_str: str) -> dict:
    """Read total_completed and total_started for a date from the Config tab."""
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        return {"total_completed": None, "total_started": None}
    try:
        service = get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{CONFIG_TAB}'!A:B",
        ).execute()
        rows = result.get("values", [])
        cfg = {}
        for row in rows:
            if len(row) >= 2:
                key = str(row[0]).strip()
                val = str(row[1]).strip()
                if key == f"total_completed:{date_str}":
                    try:
                        cfg["total_completed"] = int(val)
                    except ValueError:
                        pass
                elif key == f"total_started:{date_str}":
                    try:
                        cfg["total_started"] = int(val)
                    except ValueError:
                        pass
        return {
            "total_completed": cfg.get("total_completed"),
            "total_started": cfg.get("total_started"),
        }
    except HttpError as e:
        return {"error": f"Sheets API error: {e}"}


def set_report_config(date_str: str, total_completed: int, total_started: int) -> dict:
    """Upsert total_completed and total_started for a date in the Config tab."""
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        return {"error": "Sheet not configured."}
    try:
        service = get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{CONFIG_TAB}'!A:B",
        ).execute()
        rows = result.get("values", [])

        completed_key = f"total_completed:{date_str}"
        started_key   = f"total_started:{date_str}"
        completed_row = None
        started_row   = None

        for i, row in enumerate(rows):
            if row and str(row[0]).strip() == completed_key:
                completed_row = i + 1  # 1-based
            if row and str(row[0]).strip() == started_key:
                started_row = i + 1

        updates = []
        if completed_row:
            updates.append({"range": f"'{CONFIG_TAB}'!B{completed_row}", "values": [[total_completed]]})
        if started_row:
            updates.append({"range": f"'{CONFIG_TAB}'!B{started_row}", "values": [[total_started]]})

        if updates:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": updates},
            ).execute()

        # Append missing rows
        append_rows = []
        if not completed_row:
            append_rows.append([completed_key, total_completed])
        if not started_row:
            append_rows.append([started_key, total_started])
        if append_rows:
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"'{CONFIG_TAB}'!A:B",
                valueInputOption="USER_ENTERED",
                body={"values": append_rows},
            ).execute()

        return {"ok": True, "date": date_str, "total_completed": total_completed, "total_started": total_started}
    except HttpError as e:
        return {"error": f"Sheets API error: {e}"}


def write_daily_summary(date_str: str, summary: dict) -> dict:
    """Upsert a row in the Daily_Report_Summary tab for the given date."""
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        return {"error": "Sheet not configured."}
    try:
        service = get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{DR_SUMMARY_TAB}'!A:A",
        ).execute()
        rows = result.get("values", [])

        existing_row = None
        for i, row in enumerate(rows):
            if row and str(row[0]).strip() == date_str:
                existing_row = i + 1
                break

        row_values = [summary.get(h, "") for h in DR_SUMMARY_HEADERS]

        if existing_row:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"'{DR_SUMMARY_TAB}'!A{existing_row}",
                valueInputOption="RAW",
                body={"values": [row_values]},
            ).execute()
        else:
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"'{DR_SUMMARY_TAB}'!A:S",
                valueInputOption="RAW",
                body={"values": [row_values]},
            ).execute()

        return {"ok": True}
    except HttpError as e:
        return {"error": f"Sheets API error: {e}"}
