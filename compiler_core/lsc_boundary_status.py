"""迁移期边界结果适配；权威状态和准入来自v3 contracts与LegalFact。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from compiler_core.contracts import CertificateKind, ResultStatus
from compiler_core.types import FactTrustStatus, LegalFact


BoundaryResultStatus = ResultStatus


@dataclass(frozen=True)
class BoundaryResult:
    """旧调用者使用的机器packet；不得作为CanonicalResult的第二套定义。"""

    result_status: ResultStatus
    used_fact_keys: tuple[str, ...] = field(default_factory=tuple)
    used_rule_ids: tuple[str, ...] = field(default_factory=tuple)
    source_snapshot_ids: tuple[str, ...] = field(default_factory=tuple)
    provenance: dict[str, Any] = field(default_factory=dict)
    taint: tuple[str, ...] = field(default_factory=tuple)
    review_required: bool = False
    formal_kernel_used: bool = False
    renderer_output_kind: str = "machine_packet"
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回新的JSON-ready packet并保留旧审计字段。"""

        return {
            "result_status": self.result_status.value,
            "used_fact_keys": list(self.used_fact_keys),
            "used_rule_ids": list(self.used_rule_ids),
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "provenance": dict(self.provenance),
            "taint": list(self.taint),
            "review_required": self.review_required,
            "formal_kernel_used": self.formal_kernel_used,
            "renderer_output_kind": self.renderer_output_kind,
            "payload": dict(self.payload),
        }


def classify_boundary_result(
    used_facts: Iterable[LegalFact],
    *,
    used_rule_ids: Iterable[str] = (),
    source_snapshot_ids: Iterable[str] = (),
    conflict_nodes: Iterable[str] = (),
    engine_error: str | None = None,
    checker_accepted: bool = False,
    certificate_kind: CertificateKind | str = CertificateKind.NONE,
    formal_kernel_used: bool = False,
) -> BoundaryResult:
    """按唯一事实准入和显式checker证据分类；任何缺省组合均fail closed。"""

    facts = tuple(used_facts)
    used_fact_keys = tuple(sorted(fact.id for fact in facts))
    taint = _taint_from_facts(facts)
    provenance = {
        "summary_only": True,
        "fact_count": len(facts),
        "source_ids": sorted({source_id for fact in facts for source_id in fact.source_ids}),
    }
    common = {
        "used_fact_keys": used_fact_keys,
        "used_rule_ids": tuple(sorted({str(item) for item in used_rule_ids})),
        "source_snapshot_ids": tuple(sorted({str(item) for item in source_snapshot_ids})),
        "provenance": provenance,
        "taint": taint,
    }
    try:
        certificate = certificate_kind if isinstance(certificate_kind, CertificateKind) else CertificateKind(certificate_kind)
    except ValueError:
        certificate = CertificateKind.NONE
    if engine_error:
        return BoundaryResult(
            ResultStatus.ENGINE_ERROR,
            review_required=True,
            payload={"error": engine_error},
            **common,
        )
    conflict_tuple = tuple(sorted({str(item) for item in conflict_nodes}))
    if conflict_tuple:
        return BoundaryResult(
            ResultStatus.CONFLICT_CERTIFICATE,
            review_required=True,
            payload={"conflict_nodes": list(conflict_tuple), "auto_resolved": False},
            **common,
        )
    if any(fact.status == FactTrustStatus.UNKNOWN for fact in facts):
        missing = sorted(fact.id for fact in facts if fact.status == FactTrustStatus.UNKNOWN)
        return BoundaryResult(
            ResultStatus.MISSING_REQUIRED_FACT,
            review_required=True,
            payload={"missing_fact_keys": missing},
            **common,
        )
    if any(fact.status == FactTrustStatus.DISPUTED for fact in facts):
        return BoundaryResult(
            ResultStatus.REVIEW_ONLY_RESULT,
            review_required=True,
            payload={"alternative_paths": _alternatives(facts)},
            **common,
        )
    if "assumption" in taint:
        return BoundaryResult(
            ResultStatus.HYPOTHETICAL_RESULT,
            review_required=True,
            formal_kernel_used=formal_kernel_used,
            payload={"hypothetical": True},
            **common,
        )
    inadmissible = sorted(fact.id for fact in facts if not fact.can_enter_formal_kernel())
    if inadmissible:
        return BoundaryResult(
            ResultStatus.REVIEW_ONLY_RESULT,
            review_required=True,
            formal_kernel_used=formal_kernel_used,
            payload={"inadmissible_fact_keys": inadmissible},
            **common,
        )
    if not facts or not checker_accepted or certificate != CertificateKind.FORMAL or not formal_kernel_used:
        return BoundaryResult(
            ResultStatus.REVIEW_ONLY_RESULT,
            review_required=True,
            formal_kernel_used=formal_kernel_used,
            payload={"formal_acceptance_incomplete": True},
            **common,
        )
    return BoundaryResult(
        ResultStatus.ACCEPTED_FORMAL_RESULT,
        formal_kernel_used=True,
        payload={"checker_accepted": True, "certificate_kind": CertificateKind.FORMAL.value},
        **common,
    )


def ensure_required_audit_fields(result: Mapping[str, Any]) -> bool:
    """检查迁移期packet是否暴露全部审计字段。"""

    required = {
        "result_status",
        "used_fact_keys",
        "used_rule_ids",
        "source_snapshot_ids",
        "provenance",
        "taint",
        "review_required",
        "formal_kernel_used",
        "renderer_output_kind",
    }
    return required <= set(result)


def _taint_from_facts(facts: Iterable[LegalFact]) -> tuple[str, ...]:
    """汇总实际使用事实的类型化边界污染。"""

    labels: set[str] = set()
    for fact in facts:
        if fact.status == FactTrustStatus.USER_ASSUMED:
            labels.add("assumption")
        if fact.status == FactTrustStatus.DISPUTED:
            labels.add("disputed")
        if fact.status == FactTrustStatus.UNKNOWN:
            labels.add("unknown")
        derived = (fact.provenance.get("derived_from") or {}) if isinstance(fact.provenance, Mapping) else {}
        upstream_taint = str(derived.get("provenance_taint") or "")
        if upstream_taint == "HYPOTHETICAL_RESULT":
            labels.add("assumption")
        if upstream_taint == "DETERMINISTIC_CONDITIONAL":
            labels.add("conditional")
    return tuple(sorted(labels))


def _alternatives(facts: Iterable[LegalFact]) -> list[dict[str, Any]]:
    """按事实键稳定输出争议分支，不修改LegalFact中的候选值。"""

    paths = [
        {"fact_key": fact.id, "alternatives": [dict(item) for item in fact.alternatives]}
        for fact in facts
        if fact.status == FactTrustStatus.DISPUTED
    ]
    return sorted(paths, key=lambda item: item["fact_key"])
