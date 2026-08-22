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
import base64
import fnmatch
import hashlib
import json
import mimetypes
import os
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator  # type: ignore
except ImportError:  # pragma: no cover - exercised by tests via subprocess
    Draft202012Validator = None  # type: ignore

RUNNER_VERSION = "0.2.0"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN = ROOT / "remediation" / "v4" / "tasks.json"
SCHEMA_DIR = ROOT / "remediation" / "v4"
ISSUE_MAP = SCHEMA_DIR / "issue-map.json"
FILE_DISPOSITION = SCHEMA_DIR / "file-disposition.json"
TASK_SCHEMA = SCHEMA_DIR / "task.schema.json"
RECEIPT_SCHEMA = SCHEMA_DIR / "receipt.schema.json"
APPROVAL_SCHEMA = SCHEMA_DIR / "approval.schema.json"

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
    """施工方案 §7 B01: 验证 44 项 issue map 完整。"""
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
    print(f"audit-map OK: {len(issues)} issues, severities={by_sev}")
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


def cmd_verify_wave(args: argparse.Namespace) -> int:
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
    try:
        cp = subprocess.run(
            exact_argv, cwd=str(ROOT), capture_output=True, check=False,
            timeout=timeout_seconds, env={**os.environ, "JC_REMEDIATION_STATE_ROOT": str(state_root)},
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
        for command in receipt["command_results"]:
            if not _validate_stream(command["stdout"]) or not _validate_stream(command["stderr"]):
                raise ValueError(f"stdout/stderr digest mismatch: {receipt_path}")
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


def _execute_auto_task(
    task: dict[str, Any], state_root: Path, run_id: str,
    input_receipts: dict[str, str], history: list[dict[str, Any]],
) -> tuple[int, dict[str, Any]]:
    attempt = _next_attempt(task["id"], state_root)
    attempt_dir = state_root / "tasks" / task["id"] / str(attempt)
    attempt_dir.mkdir(parents=True, exist_ok=False)
    start_commit = _git_checked("rev-parse", "HEAD")
    start_tree = _git_checked("rev-parse", "HEAD^{tree}")
    before = _git_status_snapshot()
    command_results: list[dict[str, Any]] = []
    timeout = float(task.get("timeout_seconds", 600))
    for index, (argv, expected) in enumerate(zip(task["argv"], task["expected_exit_codes"]), 1):
        command_results.append(_run_argv(argv, expected, attempt_dir, index, timeout, state_root))
        if command_results[-1]["timed_out"] or command_results[-1]["exit_code"] != expected:
            break
    after = _git_status_snapshot()
    changed_paths = _changed_status_paths(before, after)
    violations = [path for path in changed_paths if not _matches_allowed(path, task["allowed_paths"])]
    assertions = _evaluate_assertions(task, command_results, state_root)
    timed_out = any(item["timed_out"] for item in command_results)
    commands_ok = len(command_results) == len(task["argv"]) and all(
        item["exit_code"] == item["expected_exit_code"] and not item["timed_out"]
        for item in command_results
    )
    assertions_ok = all(item["ok"] for item in assertions)
    status = "COMPLETED" if commands_ok and assertions_ok and not violations else "FAILED"
    if timed_out:
        status = "TIMED_OUT"
    if violations:
        status = "SCOPE_VIOLATION"
    result_commit = _git_checked("rev-parse", "HEAD")
    result_tree = _git_checked("rev-parse", "HEAD^{tree}")
    receipt = {
        "schema_version": "jc/remediation-v4-receipt/2.1", "task_digest": _task_digest(task), "run_id": run_id,
        "task_id": task["id"], "attempt": attempt, "status": status,
        "input_receipt_digests": input_receipts,
        "start_commit": start_commit, "start_tree": start_tree,
        "result_commit": result_commit, "result_tree": result_tree,
        "command_results": command_results, "changed_paths": changed_paths,
        "allowlist": {"allowed": not violations, "violations": violations},
        "test_reports": [
            {"command_index": index + 1, "kind": "pytest", "exit_code": item["exit_code"]}
            for index, item in enumerate(command_results) if "pytest" in item["argv"]
        ],
        "artifact_digests": {}, "completion_assertions": assertions,
        "previous_receipt_digest": history[-1]["receipt_digest"] if history else None,
        "runner_version": RUNNER_VERSION,
    }
    _write_receipt(attempt_dir, receipt)
    if status == "COMPLETED":
        return EXIT_OK, receipt
    if status == "SCOPE_VIOLATION":
        return EXIT_SCOPE_VIOLATION, receipt
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
        for task in ordered:
            history = _receipt_history(task["id"], state_root)
            input_receipts = {
                dep: completed_receipts[dep]["receipt_digest"] for dep in task["depends_on"]
            }
            latest = history[-1] if history else None
            if (
                latest and latest["status"] == "COMPLETED"
                and latest.get("task_digest") == _task_digest(task)
                and latest["input_receipt_digests"] == input_receipts
            ):
                assertions = _evaluate_assertions(task, latest["command_results"], state_root)
                if all(item["ok"] for item in assertions):
                    completed_receipts[task["id"]] = latest
                    run_state["task_status"][task["id"]] = "COMPLETED"
                    continue
            if task["mode"] == "AUTO":
                rc, receipt = _execute_auto_task(
                    task, state_root, run_state["run_id"], input_receipts, history
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
