"""Freeze the v2 semantic fields that the v3 application layer must preserve."""

from compiler_core.argumentation import grounded_extension
from compiler_core.canonical_serialization import serialize_aaf
from compiler_core.domain_config import DomainConfig
from compiler_core.evaluator import FixpointEvaluator
from compiler_core.fact_trust_envelope import FactTrustEnvelope, FactTrustStatus
from compiler_core.independent_grounded_checker import check_grounded
from compiler_core.reasoning_boundary import BoundaryResultStatus, classify_boundary_result
from compiler_core.spec_shadow_harness import (
    _build_contract_fixture,
    _build_license_fixture,
    build_jc_shadow_payload,
)
from compiler_core.types import IRState, LegalDomain, LegalFact, LegalRule


THEOREM_REFS = ["Lean.Dung1995.Grounded.unique", "Lean.Dung1995.Grounded.lfp"]


def _rule(rule_id, head, modality, *, exception_chain=()):
    """构造只含语义必需字段的规则，避免 fixture 混入来源路径或运行期元数据。"""

    return LegalRule(
        id=rule_id,
        premise_atoms=["trigger"],
        head_claim=head,
        norm_modality=modality,
        exception_chain=list(exception_chain),
    )


def _shadow_snapshot(fixture):
    """从既有 shadow payload 中仅提取跨版本必须稳定的语义字段。"""

    payload = build_jc_shadow_payload(fixture)
    return {
        "used_facts": payload["facts"],
        "used_rules": payload["horn_rules_fired"],
        "claims": {
            "closure": payload["closure_claims"],
            "accepted": payload["accepted_argument_ids"],
            "rejected": payload["rejected_argument_ids"],
            "undecided": payload["undecided_argument_ids"],
        },
        "attack_edges": payload["attacks_constructed"],
        "priority_result": {
            "applied": "PRIORITY_DEFEAT" in payload["attack_kinds"],
        },
        "checker_verdict": {"accepted": payload["checker_verdict"]["ok"]},
        "result_status": payload["status"],
    }


def _labels(result):
    """把 grounded 三分集合规范化为独立 checker 接受的确定性标签表。"""

    return {
        claim_id: label
        for label, field in (("IN", "accepted"), ("OUT", "rejected"), ("UNDEC", "undecided"))
        for claim_id in result[field]
    }


def test_v2_modal_and_exception_evaluator_semantics_are_frozen():
    """冻结 obligation、prohibition、permission 与 exception 的现有求值语义。"""

    rules = [
        _rule("R_OBLIGATION", "must_act", "OBLIGATION"),
        _rule("R_PROHIBITION", "forbidden_act", "PROHIBITION"),
        _rule("R_PERMISSION", "may_act", "PERMISSION"),
        _rule("R_GENERAL", "general_result", "OBLIGATION", exception_chain=("R_EXCEPTION",)),
        LegalRule(
            id="R_EXCEPTION",
            premise_atoms=["exception_fact"],
            head_claim="exception_result",
            norm_modality="CONSTITUTIVE",
        ),
    ]
    evaluator = FixpointEvaluator(rules, DomainConfig(domain=LegalDomain.CIVIL))
    state = IRState(
        facts={
            fact_id: LegalFact(id=fact_id, description=fact_id)
            for fact_id in ("trigger", "exception_fact")
        }
    )

    result = evaluator.evaluate(state)
    used_rules = sorted(
        {
            event["rule_id"]
            for event in evaluator.audit_log
            if event.get("rule_id")
        }
    )

    assert {
        "used_facts": sorted(result.facts),
        "used_rules": used_rules,
        "claims": {
            claim_id: claim.get_trust_label()
            for claim_id, claim in sorted(result.claims.items())
        },
        "blocked_claims": sorted(result.blocked_claims),
    } == {
        "used_facts": ["exception_fact", "trigger"],
        "used_rules": [
            "R_EXCEPTION",
            "R_GENERAL",
            "R_OBLIGATION",
            "R_PERMISSION",
            "R_PROHIBITION",
        ],
        "claims": {
            "exception_result": "ENGINEERING_BASELINE",
            "may_act": "UNVERIFIED",
            "must_act": "ENGINEERING_BASELINE",
        },
        "blocked_claims": ["forbidden_act"],
    }


