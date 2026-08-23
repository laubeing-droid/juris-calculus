"""TriRail keeps only explicit HK, US, CBL, and SPC candidate inputs."""

import pytest

from tools.run_trirail_matrix import TriRailCollider, generate_heatmap_html


@pytest.fixture(scope="module")
def collider() -> TriRailCollider:
    return TriRailCollider()


def test_runtime_reports_only_retained_candidate_tracks(collider) -> None:
    assert set(collider.pack_digests) == {"HK", "US", "PRC_CBL", "PRC_SPC"}
    assert set(collider.rule_inventory["PRC"]["tracks"]) == {"blocking", "spc"}

    result = collider.run_scenario(
        "contract-smoke",
        {"description": "bounded candidate experiment", "facts": {"breach_alleged": 1.0}},
    )
    assert result["reasoning_boundary"]["formal_kernel_used"] is False
    assert "cn_claims_count" not in result["prc"]
    assert "cn_rules_total" not in result["prc"]


def test_threat_scenario_is_review_only_fast_path(collider) -> None:
    result = collider.run_scenario(
        "threat-smoke",
        {"description": "threat signature smoke", "facts": {"Alter-Ego": 1.0}},
    )
    assert result["fast_path"] is True
    assert result["reasoning_boundary"]["review_required"] is True
    assert "FAST_PATH_INTERCEPT" in result["reasoning_boundary"]["taint"]


def test_heatmap_generation_is_timestamp_free_and_deterministic(tmp_path) -> None:
    first = tmp_path / "first.html"
    second = tmp_path / "second.html"
    generate_heatmap_html({}, first)
    generate_heatmap_html({}, second)
    assert first.read_bytes() == second.read_bytes()
