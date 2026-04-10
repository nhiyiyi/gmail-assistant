"""
validators.py — Post-LLM draft validation with auto-fix and severity scoring.

Runs AFTER the OpenAI v1 call. Returns a validation result used by the orchestrator
to decide: auto-fix → FM/ready, repair_v2, or FM/review.

Returns:
    {
        "severity":       "PASS"|"LOW"|"MEDIUM"|"HIGH",
        "issues":         list[str],       # human-readable issue descriptions
        "validator_score": float,          # 0.0–1.0, passed_checks / total_checks
        "fixed_draft":    str,             # auto-fixed draft (LOW) or original
        "review_reason_code": str|None,    # highest-severity issue code
    }

Contract schema (from scenario_contracts.py):
    {
        "scenario_id":          str,
        "required_facts":       list[str],   # substrings that must appear (case-insensitive)
        "forbidden_promises":   list[str],   # substrings that must NOT appear (case-insensitive)
        "ownership_patterns":   list[str],   # phrases indicating WRONG ownership (case-insensitive)
    }
"""

import re

# ── Markdown detection ────────────────────────────────────────────────────────

_MARKDOWN_PATTERNS = [
    r'\*\*[^*]+\*\*',           # **bold**
    r'\*[^*]+\*',               # *italic*
    r'__[^_]+__',               # __bold__
    r'_[^_]+_',                 # _italic_
    r'^#{1,6}\s',               # # Heading
    r'`[^`]+`',                 # `code`
    r'^\s*[-*+]\s',             # - bullet list
    r'^\s*\d+\.\s',             # 1. numbered list
    r'\[.+?\]\(.+?\)',          # [link](url)
]
_MARKDOWN_REGEX = re.compile(
    "|".join(_MARKDOWN_PATTERNS),
    re.MULTILINE | re.IGNORECASE,
)

# Strip markdown: bold/italic markers, inline code backticks, heading hashes
_MARKDOWN_STRIP_PATTERNS = [
    (re.compile(r'\*\*([^*]+)\*\*'), r'\1'),   # **bold** → bold
    (re.compile(r'\*([^*]+)\*'),     r'\1'),   # *italic* → italic
    (re.compile(r'__([^_]+)__'),     r'\1'),   # __bold__ → bold
    (re.compile(r'_([^_]+)_'),       r'\1'),   # _italic_ → italic
    (re.compile(r'`([^`]+)`'),       r'\1'),   # `code` → code
    (re.compile(r'^#{1,6}\s+', re.MULTILINE), ''),  # ## Heading → Heading
    (re.compile(r'^\s*[-*+]\s+', re.MULTILINE), ''),  # - item → item
]


def _strip_markdown(text: str) -> str:
    for pattern, replacement in _MARKDOWN_STRIP_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ── Salutation / closing constants ───────────────────────────────────────────

_SALUTATION_PREFIX = "Dear [Name],"     # prepended if missing (triggers AI_ERROR below)
_LUK_CLOSING      = "\n\nLet us know if you have any questions,"
_BR_CLOSING       = "\n\nBest regards,"


