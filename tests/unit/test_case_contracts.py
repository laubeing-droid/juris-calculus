from dataclasses import replace
import json
from pathlib import Path

import pytest

from compiler_core.contracts import (
    ENGINE_LIMITS,
    SCHEMA_VERSION,
    BranchResult,
    CanonicalResult,
    CertificateKind,
    CaseRequest,
    ContractValidationError,
    ExecutionStatus,
    MissingFactReview,
    RenderedArtifact,
    ResultStatus,
    RulePackDescriptor,
    SemanticResult,
    emit_audit_event,
    schema_document,
)
from compiler_core.version import __version__


DIGEST = "a" * 64
ROOT = Path(__file__).resolve().parents[2]


def _request_payload():
    """构造包含一个正式事实和一个候选事实的最小有效请求。"""

    return {
        "schema_version": SCHEMA_VERSION,
        "jurisdiction": "CN",
        "governing_law": "PRC Civil Code",
        "as_of_date": "2026-07-11",
        "facts": [
            {
                "id": "fact::b",
                "status": "candidate_fact",
            },
            {
                "id": "fact::a",
                "status": "verified_fact",
                "source_ids": ["source::1"],
                "human_reviewed": True,
            },
        ],
        "rule_pack_id": "cn-official",
        "rule_pack_version": __version__,
        "rule_pack_digest": DIGEST,
        "external_source_refs": ["source::z", "source::a"],
    }


def _semantic(status=ResultStatus.REVIEW_ONLY_RESULT, **overrides):
    """按指定状态构造合法SemanticResult，供状态矩阵测试定点修改。"""

    values = {
        "schema_version": SCHEMA_VERSION,
        "run_id": "run::1",
        "result_digest": DIGEST,
        "execution_status": ExecutionStatus.COMPLETED,
        "result_status": status,
        "formal_kernel_used": False,
        "review_required": True,
        "checker_accepted": False,
        "certificate_kind": CertificateKind.NONE,
        "engine_version": __version__,
        "pack_id": "cn-official",
        "pack_version": __version__,
        "pack_digest": DIGEST,
        "risk_labels": ("review",),
    }
    if status == ResultStatus.ACCEPTED_FORMAL_RESULT:
        values.update({
            "formal_kernel_used": True,
            "review_required": False,
            "checker_accepted": True,
            "certificate_kind": CertificateKind.FORMAL,
            "claims": ("claim::1",),
            "used_fact_ids": ("fact::1",),
            "used_rule_ids": ("rule::1",),
            "source_ids": ("source::1",),
        })
    elif status == ResultStatus.HYPOTHETICAL_RESULT:
        values["taint"] = ("assumption",)
    elif status == ResultStatus.MISSING_REQUIRED_FACT:
        values["missing_fact_ids"] = ("fact::missing",)
        values["missing_fact_review"] = (MissingFactReview("fact::missing"),)
    elif status == ResultStatus.CONFLICT_CERTIFICATE:
        values["certificate_kind"] = CertificateKind.CONFLICT
    elif status == ResultStatus.ENGINE_ERROR:
        values.update({
            "execution_status": ExecutionStatus.ENGINE_ERROR,
            "formal_kernel_used": False,
            "checker_accepted": False,
            "certificate_kind": CertificateKind.NONE,
            "claims": (),
        })
    values.update(overrides)
    return SemanticResult(**values)


def test_case_request_is_strict_sorted_and_round_trips():
    request = CaseRequest.from_dict(_request_payload())

    assert [fact.id for fact in request.facts] == ["fact::a", "fact::b"]
    assert request.external_source_refs == ("source::a", "source::z")
    assert CaseRequest.from_dict(request.to_dict()).to_dict() == request.to_dict()


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda payload: payload.update(extra=True), "UNKNOWN_FIELD"),
        (lambda payload: payload.pop("jurisdiction"), "MISSING_REQUIRED_FIELD"),
        (lambda payload: payload.update(as_of_date="not-a-date"), "INVALID_AS_OF_DATE"),
        (lambda payload: payload["facts"][0].update(status="invented"), "UNKNOWN_FACT_ENUM"),
        (lambda payload: payload["facts"].append(dict(payload["facts"][0])), "DUPLICATE_FACT_KEY"),
    ],
)
def test_case_request_rejects_invalid_public_input(mutation, code):
    payload = _request_payload()
    mutation(payload)

    with pytest.raises(ContractValidationError) as exc:
        CaseRequest.from_dict(payload)

    assert exc.value.code == code


