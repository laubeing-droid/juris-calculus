"""W8：build-bound RunIdentityV2、收据分离、FormalCertificateV1 与 AuditBundleV2。

依据：20260815 施工方案 §14。规则：

1. `RunIdentityV2` 绑定 engine commit/tree/version、wheel/package hash、
   schema、request、source bundle、evidence manifest、attestations、
   pack build、compiler、router、solver/checker/translator identity、
   runtime options。
2. 收据分离：AdmissionReceiptV1 / TranslationReceiptV1 / CheckerReceiptV2 /
   SolverReceiptV1 / ProofReceiptV1 / HumanApprovalReceiptV1；
   任一收据不能冒充另一种证明。
3. `FormalCertificateV1` 只在 source、fact、rule、translation、
   evaluation、checker、solver（如使用）、completeness、build identity、
   replay prerequisites 全部 PASS，且不存在 DISPUTED/UNKNOWN/partial/
   truncated 时生成。
4. `AuditBundleV2` 不得包含原始私人叙事、机器绝对路径或密钥；
   原子写入与离线 replay 的运行时部分由 audit_bundle.py 既有机制承担，
   本模块提供 v2 合同与门禁。
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from compiler_core.jcs import jcs_digest


RECEIPT_KINDS = (
    "AdmissionReceiptV1",
    "TranslationReceiptV1",
    "CheckerReceiptV2",
    "SolverReceiptV1",
    "ProofReceiptV1",
    "HumanApprovalReceiptV1",
)

GATE_NAMES = (
    "source",
    "fact",
    "rule",
    "translation",
    "evaluation",
    "checker",
    "solver",
    "completeness",
    "build_identity",
    "replay_prerequisites",
)

_CANONICAL_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ABSOLUTE_PATH_RE = re.compile(r"([A-Za-z]:[\\/]|^\\\\|^/)")


class CertificateGateError(ValueError):
    """证书与审计门禁错误；code 稳定可机读。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _require_nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CertificateGateError("MISSING_REQUIRED_FIELD", name)
    if _ABSOLUTE_PATH_RE.search(value):
        raise CertificateGateError("ABSOLUTE_MACHINE_PATH", name)
    return value


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise CertificateGateError("INVALID_DIGEST", name)
    return value


@dataclass(frozen=True)
class RunIdentityV2:
    """一次 run 的完整 build-bound 身份（方案 §14 绑定集）。"""

    engine_version: str
    engine_commit: str
    engine_tree: str
    package_hash: str
    schema_version: str
    request_digest: str
    source_bundle_ref: str
    evidence_manifest_ref: str
    fact_attestation_digests: tuple[str, ...]
    pack_build_digest: str
    compiler_identity: str
    router_identity: str
    checker_identity: str
    translator_identity: str
    solver_identity: str
    runtime_options: Mapping[str, Any]
    run_id: str = ""

    def __post_init__(self) -> None:
        for name in (
            "engine_version", "engine_commit", "engine_tree", "compiler_identity",
            "router_identity", "checker_identity", "translator_identity", "schema_version",
        ):
            object.__setattr__(self, name, _require_nonempty(getattr(self, name), name))
        for name in ("package_hash", "request_digest", "pack_build_digest"):
            object.__setattr__(self, name, _require_sha256(getattr(self, name), name))
        object.__setattr__(self, "source_bundle_ref", _require_nonempty(self.source_bundle_ref, "source_bundle_ref"))
        object.__setattr__(self, "evidence_manifest_ref", _require_nonempty(self.evidence_manifest_ref, "evidence_manifest_ref"))
        object.__setattr__(self, "solver_identity", self.solver_identity or "none")
        digests = tuple(sorted(_require_sha256(item, "fact_attestation_digests[]") for item in self.fact_attestation_digests))
        object.__setattr__(self, "fact_attestation_digests", digests)
        if not isinstance(self.runtime_options, Mapping):
            raise CertificateGateError("MISSING_REQUIRED_FIELD", "runtime_options")
        identity = jcs_digest(self.to_dict(exclude_run_id=True))
        if self.run_id and self.run_id != identity:
            raise CertificateGateError("RUN_IDENTITY_MISMATCH", self.run_id)
        object.__setattr__(self, "run_id", identity)

    def to_dict(self, *, exclude_run_id: bool = False) -> dict[str, Any]:
        payload = {
            "engine_version": self.engine_version,
            "engine_commit": self.engine_commit,
            "engine_tree": self.engine_tree,
            "package_hash": self.package_hash,
            "schema_version": self.schema_version,
            "request_digest": self.request_digest,
            "source_bundle_ref": self.source_bundle_ref,
            "evidence_manifest_ref": self.evidence_manifest_ref,
            "fact_attestation_digests": list(self.fact_attestation_digests),
            "pack_build_digest": self.pack_build_digest,
            "compiler_identity": self.compiler_identity,
            "router_identity": self.router_identity,
            "checker_identity": self.checker_identity,
            "translator_identity": self.translator_identity,
            "solver_identity": self.solver_identity,
            "runtime_options": dict(self.runtime_options),
        }
        if not exclude_run_id:
            payload["run_id"] = self.run_id
        return payload


