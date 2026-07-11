"""JC v3公共契约：输入准入、结果状态、不可变机器结果和JSON Schema。"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from compiler_core.types import FactCreator, FactTrustStatus, LegalFact


SCHEMA_VERSION = "3.0"
ENGINE_LIMITS = {
    "max_facts": 512,
    "max_fact_text_chars": 65_536,
    "max_external_source_refs": 512,
    "max_branches": 32,
}
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class ContractValidationError(ValueError):
    """公共契约验证失败；code可稳定映射到CLI输入错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ResultStatus(str, Enum):
    """法律推理结果状态；不表示进程是否成功运行。"""

    ACCEPTED_FORMAL_RESULT = "accepted_formal_result"
    HYPOTHETICAL_RESULT = "hypothetical_result"
    REVIEW_ONLY_RESULT = "review_only_result"
    MISSING_REQUIRED_FACT = "missing_required_fact"
    CONFLICT_CERTIFICATE = "conflict_certificate"
    ENGINE_ERROR = "engine_error"


class ExecutionStatus(str, Enum):
    """程序执行状态，与法律结果状态分离。"""

    COMPLETED = "completed"
    ADMISSION_BLOCKED = "admission_blocked"
    ENGINE_ERROR = "engine_error"


class CertificateKind(str, Enum):
    """结果可携带的证书种类。"""

    NONE = "none"
    FORMAL = "formal"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class RulePackDescriptor:
    """Phase 1最小规则包描述；完整来源解析和hash验证留给Phase 3。"""

    pack_id: str
    version: str
    content_digest: str
    verified_rule_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.pack_id.strip() or not self.version.strip():
            raise ContractValidationError("INVALID_RULE_PACK", "pack_id and version are required")
        _require_digest(self.content_digest, "content_digest")
        object.__setattr__(self, "verified_rule_ids", _sorted_unique(self.verified_rule_ids))

    def to_dict(self) -> dict[str, Any]:
        """返回新的确定性规则包字典。"""

        return {
            "pack_id": self.pack_id,
            "version": self.version,
            "content_digest": self.content_digest,
            "verified_rule_ids": list(self.verified_rule_ids),
        }


