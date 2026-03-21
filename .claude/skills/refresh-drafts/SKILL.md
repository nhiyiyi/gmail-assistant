---
name: refresh-drafts
description: Find all existing Gmail drafts that were created with an older version of the knowledge base, and rewrite them using the latest SOP. Use after updating knowledge/flowmingo-sop.md.
---

# Purpose

When the knowledge base (SOP) changes, existing drafts become stale. This skill
finds those stale drafts and rewrites them using the latest knowledge, so the team
can send up-to-date replies without redoing them manually.

Never sends. Only updates existing drafts.

# When to use

Use after editing any file in `knowledge/` to ensure all pending drafts reflect
the latest SOP.

# Workflow

## Step 1 — Load latest knowledge base

Call `get_knowledge_base` to load the current SOP.
Call `get_kb_version` to get the current KB version hash.

## Step 2 — Find stale drafts

Call `get_email_state` with:
- filter: `stale`
- kb_version: the hash from Step 1

If the result is empty, report "All drafts are up to date." and stop.

## Step 3 — For each stale draft entry

Process in the order they appear in the state.

### 3a — Load the original thread

Call `get_thread` using the `thread_id` from the state entry.
Read all messages in the thread to fully understand the context.

### 3b — Re-draft the reply

Using the current SOP and the full thread context, re-draft the reply following
the same rules as `/process-emails`:

- Keep the same greeting (Dear <Name>,)
- Address the same issue as the original draft
- Re-apply any scenario rules from the updated SOP
- If the scenario changed in the new SOP, use the new rules
- End with `Let us know if you have any questions,` and `Best regards,`

### 3c — Update the existing draft

Call `update_draft` with:
- draft_id: from the state entry
- to: sender's email address (from the state entry `from` field)
- subject: original subject
- body: the new draft body
- thread_id: the thread ID from the state entry

If `update_draft` returns an error (e.g. 404 — draft was already sent or deleted):
- Log it and skip — do not create a new draft
- Continue to the next stale entry

### 3d — Update state

Call `save_email_state` with all the same fields as the original state entry,
but update:
- draft_id: from the update_draft result
- draft_message_id: from the update_draft result
- kb_version: the current KB version hash

## Step 4 — Report summary

After processing all stale drafts, report:
- Total stale drafts found
- Drafts successfully refreshed (with subject lines)
- Drafts skipped (already sent/deleted) with reasons

# Rules

1. NEVER create new drafts. Only call `update_draft` on existing ones.
2. NEVER send. Drafts only.
3. If a draft was already sent or deleted (update_draft returns error), skip gracefully.
4. Apply the same SOP quality rules as `/process-emails` — no fabrication, no upselling.

# Done condition

This skill is complete when:
- All stale drafts have been checked
- Successfully refreshed drafts have updated state entries with the new kb_version
- Skipped drafts are logged with reasons
- Summary report shown
