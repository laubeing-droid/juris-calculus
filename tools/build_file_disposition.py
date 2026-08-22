#!/usr/bin/env python3
"""Generate remediation/v4/file-disposition.json (施工方案 §7 B01).

Sources:
- 审计报告 20260819_..._审计.md 附录 A (292 path<TAB>primary-role lines)
- 施工方案 §19.1 原 90 个 compiler_core/*.py 五组处置
- 施工方案 §19.2 其他目录处置
- 施工方案 §0.14 configs/zh_CN/rules.yaml frozen fingerprint
- 施工方案 §0.14 + §7 B01 configs/packs/cn-legacy-corpus/manifest.yaml

Output schema: jc/remediation-v4-file-disposition/1.0
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "20260819_juris-calculus_V4单主链生产投产全量代码审计.md"
OUT = ROOT / "remediation" / "v4" / "file-disposition.json"


# 施工方案 §19.1 - 原 90 个 compiler_core/*.py 五组
CORE_GROUPS: dict[str, list[str]] = {
    "KEEP_REWRITE": [
        "__init__", "application", "audit", "audit_bundle",
        "canonical_serialization", "cli", "client", "contracts",
        "rendering", "resources", "rule_packs", "version",
    ],
    "MERGE_DELETE": [
        "argumentation", "argumentation_v2", "backend_router_v1",
        "certificate_v1", "evaluator", "fact_admission_v1",
        "independent_grounded_checker", "legal_spec_ivl",
        "source_service_v2",
    ],
    # MIGRATE_INVARIANTS_THEN_DELETE - 29 paths
    "MIGRATE_INVARIANTS_THEN_DELETE": [
        "admission", "certificate_checker", "completion_status",
        "config_paths", "constraint_validator", "contracts_v4",
        "defeasible_priority", "domain_config", "evidence_chain_validator",
        "fact_trust_envelope", "g8_evaluator_patch", "horn_completeness",
        "jcs", "legal_ir_v3", "litigation_engineering", "output_firewall",
        "proof_trace", "reasoning_boundary", "rule_governance",
        "rule_router", "source_anchor", "source_manifest",
        "stratified_evaluator", "taint", "transformer", "trust_labels",
        "type_checker", "types", "validity_state_machine",
    ],
    # NONPRODUCTION_SOURCE - 38 paths. 施工方案 §19.1 calls these
    # legacy/candidate/advisory; treat as CANDIDATE_ASSET/EXPERIMENT
    "CANDIDATE_ASSET": [
        "adapter_base", "adjudication_draft", "analysis",
        "arbitration_reasoning", "banach_verifier", "breakthrough_candidates",
        "breakthrough_verification", "burden_of_proof", "classifier",
        "compliance_monitoring", "conflict_of_laws", "criminal_complexity",
        "criminal_sentencing", "cross_jurisdiction_compare",
        "cross_jurisdiction_router", "evidence_checklist", "evidence_evaluation",
        "grounded_smt_verifier", "incremental_grounded", "invariance_metrics",
        "ip_valuation", "kg_recall", "legal_memory", "legal_reasoning",
        "plugin_registry", "prc_collision_engine", "proof_trace_visualizer",
        "proof_tree", "result_diff", "result_exporter", "review_packet",
        "rule_lookup", "rule_platform_cn", "smt_sidecar",
        "spec_shadow_harness", "step_verifier", "training",
        "universal_grounded_smt",
    ],
    "DELETE_CURRENT": [
        "compat_v3_v4", "proleg_translator",
    ],
}


# 施工方案 §19.2 - 其他目录处置
OTHER_DIRECTORIES: dict[str, dict[str, str]] = {
    "addons/workbuddy_mcp.py": {"disposition": "MERGE_DELETE", "terminal_state": "MIGRATED_GREEN"},
    "addons/cn": {"disposition": "MOVE_IN_REPO_EXPERIMENT", "terminal_state": "CANDIDATE_ASSET"},
    "addons/hk": {"disposition": "MOVE_IN_REPO_EXPERIMENT", "terminal_state": "CANDIDATE_ASSET"},
    "addons/us": {"disposition": "MOVE_IN_REPO_EXPERIMENT", "terminal_state": "CANDIDATE_ASSET"},
    "addons/federation": {"disposition": "MOVE_IN_REPO_EXPERIMENT", "terminal_state": "CANDIDATE_ASSET"},
    "pipeline": {"disposition": "MOVE_IN_REPO_SOURCE_TOOL", "terminal_state": "CANDIDATE_ASSET"},
    "configs/packs/cn-official/build": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "HISTORY_ONLY"},
    "configs/packs/cn-official/release": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "HISTORY_ONLY"},
    "configs/packs/cn-official/staging": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "HISTORY_ONLY"},
    "configs/packs/cn-official/manifest.yaml": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "HISTORY_ONLY"},
    "configs/perf_patterns.yaml": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "schemas/jc-v3.schema.json": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "schemas/w1b": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "schemas/jc-v4.schema.json": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "mcp_manifest.json": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "mcp_server.py": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "pyproject.toml": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "tools/build_provenance.py": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "tools/supply_chain_gate.py": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "tools/wheel_gate.py": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "tools/build_rule_pack_manifests.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tools/perf_baseline.py": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "CANDIDATE_ASSET"},
    "tools/run_trirail_matrix.py": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "CANDIDATE_ASSET"},
    "tools/fast_path_interceptor.py": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "CANDIDATE_ASSET"},
    "tools/remediate_v4.py": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "tools/remediate_v4_verify.py": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "tools/remediation": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "requirements/core.lock": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "requirements/dev.lock": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "requirements/documents.lock": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "requirements/pipeline.lock": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "requirements/render.lock": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    ".github/workflows/ci.yml": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    ".github/workflows/auto-release.yml": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "remediation/v4": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "BUILD_ONLY"},
    "tests/run_benchmark_zh.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/stress_test_facts.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/unit/test_zh_rules.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/unit/test_adversarial.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/unit/test_trirail_collision.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/unit/test_trirail_runtime.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/unit/test_cli_subprocess.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_cli_evaluate_subprocess.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_cli_contract.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/unit/test_plugin_registry.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/unit/test_release_engineering.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/unit/test_rule_pack_manifest.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_rule_pack_manifest_builder.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
}


# CN legacy frozen fingerprints (施工方案 §0.14)
CN_FINGERPRINTS: dict[str, dict[str, Any]] = {
    "configs/zh_CN/rules.yaml": {
        "sha256": "032206c349154d77eeef771d2b40dcfb62e1f7724c420ba4c09e69aaf88e8a44",
        "bytes": 13620766,
        "unique_rule_ids": 21144,
        "git_blob_v3_0_2": "8f51fdfd1db3e343812e8f35a321418fa854f4f7",
        "git_blob_v3_0_2_commit": "aa0e038daf066bfc0baa4d27ee54adef12c3ae16",
    },
    "configs/packs/cn-legacy-corpus/manifest.yaml": {
        "sha256": "5613b20bc5e3f61655f087b827e946e58cb38e13ff985f4e01779dc4993f41f7",
        "git_blob_v3_0_2": "1b29b412ee97563381f5a9b32e8b8efb9f62e90c",
        "git_blob_v3_0_2_commit": "aa0e038daf066bfc0baa4d27ee54adef12c3ae16",
    },
    "configs/zh_CN/source_manifest.yaml": {
        "_note": "source manifest is candidate source, not CN legacy corpus",
    },
    "configs/zh_CN/ontology_map.yaml": {
        "_note": "ontology is candidate source, not CN legacy corpus",
    },
    "configs/zh_CN/domain_config.example.yaml": {
        "_note": "domain config example, not CN legacy corpus",
    },
}


# closure_task binding for known terminal branches
CLOSURE_TASK: dict[str, str] = {
    "HISTORY_BOUND": "W5-02C",
    "MIGRATED_GREEN": "W5-CUTOVER",
    "KEEP_REWRITE": "W5-CUTOVER",
    "MOVE_IN_REPO_SOURCE_TOOL": "W5-03",
    "MOVE_IN_REPO_EXPERIMENT": "W5-03",
    "CANDIDATE_ASSET": "W5-03",
    "RETAIN_NONPACKAGED": "W5-03",
    "DOC_UPDATE": "W6-08",
    "BUILD_ONLY": "Z02",
    "HISTORY_ONLY": "Z02",
    "TEST_ORACLE": "W5-01",
}

SPECIAL_CLOSURE_TASKS = {
    "configs/perf_patterns.yaml": "W5-02C",
    "tools/wheel_gate.py": "W6-01",
    "requirements/core.lock": "W6-03",
    "requirements/dev.lock": "W6-03",
    "requirements/documents.lock": "W6-03",
    "requirements/pipeline.lock": "W6-03",
    "requirements/render.lock": "W6-03",
    "compiler_core/contracts_v4.py": "W1-02",
    "tests/fixtures/v4_contract/object-state-matrix.json": "W1-02",
    "tests/contract/jcs_node_oracle.mjs": "W1-01",
    "tests/contract/test_v4_foundation_contract.py": "W4-06",
    "tests/fixtures/golden/jcs-vectors.json": "W1-01",
    "tests/fixtures/golden/jcs-v4-vectors.json": "W1-01",
    "tests/fixtures/golden/v4-foundation-contract.json": "W4-06",
    "tests/fixtures/golden/v4-resource-limit-probe.json": "W4-06",
}

MIGRATION_TARGETS = {
    "addons/workbuddy_mcp.py": ("compiler_core/mcp.py", "tests/unit/test_mcp_stdio_protocol.py"),
    "compiler_core/contracts_v4.py": ("compiler_core/contracts.py", "tests/contract/test_contracts.py"),
}


def _parse_appendix_a() -> list[tuple[str, str]]:
    audit = AUDIT.read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n((?:.+\n)+?)```", audit)
    app = blocks[1]
    entries: list[tuple[str, str]] = []
    for line in app.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            entries.append((parts[0], parts[1]))
    return entries


def _git_tracked() -> set[str]:
    cp = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return {line.strip().replace("\\", "/") for line in cp.stdout.splitlines() if line.strip()}


def _classify_core(stem: str) -> tuple[str, str]:
    """Return (disposition, terminal_state) for a compiler_core file stem."""
    for grp, stems in CORE_GROUPS.items():
        if stem in stems:
            return grp, grp
    return "CANDIDATE_ASSET", "CANDIDATE_ASSET"


def build_entry(path: str, audit_role: str) -> dict[str, Any]:
    rel = path.replace("\\", "/")
    # OTHER_DIRECTORIES overrides generic prefix matching
    if rel in OTHER_DIRECTORIES:
        disp = OTHER_DIRECTORIES[rel]["disposition"]
        terminal = OTHER_DIRECTORIES[rel]["terminal_state"]
    elif rel.startswith("compiler_core/") and rel.endswith(".py"):
        stem = rel[len("compiler_core/"):-len(".py")]
        disp, terminal = _classify_core(stem)
    elif rel in OTHER_DIRECTORIES:
        disp = OTHER_DIRECTORIES[rel]["disposition"]
        terminal = OTHER_DIRECTORIES[rel]["terminal_state"]
    elif rel.startswith("addons/cn") or rel.startswith("addons/hk") or rel.startswith("addons/us") or rel.startswith("addons/federation"):
        disp = "MOVE_IN_REPO_EXPERIMENT"
        terminal = "CANDIDATE_ASSET"
    elif rel.startswith("addons/"):
        disp = "MOVE_IN_REPO_EXPERIMENT"
        terminal = "CANDIDATE_ASSET"
    elif rel.startswith("pipeline/"):
        disp = "MOVE_IN_REPO_SOURCE_TOOL"
        terminal = "CANDIDATE_ASSET"
    elif rel.startswith("tests/run_benchmark_zh.py") or rel.startswith("tests/stress_test_facts.py"):
        disp = "DELETE_CURRENT"
        terminal = "HISTORY_BOUND"
    elif rel.startswith((
        "tests/contract/", "tests/property/", "tests/integration/",
        "tests/differential/", "tests/formal_e2e/", "tests/security/",
        "tests/storage_chaos/", "tests/windows_security/",
        "tests/mcp_protocol/", "tests/packaging/", "tests/dsh_formal/",
        "tests/fixtures/golden/", "tests/fixtures/keys/",
    )):
        disp = "TEST_ORACLE"
        terminal = "TEST_ORACLE"
    elif rel.startswith("tests/fixtures/v4_contract/"):
        disp = "TEST_ORACLE"
        terminal = "TEST_ORACLE"
    elif rel.startswith("tests/unit/") and rel.endswith(".py"):
        # default to RETAIN_NONPACKAGED unless already classified
        disp = "RETAIN_NONPACKAGED"
        terminal = "CANDIDATE_ASSET"
    elif rel.startswith("tests/"):
        disp = "RETAIN_NONPACKAGED"
        terminal = "CANDIDATE_ASSET"
    elif rel.startswith("docs/") or rel == "README.md" or rel == "HANDOFF.md" or rel == "AGENTS.md" or rel == "CHANGELOG.md" or rel == "memory.md" or rel == "CLAUDE.md":
        disp = "DOC_UPDATE"
        terminal = "DOC_UPDATE"
    elif rel.startswith("schemas/"):
        disp = "KEEP_REWRITE"
        terminal = "KEEP_REWRITE"
    elif rel.startswith("configs/zh_CN/rules.yaml"):
        disp = "DELETE_CURRENT"
        terminal = "HISTORY_BOUND"
    elif rel.startswith("configs/packs/cn-legacy-corpus/"):
        disp = "DELETE_CURRENT"
        terminal = "HISTORY_BOUND"
    elif rel.startswith("configs/packs/cn-official/"):
        disp = "RETAIN_NONPACKAGED"
        terminal = "HISTORY_ONLY"
    elif rel.startswith("configs/") and rel.endswith(".yaml"):
        disp = "RETAIN_NONPACKAGED"
        terminal = "CANDIDATE_ASSET"
    elif rel.startswith(".github/"):
        disp = "KEEP_REWRITE"
        terminal = "KEEP_REWRITE"
    elif rel.startswith("requirements/"):
        disp = "KEEP_REWRITE"
        terminal = "KEEP_REWRITE"
    elif rel.startswith("tools/"):
        disp = "KEEP_REWRITE"
        terminal = "KEEP_REWRITE"
    elif rel == "pyproject.toml":
        disp = "KEEP_REWRITE"
        terminal = "KEEP_REWRITE"
    elif rel == "mcp_manifest.json" or rel == "mcp_server.py":
        disp = "KEEP_REWRITE"
        terminal = "KEEP_REWRITE"
    elif rel.startswith("remediation/v4/"):
        disp = "RETAIN_NONPACKAGED"
        terminal = "BUILD_ONLY"
    elif rel == "LICENSE":
        disp = "RETAIN_NONPACKAGED"
        terminal = "DOC_UPDATE"
    else:
        disp = "RETAIN_NONPACKAGED"
        terminal = "CANDIDATE_ASSET"

    entry: dict[str, Any] = {
        "path": rel,
        "disposition": disp,
        "terminal_state": terminal,
        "audit_role": audit_role,
        "closure_task": SPECIAL_CLOSURE_TASKS.get(rel, CLOSURE_TASK.get(terminal, "W5-CUTOVER")),
    }
    if rel in CN_FINGERPRINTS:
        entry["frozen_fingerprint"] = CN_FINGERPRINTS[rel]
    if terminal == "HISTORY_BOUND":
        entry["history_locator_only"] = True
        # paths without CN frozen fingerprint still need at least a Git locator
        if "frozen_fingerprint" not in entry or "sha256" not in entry.get("frozen_fingerprint", {}):
            try:
                blob = subprocess.run(
                    ["git", "rev-parse", f"HEAD:{rel}"],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip()
                if blob:
                    fp = entry.setdefault("frozen_fingerprint", {})
                    fp.setdefault("git_blob_head", blob)
                    fp.setdefault("note", "current HEAD blob locator only; not pre-frozen")
            except Exception:
                pass
    if terminal == "MIGRATED_GREEN":
        target = MIGRATION_TARGETS.get(rel)
        if target is None:
            raise ValueError(f"MIGRATED_GREEN path lacks a real migration target: {rel}")
        entry["target_module"], entry["target_test"] = target
    if rel == "compiler_core/contracts_v4.py":
        entry["target_module"], entry["target_test"] = MIGRATION_TARGETS[rel]
    if terminal == "MOVE_IN_REPO_SOURCE_TOOL":
        entry["namespace"] = "source_tool"
    if terminal == "MOVE_IN_REPO_EXPERIMENT":
        entry["namespace"] = "experiment"
    if terminal == "CANDIDATE_ASSET":
        entry["namespace"] = "candidate_asset"
    if terminal == "RETAIN_NONPACKAGED":
        entry["namespace"] = "non_production"
    if terminal == "KEEP_REWRITE":
        entry["namespace"] = "formal_core"
    if terminal == "DOC_UPDATE":
        entry["namespace"] = "docs"
    if terminal in {"HISTORY_BOUND"}:
        entry["target_module"] = None
        entry["target_artifact"] = None
    return entry


def main() -> int:
    audit_entries = _parse_appendix_a()
    tracked = _git_tracked()
    paths = sorted(tracked)
    entries: list[dict[str, Any]] = []
    audit_role_map = dict(audit_entries)
    for path in paths:
        rel = path.replace("\\", "/")
        audit_role = audit_role_map.get(rel, "new_after_audit")
        entries.append(build_entry(rel, audit_role))
    payload = {
        "schema_version": "jc/remediation-v4-file-disposition/1.0",
        "baseline_commit": "dfdfab110a7ba34bbb94def6e52945602ab0b0ec",
        "audit_baseline_sha256": "9b38e52c0181dbace4758d8c681009a61427baa53b1af2dae9e9c5d20f5e31a3",
        "plan_sha256": "41ffbd0245faac0d7bd01161adc80018d3ff24f75ecdd91a25bd20f3e329812d",
        "count": len(entries),
        "paths": entries,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"file-disposition: {len(entries)} entries written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
