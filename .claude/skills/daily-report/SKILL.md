---
name: daily-report
description: Incremental daily bug report. Pulls new Slack hook + bug ticket data, classifies entries, and pushes only NEW rows to the Google Sheet. Existing reviewed rows are never touched. When user provides totals, reads Count?=Yes rows from sheet and sends a DM to Nhi Vũ (Yiyi) on Slack.
---

# Purpose

Two modes:

1. **Data refresh (auto / cron every 3 hours)** — Pull new Slack + bug ticket entries for
   yesterday (on startup) or today (incremental runs), classify them, append ONLY new rows
   to the "Daily Report" Google Sheet. Never delete existing rows. Reviewer's Count?/Notes
   edits are always preserved.

2. **Send report (manual)** — User says "send daily report for YYYY-MM-DD, X completed, Y started".
   Read Count?=Yes rows from sheet, calculate percentages, format the Slack message, DM to Nhi Vũ (Yiyi).

---

# Sheet columns (12 — simple)

| Col | Header  | Pre-filled by Claude | Reviewer edits |
|-----|---------|---------------------|----------------|
| A   | Date    | ✓ YYYY-MM-DD        |                |
| B   | Time    | ✓ HH:MM GMT+7       |                |
| C   | Source  | ✓ Sheet / Slack     |                |
| D   | Name    | ✓ person's name     |                |
| E   | Issue   | ✓ first 200 chars   |                |
| F   | Stage   | ✓                   |                |
| G   | Category| ✓                   |                |
| H   | Count?  | ✓ Yes/No/?          | **Override here** |
| I   | Notes   |                     | **Free text**  |
| J   | ID      | ✓ ticket_id or submission_id | |
| K   | Company | ✓                   |                |
| L   | Device  | ✓ browser+OS (Slack)|                |

**Count? pre-fill rules:**
- Platform Bug / Likely Platform Bug → **Yes**
- Borderline → **?** (reviewer decides before report is done)
- Likely User Error → **No**
- EXCLUDED → **No**
- Other (Company) bug → **Yes**
- Other (Candidate) unclear → **?**

**Report count = rows where Count? = "Yes"** (after reviewer overrides, if any).

---

# Workflow A — Data refresh (auto mode)

## Step 1 — Determine report date

