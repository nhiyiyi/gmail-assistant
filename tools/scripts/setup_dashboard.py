"""
setup_dashboard.py — One-time setup for Bug Reporting Dashboard.

Automatically:
  1. Adds cols Q–T headers to "Bug Tickets" tab (Screenshot URL, In Report, Report Date, Attachment URL)
  2. Backfills "In Report" = "Yes" for existing data rows that have it empty
  3. Creates (or resets) the "Config" tab with statuses, priorities, features
  4. Adds data validation dropdowns on Status (col C) and Priority (col D)

Uses existing credentials and sheet ID — no extra config needed.

Usage:
    cd d:/Cursor\ test/gmail-assistant
    python tools/scripts/setup_dashboard.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "api"))

from sheets_client import get_service, get_sheet_id, BUG_TAB

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_TAB = "Config"

STATUSES   = ["Reported", "Verified", "Fix in Progress", "Resolved", "Duplicate", "Won't Fix"]
PRIORITIES = ["High", "Normal", "Low"]
FEATURES   = ["Payroll", "Attendance", "Leave", "Reports", "Integrations", "Account", "Other"]

NEW_HEADERS = {
    # F is written by the migration script (migrate_main_issue_column.py) and
    # by append_ticket_row — do not add it here to avoid overwriting live data.
    "R": "Screenshot URL",    # col 18
    "S": "In Report",         # col 19
    "T": "Report Date",       # col 20
    "U": "Attachment URL",    # col 21
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_sheet_tab_id(service, spreadsheet_id: str, tab_name: str) -> int | None:
    """Return the sheetId (integer) for a tab by name, or None if not found."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == tab_name:
            return props["sheetId"]
    return None


def add_or_get_tab(service, spreadsheet_id: str, tab_name: str) -> int:
    """Create a tab if it doesn't exist. Return its sheetId."""
    existing = get_sheet_tab_id(service, spreadsheet_id, tab_name)
    if existing is not None:
        print(f"  Tab '{tab_name}' already exists (sheetId={existing})")
        return existing

    resp = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
    ).execute()
    new_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"  Created tab '{tab_name}' (sheetId={new_id})")
    return new_id


# ---------------------------------------------------------------------------
# Step 1 — Add Q–T headers to Bug Tickets
# ---------------------------------------------------------------------------


def add_new_headers(service, spreadsheet_id: str):
    print("\n[1] Adding Q–T headers to 'Bug Tickets'…")
    for letter, header in NEW_HEADERS.items():
        range_ = f"{BUG_TAB}!{letter}1"
        existing = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_
        ).execute().get("values", [])

        if existing and existing[0][0] == header:
            print(f"  {letter}1 already '{header}' — skipping")
            continue

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_,
            valueInputOption="USER_ENTERED",
            body={"values": [[header]]},
        ).execute()
        print(f"  Set {letter}1 = '{header}'")


# ---------------------------------------------------------------------------
# Step 2 — Backfill "In Report" = "Yes" for existing rows
# ---------------------------------------------------------------------------


def backfill_in_report(service, spreadsheet_id: str):
    print("\n[2] Backfilling 'In Report' (col R) for existing rows…")
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{BUG_TAB}!A:S",
    ).execute()
    rows = result.get("values", [])

    if len(rows) < 2:
        print("  No data rows found — nothing to backfill")
        return

    updates = []
    for i, row in enumerate(rows[1:], start=2):  # 1-indexed, skip header
        # Col S (In Report) is index 18 (0-based)
        in_report = row[18] if len(row) > 18 else ""
        ticket_id = row[1] if len(row) > 1 else ""
        if not ticket_id:
            continue  # skip empty rows
        if not in_report:
            updates.append({
                "range": f"{BUG_TAB}!S{i}",
                "values": [["Yes"]],
            })

    if not updates:
        print("  All existing rows already have 'In Report' set")
        return

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "USER_ENTERED", "data": updates},
    ).execute()
    print(f"  Backfilled {len(updates)} rows with 'In Report' = 'Yes'")


# ---------------------------------------------------------------------------
# Step 3 — Create/reset Config tab
# ---------------------------------------------------------------------------


def setup_config_tab(service, spreadsheet_id: str):
    print(f"\n[3] Setting up '{CONFIG_TAB}' tab…")
    add_or_get_tab(service, spreadsheet_id, CONFIG_TAB)

    rows = [["Category", "Value"]]
    for status in STATUSES:
        rows.append(["Statuses", status])
    for priority in PRIORITIES:
        rows.append(["Priorities", priority])
    for feature in FEATURES:
        rows.append(["Features", feature])

    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"{CONFIG_TAB}!A:B",
    ).execute()

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{CONFIG_TAB}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()
    print(f"  Wrote {len(rows) - 1} config rows ({len(STATUSES)} statuses, {len(PRIORITIES)} priorities, {len(FEATURES)} features)")


# ---------------------------------------------------------------------------
# Step 4 — Data validation on Status (col C) and Priority (col D)
# ---------------------------------------------------------------------------


def set_dropdown_validation(service, spreadsheet_id: str):
    print("\n[4] Setting data validation dropdowns…")
    bug_sheet_id = get_sheet_tab_id(service, spreadsheet_id, BUG_TAB)
    if bug_sheet_id is None:
        print(f"  ERROR: Could not find sheet '{BUG_TAB}'")
        return

    def make_validation_request(col_index: int, values: list[str]):
        return {
            "setDataValidation": {
                "range": {
                    "sheetId": bug_sheet_id,
                    "startRowIndex": 1,       # row 2 (0-based), skip header
                    "endRowIndex": 10000,
                    "startColumnIndex": col_index,
                    "endColumnIndex": col_index + 1,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in values],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        }

    requests = [
        make_validation_request(2, STATUSES),   # col C = index 2
        make_validation_request(3, PRIORITIES),  # col D = index 3
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()
    print("  Set Status dropdown (col C) and Priority dropdown (col D)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("Bug Dashboard — Sheet Setup")
    print("=" * 60)

    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        print("ERROR: No spreadsheet ID found in stats/sheets_config.json")
        print("       Run tools/scripts/setup_sheets.py first.")
        sys.exit(1)

    print(f"\nSpreadsheet ID: {spreadsheet_id}")
    print(f"Sheet URL: https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit")

    service = get_service()

    add_new_headers(service, spreadsheet_id)
    backfill_in_report(service, spreadsheet_id)
    setup_config_tab(service, spreadsheet_id)
    set_dropdown_validation(service, spreadsheet_id)

    print("\n" + "=" * 60)
    print("Setup complete!")
    print()
    print("Next steps:")
    print("  1. Open the Apps Script editor for your spreadsheet")
    print("  2. Create BugDashboard.gs and BugDashboard.html from this project")
    print("  3. In Script Properties, add:  BUG_SHEET_ID =", spreadsheet_id)
    print("  4. Deploy as Web App (Execute as: Me, Access: Anyone)")
    print("=" * 60)


if __name__ == "__main__":
    main()
