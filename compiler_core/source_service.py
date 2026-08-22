"""Resolved-byte source authenticity, time, and version-path verification."""

from __future__ import annotations

import re
import unicodedata

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import (
    DigestV4,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    CanonicalLocatorV4,
    CanonicalTimeV4,
    ContentRefV4,
    ContractV4Error,
    SignatureEnvelopeV4,
    SourceBundleV4,
    SourceSnapshotV4,
)
from compiler_core.trust import TrustVerifierV4


SOURCE_NORMALIZATION_PROFILE = "nfc-collapse-whitespace"
SOURCE_RAW_KIND = "source-raw"
SOURCE_NORMALIZED_KIND = "source-normalized"
SOURCE_SNAPSHOT_KIND = "source-snapshot"
SOURCE_BUNDLE_KIND = "source-bundle"
SOURCE_AUTHENTICITY_RECEIPT_KIND = "source-authenticity-receipt"
SOURCE_STRUCTURE_MAP_KIND = "source-structure-map"
SOURCE_PROVENANCE_KIND = "source-provenance"
SOURCE_RETRIEVAL_RECEIPT_KIND = "source-retrieval-receipt"

_VERIFIED_AUTHORITY_TIERS = frozenset({
    "official_first_party",
    "official_mirror",
    "third_party_verified",
})


def _fail(code: str, detail: str) -> None:
    raise ContractV4Error(code, detail)


def normalize_source_bytes(
    raw: bytes,
    profile: str = SOURCE_NORMALIZATION_PROFILE,
) -> bytes:
    """Return the sole W2 source normalization: UTF-8, NFC, collapsed whitespace."""

    if type(raw) is not bytes:
        _fail("SOURCE_BYTES_TYPE", "source content must be immutable bytes")
    if profile != SOURCE_NORMALIZATION_PROFILE:
        _fail("SOURCE_NORMALIZATION_PROFILE", "unknown source normalization profile")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractV4Error("SOURCE_RAW_UTF8", "source content must be valid UTF-8") from exc
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in unicodedata.normalize("NFC", text).splitlines()
    ]
    return "\n".join(lines).strip().encode("utf-8")


def source_authenticity_payload_digest(snapshot: SourceSnapshotV4) -> DigestV4:
    """Bind all snapshot metadata except the receipt ref that locates this signature."""

    if type(snapshot) is not SourceSnapshotV4:
        _fail("SOURCE_INPUT_TYPE", "snapshot must be SourceSnapshotV4")
    payload = snapshot.to_dict()
    del payload["authenticity_receipt_ref"]
    return digest_value(payload)


def source_snapshot_ref(snapshot: SourceSnapshotV4) -> ContentRefV4:
    if type(snapshot) is not SourceSnapshotV4:
        _fail("SOURCE_INPUT_TYPE", "snapshot must be SourceSnapshotV4")
    return ContentRefV4(SOURCE_SNAPSHOT_KIND, snapshot.canonical_digest())


def source_version_receipt_bytes(
    source: SourceSnapshotV4,
    target: SourceSnapshotV4,
    relation: str,
    locator: CanonicalLocatorV4,
) -> bytes:
    """Bind one version edge without creating a snapshot/signature digest cycle."""

    if (
        type(source) is not SourceSnapshotV4
        or type(target) is not SourceSnapshotV4
        or type(relation) is not str
        or not relation
        or type(locator) is not CanonicalLocatorV4
    ):
        _fail("SOURCE_VERSION_RECEIPT_INPUT", "version receipt inputs are invalid")
    return canonical_bytes({
        "schema_version": "jc/source-version-receipt/1.0",
        "source_payload_digest": str(source_authenticity_payload_digest(source)),
        "target_payload_digest": str(source_authenticity_payload_digest(target)),
        "relation": relation,
        "locator": locator.to_dict(),
    })


def source_version_receipt_ref(
    source: SourceSnapshotV4,
    target: SourceSnapshotV4,
    relation: str,
    locator: CanonicalLocatorV4,
) -> ContentRefV4:
    receipt = source_version_receipt_bytes(source, target, relation, locator)
    return ContentRefV4(SOURCE_RETRIEVAL_RECEIPT_KIND, DigestV4.from_bytes(receipt))


