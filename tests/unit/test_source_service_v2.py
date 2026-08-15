"""W2：P02/P06/P08 来源、适用时点与路径消费门测试。

用例语义与 tests/fixtures/theory_absorption/p02、p06、p08 对齐；
哈希在运行时用合法 sha256 构造（fixture 中的短哈希是占位符）。
"""

from __future__ import annotations

import pytest

from compiler_core.source_service_v2 import (
    CanonicalLocator,
    EvidenceManifestV1,
    SourceGateError,
    SourcePathEdgeV1,
    SourcePathNodeV1,
    SourcePathV1,
    SourceServiceV2,
    SourceSnapshotV2,
    compute_normalized_hash,
    reject_retrieval_score,
)


def h(prefix: str) -> str:
    return "sha256:" + (prefix * 32)[:64]


def _snapshot(**overrides) -> SourceSnapshotV2:
    payload = {
        "source_id": "src-cpl-2021",
        "authority_tier": "official_first_party",
        "issuer": "standing_committee",
        "title": "civil_procedure_law",
        "publication_time": "2021-12-24T00:00:00Z",
        "effective_time": "2022-01-01T00:00:00Z",
        "revision_time": "2021-12-24T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "canonical_locator": {"kind": "article", "value": "art_85"},
        "raw_hash": h("aa"),
        "normalized_hash": h("bb"),
        "structure_map_ref": "struct-cpl-2021",
        "signature_receipt_ref": "sig-0001",
    }
    payload.update(overrides)
    return SourceSnapshotV2.from_dict(payload)


class TestSourceSnapshot:
    def test_positive_official_snapshot_passes_source_gate(self):
        service = SourceServiceV2()
        snapshot = _snapshot()
        service.register(snapshot)
        outcome = service.source_gate(snapshot)
        assert outcome.status == "PASS"
        assert outcome.gate == "source_gate"

    def test_same_title_different_text_yields_different_identity(self):
        first = _snapshot(raw_hash=h("aa"))
        second = _snapshot(raw_hash=h("cc"))
        assert first.title == second.title
        assert first.snapshot_identity != second.snapshot_identity

    def test_same_source_id_content_swap_rejected(self):
        service = SourceServiceV2()
        service.register(_snapshot(raw_hash=h("aa")))
        with pytest.raises(SourceGateError) as exc:
            service.register(_snapshot(raw_hash=h("cc")))
        assert exc.value.code == "CONTENT_HASH_DIVERGENCE"

    def test_missing_required_field_fails_closed(self):
        payload = _snapshot().to_dict()
        payload.pop("raw_hash")
        payload.pop("snapshot_identity")
        with pytest.raises(SourceGateError) as exc:
            SourceSnapshotV2.from_dict(payload)
        assert exc.value.code == "MISSING_REQUIRED_FIELD"

    def test_unknown_field_fails_closed(self):
        with pytest.raises(SourceGateError) as exc:
            SourceSnapshotV2.from_dict({**_snapshot().to_dict(), "backdoor": True})
        assert exc.value.code == "UNKNOWN_FIELD"

    def test_version_chain_broken_blocks_source_gate(self):
        service = SourceServiceV2()
        snapshot = _snapshot(supersedes="src-cpl-2017")
        outcome = service.source_gate(snapshot)
        assert outcome.status == "BLOCKED"
        assert outcome.reason == "version_chain_broken"

    def test_normalized_hash_recomputable_and_content_sensitive(self):
        text_a = "第八十五条　期间包括法定期间。\n"
        text_a_spacing = "  第八十五条　　期间包括法定期间。   \n"
        text_b = "第八十六条　期间不包括在途时间。"
        assert compute_normalized_hash(text_a) == compute_normalized_hash(text_a_spacing)
        assert compute_normalized_hash(text_a) != compute_normalized_hash(text_b)


class TestEvidenceManifest:
    def test_manifest_round_trip_and_validation(self):
        manifest = EvidenceManifestV1(
            evidence_id="ev-0001",
            document_hash=h("ee"),
            locators=({"kind": "page", "value": "p3", "page": 3},),
            custody_provenance="custody-0001",
            fact_candidate_refs=("fc-1", "fc-2"),
            contradiction_refs=(),
            redaction_state="redacted",
            review_state="reviewed",
        )
        assert manifest.fact_candidate_refs == ("fc-1", "fc-2")
        with pytest.raises(SourceGateError):
            EvidenceManifestV1(
                evidence_id="ev-0002",
                document_hash="not-a-hash",
                locators=({"kind": "page", "value": "p1"},),
                custody_provenance="c",
                fact_candidate_refs=(),
                contradiction_refs=(),
                redaction_state="none",
                review_state="unreviewed",
            )


