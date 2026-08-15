"""JC v4 中立合同（W1）。

依据：20260815 施工方案 §7。本模块是 v4 唯一 Python authority；
`schemas/jc-v4.schema.json` 是唯一 JSON authority；二者字段一一对应，
round-trip 测试强制一致。

设计约束：
- 纯 dataclass/typed，不依赖 v3 contracts、不依赖 evaluator 状态；
- 未知字段、重复 ID、非规范时间、浮点金额、绝对机器路径、未声明扩展一律 fail closed；
- canonical 序列化使用 RFC 8785 JCS（compiler_core.jcs），保证字节级确定性；
- 外部输入不能自报 verified 事实准入；事实只能以 attestation refs 引入（W3 门禁消费）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any, Mapping

from compiler_core.jcs import jcs, jcs_digest


SCHEMA_VERSION_V4 = "jc/4.0"

REQUESTED_OUTPUTS = (
    "semantic_result",
    "checker_receipt",
    "solver_receipt",
    "translation_receipt",
    "certificate",
    "audit_bundle",
    "replay",
)

_DECISION_STATUSES = (
    "accepted_formal_result",
    "hypothetical_result",
    "review_only_result",
    "missing_required_fact",
    "conflict_certificate",
    "blocked",
    "unknown",
    "engine_error",
)

_COMPLETENESS_STATES = ("complete", "partial", "truncated", "interrupted")

_ERROR_CODE_PREFIXES = (
    "UNSUPPORTED_SCHEMA_VERSION",
    "ENGINE_VERSION_MISMATCH",
    "MISSING_REQUIRED_FIELD",
    "UNKNOWN_FIELD",
    "DUPLICATE_ID",
    "NONCANONICAL_TIME",
    "FLOAT_MONEY_FORBIDDEN",
    "ABSOLUTE_MACHINE_PATH",
    "UNDECLARED_EXTENSION",
    "INVALID_DIGEST",
    "INVALID_ENUM",
    "INVALID_LIMIT",
)

# RFC3339 UTC 规范形式：2026-08-16T00:00:00Z（允许小数秒）。
_CANONICAL_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
_DIGEST_RE = re.compile(r"^(sha256:)?[0-9a-f]{64}$")
_ABSOLUTE_PATH_RE = re.compile(r"^([A-Za-z]:[\\/]|\\\\|/)")

_ENGINE_LIMITS_V4 = {
    "max_fact_attestation_refs": 512,
    "max_proposal_refs": 512,
    "max_requested_outputs": len(REQUESTED_OUTPUTS),
}


class ContractV4Error(ValueError):
    """v4 合同验证失败；code 稳定映射到 CLI 输入错误。"""

    def __init__(self, code: str, message: str) -> None:
        if code not in _ERROR_CODE_PREFIXES:
            raise ValueError(f"unknown contract error code: {code}")
        super().__init__(message)
        self.code = code


def _require_nonempty_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractV4Error("MISSING_REQUIRED_FIELD", name)
    if _ABSOLUTE_PATH_RE.match(value):
        raise ContractV4Error("ABSOLUTE_MACHINE_PATH", f"{name}={value!r}")
    return value


def _require_canonical_time(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _CANONICAL_TIME_RE.match(value):
        raise ContractV4Error("NONCANONICAL_TIME", f"{name}={value!r}")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractV4Error("NONCANONICAL_TIME", f"{name}={value!r}") from exc
    return value


def _require_digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise ContractV4Error("INVALID_DIGEST", name)
    return value


def _sorted_unique(values: Any, name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise ContractV4Error("INVALID_ENUM", f"{name} must be an array")
    items = []
    for item in values:
        items.append(_require_nonempty_str(item, f"{name}[]"))
    unique = sorted(set(items))
    if len(unique) != len(items):
        raise ContractV4Error("DUPLICATE_ID", name)
    return tuple(unique)


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], scope: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ContractV4Error("UNKNOWN_FIELD", f"{scope}: {', '.join(unknown)}")


def _reject_float_money(payload: Mapping[str, Any], scope: str) -> None:
    """正式路径禁止 binary float；金额一律最小货币单位整数（§11 动作 2）。"""

    for key, value in payload.items():
        if isinstance(value, float):
            raise ContractV4Error("FLOAT_MONEY_FORBIDDEN", f"{scope}.{key}")
        if isinstance(value, Mapping):
            _reject_float_money(value, f"{scope}.{key}")


@dataclass(frozen=True)
class LegalContextV4:
    """中立法律语境；不含外仓产品命名。"""

    jurisdiction: str
    governing_law: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "jurisdiction", _require_nonempty_str(self.jurisdiction, "legal_context.jurisdiction"))
        object.__setattr__(self, "governing_law", _require_nonempty_str(self.governing_law, "legal_context.governing_law"))

    def to_dict(self) -> dict[str, Any]:
        return {"jurisdiction": self.jurisdiction, "governing_law": self.governing_law}

    @classmethod
    def from_dict(cls, payload: Any) -> "LegalContextV4":
        if not isinstance(payload, Mapping):
            raise ContractV4Error("MISSING_REQUIRED_FIELD", "legal_context")
        _reject_unknown(payload, {"jurisdiction", "governing_law"}, "legal_context")
        return cls(jurisdiction=payload.get("jurisdiction"), governing_law=payload.get("governing_law"))


@dataclass(frozen=True)
class RulePackRefV4:
    """规则包三元组引用；digest 必须 sha256。"""

    pack_id: str
    version: str
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "pack_id", _require_nonempty_str(self.pack_id, "rule_pack_ref.pack_id"))
        object.__setattr__(self, "version", _require_nonempty_str(self.version, "rule_pack_ref.version"))
        object.__setattr__(self, "digest", _require_digest(self.digest, "rule_pack_ref.digest"))

    def to_dict(self) -> dict[str, Any]:
        return {"pack_id": self.pack_id, "version": self.version, "digest": self.digest}

    @classmethod
    def from_dict(cls, payload: Any) -> "RulePackRefV4":
        if not isinstance(payload, Mapping):
            raise ContractV4Error("MISSING_REQUIRED_FIELD", "rule_pack_ref")
        _reject_unknown(payload, {"pack_id", "version", "digest"}, "rule_pack_ref")
        return cls(
            pack_id=payload.get("pack_id"),
            version=payload.get("version"),
            digest=payload.get("digest"),
        )


@dataclass(frozen=True)
class CaseRequestV4:
    """v4 中立案件请求（方案 §7 最少字段集）。"""

    request_id: str
    schema_version: str
    legal_context: LegalContextV4
    decision_time: str
    source_bundle_ref: str
    evidence_manifest_ref: str
    fact_attestation_refs: tuple[str, ...]
    rule_pack_ref: RulePackRefV4
    requested_outputs: tuple[str, ...]
    proposal_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require_nonempty_str(self.request_id, "request_id"))
        if self.schema_version != SCHEMA_VERSION_V4:
            raise ContractV4Error("UNSUPPORTED_SCHEMA_VERSION", str(self.schema_version))
        object.__setattr__(self, "decision_time", _require_canonical_time(self.decision_time, "decision_time"))
        object.__setattr__(self, "source_bundle_ref", _require_nonempty_str(self.source_bundle_ref, "source_bundle_ref"))
        object.__setattr__(self, "evidence_manifest_ref", _require_nonempty_str(self.evidence_manifest_ref, "evidence_manifest_ref"))
        attestations = _sorted_unique(self.fact_attestation_refs, "fact_attestation_refs")
        if len(attestations) > _ENGINE_LIMITS_V4["max_fact_attestation_refs"]:
            raise ContractV4Error("INVALID_LIMIT", "fact_attestation_refs")
        object.__setattr__(self, "fact_attestation_refs", attestations)
        outputs = _sorted_unique(self.requested_outputs, "requested_outputs")
        if not outputs:
            raise ContractV4Error("MISSING_REQUIRED_FIELD", "requested_outputs")
        unknown_outputs = sorted(set(outputs) - set(REQUESTED_OUTPUTS))
        if unknown_outputs:
            raise ContractV4Error("INVALID_ENUM", f"requested_outputs: {', '.join(unknown_outputs)}")
        object.__setattr__(self, "requested_outputs", outputs)
        proposals = _sorted_unique(self.proposal_refs, "proposal_refs")
        if len(proposals) > _ENGINE_LIMITS_V4["max_proposal_refs"]:
            raise ContractV4Error("INVALID_LIMIT", "proposal_refs")
        object.__setattr__(self, "proposal_refs", proposals)
        if not isinstance(self.legal_context, LegalContextV4):
            object.__setattr__(self, "legal_context", LegalContextV4.from_dict(self.legal_context))
        if not isinstance(self.rule_pack_ref, RulePackRefV4):
            object.__setattr__(self, "rule_pack_ref", RulePackRefV4.from_dict(self.rule_pack_ref))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CaseRequestV4":
        """严格解析公开字典；未知字段与未声明扩展 fail closed。"""

        if not isinstance(payload, Mapping):
            raise ContractV4Error("MISSING_REQUIRED_FIELD", "request")
        allowed = {
            "request_id",
            "schema_version",
            "legal_context",
            "decision_time",
            "source_bundle_ref",
            "evidence_manifest_ref",
            "fact_attestation_refs",
            "rule_pack_ref",
            "requested_outputs",
            "proposal_refs",
        }
        _reject_unknown(payload, allowed, "request")
        _reject_float_money(payload, "request")
        missing = sorted(allowed - {"proposal_refs"} - set(payload))
        if missing:
            raise ContractV4Error("MISSING_REQUIRED_FIELD", ", ".join(missing))
        return cls(
            request_id=payload.get("request_id"),
            schema_version=str(payload.get("schema_version", "")),
            legal_context=payload.get("legal_context"),
            decision_time=payload.get("decision_time"),
            source_bundle_ref=payload.get("source_bundle_ref"),
            evidence_manifest_ref=payload.get("evidence_manifest_ref"),
            fact_attestation_refs=tuple(payload.get("fact_attestation_refs") or ()),
            rule_pack_ref=payload.get("rule_pack_ref"),
            requested_outputs=tuple(payload.get("requested_outputs") or ()),
            proposal_refs=tuple(payload.get("proposal_refs") or ()),
        )

    def to_dict(self) -> dict[str, Any]:
        """规范字典；字段输入顺序不影响输出。"""

        return {
            "request_id": self.request_id,
            "schema_version": self.schema_version,
            "legal_context": self.legal_context.to_dict(),
            "decision_time": self.decision_time,
            "source_bundle_ref": self.source_bundle_ref,
            "evidence_manifest_ref": self.evidence_manifest_ref,
            "fact_attestation_refs": list(self.fact_attestation_refs),
            "rule_pack_ref": self.rule_pack_ref.to_dict(),
            "requested_outputs": list(self.requested_outputs),
            "proposal_refs": list(self.proposal_refs),
        }

    def canonical_bytes(self) -> bytes:
        """JCS 规范字节；三入口 parity 的比较基准。"""

        return jcs(self.to_dict()).encode("utf-8")

    def canonical_digest(self) -> str:
        return jcs_digest(self.to_dict())


@dataclass(frozen=True)
class SemanticResultV4:
    """v4 中立机器结果（方案 §7 最少字段集）。

    收据、argument/attack refs 等在 W4—W8 各波填充；合同字段已冻结，
    后续波次只能填充取值，不得新增权威字段（变更需新版本合同）。
    """

    request_id: str
    schema_version: str
    decision_status: str
    admitted_fact_refs: tuple[str, ...]
    rejected_fact_refs: tuple[str, ...]
    applicable_rule_refs: tuple[str, ...]
    inapplicable_rule_refs: tuple[str, ...]
    argument_refs: tuple[str, ...]
    attack_refs: tuple[str, ...]
    exception_resolution: Mapping[str, Any]
    permission_resolution: Mapping[str, Any]
    priority_resolution: Mapping[str, Any]
    temporal_numeric_result: Mapping[str, Any]
    receipt_refs: tuple[str, ...]
    completeness_state: str
    interruption_state: str
    run_identity: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require_nonempty_str(self.request_id, "request_id"))
        if self.schema_version != SCHEMA_VERSION_V4:
            raise ContractV4Error("UNSUPPORTED_SCHEMA_VERSION", str(self.schema_version))
        if self.decision_status not in _DECISION_STATUSES:
            raise ContractV4Error("INVALID_ENUM", f"decision_status={self.decision_status!r}")
        if self.completeness_state not in _COMPLETENESS_STATES:
            raise ContractV4Error("INVALID_ENUM", f"completeness_state={self.completeness_state!r}")
        if not isinstance(self.interruption_state, str) or not self.interruption_state.strip():
            raise ContractV4Error("MISSING_REQUIRED_FIELD", "interruption_state")
        for name in ("admitted_fact_refs", "rejected_fact_refs", "applicable_rule_refs",
                     "inapplicable_rule_refs", "argument_refs", "attack_refs", "receipt_refs"):
            object.__setattr__(self, name, _sorted_unique(getattr(self, name), name))
        admitted = set(self.admitted_fact_refs)
        if admitted & set(self.rejected_fact_refs):
            raise ContractV4Error("DUPLICATE_ID", "admitted/rejected fact refs must be disjoint")
        if set(self.applicable_rule_refs) & set(self.inapplicable_rule_refs):
            raise ContractV4Error("DUPLICATE_ID", "applicable/inapplicable rule refs must be disjoint")
        for name in ("exception_resolution", "permission_resolution", "priority_resolution",
                     "temporal_numeric_result", "run_identity"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise ContractV4Error("MISSING_REQUIRED_FIELD", name)
            _reject_float_money(value, name)
        if not isinstance(self.run_identity, Mapping) or not self.run_identity:
            raise ContractV4Error("MISSING_REQUIRED_FIELD", "run_identity")

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "schema_version": self.schema_version,
            "decision_status": self.decision_status,
            "admitted_fact_refs": list(self.admitted_fact_refs),
            "rejected_fact_refs": list(self.rejected_fact_refs),
            "applicable_rule_refs": list(self.applicable_rule_refs),
            "inapplicable_rule_refs": list(self.inapplicable_rule_refs),
            "argument_refs": list(self.argument_refs),
            "attack_refs": list(self.attack_refs),
            "exception_resolution": dict(self.exception_resolution),
            "permission_resolution": dict(self.permission_resolution),
            "priority_resolution": dict(self.priority_resolution),
            "temporal_numeric_result": dict(self.temporal_numeric_result),
            "receipt_refs": list(self.receipt_refs),
            "completeness_state": self.completeness_state,
            "interruption_state": self.interruption_state,
            "run_identity": dict(self.run_identity),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SemanticResultV4":
        if not isinstance(payload, Mapping):
            raise ContractV4Error("MISSING_REQUIRED_FIELD", "result")
        allowed = {
            "request_id", "schema_version", "decision_status",
            "admitted_fact_refs", "rejected_fact_refs",
            "applicable_rule_refs", "inapplicable_rule_refs",
            "argument_refs", "attack_refs",
            "exception_resolution", "permission_resolution", "priority_resolution",
            "temporal_numeric_result", "receipt_refs",
            "completeness_state", "interruption_state", "run_identity",
        }
        _reject_unknown(payload, allowed, "result")
        missing = sorted(allowed - set(payload))
        if missing:
            raise ContractV4Error("MISSING_REQUIRED_FIELD", ", ".join(missing))
        return cls(
            request_id=payload["request_id"],
            schema_version=str(payload["schema_version"]),
            decision_status=str(payload["decision_status"]),
            admitted_fact_refs=tuple(payload["admitted_fact_refs"]),
            rejected_fact_refs=tuple(payload["rejected_fact_refs"]),
            applicable_rule_refs=tuple(payload["applicable_rule_refs"]),
            inapplicable_rule_refs=tuple(payload["inapplicable_rule_refs"]),
            argument_refs=tuple(payload["argument_refs"]),
            attack_refs=tuple(payload["attack_refs"]),
            exception_resolution=payload["exception_resolution"],
            permission_resolution=payload["permission_resolution"],
            priority_resolution=payload["priority_resolution"],
            temporal_numeric_result=payload["temporal_numeric_result"],
            receipt_refs=tuple(payload["receipt_refs"]),
            completeness_state=str(payload["completeness_state"]),
            interruption_state=str(payload["interruption_state"]),
            run_identity=payload["run_identity"],
        )

    def canonical_bytes(self) -> bytes:
        return jcs(self.to_dict()).encode("utf-8")

    def canonical_digest(self) -> str:
        return jcs_digest(self.to_dict())


def require_engine_match(engine_version: str, schema_version: str = SCHEMA_VERSION_V4) -> None:
    """schema 主版本与 engine 主版本不匹配时明确拒绝（§7 Gate）。"""

    if schema_version != SCHEMA_VERSION_V4:
        raise ContractV4Error("UNSUPPORTED_SCHEMA_VERSION", str(schema_version))
    major = str(engine_version).split(".")[0]
    if not major.isdigit() or int(major) < 3:
        raise ContractV4Error("ENGINE_VERSION_MISMATCH", str(engine_version))
