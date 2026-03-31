#!/usr/bin/env python3
"""
Log daily API cost from OpenAI Console into api_stats.json.

Usage:
    python log_api_cost.py --total 1.45
    python log_api_cost.py --total 1.45 --date 2026-03-20

Get your total from: https://platform.openai.com/usage
The script computes conversation cost = total - email_processing_cost.
"""

import argparse
import json
from datetime import date
from pathlib import Path

STATS_DIR      = Path(__file__).parent.parent.parent / "stats"
EMAIL_STATS    = STATS_DIR / "email_stats.json"
API_STATS      = STATS_DIR / "api_stats.json"


def load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def get_email_cost(day: str) -> float:
    email_stats = load_json(EMAIL_STATS)
    return email_stats.get("daily", {}).get(day, {}).get("total_cost_usd", 0.0)


def main():
    parser = argparse.ArgumentParser(description="Log daily API cost split")
    parser.add_argument("--total", type=float, required=True,
                        help="Total daily cost from platform.openai.com/usage")
    parser.add_argument("--date", default=str(date.today()),
                        help="Date (YYYY-MM-DD), defaults to today")
    args = parser.parse_args()

    day          = args.date
    total        = round(args.total, 6)
    email_cost   = round(get_email_cost(day), 6)
    convo_cost   = round(total - email_cost, 6)

    api_stats = load_json(API_STATS)
    api_stats.setdefault("daily", {})

    api_stats["daily"][day] = {
        "total_cost_usd":        total,
        "email_processing_usd":  email_cost,
        "conversation_usd":      convo_cost,
    }

    # Recompute totals
    api_stats["total"] = {
        "total_cost_usd":        round(sum(v["total_cost_usd"]       for v in api_stats["daily"].values()), 6),
        "email_processing_usd":  round(sum(v["email_processing_usd"] for v in api_stats["daily"].values()), 6),
        "conversation_usd":      round(sum(v["conversation_usd"]     for v in api_stats["daily"].values()), 6),
    }

    save_json(API_STATS, api_stats)

    print(f"Logged {day}:")
    print(f"  Total            ${total:.4f}")
    print(f"  Email processing ${email_cost:.4f}")
    print(f"  Conversations    ${convo_cost:.4f}")
    print(f"Saved to {API_STATS}")


if __name__ == "__main__":
    main()
