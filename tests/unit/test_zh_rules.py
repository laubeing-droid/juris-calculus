"""Negative contract for the retired current-tree CN rule corpus."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_rules_path_is_absent_from_current_consumers() -> None:
    """The exact retired file and every former runtime construction are absent."""

    retired_path = ROOT / "configs" / "zh_CN" / "rules.yaml"
    assert not retired_path.exists()
    for relative in (
        "addons/cn/__init__.py",
        "addons/cn/adapter.py",
        "compiler_core/cli.py",
        "compiler_core/config_paths.py",
        "compiler_core/prc_collision_engine.py",
        "tools/build_rule_pack_manifests.py",
        "tools/run_trirail_matrix.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "zh_CN/rules.yaml" not in source
        assert "cn-legacy-corpus" not in source
