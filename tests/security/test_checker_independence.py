from __future__ import annotations

import ast
from base64 import b64decode, b64encode
from dataclasses import replace
from pathlib import Path

import pytest

import compiler_core.argumentation as argumentation_module
import compiler_core.backend_router as backend_module
import compiler_core.backends as backends_module
import compiler_core.independent_checker as checker_module
import compiler_core.legal_ir as legal_ir_module
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
)
from compiler_core.contracts import (
    CheckerReceiptV4,
    ContentRefV4,
    ContractV4Error,
    RunIdentityV4,
    SolverReceiptV4,
)
from compiler_core.independent_checker import (
    BACKEND_INVOCATION_KIND,
    BACKEND_PROBLEM_KIND,
    BACKEND_PROOF_KIND,
    BACKEND_RESULT_KIND,
    BACKEND_SCOPE,
    CHECKER_RECEIPT_KIND,
    CHECKER_SCOPE,
    HORN_PROVIDER_ID,
    IndependentCheckerV4Error,
)
from compiler_core.fact_admission import RUN_IDENTITY_KIND, RUN_IDENTITY_SCOPE
from tests.contract.test_backend_router import _execute, _provider
from tests.contract.test_independent_checker import _checker, _json
from tests.integration.test_trust_chain import _ChainHarness


@pytest.fixture(scope="module")
def checked_chain():
    harness, _, _, _, _, executions = _execute(
        "synthetic-exception-priority",
        "synthetic-missing-disputed",
        "synthetic-positive",
    )
    checker = _checker(harness)
    horn = _provider(executions, HORN_PROVIDER_ID)
    aaf = _provider(executions, checker_module.AAF_PROVIDER_ID)
    horn_checked = checker.check(
        run_identity_ref=harness.run_identity_ref,
        solver_receipt_ref=horn.receipt_ref,
        now=harness.now,
    )
    aaf_checked = checker.check(
        run_identity_ref=harness.run_identity_ref,
        solver_receipt_ref=aaf.receipt_ref,
        now=harness.now,
    )
    return harness, checker, horn, aaf, horn_checked, aaf_checked


def _error_code(call) -> str:
    with pytest.raises((IndependentCheckerV4Error, ContractV4Error)) as caught:
        call()
    return caught.value.code


def _wire_ref(value: object) -> ContentRefV4:
    assert type(value) is dict
    return ContentRefV4.from_dict(value)


def _stage_checker_receipt(
    harness: _ChainHarness,
    receipt: CheckerReceiptV4,
    *,
    changes: dict[str, object] | None = None,
    signer: str = "service",
    signature_evidence: tuple[ContentRefV4, ...] | None = None,
    corrupt_signature: bool = False,
) -> ContentRefV4:
    body = receipt.signature_body()
    body.update(changes or {})
    subject_ref = _wire_ref(body["subject_ref"])
    run_ref = _wire_ref(body["run_identity_ref"])
    witnesses = tuple(_wire_ref(item) for item in body["witness_refs"])
    evidence = witnesses if signature_evidence is None else signature_evidence
    signature = harness._signature(
        signer,
        subject_digest=subject_ref.digest,
        payload_digest=digest_value(body),
        evidence_refs=evidence,
        nonce=f"checker-attack-{digest_value(body).hex}-{signer}",
        issued_at=harness.now,
        run_identity_ref=run_ref,
    )
    if corrupt_signature:
        raw = b64decode(signature.signature, validate=True)
        signature = replace(
            signature,
            signature=b64encode(bytes((raw[0] ^ 1,)) + raw[1:]).decode("ascii"),
        )
    forged = CheckerReceiptV4.from_dict({**body, "signature": signature.to_dict()})
    return harness._contract(CHECKER_RECEIPT_KIND, CHECKER_SCOPE, forged)