@dataclass(frozen=True)
class CaseRequest:
    """正式application唯一接受的结构化案件请求。"""

    schema_version: str
    jurisdiction: str
    governing_law: str
    as_of_date: str
    facts: tuple[LegalFact, ...]
    rule_pack_id: str
    rule_pack_version: str
    rule_pack_digest: str
    external_source_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("UNSUPPORTED_SCHEMA_VERSION", self.schema_version)
        if not self.jurisdiction.strip() or not self.governing_law.strip():
            raise ContractValidationError("MISSING_LEGAL_CONTEXT", "jurisdiction and governing_law are required")
        try:
            date.fromisoformat(self.as_of_date)
        except ValueError as exc:
            raise ContractValidationError("INVALID_AS_OF_DATE", self.as_of_date) from exc
        if not self.rule_pack_id.strip() or not self.rule_pack_version.strip():
            raise ContractValidationError("INVALID_RULE_PACK", "rule pack id and version are required")
        _require_digest(self.rule_pack_digest, "rule_pack_digest")
        facts = tuple(self.facts)
        if len(facts) > ENGINE_LIMITS["max_facts"]:
            raise ContractValidationError("FACT_LIMIT_EXCEEDED", str(len(facts)))
        ids = [fact.id for fact in facts]
        if any(not fact_id.strip() for fact_id in ids):
            raise ContractValidationError("EMPTY_FACT_KEY", "fact id cannot be empty")
        if len(ids) != len(set(ids)):
            raise ContractValidationError("DUPLICATE_FACT_KEY", "fact ids must be unique")
        text_chars = sum(len(fact.description) + len(fact.raw_text) + len(str(fact.value or "")) for fact in facts)
        if text_chars > ENGINE_LIMITS["max_fact_text_chars"]:
            raise ContractValidationError("FACT_TEXT_LIMIT_EXCEEDED", str(text_chars))
        refs = _sorted_unique(self.external_source_refs)
        if len(refs) > ENGINE_LIMITS["max_external_source_refs"]:
            raise ContractValidationError("SOURCE_REF_LIMIT_EXCEEDED", str(len(refs)))
        object.__setattr__(self, "facts", tuple(sorted(facts, key=lambda fact: fact.id)))
        object.__setattr__(self, "external_source_refs", refs)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CaseRequest":
        """严格解析字典；拒绝未知顶层或事实字段。"""

        allowed = {
            "schema_version",
            "jurisdiction",
            "governing_law",
            "as_of_date",
            "facts",
            "rule_pack_id",
            "rule_pack_version",
            "rule_pack_digest",
            "external_source_refs",
        }
        _reject_unknown(payload, allowed, "request")
        required = allowed - {"external_source_refs"}
        missing = sorted(required - set(payload))
        if missing:
            raise ContractValidationError("MISSING_REQUIRED_FIELD", ", ".join(missing))
        facts_value = payload.get("facts")
        if not isinstance(facts_value, list):
            raise ContractValidationError("INVALID_FACTS", "facts must be an array")
        return cls(
            schema_version=str(payload["schema_version"]),
            jurisdiction=str(payload["jurisdiction"]),
            governing_law=str(payload["governing_law"]),
            as_of_date=str(payload["as_of_date"]),
            facts=tuple(_fact_from_dict(item) for item in facts_value),
            rule_pack_id=str(payload["rule_pack_id"]),
            rule_pack_version=str(payload["rule_pack_version"]),
            rule_pack_digest=str(payload["rule_pack_digest"]),
            external_source_refs=tuple(str(item) for item in payload.get("external_source_refs") or ()),
        )

    @property
    def estimated_branch_count(self) -> int:
        """确定性估算争议事实组合数；超限由application降为review-only。"""

        count = 1
        for fact in self.facts:
            if fact.status == FactTrustStatus.DISPUTED:
                count *= max(2, len(fact.alternatives))
        return count

    @property
    def branch_limit_exceeded(self) -> bool:
        """返回争议组合是否超过单一engine limit。"""

        return self.estimated_branch_count > ENGINE_LIMITS["max_branches"]

    def to_dict(self) -> dict[str, Any]:
        """返回新的规范字典；事实输入顺序不影响输出。"""

        return {
            "schema_version": self.schema_version,
            "jurisdiction": self.jurisdiction,
            "governing_law": self.governing_law,
            "as_of_date": self.as_of_date,
            "facts": [_fact_to_dict(fact) for fact in self.facts],
            "rule_pack_id": self.rule_pack_id,
            "rule_pack_version": self.rule_pack_version,
            "rule_pack_digest": self.rule_pack_digest,
            "external_source_refs": list(self.external_source_refs),
        }


@dataclass(frozen=True)
class BranchResult:
    """争议事实的一条稳定分支摘要。"""

    branch_id: str
    result_status: ResultStatus
    claims: tuple[str, ...] = field(default_factory=tuple)
    taint: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.result_status, ResultStatus):
            try:
                object.__setattr__(self, "result_status", ResultStatus(str(self.result_status)))
            except ValueError as exc:
                raise ContractValidationError("UNKNOWN_RESULT_STATUS", str(self.result_status)) from exc
        if not self.branch_id.strip():
            raise ContractValidationError("EMPTY_BRANCH_ID", "branch_id is required")
        object.__setattr__(self, "claims", _sorted_unique(self.claims))
        object.__setattr__(self, "taint", _sorted_unique(self.taint))

    def to_dict(self) -> dict[str, Any]:
        """返回新的分支字典。"""

        return {
            "branch_id": self.branch_id,
            "result_status": self.result_status.value,
            "claims": list(self.claims),
            "taint": list(self.taint),
        }


