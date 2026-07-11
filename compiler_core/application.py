"""JC v3内部唯一案件求值编排；Phase 4完成审计包前不作为公共API导出。"""

from __future__ import annotations

from copy import deepcopy
from itertools import product
from typing import Any, Iterable, Mapping

from compiler_core.argumentation import build_attack_graph_from_evaluator, grounded_extension
from compiler_core.audit import AuditRecorder
from compiler_core.canonical_serialization import content_id, semantic_digest, serialize_aaf
from compiler_core.contracts import (
    BranchResult,
    CertificateKind,
    CaseRequest,
    ExecutionStatus,
    ResultStatus,
    RulePackDescriptor,
    SCHEMA_VERSION,
    SemanticResult,
    emit_audit_event,
)
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import CriticalClarityFailure, FixpointEvaluator
from compiler_core.independent_grounded_checker import check_grounded
from compiler_core.litigation_engineering import generate_certificate
from compiler_core.source_manifest import SourceManifest
from compiler_core.types import (
    FactTrustStatus,
    IRState,
    LegalDomain,
    LegalFact,
    LegalRule,
    is_rule_reasoning_eligible,
)
from compiler_core.version import __version__


ENGINE_VERSION = __version__
THEOREM_REFS = ("Lean.Dung1995.Grounded.unique", "Lean.Dung1995.Grounded.lfp")


def evaluate_case(
    request: CaseRequest,
    rule_pack: RulePackDescriptor,
    rules: Iterable[LegalRule],
    *,
    source_manifest: SourceManifest,
    audit_sink=None,
) -> SemanticResult:
    """按固定顺序编排事实准入、现有求值器、AAF、独立checker和结果校验。"""

    run_id = content_id("run", request.to_dict())
    recorder = _audit_recorder(run_id, audit_sink)
    try:
        emit_audit_event(recorder, {"event_type": "RUN_STARTED", "engine_version": ENGINE_VERSION})
        emit_audit_event(recorder, {
            "event_type": "REQUEST_VALIDATED",
            "request_digest": semantic_digest(request.to_dict()),
        })
        all_rules = tuple(rules)
        relevant_rule_ids = _relevant_rule_ids(request.facts, all_rules)
        emit_audit_event(recorder, {
            "event_type": "RELEVANCE_SET_BUILT",
            "algorithm_version": "premise-closure-v1",
            "candidate_rule_count": len(relevant_rule_ids),
            "rule_ids_digest": semantic_digest(relevant_rule_ids),
        })
        prepared_rules, candidate_rules = _prepare_rules(
            request,
            rule_pack,
            all_rules,
            relevant_rule_ids,
            source_manifest,
            recorder,
        )
        for fact in request.facts:
            emit_audit_event(recorder, {
                "event_type": "FACT_ADMISSION",
                "fact_id": fact.id,
                "status": fact.status.value,
                "admitted": fact.can_enter_formal_kernel(),
                "source_ids": fact.source_ids,
                "reasoning_tier": fact.reasoning_tier,
            })
        unknown = tuple(sorted(fact.id for fact in request.facts if fact.status == FactTrustStatus.UNKNOWN))
        if unknown:
            for fact_id in unknown:
                emit_audit_event(recorder, {
                    "event_type": "MISSING_FACT",
                    "fact_id": fact_id,
                    "reason": "UNKNOWN",
                })
            return _result(
                request,
                run_id,
                result_status=ResultStatus.MISSING_REQUIRED_FACT,
                execution_status=ExecutionStatus.ADMISSION_BLOCKED,
                review_required=True,
                missing_fact_ids=unknown,
                risk_labels=("MISSING_REQUIRED_FACT",),
                audit_sink=recorder,
            )
        disputed = tuple(fact for fact in request.facts if fact.status == FactTrustStatus.DISPUTED)
        if disputed:
            if request.branch_limit_exceeded:
                return _result(
                    request,
                    run_id,
                    result_status=ResultStatus.REVIEW_ONLY_RESULT,
                    execution_status=ExecutionStatus.ADMISSION_BLOCKED,
                    review_required=True,
                    risk_labels=("BRANCH_LIMIT_EXCEEDED",),
                    audit_sink=recorder,
                )
            return _evaluate_disputed(
                request,
                prepared_rules,
                candidate_rules,
                source_manifest,
                run_id,
                disputed,
                recorder,
            )
        outcome = _evaluate_once(
            request,
            request.facts,
            prepared_rules,
            candidate_rules,
            source_manifest,
            run_id,
            recorder,
        )
        return _result_from_outcome(request, run_id, outcome, recorder)
    except Exception as exc:
        try:
            emit_audit_event(recorder, {"event_type": "ENGINE_ERROR", "error_type": type(exc).__name__})
        except Exception:
            pass
        return _result(
            request,
            run_id,
            result_status=ResultStatus.ENGINE_ERROR,
            execution_status=ExecutionStatus.ENGINE_ERROR,
            review_required=True,
            risk_labels=("ENGINE_ERROR", type(exc).__name__),
            audit_sink=None,
        )