def _alternate_run_ref(harness: _ChainHarness) -> ContentRefV4:
    body = harness.run.digest_body()
    body["engine_source_commit"] = "c" * 40
    alternate = RunIdentityV4.from_dict(
        {**body, "run_digest": str(digest_value(body))}
    )
    return harness._digest_contract(
        RUN_IDENTITY_KIND,
        RUN_IDENTITY_SCOPE,
        alternate,
    )


def _stage_solver_documents(
    harness: _ChainHarness,
    execution,
    *,
    problem: dict[str, object] | None = None,
    capability: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
    proof: dict[str, object] | None = None,
) -> ContentRefV4:
    problem_ref = execution.problem_ref
    invocation = execution.invocation
    invocation_ref = execution.invocation_ref
    if problem is not None:
        problem_ref = harness._json(BACKEND_PROBLEM_KIND, BACKEND_SCOPE, problem)
        invocation = replace(
            invocation,
            invocation_id=f"backend-{problem_ref.digest.hex}",
            ir_ref=problem_ref,
        )
        invocation_ref = harness._contract(
            BACKEND_INVOCATION_KIND,
            BACKEND_SCOPE,
            invocation,
        )
    if capability is not None:
        capability_ref = harness._json(
            checker_module.BACKEND_CAPABILITY_KIND,
            BACKEND_SCOPE,
            capability,
        )
        invocation = replace(
            invocation,
            provider_binary_digest=DigestV4.parse(capability["provider_binary_digest"]),
            provider_package_digest=DigestV4.parse(capability["provider_package_digest"]),
            provider_build_digest=DigestV4.parse(capability["provider_build_digest"]),
            provider_capability_ref=capability_ref,
        )
        invocation_ref = harness._contract(
            BACKEND_INVOCATION_KIND,
            BACKEND_SCOPE,
            invocation,
        )
    result_ref = execution.receipt.backend_result_ref
    if result is not None:
        result_ref = harness._json(BACKEND_RESULT_KIND, BACKEND_SCOPE, result)
    proof_ref = execution.receipt.proof_ref
    assert proof_ref is not None
    if proof is not None:
        proof_ref = harness._json(BACKEND_PROOF_KIND, BACKEND_SCOPE, proof)

    body = execution.receipt.signature_body()
    body.update(
        {
            "invocation_ref": invocation_ref.to_dict(),
            "backend_result_ref": result_ref.to_dict(),
            "proof_ref": proof_ref.to_dict(),
        }
    )
    evidence = (problem_ref, invocation_ref, result_ref, proof_ref)
    signature = harness._sign_receipt(
        result_ref.digest,
        digest_value(body),
        evidence,
        harness.run_identity_ref,
        harness.now,
    )
    receipt = SolverReceiptV4.from_dict({**body, "signature": signature.to_dict()})
    return harness._contract(
        checker_module.SOLVER_RECEIPT_KIND,
        BACKEND_SCOPE,
        receipt,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("status", "PASS"),
        ("argument_graph_ref", None),
        ("backend_result_ref", None),
        ("witness_refs", ()),
        ("checker_build_digest", None),
    ),
)
def test_caller_cannot_supply_pass_graph_result_witness_or_build(
    checked_chain,
    field: str,
    value: object,
) -> None:
    harness, checker, horn, _, _, _ = checked_chain
    kwargs = {
        "run_identity_ref": harness.run_identity_ref,
        "solver_receipt_ref": horn.receipt_ref,
        "now": harness.now,
        field: value,
    }
    with pytest.raises(TypeError):
        checker.check(**kwargs)


