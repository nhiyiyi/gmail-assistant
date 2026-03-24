---
name: process-emails
description: Process unread Flowmingo support emails and create Gmail draft replies following the SOP. Bug reports get a ticket ID, HTML draft, and a Google Sheet entry. Drafts appear in Gmail for human review — never auto-sends.
---

# Purpose

Read unread inbox emails, classify each into one of four tiers, create Gmail draft
replies where needed, apply labels, mark as read, and log history.

Never send. Only create drafts for human review in Gmail.

Bug reports get special treatment: a unique ticket ID (BUG-YYMMDD-SEQ), an HTML
acknowledgment draft, an FM/bug Gmail label, and a row in the Google Sheet.

# When to use

- Process the current batch of unread support emails
- Runs automatically every 3 hours via cron

# Workflow

## Step 1 — Setup

Call `setup_labels` to ensure FM/ready, FM/review, FM/no-reply exist in Gmail.

## Step 2 — Fetch email batch

Call `get_email_batch` with max_results: 100.

This single call handles server-side: filtering already-processed emails, deduplicating
threads, pre-classifying no-reply senders, and fetching compact thread summaries.

Returns:
- `to_process` — compact email summaries needing a draft reply
- `auto_skipped` — no-reply/automated emails (no draft needed)
- `already_processed_count`, `thread_dedup_count`
- `kb_version` — store this, used when building draft objects
- `kb_query_hint` — use this as input to get_kb_for_email

If `to_process` and `auto_skipped` are both empty: report the summary and stop.

## Step 3 — Prepare groups

Divide `to_process` into groups of 8 (oldest first). KB retrieval happens per group in Step 4.

## Step 4 — Classify and draft all emails (in groups of 8)

Work through `to_process` in groups of 8 emails (oldest first).

At the start of each group, call `get_kb_for_email` with:
- email_text: concatenated subjects + latest_message snippets for the 8 emails in this group
  (format: `"<subject>: <latest_message[:200]>"` per email, newline-separated)
- top_k: 5

Use the returned KB text for all drafts in this group only.

Then, for this group, do ALL classification and drafting in a single response with NO tool calls:

### 4a — Classify each email

For each email in the group, evaluate these six dimensions before assigning a classification:

**D1 — Sender intent:** What is the person actually asking or doing?
- Question/request: They need something done or answered. A reply is expected.
- Statement — brand moment: They are concluding an interaction, sharing a positive outcome, expressing satisfaction, confirming acceptance, announcing a withdrawal, or reporting a completion milestone. No question is asked, but a warm reply closes the loop and is the right move. Route through scenario matching (S15, S16, S18, S34).
- Statement — disengaged: They are sharing a view or opinion with no relational signal and no interaction milestone. No reply needed. Examples: "I don't find suitable roles right now." / "I already have a job." / "I'm not interested."
- Technical report: They are describing a malfunction of the Flowmingo platform — something the system did wrong, not just user confusion.
- Legal/sensitive demand: They are asserting rights, making threats, or demanding actions with legal, compliance, or reputational implications.

**D2 — Context completeness:** Do we have all the information needed to respond accurately?
- Full: Everything needed is in the current email and thread.
- Partial or missing: The email refers to conversations made outside the visible thread — e.g., "as we discussed on WhatsApp", "following up on our call", "as mentioned in the invitation", "given what was discussed". We cannot see what was previously said or agreed.

**D3 — KB (SOP) coverage:** Can the SOP produce a correct, complete, and non-fabricated reply?
- Fully covered: A clear scenario matches this email and the reply can be written entirely from that guidance.
- Partially covered: The SOP has relevant guidance but does not fully address the specific situation, or two rules give conflicting direction.
- Not covered: No scenario in the SOP applies at all.
- Fabrication risk: The topic exists broadly in the KB (e.g. pricing, timeline, platform capabilities) but the specific claim the customer is asking about is NOT stated in the KB. For example, asking about role salary, or whether Flowmingo will charge in the future — these sound answerable but would require inventing facts not present in the KB.

