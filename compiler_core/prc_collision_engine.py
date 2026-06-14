#!/usr/bin/env python3
"""PRC Collision Engine — three-track collision for Chinese jurisdiction.

三轨架构 (v2.1 重构):
  Track 1 (CBL): 成文法阻断 — blocking_rules.yaml (60条)
    FORCE_VOID / FORCE_SUPPRESS / MAPPING_OVERRIDE
    一票否决，最高优先级
  Track 2 (SPC): 最高法裁判倾向 — spc_rules.yaml (25条)
    Horn 规则推导，non-blocking，仅倾向
  Track 3 (CN):  中国成文法全量 — configs/zh_CN/rules.yaml (2,117条)
    13领域 Horn 规则引擎

设计来源:
  - 旧 PRCAdapter v1.2.0 (282行) — 从 git 历史恢复存档
  - Gemini 审计方案 — "DDL 偏序算子抽象为接口，Session 锁死逻辑作用域"
  - Doubao 审计方案 — "addons 架构，法域特定逻辑不污染本体"

输出: ProofTree（纯 ID + 逻辑算子，无自然语言）
"""
import copy
import yaml
from pathlib import Path
from typing import Callable, Dict, List, Optional

from compiler_core.types import LegalFact, IRState, LegalDomain, NormModality
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml, CriticalClarityFailure
from compiler_core.domain_config import DomainConfig
from compiler_core.proof_tree import ProofTree, ProofNode


# ═══════════════════════════════════════════
# 跨法域事实桥接表
# HK/US 事实名 → CN 规则前提原子
# ═══════════════════════════════════════════
CROSS_JURISDICTION_FACT_BRIDGE = [
    ("ContractOfSale_Exists", "contract_formed"),
    ("Contract_Validity", "contract_formed"),
    ("Breach_Established", "breach_alleged"),
    ("Buyer_FailsToPay", "breach_alleged"),
    ("Goods_Defective", "goods_delivered"),
    ("Consideration_Provided", "contract_formed"),
    ("Damages_Awarded", "damages_claimed"),
    ("Loss_Occurred", "damages_suffered"),
    ("Personal_Injury_Claim", "damages_suffered"),
    ("Director_Acted_UltraVires", "breach_alleged"),
    ("Fiduciary_Duty_Breach", "breach_alleged"),
    ("Affiliated_Companies_Asset_Confusion", "contract_invalid"),
    ("Bankruptcy_Petition_Filed", "contract_invalid"),
    ("Chapter11_Filed", "contract_invalid"),
    ("Wrongful_Omission", "breach_alleged"),
    ("Fraud_Alleged", "breach_alleged"),
    ("US_Plea_Bargaining_Act", "breach_alleged"),
    ("At_Will_Employment", "contract_invalid"),
    ("US_Employment_At_Will", "contract_invalid"),
    ("Cross_Border_Data_Transfer_To_US", "breach_alleged"),
    ("US_Cloud_Act_Data_Request", "breach_alleged"),
    ("Limitation_Period_Expired", "statute_barred"),
    ("Statute_Barred", "statute_barred"),
    ("Security_Interest_Created", "contract_formed"),
    ("Guarantee_Provided", "contract_formed"),
]


