#!/usr/bin/env python3
"""Gmail MCP server — reads email, creates drafts, loads SOP knowledge, tracks costs."""

import json
import asyncio
import sys
from pathlib import Path

# Allow sibling imports when launched from project root via `python src/api/server.py`
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "persistence"))

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

import gmail_client
import knowledge
import labels as labels_module
import rag
import stats
import sheets_client
import bug_template

app = Server("gmail")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        # ── Core email tools ──────────────────────────────────────────────────
        types.Tool(
            name="list_emails",
            description="List emails from Gmail. Defaults to unread inbox emails.",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Max emails to return (1-100, default 20)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Gmail search query, e.g. 'is:unread in:inbox'",
                    },
                    "label_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Label IDs to filter by, e.g. ['INBOX', 'UNREAD']",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_email",
            description="Get full content of a single email by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "email_id": {"type": "string", "description": "Gmail message ID"}
                },
                "required": ["email_id"],
            },
        ),
        types.Tool(
            name="get_thread",
            description="Get the full conversation thread by thread ID. Returns all messages in order.",
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {
                        "type": "string",
                        "description": "Gmail thread ID (from list_emails or get_email)",
                    }
                },
                "required": ["thread_id"],
            },
        ),
        # ── Draft tools ───────────────────────────────────────────────────────
        types.Tool(
            name="create_draft",
            description="Create a Gmail draft reply. Appears in Gmail Drafts for human review. Never auto-sends.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {
                        "type": "string",
                        "description": "Email subject. Will auto-prepend 'Re: ' if needed.",
                    },
                    "body": {"type": "string", "description": "Plain text email body"},
                    "thread_id": {
                        "type": "string",
                        "description": "Thread ID so the draft appears in the original thread",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        ),
        types.Tool(
            name="list_drafts",
            description="List all current Gmail drafts with subject, recipient, thread ID, and snippet.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="update_draft",
            description="Replace the body of an existing draft. Used when refreshing drafts after a knowledge base update.",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "string", "description": "ID of the draft to update"},
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "New plain text body"},
                    "thread_id": {
                        "type": "string",
                        "description": "Thread ID (optional, auto-resolved from draft if omitted)",
                    },
                },
                "required": ["draft_id", "to", "subject", "body"],
            },
        ),
        types.Tool(
            name="delete_draft",
            description="Permanently delete a draft.",
            inputSchema={
                "type": "object",
                "properties": {
                    "draft_id": {"type": "string", "description": "ID of the draft to delete"}
                },
                "required": ["draft_id"],
            },
        ),
        # ── Knowledge base tools ──────────────────────────────────────────────
        types.Tool(
            name="get_knowledge_base",
            description="Load the full SOP (all sections). Use get_kb_for_email instead to load only relevant sections for a specific email.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="get_kb_for_email",
            description=(
                "Load only the SOP sections relevant to a specific email using BM25 retrieval. "
                "Returns base rules (behavior, tone, links, sender types, scenario index) "
                "plus the top matching scenario/program sections. "
                "Typically ~50% fewer tokens than get_knowledge_base. "
                "Call once per email with the email subject and body as email_text."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "email_text": {
                        "type": "string",
                        "description": "Email subject + body text to match against SOP scenarios",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of scenario/program chunks to retrieve (default 3)",
                    },
                },
                "required": ["email_text"],
            },
        ),
        types.Tool(
            name="mark_as_read",
            description="Mark a Gmail message as read (removes UNREAD label). Call after creating the draft.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Gmail message ID to mark as read"}
                },
                "required": ["message_id"],
            },
        ),
        # ── Label tools ───────────────────────────────────────────────────────
        types.Tool(
            name="setup_labels",
            description="Ensure FM/ready, FM/review, and FM/no-reply labels exist in Gmail. Call once per session before applying labels.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="apply_labels",
            description="Apply a label to a Gmail message. Use FM/ready, FM/review, or FM/no-reply.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "Gmail message ID"},
                    "label":      {"type": "string", "description": "One of: FM/ready, FM/review, FM/no-reply"},
                },
                "required": ["message_id", "label"],
            },
        ),
        # ── Stats / cost tracking ─────────────────────────────────────────────
        types.Tool(
            name="get_stats",
            description="Return daily email processing counts and Claude API cost breakdown.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="log_processing",
            description="Record that an email was processed. Logs token usage and metadata for history tracking.",
            inputSchema={
                "type": "object",
                "properties": {
                    "email_id":      {"type": "string", "description": "Gmail message ID"},
                    "input_tokens":  {"type": "integer", "description": "Number of input tokens used"},
                    "output_tokens": {"type": "integer", "description": "Number of output tokens generated"},
                    "subject":       {"type": "string", "description": "Email subject line"},
                    "from_addr":     {"type": "string", "description": "Sender email address"},
                    "scenario":      {"type": "string", "description": "Matched SOP scenario, e.g. S3"},
                    "topic":         {"type": "string", "description": "Classified topic, e.g. technical"},
                    "urgency":       {"type": "string", "description": "normal | urgent | critical"},
                    "review_status": {"type": "string", "description": "ready | review | urgent | critical"},
                },
                "required": ["email_id", "input_tokens", "output_tokens"],
            },
        ),
        types.Tool(
            name="get_history",
            description="Return the most recently processed emails with subject, sender, scenario, and cost.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max entries to return (default 50)"},
                },
                "required": [],
            },
        ),
        # ── Bug ticket management ─────────────────────────────────────────────
        types.Tool(
            name="create_bug_ticket",
            description=(
                "Create a bug ticket for an email identified as a bug report. "
                "Generates a unique BUG-YYMMDD-SEQ ticket ID, renders the acknowledgment "
                "HTML email draft, applies the FM/bug Gmail label, and logs the ticket "
                "to the Google Sheet for tracking."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "email_id":               {"type": "string", "description": "Gmail message ID"},
                    "thread_id":              {"type": "string", "description": "Gmail thread ID"},
                    "customer_name":          {"type": "string", "description": "Customer's first name or full name"},
                    "from_addr":              {"type": "string", "description": "Customer's email address"},
                    "subject":                {"type": "string", "description": "Original email subject"},
                    "issue_summary":          {"type": "string", "description": "1-3 sentence summary of the bug"},
                    "issue_type":             {"type": "string", "description": "Bug category, e.g. 'Login Issue', 'Data Error'"},
                    "troubleshooting_steps":  {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-3 quick things the customer can try immediately, specific to this issue type. Keep each step under 12 words.",
                    },
                    "original_message":       {"type": "string", "description": "The customer's original email body (plain text, trimmed to ~300 chars)"},
                    "issue_summary_vi":       {"type": "string", "description": "Vietnamese translation of issue_summary (full, 1-3 sentences) for the tech team"},
                    "main_issue_vi":          {"type": "string", "description": "Single Vietnamese sentence (<10 words) naming the core problem. Start with the affected subject (Trang / Hệ thống / Nút / Câu hỏi / Màn hình…). Example: 'Câu hỏi bị lặp lại nhiều lần trong lúc phỏng vấn.'"},
                },
                "required": ["email_id", "thread_id", "customer_name", "from_addr", "subject", "issue_summary", "issue_summary_vi", "main_issue_vi", "troubleshooting_steps", "original_message"],
            },
        ),
        types.Tool(
            name="log_action_item",
            description=(
                "Log an action item to the 'Actions Required' sheet tab. "
                "Call this for every FM/review email after submit_drafts — including DNC requests, "
                "vague bugs pending more info, and any email flagged with a [REVIEW NEEDED] reason. "
                "The sheet gives the human team a single place to see everything that needs their attention."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "action_type":   {"type": "string", "description": "Review Draft | DNC Request | Manual Follow-up"},
                    "priority":      {"type": "string", "description": "High | Normal"},
                    "customer_name": {"type": "string", "description": "Customer's name (use empty string if unknown)"},
                    "email":         {"type": "string", "description": "Customer's email address"},
                    "subject":       {"type": "string", "description": "Original email subject"},
                    "reason":        {"type": "string", "description": "The exact [REVIEW NEEDED] reason string, or a short description of what action is needed"},
                    "thread_id":     {"type": "string", "description": "Gmail thread ID — used to build a direct Gmail link"},
                },
                "required": ["action_type", "priority", "subject", "reason", "thread_id"],
            },
        ),
        types.Tool(
            name="get_bug_tickets",
            description="Return bug tickets from the Google Sheet, optionally filtered by status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: Reported | Verified | Fix in Progress | Resolved",
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="update_bug_ticket",
            description="Update the status and/or notes for a bug ticket in the Google Sheet.",
            inputSchema={
                "type": "object",
                "properties": {
                    "ticket_id": {"type": "string", "description": "Ticket ID, e.g. BUG-260320-001"},
                    "status":    {"type": "string", "description": "New status: Reported | Verified | Fix in Progress | Resolved"},
                    "notes":     {"type": "string", "description": "Resolution notes or progress update"},
                },
                "required": ["ticket_id"],
            },
        ),
        # ── Daily report tools ────────────────────────────────────────────────
        types.Tool(
            name="check_report_complete",
            description=(
                "Check whether all Daily Report rows for a date have been reviewed/approved. "
                "Returns: total, pending, reviewed, approved, excluded, and complete (bool)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Report date YYYY-MM-DD"},
                },
                "required": ["date"],
            },
        ),
        types.Tool(
            name="get_report_summary",
            description=(
                "Get aggregated bug counts from approved+included Daily Report rows for a date. "
                "Returns stage totals, verdict totals, and source breakdown."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Report date YYYY-MM-DD"},
                },
                "required": ["date"],
            },
        ),
        types.Tool(
            name="set_report_config",
            description=(
                "Store total_completed and total_started for a date in the Config sheet tab. "
                "Used for computing percentages in the boss DM."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date":            {"type": "string",  "description": "Report date YYYY-MM-DD"},
                    "total_completed": {"type": "integer", "description": "Total completed interviews (including internal)"},
                    "total_started":   {"type": "integer", "description": "Total unique emails that started (including internal)"},
                },
                "required": ["date", "total_completed", "total_started"],
            },
        ),
        types.Tool(
            name="upsert_daily_report_rows",
            description=(
                "Push classified daily report rows to the 'Daily Report' Google Sheet tab. "
                "Safe to re-run: approved rows are never overwritten. "
                "Non-approved rows for the affected dates are replaced. "
                "Each row must include source_id (SLACK-{ts} or SHEET-{ticket_id})."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "description": "List of row objects. Keys must match the 29-column CSV schema.",
                        "items": {"type": "object"},
                    },
                },
                "required": ["rows"],
            },
        ),
        types.Tool(
            name="send_report_dm",
            description=(
                "Send the daily report Slack DM when yesterday's report is fully approved. "
                "Idempotent — checks dm_sent_at in the Summary tab before sending. "
                "Reads counts from the Daily Report tab and totals from Config."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "date":      {"type": "string", "description": "Report date YYYY-MM-DD"},
                    "user_id":   {"type": "string", "description": "Slack user ID to DM (e.g. U12345678)"},
                    "sheet_url": {"type": "string", "description": "Google Sheet URL for the link in the DM"},
                },
                "required": ["date", "user_id"],
            },
        ),
        # ── Batch processing tools ────────────────────────────────────────────
        types.Tool(
            name="get_email_batch",
            description=(
                "Efficiently fetch all new unread emails as compact summaries for batch processing. "
                "Server-side: filters already-processed emails, deduplicates threads, pre-classifies "
                "no-reply senders, fetches thread bodies internally, and returns only what Claude "
                "needs to draft replies (~175 tokens/email vs ~2500 for get_thread). "
                "Also returns kb_version and kb_query_hint for a single get_kb_for_email call. "
                "Use this instead of list_emails + get_thread for /process-emails."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Max emails to fetch from Gmail before filtering (default 500, max 500 — fetches all unread)",
                    }
                },
                "required": [],
            },
        ),
        types.Tool(
            name="submit_drafts",
            description=(
                "Batch submit all drafted replies in one call. For each draft: creates the Gmail draft, "
                "applies the label, marks as read, saves state, and logs cost. "
                "Also handles no-reply emails (label + mark read + log). "
                "Use after Claude has written all drafts in the batch processing flow."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "drafts": {
                        "type": "array",
                        "description": "List of draft objects to create",
                        "items": {
                            "type": "object",
                            "properties": {
                                "email_id":                {"type": "string"},
                                "thread_id":               {"type": "string"},
                                "to":                      {"type": "string"},
                                "subject":                 {"type": "string"},
                                "body":                    {"type": "string"},
                                "label":                   {"type": "string", "description": "FM/ready or FM/review"},
                                "scenario":                {"type": "string"},
                                "topic":                   {"type": "string"},
                                "urgency":                 {"type": "string"},
                                "review_status":           {"type": "string"},
                                "sender_type":             {"type": "string"},
                                "from_addr":               {"type": "string"},
                                "date":                    {"type": "string"},
                                "kb_version":              {"type": "string"},
                                "estimated_input_tokens":  {"type": "integer"},
                            },
                            "required": ["email_id", "to", "subject", "body"],
                        },
                    },
                    "no_reply_items": {
                        "type": "array",
                        "description": "Emails to mark as no-reply (label FM/no-reply + mark read + log). No draft created.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id":      {"type": "string"},
                                "from":    {"type": "string"},
                                "subject": {"type": "string"},
                            },
                            "required": ["id"],
                        },
                    },
                },
                "required": [],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "list_emails":
            return _handle_list_emails(arguments)
        elif name == "get_email":
            return _handle_get_email(arguments)
        elif name == "get_thread":
            return _handle_get_thread(arguments)
        elif name == "create_draft":
            return _handle_create_draft(arguments)
        elif name == "list_drafts":
            return _handle_list_drafts()
        elif name == "update_draft":
            return _handle_update_draft(arguments)
        elif name == "delete_draft":
            return _handle_delete_draft(arguments)
        elif name == "get_knowledge_base":
            return _handle_knowledge()
        elif name == "get_kb_for_email":
            return _handle_get_kb_for_email(arguments)
        elif name == "setup_labels":
            return _handle_setup_labels()
        elif name == "apply_labels":
            return _handle_apply_labels(arguments)
        elif name == "mark_as_read":
            return _handle_mark_as_read(arguments)
        elif name == "get_stats":
            return _handle_get_stats()
        elif name == "log_processing":
            return _handle_log_processing(arguments)
        elif name == "get_history":
            return _handle_get_history(arguments)
        elif name == "create_bug_ticket":
            return _handle_create_bug_ticket(arguments)
        elif name == "log_action_item":
            return _handle_log_action_item(arguments)
        elif name == "get_bug_tickets":
            return _handle_get_bug_tickets(arguments)
        elif name == "update_bug_ticket":
            return _handle_update_bug_ticket(arguments)
        elif name == "get_email_batch":
            return _handle_get_email_batch(arguments)
        elif name == "submit_drafts":
            return _handle_submit_drafts(arguments)
        elif name == "upsert_daily_report_rows":
            return _handle_upsert_daily_report_rows(arguments)
        elif name == "check_report_complete":
            return _handle_check_report_complete(arguments)
        elif name == "get_report_summary":
            return _handle_get_report_summary(arguments)
        elif name == "set_report_config":
            return _handle_set_report_config(arguments)
        elif name == "send_report_dm":
            return _handle_send_report_dm(arguments)
        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
    except FileNotFoundError as e:
        return [types.TextContent(type="text", text=f"ERROR: {e}")]
    except RuntimeError as e:
        return [types.TextContent(type="text", text=f"ERROR: {e}")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"ERROR ({type(e).__name__}): {e}")]


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_list_emails(args: dict) -> list[types.TextContent]:
    result = gmail_client.list_emails(
        max_results=args.get("max_results", 20),
        query=args.get("query", "is:unread in:inbox"),
        label_ids=args.get("label_ids"),
    )
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_get_email(args: dict) -> list[types.TextContent]:
    result = gmail_client.get_email(args["email_id"])
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_get_thread(args: dict) -> list[types.TextContent]:
    result = gmail_client.get_thread(args["thread_id"])
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_create_draft(args: dict) -> list[types.TextContent]:
    result = gmail_client.create_draft(
        to=args["to"],
        subject=args["subject"],
        body=args["body"],
        thread_id=args.get("thread_id"),
    )
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_list_drafts() -> list[types.TextContent]:
    result = gmail_client.list_drafts()
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_update_draft(args: dict) -> list[types.TextContent]:
    result = gmail_client.update_draft(
        draft_id=args["draft_id"],
        to=args["to"],
        subject=args["subject"],
        body=args["body"],
        thread_id=args.get("thread_id"),
    )
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_delete_draft(args: dict) -> list[types.TextContent]:
    result = gmail_client.delete_draft(args["draft_id"])
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_knowledge() -> list[types.TextContent]:
    text = knowledge.load_all()
    return [types.TextContent(type="text", text=text)]


