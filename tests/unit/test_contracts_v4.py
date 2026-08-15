"""W1：v4 中立合同与唯一兼容入口测试。

覆盖方案 §7：
- Python/JSON round-trip；
- 未知字段、重复 ID、非规范时间、浮点金额、绝对机器路径、未声明扩展 fail closed；
- schema version 与 engine version 不匹配明确拒绝；
- v3 兼容输入不能扩大权限（verified_fact 自报被拒）；
- canonical bytes 与输入顺序无关。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler_core.compat_v3_v4 import migrate_v3_request
from compiler_core.contracts_v4 import (
    CaseRequestV4,
    ContractV4Error,
    SCHEMA_VERSION_V4,
    SemanticResultV4,
    require_engine_match,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schemas" / "jc-v4.schema.json"

DIGEST_A = "a" * 64


def _request_payload(**overrides):
    payload = {
        "request_id": "req-0001",
        "schema_version": SCHEMA_VERSION_V4,
        "legal_context": {"jurisdiction": "PRC", "governing_law": "civil_procedure"},
        "decision_time": "2026-03-01T00:00:00Z",
        "source_bundle_ref": "sb-0001",
        "evidence_manifest_ref": "em-0001",
        "fact_attestation_refs": ["faa-0001"],
        "rule_pack_ref": {"pack_id": "cn-official", "version": "0.0.0", "digest": DIGEST_A},
        "requested_outputs": ["semantic_result"],
        "proposal_refs": ["prop-0001"],
    }
    payload.update(overrides)
    return payload


def _result_payload(**overrides):
    payload = {
        "request_id": "req-0001",
        "schema_version": SCHEMA_VERSION_V4,
        "decision_status": "blocked",
        "admitted_fact_refs": ["f-1"],
        "rejected_fact_refs": ["f-2"],
        "applicable_rule_refs": ["r-1"],
        "inapplicable_rule_refs": ["r-2"],
        "argument_refs": [],
        "attack_refs": [],
        "exception_resolution": {},
        "permission_resolution": {},
        "priority_resolution": {},
        "temporal_numeric_result": {},
        "receipt_refs": [],
        "completeness_state": "complete",
        "interruption_state": "none",
        "run_identity": {"run_id": "run-0001"},
    }
    payload.update(overrides)
    return payload


class TestRoundTrip:
    def test_request_python_json_round_trip(self):
        request = CaseRequestV4.from_dict(_request_payload())
        restored = CaseRequestV4.from_dict(json.loads(json.dumps(request.to_dict())))
        assert restored.canonical_bytes() == request.canonical_bytes()

    def test_result_python_json_round_trip(self):
        result = SemanticResultV4.from_dict(_result_payload())
        restored = SemanticResultV4.from_dict(json.loads(json.dumps(result.to_dict())))
        assert restored.canonical_bytes() == result.canonical_bytes()

    def test_canonical_bytes_ignore_input_order(self):
        first = CaseRequestV4.from_dict(_request_payload(fact_attestation_refs=["b", "a"]))
        second = CaseRequestV4.from_dict(_request_payload(fact_attestation_refs=["a", "b"]))
        assert first.canonical_bytes() == second.canonical_bytes()


class TestFailClosed:
    def test_unknown_field_rejected(self):
        with pytest.raises(ContractV4Error) as exc:
            CaseRequestV4.from_dict(_request_payload(undeclared_extension={"x": 1}))
        assert exc.value.code == "UNKNOWN_FIELD"

    def test_duplicate_fact_attestation_refs_rejected(self):
        with pytest.raises(ContractV4Error) as exc:
            CaseRequestV4.from_dict(_request_payload(fact_attestation_refs=["a", "a"]))
        assert exc.value.code == "DUPLICATE_ID"

    def test_noncanonical_time_rejected(self):
        for bad in ("2026-03-01", "2026-03-01T00:00:00+08:00", "2026-13-99T00:00:00Z"):
            with pytest.raises(ContractV4Error) as exc:
                CaseRequestV4.from_dict(_request_payload(decision_time=bad))
            assert exc.value.code == "NONCANONICAL_TIME"

    def test_float_money_rejected(self):
        with pytest.raises(ContractV4Error) as exc:
            CaseRequestV4.from_dict(_request_payload(
                legal_context={"jurisdiction": "PRC", "governing_law": "civil", "amount": 1.5}
            ))
        assert exc.value.code in ("UNKNOWN_FIELD", "FLOAT_MONEY_FORBIDDEN")

    def test_absolute_machine_path_rejected(self):
        with pytest.raises(ContractV4Error) as exc:
            CaseRequestV4.from_dict(_request_payload(source_bundle_ref="C:/data/bundle.json"))
        assert exc.value.code == "ABSOLUTE_MACHINE_PATH"

    def test_invalid_digest_rejected(self):
        with pytest.raises(ContractV4Error) as exc:
            CaseRequestV4.from_dict(_request_payload(
                rule_pack_ref={"pack_id": "p", "version": "1", "digest": "xyz"}
            ))
        assert exc.value.code == "INVALID_DIGEST"

    def test_schema_version_mismatch_rejected(self):
        with pytest.raises(ContractV4Error) as exc:
            CaseRequestV4.from_dict(_request_payload(schema_version="jc/3.0"))
        assert exc.value.code == "UNSUPPORTED_SCHEMA_VERSION"

    def test_result_admitted_rejected_overlap_rejected(self):
        with pytest.raises(ContractV4Error) as exc:
            SemanticResultV4.from_dict(_result_payload(
                admitted_fact_refs=["f-1"], rejected_fact_refs=["f-1"]
            ))
        assert exc.value.code == "DUPLICATE_ID"

    def test_result_float_inside_resolution_rejected(self):
        with pytest.raises(ContractV4Error) as exc:
            SemanticResultV4.from_dict(_result_payload(
                temporal_numeric_result={"amount": 1.25}
            ))
        assert exc.value.code == "FLOAT_MONEY_FORBIDDEN"

    def test_engine_version_mismatch_rejected(self):
        with pytest.raises(ContractV4Error) as exc:
            require_engine_match("2.9.9")
        assert exc.value.code == "ENGINE_VERSION_MISMATCH"
        require_engine_match("3.0.2")


class TestCompatAdapter:
    def _v3_payload(self, **overrides):
        payload = {
            "schema_version": "3.0",
            "jurisdiction": "PRC",
            "governing_law": "civil_procedure",
            "as_of_date": "2026-03-01",
            "facts": [{"id": "f-1", "status": "candidate_fact"}],
            "rule_pack_id": "cn-official",
            "rule_pack_version": "0.0.0",
            "rule_pack_digest": DIGEST_A,
            "external_source_refs": ["src-1"],
        }
        payload.update(overrides)
        return payload

    def test_projection_is_valid_v4_and_deterministic(self):
        request_a, receipt_a = migrate_v3_request(self._v3_payload())
        request_b, receipt_b = migrate_v3_request(self._v3_payload())
        assert isinstance(request_a, CaseRequestV4)
        assert request_a.canonical_bytes() == request_b.canonical_bytes()
        assert receipt_a.receipt_digest == receipt_b.receipt_digest
        assert receipt_a.defaulted_fields

    def test_verified_fact_self_claim_never_promoted(self):
        request, receipt = migrate_v3_request(self._v3_payload(
            facts=[{"id": "f-1", "status": "verified_fact"}]
        ))
        assert request.fact_attestation_refs == ()
        assert any("verified_fact" in item for item in receipt.rejected_fields)
        assert "legacy-fact:f-1" in request.proposal_refs

    def test_compat_does_not_grant_extra_privileges(self):
        request, _ = migrate_v3_request(self._v3_payload())
        assert request.fact_attestation_refs == ()
        assert request.requested_outputs == ("semantic_result",)

    def test_duplicate_fact_ids_rejected(self):
        with pytest.raises(ContractV4Error) as exc:
            migrate_v3_request(self._v3_payload(
                facts=[{"id": "f-1"}, {"id": "f-1"}]
            ))
        assert exc.value.code == "DUPLICATE_ID"


class TestSchemaAuthorityConsistency:
    """Python authority 与 JSON authority 字段必须逐一对应（§7 动作 2）。"""

    def test_request_required_fields_match(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        schema_required = set(schema["$defs"]["CaseRequestV4"]["required"])
        payload = _request_payload()
        request = CaseRequestV4.from_dict(payload)
        python_fields = set(request.to_dict())
        assert schema_required <= python_fields
        assert set(schema["$defs"]["CaseRequestV4"]["properties"]) == python_fields

    def test_result_required_fields_match(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        schema_required = set(schema["$defs"]["SemanticResultV4"]["required"])
        result = SemanticResultV4.from_dict(_result_payload())
        python_fields = set(result.to_dict())
        assert schema_required == python_fields
        assert set(schema["$defs"]["SemanticResultV4"]["properties"]) == python_fields

    def test_requested_outputs_enum_match(self):
        from compiler_core.contracts_v4 import REQUESTED_OUTPUTS

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        schema_enum = set(
            schema["$defs"]["CaseRequestV4"]["properties"]["requested_outputs"]["items"]["enum"]
        )
        assert schema_enum == set(REQUESTED_OUTPUTS)

    def test_decision_status_enum_match(self):
        from compiler_core.contracts_v4 import _DECISION_STATUSES

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        schema_enum = set(schema["$defs"]["SemanticResultV4"]["properties"]["decision_status"]["enum"])
        assert schema_enum == set(_DECISION_STATUSES)
