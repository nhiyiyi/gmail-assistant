---
name: update-kb
description: Apply user feedback about a misclassified or mishandled email to the knowledge base. Generalizes the fix — never patches only the single case. Always finds the broader pattern and fixes it at the root.
---

# Purpose

When a support email was misclassified, over-escalated, or answered incorrectly, fix the KB so the whole class of similar emails is handled correctly going forward — not just the specific example.

# When to use

- User points at an email and says it should have been answered, escalated, or ticketed differently
- User says "how can this case not have a ticket / draft / answer"
- User gives explicit correction: "this should have been FM/ready", "this should have been a bug", etc.

# Workflow

## Step 1 — Read the email and feedback

Fetch the email in question (`get_email`). Read the user's feedback carefully.

## Step 2 — Root cause analysis

Work through the 6 dimensions (D1–D6) for the email as it was processed:

- **D1 – Sender intent:** What was the person actually asking or doing?
- **D2 – Context completeness:** Was everything needed visible in the thread?
- **D3 – KB coverage:** Was the answer in the KB? Which section or scenario? Did the routing point there?
- **D4 – Technical defect:** Was there a bug signal? Was it correctly identified?
- **D5 – Sensitivity:** Was sensitivity correctly assessed?
- **D6 – Thread handled:** Had support already replied?

Identify which dimension produced the wrong answer and why.

## Step 3 — Generalize the pattern

Do not stop at the single email. Ask: what class of emails would fail the same way?

Common patterns to check:
- **Orphaned section:** KB section has answers but no scenario routes to it → extend an existing scenario
- **Wrong routing:** Existing scenario routes to a wrong answer for a subcase → add exception clause
- **Over-escalation:** FM/review triggered on a covered case → tighten the scenario trigger or D3 assessment
- **Under-escalation:** FM/ready on a case that needs human review → add guard in the scenario

## Step 4 — Find other instances

Read `knowledge/flowmingo-rules.md` and `knowledge/flowmingo-scenarios.md`. Look for:
- Other sections that might be orphaned the same way
- Other scenarios with the same routing flaw
- Edge cases in the quick reference table (SKILL.md) that are wrong or missing

## Step 5 — Fix (in order of preference)

Apply fixes in this priority order — stop as soon as the fix is sufficient:

1. **Extend an existing scenario's scope** — add a sentence covering the new sub-case
2. **Add an exception clause** to an existing scenario
3. **Add a routing note** to a KB section (as a self-annotation)
4. **Add or fix an edge-case row** in SKILL.md quick reference table
5. **New scenario** — only if no existing scenario can reasonably absorb the case and the volume warrants it

Never create a new scenario as the first resort.

## Step 6 — Report

Output in this exact structure:

```
Observed: [email sender, subject, what they asked, what went wrong]
Root cause: [which dimension failed and why]
Broader pattern: [class of emails affected by the same gap]
Other gaps found: [any related weaknesses found in step 4]
Changes made:
  - [file]: [what was changed and why]
  - [file]: [what was changed and why]
Remaining risks: [edge cases that still need human review or testing]
```

# Rules

1. Never patch only the single email. Always generalize.
2. Never add a new scenario when an existing one can be extended.
3. Every fix must have a "why" — what failure mode it prevents.
4. If the fix requires a judgment call the user should make (e.g. "should we answer company ops questions?"), surface it explicitly in Remaining risks.
5. Only edit `knowledge/` files and SKILL.md. Never edit server code.
