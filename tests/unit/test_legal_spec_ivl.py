"""W6：P07 双 IR 编译器与翻译收据测试。

用例语义与 tests/fixtures/theory_absorption/p07 对齐：
逐跳 TranslationReceiptV1、lost/defaulted 阻断、差分分类、mutation。
"""

from __future__ import annotations

import pytest

from compiler_core.legal_spec_ivl import (
    LegalSpec,
    RuleV4,
    TranslationError,
    TranslationReceiptV1,
    compile_rule,
    compile_rule_to_spec,
    differential_check,
    evaluate_direct_oracle,
    evaluate_ivl_horn,
    lower_spec_to_ivl,
)


def _rule(**overrides) -> RuleV4:
    payload = dict(
        rule_id="R-APPEAL-PERIOD",
        version="1.0",
        premises=("judgment_served",),
        head_claim="appeal_period_running",
        norm_modality="CONSTITUTIVE",
        exceptions=("force_majeure_extension",),
        temporal_bound={"valid_from": "2022-01-01T00:00:00Z", "valid_to": ""},
        source_locator={"snapshot_ref": "src-cpl-2021", "locator": "art_85"},
        authority_rank=1,
    )
    payload.update(overrides)
    return RuleV4(**payload)


FACTS = frozenset({"judgment_served"})
DECISION_TIME = "2026-03-01T00:00:00Z"


class TestTranslationReceipts:
    def test_each_hop_emits_receipt_with_traceability(self):
        compiled = compile_rule(_rule())
        receipts = compiled["receipts"]
        assert [receipt.hop for receipt in receipts] == ["RuleV4 -> LegalSpec", "LegalSpec -> Legal-IVL"]
        for receipt in receipts:
            assert receipt.status == "PASS"
            assert receipt.source_bytes_hash.startswith("sha256:")
            assert receipt.target_bytes_hash.startswith("sha256:")
            assert receipt.mapping_table
            assert receipt.lost_fields == ()
            assert receipt.defaulted_fields == ()
            assert receipt.receipt_digest

    def test_receipt_rejects_lost_or_defaulted_fields(self):
        with pytest.raises(TranslationError) as exc:
            TranslationReceiptV1(
                hop="LegalSpec -> Legal-IVL",
                translator_version="ivl@1.0",
                source_bytes_hash="sha256:" + "ab" * 32,
                target_bytes_hash="sha256:" + "cd" * 32,
                mapping_table={},
                lost_fields=("exception_chain[1].temporal_bound",),
                defaulted_fields=(),
                proof_obligations=(),
                differential_result="",
                counterexample_ref="",
                status="PASS",
            )
        assert exc.value.code == "LOST_SEMANTIC_FIELD"

    def test_lowering_blocks_on_lost_semantics(self):
        spec, _ = compile_rule_to_spec(_rule())
        broken = LegalSpec(
            rule_ref=spec.rule_ref,
            head_claim="",
            terms=spec.terms,
            conditions=spec.conditions,
            exceptions=spec.exceptions,
            modality=spec.modality,
            temporal_bound=spec.temporal_bound,
            interpretation_choices={},
            source_locator=spec.source_locator,
        )
        with pytest.raises(TranslationError) as exc:
            lower_spec_to_ivl(broken)
        assert exc.value.code == "LOST_SEMANTIC_FIELD"

    def test_exception_becomes_typed_attack_not_negative_fact(self):
        compiled = compile_rule(_rule())
        attacks = compiled["ivl"].exception_attacks
        assert len(attacks) == 1
        assert attacks[0]["attack_type"] == "exception"
        assert attacks[0]["target_aspect"] == "rule_applicability"


class TestDifferential:
    def test_dual_ir_aligns_with_direct_oracle(self):
        result = differential_check(_rule(), FACTS, decision_time=DECISION_TIME)
        assert result["aligned"] is True
        assert result["classification"] == "aligned"

    def test_exception_present_blocks_derivation_both_sides(self):
        facts = FACTS | {"force_majeure_extension"}
        result = differential_check(_rule(), facts, decision_time=DECISION_TIME)
        assert result["aligned"] is True
        assert result["ivl_result"]["holds"] is False
        assert result["oracle_result"]["holds"] is False

    def test_not_applicable_before_valid_from(self):
        result = differential_check(_rule(), FACTS, decision_time="2019-06-01T00:00:00Z")
        assert result["aligned"] is True
        assert result["ivl_result"]["reason"] == "not_applicable_at_time"

    def test_mutation_exception_flip_is_detectable(self):
        """mutation：把 exception 从事实集合移除会改变结论，验证器可捕获。"""

        rule = _rule()
        with_exception = evaluate_direct_oracle(rule, FACTS | {"force_majeure_extension"}, decision_time=DECISION_TIME)
        without_exception = evaluate_direct_oracle(rule, FACTS, decision_time=DECISION_TIME)
        assert with_exception["holds"] != without_exception["holds"]

    def test_oracle_and_ivl_are_independent_implementations(self):
        """同一输入下两条链独立求值；结果一致属于差分证据而非自证。"""

        rule = _rule()
        compiled = compile_rule(rule)
        ivl_result = evaluate_ivl_horn(compiled["ivl"], FACTS, decision_time=DECISION_TIME)
        oracle_result = evaluate_direct_oracle(rule, FACTS, decision_time=DECISION_TIME)
        assert ivl_result["holds"] == oracle_result["holds"] == True
        assert ivl_result["claim"] == oracle_result["claim"] == "appeal_period_running"


class TestRuleValidation:
    def test_missing_temporal_bound_fails_closed(self):
        with pytest.raises(TranslationError) as exc:
            _rule(temporal_bound={})
        assert exc.value.code == "MISSING_REQUIRED_FIELD"

    def test_missing_source_locator_fails_closed(self):
        with pytest.raises(TranslationError) as exc:
            _rule(source_locator={"snapshot_ref": "src"})
        assert exc.value.code == "MISSING_REQUIRED_FIELD"

    def test_unknown_modality_fails_closed(self):
        with pytest.raises(TranslationError) as exc:
            _rule(norm_modality="RECOMMENDATION")
        assert exc.value.code == "INVALID_ENUM"

    def test_duplicate_premises_rejected(self):
        with pytest.raises(TranslationError) as exc:
            _rule(premises=("a", "a"))
        assert exc.value.code == "DUPLICATE_ID"

    def test_rule_canonical_bytes_deterministic(self):
        assert _rule().canonical_bytes() == _rule().canonical_bytes()
