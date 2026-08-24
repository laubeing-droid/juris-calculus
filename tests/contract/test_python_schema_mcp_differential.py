"""W1-03 differential contract for V4 Python, JSON Schema, and MCP codecs."""
from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import MISSING, dataclass, fields
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker, validators

from compiler_core import contracts
from compiler_core.canonical_serialization import canonical_bytes, digest_value
from compiler_core import mcp


REPO = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO / "schemas" / "jc-v4.schema.json"
MANIFEST_PATH = REPO / "mcp_manifest.json"
VECTORS_PATH = REPO / "tests" / "contract" / "v4-contract-vectors.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))


STRICT_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
)
StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=STRICT_TYPE_CHECKER,
)
STRICT_FORMAT_CHECKER = FormatChecker()
_CANONICAL_TIME_PATTERN = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"T(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]{0,8}[1-9]))?Z$"
)


@STRICT_FORMAT_CHECKER.checks("jc-canonical-time", raises=ValueError)
def _is_canonical_time(value: object) -> bool:
    """Independent strict-profile calendar oracle for the public Schema."""

    if type(value) is not str:
        return True
    match = _CANONICAL_TIME_PATTERN.fullmatch(value)
    if match is None:
        return False
    datetime(
        int(match["year"]),
        int(match["month"]),
        int(match["day"]),
        int(match["hour"]),
        int(match["minute"]),
        int(match["second"]),
        tzinfo=timezone.utc,
    )
    return True


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "remediate_v4_w1_03", REPO / "tools" / "remediate_v4.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_file_disposition_generator():
    spec = importlib.util.spec_from_file_location(
        "build_file_disposition_w1_03",
        REPO / "tools" / "build_file_disposition.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema_accepts(type_name: str, payload: object) -> bool:
    validator = StrictDraft202012Validator(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": f"#/$defs/{type_name}",
            "$defs": SCHEMA["$defs"],
        },
        format_checker=STRICT_FORMAT_CHECKER,
    )
    return not list(validator.iter_errors(payload))


def _python_accepts(type_name: str, payload: object) -> bool:
    contract_type = contracts.V4_TYPE_REGISTRY[type_name]
    try:
        if isinstance(contract_type, type) and issubclass(
            contract_type, contracts.V4Contract
        ):
            contract_type.from_dict(payload)
        else:
            contract_type.parse(payload)
    except (contracts.ContractV4Error, TypeError, ValueError):
        return False
    return True


def _mcp_accepts(tool_name: str, channel: str, payload: object) -> bool:
    try:
        mcp.decode_tool_payload(tool_name, channel, payload)
    except (contracts.ContractV4Error, TypeError, ValueError):
        return False
    return True


def _tool_type(spec: contracts.ToolSpecV4, channel: str) -> str:
    return {
        "input": spec.input_type,
        "output": spec.output_type,
        "error": spec.error_type,
    }[channel]


@dataclass(frozen=True)
class AcceptanceCase:
    case_id: str
    type_name: str
    payload: object
    accepted: bool


