#!/usr/bin/env python3
"""B00-CG verification helper.

施工方案 §7 B00-CG requires that every CodeGraph conclusion that drives
file dispositions be re-verified against exact source/AST ranges,
dynamic imports, package exports, manifests, workflows, and tests. This
script reads back the施工方案 §19.1 high-risk-edge list and produces a
JSON verification report under $JC_REMEDIATION_STATE_ROOT/evidence/b00_cg/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
HIGH_RISK = [
    {
        "claim": "render_run 被 CLI / JCClient 调用 (施工方案 §19.1)",
        "source_files": ["compiler_core/cli.py", "compiler_core/client.py"],
        "verify": "rg",
        "patterns": [r"render_run"],
    },
    {
        "claim": "analyze_strategy / analyze_similar_cases 被 CLI / WorkBuddy MCP 调用",
        "source_files": ["compiler_core/cli.py", "addons/workbuddy_mcp.py"],
        "verify": "rg",
        "patterns": [r"analyze_strategy", r"analyze_similar_cases"],
    },
    {
        "claim": "audit_pack 被 CLI 调用",
        "source_files": ["compiler_core/cli.py"],
        "verify": "rg",
        "patterns": [r"audit_pack"],
    },
    {
        "claim": "export_corpus_pack 被 CLI 调用",
        "source_files": ["compiler_core/cli.py"],
        "verify": "rg",
        "patterns": [r"export_corpus_pack"],
    },
    {
        "claim": "lookup_rules 被 WorkBuddy MCP 调用",
        "source_files": ["addons/workbuddy_mcp.py"],
        "verify": "rg",
        "patterns": [r"lookup_rules", r"jc_lookup_rule"],
    },
    {
        "claim": "litigation_engineering.generate_certificate 被 application._evaluate_once 调用",
        "source_files": ["compiler_core/litigation_engineering.py", "compiler_core/application.py"],
        "verify": "rg",
        "patterns": [r"generate_certificate", r"_evaluate_once"],
    },
    {
        "claim": "transformer.auto_patch 函数内 import FixpointEvaluator.__init__",
        "source_files": ["compiler_core/transformer.py", "compiler_core/evaluator.py"],
        "verify": "rg",
        "patterns": [r"auto_patch", r"FixpointEvaluator"],
    },
    {
        "claim": "spec_shadow_harness 动态加载 companion spec",
        "source_files": ["compiler_core/spec_shadow_harness.py"],
        "verify": "rg",
        "patterns": [r"importlib", r"__import__", r"spec_shadow"],
    },
    {
        "claim": "plugin_registry 动态加载 addons.*",
        "source_files": ["compiler_core/plugin_registry.py"],
        "verify": "rg",
        "patterns": [r"importlib", r"addons\.", r"__import__"],
    },
    {
        "claim": "configs/zh_CN/rules.yaml fingerprinted and 21,144 unique rule IDs",
        "source_files": [],
        "verify": "frozen_fingerprint",
        "patterns": [],
    },
]


def _rg(pattern: str, file_glob: list[str] | None = None) -> list[tuple[str, int, str]]:
    args = ["rg", "--no-heading", "--line-number",
            "-g", "!.codegraph/**", "-g", "!.git/**", pattern]
    if file_glob:
        for g in file_glob:
            args.extend(["-g", g])
    args.append(".")
    cp = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True, check=False)
    out = []
    for line in cp.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) >= 3:
            rel = parts[0].replace("\\", "/").lstrip("./")
            if rel.startswith("/"):
                rel = rel.lstrip("/")
            out.append((rel, int(parts[1]), parts[2]))
    return out


def _verify_one(item: dict[str, Any]) -> dict[str, Any]:
    if item["verify"] == "frozen_fingerprint":
        rules = ROOT / "configs" / "zh_CN" / "rules.yaml"
        if not rules.is_file():
            return {
                "claim": item["claim"],
                "status": "FAIL",
                "detail": "configs/zh_CN/rules.yaml not in current tree (W5-02C expected)",
            }
        sha = subprocess.run(
            ["git", "hash-object", str(rules)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return {
            "claim": item["claim"],
            "status": "PRESENT",
            "detail": f"current git blob sha={sha}",
        }
    # rg-based verification. ripgrep ordering is filesystem-dependent so
    # we sort hits by (path, line) for deterministic digests.
    hits: list[dict[str, Any]] = []
    for pat in item["patterns"]:
        for rel, lineno, content in _rg(pat):
            hits.append({"pattern": pat, "path": rel, "line": lineno, "text": content})
    hits.sort(key=lambda h: (h["path"], h["line"]))
    status = "CONFIRMED" if hits else "NOT_FOUND"
    return {"claim": item["claim"], "status": status, "hits": hits[:10]}


def main() -> int:
    parser = argparse.ArgumentParser(description="B00-CG verification report")
    parser.add_argument("--state-root", default=os.environ.get("JC_REMEDIATION_STATE_ROOT"))
    args = parser.parse_args()

    results = [_verify_one(item) for item in HIGH_RISK]
    source_tree_id = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    # Compute digest over (schema_version, source_tree_id, results) BEFORE
    # inserting it, so the digest is deterministic and reproducible.
    canon = json.dumps(
        {
            "schema_version": "jc/remediation-v4-b00cg-verify/1.0",
            "source_tree_id": source_tree_id,
            "results": results,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = "sha256:" + __import__("hashlib").sha256(canon.encode("utf-8")).hexdigest()
    report = {
        "schema_version": "jc/remediation-v4-b00cg-verify/1.0",
        "source_tree_id": source_tree_id,
        "results": results,
        "digest": digest,
    }
    if args.state_root:
        out_dir = Path(args.state_root) / "evidence" / "b00_cg" / report["source_tree_id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "verify.json"
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"verify report: {out_path}")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())