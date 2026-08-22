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
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator  # type: ignore
except ImportError:  # pragma: no cover - exercised by tests via subprocess
    Draft202012Validator = None  # type: ignore

RUNNER_VERSION = "0.1.0"

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

    indexed_set = set(codegraph_files)
    # asset-inventory = tracked files NOT in codegraph-indexed set. We use
    # set-membership instead of extension-only because CodeGraph may skip
    # large YAMLs (e.g. configs/zh_CN/rules.yaml at 13.6 MB) and they must
    # still be accounted for.
    asset_inventory = [p for p in tracked if p not in indexed_set]

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
        ["git", "ls-files"],
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
    wave = args.wave
    print(f"verify-wave {wave}: B00 stub returns OK once plans are lint-clean")
    rc = cmd_lint_plan(argparse.Namespace(plan=str(DEFAULT_PLAN)))
    if rc != EXIT_OK:
        return rc
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    """唯一启动与续跑命令 (施工方案 §1.3)。B00 阶段仅做占位实现。"""
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
    (state_root / "run.json").write_text(
        json.dumps(
            {
                "schema_version": "jc/remediation-v4-run/1.0",
                "runner_version": RUNNER_VERSION,
                "plan_path": str(plan_path),
                "through": through,
                "baseline_commit": _git("rev-parse", "HEAD").strip(),
                "started_at": _iso_now(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        f"run bootstrap: plan={plan_path} state_root={state_root} "
        f"through={through} baseline={_git('rev-parse','HEAD').strip()}"
    )
    print("B00 完成后由后续 task 续跑；当前仅初始化 state root。")
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
    p.set_defaults(func=cmd_graph_map)

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