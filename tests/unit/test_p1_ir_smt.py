import yaml

from compiler_core.legal_ir_v3 import Condition, LegalIRRule, LegalType, RuleType, SourceRef, TypedVariable, Validity, legal_ir_rule_from_dict
from compiler_core.smt_sidecar import SMTSidecar
from compiler_core.source_anchor import make_source_anchor, validate_source_anchor
from compiler_core.type_checker import check_legal_ir_rule
from compiler_core.types import LegalRule


def test_legal_rule_converts_to_minimal_ir():
    rule = LegalRule(
        "R1",
        ["Contract_Exists", "Payment_Missing"],
        "Breach_Established",
        source_anchor="civil_code_577#abc",
        valid_from="2021-01-01",
        jurisdiction="PRC",
    )

    ir = LegalIRRule.from_legal_rule(rule)
    report = check_legal_ir_rule(ir)

    assert ir.rule_id == "R1"
    assert report.status == "PASS"


def test_ir_roundtrip_preserves_horn_subset():
    original = LegalRule(
        "R_RT",
        ["A", "B"],
        "C",
        exception_chain=["R_EX"],
        source_anchor="src:rt",
        jurisdiction="PRC",
        priority_over=["R_LOW"],
    )

    roundtrip = LegalIRRule.from_legal_rule(original).to_legal_rule()

    assert roundtrip.id == original.id
    assert roundtrip.premise_atoms == original.premise_atoms
    assert roundtrip.head_claim == original.head_claim
    assert roundtrip.exception_chain == original.exception_chain


def test_type_checker_rejects_unbound_variables_and_missing_source():
    ir = LegalIRRule(
        rule_id="R2",
        rule_type=RuleType.HORN,
        validity=Validity(jurisdiction="PRC"),
        source=SourceRef(authority_id=""),
        variables=[TypedVariable("debtor", LegalType.LEGAL_PERSON)],
        conditions=LegalIRRule.from_legal_rule(LegalRule("X", [], "Y", source_anchor="src:1")).conditions,
        conclusion=Condition(predicate="owes", args=["$creditor"]),
    )

    report = check_legal_ir_rule(ir)

    assert report.status == "FAIL"
    assert "SOURCE_ANCHOR_REQUIRED" in report.issues
    assert "UNBOUND_VARIABLE:$creditor" in report.issues


def test_type_checker_rejects_unknown_refs():
    ir = LegalIRRule.from_legal_rule(LegalRule("R1", ["A"], "C", exception_chain=["R_MISSING"], source_anchor="src:1"))

    report = check_legal_ir_rule(ir, known_rule_ids=["R1"])

    assert report.status == "FAIL"
    assert "UNKNOWN_EXCEPTION_REF:R_MISSING" in report.issues


def test_typed_ir_fixture_passes_core_checker():
    payload = yaml.safe_load(open("tests/fixtures/legal_ir_v3_sample.yaml", encoding="utf-8"))
    rules = [legal_ir_rule_from_dict(raw) for raw in payload["rules"]]

    assert len(rules) == 1
    assert check_legal_ir_rule(rules[0], known_rule_ids=[rule.rule_id for rule in rules]).status == "PASS"


def test_source_anchor_hash_helper():
    anchor = make_source_anchor("civil_code_577", "第五百七十七条")

    assert validate_source_anchor(anchor)
    assert anchor.startswith("civil_code_577#")


def test_smt_sidecar_checks_dates_numbers_and_states():
    result = SMTSidecar().check([
        {"name": "due_before_today", "type": "date", "left": "2024-01-01", "op": "<=", "right": "2024-02-01"},
        {"name": "amount_cap", "left": 100, "op": "<=", "right": 120},
        {"name": "validity_state", "op": "mutually_exclusive", "states": {"VALID": True, "VOID": False}},
    ])

    assert result.status == "SAT"


def test_smt_sidecar_unsat_core_for_failed_constraint():
    result = SMTSidecar().check([
        {"name": "amount_cap", "left": 200, "op": "<=", "right": 120},
    ])

    assert result.status == "UNSAT"
    assert result.unsat_core == ["amount_cap"]


def test_smt_sidecar_limitation_and_money_helpers():
    sidecar = SMTSidecar()

    assert sidecar.check_limitation_period("2024-01-01", "2024-01-10", 30).status == "SAT"
    assert sidecar.check_money_cap(15000, 10000).status == "UNSAT"
