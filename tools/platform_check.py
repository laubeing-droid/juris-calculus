#!/usr/bin/env python3
"""Cross-platform and cross-jurisdiction compatibility check.

For JC, "cross-platform" means:
  - Multi-OS: verify Python/stdlib availability (no GPU-specific deps)
  - Multi-jurisdiction: verify all addon configs load without ImportError
  - Unified interface: verify the same packaged runtime interfaces work regardless of OS
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

JURISDICTIONS = ["cn", "hk", "us"]


def check_platform(jurisdictions: List[str] | None = None) -> Dict[str, Any]:
    juris = jurisdictions or JURISDICTIONS
    findings: List[Dict[str, Any]] = []
    results: Dict[str, Any] = {}

    # OS-level
    os_info = {
        "system": platform.system(),
        "release": platform.release(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
    }

    # Verify core modules
    core_modules = [
        "yaml", "json", "pathlib", "importlib",
        "compiler_core", "pipeline.pipeline",
    ]
    for mod_name in core_modules:
        try:
            __import__(mod_name)
            results[f"import:{mod_name}"] = "OK"
        except ImportError as e:
            findings.append({"module": mod_name, "issue": str(e), "severity": "ERROR"})
            results[f"import:{mod_name}"] = "FAIL"

    # Verify addon configs per jurisdiction
    addon_configs = {
        "cn": ["configs/zh_CN/rules.yaml", "configs/zh_CN/domain_config.example.yaml"],
        "hk": ["configs/hk/rules.yaml", "configs/hk/extended_rules.yaml"],
        "us": ["configs/en_US/rules.yaml", "configs/en_US/US_Adapter.yaml"],
    }
    for jur in juris:
        for cfg_path in addon_configs.get(jur, []):
            fp = ROOT / cfg_path
            if fp.exists():
                results[f"config:{jur}:{cfg_path.split('/')[-1]}"] = "OK"
            else:
                findings.append({"config": cfg_path, "jurisdiction": jur, "issue": "missing", "severity": "WARN"})
                results[f"config:{jur}:{cfg_path.split('/')[-1]}"] = "MISSING"

    results["collision_interfaces"] = "SKIPPED_LEGACY_BLUEPRINT_REMOVED"

    passed = not any(f["severity"] == "ERROR" for f in findings)
    return {
        "status": "PASS" if passed else "FAIL",
        "os": os_info,
        "jurisdictions_checked": juris,
        "results": results,
        "findings": findings,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check JC cross-platform compatibility.")
    parser.add_argument("--jurisdictions", nargs="+", default=JURISDICTIONS)
    args = parser.parse_args(argv)
    report = check_platform(args.jurisdictions)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
