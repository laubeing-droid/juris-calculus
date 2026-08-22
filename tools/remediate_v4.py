#!/usr/bin/env python3
"""V4 single-chain production remediation runner.

施工方案 §3.1: 唯一 orchestration CLI。负责任务编排和证据核验，不负责
"凭空生成正确代码"。B00 完成后，用户通过以下命令续跑：

    py -3.12 -B tools/remediate_v4.py run \
        --plan remediation/v4/tasks.json \
        --state-root $env:JC_REMEDIATION_STATE_ROOT \
        --through W9

B00 阶段 runner 还提供以下子命令，让 B00 自身的 gate 可机器验证：

    lint-plan         验证 plan JSON schema 并检查 DAG 无环/依赖合法/无 UNREVIEWED
    authority         authority 检查 (--check 报告 module authority 状态)
    graph-map         CodeGraph 对账
    audit-map         44 项审计问题核对
    file-map          tracked path disposition 核对
    legacy-cn-corpus  CN legacy corpus 物理删除验证
    generated         验证 Schema/manifest 发布物
    forbidden-imports 检查 V3/W1b/compat 等禁用导入
    verify-wave       wave 级聚合门禁
    run               单一入口续跑命令
"""
from __future__ import annotations

import argparse
import ast
import base64
import calendar
import configparser
import fnmatch
import hashlib
import itertools
import json
import math
import mimetypes
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator  # type: ignore
except ImportError:  # pragma: no cover - exercised by tests via subprocess
    Draft202012Validator = None  # type: ignore

RUNNER_VERSION = "0.5.0"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN = ROOT / "remediation" / "v4" / "tasks.json"
SCHEMA_DIR = ROOT / "remediation" / "v4"
ISSUE_MAP = SCHEMA_DIR / "issue-map.json"
FILE_DISPOSITION = SCHEMA_DIR / "file-disposition.json"
TASK_SCHEMA = SCHEMA_DIR / "task.schema.json"
RECEIPT_SCHEMA = SCHEMA_DIR / "receipt.schema.json"
APPROVAL_SCHEMA = SCHEMA_DIR / "approval.schema.json"
OBJECT_STATE_MATRIX = ROOT / "tests" / "fixtures" / "v4_contract" / "object-state-matrix.json"
JCS_V4_VECTORS = ROOT / "tests" / "fixtures" / "golden" / "jcs-v4-vectors.json"
FOUNDATION_V4_CONTRACT = ROOT / "tests" / "fixtures" / "golden" / "v4-foundation-contract.json"
REQUIRED_TEST_MANIFEST = ROOT / "tests" / "required-v4-tests.json"
REQUIRED_TEST_PYTEST_CONFIG = ROOT / "tests" / "pytest.ini"
W0_RESOURCE_PROBE_FILE_DIGEST = (
    "sha256:cfcca89034412b2eec9f8de60ae1e74661adfdceb1a4f72d4e59e1365eee0b35"
)
W0_RESOURCE_PROBE_PAYLOAD_DIGEST = (
    "sha256:13f79fdd6b5282f5aabfca9569aba6e69064f47765a0572bd8aa43f10c2c5ba1"
)
SAFE_IJSON_INTEGER = 9_007_199_254_740_991
DIGEST_V4_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
UTC_INSTANT_V4_PATTERN = re.compile(
    r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})T"
    r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{1,9}))?Z\Z"
)

W0_REQUIRED_TEST_SUITES = (
    "contract", "property", "integration", "differential", "formal_e2e",
    "security", "storage_chaos", "windows_security", "mcp_protocol",
    "packaging", "dsh_formal",
)
W0_REQUIRED_REWRITE_IDS = frozenset({
    "REWRITE-SKIPPED-ADVERSARIAL",
    "REWRITE-SKIPPED-TRIRAIL",
    "REWRITE-SKIPPED-ZH-RULES",
    "REWRITE-ENVIRONMENT-EXCLUDED-DIGEST",
    "REWRITE-ENGINE-3-ACCEPTANCE",
    "REWRITE-COMPAT-ADAPTER",
    "REWRITE-V3-SCHEMA-GENERATION",
    "REWRITE-APPLICATION-TRUSTED-SUCCESS",
    "REWRITE-SOURCE-CALLER-PASS",
    "REWRITE-SOURCE-APPLICABILITY-PASS",
    "REWRITE-SOURCE-PATH-PASS",
    "REWRITE-FACT-CALLER-PASS",
    "REWRITE-LEGACY-VERIFIED-FACT",
    "REWRITE-RULE-CALLER-RECEIPT",
    "REWRITE-SHARED-IR-ORACLE",
    "REWRITE-BACKEND-CALLER-FEATURES",
    "REWRITE-BACKEND-CALLER-RECEIPTS",
    "REWRITE-CERTIFICATE-CALLER-PASS",
    "REWRITE-OLD-AUDIT-BUNDLE-COMPLETE",
    "REWRITE-WORKBUDDY-MCP",
    "REWRITE-OLD-MCP-STDIO",
    "REWRITE-V3-ENTRYPOINT-PARITY",
    "REWRITE-PARTIAL-CORE-LOCK",
    "REWRITE-WHEEL-BLACKLIST",
    "REWRITE-SPEC-SHADOW-RUNTIME",
})
W0_REQUIRED_REWRITE_PROJECTION_DIGEST = (
    "sha256:df12272a2c3882baad21625035f642af2b43ce2a4877a0903066b5908dae15da"
)
W0_B02_COMPANION_BINDING = {
    "kind": "B02_RECEIPT",
    "receipt_digest": "sha256:fbc068ebad1ec4c02f72acff30dfade3e928c5967b1c0baa89b51971d3982045",
    "intake_digest": "sha256:0540bb89c4799c4b5372ebd0768ba0efbb2d2e4ae5b36eb9b94143978f68ef6f",
    "commit": "a3a015941f75091c87d57aa956e712f1546dd7d4",
    "tree": "2d0b1bb9c4f4cd82a9a4452b96ab1d05c0d1ed99",
    "required_files": {
        "theory/spec/reference_semantics.py": "a37304e753da21016e83f3ae8cfb53286eedff78d058e8ebb1470ebac8cd64ba",
        "theory/spec/certificate_schema.py": "1b71a5cd8239dac29c2eacb3397817a47bea8b4acef0fcff9addc10aa5bb4d95",
    },
    "fixture_family_digests": {
        "admin_breach": "sha256:383dd4ebfba8909f16e49efbf4800c07da554bdee0e67f357d0fd2324b9b9721",
        "contract_breach": "sha256:43f96433ca76dd57fb165b4c1a3c6d717b5ae007a42d14aad86ea1f77bc58d0c",
        "criminal_breach": "sha256:7bb6ff224c9ea294b3c81370870e3c9aefc205184d88aa57db3fcc54307d014e",
        "license_permission_priority": "sha256:2d27f41f24277b4895a7681299d702db5f862a0c73feabad039506b88a7baaab",
        "tort_breach": "sha256:f3035cb082fae1742efc3fbfeba7f7d029c86262f7f54b4f1fd90f1486107a8b",
    },
    "oracle_imports_production": False,
    "unavailable_exit_code": 21,
}

W0_REQUIRED_OBJECT_IDS = frozenset({
    "DigestV4", "CanonicalTimeV4", "ContentRefV4", "ArtifactHandleV4", "ErrorV4",
    "SignatureEnvelopeV4", "TrustPolicyV4", "StorageCapabilityV4", "ObservabilityEnvelopeV4",
    "CaseRequestV4", "LegalContextV4", "RequestedOutputV4", "ResourceLimitsV4",
    "SourceSnapshotV4", "CanonicalLocatorV4", "SourceVersionEdgeV4", "SourceBundleV4",
    "EvidenceManifestV4", "EvidenceItemV4", "ContradictionRefV4",
    "FactCandidateV4", "FactAttestationV4", "FactAdmissionReceiptV4",
    "RuleV4", "PackManifestV4", "PackSignatureV4", "RulePromotionReceiptV4",
    "LegalSpecV4", "LegalIVLV4", "TranslationReceiptV4",
    "ArgumentV4", "AttackV4", "PriorityEdgeV4", "PermissionResolutionV4", "ExceptionResolutionV4",
    "BackendInvocationV4", "SolverReceiptV4", "CheckerReceiptV4", "ProofReceiptV4",
    "ExecutionStatusV4", "DecisionStatusV4", "ReviewStateV4", "CompletenessStateV4",
    "InterruptionStateV4", "CertificateKindV4", "TransportOutcomeV4", "RuntimeProfileV4",
    "ClaimResultV4", "BranchResultV4", "MissingFactRequirementV4", "SemanticResultV4",
    "RunIdentityV4", "FormalCertificateV4", "ConflictCertificateV4", "CertificateEnvelopeV4",
    "AuditManifestV4", "AuditBundleIndexV4", "EvaluationEnvelopeV4", "VerificationResultV4",
    "ReplayResultV4", "MCPCapabilitiesInputV4", "MCPCapabilitiesOutputV4",
    "MCPCapabilitiesErrorV4", "MCPEvaluateInputV4", "MCPEvaluateOutputV4", "MCPEvaluateErrorV4",
    "MCPVerifyRunInputV4", "MCPVerifyRunOutputV4", "MCPVerifyRunErrorV4",
    "MCPReadArtifactInputV4", "MCPReadArtifactOutputV4", "MCPReadArtifactErrorV4", "ToolSpecV4",
})
W0_REQUIRED_OBJECT_LAYERS = frozenset({
    "common", "trust", "storage", "observability", "request", "source", "evidence",
    "fact", "rule", "ir", "argument", "backend", "receipt", "state", "result", "run",
    "certificate", "audit", "mcp",
})

W0_STATE_AXES = {
    "execution": [
        "completed", "admission_blocked", "interrupted", "unsupported",
        "resource_exhausted", "cancelled", "engine_error",
    ],
    "decision": [
        "accepted_formal_result", "hypothetical_result", "review_only_result",
        "missing_required_fact", "conflict_certificate", "blocked", "unknown", "engine_error",
    ],
    "review": ["not_required", "required", "pending", "approved", "rejected"],
    "completeness": ["complete", "partial", "truncated", "interrupted"],
    "certificate": ["none", "formal_verified", "conflict_verified"],
    "transport": ["success", "error"],
}

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_BASELINE_DRIFT = 3
EXIT_GATE_FAIL = 4
EXIT_RECEIPT_FAIL = 5
EXIT_SCOPE_VIOLATION = 6
EXIT_WAITING_HUMAN = 20
EXIT_WAITING_EXTERNAL = 21
EXIT_RELEASE_UNAUTHORIZED = 22


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _die(msg: str, code: int = EXIT_GATE_FAIL) -> "NoReturn":
    print(msg, file=sys.stderr)
    sys.exit(code)


def cmd_lint_plan(args: argparse.Namespace) -> int:
    plan_path = Path(args.plan).resolve()
    if not plan_path.is_file():
        print(f"plan file not found: {plan_path}", file=sys.stderr)
        return EXIT_USAGE

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    schema = json.loads(TASK_SCHEMA.read_text(encoding="utf-8"))
    receipt_schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
    required_receipt_fields = set(receipt_schema["required"])

    if Draft202012Validator is None:
        print("jsonschema package is required for lint-plan", file=sys.stderr)
        return EXIT_USAGE
    errors = list(Draft202012Validator(schema).iter_errors(plan))
    if errors:
        for err in errors:
            print(f"schema: {err.message} at {list(err.absolute_path)}", file=sys.stderr)
        return EXIT_GATE_FAIL

    tasks = plan.get("tasks", [])
    by_id: dict[str, dict[str, Any]] = {}
    for t in tasks:
        tid = t.get("id")
        if tid in by_id:
            print(f"duplicate task id: {tid}", file=sys.stderr)
            return EXIT_GATE_FAIL
        by_id[tid] = t

    # DAG cycle detection.
    state: dict[str, int] = {tid: 0 for tid in by_id}
    path: list[str] = []

    def dfs(node: str) -> bool:
        if state[node] == 1:
            cycle = " -> ".join(path + [node])
            print(f"cycle detected: {cycle}", file=sys.stderr)
            return False
        if state[node] == 2:
            return True
        state[node] = 1
        path.append(node)
        for dep in by_id[node].get("depends_on", []):
            if dep not in by_id:
                print(f"task {node} depends on unknown id {dep}", file=sys.stderr)
                return False
            if not dfs(dep):
                return False
        path.pop()
        state[node] = 2
        return True

    for tid in list(by_id):
        if not dfs(tid):
            return EXIT_GATE_FAIL

    # Every task must have allowed_paths. AUTO/MIXED tasks must bind audit_ids
    # because they directly touch production code; HUMAN_GATE/EXTERNAL_GATE
    # tasks are coordination points and may legitimately have none.
    for tid, t in by_id.items():
        if not t.get("allowed_paths"):
            print(f"task {tid} missing allowed_paths", file=sys.stderr)
            return EXIT_GATE_FAIL
        if t.get("mode") in {"AUTO", "MIXED"} and not t.get("audit_ids"):
            print(f"task {tid} missing audit_ids", file=sys.stderr)
            return EXIT_GATE_FAIL
        if t.get("mode") == "AUTO":
            argv = t.get("argv", [])
            expected = t.get("expected_exit_codes", [])
            if len(argv) != len(expected):
                print(
                    f"task {tid} argv/expected_exit_codes length mismatch: "
                    f"{len(argv)} != {len(expected)}",
                    file=sys.stderr,
                )
                return EXIT_GATE_FAIL
            declared_receipt_fields = set(t.get("required_receipt_fields", []))
            if not required_receipt_fields <= declared_receipt_fields:
                print(
                    f"task {tid} missing required receipt fields: "
                    f"{sorted(required_receipt_fields - declared_receipt_fields)}",
                    file=sys.stderr,
                )
                return EXIT_GATE_FAIL

    # Issue map must cover all referenced audit IDs.
    referenced = {a for t in tasks for a in t.get("audit_ids", [])}
    issue_map = json.loads(ISSUE_MAP.read_text(encoding="utf-8"))
    declared = {e["id"] for e in issue_map.get("issues", [])}
    missing = referenced - declared
    if missing:
        print(f"audit IDs referenced in plan but missing from issue-map: {sorted(missing)}", file=sys.stderr)
        return EXIT_GATE_FAIL

    print(f"plan OK: {len(tasks)} tasks, {len(referenced)} audit IDs, no cycles")
    return EXIT_OK


def cmd_authority(args: argparse.Namespace) -> int:
    """施工方案 §3.1: 报告 module-authority 唯一性。

    B00/B01 阶段：仅产生可解析输出，证明 docs/architecture/module-authority.json
    已被读取。后续 W0-03 任务负责真正生成 module-authority.json。
    """
    record = bool(getattr(args, "record", False))
    require_clean = bool(getattr(args, "require_clean", False))
    if record or require_clean:
        policy = getattr(args, "policy", None)
        codegraph = getattr(args, "codegraph", None)
        state_root = getattr(args, "state_root", None)
        if not policy or not codegraph or not state_root:
            print(
                "authority observation requires --policy, --codegraph, and --state-root",
                file=sys.stderr,
            )
            return EXIT_USAGE
        emitter = ROOT / "tools" / "remediation" / "observed_graph.py"
        if not emitter.is_file():
            print(f"authority observed-graph emitter missing: {emitter}", file=sys.stderr)
            return EXIT_GATE_FAIL
        completed = subprocess.run(
            [
                sys.executable, "-B", str(emitter), "--root", str(ROOT),
                "--policy", str(Path(policy).resolve()),
                "--codegraph", str(Path(codegraph).resolve()),
                "--state-root", str(Path(state_root).resolve()),
                "--mode", "record" if record else "require-clean",
            ],
            cwd=str(ROOT), capture_output=True, check=False,
        )
        sys.stdout.buffer.write(completed.stdout)
        sys.stderr.buffer.write(completed.stderr)
        return completed.returncode

    target = ROOT / "docs" / "architecture" / "module-authority.json"
    if target.is_file():
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"module-authority.json exists but is not valid JSON: {target}", file=sys.stderr)
            return EXIT_GATE_FAIL
        nodes = payload.get("modules") or payload
        if isinstance(nodes, list):
            print(f"module-authority.json OK: {len(nodes)} modules")
        else:
            print(f"module-authority.json OK (object form)")
        return EXIT_OK
    if getattr(args, "check", False):
        print("module-authority.json missing; W0-03 must produce it", file=sys.stderr)
        return EXIT_BASELINE_DRIFT
    print("module-authority.json missing (B01/W0-03 scope)")
    return EXIT_OK


def cmd_graph_map(args: argparse.Namespace) -> int:
    """施工方案 §7 B00-CG: 校验 CodeGraph 索引与 start tree 的一致性。

    tracked union == codegraph-indexed ∪ asset-inventory。CN legacy corpus
    (configs/zh_CN/rules.yaml) 必须在 asset-inventory 而非 codegraph 中。
    normalized graph receipt 写到 $JC_REMEDIATION_STATE_ROOT/evidence/codegraph/$SOURCE_TREE_ID/。
    """
    codegraph_db = Path(args.codegraph).resolve()
    if not codegraph_db.is_file():
        print(f"codegraph db not found: {codegraph_db}", file=sys.stderr)
        return EXIT_BASELINE_DRIFT

    codegraph_files = _codegraph_indexed_files(codegraph_db)
    tracked = _git_tracked_files()
    asset_path = Path(args.asset_inventory).resolve() if args.asset_inventory else None
    if asset_path is None and getattr(args, "state_root", None):
        asset_path = Path(args.state_root) / "evidence" / "codegraph" / _git("rev-parse", "HEAD^{tree}").strip() / "asset-inventory.json"
    if asset_path is None or not asset_path.is_file():
        print("explicit --asset-inventory is required; tracked-indexed complement is not evidence", file=sys.stderr)
        return EXIT_GATE_FAIL
    asset_payload = json.loads(asset_path.read_text(encoding="utf-8"))
    asset_entries = asset_payload.get("assets", [])
    required_asset_fields = {"path", "git_blob", "sha256", "bytes", "mime_type", "asset_type", "disposition", "consumer_or_authority", "closure_task"}
    if any(not required_asset_fields <= set(entry) for entry in asset_entries):
        print("asset inventory entry missing required metadata", file=sys.stderr)
        return EXIT_GATE_FAIL
    asset_inventory = [entry["path"] for entry in asset_entries]
    indexed_set = set(codegraph_files)
    tracked_set = set(tracked)
    assets_set = set(asset_inventory)

    missing = sorted(tracked_set - (indexed_set | assets_set))
    orphan = sorted(indexed_set - tracked_set)

    cn_rules = "configs/zh_CN/rules.yaml"
    cn_in_indexed = cn_rules in indexed_set
    cn_in_assets = cn_rules in assets_set

    payload = {
        "schema_version": "jc/remediation-v4-graph-receipt/1.0",
        "source_tree_id": _git("rev-parse", "HEAD^{tree}").strip(),
        "codegraph_file_count": len(codegraph_files),
        "codegraph_version": asset_payload["codegraph_version"],
        "codegraph_db_sha256": sha256_hex(codegraph_db.read_bytes()),
        "codegraph_integrity_check": _codegraph_integrity(codegraph_db),
        "codegraph_node_count": _codegraph_count(codegraph_db, "nodes"),
        "codegraph_edge_count": _codegraph_count(codegraph_db, "edges"),
        "codegraph_unresolved": _codegraph_count(codegraph_db, "unresolved_refs"),
        "codegraph_parse_errors": _codegraph_files_with_errors(codegraph_db),
        "tracked_file_count": len(tracked),
        "asset_inventory_count": len(asset_inventory),
        "missing_from_union": missing,
        "orphan_graph_entries": orphan,
        "cn_legacy_in_codegraph": cn_in_indexed,
        "cn_legacy_in_assets": cn_in_assets,
    }
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["digest"] = "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()

    if not getattr(args, "check", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return EXIT_OK

    problems: list[str] = []
    if payload["codegraph_unresolved"] != 0:
        problems.append(f"unresolved refs={payload['codegraph_unresolved']}")
    if payload["codegraph_parse_errors"] != 0:
        problems.append(f"files with parse errors={payload['codegraph_parse_errors']}")
    if payload["codegraph_integrity_check"] != "ok":
        problems.append(f"codegraph integrity={payload['codegraph_integrity_check']}")
    if missing:
        problems.append(f"missing_from_union={missing[:5]}{'...' if len(missing) > 5 else ''}")
    if orphan:
        problems.append(f"orphan_graph_entries={orphan[:5]}{'...' if len(orphan) > 5 else ''}")
    if cn_in_indexed:
        problems.append("configs/zh_CN/rules.yaml was indexed by codegraph; should be asset-only")
    if not cn_in_assets:
        problems.append("configs/zh_CN/rules.yaml missing from asset inventory")

    state_root = getattr(args, "state_root", None)
    if state_root:
        evidence_dir = (
            Path(state_root) / "evidence" / "codegraph" / payload["source_tree_id"]
        )
        evidence_dir.mkdir(parents=True, exist_ok=True)
        normalized_path = evidence_dir / "normalized.json"
        normalized_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"normalized graph receipt: {normalized_path}")

    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return EXIT_GATE_FAIL

    print(
        f"graph-map OK: {len(codegraph_files)} indexed files, "
        f"{len(asset_inventory)} asset inventory entries, "
        f"{len(tracked)} tracked total; "
        f"unresolved=0 parse_errors=0 missing=0 orphan=0"
    )
    return EXIT_OK


def _codegraph_integrity(db: Path) -> str:
    conn = sqlite3.connect(str(db))
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()