def test_v2_obligation_exception_attack_shadow_baselines_are_frozen():
    """冻结 obligation 成立及 exception attack 推翻结论的 shadow 差分字段。"""

    assert _shadow_snapshot(_build_contract_fixture(False)) == {
        "used_facts": ["contract_exists", "delivery_due", "goods_not_delivered"],
        "used_rules": ["rule::delivery_obligation", "rule::failed_delivery"],
        "claims": {
            "closure": ["delivery_breach", "norm::delivery::active"],
            "accepted": ["delivery_breach", "norm::delivery::active"],
            "rejected": [],
            "undecided": [],
        },
        "attack_edges": [],
        "priority_result": {"applied": False},
        "checker_verdict": {"accepted": True},
        "result_status": "PROVED",
    }
    assert _shadow_snapshot(_build_contract_fixture(True)) == {
        "used_facts": [
            "contract_exists",
            "delivery_due",
            "goods_not_delivered",
            "force_majeure",
        ],
        "used_rules": ["rule::delivery_obligation", "rule::failed_delivery"],
        "claims": {
            "closure": ["delivery_breach", "force_majeure", "norm::delivery::active"],
            "accepted": ["force_majeure", "norm::delivery::active"],
            "rejected": ["delivery_breach"],
            "undecided": [],
        },
        "attack_edges": ["force_majeure->delivery_breach:EXCEPTION"],
        "priority_result": {"applied": False},
        "checker_verdict": {"accepted": True},
        "result_status": "REFUTED",
    }


def test_v2_permission_prohibition_priority_shadow_baseline_is_frozen():
    """冻结 permission 对 prohibition 的 priority defeat 及 checker verdict。"""

    assert _shadow_snapshot(_build_license_fixture(True)) == {
        "used_facts": [
            "license_signed",
            "rights_holder_authorized",
            "used_work",
            "use_within_scope",
        ],
        "used_rules": [
            "rule::license_status",
            "rule::licensed_use_permission",
            "rule::used_work",
        ],
        "claims": {
            "closure": [
                "license_status_active",
                "norm::unauthorized_use_prohibition::active",
                "unauthorized_use",
                "use_permitted",
            ],
            "accepted": [
                "license_status_active",
                "norm::unauthorized_use_prohibition::active",
                "use_permitted",
            ],
            "rejected": ["unauthorized_use"],
            "undecided": [],
        },
        "attack_edges": ["use_permitted->unauthorized_use:PRIORITY_DEFEAT"],
        "priority_result": {"applied": True},
        "checker_verdict": {"accepted": True},
        "result_status": "PROVED",
    }


def test_v2_conflict_is_not_auto_resolved_and_checker_accepts_it():
    """冻结双向攻击冲突：grounded 保持 UNDEC，边界层不得用 priority 自动消解。"""

    claims = [{"id": "claim::A"}, {"id": "claim::B"}]
    attacks = [("claim::A", "claim::B"), ("claim::B", "claim::A")]
    grounded = grounded_extension(claims, attacks)
    checker = check_grounded(serialize_aaf(claims, attacks), _labels(grounded), THEOREM_REFS)
    boundary = classify_boundary_result(
        [
            FactTrustEnvelope(
                fact_key="fact::conflict",
                value=True,
                status=FactTrustStatus.VERIFIED_FACT,
                source_ids=("snapshot::semantic-baseline",),
            )
        ],
        used_rule_ids=("rule::A", "rule::B"),
        conflict_nodes=("claim::A", "claim::B"),
    )

    assert {
        "used_facts": list(boundary.used_fact_keys),
        "used_rules": list(boundary.used_rule_ids),
        "claims": _labels(grounded),
        "attack_edges": attacks,
        "priority_result": {"auto_resolved": boundary.payload["auto_resolved"]},
        "checker_verdict": {"accepted": checker["valid"]},
        "result_status": boundary.result_status.value,
    } == {
        "used_facts": ["fact::conflict"],
        "used_rules": ["rule::A", "rule::B"],
        "claims": {"claim::A": "UNDEC", "claim::B": "UNDEC"},
        "attack_edges": [("claim::A", "claim::B"), ("claim::B", "claim::A")],
        "priority_result": {"auto_resolved": False},
        "checker_verdict": {"accepted": True},
        "result_status": BoundaryResultStatus.CONFLICT_CERTIFICATE.value,
    }


def test_v2_truncation_is_explicit_and_checker_rejects_partial_labels():
    """冻结 fail-closed 截断：未收敛标签不得被独立 checker 接受。"""

    claims = [{"id": claim_id} for claim_id in ("A", "B", "C", "D")]
    attacks = [("A", "B"), ("B", "C"), ("C", "D")]
    grounded = grounded_extension(claims, attacks, max_iter=1)
    checker = check_grounded(serialize_aaf(claims, attacks), _labels(grounded), THEOREM_REFS)

    assert {
        "used_facts": [],
        "used_rules": [],
        "claims": _labels(grounded),
        "attack_edges": attacks,
        "priority_result": {"applied": False},
        "checker_verdict": {"accepted": checker["valid"]},
        "result_status": {
            "convergent": grounded["convergent"],
            "truncated": grounded["truncated"],
        },
    } == {
        "used_facts": [],
        "used_rules": [],
        "claims": {"A": "IN", "B": "OUT", "C": "UNDEC", "D": "UNDEC"},
        "attack_edges": [("A", "B"), ("B", "C"), ("C", "D")],
        "priority_result": {"applied": False},
        "checker_verdict": {"accepted": False},
        "result_status": {"convergent": False, "truncated": True},
    }
