from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import replace
import json
from pathlib import Path
from typing import Callable

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import DigestV4, canonical_bytes, digest_value
from compiler_core.contracts import (
    CanonicalLocatorV4,
    CanonicalTimeV4,
    ContentRefV4,
    ContractV4Error,
    SignatureEnvelopeV4,
    SourceBundleV4,
    SourceSnapshotV4,
    SourceVersionEdgeV4,
    TrustPolicyV4,
)
from compiler_core.source_service import (
    SOURCE_AUTHENTICITY_RECEIPT_KIND,
    SOURCE_BUNDLE_KIND,
    SOURCE_NORMALIZATION_PROFILE,
    SOURCE_NORMALIZED_KIND,
    SOURCE_PROVENANCE_KIND,
    SOURCE_RAW_KIND,
    SOURCE_RETRIEVAL_RECEIPT_KIND,
    SOURCE_SNAPSHOT_KIND,
    SOURCE_STRUCTURE_MAP_KIND,
    SourceServiceV4,
    normalize_source_bytes,
    source_authenticity_payload_digest,
    source_snapshot_ref,
    source_version_receipt_bytes,
    source_version_receipt_ref,
)
from compiler_core.trust import TrustKeyV4, TrustVerifierV4


ROOT = Path(__file__).resolve().parents[2]
THEORY = ROOT / "tests" / "fixtures" / "theory_absorption"
P02 = json.loads((THEORY / "p02_source_snapshot.json").read_text(encoding="utf-8"))
P06 = json.loads((THEORY / "p06_temporal_applicability.json").read_text(encoding="utf-8"))
P08 = json.loads((THEORY / "p08_source_path.json").read_text(encoding="utf-8"))
TRUST_FIXTURE = json.loads(
    (ROOT / "tests" / "fixtures" / "golden" / "v4-test-trust-policy.json").read_text(
        encoding="utf-8"
    )
)
KEY_FIXTURE = json.loads((ROOT / TRUST_FIXTURE["key_fixture"]).read_text(encoding="utf-8"))
NOW = CanonicalTimeV4("2026-08-22T12:00:00Z")


def _policy() -> TrustPolicyV4:
    profile = next(
        item for item in TRUST_FIXTURE["profiles"] if item["scope"] == "source-authenticity"
    )
    body = {
        "policy_id": TRUST_FIXTURE["policy_id"],
        "allowed_algorithms": ["Ed25519"],
        "trusted_key_ids": [KEY_FIXTURE["key_id"]],
        "revoked_key_ids": [],
        "allowed_issuers": [TRUST_FIXTURE["issuer"]],
        "allowed_roles": [profile["role"]],
        "allowed_scopes": [profile["scope"]],
        "allowed_artifact_kinds": [profile["artifact_kind"]],
        "valid_from": {"wire": TRUST_FIXTURE["valid_from"]},
        "valid_to": {"wire": TRUST_FIXTURE["valid_to"]},
        "authorization_policy_ref": TRUST_FIXTURE["policy_refs"]["authorization"],
        "revocation_policy_ref": TRUST_FIXTURE["policy_refs"]["revocation"],
        "replay_policy_ref": TRUST_FIXTURE["policy_refs"]["replay"],
        "separation_of_duties_ref": TRUST_FIXTURE["policy_refs"]["separation_of_duties"],
    }
    return TrustPolicyV4.from_dict({**body, "policy_digest": str(digest_value(body))})


def _error_code(call: Callable[[], object]) -> str:
    with pytest.raises(ContractV4Error) as caught:
        call()
    return caught.value.code


def _version_locator(
    source: SourceSnapshotV4,
    target: SourceSnapshotV4,
) -> CanonicalLocatorV4:
    return CanonicalLocatorV4(
        "uri",
        f"authority.example/{source.source_id}-to-{target.source_id}",
        None,
        None,
        None,
    )


