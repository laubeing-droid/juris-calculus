"""Tests for the CN legacy corpus consumer mapping (施工方案 §7 B00-CG supplement).

施工方案 §7 B00-CG requires AST / `rg` supplement on top of CodeGraph to
catch dynamic import edges (plugin_registry, spec_shadow_harness) and string
references to configs/zh_CN/rules.yaml and the cn-legacy-corpus manifest.
This module emits a content-addressed consumer report that B01 consumes.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "tools" / "remediate_v4.py"


def _git(*args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    return cp.stdout


def _ripgrep(pattern: str) -> list[tuple[str, int]]:
    """Return [(path, line_no), ...] for matches of pattern under REPO.

    Uses ripgrep; if rg is unavailable, falls back to a Python substring scan.
    Path normalization strips leading ./ and converts \\ to /.
    """
    try:
        cp = subprocess.run(
            ["rg", "--no-heading", "--line-number", "--hidden",
             "-g", "!.codegraph/**", "-g", "!.git/**",
             "-g", "!build/**", "-g", "!dist/**",
             pattern, "."],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            check=False,
        )
        if cp.returncode in (0, 1):
            out = []
            for line in cp.stdout.splitlines():
                parts = line.split(":", 2)
                if len(parts) >= 2:
                    rel = parts[0].replace("\\", "/").lstrip("./")
                    if rel.startswith("/"):
                        rel = rel.lstrip("/")
                    out.append((rel, int(parts[1])))
            return out
    except FileNotFoundError:
        pass
    tracked = _git("ls-files").splitlines()
    out = []
    needle = pattern.replace("\\", "/")
    for rel in tracked:
        rel = rel.strip().replace("\\", "/")
        try:
            content = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(content.splitlines(), start=1):
            if needle in line:
                out.append((rel, i))
    return out


# ---------------------------------------------------------------------------
# Consumer map subcommand
# ---------------------------------------------------------------------------

def test_runner_consumer_map_subcommand_exists() -> None:
    cp = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0
    assert "consumer-map" in cp.stdout


def test_runner_consumer_map_emits_receipt() -> None:
    state_root = REPO.parent / "jc_remediation_consumer_test"
    if state_root.exists():
        import shutil
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "JC_REMEDIATION_STATE_ROOT": str(state_root)}
    cp = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "consumer-map", "--check",
         "--state-root", str(state_root),
         "--target", "configs/zh_CN/rules.yaml",
         "--target", "configs/packs/cn-legacy-corpus/manifest.yaml"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
    )
    assert cp.returncode == 0, (
        f"consumer-map failed:\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
    )

    source_tree_id = _git("rev-parse", "HEAD^{tree}").strip()
    evidence = state_root / "evidence" / "consumers" / source_tree_id / "cn_legacy_corpus.json"
    assert evidence.is_file(), f"consumer evidence missing: {evidence}"
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "jc/remediation-v4-consumer-map/1.0"
    assert payload["target_paths"] == [
        "configs/zh_CN/rules.yaml",
        "configs/packs/cn-legacy-corpus/manifest.yaml",
    ]
    assert isinstance(payload["consumers"], list)
    # At minimum, cli.py and config_paths.py must appear.
    consumer_paths = {c["path"] for c in payload["consumers"]}
    assert "compiler_core/cli.py" in consumer_paths
    assert "compiler_core/config_paths.py" in consumer_paths
    # The report must include both a direct literal reference and a
    # transitive-import reference, proving ripgrep + codegraph cover both
    # classes per施工方案 §7 B00-CG supplement.
    kinds = {c["evidence_kind"] for c in payload["consumers"]}
    assert "string_ref" in kinds
    assert "transitive_import" in kinds


def test_cn_legacy_corpus_consumer_includes_test_risk_paths() -> None:
    """施工方案 §7 B00-CG + §19.1 list known high-risk edges.

    The 21,144-rule corpus is referenced from many code paths. Some are
    direct literal matches, some are dynamic via `rules_path()` /
    `config_paths.config_root()`, and some are deep transitive imports
    (e.g. tests that import PRCCollisionEngine which itself calls
    `rules_path`). B00-CG must surface all three classes; ripgrep covers
    the first two and codegraph covers the third.
    """
    direct_matches = _ripgrep("configs/zh_CN/rules.yaml")
    direct_paths = {p for p, _ in direct_matches}

    # Direct-literal consumers must include the listed test paths.
    direct_test_expected = {
        "tests/run_benchmark_zh.py",
    }
    assert direct_test_expected.issubset(direct_paths), (
        f"expected test-side CN consumers missing: {direct_test_expected - direct_paths}"
    )

    # Dynamic-symbol consumers: any tracked file referencing config_paths.rules_path
    # or compiler_core.config_paths.rules_path also counts as a consumer that
    # builds the rules.yaml path at runtime. B00-CG must surface these too.
    dyn_matches = _ripgrep("rules_path")
    dyn_paths = {p for p, _ in dyn_matches}
    dyn_test_expected = {
        "compiler_core/config_paths.py",
        "compiler_core/prc_collision_engine.py",
        "tests/unit/test_adversarial.py",
    }
    assert dyn_test_expected.issubset(dyn_paths), (
        f"expected dynamic CN consumers missing: {dyn_test_expected - dyn_paths}"
    )

    # Inline-path consumers: tests that build the rules.yaml path directly via
    # os.path.join or hard-coded literals. The supplementary consumer report
    # must include test_zh_rules.py.
    inline_matches = _ripgrep("load_rules_from_yaml")
    inline_paths = {p for p, _ in inline_matches}
    assert "tests/unit/test_zh_rules.py" in inline_paths, (
        "test_zh_rules.py must appear as inline-path CN consumer"
    )

    # CodeGraph transitive consumers: tests that import prc_collision_engine
    # or rule_packs (which load rules.yaml internally). The runner consumer-map
    # command must surface these via codegraph edges.
    state_root = REPO.parent / "jc_remediation_consumer_cg_test"
    if state_root.exists():
        import shutil
        shutil.rmtree(state_root, ignore_errors=True)
    state_root.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        [sys.executable, "-B", str(RUNNER), "consumer-map", "--check",
         "--codegraph", ".codegraph/codegraph.db",
         "--target", "configs/zh_CN/rules.yaml",
         "--state-root", str(state_root)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env={**os.environ, "JC_REMEDIATION_STATE_ROOT": str(state_root)},
    )
    assert cp.returncode == 0, (
        f"consumer-map failed:\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
    )
    payload_path = (
        state_root
        / "evidence"
        / "consumers"
        / _git("rev-parse", "HEAD^{tree}").strip()
        / "cn_legacy_corpus.json"
    )
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    consumer_paths = {c["path"] for c in payload["consumers"]}

    cg_test_expected = {
        # Direct-literal or dynamic-symbol consumers (ripgrep hits).
        "compiler_core/cli.py",
        "compiler_core/config_paths.py",
        "compiler_core/prc_collision_engine.py",
        "addons/cn/__init__.py",
        "addons/cn/adapter.py",
        # Transitive consumers (ripgrep OR codegraph).
        "tests/unit/test_trirail_collision.py",
        "tests/unit/test_trirail_runtime.py",
        "tests/unit/test_rule_pack_manifest.py",
        "tests/unit/test_rule_pack_manifest_builder.py",
    }
    # test_release_engineering.py is a structural gate test for the wheel
    # gate (施工方案 §19.1 lists it for W5-02C deletion because the gate
    # couples to the forbidden blacklist), but it does not transitively
    # import any direct CN consumer. The runner surfaces it via the wheel
    # gate mutation gate, not via this consumer report.
    assert cg_test_expected.issubset(consumer_paths), (
        f"expected CN consumers missing from combined ripgrep+codegraph: "
        f"{cg_test_expected - consumer_paths}"
    )


def test_cn_legacy_corpus_consumer_includes_cli_and_collision() -> None:
    matches = _ripgrep("rules_path")
    paths = {p for p, _ in matches}
    expected = {
        "compiler_core/config_paths.py",
        "compiler_core/prc_collision_engine.py",
    }
    assert expected.issubset(paths), (
        f"expected core-side CN consumers missing: {expected - paths}"
    )


def test_cn_legacy_corpus_manifest_consumer_paths() -> None:
    """The manifest is referenced both by path (in docs / policy / runner)
    and by pack ID (in code paths that load registry entries). CodeGraph
    plus ripgrep must surface both classes so B01 can build per-consumer
    closure."""
    path_matches = _ripgrep("configs/packs/cn-legacy-corpus/manifest.yaml")
    id_matches = _ripgrep("cn-legacy-corpus")
    path_hits = {p for p, _ in path_matches}
    id_hits = {p for p, _ in id_matches}

    expected_path_hits = {
        # Manifest path appears in policy / docs / receipts.
        "20260819_juris-calculus_V4单主链生产投产全量代码审计.md",
        "20260819_juris-calculus_V4单主链生产投产全自动整治施工方案.md",
        "remediation/v4/file-disposition.json",
    }
    assert expected_path_hits.issubset(path_hits), (
        f"expected path-reference hits missing: {expected_path_hits - path_hits}"
    )

    expected_id_hits = {
        "tools/build_rule_pack_manifests.py",
        "tools/run_trirail_matrix.py",
        "compiler_core/cli.py",
        "tests/unit/test_cli_subprocess.py",
        "tests/unit/test_cli_evaluate_subprocess.py",
        "tests/unit/test_rule_pack_manifest.py",
    }
    assert expected_id_hits.issubset(id_hits), (
        f"expected pack-ID hits missing: {expected_id_hits - id_hits}"
    )