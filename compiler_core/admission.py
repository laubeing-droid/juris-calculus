"""JC W9：RuleAdmission 独立准入。

依据：任务书 W9。JC 独立拥有准入终态；RuleAdmissionRequest 只接受
LCCC SnapshotVerificationReceipt、快照成员 locator 与 LegalOS FactApprovalRef；
不读取 LCCC/LegalOS 数据库（请求即自包含证据）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from compiler_core.jcs import jcs_digest

ADMISSION_STATUS = ("admitted", "rejected", "pending_review")


@dataclass(frozen=True)
class AdmissionOutcome:
    """JC 独立准入结果（不可变）。"""

    admission_id: str
    request_id: str
    status: str
    produced_by: str = "jc"
    produced_at: str = ""
    rejection_reason: str | None = None
    result_digest: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {
            "admission_id": self.admission_id,
            "request_id": self.request_id,
            "status": self.status,
            "produced_by": self.produced_by,
            "produced_at": self.produced_at,
            "rejection_reason": self.rejection_reason,
            "result_digest": self.result_digest,
        }


def _require_fields(payload: Mapping[str, Any], fields: tuple[str, ...]) -> None:
    for f in fields:
        if not payload.get(f):
            raise ValueError(f"admission_missing_field:{f}")


def _require_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or not all(c in "0123456789abcdef" for c in value):
        raise ValueError(f"admission_invalid_digest:{field}")


def admit_rule(request: Mapping[str, Any]) -> AdmissionOutcome:
    """独立准入 RuleAdmissionRequest。

    校验（自包含，不读外部数据库）：
    1. request_id / fact_approval_ref.ref_id / locator 必填；
    2. snapshot_verification_receipt.result 必须 verified；
    3. fact_approval_ref 必须含 evidence_anchor_refs（证据锚定事实）；
    4. locator.digest 必须是 sha256；
    任一不满足 → rejected（附原因）。
    """
    _require_fields(request, ("request_id", "snapshot_verification_receipt", "fact_approval_ref", "locator"))

    receipt = request["snapshot_verification_receipt"]
    fact_ref = request["fact_approval_ref"]
    locator = request["locator"]

    reason: str | None = None
    if not isinstance(receipt, Mapping) or receipt.get("result") != "verified":
        reason = "snapshot_not_verified"
    elif not isinstance(fact_ref, Mapping) or not fact_ref.get("ref_id"):
        reason = "fact_approval_ref_missing"
    elif not isinstance(fact_ref.get("evidence_anchor_refs"), list) or not fact_ref["evidence_anchor_refs"]:
        reason = "fact_not_evidence_anchored"
    elif not isinstance(locator, Mapping) or not locator.get("digest"):
        reason = "locator_digest_missing"
    else:
        digest = str(locator["digest"]).removeprefix("sha256-")
        try:
            _require_sha256(digest, "locator.digest")
        except ValueError:
            reason = "locator_digest_invalid"

    status = "rejected" if reason else "admitted"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    outcome = AdmissionOutcome(
        admission_id=f"adm-{request.get('request_id', 'unknown')}",
        request_id=str(request.get("request_id", "")),
        status=status,
        produced_at=now,
        rejection_reason=reason,
    )
    digest = jcs_digest(outcome.public_dict())
    return AdmissionOutcome(
        admission_id=outcome.admission_id,
        request_id=outcome.request_id,
        status=outcome.status,
        produced_at=outcome.produced_at,
        rejection_reason=outcome.rejection_reason,
        result_digest=digest,
    )
