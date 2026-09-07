"""Real add-only Horn incremental reuse inside the public spine (FIX-05).

Every test drives the sole ApplicationV4 chain with public requests. The
Horn subject state artifact is the reusable parent: it is sealed into the
audit bundle, and a second request that carries ``incremental_parent_v5``
either extends the parent closure through the real worklist fast path or
falls back to a recorded full recompute. Faking the mode is impossible: the
sealed state records the deterministic solver/checker workload counts.
"""
from __future__ import annotations

from base64 import b64decode
from pathlib import Path

import pytest

import compiler_core.application as application_module
from compiler_core.application import (
    ApplicationV4,
    HORN_SUBJECT_STATE_KIND_V5,
)
from compiler_core.audit_bundle import AuditBundleStoreV4, AuditTrustMaterialV4
from compiler_core.backend_router import BackendRouterV4
from compiler_core.canonical_serialization import DigestV4, parse_json_document
from compiler_core.certificates import CertificateIssuerV4
from compiler_core.contracts import ContentRefV4, IncrementalParentV5
from compiler_core.independent_checker import IndependentCheckerV4
from compiler_core.legal_ir import LegalIRCompilerV4
from compiler_core.storage import V4TransactionStore

from tests.contract.test_v5_profile_chain import (
    EXCEPTION_FACTS,
    _application,
    _seed_with_v5,
    _v5_inputs,
)
from tests.integration.test_trust_chain import CASE_SCOPE, _ChainHarness

BASE_FACTS = EXCEPTION_FACTS + ("synthetic-horn.a",)
CHILD_ADDS_C = (*BASE_FACTS, "synthetic-horn.c")
ALT_ROUTE_FACTS = EXCEPTION_FACTS + ("synthetic-horn.a", "synthetic-horn.x")


def _horn_state(
    store: AuditBundleStoreV4, harness: _ChainHarness, run_ref: ContentRefV4,
) -> tuple[dict, dict]:
    capability = store.capability_for(run_ref)
    verified = store.verify_run(capability, now=harness.now)
    for name in sorted(verified.files):
        try:
            payload = parse_json_document(verified.files[name])
        except ValueError:
            continue
        if type(payload) is not dict or type(payload.get("artifacts")) is not list:
            continue
        for item in payload["artifacts"]:
            if item.get("artifact_kind") == HORN_SUBJECT_STATE_KIND_V5:
                content = parse_json_document(
                    b64decode(item["content_base64"], validate=True),
                )
                return content, item["content_ref"]
    raise AssertionError("horn-subject-state-v5 missing from the sealed bundle")


def _second_application(
    tmp_path: Path, harness: _ChainHarness, state_root: Path,
) -> tuple[ApplicationV4, AuditBundleStoreV4]:
    """A fresh harness/application pair sharing only the persistent store.

    This is the cross-process shape: the parent state must be recoverable
    from the sealed audit bundle, never from in-process memory.
    """

    compiler = LegalIRCompilerV4(
        harness.pack_verifier,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )
    router = BackendRouterV4(
        compiler, harness.fact_service, receipt_signer=harness._sign_receipt,
    )
    checker = IndependentCheckerV4(
        harness.resolver, harness.trust,
        receipt_issuer="synthetic-service-issuer",
        receipt_signer=harness._sign_receipt,
    )
    trust_material = AuditTrustMaterialV4(
        harness.policy,
        tuple(key for _, key in sorted(harness.trust._keys.items())),
        harness.trust.target_environment,
        tuple(sorted(harness.trust._revoked_subjects, key=str)),
        tuple(sorted(harness.trust._revoked_nonces)),
    )
    store = AuditBundleStoreV4(
        V4TransactionStore.open(state_root, quota_bytes=256 * 1024 * 1024),
        trust_material=trust_material,
        current_engine_build_digest=harness.run.engine_build_digest,
        checker_receipt_issuer="synthetic-service-issuer",
    )
    issuer = CertificateIssuerV4(
        harness.trust,
        current_engine_build_digest=harness.run.engine_build_digest,
        signer=harness._sign_receipt,
    )
    application = ApplicationV4(
        harness.resolver, harness.trust, harness.source_service,
        harness.fact_service, harness.pack_verifier, compiler,
        router, checker, store, issuer,
        receipt_signer=harness._sign_receipt,
        clock=lambda: harness.now,
        default_limits=harness.default_limits,
    )
    return application, store


