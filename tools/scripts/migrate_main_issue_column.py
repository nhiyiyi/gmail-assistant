"""
migrate_main_issue_column.py — Move "Main Issue (VI)" from col U -> col F.

Before:  A B C D E  F  G H I J  K  L  M  N  O  P  Q  R  S  T  U
         ...     E(VI) Gmail Email Notes EN  Cust Subj Type Slack Draft Thread SentAt Scr InRep RepDate Att MainIssue

After:   A B C D E  F(MainIssue)  G  H  I  J   K    L    M    N     O     P       Q      R     S     T   U
         ...     E(VI) F(Main)   Gmail Email Notes EN Cust Subj Type Slack Draft Thread SentAt Scr InRep RepDate Att

Steps:
  1. Insert a blank column at F (index 5, 0-based) — shifts all cols F+ right by 1
  2. Set header F1 = "Main Issue (VI)"
  3. Copy existing Main Issue data from col V (old U, now shifted) to col F
  4. Clear col V
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "api"))

from sheets_client import get_service, get_sheet_id, BUG_TAB

COL_F_INDEX   = 5   # 0-based index of the new col F
COL_V_LETTER  = "V" # old col U (Main Issue) shifts to V after insertion


def get_sheet_tab_id(service, spreadsheet_id, tab_name):
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == tab_name:
            return props["sheetId"]
    return None


def main():
    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        print("ERROR: No spreadsheet ID configured.")
        sys.exit(1)

    service = get_service()
    sheet_id = get_sheet_tab_id(service, spreadsheet_id, BUG_TAB)
    if sheet_id is None:
        print(f"ERROR: Tab '{BUG_TAB}' not found.")
        sys.exit(1)

    print(f"Spreadsheet: {spreadsheet_id}")
    print(f"Tab '{BUG_TAB}' sheetId: {sheet_id}\n")

    # ── Step 1: Check if col F is already "Main Issue (VI)" ──
    f1_result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{BUG_TAB}!F1",
    ).execute().get("values", [[""]])
    f1 = f1_result[0][0] if f1_result and f1_result[0] else ""

    col_already_inserted = (f1 == "Main Issue (VI)")

    if not col_already_inserted:
        # ── Step 2: Insert a blank column at position F (index 5) ──
        print("[1] Inserting blank column at F...")
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{
                "insertDimension": {
                    "range": {
                        "sheetId":    sheet_id,
                        "dimension":  "COLUMNS",
                        "startIndex": COL_F_INDEX,       # 0-based: col F = 5
                        "endIndex":   COL_F_INDEX + 1,
                    },
                    "inheritFromBefore": False,
                }
            }]},
        ).execute()
        print("  Done — cols F+ shifted right by 1. Old col U is now col V.\n")

        # ── Step 3: Write header F1 ──
        print("[2] Writing header F1 = 'Main Issue (VI)'...")
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{BUG_TAB}!F1",
            valueInputOption="USER_ENTERED",
            body={"values": [["Main Issue (VI)"]]},
        ).execute()
        print("  Done.\n")
    else:
        print("[1+2] Column F already = 'Main Issue (VI)' — skipping insert and header steps.")

    # ── Step 4: Read existing Main Issue data from col V (was col U) ──
    print("[3] Reading existing Main Issue data from col V (old col U)…")
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{BUG_TAB}!{COL_V_LETTER}:{COL_V_LETTER}",
    ).execute()
    v_values = result.get("values", [])

    # Build updates: copy V row-by-row to F, skipping header row (row 1)
    updates = []
    for i, cell in enumerate(v_values):
        row_number = i + 1  # 1-based
        if row_number == 1:
            continue  # skip header row (V1 = old shifted U1 header)
        val = cell[0] if cell else ""
        if val:
            updates.append({
                "range": f"{BUG_TAB}!F{row_number}",
                "values": [[val]],
            })

    if updates:
        print(f"  Copying {len(updates)} Main Issue values from V -> F…")
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": updates},
        ).execute()
        print("  Done.\n")
    else:
        print("  Col V was empty — nothing to copy.\n")

    # ── Step 5: Clear col V ──
    print("[4] Clearing col V (old Main Issue position)…")
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=f"{BUG_TAB}!{COL_V_LETTER}:{COL_V_LETTER}",
    ).execute()
    print("  Done.\n")

    print("=" * 50)
    print("Migration complete!")
    print("  F = Main Issue (VI)   (new, next to Issue Summary VI)")
    print("  G = Gmail Link        (was F)")
    print("  H = Email Address     (was G)")
    print("  I = Notes             (was H)")
    print("  J = Issue Summary EN  (was I)")
    print("  K = Customer Name     (was J)")
    print("  L = Subject           (was K)")
    print("  M = Issue Type        (was L)")
    print("  N = Slack Message     (was M)")
    print("  O = Draft ID          (was N)")
    print("  P = Thread ID         (was O)")
    print("  Q = Sent At           (was P)")
    print("  R = Screenshot URL    (was Q)")
    print("  S = In Report         (was R)")
    print("  T = Report Date       (was S)")
    print("  U = Attachment URL    (was T)")


if __name__ == "__main__":
    main()
