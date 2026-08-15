"""W8：RunIdentityV2、收据分离、FormalCertificateV1 与 AuditBundleV2 测试。

覆盖方案 §14 与 Gate：
- 任一输入变更破坏身份/摘要；
- 收据不能互相冒充、缺失收据阻止签发；
- partial/truncated/unknown 无证书；
- bundle 隐私、路径扫描 fail closed。
"""

from __future__ import annotations

import pytest

from compiler_core.certificate_v1 import (
    AuditBundleV2,
    CertificateGateError,
    GATE_NAMES,
    RunIdentityV2,
    TypedReceiptV1,
    issue_formal_certificate,
)


def h(prefix: str) -> str:
    return "sha256:" + (prefix * 32)[:64]


def _run_identity(**overrides) -> RunIdentityV2:
    payload = dict(
        engine_version="3.0.2",
        engine_commit="5b7bd008966703a33343ef1784fd13f5650b8e66",
        engine_tree=h("01"),
        package_hash=h("02"),
        schema_version="jc/4.0",
        request_digest=h("03"),
        source_bundle_ref="sb-0001",
        evidence_manifest_ref="em-0001",
        fact_attestation_digests=(h("04"),),
        pack_build_digest=h("05"),
        compiler_identity="jc-spec-compiler@1.0",
        router_identity="jc-router@1.0",
        checker_identity="jc-checker@2.0",
        translator_identity="jc-ivl-lowering@1.0",
        solver_identity="",
        runtime_options={"checker_strict": True},
    )
    payload.update(overrides)
    return RunIdentityV2(**payload)


def _bundle(run_identity: RunIdentityV2) -> AuditBundleV2:
    return AuditBundleV2(
        run_identity=run_identity,
        canonical_request_digest=h("10"),
        canonical_result_digest=h("11"),
        events_digest=h("12"),
        graph_digest=h("13"),
        schema_refs=("jc-v4.schema.json",),
        pack_material_digests=(h("14"),),
        receipt_digests=(h("15"),),
        manifest_digest=h("16"),
        replay_instruction_digest=h("17"),
    )


def _receipt(kind: str, *, status: str = "PASS") -> TypedReceiptV1:
    return TypedReceiptV1(
        kind=kind,
        subject_digest=h("20"),
        status=status,
        issued_at="2026-08-16T00:00:00Z",
        details={"basis": "runtime_test"},
    )


def _all_pass_gates() -> dict[str, str]:
    return {gate: "PASS" for gate in GATE_NAMES}


class TestRunIdentity:
    def test_identity_content_addressed_and_deterministic(self):
        assert _run_identity().run_id == _run_identity().run_id

    def test_any_input_change_breaks_identity(self):
        base = _run_identity()
        changed = _run_identity(engine_tree=h("99"))
        assert base.run_id != changed.run_id

    def test_forged_run_id_rejected(self):
        with pytest.raises(CertificateGateError) as exc:
            _run_identity(run_id="forged")
        assert exc.value.code == "RUN_IDENTITY_MISMATCH"

    def test_invalid_digest_rejected(self):
        with pytest.raises(CertificateGateError) as exc:
            _run_identity(package_hash="short")
        assert exc.value.code == "INVALID_DIGEST"


class TestReceiptSeparation:
    def test_receipt_kind_vocabulary_enforced(self):
        with pytest.raises(CertificateGateError) as exc:
            TypedReceiptV1(
                kind="LeanProofReceipt",
                subject_digest=h("20"),
                status="PASS",
                issued_at="2026-08-16T00:00:00Z",
                details={},
            )
        assert exc.value.code == "INVALID_ENUM"

    def test_receipt_digests_differ_across_kinds(self):
        """任一收据不能冒充另一种证明：kind 进入摘要。"""

        checker = _receipt("CheckerReceiptV2")
        solver = _receipt("SolverReceiptV1")
        assert checker.receipt_digest != solver.receipt_digest