@pytest.mark.parametrize(
    "drift",
    (
        "run",
        "subject",
        "graph",
        "result",
        "build",
        "profile",
        "input",
        "output",
        "witness-less",
        "witness-more",
    ),
)
def test_trusted_resigned_checker_receipt_rejects_binding_drift(
    checked_chain,
    drift: str,
) -> None:
    harness, checker, _, aaf, checked, aaf_checked = checked_chain
    other_digest = str(digest_value({"checker-drift": drift}))
    changes: dict[str, object]
    if drift == "run":
        changes = {"run_identity_ref": _alternate_run_ref(harness).to_dict()}
    elif drift == "subject":
        changes = {"subject_ref": aaf.receipt_ref.to_dict()}
    elif drift == "graph":
        changes = {
            "argument_graph_ref": aaf_checked.receipt.argument_graph_ref.to_dict()
        }
    elif drift == "result":
        changes = {"backend_result_ref": aaf.receipt.backend_result_ref.to_dict()}
    elif drift in {"build", "profile", "input", "output"}:
        changes = {
            {
                "build": "checker_build_digest",
                "profile": "algorithm_profile_digest",
                "input": "input_digest",
                "output": "output_digest",
            }[drift]: other_digest
        }
    elif drift == "witness-less":
        changes = {
            "witness_refs": [item.to_dict() for item in checked.receipt.witness_refs[:-1]]
        }
    else:
        changes = {
            "witness_refs": [
                *[item.to_dict() for item in checked.receipt.witness_refs],
                aaf_checked.report_ref.to_dict(),
            ]
        }
    forged_ref = _stage_checker_receipt(
        harness,
        checked.receipt,
        changes=changes,
    )
    assert _error_code(
        lambda: checker.verify_receipt(forged_ref, now=harness.now)
    ).startswith("CHECKER_")


@pytest.mark.parametrize(
    ("attack", "expected"),
    (
        ("wrong-role", "CHECKER_SIGNATURE_BINDING"),
        ("missing-evidence", "CHECKER_SIGNATURE_BINDING"),
        ("bit-flip", "TRUST_SIGNATURE_INVALID"),
    ),
)
def test_checker_receipt_rejects_wrong_signer_signature_and_evidence(
    checked_chain,
    attack: str,
    expected: str,
) -> None:
    harness, checker, _, _, checked, _ = checked_chain
    forged_ref = _stage_checker_receipt(
        harness,
        checked.receipt,
        signer="legal" if attack == "wrong-role" else "service",
        signature_evidence=(
            checked.receipt.witness_refs[:-1]
            if attack == "missing-evidence"
            else None
        ),
        corrupt_signature=attack == "bit-flip",
    )
    assert _error_code(
        lambda: checker.verify_receipt(forged_ref, now=harness.now)
    ) == expected


@pytest.mark.parametrize(
    ("target", "expected"),
    (
        ("result", "CHECKER_RESULT_MISMATCH"),
        ("proof", "CHECKER_PROOF_MISMATCH"),
        ("fact", "CHECKER_FACT_BINDING"),
        ("translation", "CHECKER_TRANSLATION_MAPPING"),
        ("pack-rule-binding", "CHECKER_IR_BINDING"),
    ),
)
def test_trusted_resigned_horn_semantic_tamper_fails_closed(
    checked_chain,
    target: str,
    expected: str,
) -> None:
    harness, checker, horn, _, _, _ = checked_chain
    problem = _json(
        harness,
        horn.problem_ref,
        kind=BACKEND_PROBLEM_KIND,
        scope=BACKEND_SCOPE,
    )
    result = _json(
        harness,
        horn.receipt.backend_result_ref,
        kind=BACKEND_RESULT_KIND,
        scope=BACKEND_SCOPE,
    )
    assert horn.receipt.proof_ref is not None
    proof = _json(
        harness,
        horn.receipt.proof_ref,
        kind=BACKEND_PROOF_KIND,
        scope=BACKEND_SCOPE,
    )
    problem_arg = result_arg = proof_arg = None
    if target == "result":
        result["outputs"]["derived_atoms"].append("trusted-forgery")
        result_arg = result
    elif target == "proof":
        proof["witness"]["applicable_rule_ids"].append("trusted-forgery")
        proof_arg = proof
    elif target == "fact":
        problem["facts"][0]["value"] = False
        problem_arg = problem
    elif target == "translation":
        problem["clauses"][0]["translation_receipt_refs"].reverse()
        problem_arg = problem
    else:
        problem["clauses"][0]["rule_ref"] = problem["clauses"][-1]["rule_ref"]
        problem_arg = problem
    forged_ref = _stage_solver_documents(
        harness,
        horn,
        problem=problem_arg,
        result=result_arg,
        proof=proof_arg,
    )
    assert _error_code(
        lambda: checker.check(
            run_identity_ref=harness.run_identity_ref,
            solver_receipt_ref=forged_ref,
            now=harness.now,
        )
    ) == expected