class _SourceHarness:
    def __init__(self) -> None:
        self.resolver = ArtifactResolverV4(max_artifact_bytes=262_144)
        policy = _policy()
        key = TrustKeyV4(
            key_id=KEY_FIXTURE["key_id"],
            issuer=TRUST_FIXTURE["issuer"],
            principal_id=TRUST_FIXTURE["principal_id"],
            roles=("source_attestor",),
            scopes=("source-authenticity",),
            artifact_kinds=(SOURCE_SNAPSHOT_KIND,),
            public_key=b64decode(KEY_FIXTURE["public_key_base64"], validate=True),
            production_allowed=False,
        )
        self.service = SourceServiceV4(
            self.resolver,
            TrustVerifierV4(policy=policy, keys=(key,), target_environment="test"),
        )
        self.policy = policy
        self.private_key = Ed25519PrivateKey.from_private_bytes(
            b64decode(KEY_FIXTURE["private_key_base64"], validate=True)
        )
        self.snapshots: dict[ContentRefV4, SourceSnapshotV4] = {}
        self._registered: set[ContentRefV4] = set()
        self._serial = 0

    def _register(
        self,
        reference: ContentRefV4,
        content: bytes,
        *,
        artifact_kind: str,
        media_type: str,
        scope: str,
    ) -> None:
        if reference in self._registered:
            return
        self._serial += 1
        self.resolver.register_bytes(
            artifact_id=f"w2-source-{self._serial}",
            content_ref=reference,
            artifact_kind=artifact_kind,
            media_type=media_type,
            scope=scope,
            content=content,
        )
        self._registered.add(reference)

    def stage_snapshot(
        self,
        source_id: str,
        *,
        raw: bytes = "第八十五条  人民法院应当调查取证。".encode(),
        title: str = "civil_procedure_law",
        publication_time: str = "2020-12-24T00:00:00Z",
        effective_from: str = "2021-01-01T00:00:00Z",
        effective_to: str | None = None,
        retrieved_at: str = "2026-08-01T00:00:00Z",
        register_raw: bool = True,
        normalized_override: bytes | None = None,
        tamper_signature: bool = False,
        fake_receipt: bool = False,
        predecessors: tuple[SourceSnapshotV4, ...] = (),
    ) -> tuple[ContentRefV4, SourceSnapshotV4]:
        raw_ref = ContentRefV4(SOURCE_RAW_KIND, DigestV4.from_bytes(raw))
        normalized = (
            normalize_source_bytes(raw)
            if normalized_override is None
            else normalized_override
        )
        normalized_ref = ContentRefV4(
            SOURCE_NORMALIZED_KIND, DigestV4.from_bytes(normalized)
        )
        if register_raw:
            self._register(
                raw_ref,
                raw,
                artifact_kind=SOURCE_RAW_KIND,
                media_type="text/plain",
                scope="source-content",
            )
        self._register(
            normalized_ref,
            normalized,
            artifact_kind=SOURCE_NORMALIZED_KIND,
            media_type="text/plain",
            scope="source-content",
        )
        structure_bytes = canonical_bytes({"source_id": source_id, "kind": "structure-map"})
        structure_ref = ContentRefV4(
            SOURCE_STRUCTURE_MAP_KIND, DigestV4.from_bytes(structure_bytes)
        )
        provenance_bytes = canonical_bytes({
            "source_id": source_id,
            "acquisition_method": "official-download",
        })
        provenance_ref = ContentRefV4(
            SOURCE_PROVENANCE_KIND, DigestV4.from_bytes(provenance_bytes)
        )
        self._register(
            structure_ref,
            structure_bytes,
            artifact_kind=SOURCE_STRUCTURE_MAP_KIND,
            media_type="application/json",
            scope="source-provenance",
        )
        self._register(
            provenance_ref,
            provenance_bytes,
            artifact_kind=SOURCE_PROVENANCE_KIND,
            media_type="application/json",
            scope="source-provenance",
        )
        placeholder_receipt = ContentRefV4(
            SOURCE_AUTHENTICITY_RECEIPT_KIND,
            DigestV4.from_bytes(f"placeholder:{source_id}".encode()),
        )
        snapshot = SourceSnapshotV4(
            source_id=source_id,
            jurisdiction="CN",
            authority_tier="official_first_party",
            issuer="standing_committee",
            title=title,
            publication_time=CanonicalTimeV4(publication_time),
            effective_from=CanonicalTimeV4(effective_from),
            effective_to=None if effective_to is None else CanonicalTimeV4(effective_to),
            retrieved_at=CanonicalTimeV4(retrieved_at),
            canonical_locator=CanonicalLocatorV4(
                "uri", f"authority.example/{source_id}", None, None, None
            ),
            raw_digest=raw_ref.digest,
            normalization_profile=SOURCE_NORMALIZATION_PROFILE,
            normalized_digest=normalized_ref.digest,
            structure_map_ref=structure_ref,
            authenticity_receipt_ref=placeholder_receipt,
            provenance_refs=(provenance_ref,),
            acquisition_method="official-download",
            license_status="verified",
            distribution_status="permitted",
        )
        version_receipts: list[ContentRefV4] = []
        for predecessor in predecessors:
            locator = _version_locator(predecessor, snapshot)
            receipt_bytes = source_version_receipt_bytes(
                predecessor,
                snapshot,
                "supersedes",
                locator,
            )
            receipt_ref = source_version_receipt_ref(
                predecessor,
                snapshot,
                "supersedes",
                locator,
            )
            self._register(
                receipt_ref,
                receipt_bytes,
                artifact_kind=SOURCE_RETRIEVAL_RECEIPT_KIND,
                media_type="application/json",
                scope="source-path",
            )
            version_receipts.append(receipt_ref)
        envelope_body = {
            "algorithm": "Ed25519",
            "key_id": KEY_FIXTURE["key_id"],
            "issuer": TRUST_FIXTURE["issuer"],
            "role": "source_attestor",
            "scope": "source-authenticity",
            "kind": SOURCE_SNAPSHOT_KIND,
            "schema_version": "jc/4.0",
            "subject_digest": str(snapshot.raw_digest),
            "run_identity_ref": None,
            "status": "APPROVED",
            "issued_at": {"wire": "2026-08-22T11:00:00Z"},
            "expires_at": {"wire": "2027-08-22T11:00:00Z"},
            "nonce": f"source-nonce-{self._serial}-{source_id}",
            "evidence_refs": [
                raw_ref.to_dict(),
                normalized_ref.to_dict(),
                structure_ref.to_dict(),
                provenance_ref.to_dict(),
                *(reference.to_dict() for reference in version_receipts),
            ],
            "payload_digest": str(source_authenticity_payload_digest(snapshot)),
            "policy_digest": str(self.policy.policy_digest),
            "revocation_ref": self.policy.revocation_policy_ref.to_dict(),
        }
        signature = self.private_key.sign(canonical_bytes(envelope_body))
        if tamper_signature:
            signature = bytes([signature[0] ^ 1, *signature[1:]])
        envelope = SignatureEnvelopeV4.from_dict({
            **envelope_body,
            "signature": b64encode(signature).decode("ascii"),
        })
        receipt_bytes = envelope.canonical_bytes()
        receipt_ref = ContentRefV4(
            SOURCE_AUTHENTICITY_RECEIPT_KIND, DigestV4.from_bytes(receipt_bytes)
        )
        if not fake_receipt:
            self._register(
                receipt_ref,
                receipt_bytes,
                artifact_kind=SOURCE_AUTHENTICITY_RECEIPT_KIND,
                media_type="application/json",
                scope="source-authenticity",
            )
        snapshot = replace(
            snapshot,
            authenticity_receipt_ref=(placeholder_receipt if fake_receipt else receipt_ref),
        )
        snapshot_ref = source_snapshot_ref(snapshot)
        self._register(
            snapshot_ref,
            snapshot.canonical_bytes(),
            artifact_kind=SOURCE_SNAPSHOT_KIND,
            media_type="application/json",
            scope="source-authenticity",
        )
        self.snapshots[snapshot_ref] = snapshot
        return snapshot_ref, snapshot

    def admit(self, source_id: str, **kwargs: object) -> ContentRefV4:
        reference, _ = self.stage_snapshot(source_id, **kwargs)
        return self.service.admit_snapshot(reference, now=NOW)

    def bundle(
        self,
        references: tuple[ContentRefV4, ...],
        edges: tuple[tuple[ContentRefV4, ContentRefV4], ...],
        *,
        root: ContentRefV4 | None = None,
        terminal: ContentRefV4 | None = None,
    ) -> ContentRefV4:
        self._serial += 1
        edge_values: list[SourceVersionEdgeV4] = []
        for source_ref, target_ref in edges:
            if source_ref in self.snapshots and target_ref in self.snapshots:
                source = self.snapshots[source_ref]
                target = self.snapshots[target_ref]
                locator = _version_locator(source, target)
                receipt_ref = source_version_receipt_ref(
                    source,
                    target,
                    "supersedes",
                    locator,
                )
            else:
                locator = CanonicalLocatorV4(
                    "uri", "authority.example/unknown-edge", None, None, None
                )
                receipt_ref = ContentRefV4(
                    SOURCE_RETRIEVAL_RECEIPT_KIND,
                    DigestV4.from_bytes(b"unknown-edge-receipt"),
                )
            edge_values.append(
                SourceVersionEdgeV4(
                    source_ref=source_ref,
                    target_ref=target_ref,
                    relation="supersedes",
                    locator=locator,
                    retrieval_receipt_ref=receipt_ref,
                )
            )
        body = {
            "bundle_id": f"source-bundle-{self._serial}",
            "root_source_ref": (root or references[0]).to_dict(),
            "terminal_source_ref": (terminal or references[-1]).to_dict(),
            "snapshots": [self.snapshots[reference].to_dict() for reference in references],
            "version_edges": [edge.to_dict() for edge in edge_values],
        }
        bundle = SourceBundleV4.from_dict({
            **body,
            "bundle_digest": str(digest_value(body)),
        })
        bundle_bytes = canonical_bytes(bundle.digest_body())
        bundle_ref = ContentRefV4(SOURCE_BUNDLE_KIND, bundle.canonical_digest())
        self._register(
            bundle_ref,
            bundle_bytes,
            artifact_kind=SOURCE_BUNDLE_KIND,
            media_type="application/json",
            scope="source-path",
        )
        return bundle_ref


