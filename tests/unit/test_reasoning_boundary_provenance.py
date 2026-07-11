import json

from compiler_core.contracts import CertificateKind
from compiler_core.fact_trust_envelope import FactTrustEnvelope, FactTrustStatus
from compiler_core.reasoning_boundary import ensure_required_audit_fields, classify_boundary_result
from compiler_core.result_exporter import export_boundary_json


def test_boundary_result_contains_required_audit_fields():
    result = classify_boundary_result(
        [FactTrustEnvelope("fact.a", True, FactTrustStatus.VERIFIED_FACT, source_ids=("src://a",))],
        used_rule_ids=["rule.a"],
        source_snapshot_ids=["snapshot.a"],
        checker_accepted=True,
        certificate_kind=CertificateKind.FORMAL,
        formal_kernel_used=True,
    ).to_dict()

    assert ensure_required_audit_fields(result)
    assert result["used_fact_keys"] == ["fact.a"]
    assert result["used_rule_ids"] == ["rule.a"]
    assert result["source_snapshot_ids"] == ["snapshot.a"]


def test_provenance_is_summary_not_repeated_source_text():
    long_text = "x" * 10000
    result = classify_boundary_result([
        FactTrustEnvelope(
            "fact.large",
            True,
            FactTrustStatus.VERIFIED_FACT,
            source_ids=("src://large",),
            provenance={"source_text": long_text},
        )
    ]).to_dict()

    encoded = json.dumps(result, ensure_ascii=False)
    assert long_text not in encoded
    assert result["provenance"]["summary_only"] is True


def test_boundary_json_export_is_stable_and_sorted():
    result = classify_boundary_result([
        FactTrustEnvelope(
            "fact.a",
            True,
            FactTrustStatus.VERIFIED_FACT,
            source_ids=("src://a",),
            human_reviewed=True,
        )
    ], checker_accepted=True, certificate_kind=CertificateKind.FORMAL, formal_kernel_used=True).to_dict()

    first = export_boundary_json(result)
    second = export_boundary_json(result)

    assert first == second
    assert json.loads(first)["result_status"] == "accepted_formal_result"


def test_boundary_json_export_rejects_missing_audit_fields():
    try:
        export_boundary_json({"result_status": "accepted_formal_result"})
    except ValueError as exc:
        assert "audit fields" in str(exc)
    else:
        raise AssertionError("missing audit fields should be rejected")

