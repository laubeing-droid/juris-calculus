"""W3：P09 三门事实准入与 FactAdmissionAttestationV1 测试。

用例语义与 tests/fixtures/theory_absorption/p09、p01、p05 对齐。
"""

from __future__ import annotations

import pytest

from compiler_core.fact_admission_v1 import (
    FactAdmissionAttestationV1,
    FactAdmissionError,
    FactAdmissionService,
    FactCandidate,
    canonical_proposition_hash,
)
from compiler_core.source_service_v2 import GateOutcome


PROPOSITION = "defendant_paid_50000_cny"
NOW = "2026-08-16T00:00:00Z"


def h(prefix: str) -> str:
    return "sha256:" + (prefix * 32)[:64]


def _attestation_payload(**overrides):
    payload = {
        "attestation_id": "faa-0001",
        "kind": "FactAdmissionAttestationV1",
        "proposition_hash": canonical_proposition_hash(PROPOSITION),
        "source_refs": [{"ref": "src-cpl-2021", "hash": h("aa")}],
        "evidence_refs": [{"ref": "ev-0001", "hash": h("ee")}],
        "interpretation_version": "interp-2026-01",
        "admission_basis": "documentary_evidence_human_reviewed",
        "issuer_role": "legal_harness_approver",
        "issuer_scope": {"case_ref": "case-0001", "run_ref": "run-0001"},
        "issued_at": "2026-08-01T00:00:00Z",
        "expires_at": "",
        "dispute_state": "undisputed",
        "assumption_state": "none",
        "revocation_ref": "",
        "signature_or_approval_receipt_ref": "approval-0001",
    }
    payload.update(overrides)
    return payload


def _service_with_attestation(**overrides) -> FactAdmissionService:
    service = FactAdmissionService()
    service.register_attestation(FactAdmissionAttestationV1.from_dict(_attestation_payload(**overrides)))
    return service


PASS_GATE = GateOutcome("source_gate", "PASS")
PASS_INTERP = GateOutcome("interpretation_gate", "PASS")


class TestAttestationValidation:
    def test_fully_bound_attestation_parses(self):
        attestation = FactAdmissionAttestationV1.from_dict(_attestation_payload())
        assert attestation.proposition_hash == canonical_proposition_hash(PROPOSITION)

    def test_agent_issuer_role_rejected(self):
        with pytest.raises(FactAdmissionError) as exc:
            FactAdmissionAttestationV1.from_dict(_attestation_payload(issuer_role="agent"))
        assert exc.value.code == "ISSUER_ROLE_NOT_AUTHORIZED"

    def test_unknown_field_fails_closed(self):
        with pytest.raises(FactAdmissionError) as exc:
            FactAdmissionAttestationV1.from_dict(_attestation_payload(escalate=True))
        assert exc.value.code == "UNKNOWN_FIELD"

    def test_missing_evidence_refs_fails_closed(self):
        with pytest.raises(FactAdmissionError) as exc:
            FactAdmissionAttestationV1.from_dict(_attestation_payload(evidence_refs=[]))
        assert exc.value.code == "EVIDENCE_MISSING"