@pytest.mark.parametrize(
    ("earlier", "later"),
    (
        ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00.1Z"),
        ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00.000000001Z"),
    ),
)
def test_fractional_instants_compare_chronologically(earlier: str, later: str) -> None:
    assert P06["cases"][0]["id"] == "p06-positive-01"
    assert not earlier < later
    assert CanonicalTimeV4(earlier) < CanonicalTimeV4(later)


@pytest.mark.parametrize(
    "wire",
    (
        "2026-01-01T00:00:00+00:00",
        "2026-02-30T00:00:00Z",
        "2026-01-01T00:00:60Z",
        None,
    ),
)
def test_offset_invalid_date_leap_second_and_missing_time_fail(wire: object) -> None:
    with pytest.raises(ContractV4Error):
        CanonicalTimeV4.parse(wire)


@pytest.mark.parametrize(
    ("decision_time", "accepted"),
    (
        ("2021-01-01T00:00:00Z", True),
        ("2022-01-01T00:00:00Z", False),
    ),
)
def test_effective_interval_is_half_open_at_exact_boundary(
    decision_time: str, accepted: bool
) -> None:
    assert P06["cases"][1]["id"] == "p06-negative-01"
    harness = _SourceHarness()
    reference = harness.admit("boundary", effective_to="2022-01-01T00:00:00Z")
    bundle = harness.bundle((reference,), ())
    if accepted:
        assert harness.service.resolve_applicable(
            bundle, decision_time=CanonicalTimeV4(decision_time)
        ) == reference
    else:
        assert _error_code(lambda: harness.service.resolve_applicable(
            bundle, decision_time=CanonicalTimeV4(decision_time)
        )) == "SOURCE_VERSION_NOT_EFFECTIVE"