def validate(draft_body: str, contract: dict, risk_triggers: list[str]) -> dict:
    """
    Validate draft_body against contract rules and risk_triggers.

    Parameters
    ----------
    draft_body    : Raw draft string produced by the LLM.
    contract      : Scenario contract dict (see module docstring for schema).
    risk_triggers : List of trigger codes from rules_engine.route().

    Returns
    -------
    dict with keys: severity, issues, validator_score, fixed_draft, review_reason_code
    """
    issues: list[str] = []
    total_checks = 0
    passed_checks = 0

    working_draft = draft_body  # mutated by LOW auto-fixes

    # ── LOW CHECKS (auto-fix) ─────────────────────────────────────────────────

    # 0. Duplicate [REVIEW NEEDED: ...] inside body — LLM sometimes puts it at the
    #    top (correct) AND again mid-body (wrong). Keep only the leading one.
    _rn_pattern = re.compile(r'\[REVIEW NEEDED:[^\]]*\]', re.IGNORECASE)
    _rn_matches = list(_rn_pattern.finditer(working_draft))
    if len(_rn_matches) > 1:
        # Remove every occurrence except the very first
        def _remove_after_first(m):
            return "" if m.start() != _rn_matches[0].start() else m.group(0)
        working_draft = _rn_pattern.sub(_remove_after_first, working_draft)
        working_draft = re.sub(r'\n{3,}', '\n\n', working_draft).strip()
        issues.append("FORMAT_VIOLATION: Duplicate [REVIEW NEEDED] in body stripped.")

    # 0b. Unhyphenated troubleshooting steps — detect 2+ consecutive lines that look
    #     like step instructions (start with capital letter, no leading "- " or digit)
    #     appearing after a trigger phrase. Auto-prefix each with "- ".
    _step_trigger = re.compile(
        r'(please try[^:\n]*:?\s*\n|steps? below[^:\n]*:?\s*\n|following steps?[^:\n]*:?\s*\n)',
        re.IGNORECASE,
    )
    if _step_trigger.search(working_draft):
        def _add_hyphen_if_missing(m):
            line = m.group(0)
            # Only add hyphen to lines that are non-empty, start with a capital,
            # and don't already have "- " or a number bullet or [REVIEW
            if re.match(r'^[A-Z][^-\n]', line) and not re.match(r'^\d+\.', line):
                return "- " + line
            return line
        # Find the trigger and fix bare lines in the block that follows
        parts = _step_trigger.split(working_draft, maxsplit=1)
        if len(parts) == 3:
            before, trigger, after = parts[0], parts[1], parts[2]
            # Fix lines in 'after' until a blank line (end of the step block)
            step_block, rest = (after.split('\n\n', 1) + [''])[:2]
            fixed_block = re.sub(r'^[A-Z][^\n]+$', _add_hyphen_if_missing, step_block, flags=re.MULTILINE)
            if fixed_block != step_block:
                working_draft = before + trigger + fixed_block + ('\n\n' + rest if rest else '')
                issues.append("FORMAT_VIOLATION: Troubleshooting steps lacked hyphen bullets — auto-fixed.")

    # 1. Markdown in body
    total_checks += 1
    if _MARKDOWN_REGEX.search(working_draft):
        issues.append("MARKDOWN: Draft contains markdown formatting — stripped.")
        working_draft = _strip_markdown(working_draft)
    else:
        passed_checks += 1

    # 2. Missing salutation ("Dear ")
    # Strip any leading [REVIEW NEEDED: ...] prefix before checking — the LLM is
    # instructed to prepend it to draft_body, so it may appear before "Dear Name,".
    _sal_check = re.sub(r"^\[REVIEW NEEDED:[^\]]*\]\s*", "", working_draft, flags=re.IGNORECASE).strip()
    total_checks += 1
    if not _sal_check.lower().startswith("dear "):
        issues.append("MISSING_SALUTATION: Draft does not start with 'Dear ...'.")
        working_draft = _SALUTATION_PREFIX + "\n\n" + working_draft
    else:
        passed_checks += 1

    # 3. Missing "Let us know..." closing
    total_checks += 1
    if "let us know if you have any questions" not in working_draft.lower():
        issues.append("MISSING_LUK_CLOSING: Missing 'Let us know if you have any questions'.")
        working_draft = working_draft.rstrip() + _LUK_CLOSING
    else:
        passed_checks += 1

    # 4. Missing "Best regards,"
    total_checks += 1
    if "best regards" not in working_draft.lower():
        issues.append("MISSING_BR_CLOSING: Missing 'Best regards,'.")
        working_draft = working_draft.rstrip() + _BR_CLOSING
    else:
        passed_checks += 1

    # 4b. Signature / confidentiality notice after "Best regards," — strip it.
    # The SOP prohibits any name, title, or signature after "Best regards,".
    # LLMs sometimes append "Jessica from Flowmingo..." or a confidentiality block.
    _br_idx = working_draft.lower().rfind("best regards")
    if _br_idx != -1:
        _after_br = working_draft[_br_idx + len("best regards"):].lstrip(",").strip()
        if len(_after_br) > 2:  # more than just whitespace after "Best regards,"
            working_draft = working_draft[:_br_idx] + "Best regards,"
            issues.append("FORMAT_VIOLATION: Content after 'Best regards,' stripped (signature/footer not allowed).")

    # ── HIGH CHECK: "Dear Customer" / "Dear [Name]" — name was not extracted ──
    total_checks += 1
    _sal_lower = working_draft.lower()
    if _sal_lower.startswith("dear customer") or _sal_lower.startswith("dear [name]"):
        issues.append(
            "AI_ERROR: Salutation uses generic placeholder — sender name was not extracted."
        )
        return _result(
            severity="HIGH",
            issues=issues,
            total_checks=total_checks,
            passed_checks=passed_checks,
            fixed_draft=draft_body,
            review_reason_code="AI_ERROR",
        )
    else:
        passed_checks += 1

    # ── HIGH CHECK: empty / short body (after LOW fixes, excluding boilerplate) ─
    # Strip salutation line and closing boilerplate before measuring body length,
    # so auto-appended closings don't mask an empty body.
    _body_only = re.sub(
        r"(?i)^dear\s[^\n]+\n+|let us know if you have any questions,.*|best regards,.*",
        "",
        working_draft,
        flags=re.DOTALL,
    ).strip()
    total_checks += 1
    if len(_body_only) < 30:
        issues.append(
            f"FORMAT_VIOLATION: Draft body is effectively empty ({len(_body_only)} chars) — "
            f"LLM produced no reply content."
        )
        return _result(
            severity="HIGH",
            issues=issues,
            total_checks=total_checks,
            passed_checks=passed_checks,
            fixed_draft=draft_body,
            review_reason_code="AI_ERROR",
        )
    else:
        passed_checks += 1

    # ── MEDIUM CHECKS ─────────────────────────────────────────────────────────

    # 5. Attachment risk trigger (partial context — LLM can't see attachment)
    if "attachment_present" in risk_triggers:
        total_checks += 1
        issues.append(
            "PARTIAL_CONTEXT: Email has attachment(s) whose content is not visible "
            "to the model — draft may be incomplete."
        )
        # Not a pass

    # 6. Scenario mismatch signal from rules_engine
    if "scenario_mismatch" in risk_triggers:
        total_checks += 1
        issues.append(
            "WRONG_SCENARIO: Pre-route hint conflicts with model scenario — "
            "review scenario selection."
        )

    # 7. Required facts not addressed
    required_facts: list[str] = contract.get("required_facts", [])
    for fact in required_facts:
        total_checks += 1
        if fact.lower() not in working_draft.lower():
            issues.append(f"MISSING_REQUIRED_FACT: Required fact not addressed: '{fact}'.")
        else:
            passed_checks += 1

    # ── HIGH CHECKS ───────────────────────────────────────────────────────────

    # 8. Forbidden promises
    forbidden_promises: list[str] = contract.get("forbidden_promises", [])
    high_triggered = False
    high_code: str | None = None

    for promise in forbidden_promises:
        total_checks += 1
        if promise.lower() in working_draft.lower():
            issues.append(
                f"FORBIDDEN_PROMISE: Draft contains forbidden promise: '{promise}'."
            )
            high_triggered = True
            high_code = high_code or "FORBIDDEN_PROMISE"
        else:
            passed_checks += 1

    # 9. Ownership mismatch
    ownership_patterns: list[str] = contract.get("ownership_patterns", [])
    for pattern in ownership_patterns:
        total_checks += 1
        if pattern.lower() in working_draft.lower():
            issues.append(
                f"WRONG_OWNERSHIP: Draft claims wrong ownership via: '{pattern}'."
            )
            high_triggered = True
            high_code = high_code or "WRONG_OWNERSHIP"
        else:
            passed_checks += 1

    # ── Determine severity ────────────────────────────────────────────────────

    medium_issues = [i for i in issues if _is_medium(i)]
    low_issues    = [i for i in issues if _is_low(i)]

    if high_triggered:
        severity         = "HIGH"
        review_code      = high_code
        return_draft     = draft_body   # preserve original on HIGH
    elif medium_issues:
        severity         = "MEDIUM"
        review_code      = _medium_review_code(medium_issues)
        return_draft     = working_draft
    elif low_issues:
        severity         = "LOW"
        review_code      = None
        return_draft     = working_draft  # auto-fixed draft
    else:
        severity         = "PASS"
        review_code      = None
        return_draft     = working_draft

    return _result(
        severity=severity,
        issues=issues,
        total_checks=total_checks,
        passed_checks=passed_checks,
        fixed_draft=return_draft,
        review_reason_code=review_code,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_low(issue: str) -> bool:
    return issue.startswith(("MARKDOWN:", "MISSING_SALUTATION:", "MISSING_LUK_CLOSING:", "MISSING_BR_CLOSING:"))


def _is_medium(issue: str) -> bool:
    return issue.startswith(("PARTIAL_CONTEXT:", "WRONG_SCENARIO:", "MISSING_REQUIRED_FACT:"))


def _medium_review_code(medium_issues: list[str]) -> str:
    """Pick the highest-priority review_reason_code from medium issues."""
    for issue in medium_issues:
        if issue.startswith("MISSING_REQUIRED_FACT:"):
            return "MISSING_REQUIRED_FACT"
        if issue.startswith("WRONG_SCENARIO:"):
            return "WRONG_SCENARIO"
        if issue.startswith("PARTIAL_CONTEXT:"):
            return "PARTIAL_CONTEXT"
    return "MISSING_REQUIRED_FACT"


def _result(
    severity: str,
    issues: list[str],
    total_checks: int,
    passed_checks: int,
    fixed_draft: str,
    review_reason_code: str | None,
) -> dict:
    validator_score = passed_checks / total_checks if total_checks > 0 else 1.0
    return {
        "severity":           severity,
        "issues":             issues,
        "validator_score":    round(validator_score, 4),
        "fixed_draft":        fixed_draft,
        "review_reason_code": review_reason_code,
    }
