#!/usr/bin/env python3
"""L0 guard: verify that JC modules resolve to the local worktree, not external leaks."""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GUARD_MODULES = [
    "compiler_core",
    "compiler_core.types",
    "compiler_core.trust_labels",
    "pipeline.pipeline",
    "pipeline.schemas",
    "legalos_services",
    "legal_gates",
]


def verify_import_sources(expected_root: str | Path) -> Dict[str, Any]:
    expected = Path(expected_root).resolve()
    findings: List[Dict[str, str]] = []
    checked: List[str] = []
    for mod_name in GUARD_MODULES:
        try:
            mod = importlib.import_module(mod_name)
            mod_file = getattr(mod, "__file__", None)
            if mod_file is None:
                findings.append({"module": mod_name, "issue": "no __file__", "status": "FAIL"})
                continue
            mod_path = Path(mod_file).resolve()
            try:
                mod_path.relative_to(expected)
                checked.append(str(mod_path.relative_to(expected)))
            except ValueError:
                findings.append({"module": mod_name, "issue": str(mod_path), "status": "FAIL"})
        except ImportError:
            findings.append({"module": mod_name, "issue": "import failed", "status": "FAIL"})

    return {
        "expected_root": str(expected),
        "checked_modules": checked,
        "findings": findings,
        "status": "PASS" if not findings else "FAIL",
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify JC module import sources.")
    parser.add_argument("--root", default="D:/v2.0")
    args = parser.parse_args(argv)
    report = verify_import_sources(args.root)
    print(f"status={report['status']} root={report['expected_root']}")
    for f in report["findings"]:
        print(f"  LEAK: {f['module']} -> {f['issue']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
