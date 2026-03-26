"""
dashboard/server.py — Local Flask server for BugDashboard.html

Serves BugDashboard.html at http://localhost:5000/
Exposes POST /api/<function_name> endpoints matching the Google Apps Script API.

Usage:
    python dashboard/server.py
    # then open http://localhost:5000 in your browser
"""

from __future__ import annotations
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory

# Resolve paths
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src" / "api"))

import sheets_client as sc  # noqa: E402
import db  # noqa: E402  (dashboard/db.py)

app = Flask(__name__)

# ── CORS headers (allow browser to call from any origin just in case) ─────────
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
    return response

@app.route("/", methods=["OPTIONS"])
@app.route("/api/<path:path>", methods=["OPTIONS"])
def options_handler(**kwargs):
    return "", 204


# ── Static: serve the dashboard HTML ─────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(str(ROOT_DIR), "BugDashboard.html")

@app.route("/daily")
def daily():
    return send_from_directory(str(Path(__file__).parent), "daily.html")

# ── Daily Review REST endpoints (SQLite-backed) ───────────────────────────────

@app.route("/api/dr/import", methods=["POST"])
def dr_import():
    """Import CSV rows into local SQLite. Body: {date, rows: [...]}"""
    body = request.get_json(silent=True) or {}
    rows = body.get("rows", [])
    if not rows:
        return jsonify({"error": "rows is required"}), 400
    result = db.upsert_rows(rows)
    return jsonify(result)


@app.route("/api/dr/entries", methods=["GET"])
def dr_entries():
    """Fetch all entries + stats for a date. Query: ?date=YYYY-MM-DD"""
    date = request.args.get("date", "")
    if not date:
        return jsonify({"error": "date query param required"}), 400
    entries = db.get_entries(date)
    stats   = db.get_stats(date)
    return jsonify({"entries": entries, "stats": stats})


@app.route("/api/dr/approve", methods=["POST"])
def dr_approve():
    """Approve one entry. Body: {source_id, reviewer?}"""
    body     = request.get_json(silent=True) or {}
    source_id = body.get("source_id", "")
    reviewer  = body.get("reviewer", "")
    if not source_id:
        return jsonify({"error": "source_id required"}), 400
    return jsonify(db.update_approval(source_id, "approved", reviewer))


@app.route("/api/dr/exclude", methods=["POST"])
def dr_exclude():
    """Exclude one entry. Body: {source_id, reviewer?}"""
    body     = request.get_json(silent=True) or {}
    source_id = body.get("source_id", "")
    reviewer  = body.get("reviewer", "")
    if not source_id:
        return jsonify({"error": "source_id required"}), 400
    return jsonify(db.update_approval(source_id, "excluded", reviewer))


@app.route("/api/dr/unapprove", methods=["POST"])
def dr_unapprove():
    """Reset an entry back to 'new'. Body: {source_id}"""
    body     = request.get_json(silent=True) or {}
    source_id = body.get("source_id", "")
    if not source_id:
        return jsonify({"error": "source_id required"}), 400
    return jsonify(db.update_approval(source_id, "new"))


@app.route("/api/dr/bulk-approve", methods=["POST"])
def dr_bulk_approve():
    """Approve all pending entries for a date. Body: {date, reviewer?}"""
    body     = request.get_json(silent=True) or {}
    date     = body.get("date", "")
    reviewer = body.get("reviewer", "")
    if not date:
        return jsonify({"error": "date required"}), 400
    return jsonify(db.mark_all_approved(date, reviewer))


@app.route("/api/dr/report", methods=["POST"])
def dr_report():
    """
    Build the Slack report text.
    Body: {date, total_completed: int, total_started: int}
    Returns {message: "...", stats: {...}}
    """
    body            = request.get_json(silent=True) or {}
    date            = body.get("date", "")
    total_completed = int(body.get("total_completed") or 0)
    total_started   = int(body.get("total_started")   or 0)
    if not date:
        return jsonify({"error": "date required"}), 400

    # Save the config values for later reference
    db.set_config(date, total_completed, total_started)

    message = db.build_report_text(date, total_completed, total_started)
    stats   = db.get_stats(date)
    summary = db.get_summary(date)
    return jsonify({"message": message, "stats": stats, "summary": summary})


@app.route("/api/dr/entry", methods=["PATCH"])
def dr_patch_entry():
    """Update stage, human_verdict, or human_notes. Body: {source_id, stage?, human_verdict?, human_notes?}"""
    body      = request.get_json(silent=True) or {}
    source_id = body.get("source_id", "")
    if not source_id:
        return jsonify({"error": "source_id required"}), 400
    fields = {k: body[k] for k in ("stage", "human_verdict", "human_notes") if k in body}
    return jsonify(db.patch_entry(source_id, fields))


