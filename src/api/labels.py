"""Flowmingo label definitions for the Gmail support assistant."""

# Three labels applied to processed Gmail messages.
LABELS = [
    "FM/ready",     # High-confidence SOP match — draft is ready to send
    "FM/review",    # Needs human review before sending (reason in draft body)
    "FM/no-reply",  # No reply needed — automated, newsletter, vendor pitch, etc.
    "FM/bug",       # Bug report — ticket created, tracked in Google Sheet
]

# Colors applied when labels are created (Gmail allowed palette).
LABEL_COLORS = {
    "FM/ready":    {"backgroundColor": "#16a765", "textColor": "#ffffff"},  # green
    "FM/review":   {"backgroundColor": "#f2c960", "textColor": "#594c05"},  # amber
    "FM/no-reply": {"backgroundColor": "#999999", "textColor": "#ffffff"},  # gray
    "FM/bug":      {"backgroundColor": "#cc3a21", "textColor": "#ffffff"},  # red
}