def _parent_input(parent_state: dict, state_ref: dict) -> IncrementalParentV5:
    return IncrementalParentV5(
        parent_run_ref=None,  # filled by callers that hold the run ref
        parent_state_ref=ContentRefV4.from_dict(state_ref),
        parent_subject_digest=DigestV4(parent_state["subject_digest"]),
    )


def _run_pair(
    tmp_path: Path,
    *,
    child_facts: tuple[str, ...],
    child_mode: str = "auto",
):
    state_root = (tmp_path / "state").resolve()
    parent_harness = _ChainHarness()
    policy, queries, _ = _v5_inputs(parent_harness, profiles=("grounded",))
    _seed, request_ref, _run, run_ref = _seed_with_v5(
        parent_harness, policy=policy, queries=queries, extra_fact_keys=BASE_FACTS,
    )
    application, store = _application(tmp_path, parent_harness)
    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    assert envelope.transport_outcome.status == "success"
    parent_state, parent_state_ref = _horn_state(store, parent_harness, run_ref)

    child_harness = _ChainHarness()
    child_policy, child_queries, _ = _v5_inputs(child_harness, profiles=("grounded",))
    parent = IncrementalParentV5(
        parent_run_ref=run_ref,
        parent_state_ref=ContentRefV4.from_dict(parent_state_ref),
        parent_subject_digest=DigestV4(parent_state["subject_digest"]),
        mode=child_mode,
    )
    _child_seed, child_request_ref, _child_run, child_run_ref = _seed_with_v5(
        child_harness,
        policy=child_policy,
        queries=child_queries,
        extra_fact_keys=child_facts,
        incremental_parent=parent,
    )
    child_application, child_store = _second_application(
        tmp_path, child_harness, state_root,
    )
    child_envelope = child_application.evaluate(
        child_request_ref, child_run_ref, case_scope=CASE_SCOPE,
    )
    return child_envelope, child_store, child_harness, child_run_ref, parent_state


def test_first_public_request_is_full_and_saves_parent_state(tmp_path: Path) -> None:
    """F01: no parent reference means a recorded full recompute with a saved,
    reusable, verified parent state."""

    harness = _ChainHarness()
    policy, queries, _ = _v5_inputs(harness, profiles=("grounded",))
    _seed, request_ref, _run, run_ref = _seed_with_v5(
        harness, policy=policy, queries=queries, extra_fact_keys=BASE_FACTS,
    )
    application, store = _application(tmp_path, harness)
    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    assert envelope.transport_outcome.status == "success"
    state, _ref = _horn_state(store, harness, run_ref)
    assert state["mode"] == "full_recompute"
    assert state["fallback_reason"] == "no_parent_reference"
    assert state["status"] == "verified_complete"
    assert "synthetic-horn.b" in state["closure"]
    assert state["solver_metrics"]["rule_evaluations"] >= 1
    assert state["checker_metrics"]["rule_evaluations"] >= 1


def test_second_request_reuses_parent_closure_incrementally(tmp_path: Path) -> None:
    """F02: the add-only child actually runs the incremental worklist from the
    parent closure (a + c -> a, b, c, d), through a second application
    instance whose only shared state is the persistent audit store."""

    envelope, store, harness, run_ref, parent_state = _run_pair(
        tmp_path, child_facts=CHILD_ADDS_C,
    )
    assert envelope.transport_outcome.status == "success"
    child_state, _ = _horn_state(store, harness, run_ref)
    assert child_state["mode"] == "incremental", child_state["fallback_reason"]
    assert child_state["fallback_reason"] is None
    assert child_state["parent"]["subject_digest"] == parent_state["subject_digest"]
    for atom in ("synthetic-horn.a", "synthetic-horn.b", "synthetic-horn.c", "synthetic-horn.d"):
        assert atom in child_state["closure"]
    # Real reuse evidence: the production solver evaluated only the delta
    # while the independent checker re-scanned the whole subject.
    assert (
        child_state["solver_metrics"]["rule_evaluations"]
        < child_state["checker_metrics"]["rule_evaluations"]
    )
    # Downstream recomputed: the child query answers are fresh, not inherited.
    assert envelope.result.completeness_state.value == "complete"