@app.route("/api/dr/config", methods=["POST"])
def dr_config():
    """Save total_completed / total_started. Body: {date, total_completed, total_started}"""
    body            = request.get_json(silent=True) or {}
    date            = body.get("date", "")
    total_completed = int(body.get("total_completed") or 0)
    total_started   = int(body.get("total_started")   or 0)
    if not date:
        return jsonify({"error": "date required"}), 400
    return jsonify(db.set_config(date, total_completed, total_started))

@app.route("/daily/v1")
def daily_v1():
    return send_from_directory(str(Path(__file__).parent), "daily-v1.html")

@app.route("/daily/v2")
def daily_v2():
    return send_from_directory(str(Path(__file__).parent), "daily-v2.html")

@app.route("/daily/v3")
def daily_v3():
    return send_from_directory(str(Path(__file__).parent), "daily-v3.html")

@app.route("/daily/v4")
def daily_v4():
    return send_from_directory(str(Path(__file__).parent), "daily-v4.html")


# ── API dispatcher ────────────────────────────────────────────────────────────
@app.route("/api/<function_name>", methods=["POST"])
def api_call(function_name):
    body = request.get_json(silent=True) or {}
    args = body.get("args", [])
    try:
        result = _dispatch(function_name, args)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _dispatch(fn: str, args: list):
    handlers = {
        "getInitialData":            lambda a: _get_initial_data(a[0] if a else {}),
        "updateBugField":            lambda a: _update_bug_field(a[0], a[1], a[2]),
        "getDailyReport":            lambda a: _get_daily_report(a[0] if a else ""),
        "updateDailyReportApproval": lambda a: _update_dr_approval(a[0], a[1], a[2] if len(a) > 2 else ""),
        "updateDailyReportRow":      lambda a: _update_dr_row(a[0], a[1], a[2] if len(a) > 2 else "", a[3] if len(a) > 3 else ""),
        "markAllApproved":           lambda a: _mark_all_approved(a[0] if a else ""),
        "checkDailyReportComplete":  lambda a: sc.check_report_complete(a[0] if a else ""),
        "sendReportDm":              lambda a: _send_report_dm(a[0] if a else ""),
        # These require Apps Script (Gmail + Drive or Claude integration)
        "backfillScreenshots":       lambda a: {"processed": 0, "skipped": 0, "errors": ["Requires Apps Script (Gmail+Drive access)."]},
        "backfillMainIssues":        lambda a: {"processed": 0, "skipped": 0, "errors": ["Requires Apps Script (Claude integration)."]},
        "generateMainIssueVi":       lambda a: {"error": "Requires Apps Script (Claude integration)."},
    }
    if fn not in handlers:
        return {"error": f"Unknown function: {fn}"}
    return handlers[fn](args)


# ── getInitialData ────────────────────────────────────────────────────────────

def _get_initial_data(filters: dict) -> dict:
    bugs_result = _get_bugs(filters)
    return {
        "bugs":      bugs_result["bugs"],
        "counters":  bugs_result["counters"],
        "total":     bugs_result["total"],
        "config":    _get_config(),
        "reporters": _get_reporter_emails(),
    }


def _get_bugs(filters: dict) -> dict:
    filters = filters or {}
    spreadsheet_id = sc.get_sheet_id()
    if not spreadsheet_id:
        return {"bugs": [], "counters": _zero_counts(), "total": 0,
                "error": "Sheet not configured. Run tools/scripts/setup_sheets.py first."}

    try:
        service = sc.get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sc.BUG_TAB}'!A:U",
        ).execute()
        rows = result.get("values", [])
    except Exception as exc:
        return {"bugs": [], "counters": _zero_counts(), "total": 0, "error": str(exc)}

    if len(rows) <= 1:
        return {"bugs": [], "counters": _zero_counts(), "total": 0}

    from_date, to_date = _date_bounds(filters)
    bugs = []

    for i, row in enumerate(rows[1:], start=2):   # i = 1-based sheet row
        row = row + [""] * (21 - len(row))          # pad to 21 cols

        # Skip completely empty rows
        if not row[1] and not row[11]:
            continue

        # ── Date filter ──────────────────────────────────────────────────────
        row_date = _fmt_date(row[0])
        if from_date and row_date < from_date:
            continue
        if to_date and row_date > to_date:
            continue

        # ── Exact-match filters ──────────────────────────────────────────────
        if filters.get("email")    and row[7]  != filters["email"]:    continue
        if filters.get("feature")  and row[12] != filters["feature"]:  continue
        if filters.get("status")   and row[2]  != filters["status"]:   continue
        if filters.get("priority") and row[4]  != filters["priority"]: continue

        # ── Keyword filter ───────────────────────────────────────────────────
        kw = (filters.get("keyword") or "").lower().strip()
        if kw and not _row_matches_keyword(row, kw):
            continue

        # ── Report-queue filter ──────────────────────────────────────────────
        in_report = row[18]   # col S (0-based index 18)
        included = in_report != "No"
        rq = filters.get("reportQueue", "all")
        if rq == "included" and not included:  continue
        if rq == "excluded" and     included:  continue

        bugs.append(_row_to_bug(row, i))

    bugs.sort(key=lambda b: b.get("date", ""), reverse=True)
    return {"bugs": bugs, "counters": _build_counters(bugs), "total": len(bugs)}


