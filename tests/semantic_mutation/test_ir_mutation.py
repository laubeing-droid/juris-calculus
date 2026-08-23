from __future__ import annotations

import inspect

import pytest

from compiler_core.canonical_serialization import (
    DigestV4,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import ContentRefV4, LegalIVLV4, LegalSpecV4, RuleV4
from compiler_core.legal_ir import LegalIRCompilerV4
from compiler_core.rule_packs import JSON_MEDIA_TYPE
from tests.integration.test_trust_chain import _ChainHarness


CRITICAL_MUTATIONS = (
    ("authority_ref", "authority"),
    ("source_locator", "source_locator"),
    ("defined_term_refs", "defined_terms"),
    ("interpretation_choice_refs", "interpretation"),
    ("modality", "modality"),
    ("temporal_constraint_refs", "temporal"),
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


def _mutation_ref(field_name: str) -> ContentRefV4:
    return ContentRefV4(
        f"critical-{field_name}",
        DigestV4.from_bytes(f"critical:{field_name}".encode("utf-8")),
    )


def _mutated_rule(rule: RuleV4, field_name: str) -> RuleV4:
    body = rule.digest_body()
    value = body[field_name]
    if isinstance(value, str):
        body[field_name] = value + "-mutated"
    elif isinstance(value, list):
        body[field_name] = [*value, _mutation_ref(field_name).to_dict()]
    elif isinstance(value, dict):
        if set(value) == {"kind", "digest"}:
            body[field_name] = _mutation_ref(field_name).to_dict()
        else:
            body[field_name] = {
                **value,
                "value": str(value["value"]) + "-mutated",
            }
    else:
        raise AssertionError(f"unsupported critical mutation: {field_name}")
    return RuleV4.from_dict({
        **body,
        "rule_digest": str(digest_value(body)),
    })


def _independent_structural_projection(
    resolver,
    spec: LegalSpecV4,
    ivl: LegalIVLV4,
) -> dict[str, tuple[object, object]]:
    """Test-side structural oracle; it never calls the production lowering."""

    def resolved(reference: ContentRefV4) -> dict:
        value = parse_json_document(resolver.resolve_content(
            reference,
            expected_artifact_kind=reference.kind,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope="legal-ir",
            max_bytes=resolver.max_artifact_bytes,
        ))
        assert isinstance(value, dict)
        return value

    return {
        "authority": (spec.authority_ref, ivl.authority_ref),
        "source_locator": (
            spec.source_locator.to_dict(),
            resolved(ivl.source_map_ref)["source_locator"],
        ),
        "defined_terms": (spec.defined_term_refs, ivl.defined_term_refs),
        "interpretation": (
            spec.interpretation_choice_refs,
            ivl.interpretation_choice_refs,
        ),
        "modality": (spec.modality, resolved(ivl.modality_ref)["modality"]),
        "temporal": (
            spec.temporal_constraint_refs,
            ivl.temporal_constraint_refs,
        ),
    }


@pytest.mark.parametrize(
    ("field_name", "projection_name"),
    CRITICAL_MUTATIONS,
    ids=tuple(item[1] for item in CRITICAL_MUTATIONS),
)
def test_independent_oracle_kills_ir_semantic_mutations(
    ir_context,
    field_name: str,
    projection_name: str,
) -> None:
    harness, compiler, compilation = ir_context
    baseline = _independent_structural_projection(
        harness.resolver, compilation.spec, compilation.ivl,
    )
    mutated_rule = _mutated_rule(compilation.rule, field_name)
    mutated_rule_ref = ContentRefV4(
        compilation.rule_ref.kind,
        mutated_rule.rule_digest,
    )
    mutated_spec, mutated_spec_ref = compiler._project_rule_to_spec(
        mutated_rule,
        rule_ref=mutated_rule_ref,
    )
    mutated_ivl, _ = compiler._project_spec_to_ivl(
        mutated_spec,
        spec_ref=mutated_spec_ref,
        interpretation_approval_refs=compilation.ivl.interpretation_approval_refs,
    )
    observed = _independent_structural_projection(
        harness.resolver, mutated_spec, mutated_ivl,
    )
    expected = {
        "authority": mutated_rule.authority_ref,
        "source_locator": mutated_rule.source_locator.to_dict(),
        "defined_terms": mutated_rule.defined_term_refs,
        "interpretation": mutated_rule.interpretation_choice_refs,
        "modality": mutated_rule.modality,
        "temporal": mutated_rule.temporal_constraint_refs,
    }[projection_name]

    assert baseline[projection_name][0] == baseline[projection_name][1]
    assert observed[projection_name] == (expected, expected)
    assert expected != baseline[projection_name][0]


def test_structural_projection_helper_is_independent() -> None:
    source = inspect.getsource(_independent_structural_projection)
    assert "LegalIRCompilerV4" not in source
    assert "compile_rule" not in source
    assert "_project_rule_to_spec" not in source
    assert "_project_spec_to_ivl" not in source
