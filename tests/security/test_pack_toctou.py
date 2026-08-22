from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier, Event, Lock

import pytest

from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import DigestV4
from compiler_core.contracts import ContentRefV4, ContractV4Error
from compiler_core.rule_packs import (
    PACK_CONFIG_KIND,
    PACK_MANIFEST_KIND,
    PACK_SIGNATURE_KIND,
    RULE_KIND,
    RULE_PACK_SCOPE,
)
from compiler_core.source_service import SOURCE_SNAPSHOT_KIND
from tests.contract.test_rule_packs import NOW, _PackHarness
from tests.contract.test_source_service import _SourceHarness


def _only_ref(harness: _PackHarness, kind: str) -> ContentRefV4:
    references = tuple(
        reference for reference in harness.resolver._by_ref if reference.kind == kind
    )
    assert len(references) == 1
    return references[0]


@pytest.mark.parametrize(
    "target_kind",
    (PACK_MANIFEST_KIND, RULE_KIND, SOURCE_SNAPSHOT_KIND, PACK_CONFIG_KIND),
)
def test_verified_bytes_are_the_executed_bytes(
    monkeypatch: pytest.MonkeyPatch,
    target_kind: str,
) -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    resolver = harness.resolver
    target_ref = _only_ref(harness, target_kind)
    manifest_ref = _only_ref(harness, PACK_MANIFEST_KIND)
    rule_ref = _only_ref(harness, RULE_KIND)
    source_ref = _only_ref(harness, SOURCE_SNAPSHOT_KIND)
    config_ref = _only_ref(harness, PACK_CONFIG_KIND)
    original_record = resolver._by_ref[target_ref]
    original_resolve = resolver.resolve_content
    before_refs = frozenset(resolver._by_ref)
    swapped = False

    def resolve_then_swap(*args: object, **kwargs: object) -> bytes:
        nonlocal swapped
        content = original_resolve(*args, **kwargs)
        if not swapped:
            with resolver._lock:
                resolver._by_ref[target_ref] = replace(
                    original_record,
                    content=b'{"attacker":"replacement"}',
                )
            swapped = True
        return content

    monkeypatch.setattr(resolver, "resolve_content", resolve_then_swap)
    try:
        verified = harness.verifier.verify(pack_ref, now=NOW)
        assert verified.status == "VERIFIED_ACTIVE"
        assert verified.verifier_issued
        assert verified.manifest_ref == manifest_ref
        assert verified.rules[0].rule_digest == rule_ref.digest
        assert verified.manifest.source_refs == (source_ref,)
        assert verified.manifest.config_refs == (config_ref,)
        assert verified.domain_bindings[0][2] == (rule_ref,)
    finally:
        with resolver._lock:
            resolver._by_ref[target_ref] = original_record

    assert swapped
    assert verified.pack_ref == pack_ref
    assert len(verified.rules) == 1
    assert frozenset(resolver._by_ref) == before_refs


@pytest.mark.parametrize(
    "target_kind",
    (PACK_MANIFEST_KIND, RULE_KIND, SOURCE_SNAPSHOT_KIND, PACK_CONFIG_KIND),
)
def test_corrupt_cache_retry_blocks_then_restore_returns_same_handle(
    target_kind: str,
) -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    first = harness.verifier.verify(pack_ref, now=NOW)
    target_ref = _only_ref(harness, target_kind)
    original_record = harness.resolver._by_ref[target_ref]

    with harness.resolver._lock:
        harness.resolver._by_ref[target_ref] = replace(
            original_record,
            content=b'{"attacker":"replacement"}',
        )
    with pytest.raises(ContractV4Error):
        harness.verifier.verify(pack_ref, now=NOW)
    assert harness.verifier._verified == {pack_ref: first}
    assert first.verifier_issued

    with harness.resolver._lock:
        harness.resolver._by_ref[target_ref] = original_record
    restored = harness.verifier.verify(pack_ref, now=NOW)
    assert restored is first