def _row_to_bug(row: list, row_number: int) -> dict:
    thread_id = row[15]
    gmail_url = row[6] or (f"https://mail.google.com/mail/u/0/#all/{thread_id}" if thread_id else "")
    in_report = row[18]
    return {
        "rowNumber":  row_number,
        "ticketId":   row[1],
        "date":       _fmt_date(row[0]),
        "status":     row[2],
        "mainIssue":  row[3],
        "priority":   row[4],
        "summaryVi":  row[5],
        "gmailUrl":   gmail_url,
        "email":      row[7],
        "notes":      row[8],
        "summaryEn":  row[9],
        "customer":   row[10],
        "subject":    row[11],
        "issueType":  row[12],
        "threadId":   thread_id,
        "sentAt":     _fmt_date(row[16]),
        "screenshot": row[17],
        "inReport":   "No" if in_report == "No" else "Yes",
        "reportDate": _fmt_date(row[19]),
        "attachment": row[20],
    }


def _row_matches_keyword(row: list, kw: str) -> bool:
    fields = [row[1], row[11], row[9], row[5], row[3], row[10],
              row[7], row[12], row[8], row[2], row[4], row[15], _fmt_date(row[0])]
    return any(kw in str(f).lower() for f in fields)


def _date_bounds(filters: dict) -> tuple[str, str]:
    r = filters.get("dateRange", "today")
    today     = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    last7     = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    if r == "yesterday": return yesterday, yesterday
    if r == "last7":     return last7, today
    if r == "custom":    return filters.get("dateFrom", ""), filters.get("dateTo", "")
    if r == "all":       return "", ""
    return today, today   # default: today


def _zero_counts() -> dict:
    return {"total": 0, "inQueue": 0, "open": 0, "inProgress": 0, "fixed": 0, "closed": 0}


def _build_counters(bugs: list) -> dict:
    return {
        "total":      len(bugs),
        "inQueue":    sum(1 for b in bugs if b["inReport"] != "No"),
        "open":       sum(1 for b in bugs if b["status"] == "Reported"),
        "inProgress": sum(1 for b in bugs if b["status"] in ("Verified", "Fix in Progress")),
        "fixed":      sum(1 for b in bugs if b["status"] == "Resolved"),
        "closed":     sum(1 for b in bugs if b["status"] in ("Duplicate", "Won't Fix")),
    }


# ── updateBugField ────────────────────────────────────────────────────────────

_BUG_FIELD_COL = {
    "status":     3,   # C
    "mainIssue":  4,   # D
    "priority":   5,   # E
    "notes":      9,   # I
    "screenshot": 18,  # R
    "inReport":   19,  # S
    "attachment": 21,  # U
}

def _update_bug_field(row_number: int, field: str, value: str) -> dict:
    if field not in _BUG_FIELD_COL:
        return {"error": f"Unknown field: {field}"}
    spreadsheet_id = sc.get_sheet_id()
    if not spreadsheet_id:
        return {"error": "Sheet not configured"}
    col = _col_letter(_BUG_FIELD_COL[field])
    try:
        service = sc.get_service()
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{sc.BUG_TAB}'!{col}{row_number}",
            valueInputOption="RAW",
            body={"values": [[value]]},
        ).execute()
        return {"ok": True}
    except Exception as exc:
        return {"error": str(exc)}


# ── Config ────────────────────────────────────────────────────────────────────