def test_normalization_is_recomputable_and_content_sensitive() -> None:
    assert P02["cases"][1]["id"] == "p02-negative-01"
    left = "A\u030A\t  第八十五条\r\n  正文  ".encode()
    right = "Å 第八十五条\n正文".encode()
    assert normalize_source_bytes(left) == normalize_source_bytes(right)
    assert normalize_source_bytes(right + "变更".encode()) != normalize_source_bytes(right)


def test_real_signed_resolved_bytes_admit_source_snapshot() -> None:
    fixture = P02["cases"][0]["input"]["snapshot"]
    harness = _SourceHarness()
    reference, snapshot = harness.stage_snapshot(
        fixture["source_id"],
        title=fixture["title"],
        publication_time=fixture["publication_time"],
        effective_from=fixture["effective_time"],
    )
    assert harness.service.admit_snapshot(reference, now=NOW) == reference
    assert harness.snapshots[reference] == snapshot
    tampered = replace(snapshot, title="caller-mutated-title")
    tampered_ref = source_snapshot_ref(tampered)
    harness._register(
        tampered_ref,
        tampered.canonical_bytes(),
        artifact_kind=SOURCE_SNAPSHOT_KIND,
        media_type="application/json",
        scope="source-authenticity",
    )
    assert _error_code(lambda: harness.service.admit_snapshot(tampered_ref, now=NOW)) == (
        "TRUST_PAYLOAD_MISMATCH"
    )