@dataclass(frozen=True)
class TypedReceiptV1:
    """收据分离的统一信封；kind 决定证明对象，禁止互相冒充。"""

    kind: str
    subject_digest: str
    status: str
    issued_at: str
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.kind not in RECEIPT_KINDS:
            raise CertificateGateError("INVALID_ENUM", f"kind={self.kind!r}")
        object.__setattr__(self, "subject_digest", _require_sha256(self.subject_digest, "subject_digest"))
        if self.status not in ("PASS", "FAIL", "BLOCKED"):
            raise CertificateGateError("INVALID_ENUM", f"status={self.status!r}")
        if not _CANONICAL_TIME_RE.match(self.issued_at):
            raise CertificateGateError("NONCANONICAL_TIME", self.issued_at)
        if not isinstance(self.details, Mapping):
            raise CertificateGateError("MISSING_REQUIRED_FIELD", "details")

    @property
    def receipt_digest(self) -> str:
        return jcs_digest({
            "kind": self.kind,
            "subject_digest": self.subject_digest,
            "status": self.status,
            "issued_at": self.issued_at,
            "details": dict(self.details),
        })


def _scan_forbidden_content(payload: Any, scope: str) -> None:
    """AuditBundleV2 隐私护栏：绝对路径、密钥材料、原始叙事字段。"""

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("private_key", "secret", "password", "token")):
                raise CertificateGateError("AUDIT_PRIVACY_VIOLATION", f"{scope}.{key}")
            if lowered in ("raw_narrative", "original_text", "private_notes"):
                raise CertificateGateError("AUDIT_PRIVACY_VIOLATION", f"{scope}.{key}")
            _scan_forbidden_content(value, f"{scope}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            _scan_forbidden_content(item, f"{scope}[{index}]")
    elif isinstance(payload, str):
        if _ABSOLUTE_PATH_RE.search(payload):
            raise CertificateGateError("AUDIT_PRIVACY_VIOLATION", f"{scope} absolute path")


@dataclass(frozen=True)
class AuditBundleV2:
    """v2 审计包合同：canonical request/result/events/graph + schema + pack 材料 +
    receipts + run identity + manifest + replay 指令；隐私扫描在构造时强制。"""

    run_identity: RunIdentityV2
    canonical_request_digest: str
    canonical_result_digest: str
    events_digest: str
    graph_digest: str
    schema_refs: tuple[str, ...]
    pack_material_digests: tuple[str, ...]
    receipt_digests: tuple[str, ...]
    manifest_digest: str
    replay_instruction_digest: str
    bundle_digest: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.run_identity, RunIdentityV2):
            raise CertificateGateError("MISSING_REQUIRED_FIELD", "run_identity")
        for name in ("canonical_request_digest", "canonical_result_digest", "events_digest",
                     "graph_digest", "manifest_digest", "replay_instruction_digest"):
            object.__setattr__(self, name, _require_sha256(getattr(self, name), name))
        for name in ("schema_refs", "pack_material_digests", "receipt_digests"):
            values = tuple(sorted(_require_nonempty(item, f"{name}[]") if name == "schema_refs"
                                  else _require_sha256(item, f"{name}[]")
                                  for item in getattr(self, name)))
            if not values:
                raise CertificateGateError("MISSING_REQUIRED_FIELD", name)
            object.__setattr__(self, name, values)
        _scan_forbidden_content(self.to_dict(exclude_bundle_digest=True), "audit_bundle_v2")
        digest = jcs_digest(self.to_dict(exclude_bundle_digest=True))
        if self.bundle_digest and self.bundle_digest != digest:
            raise CertificateGateError("BUNDLE_DIGEST_MISMATCH", self.bundle_digest)
        object.__setattr__(self, "bundle_digest", digest)

    def to_dict(self, *, exclude_bundle_digest: bool = False) -> dict[str, Any]:
        payload = {
            "run_identity": self.run_identity.to_dict(),
            "canonical_request_digest": self.canonical_request_digest,
            "canonical_result_digest": self.canonical_result_digest,
            "events_digest": self.events_digest,
            "graph_digest": self.graph_digest,
            "schema_refs": list(self.schema_refs),
            "pack_material_digests": list(self.pack_material_digests),
            "receipt_digests": list(self.receipt_digests),
            "manifest_digest": self.manifest_digest,
            "replay_instruction_digest": self.replay_instruction_digest,
        }
        if not exclude_bundle_digest:
            payload["bundle_digest"] = self.bundle_digest
        return payload