def test_concurrent_pack_loads_return_one_verified_handle() -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    before_refs = frozenset(harness.resolver._by_ref)
    barrier = Barrier(8)

    def load() -> object:
        barrier.wait()
        return harness.verifier.verify(pack_ref, now=NOW)

    with ThreadPoolExecutor(max_workers=8) as executor:
        handles = tuple(executor.map(lambda _index: load(), range(8)))

    assert all(handle is handles[0] for handle in handles)
    assert handles[0].verifier_issued
    assert frozenset(harness.resolver._by_ref) == before_refs


def test_successful_snapshot_commits_nonces_and_retry_stays_idempotent() -> None:
    harness = _PackHarness()
    pack_ref = harness.build()

    first = harness.verifier.verify(pack_ref, now=NOW)
    with harness.trust._nonce_lock:
        committed = frozenset(harness.trust._seen_nonces)

    assert {
        ("w2-03-source-key", "source-nonce"),
        ("w2-03-release-key", "release-nonce"),
    } <= committed
    assert harness.source_service._source_ids == {
        "cn-cpl-article-85": harness.last_source_ref,
    }
    admitted = harness.source_service._require_snapshot(harness.last_source_ref)
    assert admitted.source_id == "cn-cpl-article-85"
    assert harness.last_source_ref in harness.source_service._verified_issued_at
    assert harness.last_source_ref in harness.source_service._verified_expires_at
    assert harness.last_source_ref in harness.source_service._signed_evidence
    assert harness.verifier.verify(pack_ref, now=NOW) is first
    with harness.trust._nonce_lock:
        assert frozenset(harness.trust._seen_nonces) == committed


def test_preadmitted_source_can_enter_first_pack_without_replay() -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    source_nonce = ("w2-03-source-key", "source-nonce")
    assert harness.source_service.admit_snapshot(harness.last_source_ref, now=NOW) == (
        harness.last_source_ref
    )
    with harness.trust._nonce_lock:
        before = frozenset(harness.trust._seen_nonces)
    assert source_nonce in before

    verified = harness.verifier.verify(pack_ref, now=NOW)
    assert verified.verifier_issued
    with harness.trust._nonce_lock:
        after = frozenset(harness.trust._seen_nonces)
    assert source_nonce in after
    assert len(after) > len(before)


def test_existing_source_identity_ledger_survives_fresh_snapshot() -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    source_id = "cn-cpl-article-85"
    conflicting_ref = ContentRefV4(
        SOURCE_SNAPSHOT_KIND,
        DigestV4.from_bytes(b"previous-source-snapshot"),
    )
    harness.source_service._source_ids[source_id] = conflicting_ref

    with pytest.raises(ContractV4Error, match="SOURCE_ID_COLLISION"):
        harness.verifier.verify(pack_ref, now=NOW)
    assert harness.source_service._source_ids == {source_id: conflicting_ref}
    assert harness.source_service._verified == {}
    assert harness.source_service._verified_issued_at == {}
    assert harness.source_service._verified_expires_at == {}
    assert harness.source_service._signed_evidence == {}
    assert harness.verifier._signature_principals == {}

    del harness.source_service._source_ids[source_id]
    restored = harness.verifier.verify(pack_ref, now=NOW)
    assert restored.verifier_issued
    assert harness.source_service._source_ids == {source_id: harness.last_source_ref}