@dataclass(frozen=True)
class SemanticResult:
    """不含artifact refs的不可变正式语义投影。"""

    schema_version: str
    run_id: str
    result_digest: str
    execution_status: ExecutionStatus
    result_status: ResultStatus
    formal_kernel_used: bool
    review_required: bool
    checker_accepted: bool
    certificate_kind: CertificateKind
    engine_version: str
    pack_id: str
    pack_version: str
    pack_digest: str
    claims: tuple[str, ...] = field(default_factory=tuple)
    branches: tuple[BranchResult, ...] = field(default_factory=tuple)
    used_fact_ids: tuple[str, ...] = field(default_factory=tuple)
    used_rule_ids: tuple[str, ...] = field(default_factory=tuple)
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    missing_fact_ids: tuple[str, ...] = field(default_factory=tuple)
    taint: tuple[str, ...] = field(default_factory=tuple)
    risk_labels: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name, enum_type in (
            ("execution_status", ExecutionStatus),
            ("result_status", ResultStatus),
            ("certificate_kind", CertificateKind),
        ):
            value = getattr(self, name)
            if not isinstance(value, enum_type):
                try:
                    object.__setattr__(self, name, enum_type(str(value)))
                except ValueError as exc:
                    raise ContractValidationError("UNKNOWN_RESULT_ENUM", f"{name}: {value}") from exc
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("UNSUPPORTED_SCHEMA_VERSION", self.schema_version)
        if not self.run_id.strip() or not self.engine_version.strip():
            raise ContractValidationError("MISSING_RESULT_IDENTITY", "run_id and engine_version are required")
        _require_digest(self.result_digest, "result_digest")
        _require_digest(self.pack_digest, "pack_digest")
        for name in (
            "claims",
            "used_fact_ids",
            "used_rule_ids",
            "source_ids",
            "missing_fact_ids",
            "taint",
            "risk_labels",
        ):
            object.__setattr__(self, name, _sorted_unique(getattr(self, name)))
        object.__setattr__(self, "branches", tuple(sorted(tuple(self.branches), key=lambda item: item.branch_id)))
        _validate_result_state(self)

    def to_dict(self) -> dict[str, Any]:
        """返回新的深层JSON对象，不暴露冻结对象内部引用。"""

        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "result_digest": self.result_digest,
            "execution_status": self.execution_status.value,
            "result_status": self.result_status.value,
            "formal_kernel_used": self.formal_kernel_used,
            "review_required": self.review_required,
            "checker_accepted": self.checker_accepted,
            "certificate_kind": self.certificate_kind.value,
            "engine_version": self.engine_version,
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "pack_digest": self.pack_digest,
            "claims": list(self.claims),
            "branches": [branch.to_dict() for branch in self.branches],
            "used_fact_ids": list(self.used_fact_ids),
            "used_rule_ids": list(self.used_rule_ids),
            "source_ids": list(self.source_ids),
            "missing_fact_ids": list(self.missing_fact_ids),
            "taint": list(self.taint),
            "risk_labels": list(self.risk_labels),
        }


@dataclass(frozen=True)
class CanonicalResult:
    """SemanticResult加逻辑artifact引用的不可变公共结果。"""

    semantic: SemanticResult
    artifact_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_refs", _sorted_unique(self.artifact_refs))

    def to_dict(self) -> dict[str, Any]:
        """返回新的公共结果字典。"""

        return {
            "semantic": self.semantic.to_dict(),
            "artifact_refs": list(self.artifact_refs),
        }


@dataclass(frozen=True)
class RendererProfile:
    """Phase 1最小声明式profile描述；不得包含可执行模板。"""

    profile_id: str
    version: str
    profile_hash: str
    locale: str = "zh-CN"
    forbidden_phrases: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.profile_id.strip() or not self.version.strip():
            raise ContractValidationError("INVALID_RENDERER_PROFILE", "profile id and version are required")
        _require_digest(self.profile_hash, "profile_hash")
        object.__setattr__(self, "forbidden_phrases", _sorted_unique(self.forbidden_phrases))


@dataclass(frozen=True)
class RenderedArtifact:
    """只承载表达内容及其绑定信息，不复制可改写的正式结果。"""

    result_digest: str
    renderer_id: str
    renderer_version: str
    profile_id: str
    profile_version: str
    profile_hash: str
    audience: str
    locale: str
    format: str
    content: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_digest(self.result_digest, "result_digest")
        _require_digest(self.profile_hash, "profile_hash")
        if self.audience not in {"agent", "lawyer"}:
            raise ContractValidationError("INVALID_AUDIENCE", self.audience)
        object.__setattr__(self, "warnings", _sorted_unique(self.warnings))

    def to_dict(self) -> dict[str, Any]:
        """返回新的表达产物字典。"""

        return {
            "result_digest": self.result_digest,
            "renderer_id": self.renderer_id,
            "renderer_version": self.renderer_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_hash": self.profile_hash,
            "audience": self.audience,
            "locale": self.locale,
            "format": self.format,
            "content": self.content,
            "warnings": list(self.warnings),
        }


PROTECTED_RESULT_FIELDS = frozenset({
    "execution_status",
    "result_status",
    "formal_kernel_used",
    "review_required",
    "checker_accepted",
    "certificate_kind",
    "claims",
    "branches",
    "used_fact_ids",
    "used_rule_ids",
    "source_ids",
    "missing_fact_ids",
    "taint",
    "risk_labels",
})

