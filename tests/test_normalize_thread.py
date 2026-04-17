"""
Tests for _has_unreplied_support_reply() in process_emails_openai.py.

Run with: python -m pytest tests/test_normalize_thread.py -v
"""
import sys
from pathlib import Path

# Add script directory to path so we can import the function
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "scripts"))

from process_emails_openai import _has_unreplied_support_reply


def make_msg(from_addr: str, labels: list) -> dict:
    return {"from": from_addr, "labels": labels, "body": ""}


SUPPORT = "support@flowmingo.ai"
CUSTOMER = "customer@gmail.com"


def test_empty_thread():
    """No messages — no support reply."""
    assert _has_unreplied_support_reply([]) is False


def test_single_customer_message():
    """Single inbound customer email — no support reply exists."""
    msgs = [make_msg(CUSTOMER, ["INBOX", "UNREAD"])]
    assert _has_unreplied_support_reply(msgs) is False


def test_support_reply_is_last_message():
    """Support replied last, customer hasn't responded — should flag."""
    msgs = [
        make_msg(CUSTOMER, ["INBOX"]),
        make_msg(SUPPORT, ["SENT"]),
    ]
    assert _has_unreplied_support_reply(msgs) is True


def test_customer_replied_after_support():
    """Customer sent a new message after support replied — should NOT flag."""
    msgs = [
        make_msg(CUSTOMER, ["INBOX"]),
        make_msg(SUPPORT, ["SENT"]),
        make_msg(CUSTOMER, ["INBOX", "UNREAD"]),
    ]
    assert _has_unreplied_support_reply(msgs) is False


def test_contact_form_via_flowmingo_no_sent_label():
    """Contact form email has 'flowmingo.ai' in FROM but INBOX label — inbound, not support reply."""
    msgs = [make_msg("Victor Campher via Contact <contact@flowmingo.ai>", ["INBOX", "UNREAD"])]
    assert _has_unreplied_support_reply(msgs) is False


def test_draft_excluded_from_support_reply():
    """A draft reply (DRAFT label) should not count as a sent support reply."""
    msgs = [
        make_msg(CUSTOMER, ["INBOX", "UNREAD"]),
        make_msg(SUPPORT, ["DRAFT"]),
    ]
    assert _has_unreplied_support_reply(msgs) is False


def test_multiple_exchanges_last_is_customer():
    """Multi-turn thread where customer has the last word — no flag needed."""
    msgs = [
        make_msg(CUSTOMER, ["INBOX"]),
        make_msg(SUPPORT, ["SENT"]),
        make_msg(CUSTOMER, ["INBOX"]),
        make_msg(SUPPORT, ["SENT"]),
        make_msg(CUSTOMER, ["INBOX", "UNREAD"]),
    ]
    assert _has_unreplied_support_reply(msgs) is False
