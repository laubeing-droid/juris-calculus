"""正式语义审计事件的顺序、因果、隐私和失败门禁。"""

from __future__ import annotations

import json

import pytest

from compiler_core.application import evaluate_case
from compiler_core.audit import AuditRecorder, AuditValidationError
from compiler_core.canonical_serialization import content_id
from compiler_core.contracts import ResultStatus, schema_document
from compiler_core.types import FactTrustStatus, LegalRule
from tests.unit.test_application_service import _fact, _manifest, _pack, _request, _rule


def _recorder_for(request) -> AuditRecorder:
    """以application同一规范请求计算run ID。"""

    return AuditRecorder(content_id("run", request.to_dict()))


def test_accepted_result_has_complete_deterministic_semantic_event_chain() -> None:
    """正式结果可从事实准入追到规则、claim、checker和final result。"""

    request = _request(_fact())
    first = _recorder_for(request)
    second = _recorder_for(request)
    result = evaluate_case(request, _pack(), (_rule(),), source_manifest=_manifest(), audit_sink=first)
    replayed = evaluate_case(request, _pack(), (_rule(),), source_manifest=_manifest(), audit_sink=second)

    assert result.to_dict() == replayed.to_dict()
    assert [event.to_dict() for event in first.events] == [event.to_dict() for event in second.events]
    assert first.events_digest == second.events_digest
    assert [event.seq for event in first.events] == list(range(1, len(first.events) + 1))
    assert [event.event_type for event in first.events] == [
        "RUN_STARTED",
        "INPUT_VALIDATED",
        "RELEVANCE_SET_BUILT",
        "RULE_MATCHED",
        "FACT_ADMISSION_DECIDED",
        "RULE_FIRED",
        "CLAIM_DERIVED",
        "CHECKER_STARTED",
        "CHECKER_VERDICT",
        "RESULT_FINALIZED",
    ]
    seen: set[str] = set()
    for event in first.events:
        assert set(event.parent_event_ids) <= seen
        seen.add(event.event_id)
    fired = next(event for event in first.events if event.event_type == "RULE_FIRED")
    assert fired.rule_id == "R1"
    assert fired.claim_id == "claim::result"
    assert fired.premise_ids == ("fact::trigger",)
    assert result.source_ids[0] in next(
        event for event in first.events if event.event_type == "RULE_MATCHED"
    ).source_ids


def test_irrelevant_rules_are_not_written_to_case_audit() -> None:
    """审计量按本案相关规则增长，不记录同pack无关规则。"""

    request = _request(_fact())
    recorder = _recorder_for(request)
    irrelevant = LegalRule(
        id="R-IRRELEVANT",
        premise_atoms=["fact::other"],
        head_claim="claim::other",
        source_anchor="source::law",
    )
    evaluate_case(
        request,
        _pack("R1", "R-IRRELEVANT"),
        (_rule(), irrelevant),
        source_manifest=_manifest(),
        audit_sink=recorder,
    )

    encoded = json.dumps([event.to_dict() for event in recorder.events], ensure_ascii=False)
    relevance = next(event for event in recorder.events if event.event_type == "RELEVANCE_SET_BUILT")
    assert relevance.details["candidate_rule_count"] == 1
    assert "R-IRRELEVANT" not in encoded


def test_unknown_fact_records_missing_event_and_never_starts_checker() -> None:
    """UNKNOWN必须形成缺失事实事件，并在checker前停止。"""

    request = _request(_fact(FactTrustStatus.UNKNOWN))
    recorder = _recorder_for(request)
    result = evaluate_case(request, _pack(), (_rule(),), source_manifest=_manifest(), audit_sink=recorder)

    assert result.result_status is ResultStatus.MISSING_REQUIRED_FACT
    missing = next(event for event in recorder.events if event.event_type == "MISSING_FACT_RECORDED")
    assert missing.details["impacted_rule_ids"] == ("R1",)
    assert missing.details["impacted_claim_ids"] == ("claim::result",)
    assert all(event.event_type != "CHECKER_STARTED" for event in recorder.events)
    assert recorder.events[-1].event_type == "RESULT_FINALIZED"