AuditSink = Callable[[Mapping[str, Any]], None]


def emit_audit_event(sink: AuditSink | None, event: Mapping[str, Any]) -> None:
    """向可选内存sink发送事件副本；持久化writer留到Phase 4。"""

    if sink is not None:
        sink(dict(event))


def schema_document() -> dict[str, Any]:
    """返回确定性单文件JSON Schema；CLI与可选MCP必须复用此来源。"""

    string_array = {"type": "array", "items": {"type": "string"}, "uniqueItems": True}
    fact_properties = {
        "id": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "value": {},
        "status": {"type": "string", "enum": [item.value for item in FactTrustStatus]},
        "source_ids": string_array,
        "alternatives": {"type": "array", "items": {"type": "object"}},
        "provenance": {"type": "object"},
        "human_reviewed": {"type": "boolean"},
        "created_by": {"type": "string", "enum": [item.value for item in FactCreator]},
        "reasoning_tier": {"type": "string", "enum": ["P0", "P1", "P2"]},
        "source": {"type": "string"},
        "formalizable": {"type": "number"},
        "taint_status": {"type": "string"},
        "extraction_confidence": {"type": "number"},
        "carrier_level": {"type": "string"},
        "raw_text": {"type": "string"},
        "source_anchor": {"type": "string"},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://juris-calculus.local/schema/jc-v3.schema.json",
        "title": "juris-calculus v3 public contracts",
        "$defs": {
            "LegalFact": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "status"],
                "properties": fact_properties,
            },
            "CaseRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema_version",
                    "jurisdiction",
                    "governing_law",
                    "as_of_date",
                    "facts",
                    "rule_pack_id",
                    "rule_pack_version",
                    "rule_pack_digest",
                ],
                "properties": {
                    "schema_version": {"const": SCHEMA_VERSION},
                    "jurisdiction": {"type": "string", "minLength": 1},
                    "governing_law": {"type": "string", "minLength": 1},
                    "as_of_date": {"type": "string", "format": "date"},
                    "facts": {
                        "type": "array",
                        "maxItems": ENGINE_LIMITS["max_facts"],
                        "items": {"$ref": "#/$defs/LegalFact"},
                    },
                    "rule_pack_id": {"type": "string", "minLength": 1},
                    "rule_pack_version": {"type": "string", "minLength": 1},
                    "rule_pack_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "external_source_refs": string_array,
                },
            },
            "RulePackDescriptor": {
                "type": "object",
                "additionalProperties": False,
                "required": ["pack_id", "version", "content_digest", "verified_rule_ids"],
                "properties": {
                    "pack_id": {"type": "string", "minLength": 1},
                    "version": {"type": "string", "minLength": 1},
                    "content_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "verified_rule_ids": string_array,
                },
            },
            "BranchResult": {
                "type": "object",
                "additionalProperties": False,
                "required": ["branch_id", "result_status", "claims", "taint"],
                "properties": {
                    "branch_id": {"type": "string", "minLength": 1},
                    "result_status": {"type": "string", "enum": [item.value for item in ResultStatus]},
                    "claims": string_array,
                    "taint": string_array,
                },
            },
            "SemanticResult": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema_version", "run_id", "result_digest", "execution_status", "result_status",
                    "formal_kernel_used", "review_required", "checker_accepted", "certificate_kind",
                    "engine_version", "pack_id", "pack_version", "pack_digest", "claims", "branches",
                    "used_fact_ids", "used_rule_ids", "source_ids", "missing_fact_ids", "taint", "risk_labels",
                ],
                "properties": {
                    "schema_version": {"const": SCHEMA_VERSION},
                    "run_id": {"type": "string", "minLength": 1},
                    "result_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "execution_status": {"type": "string", "enum": [item.value for item in ExecutionStatus]},
                    "result_status": {"type": "string", "enum": [item.value for item in ResultStatus]},
                    "formal_kernel_used": {"type": "boolean"},
                    "review_required": {"type": "boolean"},
                    "checker_accepted": {"type": "boolean"},
                    "certificate_kind": {"type": "string", "enum": [item.value for item in CertificateKind]},
                    "engine_version": {"type": "string"},
                    "pack_id": {"type": "string"},
                    "pack_version": {"type": "string"},
                    "pack_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "claims": string_array,
                    "branches": {"type": "array", "items": {"$ref": "#/$defs/BranchResult"}},
                    "used_fact_ids": string_array,
                    "used_rule_ids": string_array,
                    "source_ids": string_array,
                    "missing_fact_ids": string_array,
                    "taint": string_array,
                    "risk_labels": string_array,
                },
            },
            "CanonicalResult": {
                "type": "object",
                "additionalProperties": False,
                "required": ["semantic", "artifact_refs"],
                "properties": {
                    "semantic": {"$ref": "#/$defs/SemanticResult"},
                    "artifact_refs": string_array,
                },
            },
            "RendererProfile": {
                "type": "object",
                "additionalProperties": False,
                "required": ["profile_id", "version", "profile_hash", "locale", "forbidden_phrases"],
                "properties": {
                    "profile_id": {"type": "string", "minLength": 1},
                    "version": {"type": "string", "minLength": 1},
                    "profile_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "locale": {"type": "string"},
                    "forbidden_phrases": string_array,
                },
            },
            "RenderedArtifact": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "result_digest", "renderer_id", "renderer_version", "profile_id", "profile_version",
                    "profile_hash", "audience", "locale", "format", "content", "warnings",
                ],
                "properties": {
                    "result_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "renderer_id": {"type": "string"},
                    "renderer_version": {"type": "string"},
                    "profile_id": {"type": "string"},
                    "profile_version": {"type": "string"},
                    "profile_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "audience": {"type": "string", "enum": ["agent", "lawyer"]},
                    "locale": {"type": "string"},
                    "format": {"type": "string"},
                    "content": {"type": "string"},
                    "warnings": string_array,
                },
            },
        },
    }


