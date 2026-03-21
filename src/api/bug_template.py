"""Bug ticket acknowledgment email template renderer."""

_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>Ticket Received</title>
</head>
<body style="margin:0; padding:0; background:#f5f7fb; font-family:Arial, Helvetica, sans-serif; color:#1f2937;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:#f5f7fb; padding:24px 0;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="background:#ffffff; border-radius:12px; overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="padding:28px 32px 16px; background:#111827; color:#ffffff;">
              <div style="font-size:22px; font-weight:bold;">We've received your ticket</div>
              <div style="margin-top:8px; font-size:14px; color:#d1d5db;">
                Our team has logged your request and will keep you updated.
              </div>
            </td>
          </tr>

          <!-- Ticket code -->
          <tr>
            <td style="padding:24px 32px 8px;">
              <div style="font-size:13px; color:#6b7280; margin-bottom:8px;">Ticket code</div>
              <div style="display:inline-block; background:#f3f4f6; border:1px solid #e5e7eb; border-radius:8px; padding:12px 16px; font-size:22px; font-weight:bold; letter-spacing:1px; color:#111827;">
                {ticket_code}
              </div>
            </td>
          </tr>

          <!-- Intro -->
          <tr>
            <td style="padding:8px 32px 8px; font-size:15px; line-height:1.6;">
              Hi {customer_name},<br><br>
              Thank you for contacting {company_name}. We've successfully received your request and created a support ticket for it.
            </td>
          </tr>

          <!-- Ticket details -->
          <tr>
            <td style="padding:8px 32px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border:1px solid #e5e7eb; border-radius:10px;">
                <tr>
                  <td style="padding:12px 16px; font-size:14px; border-bottom:1px solid #e5e7eb;"><strong>Issue type:</strong> {issue_type}</td>
                </tr>
                <tr>
                  <td style="padding:12px 16px; font-size:14px; border-bottom:1px solid #e5e7eb;"><strong>Issue summary:</strong> {issue_summary}</td>
                </tr>
                <tr>
                  <td style="padding:12px 16px; font-size:14px; border-bottom:1px solid #e5e7eb;"><strong>Submitted on:</strong> {submitted_at}</td>
                </tr>
                <tr>
                  <td style="padding:12px 16px; font-size:14px;"><strong>Next update:</strong> {next_update_eta}</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Progress bar -->
          <tr>
            <td style="padding:24px 32px 8px;">
              <div style="font-size:14px; font-weight:bold; margin-bottom:12px;">Current progress</div>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td align="center" style="font-size:12px; color:#111827; font-weight:bold;">Reported</td>
                  <td align="center" style="font-size:12px; color:#6b7280;">Verified</td>
                  <td align="center" style="font-size:12px; color:#6b7280;">Fix in Progress</td>
                  <td align="center" style="font-size:12px; color:#6b7280;">Resolved</td>
                </tr>
                <tr>
                  <td colspan="4" style="padding-top:10px;">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td width="25%" style="height:8px; background:#2563eb; border-radius:999px 0 0 999px;"></td>
                        <td width="25%" style="height:8px; background:#e5e7eb;"></td>
                        <td width="25%" style="height:8px; background:#e5e7eb;"></td>
                        <td width="25%" style="height:8px; background:#e5e7eb; border-radius:0 999px 999px 0;"></td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- While you wait: troubleshooting steps -->
          <tr>
            <td style="padding:20px 32px 8px;">
              <div style="font-size:14px; font-weight:bold; margin-bottom:6px;">In the meantime, a few things that may help</div>
              <div style="font-size:13px; color:#6b7280; margin-bottom:10px;">We know this is frustrating. These steps often resolve the issue while we investigate:</div>
              <div style="font-size:14px; line-height:1.9; color:#374151;">
                {troubleshooting_steps}
              </div>
            </td>
          </tr>

          <!-- Your original message -->
          <tr>
            <td style="padding:12px 32px 8px;">
              <div style="font-size:13px; color:#6b7280; margin-bottom:6px;">Your original message</div>
              <div style="background:#f9fafb; border-left:3px solid #d1d5db; padding:12px 16px; font-size:13px; line-height:1.6; color:#6b7280; font-style:italic; border-radius:0 6px 6px 0;">
                {original_message}
              </div>
            </td>
          </tr>

          <!-- What happens next -->
          <tr>
            <td style="padding:20px 32px 8px;">
              <div style="font-size:14px; font-weight:bold; margin-bottom:8px;">What happens next</div>
              <div style="font-size:14px; line-height:1.8; color:#374151;">
                &bull; Our team is reviewing your report<br>
                &bull; We'll update you once there is progress<br>
                &bull; If we need more details, we'll contact you directly
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 32px 32px; font-size:14px; line-height:1.7; color:#4b5563;">
              Thank you,<br>
              {agent_name}<br>
              {company_name}<br>
              {support_email}
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

# Company defaults
_COMPANY_NAME = "Flowmingo"
_AGENT_NAME = "Jessica"
_SUPPORT_EMAIL = "support@flowmingo.ai"


def _format_steps(steps: list) -> str:
    """Convert a list of step strings into HTML bullet lines."""
    return "".join(f"&bull; {s}<br>\n" for s in steps)


def _escape(text: str) -> str:
    """HTML-escape plain text for safe inline use."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\r\n", "<br>")
            .replace("\n", "<br>")
    )


def render_acknowledgment(
    ticket_code: str,
    customer_name: str,
    issue_type: str,
    submitted_at: str,
    issue_summary: str,
    troubleshooting_steps: list,
    original_message: str,
    next_update_eta: str = "Within 2 business days",
    company_name: str = _COMPANY_NAME,
    agent_name: str = _AGENT_NAME,
    support_email: str = _SUPPORT_EMAIL,
) -> str:
    """Render the bug ticket acknowledgment HTML email."""
    return _TEMPLATE.format(
        ticket_code=ticket_code,
        customer_name=_escape(customer_name),
        issue_type=_escape(issue_type),
        submitted_at=submitted_at,
        next_update_eta=next_update_eta,
        issue_summary=_escape(issue_summary),
        troubleshooting_steps=_format_steps(troubleshooting_steps),
        original_message=_escape(original_message),
        company_name=company_name,
        agent_name=agent_name,
        support_email=support_email,
    )
