#!/usr/bin/env python3
"""juris-calculus 类型定义"""
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
from enum import Enum

class LegalDomain(Enum):
    CIVIL = "民事"; CRIMINAL = "刑事"; ADMINISTRATIVE = "行政"

@dataclass
class LegalFact:
    id: str; description: str = ""; source: str = ""; formalizable: float = 1.0

@dataclass
class TaintNode:
    rule_id: str; claim_id: str; taint_source: str; formalizable_score: float; depth: int

@dataclass
class LegalClaim:
    id: str; description: str = ""; confidence: float = 1.0
    taint_chain: List[TaintNode] = field(default_factory=list)
    requires_human_review: bool = False
    def taint_summary(self) -> str:
        return "CLEAR" if not self.taint_chain else " -> ".join(f"{n.rule_id}({n.taint_source})" for n in self.taint_chain)

@dataclass
class LegalRule:
    id: str; premise_atoms: List[str] = field(default_factory=list)
    head_claim: str = ""; exception_chain: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    mechanical_exception: bool = True; head_type: str = "HORN"

@dataclass
class IRState:
    facts: Dict[str, LegalFact] = field(default_factory=dict)
    negative_facts: Dict[str, LegalFact] = field(default_factory=dict)
    claims: Dict[str, LegalClaim] = field(default_factory=dict)
    rules_applied: Set[str] = field(default_factory=set)
    temporal_scope: dict = field(default_factory=lambda: {"fact_date": "2021-03-15", "governing_law": "PRC_CivilCode_2021"})
    world_id: str = "W1"; iteration_count: int = 0; max_iterations: int = 100
    domain: LegalDomain = LegalDomain.CIVIL
