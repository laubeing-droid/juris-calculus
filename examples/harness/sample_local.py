"""Sample 4/4: the local keyless Harness -> JC -> Harness call (jc-harness-local/1).

Run:  python examples/harness/sample_local.py

This sample is self-contained: it needs no service key, trust bundle,
signed pack, activation step, or test-tree helper. It writes its
engineering-test rule pack and run records under a temporary directory and
prints the full ``evaluate_harness_bundle`` payload plus the incremental
follow-up run. The rules below are marked engineering test material; they
demonstrate the interface, not a Chinese-law capability.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from compiler_core.client import create_local_client

RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
    "sources": [
        {
            "source_id": "engineering-test-statute",
            "jurisdiction": "TEST",
            "authority_tier": "official_first_party",
            "issuer": "Engineering Test Authority",
            "title": "engineering-test-statute",
            "publication_time": "2020-01-01T00:00:00Z",
            "effective_from": "2020-01-01T00:00:00Z",
            "retrieved_at": "2026-08-01T00:00:00Z",
            "locator": {
                "kind": "uri", "value": "example.invalid/engineering-test",
                "page": None, "span_start": None, "span_end": None,
            },
            "content": (
                "工程测试规则文本：仅用于接口验证，不构成任何法律依据。"
                "第一条 设 X 前提成立则义务适用。"
                "第二条 设 例外前提成立则第一条被例外攻击。"
            ),
            "structure_sections": ["第一条", "第二条"],
        },
    ],
    "rules": [
        {
            "rule_id": "sample-base",
            "jurisdiction": "TEST",
            "governing_law": "engineering-test-statute",
            "source_id": "engineering-test-statute",
            "modality": "OBLIGATION",
            "premises": [{"fact_key": "sample.contract-signed", "required": True}],
            "conclusion": {"value": "applies"},
            "effective_from": "2020-01-01T00:00:00Z",
        },
        {
            "rule_id": "sample-derived",
            "jurisdiction": "TEST",
            "governing_law": "engineering-test-statute",
            "source_id": "engineering-test-statute",
            "modality": "CONSTITUTIVE",
            "premises": [{"fact_key": "sample.contract-signed", "required": True}],
            "conclusion": {"fact_key": "sample.notice-effective"},
            "effective_from": "2020-01-01T00:00:00Z",
        },
        {
            "rule_id": "sample-exception",
            "jurisdiction": "TEST",
            "governing_law": "engineering-test-statute",
            "source_id": "engineering-test-statute",
            "modality": "OBLIGATION",
            "premises": [{"fact_key": "sample.statute-exception", "required": True}],
            "conclusion": {"value": "exception-applies"},
            "exceptions": [{
                "target": "sample-base",
                "condition_fact_key": "sample.statute-exception",
            }],
            "effective_from": "2020-01-01T00:00:00Z",
        },
    ],
}

QUERIES = [
    {"issue_id": "issue-base", "claim": "sample-base", "profile": "grounded"},
    {"issue_id": "issue-exception", "claim": "sample-exception", "profile": "grounded"},
]


def main() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="jc-local-sample-"))
    rules_root = workspace / "rules"
    state_root = workspace / "state"
    rules_root.mkdir()
    (rules_root / "jc-local-pack.json").write_text(
        json.dumps(RULE_PACK, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    # 1. one factory call: no key material anywhere.
    client = create_local_client(state_root, rules_root)
    pack = client.local_pack()
    claims = {row["rule_id"]: row["claim"] for row in pack["rules"]}
    issue_queries = [
        {"issue_id": q["issue_id"], "claim": claims[q["claim"]], "profile": q["profile"]}
        for q in QUERIES
    ]

    # 2. build the structured case bundle through the public serialization help.
    bundle = client.local_case_bundle(
        case_id="sample-case",
        decision_time="2026-09-01T00:00:00Z",
        facts=[
            {"fact_key": "sample.contract-signed"},
            {"fact_key": "sample.statute-exception"},
        ],
        queries=issue_queries,
    )

    # 3. the one closed local call: input handling, one evaluation, projection.
    result = client.evaluate_harness_bundle(
        bundle, case_id="sample-case", issue_queries=issue_queries,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert result["harness_contract_version"] == "jc-harness-local/1"
    assert result["execution_mode"] == "local"
    assert result["signature_status"] == "not_used"
    assert result["evaluation_count"] == 1
    assert result["run_status"] == "success"
    assert result["decision_status"] == "accepted_formal_result"

    # 4. same case, add one in-universe fact: the real incremental path.
    horn = client.local_horn_subject_state(result["run_identity_ref"])
    from compiler_core.contracts import ContentRefV4, DigestV4, IncrementalParentV5

    parent = IncrementalParentV5(
        parent_run_ref=ContentRefV4.from_dict(horn["parent_run_ref"]),
        parent_state_ref=ContentRefV4.from_dict(horn["parent_state_ref"]),
        parent_subject_digest=DigestV4(horn["parent_subject_digest"]),
        mode="auto",
    )
    bundle2 = client.local_case_bundle(
        case_id="sample-case",
        decision_time="2026-09-01T00:00:00Z",
        facts=[
            {"fact_key": "sample.contract-signed"},
            {"fact_key": "sample.statute-exception"},
            {"fact_key": "sample.notice-effective"},
        ],
        queries=issue_queries,
        incremental_parent=parent,
    )
    result2 = client.evaluate_harness_bundle(
        bundle2, case_id="sample-case", issue_queries=issue_queries,
    )
    assert result2["horn"]["mode"] in {"incremental", "full_recompute"}
    assert result2["horn"]["fallback_reason"] in {None, "universe_growth"}
    assert result2["run_status"] == "success"

    # 5. read both sealed runs back through public methods, no capability key.
    for run_ref in (result["run_identity_ref"], result2["run_identity_ref"]):
        record = client.local_read_run(run_ref)
        assert record["signature_status"] == "not_used"
        assert record["decision_status"] == "accepted_formal_result"

    print("---- local summary ----")
    print("issues:", [(i["issue_id"], i["conclusion_status"]) for i in result["issues"]])
    print("incremental:", result2["horn"])
    print("state root:", state_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
