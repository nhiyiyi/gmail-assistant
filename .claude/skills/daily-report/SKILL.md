---
name: daily-report
description: Generate the daily Flowmingo bug report in Slack format. Fetches today's bug tickets, classifies them by interview stage using BUGS.md, counts by category, and outputs the formatted Slack message ready to copy-paste.
---

# Purpose

Generate the daily bug report message in the exact Slack format used by the team.
Reads today's bug tickets, classifies each into the fixed stage/category taxonomy from BUGS.md,
counts them, calculates percentages against user-provided totals, and prints the formatted message.

# When to use

- Every morning (GMT+7) to report the previous day's bugs
- User runs `/daily-report`

# Required inputs

Before starting, you need two numbers from the user. If they were not provided in the message, ask:

> "To generate the report, I need:
> 1. **Total Completed** (including internal ones): ___
> 2. **Total Started** (unique emails, including completed, not completed, and submissions that never reached the interview step — including internal): ___
> 3. **Report date** (default: yesterday GMT+7, format YYYY-MM-DD): ___
> 4. **Hook/Slack feed data** — paste the raw Slack channel log of platform feedback submissions for that day"

If the user provides only one total number, use it for both lines and note the assumption.

If the user already provided these numbers, extract them directly and proceed.

---

# Workflow

## Step 1 — Collect inputs

Extract from the user's message or ask for:
- `total_completed` — integer (e.g. 372)
- `total_started` — integer (e.g. 422)
- `report_date` — YYYY-MM-DD string (default: today in GMT+7)

## Step 2 — Fetch bug tickets + Hook emails

**2a — Google Sheet tickets:**
Call `get_bug_tickets` with no filter to get all tickets.
Filter to tickets where the date portion of `date_created` matches `report_date`.
Exclude tickets with `status = "Duplicate"`.

**2b — Hook / platform form submissions (Slack feed):**
The user will paste the raw Slack channel data containing platform feedback submissions for the report date.
These come from the Flowmingo in-platform feedback form, posted as webhook notifications to Slack.

Each entry looks like:
```
New feedback received from candidate [email]
Name: ...
Topic: Technical Issue / Bug Report / Others / User Experience Feedback / Feature Request
Content: [the actual issue text]
```

**Do NOT fetch the Gmail Hook label** — those are outbound response emails, dated when support replied (not when the submission was received), and are an incomplete subset.

Parse each submission from the pasted data and apply these filters before classifying:
- **Exclude** entries where Content is clearly a test string (e.g. "s", "test", "hhh", single characters)
- **Exclude** duplicate follow-up submissions from the same person about the same issue (keep the first/most detailed one)
- **Exclude** Feature Request topics entirely
- **Exclude** UX confusion entries where the person is asking how to use a feature (not reporting something broken)
- **Include** all Technical Issue and Bug Report topics
- **Include** Others and User Experience Feedback topics only if the Content describes a clear technical malfunction (e.g. freeze, crash, data loss, wrong behavior)

Combine with the Google Sheet tickets for classification in Step 3.

## Step 3 — Classify each ticket into BUGS.md category

For each ticket, read `issue_type` and `issue_summary` and assign exactly one category below.
Use the description and context clues — do not invent new categories.

### Stage 1 — Before the Interview
Issues occurring before the candidate answers their first question.

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
Issues occurring between the candidate's first answered question and final submission.

| Category | When to use |
|---|---|
| **Stuck analyzing** | After recording an answer, UI shows "analyzing" indefinitely and never advances |
| **Stuck during** | Interview freezes mid-question (blank screen, spinner, disconnection mid-session) |
| **Redirected to the beginning** | Candidate is sent back to intro/start screen unexpectedly |
| **Camera / microphone not working** | Browser cannot access camera or mic |
| **Answer not saved / lost** | Answer missing or disappears after recording |
| **Video upload failed** | Recorded video fails to upload |
| **Question skipped / missing** | A question was skipped or not shown |
| **AI avatar not loading** | Avatar video does not play |
| **Cannot submit** | Submit button broken or unresponsive after completing all questions |

Hints:
- "AI Interview Connection Error", "Connectivity Issue", "Session Interruption" → **Stuck during**
- Repeated questions / looping questions → **Redirected to the beginning**
- "Feature Not Working" where interview freezes or loops → **Stuck analyzing** or **Redirected to the beginning** based on description
- "Media Functionality", "Display/Visual Issue" during recording → **Camera / microphone not working** or **AI avatar not loading**
- "Interview Language / UI Issue" where interview keeps restarting → **Redirected to the beginning**
- "Video Loading Failure" during the interview → **AI avatar not loading** or **Video upload failed**

### Stage 3 — After the Interview
Issues occurring after the candidate submits.

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

Hint: "Post-Interview Issue" (loading screen after interview, camera still on) → **Stuck evaluating** (submission sent but processing not confirmed).

### Other (Company)
Recruiter/company-side bugs not tied to a candidate stage (e.g. cannot send invitations, export broken, quota issues, webhook failures).

### Other (Candidate)
Candidate-side issues that do not fit any stage above.

---

## Step 4 — Count

Tally counts:
- `total_bugs` = total non-duplicate tickets for the date
- `stage1`, `stage2`, `stage3`, `other_company` = per-stage totals
- Per-category counts within each stage

Calculate:
- `pct_completed` = `round(total_bugs / total_completed * 100, 2)`
- `pct_started` = `round(total_bugs / total_started * 100, 2)`

---

## Step 5 — Format the Slack message

Use this exact format. Do not add or remove any structural elements.

```
:large_yellow_square: Reporting Period: {Mon DD} (00:00) – {Mon DD} (11:59 PM) (1 day) @JunYuan Tan (JY)
Total Issues Reported: {total_bugs} out of {total_completed} ( [Total Completed including Internal ones] ({pct_completed}%) )
Total Issues Reported: {total_bugs} out of {total_started} ( [Total Started by Unique Emails (Include Completed, Not Completed, and Submissions never go to Interview step) including Internal ones] ({pct_started}%) )
Stage 1: Before the Interview ({stage1})
{non-zero sub-categories, one per line: "Category name: count"}

Stage 2: During the Interview ({stage2})
{non-zero sub-categories, one per line}

Stage 3: After the Interview ({stage3})
{non-zero sub-categories, one per line if any}

Other (Company) ({other_company})
{non-zero sub-categories, one per line if any}
```

Formatting rules:
- `{Mon DD}` = e.g. `Mar 24` (English 3-letter month, zero-padded day optional)
- Only list sub-categories with count > 0
- Stages with 0 issues: show the header line with `(0)` but skip sub-category lines
- Other (Company) = 0: still include the line with `(0)`, no sub-categories
- Blank line between each stage block

---

## Step 6 — Output

Print:

```
Here is today's report — copy and paste to Slack:

---
[formatted message]
---
```

Then briefly list how each ticket was classified (one line per ticket: ticket ID → category assigned), so the user can spot misclassifications.

---

# Rules

1. **Exclude Duplicate tickets** — they represent the same issue already counted.
2. **Date filter is by date portion only** — treat `date_created` as local time, compare only the `YYYY-MM-DD` prefix.
3. **Reporter is always @JunYuan Tan (JY)** — never changes.
4. **Categories are fixed** — do not invent new ones; use closest match + note any edge cases.
5. **Percentages to 2 decimal places.**
6. If no tickets match the date, output the full format with all zeros.
