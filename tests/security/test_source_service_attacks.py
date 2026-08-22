from __future__ import annotations

import pytest

from compiler_core.canonical_serialization import DigestV4
from compiler_core.contracts import CanonicalTimeV4, ContentRefV4
from compiler_core.source_service import (
    SOURCE_RETRIEVAL_RECEIPT_KIND,
    SOURCE_SNAPSHOT_KIND,
    source_version_receipt_bytes,
    source_version_receipt_ref,
)
from tests.contract.test_source_service import (
    NOW,
    P08,
    _error_code,
    _SourceHarness,
    _version_locator,
)


def _four_snapshots(harness: _SourceHarness) -> tuple[ContentRefV4, ...]:
    return tuple(
        harness.admit(
            f"attack-{index}",
            effective_from=f"20{20 + index}-01-01T00:00:00Z",
        )
        for index in range(4)
    )


def test_disconnected_source_path_cannot_pass() -> None:
    assert P08["cases"][1]["id"] == "p08-negative-01"
    harness = _SourceHarness()
    first, second, third, fourth = _four_snapshots(harness)
    bundle = harness.bundle(
        (first, second, third, fourth),
        ((first, second), (third, fourth)),
        root=first,
        terminal=fourth,
    )
    assert _error_code(lambda: harness.service.resolve_applicable(
        bundle, decision_time=CanonicalTimeV4("2026-01-01T00:00:00Z")
    )) == "SOURCE_PATH_ROOT_COUNT"


@pytest.mark.parametrize(
    ("attack", "expected_code"),
    (
        ("multi-root", "SOURCE_PATH_ROOT_COUNT"),
        ("multi-terminal", "SOURCE_PATH_TERMINAL_COUNT"),
        ("orphan", "SOURCE_PATH_ROOT_COUNT"),
        ("cycle", "SOURCE_PATH_CYCLE"),
        ("duplicate-edge", "SOURCE_PATH_DUPLICATE_EDGE"),
        ("unknown-endpoint", "SOURCE_PATH_UNKNOWN_NODE"),
    ),
)
def test_source_path_graph_attacks_fail(attack: str, expected_code: str) -> None:
    harness = _SourceHarness()
    first, second, third, fourth = _four_snapshots(harness)
    references = (first, second, third)
    root, terminal = first, third
    if attack == "multi-root":
        edges = ((first, third), (second, third))
    elif attack == "multi-terminal":
        edges = ((first, second), (first, third))
    elif attack == "orphan":
        edges = ((first, second),)
    elif attack == "cycle":
        edges = (
            (first, second),
            (second, third),
            (third, second),
            (third, fourth),
        )
        references = (first, second, third, fourth)
        terminal = fourth
    elif attack == "duplicate-edge":
        edges = ((first, second), (first, second), (second, third))
    else:
        unknown = ContentRefV4(
            SOURCE_SNAPSHOT_KIND, DigestV4.from_bytes(b"unknown-source-snapshot")
        )
        edges = ((first, unknown),)
        references = (first, second)
        terminal = second
    bundle = harness.bundle(references, edges, root=root, terminal=terminal)
    assert _error_code(lambda: harness.service.resolve_applicable(
        bundle, decision_time=CanonicalTimeV4("2026-01-01T00:00:00Z")
    )) == expected_code


@pytest.mark.parametrize("attack", ("missing-raw", "wrong-normalized"))
def test_source_content_mutations_fail_before_trust(attack: str) -> None:
    harness = _SourceHarness()
    reference, _ = harness.stage_snapshot(
        f"content-{attack}",
        register_raw=attack != "missing-raw",
        normalized_override=(
            b"attacker normalized bytes" if attack == "wrong-normalized" else None
        ),
    )
    expected = (
        "ARTIFACT_NOT_FOUND"
        if attack == "missing-raw"
        else "SOURCE_NORMALIZED_DIGEST_MISMATCH"
    )
    assert _error_code(lambda: harness.service.admit_snapshot(reference, now=NOW)) == expected