- **On startup / first run of the day**: use yesterday in GMT+7.
- **Incremental 3-hour cron run**: use yesterday in GMT+7 (same — hook submissions trickle in all day for yesterday's sessions).

## Step 2 — Fetch existing IDs from sheet

Call `get_daily_report_rows(date)` to get all rows already in the sheet for the date.
Extract the set of existing IDs (field `id` = ticket_id or submission_id).
Only entries with an ID not in this set will be classified and appended.

## Step 3 — Fetch source data

**3a — Google Sheet bug tickets:**
Call `get_bug_tickets` with no filter.
Filter to tickets where `date_created` starts with `report_date`.
Exclude `status = "Duplicate"`.
Map each ticket → ID = `ticket_id`.

**3b — Slack hook submissions (#hook-flowmingo-feedback):**
Call `slack_read_channel` with `channel_id: C095U6BHVBJ` and `limit: 200`.
If pagination cursor exists, fetch additional pages until all messages for the date are retrieved.
Filter messages to those with timestamp (GMT+7) matching `report_date`.
Map each message → ID = `submission_id` field from the message.

Slack message format:
```
New feedback received from candidate [email]
Name: ...
Topic: Technical Issue / Bug Report / Others / User Experience Feedback / Feature Request
Content: [issue text]
Submission ID: [uuid]
Browser: ... | OS: ... | Device: ...
```

**Apply these pre-filters before classification:**
- EXCLUDE: Content is clearly a test string ("s", "test", "hhh", "quy test", single characters)
- EXCLUDE: Duplicate follow-up from same person about same issue (keep the first/most detailed)
- EXCLUDE: Feature Request topic
- EXCLUDE: UX confusion — person asking how to use a feature (not reporting something broken)
- INCLUDE: Technical Issue and Bug Report (any language)
- INCLUDE: Others / User Experience Feedback only if Content describes a technical malfunction (freeze, crash, data loss, wrong behavior)
- INCLUDE: Company feedback (`New feedback received from company`) if Content is a recruiter-side platform bug → Other (Company)

## Step 4 — Filter to only new entries

Remove entries whose ID already exists in the sheet (from Step 2).
If no new entries remain, stop here — no CSV update needed.

## Step 5 — Classify new entries

For each new entry, assign **stage**, **category**, and **Count?** pre-fill.

### Stage 1 — Before the Interview

| Category | When to use |
|---|---|
| **Unable to upload CV** | CV file upload fails or errors |
| **Stuck at Preparing** | Interview set loads indefinitely, first question never appears |
| **Unable to access** | Invite link errors, expired, 404, or redirects incorrectly |
| **Email not received** | Candidate never received the invitation email |
| **Link already used / expired** | Link was already submitted or past expiry |
| **Wrong language displayed** | UI or questions shown in wrong language |
| **CV not carrying over** | CV uploaded at invite stage missing from submission |

Hint: "Website Unresponsive", "Interview Loading Error" before interview starts → **Unable to access** or **Stuck at Preparing**.

### Stage 2 — During the Interview

| Category | When to use |
|---|---|
| **Stuck analyzing** | After recording, UI shows "analyzing" indefinitely and never advances |
| **Stuck during** | Interview freezes mid-question (blank screen, spinner, disconnection) |
| **Redirected to the beginning** | Candidate sent back to intro/start screen unexpectedly |
| **Camera / microphone not working** | Browser cannot access camera or mic |
| **Answer not saved / lost** | Answer missing or disappears after recording |
| **Video upload failed** | Recorded video fails to upload |
| **Question skipped / missing** | A question was skipped or not shown |
| **AI avatar not loading** | Avatar video does not play |
| **Cannot submit** | Submit button broken or unresponsive after all questions done |

Hints:
- "AI Interview Connection Error", "Connectivity Issue", "Session Interruption" → **Stuck during**
- Repeated / looping questions → **Redirected to the beginning**
- "Feature Not Working" where interview freezes or loops → **Stuck analyzing** or **Redirected to the beginning**
- "Media Functionality", "Display/Visual Issue" during recording → **Camera / microphone not working** or **AI avatar not loading**
- "Interview keeps restarting" → **Redirected to the beginning**

### Stage 3 — After the Interview

| Category | When to use |
|---|---|
| **Stuck evaluating** | Submitted but AI evaluation never completes |
| **CV evaluation failed** | CV scoring/extraction did not run |
| **Wrong / missing score** | Score is 0, null, or obviously wrong |
| **Result email not sent** | Candidate did not receive result email |
| **Retake not working** | Cannot access retake link |
| **Transcription missing / blank** | Answer transcription empty after processing |
| **Submission not visible to recruiter** | Recruiter cannot find a completed submission |
| **Submission goes to wrong stage** | Submission not mapped to expected pipeline stage |

Hint: "Post-Interview Issue" (loading screen after interview, camera still on) → **Stuck evaluating**.

### Other (Company)
Recruiter/company-side bugs not tied to a candidate stage (e.g. cannot send invitations, export broken, quota issues).

### Other (Candidate)
Candidate-side issues that do not fit any stage above.

### EXCLUDED
Entries filtered out in Step 3. Set category to the exclusion reason:
- "Internal test", "Feature Request", "Duplicate follow-up", "UX confusion"

---

## Step 6 — Determine Count? pre-fill

For each new entry:
- `stage` = Stage 1 / Stage 2 / Stage 3 AND classification = Platform Bug or Likely Platform Bug → **Yes**
- `stage` = Stage 1 / Stage 2 / Stage 3 AND classification = Borderline → **?**
- `stage` = Stage 1 / Stage 2 / Stage 3 AND classification = Likely User Error → **No**
- `stage` = Other (Company) AND classification = Platform Bug → **Yes**
- `stage` = Other (Company) AND classification = Borderline → **?**
- `stage` = Other (Candidate) → **?** (case by case)
- `stage` = EXCLUDED → **No**

Classification rules for Count? purposes (do not output a separate "assessment" column):
- **Platform Bug**: clear technical malfunction with no plausible user-side cause
- **Likely Platform Bug**: strong evidence of platform malfunction
- **Borderline**: could be platform or user-side; not enough info
- **Likely User Error**: most likely caused by user action or user-side issue

Judgment rules:
- "I want to change my language" with no error evidence → Likely User Error → **No**
- "My info keeps getting erased" with no screenshot → Borderline → **?**
- Demo works, live interview fails → Platform Bug → **Yes**
- Both PDF and DOC fail to upload → Platform Bug → **Yes**
- Analysis stuck indefinitely → Platform Bug → **Yes**
- Loop between interview and camera check → Platform Bug → **Yes**
- Language switches after page refresh → Platform Bug → **Yes**

---

## Step 7 — Write CSV and push to sheet

Create `daily-report/YYYY-MM-DD.csv` (create folder if missing).

**If the file already exists**, append new rows. If it doesn't, create with header row.

CSV column order (12 columns):
`date, time, source, name, issue, stage, category, count, notes, id, company, device`

Where:
- `date` = YYYY-MM-DD
- `time` = HH:MM
- `source` = "Sheet" (bug ticket) or "Slack" (hook submission)
- `name` = candidate/company name
- `issue` = first 200 chars of issue text
- `stage` = Stage 1 / Stage 2 / Stage 3 / Other Company / Other Candidate / EXCLUDED
- `category` = category name or exclusion reason
- `count` = Yes / No / ? (pre-filled)
- `notes` = empty (reviewer fills)
- `id` = ticket_id (Sheet source) or submission_id (Slack source)
- `company` = company name
- `device` = "Browser OS" string (Slack only, else empty)

Then run:
```
python tools/scripts/setup_daily_report_tab.py YYYY-MM-DD
```

This appends only rows whose `id` is not already in the sheet. Human edits are preserved.

**In auto mode: stop here.** No Slack message, no summary output.

---

# Workflow B — Send report (manual)

Triggered when user says something like:
> "send daily report for 2026-03-24, 372 completed, 422 started"

## Step 1 — Extract inputs

- `report_date` = YYYY-MM-DD from user message
- `total_completed` = integer
- `total_started` = integer

If any are missing, ask before proceeding.

## Step 2 — Read sheet

Call `get_daily_report_rows(report_date)`.

Check if any rows have `count = "?"` — if so, warn:
> "⚠️ {N} entries still have Count?=? (unreviewed). Counting only the Yes entries now. You can update the sheet and resend."

## Step 3 — Count

- `total_bugs` = rows where `count = "Yes"`
- Per-stage counts: filter by `stage` field, count where `count = "Yes"`
- Per-category counts within each stage

Calculate:
- `pct_completed` = `round(total_bugs / total_completed * 100, 2)`
- `pct_started` = `round(total_bugs / total_started * 100, 2)`

## Step 4 — Format Slack message

```
:large_yellow_square: Reporting Period: {Mon DD} (00:00) – {Mon DD} (11:59 PM) (1 day) @JunYuan Tan (JY)
Total Issues Reported: {total_bugs} out of {total_completed} ( [Total Completed including Internal ones] ({pct_completed}%) )
Total Issues Reported: {total_bugs} out of {total_started} ( [Total Started by Unique Emails (Include Completed, Not Completed, and Submissions never go to Interview step) including Internal ones] ({pct_started}%) )
Stage 1: Before the Interview ({stage1})
{non-zero sub-categories, one per line: "Category name: count"}

Stage 2: During the Interview ({stage2})
{non-zero sub-categories, one per line}

Stage 3: After the Interview ({stage3})
{non-zero sub-categories, one per line}

Other (Company) ({other_company})
{non-zero sub-categories, one per line}

Other (Candidate) ({other_candidate})
{non-zero sub-categories, one per line}
```

Formatting rules:
- `{Mon DD}` = e.g. `Mar 24`
- Only list sub-categories with count > 0
- Stages with 0 issues: show header `(0)` but no sub-category lines
- Blank line between each stage block

## Step 5 — Send Slack DM

1. Call `slack_search_users` to find Nhi Vũ (Yiyi). Search for "Nhi" or "Yiyi".
2. Get the user's Slack user ID.
3. Call `slack_send_message` with `channel_id = user_id` (DMs use user ID as channel).
4. Message = the formatted Slack message from Step 4.

---

# Rules

1. **Never delete rows** — incremental append only.
2. **Existing Count?/Notes are always preserved** — the Python script deduplicates by ID.
3. **Duplicate tickets excluded** — status = "Duplicate" in Bug Tickets tab is skipped.
4. **Date filter is by date prefix** — compare only `YYYY-MM-DD` portion.
5. **Reporter is always @JunYuan Tan (JY)** — never changes in the Slack message.
6. **Categories are fixed** — do not invent new ones; use closest match.
7. **Percentages to 2 decimal places.**
8. **If no entries for the date** — output all zeros in the Slack format.
9. **EXCLUDED entries are still written to CSV/Sheet** — set `count = No` so they don't inflate the count, but reviewer can see them.
