from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "tests/semantic_mutation/critical-v4-mutations.json"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def _selector_function(selector: str) -> tuple[Path, str]:
    path, separator, function = selector.partition("::")
    assert separator and function and "::" not in function
    return ROOT / path, function


def _function_source(path: Path, function: str) -> str:
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == function
    )
    return ast.get_source_segment(source, node) or ""


def test_mutation_ledger_is_closed_and_cannot_mask_survivors_with_a_score() -> None:
    ledger = _load(LEDGER)
    assert set(ledger) == {
        "schema_version", "policy", "mutations", "deferred_runtime_closure",
    }
    assert ledger["schema_version"] == "jc/v4-semantic-mutation-ledger/1.0"
    assert ledger["policy"] == {
        "owner_task": "W3-05",
        "survivors_allowed": 0,
        "aggregate_percentage_gate": False,
    }
    assert "status" not in LEDGER.read_text(encoding="utf-8")


def test_exact_six_critical_mutations_have_fixed_owners_and_case_counts() -> None:
    mutations = _load(LEDGER)["mutations"]
    assert all(set(item) == {
        "id", "audit_id", "repair_task", "selector", "expected_cases", "oracle",
    } for item in mutations)
    assert [
        (item["id"], item["audit_id"], item["repair_task"], item["expected_cases"])
        for item in mutations
    ] == [
        ("IR-LOSS", "P1-05", "W3-01", 6),
        ("PRIORITY-IGNORED", "P1-06", "W3-02", 1),
        ("UNDEC-ACCEPTED", "P1-06", "W3-02", 1),
        ("WITNESS-OVERWRITE", "P1-06", "W3-02", 1),
        ("NAMESPACE-DOMAIN-LOSS", "P1-07", "W2-03", 1),
        ("PROVIDER-FAKE-RECEIPT", "P0-06", "W3-03", 1),
    ]
    assert len({item["id"] for item in mutations}) == 6
    assert len({item["selector"] for item in mutations}) == 6
    assert sum(item["expected_cases"] for item in mutations) == 11


def test_every_critical_selector_is_declared_and_has_no_bypass() -> None:
    for item in _load(LEDGER)["mutations"]:
        path, function = _selector_function(item["selector"])
        source = _function_source(path, function)
        assert source
        tree = ast.parse(source)
        controls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"skip", "skipif", "xfail"}
        }
        assert controls == set()


def test_mutation_oracles_do_not_reuse_the_algorithm_under_test() -> None:
    ir_source = _function_source(
        ROOT / "tests/semantic_mutation/test_ir_mutation.py",
        "_independent_structural_projection",
    )
    assert not any(token in ir_source for token in (
        "LegalIRCompilerV4", "compile_rule", "_project_rule_to_spec",
        "_project_spec_to_ivl",
    ))

    grounded_source = _function_source(
        ROOT / "tests/semantic_mutation/test_argumentation_mutation.py",
        "_independent_grounded",
    )
    assert "evaluate_argument_graph" not in grounded_source

    domain_source = _function_source(
        ROOT / "tests/semantic_mutation/test_domain_provider_mutation.py",
        "_independent_domain_projection",
    )
    assert not any(token in domain_source for token in (
        "RulePackVerifierV4", "_validate_config", "domain_bindings",
    ))

    provider_source = _function_source(
        ROOT / "tests/semantic_mutation/test_domain_provider_mutation.py",
        "test_independent_checker_kills_provider_fake_receipt",
    )
    assert "_invoke_provider" in provider_source
    assert ".check(" in provider_source
    assert "receipt=" in provider_source


def test_p1_07_runtime_closure_stays_red_and_owned_by_w4_05() -> None:
    ledger = _load(LEDGER)
    required = _load(ROOT / "tests/required-v4-tests.json")
    task_plan = _load(ROOT / "remediation/v4/tasks.json")
    p1_07 = next(item for item in required["audit_mutations"] if item["audit_id"] == "P1-07")
    task = next(item for item in task_plan["tasks"] if item["id"] == "W3-05")

    assert ledger["deferred_runtime_closure"] == {
        "audit_id": "P1-07",
        "owner_task": "W4-05",
        "selector": p1_07["selector"],
        "state": "RED_AT_TASK",
    }
    assert (p1_07["owner_task"], p1_07["state"]) == ("W4-05", "RED_AT_TASK")
    assert task["audit_ids"] == ["P0-06", "P1-05", "P1-06", "P1-07"]


def test_w3_05_declares_the_independent_ir_replacement() -> None:
    required = _load(ROOT / "tests/required-v4-tests.json")
    rewrite = next(
        item for item in required["rewrite_at_task"]
        if item["id"] == "REWRITE-SHARED-IR-ORACLE"
    )
    assert rewrite["replacement_selector"] == (
        "tests/semantic_mutation/test_ir_mutation.py::"
        "test_independent_oracle_kills_ir_semantic_mutations"
    )
    _function_source(*_selector_function(rewrite["replacement_selector"]))
