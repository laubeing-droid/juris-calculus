"""Complete deterministic identity contract for one V4 execution."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import compiler_core.backend_router as backend_module
from compiler_core.backend_router import (
    CERTIFIED_PROVIDER_IDS_V4,
    BackendV4Error,
    backend_profile_digest_v4,
)
from compiler_core.canonical_serialization import DigestV4, canonical_bytes, digest_value
from compiler_core.contracts import (
    CaseRequestV4,
    ContentRefV4,
    ContractV4Error,
    RunIdentityV4,
)


REPO = Path(__file__).resolve().parents[2]
VECTORS = json.loads(
    (REPO / "tests/contract/v4-contract-vectors.json").read_text(encoding="utf-8")
)
DIGEST_FIELDS = (
    "engine_build_digest",
    "wheel_digest",
    "package_digest",
    "schema_digest",
    "tool_spec_digest",
    "lock_digest",
    "runtime_config_digest",
    "algorithm_profile_digest",
    "backend_profile_digest",
)
IDENTITY_AXES = (
    "request_ref",
    "source_bundle_ref",
    "evidence_manifest_ref",
    "fact_attestation_refs",
    "rule_pack_ref",
    "engine_version",
    "engine_source_commit",
    "engine_source_tree",
    *DIGEST_FIELDS[:-1],
    "trust_policy_ref",
    "storage_capability_ref",
    "backend_profile_digest",
)


def _digest(label: str) -> DigestV4:
    return DigestV4.from_bytes(label.encode("utf-8"))


def _ref(kind: str, label: str) -> ContentRefV4:
    return ContentRefV4(kind=kind, digest=_digest(label))


def _request(*, two_facts: bool = False) -> CaseRequestV4:
    payload = deepcopy(VECTORS["objects"]["CaseRequestV4"])
    if two_facts:
        payload["fact_attestation_refs"].append(
            _ref("fact-attestation", "second-fact-attestation").to_dict()
        )
    return CaseRequestV4.from_dict(payload)


def _runtime_inputs() -> dict[str, object]:
    return {
        "engine_version": "4.0.0",
        "engine_source_commit": "1" * 40,
        "engine_source_tree": "2" * 40,
        "engine_build_digest": _digest("engine-build"),
        "wheel_digest": _digest("wheel"),
        "package_digest": _digest("package"),
        "schema_digest": _digest("schema"),
        "tool_spec_digest": _digest("tool-spec"),
        "lock_digest": _digest("lock"),
        "runtime_config_digest": _digest("runtime-config"),
        "algorithm_profile_digest": _digest("algorithm-profile"),
        "trust_policy_ref": _ref("trust-policy", "trust-policy"),
        "storage_capability_ref": _ref("storage-capability", "storage-capability"),
        "backend_profile_digest": backend_profile_digest_v4(solver_deadline_ms=2500),
    }


def _build(
    request: CaseRequestV4 | None = None,
    request_ref: ContentRefV4 | None = None,
    **overrides: object,
) -> RunIdentityV4:
    canonical_request = _request() if request is None else request
    canonical_ref = (
        ContentRefV4(kind="case-request", digest=canonical_request.canonical_digest())
        if request_ref is None
        else request_ref
    )
    runtime = _runtime_inputs()
    runtime.update(overrides)
    return RunIdentityV4.build(canonical_request, canonical_ref, **runtime)


@pytest.mark.parametrize("axis", IDENTITY_AXES)
def test_each_complete_identity_axis_changes_run_digest(axis: str) -> None:
    base = _build()
    payload = base.to_dict()
    original = deepcopy(payload)

    if axis in {
        "request_ref",
        "source_bundle_ref",
        "evidence_manifest_ref",
        "rule_pack_ref",
        "trust_policy_ref",
        "storage_capability_ref",
    }:
        payload[axis]["digest"] = str(_digest(f"changed-{axis}"))
    elif axis == "fact_attestation_refs":
        payload[axis][0]["digest"] = str(_digest("changed-fact-attestation"))
    elif axis == "engine_version":
        payload[axis] = "4.0.1"
    elif axis == "engine_source_commit":
        payload[axis] = "3" * 40
    elif axis == "engine_source_tree":
        payload[axis] = "4" * 40
    else:
        payload[axis] = str(_digest(f"changed-{axis}"))

    body = {key: value for key, value in payload.items() if key != "run_digest"}
    payload["run_digest"] = str(digest_value(body))
    mutated = RunIdentityV4.from_dict(payload)

    assert len(IDENTITY_AXES) == 19
    assert set(IDENTITY_AXES) == set(original) - {"run_digest"}
    assert {
        key for key in original if original[key] != payload[key]
    } == {axis, "run_digest"}
    assert mutated.run_digest != base.run_digest


def test_builder_mirrors_all_request_owned_references() -> None:
    request = _request(two_facts=True)
    request_ref = ContentRefV4(kind="case-request", digest=request.canonical_digest())

    run = _build(request, request_ref)

    assert run.request_ref == request_ref
    assert run.source_bundle_ref == request.source_bundle_ref
    assert run.evidence_manifest_ref == request.evidence_manifest_ref
    assert run.fact_attestation_refs == request.fact_attestation_refs
    assert run.rule_pack_ref == request.rule_pack_ref


def test_builder_rejects_request_ref_for_different_request() -> None:
    request = _request()
    invalid_refs = (
        _ref("case-request", "different-request"),
        ContentRefV4(kind="wrong-kind", digest=request.canonical_digest()),
    )
    for request_ref in invalid_refs:
        with pytest.raises(ContractV4Error) as caught:
            _build(request, request_ref=request_ref)

        assert caught.value.code == "RUN_REQUEST_BINDING"


def test_same_identity_is_stable_across_two_processes() -> None:
    runtime_wire = {
        name: value.to_dict()
        if type(value) is ContentRefV4
        else str(value)
        if type(value) is DigestV4
        else value
        for name, value in _runtime_inputs().items()
    }
    encoded = json.dumps(
        {
            "request": VECTORS["objects"]["CaseRequestV4"],
            "runtime": runtime_wire,
        },
        sort_keys=True,
    )
    script = "\n".join(
        (
            "import json",
            "from compiler_core.canonical_serialization import DigestV4",
            "from compiler_core.contracts import CaseRequestV4, ContentRefV4, RunIdentityV4",
            f"payload = json.loads({encoded!r})",
            "request = CaseRequestV4.from_dict(payload['request'])",
            "runtime = payload['runtime']",
            f"for name in {DIGEST_FIELDS!r}: runtime[name] = DigestV4.parse(runtime[name])",
            "for name in ('trust_policy_ref', 'storage_capability_ref'): runtime[name] = ContentRefV4.from_dict(runtime[name])",
            "request_ref = ContentRefV4(kind='case-request', digest=request.canonical_digest())",
            "print(RunIdentityV4.build(request, request_ref, **runtime).run_digest)",
        )
    )
    outputs = []
    for seed, timezone in (("1", "UTC"), ("987654", "Asia/Shanghai")):
        completed = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=REPO,
            env=dict(os.environ, PYTHONHASHSEED=seed, TZ=timezone),
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )
        outputs.append(completed.stdout.strip())

    assert outputs == [str(_build().run_digest)] * 2


@pytest.mark.parametrize("field", ("started_at", "completed_at"))
def test_run_identity_rejects_observability_fields(field: str) -> None:
    payload = _build().to_dict()
    payload[field] = {"wire": "2026-08-22T08:00:00Z"}

    with pytest.raises(ContractV4Error) as caught:
        RunIdentityV4.from_dict(payload)

    assert caught.value.code == "UNKNOWN_FIELD"


@pytest.mark.parametrize(
    "overrides",
    (
        {
            "solver_deadline_ms": 2500,
            "provider_ids": tuple(reversed(CERTIFIED_PROVIDER_IDS_V4)),
        },
        {"solver_deadline_ms": 2501},
        {"solver_deadline_ms": 2500, "seed": 1},
    ),
    ids=("provider-order", "deadline", "seed"),
)
def test_backend_profile_digest_covers_every_routing_input(
    overrides: dict[str, object],
) -> None:
    baseline = backend_profile_digest_v4(solver_deadline_ms=2500)

    assert backend_profile_digest_v4(**overrides) != baseline


@pytest.mark.parametrize(
    ("constant", "value"),
    (
        ("PROVIDER_VERSION", "1.0.1"),
        ("BACKEND_ROUTING_POLICY_V4", "different-routing-policy"),
        (
            "BACKEND_ROUTE_TABLE_V4",
            tuple(reversed(backend_module.BACKEND_ROUTE_TABLE_V4)),
        ),
    ),
)
def test_backend_profile_digest_covers_fixed_policy_identity(
    monkeypatch: pytest.MonkeyPatch,
    constant: str,
    value: str,
) -> None:
    baseline = backend_profile_digest_v4(solver_deadline_ms=2500)
    monkeypatch.setattr(backend_module, constant, value)

    assert backend_profile_digest_v4(solver_deadline_ms=2500) != baseline


def test_backend_profile_digest_covers_current_provider_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = backend_profile_digest_v4(solver_deadline_ms=2500)
    binary_digest, _, build_inputs = backend_module.provider_runtime_identity()
    changed_inputs = {**build_inputs, "backends": str(_digest("changed-backend-bytes"))}
    changed_package = DigestV4.from_bytes(canonical_bytes(changed_inputs))
    monkeypatch.setattr(
        backend_module,
        "provider_runtime_identity",
        lambda: (binary_digest, changed_package, changed_inputs),
    )

    assert backend_profile_digest_v4(solver_deadline_ms=2500) != baseline


@pytest.mark.parametrize(
    "inputs",
    (
        {"solver_deadline_ms": 0},
        {"solver_deadline_ms": True},
        {"solver_deadline_ms": 2500, "seed": True},
        {"solver_deadline_ms": 2500, "seed": "0"},
        {"solver_deadline_ms": 2500, "provider_ids": list(CERTIFIED_PROVIDER_IDS_V4)},
        {"solver_deadline_ms": 2500, "provider_ids": ()},
        {"solver_deadline_ms": 2500, "provider_ids": ("duplicate", "duplicate")},
        {"solver_deadline_ms": 2500, "provider_ids": ("",)},
    ),
    ids=(
        "zero-deadline",
        "boolean-deadline",
        "boolean-seed",
        "string-seed",
        "provider-list",
        "no-providers",
        "duplicate-provider",
        "empty-provider",
    ),
)
def test_backend_profile_rejects_invalid_input_combinations(
    inputs: dict[str, object],
) -> None:
    with pytest.raises(BackendV4Error) as caught:
        backend_profile_digest_v4(**inputs)

    assert caught.value.code == "BACKEND_PROFILE"


@pytest.mark.parametrize("invalid_part", ("request", "request_ref"))
def test_builder_requires_exact_contract_inputs(invalid_part: str) -> None:
    request = _request()
    request_ref = ContentRefV4(kind="case-request", digest=request.canonical_digest())

    with pytest.raises(ContractV4Error) as caught:
        RunIdentityV4.build(
            request.to_dict() if invalid_part == "request" else request,
            request_ref.to_dict() if invalid_part == "request_ref" else request_ref,
            **_runtime_inputs(),
        )

    assert caught.value.code == "RUN_IDENTITY_INPUT"


def test_builder_rejects_untyped_runtime_materials() -> None:
    request = _request()
    runtime = _runtime_inputs()
    invalid_values = [
        {**runtime, field: str(runtime[field])}
        for field in DIGEST_FIELDS
    ] + [
        {**runtime, field: runtime[field].to_dict()}
        for field in ("trust_policy_ref", "storage_capability_ref")
    ]

    for invalid_runtime in invalid_values:
        with pytest.raises(ContractV4Error) as caught:
            RunIdentityV4.build(
                request,
                ContentRefV4(kind="case-request", digest=request.canonical_digest()),
                **invalid_runtime,
            )

        assert caught.value.code == "RUN_IDENTITY_INPUT"


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    (
        ({"engine_version": "3.0.0"}, "ENGINE_VERSION_MISMATCH"),
        ({"engine_source_commit": "1" * 39}, "SOURCE_IDENTITY"),
        ({"engine_source_commit": "A" * 40}, "SOURCE_IDENTITY"),
        ({"engine_source_tree": "z" * 40}, "SOURCE_IDENTITY"),
    ),
)
def test_builder_rejects_invalid_engine_identity(
    overrides: dict[str, object], expected_code: str
) -> None:
    with pytest.raises(ContractV4Error) as caught:
        _build(**overrides)

    assert caught.value.code == expected_code


def test_run_identity_rejects_stale_self_digest() -> None:
    payload = _build().to_dict()
    payload["engine_version"] = "4.0.1"

    with pytest.raises(ContractV4Error) as caught:
        RunIdentityV4.from_dict(payload)

    assert caught.value.code == "SELF_DIGEST_MISMATCH"
