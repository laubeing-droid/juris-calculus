#!/usr/bin/env python3
"""juris-calculus 领域配置"""
from dataclasses import dataclass, field
from typing import Dict, Set, Tuple
from .types import LegalDomain
# === V6: 自由裁量概念注册表 ===
# 命中以下概念的FactCandidate自动标记为TAINTED，置信度上限锁定0.3
# 理由：这些概念在中国司法实践中高度依赖法官自由心证，无法机械判定
DISCRETIONARY_CONCEPTS = {
    "显失公平", "公序良俗", "诚实信用", "合理注意", "重大过失",
    "不可抗力认定", "情势变更", "公平原则", "合理期限", "适当补偿",
    "恶意串通", "乘人之危", "格式条款无效认定", "违约金过高",
    "因果关系强度", "过错程度"
}

def check_discretionary(fact_description: str) -> dict:
    """
    V6 自由裁量概念检测。
    如果事实描述中命中自由裁量概念，返回TAINTED标记和上限置信度。
    这确保"显失公平""公序良俗"等概念不会未经人工确认就进入FixpointEvaluator。
    """
    result = {"tainted": False, "matched_concepts": [], "confidence_cap": 1.0}
    for concept in DISCRETIONARY_CONCEPTS:
        if concept in fact_description:
            result["tainted"] = True
            result["matched_concepts"].append(concept)
    if result["tainted"]:
        result["confidence_cap"] = 0.3
    return result

@dataclass
class DomainConfig:
    domain: LegalDomain = LegalDomain.CIVIL
    weights: Tuple[float,float,float,float] = (0.2,0.2,0.4,0.2)
    taint_threshold: float = 0.5; hard_audit_threshold: float = 0.2
    k_max: int = 3; critical_streak_max: int = 3; critical_score_threshold: float = 0.3
    concept_registry: Set[str] = field(default_factory=set)
    valid_transitions: Dict[str,list] = field(default_factory=dict)
    # V6: 是否启用自由裁量概念自动TAINTED检测
    enable_discretionary_taint: bool = False  # 默认关闭，中国法下由预检层处理

CIVIL_CONCEPTS = {"Contract","Signature","Delivery","Damages","ForceMajeure","Payment","Interest","Termination","Breach","Notice","Indemnification","Warranty","LiquidatedDamages","SpecificPerformance","Arbitration","GoverningLaw","Confidentiality","LimitationOfLiability","EffectiveDate","Renewal","Expiration","Amendment","Waiver","ThirdParty","Assignment","Price","Quantity","Acceptance","Rejection","MaterialAdverseChange","IndirectDamages","ConsequentialDamages"}
CRIMINAL_CONCEPTS = {"故意","过失","既遂","未遂","自首","立功","正当防卫","紧急避险","累犯","主犯","从犯","管制","拘役","有期徒刑","无期徒刑","死刑","罚金","物证","书证","鉴定意见","电子数据"}

CIVIL_CONFIG = DomainConfig(domain=LegalDomain.CIVIL, k_max=3, taint_threshold=0.5, hard_audit_threshold=0.2,
    concept_registry=CIVIL_CONCEPTS,
    valid_transitions={"立案":["证据交换"],"证据交换":["一审审理"],"一审审理":["一审判决"],"一审判决":["上诉"],"上诉":["二审审理"],"二审审理":["二审判决"],"二审判决":["再审"]})
CRIMINAL_CONFIG = DomainConfig(domain=LegalDomain.CRIMINAL, weights=(0.15,0.2,0.45,0.2), k_max=4, hard_audit_threshold=0.4, critical_streak_max=2, concept_registry=CRIMINAL_CONCEPTS,
    valid_transitions={"立案":["侦查"],"侦查":["审查起诉"],"审查起诉":["提起公诉","不起诉"],"提起公诉":["一审审理"],"一审审理":["一审判决"],"一审判决":["上诉","抗诉"],"抗诉":["二审审理"],"二审审理":["二审判决"],"二审判决":["再审"]})

DOMAIN_REGISTRY = {LegalDomain.CIVIL:CIVIL_CONFIG, LegalDomain.CRIMINAL:CRIMINAL_CONFIG}
def get_domain_config(d: LegalDomain = LegalDomain.CIVIL) -> DomainConfig:
    cfg = DOMAIN_REGISTRY.get(d, CIVIL_CONFIG)
    # 尝试从 YAML 加载中文概念注册表（覆盖硬编码英文概念）
    try:
        import yaml, os
        yaml_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'zh_CN', 'domain_config.yaml')
        if os.path.exists(yaml_path):
            dc = yaml.safe_load(open(yaml_path, encoding='utf-8'))
            if 'concept_registry' in dc:
                cfg.concept_registry = set(dc['concept_registry'])
            if 'alpha_calibrated' in dc:
                cfg.alpha = dc['alpha_calibrated']
    except Exception:
        pass
    return cfg
