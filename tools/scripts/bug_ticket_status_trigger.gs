/**
 * Bug Ticket Status Update — Gmail Draft Creator
 *
 * When you change the Status cell (column C) in the Bug Tickets sheet,
 * this script automatically creates a Gmail draft reply in the customer's
 * original thread with an HTML status update email.
 *
 * Triggers on: Verified, Fix in Progress, Resolved
 * Does NOT trigger on: Reported (that draft is created by Claude)
 *
 * HOW TO INSTALL:
 *   1. Open your Bug Tickets Google Sheet
 *   2. Extensions > Apps Script
 *   3. Paste this entire file, replacing any existing code
 *   4. Save (Ctrl+S)
 *   5. Click the clock icon (Triggers) in the left sidebar
 *   6. Click "Add Trigger" (bottom right)
 *   7. Settings:
 *        Function:        onStatusChange
 *        Deployment:      Head
 *        Event source:    From spreadsheet
 *        Event type:      On edit
 *   8. Click Save → approve the permissions popup
 *
 * NOTE: Must be an installable trigger (not the simple onEdit function)
 * because GmailApp requires authorization.
 */

const SHEET_NAME    = "Bug Tickets";
const STATUS_COL    = 3;    // Column C
const COMPANY_NAME  = "Flowmingo";
const AGENT_NAME    = "Jessica";
const SUPPORT_EMAIL = "support@flowmingo.com";

// Statuses that trigger a customer draft (Reported is handled by Claude)
const DRAFT_STATUSES = ["Verified", "Fix in Progress", "Resolved"];

// Column positions (1-based) — must match sheets_client.py
const COL = {
  DATE:        1,   // A
  TICKET_ID:   2,   // B
  STATUS:      3,   // C
  PRIORITY:    4,   // D
  SUMMARY_VI:  5,   // E
  GMAIL_LINK:  6,   // F
  EMAIL:       7,   // G
  NOTES:       8,   // H
  SUMMARY_EN:  9,   // I
  CUSTOMER:   10,   // J
  SUBJECT:    11,   // K
  ISSUE_TYPE: 12,   // L
  SLACK_MSG:  13,   // M
  DRAFT_ID:   14,   // N
  THREAD_ID:  15,   // O
  SENT_AT:    16,   // P
};


function onStatusChange(e) {
  const range = e.range;
  const sheet = range.getSheet();

  if (sheet.getName() !== SHEET_NAME) return;
  if (range.getColumn() !== STATUS_COL) return;
  if (range.getRow() === 1) return;  // skip header

  const newStatus = range.getValue();
  if (!DRAFT_STATUSES.includes(newStatus)) return;

  // Read the full row
  const row = sheet.getRange(range.getRow(), 1, 1, 16).getValues()[0];
  const ticketId     = row[COL.TICKET_ID  - 1];
  const customerName = row[COL.CUSTOMER   - 1];
  const subject      = row[COL.SUBJECT    - 1];
  const issueSummary = row[COL.SUMMARY_EN - 1];  // use EN summary for email body
  const threadId     = row[COL.THREAD_ID  - 1];

  if (!threadId) {
    Logger.log(`Row ${range.getRow()}: no thread ID — skipping.`);
    return;
  }

  const htmlBody     = buildStatusEmail(newStatus, ticketId, customerName, issueSummary);
  const plainBody    = stripHtml(htmlBody);
  const replySubject = String(subject).startsWith("Re:") ? subject : "Re: " + subject;

  try {
    const thread      = GmailApp.getThreadById(threadId);
    const messages    = thread.getMessages();
    const lastMessage = messages[messages.length - 1];
    lastMessage.createDraftReply(plainBody, { htmlBody: htmlBody, subject: replySubject });
    Logger.log(`Draft created for ${ticketId} — status: ${newStatus}`);
  } catch (err) {
    Logger.log(`Error creating draft for ${ticketId}: ${err}`);
    SpreadsheetApp.getUi().alert(`Could not create draft for ${ticketId}:\n${err}`);
  }
}


// ---------------------------------------------------------------------------
// Template builder
// ---------------------------------------------------------------------------