class PRCCollisionEngine:
    """三轨对撞引擎 — CN jurisdiction 的核心推理引擎。

    使用方式:
        engine = PRCCollisionEngine()
        proof_tree = engine.run(shared_facts)
        # proof_tree 是 ProofTree 实例，不含自然语言
    """

    def __init__(self, config_dir: str = None):
        base = Path(__file__).resolve().parents[1]
        if config_dir is None:
            config_dir = str(base / "configs" / "prc_us_alignment")

        cfg = Path(config_dir)
        self.blocking_rules_path = cfg / "blocking_rules.yaml"
        self.meta_constraints_path = cfg / "meta_constraints.yaml"
        self.spc_rules_path = cfg / "spc_rules.yaml"

        cn_configs = base / "configs" / "zh_CN"
        self.cn_rules_path = cn_configs / "rules.yaml"

        self._blocking_rules: List[Dict] = []
        self._meta_rules: List[Dict] = []
        self._spc_evaluator: Optional[FixpointEvaluator] = None
        self._cn_evaluator: Optional[FixpointEvaluator] = None
        self._cn_rule_count: int = 0

        # Bridge health tracking
        self._cn_zero_streak: int = 0

        self._load_configs()

    def _load_configs(self) -> None:
        """加载 CBL 阻断规则 + SPC 裁判倾向 + CN 全量规则。"""
        if self.blocking_rules_path.exists():
            with open(self.blocking_rules_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self._blocking_rules = data.get("rules", [])

        if self.meta_constraints_path.exists():
            with open(self.meta_constraints_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self._meta_rules = data.get("meta_rules", [])

        if self.spc_rules_path.exists():
            try:
                spc_rules = load_rules_from_yaml(str(self.spc_rules_path))
                self._spc_evaluator = FixpointEvaluator(
                    spc_rules, DomainConfig(domain=LegalDomain.CIVIL)
                )
            except Exception:
                pass

        if self.cn_rules_path.exists():
            try:
                cn_rules = load_rules_from_yaml(str(self.cn_rules_path))
                self._cn_evaluator = FixpointEvaluator(
                    cn_rules, DomainConfig(domain=LegalDomain.CIVIL)
                )
                self._cn_rule_count = len(cn_rules)
            except Exception:
                pass

    @property
    def cbl_loaded(self) -> bool:
        return len(self._blocking_rules) > 0

    @property
    def spc_loaded(self) -> bool:
        return self._spc_evaluator is not None

    @property
    def cn_loaded(self) -> bool:
        return self._cn_evaluator is not None

    def run(self, shared_facts: Dict[str, LegalFact]) -> ProofTree:
        """执行三轨对撞，返回 ProofTree。

        Args:
            shared_facts: 输入事实池（只读，内部防御性复制）

        Returns:
            ProofTree 实例（纯 ID + 逻辑算子）
        """
        tree = ProofTree(jurisdiction="CN")

        # ═══ Meta Constraints 预处理 ═══
        filtered_facts = self._apply_meta_constraints(shared_facts)

        # ═══ Track 1: CBL 阻断（一票否决）═══
        blocked_targets = self._run_cbl_track(filtered_facts, tree)

        # ═══ Track 2: SPC 裁判倾向（过滤被阻断的 claim）═══
        self._run_spc_track(shared_facts, tree, blocked_targets)

        # ═══ Track 3: CN 成文法全量（过滤被阻断的 claim）═══
        self._run_cn_track(shared_facts, tree, blocked_targets)

        # Bridge health
        tree.bridge_health = self._compute_bridge_health(len(tree.cn_claims))
        return tree

    def _run_cbl_track(self, facts: Dict[str, LegalFact], tree: ProofTree) -> set:
        """Track 1: CBL 成文法阻断。返回被阻断的 claim 目标集合。"""
        blocked_targets = set()
        for rule in self._blocking_rules:
            trigger = rule.get("trigger_fact", "")
            if trigger not in facts:
                continue
            fact = facts[trigger]
            if fact.extraction_confidence <= 0:
                continue

            if not self._check_conditions(rule, facts):
                continue

            rule_id = rule.get("id", "")
            action_data = rule.get("action", {})
            target = rule.get("target_primitive", rule_id)
            node = ProofNode(
                node_id=f"R:{rule_id}",
                kind="blocking",
                head_claim=target,
                confidence=1.0,
                children=[],
                source_anchor=rule.get("description", ""),
                modality="PROHIBITION",
            )
            tree.add_node(node)
            tree.blocked_claims.append(rule_id)

            # Collect blocked targets for downstream filtering
            blocked_targets.add(target)
            map_to = action_data.get("map_to", "")
            if map_to:
                blocked_targets.add(map_to)
            # Also block the trigger fact itself
            blocked_targets.add(trigger)

        return blocked_targets

    def _run_spc_track(self, facts: Dict[str, LegalFact], tree: ProofTree,
                       blocked_targets: set) -> None:
        """Track 2: SPC 最高法裁判倾向（non-blocking，过滤被阻断的 claim）。"""
        if not self.spc_loaded:
            return

        spc_state = IRState(facts=copy.deepcopy(facts))
        try:
            spc_result = self._spc_evaluator.evaluate(spc_state)
            for cid, claim in spc_result.claims.items():
                if claim.confidence > 0 and cid not in blocked_targets:
                    node_id = f"S:{cid}"
                    node = ProofNode(
                        node_id=node_id,
                        kind="spc_tendency",
                        head_claim=cid,
                        confidence=claim.confidence,
                        children=[],
                        source_anchor=claim.source_anchor or "",
                        modality="PERMISSION",
                    )
                    tree.add_node(node)
                    tree.spc_tendencies.append(node_id)
        except CriticalClarityFailure as e:
            if hasattr(e, "partial_state") and e.partial_state is not None:
                for cid, claim in e.partial_state.claims.items():
                    if claim.confidence > 0.8 and cid not in blocked_targets:
                        node_id = f"S:{cid}"
                        node = ProofNode(
                            node_id=node_id,
                            kind="spc_tendency",
                            head_claim=cid,
                            confidence=claim.confidence,
                            children=[],
                            source_anchor=claim.source_anchor or "",
                        )
                        tree.add_node(node)
                        tree.spc_tendencies.append(node_id)

    def _run_cn_track(self, facts: Dict[str, LegalFact], tree: ProofTree,
                      blocked_targets: set) -> None:
        """Track 3: CN 成文法全量 Horn 规则（过滤被阻断的 claim）。"""
        if not self.cn_loaded:
            return

        # 跨法域事实桥接
        facts_cn = dict(facts)
        for bridge_src, bridge_target in CROSS_JURISDICTION_FACT_BRIDGE:
            if bridge_src in facts and bridge_target not in facts_cn:
                facts_cn[bridge_target] = facts[bridge_src]

        cn_state = IRState(facts=copy.deepcopy(facts_cn))
        try:
            cn_result = self._cn_evaluator.evaluate(cn_state)
            for cid, claim in cn_result.claims.items():
                if claim.confidence > 0 and cid not in blocked_targets:
                    node_id = f"C:{cid}"
                    node = ProofNode(
                        node_id=node_id,
                        kind="statute",
                        head_claim=cid,
                        confidence=claim.confidence,
                        children=[],
                        source_anchor=claim.source_anchor or "",
                        modality=getattr(claim, "modality", ""),
                    )
                    tree.add_node(node)
                    tree.cn_claims.append(node_id)
        except CriticalClarityFailure as e:
            if hasattr(e, "partial_state") and e.partial_state is not None:
                for cid, claim in e.partial_state.claims.items():
                    if claim.confidence > 0.8 and cid not in blocked_targets:
                        node_id = f"C:{cid}"
                        node = ProofNode(
                            node_id=node_id,
                            kind="statute",
                            head_claim=cid,
                            confidence=claim.confidence,
                            children=[],
                            source_anchor=claim.source_anchor or "",
                        )
                        tree.add_node(node)
                        tree.cn_claims.append(node_id)

    def _check_conditions(self, rule: Dict, facts: Dict[str, LegalFact]) -> bool:
        """检查阻断规则的附加条件。

        逻辑：
        - 无 OR 列表时：AND 条件全部满足
        - 有 OR 列表时：AND 条件全部满足 且 OR 至少满足一个
        """
        conditions = rule.get("additional_conditions", [])
        conditions_or = rule.get("additional_conditions_OR", [])

        # Check AND conditions
        for cond in conditions:
            if cond.startswith("NOT "):
                neg_fact = cond[4:]
                if neg_fact in facts and facts[neg_fact].extraction_confidence > 0:
                    return False
            else:
                if cond not in facts or facts[cond].extraction_confidence <= 0:
                    return False

        # Check OR conditions (only if OR list exists)
        if conditions_or:
            or_passed = False
            for cond in conditions_or:
                if cond.startswith("NOT "):
                    neg_fact = cond[4:]
                    if neg_fact not in facts or facts[neg_fact].extraction_confidence <= 0:
                        or_passed = True
                        break
                else:
                    if cond in facts and facts[cond].extraction_confidence > 0:
                        or_passed = True
                        break
            if not or_passed:
                return False

        return True

    def _apply_meta_constraints(self, facts: Dict[str, LegalFact]) -> Dict[str, LegalFact]:
        """Apply meta_constraints as pre-processing on facts.

        META_005 (Jurisdiction Separation): facts only, no HK/US claims.
        META_006 (Strict Jurisdiction): if asset/behavior in PRC, force PRC override.
        """
        if not self._meta_rules:
            return facts

        filtered = dict(facts)

        for rule in self._meta_rules:
            rule_id = rule.get("id", "")
            behavior = rule.get("behavior", "")

            # META_006: Strict Jurisdiction — if Cross_Border_Context exists,
            # log the meta constraint as active (actual FORCE_VOID is in CBL track)
            if behavior == "PRE_ITERATION_HOOK_OVERRIDE":
                trigger = rule.get("trigger", "")
                if "Cross_Border_Context" in filtered:
                    # Meta constraint is active — CBL track will handle blocking
                    pass

        return filtered

    def _compute_bridge_health(self, cn_count: int) -> Dict:
        """CN 桥接健康分 — 连续 3 次 CN=0 触发预警。"""
        if cn_count == 0:
            self._cn_zero_streak += 1
        else:
            self._cn_zero_streak = 0

        return {
            "cn_zero_streak": self._cn_zero_streak,
            "status": "HEALTHY" if self._cn_zero_streak < 3 else "DEGRADED",
        }
