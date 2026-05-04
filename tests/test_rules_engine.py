"""P1 unit tests for rules_engine.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "api"))

import rules_engine


def _email(
    from_addr="user@example.com",
    subject="",
    message="",
    attachments=None,
    has_support_reply=False,
):
    return {
        "from": from_addr,
        "subject": subject,
        "latest_message": message,
        "attachments": attachments or [],
        "has_support_reply": has_support_reply,
    }


class TestAlreadyReplied:
    def test_adds_already_replied_trigger(self):
        result = rules_engine.route(_email(has_support_reply=True))
        assert "already_replied" in result["risk_triggers"]

    def test_not_present_when_false(self):
        result = rules_engine.route(_email(has_support_reply=False))
        assert "already_replied" not in result["risk_triggers"]


class TestBugDetection:
    def test_image_attachment_is_bug(self):
        email = _email(attachments=[{"mimeType": "image/png", "filename": "screenshot.png"}])
        result = rules_engine.route(email)
        assert result["is_bug"] is True

    def test_hard_bug_keyword_in_message(self):
        result = rules_engine.route(_email(message="I got an error when submitting the interview"))
        assert result["is_bug"] is True

    def test_hard_bug_keyword_in_subject(self):
        result = rules_engine.route(_email(subject="Interview failed to load"))
        assert result["is_bug"] is True

    def test_status_code_error(self):
        result = rules_engine.route(_email(message="Status failed 400 when I open the link"))
        assert result["is_bug"] is True

    def test_soft_keyword_alone_not_bug(self):
        result = rules_engine.route(_email(message="I have an issue with my schedule"))
        assert result["is_bug"] is False

    def test_soft_keyword_plus_non_image_attachment_is_bug(self):
        email = _email(
            message="I have a problem with the interview",
            attachments=[{"mimeType": "application/pdf", "filename": "doc.pdf"}],
        )
        result = rules_engine.route(email)
        assert result["is_bug"] is True

    def test_normal_email_not_bug(self):
        result = rules_engine.route(_email(message="When will I get my interview results?"))
        assert result["is_bug"] is False


class TestAttachmentTrigger:
    def test_attachment_adds_trigger(self):
        email = _email(attachments=[{"mimeType": "application/pdf"}])
        result = rules_engine.route(email)
        assert "attachment_present" in result["risk_triggers"]

    def test_no_attachment_no_trigger(self):
        result = rules_engine.route(_email())
        assert "attachment_present" not in result["risk_triggers"]


class TestDNCSignals:
    def test_unsubscribe_routes_s29(self):
        result = rules_engine.route(_email(message="Please unsubscribe me from your mailing list."))
        assert result["pre_route_hint"] == "S29"
        assert "dnc_signal" in result["risk_triggers"]

    def test_gdpr_right_to_erasure_routes_s29(self):
        result = rules_engine.route(_email(message="I invoke my right to erasure under GDPR."))
        assert result["pre_route_hint"] == "S29"

    def test_opt_out_routes_s29(self):
        result = rules_engine.route(_email(message="I want to opt-out from your emails."))
        assert result["pre_route_hint"] == "S29"


class TestDeletionSignals:
    def test_delete_account_routes_s33(self):
        result = rules_engine.route(_email(message="Please delete my account and all my data."))
        assert result["pre_route_hint"] == "S33"

    def test_erase_data_routes_s33(self):
        result = rules_engine.route(_email(message="I want you to erase my data from your system."))
        assert result["pre_route_hint"] == "S33"

    def test_dnc_takes_priority_over_deletion(self):
        # Both signals in same message — DNC takes priority (S29 checked first)
        result = rules_engine.route(_email(message="Unsubscribe me and delete my account."))
        assert result["pre_route_hint"] == "S29"


class TestS4Detection:
    def test_reschedule_with_external_context_routes_s4(self):
        result = rules_engine.route(_email(
            message="I need to reschedule my interview. I was hired by Acme Corp and applied for the role."
        ))
        assert result["pre_route_hint"] == "S4"

    def test_reschedule_without_external_context_not_s4(self):
        # No external company signal — should not route to S4
        result = rules_engine.route(_email(message="I need to reschedule my interview."))
        assert result["pre_route_hint"] != "S4"


class TestSenderTypeDetection:
    def test_recruiter_keyword_returns_D(self):
        # "recruiter" is in _RECRUITER_KEYWORDS — must appear in combined from/subject/message
        result = rules_engine.route(_email(from_addr="recruiter@company.com"))
        assert result["sender_type"] == "D"

    def test_partner_keyword_returns_C(self):
        result = rules_engine.route(_email(message="I am interested in your business partner program."))
        assert result["sender_type"] == "C"

    def test_external_company_returns_B(self):
        result = rules_engine.route(_email(message="I applied for a job at TechCorp and was hired."))
        assert result["sender_type"] == "B"

    def test_unknown_returns_E(self):
        result = rules_engine.route(_email(message="When will I get my results?"))
        assert result["sender_type"] == "E"
