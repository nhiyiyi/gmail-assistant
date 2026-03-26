#!/usr/bin/env python3
"""
dashboard/load_csv.py — Import a daily-report CSV into the local SQLite DB.

Usage:
    python dashboard/load_csv.py daily-report/2026-03-25.csv
    python dashboard/load_csv.py               # auto-loads yesterday's CSV

The CSV uses the 22-column format written by the daily-report skill.
Missing fields (source_id, source_link) are generated automatically.
"""

import csv
import sys
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

# Allow importing db.py from this directory
sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402

# Map CSV column names → SQLite column names (where they differ)
CSV_ALIASES = {
    "interview_position": "interview_position",
    "interview_company":  "interview_company",
}


def make_source_id(row: dict) -> str:
    """Generate a stable source_id from ticket_id or email+date+time."""
    tid = (row.get("ticket_id") or "").strip()
    if tid:
        src = (row.get("source") or "SHEET").upper()
        return f"{src}-{tid}"
    # Fallback: hash of email + date + time
    key = f"{row.get('email','')}-{row.get('date','')}-{row.get('time_gmt7','')}".encode()
    return "HASH-" + hashlib.md5(key).hexdigest()[:12]


def load_csv(csv_path: Path) -> dict:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            row = {k: (v or "") for k, v in raw.items()}

            # Normalize column names
            for alias, real in CSV_ALIASES.items():
                if alias in row and real not in row:
                    row[real] = row.pop(alias)

            # Generate source_id if missing
            if not row.get("source_id"):
                row["source_id"] = make_source_id(row)

            # Fill optional fields that may be absent in older CSVs
            row.setdefault("source_link", "")
            row.setdefault("topic_raw",   "")
            row.setdefault("submission_id", "")

            rows.append(row)

    if not rows:
        return {"appended": 0, "skipped": 0, "note": "CSV is empty"}

    result = db.upsert_rows(rows)
    result["file"] = str(csv_path)
    result["date"] = rows[0].get("date", "?") if rows else "?"
    return result


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        # Auto-detect yesterday's CSV
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        root = Path(__file__).parent.parent
        path = root / "daily-report" / f"{yesterday}.csv"

    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    result = load_csv(path)
    print(f"Loaded {path.name}: {result['appended']} appended, {result['skipped']} skipped (approved rows protected)")
    print(f"Open http://localhost:5000/daily?date={result.get('date','')}")


if __name__ == "__main__":
    main()
