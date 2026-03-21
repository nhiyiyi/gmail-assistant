"""Cost and email count tracking for the Gmail assistant."""

import json
from datetime import date, datetime, timezone
from pathlib import Path

STATS_PATH = Path(__file__).parent.parent.parent / "stats" / "email_stats.json"
HISTORY_PATH = Path(__file__).parent.parent.parent / "stats" / "email_history.jsonl"

# Claude Sonnet 4.6 pricing (USD per million tokens)
INPUT_COST_PER_M = 3.00
OUTPUT_COST_PER_M = 15.00


def _empty_stats() -> dict:
    return {"daily": {}, "total": {"emails_processed": 0, "total_cost_usd": 0.0}}


def _empty_day() -> dict:
    return {
        "emails_processed": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cost_usd": 0.0,
        "drafts_created": 0,
        "email_ids": [],
    }


def load_stats() -> dict:
    if not STATS_PATH.exists():
        return _empty_stats()
    try:
        return json.loads(STATS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _empty_stats()


def save_stats(data: dict) -> None:
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def log_processing(
    email_id: str,
    input_tokens: int,
    output_tokens: int,
    *,
    subject: str = "",
    from_addr: str = "",
    scenario: str = "",
    topic: str = "",
    urgency: str = "",
    review_status: str = "",
) -> dict:
    """Record processing of one email. Returns today's updated stats entry."""
    data = load_stats()
    today = date.today().isoformat()

    if today not in data["daily"]:
        data["daily"][today] = _empty_day()

    day = data["daily"][today]

    # Idempotency: skip if already logged
    if email_id not in day["email_ids"]:
        cost = (input_tokens / 1_000_000 * INPUT_COST_PER_M) + (output_tokens / 1_000_000 * OUTPUT_COST_PER_M)
        day["emails_processed"] += 1
        day["drafts_created"] += 1
        day["total_input_tokens"] += input_tokens
        day["total_output_tokens"] += output_tokens
        day["total_cost_usd"] = round(day["total_cost_usd"] + cost, 6)
        day["email_ids"].append(email_id)

        data["total"]["emails_processed"] += 1
        data["total"]["total_cost_usd"] = round(data["total"]["total_cost_usd"] + cost, 6)

        # Append to history
        entry = {
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "email_id": email_id,
            "from": from_addr,
            "subject": subject,
            "scenario": scenario,
            "topic": topic,
            "urgency": urgency,
            "review_status": review_status,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
        }
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    save_stats(data)
    return day


def get_history(limit: int = 50) -> list[dict]:
    """Return the most recent `limit` processed email entries."""
    if not HISTORY_PATH.exists():
        return []
    lines = HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
    return entries[-limit:]


def get_stats() -> dict:
    """Return a summary: today's stats, last 7 days, and all-time totals."""
    data = load_stats()
    today = date.today().isoformat()

    # Last 7 days
    all_days = sorted(data["daily"].keys(), reverse=True)[:7]
    recent = {d: data["daily"][d] for d in all_days}

    return {
        "today": data["daily"].get(today, _empty_day()),
        "last_7_days": recent,
        "total": data["total"],
        "pricing": {
            "model": "Claude Sonnet 4.6",
            "input_per_million_tokens": f"${INPUT_COST_PER_M:.2f}",
            "output_per_million_tokens": f"${OUTPUT_COST_PER_M:.2f}",
        },
    }