def test_incremental_equals_forced_full_recompute(tmp_path: Path) -> None:
    """F09: default incremental and force_full on the same child agree on the
    legal semantics and the necessary support (closure, mode aside)."""

    incremental_envelope, store, harness, run_ref, _ = _run_pair(
        tmp_path / "inc", child_facts=CHILD_ADDS_C,
    )
    full_envelope, full_store, full_harness, full_run_ref, _ = _run_pair(
        tmp_path / "full", child_facts=CHILD_ADDS_C, child_mode="force_full",
    )
    assert incremental_envelope.transport_outcome.status == "success"
    assert full_envelope.transport_outcome.status == "success"
    incremental_state, _ = _horn_state(store, harness, run_ref)
    full_state, _ = _horn_state(full_store, full_harness, full_run_ref)
    assert incremental_state["mode"] == "incremental"
    assert full_state["mode"] == "full_recompute"
    assert full_state["fallback_reason"] == "forced_full_diagnostic"
    assert incremental_state["closure"] == full_state["closure"]
    assert incremental_state["facts"] == full_state["facts"]
    assert incremental_state["rules"] == full_state["rules"]
    assert (
        incremental_envelope.result.decision_status
        == full_envelope.result.decision_status
    )
    assert (
        incremental_envelope.result.completeness_state
        == full_envelope.result.completeness_state
    )


def test_new_rule_to_existing_conclusion_keeps_the_route(tmp_path: Path) -> None:
    """F04: a second admitted route to an already-derived conclusion enters
    the subject rules and the closure stays equal to the full recompute."""

    envelope, store, harness, run_ref, _ = _run_pair(
        tmp_path, child_facts=ALT_ROUTE_FACTS,
    )
    assert envelope.transport_outcome.status == "success"
    child_state, _ = _horn_state(store, harness, run_ref)
    assert child_state["mode"] == "incremental", child_state["fallback_reason"]
    rule_ids = [row[2] for row in child_state["rules"]]
    assert "synthetic-horn-alt-b" in rule_ids
    assert "synthetic-horn-step-b" in rule_ids
    assert "synthetic-horn.b" in child_state["closure"]


def test_nonmonotonic_change_falls_back_with_recorded_reason(tmp_path: Path) -> None:
    """F06: a child that drops an admitted fact (non-monotonic) must not reuse
    the parent state; it records fact_deletion and full-recomputes."""

    # Child drops synthetic-horn.a entirely and keeps only c: parent facts
    # are not a subset => fact_deletion fallback.
    shrinking_facts = EXCEPTION_FACTS + ("synthetic-horn.c",)
    envelope, store, harness, run_ref, _ = _run_pair(
        tmp_path, child_facts=shrinking_facts,
    )
    assert envelope.transport_outcome.status == "success"
    child_state, _ = _horn_state(store, harness, run_ref)
    assert child_state["mode"] == "full_recompute"
    assert child_state["fallback_reason"] == "fact_deletion"
    assert child_state["parent"] is None
    assert "synthetic-horn.b" not in child_state["closure"]


def test_universe_growth_falls_back(tmp_path: Path) -> None:
    """F06: admitting a fact key outside the pack universe grows the fixed
    universe and forces a recorded full recompute."""

    grown_facts = (*CHILD_ADDS_C, "synthetic-horn.brand-new")
    envelope, store, harness, run_ref, _ = _run_pair(
        tmp_path, child_facts=grown_facts,
    )
    assert envelope.transport_outcome.status == "success"
    child_state, _ = _horn_state(store, harness, run_ref)
    assert child_state["mode"] == "full_recompute"
    assert child_state["fallback_reason"] == "universe_growth"


