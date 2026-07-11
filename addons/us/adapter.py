#!/usr/bin/env python3
"""US adapter — US federal law with 7-title coverage.

Covers: Arbitration (Title 9), Jurisdiction/FSIA (Title 28), Sanctions (Title 50),
Bankruptcy (Title 11), Commerce/Antitrust/Securities (Title 15),
Copyrights (Title 17), Patents (Title 35).
"""
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from compiler_core.adapter_base import JurisdictionAdapter
from compiler_core.types import LegalFact, IRState
from compiler_core.constraint_validator import ConstraintValidator
from compiler_core.proof_tree import ProofTree


class USAdapter(JurisdictionAdapter):
    """US federal law adapter."""

    jurisdiction = "US"
    rules_path = "configs/us/rules.yaml"
    overrides_path = "configs/L0_overrides_us.yaml"

    # Core L0 map for US legal concepts
    _L0_MAP: Dict[str, str] = {
        # Arbitration
        "Arbitration_Agreement_Valid_Enforceable": "Status",
        "Arbitral_Award_Made": "Status",
        "Foreign_Arbitral_Award_Exists": "Status",
        "Party_Fails_To_Arbitrate": "Act",
        "Award_Procured_By_Fraud": "Defect",
        "Arbitrator_Exceeded_Powers": "Defect",
        "Written_Arbitration_Agreement_Exists": "Status",
        "Transaction_Involves_Commerce": "Status",
        # Jurisdiction
        "Action_Against_Foreign_State": "Act",
        "Claim_Arises_Under_Federal_Law": "Status",
        "Parties_Are_Diverse_Citizenship": "Status",
        "Amount_In_Controversy_Exceeds_75000": "Status",
        "Foreign_State_Engages_In_Commercial_Activity": "Act",
        "Foreign_State_Waives_Immunity": "Act",
        "Foreign_State_Commits_Tort_In_US": "Act",
        "Entity_Is_Foreign_State": "Agent",
        # Bankruptcy
        "Bankruptcy_Case_Pending": "Status",
        "Debtor_In_Chapter7": "Status",
        "Plan_Confirmed": "Status",
        "Foreign_Proceeding_Exists": "Status",
        "Foreign_Representative_Authorized": "Agent",
        # Commerce
        "Contract_Combination_Or_Conspiracy": "Act",
        "Unreasonably_Restrains_Trade": "Defect",
        "Person_Monopolizes_Or_Attempts": "Act",
        "Offering_Of_Securities": "Act",
        "Manipulative_Or_Deceptive_Act": "Defect",
        "Mark_Used_In_Commerce": "Status",
        "Confusingly_Similar_Mark_Used": "Act",
        # IP
        "Work_Is_Original": "Status",
        "Work_Fixed_In_Tangible_Medium": "Status",
        "Unauthorized_Use": "Act",
        "Invention_Is_New_Useful_Process_Machine_Manufacture": "Status",
        "Patent_In_Force": "Status",
        "Unauthorized_Make_Use_Or_Sell": "Act",
        "Copyright_Infringement_Established": "Status",
        "Patent_Infringement_Established": "Status",
        # Sanctions
        "Unusual_Extraordinary_Threat_To_US": "Status",
        "Person_Is_SDN_Listed": "Status",
        "Entity_On_Entity_List": "Status",
    }

    _MODAL_MAPPING: Dict[str, str] = {
        "shall": "OBLIGATION",
        "must": "OBLIGATION",
        "is required to": "OBLIGATION",
        "shall not": "PROHIBITION",
        "may not": "PROHIBITION",
        "must not": "PROHIBITION",
        "is prohibited": "PROHIBITION",
        "is unlawful": "PROHIBITION",
        "may": "PERMISSION",
        "is entitled to": "PERMISSION",
        "is authorized to": "PERMISSION",
        "means": "CONSTITUTIVE",
        "is defined as": "CONSTITUTIVE",
        "includes": "CONSTITUTIVE",
    }

    def __init__(self):
        self._l0_map: Optional[Dict[str, str]] = None
        self._claim_table_cn: Optional[Dict[str, str]] = None
        self._claim_table_en: Optional[Dict[str, str]] = None
        self._blocking_rules: Optional[List[Dict]] = None

    def _ensure_loaded(self) -> None:
        if self._l0_map is not None:
            return
        base = Path(__file__).resolve().parents[2]

        # Load from term_L0_mappings.yaml
        l0 = dict(self._L0_MAP)
        term_path = base / "configs" / "us" / "term_L0_mappings.yaml"
        if term_path.exists():
            with open(term_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for t in data.get("term_mappings", []):
                term = t.get("term", "").strip()
                prim = t.get("l0_primitive", "?")
                if term and term not in l0:
                    l0[term] = prim

        # Also load from prc_us_alignment term mappings
        align_path = base / "configs" / "prc_us_alignment" / "term_L0_mappings.yaml"
        align_path2 = base / "configs" / "prc_us_alignment" / "term_L0_mappings_batch2.yaml"
        for tp in [align_path, align_path2]:
            if tp.exists():
                with open(tp, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for t in data.get("term_alignments", []):
                    us = t.get("term_us", "").strip()
                    prim = t.get("l0_chain", {}).get("primitive", "?")
                    if us and us not in l0:
                        l0[us] = prim

        self._l0_map = l0
        self._claim_table_cn = {}
        self._claim_table_en = {}

        # Load US→HK blocking rules
        base = Path(__file__).resolve().parents[2]
        block_path = base / "configs" / "us" / "blocking_rules.yaml"
        if block_path.exists():
            with open(block_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._blocking_rules = data.get("rules", [])
        else:
            self._blocking_rules = []

    def check_blocking(self, fact_id: str) -> Optional[Dict]:
        """Check if a fact is blocked by US→HK blocking rules."""
        self._ensure_loaded()
        for rule in self._blocking_rules or []:
            if rule.get("trigger_fact") == fact_id:
                action = rule.get("action", {})
                if action.get("type") in ("FORCE_VOID", "FORCE_SUPPRESS"):
                    return {
                        "rule_id": rule.get("id"),
                        "action_type": action.get("type"),
                        "map_to": action.get("map_to", ""),
                        "description": rule.get("description", ""),
                    }
        return None

    def map_to_L0(self, domain_concept: str) -> str:
        self._ensure_loaded()
        return self._l0_map.get(domain_concept, "?")

    def get_claim_tables(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        self._ensure_loaded()
        return self._claim_table_cn, self._claim_table_en

    def get_modal_mapping(self) -> Dict[str, str]:
        return dict(self._MODAL_MAPPING)

    def get_legal_family(self) -> str:
        return "common_law"

    def validate_against_guardrails(self, state: IRState) -> Dict:
        issues = []
        blocked = []
        for fid, fact in state.facts.items():
            l0 = self.map_to_L0(fid)
            if l0 == "?":
                issues.append(f"{fid}: no L0 mapping")
            block_result = self.check_blocking(fid)
            if block_result:
                blocked.append(block_result)
        return {
            "valid": len(issues) == 0 and len(blocked) == 0,
            "issues": issues,
            "blocked": blocked,
        }
