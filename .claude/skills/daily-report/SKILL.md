---
name: daily-report
description: Load daily bug data into the local review DB. Fetches Slack + Sheet entries, classifies them, and imports into SQLite so the user can review at localhost:5000/daily. Stops after loading — never auto-approves or generates the report.
---

# Purpose

Load daily bug data into the local review DB for human review.

**Stop after loading. Never auto-approve entries. Never generate the Slack report.**

The report is generated from the UI ("Generate Report" button) after the user has reviewed and approved entries.

# Workflow

## Step 1 — Get report date

Default: yesterday GMT+7 (format: YYYY-MM-DD).

Do NOT ask for `total_completed` or `total_started` — those are only needed at report generation time in the UI.

## Step 2 — Check if data already loaded

`GET http://localhost:5000/api/dr/entries?date=YYYY-MM-DD`

If `stats.total > 0`: skip to Step 4 — data is already in the DB, no need to re-fetch.

## Step 3 — Fetch, classify, and load

1. Fetch Slack messages and Google Sheet tickets for the date.
2. Classify each entry (stage, category, assessment, confidence).
3. Deduplicate — mark duplicates as EXCLUDED.
4. Write to `daily-report/YYYY-MM-DD.csv`.
5. Run: `python dashboard/load_csv.py daily-report/YYYY-MM-DD.csv`

## Step 4 — Stop and report

Output exactly:
```
Loaded {stats.total} entries for YYYY-MM-DD ({stats.pending} pending, {stats.approved} approved).
Open http://localhost:5000/daily to review.
```

Done. Do not approve anything. Do not generate a Slack message.