def _get_config() -> dict:
    spreadsheet_id = sc.get_sheet_id()
    if not spreadsheet_id:
        return _default_config()
    try:
        service = sc.get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sc.CONFIG_TAB}'!A:B",
        ).execute()
        cfg: dict[str, list] = {}
        for row in result.get("values", []):
            cat = str(row[0]).strip().lower() if row else ""
            val = str(row[1]).strip() if len(row) > 1 else ""
            if cat and val:
                cfg.setdefault(cat, []).append(val)
        return {
            "statuses":   cfg.get("statuses",   _default_statuses()),
            "priorities": cfg.get("priorities", ["High", "Medium", "Low"]),
            "features":   cfg.get("features",   []),
        }
    except Exception:
        return _default_config()


def _default_config() -> dict:
    return {"statuses": _default_statuses(), "priorities": ["High", "Medium", "Low"], "features": []}


def _default_statuses() -> list:
    return ["Reported", "Verified", "Fix in Progress", "Resolved", "Duplicate", "Won't Fix"]


# ── Reporter emails ───────────────────────────────────────────────────────────

def _get_reporter_emails() -> list:
    spreadsheet_id = sc.get_sheet_id()
    if not spreadsheet_id:
        return []
    try:
        service = sc.get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sc.BUG_TAB}'!H:H",
        ).execute()
        seen: set[str] = set()
        for row in result.get("values", [])[1:]:   # skip header
            email = str(row[0]).strip() if row else ""
            if email:
                seen.add(email)
        return sorted(seen)
    except Exception:
        return []


# ── getDailyReport ────────────────────────────────────────────────────────────

def _snake_to_camel(s: str) -> str:
    special = {"interview_position": "interviewPos", "interview_company": "interviewCo"}
    if s in special:
        return special[s]
    return re.sub(r"_([a-z0-9])", lambda m: m.group(1).upper(), s)


def _get_daily_report(date_str: str) -> dict:
    rows = sc.get_daily_report_rows(date_str)
    if rows and "error" in rows[0]:
        return {"error": rows[0]["error"], "entries": [], "total": 0, "reviewed": 0}
    entries = []
    for r in rows:
        entry = {_snake_to_camel(k): v for k, v in r.items() if k != "_row"}
        entry["rowNumber"] = r.get("_row", 0)
        entries.append(entry)
    reviewed = sum(1 for e in entries if e.get("humanVerdict"))
    return {"entries": entries, "total": len(entries), "reviewed": reviewed}


# ── updateDailyReportApproval ─────────────────────────────────────────────────

def _update_dr_approval(row_number: int, status: str, reviewer: str) -> dict:
    spreadsheet_id = sc.get_sheet_id()
    if not spreadsheet_id:
        return {"error": "Sheet not configured"}
    try:
        service = sc.get_service()
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        updates = [
            {"range": f"'{sc.DAILY_REPORT_TAB}'!AA{row_number}", "values": [[status or "reviewed"]]},
            {"range": f"'{sc.DAILY_REPORT_TAB}'!AB{row_number}", "values": [[reviewer or ""]]},
            {"range": f"'{sc.DAILY_REPORT_TAB}'!AC{row_number}", "values": [[now]]},
        ]
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()
        return {"ok": True, "reviewedAt": now}
    except Exception as exc:
        return {"error": str(exc)}


# ── updateDailyReportRow ──────────────────────────────────────────────────────

def _update_dr_row(row_number: int, stage: str, category: str, notes: str) -> dict:
    spreadsheet_id = sc.get_sheet_id()
    if not spreadsheet_id:
        return {"error": "Sheet not configured"}
    try:
        service = sc.get_service()
        # DR: stage=L(12), category=M(13), human_notes=X(24)
        updates = [
            {"range": f"'{sc.DAILY_REPORT_TAB}'!L{row_number}", "values": [[stage    or ""]]},
            {"range": f"'{sc.DAILY_REPORT_TAB}'!M{row_number}", "values": [[category or ""]]},
            {"range": f"'{sc.DAILY_REPORT_TAB}'!X{row_number}", "values": [[notes    or ""]]},
        ]
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()
        return {"ok": True}
    except Exception as exc:
        return {"error": str(exc)}


# ── markAllApproved ───────────────────────────────────────────────────────────

def _mark_all_approved(date_str: str) -> dict:
    spreadsheet_id = sc.get_sheet_id()
    if not spreadsheet_id:
        return {"error": "Sheet not configured"}
    rows = sc.get_daily_report_rows(date_str)
    if rows and "error" in rows[0]:
        return rows[0]
    try:
        service = sc.get_service()
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        updates = []
        approved_count = 0
        for r in rows:
            row_num = r.get("_row", 0)
            if not row_num or r.get("approval_status") == "approved":
                continue
            updates.append({"range": f"'{sc.DAILY_REPORT_TAB}'!AA{row_num}", "values": [["approved"]]})
            updates.append({"range": f"'{sc.DAILY_REPORT_TAB}'!AC{row_num}", "values": [[now]]})
            approved_count += 1
        if updates:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "RAW", "data": updates},
            ).execute()
        return {"ok": True, "approved": approved_count}
    except Exception as exc:
        return {"error": str(exc)}


