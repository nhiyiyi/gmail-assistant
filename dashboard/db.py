"""
dashboard/db.py — Local SQLite store for Daily Review entries.

DB file: dashboard/daily_review.db  (created automatically)

Tables:
  daily_entries  — one row per candidate submission (29-col DR schema)
  report_config  — one row per date (total_completed, total_started, dm_sent_at)
"""

from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "daily_review.db"

DR_COLUMNS = [
    "source_id", "date", "time_gmt7", "source", "ticket_id", "source_link",
    "screenshot_url", "original_content", "email", "candidate_name",
    "topic_raw", "stage", "category", "interview_position", "interview_company",
    "submission_id", "browser", "os", "device",
    "assessment", "confidence", "assessment_notes",
    "human_verdict", "human_notes", "include_in_report", "report_bucket",
    "approval_status", "reviewed_by", "reviewed_at", "component", "thread_link",
]


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """Create tables if they don't exist."""
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS daily_entries (
                source_id          TEXT PRIMARY KEY,
                date               TEXT,
                time_gmt7          TEXT,
                source             TEXT,
                ticket_id          TEXT,
                source_link        TEXT,
                screenshot_url     TEXT,
                original_content   TEXT,
                email              TEXT,
                candidate_name     TEXT,
                topic_raw          TEXT,
                stage              TEXT,
                category           TEXT,
                interview_position TEXT,
                interview_company  TEXT,
                submission_id      TEXT,
                browser            TEXT,
                os                 TEXT,
                device             TEXT,
                assessment         TEXT,
                confidence         TEXT,
                assessment_notes   TEXT,
                human_verdict      TEXT DEFAULT '',
                human_notes        TEXT DEFAULT '',
                include_in_report  TEXT DEFAULT 'Yes',
                report_bucket      TEXT DEFAULT '',
                approval_status    TEXT DEFAULT 'new',
                reviewed_by        TEXT DEFAULT '',
                reviewed_at        TEXT DEFAULT '',
                component          TEXT DEFAULT '',
                thread_link        TEXT DEFAULT ''
            )
        """)
        # Migrate: add new columns if they don't exist (existing DBs)
        for col_def in [
            "component TEXT DEFAULT ''",
            "thread_link TEXT DEFAULT ''",
        ]:
            try:
                con.execute(f"ALTER TABLE daily_entries ADD COLUMN {col_def}")
            except Exception:
                pass  # Column already exists

        con.execute("""
            CREATE TABLE IF NOT EXISTS report_config (
                date               TEXT PRIMARY KEY,
                total_completed    INTEGER DEFAULT 0,
                total_started      INTEGER DEFAULT 0,
                dm_sent_at         TEXT DEFAULT ''
            )
        """)


def upsert_rows(rows: list[dict]) -> dict:
    """
    Safe idempotent upsert.
    - Rows whose source_id already has approval_status='approved' are NEVER overwritten.
    - All other rows for the affected dates are replaced with the fresh data.
    Returns {appended, skipped}.
    """
    if not rows:
        return {"appended": 0, "skipped": 0}

    with _conn() as con:
        # Find locked source_ids (approved rows for affected dates)
        dates = {r.get("date", "") for r in rows if r.get("date")}
        locked: set[str] = set()
        for date in dates:
            cur = con.execute(
                "SELECT source_id FROM daily_entries WHERE date=? AND approval_status='approved'",
                (date,)
            )
            for row in cur.fetchall():
                locked.add(row["source_id"])

            # Delete non-approved rows for this date so we can re-insert fresh data
            con.execute(
                "DELETE FROM daily_entries WHERE date=? AND approval_status != 'approved'",
                (date,)
            )

        appended = 0
        skipped = 0
        for r in rows:
            sid = str(r.get("source_id") or "")
            if not sid or sid in locked:
                skipped += 1
                continue
            vals = [str(r.get(col) or "") for col in DR_COLUMNS]
            # Ensure approval_status default
            approval_idx = DR_COLUMNS.index("approval_status")
            if not vals[approval_idx]:
                vals[approval_idx] = "new"
            placeholders = ", ".join(["?"] * len(DR_COLUMNS))
            cols_sql = ", ".join(DR_COLUMNS)
            con.execute(
                f"INSERT OR REPLACE INTO daily_entries ({cols_sql}) VALUES ({placeholders})",
                vals,
            )
            appended += 1

    return {"appended": appended, "skipped": skipped}


def get_entries(date: str) -> list[dict]:
    """Return all rows for a date, sorted by time_gmt7."""
    with _conn() as con:
        cur = con.execute(
            "SELECT * FROM daily_entries WHERE date=? ORDER BY time_gmt7, source_id",
            (date,)
        )
        return [dict(row) for row in cur.fetchall()]


def update_approval(source_id: str, status: str, reviewer: str = "") -> dict:
    """Set approval_status (and reviewed_at) for one entry."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as con:
        con.execute(
            "UPDATE daily_entries SET approval_status=?, reviewed_by=?, reviewed_at=? WHERE source_id=?",
            (status, reviewer, now, source_id),
        )
    return {"ok": True, "reviewedAt": now}