def _handle_get_kb_for_email(args: dict) -> list[types.TextContent]:
    rules_text     = knowledge.load_rules()
    scenarios_text = knowledge.load_scenarios()
    result = rag.get_relevant_context(
        rules_text=rules_text,
        scenarios_text=scenarios_text,
        email_text=args["email_text"],
        top_k=args.get("top_k", 5),
    )
    return [types.TextContent(type="text", text=result)]


def _handle_setup_labels() -> list[types.TextContent]:
    label_map = gmail_client.get_label_map()
    return [types.TextContent(type="text", text=json.dumps(label_map, indent=2))]


def _handle_apply_labels(args: dict) -> list[types.TextContent]:
    result = gmail_client.apply_labels(args["message_id"], [args["label"]])
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_mark_as_read(args: dict) -> list[types.TextContent]:
    result = gmail_client.mark_as_read(args["message_id"])
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_get_stats() -> list[types.TextContent]:
    result = stats.get_stats()
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_log_processing(args: dict) -> list[types.TextContent]:
    result = stats.log_processing(
        email_id=args["email_id"],
        input_tokens=args["input_tokens"],
        output_tokens=args["output_tokens"],
        subject=args.get("subject", ""),
        from_addr=args.get("from_addr", ""),
        scenario=args.get("scenario", ""),
        topic=args.get("topic", ""),
        urgency=args.get("urgency", ""),
        review_status=args.get("review_status", ""),
    )
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_get_history(args: dict) -> list[types.TextContent]:
    entries = stats.get_history(limit=args.get("limit", 50))
    return [types.TextContent(type="text", text=json.dumps(entries, indent=2))]