class SourceServiceV4:
    """Admit signed source snapshots and resolve one applicable connected version."""

    def __init__(self, resolver: ArtifactResolverV4, trust: TrustVerifierV4) -> None:
        if type(resolver) is not ArtifactResolverV4 or type(trust) is not TrustVerifierV4:
            _fail("SOURCE_INPUT_TYPE", "resolver and trust must be exact V4 services")
        self._resolver = resolver
        self._trust = trust
        self._verified: dict[ContentRefV4, SourceSnapshotV4] = {}
        self._signed_evidence: dict[ContentRefV4, frozenset[ContentRefV4]] = {}
        self._source_ids: dict[str, ContentRefV4] = {}

    def _resolve_json_contract(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
        contract: (
            type[SourceSnapshotV4]
            | type[SourceBundleV4]
            | type[SignatureEnvelopeV4]
        ),
    ) -> SourceSnapshotV4 | SourceBundleV4 | SignatureEnvelopeV4:
        if type(reference) is not ContentRefV4 or reference.kind != kind:
            _fail("SOURCE_REF_KIND", f"expected {kind} content reference")
        raw = self._resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type="application/json",
            expected_scope=scope,
            max_bytes=self._resolver.max_artifact_bytes,
        )
        try:
            document = parse_json_document(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ContractV4Error("SOURCE_JSON_UTF8", f"{kind} must be valid UTF-8") from exc
        if type(document) is not dict:
            _fail("SOURCE_JSON_TYPE", f"{kind} must be a JSON object")
        value = contract.from_dict(document)
        if raw != value.canonical_bytes():
            _fail("SOURCE_NONCANONICAL_JSON", f"{kind} must use canonical V4 bytes")
        return value

    def _resolve_source_bytes(
        self,
        snapshot: SourceSnapshotV4,
    ) -> tuple[ContentRefV4, ContentRefV4]:
        raw_ref = ContentRefV4(SOURCE_RAW_KIND, snapshot.raw_digest)
        normalized_ref = ContentRefV4(SOURCE_NORMALIZED_KIND, snapshot.normalized_digest)
        raw = self._resolver.resolve_content(
            raw_ref,
            expected_artifact_kind=SOURCE_RAW_KIND,
            expected_media_type="text/plain",
            expected_scope="source-content",
            max_bytes=self._resolver.max_artifact_bytes,
        )
        normalized = self._resolver.resolve_content(
            normalized_ref,
            expected_artifact_kind=SOURCE_NORMALIZED_KIND,
            expected_media_type="text/plain",
            expected_scope="source-content",
            max_bytes=self._resolver.max_artifact_bytes,
        )
        expected = normalize_source_bytes(raw, snapshot.normalization_profile)
        if (
            normalized != expected
            or DigestV4.from_bytes(expected) != snapshot.normalized_digest
        ):
            _fail(
                "SOURCE_NORMALIZED_DIGEST_MISMATCH",
                "normalized bytes do not match raw source bytes",
            )
        return raw_ref, normalized_ref

    def admit_snapshot(
        self,
        snapshot_ref: ContentRefV4,
        *,
        now: CanonicalTimeV4,
    ) -> ContentRefV4:
        """Resolve, recompute, authenticate, then register one immutable snapshot."""

        if type(snapshot_ref) is not ContentRefV4:
            _fail("SOURCE_INPUT_TYPE", "snapshot_ref must be ContentRefV4")
        if type(now) is not CanonicalTimeV4:
            _fail("SOURCE_INPUT_TYPE", "now must be CanonicalTimeV4")
        existing = self._verified.get(snapshot_ref)
        if existing is not None:
            return snapshot_ref
        snapshot = self._resolve_json_contract(
            snapshot_ref,
            kind=SOURCE_SNAPSHOT_KIND,
            scope="source-authenticity",
            contract=SourceSnapshotV4,
        )
        if type(snapshot) is not SourceSnapshotV4:
            _fail("SOURCE_CONTRACT_TYPE", "resolved source snapshot has the wrong type")
        if source_snapshot_ref(snapshot) != snapshot_ref:
            _fail(
                "SOURCE_SNAPSHOT_REF_MISMATCH",
                "snapshot bytes do not match their source reference",
            )
        if snapshot.authority_tier not in _VERIFIED_AUTHORITY_TIERS:
            _fail("SOURCE_AUTHORITY_TIER", "source authority tier is not verified")
        if snapshot.retrieved_at < snapshot.publication_time or now < snapshot.retrieved_at:
            _fail(
                "SOURCE_TIME_ORDER",
                "publication, retrieval, and verification times are inconsistent",
            )

        raw_ref, normalized_ref = self._resolve_source_bytes(snapshot)
        self._resolver.resolve_content(
            snapshot.structure_map_ref,
            expected_artifact_kind=SOURCE_STRUCTURE_MAP_KIND,
            expected_media_type="application/json",
            expected_scope="source-provenance",
            max_bytes=self._resolver.max_artifact_bytes,
        )
        for provenance_ref in snapshot.provenance_refs:
            self._resolver.resolve_content(
                provenance_ref,
                expected_artifact_kind=SOURCE_PROVENANCE_KIND,
                expected_media_type="application/json",
                expected_scope="source-provenance",
                max_bytes=self._resolver.max_artifact_bytes,
            )
        envelope = self._resolve_json_contract(
            snapshot.authenticity_receipt_ref,
            kind=SOURCE_AUTHENTICITY_RECEIPT_KIND,
            scope="source-authenticity",
            contract=SignatureEnvelopeV4,
        )
        if type(envelope) is not SignatureEnvelopeV4:
            _fail("SOURCE_CONTRACT_TYPE", "resolved signature envelope has the wrong type")
        expected_evidence = (
            raw_ref,
            normalized_ref,
            snapshot.structure_map_ref,
            *snapshot.provenance_refs,
        )
        signed_evidence = frozenset(envelope.evidence_refs)
        if (
            len(signed_evidence) != len(envelope.evidence_refs)
            or not set(expected_evidence).issubset(signed_evidence)
            or any(
                reference not in expected_evidence
                and reference.kind != SOURCE_RETRIEVAL_RECEIPT_KIND
                for reference in signed_evidence
            )
        ):
            _fail(
                "SOURCE_SIGNATURE_EVIDENCE",
                "authenticity signature does not bind source evidence",
            )
        self._trust.verify(
            envelope,
            expected_subject_digest=snapshot.raw_digest,
            expected_payload_digest=source_authenticity_payload_digest(snapshot),
            required_role="source_attestor",
            required_scope="source-authenticity",
            required_artifact_kind=SOURCE_SNAPSHOT_KIND,
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(),
        )
        prior = self._source_ids.get(snapshot.source_id)
        if prior is not None and prior != snapshot_ref:
            _fail("SOURCE_ID_COLLISION", "source_id cannot be rebound to different snapshot bytes")
        self._verified[snapshot_ref] = snapshot
        self._signed_evidence[snapshot_ref] = signed_evidence
        self._source_ids[snapshot.source_id] = snapshot_ref
        return snapshot_ref

    def _require_snapshot(self, snapshot_ref: ContentRefV4) -> SourceSnapshotV4:
        snapshot = self._verified.get(snapshot_ref)
        if snapshot is None:
            _fail("SOURCE_SNAPSHOT_NOT_VERIFIED", "snapshot has not passed source authenticity")
        return snapshot

    def resolve_applicable(
        self,
        bundle_ref: ContentRefV4,
        *,
        decision_time: CanonicalTimeV4,
    ) -> ContentRefV4:
        """Verify a connected DAG independent of edge order and select one active version."""

        if type(decision_time) is not CanonicalTimeV4:
            _fail("SOURCE_INPUT_TYPE", "decision_time must be CanonicalTimeV4")
        bundle = self._resolve_json_contract(
            bundle_ref,
            kind=SOURCE_BUNDLE_KIND,
            scope="source-path",
            contract=SourceBundleV4,
        )
        if type(bundle) is not SourceBundleV4:
            _fail("SOURCE_CONTRACT_TYPE", "resolved source bundle has the wrong type")
        if not bundle.bundle_id or not bundle.snapshots:
            _fail("SOURCE_PATH_EMPTY", "source bundle must contain snapshots")

        by_ref: dict[ContentRefV4, SourceSnapshotV4] = {}
        source_ids: set[str] = set()
        for snapshot in bundle.snapshots:
            reference = source_snapshot_ref(snapshot)
            if reference in by_ref or snapshot.source_id in source_ids:
                _fail("SOURCE_PATH_DUPLICATE_NODE", "source path contains a duplicate snapshot")
            if self._require_snapshot(reference) != snapshot:
                _fail("SOURCE_SNAPSHOT_NOT_VERIFIED", "bundle snapshot differs from admitted bytes")
            by_ref[reference] = snapshot
            source_ids.add(snapshot.source_id)

        nodes = set(by_ref)
        if bundle.root_source_ref not in nodes or bundle.terminal_source_ref not in nodes:
            _fail("SOURCE_PATH_ENDPOINT", "declared root or terminal is not a verified node")
        adjacency = {node: set() for node in nodes}
        indegree = {node: 0 for node in nodes}
        edge_pairs: set[tuple[ContentRefV4, ContentRefV4]] = set()
        for edge in bundle.version_edges:
            if edge.source_ref not in nodes or edge.target_ref not in nodes:
                _fail("SOURCE_PATH_UNKNOWN_NODE", "version edge references an unknown snapshot")
            pair = (edge.source_ref, edge.target_ref)
            if edge.source_ref == edge.target_ref or pair in edge_pairs:
                _fail(
                    "SOURCE_PATH_DUPLICATE_EDGE",
                    "version path contains a self or duplicate edge",
                )
            if not edge.relation:
                _fail("SOURCE_PATH_RELATION", "version edge relation must not be empty")
            edge_pairs.add(pair)
            adjacency[edge.source_ref].add(edge.target_ref)
            indegree[edge.target_ref] += 1

        roots = {node for node in nodes if indegree[node] == 0}
        terminals = {node for node in nodes if not adjacency[node]}
        if len(roots) != 1:
            _fail("SOURCE_PATH_ROOT_COUNT", "source path must have one root")
        if len(terminals) != 1:
            _fail("SOURCE_PATH_TERMINAL_COUNT", "source path must have one terminal")
        if roots != {bundle.root_source_ref}:
            _fail("SOURCE_PATH_ROOT_MISMATCH", "declared root does not match graph root")
        if terminals != {bundle.terminal_source_ref}:
            _fail(
                "SOURCE_PATH_TERMINAL_MISMATCH",
                "declared terminal does not match graph terminal",
            )

        reachable: set[ContentRefV4] = set()
        pending = [bundle.root_source_ref]
        while pending:
            node = pending.pop()
            if node in reachable:
                continue
            reachable.add(node)
            pending.extend(adjacency[node] - reachable)
        if reachable != nodes:
            _fail("SOURCE_PATH_DISCONNECTED", "every source path node must be root-reachable")

        remaining = dict(indegree)
        pending = [node for node, degree in remaining.items() if degree == 0]
        visited = 0
        while pending:
            node = pending.pop()
            visited += 1
            for target in adjacency[node]:
                remaining[target] -= 1
                if remaining[target] == 0:
                    pending.append(target)
        if visited != len(nodes):
            _fail("SOURCE_PATH_CYCLE", "source path must be acyclic")
        for source, target in edge_pairs:
            if not by_ref[source].effective_from < by_ref[target].effective_from:
                _fail("SOURCE_VERSION_ORDER", "version edges must advance effective time")
        ordered_versions = sorted(by_ref.values(), key=lambda item: item.effective_from)
        for previous, current in zip(ordered_versions, ordered_versions[1:]):
            if (
                previous.effective_to is None
                or current.effective_from < previous.effective_to
            ):
                _fail("SOURCE_VERSION_OVERLAP", "source versions must not overlap")
        for edge in bundle.version_edges:
            source = by_ref[edge.source_ref]
            target = by_ref[edge.target_ref]
            if (
                source.jurisdiction,
                source.issuer,
                source.title,
            ) != (
                target.jurisdiction,
                target.issuer,
                target.title,
            ):
                _fail(
                    "SOURCE_VERSION_IDENTITY",
                    "version edges must join the same jurisdiction, issuer, and title",
                )
            receipt = self._resolver.resolve_content(
                edge.retrieval_receipt_ref,
                expected_artifact_kind=SOURCE_RETRIEVAL_RECEIPT_KIND,
                expected_media_type="application/json",
                expected_scope="source-path",
                max_bytes=self._resolver.max_artifact_bytes,
            )
            if receipt != source_version_receipt_bytes(
                source,
                target,
                edge.relation,
                edge.locator,
            ):
                _fail(
                    "SOURCE_VERSION_RECEIPT_MISMATCH",
                    "version receipt does not bind the exact edge",
                )
            if edge.retrieval_receipt_ref not in self._signed_evidence[edge.target_ref]:
                _fail(
                    "SOURCE_VERSION_RECEIPT_UNSIGNED",
                    "target authenticity signature does not bind the version receipt",
                )

        applicable = [
            reference
            for reference, snapshot in by_ref.items()
            if snapshot.effective_from <= decision_time
            and (snapshot.effective_to is None or decision_time < snapshot.effective_to)
        ]
        if not applicable:
            _fail("SOURCE_VERSION_NOT_EFFECTIVE", "no source version applies at decision time")
        if len(applicable) != 1:
            _fail("SOURCE_VERSION_OVERLAP", "multiple source versions apply at decision time")
        return applicable[0]


__all__ = [
    "SOURCE_AUTHENTICITY_RECEIPT_KIND",
    "SOURCE_BUNDLE_KIND",
    "SOURCE_NORMALIZATION_PROFILE",
    "SOURCE_NORMALIZED_KIND",
    "SOURCE_PROVENANCE_KIND",
    "SOURCE_RAW_KIND",
    "SOURCE_RETRIEVAL_RECEIPT_KIND",
    "SOURCE_SNAPSHOT_KIND",
    "SOURCE_STRUCTURE_MAP_KIND",
    "SourceServiceV4",
    "normalize_source_bytes",
    "source_authenticity_payload_digest",
    "source_snapshot_ref",
    "source_version_receipt_bytes",
    "source_version_receipt_ref",
]
