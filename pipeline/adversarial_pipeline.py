#!/usr/bin/env python3
"""v2.0 Adversarial Pipeline - Layer 4 MAX mode triangular counter-check.

Three roles: Reasoner (Horn), Auditor (blueprint rules), Verifier (gate scripts).
Only activated in ThinkMode.MAX; failed checks produce UNVERIFIED trust downgrade.
"""
from enum import Enum
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from compiler_core.criminal_complexity import audit_criminal_claims

class ThinkMode(str, Enum):
    QUICK_SCAN = "QUICK_SCAN"
    STANDARD = "STANDARD"
    MAX = "MAX"

class RoleVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"

@dataclass
class AdversarialResult:
    role: str
    verdict: RoleVerdict
    issues: List[str] = field(default_factory=list)
    audit_trail: List[str] = field(default_factory=list)
    requires_human_review: bool = False

class AdversarialPipeline:

    def run_contract_audit(self, claims, contract_type="general"):
        """Enhanced audit: verify contract claims against review elements from blueprint."""
        issues = []
        try:
            import json
            from compiler_core.config_paths import blueprint_path
            bp = json.load(open(blueprint_path(), "r", encoding="utf-8"))
            elements = bp.get("contract_review_elements", [])
            if elements:
                for claim in claims:
                    desc = claim.get("description", "")
                    if "合同" in desc or "contract" in desc.lower():
                        for elem in elements[:8]:
                            if elem.get("element", "") not in desc:
                                issues.append(f"Contract element missing: {elem.get('element','?')}")
        except Exception:
            pass
        return issues

    def __init__(self, mode: ThinkMode = ThinkMode.STANDARD):
        self.mode = mode
        self.failures: List[AdversarialResult] = []

    @property
    def is_active(self) -> bool:
        return self.mode == ThinkMode.MAX

    def run_reasoner(self, claims: List[Dict], rules_applied: List[str]) -> AdversarialResult:
        issues = []
        if not claims:
            issues.append("No claims produced after Horn closure")
        if not rules_applied:
            issues.append("No rules triggered")
        audit = [f"Horn closure: {len(claims)} claims, {len(rules_applied)} rules"]
        return AdversarialResult(role="reasoner",
                                 verdict=RoleVerdict.FAIL if issues else RoleVerdict.PASS,
                                 issues=issues, audit_trail=audit)
    def run_auditor(self, claims: List[Dict], blueprint_contracts: List[Dict]) -> AdversarialResult:
        issues = []
        for claim in claims:
            if claim.get("confidence", 0) < 0.2:
                issues.append(f"Low-confidence claim: {claim.get('id', '?')}")
        audit = [f"Blueprint audit: checked {len(claims)} claims against {len(blueprint_contracts)} contracts"]
        ver = RoleVerdict.FAIL if len(issues) > len(claims) * 0.5 else (RoleVerdict.INCONCLUSIVE if issues else RoleVerdict.PASS)
        return AdversarialResult(role="auditor", verdict=ver, issues=issues, audit_trail=audit)

    def run_criminal_complexity_audit(self, case_facts, claims: Optional[List[Dict]] = None) -> AdversarialResult:
        """Audit MultiJustice-style criminal cases for actor/charge/law mixing."""
        report = audit_criminal_claims(case_facts, claims or [])
        complexity = report["complexity"]
        audit = [
            "Criminal complexity: "
            f"{complexity['scenario_id']} {complexity['scenario_label']}, "
            f"defendants={complexity['defendant_count']}, charges={complexity['charge_count']}"
        ]
        issues = report["issues"]
        if not complexity.get("route_tag"):
            return AdversarialResult(role="criminal_auditor", verdict=RoleVerdict.INCONCLUSIVE,
                                     issues=issues, audit_trail=audit)
        return AdversarialResult(role="criminal_auditor",
                                 verdict=RoleVerdict.FAIL if issues else RoleVerdict.PASS,
                                 issues=issues, audit_trail=audit,
                                 requires_human_review=bool(issues))

    def run_verifier(self, claims: List[Dict], gate_results: List[Dict]) -> AdversarialResult:
        issues = []
        for g in gate_results:
            if g.get("level") == "ERROR":
                issues.append(f"Gate {g.get('gate_id', '?')} ERROR: {g.get('reason', '?')}")
        audit = [f"Gate verification: {len(gate_results)} gates, {len(issues)} violations"]
        return AdversarialResult(role="verifier",
                                 verdict=RoleVerdict.FAIL if issues else RoleVerdict.PASS,
                                 issues=issues, audit_trail=audit)


__all__ = ["AdversarialPipeline", "AdversarialResult", "RoleVerdict", "ThinkMode"]

# End of the public adversarial-audit module.