def _handle_create_bug_ticket(args: dict) -> list[types.TextContent]:
    from datetime import datetime
    email_id      = args["email_id"]
    thread_id     = args["thread_id"]
    customer_name = args["customer_name"]
    from_addr     = args["from_addr"]
    subject       = args["subject"]
    issue_summary         = args["issue_summary"]
    issue_summary_vi      = args.get("issue_summary_vi", "")
    main_issue_vi         = args.get("main_issue_vi", "")
    issue_type            = args.get("issue_type", "Bug Report")
    troubleshooting_steps = args.get("troubleshooting_steps", [])
    original_message      = args.get("original_message", "")

    # Generate ticket ID: BUG-YYMMDD-SEQ
    date_str = datetime.now().strftime("%y%m%d")
    sheet_id = sheets_client.get_sheet_id()
    if sheet_id:
        seq = sheets_client.get_next_sequence(sheet_id, date_str)
    else:
        seq = 1
    ticket_id = f"BUG-{date_str}-{seq:03d}"
    submitted_at = datetime.now().strftime("%B %d, %Y %H:%M")

    # Render HTML acknowledgment draft
    html = bug_template.render_acknowledgment(
        ticket_code=ticket_id,
        customer_name=customer_name,
        issue_type=issue_type,
        submitted_at=submitted_at,
        issue_summary=issue_summary,
        troubleshooting_steps=troubleshooting_steps,
        original_message=original_message,
    )

    # Create Gmail draft with the HTML template
    draft_result = gmail_client.create_draft_html(
        to=from_addr,
        subject=subject,
        html_body=html,
        thread_id=thread_id,
    )
    draft_id = draft_result.get("draft_id", "")

    # Apply FM/bug label
    gmail_client.apply_labels(email_id, ["FM/bug"])

    # Log to Google Sheet
    sheet_result = sheets_client.append_ticket_row({
        "ticket_id":       ticket_id,
        "date_created":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "customer_name":   customer_name,
        "email":           from_addr,
        "subject":         subject,
        "issue_summary":    issue_summary,
        "issue_summary_vi": issue_summary_vi,
        "main_issue_vi":    main_issue_vi,
        "issue_type":       issue_type,
        "draft_id":         draft_id,
        "thread_id":        thread_id,
        "original_message": original_message,
    })

    result = {
        "ticket_id": ticket_id,
        "draft_id":  draft_id,
        "sheet":     sheet_result,
    }
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_get_bug_tickets(args: dict) -> list[types.TextContent]:
    tickets = sheets_client.get_tickets(status_filter=args.get("status"))
    return [types.TextContent(type="text", text=json.dumps(tickets, indent=2))]


