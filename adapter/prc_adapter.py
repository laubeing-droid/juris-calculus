#!/usr/bin/env python3
"""
adapter/prc_adapter.py — PRCAdapter 纯约束层引擎
══════════════════════════════════════════════════════════════
设计原则:
  1. 不产生 Horn 规则 —— 这是一个纯约束层引擎
  2. 不污染共享事实池 —— 输入只读，防御性复制隔离
  3. 输出 State_PRC —— 中国成文法视角的强制性效力覆写

行为:
  加载 blocking_rules.yaml → 遍历 constraint_rules
  → 检查 trigger_fact 是否在共享事实中 (置信度 > 0)
  → 输出覆写指令: {FORCE_VOID | FORCE_SUPPRESS | MAPPING_OVERRIDE}
══════════════════════════════════════════════════════════════
"""

import yaml
import copy
from pathlib import Path
from typing import Dict, Any, List

from compiler_core.types import LegalFact


class PRCAdapter:
    """
    PRC-First 强制性效力覆写器。

    不参与 Horn 规则链推理。仅基于共享事实池执行确定性的
    中国大陆成文法强制拦截——FORCE_VOID / FORCE_SUPPRESS / MAPPING_OVERRIDE。
    """

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = str(Path(__file__).resolve().parents[1] / "configs" / "prc_us_alignment")
        
        self.blocking_rules_path = Path(config_dir) / "blocking_rules.yaml"
        self.meta_constraints_path = Path(config_dir) / "meta_constraints.yaml"
        self.constraint_rules: List[Dict] = []
        self.meta_rules: List[Dict] = []
        self._loaded = False
        self._load_configs()

    def _load_configs(self):
        """加载 blocking_rules.yaml 和 meta_constraints.yaml"""
        if self.blocking_rules_path.exists():
            with open(self.blocking_rules_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.constraint_rules = data.get("rules", [])
            self._loaded = True

        if self.meta_constraints_path.exists():
            with open(self.meta_constraints_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.meta_rules = data.get("meta_rules", [])

    @property
    def loaded(self) -> bool:
        return self._loaded and len(self.constraint_rules) > 0

    def execute_prc_first_override(
        self, shared_facts: Dict[str, LegalFact]
    ) -> Dict[str, Dict[str, Any]]:
        """
        核心行为: 对中国大陆成文法进行强制性效力覆写。

        Args:
            shared_facts: Dict[fact_id, LegalFact] — 只读，绝不修改

        Returns:
            State_PRC: Dict[rule_id, {
                "target_primitive": str,
                "type": "FORCE_VOID" | "FORCE_SUPPRESS" | "MAPPING_OVERRIDE",
                "map_to": str,
                "status": str,
            }]

        设计保证:
          - 使用防御性浅拷贝（仅读取，不修改）
          - 所有输出在独立 dict 中，零污染
        """
        state_prc: Dict[str, Dict[str, Any]] = {}

        for rule in self.constraint_rules:
            trigger = rule.get("trigger_fact", "")

            # 检查触发事实是否存在 + 置信度筛滤
            if trigger not in shared_facts:
                continue

            fact = shared_facts[trigger]
            if fact.extraction_confidence <= 0:
                continue

            # ═══ additional_conditions 交叉校验 ═══
            conditions = rule.get("additional_conditions", [])
            condition_passed = True
            for cond in conditions:
                # 支持 NOT 前缀: "NOT FactID" → 该事实存在且置信度>0时条件失败
                if cond.startswith("NOT "):
                    neg_fact = cond[4:]
                    if neg_fact in shared_facts and shared_facts[neg_fact].extraction_confidence > 0:
                        condition_passed = False
                        break
                else:
                    # 该事实必须存在且置信度>0
                    if cond not in shared_facts or shared_facts[cond].extraction_confidence <= 0:
                        condition_passed = False
                        break

            if not condition_passed:
                continue  # 环境上下文不匹配，跳过此条阻断

            # 提取规则
            rule_id = rule.get("id", "")
            target_primitive = rule.get("target_primitive", "")
            action_data = rule.get("action", {})

            state_prc[rule_id] = {
                "target_primitive": target_primitive,
                "type": action_data.get("type", ""),
                "map_to": action_data.get("map_to", ""),
                "status": action_data.get("status", ""),
                "description": rule.get("description", ""),
            }

        return state_prc

    def get_force_void_triggers(self, state_prc: Dict) -> List[str]:
        """提取所有被 FORCE_VOID 的规则ID"""
        return [
            rid for rid, v in state_prc.items()
            if v.get("type") == "FORCE_VOID"
        ]

    def get_force_suppress_triggers(self, state_prc: Dict) -> List[str]:
        """提取所有被 FORCE_SUPPRESS 的规则ID"""
        return [
            rid for rid, v in state_prc.items()
            if v.get("type") == "FORCE_SUPPRESS"
        ]

    def get_mapping_overrides(self, state_prc: Dict) -> List[Dict]:
        """提取所有 MAPPING_OVERRIDE 规则"""
        return [
            {"id": rid, **v}
            for rid, v in state_prc.items()
            if v.get("type") == "MAPPING_OVERRIDE"
        ]
