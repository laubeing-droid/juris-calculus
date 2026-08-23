"""Independent W3-05 mutations for domain binding and provider invocation."""

from __future__ import annotations

import pytest

from compiler_core.canonical_serialization import parse_json_document
from compiler_core.contracts import ContentRefV4, ResourceLimitsV4
from tests.contract.test_backend_router import _system
from tests.contract.test_independent_checker import _checker
from tests.integration.test_trust_chain import _ChainHarness


def _independent_domain_projection(
    harness: _ChainHarness,
    config_refs: tuple[ContentRefV4, ...],
) -> tuple[tuple[str, str, tuple[ContentRefV4, ...]], ...]:
    """Read signed config bytes directly; never call the pack verifier projection."""

    rows = []
    for reference in config_refs:
        document = parse_json_document(harness.resolver.resolve_content(
            reference,
            expected_artifact_kind="domain-config",
            expected_media_type="application/json",
            expected_scope="rule-pack",
            max_bytes=harness.resolver.max_artifact_bytes,
        ))
        assert type(document) is dict
        rows.append((
            document["domain_id"],
            document["namespace"],
            tuple(ContentRefV4.from_dict(item) for item in document["rule_refs"]),
        ))
    return tuple(rows)


def test_independent_oracle_kills_namespace_domain_loss() -> None:
    harness = _ChainHarness()
    verified = harness.verify_pack()
    expected = _independent_domain_projection(harness, verified.manifest.config_refs)

    assert verified.domain_bindings == expected
    assert all(domain_id and namespace and rule_refs for domain_id, namespace, rule_refs in expected)


def test_independent_checker_kills_provider_fake_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness, compilations, fact_receipt_ref, _, router = _system("synthetic-positive")
    invoked: list[str] = []
    invoke_provider = router._invoke_provider

    def observed_invoke(provider_id: str, *args: object, **kwargs: object):
        invoked.append(provider_id)
        return invoke_provider(provider_id, *args, **kwargs)

    monkeypatch.setattr(router, "_invoke_provider", observed_invoke)
    executions = router.execute(
        compilations,
        run_identity_ref=harness.run_identity_ref,
        fact_admission_receipt_refs=(fact_receipt_ref,),
        limits=ResourceLimitsV4(),
        now=harness.now,
    )
    assert invoked == [executions[0].invocation.provider_id]
    assert _checker(harness).check(
        run_identity_ref=harness.run_identity_ref,
        solver_receipt_ref=executions[0].receipt_ref,
        now=harness.now,
    ).receipt.status == "PASS"

    with pytest.raises(TypeError):
        router.execute(
            compilations,
            run_identity_ref=harness.run_identity_ref,
            fact_admission_receipt_refs=(fact_receipt_ref,),
            limits=ResourceLimitsV4(),
            now=harness.now,
            receipt=executions[0].receipt,
        )
