"""旧报告renderer必须保持纯展示并与正式求值隔离。"""

import json
from dataclasses import asdict

from compiler_core.litigation_renderer import (
    ClaimAnalysis,
    LitigationChainRenderer,
    LitigationReport,
)


def _report() -> LitigationReport:
    """构造不需要规则或求值器的最小展示fixture。"""

    return LitigationReport(
        case_id="run::fixture",
        facts=["fact::a"],
        rules_applied=["rule::a"],
        grounded_summary={"accepted_count": 1, "rejected_count": 0, "undecided_count": 0},
        claim_analyses=[ClaimAnalysis("claim::a", "PROVED", "IN")],
        fail_closed_boundary={
            "horn_truncated": False,
            "grounded_truncated": False,
            "no_uncertainty_upgrade": True,
        },
    )


def test_renderer_has_no_evaluation_entrypoint():
    """展示层不得接受facts/rules后重新推理。"""

    renderer = LitigationChainRenderer()
    assert not hasattr(renderer, "evaluate")
    assert not hasattr(renderer, "evaluate_with_impact")


def test_renderer_produces_deterministic_markdown_from_existing_report():
    """同一报告结构产生相同Markdown。"""

    renderer = LitigationChainRenderer()
    first = renderer.render_markdown(_report())
    second = renderer.render_markdown(_report())
    assert first == second
    assert "claim::a" in first
    assert "PROVED" in first


def test_legacy_report_contract_remains_json_serializable():
    """迁移期数据契约仍可被旧离线报告读取。"""

    assert json.dumps(asdict(_report()), sort_keys=True)