def test_cached_source_authenticity_still_obeys_signature_expiry() -> None:
    harness = _SourceHarness()
    reference = harness.admit("cached-expiry")
    assert _error_code(
        lambda: harness.service.admit_snapshot(
            reference,
            now=CanonicalTimeV4("2027-08-22T11:00:00Z"),
        )
    ) == "SOURCE_AUTHENTICITY_EXPIRED"


def test_cached_source_authenticity_still_obeys_signature_issued_at() -> None:
    harness = _SourceHarness()
    reference = harness.admit("cached-issued-at")
    assert _error_code(
        lambda: harness.service.admit_snapshot(
            reference,
            now=CanonicalTimeV4("2026-08-22T10:00:00Z"),
        )
    ) == "SOURCE_AUTHENTICITY_EXPIRED"


def test_source_authenticity_signature_cannot_predate_retrieval() -> None:
    harness = _SourceHarness()
    reference, _ = harness.stage_snapshot(
        "signature-before-retrieval",
        retrieved_at="2026-08-23T00:00:00Z",
    )
    assert _error_code(
        lambda: harness.service.admit_snapshot(
            reference,
            now=CanonicalTimeV4("2026-08-24T00:00:00Z"),
        )
    ) == "SOURCE_AUTHENTICITY_TIME"


def test_same_title_different_raw_bytes_have_different_snapshot_identity() -> None:
    harness = _SourceHarness()
    left = harness.admit("same-title-a", raw=b"version a", title="same-title")
    right = harness.admit("same-title-b", raw=b"version b", title="same-title")
    assert left != right
    assert harness.snapshots[left].raw_digest != harness.snapshots[right].raw_digest


def test_source_bundle_full_wire_hash_cannot_replace_self_digest_identity() -> None:
    harness = _SourceHarness()
    source_ref = harness.admit("self-digest-bundle")
    body = {
        "bundle_id": "full-wire-is-not-logical-identity",
        "root_source_ref": source_ref.to_dict(),
        "terminal_source_ref": source_ref.to_dict(),
        "snapshots": [harness.snapshots[source_ref].to_dict()],
        "version_edges": [],
    }
    bundle = SourceBundleV4.from_dict({
        **body,
        "bundle_digest": str(digest_value(body)),
    })
    full_wire = bundle.canonical_bytes()
    wrong_ref = ContentRefV4(SOURCE_BUNDLE_KIND, DigestV4.from_bytes(full_wire))
    harness._register(
        wrong_ref,
        full_wire,
        artifact_kind=SOURCE_BUNDLE_KIND,
        media_type="application/json",
        scope="source-path",
    )
    assert _error_code(
        lambda: harness.service.resolve_applicable(
            wrong_ref,
            decision_time=CanonicalTimeV4("2026-08-22T00:00:00Z"),
        )
    ) == "SOURCE_NONCANONICAL_JSON"


def test_legal_version_chain_is_edge_order_independent() -> None:
    assert P08["cases"][0]["id"] == "p08-positive-01"
    harness = _SourceHarness()
    first = harness.admit(
        "chain-2020", effective_from="2020-01-01T00:00:00Z", effective_to="2021-01-01T00:00:00Z"
    )
    second = harness.admit(
        "chain-2021",
        effective_from="2021-01-01T00:00:00Z",
        effective_to="2022-01-01T00:00:00Z",
        predecessors=(harness.snapshots[first],),
    )
    third = harness.admit(
        "chain-2022",
        effective_from="2022-01-01T00:00:00Z",
        predecessors=(harness.snapshots[second],),
    )
    references = (first, second, third)
    forward = harness.bundle(references, ((first, second), (second, third)))
    reversed_edges = harness.bundle(references, ((second, third), (first, second)))
    decision = CanonicalTimeV4("2021-06-01T00:00:00Z")
    assert harness.service.resolve_applicable(forward, decision_time=decision) == second
    assert harness.service.resolve_applicable(reversed_edges, decision_time=decision) == second
