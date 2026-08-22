from __future__ import annotations

from hypothesis import assume, given, settings, strategies as st
import pytest

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import DigestV4
from compiler_core.contracts import ContentRefV4, ContractV4Error


def _ref(content: bytes, kind: str = "opaque-bytes") -> ContentRefV4:
    return ContentRefV4(kind=kind, digest=DigestV4.from_bytes(content))


def _register(
    resolver: ArtifactResolverV4,
    content: bytes,
    *,
    artifact_id: str = "artifact-1",
    artifact_kind: str = "source-bundle",
    media_type: str = "application/json",
    scope: str = "formal-run",
) -> ContentRefV4:
    content_ref = _ref(content)
    return resolver.register_bytes(
        artifact_id=artifact_id,
        content_ref=content_ref,
        artifact_kind=artifact_kind,
        media_type=media_type,
        scope=scope,
        content=content,
    )


@settings(max_examples=50, derandomize=True, deadline=None)
@given(st.binary(max_size=4096))
def test_registered_bytes_round_trip_under_exact_typed_metadata(content: bytes) -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=4096)
    content_ref = _register(resolver, content)
    assert content_ref.digest == DigestV4.from_bytes(content)
    assert resolver.resolve_content(
        content_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=4096,
    ) == content


@settings(max_examples=50, derandomize=True, deadline=None)
@given(st.binary(min_size=2, max_size=4096))
def test_exact_byte_limit_passes_and_one_less_rejects(content: bytes) -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=len(content))
    content_ref = _register(resolver, content)
    assert resolver.resolve_content(
        content_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=len(content),
    ) == content
    with pytest.raises(ContractV4Error, match="^ARTIFACT_TOO_LARGE:"):
        resolver.resolve_content(
            content_ref,
            expected_artifact_kind="source-bundle",
            expected_media_type="application/json",
            expected_scope="formal-run",
            max_bytes=len(content) - 1,
        )


@settings(max_examples=50, derandomize=True, deadline=None)
@given(st.binary(max_size=4096), st.integers(min_value=1, max_value=5))
def test_same_id_same_digest_and_metadata_is_idempotent(
    content: bytes, repetitions: int,
) -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=4096)
    first = _register(resolver, content)
    for _ in range(repetitions):
        assert _register(resolver, content) == first


@settings(max_examples=50, derandomize=True, deadline=None)
@given(st.binary(max_size=2048), st.binary(max_size=2048))
def test_same_id_different_digest_never_overwrites(first: bytes, second: bytes) -> None:
    assume(first != second)
    resolver = ArtifactResolverV4(max_artifact_bytes=2048)
    first_ref = _register(resolver, first)
    with pytest.raises(ContractV4Error, match="^ARTIFACT_ID_COLLISION:"):
        _register(resolver, second)
    assert resolver.resolve_content(
        first_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=2048,
    ) == first


@settings(max_examples=50, derandomize=True, deadline=None)
@given(
    st.binary(max_size=2048),
    st.sampled_from(("content_ref_kind", "artifact_kind", "media_type", "scope")),
)
def test_same_id_same_digest_each_metadata_change_preserves_original(
    content: bytes, changed_field: str,
) -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=2048)
    content_ref = _register(resolver, content)
    changed = {
        "artifact_kind": "rule-pack",
        "media_type": "text/plain",
        "scope": "other-run",
    }
    registration = {
        "artifact_kind": "source-bundle",
        "media_type": "application/json",
        "scope": "formal-run",
    }
    if changed_field != "content_ref_kind":
        registration[changed_field] = changed[changed_field]
    with pytest.raises(ContractV4Error, match="^ARTIFACT_METADATA_COLLISION:"):
        if changed_field == "content_ref_kind":
            resolver.register_bytes(
                artifact_id="artifact-1",
                content_ref=_ref(content, kind="other-bytes"),
                content=content,
                **registration,
            )
        else:
            _register(resolver, content, **registration)
    assert resolver.resolve_content(
        content_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=2048,
    ) == content


@settings(max_examples=50, derandomize=True, deadline=None)
@given(st.binary(min_size=1, max_size=2048), st.data())
def test_any_single_bit_mutation_fails_old_ref_and_preserves_original(
    content: bytes, drawn: st.DataObject,
) -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=2048)
    content_ref = _register(resolver, content)
    byte_index = drawn.draw(st.integers(min_value=0, max_value=len(content) - 1))
    bit_mask = 1 << drawn.draw(st.integers(min_value=0, max_value=7))
    mutated = bytearray(content)
    mutated[byte_index] ^= bit_mask
    with pytest.raises(ContractV4Error, match="^ARTIFACT_DIGEST_MISMATCH:"):
        resolver.register_bytes(
            artifact_id="artifact-mutated",
            content_ref=content_ref,
            artifact_kind="source-bundle",
            media_type="application/json",
            scope="formal-run",
            content=bytes(mutated),
        )
    assert resolver.resolve_content(
        content_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=2048,
    ) == content


@settings(max_examples=50, derandomize=True, deadline=None)
@given(st.binary(max_size=2048))
def test_same_ref_different_id_never_rebinds_and_preserves_original(
    content: bytes,
) -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=2048)
    content_ref = _register(resolver, content)
    with pytest.raises(ContractV4Error, match="^ARTIFACT_REFERENCE_COLLISION:"):
        _register(resolver, content, artifact_id="artifact-2")
    assert resolver.resolve_content(
        content_ref,
        expected_artifact_kind="source-bundle",
        expected_media_type="application/json",
        expected_scope="formal-run",
        max_bytes=2048,
    ) == content