def test_case_request_capacity_limits_are_single_source():
    payload = _request_payload()
    payload["facts"] = [
        {"id": f"fact::{index}", "status": "candidate_fact"}
        for index in range(ENGINE_LIMITS["max_facts"] + 1)
    ]

    with pytest.raises(ContractValidationError, match=str(ENGINE_LIMITS["max_facts"] + 1)):
        CaseRequest.from_dict(payload)


def test_disputed_branch_limit_is_review_signal_not_syntax_error():
    payload = _request_payload()
    payload["facts"] = [
        {
            "id": f"fact::{index}",
            "status": "disputed",
            "alternatives": [{"value": False}, {"value": True}],
        }
        for index in range(6)
    ]

    request = CaseRequest.from_dict(payload)

    assert request.estimated_branch_count == 64
    assert request.branch_limit_exceeded


@pytest.mark.parametrize("status", list(ResultStatus))
def test_each_public_result_status_has_a_valid_combination(status):
    assert _semantic(status).result_status == status


def test_formal_result_requires_all_acceptance_evidence():
    valid = _semantic(ResultStatus.ACCEPTED_FORMAL_RESULT)

    for mutation in (
        {"checker_accepted": False},
        {"formal_kernel_used": False},
        {"review_required": True},
        {"certificate_kind": CertificateKind.NONE},
        {"claims": ()},
        {"used_rule_ids": ()},
        {"source_ids": ()},
    ):
        with pytest.raises(ContractValidationError):
            replace(valid, **mutation)


def test_nonformal_results_reject_formal_certificate():
    with pytest.raises(ContractValidationError):
        _semantic(ResultStatus.REVIEW_ONLY_RESULT, certificate_kind=CertificateKind.FORMAL)


def test_semantic_and_canonical_results_are_deeply_copying_on_export():
    semantic = _semantic(
        ResultStatus.HYPOTHETICAL_RESULT,
        branches=(BranchResult("branch::b", ResultStatus.HYPOTHETICAL_RESULT, ("claim::2",)),),
    )
    canonical = CanonicalResult(semantic, artifact_refs=("run://1/result.json",))
    first = canonical.to_dict()
    first["semantic"]["branches"][0]["claims"].append("tampered")
    first["artifact_refs"].append("tampered")

    assert canonical.to_dict()["semantic"]["branches"][0]["claims"] == ["claim::2"]
    assert canonical.artifact_refs == ("run://1/result.json",)


def test_rule_pack_and_rendered_artifact_are_declarative_and_immutable():
    pack = RulePackDescriptor("cn-official", __version__, DIGEST, ("r2", "r1"))
    artifact = RenderedArtifact(
        result_digest=DIGEST,
        renderer_id="neutral",
        renderer_version="1",
        profile_id="neutral",
        profile_version="1",
        profile_hash=DIGEST,
        audience="lawyer",
        locale="zh-CN",
        format="markdown",
        content="review only",
        content_sha256=DIGEST,
    )

    assert pack.verified_rule_ids == ("r1", "r2")
    assert set(artifact.to_dict()) == {
        "result_digest", "renderer_id", "renderer_version", "profile_id", "profile_version",
        "profile_hash", "audience", "locale", "format", "content", "content_sha256", "warnings",
    }


def test_audit_callback_receives_a_copy_without_event_bus_abstraction():
    received = []
    event = {"event_type": "fact_admission"}

    emit_audit_event(received.append, event)
    event["event_type"] = "tampered"

    assert received == [{"event_type": "fact_admission"}]


def test_committed_schema_is_generated_from_contracts():
    committed = json.loads((ROOT / "schemas" / "jc-v3.schema.json").read_text(encoding="utf-8"))

    assert committed == schema_document()
    assert committed["$defs"]["CaseRequest"]["additionalProperties"] is False
    assert committed["$defs"]["CanonicalResult"]["additionalProperties"] is False
    assert committed["$defs"]["CanonicalResult"]["properties"]["semantic"] == {"$ref": "#/$defs/SemanticResult"}
    assert committed["$defs"]["LegalFact"]["properties"]["reasoning_tier"]["enum"] == ["P0", "P1", "P2"]
    assert {
        "MissingFactReview",
        "RuleGovernanceReport",
        "TrainingExportManifest",
        "StrategyAdvisory",
        "SimilarCasesAdvisory",
        "CaseIndex",
    } <= set(committed["$defs"])


def test_unknown_result_enums_fail_closed():
    with pytest.raises(ContractValidationError) as exc:
        _semantic(execution_status="made-up")

    assert exc.value.code == "UNKNOWN_RESULT_ENUM"
