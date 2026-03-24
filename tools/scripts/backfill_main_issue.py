"""
backfill_main_issue.py — Generate "Main Issue (VI)" for all Bug Ticket rows.

For every row that has Issue Summary (VI) or Issue Summary (EN) but an empty
col D (Main Issue), calls Claude Haiku to produce a single Vietnamese sentence
of <10 words that captures the core issue, then writes it to col D.

Usage:
    cd "d:/Cursor test/gmail-assistant"
    python tools/scripts/backfill_main_issue.py

Requires:
    ANTHROPIC_API_KEY environment variable (or a .env file in the project root)
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "api"))

import requests
from sheets_client import get_service, get_sheet_id, BUG_TAB

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COL_MAIN_ISSUE = 4   # D — Main Issue (VI)
COL_SUMMARY_VI = 6   # F — Issue Summary (VI)
COL_SUMMARY_EN = 10  # J — Issue Summary (EN)
COL_SUBJECT    = 12  # L — Subject
COL_TICKET_ID  = 2   # B — Ticket ID

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# ---------------------------------------------------------------------------
# Claude call
# ---------------------------------------------------------------------------


def generate_main_issue(api_key: str, summary_vi: str, summary_en: str, subject: str) -> str:
    """
    Call Claude Haiku and return a <10-word Vietnamese sentence summarising
    the core bug. Raises on API error.
    """
    source = summary_vi or summary_en or subject
    if not source:
        return ""

    prompt = (
        "Bạn là kỹ thuật viên QA. "
        "Dựa vào mô tả lỗi dưới đây, viết đúng 1 câu tiếng Việt, "
        "dưới 10 từ, tóm tắt vấn đề cốt lõi. "
        "Bắt đầu bằng chủ thể (ví dụ: Trang, Hệ thống, Nút, Câu hỏi, Màn hình…). "
        "Chỉ trả lời câu đó, không giải thích thêm.\n\n"
        f"Mô tả: {source}"
    )

    resp = requests.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 60,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    text = (body.get("content") or [{}])[0].get("text", "").strip()
    # Remove trailing period if any (consistent style)
    return text.rstrip(".")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        # Try reading from .env in project root
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not found.")
        print("  Set it as an environment variable or add it to .env")
        sys.exit(1)

    spreadsheet_id = get_sheet_id()
    if not spreadsheet_id:
        print("ERROR: No spreadsheet ID configured. Run setup_sheets.py first.")
        sys.exit(1)

    service = get_service()

    # Read all rows A:U
    print(f"Reading Bug Tickets sheet ({spreadsheet_id})…")
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{BUG_TAB}!A:Q",
    ).execute()
    rows = result.get("values", [])

    if len(rows) < 2:
        print("No data rows found.")
        return

    data_rows = rows[1:]   # skip header
    to_process = []

    for i, row in enumerate(data_rows, start=2):   # 1-based, start at row 2
        ticket_id  = row[COL_TICKET_ID  - 1] if len(row) >= COL_TICKET_ID  else ""
        if not ticket_id:
            continue

        main_issue = row[COL_MAIN_ISSUE - 1] if len(row) >= COL_MAIN_ISSUE else ""
        if main_issue:
            continue   # already filled

        summary_vi = row[COL_SUMMARY_VI - 1] if len(row) >= COL_SUMMARY_VI else ""
        summary_en = row[COL_SUMMARY_EN - 1] if len(row) >= COL_SUMMARY_EN else ""
        subject    = row[COL_SUBJECT    - 1] if len(row) >= COL_SUBJECT    else ""

        if not summary_vi and not summary_en and not subject:
            continue

        to_process.append({
            "sheet_row": i,
            "ticket_id": ticket_id,
            "summary_vi": summary_vi,
            "summary_en": summary_en,
            "subject": subject,
        })

    print(f"Found {len(to_process)} rows needing Main Issue (VI). Generating…\n")

    updates = []
    errors  = []

    for item in to_process:
        try:
            result_text = generate_main_issue(
                api_key,
                item["summary_vi"],
                item["summary_en"],
                item["subject"],
            )
            if result_text:
                updates.append({
                    "range": f"{BUG_TAB}!U{item['sheet_row']}",
                    "values": [[result_text]],
                })
                print(f"  [{item['ticket_id']}] {result_text}")
            else:
                print(f"  [{item['ticket_id']}] (empty response — skipped)")
        except Exception as e:
            errors.append(f"Row {item['sheet_row']} ({item['ticket_id']}): {e}")
            print(f"  [{item['ticket_id']}] ERROR: {e}")

        time.sleep(0.3)   # avoid rate limits

    # Batch write all updates
    if updates:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": updates},
        ).execute()
        print(f"\nWrote {len(updates)} Main Issue values to col U.")
    else:
        print("\nNothing to write.")

    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print(f"  {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