def _handle_update_bug_ticket(args: dict) -> list[types.TextContent]:
    result = sheets_client.update_ticket(
        ticket_id=args["ticket_id"],
        status=args.get("status"),
        notes=args.get("notes"),
    )
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_log_action_item(args: dict) -> list[types.TextContent]:
    from datetime import datetime
    thread_id = args["thread_id"]
    result = sheets_client.append_action_row({
        "date":          datetime.now().strftime("%Y-%m-%d %H:%M"),
        "action_type":   args["action_type"],
        "priority":      args.get("priority", "Normal"),
        "customer_name": args.get("customer_name", ""),
        "email":         args.get("email", ""),
        "subject":       args["subject"],
        "reason":        args["reason"],
        "thread_id":     thread_id,
    })
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _compact_thread_summary(thread_data: dict, email_meta: dict) -> dict:
    """Strip a full thread down to only what Claude needs to draft a reply."""
    SUPPORT_DOMAINS = ["flowmingo.ai"]
    messages = thread_data.get("messages", [])
    if not messages:
        return {
            **email_meta,
            "latest_message": "",
            "has_support_reply": False,
            "message_count": 0,
            "thread_context": "",
        }

    # True only if the last message is from @flowmingo.ai
    # (meaning support already replied — nothing left to draft)
    last_msg = messages[-1]
    has_support_reply = (
        any(d in last_msg.get("from", "").lower() for d in SUPPORT_DOMAINS)
        and "DRAFT" not in last_msg.get("labels", [])
    )

    latest = messages[-1]
    latest_body = (latest.get("body") or latest.get("snippet", ""))[:1000]
    attachments = latest.get("attachments", [])

    prior_context = ""
    if len(messages) > 1:
        parts = []
        for msg in messages[:-1]:
            is_support = any(d in msg.get("from", "").lower() for d in SUPPORT_DOMAINS)
            sender = "Support" if is_support else msg.get("from", "").split("<")[0].strip()[:15]
            snippet = (msg.get("body") or msg.get("snippet", ""))[:100].replace("\n", " ")
            parts.append(f"[{msg.get('date', '')[:10]}] {sender}: {snippet}")
        prior_context = " | ".join(parts)[:500]

    return {
        "id": email_meta["id"],
        "thread_id": email_meta["thread_id"],
        "from": email_meta["from"],
        "subject": email_meta["subject"],
        "date": email_meta["date"],
        "message_count": len(messages),
        "has_support_reply": has_support_reply,
        "latest_message": latest_body,
        "attachments": attachments,
        "thread_context": prior_context,
    }


