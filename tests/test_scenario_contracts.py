"""P1 unit tests for scenario_contracts.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "api"))

import scenario_contracts as sc

# Use real contracts directory
REAL_CONTRACTS = None  # populated in setup


def setup_module():
    global REAL_CONTRACTS
    REAL_CONTRACTS = sc.load_all()


class TestLoadAll:
    def test_loads_at_least_one_contract(self):
        assert len(REAL_CONTRACTS) >= 1

    def test_fallback_contract_present(self):
        ids = [c["scenario_id"] for c in REAL_CONTRACTS]
        assert "FALLBACK" in ids

    def test_all_contracts_have_required_keys(self):
        required = {"scenario_id", "required_facts", "forbidden_promises", "ownership_patterns"}
        for contract in REAL_CONTRACTS:
            for key in required:
                assert key in contract, f"Contract {contract.get('scenario_id')} missing key: {key}"

    def test_list_fields_are_lists(self):
        for contract in REAL_CONTRACTS:
            for field in ("required_facts", "forbidden_promises", "ownership_patterns"):
                assert isinstance(contract[field], list), (
                    f"Contract {contract['scenario_id']}: '{field}' should be a list"
                )


class TestSelect:
    def test_exact_match_returns_correct_contract(self):
        contracts = [
            {"scenario_id": "S4", "required_facts": ["contact the hiring company"],
             "forbidden_promises": [], "ownership_patterns": [], "force_review": False},
            sc.FALLBACK_CONTRACT,
        ]
        contract, triggers = sc.select(contracts, "unclear", "S4")
        assert contract["scenario_id"] == "S4"
        assert triggers == []

    def test_unknown_scenario_returns_fallback(self):
        contracts = [sc.FALLBACK_CONTRACT]
        contract, triggers = sc.select(contracts, "unclear", "S99")
        assert contract["scenario_id"] == "FALLBACK"
        assert "unknown_scenario" in triggers

    def test_mismatch_adds_scenario_mismatch_trigger(self):
        contracts = [
            {"scenario_id": "S3", "required_facts": [], "forbidden_promises": [],
             "ownership_patterns": [], "force_review": False},
            sc.FALLBACK_CONTRACT,
        ]
        contract, triggers = sc.select(contracts, "S4", "S3")
        assert "scenario_mismatch" in triggers
        # Still uses model_scenario_id (S3)
        assert contract["scenario_id"] == "S3"

    def test_matching_hint_and_model_no_mismatch(self):
        contracts = [
            {"scenario_id": "S4", "required_facts": [], "forbidden_promises": [],
             "ownership_patterns": [], "force_review": False},
            sc.FALLBACK_CONTRACT,
        ]
        contract, triggers = sc.select(contracts, "S4", "S4")
        assert "scenario_mismatch" not in triggers
        assert contract["scenario_id"] == "S4"

    def test_unclear_hint_with_known_model_no_mismatch(self):
        contracts = [
            {"scenario_id": "S4", "required_facts": [], "forbidden_promises": [],
             "ownership_patterns": [], "force_review": False},
            sc.FALLBACK_CONTRACT,
        ]
        contract, triggers = sc.select(contracts, "unclear", "S4")
        assert "scenario_mismatch" not in triggers


class TestRealContracts:
    def test_s4_has_required_fact(self):
        by_id = {c["scenario_id"]: c for c in REAL_CONTRACTS}
        if "S4" in by_id:
            assert len(by_id["S4"]["required_facts"]) > 0

    def test_s4_has_forbidden_promise(self):
        by_id = {c["scenario_id"]: c for c in REAL_CONTRACTS}
        if "S4" in by_id:
            assert len(by_id["S4"]["forbidden_promises"]) > 0

    def test_s29_force_review(self):
        by_id = {c["scenario_id"]: c for c in REAL_CONTRACTS}
        if "S29" in by_id:
            assert by_id["S29"].get("force_review") is True

    def test_s33_required_2_working_days(self):
        by_id = {c["scenario_id"]: c for c in REAL_CONTRACTS}
        if "S33" in by_id:
            facts = [f.lower() for f in by_id["S33"]["required_facts"]]
            assert any("2 working days" in f for f in facts)
