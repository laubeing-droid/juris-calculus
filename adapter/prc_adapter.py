#!/usr/bin/env python3
"""
adapter/prc_adapter.py — PRCAdapter 三轨约束引擎 v1.2.0
══════════════════════════════════════════════════════════════
三轨架构:
  第一轨(CBL): 成文法阻断 — blocking_rules.yaml (41条)
               FORCE_VOID / FORCE_SUPPRESS / MAPPING_OVERRIDE
  第二轨(SPC): 最高法裁判倾向 — spc_rules.yaml (23条)
               Horn 规则推导 (non-blocking, 仅倾向)
  第三轨(CN ): 中国成文法全量 — configs/zh_CN/rules.yaml (2,117条)
               13领域 Horn 规则引擎 (合同/侵权/公司/家事/刑事/行政/
               知产/程序/执行/国赔/少年/海事/审管)
  
设计原则:
  1. CBL 是一票否决——成文法阻断具有最高效力
  2. SPC 是裁判指引——不推翻 CBL，仅补充推理
  3. CN  是全量引擎——覆盖民法典/刑法/民诉/刑诉等18部法律
  4. 不污染共享事实池 —— 输入只读，防御性复制隔离
  5. 输出三层 State_PRC = {blocking + spc_claims + cn_claims}
══════════════════════════════════════════════════════════════
"""

import yaml
import copy
from pathlib import Path
from typing import Dict, Any, List

from compiler_core.types import LegalFact, IRState
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml, CriticalClarityFailure
from compiler_core.domain_config import DomainConfig, LegalDomain


# ═══════════════════════════════════════════
# 跨法域事实桥接表
# HK/US 事实名 → CN 规则前提原子 (v1.0.3 premise_atoms)
# ═══════════════════════════════════════════
CROSS_JURISDICTION_FACT_BRIDGE = [
    # 合同/违约
    ("ContractOfSale_Exists", "contract_formed"),
    ("Contract_Validity", "contract_formed"),
    ("Breach_Established", "breach_alleged"),
    ("Buyer_FailsToPay", "breach_alleged"),
    ("Goods_Defective", "goods_delivered"),
    ("Consideration_Provided", "contract_formed"),
    # 侵权/损害赔偿
    ("Damages_Awarded", "damages_claimed"),
    ("Loss_Occurred", "damages_suffered"),
    ("Personal_Injury_Claim", "damages_suffered"),
    # 公司/董事
    ("Director_Acted_UltraVires", "breach_alleged"),
    ("Fiduciary_Duty_Breach", "breach_alleged"),
    ("Affiliated_Companies_Asset_Confusion", "contract_invalid"),
    # 破产
    ("Bankruptcy_Petition_Filed", "contract_invalid"),
    ("Chapter11_Filed", "contract_invalid"),
    # 刑事/程序
    ("Wrongful_Omission", "breach_alleged"),
    ("Fraud_Alleged", "breach_alleged"),
    ("US_Plea_Bargaining_Act", "breach_alleged"),
    # 劳动
    ("At_Will_Employment", "contract_invalid"),
    ("US_Employment_At_Will", "contract_invalid"),
    # 数据/合规
    ("Cross_Border_Data_Transfer_To_US", "breach_alleged"),
    ("US_Cloud_Act_Data_Request", "breach_alleged"),
    # 时效
    ("Limitation_Period_Expired", "statute_barred"),
    ("Statute_Barred", "statute_barred"),
    # 担保
    ("Security_Interest_Created", "contract_formed"),
    ("Guarantee_Provided", "contract_formed"),
]