@pytest.mark.parametrize(
    ("target", "expected"),
    (
        ("graph", "CHECKER_PROOF_MISMATCH"),
        ("label", "CHECKER_RESULT_MISMATCH"),
        ("claim-projection", "CHECKER_RESULT_MISMATCH"),
        ("permission", "CHECKER_RESULT_MISMATCH"),
    ),
)
def test_trusted_resigned_aaf_graph_and_projection_tamper_fails_closed(
    checked_chain,
    target: str,
    expected: str,
) -> None:
    harness, checker, _, aaf, _, _ = checked_chain
    result = _json(
        harness,
        aaf.receipt.backend_result_ref,
        kind=BACKEND_RESULT_KIND,
        scope=BACKEND_SCOPE,
    )
    assert aaf.receipt.proof_ref is not None
    proof = _json(
        harness,
        aaf.receipt.proof_ref,
        kind=BACKEND_PROOF_KIND,
        scope=BACKEND_SCOPE,
    )
    result_arg = proof_arg = None
    if target == "graph":
        proof["witness"]["graph"]["arguments"] = []
        proof_arg = proof
    elif target == "label":
        result["outputs"]["labels"][0]["label"] = "OUT"
        result_arg = result
    elif target == "claim-projection":
        result["outputs"]["claim_projection"] = []
        result_arg = result
    else:
        result["outputs"]["permission_resolutions"] = [{"forged": True}]
        result_arg = result
    forged_ref = _stage_solver_documents(
        harness,
        aaf,
        result=result_arg,
        proof=proof_arg,
    )
    assert _error_code(
        lambda: checker.check(
            run_identity_ref=harness.run_identity_ref,
            solver_receipt_ref=forged_ref,
            now=harness.now,
        )
    ) == expected


def test_trusted_resigned_exact_constraint_tamper_fails_closed() -> None:
    harness, _, _, _, _, executions = _execute(
        "synthetic-permission-temporal",
        "synthetic-positive",
    )
    exact = _provider(executions, checker_module.EXACT_PROVIDER_ID)
    checker = _checker(harness)
    problem = _json(
        harness,
        exact.problem_ref,
        kind=BACKEND_PROBLEM_KIND,
        scope=BACKEND_SCOPE,
    )
    clause = next(row for row in problem["clauses"] if row["temporal_constraints"])
    clause["temporal_constraints"][0]["owner_ivl_id"] = "trusted-forgery"
    forged_ref = _stage_solver_documents(harness, exact, problem=problem)

    assert _error_code(
        lambda: checker.check(
            run_identity_ref=harness.run_identity_ref,
            solver_receipt_ref=forged_ref,
            now=harness.now,
        )
    ).startswith("CHECKER_")


def test_checker_rejects_wrong_profile_accepted_by_compromised_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrong_profile = digest_value({"backend-profile": "compromised-router"})
    monkeypatch.setattr(
        backend_module,
        "_backend_profile_digest_v4",
        lambda **kwargs: wrong_profile,
    )
    harness, _, _, _, _, executions = _execute(
        "synthetic-positive",
        backend_profile_digest=wrong_profile,
    )
    horn = _provider(executions, HORN_PROVIDER_ID)

    assert _error_code(
        lambda: _checker(harness).check(
            run_identity_ref=harness.run_identity_ref,
            solver_receipt_ref=horn.receipt_ref,
            now=harness.now,
        )
    ) == "CHECKER_BACKEND_BUILD"


