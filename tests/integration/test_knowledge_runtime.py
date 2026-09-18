"""知识运行时全链（03 卡 §4b：tests/integration/test_knowledge_runtime.py）。

规则准入 → 切分导出（split_mode 真实生效）→ 真实训练（薄入口子进程）
→ checkpoint 消费（predict_outcome 概率随输入变化）→ 增量求解等价。
全部走真实公开入口；本仓合成验收包，mock 不进本文件。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from compiler_core.client import ClientV4Error, create_local_client
from compiler_core.contracts import ContentRefV4, DigestV4, IncrementalParentV5
from compiler_core.training import export_rules_as_jsonl

from tests.local.test_local_runtime import FULL_FACTS, QUERIES, RULE_PACK

REPO = Path(__file__).resolve().parents[2]


def _rule_root(tmp_path: Path) -> Path:
    root = tmp_path / "rules"
    root.mkdir(parents=True, exist_ok=True)
    (root / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8",
    )
    return root


def _client(tmp_path: Path):
    client = create_local_client(tmp_path / "state", _rule_root(tmp_path))
    claims = {row["rule_id"]: row["claim"] for row in client.local_pack()["rules"]}
    return client, claims


def _issue_queries(claims):
    return [
        {"issue_id": q["query_id"], "claim": claims[q["claim"]], "profile": q["profile"]}
        for q in QUERIES
    ]


# ---------------------------------------------------------------------------
# 规则准入：jc.admit_verified_rule_pack（真实落盘 + 幂等重放）
# ---------------------------------------------------------------------------


def test_admit_verified_rule_pack_persists_and_replays(tmp_path):
    client, _claims = _client(tmp_path)
    decision_ref = {
        "owner": "harness", "kind": "human-decision", "id": "md-001",
        "version": "1", "matterId": None, "digest": "sha256:" + "a" * 64,
    }
    pack_path = tmp_path / "rules" / "jc-local-pack.json"
    result = client.admit_verified_rule_pack({
        "packURI": str(pack_path),
        "expectedRuleVersion": "1.0.0",
        "machineDecisionRef": decision_ref,
        "admittedRoot": tmp_path / "admitted-packs",
    })
    assert result["oldRuleVersion"] is None
    assert result["newRuleVersion"] == "1.0.0"
    assert result["replay"] is False
    assert result["admissionReceiptRef"]["kind"] == "rule-admission"
    # 同载荷重放：同一收据，不双发
    replay = client.admit_verified_rule_pack({
        "packURI": str(pack_path),
        "machineDecisionRef": decision_ref,
        "admittedRoot": tmp_path / "admitted-packs",
    })
    assert replay["replay"] is True
    assert replay["admissionReceiptRef"] == result["admissionReceiptRef"]
    # 同版本异载荷：revision_conflict
    mutated = json.loads(pack_path.read_text(encoding="utf-8"))
    mutated["rules"] = mutated["rules"][:1]
    mutated["pack_version"] = "1.0.0"
    variant = tmp_path / "rules" / "variant"
    variant.mkdir()
    (variant / "jc-local-pack.json").write_text(
        json.dumps(mutated, ensure_ascii=False), encoding="utf-8",
    )
    with pytest.raises(ClientV4Error) as error:
        client.admit_verified_rule_pack({
            "packURI": str(variant / "jc-local-pack.json"),
            "machineDecisionRef": decision_ref,
            "admittedRoot": tmp_path / "admitted-packs",
        })
    assert error.value.code == "revision_conflict"
    # 落盘可读：准入目录含 CURRENT.json 与包文件（pack id 取文件 stem）
    assert (tmp_path / "admitted-packs" / "jc-local-pack" / "1.0.0" / "jc-local-pack.json").is_file()


def test_admit_requires_machine_decision(tmp_path):
    client, _claims = _client(tmp_path)
    pack_path = tmp_path / "rules" / "jc-local-pack.json"
    with pytest.raises(ClientV4Error) as error:
        client.admit_verified_rule_pack({
            "packURI": str(pack_path),
            "admittedRoot": tmp_path / "admitted-packs",
        })
    assert error.value.code == "INVALID_ADMIT_INPUT"


# ---------------------------------------------------------------------------
# 切分诚实：export_rules_as_jsonl 的 split_mode 真实生效（rng.shuffle 缺陷回归）
# ---------------------------------------------------------------------------


def _rule_yaml(tmp_path: Path, rows: list[dict]):
    path = tmp_path / "rules.yaml"
    lines = ["rules:"]
    for row in rows:
        block = [
            "- id: " + row["id"],
            "  valid_from: '" + row["valid_from"] + "'",
            "  premise_atoms: []",
            "  head_claim: ''",
        ]
        if row.get("jurisdiction"):
            block.append("  jurisdiction: " + row["jurisdiction"])
        lines.extend(block)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_export_group_split_keeps_packs_whole(tmp_path):
    packs = {}
    for pack_index, pack_id in enumerate(["pack-a", "pack-b", "pack-c", "pack-d"]):
        rows = [
            {"id": f"{pack_id}-{i}", "valid_from": "2025-01-01", "jurisdiction": pack_id}
            for i in range(3)
        ]
        (tmp_path / f"{pack_index}").mkdir(parents=True, exist_ok=True)
        packs[pack_id] = _rule_yaml(tmp_path / f"{pack_index}", rows)
    manifest = export_rules_as_jsonl(
        list(packs.values()),
        tmp_path / "out" / "rules.jsonl",
        split_train=0.5, split_dev=0.0, split_test=0.5,
        split_mode="group", seed=7,
    )
    assert manifest["split_mode"] == "group"
    split_of = {}
    for name in ("train", "dev", "test"):
        split_file = (tmp_path / "out" / f"rules_{name}.jsonl")
        for line in split_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                split_of[row["jurisdiction"]] = name
    # 每个 pack（jurisdiction 分组）的所有行落在同一切分
    train_packs = {p for p, s in split_of.items() if s == "train"}
    test_packs = {p for p, s in split_of.items() if s == "test"}
    assert train_packs and test_packs
    assert not (train_packs & test_packs)


def test_export_time_split_is_chronological(tmp_path):
    rows = [
        {"id": f"r{i}", "valid_from": f"2024-{month:02d}-01"}
        for i, month in enumerate(range(1, 11), start=1)
    ]
    path = _rule_yaml(tmp_path, rows)
    manifest = export_rules_as_jsonl(
        [path], tmp_path / "out" / "rules.jsonl",
        split_train=0.5, split_dev=0.0, split_test=0.5,
        split_mode="time", seed=1,
    )
    train_months = [
        json.loads(line)["valid_from"]
        for line in (tmp_path / "out" / "rules_train.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    test_months = [
        json.loads(line)["valid_from"]
        for line in (tmp_path / "out" / "rules_test.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert train_months == sorted(train_months)
    assert test_months == sorted(test_months)
    assert max(train_months) <= min(test_months)


def test_export_rejects_unsupported_split_mode(tmp_path):
    path = _rule_yaml(tmp_path, [{"id": "r1", "valid_from": "2024-01-01"}])
    with pytest.raises(ValueError) as error:
        export_rules_as_jsonl(
            [path], tmp_path / "out" / "rules.jsonl", split_mode="vector",
        )
    assert "unsupported_split_mode" in str(error.value)


# ---------------------------------------------------------------------------
# 真实训练：tools/train_and_evaluate.py 薄入口（子进程公开入口）
# ---------------------------------------------------------------------------


def _write_case_dataset(path: Path, n: int = 240) -> None:
    import random as _random

    rng = _random.Random(11)
    lines = []
    for _ in range(n):
        f1 = rng.random()
        f2 = rng.random()
        score = 3.0 * f1 - 2.0 * f2 - 0.5
        label = 1 if score > 0 else 0
        lines.append(json.dumps({
            "features": {"f1": round(f1, 4), "f2": round(f2, 4)},
            "label": label,
            "groupId": f"g{_random.Random(int(f1 * 1000)).randrange(8)}",
        }, sort_keys=True))
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    root = tmp_path_factory.mktemp("jc-knowledge-runtime")
    dataset = root / "dataset.jsonl"
    _write_case_dataset(dataset)
    config = {
        "schema_version": "jc-train-eval/1",
        "task": "case_outcome",
        "dataset": str(dataset),
        "split": {"mode": "group", "seed": 5, "train": 0.7, "dev": 0.15, "test": 0.15},
        "model": {"type": "logreg", "epochs": 500, "learningRate": 0.5, "l2": 1e-3},
        "target": {"eventDefinition": "dismissal_affirmed"},
        "dataVersion": "synthetic-acceptance/1",
    }
    config_path = root / "config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    output = root / "models"
    completed = subprocess.run(
        [sys.executable, "-B", str(REPO / "tools" / "train_and_evaluate.py"),
         "--config", str(config_path), "--output", str(output)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(REPO), timeout=600,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(REPO)},
    )
    assert completed.returncode == 0, f"trainer failed: {completed.stderr}"
    return {
        "root": root,
        "output": output / "dismissal_affirmed",
        "summary": json.loads(completed.stdout),
    }


def test_trainer_writes_real_checkpoint_and_evaluation(trained):
    checkpoint = json.loads((trained["output"] / "checkpoint.json").read_text(encoding="utf-8"))
    evaluation = json.loads((trained["output"] / "evaluation.json").read_text(encoding="utf-8"))
    assert checkpoint["schema_version"] == "jc-prediction-checkpoint/1"
    assert checkpoint["eventDefinition"] == "dismissal_affirmed"
    assert checkpoint["featureOrder"] == ["f1", "f2"]
    # 参数真的被训练过：权重非零
    assert any(abs(w) > 1e-6 for w in checkpoint["parameters"]["weights"].values())
    assert evaluation["leakage"] == {"testUsedForTraining": False, "testUsedForIntervalFit": False}
    assert evaluation["test"]["n"] > 0
    assert evaluation["test"]["accuracy"] >= 0.8
    assert evaluation["test"]["brier"] <= 0.2
    assert (trained["output"] / "splits" / "test.jsonl").is_file()


def test_predict_outcome_consumes_trained_checkpoint(trained, tmp_path_factory):
    state = tmp_path_factory.mktemp("jc-predict-state")
    rules = state / "rules"
    rules.mkdir()
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8",
    )
    client = create_local_client(state / "state", rules)
    env_input = {
        "modelRoot": str(trained["output"]),
        "eventDefinition": "dismissal_affirmed",
        "observationPoint": "2026-09-19",
        "issueIds": ["issue-1"],
        "ruleVersion": "1",
        "dataVersion": "synthetic-acceptance/1",
    }
    strong = client.predict_outcome({**env_input, "features": {"f1": "0.95", "f2": "0.05"}})
    weak = client.predict_outcome({**env_input, "features": {"f1": "0.05", "f2": "0.95"}})
    assert 0.0 <= float(strong["probability"]) <= 1.0
    # 概率随输入真实变化：已训练模型不是固定输出
    assert float(strong["probability"]) > float(weak["probability"])
    for row in (strong, weak):
        interval = row["interval"]
        assert float(interval["low"]) <= float(row["probability"]) <= float(interval["high"])
        assert interval["level"] == "0.95"
        assert row["guaranteeLevel"] is None
    # 模型版本不匹配 → 具名不可用
    with pytest.raises(ClientV4Error) as error:
        client.predict_outcome({
            **env_input,
            "modelVersion": "logreg-l2/does-not-exist",
            "features": {"f1": "0.5", "f2": "0.5"},
        })
    assert error.value.code == "model_not_available"


def test_predict_outcome_without_model_root_is_named_absent(tmp_path):
    client, _claims = _client(tmp_path)
    with pytest.raises(ClientV4Error) as error:
        client.predict_outcome({
            "eventDefinition": "dismissal_affirmed",
            "observationPoint": "2026-09-19",
            "issueIds": ["issue-1"],
            "features": {"f1": "0.5", "f2": "0.5"},
        })
    assert error.value.code == "model_not_available"
    with pytest.raises(ClientV4Error) as error:
        client.predict_outcome({
            "modelRoot": str(tmp_path / "no-models"),
            "eventDefinition": "other_event",
            "observationPoint": "2026-09-19",
            "issueIds": ["issue-1"],
            "features": {"f1": "0.5", "f2": "0.5"},
        })
    assert error.value.code == "model_not_available"


# ---------------------------------------------------------------------------
# 终局统计 / 偏离排序：真实当前态（case.* 读面未接 → 具名状态，不假造）
# ---------------------------------------------------------------------------


def test_terminal_state_stats_without_reader_is_named_absent(tmp_path):
    client, _claims = _client(tmp_path)
    with pytest.raises(ClientV4Error) as error:
        client.terminal_state_stats({"datasetVersion": "pub-1"})
    assert error.value.code == "dataset_version_not_found"


def test_deviation_rank_without_reader_reports_not_compiled(tmp_path):
    client, _claims = _client(tmp_path)
    result = client.deviation_rank({
        "baselineRuleVersion": "1",
        "queryStructure": {"elements": ["contract"]},
        "candidates": [],
        "budget": 10,
    })
    assert result["status"] == "not_compiled"
    assert result["items"] == []


# ---------------------------------------------------------------------------
# 增量求解：真实追加运行进入增量路径且与全量等价（JC.incremental_enabled_and_equivalent）
# ---------------------------------------------------------------------------


def test_incremental_child_matches_full_recompute(tmp_path):
    client, claims = _client(tmp_path)
    queries = _issue_queries(claims)

    def bundle(parent=None):
        return client.local_case_bundle(
            case_id="acceptance-case",
            decision_time="2026-09-01T00:00:00Z",
            facts=[{"fact_key": "acc.contract"}, {"fact_key": "acc.exception"}],
            queries=queries,
            incremental_parent=parent,
        )

    first = client.evaluate_harness_bundle(bundle(), case_id="acceptance-case", issue_queries=queries)
    assert first["run_status"] == "success"
    horn = client.local_horn_subject_state(first["run_identity_ref"])
    parent = IncrementalParentV5(
        parent_run_ref=ContentRefV4.from_dict(horn["parent_run_ref"]),
        parent_state_ref=ContentRefV4.from_dict(horn["parent_state_ref"]),
        parent_subject_digest=DigestV4(horn["parent_subject_digest"]),
        mode="auto",
    )
    child_bundle = client.local_case_bundle(
        case_id="acceptance-case",
        decision_time="2026-09-01T00:00:00Z",
        facts=[
            {"fact_key": "acc.contract"}, {"fact_key": "acc.exception"},
            {"fact_key": "acc.notice"},
        ],
        queries=queries,
        incremental_parent=parent,
    )
    child = client.evaluate_harness_bundle(child_bundle, case_id="acceptance-case", issue_queries=queries)
    assert child["run_status"] == "success"
    # 真实走了增量路径；等价性由 run 内独立全量复算强制（mismatch 即 fail-closed）
    assert child["horn"]["mode"] == "incremental"
    assert child["horn"]["parent_binding"] is not None
    # 超出适用前提（删除事实）→ 具名回退全量，不假称增量
    shrunk_bundle = client.local_case_bundle(
        case_id="acceptance-case",
        decision_time="2026-09-01T00:00:00Z",
        facts=[{"fact_key": "acc.contract"}],
        queries=queries,
        incremental_parent=parent,
    )
    shrunk = client.evaluate_harness_bundle(shrunk_bundle, case_id="acceptance-case", issue_queries=queries)
    assert shrunk["horn"]["mode"] == "full_recompute"
    assert shrunk["horn"]["fallback_reason"] == "fact_deletion"