def write_schema(path: Path | None = None) -> Path:
    """由唯一contracts事实源写出已提交JSON Schema。"""

    target = path or Path(__file__).resolve().parents[1] / "schemas" / "jc-v3.schema.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema_document(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _validate_result_state(result: SemanticResult) -> None:
    """验证状态矩阵；任何不完整正式成功组合均fail closed。"""

    status = result.result_status
    if result.execution_status == ExecutionStatus.ENGINE_ERROR and status != ResultStatus.ENGINE_ERROR:
        raise ContractValidationError("INVALID_RESULT_STATE", "engine_error execution requires engine_error result")
    if result.execution_status == ExecutionStatus.ADMISSION_BLOCKED and status not in {
        ResultStatus.REVIEW_ONLY_RESULT,
        ResultStatus.MISSING_REQUIRED_FACT,
    }:
        raise ContractValidationError("INVALID_RESULT_STATE", "admission_blocked requires review or missing result")
    if status == ResultStatus.ACCEPTED_FORMAL_RESULT:
        if not (
            result.execution_status == ExecutionStatus.COMPLETED
            and result.formal_kernel_used
            and not result.review_required
            and result.checker_accepted
            and result.certificate_kind == CertificateKind.FORMAL
            and result.claims
            and result.used_fact_ids
            and result.used_rule_ids
            and result.source_ids
        ):
            raise ContractValidationError("INVALID_FORMAL_RESULT", "formal result is missing accepted kernel evidence")
        return
    if status == ResultStatus.HYPOTHETICAL_RESULT:
        if not result.review_required or result.certificate_kind != CertificateKind.NONE or "assumption" not in result.taint:
            raise ContractValidationError("INVALID_HYPOTHETICAL_RESULT", "hypothetical result requires assumption taint")
    elif status == ResultStatus.REVIEW_ONLY_RESULT:
        if not result.review_required or result.certificate_kind != CertificateKind.NONE or result.checker_accepted:
            raise ContractValidationError("INVALID_REVIEW_RESULT", "review-only result cannot be checker accepted")
    elif status == ResultStatus.MISSING_REQUIRED_FACT:
        if not result.review_required or not result.missing_fact_ids or result.certificate_kind != CertificateKind.NONE:
            raise ContractValidationError("INVALID_MISSING_RESULT", "missing result requires missing facts")
    elif status == ResultStatus.CONFLICT_CERTIFICATE:
        if not result.review_required or result.certificate_kind != CertificateKind.CONFLICT:
            raise ContractValidationError("INVALID_CONFLICT_RESULT", "conflict result requires conflict certificate")
    elif status == ResultStatus.ENGINE_ERROR:
        if not (
            result.execution_status == ExecutionStatus.ENGINE_ERROR
            and result.review_required
            and not result.formal_kernel_used
            and not result.checker_accepted
            and result.certificate_kind == CertificateKind.NONE
            and not result.claims
        ):
            raise ContractValidationError("INVALID_ENGINE_ERROR", "engine error cannot carry accepted output")
    if status != ResultStatus.CONFLICT_CERTIFICATE and result.certificate_kind == CertificateKind.CONFLICT:
        raise ContractValidationError("INVALID_CERTIFICATE_KIND", "conflict certificate requires conflict result")
    if status != ResultStatus.ACCEPTED_FORMAL_RESULT and result.certificate_kind == CertificateKind.FORMAL:
        raise ContractValidationError("INVALID_CERTIFICATE_KIND", "formal certificate requires accepted result")


