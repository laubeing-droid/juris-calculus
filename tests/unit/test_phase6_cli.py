"""Phase 6治理、训练和ADVISORY CLI机器合同。"""

from __future__ import annotations

import json
from pathlib import Path

import compiler_core.cli as cli
from compiler_core.audit_bundle import evaluate_to_audit_bundle
from tests.unit.test_audit_bundle import _fixture


ROOT = Path(__file__).resolve().parents[2]
CASE_INDEX = ROOT / "tests" / "fixtures" / "synthetic_case_index.json"


def _payload(capsys):
    """读取单一stdout JSON并断言stderr为空。"""

    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)


def test_governance_and_training_cli_are_compact_and_non_promoting(tmp_path, capsys) -> None:
    """大候选列表只进入artifact，stdout保持紧凑且禁止自动promotion。"""

    _fixture(tmp_path / "configs")
    state_root = tmp_path / "state"
    assert cli.main([
        "rules", "audit", "fixture-official",
        "--development", "--config-root", str(tmp_path / "configs"),
        "--audit-out", str(state_root), "--json",
    ]) == 0
    governance = _payload(capsys)
    assert governance["candidate_rule_count"] == 0
    assert governance["automatic_promotion"] is False
    assert "candidate_rule_ids" not in governance
    assert governance["artifact_ref"].startswith("governance/")

    output = tmp_path / "training"
    assert cli.main([
        "training", "export", "fixture-official", "--out", str(output), "--seed", "9",
        "--development", "--config-root", str(tmp_path / "configs"), "--json",
    ]) == 0
    training = _payload(capsys)
    assert training["split_seed"] == 9
    assert training["automatic_promotion"] is False
    assert training["private_case_facts_included"] is False


def test_strategy_and_similar_case_cli_only_return_advisory_refs(tmp_path, capsys) -> None:
    """分析CLI返回run绑定摘要，不向stdout复制完整artifact。"""

    loaded, request = _fixture(tmp_path / "configs")
    state_root = tmp_path / "state"
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=state_root)
    run_id = bundle.result.semantic.run_id

    assert cli.main(["analyze", "strategy", "--run", run_id, "--audit-out", str(state_root), "--json"]) == 0
    strategy = _payload(capsys)
    assert strategy["analysis_status"] == "ADVISORY"
    assert strategy["review_required"] is True
    assert strategy["artifact_ref"].startswith("analysis/")
    assert "paths" not in strategy

    assert cli.main([
        "analyze", "similar-cases", "--run", run_id, "--index", str(CASE_INDEX),
        "--audit-out", str(state_root), "--json",
    ]) == 0
    similar = _payload(capsys)
    assert similar["analysis_status"] == "ADVISORY"
    assert similar["quality_status"] == "FIXTURE_ONLY"
    assert similar["review_required"] is True
    assert "matches" not in similar


def test_governance_rejects_repository_state_root(tmp_path, capsys) -> None:
    """治理artifact不得写入跟踪仓库。"""

    _fixture(tmp_path / "configs")
    code = cli.main([
        "rules", "audit", "fixture-official",
        "--development", "--config-root", str(tmp_path / "configs"),
        "--audit-out", str(ROOT / ".forbidden-governance-output"), "--json",
    ])
    captured = capsys.readouterr()
    assert code == cli.EXIT_INPUT_ERROR
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "AUDIT_PATH_IN_REPOSITORY"