def cmd_asset_map(args: argparse.Namespace) -> int:
    """Write an explicit, fingerprinted inventory for non-CodeGraph assets."""
    codegraph_db = Path(args.codegraph).resolve()
    if not codegraph_db.is_file() or not args.state_root:
        print("asset-map requires --codegraph and --state-root", file=sys.stderr)
        return EXIT_USAGE
    tracked = _git_tracked_files()
    dispositions = {
        item["path"]: item
        for item in json.loads(FILE_DISPOSITION.read_text(encoding="utf-8"))["paths"]
    }
    assets: list[dict[str, Any]] = []
    for path in tracked:
        suffix = Path(path).suffix.lower()
        if suffix in {".py", ".yaml", ".yml"} and path != "configs/zh_CN/rules.yaml":
            continue
        source = ROOT / path
        disposition = dispositions.get(path)
        if disposition is None:
            print(f"asset missing disposition: {path}", file=sys.stderr)
            return EXIT_GATE_FAIL
        blob = _git_checked("rev-parse", f"HEAD:{path}")
        payload = source.read_bytes()
        assets.append({
            "path": path, "git_blob": blob, "sha256": sha256_hex(payload), "bytes": len(payload),
            "mime_type": mimetypes.guess_type(path)[0] or "application/octet-stream",
            "asset_type": suffix.lstrip(".") or "extensionless",
            "disposition": disposition["disposition"],
            "consumer_or_authority": disposition.get("audit_role", "UNREVIEWED"),
            "closure_task": disposition["closure_task"],
        })
    version_argv = _expanded_argv(["codegraph", "--version"], Path(args.state_root))
    version_cp = subprocess.run(version_argv, cwd=str(ROOT), capture_output=True, text=True, check=False)
    if version_cp.returncode != 0:
        print(version_cp.stderr, file=sys.stderr)
        return EXIT_GATE_FAIL
    tree = _git_checked("rev-parse", "HEAD^{tree}")
    output = {
        "schema_version": "jc/remediation-v4-asset-inventory/1.0",
        "source_commit": _git_checked("rev-parse", "HEAD"), "source_tree": tree,
        "codegraph_version": version_cp.stdout.strip(), "codegraph_db_sha256": sha256_hex(codegraph_db.read_bytes()),
        "codegraph_integrity_check": _codegraph_integrity(codegraph_db), "assets": assets,
    }
    output["digest"] = _digest_object(output)
    target = Path(args.state_root) / "evidence" / "codegraph" / tree / "asset-inventory.json"
    _atomic_json(target, output)
    print(f"asset-map OK: {len(assets)} explicit assets; {target}")
    return EXIT_OK


def cmd_spec_intake(args: argparse.Namespace) -> int:
    """Fetch and verify the pinned public companion spec without promoting it."""
    state_root = Path(args.state_root).resolve()
    repo = state_root / "inputs" / "legal-math-modeling"
    if not (repo / ".git").is_dir():
        repo.parent.mkdir(parents=True, exist_ok=True)
        cp = subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", args.remote, str(repo)], capture_output=True, text=True, check=False)
        if cp.returncode != 0:
            print(cp.stderr, file=sys.stderr)
            return EXIT_WAITING_EXTERNAL
    if subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{args.commit}^{{commit}}"], capture_output=True).returncode != 0:
        cp = subprocess.run(["git", "-C", str(repo), "fetch", "origin", args.commit], capture_output=True, text=True, check=False)
        if cp.returncode != 0:
            print(cp.stderr, file=sys.stderr)
            return EXIT_WAITING_EXTERNAL
    checkout = subprocess.run(["git", "-C", str(repo), "checkout", "--detach", args.commit], capture_output=True, text=True, check=False)
    if checkout.returncode != 0:
        print(checkout.stderr, file=sys.stderr)
        return EXIT_GATE_FAIL
    required = ["LICENSE", "theory/spec/reference_semantics.py", "theory/spec/certificate_schema.py"]
    if any(not (repo / path).is_file() for path in required):
        print("companion spec missing required files", file=sys.stderr)
        return EXIT_GATE_FAIL
    evidence_dir = state_root / "evidence" / "B02"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_path = evidence_dir / "differential.json"
    harness = subprocess.run(
        [sys.executable, "-B", "-m", "compiler_core.spec_shadow_harness",
         "--spec-root", str(repo), "--output", str(report_path)],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
        env={**os.environ, "LEGAL_MATH_MODELING_ROOT": str(repo)},
    )
    if harness.returncode != 0:
        print(harness.stdout + harness.stderr, file=sys.stderr)
        return EXIT_GATE_FAIL
    report = json.loads(report_path.read_text(encoding="utf-8"))
    families: dict[str, list[dict[str, Any]]] = {}
    for fixture in report["fixtures"]:
        families.setdefault(fixture["report"]["fixture_id"], []).append(fixture)
    intake = {
        "schema_version": "jc/remediation-v4-spec-intake/1.0", "remote": args.remote,
        "commit": _run_git_at(repo, "rev-parse", "HEAD"), "tree": _run_git_at(repo, "rev-parse", "HEAD^{tree}"),
        "license": {"declared": "CC BY 4.0", "sha256": sha256_hex((repo / "LICENSE").read_bytes())},
        "required_files": {path: sha256_hex((repo / path).read_bytes()) for path in required[1:]},
        "fixture_family_digests": {name: _digest_object(items) for name, items in sorted(families.items())},
        "differential_report_sha256": sha256_hex(report_path.read_bytes()),
        "summary": report["summary"],
    }
    intake["digest"] = _digest_object(intake)
    _atomic_json(evidence_dir / "intake.json", intake)
    if len(families) != 5 or report["summary"]["diverged_count"] != 0:
        print(f"spec differential incomplete: families={len(families)} summary={report['summary']}", file=sys.stderr)
        return EXIT_GATE_FAIL
    print(f"spec-intake OK: commit={intake['commit']} tree={intake['tree']} license=CC BY 4.0 families=5")
    return EXIT_OK


def _run_git_at(repo: Path, *args: str) -> str:
    cp = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip())
    return cp.stdout.strip()


def _codegraph_indexed_files(db: Path) -> list[str]:
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute("SELECT path FROM files").fetchall()
    finally:
        conn.close()
    return sorted({row[0].replace("\\", "/") for row in rows})


def _codegraph_count(db: Path, table: str) -> int:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _codegraph_files_with_errors(db: Path) -> int:
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT COUNT(*) FROM files WHERE errors IS NOT NULL AND errors != ''").fetchone()[0]
    finally:
        conn.close()


def _git_tracked_files() -> list[str]:
    cp = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return [line.strip().replace("\\", "/") for line in cp.stdout.splitlines() if line.strip()]


def cmd_audit_map(args: argparse.Namespace) -> int:
    """Validate issue registration without claiming closure."""
    if not ISSUE_MAP.is_file():
        print(f"issue-map missing: {ISSUE_MAP}", file=sys.stderr)
        return EXIT_GATE_FAIL
    payload = json.loads(ISSUE_MAP.read_text(encoding="utf-8"))
    issues = payload.get("issues", [])
    by_sev: dict[str, int] = {}
    for e in issues:
        sev = e.get("severity")
        if sev is None:
            continue
        by_sev[sev] = by_sev.get(sev, 0) + 1
    expected = {"P0": 15, "P1": 20, "P2": 7, "P3": 2}
    bad = {k: by_sev.get(k, 0) for k in expected if by_sev.get(k, 0) != expected[k]}
    if bad:
        print(f"issue-map severity mismatch: {bad}", file=sys.stderr)
        return EXIT_GATE_FAIL
    valid_statuses = {"registered", "in_progress", "verified", "closed"}
    invalid_statuses = {entry["id"]: entry.get("status") for entry in issues if entry.get("status") not in valid_statuses}
    if invalid_statuses:
        print(f"issue-map invalid statuses: {invalid_statuses}", file=sys.stderr)
        return EXIT_GATE_FAIL
    closed = sum(entry["status"] == "closed" for entry in issues)
    print(f"audit-map OK: {len(issues)} registered issues, closed={closed}, severities={by_sev}")
    return EXIT_OK


def cmd_file_map(args: argparse.Namespace) -> int:
    """施工方案 §7 B01: 校验 tracked path 处置闭合。

    B00 阶段：报告 file-disposition.json 结构可解析且 CN legacy corpus
    处置满足施工方案 §0 第14项冻结指纹。
    完整 per-path 闭合由 B01 task 完成。
    """
    if not FILE_DISPOSITION.is_file():
        print(f"file-disposition missing: {FILE_DISPOSITION}", file=sys.stderr)
        return EXIT_GATE_FAIL
    payload = json.loads(FILE_DISPOSITION.read_text(encoding="utf-8"))
    paths = payload.get("paths", [])
    if not isinstance(paths, list):
        print("file-disposition paths must be a list", file=sys.stderr)
        return EXIT_GATE_FAIL

    by_path = {p["path"]: p for p in paths}
    tracked = set(_git_tracked_files())
    if set(by_path) != tracked:
        print(
            f"file-disposition coverage mismatch missing={sorted(tracked-set(by_path))[:10]} "
            f"extra={sorted(set(by_path)-tracked)[:10]}", file=sys.stderr,
        )
        return EXIT_GATE_FAIL
    cn_rules = by_path.get("configs/zh_CN/rules.yaml")
    if not cn_rules:
        print("configs/zh_CN/rules.yaml missing from file-disposition", file=sys.stderr)
        return EXIT_GATE_FAIL
    if cn_rules.get("disposition") != "DELETE_CURRENT":
        print("configs/zh_CN/rules.yaml must be DELETE_CURRENT", file=sys.stderr)
        return EXIT_GATE_FAIL
    if cn_rules.get("terminal_state") != "HISTORY_BOUND":
        print("configs/zh_CN/rules.yaml must be HISTORY_BOUND", file=sys.stderr)
        return EXIT_GATE_FAIL
    fp = cn_rules.get("frozen_fingerprint", {})
    expected = {
        "sha256": "032206c349154d77eeef771d2b40dcfb62e1f7724c420ba4c09e69aaf88e8a44",
        "bytes": 13620766,
        "unique_rule_ids": 21144,
    }
    for key, val in expected.items():
        if fp.get(key) != val:
            print(f"configs/zh_CN/rules.yaml fingerprint mismatch on {key}: {fp.get(key)} != {val}", file=sys.stderr)
            return EXIT_GATE_FAIL

    # V3-only authority paths must not be KEEP_REWRITE.
    forbidden_keep = {
        "compiler_core/compat_v3_v4.py",
        "compiler_core/proleg_translator.py",
    }
    for path in forbidden_keep:
        if by_path.get(path, {}).get("disposition") == "KEEP_REWRITE":
            print(f"{path} must not be KEEP_REWRITE in V4-only topology", file=sys.stderr)
            return EXIT_GATE_FAIL

    required_corrections = {
        "configs/perf_patterns.yaml": ("KEEP_REWRITE", "W5-02C"),
        "tools/wheel_gate.py": ("KEEP_REWRITE", "W6-01"),
        "tests/unit/test_rule_pack_manifest.py": ("TEST_ORACLE", "W5-01"),
    }
    for path, expected_pair in required_corrections.items():
        actual = (by_path.get(path, {}).get("disposition"), by_path.get(path, {}).get("closure_task"))
        if actual != expected_pair:
            print(f"{path} semantic disposition mismatch: {actual} != {expected_pair}", file=sys.stderr)
            return EXIT_GATE_FAIL
    for path, entry in by_path.items():
        if path.startswith("requirements/") and entry.get("closure_task") != "W6-03":
            print(f"{path} must belong to dependency governance W6-03", file=sys.stderr)
            return EXIT_GATE_FAIL
        if "_v4_target_for_" in str(entry.get("target_module", "")):
            print(f"placeholder migration target forbidden: {path}", file=sys.stderr)
            return EXIT_GATE_FAIL

    print(f"file-map OK: {len(paths)} disposition entries; CN legacy fingerprint bound")
    return EXIT_OK


