#!/usr/bin/env python3
"""
juris-calculus Pipeline 守卫层 v1.0
三层防御：强度门控 + 断言校验 + 回归测试接口
"""
import re, yaml
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field

ONTOLOGY_PATH = Path(__file__).resolve().parents[1] / "configs" / "zh_CN" / "ontology_map.yaml"

# ═══════════════════════════════════════════
# 1. 二元强度门控（Boolean Gate）
# ═══════════════════════════════════════════

@dataclass
class AlignedFact:
    atom_id: str
    strength: int = 3          # 1-5 对应强度
    source: str = ""           # RAG 来源
    injectable: bool = False   # 是否可以注入 Horn 引擎
    requires_companion: bool = False  # 是否需要伴生原子

STRENGTH_GATE = {
    5: {"inject": True,  "companion": False, "label": "基本等同，直接注入"},
    4: {"inject": True,  "companion": False, "label": "高度近似，直接注入"},
    3: {"inject": True,  "companion": True,  "label": "功能近似，注入+伴生原子"},
    2: {"inject": False, "companion": False, "label": "部分重叠，拒注入"},
    1: {"inject": False, "companion": False, "label": "不建议对应，拒注入"},
}

def gate_aligned_facts(facts: List[AlignedFact]) -> Tuple[List[str], List[str], List[str]]:
    """
    强度门控：将 LLM/RAG 产出的对齐事实按强度分级
    
    Returns:
        (injectable_atoms, companion_atoms, blocked_with_reason)
    """
    injectable = []
    companions = []
    blocked = []

    for f in facts:
        gate = STRENGTH_GATE.get(f.strength, {"inject": False, "companion": False})
        if gate["inject"]:
            injectable.append(f.atom_id)
            if gate["companion"]:
                companions.append(f"Fact.SEMANTIC_WEAK_ALIGNMENT")
                companions.append(f"Fact.ALIGNMENT_SOURCE_{f.source.replace(' ','_')[:20]}")
        else:
            blocked.append(f"{f.atom_id} (强度{f.strength}: {gate['label']})")

    return injectable, companions, blocked


# ═══════════════════════════════════════════
# 2. 断言校验器（Semantic Assertion）
# ═══════════════════════════════════════════

def load_atom_whitelist() -> Set[str]:
    """从 ontology_map.yaml 加载全部合法原子白名单"""
    whitelist = set()
    if not ONTOLOGY_PATH.exists():
        return whitelist
    data = yaml.safe_load(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    for domain_key, domain_cfg in data.items():
        if isinstance(domain_cfg, dict) and "fact_atoms" in domain_cfg:
            for cn, en in domain_cfg["fact_atoms"].items():
                whitelist.add(en)
    # 允许的通用原子
    whitelist.update({
        "Fact.SEMANTIC_WEAK_ALIGNMENT",
        "Fact.DEFENDANT_REQUESTS_REDUCTION",
        "Fact.LIMITATION_INTERRUPTION_EXISTS",
        "Defense.BLOCKED_NO_EQUIVALENT",
    })
    return whitelist

_WHITELIST = None

def assert_atoms(facts: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """
    断言校验：只有白名单内的原子才能进入 juris-calculus
    
    Returns:
        (clean_facts, rejected_facts_with_reason)
    """
    global _WHITELIST
    if _WHITELIST is None:
        _WHITELIST = load_atom_whitelist()

    clean = {}
    rejected = []

    for atom_id, description in facts.items():
        # 跳过描述性字符串（用户文本，不是原子ID）
        if len(atom_id) > 80 or " " in atom_id:
            # 可能是原始文本片段，保留但标记
            clean[atom_id] = description
            continue
        
        if atom_id in _WHITELIST:
            clean[atom_id] = description
        else:
            rejected.append(f"REJECTED: '{atom_id}' 不在白名单中 ({description[:60]})")

    return clean, rejected


# ═══════════════════════════════════════════
# 3. 语义回归测试接口
# ═══════════════════════════════════════════

GOLDEN_CASES = [
    {
        "id": "GOLDEN_CROSS_BORDER_001",
        "title": "中美供应链买卖合同纠纷",
        "facts": {
            "Contract.Status.FORMED": "中美双方签署跨境供货合同",
            "Contract.Breach.OCCURRED": "美方未按期交付货物",
            "Contract.Performance.PAYMENT_OVERDUE": "中方已支付货款",
        },
        "expected_convergence": True,
        "expected_min_claims": 3,
        "expected_max_hours": 200,
    },
]


@dataclass
class RegressionReport:
    case_id: str
    passed: bool
    convergence: bool
    claims: int
    hours: float
    issues: List[str] = field(default_factory=list)

def run_semantic_regression(evaluator_func) -> List[RegressionReport]:
    """每次对齐框架更新后，跑这 5 个黄金案卷验证"""
    reports = []
    for case in GOLDEN_CASES:
        try:
            result = evaluator_func(case["facts"], case_id=case["id"])
            claims = len(result.claims) if hasattr(result, 'claims') else 0
            hours = getattr(result, 'pred_hours', 0)
            conv = hasattr(result, 'convergence') and result.convergence

            issues = []
            if claims < case["expected_min_claims"]:
                issues.append(f"结论数不足: {claims} < {case['expected_min_claims']}")
            if hours > case["expected_max_hours"]:
                issues.append(f"工时超标: {hours:.0f}h > {case['expected_max_hours']}h")

            reports.append(RegressionReport(
                case_id=case["id"],
                passed=len(issues) == 0,
                convergence=conv,
                claims=claims,
                hours=hours,
                issues=issues,
            ))
        except Exception as e:
            reports.append(RegressionReport(
                case_id=case["id"],
                passed=False, convergence=False, claims=0, hours=0,
                issues=[f"CRASH: {e}"],
            ))
    return reports
