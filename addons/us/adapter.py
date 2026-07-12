#!/usr/bin/env python3
"""Minimal US adapter kept only for plugin-registry compatibility.

This file preserves the historical ``us`` slot in ``PluginRegistry``.
It is a legacy compatibility shell, not a reasoning-ready US addon.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import yaml

from compiler_core.adapter_base import JurisdictionAdapter
from compiler_core.types import IRState


_US_CORE_L0 = {
    "Claim_Arises_Under_Federal_Law": "Status",
    "Parties_Are_Diverse_Citizenship": "Status",
    "Amount_In_Controversy_Exceeds_75000": "Status",
    "Bankruptcy_Case_Pending": "Status",
    "Plan_Confirmed": "Status",
    "Work_Is_Original": "Status",
    "Unauthorized_Use": "Act",
    "Patent_In_Force": "Status",
    "Unauthorized_Make_Use_Or_Sell": "Act",
    "Person_Is_SDN_Listed": "Status",
}


class USAdapter(JurisdictionAdapter):
    """Legacy compatibility shell for the ``us`` registry slot."""

    jurisdiction = "US"
    rules_path = "configs/us/rules.yaml"
    overrides_path = "configs/L0_overrides_us.yaml"

    _MODAL_MAPPING: Dict[str, str] = {
        "shall": "OBLIGATION",
        "must": "OBLIGATION",
        "shall not": "PROHIBITION",
        "must not": "PROHIBITION",
        "may": "PERMISSION",
        "means": "CONSTITUTIVE",
        "includes": "CONSTITUTIVE",
    }

    def __init__(self) -> None:
        self._l0_map: Optional[Dict[str, str]] = None

    def _ensure_loaded(self) -> None:
        if self._l0_map is not None:
            return
        base = Path(__file__).resolve().parents[2]
        l0 = dict(_US_CORE_L0)
        sources = (
            base / "configs" / "us" / "term_L0_mappings.yaml",
            base / "configs" / "prc_us_alignment" / "term_L0_mappings.yaml",
            base / "configs" / "prc_us_alignment" / "term_L0_mappings_batch2.yaml",
        )
        for path in sources:
            if not path.exists():
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for item in data.get("term_mappings", ()):
                term = str(item.get("term", "")).strip()
                primitive = str(item.get("l0_primitive", "?"))
                if term and term not in l0:
                    l0[term] = primitive
            for item in data.get("term_alignments", ()):
                term = str(item.get("term_us", "")).strip()
                primitive = str(item.get("l0_chain", {}).get("primitive", "?"))
                if term and term not in l0:
                    l0[term] = primitive
        self._l0_map = l0

    def map_to_L0(self, domain_concept: str) -> str:
        self._ensure_loaded()
        return self._l0_map.get(domain_concept, "?")

    def validate_against_guardrails(self, state: IRState) -> Dict:
        issues = []
        for fact_id in state.facts:
            if self.map_to_L0(fact_id) == "?":
                issues.append(f"{fact_id}: no L0 mapping")
        return {"valid": len(issues) == 0, "issues": issues, "blocked": []}

    def get_legal_family(self) -> str:
        return "common_law"

    def get_modal_mapping(self) -> Dict[str, str]:
        return dict(self._MODAL_MAPPING)

    def get_claim_tables(self) -> tuple[Dict[str, str], Dict[str, str]]:
        return {}, {}
