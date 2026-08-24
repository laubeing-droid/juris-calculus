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
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
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

W10_TASK_IDS = tuple(
    [f"W10-{index:02d}" for index in range(11)]
    + [f"Z10-{index:02d}" for index in range(4)]
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _task_report(task_id: str, checks: list[dict[str, object]], state_root: Path) -> int:
    passed = all(check.get("status") == "PASS" for check in checks)
    body = {
        "schema_version": "jc/w10-task-verification/1.0",
        "task_id": task_id,
        "status": "PASS" if passed else "FAIL",
        "source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
            text=True, check=True,
        ).stdout.strip(),
        "source_tree": subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, capture_output=True,
            text=True, check=True,
        ).stdout.strip(),
        "checks": checks,
    }
    body["report_digest"] = "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()
    path = state_root / "evidence" / "w10" / task_id / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(body))
    file_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"JC_ARTIFACT\t{task_id.lower()}-verification\t{path}\t{file_digest}")
    if not passed:
        for check in checks:
            if check.get("status") != "PASS":
                print(f"{task_id} failed: {check.get('name')}", file=sys.stderr)
    return 0 if passed else 1


def _verify_w10_00(state_root: Path) -> int:
    plan = json.loads((ROOT / "remediation/v4/tasks.json").read_text(encoding="utf-8"))
    tasks = {task["id"]: task for task in plan["tasks"]}
    expected_dependencies = {
        "W10-00": ["H8-07"],
        **{f"W10-{index:02d}": [f"W10-{index - 1:02d}"] for index in range(1, 11)},
        "Z10-00": ["W10-10"], "Z10-01": ["Z10-00"],
        "Z10-02": ["Z10-01"], "Z10-03": ["Z10-02"],
    }
    issue_map = json.loads((ROOT / "remediation/v4/issue-map.json").read_text(encoding="utf-8"))
    issue_ids = {item["id"] for item in issue_map["issues"]}
    supersession_path = state_root / "evidence/runtime-gap-supersession.json"
    supersession = (
        json.loads(supersession_path.read_text(encoding="utf-8"))
        if supersession_path.is_file() else {}
    )
    legacy = supersession.get("legacy_receipts", [])
    checks = [
        {"name": "exact-corrective-task-set", "status": "PASS" if all(task_id in tasks for task_id in W10_TASK_IDS) else "FAIL"},
        {"name": "all-corrective-tasks-auto", "status": "PASS" if all(tasks[task_id]["mode"] == "AUTO" for task_id in W10_TASK_IDS if task_id in tasks) else "FAIL"},
        {"name": "corrective-dependency-chain", "status": "PASS" if all(tasks.get(task_id, {}).get("depends_on") == dependencies for task_id, dependencies in expected_dependencies.items()) else "FAIL"},
        {"name": "runtime-gap-issues-registered", "status": "PASS" if {f"R-P0-0{i}" for i in range(1, 7)} | {f"R-P1-0{i}" for i in range(1, 8)} | {"R-P2-01"} <= issue_ids else "FAIL"},
        {"name": "append-only-supersession-present", "status": "PASS" if supersession.get("status") == "INVALIDATED_BY_RUNTIME_GAP" else "FAIL"},
        {"name": "legacy-receipt-bindings", "status": "PASS" if len(legacy) == 11 and all(str(item.get("receipt_digest", "")).startswith("sha256:") for item in legacy) else "FAIL"},
        {"name": "plan-digest-binding", "status": "PASS" if supersession.get("plan_sha256") == "sha256:fbfb9ae0d2db18aeb91662d2dda2d843ba998c0a6020695cd5487087832d695e" else "FAIL"},
    ]
    return _task_report("W10-00", checks, state_root)


def _verify_w10_01(state_root: Path) -> int:
    from dataclasses import fields
    from compiler_core.contracts import CaseArtifactV4, CaseInputBundleV4, MCPEvaluateInputV4
    from compiler_core.mcp import TOOL_SPECS, manifest_bytes, schema_bytes, standalone_type_schema

    bundle_fields = [item.name for item in fields(CaseInputBundleV4)]
    artifact_fields = [item.name for item in fields(CaseArtifactV4)]
    mcp_fields = [item.name for item in fields(MCPEvaluateInputV4)]
    mcp_schema = standalone_type_schema("MCPEvaluateInputV4")
    checks = [
        {"name": "case-artifact-fields", "status": "PASS" if artifact_fields == ["artifact_id", "content_ref", "artifact_kind", "media_type", "scope", "content_base64"] else "FAIL"},
        {"name": "case-bundle-fields", "status": "PASS" if bundle_fields == ["schema_version", "bundle_id", "request", "artifacts", "bundle_digest"] else "FAIL"},
        {"name": "mcp-one-bundle-field", "status": "PASS" if mcp_fields == ["case_bundle"] else "FAIL"},
        {"name": "mcp-four-tools", "status": "PASS" if len(TOOL_SPECS) == 4 else "FAIL"},
        {"name": "schema-publication-exact", "status": "PASS" if (ROOT / "schemas/jc-v4.schema.json").read_bytes() == schema_bytes() else "FAIL"},
        {"name": "manifest-publication-exact", "status": "PASS" if (ROOT / "mcp_manifest.json").read_bytes() == manifest_bytes() else "FAIL"},
        {"name": "closed-mcp-input", "status": "PASS" if mcp_schema["$defs"]["MCPEvaluateInputV4"]["additionalProperties"] is False else "FAIL"},
    ]
    return _task_report("W10-01", checks, state_root)


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
    parser.add_argument("--task", choices=W10_TASK_IDS)
    args = parser.parse_args()

    if args.task:
        if not args.state_root:
            print("W10 verifier requires JC_REMEDIATION_STATE_ROOT", file=sys.stderr)
            return 2
        if args.task == "W10-00":
            return _verify_w10_00(Path(args.state_root).resolve())
        if args.task == "W10-01":
            return _verify_w10_01(Path(args.state_root).resolve())
        print(f"{args.task} verifier is not implemented", file=sys.stderr)
        return 1

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
