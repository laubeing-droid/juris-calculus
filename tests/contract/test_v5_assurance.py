"""U08 acceptance samples JT35-JT39: assurance aggregation, independent
semantic re-verification, and certificate binding checks."""
from __future__ import annotations

import pytest

from compiler_core.assurance import AssuranceV5Error, combine_assurance_v5
from compiler_core.canonical_serialization import digest_value
from compiler_core.contracts import DigestV4, NotApplicableEvidenceV5
from compiler_core.contracts import AssuranceEnvelopeV5

D = lambda n: DigestV4(f"sha256:{n:064x}")


def _envelope(**overrides) -> AssuranceEnvelopeV5:
    payload = {
        "scope_request_ref": str(D(1)),
        "scope_profile": "grounded",
        "spec": "proved",
        "implementation": "crossCheckOnly",
        "run_check": "checked",
        "coverage_open_obligations": [],
        "coverage_not_applicable": [],
        "pending_refs": [],
        "assumed_refs": [],
        "open_spec_refs": [],
        "formal_assumption_refs": [],
        "tcb_refs": [],
        "notices": [],
    }
    payload.update(overrides)
    payload = {
        key: (list(value) if isinstance(value, tuple) else value)
        for key, value in payload.items()
    }
    payload["assurance_digest"] = str(
        digest_value({k: v for k, v in payload.items() if k != "assurance_digest"})
    )
    return AssuranceEnvelopeV5.from_dict(payload)


def test_jt35_coordinates_aggregate_conservatively_never_averaged() -> None:
    strong_proof = _envelope(spec="proved", implementation="crossCheckOnly")
    weak_fact = _envelope(
        spec="assumed", implementation="crossCheckOnly",
        assumed_refs=("assumption-disputed-a",),
    )
    combined = combine_assurance_v5(strong_proof, weak_fact)
    assert combined.spec == "assumed"
    assert combined.assumed_refs == ("assumption-disputed-a",)
    # a strong text axis never washes a weak fact axis: they are separate carriers
    assert combined.pending_refs == ()


def test_jt36_pending_and_assumed_refs_are_both_preserved() -> None:
    left = _envelope(pending_refs=("pending-source-1",), assumed_refs=("assumption-1",))
    right = _envelope(pending_refs=("pending-source-2",))
    combined = combine_assurance_v5(left, right)
    assert combined.pending_refs == ("pending-source-1", "pending-source-2")
    assert combined.assumed_refs == ("assumption-1",)


def test_jt37_scope_mismatch_rejected_and_pseudo_exemption_kept_visible() -> None:
    left = _envelope()
    right = _envelope(scope_profile="preferred")
    with pytest.raises(AssuranceV5Error) as caught:
        combine_assurance_v5(left, right)
    assert caught.value.code == "ASSURANCE_SCOPE"
    exempt = _envelope(coverage_not_applicable=[{
        "obligation": "banach_contraction_evidence",
        "reason": "no numerical iteration participates",
        "applicability_evidence_ref": str(D(5)),
    }])
    combined = combine_assurance_v5(left, exempt)
    assert combined.coverage_not_applicable[0].obligation == "banach_contraction_evidence"


def test_jt38_independent_family_recomputation_rejects_wrong_solver_output() -> None:
    from compiler_core.argumentation import evaluate_profile_v5, verify_profile_family_v5

    # production solver (fictitiously) reports {{a},{b}} as preferred family
    defeats = (("a", "b"), ("b", "a"))
    claimed = (frozenset({"a"}),)
    ok, reason = verify_profile_family_v5(
        "preferred", ("a", "b"), defeats, claimed, coverage="exact",
    )
    assert not ok and reason == "family_mismatch"
    reference = evaluate_profile_v5("preferred", ("a", "b"), defeats)
    assert {tuple(sorted(e)) for e in reference.extensions} == {("a",), ("b",)}


def test_jt39_kernel_verified_requires_tcb_and_rebinding_fails() -> None:
    with pytest.raises(Exception) as caught:
        _envelope(implementation="kernelVerified")
    assert "kernelVerified" in str(caught.value)
    with_tcb = _envelope(implementation="kernelVerified", tcb_refs=("checker/core",))
    assert with_tcb.tcb_refs == ("checker/core",)
    # rebinding to another request must fail the self digest
    tampered = {
        "scope_request_ref": str(D(2)),
        "scope_profile": with_tcb.scope_profile,
        "spec": with_tcb.spec,
        "implementation": with_tcb.implementation,
        "run_check": with_tcb.run_check,
        "coverage_open_obligations": [o.to_dict() for o in with_tcb.coverage_open_obligations],
        "coverage_not_applicable": [e.to_dict() for e in with_tcb.coverage_not_applicable],
        "pending_refs": list(with_tcb.pending_refs),
        "assumed_refs": list(with_tcb.assumed_refs),
        "open_spec_refs": list(with_tcb.open_spec_refs),
        "formal_assumption_refs": list(with_tcb.formal_assumption_refs),
        "tcb_refs": list(with_tcb.tcb_refs),
        "notices": [n.to_dict() for n in with_tcb.notices],
        "assurance_digest": str(with_tcb.assurance_digest),
    }
    with pytest.raises(Exception) as caught:
        AssuranceEnvelopeV5.from_dict(tampered)
    assert "SELF_DIGEST_MISMATCH" in str(caught.value)
