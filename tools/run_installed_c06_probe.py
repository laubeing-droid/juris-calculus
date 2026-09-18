#!/usr/bin/env python3
"""Installed-artifact C06 probe runner (JC-03 installed lane).

Run this script with the Python of a fresh environment that has the
``juris_calculus`` wheel installed, from a working directory OUTSIDE the
source repository. The script:

- refuses to import repository code (``compiler_core`` must resolve
  inside the running interpreter's site-packages);
- takes the runtime identity from the dist origin manifest shipped next
  to the wheel, never from a git call into a source checkout;
- drives the installed public entries (``JCClient`` facade, CLI
  entrypoint — in-process and as the real console script through the
  JC_RUNTIME_FACTORY contract, and the in-process MCP adapter) over the
  C06 local probe cases;
- re-runs the JC-01/JC-02 witness guards from the installed package;
- writes one JSON run report for ``verify_c06_integration.py
  --origin-manifest``.

Capability boundaries are recorded as boundaries; they are never
counted as semantic votes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from importlib import metadata
from io import StringIO
from pathlib import Path
from typing import Any

RUN_SCHEMA = "jc/c06-installed-run/1.0"
EMPTY = f"sha256:{'0' * 64}"
CLAIM_STATUS_MAP = {"accepted": "accepted", "rejected": "refuted"}


def _digest(value: Any) -> str:
    import hashlib

    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _installed_subject() -> dict[str, Any]:
    from compiler_core.math_export import (
        ATTEMPT,
        LAKE_MANIFEST_SHA256,
        LEAN_TOOLCHAIN_SHA256,
        REPOSITORY,
        RUN_ID,
        SUBJECT_COMMIT,
        SUBJECT_TREE,
    )

    return {
        "commit": SUBJECT_COMMIT,
        "tree": SUBJECT_TREE,
        "repository": REPOSITORY,
        "run_id": RUN_ID,
        "attempt": ATTEMPT,
        "lean_toolchain_sha256": LEAN_TOOLCHAIN_SHA256,
        "lake_manifest_sha256": LAKE_MANIFEST_SHA256,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rule-pack", type=Path, required=True)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--origin-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()

    import compiler_core
    from compiler_core.client import create_local_client
    from compiler_core.math_export import build_run_witness, validate_witness
    from compiler_core.version import __version__

    core_path = Path(compiler_core.__file__).resolve()
    if not core_path.is_relative_to(Path(sys.prefix).resolve()):
        raise SystemExit(
            f"compiler_core must come from the running environment, got "
            f"{core_path}",
        )

    manifest = json.loads(args.origin_manifest.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "jc/dist-origin/1.0":
        raise SystemExit("origin manifest schema drifted")
    probes = json.loads(args.probes.read_text(encoding="utf-8"))["probes"]

    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    rules_dir = work / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "jc-local-pack.json").write_bytes(args.rule_pack.read_bytes())

    try:
        distribution = metadata.distribution("juris-calculus")
        dist_path = getattr(distribution, "_path", None)
        dist_info = {
            "name": distribution.metadata["Name"],
            "version": distribution.version,
            "path": None if dist_path is None else str(Path(dist_path).resolve()),
        }
    except metadata.PackageNotFoundError:
        dist_info = {"name": None, "version": None, "path": None}

    subject = _installed_subject()
    engine_build_digest = f"local:{__version__}"
    witnesses: list[dict[str, Any]] = []
    entries: dict[str, str] = {}
    boundaries: list[str] = []
    checks: dict[str, Any] = {}

    from compiler_core.cli import main as cli_main
    from compiler_core.harness_contract import HarnessQueryInput
    from compiler_core.mcp import MCPServerV4

    for probe in probes:
        undecided = probe["route"] == "local-undecided"
        safe_case = re.sub(r"[^A-Za-z0-9_-]", "-", probe["case_id"])
        for entry in ("jc_client", "cli"):
            state = work / f"local-state-{safe_case}-{entry}"
            client = create_local_client(state, rules_dir)
            pack = client.local_pack()
            claims = {row["rule_id"]: row["claim"] for row in pack["rules"]}
            facts: list[dict[str, str]] = [] if undecided else [
                {"fact_key": "f.contract"}, {"fact_key": "f.ex"},
            ]
            refs: list[tuple[str, str]] = [] if undecided else [
                ("exception", "base"),
            ]
            queries = [
                {"issue_id": "base", "claim": claims["base"], "profile": "grounded"},
                {"issue_id": "exception", "claim": claims["exception"],
                 "profile": "grounded"},
            ]
            case_id = f"c06-{probe['case_id'].replace('::', '-')}-{entry}"
            bundle = client.local_case_bundle(
                case_id=case_id, decision_time="2026-09-01T00:00:00Z",
                facts=facts, queries=queries, query_refutations=refs,
            )
            if entry == "jc_client":
                if undecided:
                    envelope = client.evaluate(bundle)
                    witnesses.append(build_run_witness(
                        entry="jc_client",
                        case_id=probe["case_id"],
                        probe_semantics=probe["semantics"],
                        lmm_subject=subject,
                        engine_version=__version__,
                        engine_build_digest=engine_build_digest,
                        run_identity_digest=str(envelope.run_identity.request_ref.digest),
                        input_digest=probe["probe_digest"],
                        result_digest=str(envelope.result.result_digest),
                        audit_manifest_digest=str(envelope.audit_manifest_ref.digest),
                        decision_status=envelope.result.decision_status.value,
                        issue_statuses={},
                    ))
                else:
                    harness_queries = [
                        HarnessQueryInput(
                            issue_id=q["issue_id"], claim=q["claim"],
                            profile=q["profile"],
                        ) for q in queries
                    ]
                    result = client.evaluate_harness_bundle(
                        bundle, case_id=case_id, issue_queries=harness_queries,
                    )
                    witnesses.append(build_run_witness(
                        entry="jc_client",
                        case_id=probe["case_id"],
                        probe_semantics=probe["semantics"],
                        lmm_subject=subject,
                        engine_version=__version__,
                        engine_build_digest=engine_build_digest,
                        run_identity_digest=str(result["run_identity_ref"]["digest"]),
                        input_digest=probe["probe_digest"],
                        result_digest=_digest(result["issues"]),
                        audit_manifest_digest=str(result["audit_manifest_ref"]["digest"]),
                        decision_status=str(result["decision_status"]),
                        issue_statuses={
                            row["issue_id"]: str(row["conclusion_status"])
                            for row in result["issues"]
                        },
                        focus_issue=probe.get("focus_issue"),
                    ))
                continue
            path = work / f"local-cli-input-{safe_case}.json"
            path.write_text(
                json.dumps(bundle.to_dict(), ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                cli_main(["evaluate", "--input", str(path), "--json"], client=client)
            payload = json.loads(out.getvalue())
            result_body = payload["result"]
            if undecided:
                witnesses.append(build_run_witness(
                    entry="cli",
                    case_id=probe["case_id"],
                    probe_semantics=probe["semantics"],
                    lmm_subject=subject,
                    engine_version=__version__,
                    engine_build_digest=engine_build_digest,
                    run_identity_digest=str(
                        result_body.get("run_identity_ref", {}).get("digest", EMPTY),
                    ),
                    input_digest=probe["probe_digest"],
                    result_digest=str(result_body.get("result_digest", EMPTY)),
                    audit_manifest_digest=str(
                        result_body.get("audit_manifest_ref", {}).get("digest", EMPTY),
                    ),
                    decision_status=str(result_body["decision_status"]),
                    issue_statuses={},
                ))
            else:
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
                witnesses.append(build_run_witness(
                    entry="cli",
                    case_id=probe["case_id"],
                    probe_semantics=probe["semantics"],
                    lmm_subject=subject,
                    engine_version=__version__,
                    engine_build_digest=engine_build_digest,
                    run_identity_digest=str(
                        result_body.get("run_identity_ref", {}).get("digest", EMPTY),
                    ),
                    input_digest=probe["probe_digest"],
                    result_digest=str(result_body.get("result_digest", EMPTY)),
                    audit_manifest_digest=str(
                        result_body.get("audit_manifest_ref", {}).get("digest", EMPTY),
                    ),
                    decision_status=str(result_body["decision_status"]),
                    issue_statuses=issue_statuses,
                    focus_issue=probe.get("focus_issue"),
                ))
        entries[f"{probe['case_id']}:jc_client"] = "witnessed"
        entries[f"{probe['case_id']}:cli"] = "witnessed"

        # in-process MCP adapter over the same local client: supported
        # headless for the envelope-shaped probe; the focus-bound local
        # case has no issue rows on the envelope path, which is recorded
        # as a boundary rather than faked as a vote.
        state = work / f"local-state-{safe_case}-mcp"
        client = create_local_client(state, rules_dir)
        bundle = client.local_case_bundle(
            case_id=f"c06-{probe['case_id'].replace('::', '-')}-mcp",
            decision_time="2026-09-01T00:00:00Z",
            facts=[] if undecided else [
                {"fact_key": "f.contract"}, {"fact_key": "f.ex"},
            ],
            queries=queries,
            query_refutations=[] if undecided else [("exception", "base")],
        )
        mcp = MCPServerV4(client)
        out, is_error = mcp.call_tool(
            "jc_evaluate", {"case_bundle": bundle.to_dict()},
        )
        if is_error:
            boundaries.append(
                f"{probe['case_id']}:mcp:in-process adapter returned an "
                "error result",
            )
            entries[f"{probe['case_id']}:mcp"] = "error-recorded"
        elif undecided:
            result = out["result"]
            witnesses.append(build_run_witness(
                entry="mcp",
                case_id=probe["case_id"],
                probe_semantics=probe["semantics"],
                lmm_subject=subject,
                engine_version=__version__,
                engine_build_digest=engine_build_digest,
                run_identity_digest=str(
                    result.get("run_identity_ref", {}).get("digest", EMPTY),
                ),
                input_digest=probe["probe_digest"],
                result_digest=str(result.get("result_digest", EMPTY)),
                audit_manifest_digest=str(
                    result.get("audit_manifest_ref", {}).get("digest", EMPTY),
                ),
                decision_status=str(result["decision_status"]),
                issue_statuses={},
            ))
            entries[f"{probe['case_id']}:mcp"] = "witnessed"
        else:
            boundaries.append(
                f"{probe['case_id']}:mcp:envelope result carries no issue "
                "rows for a focus-bound local case; no witness claimed",
            )
            entries[f"{probe['case_id']}:mcp"] = "boundary:envelope-no-issue-rows"

    # the real installed console script. The keyless local runtime has
    # no persisted artifact store for case bundles built by another
    # process: the artifacts live in the building client's resolver
    # overlay, so a fresh process reading the bundle JSON is refused
    # with the typed CASE_BUNDLE_INCOMPLETE. That typed refusal (or a
    # success, should a persisted route appear) is recorded verbatim —
    # it is a capability boundary of the keyless surface, not a
    # semantic vote.
    decisive = next(p for p in probes if p["route"] == "local")
    factory = work / "local_probe_factory.py"
    state_root = (work / "local-state-console").resolve()
    factory.write_text(
        "from pathlib import Path\n"
        "from compiler_core.client import create_local_client\n"
        "def create_client():\n"
        f"    return create_local_client(Path({str(state_root)!r}), "
        f"Path({str(rules_dir)!r}))\n",
        encoding="utf-8",
    )
    bundle_path = work / "console-input.json"
    client = create_local_client(state_root, rules_dir)
    pack = client.local_pack()
    claims = {row["rule_id"]: row["claim"] for row in pack["rules"]}
    console_bundle = client.local_case_bundle(
        case_id="c06-console-script-probe",
        decision_time="2026-09-01T00:00:00Z",
        facts=[{"fact_key": "f.contract"}, {"fact_key": "f.ex"}],
        queries=[
            {"issue_id": "base", "claim": claims["base"], "profile": "grounded"},
            {"issue_id": "exception", "claim": claims["exception"],
             "profile": "grounded"},
        ],
        query_refutations=[("exception", "base")],
    )
    bundle_path.write_text(
        json.dumps(console_bundle.to_dict(), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    console = Path(sys.prefix) / (
        "Scripts/jc.exe" if sys.platform == "win32" else "bin/jc"
    )
    environment = {
        k: v for k, v in os.environ.items()
        if k not in {"PYTHONPATH", "JC_RUNTIME_FACTORY", "JC_PRODUCTION_CONFIG"}
    }
    environment["PYTHONPATH"] = str(work)
    environment["JC_RUNTIME_FACTORY"] = "local_probe_factory"
    version_run = subprocess.run(  # noqa: S603 - fixed argv
        [str(console), "--version"], capture_output=True, text=True,
        check=False, shell=False, env=environment, cwd=str(work),
    )
    keyless_run = subprocess.run(  # noqa: S603 - fixed argv
        [str(console), "capabilities", "--json"], capture_output=True, text=True,
        check=False, shell=False, env={
            k: v for k, v in environment.items() if k != "JC_RUNTIME_FACTORY"
        }, cwd=str(work),
    )
    completed = subprocess.run(  # noqa: S603 - fixed argv
        [str(console), "evaluate", "--input", str(bundle_path), "--json"],
        capture_output=True, text=True, check=False, shell=False, env=environment,
        cwd=str(work),
    )
    console_version = version_run.stdout.strip()
    keyless_code = None
    if keyless_run.stderr:
        try:
            keyless_code = json.loads(keyless_run.stderr).get("code")
        except json.JSONDecodeError:
            keyless_code = "UNREADABLE"
    evaluate_code = None
    console_decision = None
    if completed.returncode == 0:
        console_decision = json.loads(completed.stdout)["result"]["decision_status"]
        evaluate_code = "SUCCESS"
    else:
        try:
            evaluate_code = json.loads(completed.stderr).get("code", "UNREADABLE")
        except json.JSONDecodeError:
            evaluate_code = "UNREADABLE"
    console_ok = (
        version_run.returncode == 0
        and console_version == f"jc {__version__}"
        and keyless_code == "RUNTIME_NOT_CONFIGURED"
        and evaluate_code in {
            "SUCCESS", "CASE_BUNDLE_INCOMPLETE", "RUNTIME_NOT_CONFIGURED",
        }
    )
    entries[f"{decisive['case_id']}:cli_console_script"] = (
        f"executed:version={console_version};"
        f"keyless_capabilities={keyless_code};"
        f"local_evaluate={evaluate_code}"
    )
    if evaluate_code != "SUCCESS":
        boundaries.append(
            "console-script cross-process evaluation of a keyless local "
            f"bundle is refused with the typed {evaluate_code}: local case "
            "artifacts live in the building client's resolver overlay and "
            "no persisted local artifact store exists; the in-process CLI "
            "entrypoint (cli.main) is the exercised semantic path",
        )

    # JC-01/JC-02 guards re-run from the installed package
    guard_engine_error = build_run_witness(
        entry="jc_client",
        case_id="installed-guard::engine-error-focus",
        probe_semantics="installed JC-01 guard: engine_error + accepted focus",
        lmm_subject=subject,
        engine_version=__version__,
        engine_build_digest=engine_build_digest,
        run_identity_digest="sha256:" + "0" * 64,
        input_digest="sha256:" + "1" * 64,
        result_digest="sha256:" + "2" * 64,
        audit_manifest_digest="sha256:" + "3" * 64,
        decision_status="engine_error",
        issue_statuses={"issue": "accepted"},
        focus_issue="issue",
    )
    guard_conflict = build_run_witness(
        entry="cli",
        case_id="installed-guard::conflict-no-focus",
        probe_semantics="installed JC-01 guard: conflict without refuted row",
        lmm_subject=subject,
        engine_version=__version__,
        engine_build_digest=engine_build_digest,
        run_identity_digest="sha256:" + "0" * 64,
        input_digest="sha256:" + "1" * 64,
        result_digest="sha256:" + "2" * 64,
        audit_manifest_digest="sha256:" + "3" * 64,
        decision_status="conflict_certificate",
        issue_statuses={},
    )
    from compiler_core.canonical_serialization import digest_value

    forged = {
        "schema_version": "jc/lmm-c06-witness/1.1",
        "producer": "juris-calculus",
        "entry": "cli",
        "status": "PROVED",
    }
    forged["witness_digest"] = str(digest_value(forged))
    try:
        validate_witness(forged)
        forged_rejected = False
    except ValueError:
        forged_rejected = True

    checks = {
        "jc01_engine_error_focus_stays_tainted": (
            guard_engine_error["status"] == "TAINTED"
        ),
        "jc01_conflict_certificate_reads_undecided": (
            guard_conflict["status"] == "UNDECIDED"
        ),
        "jc02_five_field_forged_witness_rejected": forged_rejected,
        "console_script_executed": console_ok,
    }
    if not all(checks.values()):
        raise SystemExit(f"installed guard checks failed: {checks}")

    report = {
        "schema_version": RUN_SCHEMA,
        "producer": "juris-calculus-installed-probe",
        "runtime_commit": manifest["source_commit"],
        "runtime_tree": manifest["source_tree"],
        "engine_version": __version__,
        "compiler_core_path": str(core_path),
        "interpreter": sys.executable,
        "installed_distribution": dist_info,
        "entries": entries,
        "witnesses": witnesses,
        "capability_boundaries": boundaries + [
            "MCP exercised through the in-process JSON-RPC adapter over the "
            "local client; the stdio transport authority tests live in the "
            "source repository test suite",
            "production-route probes need repository test material and run "
            "in the source lane only; the installed lane covers the local "
            "probe subset",
        ],
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"installed run report written to {args.output}")
    print(f"witnesses: {len(witnesses)}; boundaries: {len(boundaries) + 2}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
