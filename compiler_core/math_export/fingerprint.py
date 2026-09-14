"""B07-shaped version fingerprints for LMM-bound caches and certificates.

Semantic anchor: ``JurisLean.FullMath.Burden.version_change_invalidates``
(binding ``TARGET:B07`` of the pinned subject) — a cache hit requires an
equal version key, and any change of the key invalidates the entry. On the
JC side the version key is the mathematics subject fingerprint: the LMM
commit, tree, Lean toolchain digest and lake-manifest digest. Entries
without an exact key match are misses; there is no fuzzy or fallback hit.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from compiler_core.canonical_serialization import (
    DIGEST_PATTERN,
    DigestV4,
    digest_value,
)
from compiler_core.math_export.pins import (
    LAKE_MANIFEST_SHA256,
    LEAN_TOOLCHAIN_SHA256,
    SUBJECT_COMMIT,
    SUBJECT_TREE,
)

CACHE_ENTRY_SCHEMA = "jc/lmm-cache-entry/1.0"


def subject_fingerprint(subject: Mapping[str, Any]) -> DigestV4:
    """Canonical digest over the seven subject identity fields."""

    body = {
        "commit": subject["commit"],
        "tree": subject["tree"],
        "repository": subject["repository"],
        "run_id": str(subject["run_id"]),
        "attempt": str(subject["attempt"]),
        "lean_toolchain_sha256": subject["lean_toolchain_sha256"],
        "lake_manifest_sha256": subject["lake_manifest_sha256"],
    }
    return digest_value(body)


@dataclass(frozen=True, slots=True)
class SubjectCacheKeyV1:
    """The four-field mathematics identity a cache entry is sealed with."""

    commit: str
    tree: str
    lean_toolchain_sha256: str
    lake_manifest_sha256: str

    @classmethod
    def from_subject(cls, subject: Mapping[str, Any]) -> "SubjectCacheKeyV1":
        return cls(
            commit=str(subject["commit"]),
            tree=str(subject["tree"]),
            lean_toolchain_sha256=str(subject["lean_toolchain_sha256"]),
            lake_manifest_sha256=str(subject["lake_manifest_sha256"]),
        )

    @classmethod
    def pinned(cls) -> "SubjectCacheKeyV1":
        return cls(
            commit=SUBJECT_COMMIT,
            tree=SUBJECT_TREE,
            lean_toolchain_sha256=LEAN_TOOLCHAIN_SHA256,
            lake_manifest_sha256=LAKE_MANIFEST_SHA256,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "commit": self.commit,
            "tree": self.tree,
            "lean_toolchain_sha256": self.lean_toolchain_sha256,
            "lake_manifest_sha256": self.lake_manifest_sha256,
        }

    def fingerprint(self) -> DigestV4:
        """Canonical digest over the four identity fields."""

        return digest_value(self.to_dict())


def cache_hit(stored: SubjectCacheKeyV1, current: SubjectCacheKeyV1) -> bool:
    """A hit requires every identity field to be equal; anything else misses."""

    return stored == current


def version_change_invalidates(
    stored: SubjectCacheKeyV1, current: SubjectCacheKeyV1
) -> bool:
    """Mirror of the B07 theorem: a changed key invalidates the cached entry."""

    return stored != current


def invalidation_reason(
    stored: SubjectCacheKeyV1, current: SubjectCacheKeyV1
) -> str | None:
    """The first differing identity field, or ``None`` when the entry is hit."""

    for field in (
        "commit", "tree", "lean_toolchain_sha256", "lake_manifest_sha256",
    ):
        if getattr(stored, field) != getattr(current, field):
            return field
    return None


def cache_entry(
    key: SubjectCacheKeyV1, payload_digest: DigestV4
) -> dict[str, Any]:
    """Seal a cache payload with the mathematics subject fingerprint."""

    return {
        "schema_version": CACHE_ENTRY_SCHEMA,
        "cache_key": key.to_dict(),
        "subject_fingerprint": str(key.fingerprint()),
        "payload_digest": str(payload_digest),
    }


def cache_entry_valid(entry: Mapping[str, Any], key: SubjectCacheKeyV1) -> bool:
    """Fail-closed validity check of a sealed cache entry."""

    if entry.get("schema_version") != CACHE_ENTRY_SCHEMA:
        return False
    stored_key = entry.get("cache_key")
    if not isinstance(stored_key, dict):
        return False
    stored = SubjectCacheKeyV1(
        commit=str(stored_key.get("commit")),
        tree=str(stored_key.get("tree")),
        lean_toolchain_sha256=str(stored_key.get("lean_toolchain_sha256")),
        lake_manifest_sha256=str(stored_key.get("lake_manifest_sha256")),
    )
    if stored != key:
        return False
    if entry.get("subject_fingerprint") != str(stored.fingerprint()):
        return False
    payload = entry.get("payload_digest")
    return isinstance(payload, str) and DIGEST_PATTERN.fullmatch(payload) is not None
