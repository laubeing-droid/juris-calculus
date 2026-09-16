#!/usr/bin/env python3
"""Produce C06 run witnesses and refinement receipts from JC public entries.

For the pinned legal-math-modeling full-release subject this script drives
the JC public entries (``JCClient`` facade, ``jc`` CLI, MCP ``jc_evaluate``)
over probe cases whose expected statuses were materialized by the LMM
``materialize_runtime_refinement_expected`` script, seals one run witness
per case and entry, asserts cross-entry semantic consistency, and emits
one ``spec-runtime-refinement-v2`` receipt per refinement group. The
receipts are what the LMM independent checker verifies in its own process.

Probe routes:
- the PIPL local-production route (engineering test pack signed with the
  repository's declared test-only identity) covers the decisive, disputed,
  missing-fact, assumed-fact and malformed-input statuses through all
  three entries;
- the keyless local harness route covers the refuted (force-majeure) and
  the bounded-undecided statuses; the MCP surface of the keyless runtime
  is fail-closed (``RUNTIME_NOT_CONFIGURED``) by design, which is recorded
  as a capability boundary, never as a semantic vote.

Status mapping (compiler_core.math_export.witness): only accepted results
map to PROVED, defeated claims map to REFUTED, non-decisive states map to
UNDECIDED, and every fail-closed state — including rejected input — maps
to TAINTED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess as sp
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler_core.canonical_serialization import canonical_bytes  # noqa: E402
from compiler_core.cli import EXIT_INPUT_ERROR, main as cli_main  # noqa: E402
from compiler_core.client import create_local_client, runtime_client  # noqa: E402
from compiler_core.contracts import (  # noqa: E402
    CaseInputBundleV4,
    ContractV4Error,
    EvaluationEnvelopeV4,
)
from compiler_core.math_export import (  # noqa: E402
    SUBJECT_COMMIT,
    assert_cross_entry_consistency,
    build_run_witness,
    contract_fingerprint,
    validate_export_contract,
    validate_math_completion,
    validate_witness,
)
from compiler_core.mcp import MCPServerV4  # noqa: E402
from compiler_core.version import __version__  # noqa: E402

SCHEMA = "spec-runtime-refinement-v2"
FIXTURE_SCHEMA = "jc/runtime-refinement-fixture/1.0"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")

# envelope claim statuses normalized into the harness issue vocabulary
CLAIM_STATUS_MAP = {"accepted": "accepted", "rejected": "refuted"}


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _git(args: list[str]) -> str:
    completed = sp.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True,
        shell=False,
    )
    return completed.stdout.strip()


def resolve_runtime_identity(requested_commit: str | None) -> dict[str, Any]:
    """JC-03 identity honesty: receipts cite the producer that ran.

    A requested ``--runtime-commit`` that does not equal the checked-out
    HEAD is a typed refusal: the receipts must never carry a borrowed
    SHA. The recorded identity always includes the tree and whether the
    working tree was dirty, because receipts produced by a dirty tree
    are not receipts of the commit alone.
    """

    head = _git(["rev-parse", "HEAD"])
    if requested_commit is None:
        commit = head
    else:
        if SHA_PATTERN.fullmatch(requested_commit) is None:
            raise SystemExit(
                "RUNTIME_COMMIT_INVALID: runtime commit must be a lowercase "
                "40-character Git SHA",
            )
        if requested_commit != head:
            raise SystemExit(
                f"RUNTIME_COMMIT_MISMATCH: --runtime-commit {requested_commit} "
                f"does not match the checked-out HEAD {head}; receipts must "
                "cite the producer that actually ran",
            )
        commit = requested_commit
    tree = _git(["rev-parse", "HEAD^{tree}"])
    status = sp.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True,
        capture_output=True, text=True, shell=False,
    ).stdout
    dirty_entries = sorted(
        line for line in status.splitlines() if line.strip()
    )
    return {
        "commit": commit,
        "tree": tree,
        "worktree_dirty": bool(dirty_entries),
        "dirty_entries": dirty_entries,
    }


LOCAL_RULE_PACK = {
    "schema_version": "jc/local-pack/1.0",
    "pack_version": "1.0.0",
    "sources": [{
        "source_id": "statute",
        "jurisdiction": "TEST",
        "authority_tier": "official_first_party",
        "issuer": "Engineering Test Authority",
        "title": "statute",
        "publication_time": "2020-01-01T00:00:00Z",
        "effective_from": "2020-01-01T00:00:00Z",
        "retrieved_at": "2026-08-01T00:00:00Z",
        "locator": {"kind": "uri", "value": "example.invalid/c06",
                    "page": None, "span_start": None, "span_end": None},
        "content": "工程测试文本，仅验证接口，不构成法律依据。",
        "structure_sections": ["第一条"],
    }],
    "rules": [
        {
            "rule_id": "base",
            "jurisdiction": "TEST",
            "governing_law": "statute",
            "source_id": "statute",
            "modality": "OBLIGATION",
            "premises": [{"fact_key": "f.contract", "required": True}],
            "conclusion": {"value": "applies"},
            "effective_from": "2020-01-01T00:00:00Z",
        },
        {
            "rule_id": "exception",
            "jurisdiction": "TEST",
            "governing_law": "statute",
            "source_id": "statute",
            "modality": "OBLIGATION",
            "premises": [{"fact_key": "f.ex", "required": True}],
            "conclusion": {"value": "exception-applies"},
            "exceptions": [{"target": "base", "condition_fact_key": "f.ex"}],
            "effective_from": "2020-01-01T00:00:00Z",
        },
    ],
}
LOCAL_FACTS = [{"fact_key": "f.contract"}, {"fact_key": "f.ex"}]
LOCAL_RULES_DIRNAME = "local-rules"


def _production_bundle(article: int, material: Any, **options: Any) -> CaseInputBundleV4:
    from tests.formal_e2e.test_local_production_chain import production_bundle

    return production_bundle(article, material=material, **options)


def _build_production_material(workspace: Path) -> Any:
    from tests.conftest import ProductionMaterial
    from tools.build_cn_official_pack import build_document
    from tools.build_local_production_pack import (
        LocalProductionPackBuilder,
        ensure_identity,
    )
    from tools.local_production import initialize_service_key

    root = workspace / "production-material"
    identity_path = root / "identity" / "root.json"
    identity = ensure_identity(identity_path)
    source_doc = json.loads(
        (ROOT / "tests/fixtures/cn_official/pipl-source.json").read_text(encoding="utf-8")
    )
    candidate = build_document(source_doc)
    pack, trust = LocalProductionPackBuilder(candidate, identity).build()
    pack_path = root / "packs" / "cn-official-local-c06.json"
    trust_path = root / "trust" / "cn-official-local.json"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    trust_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_bytes(canonical_bytes(pack))
    trust_path.write_bytes(canonical_bytes(trust))
    service_key_path = root / "identity" / "service-runtime.json"
    initialize_service_key(identity_path, service_key_path, trust_path)
    return ProductionMaterial(
        root=root,
        identity_path=identity_path,
        pack_path=pack_path,
        trust_path=trust_path,
        service_key_path=service_key_path,
    )


def _production_runtime_config(workspace: Path, material: Any) -> Path:
    from tests.formal_e2e.test_local_production_chain import runtime_config

    workspace.mkdir(parents=True, exist_ok=True)
    return runtime_config(
        workspace / "runtime.json", workspace / "state", material,
    )


# ---------------------------------------------------------------------------
# Probe table
# ---------------------------------------------------------------------------


def define_probes() -> list[dict[str, Any]]:
    probes = [
        {
            "group": "contract_breach", "case_id": "contract::plain",
            "expected_status": "PROVED", "route": "production",
            "article": 15, "options": {},
            "semantics": "production chain: consent-based processing "
                         "obligation accepted with a formal certificate; "
                         "decided at envelope level",
        },
        {
            "group": "contract_breach", "case_id": "contract::force-majeure",
            "expected_status": "REFUTED", "route": "local",
            "focus_issue": "base",
            "semantics": "keyless local harness: admitted exception rule "
                         "with an admitted claim refutation defeats the "
                         "base obligation; decided at issue level",
        },
        {
            "group": "contract_breach",
            "case_id": "contract::malformed-certificate",
            "expected_status": "TAINTED", "route": "production",
            "article": 15, "options": {}, "tamper": True,
            "semantics": "tampered fact-value bytes: every public entry "
                         "rejects the bundle at intake and never answers "
                         "decisively",
        },
        {
            "group": "fact_admission", "case_id": "admission::three-gates-pass",
            "expected_status": "PROVED", "route": "production",
            "article": 13, "options": {},
            "semantics": "production chain: three-gate admitted fact "
                         "reaches a formal result",
        },
        {
            "group": "fact_admission", "case_id": "admission::disputed-fact",
            "expected_status": "UNDECIDED", "route": "production",
            "article": 15, "options": {"dispute_state": "DISPUTED"},
            "semantics": "production chain: disputed fact stays "
                         "review-only, never decisive",
        },
        {
            "group": "fact_admission",
            "case_id": "admission::revoked-attestation",
            "expected_status": "UNDECIDED", "route": "production",
            "article": 15, "options": {"fact_key": "pipl.unrelated.fact"},
            "semantics": "production chain: without an admitted fact the "
                         "run reports the missing requirement and stays "
                         "undecided",
        },
        {
            "group": "unknown_timeout", "case_id": "backend::unknown-outcome",
            "expected_status": "UNDECIDED", "route": "production",
            "article": 15,
            "options": {"assumption_state": "USER_ASSUMED"},
            "semantics": "production chain: user-assumed fact yields a "
                         "hypothetical, non-decisive result",
        },
        {
            "group": "unknown_timeout", "case_id": "backend::timeout-outcome",
            "expected_status": "UNDECIDED", "route": "local-undecided",
            "semantics": "bounded local evaluation without decisive "
                         "support reports unknown and never guesses; "
                         "decided at envelope level",
        },
    ]
    for probe in probes:
        probe["probe_digest"] = canonical_digest(
            {k: v for k, v in probe.items() if k != "probe_digest"}
        )
    return probes


# ---------------------------------------------------------------------------
# Entry drivers
# ---------------------------------------------------------------------------


def _cli_rejection_code(detail: str) -> str:
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        return "INPUT_REJECTED"
    error = payload.get("error", payload)
    return str(error.get("code", "INPUT_REJECTED"))


def _tamper_bundle(bundle: CaseInputBundleV4) -> dict[str, Any]:
    payload = json.loads(json.dumps(bundle.to_dict()))
    for artifact in payload["artifacts"]:
        if artifact["artifact_kind"] == "fact-value":
            content = artifact["content_base64"]
            artifact["content_base64"] = content[:-4] + "AAAA"
            break
    return payload


def _run_mcp_probe(bundle: CaseInputBundleV4, tampered: bool) -> tuple[str, Any]:
    arguments = {
        "case_bundle": _tamper_bundle(bundle) if tampered else bundle.to_dict(),
    }
    out, is_error = MCPServerV4(runtime_client()).call_tool("jc_evaluate", arguments)
    if is_error:
        error = out.get("error")
        code = ""
        if isinstance(error, dict):
            code = str(error.get("code", ""))
        if not code and out.get("result") is None:
            code = "MCP_TOOL_ERROR"
        return "mcp", ("rejected", code or "MCP_TOOL_ERROR")
    result = out["result"]
    return "mcp", (str(result["decision_status"]), result)


# ---------------------------------------------------------------------------
# Witness assembly
# ---------------------------------------------------------------------------


def _witness(
    *, entry: str, probe: Mapping[str, Any], subject: Mapping[str, Any],
    engine_build_digest: str, decision: str | None,
    issue_statuses: Mapping[str, str], intake_error_code: str | None,
    run_identity_digest: str, result_digest: str, audit_manifest_digest: str,
) -> dict[str, Any]:
    return build_run_witness(
        entry=entry,
        case_id=probe["case_id"],
        probe_semantics=probe["semantics"],
        lmm_subject=subject,
        engine_version=__version__,
        engine_build_digest=engine_build_digest,
        run_identity_digest=run_identity_digest,
        input_digest=str(probe["probe_digest"]),
        result_digest=result_digest,
        audit_manifest_digest=audit_manifest_digest,
        decision_status=decision if decision is not None else "intake_rejected",
        issue_statuses=issue_statuses,
        intake_error_code=intake_error_code,
        focus_issue=probe.get("focus_issue"),
    )


EMPTY = f"sha256:{'0' * 64}"


def _witness_from_envelope(
    entry: str, probe: Mapping[str, Any], subject: Mapping[str, Any],
    engine_build_digest: str, decision: str, envelope: EvaluationEnvelopeV4,
) -> dict[str, Any]:
    return _witness(
        entry=entry, probe=probe, subject=subject,
        engine_build_digest=engine_build_digest, decision=decision,
        issue_statuses={},
        intake_error_code=None,
        run_identity_digest=str(envelope.run_identity.request_ref.digest),
        result_digest=str(envelope.result.result_digest),
        audit_manifest_digest=str(envelope.audit_manifest_ref.digest),
    )


def _witness_from_result(
    entry: str, probe: Mapping[str, Any], subject: Mapping[str, Any],
    engine_build_digest: str, decision: str, result: Mapping[str, Any],
) -> dict[str, Any]:
    run_ref = result.get("run_identity_ref") or {}
    manifest = result.get("audit_manifest_ref") or {}
    return _witness(
        entry=entry, probe=probe, subject=subject,
        engine_build_digest=engine_build_digest, decision=decision,
        issue_statuses={}, intake_error_code=None,
        run_identity_digest=str(run_ref.get("digest", EMPTY)),
        result_digest=str(result.get("result_digest", EMPTY)),
        audit_manifest_digest=str(manifest.get("digest", EMPTY)),
    )


# ---------------------------------------------------------------------------
# Route executors
# ---------------------------------------------------------------------------


def execute_production_probe(
    probe: Mapping[str, Any], material: Any, configs: Mapping[str, Path],
    subject: Mapping[str, Any], engine_build_digest: str, workspace: Path,
) -> list[dict[str, Any]]:
    os.environ["JC_PRODUCTION_CONFIG"] = str(configs["jc_client"])
    os.environ["JC_RUNTIME_FACTORY"] = "compiler_core.production_runtime"
    bundle = _production_bundle(probe["article"], material, **probe["options"])
    witnesses = []
    if probe.get("tamper"):
        tampered = _tamper_bundle(bundle)
        try:
            CaseInputBundleV4.from_dict(tampered)
            raise SystemExit("tampered bundle was not rejected at contract intake")
        except ContractV4Error as exc:
            witnesses.append(_witness(
                entry="jc_client", probe=probe, subject=subject,
                engine_build_digest=engine_build_digest, decision=None,
                issue_statuses={}, intake_error_code=exc.code,
                run_identity_digest=EMPTY, result_digest=EMPTY,
                audit_manifest_digest=EMPTY,
            ))
        path = workspace / "cli-input-tampered.json"
        path.write_text(
            json.dumps(tampered, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        os.environ["JC_PRODUCTION_CONFIG"] = str(configs["cli"])
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_main(["evaluate", "--input", str(path), "--json"])
        if code != EXIT_INPUT_ERROR:
            raise SystemExit("tampered bundle was not rejected by the CLI entry")
        witnesses.append(_witness(
            entry="cli", probe=probe, subject=subject,
            engine_build_digest=engine_build_digest, decision=None,
            issue_statuses={},
            intake_error_code=_cli_rejection_code(err.getvalue() or out.getvalue()),
            run_identity_digest=EMPTY, result_digest=EMPTY,
            audit_manifest_digest=EMPTY,
        ))
        os.environ["JC_PRODUCTION_CONFIG"] = str(configs["mcp"])
        entry, (kind, payload) = _run_mcp_probe(bundle, tampered=True)
        if kind == "rejected":
            witnesses.append(_witness(
                entry=entry, probe=probe, subject=subject,
                engine_build_digest=engine_build_digest, decision=None,
                issue_statuses={}, intake_error_code=payload,
                run_identity_digest=EMPTY, result_digest=EMPTY,
                audit_manifest_digest=EMPTY,
            ))
        else:
            raise SystemExit("tampered bundle was not rejected by the MCP entry")
        return witnesses
    envelope = runtime_client().evaluate(bundle)
    witnesses.append(_witness_from_envelope(
        "jc_client", probe, subject, engine_build_digest,
        envelope.result.decision_status.value, envelope,
    ))
    path = workspace / "cli-input.json"
    path.write_text(
        json.dumps(bundle.to_dict(), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    os.environ["JC_PRODUCTION_CONFIG"] = str(configs["cli"])
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        cli_code = cli_main(["evaluate", "--input", str(path), "--json"])
    if cli_code == EXIT_INPUT_ERROR:
        witnesses.append(_witness(
            entry="cli", probe=probe, subject=subject,
            engine_build_digest=engine_build_digest, decision=None,
            issue_statuses={},
            intake_error_code=_cli_rejection_code(err.getvalue() or out.getvalue()),
            run_identity_digest=EMPTY, result_digest=EMPTY,
            audit_manifest_digest=EMPTY,
        ))
    else:
        payload = json.loads(out.getvalue())
        witnesses.append(_witness_from_result(
            "cli", probe, subject, engine_build_digest,
            str(payload["result"]["decision_status"]), payload["result"],
        ))
    os.environ["JC_PRODUCTION_CONFIG"] = str(configs["mcp"])
    entry, (kind, payload) = _run_mcp_probe(bundle, tampered=False)
    if kind == "rejected":
        witnesses.append(_witness(
            entry=entry, probe=probe, subject=subject,
            engine_build_digest=engine_build_digest, decision=None,
            issue_statuses={}, intake_error_code=payload,
            run_identity_digest=EMPTY, result_digest=EMPTY,
            audit_manifest_digest=EMPTY,
        ))
    else:
        witnesses.append(_witness_from_result(
            entry, probe, subject, engine_build_digest, kind, payload,
        ))
    return witnesses


def execute_local_probes(
    probes: list[dict[str, Any]], subject: Mapping[str, Any], workspace: Path,
) -> list[dict[str, Any]]:
    from compiler_core.harness_contract import HarnessQueryInput

    witnesses: list[dict[str, Any]] = []
    for probe in probes:
        undecided = probe["route"] == "local-undecided"
        for entry in ("jc_client", "cli"):
            safe_case = re.sub(r"[^A-Za-z0-9_-]", "-", probe["case_id"])
            state = workspace / f"local-state-{safe_case}-{entry}"
            client = create_local_client(state, workspace / LOCAL_RULES_DIRNAME)
            pack = client.local_pack()
            claims = {row["rule_id"]: row["claim"] for row in pack["rules"]}
            if undecided:
                facts: list[dict[str, str]] = []
                refs: list[tuple[str, str]] = []
            else:
                facts = LOCAL_FACTS
                refs = [("exception", "base")]
            queries = [
                {"issue_id": "base", "claim": claims["base"], "profile": "grounded"},
                {"issue_id": "exception", "claim": claims["exception"], "profile": "grounded"},
            ]
            case_id = f"c06-{probe['case_id'].replace('::', '-')}-{entry}"
            bundle = client.local_case_bundle(
                case_id=case_id, decision_time="2026-09-01T00:00:00Z",
                facts=facts, queries=queries, query_refutations=refs,
            )
            if entry == "jc_client":
                if undecided:
                    envelope = client.evaluate(bundle)
                    witnesses.append(_witness_from_envelope(
                        entry, probe, subject, f"local:{__version__}",
                        envelope.result.decision_status.value, envelope,
                    ))
                    continue
                harness_queries = [
                    HarnessQueryInput(
                        issue_id=q["issue_id"], claim=q["claim"], profile=q["profile"],
                    ) for q in queries
                ]
                result = client.evaluate_harness_bundle(
                    bundle, case_id=case_id, issue_queries=harness_queries,
                )
                decision = str(result["decision_status"])
                issue_statuses = {
                    row["issue_id"]: str(row["conclusion_status"])
                    for row in result["issues"]
                }
                witnesses.append(_witness(
                    entry=entry, probe=probe, subject=subject,
                    engine_build_digest=f"local:{__version__}", decision=decision,
                    issue_statuses=issue_statuses, intake_error_code=None,
                    run_identity_digest=str(result["run_identity_ref"]["digest"]),
                    result_digest=canonical_digest(result["issues"]),
                    audit_manifest_digest=str(result["audit_manifest_ref"]["digest"]),
                ))
                continue
            path = workspace / "local-cli-input.json"
            path.write_text(
                json.dumps(bundle.to_dict(), ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                cli_code = cli_main(
                    ["evaluate", "--input", str(path), "--json"], client=client,
                )
            if cli_code == EXIT_INPUT_ERROR:
                witnesses.append(_witness(
                    entry=entry, probe=probe, subject=subject,
                    engine_build_digest=f"local:{__version__}", decision=None,
                    issue_statuses={},
                    intake_error_code=_cli_rejection_code(err.getvalue() or out.getvalue()),
                    run_identity_digest=EMPTY, result_digest=EMPTY,
                    audit_manifest_digest=EMPTY,
                ))
                continue
            payload = json.loads(out.getvalue())
            result_body = payload["result"]
            if undecided:
                witnesses.append(_witness_from_result(
                    entry, probe, subject, f"local:{__version__}",
                    str(result_body["decision_status"]), result_body,
                ))
                continue
            claim_statuses = {
                row.get("claim_ref", {}).get("digest"): row.get("status")
                for row in result_body.get("claims", [])
            }
            issue_statuses = {
                issue: CLAIM_STATUS_MAP.get(claim_statuses.get(claim), "undecided")
                for issue, claim in (
                    ("base", claims["base"]), ("exception", claims["exception"]),
                )
            }
            witnesses.append(_witness(
                entry=entry, probe=probe, subject=subject,
                engine_build_digest=f"local:{__version__}",
                decision=str(result_body["decision_status"]),
                issue_statuses=issue_statuses, intake_error_code=None,
                run_identity_digest=str(
                    result_body.get("run_identity_ref", {}).get("digest", EMPTY),
                ),
                result_digest=str(result_body.get("result_digest", EMPTY)),
                audit_manifest_digest=str(
                    result_body.get("audit_manifest_ref", {}).get("digest", EMPTY),
                ),
            ))
    return witnesses


# ---------------------------------------------------------------------------
# Receipt assembly (same schema as tools/generate_runtime_refinement_receipts)
# ---------------------------------------------------------------------------


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
    case_status: Mapping[str, str],
    witness_digests: Mapping[str, str],
    *,
    runtime_commit: str,
    runtime_build_id: str,
    runtime_tree: str,
    runtime_worktree_dirty: bool,
) -> dict[str, Any]:
    if expected.get("schema_version") != SCHEMA or expected.get("role") != "expected":
        raise ValueError("expected fixture has an unsupported schema or role")
    expected_body = {
        name: expected[name]
        for name in (
            "lmm_commit", "cases", "source_snapshot_digests", "rule_pack_digest",
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
    cases = []
    for row in expected["cases"]:
        case_id = row["case_id"]
        actual = case_status.get(case_id)
        if actual is None:
            raise SystemExit(f"no witness outcome for {case_id}")
        if actual != row["expected_status"]:
            raise SystemExit(
                f"{case_id}: entry outcome {actual} differs from the expected "
                f"status {row['expected_status']}"
            )
        cases.append({
            "case_id": case_id,
            "actual_status": actual,
            "runtime_evidence_digest": witness_digests[case_id],
        })
    body = {
        "schema_version": SCHEMA,
        "role": "actual",
        "producer": "juris-calculus",
        "lmm_commit": expected["lmm_commit"],
        "runtime_commit": runtime_commit,
        "runtime_tree": runtime_tree,
        "runtime_worktree_dirty": runtime_worktree_dirty,
        "runtime_build_id": runtime_build_id,
        "fixture_digest": expected["fixture_digest"],
        "runtime_fixture_digest": canonical_digest(fixture),
        "source_snapshot_digests": source_digests,
        "rule_pack_digest": rule_pack_digest,
        "cases": cases,
        "execution_status": "SUCCESS",
    }
    return {**body, "receipt_digest": canonical_digest(body)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--runtime-commit", default=None)
    parser.add_argument("--runtime-build-id", default="jc-c06-local:1")
    args = parser.parse_args()

    identity = resolve_runtime_identity(args.runtime_commit)
    runtime_commit = identity["commit"]

    pins = ROOT / "proofs" / "lmm-fullmath"
    completion = json.loads((pins / "MATH_COMPLETION.json").read_text(encoding="utf-8"))
    contract = json.loads((pins / "EXPORT_CONTRACT.json").read_text(encoding="utf-8"))
    subject = validate_math_completion(completion)
    validate_export_contract(contract)
    extract = json.loads((pins / "BINDINGS_EXTRACT.json").read_text(encoding="utf-8"))
    if extract["subject"]["commit"] != SUBJECT_COMMIT:
        raise SystemExit("BINDINGS_EXTRACT drifted from the pinned subject")
    contract_fingerprint(contract)

    workspace = (
        args.workspace
        or (ROOT / "work" / "jc-integration" / "receipt-workspace")
    ).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    rules_dir = workspace / LOCAL_RULES_DIRNAME
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "jc-local-pack.json").write_text(
        json.dumps(LOCAL_RULE_PACK, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )

    material = _build_production_material(workspace)
    # one state root per entry: the same probe bundle must never collide
    # with itself across entry evaluations
    configs = {
        entry: _production_runtime_config(workspace / f"cfg-{entry}", material)
        for entry in ("jc_client", "cli", "mcp")
    }
    os.environ["JC_PRODUCTION_CONFIG"] = str(configs["jc_client"])
    os.environ["JC_RUNTIME_FACTORY"] = "compiler_core.production_runtime"
    capabilities = runtime_client().capabilities()
    engine_build_digest = str(
        capabilities.to_dict().get("engine_build_digest", ""),
    )

    probes = define_probes()
    probe_by_case = {probe["case_id"]: probe for probe in probes}
    witnesses: list[dict[str, Any]] = []
    for probe in probes:
        if probe["route"] == "production":
            witnesses.extend(execute_production_probe(
                probe, material, configs, subject, engine_build_digest,
                workspace,
            ))
        else:
            witnesses.extend(execute_local_probes([probe], subject, workspace))
    for witness in witnesses:
        # JC-02 caller bindings: the producer validates every sealed
        # witness against the probe table and the pinned subject it
        # actually used; the payload never vouches for itself.
        probe = probe_by_case[witness["case_id"]]
        validate_witness(
            witness,
            expected_case_id=probe["case_id"],
            expected_subject=subject,
            expected_input_digest=probe["probe_digest"],
        )
    production_cases = {
        probe["case_id"] for probe in probes if probe["route"] == "production"
    }
    production_witnesses = [
        w for w in witnesses if w["case_id"] in production_cases
    ]
    local_witnesses = [w for w in witnesses if w["case_id"] not in production_cases]
    summary = assert_cross_entry_consistency(
        production_witnesses, required_entries=3,
    )
    summary.update(assert_cross_entry_consistency(
        local_witnesses, required_entries=2,
    ))

    by_case: dict[str, set[str]] = {}
    for witness in witnesses:
        by_case.setdefault(witness["case_id"], set()).add(witness["entry"])
    for probe in probes:
        entries = by_case.get(probe["case_id"], set())
        required = 2 if probe["route"].startswith("local") else 3
        if len(entries) < required:
            raise SystemExit(
                f"{probe['case_id']}: entries {sorted(entries)} below the "
                f"required {required}"
            )
    status_by_case = {case_id: row["status"] for case_id, row in summary.items()}
    for probe in probes:
        actual = status_by_case.get(probe["case_id"])
        if actual != probe["expected_status"]:
            raise SystemExit(
                f"{probe['case_id']}: mapped status {actual!r} differs from "
                f"the expected {probe['expected_status']!r}"
            )

    witness_digests = {
        witness["case_id"]: witness["witness_digest"] for witness in witnesses
    }
    (output / "witnesses.json").write_text(
        json.dumps(witnesses, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    (output / "consistency.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )

    fixture_dir = ROOT / "tests" / "fixtures" / "runtime_refinement"
    expected_dir = pins / "expected"
    for expected_path in sorted(expected_dir.glob("*.expected.json")):
        group = expected_path.name.removesuffix(".expected.json")
        fixture = load_fixture(fixture_dir / f"{group}.fixture.json")
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        group_probes = [p for p in probes if p["group"] == group]
        group_digests = {
            probe["case_id"]: witness_digests[probe["case_id"]]
            for probe in group_probes
        }
        receipt = build_receipt(
            expected, fixture, status_by_case, group_digests,
            runtime_commit=runtime_commit,
            runtime_build_id=args.runtime_build_id,
            runtime_tree=identity["tree"],
            runtime_worktree_dirty=identity["worktree_dirty"],
        )
        target = output / f"{group}.actual.json"
        target.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {target}")
    (output / "runtime-identity.json").write_text(
        json.dumps(identity, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(
        f"runtime identity {runtime_commit[:12]} tree {identity['tree'][:12]} "
        f"dirty={identity['worktree_dirty']}"
    )
    print(f"cross-entry agreement for {len(summary)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