def test_source_identity_rebound_during_snapshot_cannot_issue_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    source_id = "cn-cpl-article-85"
    harness.source_service._source_ids[source_id] = harness.last_source_ref
    conflicting_ref = ContentRefV4(
        SOURCE_SNAPSHOT_KIND,
        DigestV4.from_bytes(b"concurrent-source-snapshot"),
    )
    verify_snapshot = harness.verifier._verify_snapshot

    def verify_then_rebind_source(*args: object, **kwargs: object) -> object:
        handle = verify_snapshot(*args, **kwargs)
        harness.source_service._source_ids[source_id] = conflicting_ref
        return handle

    monkeypatch.setattr(harness.verifier, "_verify_snapshot", verify_then_rebind_source)
    with pytest.raises(ContractV4Error, match="SOURCE_ID_COLLISION"):
        harness.verifier.verify(pack_ref, now=NOW)
    cached = harness.verifier._verified[pack_ref]
    assert not cached.verifier_issued
    assert harness.verifier._signature_principals == {}
    assert harness.source_service._source_ids == {source_id: conflicting_ref}
    assert harness.source_service._verified == {}
    assert harness.source_service._verified_issued_at == {}
    assert harness.source_service._verified_expires_at == {}
    assert harness.source_service._signed_evidence == {}

    harness.source_service._source_ids[source_id] = harness.last_source_ref
    monkeypatch.setattr(harness.verifier, "_verify_snapshot", verify_snapshot)
    restored = harness.verifier.verify(pack_ref, now=NOW)
    assert restored is cached
    assert restored.verifier_issued


def test_source_admission_check_and_commit_share_one_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _SourceHarness()
    left_ref, _ = harness.stage_snapshot("shared-source-id", raw=b"left source")
    right_ref, _ = harness.stage_snapshot("shared-source-id", raw=b"right source")
    original_admit = harness.service._admit_snapshot
    first_entered = Event()
    second_attempted = Event()
    counter_lock = Lock()
    active = 0
    maximum_active = 0
    call_count = 0

    def controlled_admit(*args: object, **kwargs: object) -> ContentRefV4:
        nonlocal active, maximum_active, call_count
        with counter_lock:
            call_count += 1
            call_index = call_count
            active += 1
            maximum_active = max(maximum_active, active)
        try:
            if call_index == 1:
                first_entered.set()
                assert second_attempted.wait(2)
            return original_admit(*args, **kwargs)
        finally:
            with counter_lock:
                active -= 1

    monkeypatch.setattr(harness.service, "_admit_snapshot", controlled_admit)

    def admit_second() -> str:
        second_attempted.set()
        try:
            harness.service.admit_snapshot(right_ref, now=NOW)
        except ContractV4Error as exc:
            return exc.code
        return "ACCEPTED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(harness.service.admit_snapshot, left_ref, now=NOW)
        assert first_entered.wait(2)
        second = executor.submit(admit_second)
        assert first.result() == left_ref
        assert second.result() == "SOURCE_ID_COLLISION"

    assert maximum_active == 1
    assert harness.service._source_ids == {"shared-source-id": left_ref}
    with harness.service._trust._nonce_lock:
        assert len(harness.service._trust._seen_nonces) == 1

    del harness.service._source_ids["shared-source-id"]
    assert harness.service.admit_snapshot(right_ref, now=NOW) == right_ref
    with harness.service._trust._nonce_lock:
        assert len(harness.service._trust._seen_nonces) == 2


def test_source_applicability_reader_shares_admission_lock() -> None:
    harness = _SourceHarness()
    source_ref = harness.admit("locked-reader")
    bundle_ref = harness.bundle((source_ref,), ())
    attempted = Event()

    def resolve() -> ContentRefV4:
        attempted.set()
        return harness.service.resolve_applicable(bundle_ref, decision_time=NOW)

    with ThreadPoolExecutor(max_workers=1) as executor:
        with harness.service._admission_lock:
            future = executor.submit(resolve)
            assert attempted.wait(2)
            assert not future.done()
        assert future.result() == source_ref