def _acceptance_cases() -> tuple[AcceptanceCase, ...]:
    cases: list[AcceptanceCase] = []
    for type_name in contracts.V4_TYPE_REGISTRY:
        cases.append(AcceptanceCase(
            f"positive-{type_name}",
            type_name,
            deepcopy(VECTORS["objects"][type_name]),
            True,
        ))
    for type_name, payload in VECTORS["scalar_negative"].items():
        cases.append(AcceptanceCase(
            f"scalar-negative-{type_name}", type_name, deepcopy(payload), False
        ))
    for type_name in contracts.V4_OBJECT_REGISTRY:
        payload = deepcopy(VECTORS["objects"][type_name])
        payload["__unknown__"] = True
        cases.append(AcceptanceCase(
            f"unknown-field-{type_name}", type_name, payload, False
        ))
        required = [
            item.name
            for item in fields(contracts.V4_OBJECT_REGISTRY[type_name])
            if item.default is MISSING and item.default_factory is MISSING
        ]
        if required:
            missing = deepcopy(VECTORS["objects"][type_name])
            del missing[required[0]]
            cases.append(AcceptanceCase(
                f"missing-field-{type_name}-{required[0]}", type_name, missing, False
            ))

    capabilities_unknown = deepcopy(VECTORS["objects"]["MCPCapabilitiesInputV4"])
    capabilities_unknown["unknown"] = True
    cases.append(AcceptanceCase(
        "critical-empty-capabilities-unknown",
        "MCPCapabilitiesInputV4",
        capabilities_unknown,
        False,
    ))

    read_float = deepcopy(VECTORS["objects"]["MCPReadArtifactInputV4"])
    read_float["offset"] = 0.0
    cases.append(AcceptanceCase(
        "critical-nested-float", "MCPReadArtifactInputV4", read_float, False
    ))

    verify_bad_date = deepcopy(VECTORS["objects"]["MCPVerifyRunInputV4"])
    verify_bad_date["run_handle"]["expires_at"]["wire"] = "2026-02-30T08:00:00Z"
    cases.append(AcceptanceCase(
        "critical-invalid-calendar", "MCPVerifyRunInputV4", verify_bad_date, False
    ))

    capabilities_engine_three = deepcopy(VECTORS["objects"]["MCPCapabilitiesOutputV4"])
    capabilities_engine_three["engine_version"] = "3.0.2"
    cases.append(AcceptanceCase(
        "critical-engine-major-three",
        "MCPCapabilitiesOutputV4",
        capabilities_engine_three,
        False,
    ))

    evaluate_tuple_string = deepcopy(VECTORS["objects"]["MCPEvaluateInputV4"])
    evaluate_tuple_string["case_bundle"]["request"]["fact_attestation_refs"] = "not-an-array"
    cases.append(AcceptanceCase(
        "critical-tuple-string", "MCPEvaluateInputV4", evaluate_tuple_string, False
    ))
    return tuple(cases)


ACCEPTANCE_CASES = _acceptance_cases()
MCP_CHANNEL_BY_TYPE = {
    _tool_type(spec, channel): (spec.name, channel)
    for spec in mcp.TOOL_SPECS
    for channel in ("input", "output", "error")
}


@pytest.mark.parametrize(
    "case",
    ACCEPTANCE_CASES,
    ids=[case.case_id for case in ACCEPTANCE_CASES],
)
def test_python_schema_mcp_acceptance_sets_match(case: AcceptanceCase) -> None:
    """Match the frozen wire/structural corpus, not every deep typed invariant."""

    assert _python_accepts(case.type_name, case.payload) is case.accepted
    assert _schema_accepts(case.type_name, case.payload) is case.accepted
    if case.type_name in MCP_CHANNEL_BY_TYPE:
        tool_name, channel = MCP_CHANNEL_BY_TYPE[case.type_name]
        assert _mcp_accepts(tool_name, channel, case.payload) is case.accepted


def test_toolspec_manifest_and_runtime_codec_are_one_authority() -> None:
    expected = (
        ("jc_capabilities", "MCPCapabilitiesInputV4", "MCPCapabilitiesOutputV4", "MCPCapabilitiesErrorV4"),
        ("jc_evaluate", "MCPEvaluateInputV4", "MCPEvaluateOutputV4", "MCPEvaluateErrorV4"),
        ("jc_verify_run", "MCPVerifyRunInputV4", "MCPVerifyRunOutputV4", "MCPVerifyRunErrorV4"),
        ("jc_read_artifact", "MCPReadArtifactInputV4", "MCPReadArtifactOutputV4", "MCPReadArtifactErrorV4"),
    )
    assert tuple(
        (spec.name, spec.input_type, spec.output_type, spec.error_type)
        for spec in mcp.TOOL_SPECS
    ) == expected
    assert mcp.runtime_tools_list() == MANIFEST
    assert canonical_bytes(mcp.runtime_tools_list()) == MANIFEST_PATH.read_bytes()
    assert mcp.runtime_resources_list() == {"resources": []}
    assert mcp.tool_spec_digest() == digest_value(
        [spec.to_dict() for spec in mcp.TOOL_SPECS]
    )

    for tool, spec in zip(MANIFEST["tools"], mcp.TOOL_SPECS, strict=True):
        assert tool["name"] == spec.name
        assert tool["description"] == spec.description
        assert tool["inputSchema"] == mcp.standalone_type_schema(spec.input_type)
        assert tool["outputSchema"] == mcp.standalone_type_schema(spec.output_type)
        assert tool["x-jc-errorSchema"] == mcp.standalone_type_schema(spec.error_type)


