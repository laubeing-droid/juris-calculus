from __future__ import annotations

import ast
from dataclasses import fields, replace
from pathlib import Path

import pytest

from compiler_core.canonical_serialization import DigestV4, parse_json_document
from compiler_core.contracts import (
    ContractV4Error,
    LegalIVLV4,
    LegalSpecV4,
    PackSignatureV4,
    RulePromotionReceiptV4,
    RuleV4,
    TranslationReceiptV4,
)
from compiler_core.legal_ir import (
    IR_FIELD_MAPPING_KIND,
    LEGAL_IR_SCOPE,
    LegalIRCompilationV4,
    LegalIRCompilerV4,
)
from compiler_core.rule_packs import (
    JSON_MEDIA_TYPE,
    PACK_SIGNATURE_KIND,
    RULE_PACK_SCOPE,
    RULE_PROMOTION_RECEIPT_KIND,
)
from tests.integration.test_trust_chain import _ChainHarness, _ref


def _compile(rule_id: str = "synthetic-positive"):
    harness = _ChainHarness()
    pack = harness.verify_pack()
    rule_ref = next(
        reference
        for reference, rule in zip(pack.manifest.rule_refs, pack.rules)
        if rule.rule_id == rule_id
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
    return harness, pack, compiler, compilation


def test_public_compiler_consumes_verified_pack_and_emits_exact_typed_chain() -> None:
    _, pack, _, compilation = _compile()

    assert pack.verifier_issued is True
    assert type(compilation) is LegalIRCompilationV4
    assert type(compilation.rule) is RuleV4
    assert type(compilation.spec) is LegalSpecV4
    assert type(compilation.ivl) is LegalIVLV4
    assert compilation.rule_ref in pack.manifest.rule_refs
    assert compilation.spec_ref.digest == compilation.spec.spec_digest
    assert compilation.ivl_ref.digest == compilation.ivl.ivl_digest
    assert compilation.spec.rule_ref == compilation.rule_ref
    assert compilation.ivl.spec_ref == compilation.spec_ref


def test_each_receipt_is_computed_from_exact_canonical_hop() -> None:
    harness, _, _, compilation = _compile()
    hops = (
        (
            compilation.rule_to_spec_receipt,
            compilation.rule_to_spec_receipt_ref,
            compilation.rule_ref,
            compilation.spec_ref,
            tuple(item.name for item in fields(RuleV4)),
        ),
        (
            compilation.spec_to_ivl_receipt,
            compilation.spec_to_ivl_receipt_ref,
            compilation.spec_ref,
            compilation.ivl_ref,
            tuple(item.name for item in fields(LegalSpecV4)),
        ),
    )

    for receipt, receipt_ref, source_ref, target_ref, coverage in hops:
        assert type(receipt) is TranslationReceiptV4
        assert receipt.source_ref == source_ref
        assert receipt.target_ref == target_ref
        assert receipt.field_coverage == coverage
        assert receipt.lost_fields == ()
        assert receipt.defaulted_fields == ()
        assert receipt.unsupported_fields == ()
        assert receipt.status == "PASS"
        assert receipt.signature.subject_digest == target_ref.digest
        assert receipt.signature.run_identity_ref == receipt.run_identity_ref
        assert receipt_ref.digest == DigestV4.from_bytes(receipt.canonical_bytes())
        mapping_raw = harness.resolver.resolve_content(
            receipt.field_mapping_ref,
            expected_artifact_kind=IR_FIELD_MAPPING_KIND,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=LEGAL_IR_SCOPE,
            max_bytes=harness.resolver.max_artifact_bytes,
        )
        mapping = parse_json_document(mapping_raw)
        assert isinstance(mapping, dict)
        assert mapping["source_ref"] == source_ref.to_dict()
        assert mapping["target_ref"] == target_ref.to_dict()
        assert mapping["source_fields"] == list(coverage)
        assert {
            field_name
            for row in mapping["mappings"]
            for field_name in row["source_fields"]
        } == set(coverage)
        assert all(
            row["disposition"] in {
                "preserve",
                "lower",
                "explicitly_unsupported",
            }
            for row in mapping["mappings"]
        )


def test_interpretation_choices_bind_the_verified_legal_approval() -> None:
    harness, _, _, compilation = _compile()
    promotion_ref = compilation.rule.promotion_receipt_refs[0]
    promotion_raw = harness.resolver.resolve_content(
        promotion_ref,
        expected_artifact_kind=RULE_PROMOTION_RECEIPT_KIND,
        expected_media_type=JSON_MEDIA_TYPE,
        expected_scope=RULE_PACK_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    )
    promotion_value = parse_json_document(promotion_raw)
    assert isinstance(promotion_value, dict)
    promotion = RulePromotionReceiptV4.from_dict(promotion_value)

    assert compilation.spec.interpretation_choice_refs == (
        compilation.rule.interpretation_choice_refs
    )
    assert compilation.ivl.interpretation_choice_refs == (
        compilation.spec.interpretation_choice_refs
    )
    assert compilation.ivl.interpretation_approval_refs == (
        promotion.legal_review_ref,
    )


def test_caller_cannot_assert_pass_or_compile_a_bare_rule() -> None:
    harness, pack, compiler, compilation = _compile()
    with pytest.raises(ContractV4Error) as independent_trust:
        LegalIRCompilerV4(
            harness.trust,
            receipt_issuer="synthetic-service-issuer",
            receipt_signer=harness._sign_receipt,
        )
    assert independent_trust.value.code == "IR_INPUT_TYPE"

    with pytest.raises(TypeError):
        compiler.compile_rule(
            pack,
            rule_ref=compilation.rule_ref,
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
            status="PASS",
        )

    with pytest.raises(ContractV4Error) as caught:
        compiler.compile_rule(
            compilation.rule,
            rule_ref=compilation.rule_ref,
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
        )
    assert caught.value.code == "IR_PACK_HANDLE"

    foreign_harness = _ChainHarness()
    foreign_pack = foreign_harness.verify_pack()
    foreign_rule_ref = next(
        reference
        for reference, rule in zip(
            foreign_pack.manifest.rule_refs,
            foreign_pack.rules,
        )
        if rule.rule_id == compilation.rule.rule_id
    )
    with pytest.raises(ContractV4Error) as foreign_handle:
        compiler.compile_rule(
            foreign_pack,
            rule_ref=foreign_rule_ref,
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
        )
    assert foreign_handle.value.code == "IR_PACK_HANDLE"


def test_rule_ref_must_be_an_exact_member_of_the_verified_pack() -> None:
    harness, pack, compiler, compilation = _compile()
    with pytest.raises(ContractV4Error) as caught:
        compiler.compile_rule(
            pack,
            rule_ref=_ref("rule-v4", "not-in-the-pack"),
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
        )
    assert caught.value.code == "IR_RULE_NOT_IN_PACK"

    invalid_contexts = (
        (
            _ref("not-a-rule", "wrong-rule-kind"),
            harness.run_identity_ref,
            harness.now,
        ),
        (
            compilation.rule_ref,
            _ref("not-a-run-identity", "wrong-run-kind"),
            harness.now,
        ),
        (
            compilation.rule_ref,
            harness.run_identity_ref,
            "2026-08-22T11:00:00Z",
        ),
    )
    for rule_ref, run_identity_ref, now in invalid_contexts:
        with pytest.raises(ContractV4Error) as caught:
            compiler.compile_rule(
                pack,
                rule_ref=rule_ref,
                run_identity_ref=run_identity_ref,
                now=now,
            )
        assert caught.value.code == "IR_INPUT_TYPE"


@pytest.mark.parametrize(
    "drift",
    (
        "release-nonce-revoked",
        "promotion-nonce-revoked",
        "release-key-rotated",
        "release-key-unknown",
        "environment-mismatch",
    ),
)
def test_compiler_rejects_verified_pack_after_live_trust_state_drift(
    drift: str,
) -> None:
    harness, pack, compiler, compilation = _compile()

    def resolved(reference, kind, contract):
        raw = harness.resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type=JSON_MEDIA_TYPE,
            expected_scope=RULE_PACK_SCOPE,
            max_bytes=harness.resolver.max_artifact_bytes,
        )
        value = parse_json_document(raw)
        assert isinstance(value, dict)
        return contract.from_dict(value)

    release = resolved(harness.pack_ref, PACK_SIGNATURE_KIND, PackSignatureV4)
    promotion = resolved(
        compilation.rule.promotion_receipt_refs[0],
        RULE_PROMOTION_RECEIPT_KIND,
        RulePromotionReceiptV4,
    )
    if drift == "release-nonce-revoked":
        harness.trust._revoked_nonces = frozenset({release.signature.nonce})
    elif drift == "promotion-nonce-revoked":
        harness.trust._revoked_nonces = frozenset({promotion.signature.nonce})
    elif drift == "release-key-rotated":
        key_id = release.signature.key_id
        harness.trust._keys[key_id] = replace(
            harness.trust._keys[key_id],
            public_key=bytes([71]) * 32,
        )
    elif drift == "release-key-unknown":
        harness.trust._keys.pop(release.signature.key_id)
    else:
        harness.trust.target_environment = "production"

    assert pack.verifier_issued is False
    with pytest.raises(ContractV4Error) as stale:
        _ = pack.status
    assert stale.value.code == "PACK_HANDLE_NOT_ISSUED"

    with pytest.raises(ContractV4Error) as caught:
        compiler.compile_rule(
            pack,
            rule_ref=compilation.rule_ref,
            run_identity_ref=harness.run_identity_ref,
            now=harness.now,
        )
    assert caught.value.code == "IR_PACK_HANDLE"


def test_production_lowering_imports_no_legacy_or_test_oracle() -> None:
    source_path = Path(__import__("compiler_core.legal_ir", fromlist=["x"]).__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert not any(
        name == "tests"
        or name.startswith("tests.")
        or name in {
            "compiler_core.legal_spec_ivl",
            "compiler_core.legal_ir_v3",
        }
        for name in imported
    )
    assert "evaluate_direct_oracle" not in source
    assert "differential_check" not in source