def test_trust_change_at_commit_rolls_back_all_live_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    trust_state = harness.verifier._trust_state
    live_reads = 0

    def state_then_change(trust: object = None) -> tuple[object, ...]:
        nonlocal live_reads
        state = trust_state(trust)
        if trust is harness.trust:
            live_reads += 1
            if live_reads == 3:
                harness.trust.target_environment = "production"
        return state

    monkeypatch.setattr(harness.verifier, "_trust_state", state_then_change)
    with pytest.raises(ContractV4Error, match="PACK_TRUST_STATE_CHANGED"):
        harness.verifier.verify(pack_ref, now=NOW)
    cached = harness.verifier._verified[pack_ref]
    assert live_reads >= 4
    assert not cached.verifier_issued
    assert harness.trust._seen_nonces == set()
    assert harness.source_service._verified == {}
    assert harness.source_service._verified_issued_at == {}
    assert harness.source_service._verified_expires_at == {}
    assert harness.source_service._signed_evidence == {}
    assert harness.source_service._source_ids == {}
    assert harness.verifier._signature_principals == {}

    harness.trust.target_environment = "test"
    monkeypatch.setattr(harness.verifier, "_trust_state", trust_state)
    restored = harness.verifier.verify(pack_ref, now=NOW)
    assert restored is cached
    assert restored.verifier_issued


def test_failed_retry_preserves_existing_issued_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    first = harness.verifier.verify(pack_ref, now=NOW)
    with harness.trust._nonce_lock:
        nonces_before = frozenset(harness.trust._seen_nonces)
    source_ids_before = dict(harness.source_service._source_ids)
    trust_state = harness.verifier._trust_state
    live_reads = 0

    def state_then_change(trust: object = None) -> tuple[object, ...]:
        nonlocal live_reads
        state = trust_state(trust)
        if trust is harness.trust:
            live_reads += 1
            if live_reads == 3:
                harness.trust.target_environment = "production"
        return state

    monkeypatch.setattr(harness.verifier, "_trust_state", state_then_change)
    with pytest.raises(ContractV4Error, match="PACK_TRUST_STATE_CHANGED"):
        harness.verifier.verify(pack_ref, now=NOW)

    harness.trust.target_environment = "test"
    monkeypatch.setattr(harness.verifier, "_trust_state", trust_state)
    assert first.verifier_issued
    assert harness.verifier.verify(pack_ref, now=NOW) is first
    with harness.trust._nonce_lock:
        assert frozenset(harness.trust._seen_nonces) == nonces_before
    assert harness.source_service._source_ids == source_ids_before


def test_previously_consumed_nonce_blocks_without_poisoning_retry() -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    release_nonce = ("w2-03-release-key", "release-nonce")
    with harness.trust._nonce_lock:
        harness.trust._seen_nonces.add(release_nonce)

    with pytest.raises(ContractV4Error, match="TRUST_REPLAY"):
        harness.verifier.verify(pack_ref, now=NOW)
    assert pack_ref not in harness.verifier._verified
    assert harness.verifier._signature_principals == {}

    with harness.trust._nonce_lock:
        harness.trust._seen_nonces.remove(release_nonce)
    assert harness.verifier.verify(pack_ref, now=NOW).verifier_issued


def test_nonce_consumed_during_snapshot_cannot_issue_cached_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    release_nonce = ("w2-03-release-key", "release-nonce")
    verify_snapshot = harness.verifier._verify_snapshot

    def verify_then_consume_nonce(*args: object, **kwargs: object) -> object:
        handle = verify_snapshot(*args, **kwargs)
        with harness.trust._nonce_lock:
            harness.trust._seen_nonces.add(release_nonce)
        return handle

    monkeypatch.setattr(harness.verifier, "_verify_snapshot", verify_then_consume_nonce)
    with pytest.raises(ContractV4Error, match="TRUST_REPLAY"):
        harness.verifier.verify(pack_ref, now=NOW)
    cached = harness.verifier._verified[pack_ref]
    assert not cached.verifier_issued
    assert harness.verifier._signature_principals == {}

    with harness.trust._nonce_lock:
        harness.trust._seen_nonces.remove(release_nonce)
    monkeypatch.setattr(harness.verifier, "_verify_snapshot", verify_snapshot)
    restored = harness.verifier.verify(pack_ref, now=NOW)
    assert restored is cached
    assert restored.verifier_issued