function buildStatusEmail(status, ticketCode, customerName, issueSummary) {
  const cfg = {
    "Verified": {
      headline:  "Your issue has been verified",
      subline:   "We've confirmed the problem and it's in our fix queue.",
      bodyText:  `We wanted to let you know that we've reviewed your report and successfully reproduced the issue on our end. Your ticket has been marked as verified and added to our engineering fix queue.`,
      nextSteps: `&bull; Our engineering team will now investigate and implement a fix.<br>
                  &bull; We'll send you another update once a fix is in progress.<br>
                  &bull; No action is needed from you at this stage.`,
      step: 2,
    },
    "Fix in Progress": {
      headline:  "A fix is in progress",
      subline:   "Our engineering team is actively working on this.",
      bodyText:  `Good news — our engineering team has started working on a fix for the issue you reported. We're making active progress and will notify you as soon as it's resolved.`,
      nextSteps: `&bull; Our team is actively developing and testing a fix.<br>
                  &bull; We'll notify you as soon as the fix is deployed.<br>
                  &bull; If you have any additional details that might help, feel free to reply.`,
      step: 3,
    },
    "Resolved": {
      headline:  "Your issue has been resolved",
      subline:   "The fix has been deployed. Please verify everything is working.",
      bodyText:  `We're happy to let you know that the issue you reported has been fixed and the update has been deployed. You should no longer experience this problem.`,
      nextSteps: `&bull; Please try the action that was failing and confirm it now works as expected.<br>
                  &bull; If you still experience any issues, reply to this email and we'll investigate immediately.<br>
                  &bull; Thank you for taking the time to report this — your feedback helps us improve the platform.`,
      step: 4,
    },
  }[status];

  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Ticket Update</title>
</head>
<body style="margin:0; padding:0; background:#f5f7fb; font-family:Arial, Helvetica, sans-serif; color:#1f2937;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f5f7fb; padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="background:#ffffff; border-radius:12px; overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="padding:28px 32px 16px; background:#111827; color:#ffffff;">
              <div style="font-size:22px; font-weight:bold;">${cfg.headline}</div>
              <div style="margin-top:8px; font-size:14px; color:#d1d5db;">${cfg.subline}</div>
            </td>
          </tr>

          <!-- Ticket code -->
          <tr>
            <td style="padding:24px 32px 8px;">
              <div style="font-size:13px; color:#6b7280; margin-bottom:8px;">Ticket code</div>
              <div style="display:inline-block; background:#f3f4f6; border:1px solid #e5e7eb; border-radius:8px; padding:12px 16px; font-size:22px; font-weight:bold; letter-spacing:1px; color:#111827;">
                ${ticketCode}
              </div>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:8px 32px 8px; font-size:15px; line-height:1.6;">
              Hi ${customerName},<br><br>
              ${cfg.bodyText}
            </td>
          </tr>

          <!-- Issue summary -->
          <tr>
            <td style="padding:8px 32px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e5e7eb; border-radius:10px;">
                <tr>
                  <td style="padding:12px 16px; font-size:14px;"><strong>Issue summary:</strong> ${issueSummary}</td>
                </tr>
                <tr>
                  <td style="padding:12px 16px; font-size:14px; border-top:1px solid #e5e7eb;"><strong>Status:</strong> ${status}</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Progress bar -->
          <tr>
            <td style="padding:24px 32px 8px;">
              <div style="font-size:14px; font-weight:bold; margin-bottom:12px;">Current progress</div>
              ${buildProgressBar(cfg.step)}
            </td>
          </tr>

          <!-- What happens next -->
          <tr>
            <td style="padding:20px 32px 8px;">
              <div style="font-size:14px; font-weight:bold; margin-bottom:8px;">What happens next</div>
              <div style="font-size:14px; line-height:1.8; color:#374151;">${cfg.nextSteps}</div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 32px 32px; font-size:14px; line-height:1.7; color:#4b5563;">
              Let us know if you have any questions,<br>
              ${AGENT_NAME}<br>
              ${COMPANY_NAME}<br>
              ${SUPPORT_EMAIL}
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>`;
}


// ---------------------------------------------------------------------------
// Progress bar (activeStep: 1=Reported 2=Verified 3=Fix in Progress 4=Resolved)
// ---------------------------------------------------------------------------

function buildProgressBar(activeStep) {
  const steps  = ["Reported", "Verified", "Fix in Progress", "Resolved"];
  const ACTIVE = "#2563eb";
  const DONE   = "#1d4ed8";
  const EMPTY  = "#e5e7eb";

  const labelCells = steps.map((s, i) => {
    const color  = i + 1 <= activeStep ? "#111827" : "#6b7280";
    const weight = i + 1 === activeStep ? "bold" : "normal";
    return `<td align="center" style="font-size:12px; color:${color}; font-weight:${weight};">${s}</td>`;
  }).join("");

  const barCells = steps.map((s, i) => {
    const bg          = i + 1 < activeStep ? DONE : i + 1 === activeStep ? ACTIVE : EMPTY;
    const leftRadius  = i === 0                ? "border-radius:999px 0 0 999px;" : "";
    const rightRadius = i === steps.length - 1 ? "border-radius:0 999px 999px 0;" : "";
    return `<td width="25%" style="height:8px; background:${bg}; ${leftRadius}${rightRadius}"></td>`;
  }).join("");

  return `<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
    <tr>${labelCells}</tr>
    <tr>
      <td colspan="4" style="padding-top:10px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
          <tr>${barCells}</tr>
        </table>
      </td>
    </tr>
  </table>`;
}


// ---------------------------------------------------------------------------
// Strip HTML for plain-text fallback
// ---------------------------------------------------------------------------

function stripHtml(html) {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}