**D4 — Technical defect type:** Is there any signal that the platform didn't work as expected?
- Bug signal: The person says the platform did something wrong OR they tried to do something on the platform and it failed — whether they can quote an exact error or not. This includes specific error messages ("Status failed 400"), vague complaints ("I couldn't access my interview", "it didn't work", "I had a problem completing it"), and any report of unexpected behavior during a session. If the person is saying "I tried and it failed" rather than "I don't know how to do this", D4 = Bug signal.
- Not a bug: Clear user-side confusion (how-to question, doesn't know how to use a feature), extension/retake requests, or a link-access issue where the person has not yet tried basic troubleshooting and no error message is reported (e.g., "my link is expired", "my link shows 404" with nothing further).

**D5 — Sensitivity level:** Does this email require extra caution?
- Normal: Standard support interaction. No legal, ethical, or reputational risk.
- Elevated: The email touches on topics where a wrong or fabricated answer could mislead the customer, create legal exposure, or damage trust. This includes: role compensation and salary details (never in KB), future pricing commitments ("will it always be free?"), timeline guarantees beyond what the SOP authorizes, and platform capabilities not described in the SOP.
- Critical: The email demands legal action, asserts GDPR rights to stop processing or delete data, contains discrimination claims, threatens legal action, or explicitly demands no further contact.

**D6 — Thread already handled:** Has support already replied in this thread?
- Yes: The email summary has `has_support_reply: true`. No further reply needed.
- No: The thread has not been replied to by support.

---

**Classification rules:**

**FM/no-reply** — No draft. Add to no_reply batch.

Apply when D6 = Yes (thread already has a support reply), OR when D1 = Statement — disengaged. A disengaged statement expresses a view or opinion with no relational signal and no interaction milestone — no question, no milestone, no outcome being shared.

Examples that ARE FM/no-reply: "I don't find any suitable role at the moment." / "I'm not interested in this opportunity." / "I already have a job." — disengaged, nothing to close.

Examples that are NOT FM/no-reply: "I don't find any suitable role. Could you keep me in mind?" — has a request (FM/ready S17); "I'm not interested. Please remove me from your list." — has a demand (FM/review R1); "I loved the experience, thank you!" — brand moment (FM/ready S15); "I accept the offer." — brand moment (FM/ready S34); "I've completed my interview." — milestone (FM/ready S18); "I'm withdrawing my application, thanks." — brand moment (FM/ready S16).

Also applies to: newsletters, marketing emails, automated notifications, vendor pitches with no question.

---

**FM/bug** — Set aside for Step 6 (create_bug_ticket). Do not draft a reply here.

Apply when D4 = Bug signal. This takes priority over all SOP scenarios (S6–S9, S20, etc.) — a scenario being "Fully covered" in D3 does NOT override FM/bug when D4 = Bug signal.

Two tiers — both go to create_bug_ticket:
- **Detailed**: Specific error message or clear platform behavior described (e.g., "Status failed 400", "Failed to load the interview set", "already submitted" when not finished, platform frozen, random logout, camera error after granting permissions). Full ticket details available.
- **Vague**: General failure report with no specific error described ("I couldn't access my interview", "it didn't work", "I had a problem completing it"). Create the ticket with what's available — the acknowledgment email will ask the customer for more details.

**Screenshots attached but not visible:** Classify as FM/bug and create the ticket. Note `confidence: No` to flag unseen screenshots, but do NOT downgrade. The test is whether a technical issue is being reported — not the level of detail.

---

**FM/review** — Draft with `[REVIEW NEEDED: <specific reason>]` at the top. Human must review before sending.

There are 7 distinct reasons. Each has a mandatory reason format. Never use a vague reason like "unclear email."

**R1 — Critical sensitivity (legal, GDPR, do-not-contact):** Apply when D5 = Critical. This includes: do-not-contact requests, mailing list removal demands, requests to stop processing personal data, data deletion demands unrelated to the AI program, legal threats, and discrimination claims. Do NOT write a draft reply body — the [REVIEW NEEDED] note IS the only output. A human must action the request (unsubscribe, mark DNC, escalate to legal) before any reply is composed.
Reason: `[REVIEW NEEDED: Do-not-contact / GDPR stop-processing request — requires manual unsubscribe and internal DNC flag before any reply is composed]`

**R2 — External context missing:** Apply when D2 = Partial or Missing. If the email references "our WhatsApp conversation", "our phone call", "what was discussed", "as mentioned in the invitation", or any exchange we cannot see — do not guess what was said or agreed externally.
Reason: `[REVIEW NEEDED: Email references a prior WhatsApp/phone/external conversation that is not visible in this thread — cannot determine what was previously discussed or agreed without that context]`

**R3 — No SOP scenario covers this:** Apply when D3 = Not covered. If after reading the email and KB, no scenario or rule in the SOP applies to what the person is asking, do not attempt a response.
Reason: `[REVIEW NEEDED: No SOP scenario covers this request — <describe what they asked in 5–10 words>]`

**R4 — Fabrication risk (topic exists in KB, specific claim does not):** Apply when D3 = Fabrication risk. If answering correctly would require stating something NOT written in the KB, do not answer it. The most common cases: role compensation and salary (the SOP covers partner commission rates and candidate add-on prices, but NOT salaries for any specific job role — any "what is the salary?" question is FM/review); future pricing promises (the SOP states current pricing but does NOT authorize any statement about future pricing — "will it always be free?", "are you planning to charge?" are always FM/review); platform capabilities not described in the SOP.
Reason: `[REVIEW NEEDED: Customer is asking about <topic> — this specific claim is not in the KB and cannot be stated without risk of fabrication]`

**R5 — Elevated sensitivity (compensation, future commitments):** Apply when D5 = Elevated. Compensation and future pricing are always FM/review — no exceptions, even if the KB has partial coverage on the topic. Making any forward-looking statement about pricing or any compensation claim is elevated sensitivity by default. Use the same reason format as R4.

**R6 — Conflicting or insufficient SOP guidance:** Apply when two SOP rules give conflicting direction, or when the guidance is ambiguous for this specific sub-case.
Reason: `[REVIEW NEEDED: SOP rules <X and Y> conflict on this case — <brief description>]`

**R7 — Low confidence for any other specific reason:** If you have read the email and KB and are not confident the draft is correct — escalate. The reason must be specific, not generic.
Reason: `[REVIEW NEEDED: <Specific reason — what information is missing or ambiguous>]`

---

**FM/ready** — Draft with no review flag.

Apply ONLY when ALL of the following are true: D1 = Question/request OR Statement — brand moment (there is something to answer, do, or warmly close); D2 = Full context (everything needed is in the visible email and thread); D3 = Fully covered (a clear SOP scenario covers this situation, and the reply requires no fabrication); D4 = Not a bug (if D4 = Bug signal — even vague — the email must go to FM/bug, not FM/ready; no SOP scenario overrides this); D5 = Normal (no elevated or critical flags — not compensation, not future pricing, not legal); D6 = No (support has not already replied in this thread); and you are confident the reply is correct. If any single dimension fails, escalate to FM/review with the specific reason from R1–R7.

---

**Quick edge-case reference:**

| Situation | Classification |
|-----------|---------------|
| "I don't find any suitable role" | FM/no-reply — disengaged, no request |
| "I'm not interested" / "I already have a job" | FM/no-reply — disengaged, no request |
| "I don't find any suitable role. Keep me in mind." | FM/ready (S17) — has a request |
| "Remove me from your list" | FM/review R1 — critical, DNC demand |
| "I loved the experience, thank you!" | FM/ready (S15) — brand moment, Trustpilot invite |
| "I accept the offer / I'm ready to proceed" | FM/ready (S34) — brand moment, warm acceptance close |
| "I've submitted / completed my interview" | FM/ready (S18) — milestone, timeline acknowledgment |
| "I'm withdrawing my application, thanks" | FM/ready (S16) — brand moment, warm close + JOBS_URL |
| Portal shows "already submitted", candidate has not finished | FM/bug (clear) |
| Platform returns specific error message (e.g., "Status failed 400", "Failed to load the interview set") | FM/bug (detailed) — error message is sufficient, S8 does NOT apply |
| Specific 4xx/5xx error code from the platform during interview | FM/bug (detailed) |
| Interview link fails to load after person already tried multiple browsers / incognito | FM/bug (detailed) |
| "My link doesn't work" with no error message, hasn't tried troubleshooting yet | FM/ready (S8) — no failure reported, user-side issue |
| "I couldn't do the interview" / "it didn't work" / "I had a problem" | FM/bug (vague) — ticket created with what's available |
| "I couldn't access my interview" with no error | FM/bug (vague) — ticket created, ack email asks for details |
| Clear issue described + screenshots attached | FM/bug (detailed), confidence: No |
| Prospective or current BP asking about commission, payout, tracking, employment type, or formal agreement | FM/ready (S11) — answer from Section 10 + PAYOUT_SCHEME_DOC; company ops/partner experience questions → WHATSAPP |
| "As we discussed on WhatsApp, can I still interview?" | FM/review R2 |
| "What is the salary for this role?" | FM/review R4/R5 — compensation not in KB |
| "Will Flowmingo remain free in the future?" | FM/review R4/R5 — future pricing not authorized |
| Partner asking current pricing facts only | FM/ready (S8.2) — current facts, no forward-looking claims |
| "Only shortlisted candidates will be contacted" context + timeline question | FM/ready (S18 exception) — do not give 1–2 week estimate |
| "I consent and confirm that I have read the A2 and A5 forms." | FM/ready — share AI_PROGRAM_GIFT_DASHBOARD immediately |
| Website frozen / nothing clickable | FM/bug (clear) |
| Random logout mid-session | FM/bug (clear) |

### 4b — Write the draft reply for each FM/ready and FM/review email

Follow the SOP exactly:
- `Dear <Name>,` — extract from sign-off/signature; infer from email address if no name
- Acknowledge briefly
- Address the exact issue
- Include exactly once: `Let us know if you have any questions,`
- End with: `Best regards,` — no name or title after it
- English only, no emojis, no markdown, no upselling
- Links only when the scenario explicitly requires them

For FM/review: prepend `[REVIEW NEEDED: <specific reason>]` as the very first line,
then a blank line, then the draft body.

### 4c — Build draft objects

For each FM/ready and FM/review email, create a draft object:
```
{
  email_id, thread_id, to (sender's email), subject (original),
  body (the reply text),
  label: "FM/ready" or "FM/review",
  scenario: matched SOP scenario code (e.g. "S8") or "unclear",
  topic: e.g. "technical", "candidate", "partner", "billing",
  urgency: "normal" | "urgent" | "critical",
  review_status: "ready" or "review",
  sender_type: "A" | "B" | "C" | "D" | "E",
  from_addr: sender's email address,
  date: email date from the summary,
  kb_version: the kb_version from Step 2,
  estimated_input_tokens: (len(kb_text) + len(latest_message) + len(thread_context)) / 4
}
```

## Step 5 — Submit the group

After drafting each group of 8, call `submit_drafts` with:
- `drafts`: the FM/ready and FM/review draft objects for this group
- `no_reply_items`: FM/no-reply emails from this group + auto_skipped items
  (pass auto_skipped only in the FIRST group's submit call)

Format for no_reply_items: `[{"id": "...", "from": "...", "subject": "..."}]`

After `submit_drafts` completes for the group, call `log_action_item` for **each FM/review email** in that group (one call per email):
- `action_type`: "DNC Request" for R1 (do-not-contact), "Review Draft" for all other FM/review reasons
- `priority`: "High" for R1 (DNC) and vague bugs, "Normal" for everything else
- `customer_name`, `email`, `subject`: from the email summary
- `reason`: the exact `[REVIEW NEEDED: ...]` string you wrote in the draft
- `thread_id`: from the email summary

Do NOT call `log_action_item` for FM/ready, FM/no-reply, or FM/bug emails — only FM/review.

Then continue to the next group of 8 (Step 4 again).

## Step 6 — Bug tickets (after all groups are done)

Call `create_bug_ticket` for ALL FM/bug emails — both detailed and vague.

For **detailed** bugs (specific error message or clear platform behavior described):

Call `create_bug_ticket` with:
- email_id, thread_id
- customer_name: first name from signature or greeting
- from_addr: sender's email
- subject: original subject
- issue_summary: 1–3 sentences describing the bug (in English)
- issue_summary_vi: Vietnamese translation of issue_summary (full, 1-3 sentences — for the tech team col E)
- main_issue_vi: Single Vietnamese sentence, **strictly under 10 words**, naming the core problem. Start with the affected subject (Trang / Hệ thống / Nút / Câu hỏi / Màn hình…). No filler, no "người dùng báo cáo". Examples: "Câu hỏi bị lặp lại nhiều lần trong lúc phỏng vấn." · "Trang hiển thị màn hình tải vô thời hạn sau phỏng vấn." · "Hệ thống báo lỗi 400 khi gửi kết quả phỏng vấn."
- issue_type: e.g. "Login Issue", "Feature Not Working", "Performance"
- troubleshooting_steps: 2–3 quick things to try (under 12 words each), tailored by sender type:
  - **Candidate (Type A/B):** Clear browser cache and cookies. | Try incognito/private mode. | Try a different browser (Chrome, Safari, or Edge). | Try a different device if possible.
  - **Company/Recruiter (Type D):** Try logging out and back into your Flowmingo dashboard. | Clear browser cache and try in an incognito window. | Check if the issue affects all campaigns or just one. | If candidates are affected: ask them for their interview link, device type, and browser.
- original_message: customer's message body, trimmed to ~300 chars

For **vague** bugs (no specific error described — "it didn't work", "I couldn't access", etc.):

Call `create_bug_ticket` with the same fields, but:
- issue_summary: "Customer reports [describe what they tried to do] but was unable to complete it — no specific error message provided. Details needed to reproduce." (1–2 sentences max)
- issue_summary_vi: Vietnamese translation of the above (full sentence)
- main_issue_vi: Single Vietnamese sentence <10 words. Example: "Người dùng không thể hoàn thành phỏng vấn, không rõ lỗi."
- issue_type: "Feature Not Working"
- troubleshooting_steps: ["Ask customer for device type and operating system.", "Ask customer for browser name and version.", "Ask customer for exact error message or what they saw on screen."]

Then call `mark_as_read` with the message_id.

## Step 7 — Report

After all groups and bug tickets:
- Already processed (skipped, previous run): already_processed_count
- Thread duplicates collapsed: thread_dedup_count
- Auto-skipped no-reply: list with subjects
- FM/ready: list with subject lines
- FM/review: list with subject lines and review reasons
- FM/bug: list with subject lines and ticket IDs
- FM/no-reply (detected after reading): list with subjects
- Call `get_stats` — show today's count and cost

# Rules

1. NEVER send. Drafts only.
2. Always call setup_labels (Step 1). Call get_kb_for_email once per group (at the start of Step 4) before drafting that group.
3. Never fabricate contact info, links, or policy details not in the SOP.
4. Never add extra information the customer did not ask for.
5. FM/review reason must be specific — never vague like "unclear email".
6. Process oldest-first within each group.
7. One draft per thread (has_support_reply=true → FM/no-reply, do not draft).
8. Always submit after each group of 8 — do not accumulate more than 8 unsent drafts.
9. Pass auto_skipped to no_reply_items only in the first submit_drafts call.
10. FM/ready is the goal — only escalate to FM/review when genuinely needed.

# Done condition

- All to_process emails classified and drafted
- All auto_skipped emails sent to submit_drafts as no_reply_items
- Drafts created for FM/ready and FM/review via submit_drafts
- Bug tickets created via create_bug_ticket for FM/bug emails
- FM/review drafts have specific [REVIEW NEEDED] reasons
- All emails marked as read
- Summary with label breakdown and today's cost