def test_complete_schema_is_closed_and_resource_limits_are_published() -> None:
    Draft202012Validator.check_schema(SCHEMA)
    assert set(SCHEMA["$defs"]) == set(contracts.V4_TYPE_REGISTRY)
    assert len(SCHEMA["$defs"]) == 75
    assert "contracts_v4" not in json.dumps(SCHEMA, sort_keys=True)

    for type_name, contract_type in contracts.V4_OBJECT_REGISTRY.items():
        definition = SCHEMA["$defs"][type_name]
        assert definition["type"] == "object"
        assert definition["additionalProperties"] is False
        assert set(definition["properties"]) == {item.name for item in fields(contract_type)}
        assert definition["required"] == [
            item.name
            for item in fields(contract_type)
            if item.default is MISSING and item.default_factory is MISSING
        ]

    for type_name in (
        "ExecutionStatusV4",
        "DecisionStatusV4",
        "CompletenessStateV4",
        "CertificateKindV4",
    ):
        assert SCHEMA["$defs"][type_name]["enum"] == [
            item.value for item in contracts.V4_TYPE_REGISTRY[type_name]
        ]

    limit_properties = SCHEMA["$defs"]["ResourceLimitsV4"]["properties"]
    for name, (default, hard_maximum) in contracts.ENGINE_LIMITS_V4.items():
        published = limit_properties[name]
        assert published["default"] == default
        if hard_maximum is None:
            assert published["const"] is None
        else:
            assert (published["minimum"], published["maximum"]) == (1, hard_maximum)
            assert published["x-jc-integer-token"] is True


def test_committed_publications_are_canonical_emitter_bytes() -> None:
    assert mcp.schema_bytes() == SCHEMA_PATH.read_bytes()
    assert mcp.manifest_bytes() == MANIFEST_PATH.read_bytes()
    assert canonical_bytes(SCHEMA) == SCHEMA_PATH.read_bytes()
    assert canonical_bytes(MANIFEST) == MANIFEST_PATH.read_bytes()
    generator = _load_file_disposition_generator()
    disposition = json.loads(
        (REPO / "remediation" / "v4" / "file-disposition.json").read_text(
            encoding="utf-8"
        )
    )
    assert generator.build_document() == disposition
    mcp_entry = next(
        item for item in disposition["paths"]
        if item["path"] == "compiler_core/mcp.py"
    )
    assert {
        key: mcp_entry[key]
        for key in (
            "disposition", "terminal_state", "audit_role", "closure_task", "namespace"
        )
    } == {
        "disposition": "KEEP_REWRITE",
        "terminal_state": "KEEP_REWRITE",
        "audit_role": "CLI/Client/MCP",
        "closure_task": "W5-CUTOVER",
        "namespace": "formal_core",
    }


PUBLICATION_MUTATIONS = (
    ("schema-raw-byte", "schema"),
    ("schema-missing-definition", "schema"),
    ("schema-extra-definition", "schema"),
    ("schema-open-object", "schema"),
    ("schema-limit-drift", "schema"),
    ("manifest-tool-order", "manifest"),
    ("manifest-input-schema", "manifest"),
    ("manifest-tool-name", "manifest"),
)


