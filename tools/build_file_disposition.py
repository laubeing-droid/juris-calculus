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
        "__init__", "application", "artifact_store", "audit", "audit_bundle", "backend_router",
        "canonical_serialization", "certificates", "cli", "client", "contracts",
        "argumentation", "fact_admission", "independent_checker", "legal_ir", "mcp", "rendering", "resources", "rule_packs",
        "source_service", "storage", "trust", "version",
    ],
    "MERGE_DELETE": [
        "argumentation_v2", "backend_router_v1",
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
    "MOVE_IN_REPO_SOURCE_TOOL": [
        "analysis", "rule_lookup", "training",
    ],
    # NONPRODUCTION_SOURCE - 38 paths. 施工方案 §19.1 calls these
    # legacy/candidate/advisory; treat as CANDIDATE_ASSET/EXPERIMENT
    "CANDIDATE_ASSET": [
        "adapter_base", "adjudication_draft",
        "arbitration_reasoning", "banach_verifier", "breakthrough_candidates",
        "breakthrough_verification", "burden_of_proof", "classifier",
        "compliance_monitoring", "conflict_of_laws", "criminal_complexity",
        "criminal_sentencing", "cross_jurisdiction_compare",
        "cross_jurisdiction_router", "evidence_checklist", "evidence_evaluation",
        "grounded_smt_verifier", "incremental_grounded", "invariance_metrics",
        "ip_valuation", "kg_recall", "legal_memory", "legal_reasoning",
        "plugin_registry", "prc_collision_engine", "proof_trace_visualizer",
        "proof_tree", "result_diff", "result_exporter", "review_packet",
        "rule_platform_cn", "smt_sidecar",
        "spec_shadow_harness", "step_verifier",
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
    "compiler_core/backends/__init__.py": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
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
    "tools/build_rule_pack_manifests.py": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "tools/build_synthetic_pack.py": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "TEST_ORACLE"},
    "tests/integration/test_trust_chain.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/security/test_trust_chain_attacks.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tools/perf_baseline.py": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "CANDIDATE_ASSET"},
    "tools/run_trirail_matrix.py": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "CANDIDATE_ASSET"},
    "tools/fast_path_interceptor.py": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "CANDIDATE_ASSET"},
    "tools/remediate_v4.py": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "tools/remediate_v4_verify.py": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "tools/remediation": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "requirements/build.lock": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "requirements/core.lock": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "requirements/release.lock": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "requirements/source-tool.lock": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "requirements/test.lock": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    ".github/workflows/ci.yml": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    ".github/workflows/auto-release.yml": {"disposition": "KEEP_REWRITE", "terminal_state": "KEEP_REWRITE"},
    "remediation/v4": {"disposition": "RETAIN_NONPACKAGED", "terminal_state": "BUILD_ONLY"},
    "tests/run_benchmark_zh.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/stress_test_facts.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/unit/test_zh_rules.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_adversarial.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_trirail_collision.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_trirail_runtime.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_cli_subprocess.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_cli_evaluate_subprocess.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_cli_contract.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_plugin_registry.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_release_engineering.py": {"disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND"},
    "tests/unit/test_rule_pack_manifest.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_rule_pack_manifest_builder.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
    "tests/unit/test_remediation_legacy_cn_corpus.py": {"disposition": "TEST_ORACLE", "terminal_state": "TEST_ORACLE"},
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


RETIRED_HISTORY_PATHS: dict[str, dict[str, Any]] = {
    "configs/zh_CN/rules.yaml": {},
    "configs/packs/cn-legacy-corpus/manifest.yaml": {},
    "docs/guides/MIGRATION_V2_TO_V3.md": {
        "git_blob_head": "66070f1b28f5658e0e380dbff480556b624b110a",
        "sha256": "ae6fe1d6dde9e5fd197e607e1255954628b3c5746a8901a572f06b5f9a62180d",
        "bytes": 1096,
        "note": "retired at W5-07; Git history locator and frozen digest only",
    },
    "docs/guides/WORKBUDDY.md": {
        "git_blob_head": "028df6c25bc8a8896f02d2c49a19b0255cac64f5",
        "sha256": "0d85a042c4702f485c180761bb830c420eb0c44c4631ded34ad440d39d792c67",
        "bytes": 1236,
        "note": "retired at W5-07; Git history locator and frozen digest only",
    },
    "pipeline/fix_single_premise.py": {
        "git_blob_head": "5f0109ebbb0785f8a062ec78990e8132b3238f74",
        "note": "retired current-tree mutator; Git history locator only",
    },
    "tests/run_benchmark_zh.py": {
        "git_blob_head": "92eb07be371db5fd753fe646244a76712247c974",
        "note": "retired current-tree benchmark; Git history locator only",
    },
    "tests/stress_test_facts.py": {
        "git_blob_head": "34cf9823073e25938f0b4e92ecf9a38839b3c2155",
        "note": "retired current-tree stress script; Git history locator only",
    },
}

