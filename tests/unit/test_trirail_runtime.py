"""共享三轨运行时与 MCP 输出回归测试。"""

import pytest

import tools.press_long_tail as press_long_tail
from tools.run_trirail_matrix import TriRailCollider


@pytest.fixture(scope="module")
def collider() -> TriRailCollider:
    """模块内只加载一次大规则集，避免重复解析 21k 规则。"""
    return TriRailCollider()


def test_normal_scenario_runs_all_tracks_and_reports_inventory(collider):
    result = collider.run_scenario(
        "contract-smoke",
        {
            "description": "来源已核验的中国法规则 smoke",
            "facts": {"breach_alleged": 1.0, "state_compensation": 1.0},
        },
    )

    assert result["fast_path"] is False
    assert {"scenario_id", "classification", "hk", "us", "prc", "rule_inventory", "lsc_boundary"} <= set(result)
    assert result["prc"]["cn_rules_total"] == 21144
    assert result["rule_inventory"]["PRC"]["tracks"]["cn"]["corpus_total"] == 21144
    assert result["prc"]["cn_claims_count"] > 0
    assert result["lsc_boundary"]["formal_kernel_used"] is True
    assert result["lsc_boundary"]["used_rule_ids"] == sorted(result["lsc_boundary"]["used_rule_ids"])


def test_threat_scenario_is_review_only_fast_path(collider):
    result = collider.run_scenario(
        "threat-smoke",
        {"description": "威胁签名 smoke", "facts": {"Alter-Ego": 1.0}},
    )

    assert result["fast_path"] is True
    assert result["lsc_boundary"]["formal_kernel_used"] is False
    assert result["lsc_boundary"]["review_required"] is True
    assert "FAST_PATH_INTERCEPT" in result["lsc_boundary"]["taint"]


def test_long_tail_reuses_shared_collider(monkeypatch, collider):
    monkeypatch.setattr(press_long_tail, "TriRailCollider", lambda: collider)
    engine = press_long_tail.LongTailPressEngine()

    assert engine.collider is collider
