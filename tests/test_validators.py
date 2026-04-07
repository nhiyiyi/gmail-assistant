"""P1 unit tests for validators.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "api"))

import validators

EMPTY_CONTRACT = {
    "scenario_id": "TEST",
    "required_facts": [],
    "forbidden_promises": [],
    "ownership_patterns": [],
}


def _validate(body: str, contract: dict = None, triggers: list = None) -> dict:
    return validators.validate(body, contract or EMPTY_CONTRACT, triggers or [])


class TestLowAutoFix:
    def test_strips_markdown_bold(self):
        result = _validate("Dear Customer,\n\n**Hello**, this is your update.\n\nLet us know if you have any questions,\n\nBest regards,")
        assert "**" not in result["fixed_draft"]
        assert result["severity"] in ("PASS", "LOW")

    def test_prepends_salutation(self):
        result = _validate("Hello, here is your reply.\n\nLet us know if you have any questions,\n\nBest regards,")
        assert result["fixed_draft"].lower().startswith("dear ")
        assert "MISSING_SALUTATION" in str(result["issues"])

    def test_appends_luk_closing(self):
        draft = "Dear Customer,\n\nYour interview results will be ready soon.\n\nBest regards,"
        result = _validate(draft)
        assert "let us know if you have any questions" in result["fixed_draft"].lower()

    def test_appends_best_regards(self):
        draft = "Dear Customer,\n\nThank you for your message.\n\nLet us know if you have any questions,"
        result = _validate(draft)
        assert "best regards" in result["fixed_draft"].lower()

    def test_clean_draft_passes(self):
        draft = "Dear Customer,\n\nThank you for reaching out.\n\nLet us know if you have any questions,\n\nBest regards,"
        result = _validate(draft)
        assert result["severity"] == "PASS"
        assert result["validator_score"] == 1.0
        assert result["issues"] == []


class TestHighChecks:
    def test_empty_draft_gets_auto_fixed(self):
        # Empty draft triggers LOW auto-fixes (salutation + closings added).
        # After auto-fix the draft is > 50 chars so FORMAT_VIOLATION does not fire.
        result = _validate("")
        assert result["severity"] in ("PASS", "LOW")
        assert result["fixed_draft"].lower().startswith("dear ")

    def test_short_draft_gets_auto_fixed(self):
        # Short draft gets salutation prepended and closings appended — always > 50 chars.
        result = _validate("Hi there.")
        assert result["severity"] in ("PASS", "LOW")
        assert "best regards" in result["fixed_draft"].lower()

    def test_forbidden_promise_is_high(self):
        contract = {**EMPTY_CONTRACT, "forbidden_promises": ["use the original link"]}
        draft = "Dear Customer,\n\nYou can use the original link whenever you feel comfortable.\n\nLet us know if you have any questions,\n\nBest regards,"
        result = _validate(draft, contract)
        assert result["severity"] == "HIGH"
        assert result["review_reason_code"] == "FORBIDDEN_PROMISE"
        assert result["fixed_draft"] == draft  # original preserved on HIGH

    def test_wrong_ownership_is_high(self):
        contract = {**EMPTY_CONTRACT, "ownership_patterns": ["contact the hiring company"]}
        draft = "Dear Customer,\n\nPlease contact the hiring company directly for an update.\n\nLet us know if you have any questions,\n\nBest regards,"
        # This is S4 contract where ownership_patterns means THIS phrase should appear
        # Actually for S4, ownership_patterns are WRONG ownership indicators
        # Wait — for S4 the "required_facts" includes "contact the hiring company"
        # and ownership_patterns are phrases indicating WRONG ownership (support claiming they'll fix it)
        # Let me test a case where ownership_patterns fires
        contract2 = {**EMPTY_CONTRACT, "ownership_patterns": ["we will change the deadline"]}
        draft2 = "Dear Customer,\n\nWe will change the deadline for your interview.\n\nLet us know if you have any questions,\n\nBest regards,"
        result = _validate(draft2, contract2)
        assert result["severity"] == "HIGH"
        assert result["review_reason_code"] == "WRONG_OWNERSHIP"


class TestMediumChecks:
    def test_attachment_present_trigger_is_medium(self):
        draft = "Dear Customer,\n\nThank you for your message.\n\nLet us know if you have any questions,\n\nBest regards,"
        result = _validate(draft, triggers=["attachment_present"])
        assert result["severity"] == "MEDIUM"
        assert result["review_reason_code"] in ("PARTIAL_CONTEXT", "MISSING_REQUIRED_FACT", "WRONG_SCENARIO")

    def test_scenario_mismatch_is_medium(self):
        draft = "Dear Customer,\n\nThank you for your message.\n\nLet us know if you have any questions,\n\nBest regards,"
        result = _validate(draft, triggers=["scenario_mismatch"])
        assert result["severity"] == "MEDIUM"

    def test_required_fact_missing_is_medium(self):
        contract = {**EMPTY_CONTRACT, "required_facts": ["contact the hiring company"]}
        draft = "Dear Customer,\n\nThank you for your message about rescheduling.\n\nLet us know if you have any questions,\n\nBest regards,"
        result = _validate(draft, contract)
        assert result["severity"] == "MEDIUM"
        assert result["review_reason_code"] == "MISSING_REQUIRED_FACT"

    def test_required_fact_present_passes(self):
        contract = {**EMPTY_CONTRACT, "required_facts": ["contact the hiring company"]}
        draft = "Dear Customer,\n\nPlease contact the hiring company directly for rescheduling assistance.\n\nLet us know if you have any questions,\n\nBest regards,"
        result = _validate(draft, contract)
        assert result["severity"] == "PASS"


class TestValidatorScore:
    def test_score_is_float_between_0_and_1(self):
        result = _validate("")
        assert 0.0 <= result["validator_score"] <= 1.0

    def test_perfect_draft_scores_1(self):
        draft = "Dear Customer,\n\nThank you for reaching out.\n\nLet us know if you have any questions,\n\nBest regards,"
        result = _validate(draft)
        assert result["validator_score"] == 1.0

    def test_multiple_issues_lower_score(self):
        result = _validate("Hello there. No salutation, no closing.")
        # Several checks fail (salutation, LUK, BR) — score should be < 1.0
        # But it won't be FORMAT_VIOLATION because after auto-fix it's long enough
        # Actually "Hello there. No salutation, no closing." is only 38 chars — may be HIGH
        # Use a longer draft
        result2 = _validate("Hello there. No salutation, no closing. This is a longer message to avoid FORMAT_VIOLATION check.")
        assert result2["validator_score"] < 1.0