def _handle_get_email_batch(args: dict) -> list[types.TextContent]:
    import state
    import hashlib

    max_results = min(args.get("max_results", 500), 500)

    # 1. Single metadata-only list call
    emails = gmail_client.list_emails(max_results=max_results, query="is:unread in:inbox")
    if emails and isinstance(emails[0], dict) and "error" in emails[0]:
        return [types.TextContent(type="text", text=json.dumps(emails[0], indent=2))]

    # 2. Filter already-processed
    processed_ids = set(state.load_state().get("emails", {}).keys())
    already_count = sum(1 for e in emails if e.get("id") in processed_ids)
    new_emails = [e for e in emails if e.get("id") not in processed_ids]

    # 3. Thread dedup — list_emails is newest-first; first occurrence = most recent
    seen_threads: dict = {}
    for e in new_emails:
        tid = e.get("thread_id") or e["id"]
        if tid not in seen_threads:
            seen_threads[tid] = e
    deduped = list(seen_threads.values())
    thread_dedup_count = len(new_emails) - len(deduped)

    # 4. Pre-classify no-reply from metadata only (no thread fetch needed)
    NO_REPLY_FROM = [
        "noreply", "no-reply", "notifications@", "bounce@",
        "mailer-daemon", "donotreply", "do-not-reply", "postmaster@",
    ]
    NO_REPLY_SUBJECT = [
        "verification code", "otp:", "unsubscribe", "auto-reply",
        "out of office", "delivery status notification", "mail delivery failed",
    ]
    to_fetch, auto_skipped = [], []
    for e in deduped:
        from_lower = e.get("from", "").lower()
        subj_lower = e.get("subject", "").lower()
        skip_reason = None
        if any(p in from_lower for p in NO_REPLY_FROM):
            skip_reason = f"automated sender: {e.get('from', '')}"
        elif any(p in subj_lower for p in NO_REPLY_SUBJECT):
            skip_reason = f"automated subject: {e.get('subject', '')}"
        if skip_reason:
            auto_skipped.append({**e, "skip_reason": skip_reason})
        else:
            to_fetch.append(e)

    # 5. Fetch compact thread summaries server-side (Python calls, not MCP tool calls)
    to_process, fetch_errors = [], []
    for e in to_fetch:
        try:
            thread_data = gmail_client.get_thread(e["thread_id"])
            to_process.append(_compact_thread_summary(thread_data, e))
        except Exception as ex:
            fetch_errors.append({"id": e["id"], "subject": e.get("subject", ""), "error": str(ex)})

    # 6. KB version hash (for stale draft detection in /refresh-drafts)
    sop_text = knowledge.load_all()
    kb_version = hashlib.sha256(sop_text.encode()).hexdigest()[:12]

    # 7. KB query hint — combined subjects+snippets for a single get_kb_for_email call
    kb_query_hint = " | ".join(
        f"{e.get('subject', '')} {e.get('latest_message', '')[:80]}"
        for e in to_process
    )[:2000]

    result = {
        "to_process": to_process,
        "auto_skipped": auto_skipped,
        "already_processed_count": already_count,
        "thread_dedup_count": thread_dedup_count,
        "fetch_errors": fetch_errors,
        "kb_version": kb_version,
        "kb_query_hint": kb_query_hint,
        "summary": (
            f"{len(to_process)} to process, "
            f"{len(auto_skipped)} auto-skipped (no-reply), "
            f"{already_count} already processed, "
            f"{thread_dedup_count} thread duplicates removed"
        ),
    }
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_submit_drafts(args: dict) -> list[types.TextContent]:
    import state

    drafts = args.get("drafts", [])
    no_reply_items = args.get("no_reply_items", [])
    results: dict = {"created": [], "no_reply_processed": 0, "failed": []}

    # Handle no-reply emails (label + mark read + log, no draft)
    for item in no_reply_items:
        try:
            gmail_client.apply_labels(item["id"], ["FM/no-reply"])
            gmail_client.mark_as_read(item["id"])
            stats.log_processing(
                email_id=item["id"],
                input_tokens=0,
                output_tokens=0,
                subject=item.get("subject", ""),
                from_addr=item.get("from", ""),
                scenario="no-reply",
                topic="automated",
                urgency="normal",
                review_status="no-reply",
            )
            results["no_reply_processed"] += 1
        except Exception as ex:
            results["failed"].append({"id": item["id"], "error": str(ex)})

    # Handle drafts (create + label + mark read + save state + log)
    for draft in drafts:
        eid = draft.get("email_id", "")
        try:
            body = draft.get("body", "")
            dr = gmail_client.create_draft(
                to=draft["to"],
                subject=draft["subject"],
                body=body,
                thread_id=draft.get("thread_id"),
            )
            label = draft.get("label", "FM/ready")
            gmail_client.apply_labels(eid, [label])
            gmail_client.mark_as_read(eid)

            est_output = max(len(body) // 4, 50)

            state.save_email(
                email_id=eid,
                thread_id=draft.get("thread_id", ""),
                from_addr=draft.get("from_addr", ""),
                subject=draft.get("subject", ""),
                date=draft.get("date", ""),
                sender_type=draft.get("sender_type", ""),
                topic=draft.get("topic", ""),
                scenario=draft.get("scenario", ""),
                urgency=draft.get("urgency", "normal"),
                review_status=draft.get("review_status", "ready"),
                draft_id=dr.get("draft_id", ""),
                draft_message_id=dr.get("message_id", ""),
                kb_version=draft.get("kb_version", ""),
                labels_applied=[label],
            )
            stats.log_processing(
                email_id=eid,
                input_tokens=draft.get("estimated_input_tokens", 500),
                output_tokens=est_output,
                subject=draft.get("subject", ""),
                from_addr=draft.get("from_addr", ""),
                scenario=draft.get("scenario", ""),
                topic=draft.get("topic", ""),
                urgency=draft.get("urgency", "normal"),
                review_status=draft.get("review_status", "ready"),
            )
            results["created"].append({
                "id": eid,
                "draft_id": dr.get("draft_id"),
                "label": label,
            })
        except Exception as ex:
            results["failed"].append({"id": eid, "error": str(ex)})

    return [types.TextContent(type="text", text=json.dumps(results, indent=2))]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


# ── Daily report handlers ─────────────────────────────────────────────────────

def _handle_upsert_daily_report_rows(args: dict) -> list[types.TextContent]:
    rows = args.get("rows", [])
    result = sheets_client.upsert_daily_report_rows(rows)
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_check_report_complete(args: dict) -> list[types.TextContent]:
    result = sheets_client.check_report_complete(args["date"])
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_get_report_summary(args: dict) -> list[types.TextContent]:
    result = sheets_client.get_daily_summary(args["date"])
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_set_report_config(args: dict) -> list[types.TextContent]:
    result = sheets_client.set_report_config(
        date_str=args["date"],
        total_completed=args["total_completed"],
        total_started=args["total_started"],
    )
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


def _handle_send_report_dm(args: dict) -> list[types.TextContent]:
    """
    Build and send the boss DM via Slack. Idempotent — skips if dm_sent_at is set.
    The skill passes user_id; this handler builds the message text and delegates
    to slack_send_message (MCP Slack tool) — but since MCP tools can't call other
    MCP tools directly, this handler returns the formatted DM text so the skill
    can forward it to slack_send_message itself.
    """
    from datetime import datetime, timezone

    date_str  = args["date"]
    user_id   = args["user_id"]
    sheet_url = args.get("sheet_url", "")

    # Check idempotency — read dm_sent_at from Summary tab
    try:
        service = sheets_client.get_service()
        spreadsheet_id = sheets_client.get_sheet_id()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheets_client.DR_SUMMARY_TAB}'!A:S",
        ).execute()
        rows = result.get("values", [])
        for row in rows[1:]:
            row_padded = row + [""] * (len(sheets_client.DR_SUMMARY_HEADERS) - len(row))
            row_dict = dict(zip(sheets_client.DR_SUMMARY_HEADERS, row_padded))
            if row_dict.get("date") == date_str and row_dict.get("dm_sent_at"):
                return [types.TextContent(type="text", text=json.dumps({
                    "skipped": True, "reason": "DM already sent", "dm_sent_at": row_dict["dm_sent_at"]
                }))]
    except Exception:
        pass  # If summary tab missing, proceed

    # Get completion status
    completion = sheets_client.check_report_complete(date_str)
    if not completion.get("complete"):
        return [types.TextContent(type="text", text=json.dumps({
            "error": "Report not yet complete",
            "pending": completion.get("pending", "?"),
            "total": completion.get("total", "?"),
        }))]

    # Get counts
    summary = sheets_client.get_daily_summary(date_str)
    cfg     = sheets_client.get_report_config(date_str)

    total_completed = cfg.get("total_completed")
    total_started   = cfg.get("total_started")
    total_included  = summary.get("total_included", 0)
    total_excluded  = summary.get("total_excluded", 0)

    pct_completed = f"{round(total_included / total_completed * 100, 2)}%" if total_completed else "TBD"
    pct_started   = f"{round(total_included / total_started   * 100, 2)}%" if total_started   else "TBD"

    # Format date for display (e.g. Mar 24)
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        display_date = d.strftime("%b %-d") if hasattr(d, "strftime") else date_str
    except Exception:
        display_date = date_str

    lines = [
        f":white_check_mark: Daily Bug Report — {display_date} (APPROVED)",
        "",
        f"Total bugs: {total_included}",
        f"  Stage 1 — Before interview: {summary.get('stage1', 0)}",
        f"  Stage 2 — During interview: {summary.get('stage2', 0)}",
        f"  Stage 3 — After interview: {summary.get('stage3', 0)}",
        f"  Other (Company): {summary.get('other_company', 0)}",
        f"  Other (Candidate): {summary.get('other_candidate', 0)}",
        "",
        f"Excluded: {total_excluded}  (User Error: {summary.get('total_user_error', 0)}, Borderline: {summary.get('total_borderline', 0)})",
        "",
        f"Out of {total_completed or 'TBD'} completed ({pct_completed})",
        f"Out of {total_started or 'TBD'} started ({pct_started})",
    ]
    if sheet_url:
        lines.append(f"\nSheet: {sheet_url}")

    dm_text = "\n".join(lines)

    # Record dm_sent_at in Summary tab
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary_row = {**summary, "dm_sent_at": now_iso, "completion_status": "complete"}
    sheets_client.write_daily_summary(date_str, summary_row)

    return [types.TextContent(type="text", text=json.dumps({
        "ok": True,
        "user_id": user_id,
        "dm_text": dm_text,
        "dm_sent_at": now_iso,
        "note": "Call slack_send_message with channel=user_id and the dm_text to deliver the DM.",
    }, indent=2))]


if __name__ == "__main__":
    asyncio.run(main())
