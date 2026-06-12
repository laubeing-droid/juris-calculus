#!/usr/bin/env python3
"""HK addon — Hong Kong law adapter (Sale of Goods Ordinance Cap 26 etc.)."""
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from compiler_core.adapter_base import JurisdictionAdapter
from compiler_core.types import LegalFact, IRState, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.constraint_validator import ConstraintValidator
from compiler_core.config_paths import rules_path as _cp_rules, overrides_path as _cp_overrides


class HKAdapter(JurisdictionAdapter):
    jurisdiction = "HK"
    rules_path = _cp_rules("hk")
    overrides_path = _cp_overrides("hk")

    _L0_MAP = {
        "ContractOfSale_Exists": "Status",
        "Buyer_FailsToPay": "Act",
        "Delivery_Occurred": "Act",
        "Court_Ruled_ContractVoid": "Status",
        "Director_Acted_UltraVires": "Power",
        "SpecifiedPeriod_Expired": "Status",
        "Contract_Induced_By_Fraud": "Defect",
        "Goods_Perished_BeforeContract": "Defect",
        "Party_Lacks_Capacity": "Agent",
        "Goods_Defective": "Defect",
        "Consideration_Provided": "Status",
        "Seller_RightToSell": "Power",
        "Buyer_QuietPossession": "Status",
    }

    def map_to_L0(self, concept: str) -> str:
        return self._L0_MAP.get(concept, "?")

    def validate_against_guardrails(self, state: IRState) -> Dict:
        issues = []
        for fid, fact in state.facts.items():
            l0 = self.map_to_L0(fid)
            if l0 == "?":
                issues.append(f"{fid}: no L0 mapping")
        constraint_validator = ConstraintValidator(overrides_path=self.overrides_path)
        triggered_constraints = []
        for cr in constraint_validator._constraint_rules:
            trigger = cr.get("trigger_fact", "")
            if trigger in state.facts and state.facts[trigger].extraction_confidence > 0:
                conds = cr.get("additional_conditions", [])
                all_met = True
                for c in conds:
                    if c.startswith("NOT "):
                        neg = c[4:]
                        if neg in state.facts and state.facts[neg].extraction_confidence > 0:
                            all_met = False
                    elif c not in state.facts or state.facts[c].extraction_confidence <= 0:
                        all_met = False
                if all_met:
                    triggered_constraints.append({
                        "id": cr.get("id", ""),
                        "action": cr.get("action", ""),
                        "target": cr.get("target", ""),
                        "new_state": cr.get("new_state", ""),
                        "irreversible": cr.get("irreversible", False),
                    })
        return {"valid": len(issues) == 0, "issues": issues, "constraints_triggered": triggered_constraints}