class TestBundlePrivacy:
    def test_absolute_path_rejected_in_bundle(self):
        identity = _run_identity(runtime_options={"audit_out": "C:/state/runs"})
        with pytest.raises(CertificateGateError) as exc:
            _bundle(identity)
        assert exc.value.code == "AUDIT_PRIVACY_VIOLATION"

    def test_key_material_fields_rejected(self):
        identity = _run_identity(runtime_options={"api_token": "abc"})
        with pytest.raises(CertificateGateError) as exc:
            _bundle(identity)
        assert exc.value.code == "AUDIT_PRIVACY_VIOLATION"

    def test_bundle_digest_tamper_sensitive(self):
        identity = _run_identity()
        bundle = _bundle(identity)
        tampered = AuditBundleV2(
            run_identity=identity,
            canonical_request_digest=h("99"),
            canonical_result_digest=bundle.canonical_result_digest,
            events_digest=bundle.events_digest,
            graph_digest=bundle.graph_digest,
            schema_refs=bundle.schema_refs,
            pack_material_digests=bundle.pack_material_digests,
            receipt_digests=bundle.receipt_digests,
            manifest_digest=bundle.manifest_digest,
            replay_instruction_digest=bundle.replay_instruction_digest,
        )
        assert tampered.bundle_digest != bundle.bundle_digest


class TestFormalCertificate:
    def test_full_pass_issues_certificate(self):
        identity = _run_identity()
        bundle = _bundle(identity)
        receipts = (
            _receipt("AdmissionReceiptV1"),
            _receipt("TranslationReceiptV1"),
            _receipt("CheckerReceiptV2"),
        )
        result = issue_formal_certificate(
            run_identity=identity,
            gate_statuses=_all_pass_gates(),
            receipts=receipts,
            solver_used=False,
            completeness_state="complete",
            bundle=bundle,
        )
        assert result["issued"] is True
        assert result["certificate_digest"]

    def test_partial_completeness_blocks_certificate(self):
        identity = _run_identity()
        bundle = _bundle(identity)
        receipts = (
            _receipt("AdmissionReceiptV1"),
            _receipt("TranslationReceiptV1"),
            _receipt("CheckerReceiptV2"),
        )
        for state in ("partial", "truncated", "interrupted"):
            result = issue_formal_certificate(
                run_identity=identity,
                gate_statuses=_all_pass_gates(),
                receipts=receipts,
                solver_used=False,
                completeness_state=state,
                bundle=bundle,
            )
            assert result["issued"] is False
            assert any("completeness" in reason for reason in result["blocked_reasons"])

    def test_checker_disagreement_blocks_certificate(self):
        identity = _run_identity()
        bundle = _bundle(identity)
        receipts = (
            _receipt("AdmissionReceiptV1"),
            _receipt("TranslationReceiptV1"),
            _receipt("CheckerReceiptV2", status="FAIL"),
        )
        result = issue_formal_certificate(
            run_identity=identity,
            gate_statuses={**_all_pass_gates(), "checker": "FAIL"},
            receipts=receipts,
            solver_used=False,
            completeness_state="complete",
            bundle=bundle,
        )
        assert result["issued"] is False
        assert any("checker" in reason for reason in result["blocked_reasons"])

    def test_solver_used_requires_solver_receipt(self):
        identity = _run_identity(solver_identity="z3-4.13.0")
        bundle = _bundle(identity)
        receipts = (
            _receipt("AdmissionReceiptV1"),
            _receipt("TranslationReceiptV1"),
            _receipt("CheckerReceiptV2"),
        )
        result = issue_formal_certificate(
            run_identity=identity,
            gate_statuses=_all_pass_gates(),
            receipts=receipts,
            solver_used=True,
            completeness_state="complete",
            bundle=bundle,
        )
        assert result["issued"] is False
        assert any("missing_receipts" in reason for reason in result["blocked_reasons"])

    def test_bundle_run_identity_mismatch_blocks_certificate(self):
        identity = _run_identity()
        other_bundle = _bundle(_run_identity(engine_tree=h("77")))
        receipts = (
            _receipt("AdmissionReceiptV1"),
            _receipt("TranslationReceiptV1"),
            _receipt("CheckerReceiptV2"),
        )
        result = issue_formal_certificate(
            run_identity=identity,
            gate_statuses=_all_pass_gates(),
            receipts=receipts,
            solver_used=False,
            completeness_state="complete",
            bundle=other_bundle,
        )
        assert result["issued"] is False
        assert "bundle_run_identity_mismatch" in result["blocked_reasons"]
