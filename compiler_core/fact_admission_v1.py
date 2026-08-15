"""W3：P09 正式事实准入——三门分离与 FactAdmissionAttestationV1。

依据：20260815 施工方案 §9。规则：

1. `source_gate` / `interpretation_gate` / `fact_gate` 三门分别取
   PASS、FAIL、BLOCKED、DISPUTED；不得相互代替。
2. `admission.py`（v3 规则准入）与本模块职责分离：本模块是 v4 事实
   attestation 验证 authority；外部输入、Agent、Deli 和兼容 adapter
   只能提交 candidate，不能自签 attestation。
3. UNKNOWN、DISPUTED、USER_ASSUMED 可进入审查图，但不能创建 formal
   certificate。
4. attestation 对 exact proposition 和 exact source bytes 绑定；
   改一字即失效。
5. 撤销、过期、跨案复用、权限不足、部分证据缺失必须有拒绝事件。
6. 人工批准来自 Legal Harness 的 versioned receipt；JC 只验证格式、
   权限、绑定和状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Any, Mapping

from compiler_core.source_service_v2 import GateOutcome


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CANONICAL_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

ADMISSION_BASES = (
    "documentary_evidence_human_reviewed",
    "judicial_notice",
    "admitted_by_opponent",
    "presumption_of_law",
)
ISSUER_ROLES = ("legal_harness_approver", "court_of_record")
DISPUTE_STATES = ("undisputed", "DISPUTED", "UNKNOWN", "USER_ASSUMED")
ATTESTATION_KIND = "FactAdmissionAttestationV1"


class FactAdmissionError(ValueError):
    """事实准入门验证失败；code 稳定可机读。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_proposition_hash(proposition: str) -> str:
    """canonical fact proposition hash：exact bytes 绑定基础。"""

    if not isinstance(proposition, str) or not proposition.strip():
        raise FactAdmissionError("MISSING_REQUIRED_FIELD", "proposition")
    return "sha256:" + hashlib.sha256(proposition.encode("utf-8")).hexdigest()


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise FactAdmissionError("INVALID_DIGEST", name)
    return value


def _require_nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FactAdmissionError("MISSING_REQUIRED_FIELD", name)
    return value


def _require_canonical_time(value: Any, name: str, *, optional: bool = False) -> str:
    if optional and (value is None or value == ""):
        return ""
    if not isinstance(value, str) or not _CANONICAL_TIME_RE.match(value):
        raise FactAdmissionError("NONCANONICAL_TIME", f"{name}={value!r}")
    return value


@dataclass(frozen=True)
class ScopedRef:
    """带 hash 绑定的引用。"""

    ref: str
    hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", _require_nonempty(self.ref, "ref"))
        object.__setattr__(self, "hash", _require_sha256(self.hash, "ref.hash"))

    def to_dict(self) -> dict[str, Any]:
        return {"ref": self.ref, "hash": self.hash}

    @classmethod
    def from_dict(cls, payload: Any, scope: str) -> "ScopedRef":
        if not isinstance(payload, Mapping):
            raise FactAdmissionError("MISSING_REQUIRED_FIELD", scope)
        unknown = sorted(set(payload) - {"ref", "hash"})
        if unknown:
            raise FactAdmissionError("UNKNOWN_FIELD", f"{scope}: {', '.join(unknown)}")
        return cls(ref=payload.get("ref"), hash=payload.get("hash"))