class PRCAdapter:
    """
    PRC-First 三轨约束引擎。

    第一轨 (CBL): 成文法强制阻断 — 41条 FORCE_VOID/SUPPRESS/MAPPING
    第二轨 (SPC): 最高法裁判倾向 — 23条 Horn 规则
    第三轨 (CN ): 中国成文法全量 — 2,117条 Horn 规则 (13领域)
    """

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = str(Path(__file__).resolve().parents[1] / "configs" / "prc_us_alignment")
        
        cfg = Path(config_dir)
        self.blocking_rules_path = cfg / "blocking_rules.yaml"
        self.meta_constraints_path = cfg / "meta_constraints.yaml"
        self.spc_rules_path = cfg / "spc_rules.yaml"
        
        # 第三轨: 中国成文法全量规则
        cn_configs = Path(__file__).resolve().parents[1] / "configs" / "zh_CN"
        self.cn_rules_path = cn_configs / "rules.yaml"
        self.cn_concept_registry_path = cn_configs / "concept_registry.yaml"
        self.cn_concept_ocr_path = cn_configs / "concept_registry_ocr.yaml"
        
        self.constraint_rules: List[Dict] = []
        self.meta_rules: List[Dict] = []
        self._loaded = False
        self._spc_loaded = False
        self._cn_loaded = False
        self.spc_evaluator = None
        self.cn_evaluator = None
        self.cn_rule_count = 0
        self.cn_concept_registry = {}
        self.cn_concept_ocr = {}
        
        self._load_configs()

    def _load_configs(self):
        """加载 blocking + meta + SPC 三套规则"""
        if self.blocking_rules_path.exists():
            with open(self.blocking_rules_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.constraint_rules = data.get("rules", [])
            self._loaded = True

        if self.meta_constraints_path.exists():
            with open(self.meta_constraints_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.meta_rules = data.get("meta_rules", [])

        # ── 第二轨: 加载 SPC 裁判规则 ──
        if self.spc_rules_path.exists():
            try:
                spc_rules = load_rules_from_yaml(str(self.spc_rules_path))
                self.spc_evaluator = FixpointEvaluator(
                    spc_rules,
                    DomainConfig(domain=LegalDomain.CIVIL)
                )
                self._spc_loaded = True
            except Exception:
                self._spc_loaded = False

        # ── 第三轨: 加载中国成文法全量 Horn 规则 ──
        if self.cn_rules_path.exists():
            try:
                cn_rules = load_rules_from_yaml(str(self.cn_rules_path))
                self.cn_evaluator = FixpointEvaluator(
                    cn_rules,
                    DomainConfig(domain=LegalDomain.CIVIL)
                )
                self.cn_rule_count = len(cn_rules)
                self._cn_loaded = True
            except Exception:
                self._cn_loaded = False

        # ── 概念注册表 (OCR提取的776个法律概念) ──
        if self.cn_concept_registry_path.exists():
            try:
                with open(self.cn_concept_registry_path, "r", encoding="utf-8") as f:
                    self.cn_concept_registry = yaml.safe_load(f) or {}
            except Exception:
                pass

        if self.cn_concept_ocr_path.exists():
            try:
                with open(self.cn_concept_ocr_path, "r", encoding="utf-8") as f:
                    self.cn_concept_ocr = yaml.safe_load(f) or {}
            except Exception:
                pass

    @property
    def loaded(self) -> bool:
        return self._loaded and len(self.constraint_rules) > 0

    @property
    def spc_loaded(self) -> bool:
        return self._spc_loaded and self.spc_evaluator is not None

    @property
    def cn_loaded(self) -> bool:
        return self._cn_loaded and self.cn_evaluator is not None

    def execute_prc_first_override(
        self, shared_facts: Dict[str, LegalFact]
    ) -> Dict[str, Any]:
        """
        三轨并发: CBL 阻断 + SPC 裁判倾向 + CN 全量规则

        Returns:
            {
                "blocking_overrides": Dict[rule_id, {...}],
                "spc_judicial_tendencies": List[str],
                "spc_claims_count": int,
                "cn_claims": List[str],
                "cn_claims_count": int,
                "cn_rules_total": int,
            }
        """
        # ═══ 第一轨: 成文法阻断 ═══
        blocking_state = {}
        for rule in self.constraint_rules:
            trigger = rule.get("trigger_fact", "")
            if trigger not in shared_facts:
                continue
            fact = shared_facts[trigger]
            if fact.extraction_confidence <= 0:
                continue

            conditions = rule.get("additional_conditions", [])
            condition_passed = True
            for cond in conditions:
                if cond.startswith("NOT "):
                    neg_fact = cond[4:]
                    if neg_fact in shared_facts and shared_facts[neg_fact].extraction_confidence > 0:
                        condition_passed = False
                        break
                else:
                    if cond not in shared_facts or shared_facts[cond].extraction_confidence <= 0:
                        condition_passed = False
                        break
            if not condition_passed:
                continue

            rule_id = rule.get("id", "")
            action_data = rule.get("action", {})
            blocking_state[rule_id] = {
                "target_primitive": rule.get("target_primitive", ""),
                "type": action_data.get("type", ""),
                "map_to": action_data.get("map_to", ""),
                "status": action_data.get("status", ""),
                "description": rule.get("description", ""),
            }

        # ═══ 第二轨: SPC 裁判倾向 ═══
        spc_claims = []
        spc_claims_count = 0
        if self.spc_loaded:
            spc_state = IRState(facts=copy.deepcopy(shared_facts))
            try:
                spc_result = self.spc_evaluator.evaluate(spc_state)
                spc_claims = [
                    cid for cid, c in spc_result.claims.items()
                    if c.confidence > 0
                ]
                spc_claims_count = len(spc_claims)
            except CriticalClarityFailure as e:
                if hasattr(e, 'partial_state') and e.partial_state is not None:
                    # GEMINI审计修正: 原子性降级——仅保留 confidence>0.8 的确定性根节点
                    # 剔除推导链末端的临时悬空断言，防止未反驳的错误主张外泄
                    spc_claims = [
                        cid for cid, c in e.partial_state.claims.items()
                        if c.confidence > 0.8
                    ]
                    spc_claims_count = len(spc_claims)

        # ═══ 第三轨: CN 成文法全量 Horn 规则 ═══
        facts_cn = dict(shared_facts)  # shallow copy
        # 跨法域语义桥接: 将 HK/US 事实名映射到 CN 规则前提
        for bridge_src, bridge_target in CROSS_JURISDICTION_FACT_BRIDGE:
            if bridge_src in shared_facts and bridge_target not in facts_cn:
                facts_cn[bridge_target] = shared_facts[bridge_src]

        cn_claims = []
        cn_claims_count = 0
        if self.cn_loaded:
            cn_state = IRState(facts=copy.deepcopy(facts_cn))
            try:
                cn_result = self.cn_evaluator.evaluate(cn_state)
                cn_claims = [
                    cid for cid, c in cn_result.claims.items()
                    if c.confidence > 0
                ]
                cn_claims_count = len(cn_claims)
            except CriticalClarityFailure as e:
                if hasattr(e, 'partial_state') and e.partial_state is not None:
                    # GEMINI审计修正: 仅保留 confidence>0.8 的确定性根节点
                    cn_claims = [
                        cid for cid, c in e.partial_state.claims.items()
                        if c.confidence > 0.8
                    ]
                    cn_claims_count = len(cn_claims)

        return {
            "blocking_overrides": blocking_state,
            "spc_judicial_tendencies": spc_claims,
            "spc_claims_count": spc_claims_count,
            "cn_claims": cn_claims,
            "cn_claims_count": cn_claims_count,
            "cn_rules_total": self.cn_rule_count,
        }

    def get_force_void_triggers(self, state_prc: Dict) -> List[str]:
        blocking = state_prc.get("blocking_overrides", {})
        return [rid for rid, v in blocking.items() if v.get("type") == "FORCE_VOID"]

    def get_force_suppress_triggers(self, state_prc: Dict) -> List[str]:
        blocking = state_prc.get("blocking_overrides", {})
        return [rid for rid, v in blocking.items() if v.get("type") == "FORCE_SUPPRESS"]

    def get_mapping_overrides(self, state_prc: Dict) -> List[Dict]:
        blocking = state_prc.get("blocking_overrides", {})
        return [
            {"id": rid, **v}
            for rid, v in blocking.items()
            if v.get("type") == "MAPPING_OVERRIDE"
        ]

    def get_spc_claims(self, state_prc: Dict) -> List[str]:
        """提取 SPC 裁判倾向主张"""
        return state_prc.get("spc_judicial_tendencies", [])

    def get_cn_claims(self, state_prc: Dict) -> List[str]:
        """提取 CN 成文法全量主张"""
        return state_prc.get("cn_claims", [])

    def get_cn_stats(self, state_prc: Dict) -> Dict:
        """提取 CN 引擎统计信息"""
        return {
            "claims_count": state_prc.get("cn_claims_count", 0),
            "rules_total": state_prc.get("cn_rules_total", 0),
        }