def _fact_from_dict(payload: Any) -> LegalFact:
    """严格解析一个事实对象并复制全部可变容器。"""

    if not isinstance(payload, Mapping):
        raise ContractValidationError("INVALID_FACT", "fact must be an object")
    allowed = {
        "id", "description", "value", "status", "source_ids", "alternatives", "provenance",
        "human_reviewed", "created_by", "reasoning_tier", "source", "formalizable", "taint_status",
        "extraction_confidence", "carrier_level", "raw_text", "source_anchor",
    }
    _reject_unknown(payload, allowed, "fact")
    if "id" not in payload or "status" not in payload:
        raise ContractValidationError("MISSING_FACT_FIELD", "id and status are required")
    try:
        status = FactTrustStatus(str(payload["status"]))
        creator = FactCreator(str(payload.get("created_by", FactCreator.SYSTEM.value)))
    except ValueError as exc:
        raise ContractValidationError("UNKNOWN_FACT_ENUM", str(exc)) from exc
    try:
        return LegalFact(
            id=str(payload["id"]),
            description=str(payload.get("description") or ""),
            source=str(payload.get("source") or ""),
            formalizable=float(payload.get("formalizable", 1.0)),
            taint_status=str(payload.get("taint_status") or "CLEAR"),
            extraction_confidence=float(payload.get("extraction_confidence", 1.0)),
            carrier_level=str(payload.get("carrier_level") or ""),
            raw_text=str(payload.get("raw_text") or ""),
            source_anchor=str(payload.get("source_anchor") or ""),
            value=payload.get("value"),
            status=status,
            source_ids=tuple(str(item) for item in payload.get("source_ids") or ()),
            alternatives=tuple(dict(item) for item in payload.get("alternatives") or ()),
            provenance=dict(payload.get("provenance") or {}),
            human_reviewed=bool(payload.get("human_reviewed", False)),
            created_by=creator,
            reasoning_tier=str(payload.get("reasoning_tier") or "P0"),
        )
    except (TypeError, ValueError) as exc:
        raise ContractValidationError("INVALID_FACT", str(exc)) from exc


def _fact_to_dict(fact: LegalFact) -> dict[str, Any]:
    """序列化CaseRequest事实，不修改权威LegalFact对象。"""

    payload = fact.trust_dict()
    payload.update({
        "description": fact.description,
        "source": fact.source,
        "formalizable": fact.formalizable,
        "taint_status": fact.taint_status,
        "extraction_confidence": fact.extraction_confidence,
        "carrier_level": fact.carrier_level,
        "raw_text": fact.raw_text,
        "source_anchor": fact.source_anchor,
    })
    payload["id"] = payload.pop("fact_key")
    return payload


def _sorted_unique(values: Any) -> tuple[str, ...]:
    """把字符串集合复制为确定性不可变序列。"""

    return tuple(sorted({str(item) for item in values if str(item)}))


def _require_digest(value: str, field_name: str) -> None:
    """只接受小写SHA-256十六进制摘要。"""

    if not _DIGEST_RE.fullmatch(value):
        raise ContractValidationError("INVALID_DIGEST", field_name)


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], label: str) -> None:
    """拒绝公共契约中的未知字段，避免调用者误以为字段生效。"""

    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ContractValidationError("UNKNOWN_FIELD", f"{label}: {', '.join(unknown)}")


def _main() -> int:
    """提供只生成schema的模块入口。"""

    parser = argparse.ArgumentParser(description="Generate JC v3 public JSON Schema")
    parser.add_argument("--write-schema", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.write_schema:
        parser.error("--write-schema is required")
    print(write_schema(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
