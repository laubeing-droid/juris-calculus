"""Compliance monitoring module."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class ComplianceCheck:
    regulation_id: str
    requirement: str
    status: str = "unchecked"
    evidence: List[str] = field(default_factory=list)

    def evaluate(self, evidence: List[str]) -> dict:
        self.evidence = evidence
        self.status = "compliant" if evidence else "non_compliant"
        return {"regulation": self.regulation_id, "status": self.status}
