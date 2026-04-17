# TODOS

## P1 — Open

### max_tokens dynamic sizing for Node 2 calls
**What:** Scale `max_tokens` in the Node 2 `call_openai()` call based on email body length and thread depth, instead of the current hardcoded `2000`.

**Why:** Long or complex emails (deep threads, multiple questions) can hit the 2000 output token cap. When this happens, the JSON response is silently truncated → `json.JSONDecodeError` → falls to AI_ERROR FM/review fallback. Two production hits observed in the same batch (ecosystem@e27.co, nabeebash05@gmail.com). The fallback is correct behavior but the reviewer gets a blank or near-blank draft.

**Pros:** Fewer unnecessary AI_ERROR FM/review fallbacks on complex emails. Better quality on long replies.

**Cons:** Slightly higher token costs on long/complex emails. Small additional complexity in `call_openai()`.

**Context:** Node 1 uses `max_tokens=400` (classification only — truncation less likely). Node 2 uses `max_tokens=2000` (draft writing — the risk zone). Formula: `max_tokens = max(2000, len(email_body_chars) // 3 + 600)`, capped at 4000. Bumped from P2 to P1 after observing two AI_ERROR incidents in one batch.

**Effort:** S (human: ~1h / CC: ~5min)
**Priority:** P1
**Depends on:** —

## P2 — Open

### LIST_IN_PROSE formatting validator
**What:** Add a heuristic check in `validators.py` that detects 3+ parallel clauses written as prose sentences instead of hyphen bullet points, and flags the issue as LOW severity.

**Why:** The LLM sometimes ignores the formatting rule ("use bullets for 3+ parallel items") even when explicitly instructed. A validator catch provides a safety net and creates consistent formatting across drafts.

**Pros:** Consistent formatting enforcement without relying solely on LLM compliance.

**Cons:** Regex-based heuristic for detecting "list written as prose" is tricky and prone to false positives on legitimate multi-sentence paragraphs. Needs careful calibration.

**Context:** Issue #9 (katlego@reatlegilees.co.za) showed bad formatting. Immediate fix was strengthening the Node 2 formatting instruction; this TODO tracks the follow-up validator. Watch whether the stronger instruction alone resolves it before implementing the validator.

**Effort:** M (human: ~3h / CC: ~15min)
**Priority:** P2
**Depends on:** Observe whether stronger formatting instruction (added 2026-04-17) resolves issue #9-type cases first
