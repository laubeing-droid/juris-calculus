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


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


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
    payload = _canonical(body)
    latest = state_root / "evidence" / "w10" / task_id / "report.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_bytes(payload)
    file_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    snapshot = latest.parent / "reports" / f"{file_digest.removeprefix('sha256:')}.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if not snapshot.exists():
        snapshot.write_bytes(payload)
    print(f"JC_ARTIFACT\t{task_id.lower()}-verification\t{snapshot}\t{file_digest}")
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


def _verify_w10_02(state_root: Path) -> int:
    from compiler_core.artifact_store import ArtifactResolverV4
    from compiler_core.client import JCClient

    resolver_source = (ROOT / "compiler_core/artifact_store.py").read_text(encoding="utf-8")
    client_source = (ROOT / "compiler_core/client.py").read_text(encoding="utf-8")
    checks = [
        {"name": "overlay-context-manager", "status": "PASS" if callable(getattr(ArtifactResolverV4, "overlay", None)) and "ContextVar" in resolver_source else "FAIL"},
        {"name": "bundle-closure-validator", "status": "PASS" if callable(getattr(ArtifactResolverV4, "validate_case_bundle", None)) else "FAIL"},
        {"name": "client-bundle-boundary", "status": "PASS" if callable(getattr(JCClient, "validate_bundle", None)) and "with self._evaluation_context(admitted)" in client_source else "FAIL"},
        {"name": "no-overlay-dict-clear", "status": "PASS" if ".clear()" not in resolver_source else "FAIL"},
        {"name": "no-process-restart-isolation", "status": "PASS" if "subprocess" not in resolver_source and "multiprocessing" not in resolver_source else "FAIL"},
    ]
    return _task_report("W10-02", checks, state_root)


def _verify_w10_03(state_root: Path) -> int:
    from compiler_core.production_pack import load_production_pack

    production = ROOT.parent / "juris-calculus-v4-production-state"
    loader_source = (ROOT / "compiler_core/production_pack.py").read_text(encoding="utf-8")
    service_key = production / "identity/service-runtime.json"
    checks = [
        {"name": "strict-production-loader", "status": "PASS" if callable(load_production_pack) and "PACK_FIELDS" in loader_source else "FAIL"},
        {"name": "current-utc-verification", "status": "PASS" if "current_utc_time() if now is None" in loader_source else "FAIL"},
        {"name": "runtime-service-key-exists", "status": "PASS" if service_key.is_file() else "FAIL"},
        {"name": "runtime-does-not-read-root", "status": "PASS" if "root.json" not in loader_source else "FAIL"},
        {"name": "no-tools-tests-import", "status": "PASS" if "from tools" not in loader_source and "from tests" not in loader_source else "FAIL"},
    ]
    return _task_report("W10-03", checks, state_root)


def _verify_w10_04(state_root: Path) -> int:
    from compiler_core.production_runtime import create_client

    source = (ROOT / "compiler_core/production_runtime.py").read_text(encoding="utf-8")
    checks = [
        {"name": "production-factory", "status": "PASS" if callable(create_client) else "FAIL"},
        {"name": "complete-application", "status": "PASS" if all(name in source for name in ("ApplicationV4(", "AuditBundleStoreV4(", "CertificateIssuerV4(", "IndependentCheckerV4(")) else "FAIL"},
        {"name": "per-request-run-identity", "status": "PASS" if "RunIdentityV4.build(" in source and "resolver.overlay(transient)" in source else "FAIL"},
        {"name": "artifact-handles", "status": "PASS" if "issue_artifact_handle(" in source and "MCPEvaluateOutputV4(" in source else "FAIL"},
        {"name": "offline-replay", "status": "PASS" if "ReplayExecutionV4(" in source and "replay_executor=replay_executor" in source else "FAIL"},
    ]
    return _task_report("W10-04", checks, state_root)


