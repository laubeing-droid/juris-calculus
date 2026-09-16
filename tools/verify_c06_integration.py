#!/usr/bin/env python3
"""End-to-end cross-repo C06 verification and integration evidence writer.

Pipeline (each step fails closed):
1. re-derive the pinned legal-math-modeling subject identity from the
   checked-out LMM repository (HEAD, tree, lean-toolchain digest,
   lake-manifest digest) and refuse any drift;
2. validate the pinned completion documents, the export contract and the
   bindings extract against the pinned subject;
3. re-materialize the expected refinement fixtures from the LMM checkout
   and byte-compare them with the pinned copies;
4. run the C06 receipt producer across the JC public entries, with the
   producer identity (commit, tree, worktree dirtiness) resolved from
   the actual checkout — a ``--runtime-commit`` that disagrees with the
   checked-out HEAD is a typed refusal, never a borrowed SHA;
5. hand every receipt to the LMM independent checker (a separate process
   that never imports JC code and never calls the JC main solver);
6. write the integration evidence JSON with both sides' commits, the
   mathematics run id, the contract fingerprints and the honesty
   boundaries kept open.

Installed-artifact mode (``--origin-manifest``): when the runtime under
verification is an installed wheel, the runtime identity comes only from
the dist origin manifest (and, when supplied, the wheel bytes/RECORD),
never from a git call into a source checkout. The installed run report
is re-validated with the full witness binding rules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler_core.canonical_serialization import digest_value  # noqa: E402
from compiler_core.math_export import (  # noqa: E402
    ATTEMPT,
    EXPORT_INTERFACES,
    LAKE_MANIFEST_SHA256,
    LATEST_EVIDENCE,
    LATEST_EVIDENCE_RUN_ID,
    LEAN_TOOLCHAIN_SHA256,
    REPOSITORY,
    REQUIRED_INTERFACES,
    RUNTIME_REF_COMMIT,
    RUN_ID,
    SUBJECT_COMMIT,
    SUBJECT_TREE,
    contract_fingerprint,
    math_completion_fingerprint,
    subject_fingerprint,
    validate_export_contract,
    validate_math_completion,
    validate_witness,
)
from compiler_core.math_export.checker_gateway import verify_receipt  # noqa: E402
from compiler_core.version import __version__  # noqa: E402

EVIDENCE_SCHEMA = "jc/c06-integration-evidence/1.0"
INSTALLED_EVIDENCE_SCHEMA = "jc/c06-installed-verification/1.0"
INSTALLED_RUN_SCHEMA = "jc/c06-installed-run/1.0"
ORIGIN_SCHEMA = "jc/dist-origin/1.0"
GROUPS = ("contract_breach", "fact_admission", "unknown_timeout")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


class VerificationError(RuntimeError):
    """Raised when any verification step fails; no partial evidence."""


CRLF = b"\r\n"
LF = b"\n"


def _normalized(path: Path) -> bytes:
    return path.read_bytes().replace(CRLF, LF)


def _sha256(path: Path) -> str:
    return hashlib.sha256(_normalized(path)).hexdigest()


def _git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed argv
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        check=False, shell=False,
    )
    if completed.returncode != 0:
        raise VerificationError(f"git {' '.join(args)} failed in {cwd}")
    return completed.stdout.strip()


def resolve_runtime_identity(requested_commit: str | None) -> dict[str, Any]:
    """JC-03: the evidence cites the checkout that actually ran.

    A requested ``--runtime-commit`` that does not equal the checked-out
    HEAD is refused with a typed error; the recorded identity always
    carries the tree and the worktree dirtiness so a dirty producer is
    never presented as a clean commit.
    """

    head = _git(["rev-parse", "HEAD"], ROOT)
    if requested_commit is not None:
        if SHA_PATTERN.fullmatch(requested_commit) is None:
            raise VerificationError(
                "RUNTIME_COMMIT_INVALID: --runtime-commit must be a "
                "lowercase 40-character Git SHA",
            )
        if requested_commit != head:
            raise VerificationError(
                f"RUNTIME_COMMIT_MISMATCH: --runtime-commit {requested_commit} "
                f"does not match the checked-out HEAD {head}",
            )
        commit = requested_commit
    else:
        commit = head
    tree = _git(["rev-parse", "HEAD^{tree}"], ROOT)
    status = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True,
        text=True, check=False, shell=False,
    )
    if status.returncode != 0:
        raise VerificationError("git status failed in the source checkout")
    dirty_entries = sorted(line for line in status.stdout.splitlines() if line.strip())
    return {
        "commit": commit,
        "tree": tree,
        "worktree_dirty": bool(dirty_entries),
        "dirty_entries": dirty_entries,
    }


def step_identity(lmm_root: Path) -> dict[str, str]:
    commit = _git(["rev-parse", "HEAD"], lmm_root)
    tree = _git(["rev-parse", "HEAD^{tree}"], lmm_root)
    if commit != SUBJECT_COMMIT or tree != SUBJECT_TREE:
        raise VerificationError(
            f"LMM checkout {commit}/{tree} is not the pinned subject "
            f"{SUBJECT_COMMIT}/{SUBJECT_TREE}",
        )
    lean_dir = lmm_root / "proofs" / "lean" / "juris_lean"
    toolchain = _sha256(lean_dir / "lean-toolchain")
    manifest = _sha256(lean_dir / "lake-manifest.json")
    if toolchain != LEAN_TOOLCHAIN_SHA256 or manifest != LAKE_MANIFEST_SHA256:
        raise VerificationError("toolchain or lake-manifest digest drifted")
    return {
        "commit": commit,
        "tree": tree,
        "lean_toolchain_sha256": toolchain,
        "lake_manifest_sha256": manifest,
    }


def step_documents(lmm_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    pins = ROOT / "proofs" / "lmm-fullmath"
    completion = json.loads((pins / "MATH_COMPLETION.json").read_text(encoding="utf-8"))
    contract = json.loads((pins / "EXPORT_CONTRACT.json").read_text(encoding="utf-8"))
    extract = json.loads((pins / "BINDINGS_EXTRACT.json").read_text(encoding="utf-8"))
    validate_math_completion(completion)
    validate_export_contract(contract)
    if extract["subject"]["commit"] != SUBJECT_COMMIT:
        raise VerificationError("bindings extract drifted from the pinned subject")
    source = lmm_root / extract["source"]["path"]
    digest = _sha256(source)
    if digest != extract["source"]["sha256"]:
        raise VerificationError("BINDINGS.json digest drifted from the extract")
    bindings = json.loads(source.read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in bindings["bindings"]}
    if len(rows) != extract["source"]["binding_count"]:
        raise VerificationError("binding count drifted")
    for registration_id, pinned in extract["bound_registrations"].items():
        row = rows.get(registration_id)
        if row is None:
            raise VerificationError(f"bound registration missing: {registration_id}")
        for field in ("theorem", "contract", "semantic_links"):
            if row[field] != pinned[field]:
                raise VerificationError(
                    f"{registration_id} {field} drifted from the pinned extract",
                )
    for name, digest in extract["expected_fixtures_sha256"].items():
        if _sha256(pins / "expected" / name) != digest:
            raise VerificationError(f"pinned expected fixture drifted: {name}")
    return completion, contract, extract


def step_expected(lmm_root: Path, work: Path) -> dict[str, str]:
    from compiler_core.math_export.checker_gateway import materialize_expected

    regenerated = work / "expected-regenerated"
    regenerated.mkdir(parents=True, exist_ok=True)
    paths = materialize_expected(
        lmm_root, regenerated,
        lmm_commit=SUBJECT_COMMIT,
        runtime_fixture_dir=ROOT / "tests" / "fixtures" / "runtime_refinement",
    )
    pins = ROOT / "proofs" / "lmm-fullmath" / "expected"
    digests: dict[str, str] = {}
    for path in paths:
        pinned = pins / path.name
        if not pinned.is_file():
            raise VerificationError(f"regenerated fixture has no pinned copy: {path.name}")
        if _normalized(path) != _normalized(pinned):
            raise VerificationError(f"regenerated fixture differs from the pin: {path.name}")
        digests[path.name] = _sha256(pinned)
    return digests


def step_receipts(
    work: Path, runtime_commit: str, runtime_build_id: str, runtime_tree: str,
) -> dict[str, str]:
    receipts = work / "receipts"
    completed = subprocess.run(  # noqa: S603 - fixed argv
        [
            sys.executable, "-B",
            str(ROOT / "tools" / "generate_c06_entry_receipts.py"),
            "--output-dir", str(receipts),
            "--workspace", str(work / "receipt-workspace"),
            "--runtime-commit", runtime_commit,
            "--runtime-build-id", runtime_build_id,
        ],
        cwd=str(ROOT), capture_output=True, text=True, check=False, shell=False,
    )
    if completed.returncode != 0:
        raise VerificationError(
            "receipt producer failed:\n" + (completed.stderr or completed.stdout)[-2000:],
        )
    digests: dict[str, str] = {}
    for group in GROUPS:
        path = receipts / f"{group}.actual.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        # the receipts must cite the producer identity resolved from this
        # checkout, not an independently claimed one
        if receipt.get("runtime_commit") != runtime_commit:
            raise VerificationError(
                f"{group} receipt runtime_commit disagrees with the "
                "verified checkout identity",
            )
        if receipt.get("runtime_tree") != runtime_tree:
            raise VerificationError(
                f"{group} receipt runtime_tree disagrees with the "
                "verified checkout identity",
            )
        digests[f"{group}.actual.json"] = _sha256(path)
    return digests


def step_checker(
    lmm_root: Path, work: Path, runtime_commit: str,
) -> list[dict[str, Any]]:
    pins = ROOT / "proofs" / "lmm-fullmath" / "expected"
    receipts = work / "receipts"
    reports_dir = work / "checker-reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    for group in GROUPS:
        report = verify_receipt(
            lmm_root,
            pins / f"{group}.expected.json",
            receipts / f"{group}.actual.json",
            lmm_commit=SUBJECT_COMMIT,
            runtime_commit=runtime_commit,
            output=reports_dir / f"{group}.report.json",
        )
        report["group"] = group
        reports.append(report)
    return reports


def build_evidence(
    lmm_identity: dict[str, str],
    completion: dict[str, Any],
    extract: dict[str, Any],
    expected_digests: dict[str, str],
    receipt_digests: dict[str, str],
    checker_reports: list[dict[str, Any]],
    runtime_identity: dict[str, Any],
    runtime_build_id: str,
) -> dict[str, Any]:
    pins = ROOT / "proofs" / "lmm-fullmath"
    receipts_dir = receipts_path_of()
    witnesses = json.loads(
        (receipts_dir / "witnesses.json").read_text(encoding="utf-8"),
    )
    consistency = json.loads(
        (receipts_dir / "consistency.json").read_text(encoding="utf-8"),
    )
    subject = completion["subject"]
    return {
        "schema_version": EVIDENCE_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ",
        ),
        "juris_calculus": {
            "commit": runtime_identity["commit"],
            "tree": runtime_identity["tree"],
            "worktree_dirty": runtime_identity["worktree_dirty"],
            "dirty_entries": runtime_identity["dirty_entries"],
            "repository": "laubeing-droid/juris-calculus",
            "engine_version": __version__,
            "runtime_build_id": runtime_build_id,
            "runtime_identity_source": "source-checkout",
            "runtime_ref_baseline_commit": RUNTIME_REF_COMMIT,
        },
        "legal_math_modeling": {
            "repository": REPOSITORY,
            "commit": lmm_identity["commit"],
            "tree": lmm_identity["tree"],
            "run_id": RUN_ID,
            "attempt": ATTEMPT,
            "lean_toolchain_sha256": lmm_identity["lean_toolchain_sha256"],
            "lake_manifest_sha256": lmm_identity["lake_manifest_sha256"],
            "subject_fingerprint": str(subject_fingerprint(subject)),
            "scope": completion["scope"],
            "mandatory_registrations": completion["mandatory_registrations"],
            "evidence_runs": {
                "original_receipt_run": RUN_ID,
                "latest_same_subject_evidence": {
                    "run_id": LATEST_EVIDENCE_RUN_ID,
                    "completed_at_utc": LATEST_EVIDENCE["completed_at_utc"],
                    "artifact_zip_sha256": LATEST_EVIDENCE["artifact"]["zip_sha256"],
                    "action": LATEST_EVIDENCE["action"],
                    "semantic_repin": False,
                },
            },
        },
        "contract": {
            "status": "READY_FOR_LATER_INTEGRATION_DESIGN",
            "required_interfaces": list(REQUIRED_INTERFACES),
            "interface_adapters": [
                {"name": row["name"], "status": row["status"],
                 "jc_adapter": row["jc_adapter"]}
                for row in EXPORT_INTERFACES
            ],
            "math_completion_fingerprint": str(
                math_completion_fingerprint(completion),
            ),
            "export_contract_fingerprint": str(
                contract_fingerprint(json.loads(
                    (pins / "EXPORT_CONTRACT.json").read_text(encoding="utf-8"),
                )),
            ),
            "pinned_sha256": {
                "MATH_COMPLETION.json": _sha256(pins / "MATH_COMPLETION.json"),
                "EXPORT_CONTRACT.json": _sha256(pins / "EXPORT_CONTRACT.json"),
                "BINDINGS_EXTRACT.json": _sha256(pins / "BINDINGS_EXTRACT.json"),
            },
            "c06_semantic_link": "JurisLean.FullMath.Composition.checker_correspondence",
            "c06_claim": "checker acceptance of these run receipts implies the "
                         "outcomes belong to the independent solutions of the "
                         "pinned subject (Contracts.target_C06)",
        },
        "bindings": {
            "source_sha256": extract["source"]["sha256"],
            "binding_count": extract["source"]["binding_count"],
            "bound_registrations": sorted(extract["bound_registrations"]),
        },
        "expected_fixtures_sha256": expected_digests,
        "receipts_sha256": receipt_digests,
        "witnesses": witnesses,
        "cross_entry_consistency": consistency,
        "checker_reports": [
            {key: report.get(key) for key in (
                "group", "passed", "blocked", "error_codes", "lmm_commit",
                "runtime_commit", "runtime_build_id", "fixture_digest",
            )}
            for report in checker_reports
        ],
        "verification": {
            "independent_checker": "legal-math-modeling "
                                   "scripts/verify_runtime_refinement_receipt.py "
                                   "in its own process at the pinned subject",
            "main_solver_isolation": "the checker never imports juris-calculus "
                                     "code and never calls the JC main solver",
            "expected_regeneration": "byte-equal with the pinned copies",
            "all_passed": all(
                report.get("passed") is True and report.get("blocked") is False
                for report in checker_reports
            ),
            "changed_module_mode_used": False,
        },
        "boundaries": extract["honest_boundaries"],
    }


def receipts_path_of() -> Path:
    return ROOT / "work" / "jc-integration" / "receipts"


def _pinned_subject() -> dict[str, Any]:
    completion = json.loads(
        (ROOT / "proofs" / "lmm-fullmath" / "MATH_COMPLETION.json")
        .read_text(encoding="utf-8"),
    )
    return validate_math_completion(completion)


def _installed_origin_checks(
    manifest: dict[str, Any], manifest_path: Path, wheel: Path | None,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = [
        {
            "check": "origin-manifest-schema",
            "passed": (
                manifest.get("schema_version") == ORIGIN_SCHEMA
                and manifest.get("mode") == "installed"
            ),
        },
    ]
    commit = manifest.get("source_commit")
    tree = manifest.get("source_tree")
    checks.append({
        "check": "origin-manifest-identity-shape",
        "passed": (
            isinstance(commit, str) and SHA_PATTERN.fullmatch(commit) is not None
            and isinstance(tree, str) and SHA_PATTERN.fullmatch(tree) is not None
            and isinstance(manifest.get("worktree_dirty_at_build"), bool)
            and isinstance(manifest.get("wheel_sha256"), str)
            and len(manifest["wheel_sha256"]) == 64
            and isinstance(manifest.get("record_entries_sha256"), str)
            and len(manifest["record_entries_sha256"]) == 64
        ),
    })
    if wheel is not None:
        wheel_digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        checks.append({
            "check": "installed-wheel-sha256",
            "passed": wheel_digest == manifest.get("wheel_sha256"),
            "observed": wheel_digest,
        })
        import zipfile

        with zipfile.ZipFile(wheel) as archive:
            record_name = next(
                name for name in archive.namelist()
                if name.endswith(".dist-info/RECORD")
            )
            record_digest = hashlib.sha256(
                archive.read(record_name).replace(b"\r\n", b"\n"),
            ).hexdigest()
        checks.append({
            "check": "installed-wheel-record-digest",
            "passed": record_digest == manifest.get("record_entries_sha256"),
            "observed": record_digest,
        })
    if not all(row["passed"] for row in checks):
        failed = [row["check"] for row in checks if not row["passed"]]
        raise VerificationError(
            f"installed origin verification failed: {failed}",
        )
    return checks


def run_installed_verification(args: argparse.Namespace) -> int:
    """Verify an installed-artifact C06 run report.

    The runtime identity comes only from the dist origin manifest and
    (when supplied) the wheel bytes; this mode never resolves identity
    through git in a source checkout.
    """

    if args.installed_report is None:
        raise VerificationError(
            "--installed-report is required with --origin-manifest",
        )
    manifest_path = args.origin_manifest.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    origin_checks = _installed_origin_checks(
        manifest, manifest_path, args.installed_wheel,
    )

    report_path = args.installed_report.resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema_version") != INSTALLED_RUN_SCHEMA:
        raise VerificationError("installed run report schema drifted")
    if report.get("runtime_commit") != manifest.get("source_commit"):
        raise VerificationError(
            "RUNTIME_ORIGIN_MISMATCH: the installed run report cites "
            f"{report.get('runtime_commit')!r} while the dist origin "
            f"manifest cites {manifest.get('source_commit')!r}",
        )

    from tools.generate_c06_entry_receipts import define_probes

    probe_by_case = {probe["case_id"]: probe for probe in define_probes()}
    subject = _pinned_subject()
    witnesses = report.get("witnesses")
    if not isinstance(witnesses, list) or not witnesses:
        raise VerificationError("installed run report carries no witnesses")
    witness_results = []
    for witness in witnesses:
        probe = probe_by_case.get(witness.get("case_id"))
        if probe is None:
            raise VerificationError(
                f"installed witness cites unknown case {witness.get('case_id')!r}",
            )
        validate_witness(
            witness,
            expected_case_id=probe["case_id"],
            expected_subject=subject,
            expected_input_digest=probe["probe_digest"],
        )
        if witness.get("juris_calculus", {}).get("engine_version") != report.get(
            "engine_version",
        ):
            raise VerificationError(
                "installed witness engine version disagrees with the report",
            )
        witness_results.append({
            "case_id": witness["case_id"],
            "entry": witness["entry"],
            "status": witness["status"],
            "witness_digest": witness["witness_digest"],
        })

    expected_statuses = {
        probe["case_id"]: probe["expected_status"] for probe in probe_by_case.values()
    }
    for row in witness_results:
        if row["status"] != expected_statuses[row["case_id"]]:
            raise VerificationError(
                f"installed witness status for {row['case_id']} disagrees "
                f"with the pinned expectation",
            )

    evidence = {
        "schema_version": INSTALLED_EVIDENCE_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ",
        ),
        "origin_manifest": {
            "path": manifest_path.name,
            "sha256": _sha256(manifest_path),
            "source_commit": manifest.get("source_commit"),
            "source_tree": manifest.get("source_tree"),
            "worktree_dirty_at_build": manifest.get("worktree_dirty_at_build"),
            "wheel": manifest.get("wheel"),
            "identity_source": "dist-origin-manifest (no git identity of any "
                               "source checkout was consulted)",
        },
        "installed_report": {
            "path": report_path.name,
            "sha256": _sha256(report_path),
            "engine_version": report.get("engine_version"),
            "compiler_core_path": report.get("compiler_core_path"),
            "entries": report.get("entries"),
            "capability_boundaries": report.get("capability_boundaries", []),
        },
        "origin_checks": origin_checks,
        "witnesses": witness_results,
        "verification": {
            "witness_binding": "case/subject/input bindings re-derived from "
                               "the probe table and the pinned subject",
            "scope": "installed-artifact local probe subset; the full "
                     "cross-entry receipts and the independent LMM checker "
                     "run in the source lane only",
        },
    }
    output = args.output or (
        ROOT / "work" / "jc-integration" / "installed-verification.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"installed verification evidence written to {output}")
    print(
        f"installed artifact bound to source commit "
        f"{manifest.get('source_commit', '')[:12]}; "
        f"{len(witness_results)} witnesses validated",
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lmm-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--runtime-commit", default=None)
    parser.add_argument("--runtime-build-id", default="jc-c06-verification:1")
    parser.add_argument("--origin-manifest", type=Path, default=None)
    parser.add_argument("--installed-wheel", type=Path, default=None)
    parser.add_argument("--installed-report", type=Path, default=None)
    args = parser.parse_args()

    if args.origin_manifest is not None:
        try:
            return run_installed_verification(args)
        except VerificationError as exc:
            print(f"verification failed: {exc}", file=sys.stderr)
            return 2

    if args.lmm_root is None:
        print(
            "verification failed: --lmm-root is required in the source lane",
            file=sys.stderr,
        )
        return 2
    try:
        runtime_identity = resolve_runtime_identity(args.runtime_commit)
        runtime_commit = runtime_identity["commit"]
        work = ROOT / "work" / "jc-integration"

        lmm_identity = step_identity(args.lmm_root.resolve())
        completion, _contract, extract = step_documents(args.lmm_root.resolve())
        expected_digests = step_expected(args.lmm_root.resolve(), work)
        receipt_digests = step_receipts(
            work, runtime_commit, args.runtime_build_id,
            runtime_identity["tree"],
        )
        checker_reports = step_checker(
            args.lmm_root.resolve(), work, runtime_commit,
        )
        if not all(
            report.get("passed") is True and report.get("blocked") is False
            for report in checker_reports
        ):
            raise VerificationError(
                "independent checker did not accept every receipt",
            )
        evidence = build_evidence(
            lmm_identity, completion, extract, expected_digests, receipt_digests,
            checker_reports, runtime_identity, args.runtime_build_id,
        )
    except VerificationError as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 2
    output = args.output or (work / "integration-evidence.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"integration evidence written to {output}")
    print(
        f"runtime {runtime_commit[:12]} tree "
        f"{runtime_identity['tree'][:12]} dirty="
        f"{runtime_identity['worktree_dirty']}",
    )
    print(f"lmm subject {SUBJECT_COMMIT[:12]} run {RUN_ID}; all receipts accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