@pytest.mark.parametrize(
    ("mutation_id", "publication"),
    PUBLICATION_MUTATIONS,
    ids=[item[0] for item in PUBLICATION_MUTATIONS],
)
def test_publication_mutation_fails_generated_gate(
    tmp_path: Path,
    monkeypatch,
    mutation_id: str,
    publication: str,
) -> None:
    runner = _load_runner()
    schema_path = tmp_path / "jc-v4.schema.json"
    manifest_path = tmp_path / "mcp_manifest.json"
    schema_path.write_bytes(mcp.schema_bytes())
    manifest_path.write_bytes(mcp.manifest_bytes())
    assert runner._generated_publication_problems(schema_path, manifest_path) == []

    if mutation_id == "schema-raw-byte":
        schema_path.write_bytes(mcp.schema_bytes() + b"\n")
    elif mutation_id == "schema-missing-definition":
        mutated = mcp.schema_document()
        del mutated["$defs"]["DigestV4"]
        schema_path.write_bytes(canonical_bytes(mutated))
    elif mutation_id == "schema-extra-definition":
        mutated = mcp.schema_document()
        mutated["$defs"]["ExtraV4"] = {"type": "string"}
        schema_path.write_bytes(canonical_bytes(mutated))
    elif mutation_id == "schema-open-object":
        mutated = mcp.schema_document()
        mutated["$defs"]["CaseRequestV4"]["additionalProperties"] = True
        schema_path.write_bytes(canonical_bytes(mutated))
    elif mutation_id == "schema-limit-drift":
        mutated = mcp.schema_document()
        mutated["$defs"]["ResourceLimitsV4"]["properties"]["max_json_depth"][
            "maximum"
        ] += 1
        schema_path.write_bytes(canonical_bytes(mutated))
    elif mutation_id == "manifest-tool-order":
        mutated = mcp.runtime_tools_list()
        mutated["tools"][0], mutated["tools"][1] = mutated["tools"][1], mutated["tools"][0]
        manifest_path.write_bytes(canonical_bytes(mutated))
    elif mutation_id == "manifest-input-schema":
        mutated = mcp.runtime_tools_list()
        mutated["tools"][0]["inputSchema"] = {"type": "object"}
        manifest_path.write_bytes(canonical_bytes(mutated))
    elif mutation_id == "manifest-tool-name":
        mutated = mcp.runtime_tools_list()
        mutated["tools"][0]["name"] = "jc_capabilities_drifted"
        manifest_path.write_bytes(canonical_bytes(mutated))
    else:  # pragma: no cover - the frozen parameter table is exhaustive
        raise AssertionError(mutation_id)
    assert any(
        publication in problem
        for problem in runner._generated_publication_problems(schema_path, manifest_path)
    )
    if mutation_id == "manifest-tool-name":
        manifest_path.write_bytes(canonical_bytes([]))
        monkeypatch.setattr(runner, "V4_SCHEMA_PUBLICATION", schema_path)
        monkeypatch.setattr(runner, "MCP_MANIFEST_PUBLICATION", manifest_path)
        assert runner.cmd_w1_03_publication_gate() == runner.EXIT_GATE_FAIL

        def fail_load():
            raise RuntimeError("mutated staged authority")

        monkeypatch.setattr(runner, "_load_w1_03_mcp_authority", fail_load)
        assert runner.cmd_w1_03_publication_gate() == runner.EXIT_GATE_FAIL


def test_raw_json_codec_rejects_float_and_duplicate_members() -> None:
    payload = deepcopy(VECTORS["objects"]["MCPReadArtifactInputV4"])
    raw = json.dumps(payload, separators=(",", ":")).replace('"offset":0', '"offset":0.0')
    with pytest.raises(ValueError):
        mcp.decode_tool_json("jc_read_artifact", "input", raw)
    with pytest.raises(ValueError):
        mcp.decode_tool_json(
            "jc_capabilities",
            "input",
            b'{"duplicate":1,"duplicate":2}',
        )


def test_runtime_generation_has_no_manifest_path_or_capability_snapshot(
    monkeypatch,
) -> None:
    source_path = REPO / "compiler_core" / "mcp.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            assignments.extend(
                target.id for target in targets if isinstance(target, ast.Name)
            )
    assert assignments.count("TOOL_SPECS") == 1
    assert "DEFAULT_MANIFEST" not in assignments
    assert not any(name.startswith("CAPABILITIES") for name in assignments)
    assert "manifest_path" not in source
    assert "read_text(" not in source and "read_bytes(" not in source

    def fail_read(_self):
        raise AssertionError("runtime attempted to read a repository publication")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    assert [tool["name"] for tool in mcp.runtime_tools_list()["tools"]] == [
        spec.name for spec in mcp.TOOL_SPECS
    ]
    assert mcp.decode_tool_payload("jc_capabilities", "input", {}).to_dict() == {}
