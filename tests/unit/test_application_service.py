"""Phase 2统一案件求值服务的准入、状态和隔离门禁。"""

from __future__ import annotations

from copy import deepcopy

import compiler_core.application as application
from compiler_core.contracts import (
    CertificateKind,
    CaseRequest,
    ExecutionStatus,
    ResultStatus,
    RulePackDescriptor,
    SCHEMA_VERSION,
)
from compiler_core.source_manifest import SourceEntry, SourceManifest
from compiler_core.types import DataQuality, FactTrustStatus, LegalFact, LegalRule
from compiler_core.version import __version__


PACK_DIGEST = "a" * 64
SOURCE_HASH = "b" * 64


def _fact(
    status: FactTrustStatus = FactTrustStatus.VERIFIED_FACT,
    *,
    fact_id: str = "fact::trigger",
    alternatives: tuple[dict, ...] = (),
) -> LegalFact:
    """构造明确来源且经过人工复核的最小事实；状态由用例显式覆盖。"""

    return LegalFact(
        id=fact_id,
        value=True,
        status=status,
        source_ids=("evidence::1",),
        human_reviewed=True,
        alternatives=alternatives,
    )


def _request(*facts: LegalFact, digest: str = PACK_DIGEST) -> CaseRequest:
    """构造无隐藏法域、日期或规则包默认值的请求。"""

    return CaseRequest(
        schema_version=SCHEMA_VERSION,
        jurisdiction="CN",
        governing_law="PRC",
        as_of_date="2026-07-11",
        facts=tuple(facts),
        rule_pack_id="official-cn",
        rule_pack_version=__version__,
        rule_pack_digest=digest,
    )


def _rule(*, source_anchor: str = "source::law", data_quality: str = "CLEAN") -> LegalRule:
    """构造只在输入事实存在时触发的单条Horn规则。"""

    return LegalRule(
        id="R1",
        premise_atoms=["fact::trigger"],
        head_claim="claim::result",
        source_anchor=source_anchor,
        data_quality=data_quality,
    )


def _pack(*rule_ids: str, digest: str = PACK_DIGEST) -> RulePackDescriptor:
    """构造与请求绑定的确定性规则包描述。"""

    return RulePackDescriptor("official-cn", __version__, digest, tuple(rule_ids or ("R1",)))


def _manifest(*, verified: bool = True, content_hash: str = SOURCE_HASH) -> SourceManifest:
    """构造可精确匹配的测试来源清单。"""

    entry = SourceEntry(
        source_id="source::law",
        source_type="statute",
        title="Test Law",
        jurisdiction="CN",
        verified=verified,
        verification_date="2026-07-11",
        content_hash=content_hash,
    )
    return SourceManifest(entries={entry.source_id: entry}, loaded=True)


def _evaluate(request: CaseRequest, rule: LegalRule | None = None, **kwargs):
    """执行标准单规则场景，保留显式覆盖入口。"""

    selected = rule or _rule()
    return application.evaluate_case(
        request,
        kwargs.pop("pack", _pack()),
        kwargs.pop("rules", (selected,)),
        source_manifest=kwargs.pop("manifest", _manifest()),
        **kwargs,
    )