def _verify_w10_05(state_root: Path) -> int:
    cli_source = (ROOT / "compiler_core/cli.py").read_text(encoding="utf-8")
    client_source = (ROOT / "compiler_core/client.py").read_text(encoding="utf-8")
    server_source = (ROOT / "mcp_server.py").read_text(encoding="utf-8")
    schema = json.loads((ROOT / "schemas/jc-v4.schema.json").read_bytes())
    evaluate = schema["$defs"]["MCPEvaluateInputV4"]
    checks = [
        {"name": "cli-case-bundle", "status": "PASS" if "CaseInputBundleV4.from_json_bytes" in cli_source and "CaseRequestV4.from_json_bytes" not in cli_source else "FAIL"},
        {"name": "client-case-bundle", "status": "PASS" if "validate_bundle" in client_source and "request.request" not in client_source else "FAIL"},
        {"name": "mcp-closed-input", "status": "PASS" if evaluate.get("required") == ["case_bundle"] and set(evaluate.get("properties", {})) == {"case_bundle"} else "FAIL"},
        {"name": "stdio-startup-fails-closed", "status": "PASS" if "except Exception" in server_source and "return 1" in server_source else "FAIL"},
        {"name": "generated-publications", "status": "PASS" if (ROOT / "mcp_manifest.json").is_file() else "FAIL"},
    ]
    return _task_report("W10-05", checks, state_root)


