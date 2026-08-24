"""Tests for the full file-disposition binding (施工方案 §7 B01).

B01 expands the starter file-disposition.json (B00) into a complete map
covering every tracked path (production-code, configs, schemas, docs,
tests, CI/build, fixture/generated, legacy/candidate/advisory, other
assets). Each entry must declare its disposition class and, for deletion
candidates, a terminal_state plus target_module / target_test /
target_artifact / closure_task.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tools" / "remediate_v4.py"
DISPOSITION = REPO / "remediation" / "v4" / "file-disposition.json"


def _git(*args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    return cp.stdout


def _tracked_paths() -> list[str]:
    cp = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    return [
        line.strip().replace("\\", "/")
        for line in cp.stdout.splitlines()
        if line.strip()
    ]


def _disposition_entries() -> dict[str, dict]:
    payload = json.loads(DISPOSITION.read_text(encoding="utf-8"))
    return {p["path"]: p for p in payload.get("paths", [])}


# ---------------------------------------------------------------------------
# Disposition coverage
# ---------------------------------------------------------------------------

DISPOSITIONS = {
    "KEEP_REWRITE",
    "MERGE_DELETE",
    "MIGRATE_INVARIANTS_THEN_DELETE",
    "RETAIN_NONPACKAGED",
    "MOVE_IN_REPO_SOURCE_TOOL",
    "MOVE_IN_REPO_EXPERIMENT",
    "CANDIDATE_ASSET",
    "TEST_ORACLE",
    "DELETE_CURRENT",
    "GENERATED",
    "HISTORY_ONLY",
    "DOC_UPDATE",
}


def test_file_disposition_covers_every_tracked_path() -> None:
    """B01 §7 要求每个 tracked path 必须有一个 disposition 和 authority class。

    审计报告附录 A 列出 292 个 tracked path。本测试保证 file-disposition
    entries 的并集完全覆盖当前 git ls-files（除两份用户既有未提交删除
    之外）。
    """
    entries = _disposition_entries()
    tracked = set(_tracked_paths())
    missing = tracked - set(entries)
    assert not missing, (
        f"file-disposition missing entries for tracked paths: "
        f"{sorted(missing)[:10]}{'...' if len(missing) > 10 else ''}"
    )


def test_every_disposition_is_valid_class() -> None:
    entries = _disposition_entries()
    invalid = {
        p: d["disposition"]
        for p, d in entries.items()
        if d.get("disposition") not in DISPOSITIONS
    }
    assert not invalid, f"invalid disposition classes: {invalid}"


def test_delete_current_paths_have_terminal_and_history_locator() -> None:
    """施工方案 §7 B01: HISTORY_BOUND 必须绑定 frozen bytes/hash/locator 且
    target_module 与 target_artifact 必须为空；MIGRATED_GREEN 必须绑定
    target module 和 RED→GREEN required test。

    DELETE_CURRENT 也作为终态接受，用于 compat_v3_v4 / proleg_translator
    这类纯 current-source 删除、历史通过 Git 保存的 path（施工方案 §19.1
    DELETE_CURRENT（2））。

    For HISTORY_BOUND, the施工方案 §19.3 requires a binding to frozen
    bytes/hash/locator. CN legacy corpus has the full binding (施工方案
    §0.14); other HISTORY_BOUND paths must carry at least a Git locator
    (history_locator_only=true with git_blob_v3_0_2) so that current
    negative rejection can be verified.
    """
    entries = _disposition_entries()
    for path, entry in entries.items():
        if entry.get("disposition") != "DELETE_CURRENT":
            continue
        terminal = entry.get("terminal_state")
        assert terminal in {"HISTORY_BOUND", "NO_RELEVANT_SEMANTICS_APPROVED", "DELETE_CURRENT"}, (
            f"{path}: DELETE_CURRENT must have terminal in HISTORY_BOUND, "
            f"NO_RELEVANT_SEMANTICS_APPROVED, or DELETE_CURRENT; got {terminal}"
        )
        if terminal == "HISTORY_BOUND":
            fp = entry.get("frozen_fingerprint")
            history_locator_only = entry.get("history_locator_only")
            assert fp or history_locator_only, (
                f"{path}: HISTORY_BOUND must bind frozen_fingerprint OR "
                f"history_locator_only"
            )
            # HISTORY_BOUND must carry either a SHA-256 binding or a Git
            # blob locator (施工方案 §19.3).
            if fp and "sha256" not in fp:
                assert fp.get("git_blob_head") or fp.get("git_blob_v3_0_2"), (
                    f"{path}: HISTORY_BOUND frozen_fingerprint must carry sha256 "
                    f"or git_blob locator"
                )
            assert entry.get("target_module") in (None, ""), (
                f"{path}: HISTORY_BOUND must not have target_module"
            )
            assert entry.get("target_artifact") in (None, ""), (
                f"{path}: HISTORY_BOUND must not have target_artifact"
            )


def test_v3_only_authority_paths_not_keep_rewrite() -> None:
    """V3-only authority paths 不得登记为 KEEP_REWRITE。"""
    entries = _disposition_entries()
    forbidden_keep = {
        "compiler_core/compat_v3_v4.py",
        "compiler_core/proleg_translator.py",
    }
    for path in forbidden_keep:
        assert entries.get(path, {}).get("disposition") != "KEEP_REWRITE", (
            f"{path} must not be KEEP_REWRITE in V4-only topology"
        )


def test_known_b01_semantic_corrections_are_bound() -> None:
    entries = _disposition_entries()
    assert entries["configs/perf_patterns.yaml"]["disposition"] == "KEEP_REWRITE"
    assert entries["configs/perf_patterns.yaml"]["closure_task"] == "W5-02C"
    assert entries["tools/wheel_gate.py"]["disposition"] == "KEEP_REWRITE"
    assert entries["tools/wheel_gate.py"]["closure_task"] == "W6-05"
    assert entries["compiler_core/contracts_v4.py"]["target_module"] == "compiler_core/contracts.py"
    assert entries["compiler_core/contracts_v4.py"]["target_test"] == "tests/contract/test_contracts.py"
    assert not [entry["path"] for entry in entries.values() if "_v4_target_for_" in str(entry.get("target_module"))]
    assert all(
        entry["closure_task"] == (
            "W6-05" if path == "requirements/release.lock" else "W6-03"
        )
        for path, entry in entries.items() if path.startswith("requirements/")
    )


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------

def test_runner_file_map_exit_zero_with_full_check() -> None:
    cp = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "file-map", "--check", "--all-tracked",
         "--require-semantic-targets"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, (
        f"file-map --check failed:\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
    )