def test_trust_change_before_issuance_cannot_activate_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    verify_snapshot = harness.verifier._verify_snapshot

    def verify_then_change_trust(*args: object, **kwargs: object) -> object:
        handle = verify_snapshot(*args, **kwargs)
        harness.trust.target_environment = "production"
        return handle

    monkeypatch.setattr(harness.verifier, "_verify_snapshot", verify_then_change_trust)
    with pytest.raises(ContractV4Error, match="PACK_TRUST_STATE_CHANGED"):
        harness.verifier.verify(pack_ref, now=NOW)
    cached = harness.verifier._verified[pack_ref]
    assert not cached.verifier_issued

    harness.trust.target_environment = "test"
    monkeypatch.setattr(harness.verifier, "_verify_snapshot", verify_snapshot)
    assert harness.verifier.verify(pack_ref, now=NOW) is cached
    assert cached.verifier_issued


def test_transient_live_key_swap_cannot_change_trust_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    key_id = "w2-03-release-key"
    correct_key = harness.trust._keys[key_id]
    wrong_key = replace(correct_key, public_key=b"\xff" * 32)
    harness.trust._keys[key_id] = wrong_key
    resolve_content = harness.resolver.resolve_content
    calls = 0

    def resolve_during_live_key_aba(*args: object, **kwargs: object) -> bytes:
        nonlocal calls
        calls += 1
        harness.trust._keys[key_id] = correct_key if calls == 1 else wrong_key
        return resolve_content(*args, **kwargs)

    monkeypatch.setattr(
        harness.resolver,
        "resolve_content",
        resolve_during_live_key_aba,
    )
    with pytest.raises(ContractV4Error, match="TRUST_SIGNATURE_INVALID"):
        harness.verifier.verify(pack_ref, now=NOW)

    assert calls > 1
    assert harness.trust._keys[key_id] == wrong_key
    assert pack_ref not in harness.verifier._verified


def test_snapshot_hides_late_registration_until_exit() -> None:
    resolver = ArtifactResolverV4(max_artifact_bytes=128)
    original = b"original"
    original_ref = ContentRefV4("probe", DigestV4.from_bytes(original))
    resolver.register_bytes(
        artifact_id="original",
        content_ref=original_ref,
        artifact_kind="probe",
        media_type="application/octet-stream",
        scope="test-only",
        content=original,
    )
    late = b"late"
    late_ref = ContentRefV4("probe", DigestV4.from_bytes(late))

    with resolver._snapshot():
        resolver.register_bytes(
            artifact_id="late",
            content_ref=late_ref,
            artifact_kind="probe",
            media_type="application/octet-stream",
            scope="test-only",
            content=late,
        )
        with pytest.raises(ContractV4Error, match="ARTIFACT_NOT_FOUND"):
            resolver.resolve_content(
                late_ref,
                expected_artifact_kind="probe",
                expected_media_type="application/octet-stream",
                expected_scope="test-only",
                max_bytes=128,
            )

    assert resolver.resolve_content(
        late_ref,
        expected_artifact_kind="probe",
        expected_media_type="application/octet-stream",
        expected_scope="test-only",
        max_bytes=128,
    ) == late


def test_external_file_replacement_cannot_rebind_registered_pack_bytes(tmp_path) -> None:
    harness = _PackHarness()
    pack_ref = harness.build()
    expected = harness.resolver.resolve_content(
        pack_ref,
        expected_artifact_kind=PACK_SIGNATURE_KIND,
        expected_media_type="application/json",
        expected_scope=RULE_PACK_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    )
    external = tmp_path / "pack.json"
    external.write_bytes(expected)
    external.write_bytes(b'{"attacker":"replacement"}')

    assert harness.resolver.resolve_content(
        pack_ref,
        expected_artifact_kind=PACK_SIGNATURE_KIND,
        expected_media_type="application/json",
        expected_scope=RULE_PACK_SCOPE,
        max_bytes=harness.resolver.max_artifact_bytes,
    ) == expected