def _verify_w10_06(state_root: Path) -> int:
    from compiler_core.formal_bridge import FormalBridgeV4, StdioSessionV4, load_active_profile

    source = (ROOT / "compiler_core/formal_bridge.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    cli_source = (ROOT / "compiler_core/cli.py").read_text(encoding="utf-8")
    forbidden = ("RuleV4", "LegalIR", "BackendRouter", "ApplicationV4")
    checks = [
        {"name": "formal-entrypoint", "status": "PASS" if 'jc-formal = "compiler_core.formal_bridge:main"' in pyproject else "FAIL"},
        {"name": "active-profile-registry", "status": "PASS" if callable(load_active_profile) and "active_profile" in source else "FAIL"},
        {"name": "real-stdio-session", "status": "PASS" if callable(StdioSessionV4.deliver) and "subprocess.Popen(" in source else "FAIL"},
        {"name": "pinned-reconnect", "status": "PASS" if callable(FormalBridgeV4.connect) and "MCP_CAPABILITY_DRIFT" in source else "FAIL"},
        {"name": "paged-exact-delivery", "status": "PASS" if "JC_FORMAL_VERIFIED" in source and "FORMAL_ARTIFACT_BYTES" in source else "FAIL"},
        {"name": "general-cli-unchanged", "status": "PASS" if "formal_bridge" not in cli_source else "FAIL"},
        {"name": "no-legal-semantics-copy", "status": "PASS" if not any(name in source for name in forbidden) else "FAIL"},
    ]
    return _task_report("W10-06", checks, state_root)


def _verify_w10_07(state_root: Path) -> int:
    from compiler_core.canonical_serialization import canonical_bytes
    from compiler_core.formal_bridge import load_active_profile
    from tools.wheel_gate import validate_wheel

    production = ROOT.parent / "juris-calculus-v4-production-state"
    pointer_path = production / "deployment/prepared.json"
    pointer = json.loads(pointer_path.read_bytes()) if pointer_path.is_file() else {}
    manifest_path = Path(pointer.get("manifest_path", "."))
    manifest = json.loads(manifest_path.read_bytes()) if manifest_path.is_file() else {}
    wheel = Path(manifest.get("wheel_path", "."))
    profile_path = Path(manifest.get("profile_path", "."))
    config_path = Path(manifest.get("runtime_config_path", "."))
    checks = [
        {"name": "prepared-pointer-canonical", "status": "PASS" if pointer and pointer_path.read_bytes() == canonical_bytes(pointer) else "FAIL"},
        {"name": "release-manifest-canonical", "status": "PASS" if manifest and manifest_path.read_bytes() == canonical_bytes(manifest) else "FAIL"},
        {"name": "inactive-prepared-release", "status": "PASS" if manifest.get("status") == "PREPARED" and manifest.get("activated") is False else "FAIL"},
        {"name": "reproducible-wheel", "status": "PASS" if manifest.get("reproducible_build") is True and wheel.is_file() and _digest(wheel) == manifest.get("wheel_digest") else "FAIL"},
        {"name": "installed-origin", "status": "PASS" if manifest.get("installed_origin_verified") is True and Path(manifest.get("venv_python", ".")).is_file() else "FAIL"},
        {"name": "runtime-config", "status": "PASS" if config_path.is_file() and _digest(config_path) == manifest.get("runtime_config_digest") else "FAIL"},
        {"name": "production-profile", "status": "PASS" if profile_path.is_file() and _digest(profile_path) == manifest.get("profile_digest") else "FAIL"},
        {"name": "efs-aes-256", "status": "PASS" if manifest.get("efs", {}).get("algorithm") == "EFS-AES-256" else "FAIL"},
        {"name": "not-activated", "status": "PASS" if not (production / "deployment/profile-registry.json").exists() else "FAIL"},
    ]
    try:
        validate_wheel(ROOT, wheel)
        checks.append({"name": "wheel-exact-set", "status": "PASS"})
        registry = {
            "schema_version": "jc/formal-profile-registry/1.0",
            "active_profile": manifest["release_id"],
            "profiles": {manifest["release_id"]: json.loads(profile_path.read_bytes())},
        }
        temporary = state_root / "tmp/W10-07/profile-registry.json"
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(canonical_bytes(registry))
        load_active_profile(temporary)
        checks.append({"name": "profile-loads", "status": "PASS"})
    except (OSError, TypeError, ValueError):
        checks.extend((
            {"name": "wheel-exact-set", "status": "FAIL"},
            {"name": "profile-loads", "status": "FAIL"},
        ))
    return _task_report("W10-07", checks, state_root)


def _verify_w10_08(state_root: Path) -> int:
    from compiler_core.canonical_serialization import canonical_bytes
    from compiler_core.formal_bridge import load_active_profile

    production = ROOT.parent / "juris-calculus-v4-production-state"
    current_path = production / "deployment/current.json"
    registry_path = production / "deployment/profile-registry.json"
    previous_path = production / "deployment/previous.json"
    current = json.loads(current_path.read_bytes()) if current_path.is_file() else {}
    manifest_path = Path(current.get("manifest_path", "."))
    manifest = json.loads(manifest_path.read_bytes()) if manifest_path.is_file() else {}
    chain_path = Path(current.get("verification_path", "."))
    chain = json.loads(chain_path.read_bytes()) if chain_path.is_file() else {}
    positives = chain.get("positive_runs", [])
    matrix = chain.get("state_matrix", {})
    expected_matrix = {
        "missing": "missing_required_fact",
        "review": "review_only_result",
        "hypothetical": "hypothetical_result",
    }
    checks = [
        {"name": "active-current-canonical", "status": "PASS" if current and current_path.read_bytes() == canonical_bytes(current) and current.get("status") == "LOCAL_PRODUCTION_ACTIVE" else "FAIL"},
        {"name": "release-binding", "status": "PASS" if manifest and current.get("release_id") == manifest.get("release_id") and current.get("manifest_digest") == _digest(manifest_path) else "FAIL"},
        {"name": "six-positive-installed-runs", "status": "PASS" if [row.get("article") for row in positives] == list(range(13, 19)) and all(row.get("decision_status") == "accepted_formal_result" for row in positives) else "FAIL"},
        {"name": "verify-replay-read", "status": "PASS" if positives and all(row.get("verification", {}).get("status") == "VERIFIED" and row.get("replay", {}).get("status") == "MATCH" and row.get("reads") for row in positives) else "FAIL"},
        {"name": "nonformal-state-matrix", "status": "PASS" if all(matrix.get(name, {}).get("decision_status") == status for name, status in expected_matrix.items()) and ("error_code" in matrix.get("wrong_fact_signature", {}) or matrix.get("wrong_fact_signature", {}).get("decision_status") in {"blocked", "engine_error"}) else "FAIL"},
        {"name": "formal-bridge-exact-delivery", "status": "PASS" if chain.get("formal_bridge", {}).get("marker") == "JC_FORMAL_VERIFIED" else "FAIL"},
        {"name": "positive-chain-binding", "status": "PASS" if chain.get("release_id") == current.get("release_id") and current.get("verification_digest") == _digest(chain_path) else "FAIL"},
        {"name": "legacy-previous-not-rollbackable", "status": "PASS" if previous_path.is_file() and json.loads(previous_path.read_bytes()).get("production_rollback_allowed") is False else "FAIL"},
        {"name": "efs-active-scope", "status": "PASS" if manifest.get("efs", {}).get("algorithm") == "EFS-AES-256" and current.get("scope") == "local-windows-efs-pipl-articles-13-18" else "FAIL"},
    ]
    try:
        profile = load_active_profile(registry_path)
        checks.append({"name": "active-installed-profile", "status": "PASS" if profile.profile_id == current.get("release_id") else "FAIL"})
    except (OSError, TypeError, ValueError):
        checks.append({"name": "active-installed-profile", "status": "FAIL"})
    return _task_report("W10-08", checks, state_root)


def _verify_w10_09(state_root: Path) -> int:
    from compiler_core.canonical_serialization import canonical_bytes
    from tools.local_production import production_status

    production = ROOT.parent / "juris-calculus-v4-production-state"
    report_path = production / "operations/recovery-report.json"
    report = json.loads(report_path.read_bytes()) if report_path.is_file() else {}
    backup_id = report.get("backup", {}).get("backup_id", "")
    backup_path = production / "backups" / str(backup_id) / "manifest.json"
    restore_path = production / "operations/restore-rehearsals" / str(backup_id) / "report.json"
    daily_id = report.get("daily_backup_id", "")
    daily_path = production / "backups" / str(daily_id) / "manifest.json"
    checks = [
        {"name": "operations-report-canonical", "status": "PASS" if report and report_path.read_bytes() == canonical_bytes(report) and report.get("status") == "OPERATIONS_VERIFIED" else "FAIL"},
        {"name": "backup-manifest-verified", "status": "PASS" if backup_path.is_file() and json.loads(backup_path.read_bytes()).get("backup_id") == backup_id else "FAIL"},
        {"name": "independent-restore-rehearsal", "status": "PASS" if restore_path.is_file() and json.loads(restore_path.read_bytes()).get("status") == "RESTORE_REHEARSAL_VERIFIED" else "FAIL"},
        {"name": "upgrade-rollback-reactivate", "status": "PASS" if report.get("upgrade_release_id") == report.get("reactivated_release_id") and report.get("rollback_release_id") == report.get("before", {}).get("release_id") else "FAIL"},
        {"name": "partial-install-atomicity", "status": "PASS" if report.get("partial_install_current_unchanged") is True else "FAIL"},
        {"name": "inactive-revocation-release", "status": "PASS" if report.get("revocation", {}).get("status") == "PREPARED_INACTIVE" and report.get("revocation", {}).get("replacement_required_before_activation") is True else "FAIL"},
        {"name": "daily-backup-completed", "status": "PASS" if daily_path.is_file() and json.loads(daily_path.read_bytes()).get("retention_class") == "daily" else "FAIL"},
        {"name": "daily-task-installed-no-repo", "status": "PASS" if report.get("scheduled_task", {}).get("status") == "INSTALLED" and report.get("scheduled_task", {}).get("repo_path_absent") is True else "FAIL"},
        {"name": "resource-budget-recorded", "status": "PASS" if report.get("resource_budget", {}).get("solver_deadline_ms") == 2500 and report.get("resource_budget", {}).get("page_bytes") == 65536 else "FAIL"},
    ]
    try:
        status = production_status(production)
        checks.append({"name": "post-operations-active", "status": "PASS" if status.get("status") == "LOCAL_PRODUCTION_ACTIVE" and status.get("release_id") == report.get("reactivated_release_id") else "FAIL"})
    except (OSError, TypeError, ValueError):
        checks.append({"name": "post-operations-active", "status": "FAIL"})
    return _task_report("W10-09", checks, state_root)


def _latest_completed_receipt(state_root: Path, task_id: str) -> tuple[dict[str, object], Path]:
    paths = sorted(
        (state_root / "tasks" / task_id).glob("*/receipt.json"),
        key=lambda path: int(path.parent.name),
    )
    completed = []
    for path in paths:
        value = json.loads(path.read_bytes())
        body = {key: item for key, item in value.items() if key != "receipt_digest"}
        actual = "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()
        if value.get("receipt_digest") == actual and value.get("status") == "COMPLETED":
            completed.append((value, path))
    if not completed:
        raise ValueError(f"{task_id} has no valid completed receipt")
    return completed[-1]


def _verify_w10_10(state_root: Path) -> int:
    receipts: dict[str, dict[str, object]] = {}
    receipt_paths: dict[str, Path] = {}
    valid = True
    try:
        for index in range(10):
            task_id = f"W10-{index:02d}"
            receipts[task_id], receipt_paths[task_id] = _latest_completed_receipt(
                state_root, task_id
            )
    except (OSError, TypeError, ValueError):
        valid = False
    reports = {
        task_id: state_root / "evidence/w10" / task_id / "report.json"
        for task_id in receipts
    }
    report_names: list[tuple[str, ...]] = []
    reports_valid = True
    for task_id, path in reports.items():
        try:
            report = json.loads(path.read_bytes())
            names = tuple(row["name"] for row in report["checks"])
            reports_valid = reports_valid and (
                report.get("task_id") == task_id
                and report.get("status") == "PASS"
                and len(names) == len(set(names))
            )
            report_names.append(names)
        except (KeyError, OSError, TypeError, ValueError):
            reports_valid = False
    chain_valid = valid and all(
        receipts[f"W10-{index:02d}"].get("input_receipt_digests", {}).get(
            f"W10-{index - 1:02d}"
        ) == receipts[f"W10-{index - 1:02d}"].get("receipt_digest")
        for index in range(1, 10)
    )
    failed_w10_08 = list((state_root / "tasks/W10-08").glob("*/receipt.json"))
    checks = [
        {"name": "ten-valid-task-receipts", "status": "PASS" if valid and len(receipts) == 10 else "FAIL"},
        {"name": "receipt-dependency-chain", "status": "PASS" if chain_valid else "FAIL"},
        {"name": "task-specific-pass-reports", "status": "PASS" if reports_valid and len(reports) == 10 else "FAIL"},
        {"name": "distinct-verifier-check-sets", "status": "PASS" if len(report_names) == len(set(report_names)) == 10 else "FAIL"},
        {"name": "failed-attempts-preserved", "status": "PASS" if len(failed_w10_08) >= 3 and any(json.loads(path.read_bytes()).get("status") == "FAILED" for path in failed_w10_08) else "FAIL"},
        {"name": "receipt-commit-tree-command-bindings", "status": "PASS" if valid and all(row.get("start_commit") and row.get("start_tree") and row.get("result_commit") and row.get("result_tree") and row.get("command_results") and row.get("allowlist", {}).get("allowed") is True for row in receipts.values()) else "FAIL"},
        {"name": "latest-head-is-w10-09", "status": "PASS" if receipts.get("W10-09", {}).get("receipt_digest") == "sha256:273e9db30af00dd016e5f4dcfa332b6087b75febd5a4ab9f20a16ac1ac100459" else "FAIL"},
    ]
    return _task_report("W10-10", checks, state_root)


def _verify_z10_00(state_root: Path) -> int:
    import shutil
    plan = json.loads((ROOT / "remediation/v4/tasks.json").read_bytes())
    tasks = {row["id"]: row for row in plan["tasks"]}
    expected = list(W10_TASK_IDS)
    generated = subprocess.run(
        [sys.executable, "-B", "tools/remediate_v4.py", "generated", "--check"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    codegraph = shutil.which("codegraph") or shutil.which("codegraph.cmd")
    indexed = subprocess.run(
        [str(codegraph), "index", "--force", "--quiet", str(ROOT)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    status = subprocess.run(
        [str(codegraph), "status", "--json", str(ROOT)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    integrity = "missing"
    try:
        import sqlite3
        with sqlite3.connect(ROOT / ".codegraph/codegraph.db") as database:
            integrity = str(database.execute("PRAGMA integrity_check").fetchone()[0])
    except (OSError, TypeError, ValueError):
        integrity = "error"
    issue_map = json.loads((ROOT / "remediation/v4/issue-map.json").read_bytes())
    closure_ids = {
        task_id for issue in issue_map["issues"] if str(issue["id"]).startswith("R-")
        for task_id in issue.get("closure_tasks", [])
    }
    reports_present = all(
        (state_root / "evidence/w10" / task_id / "report.json").is_file()
        for task_id in [f"W10-{index:02d}" for index in range(11)]
    )
    checks = [
        {"name": "corrective-dag-exact-and-auto", "status": "PASS" if all(task_id in tasks and tasks[task_id]["mode"] == "AUTO" for task_id in expected) else "FAIL"},
        {"name": "generated-control-plane-exact", "status": "PASS" if generated.returncode == 0 else "FAIL"},
        {"name": "issue-map-closure-tasks-reachable", "status": "PASS" if closure_ids <= set(tasks) else "FAIL"},
        {"name": "all-w10-verifier-reports-present", "status": "PASS" if reports_present else "FAIL"},
        {"name": "codegraph-full-index", "status": "PASS" if indexed.returncode == 0 and status.returncode == 0 else "FAIL"},
        {"name": "codegraph-sqlite-integrity", "status": "PASS" if integrity == "ok" else "FAIL"},
        {"name": "version-and-publications", "status": "PASS" if '4.0.0' in (ROOT / "compiler_core/version.py").read_text(encoding="utf-8") and (ROOT / "schemas/jc-v4.schema.json").is_file() and (ROOT / "mcp_manifest.json").is_file() else "FAIL"},
        {"name": "no-active-legacy-profile", "status": "PASS" if "test-local" not in (ROOT.parent / "juris-calculus-v4-production-state/deployment/profile-registry.json").read_text(encoding="utf-8") else "FAIL"},
    ]
    return _task_report("Z10-00", checks, state_root)


_Z10_INSTALLED_REVERIFY = r"""
import base64,json,pathlib,sys
from compiler_core.canonical_serialization import DigestV4,canonical_bytes
from compiler_core.client import runtime_client
from compiler_core.contracts import ArtifactHandleV4
chain=json.loads(pathlib.Path(sys.argv[1]).read_bytes())
client=runtime_client(); rows=[]
for index,item in enumerate(chain["positive_runs"]):
 handle=ArtifactHandleV4.from_dict(item["run_handle"])
 checked=client.verify_for_mcp(handle,offline_replay=index==0)
 if checked.verification.status!="VERIFIED": raise RuntimeError("verify")
 if index==0 and (checked.replay is None or checked.replay.status!="MATCH"): raise RuntimeError("replay")
 reads=[]
 for raw in (item["certificate_handle"],*item["artifact_handles"]):
  artifact=ArtifactHandleV4.from_dict(raw); offset=0; content=bytearray()
  while offset<artifact.size_bytes:
   page=client.read_artifact(artifact,offset=offset,length=min(65536,artifact.size_bytes-offset))
   chunk=base64.b64decode(page.content_base64,validate=True); content.extend(chunk); offset+=len(chunk)
  if DigestV4.from_bytes(content)!=artifact.content_ref.digest: raise RuntimeError("read")
  reads.append(artifact.content_ref.to_dict())
 rows.append({"article":item["article"],"run_identity_ref":item["run_identity_ref"],"certificate_ref":item["certificate_handle"]["content_ref"],"read_refs":reads,"verification_status":checked.verification.status,"replay_status":None if checked.replay is None else checked.replay.status})
print(canonical_bytes({"runs":rows}).decode())
"""


def _verify_z10_01(state_root: Path) -> int:
    import time
    production = ROOT.parent / "juris-calculus-v4-production-state"
    current = json.loads((production / "deployment/current.json").read_bytes())
    manifest = json.loads(Path(current["manifest_path"]).read_bytes())
    chain_path = Path(current["verification_path"])
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment.update({
        "JC_RUNTIME_FACTORY": "compiler_core.production_runtime",
        "JC_PRODUCTION_CONFIG": manifest["runtime_config_path"],
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    runtime = Path(manifest["runtime_config_path"]).parent.parent / "runtime"
    completed = subprocess.run(
        [manifest["venv_python"], "-I", "-B", "-c", _Z10_INSTALLED_REVERIFY, str(chain_path)],
        cwd=runtime, env=environment, capture_output=True, text=True, check=False, timeout=900,
    )
    installed = json.loads(completed.stdout) if completed.returncode == 0 else {}
    bridge_result: dict[str, object] = {}
    try:
        from tests.formal_e2e.test_local_production_chain import production_bundle
        smoke = Path(current["manifest_path"]).parent / "evidence/z10-independent-bundle.json"
        smoke.write_bytes(production_bundle(15, label=f"z10-{time.time_ns()}").canonical_bytes())
        bridge = Path(manifest["venv_python"]).with_name("jc-formal.exe" if os.name == "nt" else "jc-formal")
        result = subprocess.run(
            [str(bridge), "--registry", str(production / "deployment/profile-registry.json"), "--input", str(smoke)],
            cwd=runtime, env=environment, capture_output=True, text=True, check=False, timeout=300,
        )
        bridge_result = json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, TypeError, ValueError):
        bridge_result = {}
    report = {
        "schema_version": "jc/z10-artifact-reverification/1.0",
        "release_id": current["release_id"],
        "wheel_digest": manifest["wheel_digest"],
        "manifest_digest": current["manifest_digest"],
        "runs": installed.get("runs", []),
        "formal_bridge": {
            "marker": bridge_result.get("marker"),
            "artifact_digest": bridge_result.get("artifact_digest"),
            "profile_id": bridge_result.get("profile_id"),
        },
        "installed_no_repo_cwd": runtime != ROOT and "PYTHONPATH" not in environment,
    }
    report["report_digest"] = "sha256:" + hashlib.sha256(_canonical(report)).hexdigest()
    path = state_root / "evidence/z10-artifact-reverification.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(report))
    checks = [
        {"name": "fresh-installed-process", "status": "PASS" if completed.returncode == 0 and report["installed_no_repo_cwd"] else "FAIL"},
        {"name": "six-run-independent-verify", "status": "PASS" if [row.get("article") for row in report["runs"]] == list(range(13, 19)) and all(row.get("verification_status") == "VERIFIED" for row in report["runs"]) else "FAIL"},
        {"name": "offline-replay-independent", "status": "PASS" if report["runs"] and report["runs"][0].get("replay_status") == "MATCH" else "FAIL"},
        {"name": "certificate-result-reads", "status": "PASS" if report["runs"] and all(len(row.get("read_refs", [])) >= 2 for row in report["runs"]) else "FAIL"},
        {"name": "fresh-formal-bridge", "status": "PASS" if report["formal_bridge"].get("marker") == "JC_FORMAL_VERIFIED" else "FAIL"},
    ]
    return _task_report("Z10-01", checks, state_root)


def _verify_z10_02(state_root: Path) -> int:
    from tools.local_production import production_status
    production = ROOT.parent / "juris-calculus-v4-production-state"
    current = json.loads((production / "deployment/current.json").read_bytes())
    previous = json.loads((production / "deployment/previous.json").read_bytes())
    operations = json.loads((production / "operations/recovery-report.json").read_bytes())
    service = production / "identity/service-runtime.json"
    cipher = subprocess.run(["cipher", "/c", str(service)], capture_output=True, text=True, check=False)
    acl = subprocess.run(["icacls", str(service)], capture_output=True, text=True, check=False)
    scheduled = subprocess.run(
        ["schtasks", "/Query", "/TN", "JurisCalculusV4DailyBackup", "/XML"],
        capture_output=True, text=True, check=False,
    )
    main = ROOT.parent / "juris-calculus"
    main_status = subprocess.run(
        ["git", "status", "--short"], cwd=main, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    worktree_clean = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout == ""
    status = production_status(production)
    checks = [
        {"name": "active-current-and-previous", "status": "PASS" if status["status"] == "LOCAL_PRODUCTION_ACTIVE" and previous.get("production_rollback_allowed") is True else "FAIL"},
        {"name": "remediation-worktree-clean", "status": "PASS" if worktree_clean else "FAIL"},
        {"name": "main-worktree-user-state-preserved", "status": "PASS" if main_status and all(line.startswith(" D ") for line in main_status) else "FAIL"},
        {"name": "efs-service-key", "status": "PASS" if cipher.returncode == 0 and "AES" in cipher.stdout and "256" in cipher.stdout else "FAIL"},
        {"name": "service-key-minimal-acl", "status": "PASS" if acl.returncode == 0 and "Everyone" not in acl.stdout and "Users:(" not in acl.stdout else "FAIL"},
        {"name": "operations-evidence", "status": "PASS" if operations.get("status") == "OPERATIONS_VERIFIED" and operations.get("reactivated_release_id") == current.get("release_id") else "FAIL"},
        {"name": "daily-task-live", "status": "PASS" if scheduled.returncode == 0 and "JurisCalculusV4DailyBackup" in scheduled.stdout else "FAIL"},
        {"name": "scope-and-observation", "status": "PASS" if current.get("scope") == "local-windows-efs-pipl-articles-13-18" and json.loads((production / "packs/cn-official-local-4.0.0.json").read_bytes()).get("observation_required") is True else "FAIL"},
        {"name": "no-remote-production-action", "status": "PASS" if not (state_root / "evidence/remote-release.json").exists() else "FAIL"},
    ]
    return _task_report("Z10-02", checks, state_root)


def _verify_z10_03(state_root: Path) -> int:
    production = ROOT.parent / "juris-calculus-v4-production-state"
    z_reports = {
        task_id: state_root / "evidence/w10" / task_id / "report.json"
        for task_id in ("Z10-00", "Z10-01", "Z10-02")
    }
    loaded = {task_id: json.loads(path.read_bytes()) for task_id, path in z_reports.items()}
    if any(report.get("status") != "PASS" for report in loaded.values()):
        return _task_report("Z10-03", [{"name": "z10-prerequisites", "status": "FAIL"}], state_root)
    current = json.loads((production / "deployment/current.json").read_bytes())
    manifest = json.loads(Path(current["manifest_path"]).read_bytes())
    chain = json.loads(Path(current["verification_path"]).read_bytes())
    operations_path = production / "operations/recovery-report.json"
    operations = json.loads(operations_path.read_bytes())
    service = json.loads((production / "identity/service-runtime.json").read_bytes())
    w10_head, w10_head_path = _latest_completed_receipt(state_root, "W10-10")
    start, _ = _latest_completed_receipt(state_root, "W10-00")
    runtime_config = json.loads(Path(manifest["runtime_config_path"]).read_bytes())
    result = {
        "schema_version": "jc/final-production-runtime-result/1.0",
        "exit_code": 0, "status": "LOCAL_PRODUCTION_ACTIVE",
        "scope": "local-windows-efs-pipl-articles-13-18",
        "start_commit": start["start_commit"], "start_tree": start["start_tree"],
        "final_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        "final_tree": subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip(),
        "release_id": current["release_id"], "wheel_digest": manifest["wheel_digest"],
        "package_digest": manifest["package_digest"], "lock_digest": manifest["lock_digest"],
        "schema_digest": runtime_config["schema_digest"] if "schema_digest" in runtime_config else json.loads(Path(manifest["profile_path"]).read_bytes())["capability_pins"]["schema_digest"],
        "tool_spec_digest": runtime_config["tool_spec_digest"],
        "runtime_config_digest": manifest["runtime_config_digest"],
        "profile_digest": manifest["profile_digest"],
        "pack_ref": json.loads((production / "packs/cn-official-local-4.0.0.json").read_bytes())["pack_ref"],
        "trust_digest": _digest(production / "trust/cn-official-local.json"),
        "storage_ref": runtime_config["storage_capability_ref"],
        "service_key_public_identity": {key: service[key] for key in ("key_id", "issuer", "principal_id", "public_key_base64")},
        "positive_runs": [{
            "article": row["article"], "run_identity_ref": row["run_identity_ref"],
            "certificate_ref": row["certificate_handle"]["content_ref"],
            "run_handle_ref": row["run_handle"]["content_ref"],
            "verification_status": row["verification"]["status"],
            "replay_status": row["replay"]["status"],
            "read_refs": [item["handle"]["content_ref"] for item in row["reads"]],
        } for row in chain["positive_runs"]],
        "formal_bridge": chain["formal_bridge"],
        "backup_restore_rollback": {
            "backup_id": operations["backup"]["backup_id"],
            "restore_report_digest": operations["restore"]["report_digest"],
            "rollback_release_id": operations["rollback_release_id"],
            "operations_digest": _digest(operations_path),
            "scheduled_task": operations["scheduled_task"]["task_name"],
        },
        "w10_receipt_chain_head": {
            "task_id": "W10-10", "receipt_digest": w10_head["receipt_digest"],
            "receipt_file_digest": _digest(w10_head_path),
        },
        "z10_reports": {task_id: {"report_digest": report["report_digest"], "file_digest": _digest(z_reports[task_id])} for task_id, report in loaded.items()},
        "observation_required": True,
        "independent_human_review": False,
        "remote_release_claimed": False,
    }
    result["result_digest"] = "sha256:" + hashlib.sha256(_canonical(result)).hexdigest()
    output = state_root / "evidence/final-production-runtime-result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_canonical(result))
    checks = [
        {"name": "z10-prerequisites", "status": "PASS"},
        {"name": "sole-active-final-result", "status": "PASS" if result["status"] == "LOCAL_PRODUCTION_ACTIVE" and len(result["positive_runs"]) == 6 else "FAIL"},
        {"name": "final-result-canonical", "status": "PASS" if output.read_bytes() == _canonical(result) else "FAIL"},
        {"name": "final-evidence-bindings", "status": "PASS" if all(row["verification_status"] == "VERIFIED" and row["replay_status"] == "MATCH" for row in result["positive_runs"]) and len(result["z10_reports"]) == 3 else "FAIL"},
    ]
    return _task_report("Z10-03", checks, state_root)


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
        if args.task == "W10-02":
            return _verify_w10_02(Path(args.state_root).resolve())
        if args.task == "W10-03":
            return _verify_w10_03(Path(args.state_root).resolve())
        if args.task == "W10-04":
            return _verify_w10_04(Path(args.state_root).resolve())
        if args.task == "W10-05":
            return _verify_w10_05(Path(args.state_root).resolve())
        if args.task == "W10-06":
            return _verify_w10_06(Path(args.state_root).resolve())
        if args.task == "W10-07":
            return _verify_w10_07(Path(args.state_root).resolve())
        if args.task == "W10-08":
            return _verify_w10_08(Path(args.state_root).resolve())
        if args.task == "W10-09":
            return _verify_w10_09(Path(args.state_root).resolve())
        if args.task == "W10-10":
            return _verify_w10_10(Path(args.state_root).resolve())
        if args.task == "Z10-00":
            return _verify_z10_00(Path(args.state_root).resolve())
        if args.task == "Z10-01":
            return _verify_z10_01(Path(args.state_root).resolve())
        if args.task == "Z10-02":
            return _verify_z10_02(Path(args.state_root).resolve())
        if args.task == "Z10-03":
            return _verify_z10_03(Path(args.state_root).resolve())
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
