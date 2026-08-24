from __future__ import annotations

from dataclasses import replace

import pytest

from compiler_core.canonical_serialization import DigestV4, digest_value
from compiler_core.contracts import (
    CaseArtifactV4,
    CaseInputBundleV4,
    ContentRefV4,
    ContractV4Error,
    ResourceLimitsV4,
)
from tests.contract.test_case_input_bundle import bundle


def _rebuild(value: CaseInputBundleV4, artifacts: tuple[CaseArtifactV4, ...]) -> CaseInputBundleV4:
    body = {
        "schema_version": value.schema_version, "bundle_id": value.bundle_id,
        "request": value.request.to_dict(), "artifacts": [item.to_dict() for item in artifacts],
    }
    return CaseInputBundleV4.from_dict({**body, "bundle_digest": str(digest_value(body))})


def test_invalid_base64_and_digest_mismatch_fail() -> None:
    item = bundle().artifacts[0]
    with pytest.raises(ContractV4Error, match="INVALID_BASE64"):
        replace(item, content_base64="@@")
    with pytest.raises(ContractV4Error, match="ARTIFACT_DIGEST_MISMATCH"):
        replace(item, content_ref=ContentRefV4(item.content_ref.kind, DigestV4.from_bytes(b"wrong")))


def test_duplicate_id_and_reference_fail() -> None:
    value = bundle()
    item = value.artifacts[0]
    second_content = b"different"
    second = CaseArtifactV4(
        item.artifact_id,
        ContentRefV4(item.content_ref.kind, DigestV4.from_bytes(second_content)),
        item.artifact_kind, item.media_type, item.scope, "ZGlmZmVyZW50",
    )
    with pytest.raises(ContractV4Error, match="ARTIFACT_ID_COLLISION"):
        _rebuild(value, (item, second))
    with pytest.raises(ContractV4Error, match="ARTIFACT_REFERENCE_COLLISION"):
        _rebuild(value, (item, replace(item, artifact_id="other")))


def test_pack_override_and_configured_limits_fail() -> None:
    value = bundle()
    item = value.artifacts[0]
    request = replace(value.request, rule_pack_ref=item.content_ref)
    override_body = {
        "schema_version": value.schema_version, "bundle_id": value.bundle_id,
        "request": request.to_dict(), "artifacts": [item.to_dict()],
    }
    with pytest.raises(ContractV4Error, match="PACK_OVERRIDE"):
        CaseInputBundleV4.from_dict({
            **override_body, "bundle_digest": str(digest_value(override_body)),
        })
    second_content = b"different"
    second = CaseArtifactV4(
        "other", ContentRefV4(item.content_ref.kind, DigestV4.from_bytes(second_content)),
        item.artifact_kind, item.media_type, item.scope, "ZGlmZmVyZW50",
    )
    with pytest.raises(ContractV4Error, match="CASE_ARTIFACT_COUNT"):
        CaseInputBundleV4.from_json_bytes(
            _rebuild(value, (item, second)).canonical_bytes(),
            limits=replace(ResourceLimitsV4(), max_case_artifacts=1),
        )


def test_unknown_path_field_is_rejected() -> None:
    payload = bundle().to_dict()
    payload["artifacts"][0]["path"] = "C:/private.txt"
    with pytest.raises(ContractV4Error, match="UNKNOWN_FIELD"):
        CaseInputBundleV4.from_dict(payload)
