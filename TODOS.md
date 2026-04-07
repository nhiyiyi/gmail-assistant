# TODOS

## P2 — Open

### max_tokens dynamic sizing for v1 calls
**What:** Scale `max_tokens` in the v1 `call_openai()` call based on email body length and thread depth, instead of the current hardcoded `1200`.

**Why:** Long or complex emails (deep threads, multiple questions) can exceed 1200 output tokens. When this happens, the JSON response is silently truncated → `json.JSONDecodeError` → falls to FM/review fallback. The fallback is correct behavior, but the truncation isn't logged, so you can't see it happening or distinguish it from other AI errors.

**Pros:** Fewer unnecessary FM/review fallbacks on complex emails. Better quality on long replies.

**Cons:** Slightly higher token costs on long emails. Small additional complexity in `call_openai()`.

**Context:** The repair v2 call already uses `max_tokens=2000`. v1 is the remaining gap. Formula would be something like `max_tokens = max(1200, len(email_body_chars) // 3 + 400)`, capped at 3000. Implement after the pipeline redesign (rules_engine, validators, scenario_contracts) is stable and generating real data.

**Effort:** S (human: ~1h / CC: ~5min)
**Priority:** P2
**Depends on:** Pipeline redesign (Approach C) shipped and stable
