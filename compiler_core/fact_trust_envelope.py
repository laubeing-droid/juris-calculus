"""旧FactCoordinate payload到唯一LegalFact对象的保守转换。"""

from __future__ import annotations

from typing import Any, Mapping

from compiler_core.types import FactCreator, FactTrustStatus, LegalFact


LSC_STATUS_MAP = {
    "ADMITTED": FactTrustStatus.CHECKED_FACT,
    "HUMAN_REVIEWED": FactTrustStatus.CHECKED_FACT,
    "VERIFIED": FactTrustStatus.VERIFIED_FACT,
    "COURT_FIXED": FactTrustStatus.VERIFIED_FACT,
    "USER_ASSUMED": FactTrustStatus.USER_ASSUMED,
    "DISPUTED": FactTrustStatus.DISPUTED,
    "UNKNOWN": FactTrustStatus.UNKNOWN,
    "ENGINE_DERIVED": FactTrustStatus.CHECKED_FACT,
}


def FactTrustEnvelope(
    fact_key: str,
    value: Any = None,
    status: FactTrustStatus = FactTrustStatus.CANDIDATE_FACT,
    source_ids: tuple[str, ...] = (),
    alternatives: tuple[dict[str, Any], ...] = (),
    provenance: Mapping[str, Any] | None = None,
    human_reviewed: bool = False,
    created_by: FactCreator = FactCreator.SYSTEM,
) -> LegalFact:
    """迁移期工厂：接受旧构造签名，但只创建LegalFact，不保留平行业务对象。"""

    return LegalFact(
        id=fact_key,
        description="" if value is None else str(value),
        value=value,
        status=status,
        source_ids=source_ids,
        alternatives=alternatives,
        provenance=dict(provenance or {}),
        human_reviewed=human_reviewed,
        created_by=created_by,
    )


def from_lsc_fact_coordinate(payload: Mapping[str, Any]) -> LegalFact:
    """把旧FactCoordinate形payload保守转换为LegalFact，不推断或晋升事实。"""

    raw_state = str(payload.get("determination_state") or payload.get("truth_status") or "")
    status = LSC_STATUS_MAP.get(raw_state, FactTrustStatus.CANDIDATE_FACT)
    provenance = dict(payload.get("provenance") or {})
    return LegalFact(
        id=str(payload.get("fact_key") or ""),
        description=str(payload.get("description") or ""),
        value=payload.get("value"),
        status=status,
        source_ids=tuple(_source_ids(provenance)),
        alternatives=tuple(dict(item) for item in payload.get("alternatives") or ()),
        provenance=provenance,
        human_reviewed=bool(payload.get("human_reviewed") or raw_state == "HUMAN_REVIEWED"),
        created_by=_creator_from_payload(raw_state, provenance),
        reasoning_tier=str(payload.get("reasoning_tier") or "P0"),
    )


def can_enter_formal_kernel(fact: LegalFact) -> bool:
    """兼容函数只委托LegalFact的唯一准入逻辑。"""

    return fact.can_enter_formal_kernel()


def _creator_from_payload(raw_state: str, provenance: Mapping[str, Any]) -> FactCreator:
    """从显式创建者字段解析来源；未知值降为system，不作事实晋升。"""

    created_by = str(provenance.get("created_by") or provenance.get("source_agent") or "").lower()
    if raw_state == "COURT_FIXED" or created_by == "court":
        return FactCreator.COURT
    if created_by in {item.value for item in FactCreator}:
        return FactCreator(created_by)
    if raw_state in {"ADMITTED", "HUMAN_REVIEWED"}:
        return FactCreator.HUMAN
    return FactCreator.SYSTEM


def _source_ids(provenance: Mapping[str, Any]) -> list[str]:
    """只复制payload中已有的结构化来源ID，不从说明文字猜测。"""

    values: list[str] = []
    for key in ("source_id", "source_ref", "source_document_id"):
        value = provenance.get(key)
        if value:
            values.append(str(value))
    return values


__all__ = [
    "FactCreator",
    "FactTrustEnvelope",
    "FactTrustStatus",
    "LSC_STATUS_MAP",
    "can_enter_formal_kernel",
    "from_lsc_fact_coordinate",
]
