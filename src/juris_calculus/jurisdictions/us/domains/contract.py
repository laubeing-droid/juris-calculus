#!/usr/bin/env python3
"""美国法域 — UCC Article 2 合同纠纷 Provider"""
import os
from pathlib import Path
from src.juris_calculus.core.base import BaseDomainProvider

class USContractProvider(BaseDomainProvider):
    @property
    def domain_id(self) -> str: return "us_contract"
    @property
    def jurisdiction(self) -> str: return "us"
    @property
    def atom_registry(self) -> dict:
        return {
            "ContractFormed": "ContractStatus.FORMED",
            "GoodsDelivered": "PerformanceStatus.FULFILLED",
            "PaymentDue": "Financial.PAYMENT_DUE",
            "BreachAlleged": "BreachStatus.BREACHED",
            "Damages": "Damages.ACTUAL_LOSS",
            "ForceMajeure": "Defense.FORCE_MAJEURE",
            "Impossibility": "Defense.IMPOSSIBILITY",
        }
    @property
    def rules(self) -> list:
        from compiler_core.evaluator import load_rules_from_yaml
        p = Path(__file__).resolve().parents[5] / "configs" / "en_US" / "rules.yaml"
        return load_rules_from_yaml(str(p)) if p.exists() else []
    @property
    def concepts(self) -> list:
        return ["Contract","Offer","Acceptance","Consideration","Delivery","Payment","Breach","Damages","Remedies"]
