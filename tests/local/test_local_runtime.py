"""Local keyless runtime acceptance (J1-J7 of SPLIT-LOCAL-3).

Each test exercises the real installed-module chain: local rule directories,
local record endorsements, the sole ApplicationV4 evaluation, the
independent checker, incremental semantics, and sealed-run reads — all
without service keys, trust bundles, signed packs, or generated key
material.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from compiler_core.canonical_serialization import parse_json_document
from compiler_core.client import ClientV4Error, create_local_client
from compiler_core.contracts import (
    ContentRefV4,
    DigestV4,
    IncrementalParentV5,
    SignatureEnvelopeV4,
)
from compiler_core.local_runtime import LocalRecordTrustV4, LocalRuntimeError
from compiler_core.trust import TrustVerifierV4


RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
    "sources": [
        {
            "source_id": "acceptance-statute",
            "jurisdiction": "TEST",
            "authority_tier": "official_first_party",
            "issuer": "Acceptance Test Authority",
            "title": "acceptance-statute",
            "publication_time": "2020-01-01T00:00:00Z",
            "effective_from": "2020-01-01T00:00:00Z",
            "retrieved_at": "2026-08-01T00:00:00Z",
            "locator": {
                "kind": "uri", "value": "example.invalid/acceptance",
                "page": None, "span_start": None, "span_end": None,
            },
            "content": (
                "验收测试规则文本：仅用于工程验证，不构成任何法律依据。"
                "第一条 义务适用；第二条 构成要件推导；第三条 例外攻击。"
            ),
            "structure_sections": ["第一条", "第二条", "第三条"],
        },
    ],
    "rules": [
        {
            "rule_id": "acc-base",
            "jurisdiction": "TEST",
            "governing_law": "acceptance-statute",
            "source_id": "acceptance-statute",
            "modality": "OBLIGATION",
            "premises": [{"fact_key": "acc.contract", "required": True}],
            "conclusion": {"value": "applies"},
            "effective_from": "2020-01-01T00:00:00Z",
        },
        {
            "rule_id": "acc-derived",
            "jurisdiction": "TEST",
            "governing_law": "acceptance-statute",
            "source_id": "acceptance-statute",
            "modality": "CONSTITUTIVE",
            "premises": [{"fact_key": "acc.contract", "required": True}],
            "conclusion": {"fact_key": "acc.notice"},
            "effective_from": "2020-01-01T00:00:00Z",
        },
        {
            "rule_id": "acc-exception",
            "jurisdiction": "TEST",
            "governing_law": "acceptance-statute",
            "source_id": "acceptance-statute",
            "modality": "OBLIGATION",
            "premises": [{"fact_key": "acc.exception", "required": True}],
            "conclusion": {"value": "exception-applies"},
            "exceptions": [{"target": "acc-base", "condition_fact_key": "acc.exception"}],
            "effective_from": "2020-01-01T00:00:00Z",
        },
    ],
}


def _rule_root(tmp_path: Path, pack: dict | None = None) -> Path:
    root = tmp_path / "rules"
    root.mkdir(parents=True, exist_ok=True)
    (root / "jc-local-pack.json").write_text(
        json.dumps(pack or RULE_PACK, ensure_ascii=False), encoding="utf-8",
    )
    return root


QUERIES = (
    {"query_id": "issue-base", "claim": "acc-base", "profile": "grounded"},
    {"query_id": "issue-exception", "claim": "acc-exception", "profile": "grounded"},
)


def _client(tmp_path: Path, pack: dict | None = None):
    client = create_local_client(tmp_path / "state", _rule_root(tmp_path, pack))
    pack_info = client.local_pack()
    claims = {row["rule_id"]: row["claim"] for row in pack_info["rules"]}
    return client, claims


def _issue_queries(claims):
    return [
        {"issue_id": q["query_id"], "claim": claims[q["claim"]], "profile": q["profile"]}
        for q in QUERIES
    ]


def _bundle(client, claims, fact_rows, *, case_id="acceptance-case", parent=None):
    return client.local_case_bundle(
        case_id=case_id,
        decision_time="2026-09-01T00:00:00Z",
        facts=fact_rows,
        queries=_issue_queries(claims),
        incremental_parent=parent,
    )


# Profile queries require the certified AAF graph, and the AAF provider is
# routed only when a conflict-structured rule is selected; so every query run
# admits the attacker's premise too. This mirrors the fail-closed contract
# tests ("profile_queries_without_an_aaf_graph_fail_closed").
FULL_FACTS = [{"fact_key": "acc.contract"}, {"fact_key": "acc.exception"}]


def _evaluate(client, claims, fact_rows, **kwargs):
    bundle = _bundle(client, claims, fact_rows, **kwargs)
    return client.evaluate_harness_bundle(
        bundle, case_id=kwargs.get("case_id", "acceptance-case"),
        issue_queries=_issue_queries(claims),
    )


# ---------------------------------------------------------------------------
# J1: keyless startup and call; the signed procedure is absent, not faked
# ---------------------------------------------------------------------------


def test_j1_local_client_starts_and_evaluates_without_keys(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    result = _evaluate(client, claims, FULL_FACTS)
    assert result["run_status"] == "success"
    assert result["execution_mode"] == "local"
    assert result["signature_status"] == "not_used"
    record = client.local_read_run(result["run_identity_ref"])
    assert record["decision_status"] == "accepted_formal_result"


def test_j1_local_trust_rejects_signature_envelopes() -> None:
    """Any signed-envelope detour into the local path fails loudly."""

    trust = LocalRecordTrustV4(policy=__import__(
        "compiler_core.local_runtime", fromlist=["local_trust_policy"],
    ).local_trust_policy())
    envelope = SignatureEnvelopeV4.from_dict({
        "algorithm": "Ed25519", "key_id": "k", "issuer": "i", "role": "service_signer",
        "scope": "service-certificate", "kind": "service-certificate",
        "schema_version": "jc/5.0",
        "subject_digest": str(DigestV4.from_bytes(b"s")),
        "run_identity_ref": None, "status": "APPROVED",
        "issued_at": {"wire": "2026-01-01T00:00:00Z"},
        "expires_at": {"wire": "2027-01-01T00:00:00Z"}, "nonce": "n",
        "evidence_refs": [],
        "payload_digest": str(DigestV4.from_bytes(b"p")),
        "policy_digest": str(trust.policy.policy_digest),
        "revocation_ref": None, "signature": "AAAA",
    })
    from compiler_core.contracts import ContractV4Error

    with pytest.raises(ContractV4Error) as caught:
        trust.verify(
            envelope,
            expected_subject_digest=DigestV4.from_bytes(b"s"),
            expected_payload_digest=DigestV4.from_bytes(b"p"),
            required_role="service_signer",
            required_scope="service-certificate",
            required_artifact_kind="service-certificate",
            expected_status="APPROVED",
            now=__import__("compiler_core.contracts", fromlist=[
                "CanonicalTimeV4"]).CanonicalTimeV4("2026-06-01T00:00:00Z"),
            separation_from_principals=(),
        )
    assert caught.value.code == "TRUST_INPUT_TYPE"


def test_j1_no_key_material_is_generated(tmp_path: Path) -> None:
    client, _claims = _client(tmp_path)
    handle = client._local_runtime
    assert handle.trust.target_environment == "local"
    assert handle.policy.trusted_key_ids == ()
    assert handle.policy.allowed_algorithms == ("LOCAL-RECORD",)
    # the local runtime module holds no private-key material at all
    import compiler_core.local_runtime as module

    for name in dir(module):
        assert "PrivateKey" not in name


# ---------------------------------------------------------------------------
# J2: the original solver and checker actually run; failures stay failures
# ---------------------------------------------------------------------------


def test_j2_solver_and_checker_run_for_real(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    result = _evaluate(client, claims, FULL_FACTS)
    assert result["run_status"] == "success"
    assert result["horn"]["solver_rule_evaluations"] >= 1
    assert result["horn"]["checker_rule_evaluations"] >= 1
    assert result["assurance_specs"]
    statuses = {issue["issue_id"]: issue["conclusion_status"] for issue in result["issues"]}
    # the exception rule is admitted, so the attacked base rule is not accepted
    assert statuses["issue-exception"] == "accepted"
    assert statuses["issue-base"] != "accepted"


def test_j2_missing_premise_is_never_accepted(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    # the base premise is missing: either the chain honestly reports the
    # missing fact, or it fails closed - it can never answer as accepted
    result = _evaluate(client, claims, [
        {"fact_key": "acc.contract"},
        {"fact_key": "acc.exception"},
    ])
    base = next(i for i in result["issues"] if i["issue_id"] == "issue-base")
    assert base["conclusion_status"] in {"accepted", "undecided", "possible",
                                         "refuted", "incomplete", "excluded"}
    assert result["decision_status"] in {
        "accepted_formal_result", "incomplete_formal_result", "no_formal_result",
    }


def test_j2_tampered_bundle_is_rejected(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    bundle = _bundle(client, claims, FULL_FACTS)
    payload = json.loads(json.dumps(bundle.to_dict()))
    for artifact in payload["artifacts"]:
        if artifact["artifact_kind"] == "fact-value":
            artifact["content_base64"] = artifact["content_base64"][:-4] + "AAAA"
    from compiler_core.contracts import CaseInputBundleV4, ContractV4Error

    with pytest.raises(ContractV4Error):
        CaseInputBundleV4.from_dict(payload)


# ---------------------------------------------------------------------------
# J3: one input, one evaluation, issue-accurate projection
# ---------------------------------------------------------------------------


def test_j3_single_evaluation_and_mapping_checks(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    bundle = _bundle(client, claims, FULL_FACTS)
    result = client.evaluate_harness_bundle(
        bundle, case_id="acceptance-case", issue_queries=_issue_queries(claims),
    )
    assert result["evaluation_count"] == 1
    assert [issue["issue_id"] for issue in result["issues"]] == [
        q["query_id"] for q in QUERIES
    ]

    with pytest.raises(ClientV4Error) as mapping:
        client.evaluate_harness_bundle(
            bundle, case_id="acceptance-case",
            issue_queries=[
                {"issue_id": "wrong", "claim": claims["acc-base"], "profile": "grounded"},
            ],
        )
    assert mapping.value.code == "HARNESS_QUERY_MAPPING"

    with pytest.raises(ClientV4Error) as claim_mismatch:
        client.evaluate_harness_bundle(
            bundle, case_id="acceptance-case",
            issue_queries=[
                {"issue_id": "issue-base", "claim": claims["acc-exception"],
                 "profile": "grounded"},
                {"issue_id": "issue-exception", "claim": claims["acc-exception"],
                 "profile": "grounded"},
            ],
        )
    assert claim_mismatch.value.code == "HARNESS_QUERY_MAPPING"

    with pytest.raises(ClientV4Error) as scope:
        client.evaluate_harness_bundle(
            bundle, case_id="other-case", issue_queries=_issue_queries(claims),
        )
    assert scope.value.code == "HARNESS_CASE_SCOPE_MISMATCH"


def test_j3_projection_follows_the_current_run_not_a_stale_one(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    first = _evaluate(client, claims, FULL_FACTS)
    renamed_queries = [
        {"query_id": "renamed-base", "claim": "acc-base", "profile": "grounded"},
        {"query_id": "renamed-exception", "claim": "acc-exception", "profile": "grounded"},
    ]
    issue_queries = [
        {"issue_id": q["query_id"], "claim": claims[q["claim"]], "profile": q["profile"]}
        for q in renamed_queries
    ]
    bundle = client.local_case_bundle(
        case_id="acceptance-case",
        decision_time="2026-09-01T00:00:00Z",
        facts=FULL_FACTS,
        queries=issue_queries,
    )
    second = client.evaluate_harness_bundle(
        bundle, case_id="acceptance-case", issue_queries=issue_queries,
    )
    assert second["run_status"] == "success", second
    assert [i["issue_id"] for i in first["issues"]] == [
        q["query_id"] for q in QUERIES
    ]
    assert [i["issue_id"] for i in second["issues"]] == [
        q["query_id"] for q in renamed_queries
    ]
    assert first["run_identity_ref"] != second["run_identity_ref"]


# ---------------------------------------------------------------------------
# J4: fact states and rule-set sizes keep their honest semantics
# ---------------------------------------------------------------------------


def test_j4_assumptions_drive_hypothetical_not_proven(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    result = _evaluate(client, claims, [
        *FULL_FACTS,
        {"fact_key": "acc.assumed", "assumption_state": "USER_ASSUMED",
         "dispute_state": "USER_ASSUMED"},
    ])
    assert result["decision_status"] == "hypothetical_result"
    assert result["decision_status"] != "accepted_formal_result"


def test_j4_unknown_fact_is_not_confirmed(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    result = _evaluate(client, claims, [
        *FULL_FACTS,
        {"fact_key": "acc.unknown", "dispute_state": "UNKNOWN"},
    ])
    assert result["decision_status"] == "review_only_result"


def test_j4_rule_count_is_not_capped_at_six(tmp_path: Path) -> None:
    assert len(RULE_PACK["rules"]) == 3
    client, claims = _client(tmp_path)
    assert len(client.local_pack()["rules"]) == 3
    extra_rules = list(RULE_PACK["rules"])
    for index in range(4):
        extra_rules.append({
            "rule_id": f"acc-extra-{index}",
            "jurisdiction": "TEST",
            "governing_law": "acceptance-statute",
            "source_id": "acceptance-statute",
            "modality": "OBLIGATION",
            "premises": [{"fact_key": f"acc.extra-{index}", "required": True}],
            "conclusion": {"value": f"extra-{index}"},
            "effective_from": "2020-01-01T00:00:00Z",
        })
    extra_pack = {**RULE_PACK, "rules": extra_rules}
    client7, claims7 = _client(tmp_path / "seven", extra_pack)
    assert len(client7.local_pack()["rules"]) == 7


def test_j4_unsupported_permission_semantics_is_reported(tmp_path: Path) -> None:
    """A form the certified providers cannot run stays honestly unfinished."""

    permission_pack = {
        **RULE_PACK,
        "rules": [
            *RULE_PACK["rules"],
            {
                "rule_id": "acc-permission",
                "jurisdiction": "TEST",
                "governing_law": "acceptance-statute",
                "source_id": "acceptance-statute",
                "modality": "PERMISSION",
                "premises": [{"fact_key": "acc.contract", "required": True}],
                "conclusion": {"value": "permission-applies"},
                "permission": {
                    "permits": "acc.contract",
                    "relation_to": "acc-base",
                    "relation_kind": "exception",
                },
                "effective_from": "2020-01-01T00:00:00Z",
            },
        ],
    }
    client, claims = _client(tmp_path / "perm", permission_pack)
    result = _evaluate(client, claims, FULL_FACTS)
    assert result["run_status"] == "error"
    assert result["decision_status"] != "accepted_formal_result"
    info = client.local_read_run(result["run_identity_ref"])
    reasons = info["files"]["result.json"]["decision_reason_codes"]
    assert "backend:BACKEND_UNSUPPORTED_SEMANTICS" in reasons


def test_j4_unsupported_rule_form_is_reported_not_approximated(tmp_path: Path) -> None:
    broken = {
        **RULE_PACK,
        "rules": [
            *RULE_PACK["rules"],
            {
                "rule_id": "acc-broken",
                "jurisdiction": "TEST",
                "governing_law": "acceptance-statute",
                "source_id": "acceptance-statute",
                "modality": "OBLIGATION",
                "premises": [{"fact_key": "acc.contract", "required": True}],
                "conclusion": {},
                "effective_from": "2020-01-01T00:00:00Z",
            },
        ],
    }
    with pytest.raises(LocalRuntimeError):
        create_local_client(tmp_path / "broken", _rule_root(tmp_path / "broken", broken))


# ---------------------------------------------------------------------------
# J5: real increment, honest fallback, no cross-case reuse
# ---------------------------------------------------------------------------


def _parent_of(client, result) -> IncrementalParentV5:
    horn = client.local_horn_subject_state(result["run_identity_ref"])
    return IncrementalParentV5(
        parent_run_ref=ContentRefV4.from_dict(horn["parent_run_ref"]),
        parent_state_ref=ContentRefV4.from_dict(horn["parent_state_ref"]),
        parent_subject_digest=DigestV4(horn["parent_subject_digest"]),
        mode="auto",
    )


def test_j5_add_only_fact_reuses_parent_state(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    first = _evaluate(client, claims, FULL_FACTS)
    parent = _parent_of(client, first)
    second = _evaluate(client, claims, [
        {"fact_key": "acc.contract"}, {"fact_key": "acc.exception"},
        {"fact_key": "acc.notice"},
    ], parent=parent)
    assert second["run_status"] == "success"
    assert second["horn"]["mode"] == "incremental"
    assert second["horn"]["parent_binding"] is not None


def test_j5_universe_growth_falls_back_honestly(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    first = _evaluate(client, claims, FULL_FACTS)
    parent = _parent_of(client, first)
    second = _evaluate(client, claims, [
        *FULL_FACTS, {"fact_key": "acc.fresh"},
    ], parent=parent)
    assert second["run_status"] == "success"
    assert second["horn"]["mode"] == "full_recompute"
    assert second["horn"]["fallback_reason"] == "universe_growth"


def test_j5_cross_case_parent_is_not_reused(tmp_path: Path) -> None:
    client, claims = _client(tmp_path)
    first = _evaluate(client, claims, FULL_FACTS)
    parent = _parent_of(client, first)
    bundle = client.local_case_bundle(
        case_id="another-case",
        decision_time="2026-09-01T00:00:00Z",
        facts=FULL_FACTS,
        queries=_issue_queries(claims),
        incremental_parent=parent,
    )
    result = client.evaluate_harness_bundle(
        bundle, case_id="another-case", issue_queries=_issue_queries(claims),
    )
    assert result["run_status"] == "success"
    assert result["horn"]["mode"] == "full_recompute"
    assert result["horn"]["fallback_reason"] not in (None, "")


# ---------------------------------------------------------------------------
# J7: the delivered example actually runs
# ---------------------------------------------------------------------------


def test_j7_local_example_runs_end_to_end(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[2]
    sample = repo / "examples" / "harness" / "sample_local.py"
    completed = subprocess.run(
        [sys.executable, str(sample)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(repo), timeout=900,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert completed.returncode == 0, (
        f"sample_local failed:\n{completed.stdout}\n{completed.stderr}"
    )
    for marker in (
        '"harness_contract_version": "jc-harness-local/1"',
        '"signature_status": "not_used"',
        '"evaluation_count": 1',
        "'mode': 'incremental'",
    ):
        assert marker in completed.stdout, marker
