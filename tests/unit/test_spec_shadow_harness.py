from pathlib import Path

from compiler_core.spec_shadow_harness import (
    SPEC_REPO_ROOT,
    _build_contract_fixture,
    _build_license_fixture,
    build_cross_repo_differential_report,
    build_jc_shadow_payload,
    run_fixture_comparison,
)


def test_contract_shadow_fixture_aligns_with_spec():
    fixture = _build_contract_fixture(False)
    result = run_fixture_comparison(fixture, SPEC_REPO_ROOT)

    assert result["report"]["status"] == "ALIGNED"
    assert result["jc"]["status"] == "PROVED"
    assert result["jc"]["checker_verdict"]["ok"] is True


def test_force_majeure_shadow_fixture_aligns_with_spec():
    fixture = _build_contract_fixture(True)
    result = run_fixture_comparison(fixture, SPEC_REPO_ROOT)

    assert result["report"]["status"] == "ALIGNED"
    assert result["jc"]["status"] == "REFUTED"
    assert result["jc"]["checker_verdict"]["ok"] is True


def test_priority_shadow_fixture_aligns_with_spec():
    fixture = _build_license_fixture(True)
    result = run_fixture_comparison(fixture, SPEC_REPO_ROOT)

    assert result["report"]["status"] == "ALIGNED"
    assert result["jc"]["status"] == "PROVED"
    assert "PRIORITY_DEFEAT" in result["jc"]["attack_kinds"]


def test_priority_off_shadow_fixture_aligns_with_spec():
    fixture = _build_license_fixture(False)
    result = run_fixture_comparison(fixture, SPEC_REPO_ROOT)

    assert result["report"]["status"] == "ALIGNED"
    assert result["jc"]["status"] == "REFUTED"


def test_cross_repo_differential_report_counts_all_fixtures(tmp_path):
    report = build_cross_repo_differential_report(SPEC_REPO_ROOT)

    assert report["summary"]["fixture_count"] == 10
    assert report["summary"]["aligned_count"] == 8
    assert report["summary"]["diverged_count"] == 2  # admin slice spec-side priority bug, tracked separately