def test_disputed_branches_have_stable_creation_events() -> None:
    """分支按稳定组合串行创建，并记录假设摘要而非原始卷宗。"""

    request = _request(_fact(
        FactTrustStatus.DISPUTED,
        alternatives=({"value": False}, {"value": True}),
    ))
    recorder = _recorder_for(request)
    evaluate_case(request, _pack(), (_rule(),), source_manifest=_manifest(), audit_sink=recorder)

    branches = [event for event in recorder.events if event.event_type == "BRANCH_CREATED"]
    assert [event.details["branch_index"] for event in branches] == [0, 1]
    assert all(len(event.details["assumptions_digest"]) == 64 for event in branches)


def test_permission_prohibition_and_taint_have_explicit_events() -> None:
    """三类review边界不得只藏在最终risk label中。"""

    rules = (
        LegalRule(
            id="PERMISSION",
            premise_atoms=["fact::trigger"],
            head_claim="claim::permission",
            norm_modality="PERMISSION",
            source_anchor="source::law",
        ),
        LegalRule(
            id="PROHIBITION",
            premise_atoms=["fact::trigger"],
            head_claim="claim::blocked",
            norm_modality="PROHIBITION",
            source_anchor="source::law",
        ),
        LegalRule(
            id="TAINTED",
            premise_atoms=["fact::trigger"],
            head_claim="claim::tainted",
            concepts=["unregistered::concept"],
            mechanical_exception=False,
            source_anchor="source::law",
        ),
    )
    request = _request(_fact())
    recorder = _recorder_for(request)
    evaluate_case(
        request,
        _pack("PERMISSION", "PROHIBITION", "TAINTED"),
        rules,
        source_manifest=_manifest(),
        audit_sink=recorder,
    )

    event_types = {event.event_type for event in recorder.events}
    assert {"PERMISSION_EVALUATED", "RULE_BLOCKED", "TAINT_PROPAGATED"} <= event_types


def test_audit_rejects_unknown_details_absolute_paths_and_missing_parents() -> None:
    """details不是任意字典，路径和伪父事件均fail closed。"""

    recorder = AuditRecorder("run::fixture")
    recorder.record("RUN_STARTED", details={"engine_version": "3.0"})

    with pytest.raises(AuditValidationError, match="unknown details"):
        recorder.record("RUN_STARTED", details={"engine_version": "3.0", "extra": "x"})
    with pytest.raises(AuditValidationError, match="absolute path"):
        recorder.record("RUN_FAILED", details={"error_type": "D:/private/case.txt"})
    with pytest.raises(AuditValidationError, match="unknown parent"):
        recorder.record("RUN_FAILED", parent_event_ids=("event::missing",), details={"error_type": "RuntimeError"})


def test_recorder_failure_forces_engine_error_without_accepted_claims() -> None:
    """观察者写入失败时不得在无完整审计的情况下返回正式成功。"""

    def broken_sink(_event):
        raise OSError("audit storage unavailable")

    result = evaluate_case(
        _request(_fact()),
        _pack(),
        (_rule(),),
        source_manifest=_manifest(),
        audit_sink=broken_sink,
    )

    assert result.result_status is ResultStatus.ENGINE_ERROR
    assert result.claims == ()
    assert result.formal_kernel_used is False


def test_schema_has_one_strict_details_definition_per_event_type() -> None:
    """公共schema包含事件/图，并为每类details拒绝额外字段。"""

    definitions = schema_document()["$defs"]
    event_types = definitions["AuditEvent"]["properties"]["event_type"]["enum"]

    assert "GraphDocument" in definitions
    for event_type in event_types:
        detail = definitions[f"{event_type}Details"]
        assert detail["additionalProperties"] is False
        assert set(detail["required"]) == set(detail["properties"])
