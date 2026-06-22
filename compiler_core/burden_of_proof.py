"""Burden of proof tracker."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class BurdenAllocation:
    party: str
    allegation: str
    burden_type: str
    standard: str
    evidence_submitted: List[str] = field(default_factory=list)
    met: bool = False


@dataclass
class BurdenTracker:
    allocations: List[BurdenAllocation] = field(default_factory=list)

    def add(self, party: str, allegation: str, burden_type: str, standard: str):
        self.allocations.append(BurdenAllocation(
            party=party, allegation=allegation,
            burden_type=burden_type, standard=standard
        ))

    def submit_evidence(self, allegation: str, evidence_id: str):
        for a in self.allocations:
            if a.allegation == allegation:
                a.evidence_submitted.append(evidence_id)

    def evaluate_completion(self, allegation: str) -> dict:
        for a in self.allocations:
            if a.allegation == allegation:
                return {
                    "allegation": allegation,
                    "party": a.party,
                    "standard": a.standard,
                    "evidence_count": len(a.evidence_submitted),
                    "burden_met": len(a.evidence_submitted) > 0,
                }
        return {"allegation": allegation, "burden_met": False}
