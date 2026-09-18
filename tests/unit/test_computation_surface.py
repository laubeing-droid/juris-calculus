"""公开计算入口（03 卡步骤 4/§4a；JCClient 五入口 + jc.price/recompute）。

真实 create_local_client 走本仓 artifact store；规则包为仓库既有合成
验收包（tests/local 同源，明确标注不构成法律依据）；mock 不进本文件。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler_core.client import ClientV4Error, create_local_client

from compiler_core.pricing import (
    HUMAN_RESIDUAL_DEFAULT_RATE_PER_HOUR_MINOR,
)

from tests.local.test_local_runtime import RULE_PACK


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp("jc-computation-state")
    rules = root / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False), encoding="utf-8",
    )
    return create_local_client(root / "state", rules)


# ---------------------------------------------------------------------------
# calibrate.fit
# ---------------------------------------------------------------------------


def _samples(nodes_hours):
    return [
        {
            "entryRef": f"entry-{index}",
            "featureDefinitionVersion": "facts-claims-raw-count/1",
            "durationSeconds": int(hours * 3600),
            "effectiveNodes": nodes,
        }
        for index, (nodes, hours) in enumerate(nodes_hours)
    ]


def test_calibrate_fit_and_snapshot_is_frozen(client):
    snapshot = client.calibrate({
        "matterId": "m-1",
        "featureDefinitionVersion": "facts-claims-raw-count/1",
        "samples": _samples([(10 * n, 1.25 * 10 * n) for n in range(1, 11)]),
    })
    assert snapshot["alpha"] == "1.25"
    assert snapshot["status"] == "fitted"
    assert snapshot["samplesUsed"] == 10
    assert snapshot["guaranteeLevel"] is None
    assert snapshot["delta"] is None
    assert snapshot["estimatorVersion"] == "theilsen-legacy-branches/1"
    assert snapshot["ref"]["owner"] == "jc"
    assert snapshot["ref"]["kind"] == "calibration"


def test_calibrate_unattributed_excluded(client):
    samples = _samples([(10, 12.5), (20, 25.0), (30, 37.5), (40, 50.0)])
    noisy = dict(samples[0], attributed=False)
    snapshot = client.calibrate({
        "matterId": "m-1",
        "featureDefinitionVersion": "facts-claims-raw-count/1",
        "samples": [noisy, *samples[1:]],
    })
    assert snapshot["alpha"] == "1.25"
    assert snapshot["samplesUsed"] == 3
    assert len(snapshot["excludedEntryRefs"]) == 1


def test_calibrate_unknown_estimator_rejected(client):
    with pytest.raises(ClientV4Error) as error:
        client.calibrate({
            "matterId": "m-1",
            "featureDefinitionVersion": "facts-claims-raw-count/1",
            "estimatorVersion": "theilsen-v2",
            "samples": _samples([(10, 12.5)]),
        })
    assert error.value.code == "estimator_version_unknown"


# ---------------------------------------------------------------------------
# pricing.estimate + recompute（Z-v1-default 冻结样例）
# ---------------------------------------------------------------------------


def _feature(nodes=10):
    return {
        "ref": None,
        "featureDefinitionVersion": "facts-claims-raw-count/1",
        "factRefs": [],
        "claimRefs": [],
        "effectiveNodes": nodes,
        "legacyDth": None,
    }


def _alpha(alpha="1.25", status="fitted"):
    return {"ref": None, "alpha": alpha, "status": status}


def test_price_frozen_example_and_recompute(client):
    quote = client.price({
        "matterId": "m-2",
        "feature": _feature(10),
        "alpha": _alpha("1.25", "fitted"),
        "batchPosition": 1,
        "rateMinorPerHour": 3300,
        "overheadHours": "8",
        "locationFactor": "1.3",
        "stageFactor": "1.25",
    })
    assert quote["variableHoursUnrounded"] == "20.3125"
    assert quote["amountMinor"] == 93431
    assert quote["displayHours"] == "28.3"
    assert quote["currency"] == "CNY"
    recomputed = client.recompute_price(quote["calculationReceiptRef"])
    assert recomputed["equal"] is True
    assert recomputed["recomputed"]["amountMinor"] == 93431


def test_recompute_detects_tampered_receipt(client):
    quote = client.price({
        "matterId": "m-2",
        "feature": _feature(10),
        "alpha": _alpha("1.25", "fitted"),
        "batchPosition": 1,
        "rateMinorPerHour": 3300,
        "overheadHours": "8",
    })
    tampered = dict(quote["input"])
    result = client.recompute_price({
        "schema_version": "jc-calculation-receipt/1",
        "kind": "pricing",
        "input": dict(tampered, batchPosition=3),
        "computed": dict(quote["input"], amountMinor=1),
    })
    assert result["equal"] is False


def test_price_rejects_unknown_model(client):
    with pytest.raises(ClientV4Error) as error:
        client.price({
            "matterId": "m-2",
            "feature": _feature(10),
            "alpha": _alpha("1.25", "fitted"),
            "batchPosition": 1,
            "rateMinorPerHour": 3300,
            "overheadHours": "8",
            "modelVersion": "Z-v2",
        })
    assert error.value.code == "model_version_unknown"


# ---------------------------------------------------------------------------
# jc.price / jc.recompute_price（issue-human-residual/1）
# ---------------------------------------------------------------------------


def _item(item_id, hours, *, ai=False, verify=False, rework=False, shared=False, issues=None):
    return {
        "workItemId": item_id,
        "issueIds": issues if issues is not None else ["issue-1"],
        "actionCategory": "communication",
        "requiredHumanHours": hours,
        "aiCompleted": ai,
        "humanVerificationRequired": verify,
        "reworkRequired": rework,
        "shared": shared,
        "estimateBasis": "engineering-initial/1",
    }


def test_human_residual_zero_history_quotes(client):
    quote = client.price_human_residual({
        "matterId": "m-3",
        "issueIds": ["issue-1"],
        "workItems": [_item("w-1", "2.5")],
    })
    assert quote["model_version"] == "issue-human-residual/1"
    assert quote["residual_hours_unrounded"] == "2.5"
    # 工程初值：费率 30000 分/h → 2.5h = 75000 分
    assert quote["quote_amount_minor"] == 75000
    assert quote["direct_cost_minor"] == 0
    assert quote["rate_minor_per_hour"] == HUMAN_RESIDUAL_DEFAULT_RATE_PER_HOUR_MINOR
    recomputed = client.recompute_price(quote["calculationReceiptRef"])
    assert recomputed["equal"] is True


def test_human_residual_ai_completed_drops_hours(client):
    done = client.price_human_residual({
        "matterId": "m-3",
        "workItems": [_item("w-1", "2.5", ai=True)],
    })
    assert done["residual_hours_unrounded"] == "0"
    assert done["quote_amount_minor"] == 0
    # AI 完成但需专业核验：核验是独立工作项，不被删除
    with_verification = client.price_human_residual({
        "matterId": "m-3",
        "workItems": [
            _item("w-1", "2.5", ai=True, verify=True),
            _item("w-2", "0.25"),
        ],
    })
    assert with_verification["residual_hours_unrounded"] == "0.25"
    assert any("verification" in row for row in with_verification["assumptions"])


def test_human_residual_shared_counts_once_and_rate_only_changes_quote(client):
    base = client.price_human_residual({
        "matterId": "m-3",
        "workItems": [_item("w-1", "4", shared=True, issues=["issue-1", "issue-2", "issue-3"])],
    })
    assert base["residual_hours_unrounded"] == "4"
    assert any("counted once" in row for row in base["assumptions"])
    rerated = client.price_human_residual({
        "matterId": "m-3",
        "workItems": [_item("w-1", "4", shared=True, issues=["issue-1", "issue-2", "issue-3"])],
        "params": {"rateMinorPerHour": 60000, "internalCostPerHourMinor": 10000},
    })
    assert rerated["residual_hours_unrounded"] == "4"
    assert rerated["quote_amount_minor"] == 240000
    assert rerated["estimated_internal_cost_minor"] == base["estimated_internal_cost_minor"]


def test_human_residual_rework_and_duplicate_rules(client):
    reworked = client.price_human_residual({
        "matterId": "m-3",
        "workItems": [_item("w-1", "1.5", ai=True, rework=True)],
    })
    assert reworked["residual_hours_unrounded"] == "1.5"
    with pytest.raises(ClientV4Error):
        client.price_human_residual({
            "matterId": "m-3",
            "workItems": [_item("w-1", "1"), _item("w-1", "2")],
        })
    with pytest.raises(ClientV4Error) as error:
        client.price_human_residual({
            "matterId": "m-3",
            "workItems": [_item("w-1", "1")],
            "modelVersion": "Z-v1-default",
        })
    assert error.value.code == "model_version_explicit_required"


# ---------------------------------------------------------------------------
# deadlines.calculate（真实事件 artifact + 注册表）
# ---------------------------------------------------------------------------


def _register_event(client, *, event_id, revision, matter_id, served_at):
    event = {
        "id": event_id,
        "revision": revision,
        "matterId": matter_id,
        "kind": "procedure-event",
        "procedureType": "civil_first_instance",
        "procedureStage": "judgment_service",
        "servedAt": {"value": served_at, "precision": "date", "timezone": "Asia/Shanghai", "sourceRefs": []},
        "occurredAt": {"value": None, "precision": "unknown", "timezone": None, "sourceRefs": []},
        "awareAt": {"value": None, "precision": "unknown", "timezone": None, "sourceRefs": []},
        "filedAt": {"value": None, "precision": "unknown", "timezone": None, "sourceRefs": []},
        "hearingAt": {"value": None, "precision": "unknown", "timezone": None, "sourceRefs": []},
    }
    reference = client._register_json("procedure-event", event, scope="case")
    return client._wire_ref(reference, matter_id=matter_id)


def _calendar_binding(released=True, start="2026-01-01", end="2026-12-31"):
    return {
        "ref": None,
        "coverageStart": start,
        "coverageEnd": end,
        "released": released,
        "sourceRefs": [],
        "checkedAt": "2026-09-19T00:00:00Z",
    }


def test_calculate_deadlines_appeal(client):
    event_ref = _register_event(client, event_id="e-1", revision=3, matter_id="m-4",
                                served_at="2026-03-02")
    result = client.calculate_deadlines({
        "matterId": "m-4",
        "eventRef": event_ref,
        "eventRevision": 3,
        "rules": [{"ruleId": "civil.appeal.judgment", "ruleVersion": "1"}],
        "calendar": _calendar_binding(),
    })
    assert len(result["deadlines"]) == 1
    row = result["deadlines"][0]
    assert row["dueDate"] == "2026-03-17"
    assert row["eventId"] == "e-1"
    assert result["receipt"]["scope"] == {"kind": "matter", "matterId": "m-4", "runId": None}
    assert result["receipt"]["outputRefs"] == [row["ref"]]


def test_calculate_deadlines_revision_conflict_and_unknown_rule(client):
    event_ref = _register_event(client, event_id="e-2", revision=5, matter_id="m-4",
                                served_at="2026-03-02")
    with pytest.raises(ClientV4Error) as error:
        client.calculate_deadlines({
            "matterId": "m-4",
            "eventRef": event_ref,
            "eventRevision": 4,
            "rules": [{"ruleId": "civil.appeal.judgment", "ruleVersion": "1"}],
            "calendar": _calendar_binding(),
        })
    assert error.value.code == "revision_conflict"
    with pytest.raises(ClientV4Error) as error:
        client.calculate_deadlines({
            "matterId": "m-4",
            "eventRef": event_ref,
            "eventRevision": 5,
            "rules": [{"ruleId": "civil.appeal.judgment", "ruleVersion": "9"}],
            "calendar": _calendar_binding(),
        })
    assert error.value.code == "ref_not_found"


def test_calculate_deadlines_unreleased_calendar_is_fail_closed(client):
    event_ref = _register_event(client, event_id="e-3", revision=1, matter_id="m-4",
                                served_at="2026-03-02")
    with pytest.raises(ClientV4Error) as error:
        client.calculate_deadlines({
            "matterId": "m-4",
            "eventRef": event_ref,
            "eventRevision": 1,
            "rules": [{"ruleId": "civil.appeal.judgment", "ruleVersion": "1"}],
            "calendar": _calendar_binding(released=False),
        })
    assert error.value.code == "calendar_coverage_missing"


def test_calculate_deadlines_2027_boundary_reports_gap(client):
    # 2026-12-28 送达 +15 日 → 2027-01-12 在覆盖外：dueDate=null + 缺口步骤
    event_ref = _register_event(client, event_id="e-4", revision=1, matter_id="m-4",
                                served_at="2026-12-28")
    result = client.calculate_deadlines({
        "matterId": "m-4",
        "eventRef": event_ref,
        "eventRevision": 1,
        "rules": [{"ruleId": "civil.appeal.judgment", "ruleVersion": "1"}],
        "calendar": _calendar_binding(),
    })
    row = result["deadlines"][0]
    assert row["dueDate"] is None
    assert "calendar_coverage_missing:true" in row["calculationSteps"]


# ---------------------------------------------------------------------------
# deviation_rank / terminal_state_stats（case.* 读面经注入 reader 的独立单测；
# 集成态=未接读面时具名 not_compiled / dataset_version_not_found，
# 见 tests/integration/test_knowledge_runtime.py）
# ---------------------------------------------------------------------------


def test_deviation_rank_ranks_structural_and_numeric_diffs(client):
    structures = {
        "doc-low": {"elements": ["contract", "delivery"], "numeric": {"amount": "100"}},
        "doc-high": {"elements": ["contract", "delivery", "acceptance", "warranty"],
                     "numeric": {"amount": "100"}},
    }
    reader = lambda locator: structures.get(locator["canonicalDocId"])  # noqa: E731
    result = client.deviation_rank({
        "baselineRuleVersion": "1",
        "budget": 10,
        "queryStructure": {"elements": ["contract", "delivery"], "numeric": {"amount": "100"}},
        "candidates": [
            {"datasetVersion": "v1", "canonicalDocId": "doc-low", "month": "2026-01",
             "locator": {"sourceRow": 1, "recordHash": "h1"}},
            {"datasetVersion": "v1", "canonicalDocId": "doc-high", "month": "2026-01",
             "locator": {"sourceRow": 2, "recordHash": "h2"}},
        ],
        "structureReader": reader,
    })
    assert result["status"] == "ok"
    assert result["items"][0]["locator"]["canonicalDocId"] == "doc-low"  # 偏离更小者在前
    top = result["items"][0]["deviations"]
    assert all(row["measure"] is None for row in top)  # 结构差异不标精确偏离度
    bottom = result["items"][1]["deviations"]
    numeric_row = [row for row in bottom if row["position"] == "amount"]
    assert numeric_row == []  # 数值相同则无数值偏离行


def test_deviation_rank_budget_exceeded(client):
    result = client.deviation_rank({
        "baselineRuleVersion": "1",
        "budget": 1,
        "queryStructure": {"elements": ["contract"]},
        "candidates": [
            {"datasetVersion": "v1", "canonicalDocId": f"doc-{i}", "month": "2026-01",
             "locator": {"sourceRow": i, "recordHash": "h"}}
            for i in range(3)
        ],
        "structureReader": lambda locator: {"elements": [], "numeric": {}},
    })
    assert result["status"] == "budget_exceeded"


def test_terminal_state_stats_filters_via_public_reader(client):
    def reader(dataset_version, filters, rule_version):
        if dataset_version != "pub-1":
            return None
        outcome = filters.get("cause")
        rows = [
            {"outcome": "dismissed", "n": 30, "rate": "0.3"},
            {"outcome": "supported", "n": 70, "rate": "0.7"},
        ]
        return {
            "distribution": [r for r in rows if not outcome or r["outcome"] == outcome],
            "counts": {"total": 100},
            "range": "2015-01..2026-08",
        }

    result = client.terminal_state_stats({
        "datasetVersion": "pub-1",
        "filters": {"cause": "supported"},
        "ruleVersion": "1",
        "statsReader": reader,
    })
    assert result["distribution"] == [{"outcome": "supported", "n": 70, "rate": "0.7"}]
    assert result["range"] == "2015-01..2026-08"
    with pytest.raises(ClientV4Error) as error:
        client.terminal_state_stats({
            "datasetVersion": "unknown-version",
            "statsReader": reader,
        })
    assert error.value.code == "dataset_version_not_found"
