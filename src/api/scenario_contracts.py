"""
scenario_contracts.py — Loads and selects JSON scenario contracts.

Contracts live in knowledge/contracts/<SCENARIO_ID>.json (plus FALLBACK.json).
Load once at startup via load_all(); call select() per email after the LLM call.

Contract schema:
    {
        "scenario_id":        str,          # e.g. "S4" or "FALLBACK"
        "description":        str,          # human-readable summary
        "required_facts":     list[str],    # substrings that must appear (case-insensitive)
        "forbidden_promises": list[str],    # substrings that must NOT appear
        "ownership_patterns": list[str],    # phrases indicating wrong ownership
        "force_review":       bool,         # if true, always FM/review regardless of severity
    }
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONTRACTS_DIR = Path(__file__).parent.parent.parent / "knowledge" / "contracts"

_REQUIRED_KEYS = {"scenario_id", "required_facts", "forbidden_promises", "ownership_patterns"}

FALLBACK_CONTRACT: dict = {
    "scenario_id":        "FALLBACK",
    "description":        "Fallback — no matching contract.",
    "required_facts":     [],
    "forbidden_promises": [],
    "ownership_patterns": [],
    "force_review":       False,
}


def load_all() -> list[dict]:
    """
    Load all JSON contract files from knowledge/contracts/.

    Raises SystemExit(1) on any schema validation error (fail-fast at startup).
    Returns list of validated contract dicts (FALLBACK included).
    """
    if not CONTRACTS_DIR.exists():
        raise SystemExit(f"[scenario_contracts] contracts dir not found: {CONTRACTS_DIR}")

    contract_files = sorted(CONTRACTS_DIR.glob("*.json"))
    if not contract_files:
        raise SystemExit(f"[scenario_contracts] no JSON files found in {CONTRACTS_DIR}")

    contracts: list[dict] = []
    for path in contract_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"[scenario_contracts] invalid JSON in {path.name}: {exc}") from exc

        missing = _REQUIRED_KEYS - data.keys()
        if missing:
            raise SystemExit(
                f"[scenario_contracts] {path.name} missing required keys: {missing}"
            )

        # Ensure list fields are lists
        for list_key in ("required_facts", "forbidden_promises", "ownership_patterns"):
            if not isinstance(data[list_key], list):
                raise SystemExit(
                    f"[scenario_contracts] {path.name}: '{list_key}' must be a list"
                )

        data.setdefault("description", "")
        data.setdefault("force_review", False)
        contracts.append(data)
        logger.debug("Loaded contract: %s", data["scenario_id"])

    return contracts


def select(
    contracts: list[dict],
    pre_route_hint: str,
    model_scenario_id: str,
) -> tuple[dict, list[str]]:
    """
    Select the best contract for this email and report any mismatch.

    Parameters
    ----------
    contracts         : List returned by load_all().
    pre_route_hint    : Scenario ID hint from rules_engine (or "unclear").
    model_scenario_id : Scenario ID chosen by the LLM (e.g. "S4").

    Returns
    -------
    (contract, extra_risk_triggers)
        contract           — the matched contract dict (FALLBACK if no match)
        extra_risk_triggers — list of additional risk_trigger codes to append
                              (contains "scenario_mismatch" on conflict)
    """
    extra_triggers: list[str] = []

    # Build lookup
    by_id: dict[str, dict] = {c["scenario_id"]: c for c in contracts}

    # Detect hint vs model conflict
    hint_normalised = pre_route_hint.upper() if pre_route_hint else "UNCLEAR"
    model_normalised = model_scenario_id.upper() if model_scenario_id else ""

    if (
        hint_normalised not in ("UNCLEAR", "")
        and model_normalised
        and hint_normalised != model_normalised
    ):
        logger.warning(
            "Scenario mismatch: rules_engine hint=%s, model chose=%s",
            hint_normalised,
            model_normalised,
        )
        extra_triggers.append("scenario_mismatch")

    # Always trust model_scenario_id (LLM has full email context)
    contract = by_id.get(model_normalised)
    if contract is None:
        if model_normalised:
            logger.warning(
                "No contract for scenario_id=%s — using FALLBACK", model_normalised
            )
        contract = by_id.get("FALLBACK", FALLBACK_CONTRACT)
        extra_triggers.append("unknown_scenario")

    return contract, extra_triggers
