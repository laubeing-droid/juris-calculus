#!/usr/bin/env python3
"""v2.0 Addon plugin registry with auto-discovery.

Usage:
    from compiler_core.plugin_registry import registry
    registry.discover()  # auto-scans addons/ directory
    adapter = registry.get("us")  # None if addon not installed
"""
from typing import Dict, Optional, Any, List
from pathlib import Path


class PluginRegistry:
    def __init__(self):
        self._adapters: Dict[str, Dict] = {}

    def register(self, code: str, adapter_class: type, rules_path: str = "",
                 overrides_path: str = "", blocking_path: str = "",
                 label: str = "", legal_family: str = "civil_law"):
        self._adapters[code] = {
            "code": code,
            "class": adapter_class,
            "rules_path": rules_path,
            "overrides_path": overrides_path,
            "blocking_path": blocking_path,
            "label": label or code.upper(),
        }

    def get(self, code: str) -> Optional[Any]:
        entry = self._adapters.get(code)
        if entry is None:
            return None
        if "instance" not in entry:
            try:
                entry["instance"] = entry["class"]()
            except Exception:
                return None
        return entry["instance"]

    def get_rules_path(self, code: str) -> Optional[str]:
        entry = self._adapters.get(code)
        return entry["rules_path"] if entry else None

    def is_installed(self, code: str) -> bool:
        return code in self._adapters

    def get_by_family(self, family: str):
        return {code: self.get(code) for code in self._adapters
                if self._adapters[code].get("legal_family") == family}

    def list_installed(self) -> List[str]:
        return sorted(self._adapters.keys())

    def get_all(self) -> Dict[str, Any]:
        return {code: self.get(code) for code in self._adapters}

    def discover(self) -> int:
        """Auto-discover addons under addons/ directory.

        Scans addons/*/__init__.py and imports each as addons.{name}.
        Idempotent. Returns number of newly discovered addons.
        """
        import importlib
        d = Path(__file__).resolve().parent.parent / "addons"
        if not d.exists():
            return 0
        before = len(self._adapters)
        for e in sorted(d.iterdir()):
            if e.is_dir() and not e.name.startswith("_"):
                init_f = e / "__init__.py"
                if init_f.exists():
                    try:
                        importlib.import_module("addons." + e.name)
                    except Exception:
                        pass
        return len(self._adapters) - before


registry = PluginRegistry()
registry.discover()