def _prepare_rules(
    request: CaseRequest,
    rule_pack: RulePackDescriptor,
    rules: tuple[LegalRule, ...],
    relevant_rule_ids: tuple[str, ...],
    source_manifest: SourceManifest,
    audit_sink,
) -> tuple[tuple[LegalRule, ...], tuple[LegalRule, ...]]:
    """验证内部pack描述并返回已声明verified的唯一规则集合。"""

    if (
        request.rule_pack_id != rule_pack.pack_id
        or request.rule_pack_version != rule_pack.version
        or request.rule_pack_digest != rule_pack.content_digest
    ):
        raise ValueError("request rule pack does not match verified descriptor")
    ids = [rule.id for rule in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate rule id")
    by_id = {rule.id: rule for rule in rules}
    missing = sorted(set(rule_pack.verified_rule_ids) - set(by_id))
    if missing:
        raise ValueError(f"verified rules missing from runtime pack: {missing}")
    admitted: list[LegalRule] = []
    candidates: list[LegalRule] = []
    relevant = set(relevant_rule_ids)
    for rule_id in rule_pack.verified_rule_ids:
        rule = by_id[rule_id]
        source_verdict = source_manifest.validate_anchor(rule.source_anchor)
        eligible = is_rule_reasoning_eligible(rule) and source_verdict.get("status") == "VERIFIED"
        if rule.id in relevant:
            emit_audit_event(audit_sink, {
                "event_type": "RULE_ADMISSION",
                "rule_id": rule.id,
                "source_status": source_verdict.get("status", "UNKNOWN"),
                "source_ids": (
                    (str(source_verdict["source_snapshot_id"]),)
                    if source_verdict.get("source_snapshot_id")
                    else ()
                ),
                "admitted": eligible,
            })
        (admitted if eligible else candidates).append(rule)
    return tuple(admitted), tuple(candidates)


def _evaluate_disputed(
    request: CaseRequest,
    rules: tuple[LegalRule, ...],
    candidate_rules: tuple[LegalRule, ...],
    source_manifest: SourceManifest,
    run_id: str,
    disputed: tuple[LegalFact, ...],
    audit_sink,
) -> SemanticResult:
    """对争议事实做稳定笛卡尔分支；整体永远不升级为正式certificate。"""

    alternatives = [fact.alternatives or ({"value": False}, {"value": True}) for fact in disputed]
    branches: list[BranchResult] = []
    used_facts: set[str] = set()
    used_rules: set[str] = set()
    sources: set[str] = set()
    formal_kernel_used = False
    for index, selected in enumerate(product(*alternatives)):
        branch_facts = deepcopy(list(request.facts))
        selected_by_id = {fact.id: alternative for fact, alternative in zip(disputed, selected)}
        for fact in branch_facts:
            if fact.id in selected_by_id:
                fact.status = FactTrustStatus.USER_ASSUMED
                fact.value = selected_by_id[fact.id].get("value")
        branch_id = content_id("branch", {"request": request.to_dict(), "alternatives": selected_by_id})
        emit_audit_event(audit_sink, {
            "event_type": "BRANCH_CREATED",
            "branch_id": branch_id,
            "branch_index": index,
            "assumptions_digest": semantic_digest(selected_by_id),
        })
        outcome = _evaluate_once(
            request,
            tuple(branch_facts),
            rules,
            candidate_rules,
            source_manifest,
            branch_id,
            audit_sink,
        )
        branches.append(BranchResult(
            branch_id=branch_id,
            result_status=outcome["result_status"],
            claims=outcome["claims"],
            taint=tuple(sorted(set(outcome["taint"]) | {"disputed"})),
        ))
        used_facts.update(outcome["used_fact_ids"])
        used_rules.update(outcome["used_rule_ids"])
        sources.update(outcome["source_ids"])
        formal_kernel_used = formal_kernel_used or outcome["formal_kernel_used"]
    return _result(
        request,
        run_id,
        result_status=ResultStatus.REVIEW_ONLY_RESULT,
        execution_status=ExecutionStatus.COMPLETED,
        review_required=True,
        formal_kernel_used=formal_kernel_used,
        branches=tuple(branches),
        used_fact_ids=tuple(used_facts),
        used_rule_ids=tuple(used_rules),
        source_ids=tuple(sources),
        taint=("disputed",),
        risk_labels=("DISPUTED_BRANCHES",),
        audit_sink=audit_sink,
    )


def _evaluate_once(
    request: CaseRequest,
    facts: tuple[LegalFact, ...],
    rules: tuple[LegalRule, ...],
    candidate_rules: tuple[LegalRule, ...],
    source_manifest: SourceManifest,
    run_id: str,
    audit_sink,
) -> dict[str, Any]:
    """运行一条无争议分支；底层算法全部复用现有实现。"""

    admitted = [fact for fact in facts if fact.can_enter_formal_kernel()]
    assumed = [fact for fact in facts if fact.status == FactTrustStatus.USER_ASSUMED]
    available = admitted + assumed
    available_ids = {fact.id for fact in available}
    relevant_candidate_ids = sorted({
        fact.id
        for fact in facts
        if fact.id not in available_ids
        and any(fact.id in rule.premise_atoms for rule in rules)
    })
    relevant_candidate_rule_ids = sorted(
        rule.id
        for rule in candidate_rules
        if not rule.premise_atoms or set(rule.premise_atoms) & available_ids
    )
    state = IRState(
        facts={fact.id: deepcopy(fact) for fact in available},
        world_id=run_id,
        domain=LegalDomain.CIVIL,
        temporal_scope={"fact_date": request.as_of_date, "governing_law": request.governing_law},
        jurisdiction=request.jurisdiction,
    )
    evaluator = FixpointEvaluator(
        list(rules),
        DomainConfig(domain=LegalDomain.CIVIL),
        case_date=request.as_of_date,
    )
    try:
        evaluated_state = evaluator.evaluate(state)
    except CriticalClarityFailure as exc:
        partial = getattr(exc, "partial_state", None)
        evaluated_state = partial if partial is not None else state
    rules_by_id = {rule.id: rule for rule in rules}
    evaluator_events = tuple(
        _enrich_evaluator_event(_without_runtime_fields(event), rules_by_id)
        for event in evaluator.audit_log
    )
    for event in evaluator_events:
        emit_audit_event(audit_sink, event)
    active_claims = {
        claim_id: claim
        for claim_id, claim in evaluated_state.claims.items()
        if claim.confidence > 0 and claim_id not in evaluated_state.blocked_claims
    }
    claims = [{"id": claim_id} for claim_id in sorted(active_claims)]
    attacks = sorted(build_attack_graph_from_evaluator(
        list(rules),
        {"labels": {claim_id: claim_id for claim_id in active_claims}},
    ))
    for source, target in attacks:
        emit_audit_event(audit_sink, {"event_type": "ATTACK", "source": source, "target": target})
        priority_rule = next(
            (
                rule
                for rule in rules
                if rule.head_claim == source and target in rule.priority_over
            ),
            None,
        )
        if priority_rule is not None:
            emit_audit_event(audit_sink, {
                "event_type": "PRIORITY",
                "rule_id": priority_rule.id,
                "source": source,
                "target": target,
            })
    grounded = grounded_extension(claims, attacks)
    labels = {
        claim_id: label
        for label, field in (("IN", "accepted"), ("OUT", "rejected"), ("UNDEC", "undecided"))
        for claim_id in grounded[field]
    }
    emit_audit_event(audit_sink, {
        "event_type": "CHECKER_STARTED",
        "theorem_refs_digest": semantic_digest(THEOREM_REFS),
    })
    checker = check_grounded(serialize_aaf(claims, attacks), labels, list(THEOREM_REFS))
    emit_audit_event(audit_sink, {
        "event_type": "CHECKER_VERDICT",
        "accepted": bool(checker["valid"]),
        "violations": tuple(sorted(checker["violations"])),
    })
    accepted_claims = tuple(grounded["accepted"])
    certificates = [generate_certificate(claim_id, claims, attacks, grounded) for claim_id in accepted_claims]
    certificates_valid = bool(certificates) and all(certificate.verifiable for certificate in certificates)
    material_event_types = {"RULE_APPLIED", "RULE_EXCEPTION_TRIGGERED", "PROHIBITION_BLOCK"}
    used_rule_ids = tuple(sorted({
        str(event["rule_id"])
        for event in evaluator_events
        if event.get("event_type") in material_event_types and event.get("rule_id")
    }))
    used_fact_ids = tuple(sorted({
        premise
        for rule in rules
        if rule.id in used_rule_ids
        for premise in rule.premise_atoms
        if premise in available_ids
    }))
    source_ids, unverified_rules = _verified_sources(used_rule_ids, rules, source_manifest)
    formal_kernel_used = bool(used_rule_ids)
    risk_labels: set[str] = set()
    if relevant_candidate_ids:
        risk_labels.add("RELEVANT_FACT_NOT_ADMITTED")
    if relevant_candidate_rule_ids:
        risk_labels.add("RELEVANT_RULE_NOT_ADMITTED")
    if unverified_rules:
        risk_labels.add("USED_RULE_SOURCE_UNVERIFIED")
    if not grounded["convergent"]:
        risk_labels.add("GROUNDED_TRUNCATED")
    permission_used = any(
        rule.id in used_rule_ids and rule.norm_modality == "PERMISSION"
        for rule in rules
    )
    prohibition_used = bool(evaluated_state.blocked_claims)
    claim_tainted = any(
        claim.taint_chain or claim.requires_human_review
        for claim in active_claims.values()
    )
    if permission_used:
        risk_labels.add("PERMISSION_REQUIRES_REVIEW")
        for rule in rules:
            if rule.id in used_rule_ids and rule.norm_modality == "PERMISSION":
                emit_audit_event(audit_sink, {
                    "event_type": "PERMISSION",
                    "rule_id": rule.id,
                    "claim_id": rule.head_claim,
                })
    if prohibition_used:
        risk_labels.add("PROHIBITION_APPLIED")
    if claim_tainted:
        risk_labels.add("TAINT_REQUIRES_REVIEW")
        for claim_id, claim in sorted(active_claims.items()):
            if claim.taint_chain or claim.requires_human_review:
                emit_audit_event(audit_sink, {
                    "event_type": "TAINT",
                    "claim_id": claim_id,
                    "rule_id": next((rule.id for rule in rules if rule.head_claim == claim_id), ""),
                    "taint": ("claim_taint",),
                    "taint_source": "formalizable_or_review_threshold",
                })
    if grounded["undecided"]:
        result_status = ResultStatus.CONFLICT_CERTIFICATE
        certificate_kind = CertificateKind.CONFLICT
        review_required = True
        checker_accepted = bool(checker["valid"])
    elif assumed:
        result_status = ResultStatus.HYPOTHETICAL_RESULT
        certificate_kind = CertificateKind.NONE
        review_required = True
        checker_accepted = False
    elif (
        accepted_claims
        and checker["valid"]
        and certificates_valid
        and formal_kernel_used
        and not relevant_candidate_ids
        and not relevant_candidate_rule_ids
        and not unverified_rules
        and not permission_used
        and not claim_tainted
    ):
        result_status = ResultStatus.ACCEPTED_FORMAL_RESULT
        certificate_kind = CertificateKind.FORMAL
        review_required = False
        checker_accepted = True
    else:
        result_status = ResultStatus.REVIEW_ONLY_RESULT
        certificate_kind = CertificateKind.NONE
        review_required = True
        checker_accepted = False
    return {
        "result_status": result_status,
        "execution_status": ExecutionStatus.COMPLETED,
        "formal_kernel_used": formal_kernel_used,
        "review_required": review_required,
        "checker_accepted": checker_accepted,
        "certificate_kind": certificate_kind,
        "claims": accepted_claims,
        "used_fact_ids": used_fact_ids,
        "used_rule_ids": used_rule_ids,
        "source_ids": source_ids,
        "missing_fact_ids": (),
        "taint": tuple(sorted(
            ({"assumption"} if assumed else set())
            | ({"claim_taint"} if claim_tainted else set())
        )),
        "risk_labels": tuple(sorted(risk_labels)),
    }


def _verified_sources(
    used_rule_ids: tuple[str, ...],
    rules: tuple[LegalRule, ...],
    source_manifest: SourceManifest,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """只接受manifest精确匹配且具备内容hash的规则来源。"""

    by_id = {rule.id: rule for rule in rules}
    source_ids: set[str] = set()
    unverified: list[str] = []
    for rule_id in used_rule_ids:
        anchor = by_id[rule_id].source_anchor
        verdict = source_manifest.validate_anchor(anchor)
        if verdict.get("status") == "VERIFIED":
            source_ids.add(str(verdict["source_snapshot_id"]))
        else:
            unverified.append(rule_id)
    return tuple(sorted(source_ids)), tuple(sorted(unverified))


def _result_from_outcome(request: CaseRequest, run_id: str, outcome: Mapping[str, Any], audit_sink) -> SemanticResult:
    """把单分支执行结果交给统一不可变契约校验。"""

    return _result(request, run_id, audit_sink=audit_sink, **dict(outcome))


def _result(
    request: CaseRequest,
    run_id: str,
    *,
    result_status: ResultStatus,
    execution_status: ExecutionStatus,
    review_required: bool,
    formal_kernel_used: bool = False,
    checker_accepted: bool = False,
    certificate_kind: CertificateKind = CertificateKind.NONE,
    claims: tuple[str, ...] = (),
    branches: tuple[BranchResult, ...] = (),
    used_fact_ids: tuple[str, ...] = (),
    used_rule_ids: tuple[str, ...] = (),
    source_ids: tuple[str, ...] = (),
    missing_fact_ids: tuple[str, ...] = (),
    taint: tuple[str, ...] = (),
    risk_labels: tuple[str, ...] = (),
    audit_sink=None,
) -> SemanticResult:
    """先计算不含digest自身的投影，再构造并验证SemanticResult。"""

    values = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "execution_status": execution_status,
        "result_status": result_status,
        "formal_kernel_used": formal_kernel_used,
        "review_required": review_required,
        "checker_accepted": checker_accepted,
        "certificate_kind": certificate_kind,
        "engine_version": ENGINE_VERSION,
        "pack_id": request.rule_pack_id,
        "pack_version": request.rule_pack_version,
        "pack_digest": request.rule_pack_digest,
        "claims": claims,
        "branches": branches,
        "used_fact_ids": used_fact_ids,
        "used_rule_ids": used_rule_ids,
        "source_ids": source_ids,
        "missing_fact_ids": missing_fact_ids,
        "taint": taint,
        "risk_labels": risk_labels,
    }
    projection = {
        key: (
            value.value
            if isinstance(value, (ExecutionStatus, ResultStatus, CertificateKind))
            else [branch.to_dict() for branch in value]
            if key == "branches"
            else value
        )
        for key, value in values.items()
    }
    result = SemanticResult(result_digest=semantic_digest(projection), **values)
    emit_audit_event(audit_sink, {
        "event_type": "RESULT_FINALIZED",
        "result_status": result.result_status.value,
        "result_digest": result.result_digest,
    })
    return result


def _without_runtime_fields(event: Mapping[str, Any]) -> dict[str, Any]:
    """Phase 2内存事件移除时间戳；持久化seq/run字段留给Phase 4。"""

    return {key: deepcopy(value) for key, value in event.items() if key != "timestamp"}


def _audit_recorder(run_id: str, audit_sink) -> AuditRecorder:
    """每次运行只创建一个recorder，并允许测试观察规范事件副本。"""

    if isinstance(audit_sink, AuditRecorder):
        if audit_sink.run_id != run_id:
            raise ValueError("audit recorder run_id mismatch")
        return audit_sink
    return AuditRecorder(run_id, downstream=audit_sink)


def _relevant_rule_ids(facts: tuple[LegalFact, ...], rules: tuple[LegalRule, ...]) -> tuple[str, ...]:
    """按事实前提及exception/priority可达关系构建稳定相关规则集合。"""

    fact_ids = {fact.id for fact in facts}
    by_id = {rule.id: rule for rule in rules}
    by_head = {rule.head_claim: rule.id for rule in rules if rule.head_claim}
    relevant = {
        rule.id
        for rule in rules
        if not rule.premise_atoms or fact_ids.intersection(rule.premise_atoms)
    }
    changed = True
    while changed:
        changed = False
        for rule_id in tuple(sorted(relevant)):
            rule = by_id[rule_id]
            dependencies = set(rule.exception_chain)
            dependencies.update(by_head[target] for target in rule.priority_over if target in by_head)
            dependencies.update(
                candidate.id
                for candidate in rules
                if rule.head_claim and rule.head_claim in candidate.premise_atoms
            )
            before = len(relevant)
            relevant.update(item for item in dependencies if item in by_id)
            changed = changed or len(relevant) != before
    return tuple(sorted(relevant))


def _enrich_evaluator_event(
    event: Mapping[str, Any],
    rules_by_id: Mapping[str, LegalRule],
) -> dict[str, Any]:
    """只补充现有规则对象中的modality，不加工法律内容。"""

    enriched = dict(event)
    rule = rules_by_id.get(str(event.get("rule_id", "")))
    enriched["modality"] = rule.norm_modality if rule is not None else ""
    return enriched
