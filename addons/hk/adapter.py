#!/usr/bin/env python3
"""HK addon — Hong Kong law adapter (trilingual bridge layer).

Hong Kong's role: NOT an independent reasoning engine, but the
"Rosetta Stone" bridge between US common law and CN civil law.

v2.1 additions:
  - Dynamic L0_MAP from configs/hk/term_L0_mappings.yaml (1,729 terms)
  - get_claim_tables(): CN/EN translation tables for LanguageRenderer
  - get_modal_mapping(): HK DDL modal words (shall/must/may)
  - trilingual_bridge(): US term → L0 → HK → L0 → CN
"""
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from compiler_core.adapter_base import JurisdictionAdapter
from compiler_core.types import LegalFact, IRState
from compiler_core.constraint_validator import ConstraintValidator


# Core L0 map (hand-maintained, 13 entries from Cap 26)
_HK_CORE_L0 = {
    "ContractOfSale_Exists": "Status",
    "Buyer_FailsToPay": "Act",
    "Delivery_Occurred": "Act",
    "Court_Ruled_ContractVoid": "Status",
    "Director_Acted_UltraVires": "Power",
    "SpecifiedPeriod_Expired": "Status",
    "Contract_Induced_By_Fraud": "Defect",
    "Goods_Perished_BeforeContract": "Defect",
    "Party_Lacks_Capacity": "Agent",
    "Goods_Defective": "Defect",
    "Consideration_Provided": "Status",
    "Seller_RightToSell": "Power",
    "Buyer_QuietPossession": "Status",
}


