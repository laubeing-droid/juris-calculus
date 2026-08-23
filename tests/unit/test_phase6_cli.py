"""W5-03 CLI isolation for offline analysis, training, lookup, and governance."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cli_has_no_nonproduction_import_edge() -> None:
    source = (ROOT / "compiler_core/cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert imported.isdisjoint({
        "compiler_core.analysis",
        "compiler_core.training",
        "compiler_core.rule_lookup",
        "compiler_core.rule_governance",
    })


def test_cli_command_tree_omits_offline_source_tools() -> None:
    source = (ROOT / "compiler_core/cli.py").read_text(encoding="utf-8")

    for marker in (
        'commands.add_parser("rules"',
        'commands.add_parser("training"',
        'commands.add_parser("analyze"',
        '"rules.audit"',
        '"training.export"',
        '"analyze.strategy"',
        '"analyze.similar-cases"',
    ):
        assert marker not in source


def test_offline_source_modules_remain_explicit_and_importable() -> None:
    from compiler_core import analysis, rule_lookup, training

    assert "analyze_strategy" in analysis.__all__
    assert rule_lookup.__all__ == ("lookup_rules",)
    assert "export_corpus_pack" in training.__all__