@dataclass(frozen=True)
class FactAdmissionAttestationV1:
    """正式事实准入凭据（方案 §9 最少绑定集）。"""

    attestation_id: str
    kind: str
    proposition_hash: str
    source_refs: tuple[ScopedRef, ...]
    evidence_refs: tuple[ScopedRef, ...]
    interpretation_version: str
    admission_basis: str
    issuer_role: str
    issuer_scope_case: str
    issuer_scope_run: str
    issued_at: str
    dispute_state: str
    assumption_state: str
    signature_or_approval_receipt_ref: str
    expires_at: str = ""
    revocation_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "attestation_id", _require_nonempty(self.attestation_id, "attestation_id"))
        if self.kind != ATTESTATION_KIND:
            raise FactAdmissionError("INVALID_ENUM", f"kind={self.kind!r}")
        object.__setattr__(self, "proposition_hash", _require_sha256(self.proposition_hash, "proposition_hash"))
        object.__setattr__(self, "interpretation_version", _require_nonempty(self.interpretation_version, "interpretation_version"))
        if self.admission_basis not in ADMISSION_BASES:
            raise FactAdmissionError("INVALID_ENUM", f"admission_basis={self.admission_basis!r}")
        if self.issuer_role not in ISSUER_ROLES:
            raise FactAdmissionError("ISSUER_ROLE_NOT_AUTHORIZED", self.issuer_role)
        object.__setattr__(self, "issuer_scope_case", _require_nonempty(self.issuer_scope_case, "issuer_scope.case_ref"))
        object.__setattr__(self, "issuer_scope_run", _require_nonempty(self.issuer_scope_run, "issuer_scope.run_ref"))
        object.__setattr__(self, "issued_at", _require_canonical_time(self.issued_at, "issued_at"))
        object.__setattr__(self, "expires_at", _require_canonical_time(self.expires_at, "expires_at", optional=True))
        if self.dispute_state not in DISPUTE_STATES:
            raise FactAdmissionError("INVALID_ENUM", f"dispute_state={self.dispute_state!r}")
        object.__setattr__(self, "assumption_state", _require_nonempty(self.assumption_state, "assumption_state"))
        object.__setattr__(self, "signature_or_approval_receipt_ref",
                           _require_nonempty(self.signature_or_approval_receipt_ref, "signature_or_approval_receipt_ref"))
        if not self.source_refs or not self.evidence_refs:
            raise FactAdmissionError("EVIDENCE_MISSING", "source_refs/evidence_refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "attestation_id": self.attestation_id,
            "kind": self.kind,
            "proposition_hash": self.proposition_hash,
            "source_refs": [item.to_dict() for item in self.source_refs],
            "evidence_refs": [item.to_dict() for item in self.evidence_refs],
            "interpretation_version": self.interpretation_version,
            "admission_basis": self.admission_basis,
            "issuer_role": self.issuer_role,
            "issuer_scope": {"case_ref": self.issuer_scope_case, "run_ref": self.issuer_scope_run},
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "dispute_state": self.dispute_state,
            "assumption_state": self.assumption_state,
            "revocation_ref": self.revocation_ref,
            "signature_or_approval_receipt_ref": self.signature_or_approval_receipt_ref,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FactAdmissionAttestationV1":
        if not isinstance(payload, Mapping):
            raise FactAdmissionError("MISSING_REQUIRED_FIELD", "attestation")
        allowed = {
            "attestation_id", "kind", "proposition_hash", "source_refs", "evidence_refs",
            "interpretation_version", "admission_basis", "issuer_role", "issuer_scope",
            "issued_at", "expires_at", "dispute_state", "assumption_state",
            "revocation_ref", "signature_or_approval_receipt_ref",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise FactAdmissionError("UNKNOWN_FIELD", ", ".join(unknown))
        required = allowed - {"expires_at", "revocation_ref"}
        missing = sorted(required - set(payload))
        if missing:
            raise FactAdmissionError("MISSING_REQUIRED_FIELD", ", ".join(missing))
        scope = payload["issuer_scope"]
        if not isinstance(scope, Mapping):
            raise FactAdmissionError("MISSING_REQUIRED_FIELD", "issuer_scope")
        return cls(
            attestation_id=payload["attestation_id"],
            kind=payload["kind"],
            proposition_hash=payload["proposition_hash"],
            source_refs=tuple(ScopedRef.from_dict(item, "source_refs") for item in payload["source_refs"]),
            evidence_refs=tuple(ScopedRef.from_dict(item, "evidence_refs") for item in payload["evidence_refs"]),
            interpretation_version=payload["interpretation_version"],
            admission_basis=payload["admission_basis"],
            issuer_role=payload["issuer_role"],
            issuer_scope_case=scope.get("case_ref"),
            issuer_scope_run=scope.get("run_ref"),
            issued_at=payload["issued_at"],
            expires_at=payload.get("expires_at") or "",
            dispute_state=payload["dispute_state"],
            assumption_state=payload["assumption_state"],
            revocation_ref=str(payload.get("revocation_ref") or ""),
            signature_or_approval_receipt_ref=payload["signature_or_approval_receipt_ref"],
        )


@dataclass(frozen=True)
class FactCandidate:
    """外部候选事实；任何入口只能提交 candidate，不得自签 attestation。"""

    proposition: str
    producer_kind: str
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    self_attestation: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "proposition", _require_nonempty(self.proposition, "proposition"))
        if self.producer_kind not in ("agent", "extraction", "lawyer", "system"):
            raise FactAdmissionError("INVALID_ENUM", f"producer_kind={self.producer_kind!r}")

    @property
    def proposition_hash(self) -> str:
        return canonical_proposition_hash(self.proposition)


class FactAdmissionService:
    """三门分离验证；任一门通过不得替代其他门。"""

    def __init__(self) -> None:
        self._attestations: dict[str, FactAdmissionAttestationV1] = {}
        self._consumed_scopes: set[tuple[str, str, str]] = set()
        self._rejection_events: list[dict[str, Any]] = []

    @property
    def rejection_events(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._rejection_events)

    def register_attestation(self, attestation: FactAdmissionAttestationV1) -> None:
        self._attestations[attestation.attestation_id] = attestation

    def _reject(self, gate: str, reason: str, details: Mapping[str, Any]) -> GateOutcome:
        self._rejection_events.append({"gate": gate, "reason": reason, "details": dict(details)})
        return GateOutcome(gate, "FAIL", reason, details)

    def interpretation_gate(self, *, interpretation_version: str, disputed: bool) -> GateOutcome:
        """从材料到命题的解释门；争议状态显式化。"""

        if not interpretation_version or not interpretation_version.strip():
            return GateOutcome("interpretation_gate", "BLOCKED", "interpretation_version_missing")
        if disputed:
            return GateOutcome("interpretation_gate", "DISPUTED", "interpretation_disputed")
        return GateOutcome("interpretation_gate", "PASS")

    def fact_gate(
        self,
        *,
        proposition: str,
        attestation_ref: str | None,
        case_ref: str,
        run_ref: str,
        now: str,
    ) -> GateOutcome:
        """命题是否达到该运行所需准入等级。"""

        if not attestation_ref:
            return GateOutcome("fact_gate", "BLOCKED", "attestation_absent_or_disputed")
        attestation = self._attestations.get(attestation_ref)
        if attestation is None:
            return self._reject("fact_gate", "attestation_unregistered", {"attestation_ref": attestation_ref})

        presented_hash = canonical_proposition_hash(proposition)
        if presented_hash != attestation.proposition_hash:
            return self._reject(
                "fact_gate", "attestation_binding_broken",
                {"attestation_ref": attestation_ref, "presented_hash": presented_hash},
            )
        if attestation.issuer_scope_case != case_ref or attestation.issuer_scope_run != run_ref:
            return self._reject(
                "fact_gate", "attestation_scope_mismatch",
                {"attestation_ref": attestation_ref, "case_ref": case_ref, "run_ref": run_ref},
            )
        scope_key = (attestation.attestation_id, case_ref, run_ref)
        if scope_key in self._consumed_scopes:
            return self._reject("fact_gate", "attestation_replayed", {"attestation_ref": attestation_ref})
        if attestation.revocation_ref:
            return self._reject("fact_gate", "attestation_revoked", {"revocation_ref": attestation.revocation_ref})
        if attestation.expires_at and now >= attestation.expires_at:
            return self._reject("fact_gate", "attestation_expired", {"expires_at": attestation.expires_at})
        if now < attestation.issued_at:
            return self._reject("fact_gate", "attestation_not_yet_valid", {"issued_at": attestation.issued_at})
        if attestation.dispute_state in ("DISPUTED", "UNKNOWN", "USER_ASSUMED"):
            return GateOutcome(
                "fact_gate", "DISPUTED", "attestation_disputed",
                {"dispute_state": attestation.dispute_state},
            )
        self._consumed_scopes.add(scope_key)
        return GateOutcome("fact_gate", "PASS", details={"attestation_ref": attestation_ref})

    def admit_fact(
        self,
        *,
        candidate: FactCandidate,
        attestation_ref: str | None,
        source_outcome: GateOutcome,
        interpretation_outcome: GateOutcome,
        case_ref: str,
        run_ref: str,
        now: str,
    ) -> dict[str, Any]:
        """三门联合裁决；三门状态分别记录，任一 FAIL/BLOCKED 不得准入。

        DISPUTED 事实进入审查图（admitted=False, review_only=True），
        但永远不创建 formal premise/certificate。
        """

        if candidate.self_attestation is not None:
            self._rejection_events.append({
                "gate": "quarantine",
                "reason": "agent_cannot_self_attest",
                "details": {"proposition_hash": candidate.proposition_hash},
            })
            return {
                "admitted": False,
                "review_only": False,
                "proposition_hash": candidate.proposition_hash,
                "gates": {"quarantine": "FAIL"},
                "reason": "agent_cannot_self_attest",
            }

        fact_outcome = self.fact_gate(
            proposition=candidate.proposition,
            attestation_ref=attestation_ref,
            case_ref=case_ref,
            run_ref=run_ref,
            now=now,
        )
        gates = {
            "source_gate": source_outcome.status,
            "interpretation_gate": interpretation_outcome.status,
            "fact_gate": fact_outcome.status,
        }
        statuses = set(gates.values())
        admitted = statuses == {"PASS"}
        review_only = (not admitted) and "FAIL" not in statuses and "BLOCKED" not in statuses
        return {
            "admitted": admitted,
            "review_only": review_only,
            "proposition_hash": candidate.proposition_hash,
            "gates": gates,
            "reason": fact_outcome.reason or interpretation_outcome.reason or source_outcome.reason,
        }
