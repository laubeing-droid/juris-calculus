"""Evidence evaluation system.

S(e) = reliability * independence * authenticity
C_chain = documented_links / required_links
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EvidenceItem:
    id: str
    description: str
    reliability: float = 1.0
    independence: float = 1.0
    authenticity: float = 1.0

    @property
    def credibility_score(self) -> float:
        return self.reliability * self.independence * self.authenticity


def compute_chain_completeness(documented_links: int, required_links: int) -> float:
    if required_links == 0:
        return 1.0
    return min(1.0, documented_links / required_links)


def detect_contradiction(e1: EvidenceItem, e2: EvidenceItem, fact_id: str) -> Optional[dict]:
    if e1.credibility_score > 0 and e2.credibility_score > 0:
        if e1.description != e2.description:
            return {
                "type": "CONTRADICTION",
                "fact_id": fact_id,
                "evidence_1": e1.id,
                "evidence_2": e2.id,
                "discount_factor": 0.5,
            }
    return None
