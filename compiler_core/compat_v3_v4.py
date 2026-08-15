"""v3/W1b → v4 唯一兼容入口（W1）。

依据：20260815 施工方案 §7 动作 3、§18。约束：

1. CLI/Client/MCP 不得各自携带兼容逻辑；兼容只经本模块。
2. adapter 输出 MigrationReceiptV1：来源 schema 版本、字段映射、
   defaulted 字段、被拒字段；defaulted 字段不得静默扩权。
3. 兼容层不得授予 v4 没有的权限：v3/W1b 事实一律作为 candidate
   proposal 投影，`verified_fact` 自报状态不被继承；
   attestation refs 只能由外部凭据提供，adapter 不生成。
4. adapter 不读取 v4 内部状态，只调用 contracts_v4 公共验证。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from compiler_core.contracts_v4 import (
    CaseRequestV4,
    ContractV4Error,
    SCHEMA_VERSION_V4,
    _reject_float_money,
    _reject_unknown,
)
from compiler_core.jcs import jcs_digest


_V3_ALLOWED = {
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

_COMPAT_KINDS = ("jc-v3", "w1b-case-request")


@dataclass(frozen=True)
class MigrationReceiptV1:
    """兼容投影收据；defaulted 与 rejected 字段全部显式记录。"""

    kind: str
    source_schema_version: str
    request_digest: str
    field_mappings: Mapping[str, str]
    defaulted_fields: tuple[str, ...]
    rejected_fields: tuple[str, ...]
    receipt_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source_schema_version": self.source_schema_version,
            "request_digest": self.request_digest,
            "field_mappings": dict(self.field_mappings),
            "defaulted_fields": list(self.defaulted_fields),
            "rejected_fields": list(self.rejected_fields),
        }

    def with_digest(self) -> "MigrationReceiptV1":
        payload = self.to_dict()
        return MigrationReceiptV1(
            kind=self.kind,
            source_schema_version=self.source_schema_version,
            request_digest=self.request_digest,
            field_mappings=self.field_mappings,
            defaulted_fields=self.defaulted_fields,
            rejected_fields=self.rejected_fields,
            receipt_digest=jcs_digest(payload),
        )


def _legacy_source_bundle_ref(external_refs: tuple[str, ...]) -> str:
    """把 v3 external_source_refs 投影为确定性 legacy 引用（非来源验证）。"""

    digest = jcs_digest({"external_source_refs": sorted(set(external_refs))})
    return f"legacy-source-bundle:{digest[7:23]}"


def _legacy_evidence_manifest_ref(fact_ids: tuple[str, ...]) -> str:
    digest = jcs_digest({"legacy_fact_ids": sorted(set(fact_ids))})
    return f"legacy-evidence-manifest:{digest[7:23]}"


def migrate_v3_request(payload: Mapping[str, Any], *, compat_kind: str = "jc-v3") -> tuple[CaseRequestV4, MigrationReceiptV1]:
    """把 v3/W1b CaseRequest 字典投影为 CaseRequestV4。

    语义保持：
    - facts 一律降为 candidate proposal；verified_fact 自报不被继承；
    - as_of_date 扩展为 decision_time 的 UTC 零点（记录为 defaulted）；
    - request_id、source_bundle_ref、evidence_manifest_ref、requested_outputs
      为兼容默认值，全部进入 receipt，不取得额外权限。
    """

    if compat_kind not in _COMPAT_KINDS:
        raise ContractV4Error("UNKNOWN_FIELD", f"compat_kind={compat_kind!r}")
    if not isinstance(payload, Mapping):
        raise ContractV4Error("MISSING_REQUIRED_FIELD", "request")
    _reject_unknown(payload, _V3_ALLOWED, "v3_request")
    _reject_float_money(payload, "v3_request")

    defaulted: list[str] = []
    rejected: list[str] = []

    source_version = str(payload.get("schema_version", ""))
    facts_raw = payload.get("facts") or []
    if not isinstance(facts_raw, list):
        raise ContractV4Error("INVALID_ENUM", "facts must be an array")

    fact_ids: list[str] = []
    for item in facts_raw:
        if not isinstance(item, Mapping):
            raise ContractV4Error("INVALID_ENUM", "fact must be an object")
        fact_id = str(item.get("id") or "").strip()
        if not fact_id:
            raise ContractV4Error("MISSING_REQUIRED_FIELD", "facts[].id")
        if fact_id in fact_ids:
            raise ContractV4Error("DUPLICATE_ID", "facts[].id")
        fact_ids.append(fact_id)
        status = str(item.get("status") or "candidate_fact")
        if status == "verified_fact":
            # 兼容层不得授予 v4 没有的权限：自报 verified 一律降为 candidate。
            rejected.append(f"facts[{fact_id}].status=verified_fact")

    external_refs = tuple(str(item) for item in payload.get("external_source_refs") or ())

    as_of_date = str(payload.get("as_of_date") or "")
    if len(as_of_date) != 10:
        raise ContractV4Error("NONCANONICAL_TIME", f"as_of_date={as_of_date!r}")
    decision_time = f"{as_of_date}T00:00:00Z"
    defaulted.append("decision_time.utc_midnight")

    request_seed = jcs_digest({"v3_request": dict(payload), "compat_kind": compat_kind})
    request_id = f"legacy-request:{request_seed[7:23]}"
    defaulted.append("request_id.derived")

    source_bundle_ref = _legacy_source_bundle_ref(external_refs)
    evidence_manifest_ref = _legacy_evidence_manifest_ref(tuple(fact_ids))
    defaulted.append("source_bundle_ref.legacy_projection")
    defaulted.append("evidence_manifest_ref.legacy_projection")

    requested_outputs = ("semantic_result",)
    defaulted.append("requested_outputs.default_semantic_result")

    v4_payload = {
        "request_id": request_id,
        "schema_version": SCHEMA_VERSION_V4,
        "legal_context": {
            "jurisdiction": payload.get("jurisdiction"),
            "governing_law": payload.get("governing_law"),
        },
        "decision_time": decision_time,
        "source_bundle_ref": source_bundle_ref,
        "evidence_manifest_ref": evidence_manifest_ref,
        "fact_attestation_refs": [],
        "rule_pack_ref": {
            "pack_id": payload.get("rule_pack_id"),
            "version": payload.get("rule_pack_version"),
            "digest": payload.get("rule_pack_digest"),
        },
        "requested_outputs": list(requested_outputs),
        "proposal_refs": [f"legacy-fact:{fact_id}" for fact_id in fact_ids],
    }
    request = CaseRequestV4.from_dict(v4_payload)

    receipt = MigrationReceiptV1(
        kind=f"migration:{compat_kind}->jc/4.0",
        source_schema_version=source_version,
        request_digest=request.canonical_digest(),
        field_mappings={
            "jurisdiction": "legal_context.jurisdiction",
            "governing_law": "legal_context.governing_law",
            "as_of_date": "decision_time",
            "facts": "proposal_refs(candidate)",
            "rule_pack_id": "rule_pack_ref.pack_id",
            "rule_pack_version": "rule_pack_ref.version",
            "rule_pack_digest": "rule_pack_ref.digest",
            "external_source_refs": "source_bundle_ref(legacy projection)",
        },
        defaulted_fields=tuple(sorted(defaulted)),
        rejected_fields=tuple(sorted(rejected)),
    ).with_digest()
    return request, receipt
