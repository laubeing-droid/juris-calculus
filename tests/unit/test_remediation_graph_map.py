"""Tests for the CodeGraph reconciliation gate (施工方案 §7 B00-CG).

These tests are RED until the runner implements real reconciliation. They
lock the contract: tracked Python+YAML must equal codegraph-indexed files;
tracked JSON/Markdown/lock/asset files must equal asset-inventory; CN
legacy corpus (configs/zh_CN/rules.yaml) belongs to asset-inventory only;
the normalized graph digest is content-addressed and reproducible.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tools" / "remediate_v4.py"
CODEGRAPH_DB = REPO / ".codegraph" / "codegraph.db"
CODEGRAPH_DIR = REPO / ".codegraph"


def _git(*args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    return cp.stdout


def _tracked_files() -> list[str]:
    out = _git("ls-files")
    return [line for line in out.splitlines() if line]


def _asset_inventory() -> list[str]:
    """Asset inventory: every tracked file that CodeGraph did NOT index.

    CodeGraph 0.9.9 indexes Python + YAML, but it may skip very large YAMLs
    (configs/zh_CN/rules.yaml is 13.6 MB) or files with parse errors. Asset
    inventory closes the union so the runner can prove tracked ==
    codegraph-indexed ∪ asset-inventory (施工方案 §7 B00-CG).
    """
    indexed = set(_codegraph_indexed_files())
    return [p for p in _tracked_files() if p not in indexed]


def _codegraph_indexed_files() -> list[str]:
    if not CODEGRAPH_DB.is_file():
        return []
    conn = sqlite3.connect(str(CODEGRAPH_DB))
    try:
        rows = conn.execute("SELECT path FROM files").fetchall()
    finally:
        conn.close()
    return sorted({row[0].replace("\\", "/") for row in rows})


def _codegraph_unresolved() -> int:
    if not CODEGRAPH_DB.is_file():
        return -1
    conn = sqlite3.connect(str(CODEGRAPH_DB))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='unresolved_refs'"
        ).fetchall()
        if not rows:
            return 0
        return conn.execute("SELECT COUNT(*) FROM unresolved_refs").fetchone()[0]
    finally:
        conn.close()


def _codegraph_parse_errors() -> int:
    if not CODEGRAPH_DB.is_file():
        return -1
    conn = sqlite3.connect(str(CODEGRAPH_DB))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='parse_errors'"
        ).fetchall()
        if not rows:
            return 0
        return conn.execute("SELECT COUNT(*) FROM parse_errors").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CodeGraph presence
# ---------------------------------------------------------------------------

def test_codegraph_directory_exists() -> None:
    assert CODEGRAPH_DIR.is_dir(), (
        f"CodeGraph not initialized: missing {CODEGRAPH_DIR}; run codegraph init first"
    )


def test_codegraph_db_exists() -> None:
    assert CODEGRAPH_DB.is_file(), f"missing {CODEGRAPH_DB}"


def test_codegraph_db_zero_unresolved_refs() -> None:
    assert _codegraph_unresolved() == 0, (
        f"unresolved refs in codegraph: {_codegraph_unresolved()}"
    )


def test_codegraph_db_zero_parse_errors() -> None:
    assert _codegraph_parse_errors() == 0, (
        f"parse errors in codegraph: {_codegraph_parse_errors()}"
    )


# ---------------------------------------------------------------------------
# tracked union = codegraph-indexed ∪ asset-inventory
# ---------------------------------------------------------------------------

def test_tracked_union_equals_graph_plus_assets() -> None:
    tracked = set(_tracked_files())
    indexed = set(_codegraph_indexed_files())
    assets = set(_asset_inventory())

    # Every tracked file must be either codegraph-indexed or in asset inventory.
    missing = tracked - (indexed | assets)
    assert not missing, f"tracked files outside both codegraph + assets: {sorted(missing)[:20]}"

    # Files in codegraph must also be tracked (no orphan graph entries).
    orphan_graph = indexed - tracked
    assert not orphan_graph, f"codegraph entries not in tracked: {sorted(orphan_graph)[:20]}"


def test_cn_legacy_rules_yaml_not_in_codegraph() -> None:
    """configs/zh_CN/rules.yaml is a 13.6 MB YAML; it must NOT be in codegraph because
    CodeGraph cannot parse it; it must be in asset inventory."""
    indexed = set(_codegraph_indexed_files())
    assert "configs/zh_CN/rules.yaml" not in indexed, (
        "configs/zh_CN/rules.yaml must not be parsed by codegraph"
    )
    assert "configs/zh_CN/rules.yaml" in set(_asset_inventory())


# ---------------------------------------------------------------------------
# Runner graph-map command produces real reconciliation (not stub)
# ---------------------------------------------------------------------------

def test_runner_graph_map_returns_exit_0_with_real_check() -> None:
    cp = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "graph-map", "--check",
         "--codegraph", ".codegraph/codegraph.db", "--all-tracked"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, (
        f"graph-map --check must reconcile tracked ∪ codegraph ∪ assets; "
        f"got exit={cp.returncode}\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
    )


def test_runner_graph_map_produces_normalized_receipt() -> None:
    """The runner must persist a content-addressed normalized graph receipt
    under $JC_REMEDIATION_STATE_ROOT/evidence/codegraph/$SOURCE_TREE_ID/."""
    state_root = REPO.parent / "jc_remediation_state_b00_cg_test"
    if state_root.exists():
        import shutil
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    env = {**__import__("os").environ, "JC_REMEDIATION_STATE_ROOT": str(state_root)}
    cp = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "graph-map", "--check",
         "--codegraph", ".codegraph/codegraph.db", "--all-tracked",
         "--state-root", str(state_root)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
    )
    assert cp.returncode == 0, (
        f"graph-map failed:\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
    )

    source_tree_id = _git("rev-parse", "HEAD^{tree}").strip()
    evidence_dir = state_root / "evidence" / "codegraph" / source_tree_id
    assert evidence_dir.is_dir(), f"evidence dir missing: {evidence_dir}"

    normalized = evidence_dir / "normalized.json"
    assert normalized.is_file(), f"normalized graph receipt missing: {normalized}"
    payload = json.loads(normalized.read_text(encoding="utf-8"))

    expected_keys = {
        "schema_version",
        "source_tree_id",
        "codegraph_file_count",
        "codegraph_node_count",
        "codegraph_edge_count",
        "codegraph_unresolved",
        "codegraph_parse_errors",
        "tracked_file_count",
        "asset_inventory_count",
        "missing_from_union",
        "orphan_graph_entries",
        "digest",
    }
    assert expected_keys.issubset(payload.keys()), (
        f"normalized receipt missing keys: {expected_keys - set(payload.keys())}"
    )
    assert payload["source_tree_id"] == source_tree_id
    assert payload["codegraph_unresolved"] == 0
    assert payload["codegraph_parse_errors"] == 0
    assert payload["missing_from_union"] == []
    assert payload["orphan_graph_entries"] == []

    # Digest must be content-addressed and reproducible.
    canon = json.dumps({k: payload[k] for k in sorted(payload) if k != "digest"},
                       sort_keys=True, separators=(",", ":"))
    expected_digest = "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()
    assert payload["digest"] == expected_digest, (
        f"digest mismatch: {payload['digest']} != {expected_digest}"
    )


# ---------------------------------------------------------------------------
# Import/call/consumer mapping — concrete graph conclusions
# ---------------------------------------------------------------------------

def test_cn_legacy_corpus_consumers_in_compiler_core() -> None:
    """At minimum, compiler_core/{cli,config_paths,prc_collision_engine}.py
    must show graph references to configs/zh_CN/rules.yaml in source.

    This is an absolute-low-bar smoke for CodeGraph's import resolution; the
    full B01 task will expand to consumer mapping per施工方案 §19.1.
    """
    cli_text = (REPO / "compiler_core" / "cli.py").read_text(encoding="utf-8", errors="replace")
    config_text = (REPO / "compiler_core" / "config_paths.py").read_text(encoding="utf-8", errors="replace")
    prc_text = (REPO / "compiler_core" / "prc_collision_engine.py").read_text(encoding="utf-8", errors="replace")
    rules_text = "configs/zh_CN/rules.yaml"
    assert rules_text in cli_text or rules_text in config_text or rules_text in prc_text, (
        "CN legacy rules.yaml must be referenced in at least one compiler_core consumer"
    )