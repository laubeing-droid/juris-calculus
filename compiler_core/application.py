"""JC v3内部唯一案件求值编排；Phase 4完成审计包前不作为公共API导出。"""

from __future__ import annotations

from copy import deepcopy
from itertools import product
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from compiler_core.argumentation import build_attack_graph_from_evaluator, grounded_extension
from compiler_core.audit import AuditRecorder
from compiler_core.canonical_serialization import content_id, semantic_digest, serialize_aaf
from compiler_core.contracts import (
    BranchResult,
    CertificateKind,
    CaseRequest,
    ExecutionStatus,
    MissingFactReview,
    ResultStatus,
    RulePackDescriptor,
    SCHEMA_VERSION,
    SemanticResult,
    emit_audit_event,
)
from compiler_core.domain_config import get_domain_config
from compiler_core.evaluator import FixpointEvaluator
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
    pack_config_files: tuple[Path, ...] = (),
    checker_strict: bool = False,
) -> SemanticResult:
    """按固定顺序编排事实准入、现有求值器、AAF、独立checker和结果校验。"""

    if not rule_pack.kind or str(rule_pack.kind).lower() != "official":
        return _pack_admission_blocked_result(
            request, rule_pack, pack_config_files, checker_strict,
            ("RULE_PACK_NOT_FORMAL_READY",), audit_sink,
        )
    if rule_pack.review_only:
        labels = ("RULE_PACK_DEVELOPMENT",) if rule_pack.development_override else ("RULE_PACK_REVIEW_ONLY",)
        return _pack_admission_blocked_result(
            request, rule_pack, pack_config_files, checker_strict, labels, audit_sink,
        )
    if rule_pack.distribution_channel == "review":
        return _pack_admission_blocked_result(
            request, rule_pack, pack_config_files, checker_strict,
            ("RULE_PACK_REVIEW_CHANNEL",), audit_sink,
        )
    if rule_pack.development_override:
        return _pack_admission_blocked_result(
            request, rule_pack, pack_config_files, checker_strict,
            ("RULE_PACK_DEVELOPMENT",), audit_sink,
        )
    try:
        domain = _resolve_rule_pack_context(request, rule_pack)
    except ValueError as exc:
        return _pack_admission_blocked_result(
            request, rule_pack, pack_config_files, checker_strict,
            ("RULE_PACK_CONTEXT_MISMATCH", str(exc)), audit_sink,
        )
    checker_ontology, checker_overrides = _resolve_checker_config_paths(
        pack_config_files,
        strict=checker_strict,
    )
    run_id = _run_id_for_case(
        request,
        rule_pack,
        domain,
        tuple(rule_pack.config_files),
        checker_strict,
    )
    recorder = _audit_recorder(run_id, audit_sink)
    run_profile = _run_profile_for_case(
        request,
        rule_pack,
        domain,
        tuple(rule_pack.config_files),
        checker_strict,
    )
    try:
        emit_audit_event(recorder, {
            "event_type": "RUN_STARTED",
            "engine_version": ENGINE_VERSION,
            "run_profile_digest": semantic_digest(run_profile),
        })
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
            reviews = tuple(_missing_fact_review(fact_id, prepared_rules) for fact_id in unknown)
            for fact_id in unknown:
                review = next(item for item in reviews if item.fact_id == fact_id)
                emit_audit_event(recorder, {
                    "event_type": "MISSING_FACT",
                    "fact_id": fact_id,
                    "reason": "UNKNOWN",
                    "impacted_rule_ids": review.impacted_rule_ids,
                    "impacted_claim_ids": review.impacted_claim_ids,
                    "allowed_answer_types": review.allowed_answer_types,
                    "source_requirement": review.source_requirement,
                })
            return _result(
                request,
                run_id,
                result_status=ResultStatus.MISSING_REQUIRED_FACT,
                execution_status=ExecutionStatus.ADMISSION_BLOCKED,
                review_required=True,
                missing_fact_ids=unknown,
                missing_fact_review=reviews,
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
                domain=domain,
                run_id=run_id,
                disputed=disputed,
                ontology_path=checker_ontology,
                overrides_path=checker_overrides,
                checker_strict=checker_strict,
                audit_sink=recorder,
            )
        outcome = _evaluate_once(
            request,
            request.facts,
            prepared_rules,
            candidate_rules,
            source_manifest,
            domain=domain,
            run_id=run_id,
            ontology_path=checker_ontology,
            overrides_path=checker_overrides,
            checker_strict=checker_strict,
            audit_sink=recorder,
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


def _run_profile_for_case(
    request: CaseRequest,
    rule_pack: RulePackDescriptor,
    domain: LegalDomain,
    pack_config_files: tuple[str, ...],
    checker_strict: bool,
) -> dict[str, Any]:
    """构建执行身份，仅用于可复验 run id。"""

    config = get_domain_config(domain)
    return {
        "engine_version": ENGINE_VERSION,
        "checker_profile": {
            "name": "independent_grounded_checker.check_grounded",
            "theorem_refs": list(THEOREM_REFS),
            "strict_mode": checker_strict,
            "config_files": sorted(pack_config_files),
        },
        "compiler_profile": {"name": "FixpointEvaluator", "domain": domain.value},
        "semantics_profile": {
            "implementation": "fixpoint+grounded",
            "critical_streak_max": config.critical_streak_max,
            "critical_score_threshold": config.critical_score_threshold,
            "k_max": config.k_max,
            "taint_threshold": config.taint_threshold,
            "hard_audit_threshold": config.hard_audit_threshold,
            "weights": list(config.weights),
            "enable_discretionary_taint": config.enable_discretionary_taint,
            "concept_registry_digest": semantic_digest(sorted(config.concept_registry)),
            "transition_signature": semantic_digest({
                step: sorted(next_targets)
                for step, next_targets in sorted(config.valid_transitions.items())
            }),
        },
        "pack_profile": {
            "pack_id": rule_pack.pack_id,
            "pack_version": rule_pack.version,
            "pack_digest": rule_pack.content_digest,
            "kind": rule_pack.kind,
            "jurisdiction": request.jurisdiction,
            "governing_law": request.governing_law,
            "distribution_channel": rule_pack.distribution_channel,
            "review_only": rule_pack.review_only,
            "development_override": rule_pack.development_override,
            "config_files": sorted(pack_config_files),
        },
    }


def _run_id_for_case(
    request: CaseRequest,
    rule_pack: RulePackDescriptor,
    domain: LegalDomain,
    pack_config_files: tuple[str, ...],
    checker_strict: bool,
) -> str:
    """带身份的 run id，防止配置变更后误复用旧缓存。"""

    return content_id("run", {
        "request": request.to_dict(),
        "run_profile": _run_profile_for_case(
            request,
            rule_pack,
            domain,
            pack_config_files,
            checker_strict,
        ),
    })


def run_id_for_case(
    request: CaseRequest,
    rule_pack: RulePackDescriptor,
    pack_config_files: tuple[str, ...] = (),
    checker_strict: bool = False,
) -> str:
    """按应用级上下文规则计算run_id，供外部持久化/重放复用。"""

    domain = _resolve_rule_pack_context(request, rule_pack)
    return _run_id_for_case(request, rule_pack, domain, pack_config_files, checker_strict)


def _pack_admission_blocked_result(
    request: CaseRequest,
    rule_pack: RulePackDescriptor,
    pack_config_files: tuple[Path, ...],
    checker_strict: bool,
    risk_labels: tuple[str, ...],
    audit_sink,
) -> SemanticResult:
    """让所有pack早期阻断共享执行身份与最小审计事件。"""

    try:
        run_id = run_id_for_case(
            request,
            rule_pack,
            tuple(rule_pack.config_files),
            checker_strict,
        )
    except ValueError:
        run_id = content_id("run", {
            "request": request.to_dict(),
            "run_profile": {
                "engine_version": ENGINE_VERSION,
                "checker_strict": checker_strict,
                "config_files": sorted(str(path) for path in pack_config_files),
                "pack": rule_pack.to_dict(),
                "context_status": "unresolved",
            },
        })
    recorder = _audit_recorder(run_id, audit_sink)
    emit_audit_event(recorder, {
        "event_type": "RUN_STARTED",
        "engine_version": ENGINE_VERSION,
    })
    emit_audit_event(recorder, {
        "event_type": "REQUEST_VALIDATED",
        "request_digest": semantic_digest(request.to_dict()),
    })
    return _result(
        request,
        run_id,
        result_status=ResultStatus.REVIEW_ONLY_RESULT,
        execution_status=ExecutionStatus.ADMISSION_BLOCKED,
        formal_kernel_used=False,
        review_required=True,
        checker_accepted=False,
        certificate_kind=CertificateKind.NONE,
        claims=(),
        used_fact_ids=(),
        used_rule_ids=(),
        source_ids=(),
        risk_labels=risk_labels,
        audit_sink=recorder,
    )


def _resolve_checker_config_paths(
    pack_config_files: tuple[Path, ...],
    *,
    strict: bool,
) -> tuple[str | None, str | None]:
    """按 pack 配置路径解析 checker 约束配置；严格模式下缺省项直接失败。"""

    ontology_path: str | None = None
    overrides_path: str | None = None
    for candidate in pack_config_files:
        file_name = Path(candidate).name
        if file_name == "core_ontology.yaml":
            ontology_path = str(candidate)
        elif file_name == "L0_overrides_hk.yaml":
            overrides_path = str(candidate)
    if strict and ontology_path is None:
        raise ValueError("checker strict mode requires core_ontology.yaml in pack_config_files")
    if strict and overrides_path is None:
        raise ValueError("checker strict mode requires L0_overrides_hk.yaml in pack_config_files")
    return ontology_path, overrides_path


def _prepare_rules(
    request: CaseRequest,
    rule_pack: RulePackDescriptor,
    rules: tuple[LegalRule, ...],
    relevant_rule_ids: tuple[str, ...],
    source_manifest: SourceManifest,
    audit_sink,
) -> tuple[tuple[LegalRule, ...], tuple[LegalRule, ...]]:
    """验证内部pack描述并返回已声明规则的审计可追踪集合。"""

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
    declared_ids = tuple(
        rule_id
        for rule_id in (
            *rule_pack.verified_rule_ids,
            *rule_pack.candidate_rule_ids,
            *rule_pack.rejected_rule_ids,
        )
    )
    if not declared_ids:
        declared_ids = tuple(rule.id for rule in rules)
    declared_ids = tuple(dict.fromkeys(declared_ids))
    missing = sorted(set(declared_ids) - set(by_id))
    if missing:
        raise ValueError(f"declared rules missing from runtime pack: {missing}")
    verified_ids = set(rule_pack.verified_rule_ids)
    admitted: list[LegalRule] = []
    candidates: list[LegalRule] = []
    relevant = set(relevant_rule_ids)
    for rule_id in declared_ids:
        if rule_id not in relevant:
            continue
        rule = by_id[rule_id]
        source_verdict = source_manifest.validate_anchor(rule.source_anchor)
        eligible = (
            rule_id in verified_ids
            and is_rule_reasoning_eligible(rule)
            and source_verdict.get("status") == "VERIFIED"
        )
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
    *,
    domain: LegalDomain,
    run_id: str,
    disputed: tuple[LegalFact, ...],
    ontology_path: str | None,
    overrides_path: str | None,
    checker_strict: bool,
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
            domain=domain,
            run_id=branch_id,
            ontology_path=ontology_path,
            overrides_path=overrides_path,
            checker_strict=checker_strict,
            audit_sink=audit_sink,
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
    domain: LegalDomain,
    run_id: str,
    audit_sink,
    ontology_path: str | None = None,
    overrides_path: str | None = None,
    checker_strict: bool = False,
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
        domain=domain,
        temporal_scope={"fact_date": request.as_of_date, "governing_law": request.governing_law},
        jurisdiction=request.jurisdiction,
    )
    evaluator = FixpointEvaluator(
        list(rules),
        get_domain_config(domain),
        case_date=request.as_of_date,
        ontology_path=ontology_path,
        overrides_path=overrides_path,
        strict=checker_strict,
    )
    evaluated_state = evaluator.evaluate(state)
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
    material_event_types = {"RULE_APPLIED", "RULE_EXCEPTION_TRIGGERED", "PROHIBITION_BLOCK"}
    material_rule_ids = {
        str(event["rule_id"])
        for event in evaluator_events
        if event.get("event_type") in material_event_types and event.get("rule_id")
    }
    satisfied_ids = set(evaluated_state.facts) | set(evaluated_state.claims)
    supporting_rule_ids = {
        rule.id
        for rule in rules
        if rule.head_claim in active_claims
        and set(rule.premise_atoms).issubset(satisfied_ids)
    }
    used_rule_ids = tuple(sorted(material_rule_ids | supporting_rule_ids))
    argument_witnesses = _argument_witnesses(
        run_id,
        used_rule_ids,
        rules,
        active_claims,
        source_manifest,
    )
    arguments = [{"id": witness["argument_id"]} for witness in argument_witnesses]
    claim_attacks = sorted(build_attack_graph_from_evaluator(
        list(rules),
        {"labels": {claim_id: claim_id for claim_id in active_claims}},
    ))
    priority_edges = _priority_edges(rules)
    for source, target in claim_attacks:
        emit_audit_event(audit_sink, {"event_type": "ATTACK", "source": source, "target": target})
        for priority_rule_id in priority_edges.get((source, target), ()):
            emit_audit_event(audit_sink, {
                "event_type": "PRIORITY",
                "rule_id": priority_rule_id,
                "source": source,
                "target": target,
            })
    attack_witnesses = _attack_witnesses(argument_witnesses, claim_attacks, rules)
    argument_attacks = [
        (witness["source_argument_id"], witness["target_argument_id"])
        for witness in attack_witnesses
    ]
    grounded = grounded_extension(arguments, argument_attacks)
    labels = {
        claim_id: label
        for label, field in (("IN", "accepted"), ("OUT", "rejected"), ("UNDEC", "undecided"))
        for claim_id in grounded[field]
    }
    emit_audit_event(audit_sink, {
        "event_type": "CHECKER_STARTED",
        "theorem_refs_digest": semantic_digest(THEOREM_REFS),
    })
    serialized_aaf = serialize_aaf(arguments, argument_attacks)
    checker = check_grounded(serialized_aaf, labels, list(THEOREM_REFS))
    accepted_argument_ids = set(grounded["accepted"])
    accepted_claims = tuple(sorted({
        str(witness["claim_id"])
        for witness in argument_witnesses
        if witness["argument_id"] in accepted_argument_ids
    }))
    checker_receipt = {
        "receipt_kind": "independent_grounded_checker",
        "valid": bool(checker["valid"]),
        "violations": list(sorted(checker["violations"])),
        "aaf_digest": semantic_digest({
            "arguments": arguments,
            "attacks": argument_attacks,
        }),
        "argument_witnesses": list(argument_witnesses),
        "attack_witnesses": list(attack_witnesses),
        "claim_projection": {
            "accepted_argument_ids": sorted(accepted_argument_ids),
            "accepted_claim_ids": list(accepted_claims),
        },
    }
    emit_audit_event(audit_sink, {
        "event_type": "CHECKER_VERDICT",
        "accepted": bool(checker["valid"]),
        "violations": tuple(sorted(checker["violations"])),
    })
    certificates = [
        generate_certificate(argument_id, arguments, argument_attacks, grounded)
        for argument_id in sorted(accepted_argument_ids)
    ]
    certificates_valid = bool(certificates) and all(certificate.verifiable for certificate in certificates)
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
        "checker_receipt": checker_receipt,
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
    missing_fact_review: tuple[MissingFactReview, ...] = (),
    taint: tuple[str, ...] = (),
    risk_labels: tuple[str, ...] = (),
    checker_receipt: Mapping[str, Any] | None = None,
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
        "missing_fact_review": missing_fact_review,
        "taint": taint,
        "risk_labels": risk_labels,
        "checker_receipt": dict(checker_receipt or {}),
    }
    projection = {
        key: (
            value.value
            if isinstance(value, (ExecutionStatus, ResultStatus, CertificateKind))
            else [branch.to_dict() for branch in value]
            if key == "branches"
            else [item.to_dict() for item in value]
            if key == "missing_fact_review"
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


def _missing_fact_review(fact_id: str, rules: tuple[LegalRule, ...]) -> MissingFactReview:
    """从已准入规则构建UNKNOWN事实的确定性影响范围。"""

    impacted = tuple(sorted(rule.id for rule in rules if fact_id in rule.premise_atoms))
    claims = tuple(sorted({rule.head_claim for rule in rules if rule.id in impacted and rule.head_claim}))
    return MissingFactReview(
        fact_id=fact_id,
        impacted_rule_ids=impacted,
        impacted_claim_ids=claims,
    )


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


def _priority_edges(rules: tuple[LegalRule, ...]) -> dict[tuple[str, str], tuple[str, ...]]:
    """将priority_over按头claim对索引为固定的法条ID集合。"""

    edges: dict[tuple[str, str], list[str]] = {}
    for rule in rules:
        source = rule.head_claim
        if not source:
            continue
        for target in rule.priority_over:
            edges.setdefault((source, target), []).append(rule.id)
    return {key: tuple(sorted(set(ids))) for key, ids in edges.items()}


def _argument_witnesses(
    run_id: str,
    used_rule_ids: tuple[str, ...],
    rules: tuple[LegalRule, ...],
    active_claims: Mapping[str, Any],
    source_manifest: SourceManifest,
) -> tuple[dict[str, Any], ...]:
    """为每个实际触发规则保留独立argument identity。"""

    by_id = {rule.id: rule for rule in rules}
    witnesses: list[dict[str, Any]] = []
    for rule_id in used_rule_ids:
        rule = by_id[rule_id]
        if not rule.head_claim or rule.head_claim not in active_claims:
            continue
        source_verdict = source_manifest.validate_anchor(rule.source_anchor)
        payload = {
            "run_id": run_id,
            "rule_id": rule.id,
            "claim_id": rule.head_claim,
            "premise_ids": sorted(rule.premise_atoms),
            "source_snapshot_id": str(source_verdict.get("source_snapshot_id", "")),
        }
        witnesses.append({
            "argument_id": content_id("argument", payload),
            "rule_id": rule.id,
            "claim_id": rule.head_claim,
            "premise_ids": list(payload["premise_ids"]),
            "source_snapshot_id": payload["source_snapshot_id"],
        })
    return tuple(sorted(witnesses, key=lambda item: item["argument_id"]))


def _attack_witnesses(
    argument_witnesses: tuple[dict[str, Any], ...],
    claim_attacks: list[tuple[str, str]],
    rules: tuple[LegalRule, ...],
) -> tuple[dict[str, Any], ...]:
    """把claim relation提升为argument笛卡尔边并绑定来源规则。"""

    by_claim: dict[str, list[dict[str, Any]]] = {}
    for witness in argument_witnesses:
        by_claim.setdefault(str(witness["claim_id"]), []).append(witness)
    witnesses: list[dict[str, Any]] = []
    for source_claim, target_claim in claim_attacks:
        origins = _claim_attack_origins(rules, source_claim, target_claim)
        for source in by_claim.get(source_claim, ()):
            for target in by_claim.get(target_claim, ()):
                witnesses.append({
                    "source_argument_id": source["argument_id"],
                    "target_argument_id": target["argument_id"],
                    "source_claim_id": source_claim,
                    "target_claim_id": target_claim,
                    "origins": list(origins),
                })
    return tuple(sorted(
        witnesses,
        key=lambda item: (item["source_argument_id"], item["target_argument_id"]),
    ))


def _claim_attack_origins(
    rules: tuple[LegalRule, ...],
    source_claim: str,
    target_claim: str,
) -> tuple[dict[str, str], ...]:
    """记录attack的typed relation与原始规则ID。"""

    by_id = {rule.id: rule for rule in rules}
    origins: set[tuple[str, str]] = set()
    for rule in rules:
        if rule.head_claim == source_claim:
            for kind, refs in (
                ("explicit", rule.attacks),
                ("priority", rule.priority_over),
                ("exception_to", getattr(rule, "exception_to", ())),
            ):
                for ref in refs:
                    resolved = by_id.get(str(ref))
                    if str(ref) == target_claim or (resolved and resolved.head_claim == target_claim):
                        origins.add((kind, rule.id))
        if rule.head_claim == target_claim:
            for ref in rule.exception_chain:
                resolved = by_id.get(str(ref))
                if str(ref) == source_claim or (resolved and resolved.head_claim == source_claim):
                    origins.add(("exception_chain", rule.id))
    if not origins:
        origins.add(("relation", ""))
    return tuple(
        {"kind": kind, "origin_rule_id": rule_id}
        for kind, rule_id in sorted(origins)
    )


def _rule_pack_context(request: CaseRequest, rule_pack: RulePackDescriptor) -> tuple[str, str]:
    """返回规则包上下文并做法域一致性校验。"""

    request_law = _normalise_governing_law(request.governing_law)
    request_jur = _normalise_jurisdiction(request.jurisdiction)
    pack_law = _normalise_governing_law(rule_pack.governing_law)
    pack_jur = _normalise_jurisdiction(rule_pack.jurisdiction)
    request_case_date = _parse_iso_date(request.as_of_date)
    if rule_pack.effective_from:
        if request_case_date < _parse_iso_date(rule_pack.effective_from):
            raise ValueError("request as_of_date before rule pack effective_from")
    if rule_pack.effective_to:
        if request_case_date > _parse_iso_date(rule_pack.effective_to):
            raise ValueError("request as_of_date after rule pack effective_to")
    if pack_jur and pack_jur != request_jur:
        raise ValueError("jurisdiction mismatch between request and rule pack")
    if pack_law and request_law and pack_law != request_law:
        raise ValueError("governing_law mismatch between request and rule pack")
    return (
        request_law or pack_law,
        request_jur or pack_jur,
    )


def _resolve_rule_pack_context(request: CaseRequest, rule_pack: RulePackDescriptor) -> LegalDomain:
    """从上下文确定评估法律域；不允许未识别法域自动回落。"""

    governing_law, jurisdiction = _rule_pack_context(request, rule_pack)
    if jurisdiction == "":
        raise ValueError("jurisdiction is required for formal evaluation")
    if governing_law == "CRIMINAL":
        return LegalDomain.CRIMINAL
    if governing_law == "ADMINISTRATIVE":
        return LegalDomain.ADMINISTRATIVE
    if jurisdiction not in {"CN", "HK", "US"}:
        raise ValueError(f"unsupported jurisdiction for rule packing: {jurisdiction}")
    return LegalDomain.CIVIL


def _parse_iso_date(value: str) -> date:
    """从可信输入中解析 ISO 日期；保留异常用于上层 admission blocked。"""

    return date.fromisoformat(str(value))


def _normalise_governing_law(value: str) -> str:
    text = str(value or "").upper().replace(" ", "")
    if any(token in text for token in ("刑事", "CRIMINAL", "PENAL")):
        return "CRIMINAL"
    if any(token in text for token in ("行政", "ADMINISTRATIVE")):
        return "ADMINISTRATIVE"
    if any(token in text for token in ("PRC", "CN", "CHINA", "中华人民共和国", "中国", "民事")):
        return "CN"
    if "HK" in text or "HONGKONG" in text:
        return "HK"
    if "US" in text or "USA" in text:
        return "US"
    return ""


def _normalise_jurisdiction(value: str) -> str:
    text = str(value or "").strip().upper().replace("-", "").replace("_", "").replace(" ", "")
    if text in {"CN", "PRC", "CIVIL", "中华人民共和国", "CHINA", "中国"}:
        return "CN"
    if text in {"HK", "HONGKONG", "香港", "HKSAR"}:
        return "HK"
    if text in {"US", "USA", "ENGLISH", "ENUS", "UNITEDSTATES"}:
        return "US"
    return text


def _relevant_rule_ids(facts: tuple[LegalFact, ...], rules: tuple[LegalRule, ...]) -> tuple[str, ...]:
    """按事实前提及exception/priority可达关系构建稳定相关规则集合。"""

    fact_ids = {fact.id for fact in facts}
    by_id = {rule.id: rule for rule in rules}
    by_head: dict[str, set[str]] = {}
    by_premise: dict[str, set[str]] = {}
    for rule in rules:
        if rule.head_claim:
            by_head.setdefault(rule.head_claim, set()).add(rule.id)
        for premise in rule.premise_atoms:
            by_premise.setdefault(premise, set()).add(rule.id)
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
            for target in rule.priority_over:
                dependencies.update(by_head.get(target, set()))
                mapped = by_id.get(str(target))
                if mapped and mapped.id in by_id:
                    dependencies.add(mapped.id)
            if rule.head_claim:
                dependencies.update(by_head.get(rule.head_claim, set()))
                dependencies.update(by_premise.get(rule.head_claim, set()))
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