def test_checker_rejects_self_consistent_provider_bytes_outside_run_profile() -> None:
    harness, _, _, _, _, executions = _execute("synthetic-positive")
    horn = _provider(executions, HORN_PROVIDER_ID)
    capability = _json(
        harness,
        horn.invocation.provider_capability_ref,
        kind=checker_module.BACKEND_CAPABILITY_KIND,
        scope=BACKEND_SCOPE,
    )
    changed_inputs = {
        **capability["provider_build_inputs"],
        "backends": str(digest_value({"changed-provider-bytes": True})),
    }
    capability["provider_build_inputs"] = changed_inputs
    capability["provider_package_digest"] = str(
        DigestV4.from_bytes(canonical_bytes(changed_inputs))
    )
    build_body = dict(capability)
    del build_body["provider_build_digest"]
    capability["provider_build_digest"] = str(digest_value(build_body))
    forged_ref = _stage_solver_documents(harness, horn, capability=capability)

    assert _error_code(
        lambda: _checker(harness).check(
            run_identity_ref=harness.run_identity_ref,
            solver_receipt_ref=forged_ref,
            now=harness.now,
        )
    ) == "CHECKER_BACKEND_BUILD"


def test_checker_ast_has_no_production_semantic_import_or_call() -> None:
    source = Path(checker_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = (
        "compiler_core.argumentation",
        "compiler_core.backend_router",
        "compiler_core.backends",
        "compiler_core.fact_admission",
        "compiler_core.legal_ir",
        "compiler_core.rule_packs",
    )
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    assert not {
        module
        for module in imports
        if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden_modules)
    }
    forbidden_calls = {
        "compile_rule",
        "evaluate_argument_graph",
        "execute_aaf",
        "execute_exact",
        "execute_horn",
        "grounded_extension",
        "verify_compilation",
    }
    assert not {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden_calls
    }


def test_checker_does_not_call_monkeypatched_production_oracles(
    checked_chain,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, checker, horn, _, _, _ = checked_chain

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("production semantic oracle was called")

    for module, names in (
        (backends_module, ("execute_horn", "execute_aaf", "execute_exact")),
        (argumentation_module, ("evaluate_argument_graph", "grounded_extension")),
    ):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(legal_ir_module.LegalIRCompilerV4, "compile_rule", forbidden)
    monkeypatch.setattr(
        legal_ir_module.LegalIRCompilerV4,
        "verify_compilation",
        forbidden,
    )
    monkeypatch.setattr(backend_module.BackendRouterV4, "_invoke_provider", forbidden)
    monkeypatch.setattr(backend_module.BackendRouterV4, "replay", forbidden)

    checked = checker.check(
        run_identity_ref=harness.run_identity_ref,
        solver_receipt_ref=horn.receipt_ref,
        now=harness.now,
    )
    assert checker.verify_receipt(checked.receipt_ref, now=harness.now) == checked.receipt


def test_check_and_verify_pin_one_resolver_snapshot(
    checked_chain,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, checker, horn, _, checked, _ = checked_chain
    recompute = checker._recompute_pinned
    verify = checker._verify_receipt_pinned

    def recompute_in_snapshot(**kwargs):
        assert harness.resolver._active_snapshot.get() is not None
        return recompute(**kwargs)

    def verify_in_snapshot(receipt_ref: ContentRefV4, *, now):
        assert harness.resolver._active_snapshot.get() is not None
        return verify(receipt_ref, now=now)

    monkeypatch.setattr(checker, "_recompute_pinned", recompute_in_snapshot)
    issued = checker.check(
        run_identity_ref=harness.run_identity_ref,
        solver_receipt_ref=horn.receipt_ref,
        now=harness.now,
    )
    monkeypatch.setattr(checker, "_verify_receipt_pinned", verify_in_snapshot)
    assert checker.verify_receipt(issued.receipt_ref, now=harness.now) == issued.receipt
    assert checked.receipt.status == "PASS"