W6_03_RETIRED_LOCKS: dict[str, dict[str, Any]] = {
    "requirements/dev.lock": {
        "disposition": "MERGE_DELETE", "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "0313594d7d21b1dc0d44db1bd9bb6504f8143fa4",
        "sha256": "ffacd6f2d832926b2af12fbd911b5857f9e86003db23a191030c68bc9fe1f4d3",
        "bytes": 104,
        "targets": ["requirements/build.lock", "requirements/test.lock", "requirements/release.lock"],
    },
    "requirements/documents.lock": {
        "disposition": "MERGE_DELETE", "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "0f5608400f4984011a6bbd4bf93654d3cb4ed37b",
        "sha256": "96ebfc87f26d987f8608ece069f034d60f0d786dbf6c8947c0d8db47d48a326e",
        "bytes": 40, "targets": ["requirements/source-tool.lock"],
    },
    "requirements/pipeline.lock": {
        "disposition": "MERGE_DELETE", "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "4b5fe4d67d6aa95e64f4be521ec189e7bac77ff3",
        "sha256": "f806f7e2f1a0eac9d9346baf64284535dce1c6dbdec3f3c47519752e26beda54",
        "bytes": 18, "targets": ["requirements/source-tool.lock"],
    },
    "requirements/render.lock": {
        "disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND",
        "git_blob_head": "f7c9608a79bd0f7f35f2649e73e1bff9658af05b",
        "sha256": "77aeb2dd7399fefb991f8ac568cfa12b8c69fd2237fa63a8c318186295f46c75",
        "bytes": 15, "targets": [],
    },
}


W6_05_RETIRED_PATHS: dict[str, dict[str, Any]] = {
    "tests/unit/test_release_engineering.py": {
        "disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND",
        "git_blob_head": "da706db39c6857e828661775ce5483c30ef10776",
        "sha256": "d1ec7f83c35aa1755ac150e040ce080f05565c4db524c95d6cc455fea790ce9b",
        "bytes": 3676,
    },
    "tests/unit/test_spec_shadow_harness.py": {
        "disposition": "DELETE_CURRENT", "terminal_state": "HISTORY_BOUND",
        "git_blob_head": "c27dcca942edfaba68ab691c20bcafdc85dcf345",
        "sha256": "b3e4e355cb3b1e905600470d6d792d2984fd469097e231c20525743794dfd93e",
        "bytes": 1824,
    },
}


