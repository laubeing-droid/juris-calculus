#!/usr/bin/env python3
"""Pin the fixed legal-math-modeling full-release subject into proofs/lmm-fullmath.

Copies the completion documents, materializes the expected refinement
fixtures from the pinned LMM subject, and extracts the bound registration
rows from BINDINGS.json. Everything is content-addressed so the cross-repo
verification can regenerate and byte-compare every pin at the fixed ref.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUBJECT_COMMIT = "5084f25e69ae27332404dc9f341a61d46ef0fc53"
SUBJECT_TREE = "184a766a2d22b1c4be31bb119e4b82b76f0be540"
RUN_ID = "34797682659"
ATTEMPT = "1"
LEAN_TOOLCHAIN_SHA256 = "54727eec5cba149c18842e6deb5c41b369d66455c93ce135d7d5347c782b2325"
LAKE_MANIFEST_SHA256 = "7230ea7eeaf37899cdf17d1c878e853e3650d276e6ec6b7f1d2f4c841952963e"
RUNTIME_REF_COMMIT = "c79e03b8d0cfed85c43cc013bf8a0b50326bc858"

# Bound registrations among the 217 mandatory ones: the rows this integration
# actually exercises, each with the reason it is bound.
BOUND_REGISTRATIONS: dict[str, str] = {
    "TARGET:C06": "checker correspondence: JC public-entry witnesses are verified by the LMM independent checker",
    "TARGET:C07": "unified correctness exit: all entry witnesses compose through the seven roots",
    "TARGET:B07": "source/version invalidation: JC caches and certificates carry the LMM subject fingerprint",
    "TARGET:F02": "identity codec: canonical digest identity for witnesses",
    "EXT:EXT02": "codec extension: structured identity carries binds across versions",
    "TARGET:F05": "horn fixpoint: formal semantics of the probe rule packs",
    "TARGET:F08": "attack compilation: exception attack structure of the probes",
    "TARGET:F09": "attack compilation edge fuel: bounded compiled checker of the probes",
    "TARGET:F10": "grounded extension profile: probe issue queries use profile=grounded",
    "TARGET:F12": "admission discipline: only admitted facts and rules reach the probes",
    "TARGET:F14": "add-only reuse: incremental channel recorded on the local runs",
    "ROOT:GENERIC_FINITE": "C07 closure root exercised by the finite probes",
    "ROOT:SYMBOLIC_EXACT": "C07 closure root cited by the exact status mapping",
    "ROOT:STATISTICAL_COMPOSITION": "C07 closure root retained by the unified exit",
    "ROOT:CIVIL": "C07 closure root for the civil contract probes",
    "ROOT:CRIMINAL": "C07 closure root declared by the unified exit",
    "ROOT:ADMINISTRATIVE": "C07 closure root declared by the unified exit",
    "ROOT:DOCUMENT_DELIVERY": "C07 closure root for byte-syntax delivery of evidence",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(args: list[str], cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lmm-root", type=Path, required=True)
    parser.add_argument(
        "--final-dir", type=Path, default=None,
        help="directory holding MATH_COMPLETION.json and EXPORT_CONTRACT.json",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "proofs" / "lmm-fullmath",
    )
    parser.add_argument("--work-dir", type=Path, default=None)
    args = parser.parse_args()

    lmm = args.lmm_root.resolve()
    head = git(["rev-parse", "HEAD"], lmm)
    tree = git(["rev-parse", "HEAD^{tree}"], lmm)
    if head != SUBJECT_COMMIT or tree != SUBJECT_TREE:
        raise SystemExit(
            f"LMM checkout {head} / {tree} is not the pinned subject "
            f"{SUBJECT_COMMIT} / {SUBJECT_TREE}"
        )
    lean_dir = lmm / "proofs" / "lean" / "juris_lean"
    toolchain = sha256_file(lean_dir / "lean-toolchain")
    manifest = sha256_file(lean_dir / "lake-manifest.json")
    if toolchain != LEAN_TOOLCHAIN_SHA256 or manifest != LAKE_MANIFEST_SHA256:
        raise SystemExit("toolchain or lake-manifest digest drifted from the pinned subject")

    final_dir = args.final_dir or (lmm / "work" / "full-math" / "FINAL")
    completion_path = final_dir / "MATH_COMPLETION.json"
    contract_path = final_dir / "EXPORT_CONTRACT.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    subject = completion["subject"]
    for key, expected in (
        ("commit", SUBJECT_COMMIT), ("tree", SUBJECT_TREE),
        ("run_id", RUN_ID), ("attempt", ATTEMPT),
        ("lean_toolchain_sha256", LEAN_TOOLCHAIN_SHA256),
        ("lake_manifest_sha256", LAKE_MANIFEST_SHA256),
    ):
        if str(subject[key]) != expected:
            raise SystemExit(f"completion subject field {key} drifted: {subject[key]!r}")
    if contract["status"] != "READY_FOR_LATER_INTEGRATION_DESIGN":
        raise SystemExit("EXPORT_CONTRACT status drifted")
    if completion["status"] != "MATH_BUILD_COMPLETE":
        raise SystemExit("MATH_COMPLETION status drifted")

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "MATH_COMPLETION.json").write_bytes(completion_path.read_bytes())
    (out / "EXPORT_CONTRACT.json").write_bytes(contract_path.read_bytes())

    work = (args.work_dir or (ROOT / "work" / "jc-integration" / "materialized-expected")).resolve()
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(lmm / "scripts" / "materialize_runtime_refinement_expected.py"),
         "--output-dir", str(work), "--lmm-commit", SUBJECT_COMMIT,
         "--runtime-fixture-dir", str(ROOT / "tests" / "fixtures" / "runtime_refinement")],
        check=True,
    )
    expected_out = out / "expected"
    expected_out.mkdir(exist_ok=True)
    expected_pins: dict[str, object] = {}
    for path in sorted(work.glob("*.expected.json")):
        (expected_out / path.name).write_bytes(path.read_bytes())
        expected_pins[path.name] = sha256_file(path)

    bindings_path = lmm / "tools" / "full_math" / "spec" / "BINDINGS.json"
    bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
    rows = bindings["bindings"]
    by_id = {row["id"]: row for row in rows}
    missing = sorted(set(BOUND_REGISTRATIONS) - set(by_id))
    if missing:
        raise SystemExit(f"bound registrations absent from BINDINGS.json: {missing}")
    extract_rows = {}
    for registration_id, reason in BOUND_REGISTRATIONS.items():
        row = by_id[registration_id]
        extract_rows[registration_id] = {
            "theorem": row["theorem"],
            "contract": row["contract"],
            "semantic_links": row["semantic_links"],
            "proof_sources": row["proof_sources"],
            "implementation_sources": row["implementation_sources"],
            "bound_because": reason,
        }
    extract = {
        "schema_version": "jc/lmm-fullmath-bindings-extract/1.0",
        "subject": {
            "commit": SUBJECT_COMMIT,
            "tree": SUBJECT_TREE,
            "repository": subject["repository"],
            "run_id": RUN_ID,
            "attempt": ATTEMPT,
            "lean_toolchain_sha256": LEAN_TOOLCHAIN_SHA256,
            "lake_manifest_sha256": LAKE_MANIFEST_SHA256,
            "runtime_ref_commit": RUNTIME_REF_COMMIT,
        },
        "source": {
            "path": "tools/full_math/spec/BINDINGS.json",
            "sha256": sha256_file(bindings_path),
            "binding_count": len(rows),
        },
        "math_completion_sha256": sha256_file(out / "MATH_COMPLETION.json"),
        "export_contract_sha256": sha256_file(out / "EXPORT_CONTRACT.json"),
        "expected_fixtures_sha256": expected_pins,
        "bound_registrations": extract_rows,
        "honest_boundaries": {
            "not_established": completion["not_established"],
            "open_external_items": [
                item["id"] for item in contract["external"]["items"]
            ],
            "claim": "JC integration claims checker correspondence and version "
                     "invalidation only; it does not close E01 empirical "
                     "validation, legal source review, or external factual truth.",
        },
    }
    (out / "BINDINGS_EXTRACT.json").write_text(
        json.dumps(extract, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
    )
    print(f"pinned {len(extract_rows)} registrations to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
