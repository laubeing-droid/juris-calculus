from __future__ import annotations

from dataclasses import fields

import pytest

from compiler_core.canonical_serialization import (
    DigestV4,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    ContentRefV4,
    ContractV4Error,
    LegalSpecV4,
    RuleV4,
)
from compiler_core.legal_ir import LegalIRCompilerV4
from compiler_core.rule_packs import JSON_MEDIA_TYPE
from tests.integration.test_trust_chain import _ChainHarness


RULE_FIELDS = tuple(item.name for item in fields(RuleV4))
SPEC_FIELDS = tuple(item.name for item in fields(LegalSpecV4))
FIELD_CASES = (
    *(("rule", field_name) for field_name in RULE_FIELDS),
    *(("spec", field_name) for field_name in SPEC_FIELDS),
)


@pytest.fixture(scope="module")
def ir_context():
    harness = _ChainHarness()
    pack = harness.verify_pack()
    rule_ref = next(
        reference
        for reference, rule in zip(pack.manifest.rule_refs, pack.rules)
        if rule.rule_id == "synthetic-positive"
    )
    compiler = LegalIRCompilerV4(
        harness.pack_verifier,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )
    compilation = compiler.compile_rule(
        pack,
        rule_ref=rule_ref,
        run_identity_ref=harness.run_identity_ref,
        now=harness.now,
    )
    return harness, compiler, compilation


def _resolved_ir_json(harness: _ChainHarness, reference: ContentRefV4) -> dict:
    value = parse_json_document(harness.resolver.resolve_content(
        reference,
        expected_artifact_kind=reference.kind,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope="legal-ir",
        max_bytes=harness.resolver.max_artifact_bytes,
    ))
    assert isinstance(value, dict)
    return value


def _assert_rule_field_preserved(
    rule: RuleV4,
    spec: LegalSpecV4,
    field_name: str,
) -> None:
    if field_name == "rule_id":
        assert spec.spec_id == rule.rule_id
    elif field_name == "rule_digest":
        assert spec.rule_ref.digest == rule.rule_digest
    else:
        assert getattr(spec, field_name) == getattr(rule, field_name)


def _assert_spec_field_preserved(
    harness: _ChainHarness,
    spec: LegalSpecV4,
    ivl,
    field_name: str,
) -> None:
    direct = {
        "authority_ref": "authority_ref",
        "variable_declaration_refs": "variable_declaration_refs",
        "premise_refs": "premise_refs",
        "conclusion_ref": "conclusion_ref",
        "priority_refs": "priority_refs",
        "temporal_constraint_refs": "temporal_constraint_refs",
        "numeric_constraint_refs": "numeric_constraint_refs",
        "interpretation_choice_refs": "interpretation_choice_refs",
        "defined_term_refs": "defined_term_refs",
    }
    if field_name == "spec_id":
        assert ivl.ivl_id == spec.spec_id
    elif field_name == "spec_digest":
        assert ivl.spec_ref.digest == spec.spec_digest
    elif field_name in direct:
        assert getattr(ivl, direct[field_name]) == getattr(spec, field_name)
    elif field_name == "permission_ref":
        assert ivl.permission_refs == (
            (spec.permission_ref,) if spec.permission_ref is not None else ()
        )
    elif field_name == "exception_refs":
        assert ivl.exception_attack_refs[:len(spec.exception_refs)] == spec.exception_refs
    elif field_name == "attack_refs":
        assert ivl.exception_attack_refs[len(spec.exception_refs):] == spec.attack_refs
    elif field_name == "modality":
        assert _resolved_ir_json(harness, ivl.modality_ref)["modality"] == spec.modality
    elif field_name in {
        "jurisdiction",
        "governing_law",
    }:
        assert _resolved_ir_json(harness, ivl.type_environment_ref)[field_name] == (
            getattr(spec, field_name)
        )
    else:
        source_map = _resolved_ir_json(harness, ivl.source_map_ref)
        expected = getattr(spec, field_name)
        if isinstance(expected, tuple):
            expected = [item.to_dict() for item in expected]
        elif hasattr(expected, "to_dict"):
            expected = expected.to_dict()
        assert source_map[field_name] == expected


def _ref_wire(field_name: str) -> dict[str, str]:
    return ContentRefV4(
        f"ir-mutation-{field_name}",
        DigestV4.from_bytes(f"ir-mutation:{field_name}".encode("utf-8")),
    ).to_dict()


def _wrong_digest(value: str) -> str:
    candidate = "sha256:" + "f" * 64
    return candidate if candidate != value else "sha256:" + "e" * 64


def _mutate_wire(field_name: str, value: object) -> object:
    if isinstance(value, str):
        return value + "-mutated"
    if isinstance(value, list):
        return [*value, _ref_wire(field_name)]
    if isinstance(value, dict):
        mutated = dict(value)
        if set(mutated) == {"kind", "digest"}:
            mutated["digest"] = _wrong_digest(str(mutated["digest"]))
        elif set(mutated) == {"wire"}:
            mutated["wire"] = "2023-01-01T00:00:00Z"
        else:
            mutated["value"] = str(mutated["value"]) + "-mutated"
        return mutated
    if value is None:
        if field_name == "permission_ref":
            return _ref_wire(field_name)
        if field_name == "effective_to":
            return {"wire": "2028-01-01T00:00:00Z"}
    raise AssertionError(f"no contract mutation for {field_name}: {value!r}")


def _mutated_contract(value: RuleV4 | LegalSpecV4, field_name: str):
    digest_field = "rule_digest" if type(value) is RuleV4 else "spec_digest"
    payload = value.to_dict()
    if field_name == digest_field:
        payload[field_name] = _wrong_digest(str(payload[field_name]))
    else:
        payload[field_name] = _mutate_wire(field_name, payload[field_name])
        body = {key: item for key, item in payload.items() if key != digest_field}
        payload[digest_field] = str(digest_value(body))
    return type(value).from_dict(payload)


@pytest.mark.parametrize(
    ("layer", "field_name"),
    FIELD_CASES,
    ids=tuple(f"{layer}-{field_name}" for layer, field_name in FIELD_CASES),
)
def test_every_legal_ir_field_survives_lowering_or_blocks(
    ir_context,
    layer: str,
    field_name: str,
) -> None:
    harness, compiler, compilation = ir_context
    digest_field = "rule_digest" if layer == "rule" else "spec_digest"
    source = compilation.rule if layer == "rule" else compilation.spec

    if field_name == digest_field:
        with pytest.raises(ContractV4Error) as caught:
            _mutated_contract(source, field_name)
        assert caught.value.code == "SELF_DIGEST_MISMATCH"
        return

    mutated = _mutated_contract(source, field_name)
    if layer == "rule":
        mutated_ref = ContentRefV4(compilation.rule_ref.kind, mutated.rule_digest)
        target, target_ref = compiler._project_rule_to_spec(
            mutated,
            rule_ref=mutated_ref,
        )
        _assert_rule_field_preserved(mutated, target, field_name)
        assert target_ref != compilation.spec_ref
    else:
        mutated_ref = ContentRefV4(compilation.spec_ref.kind, mutated.spec_digest)
        target, target_ref = compiler._project_spec_to_ivl(
            mutated,
            spec_ref=mutated_ref,
            interpretation_approval_refs=(
                compilation.ivl.interpretation_approval_refs
            ),
        )
        _assert_spec_field_preserved(harness, mutated, target, field_name)
        assert target_ref != compilation.ivl_ref
