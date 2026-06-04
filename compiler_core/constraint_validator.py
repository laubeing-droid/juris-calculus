"""
constraint_validator.py — Rebuttal Hook + Audit Trail + Oscillation Guard
三层架构之约束层 v0.9.1
- 绝对反驳(Absolute_Rebuttal): 置信度→0
- 条件反驳(Conditional_Rebuttal): 事实+附加条件→置信度→0
- 迭代保护: MAX_MODIFICATION_COUNT=3 防止循环振荡
- 独立条款: 争议解决/清算条款不受合同整体效力影响
"""
import yaml, json, logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timezone

MAX_MODIFICATION_COUNT = 3  # 防止循环振荡的硬上限

logger = logging.getLogger(__name__)

@dataclass
class RebuttalResult:
    triggered: bool = False
    claim_id: str = ""
    rule_id: str = ""
    trigger_fact: str = ""
    rebuttal_criteria: List[str] = field(default_factory=list)
    confidence_before: float = 0.0
    confidence_after: float = 0.0
    timestamp: str = ""
    new_state: str = ""  # v1.1: 状态机——反驳触发后的新效力状态 (VOID/VOIDABLE)

class ConstraintValidator:
    """
    运行时约束校验器 v0.9.1。
    - 加载 core_ontology.yaml → 在 evaluator 钩子中检查 Defeasible Atom 的反驳条件。
    - 加载失败时降级：所有原子按 Strict 处理，引擎照常运行。
    - 迭代保护：每个可废止原子的修改次数上限为 MAX_MODIFICATION_COUNT。
    """

    def __init__(self, ontology_path: Optional[str] = None, overrides_path: Optional[str] = None):
        self.ontology = {}
        self.L1_meta = {}
        self._constraint_rules = []  # v1.1: L0_overrides constraint_rules
        self._loaded = False
        self._modification_counts: Dict[str, int] = {}
        if ontology_path is None:
            ontology_path = str(Path(__file__).resolve().parents[1] / "configs" / "core_ontology.yaml")
        try:
            with open(ontology_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            self.ontology = raw.get("concepts", {})
            self.L1_meta = raw.get("L1_meta_ontology", {}).get("concepts", {})
            self._loaded = True
            logger.info(f"ConstraintValidator v0.9.1 loaded: {len(self.ontology)} concepts, {len(self.L1_meta)} L1 meta")
        except Exception as e:
            logger.warning(f"ConstraintValidator: ontology load failed ({e}) — all atoms treated as Strict. Engine safe.")

        # v1.1: 加载 L0_overrides 中的强制收敛规则（支持法域特定）
        if overrides_path is None:
            overrides_path = str(Path(__file__).resolve().parents[1] / "configs" / "L0_overrides_hk.yaml")
        try:
            with open(overrides_path, "r", encoding="utf-8") as f:
                ov = yaml.safe_load(f)
            self._constraint_rules = ov.get("constraint_rules", [])
            if self._constraint_rules:
                logger.info(f"ConstraintValidator: loaded {len(self._constraint_rules)} L0 constraint rules from {overrides_path}")
        except Exception as e:
            logger.warning(f"ConstraintValidator: L0_overrides load failed ({e}) — constraint rules disabled.")

    @property
    def loaded(self) -> bool:
        return self._loaded

    def get_concept(self, concept_name: str) -> Optional[Dict]:
        return self.ontology.get(concept_name)

    def resolve_concept(self, concept_name: str) -> Optional[Dict]:
        """解析概念：精确匹配 → 别名匹配 → 模糊匹配 → None。"""
        # 精确匹配
        if concept_name in self.ontology:
            return self.ontology[concept_name]
        # 别名匹配
        for onto_name, onto_def in self.ontology.items():
            aliases = onto_def.get("aliases", [])
            if concept_name in aliases:
                return onto_def
        # 模糊匹配
        for onto_name, onto_def in self.ontology.items():
            if concept_name.lower() in onto_name.lower() or onto_name.lower() in concept_name.lower():
                return onto_def
        return None

    def is_defeasible(self, concept_name: str) -> bool:
        if not self._loaded:
            return False
        c = self.ontology.get(concept_name)
        if c is None:
            return False
        return c.get("attributes", {}).get("defeasible", False)

    def get_lex_loci_weight(self, concept_name: str, jurisdiction: str) -> float:
        """获取法域权重。未定义时返回 0.0。"""
        if not self._loaded:
            return 0.0
        c = self.ontology.get(concept_name)
        if c is None:
            return 0.0
        return c.get("behavioral_logic", {}).get("lex_loci_weight", {}).get(jurisdiction, 0.0)

    def check_rebuttal(self, rule_head_claim: str, concepts: List[str], state) -> RebuttalResult:
        """
        检查可废止原子是否被事实反驳。
        支持两种反驳模式：
        - Absolute_Rebuttal: 事实存在 → 置信度归零
        - Conditional_Rebuttal: 事实存在 + 所有附加条件满足 → 置信度归零
        """
        result = RebuttalResult()
        if not self._loaded:
            return result

        jurisdiction = getattr(state, "jurisdiction", "") or "HK"

        for concept_name in concepts:
            onto_def = self.resolve_concept(concept_name)
            if onto_def is None:
                continue
            if not onto_def.get("attributes", {}).get("defeasible", False):
                continue

            rebuttal_specs = onto_def.get("attributes", {}).get("rebuttal_criteria", [])

            for spec in rebuttal_specs:
                # v2 format: list of dicts with type/jurisdiction/fact
                if isinstance(spec, dict):
                    spec_type = spec.get("type", "Absolute_Rebuttal")
                    spec_jdx = spec.get("jurisdiction", [])
                    fact_name = spec.get("fact", "")
                    conditions = spec.get("additional_conditions", [])

                    # Jurisdiction filter
                    if spec_jdx and jurisdiction not in spec_jdx:
                        continue

                    if fact_name not in state.facts:
                        continue
                    fact = state.facts[fact_name]
                    if fact.extraction_confidence <= 0:
                        continue

                    # For conditional rebuttal, check additional conditions
                    if spec_type == "Conditional_Rebuttal":
                        all_met = all(
                            c in state.facts and state.facts[c].extraction_confidence > 0
                            for c in conditions
                        )
                        if not all_met:
                            continue

                    result.triggered = True
                    result.claim_id = rule_head_claim
                    result.trigger_fact = fact_name
                    result.rebuttal_criteria = [fact_name] + conditions
                    result.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    # v1.1 State Machine: record new validity state
                    result.new_state = spec.get("effect", "").split("_")[-1] if spec.get("effect") else "VOID"
                    if spec_type == "Conditional_Rebuttal" and result.new_state == "Voidable":
                        result.new_state = "VOIDABLE"
                    # Oscillation guard
                    key = f"{rule_head_claim}:{fact_name}"
                    self._modification_counts[key] = self._modification_counts.get(key, 0) + 1
                    if self._modification_counts[key] > MAX_MODIFICATION_COUNT:
                        logger.warning(f"[OSCILLATION_GUARD] {key} modified {self._modification_counts[key]} times — halted")
                        return result  # Still apply but log warning
                    return result

                # v1 backward compat: plain string facts
                elif isinstance(spec, str):
                    if spec in state.facts:
                        fact = state.facts[spec]
                        if fact.extraction_confidence > 0:
                            result.triggered = True
                            result.claim_id = rule_head_claim
                            result.trigger_fact = spec
                            result.rebuttal_criteria = [s for s in onto_def["attributes"]["rebuttal_criteria"] if isinstance(s, str)]
                            result.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                            return result
        return result

    def get_undefined_concepts(self, concepts: List[str]) -> List[str]:
        """返回未在本体中定义的概念列表。"""
        return [c for c in concepts if self.resolve_concept(c) is None]

    def check_constraint_rules(self, state) -> List[Dict]:
        """v1.1 强制收敛: 检查 L0_overrides 中的 constraint_rules。
        遍历 state.facts → 匹配 trigger_fact → 执行 action (force_state/suppress_power)。
        返回触发的约束规则列表。
        """
        results = []
        if not self._loaded or not self._constraint_rules:
            return results

        for cr in self._constraint_rules:
            trigger = cr.get("trigger_fact", "")
            if trigger not in state.facts:
                continue
            if state.facts[trigger].extraction_confidence <= 0:
                continue

            # 附加条件检查
            conditions = cr.get("additional_conditions", [])
            all_met = True
            for cond in conditions:
                if cond.startswith("NOT "):
                    neg_fact = cond[4:]
                    if neg_fact in state.facts and state.facts[neg_fact].extraction_confidence > 0:
                        all_met = False
                        break
                else:
                    if cond not in state.facts or state.facts[cond].extraction_confidence <= 0:
                        all_met = False
                        break
            if not all_met:
                continue

            results.append({
                "id": cr.get("id", ""),
                "action": cr.get("action", "force_state"),
                "target": cr.get("target", ""),
                "new_state": cr.get("new_state", ""),
                "irreversible": cr.get("irreversible", False),
                "reason": cr.get("reason", ""),
            })

        return results

    def resolve_L0_primitive(self, concepts: List[str]) -> str:
        """v1.1 护栏3: 溯源——从 L2 概念链追溯至 L0 原语。
        L2(parent=L1 concept) → L1.maps_to_L0 → 返回 L0 原语名。
        """
        if not self._loaded:
            return ""
        for concept_name in concepts:
            onto_def = self.resolve_concept(concept_name)
            if onto_def is None:
                continue
            parent_l1 = onto_def.get('parent', '')
            if not parent_l1:
                continue
            # L1→L0 mapping from L1_meta
            l1_def = self.L1_meta.get(parent_l1)
            if l1_def and l1_def.get('maps_to_L0'):
                return l1_def['maps_to_L0']
        return ""

    def validate_L2_L0_completeness(self) -> List[str]:
        """v1.1 护栏1: L2→L0 完备性校验。L2.parent→L1.maps_to_L0→检查可达性。"""
        issues = []
        if not self._loaded:
            return issues
        L0_SET = {'Agent', 'Asset', 'Act', 'Status', 'Power', 'Defect'}
        for name, c_def in self.ontology.items():
            parent_l1 = c_def.get('parent', '')
            if not parent_l1:
                continue
            l1_meta = self.L1_meta.get(parent_l1)
            if not l1_meta:
                issues.append(f'{name}: parent={parent_l1} → L1 无定义')
                continue
            l0 = l1_meta.get('maps_to_L0', '')
            if not l0 or l0 not in L0_SET:
                issues.append(f'{name}: parent={parent_l1} → maps_to_L0={l0} → 不在 L0 原语中')
        return issues

    def to_audit_json(self, result: RebuttalResult, rule_id: str = "",
                      confidence_before: float = 0.0) -> Dict[str, Any]:
        """生成结构化审计日志。"""
        return {
            "claim_id": result.claim_id,
            "rule_id": rule_id,
            "status": "rebutted" if result.triggered else "passed",
            "trigger_fact": result.trigger_fact or "",
            "rebuttal_criteria": result.rebuttal_criteria,
            "confidence_before": round(confidence_before, 4),
            "confidence_after": 0.0 if result.triggered else round(confidence_before, 4),
            "timestamp": result.timestamp,
        }
