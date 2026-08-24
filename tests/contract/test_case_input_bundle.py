from __future__ import annotations

from base64 import b64encode

import pytest

from compiler_core.canonical_serialization import DigestV4, digest_value
from compiler_core.contracts import (
    CanonicalTimeV4,
    CaseArtifactV4,
    CaseInputBundleV4,
    CaseRequestV4,
    ContentRefV4,
    ContractV4Error,
    LegalContextV4,
    MCPEvaluateInputV4,
    RequestedOutputV4,
)
from compiler_core.mcp import standalone_type_schema


def _ref(kind: str, label: str) -> ContentRefV4:
    return ContentRefV4(kind, DigestV4.from_bytes(label.encode()))


def bundle() -> CaseInputBundleV4:
    content = b'{"schema_version":"jc/source-bundle/1.0"}'
    artifact = CaseArtifactV4(
        "source-bundle", ContentRefV4("source-bundle", DigestV4.from_bytes(content)),
        "source-bundle", "application/json", "case-input",
        b64encode(content).decode("ascii"),
    )
    request = CaseRequestV4(
        "case-1", "jc/4.0", LegalContextV4("CN", "中华人民共和国个人信息保护法"),
        CanonicalTimeV4("2026-08-24T00:00:00Z"), artifact.content_ref,
        _ref("evidence-manifest", "evidence"), (), _ref("pack-signature", "pack"),
        (RequestedOutputV4("semantic_result", "json", "zh-CN"),), (),
    )
    body = {
        "schema_version": "jc/case-input-bundle/1.0",
        "bundle_id": "bundle-1",
        "request": request.to_dict(),
        "artifacts": [artifact.to_dict()],
    }
    return CaseInputBundleV4.from_dict({**body, "bundle_digest": str(digest_value(body))})


def test_case_bundle_roundtrips_canonically() -> None:
    value = bundle()
    assert CaseInputBundleV4.from_json_bytes(value.canonical_bytes()) == value
    assert MCPEvaluateInputV4.from_dict({"case_bundle": value.to_dict()}).case_bundle == value


def test_bundle_digest_excludes_only_itself() -> None:
    value = bundle().to_dict()
    value["bundle_id"] = "changed"
    with pytest.raises(ContractV4Error, match="SELF_DIGEST_MISMATCH"):
        CaseInputBundleV4.from_dict(value)


def test_mcp_schema_has_one_closed_case_bundle_field() -> None:
    schema = standalone_type_schema("MCPEvaluateInputV4")
    definition = schema["$defs"]["MCPEvaluateInputV4"]
    assert definition["required"] == ["case_bundle"]
    assert set(definition["properties"]) == {"case_bundle"}
    artifact = schema["$defs"]["CaseArtifactV4"]
    assert artifact["properties"]["content_base64"]["maxLength"] == 1_398_104