class TestFactGate:
    def test_positive_attestation_admits_fact(self):
        service = _service_with_attestation()
        candidate = FactCandidate(proposition=PROPOSITION, producer_kind="lawyer")
        decision = service.admit_fact(
            candidate=candidate,
            attestation_ref="faa-0001",
            source_outcome=PASS_GATE,
            interpretation_outcome=PASS_INTERP,
            case_ref="case-0001",
            run_ref="run-0001",
            now=NOW,
        )
        assert decision["admitted"] is True
        assert decision["gates"] == {
            "source_gate": "PASS",
            "interpretation_gate": "PASS",
            "fact_gate": "PASS",
        }

    def test_altered_proposition_breaks_binding(self):
        service = _service_with_attestation()
        candidate = FactCandidate(proposition="defendant_paid_50001_cny", producer_kind="lawyer")
        decision = service.admit_fact(
            candidate=candidate,
            attestation_ref="faa-0001",
            source_outcome=PASS_GATE,
            interpretation_outcome=PASS_INTERP,
            case_ref="case-0001",
            run_ref="run-0001",
            now=NOW,
        )
        assert decision["admitted"] is False
        assert decision["reason"] == "attestation_binding_broken"
        assert any(event["reason"] == "attestation_binding_broken" for event in service.rejection_events)

    def test_missing_attestation_blocks_formal_premise(self):
        service = FactAdmissionService()
        candidate = FactCandidate(proposition="payment_was_made", producer_kind="agent")
        decision = service.admit_fact(
            candidate=candidate,
            attestation_ref=None,
            source_outcome=PASS_GATE,
            interpretation_outcome=PASS_INTERP,
            case_ref="case-0001",
            run_ref="run-0001",
            now=NOW,
        )
        assert decision["admitted"] is False
        assert decision["review_only"] is False
        assert decision["gates"]["fact_gate"] == "BLOCKED"

    def test_disputed_attestation_is_review_only(self):
        service = _service_with_attestation(dispute_state="DISPUTED")
        candidate = FactCandidate(proposition=PROPOSITION, producer_kind="lawyer")
        decision = service.admit_fact(
            candidate=candidate,
            attestation_ref="faa-0001",
            source_outcome=PASS_GATE,
            interpretation_outcome=PASS_INTERP,
            case_ref="case-0001",
            run_ref="run-0001",
            now=NOW,
        )
        assert decision["admitted"] is False
        assert decision["review_only"] is True

    def test_cross_case_reuse_rejected(self):
        service = _service_with_attestation()
        candidate = FactCandidate(proposition=PROPOSITION, producer_kind="lawyer")
        decision = service.admit_fact(
            candidate=candidate,
            attestation_ref="faa-0001",
            source_outcome=PASS_GATE,
            interpretation_outcome=PASS_INTERP,
            case_ref="case-9999",
            run_ref="run-0001",
            now=NOW,
        )
        assert decision["admitted"] is False
        assert decision["reason"] == "attestation_scope_mismatch"

    def test_replay_within_same_scope_rejected(self):
        service = _service_with_attestation()
        candidate = FactCandidate(proposition=PROPOSITION, producer_kind="lawyer")
        kwargs = dict(
            candidate=candidate,
            attestation_ref="faa-0001",
            source_outcome=PASS_GATE,
            interpretation_outcome=PASS_INTERP,
            case_ref="case-0001",
            run_ref="run-0001",
            now=NOW,
        )
        assert service.admit_fact(**kwargs)["admitted"] is True
        second = service.admit_fact(**kwargs)
        assert second["admitted"] is False
        assert second["reason"] == "attestation_replayed"

    def test_revoked_and_expired_attestations_rejected(self):
        revoked = _service_with_attestation(revocation_ref="rev-0001")
        expired = _service_with_attestation(expires_at="2026-08-01T00:00:00Z")
        candidate = FactCandidate(proposition=PROPOSITION, producer_kind="lawyer")
        base = dict(
            candidate=candidate,
            attestation_ref="faa-0001",
            source_outcome=PASS_GATE,
            interpretation_outcome=PASS_INTERP,
            case_ref="case-0001",
            run_ref="run-0001",
            now=NOW,
        )
        assert revoked.admit_fact(**base)["reason"] == "attestation_revoked"
        assert expired.admit_fact(**base)["reason"] == "attestation_expired"

    def test_self_attestation_from_agent_field_rejected(self):
        service = FactAdmissionService()
        candidate = FactCandidate(
            proposition="contract_was_signed",
            producer_kind="agent",
            self_attestation={"issuer": "deli-agent-1"},
        )
        decision = service.admit_fact(
            candidate=candidate,
            attestation_ref="faa-0001",
            source_outcome=PASS_GATE,
            interpretation_outcome=PASS_INTERP,
            case_ref="case-0001",
            run_ref="run-0001",
            now=NOW,
        )
        assert decision["admitted"] is False
        assert decision["reason"] == "agent_cannot_self_attest"

    def test_any_gate_failure_blocks_admission(self):
        service = _service_with_attestation()
        candidate = FactCandidate(proposition=PROPOSITION, producer_kind="lawyer")
        blocked_source = GateOutcome("source_gate", "BLOCKED", "hash_locator_version_missing")
        decision = service.admit_fact(
            candidate=candidate,
            attestation_ref="faa-0001",
            source_outcome=blocked_source,
            interpretation_outcome=PASS_INTERP,
            case_ref="case-0001",
            run_ref="run-0001",
            now=NOW,
        )
        assert decision["admitted"] is False
        assert decision["review_only"] is False
