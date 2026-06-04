#!/usr/bin/env python3
"""
adapter/prc_adapter.py — PRCAdapter 双轨约束引擎 v1.2.0
══════════════════════════════════════════════════════════════
双轨架构:
  第一轨(CBL): 成文法阻断 — blocking_rules.yaml
               FORCE_VOID / FORCE_SUPPRESS / MAPPING_OVERRIDE
  第二轨(SPC): 最高法裁判倾向 — spc_rules.yaml  
               Horn 规则推导 (non-blocking, 仅倾向)
  
设计原则:
  1. CBL 是一票否决——成文法阻断具有最高效力
  2. SPC 是裁判指引——不推翻 CBL，仅补充推理
  3. 不污染共享事实池 —— 输入只读，防御性复制隔离
  4. 输出双层 State_PRC = {blocking + spc_claims}
══════════════════════════════════════════════════════════════
"""

import yaml
import copy
from pathlib import Path
from typing import Dict, Any, List

from compiler_core.types import LegalFact, IRState
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml, CriticalClarityFailure
from compiler_core.domain_config import DomainConfig, LegalDomain


class PRCAdapter:
    """
    PRC-First 双轨约束引擎。

    第一轨 (CBL): 成文法强制阻断
    第二轨 (SPC): 最高法裁判倾向 (Horn 规则推导)
    """

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = str(Path(__file__).resolve().parents[1] / "configs" / "prc_us_alignment")
        
        cfg = Path(config_dir)
        self.blocking_rules_path = cfg / "blocking_rules.yaml"
        self.meta_constraints_path = cfg / "meta_constraints.yaml"
        self.spc_rules_path = cfg / "spc_rules.yaml"
        
        self.constraint_rules: List[Dict] = []
        self.meta_rules: List[Dict] = []
        self._loaded = False
        self._spc_loaded = False
        self.spc_evaluator = None
        
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

    @property
    def loaded(self) -> bool:
        return self._loaded and len(self.constraint_rules) > 0

    @property
    def spc_loaded(self) -> bool:
        return self._spc_loaded and self.spc_evaluator is not None

    def execute_prc_first_override(
        self, shared_facts: Dict[str, LegalFact]
    ) -> Dict[str, Any]:
        """
        双轨并发: CBL 阻断 + SPC 裁判倾向

        Returns:
            {
                "blocking_overrides": Dict[rule_id, {...}],
                "spc_judicial_tendencies": List[str],  # SPC claims
                "spc_claims_count": int,
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
                    spc_claims = [
                        cid for cid, c in e.partial_state.claims.items()
                        if c.confidence > 0
                    ]
                    spc_claims_count = len(spc_claims)

        return {
            "blocking_overrides": blocking_state,
            "spc_judicial_tendencies": spc_claims,
            "spc_claims_count": spc_claims_count,
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
