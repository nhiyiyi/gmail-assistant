#!/usr/bin/env python3
"""
Push daily-report/YYYY-MM-DD.csv rows to the "Daily Report" sheet tab.

Usage:
    python tools/scripts/setup_daily_report_tab.py [YYYY-MM-DD]
    If date is omitted, defaults to the most recent CSV in daily-report/.

Incremental by design: existing rows are never deleted. Only rows whose ID
(col J = ticket_id or submission_id) is not already in the sheet are appended.
Human Count?/Notes edits in the sheet are always preserved.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src" / "api"))

from sheets_client import get_service, get_sheet_id

DAILY_REPORT_TAB = "Daily Report"

# 12 simple columns — replaces the old 22-column layout
DR_HEADERS = [
    "Date",       # A — YYYY-MM-DD
    "Time",       # B — HH:MM GMT+7
    "Source",     # C — Sheet / Slack
    "Name",       # D — candidate/company name
    "Issue",      # E — first 200 chars of issue text
    "Stage",      # F — Stage 1 / Stage 2 / Stage 3 / Other Company / Other Candidate / EXCLUDED
    "Category",   # G — specific bug category
    "Count?",     # H — Yes / No / ?  (pre-filled by Claude, editable by reviewer)
    "Notes",      # I — reviewer free text
    "ID",         # J — ticket_id or submission_id (used for dedup)
    "Company",    # K — company name
    "Device",     # L — browser + OS (Slack only)
]

# Column widths in pixels
COL_WIDTHS = [100, 65, 80, 140, 340, 110, 220, 80, 220, 260, 150, 200]

# Old layout had 22 columns — detect and migrate
OLD_COL_COUNT = 22


def _get_sheet_meta(service, spreadsheet_id):
    return service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()


def get_or_create_tab(service, spreadsheet_id):
    """Return sheetId of 'Daily Report' tab, creating it if needed.
    Also detects old 22-column layout and wipes it for migration."""
    meta = _get_sheet_meta(service, spreadsheet_id)
    for s in meta["sheets"]:
        if s["properties"]["title"] == DAILY_REPORT_TAB:
            sheet_id = s["properties"]["sheetId"]
            # Check if it's the old layout by reading the header row
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"'{DAILY_REPORT_TAB}'!1:1",
            ).execute()
            header_row = result.get("values", [[]])[0]
            if len(header_row) == OLD_COL_COUNT or (header_row and header_row[0] == "screenshot_url"):
                print(f"Detected old 22-column layout — wiping and recreating tab.")
                # Delete all data rows (keep tab, clear everything)
                service.spreadsheets().values().clear(
                    spreadsheetId=spreadsheet_id,
                    range=f"'{DAILY_REPORT_TAB}'",
                    body={},
                ).execute()
                # Remove all conditional format rules by fetching and deleting
                _clear_conditional_formats(service, spreadsheet_id, sheet_id)
            else:
                print(f"Tab '{DAILY_REPORT_TAB}' already exists (new format).")
            return sheet_id

    # Create the tab
    resp = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": DAILY_REPORT_TAB}}}]},
    ).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"Created tab '{DAILY_REPORT_TAB}' (sheetId={sheet_id})")
    return sheet_id


def _clear_conditional_formats(service, spreadsheet_id, sheet_id):
    """Remove all conditional format rules from a sheet."""
    meta = _get_sheet_meta(service, spreadsheet_id)
    for s in meta["sheets"]:
        if s["properties"]["sheetId"] == sheet_id:
            rules = s.get("conditionalFormats", [])
            if rules:
                requests = [
                    {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}
                    for _ in rules
                ]
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id, body={"requests": requests}
                ).execute()
            break


def setup_headers_and_formatting(service, spreadsheet_id, sheet_id):
    """Write header row, freeze it, set column widths, apply dropdowns + colors."""
    num_cols = len(DR_HEADERS)
    requests = []

    # Column widths
    for i, px in enumerate(COL_WIDTHS):
        requests.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }
        })

    # Freeze row 1
    requests.append({
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # Header style: dark background, white bold text
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": num_cols},
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.122, "green": 0.161, "blue": 0.216},
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    "verticalAlignment": "MIDDLE",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)",
        }
    })

    # Dropdown: Count? (col H = index 7)
    count_col = DR_HEADERS.index("Count?")
    requests.append({
        "setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 5000,
                      "startColumnIndex": count_col, "endColumnIndex": count_col + 1},
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [
                        {"userEnteredValue": "Yes"},
                        {"userEnteredValue": "No"},
                        {"userEnteredValue": "?"},
                    ]
                },
                "showCustomUi": True, "strict": False,
            }
        }
    })

    # Dropdown: Stage (col F = index 5)
    stage_col = DR_HEADERS.index("Stage")
    requests.append({
        "setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 5000,
                      "startColumnIndex": stage_col, "endColumnIndex": stage_col + 1},
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [
                        {"userEnteredValue": "Stage 1"},
                        {"userEnteredValue": "Stage 2"},
                        {"userEnteredValue": "Stage 3"},
                        {"userEnteredValue": "Other Company"},
                        {"userEnteredValue": "Other Candidate"},
                        {"userEnteredValue": "EXCLUDED"},
                    ]
                },
                "showCustomUi": True, "strict": False,
            }
        }
    })

    # Conditional formatting on Count? column
    def cf_rule(value, bg_rgb):
        return {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 5000,
                                "startColumnIndex": count_col, "endColumnIndex": count_col + 1}],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": value}]},
                        "format": {
                            "backgroundColor": {"red": bg_rgb[0], "green": bg_rgb[1], "blue": bg_rgb[2]},
                        }
                    }
                },
                "index": 0
            }
        }

    # Yes = light green, No = light gray, ? = light yellow
    requests += [
        cf_rule("Yes", (0.820, 0.980, 0.820)),
        cf_rule("No",  (0.900, 0.900, 0.900)),
        cf_rule("?",   (1.000, 0.980, 0.800)),
    ]

    # Also gray out EXCLUDED rows (Stage col F = EXCLUDED → light gray entire row)
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 5000,
                            "startColumnIndex": 0, "endColumnIndex": num_cols}],
                "booleanRule": {
                    "condition": {
                        "type": "CUSTOM_FORMULA",
                        "values": [{"userEnteredValue": '=$F2="EXCLUDED"'}]
                    },
                    "format": {
                        "textFormat": {"foregroundColor": {"red": 0.6, "green": 0.6, "blue": 0.6}},
                        "backgroundColor": {"red": 0.965, "green": 0.965, "blue": 0.965},
                    }
                }
            },
            "index": 0
        }
    })

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()

    # Write header row
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{DAILY_REPORT_TAB}'!A1",
        valueInputOption="RAW",
        body={"values": [DR_HEADERS]},
    ).execute()
    print("Headers and formatting applied.")


def _get_existing_ids(service, spreadsheet_id):
    """Return a set of IDs already in the sheet (col J = index 9)."""
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{DAILY_REPORT_TAB}'!J:J",
    ).execute()
    rows = result.get("values", [])
    # Skip header row, collect non-empty values
    return {row[0].strip() for row in rows[1:] if row and row[0].strip()}


def push_incremental(service, spreadsheet_id, csv_path):
    """Append only rows whose ID (col J) is not already in the sheet."""
    existing_ids = _get_existing_ids(service, spreadsheet_id)
    print(f"Existing IDs in sheet: {len(existing_ids)}")

    new_rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry_id = row.get("id", "").strip()
            if not entry_id or entry_id in existing_ids:
                continue  # skip already-present or ID-less rows
            new_rows.append([row.get(h, "") for h in DR_HEADERS])

    if not new_rows:
        print("No new rows to add.")
        return

    # Find where to append
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{DAILY_REPORT_TAB}'!A:A",
    ).execute()
    next_row = len(result.get("values", [])) + 1

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{DAILY_REPORT_TAB}'!A{next_row}",
        valueInputOption="RAW",
        body={"values": new_rows},
    ).execute()
    print(f"Appended {len(new_rows)} new rows starting at row {next_row}.")


def main():
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        print("ERROR: Spreadsheet ID not configured. Run tools/scripts/setup_sheets.py first.")
        sys.exit(1)

    # Resolve CSV path
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        daily_dir = ROOT / "daily-report"
        csvs = sorted(daily_dir.glob("*.csv"))
        if not csvs:
            print(f"No CSVs found in {daily_dir}")
            sys.exit(1)
        date_str = csvs[-1].stem  # most recent

    csv_path = ROOT / "daily-report" / f"{date_str}.csv"
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    print(f"Using spreadsheet: {spreadsheet_id}")
    print(f"Using CSV: {csv_path}")

    service = get_service()
    sheet_id = get_or_create_tab(service, spreadsheet_id)
    setup_headers_and_formatting(service, spreadsheet_id, sheet_id)
    push_incremental(service, spreadsheet_id, csv_path)
    print("Done.")


if __name__ == "__main__":
    main()
