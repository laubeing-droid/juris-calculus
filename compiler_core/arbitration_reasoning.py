"""Arbitration reasoning module."""
from dataclasses import dataclass


@dataclass
class ArbitrationAnalysis:
    arbitration_clause_valid: bool = False
    arbitral_institution: str = ""
    seat_of_arbitration: str = ""
    applicable_law: str = ""

    def evaluate_enforceability(self) -> dict:
        return {
            "clause_valid": self.arbitration_clause_valid,
            "enforceable": self.arbitration_clause_valid and bool(self.arbitral_institution),
        }
