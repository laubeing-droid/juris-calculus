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
4. run the C06 receipt producer across the JC public entries;
5. hand every receipt to the LMM independent checker (a separate process
   that never imports JC code and never calls the JC main solver);
6. write the integration evidence JSON with both sides' commits, the
   mathematics run id, the contract fingerprints and the honesty
   boundaries kept open.
"""
from __future__ import annotations

import argparse
import hashlib
import json
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
)
from compiler_core.math_export.checker_gateway import verify_receipt  # noqa: E402
from compiler_core.version import __version__  # noqa: E402

EVIDENCE_SCHEMA = "jc/c06-integration-evidence/1.0"
GROUPS = ("contract_breach", "fact_admission", "unknown_timeout")


class VerificationError(RuntimeError):
    """Raised when any verification step fails; no partial evidence."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed argv
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        check=False, shell=False,
    )
    if completed.returncode != 0:
        raise VerificationError(f"git {' '.join(args)} failed in {cwd}")
    return completed.stdout.strip()


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
        if path.read_bytes() != pinned.read_bytes():
            raise VerificationError(f"regenerated fixture differs from the pin: {path.name}")
        digests[path.name] = _sha256(pinned)
    return digests


def step_receipts(
    work: Path, runtime_commit: str, runtime_build_id: str,
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
    return {
        f"{group}.actual.json": _sha256(receipts / f"{group}.actual.json")
        for group in GROUPS
    }


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
    runtime_commit: str,
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
            "commit": runtime_commit,
            "tree": _git(["rev-parse", "HEAD^{tree}"], ROOT),
            "repository": "laubeing-droid/juris-calculus",
            "engine_version": __version__,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lmm-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--runtime-commit", default=None)
    parser.add_argument("--runtime-build-id", default="jc-c06-verification:1")
    args = parser.parse_args()

    runtime_commit = args.runtime_commit or _git(["rev-parse", "HEAD"], ROOT)
    work = ROOT / "work" / "jc-integration"

    lmm_identity = step_identity(args.lmm_root.resolve())
    completion, _contract, extract = step_documents(args.lmm_root.resolve())
    expected_digests = step_expected(args.lmm_root.resolve(), work)
    receipt_digests = step_receipts(work, runtime_commit, args.runtime_build_id)
    checker_reports = step_checker(
        args.lmm_root.resolve(), work, runtime_commit,
    )
    if not all(
        report.get("passed") is True and report.get("blocked") is False
        for report in checker_reports
    ):
        raise VerificationError("independent checker did not accept every receipt")
    evidence = build_evidence(
        lmm_identity, completion, extract, expected_digests, receipt_digests,
        checker_reports, runtime_commit, args.runtime_build_id,
    )
    output = args.output or (work / "integration-evidence.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"integration evidence written to {output}")
    print(f"lmm subject {SUBJECT_COMMIT[:12]} run {RUN_ID}; all receipts accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