def test_verified_fact_rule_source_and_checker_produce_formal_result() -> None:
    """只有全部准入和独立checker成立时才产生正式certificate。"""

    events: list[dict] = []
    result = _evaluate(_request(_fact()), audit_sink=events.append)

    assert result.result_status is ResultStatus.ACCEPTED_FORMAL_RESULT
    assert result.execution_status is ExecutionStatus.COMPLETED
    assert result.certificate_kind is CertificateKind.FORMAL
    assert result.formal_kernel_used is True
    assert result.checker_accepted is True
    assert result.claims == ("claim::result",)
    assert result.used_fact_ids == ("fact::trigger",)
    assert result.used_rule_ids == ("R1",)
    assert result.source_ids == (f"source::law@{SOURCE_HASH}",)
    assert [event["event_type"] for event in events] == [
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


def test_unverified_or_candidate_rule_never_enters_formal_kernel() -> None:
    """来源缺失和候选规则均保留审计，但评估器不得应用。"""

    for rule, manifest in (
        (_rule(), _manifest(verified=False)),
        (_rule(source_anchor=""), _manifest()),
        (_rule(data_quality=DataQuality.CANDIDATE_ONLY.value), _manifest()),
    ):
        result = _evaluate(_request(_fact()), rule, manifest=manifest)
        assert result.result_status is ResultStatus.REVIEW_ONLY_RESULT
        assert result.formal_kernel_used is False
        assert result.claims == ()
        assert result.used_rule_ids == ()
        assert "RELEVANT_RULE_NOT_ADMITTED" in result.risk_labels


def test_non_admitted_relevant_fact_cannot_trigger_claim() -> None:
    """候选事实即使键名满足前提也只能进入review-only。"""

    result = _evaluate(_request(_fact(FactTrustStatus.CANDIDATE_FACT)))

    assert result.result_status is ResultStatus.REVIEW_ONLY_RESULT
    assert result.formal_kernel_used is False
    assert result.claims == ()
    assert "RELEVANT_FACT_NOT_ADMITTED" in result.risk_labels


def test_unknown_and_assumed_have_distinct_non_formal_results() -> None:
    """UNKNOWN生成缺失事实，USER_ASSUMED生成带污染的假设结果。"""

    unknown = _evaluate(_request(_fact(FactTrustStatus.UNKNOWN)))
    assumed = _evaluate(_request(_fact(FactTrustStatus.USER_ASSUMED)))

    assert unknown.result_status is ResultStatus.MISSING_REQUIRED_FACT
    assert unknown.execution_status is ExecutionStatus.ADMISSION_BLOCKED
    assert unknown.missing_fact_ids == ("fact::trigger",)
    assert unknown.missing_fact_review[0].to_dict() == {
        "fact_id": "fact::trigger",
        "impacted_rule_ids": ["R1"],
        "impacted_claim_ids": ["claim::result"],
        "reason": "UNKNOWN",
        "allowed_answer_types": ["DISPUTED_ALTERNATIVES", "REMAIN_UNKNOWN", "VERIFIED_FACT"],
        "source_requirement": "source_ids and human_reviewed are required for VERIFIED_FACT",
    }
    assert unknown.certificate_kind is CertificateKind.NONE
    assert assumed.result_status is ResultStatus.HYPOTHETICAL_RESULT
    assert assumed.claims == ("claim::result",)
    assert assumed.taint == ("assumption",)
    assert assumed.checker_accepted is False
    assert assumed.certificate_kind is CertificateKind.NONE


def test_disputed_fact_branches_deterministically_without_formal_certificate() -> None:
    """争议事实分支可运行内核，但总结果必须保持review-only。"""

    disputed = _fact(
        FactTrustStatus.DISPUTED,
        alternatives=({"value": False}, {"value": True}),
    )
    first = _evaluate(_request(disputed))
    second = _evaluate(_request(deepcopy(disputed)))

    assert first.to_dict() == second.to_dict()
    assert first.result_status is ResultStatus.REVIEW_ONLY_RESULT
    assert first.certificate_kind is CertificateKind.NONE
    assert first.checker_accepted is False
    assert len(first.branches) == 2
    assert all(branch.result_status is ResultStatus.HYPOTHETICAL_RESULT for branch in first.branches)
    assert all("disputed" in branch.taint for branch in first.branches)


def test_branch_limit_is_fail_closed_before_rule_execution() -> None:
    """超过分支上限时不抽样、不截断为貌似完整的结果。"""

    disputed = tuple(
        _fact(
            FactTrustStatus.DISPUTED,
            fact_id=f"fact::{index}",
            alternatives=({"value": False}, {"value": True}),
        )
        for index in range(6)
    )
    result = _evaluate(_request(*disputed))

    assert result.result_status is ResultStatus.REVIEW_ONLY_RESULT
    assert result.execution_status is ExecutionStatus.ADMISSION_BLOCKED
    assert result.formal_kernel_used is False
    assert result.branches == ()
    assert result.risk_labels == ("BRANCH_LIMIT_EXCEEDED",)


def test_pack_mismatch_and_checker_failure_are_engine_errors_without_claims(monkeypatch) -> None:
    """规则包绑定错误或checker异常都不得包装成业务成功。"""

    mismatch = _evaluate(_request(_fact()), pack=_pack(digest="c" * 64))
    assert mismatch.result_status is ResultStatus.ENGINE_ERROR
    assert mismatch.execution_status is ExecutionStatus.ENGINE_ERROR
    assert mismatch.claims == ()

    def broken_checker(*_args, **_kwargs):
        raise RuntimeError("checker unavailable")

    monkeypatch.setattr(application, "check_grounded", broken_checker)
    checker_error = _evaluate(_request(_fact()))
    assert checker_error.result_status is ResultStatus.ENGINE_ERROR
    assert checker_error.formal_kernel_used is False
    assert checker_error.checker_accepted is False
    assert checker_error.claims == ()


def test_runs_are_deterministic_and_do_not_leak_state_after_error() -> None:
    """失败运行不得污染后续案件，语义事件和结果必须可重放。"""

    request = _request(_fact())
    first_events: list[dict] = []
    second_events: list[dict] = []
    failed = _evaluate(request, pack=_pack(digest="c" * 64))
    first = _evaluate(request, audit_sink=first_events.append)
    second = _evaluate(deepcopy(request), audit_sink=second_events.append)

    assert failed.result_status is ResultStatus.ENGINE_ERROR
    assert first.to_dict() == second.to_dict()
    assert first_events == second_events
    assert first.result_status is ResultStatus.ACCEPTED_FORMAL_RESULT


def test_exception_path_uses_existing_evaluator_semantics() -> None:
    """触发exception时记录一般规则和例外规则，并只保留例外结论。"""

    general = LegalRule(
        id="GENERAL",
        premise_atoms=["fact::trigger"],
        head_claim="claim::general",
        exception_chain=["EXCEPTION"],
        source_anchor="source::law",
    )
    exception = LegalRule(
        id="EXCEPTION",
        premise_atoms=["fact::exception"],
        head_claim="claim::exception",
        source_anchor="source::law",
    )
    result = _evaluate(
        _request(_fact(), _fact(fact_id="fact::exception")),
        pack=_pack("GENERAL", "EXCEPTION"),
        rules=(general, exception),
    )

    assert result.result_status is ResultStatus.ACCEPTED_FORMAL_RESULT
    assert result.claims == ("claim::exception",)
    assert result.used_rule_ids == ("EXCEPTION", "GENERAL")
    assert result.used_fact_ids == ("fact::exception", "fact::trigger")


def test_prohibition_and_permission_cannot_become_unqualified_formal_results() -> None:
    """禁止规则保留阻断效果，许可结论保留review边界。"""

    prohibition = LegalRule(
        id="PROHIBITION",
        premise_atoms=["fact::trigger"],
        head_claim="claim::blocked",
        norm_modality="PROHIBITION",
        source_anchor="source::law",
    )
    permission = LegalRule(
        id="PERMISSION",
        premise_atoms=["fact::trigger"],
        head_claim="claim::permitted",
        norm_modality="PERMISSION",
        source_anchor="source::law",
    )

    blocked = _evaluate(
        _request(_fact()),
        prohibition,
        pack=_pack("PROHIBITION"),
    )
    permitted = _evaluate(
        _request(_fact()),
        permission,
        pack=_pack("PERMISSION"),
    )

    assert blocked.result_status is ResultStatus.REVIEW_ONLY_RESULT
    assert blocked.formal_kernel_used is True
    assert blocked.claims == ()
    assert blocked.used_rule_ids == ("PROHIBITION",)
    assert "PROHIBITION_APPLIED" in blocked.risk_labels
    assert permitted.result_status is ResultStatus.REVIEW_ONLY_RESULT
    assert permitted.claims == ("claim::permitted",)
    assert permitted.certificate_kind is CertificateKind.NONE
    assert "PERMISSION_REQUIRES_REVIEW" in permitted.risk_labels


def test_priority_attack_is_checked_before_formal_acceptance() -> None:
    """priority生成attack，独立checker核验后只接受胜出结论。"""

    winner = LegalRule(
        id="WINNER",
        premise_atoms=["fact::trigger"],
        head_claim="claim::winner",
        priority_over=["claim::loser"],
        source_anchor="source::law",
    )
    loser = LegalRule(
        id="LOSER",
        premise_atoms=["fact::trigger"],
        head_claim="claim::loser",
        source_anchor="source::law",
    )
    events: list[dict] = []
    result = _evaluate(
        _request(_fact()),
        pack=_pack("WINNER", "LOSER"),
        rules=(winner, loser),
        audit_sink=events.append,
    )

    assert result.result_status is ResultStatus.ACCEPTED_FORMAL_RESULT
    assert result.claims == ("claim::winner",)
    assert result.used_rule_ids == ("LOSER", "WINNER")
    assert any(
        event.get("event_type") == "ATTACK_ADDED"
        and event.get("details", {}).get("source_claim_id") == "claim::winner"
        and event.get("details", {}).get("target_claim_id") == "claim::loser"
        for event in events
    )
    assert any(event.get("event_type") == "PRIORITY_RESOLVED" for event in events)
