"""Independent W1-02 vectors for the closed V4 Python contract authority."""

from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import MISSING, fields, is_dataclass, replace
import json
from pathlib import Path
from types import UnionType
from typing import Any, Mapping, get_args, get_origin, get_type_hints

import pytest

import compiler_core
import compiler_core.contracts as contracts
from compiler_core.canonical_serialization import digest_value


REPO = Path(__file__).resolve().parents[2]
MATRIX = json.loads(
    (REPO / "tests/fixtures/v4_contract/object-state-matrix.json").read_text(
        encoding="utf-8"
    )
)
FOUNDATION = json.loads(
    (REPO / "tests/fixtures/golden/v4-foundation-contract.json").read_text(
        encoding="utf-8"
    )
)
VECTORS = json.loads(
    (REPO / "tests/contract/v4-contract-vectors.json").read_text(encoding="utf-8")
)

OBJECT_IDS = tuple(
    item["id"] for item in MATRIX["object_types"] if item["schema_kind"] == "object"
)
SCALAR_IDS = tuple(
    item["id"] for item in MATRIX["object_types"] if item["schema_kind"] != "object"
)
FORBIDDEN_OPEN_TYPES = {Any, Mapping, dict, object}
SELF_DIGEST_FIELDS = {
    "TrustPolicyV4": "policy_digest",
    "StorageCapabilityV4": "capability_digest",
    "SourceBundleV4": "bundle_digest",
    "EvidenceManifestV4": "manifest_digest",
    "RuleV4": "rule_digest",
    "PackManifestV4": "manifest_digest",
    "LegalSpecV4": "spec_digest",
    "LegalIVLV4": "ivl_digest",
    "BranchResultV4": "branch_digest",
    "SemanticResultV4": "result_digest",
    "RunIdentityV4": "run_digest",
    "FormalCertificateV4": "certificate_digest",
    "ConflictCertificateV4": "certificate_digest",
    "AuditManifestV4": "manifest_digest",
    "AuditBundleIndexV4": "bundle_digest",
}
SIGNED_SUBJECT_FIELDS = {
    "ArtifactHandleV4": "content_ref",
    "PackSignatureV4": "manifest_ref",
    "FactAttestationV4": "candidate_ref",
    "FactAdmissionReceiptV4": "subject_digest",
    "RulePromotionReceiptV4": "rule_subject_digest",
    "TranslationReceiptV4": "target_ref",
    "SolverReceiptV4": "backend_result_ref",
    "CheckerReceiptV4": "subject_ref",
    "ProofReceiptV4": "subject_ref",
}
SIGNED_MUTATION_PATHS = {
    "ArtifactHandleV4": ("content_ref", "kind"),
    "PackSignatureV4": ("manifest_ref", "kind"),
    "FactAttestationV4": ("candidate_ref", "kind"),
    "FactAdmissionReceiptV4": ("request_ref", "kind"),
    "RulePromotionReceiptV4": ("legal_review_ref", "kind"),
    "TranslationReceiptV4": ("target_ref", "kind"),
    "SolverReceiptV4": ("backend_result_ref", "kind"),
    "CheckerReceiptV4": ("subject_ref", "kind"),
    "ProofReceiptV4": ("subject_ref", "kind"),
}


def _error_code(exc: BaseException) -> str | None:
    return getattr(exc, "code", None)


def _contains_open_type(annotation: object) -> bool:
    origin = get_origin(annotation)
    if annotation in FORBIDDEN_OPEN_TYPES or origin in FORBIDDEN_OPEN_TYPES:
        return True
    return any(_contains_open_type(item) for item in get_args(annotation))


def _limits_payload(**overrides: object) -> dict[str, object]:
    policy = FOUNDATION["resource_limit_policy"]
    payload: dict[str, object] = {
        item["id"]: item["default"] for item in policy["benchmarked_limits"]
    }
    page_policy = policy["artifact_page_policy"]
    payload[page_policy["id"]] = page_policy["default"]
    solver_policy = policy["solver_deadline_policy"]
    payload[solver_policy["id"]] = solver_policy["default"]
    payload.update({item["id"]: None for item in policy["deferred_limits"]})
    payload.update(overrides)
    return payload


def _case_payload() -> dict[str, object]:
    return deepcopy(VECTORS["objects"]["CaseRequestV4"])


def _wire_metrics(value: object, *, depth: int = 1, parent_key: str | None = None) -> dict[str, int]:
    metrics = {
        "nodes": 1,
        "depth": depth,
        "members": 0,
        "max_members": 0,
        "items": 0,
        "max_items": 0,
        "string_bytes": 0,
        "max_string_bytes": 0,
        "references": 0,
    }
    if parent_key is not None and parent_key.endswith("_refs") and type(value) is list:
        metrics["references"] += len(value)
    elif parent_key is not None and parent_key.endswith("_ref"):
        metrics["references"] += 1
    if type(value) is str:
        size = len(value.encode("utf-8"))
        metrics["string_bytes"] = size
        metrics["max_string_bytes"] = size
        return metrics
    children: list[tuple[str | None, object]] = []
    if type(value) is dict:
        metrics["members"] = len(value)
        metrics["max_members"] = len(value)
        for key, nested in value.items():
            key_size = len(key.encode("utf-8"))
            metrics["string_bytes"] += key_size
            metrics["max_string_bytes"] = max(metrics["max_string_bytes"], key_size)
            children.append((key, nested))
    elif type(value) is list:
        metrics["items"] = len(value)
        metrics["max_items"] = len(value)
        children.extend((parent_key, nested) for nested in value)
    for key, nested in children:
        child = _wire_metrics(nested, depth=depth + 1, parent_key=key)
        for name in ("nodes", "members", "items", "string_bytes", "references"):
            metrics[name] += child[name]
        for name in ("depth", "max_members", "max_items", "max_string_bytes"):
            metrics[name] = max(metrics[name], child[name])
    return metrics