def mark_all_approved(date: str, reviewer: str = "") -> dict:
    """Approve all non-excluded pending rows for a date."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with _conn() as con:
        cur = con.execute(
            """UPDATE daily_entries
               SET approval_status='approved', reviewed_by=?, reviewed_at=?
               WHERE date=? AND approval_status NOT IN ('approved', 'excluded')""",
            (reviewer, now, date),
        )
        approved = cur.rowcount
    return {"ok": True, "approved": approved}


def get_stats(date: str) -> dict:
    """Return approval counts for a date."""
    with _conn() as con:
        cur = con.execute(
            """SELECT approval_status, COUNT(*) as cnt
               FROM daily_entries WHERE date=?
               GROUP BY approval_status""",
            (date,)
        )
        counts: dict[str, int] = {}
        for row in cur.fetchall():
            counts[row["approval_status"]] = row["cnt"]
    total    = sum(counts.values())
    approved = counts.get("approved", 0)
    excluded = counts.get("excluded", 0)
    pending  = total - approved - excluded
    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "excluded": excluded,
        "complete": total > 0 and pending == 0 and approved > 0,
    }


def get_summary(date: str) -> dict:
    """
    Aggregate counts from approved+included rows for the Slack report.
    Returns stage totals, per-stage category breakdowns, verdict totals, source totals.
    """
    with _conn() as con:
        cur = con.execute(
            """SELECT stage, category, assessment, source
               FROM daily_entries
               WHERE date=?
                 AND approval_status='approved'
                 AND include_in_report != 'No'
                 AND LOWER(stage) != 'excluded'""",
            (date,)
        )
        rows = cur.fetchall()

    stage_counts: dict[str, int] = {}
    stage_categories: dict[str, dict[str, int]] = {}
    verdict_counts: dict[str, int] = {"platform_bug": 0, "user_error": 0, "borderline": 0}
    source_counts: dict[str, int] = {"slack": 0, "email": 0}

    for row in rows:
        stage    = (row["stage"]    or "").strip()
        category = (row["category"] or "").strip()
        assess   = (row["assessment"] or "").lower()
        source   = (row["source"]   or "").lower()

        # Stage bucket
        if "stage 1" in stage.lower():
            bucket = "stage1"
        elif "stage 2" in stage.lower():
            bucket = "stage2"
        elif "stage 3" in stage.lower():
            bucket = "stage3"
        elif "company" in stage.lower():
            bucket = "other_company"
        elif "candidate" in stage.lower():
            bucket = "other_candidate"
        else:
            bucket = "other"

        stage_counts[bucket] = stage_counts.get(bucket, 0) + 1

        # Per-stage category breakdown
        if category:
            if bucket not in stage_categories:
                stage_categories[bucket] = {}
            stage_categories[bucket][category] = stage_categories[bucket].get(category, 0) + 1

        # Verdict
        if "platform bug" in assess:
            verdict_counts["platform_bug"] += 1
        elif "user error" in assess:
            verdict_counts["user_error"] += 1
        elif "borderline" in assess:
            verdict_counts["borderline"] += 1

        # Source
        if "slack" in source:
            source_counts["slack"] += 1
        else:
            source_counts["email"] += 1

    total_included = len(rows)
    total_excluded = 0
    with _conn() as con:
        cur = con.execute(
            "SELECT COUNT(*) as cnt FROM daily_entries WHERE date=? AND (approval_status='excluded' OR LOWER(stage)='excluded')",
            (date,)
        )
        total_excluded = cur.fetchone()["cnt"]

    return {
        "date":           date,
        "total_included": total_included,
        "total_excluded": total_excluded,
        "stage1":         stage_counts.get("stage1", 0),
        "stage2":         stage_counts.get("stage2", 0),
        "stage3":         stage_counts.get("stage3", 0),
        "other_company":  stage_counts.get("other_company", 0),
        "other_candidate":stage_counts.get("other_candidate", 0),
        "stage_categories": stage_categories,
        "total_platform_bug": verdict_counts["platform_bug"],
        "total_user_error":   verdict_counts["user_error"],
        "total_borderline":   verdict_counts["borderline"],
        "total_slack":        source_counts["slack"],
        "total_email_bugs":   source_counts["email"],
    }


def get_config(date: str) -> dict:
    """Read report config for a date."""
    with _conn() as con:
        cur = con.execute("SELECT * FROM report_config WHERE date=?", (date,))
        row = cur.fetchone()
    if row:
        return dict(row)
    return {"date": date, "total_completed": 0, "total_started": 0, "dm_sent_at": ""}


def set_config(date: str, total_completed: int = 0, total_started: int = 0) -> dict:
    """Upsert report config for a date."""
    with _conn() as con:
        con.execute(
            """INSERT INTO report_config (date, total_completed, total_started)
               VALUES (?, ?, ?)
               ON CONFLICT(date) DO UPDATE SET
                 total_completed = excluded.total_completed,
                 total_started   = excluded.total_started""",
            (date, total_completed, total_started),
        )
    return {"ok": True}


def build_report_text(date: str, total_completed: int = 0, total_started: int = 0) -> str:
    """Build the Slack DM report text from approved data."""
    s = get_summary(date)

    # Format display date: "Mar 25"
    parts = date.split("-")
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    try:
        fmt_date = months[int(parts[1]) - 1] + " " + str(int(parts[2]))
    except (IndexError, ValueError):
        fmt_date = date

    total_included = s["total_included"]
    lines: list[str] = [
        f":large_yellow_square: Reporting Period: {fmt_date} (00:00) \u2013 {fmt_date} (11:59 PM) (1 day) @JunYuan Tan (JY)",
    ]

    if total_completed:
        pct = f"{total_included / total_completed * 100:.2f}"
        lines.append(
            f"Total Issues Reported: {total_included} out of {total_completed} "
            f"( [Total Completed including Internal ones] ({pct}%) )"
        )
    if total_started:
        pct = f"{total_included / total_started * 100:.2f}"
        lines.append(
            f"Total Issues Reported: {total_included} out of {total_started} "
            f"( [Total Started by Unique Emails (Include Completed, Not Completed, and "
            f"Submissions never go to Interview step) including Internal ones] ({pct}%) )"
        )
    if not total_completed and not total_started:
        lines.append(f"Total Issues Reported: {total_included}")

    cats = s.get("stage_categories", {})

    def stage_block(label: str, bucket: str, count: int) -> list[str]:
        block = [f"{label} ({count})"]
        cat_map = cats.get(bucket, {})
        for cat, cnt in sorted(cat_map.items(), key=lambda x: -x[1]):
            block.append(f"  {cat}: {cnt}")
        return block

    lines += stage_block("Stage 1: Before the Interview", "stage1", s["stage1"])
    lines += stage_block("Stage 2: During the Interview", "stage2", s["stage2"])
    lines += stage_block("Stage 3: After the Interview",  "stage3", s["stage3"])
    lines.append(f"Other (Company) ({s['other_company']})")
    lines.append(f"Other (Candidate) ({s['other_candidate']})")
    lines.append("")
    lines.append(
        f"Platform Bug: {s['total_platform_bug']} | "
        f"User Error: {s['total_user_error']} | "
        f"Borderline: {s['total_borderline']}"
    )
    lines.append(
        f"Slack submissions: {s['total_slack']} | "
        f"Email tickets: {s['total_email_bugs']}"
    )

    return "\n".join(lines)


def patch_entry(source_id: str, fields: dict) -> dict:
    """Update stage, human_verdict, or human_notes without changing approval_status."""
    allowed = {"stage", "human_verdict", "human_notes"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return {"ok": True}
    sets["reviewed_by"] = "user"
    cols = ", ".join(f"{k}=?" for k in sets)
    with _conn() as con:
        con.execute(
            f"UPDATE daily_entries SET {cols} WHERE source_id=?",
            [*sets.values(), source_id],
        )
    return {"ok": True}


# Auto-init on import
init_db()
