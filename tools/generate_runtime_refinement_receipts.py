#!/usr/bin/env python3
"""Execute JC conformance fixtures and emit LMM-bound runtime receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler_core.argumentation import (  # noqa: E402
    ArgumentGraphV4,
    ArgumentationV4Error,
    argument_ref_v4,
    evaluate_argument_graph,
)
from compiler_core.backends import HORN_PROVIDER_ID  # noqa: E402
from compiler_core.canonical_serialization import (  # noqa: E402
    DigestV4,
    canonical_bytes,
)
from compiler_core.contracts import (  # noqa: E402
    ArgumentV4,
    AttackV4,
    ContentRefV4,
    ContractV4Error,
)

SCHEMA = "spec-runtime-refinement-v2"
FIXTURE_SCHEMA = "jc/runtime-refinement-fixture/1.0"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ref(kind: str, label: str) -> ContentRefV4:
    return ContentRefV4(kind, DigestV4.from_bytes(label.encode("utf-8")))


def _argument(row: Mapping[str, Any]) -> ArgumentV4:
    argument_id = row["argument_id"]
    return ArgumentV4(
        argument_id=argument_id,
        premise_refs=(_ref("fact", f"fact::{argument_id}"),),
        rule_ref=_ref("rule-v4", f"rule::{argument_id}"),
        claim_ref=_ref("claim-v4", row["claim_id"]),
        derivation_refs=(_ref("derivation", f"derivation::{argument_id}"),),
    )


def _contract_case(
    case: Mapping[str, Any], rules: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    facts = case["facts"]
    active = {
        row["argument_id"]: _argument(row)
        for row in rules["arguments"]
        if all(facts.get(name) is True for name in row["requires"])
    }
    focus_id = rules["focus_argument"]
    if focus_id not in active:
        raise ValueError("contract fixture did not activate its focus argument")

    attacks: list[AttackV4] = []
    for row in rules["attacks"]:
        if facts.get(row["when"]) is not True:
            continue
        target_id = case.get("malformed_attack_target", row["target"])
        target_ref = (
            argument_ref_v4(active[target_id])
            if target_id in active
            else _ref("argument-v4", f"missing::{target_id}")
        )
        attacks.append(
            AttackV4(
                attack_id=row["attack_id"],
                attacker_ref=argument_ref_v4(active[row["attacker"]]),
                target_ref=target_ref,
                attack_type="exception",
                target_aspect="claim",
            )
        )

    try:
        evaluation = evaluate_argument_graph(
            ArgumentGraphV4(tuple(active.values()), attacks=tuple(attacks))
        )
    except ArgumentationV4Error as exc:
        if "malformed_attack_target" not in case:
            raise
        return "TAINTED", {"error_code": exc.code}

    focus_ref = argument_ref_v4(active[focus_id])
    label = next(item.label for item in evaluation.labels if item.argument_ref == focus_ref)
    status = {"IN": "PROVED", "OUT": "REFUTED", "UNDEC": "UNDECIDED"}[label]
    return status, evaluation.to_dict()


def _fact_case(
    case: Mapping[str, Any], rules: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    from tests.contract.test_fact_admission import _Harness, _ref as fact_ref

    harness = _Harness()
    options: dict[str, Any] = {"dispute_state": case["dispute_state"]}
    if case["revoked"] is True:
        options["revocation_ref"] = fact_ref("revocation", "revoked-attestation")
    stage = harness.stage(**options)
    try:
        receipt_ref = harness.admit(stage)
    except ContractV4Error as exc:
        if exc.code not in rules["nonformal_error_codes"]:
            raise
        return "UNDECIDED", {"error_code": exc.code}

    receipt = harness.receipt(receipt_ref)
    if receipt.status != "ADMITTED":
        raise ValueError(f"unexpected fact admission status: {receipt.status}")
    return "PROVED", receipt.to_dict()


def _backend_case(
    case: Mapping[str, Any], rules: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    from tests.security.test_backend_attacks import _backend, _minimal_horn_problem

    if rules["provider"] != HORN_PROVIDER_ID:
        raise ValueError("backend fixture provider does not bind the JC Horn provider")
    problem = (
        _minimal_horn_problem()
        if case["input"] == "minimal-horn-problem"
        else canonical_bytes({"schema_version": "invalid-provider-problem"})
    )
    _, _, router, _, _, _ = _backend()
    run = router._invoke_provider(
        HORN_PROVIDER_ID,
        problem,
        DigestV4.from_bytes(problem),
        deadline_ms=case["deadline_ms"],
        cancel_check=None,
    )
    try:
        status = rules["status_projection"][run.status]
    except KeyError as exc:
        raise ValueError(f"unexpected backend status: {run.status}") from exc
    return status, {
        "provider": run.provider_id,
        "provider_status": run.status,
        "exit_status": run.exit_status,
        "input_digest": str(run.input_digest),
    }


RUNNERS = {
    "contract_breach": _contract_case,
    "fact_admission": _fact_case,
    "unknown_timeout": _backend_case,
}


def load_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        type(value) is not dict
        or value.get("schema_version") != FIXTURE_SCHEMA
        or value.get("group") != path.name.removesuffix(".fixture.json")
        or set(value) != {"schema_version", "group", "source_snapshot", "rule_pack"}
    ):
        raise ValueError(f"invalid runtime refinement fixture: {path}")
    return value


def fixture_bindings(fixture: Mapping[str, Any]) -> tuple[list[str], str]:
    return (
        [canonical_digest(fixture["source_snapshot"])],
        canonical_digest(fixture["rule_pack"]),
    )


def build_receipt(
    expected: Mapping[str, Any],
    fixture: Mapping[str, Any],
    *,
    runtime_commit: str,
    runtime_build_id: str,
) -> dict[str, Any]:
    if expected.get("schema_version") != SCHEMA or expected.get("role") != "expected":
        raise ValueError("expected fixture has an unsupported schema or role")
    expected_body = {
        name: expected[name]
        for name in (
            "lmm_commit",
            "cases",
            "source_snapshot_digests",
            "rule_pack_digest",
            "semantics",
        )
    }
    if canonical_digest(expected_body) != expected.get("fixture_digest"):
        raise ValueError("expected fixture digest does not match its content")
    source_digests, rule_pack_digest = fixture_bindings(fixture)
    if expected["source_snapshot_digests"] != source_digests:
        raise ValueError("expected fixture does not bind the JC source fixture")
    if expected["rule_pack_digest"] != rule_pack_digest:
        raise ValueError("expected fixture does not bind the JC rule fixture")

    group = fixture["group"]
    source_cases = fixture["source_snapshot"]["cases"]
    expected_case_ids = [row["case_id"] for row in expected["cases"]]
    source_case_ids = [row["case_id"] for row in source_cases]
    if expected_case_ids != source_case_ids:
        raise ValueError("expected and executable fixture case identities differ")

    runner = RUNNERS[group]
    executed: dict[str, dict[str, Any]] = {}
    for case in source_cases:
        actual_status, evidence = runner(case, fixture["rule_pack"])
        executed[case["case_id"]] = {
            "case_id": case["case_id"],
            "actual_status": actual_status,
            "runtime_evidence_digest": canonical_digest(evidence),
        }
    body = {
        "schema_version": SCHEMA,
        "role": "actual",
        "producer": "juris-calculus",
        "lmm_commit": expected["lmm_commit"],
        "runtime_commit": runtime_commit,
        "runtime_build_id": runtime_build_id,
        "fixture_digest": expected["fixture_digest"],
        "runtime_fixture_digest": canonical_digest(fixture),
        "source_snapshot_digests": source_digests,
        "rule_pack_digest": rule_pack_digest,
        "cases": [executed[case_id] for case_id in expected_case_ids],
        "execution_status": "SUCCESS",
    }
    return {**body, "receipt_digest": canonical_digest(body)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-dir", type=Path, required=True)
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=ROOT / "tests" / "fixtures" / "runtime_refinement",
    )
    parser.add_argument("--runtime-commit", required=True)
    parser.add_argument("--runtime-build-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    if SHA_PATTERN.fullmatch(args.runtime_commit) is None:
        raise ValueError("runtime commit must be a lowercase 40-character Git SHA")
    if not args.runtime_build_id:
        raise ValueError("runtime build id must be non-empty")

    expected_paths = sorted(args.expected_dir.glob("*.expected.json"))
    if not expected_paths:
        raise ValueError("no expected refinement fixtures found")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for expected_path in expected_paths:
        group = expected_path.name.removesuffix(".expected.json")
        fixture = load_fixture(args.fixture_dir / f"{group}.fixture.json")
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        receipt = build_receipt(
            expected,
            fixture,
            runtime_commit=args.runtime_commit,
            runtime_build_id=args.runtime_build_id,
        )
        output = args.output_dir / f"{group}.actual.json"
        output.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