def issue_formal_certificate(
    *,
    run_identity: RunIdentityV2,
    gate_statuses: Mapping[str, str],
    receipts: tuple[TypedReceiptV1, ...],
    solver_used: bool,
    completeness_state: str,
    bundle: AuditBundleV2,
) -> dict[str, Any]:
    """FormalCertificateV1：全部条件满足才生成；否则给出受阻原因清单。"""

    blocked_reasons: list[str] = []

    missing_gates = sorted(set(GATE_NAMES) - set(gate_statuses))
    if missing_gates:
        blocked_reasons.append(f"missing_gates:{','.join(missing_gates)}")
    for gate in GATE_NAMES:
        status = gate_statuses.get(gate)
        if gate == "solver" and not solver_used:
            continue
        if status != "PASS":
            blocked_reasons.append(f"gate_{gate}:{status or 'absent'}")

    if completeness_state != "complete":
        # DISPUTED/UNKNOWN/partial/truncated/interrupted 一律不得签发。
        blocked_reasons.append(f"completeness:{completeness_state}")

    for receipt in receipts:
        if receipt.status != "PASS":
            blocked_reasons.append(f"receipt_{receipt.kind}:{receipt.status}")
    kinds = {receipt.kind for receipt in receipts}
    required_kinds = {"CheckerReceiptV2", "TranslationReceiptV1", "AdmissionReceiptV1"}
    if solver_used:
        required_kinds.add("SolverReceiptV1")
    missing_kinds = sorted(required_kinds - kinds)
    if missing_kinds:
        blocked_reasons.append(f"missing_receipts:{','.join(missing_kinds)}")

    if bundle.run_identity.run_id != run_identity.run_id:
        blocked_reasons.append("bundle_run_identity_mismatch")

    if blocked_reasons:
        return {
            "issued": False,
            "kind": "FormalCertificateV1",
            "blocked_reasons": sorted(blocked_reasons),
            "run_id": run_identity.run_id,
        }

    certificate_payload = {
        "kind": "FormalCertificateV1",
        "run_id": run_identity.run_id,
        "bundle_digest": bundle.bundle_digest,
        "gate_statuses": {gate: gate_statuses[gate] for gate in GATE_NAMES if gate in gate_statuses},
        "receipt_digests": sorted(receipt.receipt_digest for receipt in receipts),
        "completeness_state": completeness_state,
    }
    return {
        "issued": True,
        "kind": "FormalCertificateV1",
        "certificate_digest": jcs_digest(certificate_payload),
        "certificate": certificate_payload,
        "run_id": run_identity.run_id,
    }
