import yaml

from compiler_core.argumentation import build_attack_edges_from_rules, grounded_extension
from compiler_core.evaluator import FixpointEvaluator
from compiler_core.types import IRState, LegalDomain, LegalFact, LegalRule
from compiler_core.domain_config import DomainConfig
from tools.relevance_sensitivity_runner import run_fixture, run_path
from tools.rule_quality_auditor import audit_rules


def test_evaluator_emits_trace_and_epistemic_status():
    rule = LegalRule("R1", ["A"], "C1", source_anchor="src:1")
    state = IRState(world_id="trace-test", domain=LegalDomain.CIVIL)
    state.facts["A"] = LegalFact("A")

    result = FixpointEvaluator([rule], DomainConfig(domain=LegalDomain.CIVIL)).evaluate(state)
    claim = result.claims["C1"]

    assert claim.execution_trace_id
    assert claim.epistemic_status is not None
    assert claim.proof_trace[0]["rule_id"] == "R1"
    assert claim.source_anchor == "src:1"


def test_explicit_attack_edges_from_rule_metadata():
    rules = [
        LegalRule("R1", ["A"], "C1", attacks=["R2"]),
        LegalRule("R2", ["B"], "C2"),
    ]

    edges = build_attack_edges_from_rules(rules)
    result = grounded_extension([{"id": "C1"}, {"id": "C2"}], edges)

    assert edges == [("C1", "C2")]
    assert "C2" in result["rejected"]


def test_rule_quality_auditor_flags_unknown_exception(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({
        "rules": [{
            "id": "R1",
            "premise_atoms": ["A"],
            "head_claim": "C1",
            "head_type": "HORN",
            "exception_chain": ["MISSING"],
        }]
    }), encoding="utf-8")

    report = audit_rules(path)

    assert report["status"] == "FAIL"
    assert report["blocking_count"] >= 1  # DDL auditor may add modality findings


def test_rule_quality_auditor_strict_source_anchor_and_test_warning(tmp_path):
    rules = tmp_path / "rules.yaml"
    tests = tmp_path / "tests"
    tests.mkdir()
    rules.write_text(yaml.safe_dump({
        "rules": [{
            "id": "R_UNTESTED",
            "premise_atoms": ["A"],
            "head_claim": "C1",
            "head_type": "HORN",
        }]
    }), encoding="utf-8")

    report = audit_rules(rules, strict_source_anchor=True, tests_root=tests)

    assert report["status"] == "FAIL"
    assert any(f["issue"] == "SOURCE_ANCHOR_MISSING" and f["blocking_issue"] for f in report["findings"])
    assert any(f["issue"] == "RULE_ID_NOT_MENTIONED_IN_TESTS" and not f["blocking_issue"] for f in report["findings"])


def test_rule_quality_auditor_flags_duplicate_and_cycles(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({
            "rules": [
                {"id": "R1", "premise_atoms": ["A"], "head_claim": "C1", "head_type": "HORN"},
                {"id": "R1", "premise_atoms": ["B"], "head_claim": "C2", "head_type": "HORN"},
                {"id": "R2", "premise_atoms": ["C"], "head_claim": "C3", "head_type": "HORN", "attacks": ["R3"]},
                {"id": "R3", "premise_atoms": ["D"], "head_claim": "C4", "head_type": "HORN", "attacks": ["R2"]},
            ]
    }), encoding="utf-8")

    report = audit_rules(path)

    assert report["status"] == "FAIL"
    assert any(f["issue"] == "DUPLICATE_RULE_ID" for f in report["findings"])
    assert any(f["issue"] == "RULE_GRAPH_CYCLE" for f in report["findings"])


def test_relevance_sensitivity_fixture_passes():
    report = run_fixture("tests/relevance_sensitivity/contract_basics.yaml")

    assert report["status"] == "PASS"
    assert report["case_count"] == 3


def test_relevance_sensitivity_directory_metrics_pass():
    report = run_path("tests/relevance_sensitivity")

    assert report["status"] == "PASS"
    assert report["fixture_count"] >= 2
    assert report["metrics"]["invariance"] == 1.0
    assert report["metrics"]["statute_confusion"] == 1.0
