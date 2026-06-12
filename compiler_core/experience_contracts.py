#!/usr/bin/env python3
"""Structured legal experience contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from compiler_core.config_paths import juris_contracts_path


@dataclass
class ExperienceContract:
    contract_id: str
    layer: str
    purpose: str
    pseudocode: str
    ref_docs: List[str] = field(default_factory=list)
    ref_code: List[str] = field(default_factory=list)
    ref_tests: List[str] = field(default_factory=list)
    dynamic_parameters: List[Dict[str, str]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


class ExperienceContractRegistry:
    def __init__(self, path: Optional[str] = None):
        self.path = Path(path or juris_contracts_path())
        self.data: Dict[str, Any] = {}
        self.contracts: Dict[str, ExperienceContract] = {}
        if self.path.exists():
            self.data = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            self.contracts = {
                contract.contract_id: contract
                for contract in self._parse_contracts(self.data.get("contracts", []))
            }

    def get(self, contract_id: str) -> Optional[ExperienceContract]:
        return self.contracts.get(contract_id)

    def list_ids(self) -> List[str]:
        return sorted(self.contracts)

    def by_layer(self, layer: str) -> List[ExperienceContract]:
        return [contract for contract in self.contracts.values() if contract.layer == layer]

    @staticmethod
    def _parse_contracts(raw_contracts: List[Dict[str, Any]]) -> List[ExperienceContract]:
        parsed: List[ExperienceContract] = []
        for item in raw_contracts or []:
            if not isinstance(item, dict):
                continue
            parsed.append(
                ExperienceContract(
                    contract_id=str(item.get("contract_id", "")),
                    layer=str(item.get("layer", "")),
                    purpose=str(item.get("purpose", "")),
                    pseudocode=str(item.get("pseudocode", "")),
                    ref_docs=[str(x) for x in item.get("ref_docs", [])],
                    ref_code=[str(x) for x in item.get("ref_code", [])],
                    ref_tests=[str(x) for x in item.get("ref_tests", [])],
                    dynamic_parameters=[dict(x) for x in item.get("dynamic_parameters", [])],
                    raw=item,
                )
            )
        return parsed
