#!/usr/bin/env python3
"""
Run ONCE to create the Flowmingo Bug Tickets Google Sheet with full formatting.

Creates 3 tabs:
  - Bug Tickets      : main ticket tracker (two-color zones for tech vs ops team)
  - Actions Required : action items Claude flags for human review
  - README           : usage guide

Usage:
    python tools/scripts/setup_sheets.py

Prerequisites:
    1. Complete OAuth setup first: python tools/scripts/setup_oauth.py
       (must include spreadsheets scope — if you ran setup_oauth.py before adding
        the spreadsheets scope, delete credentials/token.json and re-run it)
    2. Enable the Google Sheets API in your Google Cloud project:
       APIs & Services → Library → search "Google Sheets API" → Enable

After running:
    - Open the sheet URL that is printed
    - Install the onStatusChange trigger manually (see instructions printed at end)
    - Process emails with /process-emails — bug tickets and action items populate automatically
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "persistence"))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

CREDENTIALS_PATH = Path(__file__).parent.parent.parent / "credentials" / "credentials.json"
TOKEN_PATH       = Path(__file__).parent.parent.parent / "credentials" / "token.json"
CONFIG_PATH      = Path(__file__).parent.parent.parent / "stats" / "sheets_config.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/spreadsheets",
]

SHEET_TITLE = "Flowmingo Bug Tickets"
BUG_TAB     = "Bug Tickets"
ACTION_TAB  = "Actions Required"
README_TAB  = "README"

# ---------------------------------------------------------------------------
# Column headers
# ---------------------------------------------------------------------------
BUG_HEADERS = [
    "Date Created",        # A — Zone 1 (tech)
    "Ticket ID",           # B — Zone 1
    "Status",              # C — Zone 1
    "Priority",            # D — Zone 1
    "Issue Summary (VI)",  # E — Zone 1
    "Gmail Link",          # F — Zone 1
    "Email Address",       # G — Zone 1
    "Notes",               # H — Zone 1
    "Issue Summary (EN)",  # I — Zone 2 (ops)
    "Customer Name",       # J — Zone 2
    "Subject",             # K — Zone 2
    "Issue Type",          # L — Zone 2
    "Slack Message",       # M — Zone 2
    "Draft ID",            # N — Zone 2
    "Thread ID",           # O — Zone 2
    "Sent At",             # P — Zone 2
]

ACTION_HEADERS = [
    "Date Logged",    # A
    "Action Type",    # B
    "Priority",       # C
    "Customer Name",  # D
    "Email Address",  # E
    "Subject",        # F
    "Reason / Details",  # G
    "Gmail Link",     # H
    "Status",         # I
    "Handled By",     # J
    "Handled At",     # K
]

# Column widths in pixels
BUG_WIDTHS = [120, 140, 130, 100, 280, 60, 180, 300, 280, 130, 200, 120, 300, 160, 160, 120]
ACTION_WIDTHS = [130, 140, 90, 140, 180, 200, 350, 60, 90, 130, 120]

# Zone 1: columns A–H (indices 0–7) — tech team, light blue header
# Zone 2: columns I–P (indices 8–15) — operations, light green header
ZONE1_HEADER_COLOR = {"red": 0.812, "green": 0.886, "blue": 1.0}       # #cfe2ff
ZONE2_HEADER_COLOR = {"red": 0.851, "green": 0.918, "blue": 0.827}     # #d9ead3
HEADER_TEXT_COLOR  = {"red": 0.122, "green": 0.161, "blue": 0.216}     # #1f2937

# Status conditional formatting colors
STATUS_COLORS = {
    "Reported":         {"red": 0.918, "green": 0.918, "blue": 0.918},  # #eaeaea
    "Verified":         {"red": 0.988, "green": 0.91,  "blue": 0.698},  # #fce8b2
    "Fix in Progress":  {"red": 0.788, "green": 0.855, "blue": 0.973},  # #c9daf8
    "Resolved":         {"red": 0.714, "green": 0.843, "blue": 0.659},  # #b6d7a8
}

# Action priority colors
PRIORITY_COLORS = {
    "High":   {"red": 0.988, "green": 0.733, "blue": 0.733},  # #fbbe bb
    "Normal": {"red": 1.0,   "green": 1.0,   "blue": 1.0},
}


def rgb(r, g, b):
    return {"red": r / 255, "green": g / 255, "blue": b / 255}


def get_service(api: str, version: str):
    creds = Credentials.from_authorized_user_info(
        json.loads(TOKEN_PATH.read_text()), SCOPES
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return build(api, version, credentials=creds)


def create_spreadsheet() -> tuple[str, dict]:
    """Create spreadsheet with 3 tabs. Returns (spreadsheet_id, tab_ids dict)."""
    service = get_service("sheets", "v4")
    body = {
        "properties": {"title": SHEET_TITLE},
        "sheets": [
            {"properties": {"title": BUG_TAB,    "index": 0}},
            {"properties": {"title": ACTION_TAB, "index": 1}},
            {"properties": {"title": README_TAB, "index": 2}},
        ],
    }
    result = service.spreadsheets().create(body=body).execute()
    sid = result["spreadsheetId"]
    tab_ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in result["sheets"]}
    return sid, tab_ids


def write_headers(service, sid: str):
    """Write header rows for Bug Tickets and Actions Required."""
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=sid,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": [
                {"range": f"{BUG_TAB}!A1",    "values": [BUG_HEADERS]},
                {"range": f"{ACTION_TAB}!A1",  "values": [ACTION_HEADERS]},
            ],
        },
    ).execute()


def _col_width_request(sheet_id: int, col_index: int, width: int) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": col_index,
                "endIndex": col_index + 1,
            },
            "properties": {"pixelSize": width},
            "fields": "pixelSize",
        }
    }


def _freeze_request(sheet_id: int, rows: int = 1) -> dict:
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": rows},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    }


def _header_format_request(sheet_id: int, start_col: int, end_col: int, bg_color: dict) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": bg_color,
                    "textFormat": {
                        "foregroundColor": HEADER_TEXT_COLOR,
                        "bold": True,
                        "fontSize": 10,
                    },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "WRAP",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
        }
    }


def _dropdown_request(sheet_id: int, col_index: int, values: list[str]) -> dict:
    return {
        "setDataValidation": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 2000,
                "startColumnIndex": col_index,
                "endColumnIndex": col_index + 1,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in values],
                },
                "strict": True,
                "showCustomUi": True,
            },
        }
    }


def _conditional_format_eq(sheet_id: int, col_index: int, value: str, bg_color: dict) -> dict:
    """Conditional format: entire row shaded when col_index cell equals value."""
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 2000,
                }],
                "booleanRule": {
                    "condition": {
                        "type": "CUSTOM_FORMULA",
                        "values": [{"userEnteredValue": f'=${chr(65 + col_index)}2="{value}"'}],
                    },
                    "format": {"backgroundColor": bg_color},
                },
            },
            "index": 0,
        }
    }


def _protect_range_request(sheet_id: int, start_col: int, end_col: int, description: str) -> dict:
    """Add a warning-only protection on a column range (does not block editing, just warns)."""
    return {
        "addProtectedRange": {
            "protectedRange": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 2000,
                    "startColumnIndex": start_col,
                    "endColumnIndex": end_col,
                },
                "description": description,
                "warningOnly": True,
            }
        }
    }


def format_bug_tab(service, sid: str, sheet_id: int):
    requests = []

    # Freeze header
    requests.append(_freeze_request(sheet_id))

    # Zone 1 header (cols A–H, indices 0–7): light blue
    requests.append(_header_format_request(sheet_id, 0, 8, ZONE1_HEADER_COLOR))
    # Zone 2 header (cols I–P, indices 8–16): light green
    requests.append(_header_format_request(sheet_id, 8, 16, ZONE2_HEADER_COLOR))

    # Column widths
    for i, w in enumerate(BUG_WIDTHS):
        requests.append(_col_width_request(sheet_id, i, w))

    # Row height for header
    requests.append({
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 40},
            "fields": "pixelSize",
        }
    })

    # Status dropdown (col C, index 2)
    requests.append(_dropdown_request(sheet_id, 2, ["Reported", "Verified", "Fix in Progress", "Resolved"]))

    # Priority dropdown (col D, index 3)
    requests.append(_dropdown_request(sheet_id, 3, ["Low", "Normal", "High", "Critical"]))

    # Conditional formatting on Status (col C): color-code each status value
    for status, color in STATUS_COLORS.items():
        requests.append(_conditional_format_eq(sheet_id, 2, status, color))

    # Warning protection on auto-filled locked columns: A, B, F, G, I–O (not C, D, E, H, P)
    requests.append(_protect_range_request(sheet_id, 0, 2, "Auto-filled by Claude — Date, Ticket ID"))
    requests.append(_protect_range_request(sheet_id, 5, 7, "Auto-filled by Claude — Gmail Link, Email"))
    requests.append(_protect_range_request(sheet_id, 8, 15, "Auto-filled by Claude — Ops columns (EN summary through Thread ID)"))

    # Bold Ticket ID column (B)
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2000,
                      "startColumnIndex": 1, "endColumnIndex": 2},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold",
        }
    })

    service.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": requests}).execute()


def format_action_tab(service, sid: str, sheet_id: int):
    requests = []

    # Freeze header
    requests.append(_freeze_request(sheet_id))

    # Header: dark slate background across all columns
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.17, "green": 0.24, "blue": 0.31},
                    "textFormat": {
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        "bold": True, "fontSize": 10,
                    },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "WRAP",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
        }
    })

    # Row height for header
    requests.append({
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 40},
            "fields": "pixelSize",
        }
    })

    # Column widths
    for i, w in enumerate(ACTION_WIDTHS):
        requests.append(_col_width_request(sheet_id, i, w))

    # Status dropdown (col I, index 8): Pending / Done
    requests.append(_dropdown_request(sheet_id, 8, ["Pending", "Done"]))

    # Priority dropdown (col C, index 2)
    requests.append(_dropdown_request(sheet_id, 2, ["High", "Normal"]))

    # Conditional: Pending rows → light yellow
    requests.append(_conditional_format_eq(sheet_id, 8, "Pending",
                                           {"red": 1.0, "green": 0.949, "blue": 0.8}))
    # Conditional: Done rows → light green
    requests.append(_conditional_format_eq(sheet_id, 8, "Done",
                                           {"red": 0.851, "green": 0.918, "blue": 0.827}))
    # Conditional: High priority → light red background on Priority cell
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2000,
                             "startColumnIndex": 2, "endColumnIndex": 3}],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "High"}]},
                    "format": {"backgroundColor": {"red": 0.988, "green": 0.733, "blue": 0.733}},
                },
            },
            "index": 0,
        }
    })

    service.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": requests}).execute()


def write_readme(service, sid: str, readme_sheet_id: int):
    """Write README content and format the tab."""
    content = [
        ["Flowmingo Bug Ticket Sheet — Usage Guide"],
        [""],
        ["TABS"],
        ["Bug Tickets",       "Main tracker. One row per customer bug report."],
        ["Actions Required",  "Items that need human action before Claude can proceed (FM/review emails, DNC requests, vague bugs)."],
        ["README",            "This guide."],
        [""],
        ["BUG TICKETS — COLUMN ZONES"],
        ["Zone",  "Columns", "Color",      "Who manages it"],
        ["Tech team",   "A–H",  "Light blue header",  "Daily: update Status, Priority, Issue Summary (VI), Notes"],
        ["Operations",  "I–P",  "Light green header", "Admin: Slack copy, Draft ID, Thread ID, Sent At"],
        [""],
        ["BUG TICKETS — EDITABLE COLUMNS (tech team)"],
        ["C — Status",            "Dropdown: Reported → Verified → Fix in Progress → Resolved. Changing this auto-creates a Gmail draft for the customer."],
        ["D — Priority",          "Dropdown: Low / Normal / High / Critical"],
        ["E — Issue Summary (VI)", "Translate or annotate the English issue summary in Vietnamese for internal use."],
        ["H — Notes",             "Internal technical notes. Visible only to the team. Not sent to the customer."],
        [""],
        ["BUG TICKETS — AUTO-FILLED COLUMNS (do not edit)"],
        ["A — Date Created",      "Auto-set by Claude when the ticket is created."],
        ["B — Ticket ID",         "Unique ID in format BUG-YYMMDD-SEQ. Never change this."],
        ["F — Gmail Link",        "Click 'Open' to open the original email thread in Gmail (view attachments, context)."],
        ["G — Email Address",     "Customer email address."],
        ["I — Issue Summary (EN)", "English summary written by Claude. Source for the customer-facing emails."],
        ["M — Slack Message",     "Pre-formatted Slack post. Copy-paste to your team channel. Includes Gmail link and original message."],
        ["N — Draft ID",          "Gmail draft ID for the acknowledgment email."],
        ["O — Thread ID",         "Gmail thread ID. Used by the auto-draft trigger."],
        [""],
        ["STATUS WORKFLOW"],
        ["Reported",        "Claude created the ticket. Acknowledgment draft is in Gmail — send it to the customer."],
        ["Verified",        "Tech team confirmed the bug. Change status here → Gmail draft is auto-created to notify the customer."],
        ["Fix in Progress", "Engineering is working on it. Change status here → Gmail draft is auto-created."],
        ["Resolved",        "Fix deployed. Change status here → Gmail draft is auto-created. Fill Sent At after sending."],
        [""],
        ["ACTIONS REQUIRED TAB"],
        ["Review Draft",    "Claude created a draft but flagged it for human review before sending. Check the Gmail draft, edit if needed, then send manually."],
        ["DNC Request",     "Customer demanded no further contact. Unsubscribe them and mark as DNC before doing anything else."],
        ["Manual Follow-up", "Something else needs human attention — see the Reason column for details."],
        [""],
        ["STATUS CHANGE → AUTO-DRAFT"],
        ["When you change Status (col C) to Verified, Fix in Progress, or Resolved, an Apps Script trigger automatically",
         "creates a Gmail draft in the customer's original thread. Review and send it from Gmail."],
        ["To install the trigger: Extensions > Apps Script > Triggers (clock icon) > Add Trigger",
         "Function: onStatusChange | Event: On edit | then Save and approve permissions."],
    ]

    service.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"{README_TAB}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": content},
    ).execute()

    # Format the README tab
    requests = [
        # Title row: large bold
        {
            "repeatCell": {
                "range": {"sheetId": readme_sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True, "fontSize": 14},
                    "backgroundColor": {"red": 0.17, "green": 0.24, "blue": 0.31},
                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                   "bold": True, "fontSize": 14},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
        # Section headers bold
        {
            "repeatCell": {
                "range": {"sheetId": readme_sheet_id, "startRowIndex": 2, "endRowIndex": 3},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 11}}},
                "fields": "userEnteredFormat.textFormat",
            }
        },
        # Col A wider
        _col_width_request(readme_sheet_id, 0, 260),
        _col_width_request(readme_sheet_id, 1, 520),
        _freeze_request(readme_sheet_id, 0),
    ]
    service.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": requests}).execute()


def install_apps_script(spreadsheet_id: str):
    """Install the combined Apps Script (menu + onStatusChange trigger)."""
    apps_script_code = read_gs_file()

    try:
        script_service = get_service("script", "v1")
        project = script_service.projects().create(body={
            "title": "Flowmingo Ticket Actions",
            "parentId": spreadsheet_id,
        }).execute()
        script_id = project["scriptId"]

        script_service.projects().updateContent(
            scriptId=script_id,
            body={
                "files": [
                    {
                        "name": "Code",
                        "type": "SERVER_JS",
                        "source": apps_script_code,
                    },
                    {
                        "name": "appsscript",
                        "type": "JSON",
                        "source": json.dumps({
                            "timeZone": "Asia/Ho_Chi_Minh",
                            "exceptionLogging": "STACKDRIVER",
                            "runtimeVersion": "V8",
                            "oauthScopes": [
                                "https://www.googleapis.com/auth/gmail.modify",
                                "https://www.googleapis.com/auth/gmail.compose",
                                "https://www.googleapis.com/auth/spreadsheets",
                            ],
                        }),
                    },
                ]
            },
        ).execute()
        print("Apps Script installed successfully.")
        return script_id
    except HttpError as e:
        print(f"Warning: Could not install Apps Script automatically: {e}")
        print("Add the script manually via Extensions > Apps Script in the sheet.")
        return None


def read_gs_file() -> str:
    """Read the .gs trigger file to use as the Apps Script source."""
    gs_path = Path(__file__).parent / "bug_ticket_status_trigger.gs"
    if gs_path.exists():
        return gs_path.read_text(encoding="utf-8")
    # Fallback: minimal script if .gs file is missing
    return """
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Flowmingo Tickets')
    .addItem('Open README', 'openReadme')
    .addToUi();
}
function openReadme() {
  SpreadsheetApp.getActiveSpreadsheet().getSheetByName('README').activate();
}
"""


def save_config(spreadsheet_id: str):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = {}
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass

    old_id = config.get("spreadsheet_id")
    if old_id and old_id != spreadsheet_id:
        print(f"Note: previous sheet ID was {old_id} — now replaced with new sheet.")
        print(f"Old sheet: https://docs.google.com/spreadsheets/d/{old_id}")

    config["spreadsheet_id"] = spreadsheet_id
    config["sheet_name"] = SHEET_TITLE
    config["tab_name"] = BUG_TAB
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


def main():
    if not TOKEN_PATH.exists():
        print("ERROR: token.json not found.")
        print("Run: python tools/scripts/setup_oauth.py")
        sys.exit(1)

    print(f"Creating Google Sheet: '{SHEET_TITLE}'...")
    sid, tab_ids = create_spreadsheet()
    bug_id    = tab_ids[BUG_TAB]
    action_id = tab_ids[ACTION_TAB]
    readme_id = tab_ids[README_TAB]
    print(f"Sheet created: {sid}")

    service = get_service("sheets", "v4")

    print("Writing headers...")
    write_headers(service, sid)

    print("Formatting Bug Tickets tab...")
    format_bug_tab(service, sid, bug_id)

    print("Formatting Actions Required tab...")
    format_action_tab(service, sid, action_id)

    print("Writing README tab...")
    write_readme(service, sid, readme_id)

    print("Installing Apps Script...")
    install_apps_script(sid)

    save_config(sid)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sid}"
    print()
    print("=" * 60)
    print("Setup complete!")
    print(f"Sheet URL: {sheet_url}")
    print()
    print("NEXT STEPS:")
    print("  1. Open the sheet URL above")
    print("  2. Install the onStatusChange trigger:")
    print("       Extensions > Apps Script")
    print("       Click the clock icon (Triggers) > Add Trigger")
    print("       Function: onStatusChange")
    print("       Event source: From spreadsheet")
    print("       Event type: On edit")
    print("       Save + approve permissions")
    print("  3. Run /process-emails — bug tickets and action items populate automatically")
    print("  4. Read the README tab for a full guide")
    print("=" * 60)


if __name__ == "__main__":
    main()
