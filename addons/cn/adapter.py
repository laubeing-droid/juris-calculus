#!/usr/bin/env python3
"""CN adapter — Chinese jurisdiction with three-track collision engine.

Extends JurisdictionAdapter with:
  - map_to_L0: CN law concepts → L0 primitives (loaded from 207 term alignments)
  - validate_against_guardrails: CN-specific guardrail checks
  - run_collision: three-track collision (CBL + SPC + CN)
  - get_legal_family: "civil_law"
  - get_modal_mapping: 应当/不得/可以 → OBLIGATION/PROHIBITION/PERMISSION
  - get_claim_tables: (cn_table, en_table) for LanguageRenderer
"""
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from compiler_core.adapter_base import JurisdictionAdapter
from compiler_core.types import LegalFact, IRState, LegalDomain
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator, load_rules_from_yaml
from compiler_core.legal_compiler import LegalCompiler
from compiler_core.constraint_validator import ConstraintValidator
from compiler_core.proof_tree import ProofTree
from compiler_core.prc_collision_engine import PRCCollisionEngine


# ═══════════════════════════════════════════
# CN 核心概念 L0 映射（手动维护，7条）
# ═══════════════════════════════════════════
_CN_CORE_L0 = {
    "contract_formed": "Status",
    "breach_alleged": "Act",
    "contract_invalid": "Status",
    "damages_claimed": "Act",
    "damages_suffered": "Status",
    "goods_delivered": "Act",
    "statute_barred": "Status",
}


class CNAdapter(JurisdictionAdapter):
    """中国法适配器 — 含三轨对撞模式。"""

    jurisdiction = "CN"
    rules_path = "configs/zh_CN/rules.yaml"
    overrides_path = "configs/L0_overrides_cn.yaml"

    _MODAL_MAPPING: Dict[str, str] = {
        "应当": "OBLIGATION",
        "必须": "OBLIGATION",
        "不得": "PROHIBITION",
        "禁止": "PROHIBITION",
        "不可以": "PROHIBITION",
        "可以": "PERMISSION",
        "有权": "PERMISSION",
        "允许": "PERMISSION",
        "属于": "CONSTITUTIVE",
        "视为": "CONSTITUTIVE",
        "是指": "CONSTITUTIVE",
    }

    def __init__(self):
        self._collision_engine: Optional[PRCCollisionEngine] = None
        self._constraint_validator: Optional[ConstraintValidator] = None
        self._l0_map: Optional[Dict[str, str]] = None
        self._claim_table_cn: Optional[Dict[str, str]] = None
        self._claim_table_en: Optional[Dict[str, str]] = None

    def _ensure_term_tables(self) -> None:
        """从 term_L0_mappings.yaml 懒加载 L0 映射 + 翻译表。"""
        if self._l0_map is not None:
            return

        base = Path(__file__).resolve().parents[2]
        files = [
            base / "configs" / "prc_us_alignment" / "term_L0_mappings.yaml",
            base / "configs" / "prc_us_alignment" / "term_L0_mappings_batch2.yaml",
        ]

        l0 = dict(_CN_CORE_L0)
        cn_table: Dict[str, str] = {}
        en_table: Dict[str, str] = {}

        for fp in files:
            if not fp.exists():
                continue
            with open(fp, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for t in data.get("term_alignments", []):
                us = t.get("term_us", "")
                cn = t.get("term_cn", "")
                chain = t.get("l0_chain", {})
                prim = chain.get("primitive", "?")
                if us and us not in l0:
                    l0[us] = prim
                if us and cn:
                    cn_table[us] = cn
                    en_table[us] = us.replace("_", " ")

        self._l0_map = l0
        self._claim_table_cn = cn_table
        self._claim_table_en = en_table

    def map_to_L0(self, domain_concept: str) -> str:
        self._ensure_term_tables()
        return self._l0_map.get(domain_concept, "?")

    def get_claim_tables(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        """返回 (中文翻译表, 英文翻译表)，用于 LanguageRenderer。"""
        self._ensure_term_tables()
        return self._claim_table_cn, self._claim_table_en

    def validate_against_guardrails(self, state: IRState) -> Dict:
        issues = []
        for fid, fact in state.facts.items():
            l0 = self.map_to_L0(fid)
            if l0 == "?":
                issues.append(f"{fid}: no L0 mapping")

        if self._constraint_validator is None:
            try:
                self._constraint_validator = ConstraintValidator(
                    overrides_path=self.overrides_path
                )
            except Exception:
                pass

        triggered = []
        if self._constraint_validator and hasattr(self._constraint_validator, "_constraint_rules"):
            for cr in self._constraint_validator._constraint_rules:
                trigger = cr.get("trigger_fact", "")
                if trigger in state.facts and state.facts[trigger].extraction_confidence > 0:
                    conds = cr.get("additional_conditions", [])
                    all_met = True
                    for c in conds:
                        if c.startswith("NOT "):
                            neg = c[4:]
                            if neg in state.facts and state.facts[neg].extraction_confidence > 0:
                                all_met = False
                        elif c not in state.facts or state.facts[c].extraction_confidence <= 0:
                            all_met = False
                    if all_met:
                        triggered.append({"id": cr.get("id", ""), "action": cr.get("action", "")})

        return {"valid": len(issues) == 0, "issues": issues, "constraints_triggered": triggered}

    def get_legal_family(self) -> str:
        return "civil_law"

    def get_modal_mapping(self) -> Dict[str, str]:
        return dict(self._MODAL_MAPPING)

    def run_collision(self, facts: Dict[str, LegalFact]) -> ProofTree:
        """执行三轨对撞，返回 ProofTree。"""
        if self._collision_engine is None:
            self._collision_engine = PRCCollisionEngine()
        return self._collision_engine.run(facts)

    def load_evaluator(self, route_request: Optional[List[str]] = None) -> FixpointEvaluator:
        """加载 CN 全量规则并创建 FixpointEvaluator。"""
        compiler = LegalCompiler(self.rules_path, overrides_path=self.overrides_path)
        rules = compiler.compile_rules(route_request)
        self._ensure_term_tables()
        return FixpointEvaluator(
            rules,
            DomainConfig(domain=LegalDomain.CIVIL),
            overrides_path=self.overrides_path,
            l0_map=self._l0_map,
        )
