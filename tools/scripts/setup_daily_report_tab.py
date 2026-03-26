#!/usr/bin/env python3
"""
Set up (or migrate) the Daily Report sheet infrastructure:
  - "Daily Report"          tab (29 columns, 5 colour zones)
  - "Daily_Report_Summary"  tab
  - "Definitions"           tab
  - Writes CSV data with upsert (approved rows are never deleted)

Usage:
    python tools/scripts/setup_daily_report_tab.py [YYYY-MM-DD]
    If date is omitted, defaults to the most recent CSV in daily-report/.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "src" / "api"))

from sheets_client import (
    get_service, get_sheet_id,
    DR_HEADERS, DR_SUMMARY_HEADERS,
    DAILY_REPORT_TAB, DR_SUMMARY_TAB,
)

DEFINITIONS_TAB = "Definitions"

# ── Column widths (pixels) ────────────────────────────────────────────────────
COL_WIDTHS = [
    # Group A — Identity (cols 0-5)
    160, 100, 90, 110, 150, 220,
    # Group B — Raw Content (cols 6-18)
    220, 360, 180, 160, 160, 100, 200, 200, 160, 260, 110, 100, 130,
    # Group C — Claude Judgment (cols 19-21)
    155, 100, 320,
    # Group D — Human Review (cols 22-25)
    140, 220, 110, 180,
    # Group E — Approval (cols 26-28)
    130, 140, 160,
]

# ── Header colour zones ───────────────────────────────────────────────────────
# Each zone: (start_col_0based, end_col_exclusive, bg_rgb, text_rgb)
HEADER_ZONES = [
    (0,  6,  (0.30, 0.30, 0.35), (1, 1, 1)),   # Group A — dark grey
    (6,  19, (0.18, 0.39, 0.70), (1, 1, 1)),   # Group B — blue
    (19, 22, (0.60, 0.55, 0.10), (1, 1, 1)),   # Group C — gold/yellow
    (22, 26, (0.13, 0.50, 0.30), (1, 1, 1)),   # Group D — green
    (26, 29, (0.40, 0.20, 0.60), (1, 1, 1)),   # Group E — purple
]

# ── Definitions content ───────────────────────────────────────────────────────
DEFINITIONS = [
    ("Term", "Definition"),
    ("Platform Bug", "A confirmed technical defect in the Flowmingo platform — not caused by the user."),
    ("Likely Platform Bug", "Strong indicators of a platform defect, but not yet confirmed."),
    ("Borderline", "Could be platform or user error. Requires human judgement. Counted separately."),
    ("Likely User Error", "Issue is almost certainly caused by user action or environment (browser, network)."),
    ("User Error", "Confirmed user-caused issue. Does NOT count toward the boss bug report."),
    ("Exclude", "Should not appear in the report at all (test entry, duplicate, feature request, etc.)."),
    ("", ""),
    ("approval_status: new", "Row just written by Claude. Needs human review."),
    ("approval_status: reviewed", "Human has looked at the row but not yet finalised verdict."),
    ("approval_status: approved", "Human has approved this row. It counts in the final report totals."),
    ("approval_status: excluded", "Human has excluded this row. It does NOT count."),
    ("", ""),
    ("include_in_report: Yes", "This item is included in the final boss count."),
    ("include_in_report: No", "This item is excluded from the boss count."),
    ("include_in_report: ?", "Default — not yet decided. Treated as excluded until approved."),
    ("", ""),
    ("human_verdict overrides assessment", "If human_verdict is set, it takes priority over Claude's assessment when computing totals."),
    ("Percentages", "pct_completed = total_included / total_completed. pct_started = total_included / total_started."),
    ("Stage 1", "Issues before the candidate answers their first question."),
    ("Stage 2", "Issues during the interview (between first answer and submission)."),
    ("Stage 3", "Issues after submission (evaluation, results, retake)."),
    ("Other (Company)", "Recruiter/company-side bugs not tied to a candidate stage."),
    ("Other (Candidate)", "Candidate-side issues that don't fit any numbered stage."),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_or_create_tab(service, spreadsheet_id: str, title: str) -> int:
    """Return sheetId of a tab (by title), creating it if missing."""
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    resp = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
    ).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"  Created tab '{title}' (sheetId={sheet_id})")
    return sheet_id


def get_sheet_id_for_tab(service, spreadsheet_id: str, title: str) -> int:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    raise ValueError(f"Tab '{title}' not found")


# ── Daily Report tab setup ────────────────────────────────────────────────────

def setup_daily_report_tab(service, spreadsheet_id: str):
    """Create or update the Daily Report tab with 29-column schema."""
    sheet_id = get_or_create_tab(service, spreadsheet_id, DAILY_REPORT_TAB)
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

    # Colour zone headers
    for start, end, bg, fg in HEADER_ZONES:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": start, "endColumnIndex": end},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": bg[0], "green": bg[1], "blue": bg[2]},
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": fg[0], "green": fg[1], "blue": fg[2]},
                        },
                        "verticalAlignment": "MIDDLE",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment)",
            }
        })

    # Data validation dropdowns
    def dropdown(col_name, values):
        col_idx = DR_HEADERS.index(col_name)
        return {
            "setDataValidation": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2000,
                          "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1},
                "rule": {
                    "condition": {"type": "ONE_OF_LIST",
                                  "values": [{"userEnteredValue": v} for v in values]},
                    "showCustomUi": True, "strict": False,
                }
            }
        }

    requests += [
        dropdown("assessment",      ["Platform Bug", "Likely Platform Bug", "Borderline", "Likely User Error", "Unknown", "N/A"]),
        dropdown("confidence",      ["High", "Medium", "Low"]),
        dropdown("source",          ["Google Sheet", "Slack"]),
        dropdown("human_verdict",   ["Platform Bug", "User Error", "Borderline", "Exclude"]),
        dropdown("include_in_report", ["Yes", "No", "?"]),
        dropdown("report_bucket",   ["stage1", "stage2", "stage3", "other_company", "other_candidate", "excluded"]),
        dropdown("approval_status", ["new", "reviewed", "approved", "excluded"]),
        dropdown("stage",           ["Stage 1", "Stage 2", "Stage 3", "Other Company", "Other Candidate", "EXCLUDED"]),
    ]

    # Conditional formatting — human_verdict
    verdict_col = DR_HEADERS.index("human_verdict")

    def cf(col_idx, value, bg_rgb, text_rgb):
        return {
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2000,
                                "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1}],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": value}]},
                        "format": {
                            "backgroundColor": {"red": bg_rgb[0], "green": bg_rgb[1], "blue": bg_rgb[2]},
                            "textFormat": {"foregroundColor": {"red": text_rgb[0], "green": text_rgb[1], "blue": text_rgb[2]}},
                        }
                    }
                },
                "index": 0,
            }
        }

    requests += [
        cf(verdict_col, "Platform Bug", (0.820, 0.980, 0.898), (0.024, 0.306, 0.271)),
        cf(verdict_col, "User Error",   (0.996, 0.953, 0.780), (0.475, 0.212, 0.000)),
        cf(verdict_col, "Borderline",   (0.859, 0.918, 0.996), (0.118, 0.227, 0.545)),
        cf(verdict_col, "Exclude",      (0.953, 0.957, 0.961), (0.216, 0.255, 0.318)),
    ]

    # Conditional formatting — approval_status
    ap_col = DR_HEADERS.index("approval_status")
    requests += [
        cf(ap_col, "approved", (0.820, 0.980, 0.898), (0.024, 0.306, 0.271)),
        cf(ap_col, "excluded", (0.953, 0.957, 0.961), (0.216, 0.255, 0.318)),
        cf(ap_col, "reviewed", (0.859, 0.918, 0.996), (0.118, 0.227, 0.545)),
        cf(ap_col, "new",      (0.996, 0.953, 0.780), (0.475, 0.212, 0.000)),
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()

    # Always overwrite header row with current DR_HEADERS
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{DAILY_REPORT_TAB}'!A1",
        valueInputOption="RAW",
        body={"values": [DR_HEADERS]},
    ).execute()
    print("  Header row written.")

    print(f"  Tab '{DAILY_REPORT_TAB}' formatted (29 columns, 5 zones).")


# ── Daily_Report_Summary tab setup ───────────────────────────────────────────

def setup_summary_tab(service, spreadsheet_id: str):
    sheet_id = get_or_create_tab(service, spreadsheet_id, DR_SUMMARY_TAB)
    existing = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{DR_SUMMARY_TAB}'!A1:S1",
    ).execute().get("values", [[]])
    if not existing or not existing[0]:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{DR_SUMMARY_TAB}'!A1",
            valueInputOption="RAW",
            body={"values": [DR_SUMMARY_HEADERS]},
        ).execute()
    # Freeze + bold header
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [
            {"updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }},
            {"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": len(DR_SUMMARY_HEADERS)},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.122, "green": 0.161, "blue": 0.216},
                    "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }},
        ]},
    ).execute()
    print(f"  Tab '{DR_SUMMARY_TAB}' ready.")


# ── Definitions tab setup ─────────────────────────────────────────────────────

def setup_definitions_tab(service, spreadsheet_id: str):
    sheet_id = get_or_create_tab(service, spreadsheet_id, DEFINITIONS_TAB)
    existing = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{DEFINITIONS_TAB}'!A1:B1",
    ).execute().get("values", [[]])
    if existing and existing[0] and existing[0][0] == "Term":
        print(f"  Tab '{DEFINITIONS_TAB}' already has content — skipping write.")
        return
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{DEFINITIONS_TAB}'!A1",
        valueInputOption="RAW",
        body={"values": [list(row) for row in DEFINITIONS]},
    ).execute()
    # Bold header row, set column widths
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [
            {"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95},
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }},
            {"updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 260}, "fields": "pixelSize",
            }},
            {"updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
                "properties": {"pixelSize": 560}, "fields": "pixelSize",
            }},
        ]},
    ).execute()
    print(f"  Tab '{DEFINITIONS_TAB}' written ({len(DEFINITIONS)} rows).")


# ── CSV data upsert ───────────────────────────────────────────────────────────

def upsert_csv_data(service, spreadsheet_id: str, csv_path: Path, date_str: str):
    """
    Safe upsert: never deletes rows whose approval_status='approved'.
    1. Read existing rows for this date.
    2. Collect locked source_ids (approval_status=approved).
    3. Delete non-locked rows for this date.
    4. Append new rows whose source_id is not locked.
    """
    # Load CSV
    new_rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            new_rows.append([row.get(h, "") for h in DR_HEADERS])

    if not new_rows:
        print("  No data rows in CSV.")
        return

    # Read existing sheet rows
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{DAILY_REPORT_TAB}'!A:AC",
    ).execute()
    existing = result.get("values", [])

    # Get sheetId for deleteDimension
    sheet_id = get_sheet_id_for_tab(service, spreadsheet_id, DAILY_REPORT_TAB)

    source_id_col  = DR_HEADERS.index("source_id")
    date_col       = DR_HEADERS.index("date")
    approval_col   = DR_HEADERS.index("approval_status")

    # Build map of existing rows for this date
    locked_ids   = set()
    rows_to_delete = []
    for i, row in enumerate(existing[1:], start=1):  # 0-based, skip header
        row_padded = row + [""] * (len(DR_HEADERS) - len(row))
        if row_padded[date_col] != date_str:
            continue
        sid    = row_padded[source_id_col]
        status = row_padded[approval_col]
        if status == "approved":
            locked_ids.add(sid)
        else:
            rows_to_delete.append(i)

    # Delete non-locked rows (reverse order so indices stay valid)
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
        print(f"  Deleted {len(rows_to_delete)} non-approved rows for {date_str}.")

    # Filter new rows — skip locked
    fresh_rows = [r for r in new_rows if r[source_id_col] not in locked_ids]
    skipped    = len(new_rows) - len(fresh_rows)
    if skipped:
        print(f"  Skipped {skipped} approved (locked) rows.")

    if not fresh_rows:
        print("  Nothing new to append.")
        return

    # Append after existing rows
    result2 = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"'{DAILY_REPORT_TAB}'!A:A",
    ).execute()
    next_row = len(result2.get("values", [])) + 1

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{DAILY_REPORT_TAB}'!A{next_row}",
        valueInputOption="RAW",
        body={"values": fresh_rows},
    ).execute()
    print(f"  Appended {len(fresh_rows)} rows starting at row {next_row}.")


# ── Main ──────────────────────────────────────────────────────────────────────

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
        date_str = csvs[-1].stem

    csv_path = ROOT / "daily-report" / f"{date_str}.csv"
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    print(f"Spreadsheet: {spreadsheet_id}")
    print(f"Date: {date_str}  CSV: {csv_path.name}")
    print()

    service = get_service()

    print("[1/4] Setting up Daily Report tab...")
    setup_daily_report_tab(service, spreadsheet_id)

    print("[2/4] Setting up Daily_Report_Summary tab...")
    setup_summary_tab(service, spreadsheet_id)

    print("[3/4] Setting up Definitions tab...")
    setup_definitions_tab(service, spreadsheet_id)

    print("[4/4] Upserting CSV data...")
    upsert_csv_data(service, spreadsheet_id, csv_path, date_str)

    print("\nDone.")


if __name__ == "__main__":
    main()
