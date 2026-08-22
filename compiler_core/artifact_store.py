"""Bounded, exact V4 content resolver with no filesystem or network authority."""

from __future__ import annotations

from dataclasses import dataclass
import re
from threading import Lock

from compiler_core.canonical_serialization import DigestV4
from compiler_core.contracts import (
    ArtifactHandleV4,
    ContentRefV4,
    ContractV4Error,
    DEFAULT_RESOURCE_LIMITS_V4,
    HARD_MAX_RESOURCE_LIMITS_V4,
)


_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_MEDIA_TYPE_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}/"
    r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}\Z"
)


def _fail(code: str, detail: str) -> None:
    raise ContractV4Error(code, detail)


def _identifier(value: object, field: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        _fail("ARTIFACT_ID_GRAMMAR", f"{field} must be an exact logical identifier")
    return value


def _media_type(value: object, field: str) -> str:
    if type(value) is not str or _MEDIA_TYPE_RE.fullmatch(value) is None:
        _fail("ARTIFACT_MEDIA_TYPE", f"{field} must be an exact type/subtype")
    return value


def _nonnegative_integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        _fail("ARTIFACT_BOUNDS", f"{field} must be a non-negative integer")
    return value


def _positive_integer(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        _fail("ARTIFACT_RANGE", f"{field} must be a positive integer")
    return value


def _content_ref(value: object) -> ContentRefV4:
    if type(value) is not ContentRefV4:
        _fail("ARTIFACT_REFERENCE_TYPE", "content_ref must be ContentRefV4")
    _identifier(value.kind, "content_ref.kind")
    return value


@dataclass(frozen=True, slots=True)
class _ArtifactRecordV4:
    artifact_id: str
    content_ref: ContentRefV4
    artifact_kind: str
    media_type: str
    scope: str
    content: bytes


class ArtifactResolverV4:
    """Resolve only exact, process-local records admitted as immutable bytes."""

    def __init__(
        self,
        *,
        max_artifact_bytes: int,
        artifact_page_bytes: int = DEFAULT_RESOURCE_LIMITS_V4["artifact_page_bytes"],
    ) -> None:
        self.max_artifact_bytes = _nonnegative_integer(
            max_artifact_bytes, "max_artifact_bytes"
        )
        if (
            type(artifact_page_bytes) is not int
            or artifact_page_bytes <= 0
            or artifact_page_bytes > HARD_MAX_RESOURCE_LIMITS_V4["artifact_page_bytes"]
        ):
            _fail("ARTIFACT_PAGE_LIMIT", "artifact_page_bytes is outside its hard bound")
        self.artifact_page_bytes = artifact_page_bytes
        self._by_id: dict[str, _ArtifactRecordV4] = {}
        self._by_ref: dict[ContentRefV4, _ArtifactRecordV4] = {}
        self._lock = Lock()

    @staticmethod
    def _metadata(
        *, artifact_id: object, artifact_kind: object, media_type: object, scope: object
    ) -> tuple[str, str, str, str]:
        return (
            _identifier(artifact_id, "artifact_id"),
            _identifier(artifact_kind, "artifact_kind"),
            _media_type(media_type, "media_type"),
            _identifier(scope, "scope"),
        )

    def register_bytes(
        self,
        *,
        artifact_id: str,
        content_ref: ContentRefV4,
        artifact_kind: str,
        media_type: str,
        scope: str,
        content: bytes,
    ) -> ContentRefV4:
        content_ref = _content_ref(content_ref)
        artifact_id, artifact_kind, media_type, scope = self._metadata(
            artifact_id=artifact_id,
            artifact_kind=artifact_kind,
            media_type=media_type,
            scope=scope,
        )
        if type(content) is not bytes:
            _fail("ARTIFACT_CONTENT_TYPE", "content must be immutable bytes")
        if len(content) > self.max_artifact_bytes:
            _fail("ARTIFACT_TOO_LARGE", "content exceeds max_artifact_bytes")
        if DigestV4.from_bytes(content) != content_ref.digest:
            _fail("ARTIFACT_DIGEST_MISMATCH", "content digest does not match content_ref")

        proposed = _ArtifactRecordV4(
            artifact_id=artifact_id,
            content_ref=content_ref,
            artifact_kind=artifact_kind,
            media_type=media_type,
            scope=scope,
            content=content,
        )
        with self._lock:
            existing_id = self._by_id.get(artifact_id)
            if existing_id is not None:
                if existing_id.content_ref.digest != content_ref.digest:
                    _fail("ARTIFACT_ID_COLLISION", "artifact_id already binds another digest")
                if (
                    existing_id.content_ref.kind != content_ref.kind
                    or existing_id.artifact_kind != artifact_kind
                    or existing_id.media_type != media_type
                    or existing_id.scope != scope
                ):
                    _fail(
                        "ARTIFACT_METADATA_COLLISION",
                        "artifact_id metadata cannot be rebound",
                    )
                if existing_id.content != content:
                    _fail(
                        "ARTIFACT_DIGEST_COLLISION",
                        "one digest cannot bind different bytes",
                    )
                return existing_id.content_ref

            existing_ref = self._by_ref.get(content_ref)
            if existing_ref is not None:
                if existing_ref.content != content:
                    _fail(
                        "ARTIFACT_DIGEST_COLLISION",
                        "one digest cannot bind different bytes",
                    )
                _fail(
                    "ARTIFACT_REFERENCE_COLLISION",
                    "content_ref already binds another artifact record",
                )
            self._by_id[artifact_id] = proposed
            self._by_ref[content_ref] = proposed
        return proposed.content_ref

    def _record(self, content_ref: object) -> _ArtifactRecordV4:
        exact_ref = _content_ref(content_ref)
        with self._lock:
            record = self._by_ref.get(exact_ref)
        if record is None:
            _fail("ARTIFACT_NOT_FOUND", "content_ref is not registered")
        return record

    @staticmethod
    def _expected_metadata(
        *,
        expected_artifact_kind: object,
        expected_media_type: object,
        expected_scope: object,
    ) -> tuple[str, str, str]:
        return (
            _identifier(expected_artifact_kind, "expected_artifact_kind"),
            _media_type(expected_media_type, "expected_media_type"),
            _identifier(expected_scope, "expected_scope"),
        )

    @staticmethod
    def _match_metadata(
        record: _ArtifactRecordV4,
        *,
        expected_artifact_kind: str,
        expected_media_type: str,
        expected_scope: str,
    ) -> None:
        if record.artifact_kind != expected_artifact_kind:
            _fail("ARTIFACT_KIND_MISMATCH", "artifact kind does not match expectation")
        if record.media_type != expected_media_type:
            _fail("ARTIFACT_MEDIA_TYPE_MISMATCH", "media type does not match expectation")
        if record.scope != expected_scope:
            _fail("ARTIFACT_SCOPE_MISMATCH", "scope does not match expectation")

    @staticmethod
    def _verified_bytes(record: _ArtifactRecordV4) -> bytes:
        content = record.content
        if type(content) is not bytes or DigestV4.from_bytes(content) != record.content_ref.digest:
            _fail("ARTIFACT_DIGEST_MISMATCH", "stored bytes do not match content_ref")
        return content

    def resolve_content(
        self,
        content_ref: object,
        *,
        expected_artifact_kind: str,
        expected_media_type: str,
        expected_scope: str,
        max_bytes: int,
    ) -> bytes:
        expected_artifact_kind, expected_media_type, expected_scope = (
            self._expected_metadata(
                expected_artifact_kind=expected_artifact_kind,
                expected_media_type=expected_media_type,
                expected_scope=expected_scope,
            )
        )
        max_bytes = _nonnegative_integer(max_bytes, "max_bytes")
        record = self._record(content_ref)
        self._match_metadata(
            record,
            expected_artifact_kind=expected_artifact_kind,
            expected_media_type=expected_media_type,
            expected_scope=expected_scope,
        )
        if len(record.content) > max_bytes:
            _fail("ARTIFACT_TOO_LARGE", "artifact exceeds caller byte bound")
        return self._verified_bytes(record)

    def resolve_handle(
        self,
        handle: object,
        *,
        expected_artifact_kind: str,
        expected_media_type: str,
        expected_scope: str,
        offset: int,
        length: int,
    ) -> bytes:
        if type(handle) is not ArtifactHandleV4:
            _fail("ARTIFACT_REFERENCE_TYPE", "handle must be ArtifactHandleV4")
        expected_artifact_kind, expected_media_type, expected_scope = (
            self._expected_metadata(
                expected_artifact_kind=expected_artifact_kind,
                expected_media_type=expected_media_type,
                expected_scope=expected_scope,
            )
        )
        offset = _nonnegative_integer(offset, "offset")
        length = _positive_integer(length, "length")
        if length > self.artifact_page_bytes:
            _fail("ARTIFACT_PAGE_LIMIT", "requested page exceeds artifact_page_bytes")
        _identifier(handle.artifact_id, "handle.artifact_id")
        _identifier(handle.kind, "handle.kind")
        _identifier(handle.scope, "handle.scope")
        _media_type(handle.media_type, "handle.media_type")
        handle_size_bytes = _nonnegative_integer(
            handle.size_bytes, "handle.size_bytes"
        )
        handle_max_bytes = _nonnegative_integer(
            handle.max_bytes, "handle.max_bytes"
        )
        if handle_max_bytes > handle_size_bytes:
            _fail("ARTIFACT_BOUNDS", "handle byte bound exceeds declared size")
        if handle.kind != expected_artifact_kind:
            _fail("ARTIFACT_KIND_MISMATCH", "handle kind does not match expectation")
        if handle.media_type != expected_media_type:
            _fail("ARTIFACT_MEDIA_TYPE_MISMATCH", "handle media type does not match expectation")
        if handle.scope != expected_scope:
            _fail("ARTIFACT_SCOPE_MISMATCH", "handle scope does not match expectation")

        record = self._record(handle.content_ref)
        self._match_metadata(
            record,
            expected_artifact_kind=expected_artifact_kind,
            expected_media_type=expected_media_type,
            expected_scope=expected_scope,
        )
        if record.artifact_id != handle.artifact_id:
            _fail("ARTIFACT_ID_MISMATCH", "handle artifact_id does not match record")
        if handle_size_bytes != len(record.content):
            _fail("ARTIFACT_SIZE_MISMATCH", "handle size does not match stored bytes")
        requested_end = offset + length
        if requested_end > handle_max_bytes or requested_end > handle_size_bytes:
            _fail("ARTIFACT_RANGE", "requested range exceeds the handle byte bound")
        return self._verified_bytes(record)[offset:requested_end]


__all__ = ["ArtifactResolverV4"]
