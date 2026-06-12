#!/usr/bin/env python3
"""v2.0 Juris Blueprint manager - Layer 0 single source of truth."""
import json
from pathlib import Path
from compiler_core.config_paths import blueprint_path as _cp_bp
from typing import Dict, List, Optional


class JurisBlueprint:
    def __init__(self, blueprint_path: str = None):
        self.path = Path(blueprint_path)
        self.data: Dict = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    @property
    def version(self) -> str:
        return self.data.get("metadata", {}).get("version", "0.0.0")

    @property
    def contracts(self) -> List[Dict]:
        return self.data.get("element_composition_contracts", [])

    @property
    def conflict_interfaces(self) -> List[Dict]:
        return self.data.get("jurisdiction_conflict_interfaces", [])

    @property
    def failure_modes(self) -> List[Dict]:
        return self.data.get("failure_mode_library", [])

    @property
    def source_statutes(self) -> Dict:
        return self.data.get("metadata", {}).get("source_statutes", {})