W5_CUTOVER_RETIRED_PATHS: dict[str, dict[str, str]] = {
    "addons/workbuddy_mcp.py": {
        "disposition": "MERGE_DELETE",
        "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "630fa1285d77a8dc34d232ee5c396a53c364a440",
    },
    "compiler_core/argumentation_v2.py": {
        "disposition": "MERGE_DELETE",
        "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "dd70775fbc85ba9234ef0729bba90f083062965a",
    },
    "compiler_core/backend_router_v1.py": {
        "disposition": "MERGE_DELETE",
        "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "975b190026e02cc0be70ac7d5377c24a4117beeb",
    },
    "compiler_core/certificate_v1.py": {
        "disposition": "MERGE_DELETE",
        "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "4184f144346739e396c59b602b04ee9f6913b2d0",
    },
    "compiler_core/compat_v3_v4.py": {
        "disposition": "DELETE_CURRENT",
        "terminal_state": "HISTORY_BOUND",
        "git_blob_head": "b61f3e88251058b1fdc367ce0119409160211dda",
    },
    "compiler_core/contracts_v4.py": {
        "disposition": "MIGRATE_INVARIANTS_THEN_DELETE",
        "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "79e1d82627e51670ecb3aab877bdb783aaff420c",
    },
    "compiler_core/fact_admission_v1.py": {
        "disposition": "MERGE_DELETE",
        "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "49614956352489322753d693b5ef277705fd8603",
    },
    "compiler_core/legal_ir_v3.py": {
        "disposition": "MIGRATE_INVARIANTS_THEN_DELETE",
        "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "7e913bb7f9775bbfea8c194325fc44db65329119",
    },
    "compiler_core/proleg_translator.py": {
        "disposition": "DELETE_CURRENT",
        "terminal_state": "HISTORY_BOUND",
        "git_blob_head": "403c7046aedc52ccde03dc00a9f6e3225caed404",
    },
    "compiler_core/source_service_v2.py": {
        "disposition": "MERGE_DELETE",
        "terminal_state": "MIGRATED_GREEN",
        "git_blob_head": "a4e21ee2e049beac36fc5b8a2f88cd5066d55336",
    },
    "schemas/jc-v3.schema.json": {
        "disposition": "DELETE_CURRENT",
        "terminal_state": "HISTORY_BOUND",
        "git_blob_head": "8890718afad14634682ee3899e737bcf20a6fbf4",
    },
    "schemas/w1b/admission-result.schema.json": {
        "disposition": "DELETE_CURRENT",
        "terminal_state": "HISTORY_BOUND",
        "git_blob_head": "83b45154f575610669d0f48e7da54aa2bb662aae",
    },
    "schemas/w1b/case-request.schema.json": {
        "disposition": "DELETE_CURRENT",
        "terminal_state": "HISTORY_BOUND",
        "git_blob_head": "e5459aff6c1ec828fb6457623f1e8773e16ee9bc",
    },
    "schemas/w1b/proof-bundle-ref.schema.json": {
        "disposition": "DELETE_CURRENT",
        "terminal_state": "HISTORY_BOUND",
        "git_blob_head": "ce12dfd36b40b258824c0112875d8dcc8edaaaf8",
    },
    "schemas/w1b/rule-admission-request.schema.json": {
        "disposition": "DELETE_CURRENT",
        "terminal_state": "HISTORY_BOUND",
        "git_blob_head": "4e9888871854a965170caec474119f67ef60d32a",
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
    ".github/CODEOWNERS": "W6-08",
    ".github/workflows/auto-release.yml": "W6-08",
    ".github/workflows/ci.yml": "W6-08",
    "20260819_juris-calculus_V4单主链生产投产全自动整治施工方案.md": "W6-08",
    "AGENTS.md": "W6-08",
    "CHANGELOG.md": "W6-08",
    "HANDOFF.md": "W6-08",
    "README.md": "W6-08",
    "SECURITY.md": "W6-08",
    "compiler_core/cli.py": "W5-06",
    "compiler_core/audit.py": "W5-05",
    "compiler_core/rule_packs.py": "W5-05",
    "docs/architecture/contract-authority-v4.md": "W5-05",
    "docs/architecture/module-authority.json": "W5-05",
    "docs/architecture/runtime-path-inventory.md": "W5-05",
    "docs/README.md": "W6-08",
    "docs/guides/MIGRATION_V2_TO_V3.md": "W5-07",
    "docs/guides/README_CN.md": "W5-07",
    "docs/guides/WORKBUDDY.md": "W5-07",
    "docs/operations/V3_HISTORICAL_REPLAY.md": "W5-07",
    "docs/operations/RELEASE_V4.md": "W6-08",
    "memory.md": "W6-08",
    "pyproject.toml": "W6-03",
    "remediation/v4/file-disposition.json": "W6-08",
    "remediation/v4/tasks.json": "W6-08",
    "tests/contract/test_required_test_manifest.py": "W6-08",
    "tests/differential/test_pinned_companion_spec.py": "W6-05",
    "tests/differential/test_self_contained_v4.py": "W6-05",
    "tests/fixtures/companion_spec/NOTICE.md": "W6-05",
    "tests/fixtures/companion_spec/manifest.json": "W6-05",
    "tests/fixtures/companion_spec/oracle.json": "W6-05",
    "tests/formal_e2e/test_installed_production.py": "W6-05",
    "tests/formal_e2e/test_three_entrypoint_error_matrix.py": "W5-06",
    "tests/packaging/test_current_authority_docs.py": "W5-05",
    "tests/packaging/test_wheel_gate_v4.py": "W6-01",
    "tests/packaging/test_ci_matrix.py": "W6-08",
    "tests/packaging/test_current_docs.py": "W6-08",
    "tests/packaging/test_provenance.py": "W6-06",
    "tests/packaging/test_release_promotion.py": "W6-08",
    "tests/packaging/test_hash_locks.py": "W6-05",
    "tests/packaging/test_wheel_exact_set.py": "W6-05",
    "tests/required-v4-tests.json": "W6-08",
    "tests/unit/test_release_engineering.py": "W6-05",
    "tests/unit/test_spec_shadow_harness.py": "W6-05",
    "tools/build_file_disposition.py": "W6-08",
    "tools/build_provenance.py": "W6-06",
    "tools/remediate_v4.py": "W6-08",
    "configs/perf_patterns.yaml": "W5-02C",
    "tools/wheel_gate.py": "W6-05",
    "requirements/build.lock": "W6-03",
    "requirements/core.lock": "W6-03",
    "requirements/dev.lock": "W6-03",
    "requirements/documents.lock": "W6-03",
    "requirements/pipeline.lock": "W6-03",
    "requirements/release.lock": "W6-05",
    "requirements/render.lock": "W6-03",
    "requirements/source-tool.lock": "W6-03",
    "requirements/test.lock": "W6-03",
    "tools/supply_chain_gate.py": "W6-05",
    "addons/workbuddy_mcp.py": "W5-CUTOVER",
    "compiler_core/argumentation_v2.py": "W5-CUTOVER",
    "compiler_core/backend_router_v1.py": "W5-CUTOVER",
    "compiler_core/certificate_v1.py": "W5-CUTOVER",
    "compiler_core/compat_v3_v4.py": "W5-CUTOVER",
    "compiler_core/contracts_v4.py": "W5-CUTOVER",
    "compiler_core/fact_admission_v1.py": "W5-CUTOVER",
    "compiler_core/legal_ir_v3.py": "W5-CUTOVER",
    "compiler_core/proleg_translator.py": "W5-CUTOVER",
    "compiler_core/source_service_v2.py": "W5-CUTOVER",
    "schemas/jc-v3.schema.json": "W5-CUTOVER",
    "schemas/w1b/admission-result.schema.json": "W5-CUTOVER",
    "schemas/w1b/case-request.schema.json": "W5-CUTOVER",
    "schemas/w1b/proof-bundle-ref.schema.json": "W5-CUTOVER",
    "schemas/w1b/rule-admission-request.schema.json": "W5-CUTOVER",
    "tests/fixtures/v4_contract/object-state-matrix.json": "W1-02",
    "tests/contract/jcs_node_oracle.mjs": "W1-01",
    "tests/contract/test_v4_legacy_rejection.py": "W1-06",
    "tests/contract/test_v4_foundation_contract.py": "W4-06",
    "tests/contract/test_run_identity.py": "W4-01",
    "tests/contract/test_audit_bundle.py": "W4-03",
    "tests/security/test_audit_bundle_attacks.py": "W4-03",
    "tests/storage_chaos/test_audit_bundle_recovery.py": "W4-03",
    "compiler_core/audit_bundle.py": "W4-07",
    "compiler_core/certificates.py": "W4-04",
    "tests/contract/test_certificates.py": "W4-04",
    "tests/security/test_certificate_attacks.py": "W4-04",
    "compiler_core/application.py": "W4-07",
    "tests/contract/test_application.py": "W4-05",
    "tests/formal_e2e/test_single_chain.py": "W4-05",
    "tests/security/test_application_attacks.py": "W4-05",
    "tests/security/test_privacy_firewall.py": "W4-06",
    "tests/security/test_resource_limits.py": "W4-06",
    "tests/formal_e2e/test_positive_vertical_slice.py": "W4-07",
    "tests/formal_e2e/test_public_boundary_inputs.py": "W4-07",
    "tests/security/test_vertical_slice_attacks.py": "W4-07",
    "tests/storage_chaos/test_vertical_slice_recovery.py": "W4-07",
    "tests/contract/w5_package_red.py": "W5-01",
    "tests/formal_e2e/w5_entrypoint_red.py": "W5-01",
    "tests/mcp_protocol/w5_transport_red.py": "W5-01",
    "tests/unit/test_adversarial.py": "W5-02C",
    "tests/unit/test_cli_contract.py": "W5-02C",
    "tests/unit/test_plugin_registry.py": "W5-02C",
    "tests/unit/test_rule_pack_manifest_builder.py": "W5-02C",
    "tests/unit/test_trirail_collision.py": "W5-02C",
    "tests/unit/test_trirail_runtime.py": "W5-02C",
    "tests/unit/test_zh_rules.py": "W5-02C",
    "tests/unit/test_remediation_legacy_cn_corpus.py": "W5-02C",
    "tests/packaging/test_legacy_cn_corpus_absent.py": "W5-02C",
    "tests/mcp_protocol/test_mcp_legacy_cn_corpus_absent.py": "W5-03",
    "tests/unit/test_advisory_governance.py": "W5-03",
    "tests/unit/test_mcp_manifest_dispatch.py": "W5-03",
    "tests/unit/test_mcp_stdio_protocol.py": "W5-03",
    "tests/unit/test_phase6_cli.py": "W5-03",
    "tests/unit/test_w5_03_nonproduction_boundaries.py": "W5-03",
    "tests/fixtures/golden/jcs-vectors.json": "W1-01",
    "tests/fixtures/golden/jcs-v4-vectors.json": "W1-01",
    "tests/fixtures/golden/v4-foundation-contract.json": "W4-06",
    "tests/fixtures/golden/v4-resource-limit-probe.json": "W4-06",
    "tests/fixtures/golden/v4-backend-provider-probe.json": "W3-03",
}

MIGRATION_TARGETS = {
    "addons/workbuddy_mcp.py": ("compiler_core/mcp.py", "tests/mcp_protocol/w5_transport_red.py"),
    "compiler_core/argumentation_v2.py": (
        "compiler_core/argumentation.py", "tests/contract/test_argumentation.py",
    ),
    "compiler_core/backend_router_v1.py": (
        "compiler_core/backend_router.py", "tests/contract/test_backend_router.py",
    ),
    "compiler_core/independent_grounded_checker.py": (
        "compiler_core/independent_checker.py", "tests/contract/test_independent_checker.py",
    ),
    "compiler_core/contracts_v4.py": ("compiler_core/contracts.py", "tests/contract/test_contracts.py"),
    "compiler_core/certificate_v1.py": (
        "compiler_core/certificates.py", "tests/contract/test_certificates.py",
    ),
    "compiler_core/fact_admission_v1.py": (
        "compiler_core/fact_admission.py", "tests/contract/test_fact_admission.py",
    ),
    "compiler_core/legal_ir_v3.py": (
        "compiler_core/legal_ir.py", "tests/contract/test_legal_ir.py",
    ),
    "compiler_core/source_service_v2.py": (
        "compiler_core/source_service.py", "tests/contract/test_source_service.py",
    ),
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
    if stem in {"argumentation_v2", "backend_router_v1", "independent_grounded_checker"}:
        return "MERGE_DELETE", "MIGRATED_GREEN"
    for grp, stems in CORE_GROUPS.items():
        if stem in stems:
            if grp == "MOVE_IN_REPO_SOURCE_TOOL":
                return grp, "CANDIDATE_ASSET"
            return grp, grp
    return "CANDIDATE_ASSET", "CANDIDATE_ASSET"


def build_entry(path: str, audit_role: str) -> dict[str, Any]:
    rel = path.replace("\\", "/")
    if rel == "compiler_core/mcp.py":
        audit_role = "CLI/Client/MCP"
    # OTHER_DIRECTORIES overrides generic prefix matching
    if rel in W6_05_RETIRED_PATHS:
        disp = W6_05_RETIRED_PATHS[rel]["disposition"]
        terminal = W6_05_RETIRED_PATHS[rel]["terminal_state"]
    elif rel in W5_CUTOVER_RETIRED_PATHS:
        disp = W5_CUTOVER_RETIRED_PATHS[rel]["disposition"]
        terminal = W5_CUTOVER_RETIRED_PATHS[rel]["terminal_state"]
    elif rel in W6_03_RETIRED_LOCKS:
        disp = W6_03_RETIRED_LOCKS[rel]["disposition"]
        terminal = W6_03_RETIRED_LOCKS[rel]["terminal_state"]
    elif rel in RETIRED_HISTORY_PATHS:
        disp = "DELETE_CURRENT"
        terminal = "HISTORY_BOUND"
    elif rel in OTHER_DIRECTORIES:
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
        "tests/contract/", "tests/property/", "tests/semantic_mutation/",
        "tests/integration/",
        "tests/differential/", "tests/formal_e2e/", "tests/security/",
        "tests/storage_chaos/", "tests/windows_security/",
        "tests/mcp_protocol/", "tests/packaging/", "tests/dsh_formal/",
        "tests/fixtures/companion_spec/", "tests/fixtures/golden/",
        "tests/fixtures/keys/", "tests/fixtures/packs/",
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
    elif rel.startswith("docs/") or rel in {
        "README.md", "HANDOFF.md", "AGENTS.md", "CHANGELOG.md", "SECURITY.md",
        "memory.md", "CLAUDE.md",
        "20260819_juris-calculus_V4单主链生产投产全自动整治施工方案.md",
    }:
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
    if rel in W6_05_RETIRED_PATHS:
        retired = W6_05_RETIRED_PATHS[rel]
        entry["frozen_fingerprint"] = {
            key: retired[key] for key in ("git_blob_head", "sha256", "bytes")
        }
    elif rel in CN_FINGERPRINTS:
        entry["frozen_fingerprint"] = CN_FINGERPRINTS[rel]
    elif rel in W5_CUTOVER_RETIRED_PATHS:
        entry["frozen_fingerprint"] = {
            "git_blob_head": W5_CUTOVER_RETIRED_PATHS[rel]["git_blob_head"],
            "note": "retired at W5-CUTOVER; current HEAD blob locator only",
        }
    elif rel in W6_03_RETIRED_LOCKS:
        retired = W6_03_RETIRED_LOCKS[rel]
        entry["frozen_fingerprint"] = {
            key: retired[key] for key in ("git_blob_head", "sha256", "bytes")
        }
    elif rel in RETIRED_HISTORY_PATHS:
        entry["frozen_fingerprint"] = RETIRED_HISTORY_PATHS[rel]
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
        if rel in W6_03_RETIRED_LOCKS:
            targets = W6_03_RETIRED_LOCKS[rel]["targets"]
            entry["target_module"] = targets[0]
            entry["target_artifacts"] = targets
            entry["target_test"] = "tests/packaging/test_hash_locks.py"
        else:
            target = MIGRATION_TARGETS.get(rel)
            if target is None:
                raise ValueError(f"MIGRATED_GREEN path lacks a real migration target: {rel}")
            entry["target_module"], entry["target_test"] = target
    if rel == "compiler_core/contracts_v4.py":
        entry["target_module"], entry["target_test"] = MIGRATION_TARGETS[rel]
    if disp == "MOVE_IN_REPO_SOURCE_TOOL":
        entry["namespace"] = "source_tool"
    elif disp == "MOVE_IN_REPO_EXPERIMENT":
        entry["namespace"] = "experiment"
    elif terminal == "CANDIDATE_ASSET":
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


def build_document() -> dict[str, Any]:
    """Build the complete tracked-path disposition from declared sources."""

    audit_entries = _parse_appendix_a()
    tracked = _git_tracked()
    paths = sorted(
        tracked | set(RETIRED_HISTORY_PATHS) | set(W5_CUTOVER_RETIRED_PATHS)
        | set(W6_03_RETIRED_LOCKS) | set(W6_05_RETIRED_PATHS)
    )
    entries: list[dict[str, Any]] = []
    audit_role_map = dict(audit_entries)
    for path in paths:
        rel = path.replace("\\", "/")
        audit_role = audit_role_map.get(rel, "new_after_audit")
        entries.append(build_entry(rel, audit_role))
    return {
        "schema_version": "jc/remediation-v4-file-disposition/1.0",
        "baseline_commit": "dfdfab110a7ba34bbb94def6e52945602ab0b0ec",
        "audit_baseline_sha256": "9b38e52c0181dbace4758d8c681009a61427baa53b1af2dae9e9c5d20f5e31a3",
        "plan_sha256": "138b18236acc77bdfb80870e944407e9854da60c157e4a539f0458e3ff07014e",
        "count": len(entries),
        "paths": entries,
    }


def main() -> int:
    payload = build_document()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"file-disposition: {payload['count']} entries written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
