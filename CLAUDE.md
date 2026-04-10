# Flowmingo Gmail Support Assistant

This project reads Flowmingo customer support emails and creates Gmail draft replies
using the SOP in `knowledge/`. Drafts appear in Gmail and must be reviewed before sending.

## How to process emails

```
/process-emails
```

Claude reads unread inbox emails, classifies them, creates draft replies, applies Gmail
labels, and saves state. Runs automatically every hour via cron.

## How to refresh drafts after an SOP update

```
/refresh-drafts
```

After editing `knowledge/flowmingo-sop.md`, run this to rewrite all pending drafts
using the latest SOP. The assistant finds stale drafts automatically using KB version tracking.

## How to get a report

Ask: "Show me a report for today" or "Show me a report for 2026-03-20"

Claude will call `get_report` and show topic, sender type, urgency, and status breakdowns
with counts and percentages — e.g., "20 of 100 emails were technical issues."

## Check costs and stats

Ask Claude: "Show me today's stats" — calls `get_stats` tool.

## First-time setup

1. Get `credentials.json` from Google Cloud Console (see steps in `tools/scripts/setup_oauth.py`)
2. Place it at `credentials/credentials.json`
3. Run the OAuth flow:
   ```
   python tools/scripts/setup_oauth.py
   ```
4. Browser opens → log in → Allow → done
5. Run `/process-emails` once to initialize Gmail labels.

## Updating the SOP

Edit `knowledge/flowmingo-sop.md` only. No code changes needed.
Additional `.md` files added to `knowledge/` are auto-loaded.

After editing, run `/refresh-drafts` to update any pending draft replies.

## Git workflow

After every edit session, ask the user: "Do you want to push to main?"

## Key rules

- Drafts only. This assistant NEVER sends emails.
- All drafts must be reviewed and sent manually from the Gmail UI.
- OAuth scope is `gmail.modify` — sending is technically impossible.

## Cost guidance

Main cost driver is the SOP loaded into context (~2,500 tokens) per run.

- **Use Haiku for processing:** `/model haiku` before `/process-emails`, then `/model default` to return to Sonnet. Haiku is ~4x cheaper for the same quality on support emails.
- Drafts with `[REVIEW NEEDED]` in the body need human review before sending.

## Hourly auto-run

The assistant processes new emails automatically every hour via cron.
If you restart Claude Code, restore the cron by asking Claude:
"Set up the hourly cron for process-emails."

## On startup — automatic daily report

**Every time this project is opened in Claude Code**, immediately and silently:

1. Run the daily bug report for **yesterday (GMT+7)** using the `/daily-report` skill.
2. Write the results to `daily-report/YYYY-MM-DD.csv`.
3. Push the rows to the "Daily Report" Google Sheet tab using `tools/scripts/setup_daily_report_tab.py`.
   - If the tab already has rows for that date, clear them first before pushing fresh data.
4. Do **not** output the Slack message — auto mode only.
5. Do **not** ask for `total_completed` or `total_started` — skip the percentage calculation in auto mode.

This ensures the Daily Report tab always reflects the latest hook submissions when you start your day.

## MCP server

Gmail tools are available via the MCP server at `src/api/server.py`.
It starts automatically when you open this directory in Claude Code.

To verify it works: ask Claude "list my unread emails".

## Email pipeline architecture

Every unread inbox email goes through this pipeline in `tools/scripts/process_emails_openai.py`:

1. **rules_engine** (`src/api/rules_engine.py`) — deterministic pre-routing before any LLM call. Detects bugs, DNC signals, deletion requests, external reschedules. Returns `{sender_type, is_bug, risk_triggers, pre_route_hint}`.
2. **Per-email RAG** — BM25 retrieves the most relevant KB sections for each email individually.
3. **OpenAI gpt-4o-mini** — classifies email, selects scenario, returns `scenario_confidence` (0–1).
4. **scenario_contracts** (`src/api/scenario_contracts.py`) — loads JSON contracts from `knowledge/contracts/`. Validates the model's scenario selection against the pre-route hint; adds `scenario_mismatch` or `unknown_scenario` to risk triggers.
5. **Confidence gate** — if `scenario_confidence < 0.7` → FM/review with `LOW_CONFIDENCE` reason.
6. **validators** (`src/api/validators.py`) — checks draft against contract rules (required facts, forbidden promises, ownership patterns). Returns severity: PASS / LOW / MEDIUM / HIGH.
7. **Repair or label**:
   - LOW → auto-fixed in-place (strip markdown, add salutation/closing)
   - MEDIUM → `repair_v2` (re-classify with validation errors injected, max_tokens=2000)
   - HIGH → FM/review with `review_reason_code`
   - PASS/LOW after fix → FM/ready

**Dedup rule**: No email is ever skipped because it was previously processed. Any email still unread in inbox is always re-processed — if it's unread it means `mark_as_read` failed or the draft was deleted. A stale draft is deleted before creating the replacement.

**Bug path**: `FM/bug` label applied immediately before ticket creation. Bug dedup by `thread_id` within a single run.

**Labels**: FM/ready (send as-is), FM/review (needs human edits), FM/bug (bug ticket created), FM/no-reply (auto-reply sender, skipped).

## Scenario contracts

JSON files in `knowledge/contracts/` define per-scenario validation rules:

```json
{
  "scenario_id": "S18",
  "required_facts": [...],
  "forbidden_promises": [...],
  "ownership_patterns": [...],
  "force_review": false
}
```

To add a new scenario contract, create a new JSON file in `knowledge/contracts/` matching a scenario ID from the SOP. The pipeline validates contract IDs against the SOP on startup.

## review_reason_code values

`LOW_CONFIDENCE`, `ALREADY_REPLIED`, `PARTIAL_CONTEXT`, `WRONG_OWNERSHIP`, `MISSING_REQUIRED_FACT`, `FORBIDDEN_PROMISE`, `FORMAT_VIOLATION`, `WRONG_SCENARIO`, `AI_ERROR`, `BUG_TICKET_FAILED`, `UNKNOWN_SCENARIO`

## Files

| File | Purpose |
|------|---------|
| `knowledge/flowmingo-sop.md` | SOP — edit to update knowledge |
| `knowledge/contracts/` | Per-scenario validation contracts (JSON) |
| `credentials/credentials.json` | Google OAuth client credentials (you provide) |
| `credentials/token.json` | Auto-generated by setup_oauth.py |
| `stats/email_stats.json` | Daily cost and token usage |
| `stats/email_state.json` | Per-email state: type, topic, draft ID, KB version, validator_score, repair_attempted, review_reason_code |
| `src/api/server.py` | MCP server |
| `src/api/gmail_client.py` | Gmail API wrapper |
| `src/api/rules_engine.py` | Deterministic pre-routing (bug/DNC/deletion/reschedule detection) |
| `src/api/validators.py` | Draft validation against scenario contracts |
| `src/api/scenario_contracts.py` | Contract loader and scenario selector |
| `src/api/labels.py` | Flowmingo label definitions |
| `src/persistence/state.py` | Email state persistence |
| `src/persistence/stats.py` | Cost tracking |
| `tools/scripts/process_emails_openai.py` | Main pipeline (OpenAI gpt-4o-mini) |
| `tools/scripts/setup_oauth.py` | One-time OAuth setup |