class TestApplicabilityGate:
    def test_rule_effective_at_decision_time_passes(self):
        service = SourceServiceV2()
        snapshot = _snapshot()
        service.register(snapshot)
        outcome = service.applicability_gate(snapshot, "2026-03-01T00:00:00Z")
        assert outcome.status == "PASS"

    def test_current_version_not_applicable_at_earlier_dispute_time(self):
        service = SourceServiceV2()
        snapshot = _snapshot()
        service.register(snapshot)
        outcome = service.applicability_gate(snapshot, "2019-06-01T00:00:00Z")
        assert outcome.status == "FAIL"
        assert outcome.reason == "rule_not_effective_at_decision_time"

    def test_missing_decision_time_blocks_formal_evaluation(self):
        service = SourceServiceV2()
        snapshot = _snapshot()
        outcome = service.applicability_gate(snapshot, None)
        assert outcome.status == "BLOCKED"
        assert outcome.reason == "decision_time_missing_or_version_chain_broken"

    def test_broken_version_chain_blocks_applicability(self):
        service = SourceServiceV2()
        snapshot = _snapshot(supersedes="src-cpl-2017")
        outcome = service.applicability_gate(snapshot, "2026-03-01T00:00:00Z")
        assert outcome.status == "BLOCKED"

    def test_expired_snapshot_not_applicable(self):
        service = SourceServiceV2()
        snapshot = _snapshot(expiry_time="2025-01-01T00:00:00Z")
        outcome = service.applicability_gate(snapshot, "2026-03-01T00:00:00Z")
        assert outcome.status == "FAIL"


class TestSourcePath:
    def _path(self, *, target_hash: str | None = None, cyclic: bool = False) -> SourcePathV1:
        nodes = (
            SourcePathNodeV1("n1", "statute", h("aa")),
            SourcePathNodeV1("n2", "judicial_interpretation", h("bb")),
        )
        edges = [
            SourcePathEdgeV1("e1", "n1", "n2", "authorizes", h("aa"), target_hash or h("bb"), "art_3", "rr-1"),
        ]
        if cyclic:
            edges.append(SourcePathEdgeV1("e2", "n2", "n1", "cites", h("bb"), h("aa"), "sec_1", "rr-2"))
        return SourcePathV1(
            path_id="sp-0001",
            purpose="interpretation_chain",
            nodes=nodes,
            edges=tuple(edges),
        )

    def test_positive_path_with_terminal_binding_passes(self):
        service = SourceServiceV2()
        snapshot = _snapshot(source_id="src-n2", raw_hash=h("bb"))
        service.register(snapshot)
        path = self._path()
        service.bind_terminal(path.path_id, "n2", "src-n2")
        outcome = service.path_gate(path)
        assert outcome.status == "PASS"
        assert outcome.details["terminal_node"] == "n2"

    def test_broken_link_fails_integrity(self):
        service = SourceServiceV2()
        path = self._path(target_hash=h("ff"))
        outcome = service.path_gate(path)
        assert outcome.status == "FAIL"
        assert outcome.reason == "broken_link_hash_mismatch"

    def test_cycle_blocks_path(self):
        service = SourceServiceV2()
        path = self._path(cyclic=True)
        outcome = service.path_gate(path)
        assert outcome.status == "BLOCKED"
        assert outcome.reason == "cycle_detected"

    def test_unbound_terminal_blocks_authority_hop(self):
        service = SourceServiceV2()
        path = self._path()
        outcome = service.path_gate(path)
        assert outcome.status == "BLOCKED"
        assert outcome.reason == "terminal_source_unregistered"

    def test_retrieval_score_forbidden_inside_path_payload(self):
        with pytest.raises(SourceGateError) as exc:
            reject_retrieval_score({"edges": [{"retrieval_score": 0.9}]}, "path")
        assert exc.value.code == "RETRIEVAL_SCORE_IN_PATH"