def test_signature_bit_flip_cannot_authenticate_source_bytes() -> None:
    harness = _SourceHarness()
    reference, _ = harness.stage_snapshot("bad-signature", tamper_signature=True)
    assert _error_code(lambda: harness.service.admit_snapshot(reference, now=NOW)) == (
        "TRUST_SIGNATURE_INVALID"
    )


def test_caller_snapshot_and_forged_receipt_cannot_create_trust() -> None:
    harness = _SourceHarness()
    reference, snapshot = harness.stage_snapshot("caller-pass", fake_receipt=True)
    assert _error_code(lambda: harness.service.admit_snapshot(snapshot, now=NOW)) == (
        "SOURCE_INPUT_TYPE"
    )
    assert _error_code(lambda: harness.service.admit_snapshot(reference, now=NOW)) == (
        "ARTIFACT_NOT_FOUND"
    )

    unrelated = _SourceHarness()
    first = unrelated.admit(
        "unrelated-a",
        title="law-a",
        effective_from="2020-01-01T00:00:00Z",
        effective_to="2021-01-01T00:00:00Z",
    )
    second = unrelated.admit(
        "unrelated-b",
        title="law-b",
        effective_from="2021-01-01T00:00:00Z",
    )
    unrelated_bundle = unrelated.bundle((first, second), ((first, second),))
    assert _error_code(lambda: unrelated.service.resolve_applicable(
        unrelated_bundle, decision_time=CanonicalTimeV4("2021-06-01T00:00:00Z")
    )) == "SOURCE_VERSION_IDENTITY"

    unsigned = _SourceHarness()
    first = unsigned.admit(
        "unsigned-2020",
        effective_from="2020-01-01T00:00:00Z",
        effective_to="2021-01-01T00:00:00Z",
    )
    second = unsigned.admit(
        "unsigned-2021",
        effective_from="2021-01-01T00:00:00Z",
    )
    unsigned_bundle = unsigned.bundle((first, second), ((first, second),))
    decision = CanonicalTimeV4("2021-06-01T00:00:00Z")
    assert _error_code(lambda: unsigned.service.resolve_applicable(
        unsigned_bundle, decision_time=decision
    )) == "ARTIFACT_NOT_FOUND"
    source = unsigned.snapshots[first]
    target = unsigned.snapshots[second]
    locator = _version_locator(source, target)
    receipt_ref = source_version_receipt_ref(source, target, "supersedes", locator)
    unsigned._register(
        receipt_ref,
        source_version_receipt_bytes(source, target, "supersedes", locator),
        artifact_kind=SOURCE_RETRIEVAL_RECEIPT_KIND,
        media_type="application/json",
        scope="source-path",
    )
    assert _error_code(lambda: unsigned.service.resolve_applicable(
        unsigned_bundle, decision_time=decision
    )) == "SOURCE_VERSION_RECEIPT_UNSIGNED"

    overlap = _SourceHarness()
    root = overlap.admit(
        "diamond-root",
        effective_from="2020-01-01T00:00:00Z",
        effective_to="2021-01-01T00:00:00Z",
    )
    left = overlap.admit(
        "diamond-left",
        effective_from="2021-01-01T00:00:00Z",
        effective_to="2024-01-01T00:00:00Z",
        predecessors=(overlap.snapshots[root],),
    )
    right = overlap.admit(
        "diamond-right",
        effective_from="2022-01-01T00:00:00Z",
        effective_to="2023-01-01T00:00:00Z",
        predecessors=(overlap.snapshots[root],),
    )
    terminal = overlap.admit(
        "diamond-terminal",
        effective_from="2024-01-01T00:00:00Z",
        predecessors=(overlap.snapshots[left], overlap.snapshots[right]),
    )
    overlap_bundle = overlap.bundle(
        (root, left, right, terminal),
        ((root, left), (root, right), (left, terminal), (right, terminal)),
    )
    assert _error_code(lambda: overlap.service.resolve_applicable(
        overlap_bundle, decision_time=CanonicalTimeV4("2024-06-01T00:00:00Z")
    )) == "SOURCE_VERSION_OVERLAP"
