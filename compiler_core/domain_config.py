#!/usr/bin/env python3
"""juris-calculus 领域配置"""
from dataclasses import dataclass, field
from typing import Dict, Set, Tuple
from .types import LegalDomain

@dataclass
class DomainConfig:
    domain: LegalDomain = LegalDomain.CIVIL
    weights: Tuple[float,float,float,float] = (0.2,0.2,0.4,0.2)
    taint_threshold: float = 0.5; hard_audit_threshold: float = 0.2
    k_max: int = 3; critical_streak_max: int = 3; critical_score_threshold: float = 0.3
    concept_registry: Set[str] = field(default_factory=set)
    valid_transitions: Dict[str,list] = field(default_factory=dict)

CIVIL_CONCEPTS = {"Contract","Signature","Delivery","Damages","ForceMajeure","Payment","Interest","Termination","Breach","Notice","Indemnification","Warranty","LiquidatedDamages","SpecificPerformance","Arbitration","GoverningLaw","Confidentiality","LimitationOfLiability","EffectiveDate","Renewal","Expiration","Amendment","Waiver","ThirdParty","Assignment","Price","Quantity","Acceptance","Rejection","MaterialAdverseChange","IndirectDamages","ConsequentialDamages"}
CRIMINAL_CONCEPTS = {"故意","过失","既遂","未遂","自首","立功","正当防卫","紧急避险","累犯","主犯","从犯","管制","拘役","有期徒刑","无期徒刑","死刑","罚金","物证","书证","鉴定意见","电子数据"}

CIVIL_CONFIG = DomainConfig(domain=LegalDomain.CIVIL, k_max=3, taint_threshold=0.5, hard_audit_threshold=0.2,
    concept_registry=CIVIL_CONCEPTS,
    valid_transitions={"立案":["证据交换"],"证据交换":["一审审理"],"一审审理":["一审判决"],"一审判决":["上诉"],"上诉":["二审审理"],"二审审理":["二审判决"],"二审判决":["再审"]})
CRIMINAL_CONFIG = DomainConfig(domain=LegalDomain.CRIMINAL, weights=(0.15,0.2,0.45,0.2), k_max=4, hard_audit_threshold=0.4, critical_streak_max=2, concept_registry=CRIMINAL_CONCEPTS,
    valid_transitions={"立案":["侦查"],"侦查":["审查起诉"],"审查起诉":["提起公诉","不起诉"],"提起公诉":["一审审理"],"一审审理":["一审判决"],"一审判决":["上诉","抗诉"],"抗诉":["二审审理"],"二审审理":["二审判决"],"二审判决":["再审"]})

DOMAIN_REGISTRY = {LegalDomain.CIVIL:CIVIL_CONFIG, LegalDomain.CRIMINAL:CRIMINAL_CONFIG}
def get_domain_config(d: LegalDomain = LegalDomain.CIVIL) -> DomainConfig:
    return DOMAIN_REGISTRY.get(d, CIVIL_CONFIG)
