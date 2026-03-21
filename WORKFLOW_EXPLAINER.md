# Flowmingo Gmail Support Assistant — Executive Overview

## What It Does

An AI agent that reads every new customer support email, drafts a reply, and organizes the inbox — fully automatically, every hour. A human only needs to open Gmail, review the draft, and click Send.

**The agent never sends email on its own.** The Google API permission (`gmail.modify`) makes sending technically impossible — it can only create drafts.

---

## End-to-End Flow

```
Every 3 hours (automated cron)
         │
         ▼
1. Fetch up to 500 unread inbox emails
         │
         ├─ Already processed? → Skip
         ├─ Duplicate thread? → Keep only the latest message
         ├─ Auto-sender (noreply@, OTP, delivery notice)? → Label FM/no-reply, done
         │
         ▼
2. Load the SOP (only the relevant sections per email — ~50% token savings)
         │
         ▼
3. For each email: classify sender, match scenario, draft reply
         │
         ├─ Bug report? → Full bug ticket flow (see below)
         ├─ Needs human judgement? → Flag FM/review + log action item
         └─ Clear SOP match? → Flag FM/ready
         │
         ▼
4. Submit all drafts in one batch call
   (create draft + apply label + mark as read + log cost + save state)
         │
         ▼
5. Human opens Gmail → reviews color-coded drafts → clicks Send
```

---

## Batch Size & Token Efficiency


| What                    | Detail                                                                                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Emails per run          | Up to **500** (all unread, default)                                                                                                        |
| Already-processed       | Skipped automatically using a state file                                                                                                   |
| Thread deduplication    | One email per thread — no duplicate work                                                                                                   |
| Auto-skipped (no-reply) | Detected from sender/subject patterns, no AI needed                                                                                        |
| Tokens per email        | **~175 tokens** (compact summary) vs ~2,500 with full thread fetch — **14x reduction**                                                     |
| SOP loading             | `get_kb_for_email`: only relevant SOP sections retrieved per email via BM25 keyword matching — ~50% fewer tokens than loading the full SOP |


---

## Cost Optimization — Three Layers

**1. Smart batching** — A single `get_email_batch` call handles all filtering, deduplication, and thread fetching server-side before Claude sees anything. Claude only processes emails that actually need a reply.

**2. Partial SOP retrieval (RAG)** — Instead of loading the full ~2,500-token SOP for every email, BM25 retrieval finds only the matching scenario sections. Base rules + top 3–5 relevant chunks ≈ half the tokens.

**3. Model selection** — Run on Claude Haiku (`/model haiku`) for ~4x cost reduction with comparable quality on support emails. Switch back to Sonnet for complex or sensitive cases.

**Net effect:** A batch of 50 real emails costs a fraction of what naive per-email full-context processing would cost.

---

## Gmail Labels (What the Reviewer Sees)


| Label         | Color | Action needed                                                          |
| ------------- | ----- | ---------------------------------------------------------------------- |
| `FM/ready`    | Green | Draft is ready — review and send                                       |
| `FM/review`   | Amber | Read the `[REVIEW NEEDED]` note in the draft — human decision required |
| `FM/no-reply` | Gray  | Nothing — automated email, vendor pitch, etc.                          |
| `FM/bug`      | Red   | Bug report — ticket already created and logged (see below)             |


---

## Bug Report Flow (Fully Automated)

When an email is identified as a bug report, the system does **four things in one tool call**:

1. **Generates a ticket ID** — format `BUG-YYMMDD-001`, auto-incremented per day
2. **Creates an HTML draft** — branded acknowledgment email with ticket code, issue summary, 2–3 troubleshooting steps, progress bar (`Reported → Verified → Fix in Progress → Resolved`), and the customer's original message quoted back
3. **Applies `FM/bug` label** (red) in Gmail
4. **Logs a row to Google Sheets** — ticket ID, date, customer name/email, issue summary (in English and Vietnamese for the tech team), issue type, draft ID, and thread link

The Google Sheet has two tabs:

- **Bug Tickets** — all bug reports with status tracking
- **Actions Required** — every `FM/review` item (GDPR requests, DNC, vague bugs) in one place so nothing gets missed

---

## SOP Updates — Zero Downtime

The SOP lives entirely in `knowledge/*.md` files. No code changes needed.

- Edit `flowmingo-rules.md` or `flowmingo-scenarios.md`
- Run `/refresh-drafts`
- The system compares the SHA-256 hash of the current SOP against the version stored per draft, finds stale drafts, and rewrites only those — leaving already-correct drafts untouched

---

## Reporting

Ask Claude at any time:


| Query                        | Returns                                                            |
| ---------------------------- | ------------------------------------------------------------------ |
| "Show me a report for today" | Breakdown by topic, sender type, urgency, status with counts and % |
| "Show me today's stats"      | Total emails processed, tokens used, estimated cost                |
| "Show me bug tickets"        | All tickets from Google Sheets, filterable by status               |


---

## What the Human Reviewer Does

1. Open Gmail
2. Look at `FM/` labels in the left sidebar
3. **Green** → read draft → Send
4. **Amber** → read the note at the top of the draft → decide
5. **Red** → check Google Sheet for the ticket; reply draft is already there
6. **Gray** → ignore

That's it. Everything else is automated.

---

## Architecture (One Paragraph)

The system is a Python MCP server (`src/api/server.py`) exposing 17 tools to Claude. When Claude Code opens this project, the server starts automatically. Claude calls tools to read emails, load the SOP, write drafts, apply labels, log state, and update Google Sheets — all via authenticated Google API calls. State is persisted locally in two JSON files (`email_state.json` for per-email metadata, `email_stats.json` for daily costs). The cron runs `/process-emails` every hour without any human involvement.

---

## Safety Guarantees


| Risk                            | Mitigation                                                                                |
| ------------------------------- | ----------------------------------------------------------------------------------------- |
| AI sends email without approval | Impossible — OAuth scope is `gmail.modify` (no send permission)                           |
| Wrong reply goes out            | Human reviews every draft before sending                                                  |
| Low-confidence email sent       | Amber label + `[REVIEW NEEDED]` note in draft body; also logged to Actions Required sheet |
| SOP change breaks old drafts    | `/refresh-drafts` rewrites stale drafts using KB version hash                             |
| Bug report gets lost            | Auto-logged to Google Sheets + red label                                                  |
| Legal/GDPR requests missed      | Always flagged amber + logged to Actions Required sheet                                   |