class HKAdapter(JurisdictionAdapter):
    """Hong Kong adapter — trilingual bridge between US and CN."""

    jurisdiction = "HK"
    rules_path = "configs/hk/rules.yaml"
    overrides_path = "configs/L0_overrides_hk.yaml"

    _MODAL_MAPPING: Dict[str, str] = {
        "shall": "OBLIGATION",
        "must": "OBLIGATION",
        "is required to": "OBLIGATION",
        "shall not": "PROHIBITION",
        "must not": "PROHIBITION",
        "may not": "PROHIBITION",
        "may": "PERMISSION",
        "is entitled to": "PERMISSION",
        "is permitted to": "PERMISSION",
        "means": "CONSTITUTIVE",
        "is defined as": "CONSTITUTIVE",
        "refers to": "CONSTITUTIVE",
        # Chinese equivalents in HK legislation
        "须": "OBLIGATION",
        "不得": "PROHIBITION",
        "可": "PERMISSION",
        "有权": "PERMISSION",
        "即为": "CONSTITUTIVE",
        "意指": "CONSTITUTIVE",
    }

    def __init__(self):
        self._l0_map: Optional[Dict[str, str]] = None
        self._claim_table_cn: Optional[Dict[str, str]] = None
        self._claim_table_en: Optional[Dict[str, str]] = None
        self._trilingual: Optional[List[Dict]] = None
        self._blocking_rules: Optional[List[Dict]] = None

    def _ensure_loaded(self) -> None:
        """Lazy-load L0 map, claim tables, and blocking rules from YAML."""
        if self._l0_map is not None:
            return

        base = Path(__file__).resolve().parents[2]
        term_path = base / "configs" / "hk" / "term_L0_mappings.yaml"
        tri_path = base / "configs" / "hk" / "trilingual_alignment.yaml"
        block_path = base / "configs" / "hk" / "blocking_rules.yaml"

        l0 = dict(_HK_CORE_L0)
        cn_table: Dict[str, str] = {}
        en_table: Dict[str, str] = {}

        if term_path.exists():
            with open(term_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for t in data.get("term_mappings", []):
                en = t.get("hk_term_en", "").strip()
                cn = t.get("hk_term_cn", "").strip()
                prim = t.get("l0_primitive", "?")
                if en:
                    key = en.lower().replace(" ", "_")
                    if key not in l0:
                        l0[key] = prim
                    if cn:
                        cn_table[en] = cn
                        en_table[en] = en

        self._l0_map = l0
        self._claim_table_cn = cn_table
        self._claim_table_en = en_table

        # Load trilingual alignment
        if tri_path.exists():
            with open(tri_path, "r", encoding="utf-8") as f:
                tri_data = yaml.safe_load(f) or {}
            self._trilingual = tri_data.get("alignments", [])
        else:
            self._trilingual = []

        # Load US→HK blocking rules
        if block_path.exists():
            with open(block_path, "r", encoding="utf-8") as f:
                block_data = yaml.safe_load(f) or {}
            self._blocking_rules = block_data.get("rules", [])
        else:
            self._blocking_rules = []

    def check_blocking(self, fact_id: str) -> Optional[Dict]:
        """Check if a fact is blocked by US→HK blocking rules.

        Returns blocking rule dict if blocked, None otherwise.
        """
        self._ensure_loaded()
        for rule in self._blocking_rules or []:
            if rule.get("trigger_fact") == fact_id:
                action = rule.get("action", {})
                if action.get("type") in ("FORCE_VOID", "FORCE_SUPPRESS"):
                    return {
                        "rule_id": rule.get("id"),
                        "action_type": action.get("type"),
                        "map_to": action.get("map_to", ""),
                        "description": rule.get("description", ""),
                    }
        return None

    def map_to_L0(self, domain_concept: str) -> str:
        self._ensure_loaded()
        return self._l0_map.get(domain_concept, "?")

    def get_claim_tables(self) -> Tuple[Dict[str, str], Dict[str, str]]:
        self._ensure_loaded()
        return self._claim_table_cn, self._claim_table_en

    def get_modal_mapping(self) -> Dict[str, str]:
        return dict(self._MODAL_MAPPING)

    def get_legal_family(self) -> str:
        return "common_law"

    def trilingual_bridge(self, us_term: str) -> Dict:
        """US term → L0 → HK → L0 → CN bridge lookup.

        Returns:
            {
                'us_term': str,
                'us_l0': str,
                'hk_term': str,
                'hk_l0': str,
                'cn_term': str,
                'alignment': str,  # ALIGNED / CROSS_L0 / BLOCKED / NOT_FOUND
            }
        """
        self._ensure_loaded()

        # Check blocking rules first — if blocked, short-circuit
        block_result = self.check_blocking(us_term)
        if block_result:
            return {
                'us_term': us_term,
                'us_l0': '?',
                'hk_term': block_result.get('map_to', ''),
                'hk_l0': '?',
                'cn_term': '',
                'alignment': 'BLOCKED',
                'block_rule': block_result['rule_id'],
                'block_reason': block_result['description'],
            }

        # Normalize US term
        us_norm = us_term.strip().replace("_", " ").lower()

        # Search trilingual table
        for entry in self._trilingual or []:
            if entry.get("us_term", "").lower().strip() == us_norm or \
               entry.get("us_term", "").lower().replace("_", " ").strip() == us_norm:
                return {
                    'us_term': entry.get('us_term', us_term),
                    'us_l0': entry.get('l0', '?'),
                    'hk_term': entry.get('hk_en', ''),
                    'hk_l0': entry.get('l0', '?'),
                    'cn_term': entry.get('us_cn', ''),
                    'alignment': entry.get('alignment', 'UNKNOWN'),
                }

        # Fallback: look up L0 for both US and HK
        us_l0 = "?"
        # Try to find in CN adapter's US L0 map
        try:
            from compiler_core.plugin_registry import registry
            cn = registry.get("cn")
            if cn:
                us_l0 = cn.map_to_L0(us_term)
        except Exception:
            pass

        hk_l0 = self.map_to_L0(us_term.lower().replace(" ", "_"))

        if us_l0 == "?" and hk_l0 == "?":
            alignment = "NOT_FOUND"
        elif us_l0 == hk_l0 and us_l0 != "?":
            alignment = "ALIGNED"
        else:
            alignment = "CROSS_L0"

        return {
            'us_term': us_term,
            'us_l0': us_l0,
            'hk_term': '',
            'hk_l0': hk_l0,
            'cn_term': '',
            'alignment': alignment,
        }

    def validate_against_guardrails(self, state: IRState) -> Dict:
        issues = []
        blocked = []
        for fid, fact in state.facts.items():
            l0 = self.map_to_L0(fid)
            if l0 == "?":
                issues.append(f"{fid}: no L0 mapping")
            # Check US→HK blocking rules
            block_result = self.check_blocking(fid)
            if block_result:
                blocked.append(block_result)
        return {
            "valid": len(issues) == 0 and len(blocked) == 0,
            "issues": issues,
            "blocked": blocked,
        }