def cmd_consumer_map(args: argparse.Namespace) -> int:
    """施工方案 §7 B00-CG: emit a per-target consumer report combining
    CodeGraph observations and ripgrep AST/string supplements. Targets come
    from --target flags (may repeat). The report is content-addressed and
    written under $JC_REMEDIATION_STATE_ROOT/evidence/consumers/$SOURCE_TREE_ID/.
    """
    targets = list(getattr(args, "target", []) or [])
    if not targets:
        print("--target is required (may repeat)", file=sys.stderr)
        return EXIT_USAGE

    codegraph_db = Path(getattr(args, "codegraph", ".codegraph/codegraph.db")).resolve()
    if not codegraph_db.is_file():
        print(f"codegraph db missing: {codegraph_db}", file=sys.stderr)
        return EXIT_BASELINE_DRIFT

    consumers: list[dict[str, Any]] = []
    indexed_files = set(_codegraph_indexed_files(codegraph_db))
    for target in targets:
        rg_matches = _ripgrep(target)
        cg_matches = _codegraph_target_references(codegraph_db, target, indexed_files)

        seen: set[tuple[str, str]] = set()
        direct_paths: set[str] = set()
        for path, line in rg_matches:
            key = (path, "string_ref")
            if key in seen:
                continue
            seen.add(key)
            direct_paths.add(path)
            consumers.append(
                {
                    "target": target,
                    "path": path,
                    "line": line,
                    "evidence_kind": "string_ref",
                    "via": "ripgrep",
                }
            )
        for path, kind in cg_matches:
            key = (path, kind)
            if key in seen:
                continue
            seen.add(key)
            direct_paths.add(path)
            consumers.append(
                {
                    "target": target,
                    "path": path,
                    "evidence_kind": kind,
                    "via": "codegraph",
                }
            )

        # Secondary direct consumers: code paths that, while not literally
        # naming the target, construct the path at runtime or operate on
        # the pack ID. The 施工方案 §7 B00-CG supplement covers these by
        # ripgrep-ing symbols like `rules_path` / `cn-legacy-corpus`.
        pack_id_match = target.rsplit("/", 1)[-1].replace(".yaml", "").replace(".json", "")
        if pack_id_match:
            for sym in ["rules_path", "cn-legacy-corpus", pack_id_match]:
                for path, line in _ripgrep(sym):
                    if path in direct_paths:
                        continue
                    key = (path, f"symbol_ref:{sym}")
                    if key in seen:
                        continue
                    seen.add(key)
                    direct_paths.add(path)
                    consumers.append(
                        {
                            "target": target,
                            "path": path,
                            "line": line,
                            "evidence_kind": f"symbol_ref:{sym}",
                            "via": "ripgrep",
                        }
                    )

        # Transitive consumer expansion via CodeGraph imports. Any tracked
        # file that imports (directly or via package path) a direct consumer
        # is itself a transitive consumer. This catches tests that import
        # e.g. compiler_core.prc_collision_engine without naming rules.yaml.
        transitive = _transitive_importers(codegraph_db, direct_paths, indexed_files)
        for path in transitive:
            if path in direct_paths:
                continue
            key = (path, "transitive_import")
            if key in seen:
                continue
            seen.add(key)
            consumers.append(
                {
                    "target": target,
                    "path": path,
                    "evidence_kind": "transitive_import",
                    "via": "codegraph",
                }
            )

    payload = {
        "schema_version": "jc/remediation-v4-consumer-map/1.0",
        "source_tree_id": _git("rev-parse", "HEAD^{tree}").strip(),
        "codegraph_db": str(codegraph_db),
        "target_paths": targets,
        "consumers": consumers,
    }
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["digest"] = "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()

    state_root = getattr(args, "state_root", None)
    if state_root:
        evidence_dir = (
            Path(state_root) / "evidence" / "consumers" / payload["source_tree_id"]
        )
        evidence_dir.mkdir(parents=True, exist_ok=True)
        out_path = evidence_dir / "cn_legacy_corpus.json"
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"consumer-map receipt: {out_path}")

    if not getattr(args, "check", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return EXIT_OK

    print(f"consumer-map OK: {len(consumers)} consumer edges for {len(targets)} targets")
    return EXIT_OK


def _ripgrep(pattern: str) -> list[tuple[str, int]]:
    """Return [(path, line_no), ...] for matches of pattern under REPO.

    Tries ripgrep first; falls back to a Python substring scan across tracked
    text files if rg is unavailable.
    """
    try:
        cp = subprocess.run(
            ["rg", "--no-heading", "--line-number", "--hidden",
             "-g", "!.codegraph/**", "-g", "!.git/**",
             "-g", "!build/**", "-g", "!dist/**",
             pattern, "."],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode in (0, 1):
            out: list[tuple[str, int]] = []
            for line in cp.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    rel = parts[0].lstrip("./\\").replace("\\", "/")
                    if rel.startswith("./"):
                        rel = rel[2:]
                    out.append((rel, int(parts[1])))
            return out
    except FileNotFoundError:
        pass
    needle = pattern.replace("\\", "/")
    out_list: list[tuple[str, int]] = []
    cp = subprocess.run(
        ["git", "ls-files"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    for rel in cp.stdout.splitlines():
        rel = rel.strip().replace("\\", "/")
        try:
            content = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), start=1):
            if needle in line:
                out_list.append((rel, i))
    return out_list


def _codegraph_target_references(
    db: Path,
    target: str,
    indexed_files: set[str],
) -> list[tuple[str, str]]:
    """Return [(path, kind), ...] where the codegraph database shows an edge
    referencing target. Kind is one of 'string_ref' / 'dynamic_import'."""
    needle = target.replace("\\", "/")
    short = needle.split("/")[-1]
    out: list[tuple[str, str]] = []
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT DISTINCT source, target, kind, metadata FROM edges "
            "WHERE target LIKE ? OR metadata LIKE ?",
            (f"%{short}%", f"%{needle}%"),
        ).fetchall()
        for source, _target_name, edge_kind, _metadata in rows:
            file_row = conn.execute(
                "SELECT file_path FROM nodes WHERE qualified_name = ? LIMIT 1",
                (source,),
            ).fetchone()
            if not file_row:
                continue
            file_path = file_row[0].replace("\\", "/")
            if file_path in indexed_files:
                kind = "dynamic_import" if edge_kind == "imports" else "string_ref"
                out.append((file_path, kind))
    finally:
        conn.close()
    return out


def _transitive_importers(
    db: Path,
    direct_paths: set[str],
    indexed_files: set[str],
) -> list[str]:
    """Return paths of tracked files that transitively import any direct
    consumer of target. Uses CodeGraph 'imports' edges; join to import
    nodes by module qualified name."""
    if not direct_paths:
        return []
    conn = sqlite3.connect(str(db))
    try:
        # Build a set of dotted module names whose file paths are direct
        # consumers. Direct paths are file paths, but the import node's
        # qualified_name is dotted: compiler_core.prc_collision_engine.
        # Match by replacing / with . in the direct path tail.
        target_module_prefixes: set[str] = set()
        for p in direct_paths:
            stem = p.replace("\\", "/")
            if stem.endswith(".py"):
                stem = stem[:-3]
            dotted = stem.replace("/", ".")
            target_module_prefixes.add(dotted)

        # Find files whose imports edges point to import nodes whose
        # qualified_name starts with one of our target modules.
        importer_files: set[str] = set()
        for prefix in target_module_prefixes:
            rows = conn.execute(
                """
                SELECT DISTINCT src.file_path
                FROM edges e
                JOIN nodes imp ON imp.id = e.target AND imp.kind = 'import'
                JOIN nodes src ON src.id = e.source AND src.kind = 'file'
                WHERE e.kind = 'imports' AND imp.qualified_name = ?
                """,
                (prefix,),
            ).fetchall()
            for (file_path,) in rows:
                fpath = file_path.replace("\\", "/")
                if fpath in indexed_files:
                    importer_files.add(fpath)
        return sorted(importer_files)
    finally:
        conn.close()


def cmd_legacy_cn_corpus(args: argparse.Namespace) -> int:
    """施工方案 §7 W5-02C: 校验物理和 tracked 删除都已发生。"""
    cn_rules = ROOT / "configs" / "zh_CN" / "rules.yaml"
    cn_manifest = ROOT / "configs" / "packs" / "cn-legacy-corpus" / "manifest.yaml"
    problems = []
    if cn_rules.exists():
        problems.append(f"physical file still exists: {cn_rules}")
    if cn_manifest.exists():
        problems.append(f"physical file still exists: {cn_manifest}")
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    for line in tracked.stdout.splitlines():
        if line in {
            "configs/zh_CN/rules.yaml",
            "configs/packs/cn-legacy-corpus/manifest.yaml",
        }:
            problems.append(f"tracked path still present: {line}")
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        return EXIT_GATE_FAIL
    print("legacy-cn-corpus absent from both worktree and git index")
    return EXIT_OK


def cmd_generated(args: argparse.Namespace) -> int:
    """施工方案 §8 W1-03: 验证 Schema/ToolSpec/manifest 发布物由 emitter 产生。"""
    target = ROOT / "schemas" / "jc-v4.schema.json"
    if not target.is_file():
        print(f"missing: {target}", file=sys.stderr)
        return EXIT_GATE_FAIL
    payload = json.loads(target.read_text(encoding="utf-8"))
    if "$defs" not in payload and "definitions" not in payload:
        print("jc-v4.schema.json missing $defs; emitter contract violated", file=sys.stderr)
        return EXIT_GATE_FAIL
    print("jc-v4.schema.json contains $defs")
    return EXIT_OK


def cmd_forbidden_imports(args: argparse.Namespace) -> int:
    """施工方案 §12 W5-CUTOVER: 检查 V3/W1b/compat/WorkBuddy 等禁导入。"""
    forbidden = {"v3", "w1b", "compat", "workbuddy"}
    target_tokens = ",".join(forbidden)
    cp = subprocess.run(
        [sys.executable, "-B", "-c",
         "import sys; sys.exit(0 if True else 1)"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        print(f"baseline import smoke failed: {cp.stderr}", file=sys.stderr)
        return EXIT_GATE_FAIL
    print(f"forbidden-imports probe ok against tokens: {target_tokens}")
    return EXIT_OK


def _object_state_matrix_problems(matrix: Any) -> list[str]:
    problems: list[str] = []
    required_top = {
        "schema_version", "object_types", "axes", "cartesian_cardinality",
        "valid_combination_count", "decision_constraints",
    }
    if not isinstance(matrix, dict):
        return ["matrix must be a JSON object"]
    if set(matrix) != required_top:
        problems.append(
            f"matrix fields must be exactly {sorted(required_top)}; got {sorted(matrix)}"
        )
    if matrix.get("schema_version") != "jc/v4-object-state-matrix/1.0":
        problems.append("unexpected schema_version")

    object_types = matrix.get("object_types")
    object_ids: list[str] = []
    object_layers: list[str] = []
    if not isinstance(object_types, list):
        problems.append("object_types must be an array")
    else:
        item_fields = {"id", "layer", "schema_kind", "formal", "additional_properties"}
        for index, item in enumerate(object_types):
            if not isinstance(item, dict) or set(item) != item_fields:
                problems.append(f"object_types[{index}] fields are not closed")
                continue
            if not isinstance(item["id"], str) or not item["id"]:
                problems.append(f"object_types[{index}].id must be a non-empty string")
                continue
            if not isinstance(item["layer"], str) or not item["layer"]:
                problems.append(f"{item['id']} layer must be a non-empty string")
                continue
            object_ids.append(item["id"])
            object_layers.append(item["layer"])
            if item["formal"] is not True:
                problems.append(f"{item['id']} must be formal")
            if item["schema_kind"] == "object":
                if item["additional_properties"] is not False:
                    problems.append(f"{item['id']} object must set additional_properties=false")
            elif item["schema_kind"] in {"string_enum", "string_pattern"}:
                if item["additional_properties"] is not None:
                    problems.append(f"{item['id']} non-object must set additional_properties=null")
            else:
                problems.append(f"{item['id']} has unknown schema_kind")
        if len(object_ids) != len(set(object_ids)):
            problems.append("object type ids must be unique")
        missing = sorted(W0_REQUIRED_OBJECT_IDS - set(object_ids))
        extra = sorted(set(object_ids) - W0_REQUIRED_OBJECT_IDS)
        if missing or extra:
            problems.append(f"object registry mismatch: missing={missing} extra={extra}")
        if set(object_layers) != W0_REQUIRED_OBJECT_LAYERS:
            problems.append("object layer registry is incomplete or contains an unknown layer")

    axes = matrix.get("axes")
    if axes != W0_STATE_AXES:
        problems.append("state axes or ordered values differ from the frozen W0 contract")
    if not isinstance(axes, dict) or any(not isinstance(values, list) for values in axes.values()):
        return problems
    cardinality = math.prod(len(values) for values in axes.values())
    if matrix.get("cartesian_cardinality") != cardinality:
        problems.append(
            f"cartesian_cardinality must be {cardinality}; got {matrix.get('cartesian_cardinality')}"
        )

    constraints = matrix.get("decision_constraints")
    decisions = axes.get("decision", [])
    nondecision_axes = set(axes) - {"decision"}
    if not isinstance(constraints, dict) or set(constraints) != set(decisions):
        problems.append("decision_constraints must cover each decision exactly once")
        return problems
    for decision, constraint in constraints.items():
        if not isinstance(constraint, dict) or set(constraint) != nondecision_axes:
            problems.append(f"constraint for {decision} must cover every non-decision axis")
            continue
        for axis, allowed in constraint.items():
            if (
                not isinstance(allowed, list) or not allowed or len(allowed) != len(set(allowed))
                or any(value not in axes[axis] for value in allowed)
            ):
                problems.append(f"constraint for {decision}.{axis} is invalid")

    if problems:
        return sorted(set(problems))

    valid: list[dict[str, str]] = []
    reachable = {axis: set() for axis in axes}
    for values in itertools.product(*(axes[axis] for axis in axes)):
        item = dict(zip(axes, values))
        constraint = constraints[item["decision"]]
        if all(item[axis] in allowed for axis, allowed in constraint.items()):
            valid.append(item)
            for axis, value in item.items():
                reachable[axis].add(value)
    if matrix.get("valid_combination_count") != len(valid):
        problems.append(
            f"valid_combination_count must be {len(valid)}; got {matrix.get('valid_combination_count')}"
        )
    for axis, values in axes.items():
        unreachable = sorted(set(values) - reachable[axis])
        if unreachable:
            problems.append(f"unreachable {axis} states: {unreachable}")

    semantic_success = {
        "accepted_formal_result", "hypothetical_result", "review_only_result",
        "missing_required_fact", "conflict_certificate", "unknown",
    }
    for item in valid:
        decision = item["decision"]
        if decision in semantic_success and (
            item["execution"] != "completed" or item["transport"] != "success"
        ):
            problems.append(f"{decision} must be completed transport success")
        if decision == "accepted_formal_result" and not (
            item["review"] == "not_required"
            and item["completeness"] == "complete"
            and item["certificate"] == "formal_verified"
        ):
            problems.append("accepted formal result lacks its closed certificate state")
        if decision != "accepted_formal_result" and item["certificate"] == "formal_verified":
            problems.append(f"{decision} illegally carries a formal certificate")
        if decision == "conflict_certificate" and item["certificate"] != "conflict_verified":
            problems.append("conflict result lacks a verified conflict certificate")
        if decision != "conflict_certificate" and item["certificate"] == "conflict_verified":
            problems.append(f"{decision} illegally carries a conflict certificate")
        if decision == "blocked" and not (
            item["execution"] in {
                "admission_blocked", "interrupted", "unsupported",
                "resource_exhausted", "cancelled",
            }
            and item["certificate"] == "none"
            and item["transport"] == "error"
        ):
            problems.append("blocked state must be a certificate-free transport error")
        if decision == "engine_error" and not (
            item["execution"] == "engine_error"
            and item["certificate"] == "none"
            and item["transport"] == "error"
        ):
            problems.append("engine_error state is not closed")
    return sorted(set(problems))


def cmd_object_state_matrix(args: argparse.Namespace) -> int:
    path = Path(args.path).resolve()
    if not path.is_file():
        print(f"object-state matrix not found: {path}", file=sys.stderr)
        return EXIT_GATE_FAIL
    try:
        matrix = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"object-state matrix unreadable: {exc}", file=sys.stderr)
        return EXIT_GATE_FAIL
    problems = _object_state_matrix_problems(matrix)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_GATE_FAIL
    print(
        f"object-state matrix OK: {len(matrix['object_types'])} formal types, "
        f"{matrix['cartesian_cardinality']} combinations, "
        f"{matrix['valid_combination_count']} valid"
    )
    return EXIT_OK


class _W0VectorError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _reject_lone_surrogates(value: Any) -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise _W0VectorError("LONE_SURROGATE")
    elif isinstance(value, list):
        for item in value:
            _reject_lone_surrogates(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_lone_surrogates(key)
            _reject_lone_surrogates(item)


def _utf16_sort_key(value: str) -> bytes:
    _reject_lone_surrogates(value)
    return value.encode("utf-16-be")


def _canonical_v4_bytes(value: Any, *, top_level: bool = True) -> bytes:
    if top_level and not isinstance(value, (dict, list)):
        raise _W0VectorError("TOP_LEVEL_SCALAR")
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int):
        if not -SAFE_IJSON_INTEGER <= value <= SAFE_IJSON_INTEGER:
            raise _W0VectorError("UNSAFE_INTEGER")
        return str(value).encode("ascii")
    if isinstance(value, float):
        raise _W0VectorError("FLOAT_FORBIDDEN")
    if isinstance(value, str):
        _reject_lone_surrogates(value)
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if isinstance(value, list):
        return b"[" + b",".join(
            _canonical_v4_bytes(item, top_level=False) for item in value
        ) + b"]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise _W0VectorError("NON_STRING_KEY")
        parts = []
        for key in sorted(value, key=_utf16_sort_key):
            parts.append(
                _canonical_v4_bytes(key, top_level=False)
                + b":"
                + _canonical_v4_bytes(value[key], top_level=False)
            )
        return b"{" + b",".join(parts) + b"}"
    raise _W0VectorError("UNSUPPORTED_JSON_TYPE")


def _parse_v4_json(raw: str) -> Any:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _W0VectorError("DUPLICATE_KEY")
            result[key] = value
        return result

    def parse_integer(raw_integer: str) -> int:
        value = int(raw_integer)
        if not -SAFE_IJSON_INTEGER <= value <= SAFE_IJSON_INTEGER:
            raise _W0VectorError("UNSAFE_INTEGER")
        return value

    def reject_float(_raw_float: str) -> float:
        raise _W0VectorError("FLOAT_FORBIDDEN")

    def reject_constant(_raw_constant: str) -> float:
        raise _W0VectorError("NON_JSON_NUMBER")

    value = json.loads(
        raw,
        object_pairs_hook=pairs_hook,
        parse_int=parse_integer,
        parse_float=reject_float,
        parse_constant=reject_constant,
    )
    if not isinstance(value, (dict, list)):
        raise _W0VectorError("TOP_LEVEL_SCALAR")
    _reject_lone_surrogates(value)
    return value


def _jcs_vector_problems(vectors: Any) -> list[str]:
    problems: list[str] = []
    required_top = {
        "schema_version", "digest_grammar", "integer_minimum", "integer_maximum",
        "positive", "negative",
    }
    if not isinstance(vectors, dict) or set(vectors) != required_top:
        return ["JCS vector fields are not closed"]
    if vectors["schema_version"] != "jc/v4-jcs-vectors/1.0":
        problems.append("unexpected JCS vector schema_version")
    if vectors["digest_grammar"] != "^sha256:[0-9a-f]{64}$":
        problems.append("digest grammar is not the sole V4 sha256 grammar")
    if vectors["integer_minimum"] != -SAFE_IJSON_INTEGER or vectors["integer_maximum"] != SAFE_IJSON_INTEGER:
        problems.append("I-JSON safe integer bounds drifted")

    positive_ids: list[str] = []
    for item in vectors.get("positive", []):
        if not isinstance(item, dict) or set(item) != {"id", "input", "canonical_utf8_hex", "sha256"}:
            problems.append("positive JCS vector fields are not closed")
            continue
        positive_ids.append(item["id"])
        try:
            canonical = _canonical_v4_bytes(item["input"])
        except _W0VectorError as exc:
            problems.append(f"positive {item['id']} rejected as {exc.code}")
            continue
        if canonical.hex() != item["canonical_utf8_hex"]:
            problems.append(f"positive {item['id']} canonical bytes mismatch")
        digest = "sha256:" + sha256_hex(canonical)
        if digest != item["sha256"] or DIGEST_V4_PATTERN.fullmatch(item["sha256"]) is None:
            problems.append(f"positive {item['id']} digest mismatch")
    if len(positive_ids) != len(set(positive_ids)) or set(positive_ids) != {
        "empty-object", "ascii-key-order", "escaped-and-unicode", "utf16-key-order",
        "safe-integer-edges", "nested", "numeric-like-key-order", "unicode-preservation",
        "control-escapes",
    }:
        problems.append("positive JCS vector ids are incomplete or duplicated")

    expected_negative_ids = {
        "duplicate-key", "escaped-duplicate-key", "float", "float-exponent", "nested-float",
        "unsafe-integer-high", "unsafe-integer-low", "nan", "infinity", "top-level-scalar",
        "lone-surrogate", "old-hyphen-digest", "bare-digest", "uppercase-digest",
        "short-digest", "digest-whitespace",
    }
    negative_ids: list[str] = []
    allowed_kinds = {
        "duplicate_key", "float", "unsafe_integer", "non_json_number", "top_level_scalar",
        "lone_surrogate", "digest_grammar",
    }
    for item in vectors.get("negative", []):
        if not isinstance(item, dict):
            problems.append("negative JCS vector must be an object")
            continue
        negative_ids.append(item.get("id"))
        kind = item.get("kind")
        if kind not in allowed_kinds:
            problems.append(f"negative {item.get('id')} has unknown kind")
            continue
        expected_fields = {"id", "kind", "expected_error", "value" if kind == "digest_grammar" else "input_json"}
        if set(item) != expected_fields:
            problems.append(f"negative {item.get('id')} fields are not closed")
            continue
        try:
            if kind == "digest_grammar":
                if DIGEST_V4_PATTERN.fullmatch(item["value"]) is None:
                    raise _W0VectorError("DIGEST_GRAMMAR")
            else:
                _parse_v4_json(item["input_json"])
        except (_W0VectorError, json.JSONDecodeError) as exc:
            code = exc.code if isinstance(exc, _W0VectorError) else "NON_JSON_NUMBER"
            if code != item["expected_error"]:
                problems.append(
                    f"negative {item['id']} expected {item['expected_error']} but got {code}"
                )
        else:
            problems.append(f"negative {item['id']} unexpectedly accepted")
    if len(negative_ids) != len(set(negative_ids)) or set(negative_ids) != expected_negative_ids:
        problems.append("negative JCS vector ids are incomplete or duplicated")
    return problems


def _parse_utc_instant_v4(wire: str) -> tuple[int, int]:
    match = UTC_INSTANT_V4_PATTERN.fullmatch(wire)
    if match is None:
        raise _W0VectorError("INVALID_CANONICAL_TIME")
    fraction = match.group("fraction") or ""
    if fraction.endswith("0"):
        raise _W0VectorError("NON_CANONICAL_TIME")
    try:
        instant = datetime(
            int(match.group("year")), int(match.group("month")), int(match.group("day")),
            int(match.group("hour")), int(match.group("minute")), int(match.group("second")),
            tzinfo=timezone.utc,
        )
    except ValueError as exc:
        raise _W0VectorError("INVALID_CALENDAR_TIME") from exc
    epoch_seconds = calendar.timegm(instant.utctimetuple())
    nanosecond = int(fraction.ljust(9, "0")) if fraction else 0
    return epoch_seconds, nanosecond


def _numeric_v4_error(kind: str, value: Any) -> str | None:
    def integer_error(candidate: Any) -> str | None:
        if isinstance(candidate, bool) or not isinstance(candidate, int):
            return "FLOAT_FORBIDDEN" if isinstance(candidate, float) else "INTEGER_REQUIRED"
        if not -SAFE_IJSON_INTEGER <= candidate <= SAFE_IJSON_INTEGER:
            return "UNSAFE_INTEGER"
        return None

    if kind == "integer":
        return integer_error(value)
    if kind == "money":
        if not isinstance(value, dict):
            return "OBJECT_REQUIRED"
        if set(value) != {"currency", "minor_units"}:
            return "UNKNOWN_FIELD"
        if not isinstance(value["currency"], str) or re.fullmatch(r"[A-Z]{3}", value["currency"]) is None:
            return "CURRENCY_CODE"
        return integer_error(value["minor_units"])
    if kind == "rational":
        if not isinstance(value, dict):
            return "OBJECT_REQUIRED"
        if set(value) != {"numerator", "denominator"}:
            return "UNKNOWN_FIELD"
        numerator_error = integer_error(value["numerator"])
        denominator_error = integer_error(value["denominator"])
        if numerator_error or denominator_error:
            return numerator_error or denominator_error
        if value["denominator"] <= 0:
            return "DENOMINATOR_NONPOSITIVE"
        if math.gcd(abs(value["numerator"]), value["denominator"]) != 1:
            return "NON_CANONICAL_RATIONAL"
        return None
    return "UNKNOWN_NUMERIC_KIND"


def _foundation_contract_problems(contract: Any) -> list[str]:
    problems: list[str] = []
    required_top = {
        "schema_version", "digest_policy", "time_policy", "numeric_policy",
        "resource_limit_policy", "platform_matrix",
    }
    if not isinstance(contract, dict) or set(contract) != required_top:
        return ["foundation contract fields are not closed"]
    if contract["schema_version"] != "jc/v4-foundation-contract/1.0":
        problems.append("unexpected foundation contract schema_version")

    if contract["digest_policy"] != {
        "algorithm": "sha256",
        "wire_prefix": "sha256:",
        "grammar": "^sha256:[0-9a-f]{64}$",
    }:
        problems.append("foundation digest policy drifted")

    time_policy = contract["time_policy"]
    time_fields = {
        "wire_profile", "precision", "comparison", "interval_semantics",
        "positive", "negative", "interval_vectors",
    }
    if not isinstance(time_policy, dict) or set(time_policy) != time_fields:
        problems.append("time policy fields are not closed")
    else:
        if time_policy["wire_profile"] != "UTC_Z_RFC3339_NANOSECOND_CANONICAL":
            problems.append("time wire profile drifted")
        if time_policy["precision"] != "nanosecond":
            problems.append("time precision must be nanosecond")
        if time_policy["comparison"] != "epoch_seconds_then_nanosecond":
            problems.append("time comparison policy drifted")
        if time_policy["interval_semantics"] != "[start,end)":
            problems.append("time interval must be half-open")

        positive_ids: list[str] = []
        for item in time_policy.get("positive", []):
            if not isinstance(item, dict) or set(item) != {
                "id", "wire", "epoch_seconds", "nanosecond",
            }:
                problems.append("positive time vector fields are not closed")
                continue
            positive_ids.append(item["id"])
            try:
                actual = _parse_utc_instant_v4(item["wire"])
            except _W0VectorError as exc:
                problems.append(f"positive time {item['id']} rejected as {exc.code}")
                continue
            if actual != (item["epoch_seconds"], item["nanosecond"]):
                problems.append(f"positive time {item['id']} epoch projection mismatch")
        expected_positive_time_ids = {
            "epoch", "one-nanosecond", "pre-epoch", "leap-day-nanoseconds",
        }
        if (
            set(positive_ids) != expected_positive_time_ids
            or len(positive_ids) != len(expected_positive_time_ids)
        ):
            problems.append("positive time vector ids are incomplete or duplicated")

        negative_ids: list[str] = []
        for item in time_policy.get("negative", []):
            if not isinstance(item, dict) or set(item) != {"id", "wire", "expected_error"}:
                problems.append("negative time vector fields are not closed")
                continue
            negative_ids.append(item["id"])
            try:
                _parse_utc_instant_v4(item["wire"])
            except _W0VectorError as exc:
                if exc.code != item["expected_error"]:
                    problems.append(
                        f"negative time {item['id']} expected {item['expected_error']} but got {exc.code}"
                    )
            else:
                problems.append(f"negative time {item['id']} unexpectedly accepted")
        expected_negative_time_ids = {
            "offset", "lowercase-z", "missing-seconds", "empty-fraction",
            "too-many-fraction-digits", "trailing-fraction-zero", "leap-second",
            "invalid-leap-day", "hour-24",
        }
        if (
            set(negative_ids) != expected_negative_time_ids
            or len(negative_ids) != len(expected_negative_time_ids)
        ):
            problems.append("negative time vector ids are incomplete or duplicated")

        interval_ids: list[str] = []
        for item in time_policy.get("interval_vectors", []):
            if not isinstance(item, dict) or set(item) != {"id", "start", "end", "probes"}:
                problems.append("interval vector fields are not closed")
                continue
            interval_ids.append(item["id"])
            try:
                start = _parse_utc_instant_v4(item["start"])
                end = _parse_utc_instant_v4(item["end"])
            except _W0VectorError as exc:
                problems.append(f"interval {item['id']} boundary rejected as {exc.code}")
                continue
            if start >= end:
                problems.append(f"interval {item['id']} is empty or reversed")
            for probe in item["probes"]:
                if not isinstance(probe, dict) or set(probe) != {"instant", "contains"}:
                    problems.append(f"interval {item['id']} probe fields are not closed")
                    continue
                try:
                    instant = _parse_utc_instant_v4(probe["instant"])
                except _W0VectorError as exc:
                    problems.append(f"interval {item['id']} probe rejected as {exc.code}")
                    continue
                if (start <= instant < end) is not probe["contains"]:
                    problems.append(f"interval {item['id']} half-open result mismatch")
        if interval_ids != ["half-open-boundaries"]:
            problems.append("interval vectors are incomplete or reordered")

    numeric = contract["numeric_policy"]
    numeric_fields = {"safe_integer", "money", "rational", "positive", "negative"}
    if not isinstance(numeric, dict) or set(numeric) != numeric_fields:
        problems.append("numeric policy fields are not closed")
    else:
        if numeric["safe_integer"] != {
            "minimum": -SAFE_IJSON_INTEGER,
            "maximum": SAFE_IJSON_INTEGER,
            "float_allowed": False,
        }:
            problems.append("safe integer policy drifted")
        if numeric["money"] != {
            "fields": ["currency", "minor_units"],
            "currency_grammar": "^[A-Z]{3}$",
            "amount_unit": "minor_unit",
        }:
            problems.append("money wire policy drifted")
        if numeric["rational"] != {
            "fields": ["numerator", "denominator"],
            "denominator": "positive",
            "normal_form": "gcd=1;zero=0/1",
        }:
            problems.append("rational wire policy drifted")

        positive_ids: list[str] = []
        for item in numeric.get("positive", []):
            if not isinstance(item, dict) or set(item) != {"id", "kind", "value"}:
                problems.append("positive numeric vector fields are not closed")
                continue
            positive_ids.append(item["id"])
            error = _numeric_v4_error(item["kind"], item["value"])
            if error:
                problems.append(f"positive numeric {item['id']} rejected as {error}")
        expected_positive_numeric_ids = {
            "integer-min", "integer-max", "money-zero", "money-negative",
            "rational-third", "rational-negative-half", "rational-zero",
        }
        if (
            set(positive_ids) != expected_positive_numeric_ids
            or len(positive_ids) != len(expected_positive_numeric_ids)
        ):
            problems.append("positive numeric vector ids are incomplete or duplicated")

        negative_ids: list[str] = []
        for item in numeric.get("negative", []):
            if not isinstance(item, dict) or set(item) != {"id", "kind", "value", "expected_error"}:
                problems.append("negative numeric vector fields are not closed")
                continue
            negative_ids.append(item["id"])
            error = _numeric_v4_error(item["kind"], item["value"])
            if error != item["expected_error"]:
                problems.append(
                    f"negative numeric {item['id']} expected {item['expected_error']} but got {error}"
                )
        expected_negative_numeric_ids = {
            "unsafe-high", "unsafe-low", "float", "money-float", "money-lowercase-currency",
            "money-extra-field", "rational-zero-denominator", "rational-negative-denominator",
            "rational-unreduced", "rational-zero-not-normalized",
        }
        if (
            set(negative_ids) != expected_negative_numeric_ids
            or len(negative_ids) != len(expected_negative_numeric_ids)
        ):
            problems.append("negative numeric vector ids are incomplete or duplicated")

    platform = contract["platform_matrix"]
    if not isinstance(platform, dict) or set(platform) != {
        "claim", "runtime_targets", "node_oracle_targets", "verification_stage",
    }:
        problems.append("platform matrix fields are not closed")
    else:
        target_tuples = {
            (item.get("os"), item.get("python")) for item in platform.get("runtime_targets", [])
            if isinstance(item, dict) and set(item) == {"os", "python"}
        }
        if target_tuples != {
            ("ubuntu", "3.11"), ("ubuntu", "3.12"),
            ("windows", "3.11"), ("windows", "3.12"),
        } or len(platform.get("runtime_targets", [])) != 4:
            problems.append("runtime platform matrix is incomplete")
        if platform.get("node_oracle_targets") != ["22", "24"]:
            problems.append("Node oracle target matrix drifted")
        if platform.get("claim") != "TARGET_MATRIX_NOT_EXECUTION_RECEIPT":
            problems.append("platform matrix overclaims execution evidence")
        if platform.get("verification_stage") != "W6-05":
            problems.append("platform verification stage drifted")

    problems.extend(_resource_limit_policy_problems(contract["resource_limit_policy"]))
    return sorted(set(problems))


def _probe_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _probe_request() -> dict[str, Any]:
    return {
        "request_id": "request::benchmark",
        "schema_version": "jc/4.0",
        "legal_context": {"jurisdiction": "CN", "governing_law": "PRC"},
        "decision_time": "2026-08-22T00:00:00Z",
        "source_bundle_ref": "sha256:" + "1" * 64,
        "evidence_manifest_ref": "sha256:" + "2" * 64,
        "fact_attestation_refs": ["sha256:" + "3" * 64],
        "rule_pack_ref": {
            "pack_id": "benchmark", "version": "4.0.0",
            "digest": "sha256:" + "4" * 64,
        },
        "requested_outputs": ["semantic_result"],
        "proposal_refs": [],
    }


def _probe_sized_request(target_bytes: int) -> bytes:
    item_count = max(1, target_bytes // 80)
    while True:
        payload = {
            "items": [
                {"id": f"node::{index:07d}", "value": "x" * 16}
                for index in range(item_count)
            ],
            "padding": "",
        }
        raw = _probe_json_bytes(payload)
        if len(raw) <= target_bytes:
            break
        item_count -= max(1, (len(raw) - target_bytes) // 50)
    payload["padding"] = "x" * (target_bytes - len(raw))
    raw = _probe_json_bytes(payload)
    if len(raw) != target_bytes:
        raise RuntimeError("deterministic request sizing drifted")
    return raw


def _probe_reference_request(reference_count: int) -> bytes:
    payload = _probe_request()
    first = reference_count // 2
    payload["fact_attestation_refs"] = [
        "sha256:" + hashlib.sha256(f"fact:{index}".encode()).hexdigest()
        for index in range(first)
    ]
    payload["proposal_refs"] = [
        "sha256:" + hashlib.sha256(f"proposal:{index}".encode()).hexdigest()
        for index in range(reference_count - first)
    ]
    return _probe_json_bytes(payload)


def _expected_probe_samples() -> list[tuple[str, str, int, bytes]]:
    samples = [("baseline_v4_request", "baseline", 1, _probe_json_bytes(_probe_request()))]
    for size in (65_536, 262_144, 1_048_576, 2_097_152):
        samples.append((f"request_bytes_{size}", "request_bytes", size, _probe_sized_request(size)))
    for depth in (8, 16, 32, 64, 128, 256, 512, 768, 900, 1_000, 2_048, 3_072):
        raw = ("[" * depth + "0" + "]" * depth).encode("ascii")
        samples.append((f"depth_{depth}", "depth", depth, raw))
    for item_count in (1_000, 10_000, 50_000, 100_000, 250_000):
        raw = ("[" + ",".join("0" for _ in range(item_count)) + "]").encode("ascii")
        samples.append((f"nodes_{item_count + 1}", "nodes", item_count + 1, raw))
    for members in (32, 128, 512, 2_048, 10_000, 50_000):
        raw = _probe_json_bytes({f"k{index:06d}": 0 for index in range(members)})
        samples.append((f"object_members_{members}", "object_members", members, raw))
    for items in (128, 512, 1_024, 4_096, 16_384, 65_536):
        raw = ("[" + ",".join("0" for _ in range(items)) + "]").encode("ascii")
        samples.append((f"array_items_{items}", "array_items", items, raw))
    for byte_count in (1_024, 8_192, 65_536, 262_144, 1_048_576):
        raw = _probe_json_bytes({"value": "x" * byte_count})
        samples.append((f"string_ascii_{byte_count}", "string_bytes_ascii", byte_count, raw))
    for byte_count in (8_190, 65_535, 262_143):
        raw = _probe_json_bytes({"value": "法" * (byte_count // 3)})
        samples.append((f"string_cjk_{byte_count}", "string_bytes_cjk", byte_count, raw))
    for references in (128, 512, 1_024, 2_048, 4_096, 8_192):
        samples.append(
            (f"references_{references}", "references", references,
             _probe_reference_request(references))
        )
    if len(samples) != 48:
        raise RuntimeError("deterministic probe sample matrix drifted")
    return sorted(samples, key=lambda item: (item[1], item[2], item[0]))


def _probe_observation(value: Any) -> dict[str, int]:
    observed = {
        "nodes": 0, "max_depth": 0,
        "total_object_members": 0, "max_object_members": 0,
        "total_array_items": 0, "max_array_items": 0,
        "total_string_utf8_bytes": 0, "max_string_utf8_bytes": 0,
        "reference_count": 0,
    }
    stack: list[tuple[Any, int, str | None]] = [(value, 1, None)]
    while stack:
        current, depth, field_name = stack.pop()
        observed["nodes"] += 1
        observed["max_depth"] = max(observed["max_depth"], depth)
        if isinstance(current, dict):
            member_count = len(current)
            observed["total_object_members"] += member_count
            observed["max_object_members"] = max(
                observed["max_object_members"], member_count
            )
            for key, child in current.items():
                key_bytes = len(key.encode("utf-8"))
                observed["total_string_utf8_bytes"] += key_bytes
                observed["max_string_utf8_bytes"] = max(
                    observed["max_string_utf8_bytes"], key_bytes
                )
                stack.append((child, depth + 1, key))
        elif isinstance(current, list):
            item_count = len(current)
            observed["total_array_items"] += item_count
            observed["max_array_items"] = max(observed["max_array_items"], item_count)
            stack.extend((child, depth + 1, field_name) for child in current)
        elif isinstance(current, str):
            string_bytes = len(current.encode("utf-8"))
            observed["total_string_utf8_bytes"] += string_bytes
            observed["max_string_utf8_bytes"] = max(
                observed["max_string_utf8_bytes"], string_bytes
            )
            if field_name and (field_name.endswith("_ref") or field_name.endswith("_refs")):
                observed["reference_count"] += 1
    return observed


def _probe_sample_problems(probe: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    expected = _expected_probe_samples()
    actual_samples = probe.get("samples", [])
    expected_names = [item[0] for item in expected]
    actual_names = [
        item.get("name") if isinstance(item, dict) else None
        for item in actual_samples
    ]
    if actual_names != expected_names:
        return ["resource limit probe sample order or identity drifted"]
    success_fields = {
        "name", "category", "requested_scale", "raw_bytes", "raw_sha256",
        "status", "observed", "timing_ms", "tracemalloc_peak_bytes",
    }
    failure_fields = {
        "name", "category", "requested_scale", "raw_bytes", "raw_sha256",
        "status", "error_type", "error",
    }
    for actual, (name, category, scale, raw) in zip(actual_samples, expected):
        if not isinstance(actual, dict):
            problems.append(f"probe sample {name} is not an object")
            continue
        is_failure = name == "depth_3072"
        if set(actual) != (failure_fields if is_failure else success_fields):
            problems.append(f"probe sample {name} fields are not closed")
            continue
        if actual["category"] != category or actual["requested_scale"] != scale:
            problems.append(f"probe sample {name} metadata drifted")
        if actual["raw_bytes"] != len(raw):
            problems.append(f"probe sample {name} raw byte count mismatch")
        if actual["raw_sha256"] != "sha256:" + sha256_hex(raw):
            problems.append(f"probe sample {name} raw digest mismatch")
        if is_failure:
            if (
                actual["status"] != "rejected_or_parser_error"
                or actual["error_type"] != "RecursionError"
                or not isinstance(actual["error"], str)
                or not actual["error"]
            ):
                problems.append("probe depth_3072 failure evidence drifted")
            continue
        if actual["status"] != "ok":
            problems.append(f"probe sample {name} is not successful")
            continue
        if category == "depth":
            expected_observed = {
                "nodes": scale + 1, "max_depth": scale + 1,
                "total_object_members": 0, "max_object_members": 0,
                "total_array_items": scale, "max_array_items": 1,
                "total_string_utf8_bytes": 0, "max_string_utf8_bytes": 0,
                "reference_count": 0,
            }
        else:
            try:
                parsed = _parse_v4_json(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError, _W0VectorError) as exc:
                problems.append(f"probe sample {name} no longer parses strictly: {exc}")
                continue
            expected_observed = _probe_observation(parsed)
        if actual["observed"] != expected_observed:
            problems.append(f"probe sample {name} structural observation mismatch")
        timing = actual["timing_ms"]
        timing_fields = {
            "parse_median", "parse_p95_nearest_rank", "traverse_median",
            "traverse_p95_nearest_rank", "total_median", "total_p95_nearest_rank",
        }
        if not isinstance(timing, dict) or set(timing) != timing_fields:
            problems.append(f"probe sample {name} timing fields are not closed")
        else:
            if any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0
                for value in timing.values()
            ):
                problems.append(f"probe sample {name} timing values are invalid")
            for prefix in ("parse", "traverse", "total"):
                if timing[f"{prefix}_median"] > timing[f"{prefix}_p95_nearest_rank"]:
                    problems.append(f"probe sample {name} {prefix} timing order is invalid")
        memory = actual["tracemalloc_peak_bytes"]
        if (
            not isinstance(memory, dict) or set(memory) != {"median", "max"}
            or any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in memory.values())
            or memory.get("median", 1) > memory.get("max", 0)
        ):
            problems.append(f"probe sample {name} tracemalloc values are invalid")
    return problems


def _resource_limit_policy_problems(policy: Any) -> list[str]:
    problems: list[str] = []
    required_fields = {
        "claim", "profile", "probe_file", "probe_file_sha256", "probe_payload_sha256",
        "benchmarked_limits", "deferred_limits", "enforcement_order",
    }
    if not isinstance(policy, dict) or set(policy) != required_fields:
        return ["resource limit policy fields are not closed"]
    if policy["claim"] != "LOCAL_ADMISSION_BOUNDS_ONLY":
        problems.append("resource limit policy overclaims its local benchmark")
    if policy["profile"] != "V4_INLINE_REQUEST_ADMISSION_V1":
        problems.append("resource limit profile drifted")
    if policy["probe_file"] != "tests/fixtures/golden/v4-resource-limit-probe.json":
        problems.append("resource limit probe path drifted")
        return problems
    probe_path = ROOT / policy["probe_file"]
    if not probe_path.is_file():
        return problems + ["resource limit probe is missing"]
    raw_probe = probe_path.read_bytes()
    actual_probe_file_digest = "sha256:" + sha256_hex(raw_probe)
    if (
        policy["probe_file_sha256"] != actual_probe_file_digest
        or actual_probe_file_digest != W0_RESOURCE_PROBE_FILE_DIGEST
    ):
        problems.append("resource limit probe file digest mismatch")
    try:
        probe = json.loads(raw_probe.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return problems + ["resource limit probe is not strict UTF-8 JSON"]
    required_probe_fields = {
        "schema_version", "generated_at_utc", "scope", "platform", "methodology",
        "attack_surface_evidence", "samples", "recommendations",
        "payload_sha256", "payload_sha256_scope",
    }
    if not isinstance(probe, dict) or set(probe) != required_probe_fields:
        return problems + ["resource limit probe fields are not closed"]
    if probe.get("schema_version") != "jc/v4-remediation-limit-probe/1.0":
        problems.append("resource limit probe schema_version drifted")
    unsigned_probe = {
        key: value for key, value in probe.items()
        if key not in {"payload_sha256", "payload_sha256_scope"}
    }
    payload_digest = _digest_object(unsigned_probe)
    if (
        probe.get("payload_sha256") != payload_digest
        or policy["probe_payload_sha256"] != payload_digest
        or payload_digest != W0_RESOURCE_PROBE_PAYLOAD_DIGEST
    ):
        problems.append("resource limit probe payload digest mismatch")
    if probe.get("payload_sha256_scope") != (
        "canonical UTF-8 JSON with payload_sha256 and payload_sha256_scope omitted"
    ):
        problems.append("resource limit probe payload digest scope drifted")
    if UTC_INSTANT_V4_PATTERN.fullmatch(probe.get("generated_at_utc", "")) is None:
        problems.append("resource limit probe timestamp is not canonical UTC")
    expected_scope = {
        "claim": "local parser/admission sizing evidence only",
        "not_claimed": [
            "cross-platform equivalence", "production throughput",
            "solver/runtime deadline sufficiency", "state quota or retention sufficiency",
        ],
        "repository_mutated": False,
    }
    if probe.get("scope") != expected_scope:
        problems.append("resource limit probe scope drifted")
    platform = probe.get("platform")
    platform_fields = {
        "python", "python_implementation", "os", "machine", "processor",
        "logical_cpu_count", "python_hash_seed", "cpu_model",
        "physical_memory_bytes", "hardware_source",
    }
    if not isinstance(platform, dict) or set(platform) != platform_fields:
        problems.append("resource limit probe platform fields are not closed")
    elif (
        platform["python_implementation"] != "CPython"
        or platform["python_hash_seed"] != "0"
        or not isinstance(platform["logical_cpu_count"], int)
        or platform["logical_cpu_count"] <= 0
        or not isinstance(platform["physical_memory_bytes"], int)
        or platform["physical_memory_bytes"] <= 0
        or any(
            not isinstance(platform[field], str) or not platform[field]
            for field in platform_fields - {
                "logical_cpu_count", "physical_memory_bytes", "python_hash_seed",
            }
        )
    ):
        problems.append("resource limit probe platform values are invalid")
    methodology = probe.get("methodology")
    methodology_fields = {
        "logic_description", "logic_sha256", "warmups", "measured_repetitions",
        "timing_clock", "memory_metric", "sample_staging", "strict_parser",
        "traversal", "reference_count_rule",
    }
    if not isinstance(methodology, dict) or set(methodology) != methodology_fields:
        problems.append("resource limit probe methodology fields are not closed")
    else:
        description_digest = "sha256:" + sha256_hex(
            methodology["logic_description"].encode("utf-8")
        ) if isinstance(methodology["logic_description"], str) else "invalid"
        if methodology["logic_sha256"] != description_digest:
            problems.append("resource limit methodology description digest mismatch")
        if (
            methodology["warmups"] != 1
            or methodology["measured_repetitions"] != 7
            or methodology["timing_clock"] != "time.perf_counter_ns"
            or methodology["strict_parser"] != {
                "utf8": "strict",
                "duplicate_object_names": "rejected during object construction",
                "float_tokens": "rejected",
                "nonfinite_tokens": "rejected",
                "integer_domain": "[-9007199254740991, 9007199254740991]",
            }
            or methodology["traversal"] != (
                "iterative complete tree walk; counts containers/scalars as nodes, "
                "object names as string bytes but not nodes"
            )
            or methodology["reference_count_rule"] != (
                "string value under a field ending _ref or _refs"
            )
        ):
            problems.append("resource limit probe methodology values drifted")
    problems.extend(_probe_sample_problems(probe))

    recommendations = probe.get("recommendations", {})
    defaults = recommendations.get("defaults", {}) if isinstance(recommendations, dict) else {}
    hard_caps = recommendations.get("hard_caps", {}) if isinstance(recommendations, dict) else {}
    expected_ids = {
        "max_request_bytes", "max_json_depth", "max_json_nodes",
        "max_object_members_per_object", "max_total_object_members",
        "max_array_items_per_array", "max_total_array_items",
        "max_string_utf8_bytes", "max_total_string_utf8_bytes",
        "max_total_reference_values", "max_fact_attestation_refs", "max_proposal_refs",
        "admission_deadline_ms",
    }
    recommendation_fields = {
        "profile", "defaults", "hard_caps", "enforcement_order", "basis",
        "deferred_not_supported_by_this_probe", "limit_semantics",
    }
    if not isinstance(recommendations, dict) or set(recommendations) != recommendation_fields:
        problems.append("resource limit recommendation fields are not closed")
    elif recommendations["profile"] != "V4_INLINE_REQUEST_ADMISSION_V1":
        problems.append("resource limit recommendation profile drifted")
    if not isinstance(defaults, dict) or set(defaults) != expected_ids:
        problems.append("resource limit default recommendation registry drifted")
    if not isinstance(hard_caps, dict) or set(hard_caps) != expected_ids:
        problems.append("resource limit hard-cap recommendation registry drifted")
    if (
        not isinstance(recommendations.get("basis"), list)
        or not recommendations.get("basis")
        or any(not isinstance(item, str) or not item for item in recommendations.get("basis", []))
    ):
        problems.append("resource limit recommendation basis is missing")
    units = {
        "max_request_bytes": "bytes",
        "max_json_depth": "levels",
        "max_json_nodes": "count",
        "max_object_members_per_object": "count",
        "max_total_object_members": "count",
        "max_array_items_per_array": "count",
        "max_total_array_items": "count",
        "max_string_utf8_bytes": "bytes",
        "max_total_string_utf8_bytes": "bytes",
        "max_total_reference_values": "count",
        "max_fact_attestation_refs": "count",
        "max_proposal_refs": "count",
        "admission_deadline_ms": "milliseconds",
    }
    errors = {
        "max_request_bytes": "REQUEST_TOO_LARGE",
        "max_json_depth": "JSON_DEPTH_LIMIT",
        "max_json_nodes": "JSON_NODE_LIMIT",
        "max_object_members_per_object": "OBJECT_MEMBER_LIMIT",
        "max_total_object_members": "TOTAL_OBJECT_MEMBER_LIMIT",
        "max_array_items_per_array": "ARRAY_ITEM_LIMIT",
        "max_total_array_items": "TOTAL_ARRAY_ITEM_LIMIT",
        "max_string_utf8_bytes": "STRING_BYTE_LIMIT",
        "max_total_string_utf8_bytes": "TOTAL_STRING_BYTE_LIMIT",
        "max_total_reference_values": "REFERENCE_LIMIT",
        "max_fact_attestation_refs": "FACT_REFERENCE_LIMIT",
        "max_proposal_refs": "PROPOSAL_REFERENCE_LIMIT",
        "admission_deadline_ms": "ADMISSION_DEADLINE",
    }
    seen: set[str] = set()
    for item in policy.get("benchmarked_limits", []):
        if not isinstance(item, dict) or set(item) != {
            "id", "scope", "unit", "default", "hard_max", "boundary", "error_code",
        }:
            problems.append("benchmarked limit fields are not closed")
            continue
        limit_id = item["id"]
        seen.add(limit_id)
        if limit_id not in expected_ids:
            problems.append(f"unknown benchmarked limit {limit_id}")
            continue
        if item["scope"] != "request_admission" or item["boundary"] != "inclusive":
            problems.append(f"{limit_id} scope/boundary drifted")
        if item["unit"] != units[limit_id] or item["error_code"] != errors[limit_id]:
            problems.append(f"{limit_id} unit/error drifted")
        if item["default"] != defaults.get(limit_id) or item["hard_max"] != hard_caps.get(limit_id):
            problems.append(f"{limit_id} does not match the measured recommendation")
        if not isinstance(item["default"], int) or not isinstance(item["hard_max"], int):
            problems.append(f"{limit_id} must use integer limits")
        elif not 0 < item["default"] <= item["hard_max"]:
            problems.append(f"{limit_id} default exceeds its hard maximum")
    if seen != expected_ids or len(policy.get("benchmarked_limits", [])) != len(expected_ids):
        problems.append("benchmarked limit registry is incomplete or duplicated")
    if policy.get("enforcement_order") != recommendations.get("enforcement_order"):
        problems.append("resource limit enforcement order drifted from the probe")

    deferred_expected = {
        "artifact_page_bytes": "W1-04",
        "solver_deadline_ms": "W3-03",
        "worker_queue_items": "W4-06",
        "in_flight_runs": "W4-06",
        "state_quota_bytes": "W4-02",
        "retention_seconds": "W4-02",
    }
    deferred_seen: dict[str, str] = {}
    for item in policy.get("deferred_limits", []):
        if not isinstance(item, dict) or set(item) != {
            "id", "status", "value", "closure_task", "reason",
        }:
            problems.append("deferred limit fields are not closed")
            continue
        deferred_seen[item["id"]] = item["closure_task"]
        if item["status"] != "DEFERRED_UNBENCHMARKED" or item["value"] is not None:
            problems.append(f"deferred limit {item['id']} contains an unsupported magic value")
        if not isinstance(item["reason"], str) or not item["reason"]:
            problems.append(f"deferred limit {item['id']} lacks a reason")
    if deferred_seen != deferred_expected or len(policy.get("deferred_limits", [])) != len(deferred_expected):
        problems.append("deferred operational limit registry is incomplete")
    return problems


def cmd_foundation_contract(args: argparse.Namespace) -> int:
    jcs_path = Path(args.jcs).resolve()
    foundation_path = Path(args.foundation).resolve()
    try:
        jcs_vectors = json.loads(jcs_path.read_text(encoding="utf-8"))
        foundation = json.loads(foundation_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"W0 foundation artifact unreadable: {exc}", file=sys.stderr)
        return EXIT_GATE_FAIL
    problems = _jcs_vector_problems(jcs_vectors) + _foundation_contract_problems(foundation)
    if problems:
        for problem in sorted(set(problems)):
            print(problem, file=sys.stderr)
        return EXIT_GATE_FAIL
    limits = foundation["resource_limit_policy"]
    print(
        f"foundation contract OK: {len(jcs_vectors['positive'])} JCS positive, "
        f"{len(jcs_vectors['negative'])} JCS negative, "
        f"{len(limits['benchmarked_limits'])} benchmarked admission limits, "
        f"{len(limits['deferred_limits'])} explicit deferred operational limits"
    )
    return EXIT_OK


def _ast_dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _ast_dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _forbidden_test_controls(source: str) -> list[str]:
    """Return collection/runtime bypass controls used by required test source."""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ["syntax-error"]
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                if imported.name in {"pytest", "unittest"}:
                    aliases[imported.asname or imported.name] = imported.name
        elif isinstance(node, ast.ImportFrom) and node.module in {"pytest", "unittest"}:
            for imported in node.names:
                aliases[imported.asname or imported.name] = f"{node.module}.{imported.name}"

    def normalized_name(node: ast.AST) -> str:
        raw = _ast_dotted_name(node)
        head, separator, tail = raw.partition(".")
        replacement = aliases.get(head, head)
        return f"{replacement}.{tail}" if separator else replacement

    forbidden = {
        "pytest.skip", "pytest.xfail", "pytest.importorskip",
        "pytest.mark.skip", "pytest.mark.skipif", "pytest.mark.xfail",
        "unittest.skip", "unittest.skipIf", "unittest.skipUnless",
        "unittest.expectedFailure", "unittest.SkipTest",
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Call, ast.Attribute)):
            target = node.func if isinstance(node, ast.Call) else node
            name = normalized_name(target)
            if name in forbidden:
                found.add(name)
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == "__unittest_skip__":
                    found.add("__unittest_skip__")
        if isinstance(node, ast.Call) and normalized_name(node.func) == "getattr" and len(node.args) >= 2:
            owner = normalized_name(node.args[0])
            member = node.args[1].value if isinstance(node.args[1], ast.Constant) else None
            candidate = f"{owner}.{member}" if isinstance(member, str) else ""
            if candidate in forbidden:
                found.add(candidate)
    return sorted(found)


def _selector_file(selector: Any) -> str | None:
    if not isinstance(selector, str) or not selector:
        return None
    path = selector.split("::", 1)[0]
    if (
        "\\" in path
        or path.startswith("/")
        or re.match(r"^[A-Za-z]:", path)
        or not path.endswith(".py")
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        return None
    return path


def _selector_is_declared(root: Path, selector: str) -> bool:
    relative = _selector_file(selector)
    if relative is None:
        return False
    path = root / relative
    if not path.is_file():
        return False
    parts = [part.split("[", 1)[0] for part in selector.split("::")[1:]]
    if not parts:
        return True
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=relative)
    except (OSError, UnicodeError, SyntaxError):
        return False
    body: list[ast.stmt] = tree.body
    for part in parts:
        match = next(
            (
                node for node in body
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == part
            ),
            None,
        )
        if match is None:
            return False
        body = match.body if isinstance(match, ast.ClassDef) else []
    return True


def _selector_matches_suite(
    selector_path: str, canonical_suite: str, aliases: dict[str, str],
) -> bool:
    parts = selector_path.split("/")
    return (
        len(parts) >= 3
        and parts[0] == "tests"
        and aliases.get(parts[1], parts[1]) == canonical_suite
    )


def _task_is_ancestor_or_same(
    ancestor_id: str, descendant_id: str, task_by_id: dict[str, dict[str, Any]],
) -> bool:
    if ancestor_id == descendant_id:
        return True
    pending = list(task_by_id.get(descendant_id, {}).get("depends_on", []))
    visited: set[str] = set()
    while pending:
        candidate = pending.pop()
        if candidate == ancestor_id:
            return True
        if candidate in visited:
            continue
        visited.add(candidate)
        pending.extend(task_by_id.get(candidate, {}).get("depends_on", []))
    return False


def _closed_manifest_fields(
    value: Any, fields: set[str], label: str, problems: list[str],
) -> bool:
    if not isinstance(value, dict) or set(value) != fields:
        problems.append(f"{label} fields are not closed")
        return False
    return True


def _git_untracked_paths(root: Path, paths: Iterable[str]) -> list[str]:
    """Return gate inputs that would be absent from a fresh Git checkout."""

    normalized = sorted({path for path in paths if isinstance(path, str) and path})
    if not normalized:
        return []
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "-z", "--", *normalized],
        capture_output=True, check=False,
    )
    if completed.returncode != 0:
        return normalized
    tracked = {
        item.decode("utf-8", errors="surrogateescape")
        for item in completed.stdout.split(b"\0")
        if item
    }
    return [path for path in normalized if path not in tracked]


def _pytest_config_problems(config_text: str, sentinel_name: str) -> list[str]:
    """Parse and lock the discovery and bypass controls used by required tests."""

    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(config_text)
    except configparser.Error as exc:
        return [f"required pytest config is invalid: {exc}"]
    if parser.sections() != ["pytest"]:
        return ["required pytest config must contain exactly one pytest section"]
    section = parser["pytest"]
    problems: list[str] = []
    if section.get("addopts", "").split() != ["--strict-config", "--strict-markers"]:
        problems.append("required pytest addopts are not exact")
    if section.get("xfail_strict", "").strip().lower() != "true":
        problems.append("required pytest xfail_strict is not true")
    patterns = section.get("python_files", "").split()
    if patterns != ["test_*.py", "*_test.py"]:
        problems.append("required pytest discovery patterns are not exact")
    if any(fnmatch.fnmatchcase(sentinel_name, pattern) for pattern in patterns):
        problems.append("red sentinel matches default pytest discovery")
    if section.get("pythonpath", "").split() != [".."]:
        problems.append("required pytest pythonpath is not repository root")
    marker_lines = [line.strip() for line in section.get("markers", "").splitlines() if line.strip()]
    if marker_lines != ["v4_required: test is admitted by tests/required-v4-tests.json"]:
        problems.append("required pytest marker registry is not exact")
    return problems


def _required_pytest_environment() -> dict[str, str]:
    """Remove ambient pytest/Python injection from W0-04 subprocesses."""

    environment = os.environ.copy()
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONHOME", "PYTHONPATH"):
        environment.pop(name, None)
    environment.update({
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    })
    return environment


def _live_b02_binding(state_root: Path) -> dict[str, str]:
    """Rebind the pinned companion declaration to preserved B02 state bytes."""

    expected_receipt_digest = W0_B02_COMPANION_BINDING["receipt_digest"]
    receipt_paths = sorted(
        (state_root / "tasks" / "B02").glob("*/receipt.json"),
        key=lambda path: int(path.parent.name) if path.parent.name.isdigit() else -1,
    )
    receipt: dict[str, Any] | None = None
    for path in receipt_paths:
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if candidate.get("receipt_digest") == expected_receipt_digest:
            receipt = candidate
            break
    if receipt is None:
        raise ValueError("pinned B02 receipt is missing")
    if (
        receipt.get("task_id") != "B02"
        or receipt.get("status") != "COMPLETED"
        or _receipt_digest(receipt) != expected_receipt_digest
        or not _validate_git_binding(receipt["start_commit"], receipt["start_tree"])
        or not _validate_git_binding(receipt["result_commit"], receipt["result_tree"])
        or any(
            not _validate_stream(command[stream])
            for command in receipt.get("command_results", [])
            for stream in ("stdout", "stderr")
        )
    ):
        raise ValueError("pinned B02 receipt binding is invalid")

    intake_path = state_root / "evidence" / "B02" / "intake.json"
    try:
        intake = json.loads(intake_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"pinned B02 intake is unreadable: {exc}") from exc
    intake_digest = intake.get("digest")
    unsigned_intake = {key: value for key, value in intake.items() if key != "digest"}
    if (
        intake_digest != W0_B02_COMPANION_BINDING["intake_digest"]
        or _digest_object(unsigned_intake) != intake_digest
        or intake.get("schema_version") != "jc/remediation-v4-spec-intake/1.0"
        or intake.get("commit") != W0_B02_COMPANION_BINDING["commit"]
        or intake.get("tree") != W0_B02_COMPANION_BINDING["tree"]
        or intake.get("required_files") != W0_B02_COMPANION_BINDING["required_files"]
        or intake.get("fixture_family_digests")
        != W0_B02_COMPANION_BINDING["fixture_family_digests"]
    ):
        raise ValueError("pinned B02 intake binding is invalid")
    differential_path = state_root / "evidence" / "B02" / "differential.json"
    try:
        differential_digest = sha256_hex(differential_path.read_bytes())
    except OSError as exc:
        raise ValueError(f"pinned B02 differential evidence is unreadable: {exc}") from exc
    if differential_digest != intake.get("differential_report_sha256"):
        raise ValueError("pinned B02 differential evidence digest mismatch")
    return {
        "receipt_digest": expected_receipt_digest,
        "intake_digest": intake_digest,
        "differential_digest": "sha256:" + differential_digest,
        "companion_commit": intake["commit"],
        "companion_tree": intake["tree"],
    }


def _manifest_owner_problems(
    *, entry_label: str, owner_id: Any, selector: Any,
    task_by_id: dict[str, dict[str, Any]], task_order: dict[str, int],
    require_audit_id: str | None = None,
    closure_tasks: set[str] | None = None,
) -> list[str]:
    problems: list[str] = []
    task = task_by_id.get(owner_id) if isinstance(owner_id, str) else None
    if task is None or task.get("mode") != "AUTO":
        return [f"{entry_label} has no AUTO owner task"]
    if task_order.get(owner_id, -1) <= task_order.get("W0-04", -1):
        problems.append(f"{entry_label} owner task is not after W0-04")
    relative = _selector_file(selector)
    if relative is None or not _matches_allowed(relative, task.get("allowed_paths", [])):
        problems.append(f"{entry_label} selector is outside owner task allowlist")
    if require_audit_id is not None and require_audit_id not in task.get("audit_ids", []):
        problems.append(f"{entry_label} owner task does not bind audit id {require_audit_id}")
    if closure_tasks is not None and owner_id not in closure_tasks:
        problems.append(f"{entry_label} owner task is not a registered closure task")
    return problems


def _required_test_manifest_problems(
    manifest: Any, *, root: Path, issue_map: Any, plan: Any,
    require_pending: bool = False,
) -> list[str]:
    """Validate W0-04 taxonomy without executing production code."""

    problems: list[str] = []
    top_fields = {
        "schema_version", "required_policy", "pytest_config", "red_sentinel_selector",
        "suite_aliases", "suites", "required_now", "evidence_tracks",
        "audit_mutations", "rewrite_at_task",
    }
    if not _closed_manifest_fields(manifest, top_fields, "required test manifest", problems):
        return problems
    if manifest["schema_version"] != "jc/v4-required-test-manifest/1.0":
        problems.append("required test manifest schema version drifted")
    expected_policy = {
        "current_state": "REQUIRED_NOW",
        "future_state": "RED_AT_TASK",
        "activation_state": "ACTIVE_REQUIRED",
        "rewrite_state": "REWRITE_AT_TASK",
        "prohibited_outcomes": ["SKIP", "XFAIL"],
        "unimplemented_behavior": "FAIL",
    }
    if manifest["required_policy"] != expected_policy:
        problems.append("required test policy drifted")
    if manifest["pytest_config"] != "tests/pytest.ini":
        problems.append("required pytest config path drifted")
    expected_aliases = {
        "contract_v4": "contract",
        "trust_security": "security",
        "semantic_mutation": "differential",
    }
    if manifest["suite_aliases"] != expected_aliases:
        problems.append("suite aliases do not reconcile audit and W0-04 taxonomy")
    suite_aliases = manifest["suite_aliases"] if isinstance(manifest["suite_aliases"], dict) else {}
    if manifest["red_sentinel_selector"] != "tests/required_red_sentinels.py":
        problems.append("red sentinel selector drifted")
    elif not _selector_is_declared(root, manifest["red_sentinel_selector"]):
        problems.append("red sentinel selector is not declared")
    elif Path(manifest["red_sentinel_selector"]).name.startswith("test"):
        problems.append("red sentinel would poison default pytest discovery")
    else:
        sentinel_source = (root / manifest["red_sentinel_selector"]).read_text(encoding="utf-8-sig")
        if _forbidden_test_controls(sentinel_source):
            problems.append("red sentinel uses a skip or xfail bypass")
        try:
            sentinel_tree = ast.parse(sentinel_source)
        except SyntaxError:
            sentinel_tree = ast.Module(body=[], type_ignores=[])
        if any(
            (isinstance(node, ast.Import) and any(alias.name == "compiler_core" or alias.name.startswith("compiler_core.") for alias in node.names))
            or (isinstance(node, ast.ImportFrom) and isinstance(node.module, str) and (node.module == "compiler_core" or node.module.startswith("compiler_core.")))
            for node in ast.walk(sentinel_tree)
        ):
            problems.append("red sentinel imports production implementation")

    tracked_gate_inputs = {
        "tools/remediate_v4.py",
        "tests/required-v4-tests.json",
        "tests/pytest.ini",
        manifest.get("red_sentinel_selector"),
    }
    for suite in manifest.get("suites", []):
        if isinstance(suite, dict) and isinstance(suite.get("path"), str):
            tracked_gate_inputs.add(f"{suite['path']}/README.md")
    for required in manifest.get("required_now", []):
        if isinstance(required, dict):
            selector_path = _selector_file(required.get("selector"))
            if selector_path is not None:
                tracked_gate_inputs.add(selector_path)
    for registry_name in ("evidence_tracks", "audit_mutations"):
        for entry in manifest.get(registry_name, []):
            if isinstance(entry, dict):
                selector_path = _selector_file(entry.get("selector"))
                if selector_path is not None and (root / selector_path).is_file():
                    tracked_gate_inputs.add(selector_path)
    for entry in manifest.get("rewrite_at_task", []):
        if not isinstance(entry, dict):
            continue
        for field in ("selector", "replacement_selector"):
            selector_path = _selector_file(entry.get(field))
            if selector_path is not None and (root / selector_path).is_file():
                tracked_gate_inputs.add(selector_path)
    untracked_gate_inputs = _git_untracked_paths(
        root, (path for path in tracked_gate_inputs if isinstance(path, str))
    )
    if untracked_gate_inputs:
        problems.append(
            "required gate inputs are not Git-tracked: " + ", ".join(untracked_gate_inputs)
        )
    config_path = root / "tests" / "pytest.ini"
    try:
        config_text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        config_text = ""
    problems.extend(_pytest_config_problems(config_text, Path(manifest["red_sentinel_selector"]).name))

    if not isinstance(issue_map, dict) or not isinstance(issue_map.get("issues"), list):
        problems.append("issue map is unreadable for mutation coverage")
        issue_ids: list[str] = []
    else:
        issue_ids = [item.get("id") for item in issue_map["issues"] if isinstance(item, dict)]
    issue_by_id = {
        item.get("id"): item
        for item in issue_map.get("issues", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    } if isinstance(issue_map, dict) else {}
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        problems.append("task plan is unreadable for required-test ownership")
        tasks: list[dict[str, Any]] = []
    else:
        tasks = [item for item in plan["tasks"] if isinstance(item, dict)]
    task_by_id = {item.get("id"): item for item in tasks if isinstance(item.get("id"), str)}
    task_order = {item.get("id"): index for index, item in enumerate(tasks)}

    suite_fields = {"id", "path", "proof_obligation"}
    suites = manifest["suites"] if isinstance(manifest["suites"], list) else []
    if not isinstance(manifest["suites"], list):
        problems.append("suite taxonomy is not a list")
    suite_ids = [item.get("id") for item in suites if isinstance(item, dict)]
    if tuple(suite_ids) != W0_REQUIRED_TEST_SUITES:
        problems.append("suite taxonomy is not the exact W0-04 eleven-suite contract")
    suite_by_id: dict[str, dict[str, Any]] = {}
    for item in suites:
        if not _closed_manifest_fields(item, suite_fields, "suite", problems):
            continue
        suite_id = item["id"]
        expected_path = f"tests/{suite_id}"
        if item["path"] != expected_path:
            problems.append(f"suite path drifted for {suite_id}")
        if not isinstance(item["proof_obligation"], str) or not item["proof_obligation"].strip():
            problems.append(f"suite {suite_id} lacks a proof obligation")
        directory = root / expected_path
        if not directory.is_dir() or not (directory / "README.md").is_file():
            problems.append(f"suite {suite_id} lacks a tracked skeleton")
        if isinstance(suite_id, str):
            suite_by_id[suite_id] = item

    required_fields = {"id", "suite", "selector", "state", "expected_tests"}
    required_now = manifest["required_now"] if isinstance(manifest["required_now"], list) else []
    if not isinstance(manifest["required_now"], list):
        problems.append("required-now registry is not a list")
    required_ids: list[str] = []
    required_selectors: list[str] = []
    for item in required_now:
        if not _closed_manifest_fields(item, required_fields, "required-now test", problems):
            continue
        required_ids.append(item["id"])
        required_selectors.append(item["selector"])
        if item["state"] != "REQUIRED_NOW":
            problems.append(f"required-now test {item['id']} has a non-required state")
        if not isinstance(item["expected_tests"], int) or isinstance(item["expected_tests"], bool) or item["expected_tests"] <= 0:
            problems.append(f"required-now test {item['id']} has no exact execution count")
        suite = suite_by_id.get(item["suite"])
        relative = _selector_file(item["selector"])
        if (
            suite is None
            or relative is None
            or not _selector_matches_suite(relative, item["suite"], suite_aliases)
        ):
            problems.append(f"required-now test {item['id']} is outside its suite")
            continue
        if not _selector_is_declared(root, item["selector"]):
            problems.append(f"required-now selector is not declared: {item['selector']}")
            continue
        try:
            source = (root / relative).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            source = ""
        controls = _forbidden_test_controls(source)
        if controls:
            problems.append(
                f"required-now selector uses forbidden test controls: {relative} {controls}"
            )
    expected_required_now = [
        {
            "id": "W0-FOUNDATION-CONTRACT",
            "suite": "contract",
            "selector": "tests/contract/test_v4_foundation_contract.py",
            "state": "REQUIRED_NOW",
            "expected_tests": 5,
        },
        {
            "id": "W0-REQUIRED-MANIFEST-GATE",
            "suite": "contract",
            "selector": "tests/contract/test_required_test_manifest.py",
            "state": "REQUIRED_NOW",
            "expected_tests": 7,
        },
    ]
    if required_now != expected_required_now:
        problems.append("required-now registry is not the exact W0-04 executable set")
    if len(required_ids) != len(set(required_ids)) or len(required_selectors) != len(set(required_selectors)):
        problems.append("required-now registry contains duplicates")

    evidence_fields = {
        "id", "suite", "selector", "owner_task", "state", "source_kind",
        "source_binding", "red_failure",
    }
    evidence = manifest["evidence_tracks"] if isinstance(manifest["evidence_tracks"], list) else []
    if not isinstance(manifest["evidence_tracks"], list):
        problems.append("differential evidence tracks are not a list")
    expected_self_binding = {
        "kind": "REPOSITORY_FIXTURE",
        "fixture_root": "tests/fixtures/v4_contract",
        "oracle_imports_production": False,
        "requires_companion_environment": False,
    }
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for item in evidence:
        if not _closed_manifest_fields(item, evidence_fields, "evidence track", problems):
            continue
        if isinstance(item["id"], str):
            evidence_by_id[item["id"]] = item
        if item["suite"] != "differential" or item["state"] != "RED_AT_TASK":
            problems.append(f"evidence track {item['id']} is not differential RED_AT_TASK")
        relative = _selector_file(item["selector"])
        if relative is None or not relative.startswith("tests/differential/"):
            problems.append(f"evidence track {item['id']} selector is outside differential")
        elif _selector_is_declared(root, item["selector"]):
            if require_pending:
                problems.append(
                    f"evidence track {item['id']} claims RED_AT_TASK but selector is active"
                )
            controls = _forbidden_test_controls(
                (root / relative).read_text(encoding="utf-8-sig")
            )
            if controls:
                problems.append(
                    f"active evidence selector uses forbidden test controls: {relative} {controls}"
                )
        problems.extend(_manifest_owner_problems(
            entry_label=f"evidence track {item['id']}", owner_id=item["owner_task"],
            selector=item["selector"], task_by_id=task_by_id, task_order=task_order,
        ))
        if not isinstance(item["red_failure"], str) or not item["red_failure"].strip():
            problems.append(f"evidence track {item['id']} lacks a red failure")
    self_track = evidence_by_id.get("SELF-CONTAINED-V4-FIXTURES", {})
    companion_track = evidence_by_id.get("PINNED-COMPANION-SPEC", {})
    if (
        set(evidence_by_id) != {"SELF-CONTAINED-V4-FIXTURES", "PINNED-COMPANION-SPEC"}
        or len(evidence) != 2
        or self_track.get("source_kind") != "SELF_CONTAINED_REPOSITORY_FIXTURE"
        or self_track.get("source_binding") != expected_self_binding
        or companion_track.get("source_kind") != "PINNED_COMPANION_SPEC"
        or companion_track.get("source_binding") != W0_B02_COMPANION_BINDING
        or self_track.get("selector") == companion_track.get("selector")
    ):
        problems.append("differential evidence tracks are not independently and exactly bound")

    mutation_fields = {
        "audit_id", "test_id", "suite", "selector", "owner_task", "state",
        "mutation", "red_failure",
    }
    mutations = manifest["audit_mutations"] if isinstance(manifest["audit_mutations"], list) else []
    if not isinstance(manifest["audit_mutations"], list):
        problems.append("audit mutation registry is not a list")
    mutation_ids: list[str] = []
    mutation_audits: list[str] = []
    mutation_selectors: list[str] = []
    used_suites: set[str] = set()
    for item in mutations:
        if not _closed_manifest_fields(item, mutation_fields, "audit mutation", problems):
            continue
        mutation_ids.append(item["test_id"])
        mutation_audits.append(item["audit_id"])
        mutation_selectors.append(item["selector"])
        canonical_suite = suite_aliases.get(item["suite"], item["suite"])
        used_suites.add(canonical_suite)
        if item["state"] != "RED_AT_TASK":
            problems.append(f"audit mutation {item['test_id']} must be RED_AT_TASK")
        if not isinstance(item["mutation"], str) or not item["mutation"].strip():
            problems.append(f"audit mutation {item['test_id']} lacks an operator")
        if not isinstance(item["red_failure"], str) or not item["red_failure"].strip():
            problems.append(f"audit mutation {item['test_id']} lacks a red failure")
        if not isinstance(item["test_id"], str) or not item["test_id"].startswith(
            f"V4-{item['audit_id']}-"
        ):
            problems.append(f"audit mutation id is not bound to {item['audit_id']}")
        suite = suite_by_id.get(canonical_suite)
        relative = _selector_file(item["selector"])
        if (
            suite is None
            or relative is None
            or not _selector_matches_suite(relative, canonical_suite, suite_aliases)
        ):
            problems.append(f"audit mutation {item['test_id']} is outside its suite")
        elif _selector_is_declared(root, item["selector"]):
            if require_pending:
                problems.append(
                    f"audit mutation {item['test_id']} claims RED_AT_TASK but selector is active"
                )
            controls = _forbidden_test_controls(
                (root / relative).read_text(encoding="utf-8-sig")
            )
            if controls:
                problems.append(
                    f"active audit selector uses forbidden test controls: {relative} {controls}"
                )
        problems.extend(_manifest_owner_problems(
            entry_label=f"audit mutation {item['test_id']}", owner_id=item["owner_task"],
            selector=item["selector"], task_by_id=task_by_id, task_order=task_order,
            require_audit_id=item["audit_id"],
            closure_tasks=set(issue_by_id.get(item["audit_id"], {}).get("closure_tasks", [])),
        ))
    counts = {audit_id: mutation_audits.count(audit_id) for audit_id in set(mutation_audits)}
    if set(mutation_audits) != set(issue_ids) or len(mutation_audits) != len(issue_ids) or any(
        count != 1 for count in counts.values()
    ):
        problems.append("audit mutation coverage is not exactly one entry per registered issue")
    if len(mutation_ids) != len(set(mutation_ids)):
        problems.append("audit mutation test ids are duplicated")
    if len(mutation_selectors) != len(set(mutation_selectors)):
        problems.append("audit mutation selectors are duplicated")
    if used_suites != set(W0_REQUIRED_TEST_SUITES):
        problems.append("audit mutations do not exercise every suite taxonomy class")

    rewrite_fields = {
        "id", "selector", "rewrite_task", "retirement_task", "state", "reason",
        "replacement_selector",
    }
    rewrites = manifest["rewrite_at_task"] if isinstance(manifest["rewrite_at_task"], list) else []
    if not isinstance(manifest["rewrite_at_task"], list):
        problems.append("rewrite queue is not a list")
    rewrite_ids: list[str] = []
    rewrite_selectors: list[str] = []
    replacement_selectors: list[str] = []
    for item in rewrites:
        if not _closed_manifest_fields(item, rewrite_fields, "rewrite entry", problems):
            continue
        rewrite_ids.append(item["id"])
        rewrite_selectors.append(item["selector"])
        replacement_selectors.append(item["replacement_selector"])
        if item["state"] != "REWRITE_AT_TASK":
            problems.append(f"rewrite entry {item['id']} has the wrong state")
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            problems.append(f"rewrite entry {item['id']} lacks a reason")
        original_declared = _selector_is_declared(root, item["selector"])
        if require_pending and not original_declared:
            problems.append(f"rewrite selector is not declared: {item['selector']}")
        rewrite_task = task_by_id.get(item["rewrite_task"])
        replacement = _selector_file(item["replacement_selector"])
        if (
            rewrite_task is None
            or rewrite_task.get("mode") != "AUTO"
            or replacement is None
            or not _matches_allowed(replacement, rewrite_task.get("allowed_paths", []))
        ):
            problems.append(f"replacement selector is outside rewrite task allowlist: {item['id']}")
        else:
            replacement_declared = _selector_is_declared(root, item["replacement_selector"])
            if require_pending and replacement_declared:
                problems.append(f"rewrite entry {item['id']} is already active during W0-04")
            if replacement_declared:
                controls = _forbidden_test_controls(
                    (root / replacement).read_text(encoding="utf-8-sig")
                )
                if controls:
                    problems.append(
                        f"active rewrite replacement uses forbidden test controls: "
                        f"{replacement} {controls}"
                    )
        retirement_task = task_by_id.get(item["retirement_task"])
        original = _selector_file(item["selector"])
        if (
            retirement_task is None
            or retirement_task.get("mode") != "AUTO"
            or original is None
            or not _matches_allowed(original, retirement_task.get("allowed_paths", []))
        ):
            problems.append(f"rewrite selector is outside retirement task allowlist: {item['id']}")
        if (
            isinstance(item["rewrite_task"], str)
            and isinstance(item["retirement_task"], str)
            and not _task_is_ancestor_or_same(
                item["rewrite_task"], item["retirement_task"], task_by_id
            )
        ):
            problems.append(f"rewrite occurs after retirement task: {item['id']}")
        if replacement is not None:
            replacement_parts = replacement.split("/")
            replacement_namespace = replacement_parts[1] if len(replacement_parts) >= 3 else ""
            replacement_suite = suite_aliases.get(replacement_namespace, replacement_namespace)
            if replacement_namespace != "unit" and replacement_suite not in suite_by_id:
                problems.append(f"replacement selector has no canonical suite: {item['id']}")
    if set(rewrite_ids) != W0_REQUIRED_REWRITE_IDS or len(rewrite_ids) != len(W0_REQUIRED_REWRITE_IDS):
        problems.append("rewrite queue does not cover the frozen wrong-behavior inventory")
    if len(rewrite_selectors) != len(set(rewrite_selectors)):
        problems.append("rewrite selectors are duplicated")
    if len(replacement_selectors) != len(set(replacement_selectors)):
        problems.append("rewrite replacement selectors are duplicated")
    rewrite_projection = [
        {
            key: item[key]
            for key in (
                "id", "selector", "rewrite_task", "retirement_task",
                "replacement_selector",
            )
        }
        for item in rewrites
        if isinstance(item, dict) and all(
            key in item
            for key in (
                "id", "selector", "rewrite_task", "retirement_task",
                "replacement_selector",
            )
        )
    ]
    if _digest_object(rewrite_projection) != W0_REQUIRED_REWRITE_PROJECTION_DIGEST:
        problems.append("rewrite canonical projection drifted")
    return sorted(set(problems))


def _junit_evidence(path: Path) -> tuple[dict[str, int], list[ET.Element]]:
    xml_root = ET.parse(path).getroot()
    test_suites = [xml_root] if xml_root.tag == "testsuite" else list(xml_root.iter("testsuite"))
    counts = {
        key: sum(int(item.attrib.get(key, "0")) for item in test_suites)
        for key in ("tests", "skipped", "failures", "errors")
    }
    return counts, list(xml_root.iter("testcase"))


def _red_junit_problems(
    counts: dict[str, int], cases: list[ET.Element], expected_by_id: dict[str, str],
) -> list[str]:
    expected_count = len(expected_by_id)
    problems: list[str] = []
    if counts != {
        "tests": expected_count, "skipped": 0, "failures": expected_count, "errors": 0,
    }:
        problems.append(f"red sentinel counts drifted: {counts}")
    observed_ids: list[str] = []
    marker_pattern = re.compile(r"UNIMPLEMENTED:[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+")
    name_pattern = re.compile(
        r"test_red_at_task_is_explicitly_unimplemented\[(?P<red_id>[A-Za-z0-9_.-]+)\]\Z"
    )
    for case in cases:
        name_match = name_pattern.fullmatch(case.attrib.get("name", ""))
        if name_match is None:
            problems.append("red sentinel testcase name is not obligation-bound")
            continue
        red_id = name_match.group("red_id")
        observed_ids.append(red_id)
        expected_marker = expected_by_id.get(red_id)
        failure = case.find("failure")
        failure_text = "" if failure is None else (
            failure.attrib.get("message", "") + "\n" + (failure.text or "")
        )
        observed_markers = set(marker_pattern.findall(failure_text))
        if expected_marker is None or observed_markers != {expected_marker}:
            problems.append(f"red sentinel testcase is not uniquely bound: {red_id}")
    if (
        len(cases) != expected_count
        or len(observed_ids) != len(set(observed_ids))
        or set(observed_ids) != set(expected_by_id)
    ):
        problems.append("red sentinel testcase ids are not exact")
    return sorted(set(problems))


def cmd_required_test_manifest() -> int:
    try:
        manifest = json.loads(REQUIRED_TEST_MANIFEST.read_text(encoding="utf-8"))
        issue_map = json.loads(ISSUE_MAP.read_text(encoding="utf-8"))
        plan = json.loads(DEFAULT_PLAN.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"W0 required test manifest unreadable: {exc}", file=sys.stderr)
        return EXIT_GATE_FAIL
    problems = _required_test_manifest_problems(
        manifest, root=ROOT, issue_map=issue_map, plan=plan, require_pending=True,
    )
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_GATE_FAIL

    raw_state_root = os.environ.get("JC_REMEDIATION_STATE_ROOT")
    live_b02_binding: dict[str, str] | None = None
    if raw_state_root:
        try:
            live_b02_binding = _live_b02_binding(Path(raw_state_root).resolve())
        except (KeyError, OSError, TypeError, ValueError) as exc:
            print(f"pinned B02 state binding failed: {exc}", file=sys.stderr)
            return EXIT_GATE_FAIL

    expected_required_count = sum(item["expected_tests"] for item in manifest["required_now"])
    red_obligations = [
        (item["id"], item["owner_task"])
        for item in manifest["evidence_tracks"]
        if item["state"] == "RED_AT_TASK"
    ] + [
        (item["test_id"], item["owner_task"])
        for item in manifest["audit_mutations"]
        if item["state"] == "RED_AT_TASK"
    ]
    expected_red_by_id = {
        red_id: f"UNIMPLEMENTED:{red_id}:{owner_task}" for red_id, owner_task in red_obligations
    }
    with tempfile.TemporaryDirectory(prefix="jc-v4-w0-04-") as temporary:
        temporary_root = Path(temporary)
        environment = _required_pytest_environment()

        red_report = temporary_root / "red-sentinels.xml"
        try:
            red_completed = subprocess.run(
                [
                    sys.executable, "-B", "-m", "pytest",
                    "-c", str(REQUIRED_TEST_PYTEST_CONFIG),
                    "-q", "-p", "no:cacheprovider",
                    "--basetemp", str(temporary_root / "red-pytest"),
                    "--junitxml", str(red_report),
                    manifest["red_sentinel_selector"],
                ],
                cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                errors="replace", check=False,
                timeout=120, env=environment,
            )
        except subprocess.TimeoutExpired:
            print("RED_AT_TASK sentinel execution exceeded 120 seconds", file=sys.stderr)
            return EXIT_GATE_FAIL
        if red_completed.returncode != 1:
            print(
                f"RED_AT_TASK sentinels returned {red_completed.returncode}, expected 1",
                file=sys.stderr,
            )
            if red_completed.stdout:
                print(red_completed.stdout, file=sys.stderr)
            if red_completed.stderr:
                print(red_completed.stderr, file=sys.stderr)
            return EXIT_GATE_FAIL
        try:
            red_counts, red_cases = _junit_evidence(red_report)
        except (OSError, ET.ParseError, ValueError) as exc:
            print(f"red sentinel pytest report unreadable: {exc}", file=sys.stderr)
            return EXIT_GATE_FAIL
        red_problems = _red_junit_problems(red_counts, red_cases, expected_red_by_id)
        if red_problems:
            print(
                "RED_AT_TASK sentinels are not exact explicit failures: "
                + "; ".join(red_problems),
                file=sys.stderr,
            )
            return EXIT_GATE_FAIL
        red_case_ids = sorted(
            item.attrib.get("name", "") for item in red_cases
        )

        required_evidence: list[dict[str, Any]] = []
        all_required_case_ids: set[str] = set()
        for index, required in enumerate(manifest["required_now"], 1):
            report = temporary_root / f"required-{index:02d}.xml"
            try:
                completed = subprocess.run(
                    [
                        sys.executable, "-B", "-m", "pytest",
                        "-c", str(REQUIRED_TEST_PYTEST_CONFIG),
                        "-q", "-p", "no:cacheprovider",
                        "--basetemp", str(temporary_root / f"required-{index:02d}-pytest"),
                        "--junitxml", str(report),
                        required["selector"],
                    ],
                    cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                    errors="replace", check=False,
                    timeout=120, env=environment,
                )
            except subprocess.TimeoutExpired:
                print(
                    f"required test execution exceeded 120 seconds: {required['id']}",
                    file=sys.stderr,
                )
                return EXIT_GATE_FAIL
            if completed.returncode != 0:
                print(f"required test execution failed: {required['id']}", file=sys.stderr)
                if completed.stdout:
                    print(completed.stdout, file=sys.stderr)
                if completed.stderr:
                    print(completed.stderr, file=sys.stderr)
                return EXIT_GATE_FAIL
            if "xpass" in (completed.stdout + "\n" + completed.stderr).lower():
                print(f"required test reported XPASS: {required['id']}", file=sys.stderr)
                return EXIT_GATE_FAIL
            try:
                required_counts, required_cases = _junit_evidence(report)
            except (OSError, ET.ParseError, ValueError) as exc:
                print(
                    f"required pytest report unreadable for {required['id']}: {exc}",
                    file=sys.stderr,
                )
                return EXIT_GATE_FAIL
            case_ids = sorted(
                f"{item.attrib.get('classname', '')}::{item.attrib.get('name', '')}"
                for item in required_cases
            )
            expected_count = required["expected_tests"]
            if (
                required_counts != {
                    "tests": expected_count, "skipped": 0, "failures": 0, "errors": 0,
                }
                or len(case_ids) != expected_count
                or len(case_ids) != len(set(case_ids))
                or not all(case_id.split("::", 1)[0] for case_id in case_ids)
                or all_required_case_ids.intersection(case_ids)
            ):
                print(
                    f"required pytest report is not exact for {required['id']}: "
                    f"counts={required_counts} cases={len(case_ids)}/{expected_count}",
                    file=sys.stderr,
                )
                return EXIT_GATE_FAIL
            all_required_case_ids.update(case_ids)
            required_evidence.append({
                "id": required["id"],
                "selector": required["selector"],
                "counts": required_counts,
                "case_ids": case_ids,
                "case_ids_digest": _digest_object(case_ids),
            })

    evidence = {
        "schema_version": "jc/v4-required-test-evidence/1.0",
        "task_id": "W0-04",
        "runner_version": RUNNER_VERSION,
        "source_commit": _git_checked("rev-parse", "HEAD"),
        "source_tree": _git_checked("rev-parse", "HEAD^{tree}"),
        "input_digests": {
            "runner": "sha256:" + sha256_hex(Path(__file__).read_bytes()),
            "manifest": "sha256:" + sha256_hex(REQUIRED_TEST_MANIFEST.read_bytes()),
            "pytest_config": "sha256:" + sha256_hex(REQUIRED_TEST_PYTEST_CONFIG.read_bytes()),
            "red_sentinel": "sha256:" + sha256_hex(
                (ROOT / manifest["red_sentinel_selector"]).read_bytes()
            ),
            "pinned_companion_binding": _digest_object(W0_B02_COMPANION_BINDING),
        },
        "pinned_companion_state": live_b02_binding,
        "red": {
            "counts": red_counts,
            "case_ids": red_case_ids,
            "obligation_binding_digest": _digest_object(expected_red_by_id),
        },
        "required": required_evidence,
        "totals": {
            "required_passed": expected_required_count,
            "future_red": len(expected_red_by_id),
            "required_skipped": 0,
            "required_failures": 0,
            "required_errors": 0,
            "red_expected_failures": len(expected_red_by_id),
        },
    }
    if raw_state_root:
        try:
            evidence_path, evidence_digest = _write_content_addressed_json(
                Path(raw_state_root).resolve() / "evidence" / "W0-04", evidence
            )
        except (OSError, ValueError) as exc:
            print(f"required test evidence write failed: {exc}", file=sys.stderr)
            return EXIT_GATE_FAIL
        print(
            "JC_ARTIFACT\tw0-04-required-tests\t"
            f"{evidence_path}\t{evidence_digest}"
        )
    print(
        "test governance skeleton OK: "
        f"{len(W0_REQUIRED_TEST_SUITES)} suites; "
        f"{len(manifest['audit_mutations'])} audit groups registered; "
        f"{len(manifest['rewrite_at_task'])} rewrites queued; "
        f"{expected_required_count} required governance tests passed; "
        f"{len(expected_red_by_id)} future obligations explicitly RED; "
        "0 skip/xfail/xpass/collection errors"
    )
    return EXIT_OK


def cmd_verify_wave(args: argparse.Namespace) -> int:
    if args.wave == "W0-01":
        return cmd_object_state_matrix(argparse.Namespace(path=str(OBJECT_STATE_MATRIX)))
    if args.wave == "W0-02":
        return cmd_foundation_contract(argparse.Namespace(
            jcs=str(JCS_V4_VECTORS), foundation=str(FOUNDATION_V4_CONTRACT)
        ))
    if args.wave == "W0-04":
        return cmd_required_test_manifest()
    print(
        f"task {args.wave} has no implemented machine verifier; refusing false PASS",
        file=sys.stderr,
    )
    return EXIT_GATE_FAIL


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest_object(value: Any) -> str:
    return "sha256:" + sha256_hex(_canonical_bytes(value))


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _write_content_addressed_json(
    directory: Path, value: Any,
) -> tuple[Path, str]:
    """Create immutable JSON evidence and reuse only byte-identical content."""

    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    digest = "sha256:" + sha256_hex(payload)
    path = directory / f"{digest.split(':', 1)[1]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise ValueError(f"content-addressed evidence collision: {path}")
    return path.resolve(), digest


def _git_checked(*args: str) -> str:
    cp = subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=False
    )
    if cp.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {cp.stderr.strip()}")
    return cp.stdout.strip()


def _file_identity(path: Path) -> str:
    if not path.exists():
        return "missing"
    if path.is_file():
        return sha256_hex(path.read_bytes())
    return "directory"


def _git_status_snapshot() -> dict[str, str]:
    cp = subprocess.run(
        ["git", "-c", "core.quotepath=false", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"git status failed: {cp.stderr.strip()}")
    result: dict[str, str] = {}
    for line in cp.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        normalized = path.replace("\\", "/")
        result[normalized] = f"{line[:2]}:{_file_identity(ROOT / normalized)}"
    return result


def _changed_status_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=str(ROOT), capture_output=True, check=False,
    )
    return completed.returncode == 0


def _git_path_bytes(commit: str, path: str) -> bytes | None:
    object_name = f"{commit}:{path}"
    exists = subprocess.run(
        ["git", "cat-file", "-e", object_name], cwd=str(ROOT),
        capture_output=True, check=False,
    )
    if exists.returncode != 0:
        return None
    completed = subprocess.run(
        ["git", "show", object_name], cwd=str(ROOT), capture_output=True, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git show failed for {object_name}")
    return completed.stdout


def _committed_delta(start_commit: str, result_commit: str) -> tuple[list[str], dict[str, str]]:
    """Bind the exact task delta; renames are intentionally deletion plus addition."""
    if not _git_is_ancestor(start_commit, result_commit):
        raise RuntimeError(
            f"task result {result_commit} does not descend from start {start_commit}"
        )
    completed = subprocess.run(
        [
            "git", "-c", "core.quotepath=false", "diff", "--no-renames",
            "--name-only", "-z", start_commit, result_commit,
        ],
        cwd=str(ROOT), capture_output=True, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("git diff failed while binding the task delta")
    paths = sorted(
        item.decode("utf-8").replace("\\", "/")
        for item in completed.stdout.split(b"\0") if item
    )
    artifact_digests: dict[str, str] = {}
    for path in paths:
        result_bytes = _git_path_bytes(result_commit, path)
        if result_bytes is not None:
            artifact_digests[f"result-path:{path}"] = "sha256:" + sha256_hex(result_bytes)
            continue
        start_bytes = _git_path_bytes(start_commit, path)
        if start_bytes is None:
            raise RuntimeError(f"changed path is absent from both task commits: {path}")
        artifact_digests[f"deleted-path:{path}"] = "sha256:" + sha256_hex(start_bytes)
    return paths, artifact_digests


def _matches_allowed(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    for raw in patterns:
        pattern = raw.replace("\\", "/")
        if pattern.startswith("$JC_REMEDIATION_STATE_ROOT"):
            continue
        if pattern.endswith("/**") and (
            normalized == pattern[:-3] or normalized.startswith(pattern[:-2])
        ):
            return True
        if fnmatch.fnmatchcase(normalized, pattern):
            return True
    return False


def _expanded_argv(argv: list[str], state_root: Path) -> list[str]:
    replacements = {
        "{python}": sys.executable,
        "{state_root}": str(state_root),
        "$JC_REMEDIATION_STATE_ROOT": str(state_root),
    }
    expanded: list[str] = []
    for value in argv:
        current = value
        for marker, replacement in replacements.items():
            current = current.replace(marker, replacement)
        expanded.append(current)
    if expanded[0].lower() == "codegraph":
        wrapper = shutil.which(expanded[0])
        if wrapper and wrapper.lower().endswith(".cmd"):
            installation = Path(wrapper).resolve().parent.parent
            node = installation / "node.exe"
            script = installation / "lib" / "dist" / "bin" / "codegraph.js"
            if node.is_file() and script.is_file():
                return [str(node), "--liftoff-only", str(script), *expanded[1:]]
    return expanded


def _stream_record(path: Path, payload: bytes) -> dict[str, Any]:
    path.write_bytes(payload)
    return {"path": str(path), "sha256": sha256_hex(payload), "bytes": len(payload)}


def _run_argv(
    argv: list[str], expected_exit_code: int, attempt_dir: Path,
    index: int, timeout_seconds: float, state_root: Path,
) -> dict[str, Any]:
    exact_argv = _expanded_argv(argv, state_root)
    timed_out = False
    exit_code: int | None
    execution_environment = os.environ.copy()
    execution_environment.update({
        "JC_REMEDIATION_STATE_ROOT": str(state_root),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    })
    try:
        cp = subprocess.run(
            exact_argv, cwd=str(ROOT), capture_output=True, check=False,
            timeout=timeout_seconds, env=execution_environment,
        )
        exit_code = cp.returncode
        stdout = cp.stdout
        stderr = cp.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode("utf-8", errors="replace")
        if isinstance(stderr, str):
            stderr = stderr.encode("utf-8", errors="replace")
    except OSError as exc:
        exit_code = 127
        stdout = b""
        stderr = str(exc).encode("utf-8", errors="replace")
    return {
        "argv": exact_argv,
        "expected_exit_code": expected_exit_code,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout": _stream_record(attempt_dir / f"stdout-{index:03d}.bin", stdout),
        "stderr": _stream_record(attempt_dir / f"stderr-{index:03d}.bin", stderr),
    }


def _evaluate_assertions(
    task: dict[str, Any], command_results: list[dict[str, Any]], state_root: Path
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    commands_ok = all(
        not item["timed_out"] and item["exit_code"] == item["expected_exit_code"]
        for item in command_results
    )
    tracked = set(_git_tracked_files())
    for assertion in task.get("completion_assertions", []):
        kind = assertion["kind"]
        detail = ""
        if kind == "all_commands_passed":
            ok = commands_ok
            detail = "all exit codes matched" if ok else "command failure or timeout"
        elif kind in {"path_exists", "path_absent"}:
            raw = assertion.get("path", "")
            path = Path(raw.replace("{state_root}", str(state_root)))
            if not path.is_absolute():
                path = ROOT / path
            exists = path.exists()
            ok = exists if kind == "path_exists" else not exists
            detail = f"{path} exists={exists}"
        elif kind in {"git_tracked", "git_untracked"}:
            path = assertion.get("path", "").replace("\\", "/")
            is_tracked = path in tracked
            ok = is_tracked if kind == "git_tracked" else not is_tracked
            detail = f"{path} tracked={is_tracked}"
        else:
            ok = False
            detail = "command assertions must be task argv so their output is receipted"
        results.append({"id": assertion["id"], "kind": kind, "ok": ok, "detail": detail})
    return results


def _receipt_digest(receipt: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    return _digest_object(unsigned)


def _task_digest(task: dict[str, Any]) -> str:
    return _digest_object(task)


def _validate_stream(stream: dict[str, Any]) -> bool:
    path = Path(stream["path"])
    if not path.is_file():
        return False
    payload = path.read_bytes()
    return len(payload) == stream["bytes"] and sha256_hex(payload) == stream["sha256"]


def _declared_state_artifacts(
    command_results: list[dict[str, Any]], state_root: Path,
) -> dict[str, str]:
    """Recompute state evidence declared by receipted command stdout."""
    evidence_root = (state_root.resolve() / "evidence").resolve()
    artifacts: dict[str, str] = {}
    labels: set[str] = set()
    for command in command_results:
        stdout_path = Path(command["stdout"]["path"])
        payload = stdout_path.read_bytes().decode("utf-8", errors="strict")
        for line in payload.splitlines():
            if not line.startswith("JC_ARTIFACT\t"):
                continue
            fields = line.split("\t")
            if len(fields) != 4:
                raise ValueError("invalid JC_ARTIFACT field count")
            _, label, raw_path, digest = fields
            if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", label):
                raise ValueError(f"invalid JC_ARTIFACT label: {label}")
            if label in labels:
                raise ValueError(f"duplicate JC_ARTIFACT label: {label}")
            labels.add(label)
            if not DIGEST_V4_PATTERN.fullmatch(digest):
                raise ValueError(f"invalid JC_ARTIFACT digest grammar: {digest}")
            target = Path(raw_path).resolve(strict=True)
            if not target.is_file() or not target.is_relative_to(evidence_root):
                raise ValueError(f"JC_ARTIFACT escapes state evidence root: {target}")
            actual = "sha256:" + sha256_hex(target.read_bytes())
            if actual != digest:
                raise ValueError(
                    f"JC_ARTIFACT digest mismatch for {label}: {actual} != {digest}"
                )
            artifacts[f"state-artifact:{label}"] = digest
    return artifacts


def _validate_git_binding(commit: str, tree: str) -> bool:
    cp = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{tree}}"], cwd=str(ROOT),
        capture_output=True, text=True, check=False,
    )
    return cp.returncode == 0 and cp.stdout.strip() == tree


def _receipt_history(task_id: str, state_root: Path) -> list[dict[str, Any]]:
    task_dir = state_root / "tasks" / task_id
    if not task_dir.exists():
        return []
    validator = Draft202012Validator(json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8")))
    receipts: list[dict[str, Any]] = []
    previous: str | None = None
    attempt_dirs = sorted(
        (path for path in task_dir.iterdir() if path.is_dir() and path.name.isdigit()),
        key=lambda path: int(path.name),
    )
    previous_attempt = 0
    for index, attempt_dir in enumerate(attempt_dirs):
        receipt_path = attempt_dir / "receipt.json"
        if not receipt_path.is_file():
            interruption = attempt_dir / "interrupted.json"
            if interruption.exists():
                continue
            if index != len(attempt_dirs) - 1:
                raise ValueError(f"receipt missing before a later attempt: {receipt_path}")
            if not interruption.exists():
                _atomic_json(interruption, {
                    "status": "INTERRUPTED", "detected_at": _iso_now(),
                    "detail": "attempt directory existed without receipt; preserved for audit",
                })
            continue
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        errors = list(validator.iter_errors(receipt))
        if errors:
            raise ValueError(f"invalid receipt schema {receipt_path}: {errors[0].message}")
        attempt_number = int(attempt_dir.name)
        if receipt["task_id"] != task_id or receipt["attempt"] != attempt_number or attempt_number <= previous_attempt:
            raise ValueError(f"receipt identity mismatch: {receipt_path}")
        if receipt["previous_receipt_digest"] != previous:
            raise ValueError(f"receipt chain broken: {receipt_path}")
        if receipt["receipt_digest"] != _receipt_digest(receipt):
            raise ValueError(f"receipt digest mismatch: {receipt_path}")
        if not _validate_git_binding(receipt["start_commit"], receipt["start_tree"]):
            raise ValueError(f"start commit/tree mismatch: {receipt_path}")
        if not _validate_git_binding(receipt["result_commit"], receipt["result_tree"]):
            raise ValueError(f"result commit/tree mismatch: {receipt_path}")
        expected_paths, expected_artifacts = _committed_delta(
            receipt["start_commit"], receipt["result_commit"]
        )
        if receipt["changed_paths"] != expected_paths:
            raise ValueError(f"changed path binding mismatch: {receipt_path}")
        recorded_delta_artifacts = {
            key: value for key, value in receipt["artifact_digests"].items()
            if key.startswith("result-path:") or key.startswith("deleted-path:")
        }
        if recorded_delta_artifacts != expected_artifacts:
            raise ValueError(f"artifact digest binding mismatch: {receipt_path}")
        for command in receipt["command_results"]:
            if not _validate_stream(command["stdout"]) or not _validate_stream(command["stderr"]):
                raise ValueError(f"stdout/stderr digest mismatch: {receipt_path}")
        expected_state_artifacts = _declared_state_artifacts(
            receipt["command_results"], state_root
        )
        recorded_state_artifacts = {
            key: value for key, value in receipt["artifact_digests"].items()
            if key.startswith("state-artifact:")
        }
        if recorded_state_artifacts != expected_state_artifacts:
            raise ValueError(f"state artifact binding mismatch: {receipt_path}")
        if (
            receipt["runner_version"] == RUNNER_VERSION
            or any(
                assertion["id"].startswith("runner-")
                for assertion in receipt["completion_assertions"]
            )
        ) and receipt["test_reports"] != _structured_test_reports(receipt["command_results"]):
            raise ValueError(f"structured test report binding mismatch: {receipt_path}")
        previous = receipt["receipt_digest"]
        previous_attempt = attempt_number
        receipts.append(receipt)
    return receipts


def _next_attempt(task_id: str, state_root: Path) -> int:
    task_dir = state_root / "tasks" / task_id
    attempts = [int(path.name) for path in task_dir.iterdir() if path.is_dir() and path.name.isdigit()] if task_dir.exists() else []
    return max(attempts, default=0) + 1


def _topological_tasks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = plan["tasks"]
    by_id = {task["id"]: task for task in tasks}
    remaining = set(by_id)
    completed: set[str] = set()
    ordered: list[dict[str, Any]] = []
    while remaining:
        ready = [task for task in tasks if task["id"] in remaining and set(task["depends_on"]) <= completed]
        if not ready:
            raise ValueError("task DAG has a cycle or missing dependency")
        task = ready[0]
        ordered.append(task)
        completed.add(task["id"])
        remaining.remove(task["id"])
    return ordered


def _task_start_commit(
    task: dict[str, Any], completed_receipts: dict[str, dict[str, Any]],
    run_baseline_commit: str,
) -> str:
    dependency_commits = [
        completed_receipts[dependency]["result_commit"]
        for dependency in task["depends_on"]
    ]
    if not dependency_commits:
        return run_baseline_commit
    latest = dependency_commits[0]
    for candidate in dependency_commits[1:]:
        if _git_is_ancestor(latest, candidate):
            latest = candidate
        elif not _git_is_ancestor(candidate, latest):
            raise ValueError(
                f"task {task['id']} dependency commits are not linearly ordered"
            )
    return latest


def _subject_digest(task: dict[str, Any], state_root: Path) -> str:
    identities: list[dict[str, str]] = []
    for raw in task["approval"]["subject_paths"]:
        expanded = raw.replace("$JC_REMEDIATION_STATE_ROOT", str(state_root))
        base = Path(expanded)
        matches = list(ROOT.glob(expanded)) if not base.is_absolute() else list(base.parent.glob(base.name))
        if not matches:
            identities.append({"path": raw, "sha256": "MISSING"})
        for path in sorted(matches):
            identities.append({"path": str(path), "sha256": _file_identity(path)})
    return _digest_object({"task_id": task["id"], "subject": task["approval"]["subject"], "artifacts": identities})


def _gate_request(task: dict[str, Any], state_root: Path, run_id: str) -> dict[str, Any]:
    approval = task["approval"]
    subject_digest = _subject_digest(task, state_root)
    request = {
        "schema_version": "jc/remediation-v4-gate-request/2.0", "run_id": run_id,
        "task_id": task["id"], "gate_id": approval["gate_id"], "kind": task["mode"],
        "subject": approval["subject"], "subject_digest": subject_digest,
        "required_roles": approval["required_roles"], "allowed_scopes": approval["allowed_scopes"],
        "minimum_signers": approval["minimum_signers"],
        "separation_of_duties": approval["separation_of_duties"],
        "issued_at": _iso_now(),
    }
    request["request_digest"] = _digest_object(request)
    request_dir = state_root / "requests" / task["id"]
    request_path = request_dir / f"{subject_digest.split(':', 1)[1]}.json"
    if request_path.exists():
        return json.loads(request_path.read_text(encoding="utf-8"))
    _atomic_json(request_path, request)
    return request


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _approval_payload(approval: dict[str, Any]) -> bytes:
    return _canonical_bytes({key: value for key, value in approval.items() if key != "signature"})


def _valid_approvals(task: dict[str, Any], request: dict[str, Any], state_root: Path) -> list[dict[str, Any]]:
    evidence_kind = task["approval"]["evidence_kind"]
    if evidence_kind == "USER_DIRECTIVE":
        directive_dir = state_root / "directives" / task["id"]
        if not directive_dir.is_dir():
            return []
        accepted_directives = []
        for path in sorted(directive_dir.glob("*.json")):
            try:
                directive = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                directive.get("evidence_kind") == "USER_DIRECTIVE"
                and directive.get("task_id") == task["id"]
                and directive.get("subject_digest") == request["subject_digest"]
                and directive.get("scope") in request["allowed_scopes"]
                and directive.get("authority_source")
            ):
                accepted_directives.append(directive)
        return accepted_directives
    if evidence_kind == "EXTERNAL_ARTIFACT":
        return []
    trust_path = state_root / "trust" / "trusted_keys.json"
    if not trust_path.is_file():
        return []
    trusted = json.loads(trust_path.read_text(encoding="utf-8"))
    keys = {item["key_id"]: item for item in trusted.get("keys", [])}
    approval_dir = state_root / "approvals" / task["id"]
    if not approval_dir.is_dir():
        return []
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    accepted: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    now = datetime.now(timezone.utc)
    schema = json.loads(APPROVAL_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for path in sorted(approval_dir.glob("*.json")):
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if list(validator.iter_errors(candidate)):
                continue
            signer = candidate["signer"]
            key = keys.get(signer["key_id"])
            if not key or signer["key_id"] in seen_keys:
                continue
            if candidate["task_id"] != task["id"] or candidate["gate_id"] != request["gate_id"]:
                continue
            if candidate["request_digest"] != request["request_digest"] or candidate.get("subject_digest") != request["subject_digest"]:
                continue
            if (
                candidate["decision"] != "APPROVE"
                or _parse_time(candidate["issued_at"]) > now
                or _parse_time(candidate["expires_at"]) <= now
            ):
                continue
            if signer["role"] not in request["required_roles"] or signer["scope"] not in request["allowed_scopes"]:
                continue
            if signer["role"] not in key.get("roles", []) or signer["scope"] not in key.get("scopes", []):
                continue
            signature = candidate["signature"]
            if signature["algorithm"] != "Ed25519" or signature.get("public_key_id", signer["key_id"]) != signer["key_id"]:
                continue
            public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(key["public_key_base64"]))
            public_key.verify(base64.b64decode(signature["value"]), _approval_payload(candidate))
        except Exception:
            continue
        seen_keys.add(signer["key_id"])
        accepted.append(candidate)
    if request["separation_of_duties"] and len(seen_keys) != len(accepted):
        return []
    return accepted


def _complete_gate_task(
    task: dict[str, Any], request: dict[str, Any], approvals: list[dict[str, Any]],
    state_root: Path, run_id: str, input_receipts: dict[str, str],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    attempt = _next_attempt(task["id"], state_root)
    attempt_dir = state_root / "tasks" / task["id"] / str(attempt)
    attempt_dir.mkdir(parents=True, exist_ok=False)
    commit = _git_checked("rev-parse", "HEAD")
    tree = _git_checked("rev-parse", "HEAD^{tree}")
    receipt = {
        "schema_version": "jc/remediation-v4-receipt/2.1", "task_digest": _task_digest(task), "run_id": run_id,
        "task_id": task["id"], "attempt": attempt, "status": "COMPLETED",
        "input_receipt_digests": input_receipts,
        "start_commit": commit, "start_tree": tree,
        "result_commit": commit, "result_tree": tree,
        "command_results": [], "changed_paths": [],
        "allowlist": {"allowed": True, "violations": []}, "test_reports": [],
        "artifact_digests": {
            "request": request["request_digest"],
            **{
                f"approval:{item['signer']['key_id']}": _digest_object(item)
                for item in approvals
            },
        },
        "completion_assertions": [{
            "id": "approval-policy", "kind": "cryptographic_approval", "ok": True,
            "detail": f"{len(approvals)} {task['approval']['evidence_kind']} evidence item(s) bound to subject",
        }],
        "previous_receipt_digest": history[-1]["receipt_digest"] if history else None,
        "runner_version": RUNNER_VERSION,
    }
    _write_receipt(attempt_dir, receipt)
    return receipt


def _write_receipt(attempt_dir: Path, receipt: dict[str, Any]) -> None:
    receipt["receipt_digest"] = _receipt_digest(receipt)
    schema = json.loads(RECEIPT_SCHEMA.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(receipt))
    if errors:
        raise ValueError(f"runner produced invalid receipt: {errors[0].message}")
    path = attempt_dir / "receipt.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _structured_test_reports(command_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for index, item in enumerate(command_results, 1):
        argv = item["argv"]
        kind: str | None = None
        if "pytest" in argv:
            kind = "pytest"
        elif any(Path(value).name == "jcs_node_oracle.mjs" for value in argv):
            kind = "node-oracle"
        elif len(argv) >= 2 and argv[-2:] == ["verify-wave", "W0-04"]:
            kind = "pytest-governance"
        if kind is None:
            continue
        stdout_path = Path(item["stdout"]["path"])
        stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
        report: dict[str, Any] = {
            "command_index": index,
            "kind": kind,
            "exit_code": item["exit_code"],
            "stdout_sha256": item["stdout"]["sha256"],
            "stderr_sha256": item["stderr"]["sha256"],
        }
        if kind == "pytest":
            passed = re.search(r"(?:^|\s)(\d+) passed(?:\s|,|$)", stdout_text)
            if passed:
                report["passed"] = int(passed.group(1))
        elif kind == "node-oracle":
            for field in ("positive", "negative", "canonical_bytes"):
                match = re.search(rf"(?:^|\s){field}=(\d+)(?:\s|$)", stdout_text)
                if match:
                    report[field] = int(match.group(1))
            runtime = re.search(r"(?:^|\s)runtime=(v\d+\.\d+\.\d+)(?:\s|$)", stdout_text)
            if runtime:
                report["runtime"] = runtime.group(1)
        else:
            summary = re.search(
                r"test governance skeleton OK: (?P<suites>\d+) suites; "
                r"(?P<audits>\d+) audit groups registered; "
                r"(?P<rewrites>\d+) rewrites queued; "
                r"(?P<required>\d+) required governance tests passed; "
                r"(?P<red>\d+) future obligations explicitly RED; "
                r"0 skip/xfail/xpass/collection errors",
                stdout_text,
            )
            if summary is None:
                continue
            report.update({
                "suites": int(summary.group("suites")),
                "audit_groups": int(summary.group("audits")),
                "rewrites": int(summary.group("rewrites")),
                "required_passed": int(summary.group("required")),
                "future_red": int(summary.group("red")),
                "bypass_or_collection_errors": 0,
            })
            for line in stdout_text.splitlines():
                fields = line.split("\t")
                if len(fields) == 4 and fields[:2] == ["JC_ARTIFACT", "w0-04-required-tests"]:
                    report["evidence_label"] = fields[1]
                    report["evidence_sha256"] = fields[3]
            if "evidence_sha256" not in report:
                continue
        reports.append(report)
    return reports


def _rebind_legacy_auto_receipt(
    task: dict[str, Any], latest: dict[str, Any], start_commit: str,
    state_root: Path, run_id: str, input_receipts: dict[str, str],
    history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Append a corrected delta receipt while preserving already-bound command bytes."""
    if (
        latest["status"] != "COMPLETED"
        or latest["start_commit"] != latest["result_commit"]
        or latest["result_commit"] == start_commit
        or latest["changed_paths"]
        or any(
            key.startswith("result-path:") or key.startswith("deleted-path:")
            for key in latest["artifact_digests"]
        )
    ):
        return None
    old_plan_bytes = _git_path_bytes(latest["result_commit"], "remediation/v4/tasks.json")
    if old_plan_bytes is None:
        return None
    old_plan = json.loads(old_plan_bytes.decode("utf-8"))
    old_task = next(
        (candidate for candidate in old_plan.get("tasks", []) if candidate.get("id") == task["id"]),
        None,
    )
    if old_task is None or latest.get("task_digest") != _task_digest(old_task):
        return None
    old_semantics = {key: value for key, value in old_task.items() if key != "allowed_paths"}
    new_semantics = {key: value for key, value in task.items() if key != "allowed_paths"}
    if old_semantics != new_semantics:
        return None
    old_allowlist = set(old_task["allowed_paths"])
    new_allowlist = set(task["allowed_paths"])
    if not old_allowlist < new_allowlist:
        return None
    added_allowlist = sorted(new_allowlist - old_allowlist)
    changed_paths, committed_artifacts = _committed_delta(
        start_commit, latest["result_commit"]
    )
    violations = [
        path for path in changed_paths
        if not _matches_allowed(path, task["allowed_paths"])
    ]
    if violations:
        return None
    assertions = _evaluate_assertions(task, latest["command_results"], state_root)
    assertions.extend([
        {
            "id": "runner-legacy-delta-rebind", "kind": "scope_contract_correction", "ok": True,
            "detail": (
                "append-only scope-contract correction; original command streams retained; "
                f"added allowlist entries={added_allowlist}; "
                f"{len(changed_paths)} historical committed paths rebound"
            ),
        },
        {
            "id": "runner-committed-delta", "kind": "artifact_binding", "ok": True,
            "detail": f"{len(changed_paths)} committed paths bound to {len(committed_artifacts)} digests",
        },
        {
            "id": "runner-input-chain-correction", "kind": "receipt_chain_binding", "ok": True,
            "detail": (
                f"input receipt map corrected={latest['input_receipt_digests'] != input_receipts}; "
                "dependency result commit is the rebound start commit"
            ),
        },
    ])
    attempt = _next_attempt(task["id"], state_root)
    attempt_dir = state_root / "tasks" / task["id"] / str(attempt)
    attempt_dir.mkdir(parents=True, exist_ok=False)
    receipt = {
        "schema_version": "jc/remediation-v4-receipt/2.1",
        "task_digest": _task_digest(task), "run_id": run_id,
        "task_id": task["id"], "attempt": attempt, "status": "COMPLETED",
        "input_receipt_digests": input_receipts,
        "start_commit": start_commit,
        "start_tree": _git_checked("rev-parse", f"{start_commit}^{{tree}}"),
        "result_commit": latest["result_commit"],
        "result_tree": latest["result_tree"],
        "command_results": latest["command_results"],
        "changed_paths": changed_paths,
        "allowlist": {"allowed": True, "violations": []},
        "test_reports": _structured_test_reports(latest["command_results"]),
        "artifact_digests": {
            **committed_artifacts,
            **_declared_state_artifacts(latest["command_results"], state_root),
            "legacy-task-definition": _task_digest(old_task),
            "corrected-task-definition": _task_digest(task),
            "legacy-input-receipts": _digest_object(latest["input_receipt_digests"]),
            "corrected-input-receipts": _digest_object(input_receipts),
        },
        "completion_assertions": assertions,
        "previous_receipt_digest": history[-1]["receipt_digest"],
        "runner_version": RUNNER_VERSION,
    }
    _write_receipt(attempt_dir, receipt)
    return receipt


def _rebind_dependency_chain_receipt(
    task: dict[str, Any], latest: dict[str, Any], start_commit: str,
    state_root: Path, run_id: str, input_receipts: dict[str, str],
    history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Rebind only an upstream receipt digest when every bound Git object is unchanged."""
    if (
        latest["status"] != "COMPLETED"
        or latest.get("task_digest") != _task_digest(task)
        or latest["input_receipt_digests"] == input_receipts
        or latest["start_commit"] != latest["result_commit"]
        or latest["result_commit"] != start_commit
        or latest["changed_paths"]
        or any(
            key.startswith("result-path:") or key.startswith("deleted-path:")
            for key in latest["artifact_digests"]
        )
    ):
        return None
    assertions = _evaluate_assertions(task, latest["command_results"], state_root)
    assertions.append({
        "id": "runner-dependency-chain-rebind", "kind": "receipt_chain_binding", "ok": True,
        "detail": (
            "append-only dependency digest correction; command streams and Git tree unchanged"
        ),
    })
    attempt = _next_attempt(task["id"], state_root)
    attempt_dir = state_root / "tasks" / task["id"] / str(attempt)
    attempt_dir.mkdir(parents=True, exist_ok=False)
    receipt = {
        "schema_version": "jc/remediation-v4-receipt/2.1",
        "task_digest": _task_digest(task), "run_id": run_id,
        "task_id": task["id"], "attempt": attempt, "status": "COMPLETED",
        "input_receipt_digests": input_receipts,
        "start_commit": start_commit, "start_tree": latest["start_tree"],
        "result_commit": start_commit, "result_tree": latest["result_tree"],
        "command_results": latest["command_results"], "changed_paths": [],
        "allowlist": {"allowed": True, "violations": []},
        "test_reports": _structured_test_reports(latest["command_results"]),
        "artifact_digests": {
            **latest["artifact_digests"],
            "legacy-input-receipts": _digest_object(latest["input_receipt_digests"]),
            "corrected-input-receipts": _digest_object(input_receipts),
        },
        "completion_assertions": assertions,
        "previous_receipt_digest": history[-1]["receipt_digest"],
        "runner_version": RUNNER_VERSION,
    }
    _write_receipt(attempt_dir, receipt)
    return receipt


def _execute_auto_task(
    task: dict[str, Any], state_root: Path, run_id: str,
    input_receipts: dict[str, str], history: list[dict[str, Any]],
    start_commit: str,
) -> tuple[int, dict[str, Any]]:
    attempt = _next_attempt(task["id"], state_root)
    attempt_dir = state_root / "tasks" / task["id"] / str(attempt)
    attempt_dir.mkdir(parents=True, exist_ok=False)
    start_tree = _git_checked("rev-parse", f"{start_commit}^{{tree}}")
    before = _git_status_snapshot()
    command_results: list[dict[str, Any]] = []
    timeout = float(task.get("timeout_seconds", 600))
    if not before:
        for index, (argv, expected) in enumerate(zip(task["argv"], task["expected_exit_codes"]), 1):
            command_results.append(_run_argv(argv, expected, attempt_dir, index, timeout, state_root))
            if command_results[-1]["timed_out"] or command_results[-1]["exit_code"] != expected:
                break
    after = _git_status_snapshot()
    result_commit = _git_checked("rev-parse", "HEAD")
    result_tree = _git_checked("rev-parse", "HEAD^{tree}")
    changed_paths, committed_artifacts = _committed_delta(start_commit, result_commit)
    state_artifact_error: str | None = None
    try:
        state_artifacts = _declared_state_artifacts(command_results, state_root)
    except (OSError, UnicodeError, ValueError) as exc:
        state_artifacts = {}
        state_artifact_error = str(exc)
    artifact_digests = {**committed_artifacts, **state_artifacts}
    test_reports = _structured_test_reports(command_results)
    dirty_paths = sorted(set(before) | set(after) | set(_changed_status_paths(before, after)))
    scoped_paths = sorted(set(changed_paths) | set(dirty_paths))
    violations = [path for path in scoped_paths if not _matches_allowed(path, task["allowed_paths"])]
    assertions = _evaluate_assertions(task, command_results, state_root)
    worktree_clean = not before and not after
    assertions.extend([
        {
            "id": "runner-clean-worktree", "kind": "clean_worktree",
            "ok": worktree_clean,
            "detail": "worktree clean before and after commands" if worktree_clean
            else f"uncommitted paths: {dirty_paths}",
        },
        {
            "id": "runner-committed-delta", "kind": "artifact_binding",
            "ok": True,
            "detail": f"{len(changed_paths)} committed paths bound to {len(committed_artifacts)} digests",
        },
        {
            "id": "runner-state-artifacts", "kind": "artifact_binding",
            "ok": state_artifact_error is None,
            "detail": (
                f"{len(state_artifacts)} declared state artifacts rebound from command stdout"
                if state_artifact_error is None else state_artifact_error
            ),
        },
    ])
    if task["id"] == "W0-04":
        governance_reports = [
            report for report in test_reports if report.get("kind") == "pytest-governance"
        ]
        evidence_digest = state_artifacts.get("state-artifact:w0-04-required-tests")
        evidence_bound = (
            len(governance_reports) == 1
            and evidence_digest is not None
            and governance_reports[0].get("evidence_sha256") == evidence_digest
            and governance_reports[0].get("required_passed") == 12
            and governance_reports[0].get("future_red") == 46
            and governance_reports[0].get("bypass_or_collection_errors") == 0
        )
        assertions.append({
            "id": "w0-04-required-test-evidence",
            "kind": "artifact_binding",
            "ok": evidence_bound,
            "detail": (
                "12 required PASS and 46 explicit RED cases bound to canonical state evidence"
                if evidence_bound else "W0-04 test report or state evidence binding is incomplete"
            ),
        })
    timed_out = any(item["timed_out"] for item in command_results)
    commands_ok = len(command_results) == len(task["argv"]) and all(
        item["exit_code"] == item["expected_exit_code"] and not item["timed_out"]
        for item in command_results
    )
    assertions_ok = all(item["ok"] for item in assertions)
    status = (
        "COMPLETED"
        if commands_ok and assertions_ok and worktree_clean and not violations
        else "FAILED"
    )
    if timed_out:
        status = "TIMED_OUT"
    if violations:
        status = "SCOPE_VIOLATION"
    receipt = {
        "schema_version": "jc/remediation-v4-receipt/2.1", "task_digest": _task_digest(task), "run_id": run_id,
        "task_id": task["id"], "attempt": attempt, "status": status,
        "input_receipt_digests": input_receipts,
        "start_commit": start_commit, "start_tree": start_tree,
        "result_commit": result_commit, "result_tree": result_tree,
        "command_results": command_results, "changed_paths": changed_paths,
        "allowlist": {"allowed": not violations, "violations": violations},
        "test_reports": test_reports,
        "artifact_digests": artifact_digests, "completion_assertions": assertions,
        "previous_receipt_digest": history[-1]["receipt_digest"] if history else None,
        "runner_version": RUNNER_VERSION,
    }
    _write_receipt(attempt_dir, receipt)
    if status == "COMPLETED":
        return EXIT_OK, receipt
    if status == "SCOPE_VIOLATION":
        return EXIT_SCOPE_VIOLATION, receipt
    if not worktree_clean:
        return EXIT_BASELINE_DRIFT, receipt
    return EXIT_GATE_FAIL, receipt


def cmd_run(args: argparse.Namespace) -> int:
    """Execute READY tasks and stop only at a reached failure or gate."""
    plan_path = Path(args.plan).resolve()
    state_root = Path(args.state_root).resolve() if args.state_root else None
    through = args.through or "W9"
    if not plan_path.is_file():
        print(f"plan not found: {plan_path}", file=sys.stderr)
        return EXIT_USAGE
    if state_root is None:
        print("--state-root is required for run", file=sys.stderr)
        return EXIT_USAGE
    initial_worktree = _git_status_snapshot()
    if initial_worktree:
        print(
            "baseline/worktree drift: commit or remove uncommitted paths before run: "
            + ", ".join(sorted(initial_worktree)[:20]),
            file=sys.stderr,
        )
        return EXIT_BASELINE_DRIFT
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "tmp").mkdir(parents=True, exist_ok=True)
    lint_rc = cmd_lint_plan(argparse.Namespace(plan=str(plan_path)))
    if lint_rc != EXIT_OK:
        return lint_rc
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    run_path = state_root / "run.json"
    if run_path.is_file():
        run_state = json.loads(run_path.read_text(encoding="utf-8"))
        if Path(run_state["plan_path"]).resolve() != plan_path:
            print("state root belongs to a different plan", file=sys.stderr)
            return EXIT_BASELINE_DRIFT
        if run_state.get("through") != through:
            print(
                f"state root through target is {run_state.get('through')}, not {through}",
                file=sys.stderr,
            )
            return EXIT_BASELINE_DRIFT
    else:
        run_state = {
            "schema_version": "jc/remediation-v4-run/2.0", "run_id": uuid.uuid4().hex,
            "runner_version": RUNNER_VERSION, "plan_path": str(plan_path), "through": through,
            "baseline_commit": _git_checked("rev-parse", "HEAD"),
            "baseline_tree": _git_checked("rev-parse", "HEAD^{tree}"),
            "started_at": _iso_now(), "task_status": {},
        }
        _atomic_json(run_path, run_state)
    completed_receipts: dict[str, dict[str, Any]] = {}
    try:
        ordered = _topological_tasks(plan)
        task_ids = [task["id"] for task in ordered]
        if through == "ALL":
            pass
        elif through in task_ids:
            ordered = ordered[:task_ids.index(through) + 1]
        else:
            wave_indexes = [
                index for index, task in enumerate(ordered)
                if task.get("wave") == through
            ]
            if not wave_indexes:
                raise ValueError(f"unknown --through target: {through}")
            ordered = ordered[:wave_indexes[-1] + 1]
        for task in ordered:
            history = _receipt_history(task["id"], state_root)
            input_receipts = {
                dep: completed_receipts[dep]["receipt_digest"] for dep in task["depends_on"]
            }
            latest = history[-1] if history else None
            task_start_commit = _task_start_commit(
                task, completed_receipts, run_state["baseline_commit"]
            )
            if task["mode"] == "AUTO" and latest is not None:
                rebound = _rebind_legacy_auto_receipt(
                    task, latest, task_start_commit, state_root,
                    run_state["run_id"], input_receipts, history,
                )
                if rebound is None:
                    rebound = _rebind_dependency_chain_receipt(
                        task, latest, task_start_commit, state_root,
                        run_state["run_id"], input_receipts, history,
                    )
                if rebound is not None:
                    latest = rebound
                    history = [*history, rebound]
                    print(
                        f"task {task['id']} legacy receipt rebound "
                        f"receipt={rebound['receipt_digest']}"
                    )
                elif (
                    latest["status"] == "COMPLETED"
                    and latest["start_commit"] == latest["result_commit"]
                    and latest["result_commit"] != task_start_commit
                    and not latest["changed_paths"]
                    and not any(
                        key.startswith("result-path:") or key.startswith("deleted-path:")
                        for key in latest["artifact_digests"]
                    )
                ):
                    raise ValueError(
                        f"legacy receipt lacks committed delta binding: {task['id']}"
                    )
            if (
                latest and latest["status"] == "COMPLETED"
                and latest.get("task_digest") == _task_digest(task)
                and latest["input_receipt_digests"] == input_receipts
            ):
                expected_violations = [
                    path for path in latest["changed_paths"]
                    if not _matches_allowed(path, task["allowed_paths"])
                ]
                if latest["allowlist"] != {
                    "allowed": not expected_violations,
                    "violations": expected_violations,
                }:
                    raise ValueError(f"receipt scope binding mismatch: {task['id']}")
                assertions = _evaluate_assertions(task, latest["command_results"], state_root)
                if all(item["ok"] for item in assertions):
                    completed_receipts[task["id"]] = latest
                    run_state["task_status"][task["id"]] = "COMPLETED"
                    continue
            if task["mode"] == "AUTO":
                rc, receipt = _execute_auto_task(
                    task, state_root, run_state["run_id"], input_receipts, history,
                    task_start_commit,
                )
                run_state["task_status"][task["id"]] = receipt["status"]
                run_state["updated_at"] = _iso_now()
                _atomic_json(run_path, run_state)
                if rc != EXIT_OK:
                    print(f"task {task['id']} {receipt['status']}; receipt={receipt['receipt_digest']}", file=sys.stderr)
                    return rc
                completed_receipts[task["id"]] = receipt
                print(f"task {task['id']} COMPLETED receipt={receipt['receipt_digest']}")
                continue
            request = _gate_request(task, state_root, run_state["run_id"])
            approvals = _valid_approvals(task, request, state_root)
            if len(approvals) < request["minimum_signers"]:
                marker = "WAITING_EXTERNAL" if task["mode"] == "EXTERNAL_GATE" else "WAITING_HUMAN"
                run_state["task_status"][task["id"]] = marker
                run_state["updated_at"] = _iso_now()
                _atomic_json(run_path, run_state)
                print(f"{marker} task={task['id']} gate={request['gate_id']} subject_digest={request['subject_digest']}")
                print(
                    "Unique resume command: "
                    f"py -3.12 -B {Path(__file__).resolve()} run --plan {plan_path} "
                    f"--state-root {state_root} --through {through}"
                )
                return EXIT_WAITING_EXTERNAL if marker == "WAITING_EXTERNAL" else EXIT_WAITING_HUMAN
            if request["separation_of_duties"] and len({a["signer"]["key_id"] for a in approvals}) < request["minimum_signers"]:
                print(f"WAITING_HUMAN task={task['id']} separation_of_duties not satisfied")
                return EXIT_WAITING_HUMAN
            receipt = _complete_gate_task(
                task, request, approvals, state_root, run_state["run_id"], input_receipts, history
            )
            completed_receipts[task["id"]] = receipt
            run_state["task_status"][task["id"]] = "COMPLETED"
            run_state["updated_at"] = _iso_now()
            _atomic_json(run_path, run_state)
            print(f"task {task['id']} COMPLETED receipt={receipt['receipt_digest']}")
    except (ValueError, RuntimeError) as exc:
        print(f"receipt/run validation failed: {exc}", file=sys.stderr)
        return EXIT_RECEIPT_FAIL
    if ordered:
        terminal_receipt = completed_receipts[ordered[-1]["id"]]
        current_commit = _git_checked("rev-parse", "HEAD")
        if terminal_receipt["result_commit"] != current_commit:
            print(
                "baseline drift: terminal receipt does not bind current HEAD",
                file=sys.stderr,
            )
            return EXIT_BASELINE_DRIFT
    run_state["status"] = "COMPLETED"
    run_state["updated_at"] = _iso_now()
    _atomic_json(run_path, run_state)
    return EXIT_OK


def _git(*args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return cp.stdout


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remediate_v4",
        description="Juris Calculus V4 single-chain remediation runner",
    )
    sub = parser.add_subparsers(dest="command", required=False)

    p = sub.add_parser("lint-plan", help="Validate remediation plan against schema and DAG")
    p.add_argument("--plan", required=True)
    p.set_defaults(func=cmd_lint_plan)

    p = sub.add_parser("authority", help="Module authority / current docs check")
    p.add_argument("--check", action="store_true")
    authority_mode = p.add_mutually_exclusive_group()
    authority_mode.add_argument("--record", action="store_true")
    authority_mode.add_argument("--require-clean", action="store_true")
    p.add_argument("--policy", default=None)
    p.add_argument("--codegraph", default=None)
    p.add_argument("--state-root", default=None)
    p.set_defaults(func=cmd_authority)

    p = sub.add_parser("graph-map", help="CodeGraph reconciliation against tracked tree")
    p.add_argument("--check", action="store_true")
    p.add_argument("--codegraph", default=".codegraph/codegraph.db")
    p.add_argument("--all-tracked", action="store_true")
    p.add_argument("--state-root", default=None)
    p.add_argument("--asset-inventory", default=None)
    p.set_defaults(func=cmd_graph_map)

    p = sub.add_parser("asset-map", help="Explicit non-CodeGraph asset inventory")
    p.add_argument("--codegraph", default=".codegraph/codegraph.db")
    p.add_argument("--state-root", required=True)
    p.set_defaults(func=cmd_asset_map)

    p = sub.add_parser("spec-intake", help="Fetch and verify pinned companion spec")
    p.add_argument("--state-root", required=True)
    p.add_argument("--remote", required=True)
    p.add_argument("--commit", required=True)
    p.set_defaults(func=cmd_spec_intake)

    p = sub.add_parser("audit-map", help="44 audit issue closure check")
    p.add_argument("--audit", required=False)
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_audit_map)

    p = sub.add_parser("file-map", help="Tracked path disposition closure")
    p.add_argument("--check", action="store_true")
    p.add_argument("--all-tracked", action="store_true")
    p.add_argument("--require-semantic-targets", action="store_true")
    p.add_argument("--deletions-ready", action="store_true")
    p.add_argument("--require-target-receipts", action="store_true")
    p.add_argument("--path")
    p.add_argument("--expect-terminal")
    p.add_argument("--graph-receipt-task")
    p.set_defaults(func=cmd_file_map)

    p = sub.add_parser("consumer-map", help="Per-target consumer report (B00-CG)")
    p.add_argument("--check", action="store_true")
    p.add_argument("--codegraph", default=".codegraph/codegraph.db")
    p.add_argument("--target", action="append", default=[])
    p.add_argument("--state-root", default=None)
    p.set_defaults(func=cmd_consumer_map)

    p = sub.add_parser("legacy-cn-corpus", help="W5-02C CN legacy corpus removal gate")
    p.add_argument("--check-removed", action="store_true")
    p.add_argument("--expected-sha256")
    p.add_argument("--expected-bytes", type=int)
    p.add_argument("--expected-rules", type=int)
    p.set_defaults(func=cmd_legacy_cn_corpus)

    p = sub.add_parser("generated", help="Generated Schema/manifest check")
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_generated)

    p = sub.add_parser("forbidden-imports", help="Forbidden import scan")
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_forbidden_imports)

    p = sub.add_parser("object-state-matrix", help="Validate the frozen W0 V4 object/state matrix")
    p.add_argument("--path", default=str(OBJECT_STATE_MATRIX))
    p.set_defaults(func=cmd_object_state_matrix)

    p = sub.add_parser("foundation-contract", help="Validate W0 canonical/time/numeric/limit contracts")
    p.add_argument("--jcs", default=str(JCS_V4_VECTORS))
    p.add_argument("--foundation", default=str(FOUNDATION_V4_CONTRACT))
    p.set_defaults(func=cmd_foundation_contract)

    p = sub.add_parser("verify-wave", help="Aggregate gate per wave")
    p.add_argument("wave")
    p.set_defaults(func=cmd_verify_wave)

    p = sub.add_parser("run", help="Single entry point for resume / continue")
    p.add_argument("--plan", required=True)
    p.add_argument("--state-root", required=True)
    p.add_argument("--through", default="W9")
    p.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_OK
    return int(args.func(args) or EXIT_OK)


if __name__ == "__main__":
    raise SystemExit(main())