# ── sendReportDm ──────────────────────────────────────────────────────────────

def _send_report_dm(date_str: str) -> dict:
    if not date_str:
        return {"error": "date is required"}

    # Idempotency check
    already_sent_at = _get_config_value(f"dm_sent_at:{date_str}")
    if already_sent_at:
        return {"already_sent": True, "dm_sent_at": already_sent_at}

    # Completion check
    completion = sc.check_report_complete(date_str)
    if completion.get("error"):
        return completion
    if not completion.get("complete"):
        pending = completion.get("pending", 0)
        total = completion.get("total", 0)
        return {"error": f"Report is not complete: {pending} pending of {total} total"}

    # Build DM text from aggregated summary
    s = sc.get_daily_summary(date_str)
    cfg = sc.get_report_config(date_str)
    total_completed = cfg.get("total_completed") or 0
    total_started   = cfg.get("total_started")   or 0
    total_included  = s.get("total_included", 0)

    # Format date display: "Mar 25"
    parts = date_str.split("-")
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    fmt_date = months[int(parts[1]) - 1] + " " + str(int(parts[2]))

    lines = [
        f":large_yellow_square: Reporting Period: {fmt_date} (00:00) – {fmt_date} (11:59 PM) (1 day) @JunYuan Tan (JY)",
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
            f"( [Total Started by Unique Emails (Include Completed, Not Completed, and Submissions never go to Interview step) including Internal ones] ({pct}%) )"
        )
    if not total_completed and not total_started:
        lines.append(f"Total Issues Reported: {total_included}")

    lines += [
        f"Stage 1: Before the Interview ({s.get('stage1', 0)})",
        f"Stage 2: During the Interview ({s.get('stage2', 0)})",
        f"Stage 3: After the Interview ({s.get('stage3', 0)})",
        f"Other (Company) ({s.get('other_company', 0)})",
        f"Other (Candidate) ({s.get('other_candidate', 0)})",
        "",
        f"Platform Bug: {s.get('total_platform_bug', 0)} | User Error: {s.get('total_user_error', 0)} | Borderline: {s.get('total_borderline', 0)}",
        f"Slack submissions: {s.get('total_slack', 0)} | Email tickets: {s.get('total_email_bugs', 0)}",
    ]

    dm_text = "\n".join(lines)

    # Mark as sent
    sent_at = datetime.utcnow().isoformat() + "Z"
    _set_config_value(f"dm_sent_at:{date_str}", sent_at)

    return {"message": dm_text, "already_sent": False}


# ── Config helpers ────────────────────────────────────────────────────────────

def _get_config_value(key: str) -> str:
    spreadsheet_id = sc.get_sheet_id()
    if not spreadsheet_id:
        return ""
    try:
        service = sc.get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sc.CONFIG_TAB}'!A:B",
        ).execute()
        for row in result.get("values", []):
            if row and str(row[0]).strip().lower() == key.lower():
                return str(row[1]).strip() if len(row) > 1 else ""
        return ""
    except Exception:
        return ""


def _set_config_value(key: str, value: str) -> None:
    spreadsheet_id = sc.get_sheet_id()
    if not spreadsheet_id:
        return
    try:
        service = sc.get_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sc.CONFIG_TAB}'!A:B",
        ).execute()
        rows = result.get("values", [])
        for i, row in enumerate(rows):
            if row and str(row[0]).strip().lower() == key.lower():
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"'{sc.CONFIG_TAB}'!B{i + 1}",
                    valueInputOption="RAW",
                    body={"values": [[value]]},
                ).execute()
                return
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{sc.CONFIG_TAB}'!A:B",
            valueInputOption="RAW",
            body={"values": [[key, value]]},
        ).execute()
    except Exception:
        pass


# ── Utility ───────────────────────────────────────────────────────────────────

def _col_letter(n: int) -> str:
    """Convert 1-based column number to letter(s). 1→A, 26→Z, 27→AA."""
    letters = ""
    while n:
        n, r = divmod(n - 1, 26)
        letters = chr(65 + r) + letters
    return letters


def _fmt_date(value) -> str:
    if not value:
        return ""
    s = str(value).strip()
    # YYYY-MM-DD prefix
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        return s[:10]
    return s


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Bug Dashboard running at http://localhost:5000")
    app.run(debug=True, port=5000)