def test_forged_parent_reference_is_rejected_or_falls_back(tmp_path: Path) -> None:
    """F07: a parent reference whose subject digest does not bind the sealed
    state is never treated as a legal cache hit."""

    state_root_parent = tmp_path / "state"
    parent_harness = _ChainHarness()
    policy, queries, _ = _v5_inputs(parent_harness, profiles=("grounded",))
    _seed, request_ref, _run, run_ref = _seed_with_v5(
        parent_harness, policy=policy, queries=queries, extra_fact_keys=BASE_FACTS,
    )
    application, store = _application(tmp_path, parent_harness)
    envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    assert envelope.transport_outcome.status == "success"
    parent_state, parent_state_ref = _horn_state(store, parent_harness, run_ref)

    child_harness = _ChainHarness()
    child_policy, child_queries, _ = _v5_inputs(child_harness, profiles=("grounded",))
    forged = IncrementalParentV5(
        parent_run_ref=run_ref,
        parent_state_ref=ContentRefV4.from_dict(parent_state_ref),
        parent_subject_digest=DigestV4.from_bytes(b"forged-subject"),
    )
    _child_seed, child_request_ref, _child_run, child_run_ref = _seed_with_v5(
        child_harness,
        policy=child_policy,
        queries=child_queries,
        extra_fact_keys=CHILD_ADDS_C,
        incremental_parent=forged,
    )
    child_application, child_store = _second_application(
        tmp_path, child_harness, state_root_parent.resolve(),
    )
    child_envelope = child_application.evaluate(
        child_request_ref, child_run_ref, case_scope=CASE_SCOPE,
    )
    assert child_envelope.transport_outcome.status == "success"
    child_state, _ = _horn_state(child_store, child_harness, child_run_ref)
    assert child_state["mode"] == "full_recompute"
    assert child_state["fallback_reason"] == "parent_state_unavailable"
    # the closure is still correct
    assert "synthetic-horn.d" in child_state["closure"]


def test_faulty_incremental_propagation_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F08: an incremental engine that drops one propagation cannot deliver:
    the independent full recomputation mismatch fails the run closed."""

    real_incremental = application_module.incremental_horn_closure

    def lossy_incremental(parent_closure, parent_rules, added_facts, added_rules):
        closure, metrics = real_incremental(
            parent_closure, parent_rules, added_facts, added_rules,
        )
        # silently drop one derived atom
        dropped = sorted(closure - set(parent_closure) - set(added_facts))
        if dropped:
            closure = frozenset(closure) - {dropped[-1]}
        return closure, metrics

    monkeypatch.setattr(
        application_module, "incremental_horn_closure", lossy_incremental,
    )
    harness = _ChainHarness()
    policy, queries, _ = _v5_inputs(harness, profiles=("grounded",))
    _seed, request_ref, _run, run_ref = _seed_with_v5(
        harness, policy=policy, queries=queries, extra_fact_keys=BASE_FACTS,
    )
    application, store = _application(tmp_path / "parent", harness)
    parent_envelope = application.evaluate(request_ref, run_ref, case_scope=CASE_SCOPE)
    assert parent_envelope.transport_outcome.status == "success"
    parent_state, parent_state_ref = _horn_state(store, harness, run_ref)

    child_harness = _ChainHarness()
    child_policy, child_queries, _ = _v5_inputs(child_harness, profiles=("grounded",))
    parent = IncrementalParentV5(
        parent_run_ref=run_ref,
        parent_state_ref=ContentRefV4.from_dict(parent_state_ref),
        parent_subject_digest=DigestV4(parent_state["subject_digest"]),
    )
    _child_seed, child_request_ref, _child_run, child_run_ref = _seed_with_v5(
        child_harness,
        policy=child_policy,
        queries=child_queries,
        extra_fact_keys=CHILD_ADDS_C,
        incremental_parent=parent,
    )
    child_application, _child_store = _second_application(
        tmp_path / "parent", child_harness, (tmp_path / "parent" / "state").resolve(),
    )
    child_envelope = child_application.evaluate(
        child_request_ref, child_run_ref, case_scope=CASE_SCOPE,
    )
    assert child_envelope.transport_outcome.status == "error"
    assert child_envelope.transport_outcome.error.code == (
        "APPLICATION_HORN_INCREMENTAL_MISMATCH"
    )