def _encoded_case(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _additional_ref() -> dict[str, str]:
    return {"kind": "boundary-probe", "digest": "sha256:" + "f" * 64}


def _wrong_digest(value: str) -> str:
    replacement = "0" if value[7] != "0" else "1"
    return value[:7] + replacement + value[8:]


def _self_digest_body(type_id: str, payload: dict[str, object]) -> dict[str, object]:
    body = deepcopy(payload)
    del body[SELF_DIGEST_FIELDS[type_id]]
    if type_id == "SemanticResultV4":
        del body["runtime_profile"]["backend_receipt_ref"]
        for claim in body["claims"]:
            del claim["proof_receipt_refs"]
            del claim["checker_receipt_refs"]
        del body["receipt_refs"]
    return body


def _refresh_self_digest(type_id: str, payload: dict[str, object]) -> None:
    field_name = SELF_DIGEST_FIELDS[type_id]
    payload[field_name] = str(digest_value(_self_digest_body(type_id, payload)))


def _signed_certificate_envelope(type_id: str, kind: str) -> dict[str, object]:
    certificate_field = "formal" if type_id == "FormalCertificateV4" else "conflict"
    certificate = deepcopy(VECTORS["objects"][type_id])
    payload: dict[str, object] = {
        "kind": kind,
        "formal": certificate if certificate_field == "formal" else None,
        "conflict": certificate if certificate_field == "conflict" else None,
        "service_signature": None,
    }
    unsigned_payload = {
        field_name: field_value
        for field_name, field_value in payload.items()
        if field_name != "service_signature"
    }
    signature = deepcopy(VECTORS["objects"]["SignatureEnvelopeV4"])
    signature["subject_digest"] = certificate["certificate_digest"]
    signature["run_identity_ref"] = deepcopy(certificate["run_identity_ref"])
    signature["payload_digest"] = str(digest_value(unsigned_payload))
    payload["service_signature"] = signature
    return payload


def _mutate_first_nested_digest(value: object, *, skip_key: str) -> bool:
    if type(value) is dict:
        for key, nested in value.items():
            if key != skip_key and (
                key == "digest" or key.endswith("_digest")
            ) and type(nested) is str and nested.startswith("sha256:"):
                value[key] = _wrong_digest(nested)
                return True
            if _mutate_first_nested_digest(nested, skip_key=skip_key):
                return True
    elif type(value) is list:
        for nested in value:
            if _mutate_first_nested_digest(nested, skip_key=skip_key):
                return True
    return False


def test_w0_public_type_set_is_exact_and_distinct() -> None:
    expected = {item["id"] for item in MATRIX["object_types"]}
    assert set(contracts.V4_TYPE_REGISTRY) == expected
    assert len({id(value) for value in contracts.V4_TYPE_REGISTRY.values()}) == 73
    assert set(contracts.V4_TYPE_REGISTRY) == set(VECTORS["objects"])
    assert set(OBJECT_IDS) == set(VECTORS["field_authority"])
    assert dict(contracts._SELF_DIGEST_FIELDS_V4) == SELF_DIGEST_FIELDS
    assert (
        VECTORS["objects"]["PackSignatureV4"]["manifest_ref"]["digest"]
        == VECTORS["objects"]["PackManifestV4"]["manifest_digest"]
    )
    rule_payload = deepcopy(VECTORS["objects"]["RuleV4"])
    promotion_receipt = deepcopy(VECTORS["objects"]["RulePromotionReceiptV4"])
    del rule_payload["rule_digest"]
    del rule_payload["promotion_receipt_refs"]
    promotion_subject = str(digest_value(rule_payload))
    assert promotion_receipt["rule_subject_digest"] == promotion_subject
    assert promotion_receipt["signature"]["subject_digest"] == promotion_subject
    assert (
        VECTORS["objects"]["RuleV4"]["promotion_receipt_refs"][0]["digest"]
        == str(digest_value(promotion_receipt))
    )

    for type_id in OBJECT_IDS:
        model_type = contracts.V4_TYPE_REGISTRY[type_id]
        assert is_dataclass(model_type), type_id
        assert model_type.__dataclass_params__.frozen, type_id
        assert "__slots__" in model_type.__dict__, type_id
        annotations = get_type_hints(model_type)
        if type_id == "MCPCapabilitiesInputV4":
            assert annotations == {}
        else:
            assert annotations, type_id
        assert [field.name for field in fields(model_type)] == VECTORS["field_authority"][type_id]
        assert not any(_contains_open_type(value) for value in annotations.values()), type_id
        assert issubclass(model_type, contracts.V4Contract), type_id


@pytest.mark.parametrize("type_id", OBJECT_IDS)
def test_every_object_positive_round_trip(type_id: str) -> None:
    payload = deepcopy(VECTORS["objects"][type_id])
    model_type = contracts.V4_TYPE_REGISTRY[type_id]
    decoded = model_type.from_dict(payload)
    assert decoded.to_dict() == payload
    assert model_type.from_dict(decoded.to_dict()) == decoded
    assert decoded.canonical_bytes() == model_type.from_dict(payload).canonical_bytes()
    assert isinstance(decoded.canonical_digest(), contracts.DigestV4)
    digest_field = SELF_DIGEST_FIELDS.get(type_id)
    if digest_field is not None:
        expected_body = _self_digest_body(type_id, payload)
        assert decoded.digest_body() == expected_body
        assert contracts.DigestV4.parse(payload[digest_field]) == digest_value(expected_body)
        assert decoded.canonical_digest() == contracts.DigestV4.parse(payload[digest_field])
    subject_field = SIGNED_SUBJECT_FIELDS.get(type_id)
    if subject_field is not None:
        signature = payload["signature"]
        subject = payload[subject_field]
        expected_subject = subject["digest"] if type(subject) is dict else subject
        expected_signed_body = deepcopy(payload)
        del expected_signed_body["signature"]
        assert signature["subject_digest"] == expected_subject
        assert decoded.signature_body() == expected_signed_body
        assert signature["payload_digest"] == str(digest_value(expected_signed_body))


@pytest.mark.parametrize("type_id", OBJECT_IDS)
def test_every_object_rejects_unknown_field(type_id: str) -> None:
    payload = deepcopy(VECTORS["objects"][type_id])
    model_type = contracts.V4_TYPE_REGISTRY[type_id]
    payload["undeclared_extension"] = "forbidden"
    with pytest.raises(contracts.ContractV4Error) as caught:
        model_type.from_dict(payload)
    assert _error_code(caught.value) == "UNKNOWN_FIELD"

    required = [
        item
        for item in fields(model_type)
        if item.default is MISSING and item.default_factory is MISSING
    ]
    if required:
        payload = deepcopy(VECTORS["objects"][type_id])
        payload.pop(required[0].name)
        with pytest.raises(contracts.ContractV4Error) as caught:
            model_type.from_dict(payload)
        assert _error_code(caught.value) == "MISSING_FIELD"

    digest_field = SELF_DIGEST_FIELDS.get(type_id)
    if digest_field is not None:
        valid = deepcopy(VECTORS["objects"][type_id])
        wrong_wire = _wrong_digest(valid[digest_field])
        wrong = deepcopy(valid)
        wrong[digest_field] = wrong_wire
        with pytest.raises(contracts.ContractV4Error) as caught:
            model_type.from_dict(wrong)
        assert _error_code(caught.value) == "SELF_DIGEST_MISMATCH"

        tampered = deepcopy(valid)
        assert _mutate_first_nested_digest(tampered, skip_key=digest_field), type_id
        with pytest.raises(contracts.ContractV4Error) as caught:
            model_type.from_dict(tampered)
        assert _error_code(caught.value) == "SELF_DIGEST_MISMATCH"

        decoded = model_type.from_dict(valid)
        with pytest.raises(contracts.ContractV4Error) as caught:
            replace(decoded, **{digest_field: contracts.DigestV4.parse(wrong_wire)})
        assert _error_code(caught.value) == "SELF_DIGEST_MISMATCH"

    subject_field = SIGNED_SUBJECT_FIELDS.get(type_id)
    if subject_field is not None:
        for signature_digest_field in ("payload_digest", "subject_digest"):
            invalid_signature = deepcopy(VECTORS["objects"][type_id])
            invalid_signature["signature"][signature_digest_field] = _wrong_digest(
                invalid_signature["signature"][signature_digest_field]
            )
            with pytest.raises(contracts.ContractV4Error) as caught:
                model_type.from_dict(invalid_signature)
            assert _error_code(caught.value) == "SIGNATURE_SUBJECT_MISMATCH"

        tampered_body = deepcopy(VECTORS["objects"][type_id])
        current: Any = tampered_body
        mutation_path = SIGNED_MUTATION_PATHS[type_id]
        for segment in mutation_path[:-1]:
            current = current[segment]
        current[mutation_path[-1]] += "-tampered"
        with pytest.raises(contracts.ContractV4Error) as caught:
            model_type.from_dict(tampered_body)
        assert _error_code(caught.value) == "SIGNATURE_SUBJECT_MISMATCH"


@pytest.mark.parametrize("type_id", SCALAR_IDS)
def test_every_scalar_type_round_trips_and_rejects_invalid_wire(type_id: str) -> None:
    scalar_type = contracts.V4_TYPE_REGISTRY[type_id]
    valid_wire = VECTORS["objects"][type_id]
    valid = scalar_type.parse(valid_wire)
    assert str(valid) == valid_wire
    with pytest.raises((contracts.ContractV4Error, ValueError)):
        scalar_type.parse(VECTORS["scalar_negative"][type_id])


def test_case_request_fields_are_exact_and_external_only() -> None:
    assert tuple(field.name for field in fields(contracts.CaseRequestV4)) == (
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
    )
    for forbidden in VECTORS["case_request_forbidden_fields"]:
        payload = _case_payload()
        payload[forbidden] = "caller-authority"
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.CaseRequestV4.from_dict(payload)
        assert _error_code(caught.value) == "UNKNOWN_FIELD"


def test_reference_arrays_reject_string_iterables() -> None:
    for field_name in ("fact_attestation_refs", "requested_outputs", "proposal_refs"):
        payload = _case_payload()
        payload[field_name] = "not-an-array"
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.CaseRequestV4.from_dict(payload)
        assert _error_code(caught.value) == "ARRAY_REQUIRED"
    for field_name in ("fact_attestation_refs", "proposal_refs"):
        payload = _case_payload()
        payload[field_name].append(deepcopy(payload[field_name][0]))
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.CaseRequestV4.from_dict(payload)
        assert _error_code(caught.value) == "DUPLICATE_REFERENCE"
    payload = _case_payload()
    payload["requested_outputs"].append(deepcopy(payload["requested_outputs"][0]))
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.CaseRequestV4.from_dict(payload)
    assert _error_code(caught.value) == "DUPLICATE_REQUESTED_OUTPUT"


def test_nested_float_and_unsafe_integer_are_rejected_recursively() -> None:
    payload = _case_payload()
    payload["legal_context"]["jurisdiction"] = {"nested": [1.5]}
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.CaseRequestV4.from_dict(payload)
    assert _error_code(caught.value) == "FLOAT_FORBIDDEN"

    payload = _case_payload()
    payload["legal_context"]["jurisdiction"] = {"nested": [2**53]}
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.CaseRequestV4.from_dict(payload)
    assert _error_code(caught.value) == "UNSAFE_INTEGER"

    payload = _case_payload()
    payload["request_id"] = "request\u0000hidden"
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.CaseRequestV4.from_dict(payload)
    assert _error_code(caught.value) == "CONTROL_CHARACTER"


def test_decoded_models_do_not_retain_mutable_mappings() -> None:
    payload = _case_payload()
    decoded = contracts.CaseRequestV4.from_dict(payload)
    baseline = decoded.canonical_bytes()
    payload["legal_context"]["jurisdiction"] = "mutated"
    returned = decoded.to_dict()
    returned["legal_context"]["jurisdiction"] = "mutated-again"
    returned["fact_attestation_refs"].append(deepcopy(returned["source_bundle_ref"]))
    assert decoded.canonical_bytes() == baseline


def test_canonical_time_vectors_and_half_open_intervals() -> None:
    policy = FOUNDATION["time_policy"]
    for vector in policy["positive"]:
        value = contracts.CanonicalTimeV4.from_dict({"wire": vector["wire"]})
        assert value.epoch_seconds == vector["epoch_seconds"]
        assert value.nanosecond == vector["nanosecond"]
        assert value.to_dict() == {"wire": vector["wire"]}
    for vector in policy["negative"]:
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.CanonicalTimeV4.from_dict({"wire": vector["wire"]})
        assert _error_code(caught.value) == vector["expected_error"]
    for vector in policy["interval_vectors"]:
        start = contracts.CanonicalTimeV4.from_dict({"wire": vector["start"]})
        end = contracts.CanonicalTimeV4.from_dict({"wire": vector["end"]})
        for probe in vector["probes"]:
            instant = contracts.CanonicalTimeV4.from_dict({"wire": probe["instant"]})
            assert contracts.CanonicalTimeV4.contains_half_open(start, end, instant) is probe["contains"]


def test_money_and_rational_vectors_match_foundation() -> None:
    policy = FOUNDATION["numeric_policy"]
    for vector in policy["positive"]:
        if vector["kind"] == "integer":
            assert contracts.validate_safe_integer_v4(vector["value"]) == vector["value"]
        elif vector["kind"] == "money":
            assert contracts.validate_money_v4(vector["value"]) == (
                vector["value"]["currency"],
                vector["value"]["minor_units"],
            )
        else:
            assert contracts.validate_rational_v4(vector["value"]) == (
                vector["value"]["numerator"],
                vector["value"]["denominator"],
            )
    for vector in policy["negative"]:
        validator = {
            "integer": contracts.validate_safe_integer_v4,
            "money": contracts.validate_money_v4,
            "rational": contracts.validate_rational_v4,
        }[vector["kind"]]
        with pytest.raises(contracts.ContractV4Error) as caught:
            validator(vector["value"])
        assert _error_code(caught.value) == vector["expected_error"]


def test_engine_limits_match_frozen_foundation() -> None:
    policy = FOUNDATION["resource_limit_policy"]
    bounded_limits = [
        *policy["benchmarked_limits"],
        policy["artifact_page_policy"],
        policy["solver_deadline_policy"],
    ]
    limits = contracts.ResourceLimitsV4.from_dict(_limits_payload())
    assert limits.to_dict() == _limits_payload()
    assert contracts.DEFAULT_RESOURCE_LIMITS_V4 == {
        item["id"]: item["default"] for item in bounded_limits
    }
    assert contracts.HARD_MAX_RESOURCE_LIMITS_V4 == {
        item["id"]: item["hard_max"] for item in bounded_limits
    }
    assert contracts.RESOURCE_LIMIT_ERROR_CODES_V4 == {
        item["id"]: item["error_code"] for item in bounded_limits
    }
    for item in policy["deferred_limits"]:
        payload = _limits_payload(**{item["id"]: 1})
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.ResourceLimitsV4.from_dict(payload)
        assert _error_code(caught.value) == "DEFERRED_LIMIT"

    for bounded in (
        policy["artifact_page_policy"],
        policy["solver_deadline_policy"],
    ):
        accepted = _limits_payload(**{bounded["id"]: bounded["hard_max"]})
        assert contracts.ResourceLimitsV4.from_dict(accepted).to_dict() == accepted
        rejected = _limits_payload(**{bounded["id"]: bounded["hard_max"] + 1})
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.ResourceLimitsV4.from_dict(rejected)
        assert _error_code(caught.value) == bounded["error_code"]


@pytest.mark.parametrize(
    "limit",
    FOUNDATION["resource_limit_policy"]["benchmarked_limits"],
    ids=lambda item: item["id"],
)
def test_each_admission_limit_is_inclusive_and_plus_one_fails(limit: dict[str, object]) -> None:
    accepted = _limits_payload(**{limit["id"]: limit["hard_max"]})
    assert contracts.ResourceLimitsV4.from_dict(accepted).to_dict() == accepted
    rejected = _limits_payload(**{limit["id"]: limit["hard_max"] + 1})
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.ResourceLimitsV4.from_dict(rejected)
    assert _error_code(caught.value) == limit["error_code"]

    limit_id = limit["id"]
    payload = _case_payload()
    encoded = _encoded_case(payload)
    metrics = _wire_metrics(payload)
    configured_value: int
    overflowing_payload = deepcopy(payload)
    if limit_id == "max_request_bytes":
        configured_value = len(encoded)
        overflowing_bytes = encoded + b" "
    elif limit_id == "max_json_depth":
        configured_value = metrics["depth"]
        overflowing_payload["legal_context"]["jurisdiction"] = {
            "probe": {"deeper": "x"}
        }
        overflowing_bytes = _encoded_case(overflowing_payload)
    elif limit_id == "max_json_nodes":
        configured_value = metrics["nodes"]
        overflowing_payload["unexpected"] = None
        overflowing_bytes = _encoded_case(overflowing_payload)
    elif limit_id == "max_object_members_per_object":
        configured_value = metrics["max_members"]
        overflowing_payload["unexpected"] = None
        overflowing_bytes = _encoded_case(overflowing_payload)
    elif limit_id == "max_total_object_members":
        configured_value = metrics["members"]
        overflowing_payload["unexpected"] = None
        overflowing_bytes = _encoded_case(overflowing_payload)
    elif limit_id == "max_array_items_per_array":
        configured_value = metrics["max_items"]
        overflowing_payload["proposal_refs"].append(_additional_ref())
        overflowing_bytes = _encoded_case(overflowing_payload)
    elif limit_id == "max_total_array_items":
        configured_value = metrics["items"]
        overflowing_payload["proposal_refs"].append(_additional_ref())
        overflowing_bytes = _encoded_case(overflowing_payload)
    elif limit_id == "max_string_utf8_bytes":
        configured_value = metrics["max_string_bytes"]
        overflowing_payload["request_id"] = "x" * (configured_value + 1)
        overflowing_bytes = _encoded_case(overflowing_payload)
    elif limit_id == "max_total_string_utf8_bytes":
        configured_value = metrics["string_bytes"]
        overflowing_payload["request_id"] += "x"
        overflowing_bytes = _encoded_case(overflowing_payload)
    elif limit_id == "max_total_reference_values":
        configured_value = metrics["references"]
        overflowing_payload["proposal_refs"].append(_additional_ref())
        overflowing_bytes = _encoded_case(overflowing_payload)
    elif limit_id == "max_fact_attestation_refs":
        configured_value = len(payload["fact_attestation_refs"])
        overflowing_payload["fact_attestation_refs"].append(_additional_ref())
        overflowing_bytes = _encoded_case(overflowing_payload)
    elif limit_id == "max_proposal_refs":
        configured_value = len(payload["proposal_refs"])
        overflowing_payload["proposal_refs"].append(_additional_ref())
        overflowing_bytes = _encoded_case(overflowing_payload)
    else:
        configured_value = limit["hard_max"]
        overflowing_bytes = encoded

    runtime_limits = contracts.ResourceLimitsV4.from_dict(
        _limits_payload(**{limit_id: configured_value})
    )
    if limit_id != "admission_deadline_ms":
        assert contracts.CaseRequestV4.from_json_bytes(
            encoded, limits=runtime_limits
        ).to_dict() == payload
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.CaseRequestV4.from_json_bytes(
                overflowing_bytes, limits=runtime_limits
            )
        assert _error_code(caught.value) == limit["error_code"]
    else:
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.CaseRequestV4.from_json_bytes(
                encoded, limits=runtime_limits, deadline_ns=0
            )
        assert _error_code(caught.value) == "ADMISSION_DEADLINE"


def test_admission_enforcement_order_is_fail_closed() -> None:
    tiny = contracts.ResourceLimitsV4.from_dict(_limits_payload(max_request_bytes=20))
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.CaseRequestV4.from_json_bytes(b"\xff" * 21, limits=tiny)
    assert _error_code(caught.value) == "REQUEST_TOO_LARGE"

    shallow = contracts.ResourceLimitsV4.from_dict(
        _limits_payload(max_request_bytes=100, max_json_depth=2)
    )
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.CaseRequestV4.from_json_bytes(
            b"{\"a\":{\"b\":{\"c\":1.5}}}", limits=shallow
        )
    assert _error_code(caught.value) == "JSON_DEPTH_LIMIT"

    generous = contracts.ResourceLimitsV4.from_dict(_limits_payload())
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.CaseRequestV4.from_json_bytes(b'{"a":1,"a":2}', limits=generous)
    assert _error_code(caught.value) == "DUPLICATE_KEY"

    encoded = json.dumps(_case_payload(), separators=(",", ":")).encode("utf-8")
    assert contracts.CaseRequestV4.from_json_bytes(encoded, limits=generous).to_dict() == _case_payload()
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.CaseRequestV4.from_json_bytes(
            encoded, limits=generous, deadline_ns=0
        )
    assert _error_code(caught.value) == "ADMISSION_DEADLINE"


@pytest.mark.parametrize("depth", (2_048, 3_072))
def test_deep_json_bombs_fail_as_depth_errors_before_recursive_decode(depth: int) -> None:
    bomb = b'{"probe":' + b"[" * depth + b"0" + b"]" * depth + b"}"
    limits = contracts.ResourceLimitsV4.from_dict(_limits_payload())

    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.CaseRequestV4.from_json_bytes(bomb, limits=limits)
    assert _error_code(caught.value) == "JSON_DEPTH_LIMIT"


def test_engine_major_four_is_exact() -> None:
    assert contracts.require_engine_match("4.0.0") == "4.0.0"
    assert contracts.require_engine_match("4.0.0rc1") == "4.0.0rc1"
    for value in ("3.0.2", "5.0.0", "04.0.0", "4", "4.0", "v4.0.0", "4.0.0+local"):
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.require_engine_match(value)
        assert _error_code(caught.value) == "ENGINE_VERSION_MISMATCH"


def test_v3_classes_aliases_and_imports_are_absent() -> None:
    old_names = {
        "CanonicalResult",
        "CaseRequest",
        "CertificateKind",
        "ContractValidationError",
        "ExecutionStatus",
        "MissingFactReview",
        "ResultStatus",
        "RulePackDescriptor",
        "SemanticResult",
    }
    assert not (old_names & set(vars(contracts)))
    assert not (old_names & set(vars(compiler_core)))

    source = (REPO / "compiler_core/contracts.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = {
        "compiler_core.compat_v3_v4",
        "compiler_core.contracts_v4",
        "compiler_core.jcs",
        "compiler_core.types",
    }
    assert not any(
        isinstance(node, ast.ImportFrom) and node.module in forbidden_modules
        or isinstance(node, ast.Import)
        and any(alias.name in forbidden_modules for alias in node.names)
        for node in ast.walk(tree)
    )
    for locator in (
        "C:\\case\\source.pdf",
        "/etc/passwd",
        "\\\\host\\share",
        "a/../b",
        "file:///C:/Users/being/secret.pdf",
        "file://server/share/secret.pdf",
        "file:C:/Users/being/secret.pdf",
        "C:case-secret.pdf",
    ):
        payload = deepcopy(VECTORS["objects"]["CanonicalLocatorV4"])
        payload["value"] = locator
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.CanonicalLocatorV4.from_dict(payload)
        assert _error_code(caught.value) == "UNSAFE_LOCATOR"

    for field_name, invalid_value, expected_code in (
        ("attack_type", "invented_attack_kind", "ATTACK_TYPE"),
        ("target_aspect", "invented_target", "ATTACK_TARGET_ASPECT"),
    ):
        invalid_attack = deepcopy(VECTORS["objects"]["AttackV4"])
        invalid_attack[field_name] = invalid_value
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.AttackV4.from_dict(invalid_attack)
        assert _error_code(caught.value) == expected_code

    for field_name, invalid_value, expected_code in (
        ("status", "invented_permission_state", "PERMISSION_STATUS"),
        ("witness_refs", [], "PERMISSION_WITNESS_REQUIRED"),
    ):
        invalid_permission = deepcopy(VECTORS["objects"]["PermissionResolutionV4"])
        invalid_permission[field_name] = invalid_value
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.PermissionResolutionV4.from_dict(invalid_permission)
        assert _error_code(caught.value) == expected_code

    for forbidden_field in ("semantic_result_ref", "observability_ref"):
        invalid_solver_receipt = deepcopy(VECTORS["objects"]["SolverReceiptV4"])
        invalid_solver_receipt[forbidden_field] = deepcopy(
            VECTORS["objects"]["ContentRefV4"]
        )
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.SolverReceiptV4.from_dict(invalid_solver_receipt)
        assert _error_code(caught.value) == "UNKNOWN_FIELD"

    for type_id, forbidden_field in (
        ("RulePromotionReceiptV4", "rule_ref"),
        ("PackManifestV4", "signature_ref"),
    ):
        cyclic_payload = deepcopy(VECTORS["objects"][type_id])
        cyclic_payload[forbidden_field] = deepcopy(VECTORS["objects"]["ContentRefV4"])
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.V4_TYPE_REGISTRY[type_id].from_dict(cyclic_payload)
        assert _error_code(caught.value) == "UNKNOWN_FIELD"

    error_payload = deepcopy(VECTORS["objects"]["ErrorV4"])
    for transport_payload in (
        {"status": "success", "error": error_payload},
        {"status": "error", "error": None},
    ):
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.TransportOutcomeV4.from_dict(transport_payload)
        assert _error_code(caught.value) == "TRANSPORT_OUTCOME"

    for forbidden_field, value in (
        ("certificate", None),
        ("transport_outcome", {"status": "success", "error": None}),
    ):
        inline_envelope = deepcopy(VECTORS["objects"]["SemanticResultV4"])
        inline_envelope[forbidden_field] = value
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.SemanticResultV4.from_dict(inline_envelope)
        assert _error_code(caught.value) == "UNKNOWN_FIELD"

    formal_result = deepcopy(VECTORS["objects"]["SemanticResultV4"])
    formal_result.update({
        "decision_status": "accepted_formal_result",
        "review_state": {
            "status": "not_required",
            "unresolved_item_refs": [],
            "responsible_role": None,
            "release_condition_refs": [],
            "review_receipt_ref": None,
        },
        "completeness_state": "complete",
        "certificate_kind": "formal_verified",
        "taint_codes": [],
    })
    _refresh_self_digest("SemanticResultV4", formal_result)
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.SemanticResultV4.from_dict(formal_result)
    assert _error_code(caught.value) == "FORMAL_KERNEL_REQUIRED"

    formal_result["runtime_profile"]["formal_kernel"] = True
    _refresh_self_digest("SemanticResultV4", formal_result)
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.SemanticResultV4.from_dict(formal_result)
    assert _error_code(caught.value) == "FORMAL_CLAIM_REQUIRED"

    formal_result["claims"] = [deepcopy(VECTORS["objects"]["ClaimResultV4"])]
    formal_result["runtime_profile"]["backend_invocation_ref"] = deepcopy(
        VECTORS["objects"]["ContentRefV4"]
    )
    formal_result["runtime_profile"]["backend_receipt_ref"] = deepcopy(
        VECTORS["objects"]["ContentRefV4"]
    )
    _refresh_self_digest("SemanticResultV4", formal_result)
    formal_decoded = contracts.SemanticResultV4.from_dict(formal_result)
    assert formal_decoded.to_dict() == formal_result

    for claim_binding in ("argument_refs", "fact_refs", "rule_refs", "source_refs"):
        incomplete_formal_result = deepcopy(formal_result)
        incomplete_formal_result["claims"][0][claim_binding] = []
        _refresh_self_digest("SemanticResultV4", incomplete_formal_result)
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.SemanticResultV4.from_dict(incomplete_formal_result)
        assert _error_code(caught.value) == "FORMAL_CLAIM_BINDING_REQUIRED"

    receipt_variant = deepcopy(formal_result)
    receipt_variant["runtime_profile"]["backend_receipt_ref"]["kind"] += "-variant"
    receipt_variant["claims"][0]["proof_receipt_refs"][0]["kind"] += "-variant"
    receipt_variant["claims"][0]["checker_receipt_refs"][0]["kind"] += "-variant"
    receipt_variant["receipt_refs"][0]["kind"] += "-variant"
    receipt_variant_decoded = contracts.SemanticResultV4.from_dict(receipt_variant)
    assert receipt_variant_decoded.canonical_digest() == formal_decoded.canonical_digest()
    assert receipt_variant_decoded.canonical_bytes() != formal_decoded.canonical_bytes()

    for required_field in (
        "impacted_rule_refs",
        "impacted_claim_refs",
        "allowed_answer_types",
        "required_source_kinds",
    ):
        incomplete_requirement = deepcopy(
            VECTORS["objects"]["MissingFactRequirementV4"]
        )
        incomplete_requirement[required_field] = []
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.MissingFactRequirementV4.from_dict(incomplete_requirement)
        assert _error_code(caught.value) == "MISSING_FACT_BINDING_REQUIRED"

    branch_review = {
        "status": "required",
        "unresolved_item_refs": [_additional_ref()],
        "responsible_role": "reviewer",
        "release_condition_refs": [_additional_ref()],
        "review_receipt_ref": None,
    }
    hypothetical_result = deepcopy(VECTORS["objects"]["SemanticResultV4"])
    hypothetical_result.update({
        "decision_status": "hypothetical_result",
        "review_state": branch_review,
        "completeness_state": "complete",
        "certificate_kind": "none",
        "branches": [],
    })
    _refresh_self_digest("SemanticResultV4", hypothetical_result)
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.SemanticResultV4.from_dict(hypothetical_result)
    assert _error_code(caught.value) == "HYPOTHETICAL_ASSUMPTION_REQUIRED"

    hypothetical_result["branches"] = [
        deepcopy(VECTORS["objects"]["BranchResultV4"])
    ]
    _refresh_self_digest("SemanticResultV4", hypothetical_result)
    assert contracts.SemanticResultV4.from_dict(hypothetical_result)
    mixed_hypothetical = deepcopy(hypothetical_result)
    mixed_hypothetical["admitted_fact_refs"] = [
        deepcopy(mixed_hypothetical["branches"][0]["assumption_refs"][0])
    ]
    _refresh_self_digest("SemanticResultV4", mixed_hypothetical)
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.SemanticResultV4.from_dict(mixed_hypothetical)
    assert _error_code(caught.value) == "HYPOTHETICAL_FACT_MIX"

    conflict_result = deepcopy(VECTORS["objects"]["SemanticResultV4"])
    conflict_result.update({
        "decision_status": "conflict_certificate",
        "review_state": branch_review,
        "completeness_state": "complete",
        "certificate_kind": "conflict_verified",
        "claims": [],
        "argument_refs": [],
        "attack_refs": [],
    })
    _refresh_self_digest("SemanticResultV4", conflict_result)
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.SemanticResultV4.from_dict(conflict_result)
    assert _error_code(caught.value) == "CONFLICT_WITNESS_REQUIRED"

    for receipt_field, expected_code in (
        ("claim_refs", "FORMAL_CLAIM_REQUIRED"),
        ("source_receipt_refs", "FORMAL_RECEIPT_CHAIN_REQUIRED"),
        ("evidence_receipt_refs", "FORMAL_RECEIPT_CHAIN_REQUIRED"),
        ("fact_admission_receipt_refs", "FORMAL_RECEIPT_CHAIN_REQUIRED"),
        ("rule_promotion_receipt_refs", "FORMAL_RECEIPT_CHAIN_REQUIRED"),
        ("translation_receipt_refs", "FORMAL_RECEIPT_CHAIN_REQUIRED"),
        ("solver_receipt_refs", "FORMAL_RECEIPT_CHAIN_REQUIRED"),
        ("proof_receipt_refs", "FORMAL_PROOF_REQUIRED"),
        ("checker_receipt_refs", "FORMAL_CHECKER_REQUIRED"),
    ):
        invalid_certificate = deepcopy(VECTORS["objects"]["FormalCertificateV4"])
        invalid_certificate[receipt_field] = []
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.FormalCertificateV4.from_dict(invalid_certificate)
        assert _error_code(caught.value) == expected_code

    for certificate_type, certificate_kind in (
        ("FormalCertificateV4", "formal_verified"),
        ("ConflictCertificateV4", "conflict_verified"),
    ):
        signed_certificate = _signed_certificate_envelope(
            certificate_type, certificate_kind
        )
        decoded_certificate = contracts.CertificateEnvelopeV4.from_dict(
            signed_certificate
        )
        assert decoded_certificate.to_dict() == signed_certificate
        unsigned_certificate = deepcopy(signed_certificate)
        unsigned_certificate["service_signature"] = None
        assert (
            contracts.CertificateEnvelopeV4.from_dict(unsigned_certificate).to_dict()
            == unsigned_certificate
        )
        for digest_field in ("payload_digest", "subject_digest"):
            stale_certificate_signature = deepcopy(signed_certificate)
            stale_certificate_signature["service_signature"][digest_field] = _wrong_digest(
                stale_certificate_signature["service_signature"][digest_field]
            )
            with pytest.raises(contracts.ContractV4Error) as caught:
                contracts.CertificateEnvelopeV4.from_dict(stale_certificate_signature)
            assert _error_code(caught.value) == "CERTIFICATE_SIGNATURE_MISMATCH"
        wrong_run_signature = deepcopy(signed_certificate)
        wrong_run_signature["service_signature"]["run_identity_ref"]["digest"] = (
            _wrong_digest(
                wrong_run_signature["service_signature"]["run_identity_ref"]["digest"]
            )
        )
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.CertificateEnvelopeV4.from_dict(wrong_run_signature)
        assert _error_code(caught.value) == "CERTIFICATE_SIGNATURE_MISMATCH"

    signed_none_certificate = deepcopy(VECTORS["objects"]["CertificateEnvelopeV4"])
    signed_none_certificate["service_signature"] = deepcopy(
        VECTORS["objects"]["SignatureEnvelopeV4"]
    )
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.CertificateEnvelopeV4.from_dict(signed_none_certificate)
    assert _error_code(caught.value) == "CERTIFICATE_ENVELOPE"

    for forbidden_time_field in ("started_at", "completed_at"):
        run_with_observability = deepcopy(VECTORS["objects"]["RunIdentityV4"])
        run_with_observability[forbidden_time_field] = {"wire": "2026-08-22T08:00:00Z"}
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.RunIdentityV4.from_dict(run_with_observability)
        assert _error_code(caught.value) == "UNKNOWN_FIELD"

    reversed_observability = deepcopy(VECTORS["objects"]["ObservabilityEnvelopeV4"])
    reversed_observability["started_at"] = {"wire": "2026-08-22T08:00:01Z"}
    reversed_observability["finished_at"] = {"wire": "2026-08-22T08:00:00Z"}
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.ObservabilityEnvelopeV4.from_dict(reversed_observability)
    assert _error_code(caught.value) == "RUN_TIME_ORDER"

    inline_request = deepcopy(VECTORS["objects"]["CaseRequestV4"])
    request_handle = deepcopy(VECTORS["objects"]["ArtifactHandleV4"])
    for mcp_request in (
        {"request": None, "request_handle": None},
        {"request": inline_request, "request_handle": request_handle},
    ):
        with pytest.raises(contracts.ContractV4Error) as caught:
            contracts.MCPEvaluateInputV4.from_dict(mcp_request)
        assert _error_code(caught.value) == "MCP_REQUEST_SOURCE"

    unsafe_error = deepcopy(VECTORS["objects"]["ErrorV4"])
    unsafe_error["field_path"] = ["C:secret"]
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.ErrorV4.from_dict(unsafe_error)
    assert _error_code(caught.value) == "ERROR_FIELD_PATH"

    open_review = deepcopy(VECTORS["objects"]["ReviewStateV4"])
    open_review["status"] = "required"
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.ReviewStateV4.from_dict(open_review)
    assert _error_code(caught.value) == "REVIEW_STATE_DETAIL"

    envelope = deepcopy(VECTORS["objects"]["EvaluationEnvelopeV4"])
    envelope["certificate"] = _signed_certificate_envelope(
        "FormalCertificateV4", "formal_verified"
    )
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.EvaluationEnvelopeV4.from_dict(envelope)
    assert _error_code(caught.value) == "CERTIFICATE_KIND"

    request_mismatch = deepcopy(VECTORS["objects"]["EvaluationEnvelopeV4"])
    request_mismatch["run_identity"]["request_ref"]["digest"] = str(
        VECTORS["objects"]["DigestV4"]
    )
    _refresh_self_digest("RunIdentityV4", request_mismatch["run_identity"])
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.EvaluationEnvelopeV4.from_dict(request_mismatch)
    assert _error_code(caught.value) == "REQUEST_BINDING_MISMATCH"

    run_mismatch = deepcopy(VECTORS["objects"]["EvaluationEnvelopeV4"])
    run_mismatch["result"]["run_identity_ref"]["digest"] = str(
        VECTORS["objects"]["DigestV4"]
    )
    _refresh_self_digest("SemanticResultV4", run_mismatch["result"])
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.EvaluationEnvelopeV4.from_dict(run_mismatch)
    assert _error_code(caught.value) == "RUN_BINDING_MISMATCH"

    oversized_read = deepcopy(VECTORS["objects"]["MCPReadArtifactInputV4"])
    oversized_read["offset"] = oversized_read["artifact_handle"]["max_bytes"]
    oversized_read["length"] = 1
    with pytest.raises(contracts.ContractV4Error) as caught:
        contracts.MCPReadArtifactInputV4.from_dict(oversized_read)
    assert _error_code(caught.value) == "ARTIFACT_RANGE"
