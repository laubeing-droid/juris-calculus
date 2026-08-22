r"""Tests for the B00-CG verification report (施工方案 §7 B00-CG supplement).

Each high-risk edge from施工方案 §19.1 must be re-verified against exact
source range; the verifier emits a content-addressed JSON report under
\$JC_REMEDIATION_STATE_ROOT/evidence/b00_cg/\$SOURCE_TREE_ID/.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
VERIFIER = REPO / "tools" / "remediate_v4_verify.py"


def _git(*args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    return cp.stdout


def test_verifier_emits_receipt() -> None:
    state_root = REPO.parent / "jc_b00cg_verify_test"
    if state_root.exists():
        import shutil
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        [sys.executable, "-B", str(VERIFIER), "--state-root", str(state_root)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"verifier failed:\n{cp.stdout}\n{cp.stderr}"

    source_tree_id = _git("rev-parse", "HEAD^{tree}").strip()
    out_path = state_root / "evidence" / "b00_cg" / source_tree_id / "verify.json"
    assert out_path.is_file(), f"verify report missing: {out_path}"
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "jc/remediation-v4-b00cg-verify/1.0"
    assert payload["source_tree_id"] == source_tree_id
    assert isinstance(payload["results"], list)
    # The施工方案 §19.1 lists 9 high-risk code claims plus 1 fingerprint check.
    assert len(payload["results"]) >= 9


def test_high_risk_edges_confirmed() -> None:
    """The施工方案 §19.1 high-risk edges must be CONFIRMED against source."""
    state_root = REPO.parent / "jc_b00cg_verify_test2"
    if state_root.exists():
        import shutil
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        [sys.executable, "-B", str(VERIFIER), "--state-root", str(state_root)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"verifier failed:\n{cp.stderr}"

    source_tree_id = _git("rev-parse", "HEAD^{tree}").strip()
    payload = json.loads(
        (state_root / "evidence" / "b00_cg" / source_tree_id / "verify.json").read_text()
    )
    statuses = {r["claim"]: r["status"] for r in payload["results"]}
    # Every code-level claim from施工方案 §19.1 must be CONFIRMED in
    # current source. The CN legacy fingerprint check returns PRESENT
    # because W5-02C has not run yet.
    expected_confirmed = [
        "render_run 被 CLI / JCClient 调用 (施工方案 §19.1)",
        "analyze_strategy / analyze_similar_cases 被 CLI / WorkBuddy MCP 调用",
        "audit_pack 被 CLI 调用",
        "export_corpus_pack 被 CLI 调用",
        "lookup_rules 被 WorkBuddy MCP 调用",
        "litigation_engineering.generate_certificate 被 application._evaluate_once 调用",
        "transformer.auto_patch 函数内 import FixpointEvaluator.__init__",
        "spec_shadow_harness 动态加载 companion spec",
        "plugin_registry 动态加载 addons.*",
    ]
    missing = [c for c in expected_confirmed if statuses.get(c) != "CONFIRMED"]
    assert not missing, (
        f"施工方案 §19.1 high-risk edges NOT confirmed in current source: {missing}"
    )


def test_cn_legacy_fingerprint_present() -> None:
    state_root = REPO.parent / "jc_b00cg_verify_test3"
    if state_root.exists():
        import shutil
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        [sys.executable, "-B", str(VERIFIER), "--state-root", str(state_root)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0
    payload = json.loads(
        (state_root / "evidence" / "b00_cg" / _git("rev-parse", "HEAD^{tree}").strip()
         / "verify.json").read_text()
    )
    fingerprint_status = next(
        r["status"] for r in payload["results"]
        if "configs/zh_CN/rules.yaml" in r["claim"]
    )
    assert fingerprint_status == "PRESENT", (
        "CN legacy rules.yaml fingerprint must be PRESENT before W5-02C"
    )


def test_verify_report_digest_is_reproducible() -> None:
    state_root_a = REPO.parent / "jc_b00cg_verify_a"
    state_root_b = REPO.parent / "jc_b00cg_verify_b"
    for d in (state_root_a, state_root_b):
        if d.exists():
            import shutil
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    for d in (state_root_a, state_root_b):
        cp = subprocess.run(
            [sys.executable, "-B", str(VERIFIER), "--state-root", str(d)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
        )
        assert cp.returncode == 0

    payload_a = json.loads(
        (state_root_a / "evidence" / "b00_cg" / _git("rev-parse", "HEAD^{tree}").strip()
         / "verify.json").read_text()
    )
    payload_b = json.loads(
        (state_root_b / "evidence" / "b00_cg" / _git("rev-parse", "HEAD^{tree}").strip()
         / "verify.json").read_text()
    )
    assert payload_a["digest"] == payload_b["digest"]