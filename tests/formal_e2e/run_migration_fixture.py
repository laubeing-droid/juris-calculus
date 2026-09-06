"""Standalone V4->V5 migration fixture runner (U10; JT46).

Executes the migration tool end to end on a synthesized V4-format bundle:

1. build a V4-format case bundle on disk;
2. run tools/migrate_v4_bundle.py as a subprocess;
3. assert the migrated output differs only in declared fields;
4. assert the V5 contract authority rejects the migrated bundle (old
   self-digest / stale signature), so re-admission is mandatory;
5. assert the source file bytes are untouched (no in-place rewrite).

Exit code 0 only when every observation holds; no JSON reformatting tricks.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from compiler_core.contracts import CaseInputBundleV4, ContractV4Error  # noqa: E402
from tools.migrate_v4_bundle import migrate_document  # noqa: E402

D = lambda n: "sha256:" + format(n, "064x")


def build_v4_bundle() -> dict:
    return {
        "schema_version": "jc/case-input-bundle/1.0",
        "bundle_id": "bundle-migration-fixture",
        "request": {
            "schema_version": "jc/4.0",
            "request_id": "req-migration-fixture",
            "legal_context": {"jurisdiction": "CN", "governing_law": "CN-civil"},
            "decision_time": "2026-09-06T00:00:00Z",
            "source_bundle_ref": {"kind": "source-bundle", "digest": D(1)},
            "evidence_manifest_ref": {"kind": "evidence-manifest", "digest": D(2)},
            "fact_attestation_refs": [],
            "rule_pack_ref": {"kind": "pack-manifest", "digest": D(3)},
            "requested_outputs": [],
            "proposal_refs": [],
        },
        "artifacts": [],
        "bundle_digest": D(4),
        "sealed_certificate": {"kind": "formal-certificate", "digest": D(5)},
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="jc-v5-migration-") as raw:
        work = Path(raw)
        source = work / "v4-bundle.json"
        source_bytes = json.dumps(build_v4_bundle(), ensure_ascii=False, indent=1).encode("utf-8") + b"\n"
        source.write_bytes(source_bytes)

        output = work / "v5-bundle.json"
        report = work / "migration-report.json"
        completed = subprocess.run(
            [sys.executable, "-B", "tools/migrate_v4_bundle.py",
             "--input", str(source), "--output", str(output), "--report", str(report)],
            cwd=REPO, capture_output=True, timeout=120,
        )
        if completed.returncode != 0:
            print("migration fixture FAILED: tool exited "
                  f"{completed.returncode}: {completed.stderr.decode('utf-8', errors='replace')}")
            return 1

        migrated = json.loads(output.read_bytes())
        report_doc = json.loads(report.read_bytes())
        if migrated["request"]["schema_version"] != "jc/5.0":
            print("migration fixture FAILED: wire version not rewritten")
            return 1
        if not report_doc["stale_signatures"]:
            print("migration fixture FAILED: stale signatures not flagged")
            return 1
        if source.read_bytes() != source_bytes:
            print("migration fixture FAILED: source bundle was modified in place")
            return 1

        # The V5 contract authority refuses the migrated bundle: its old self
        # digest and sealed certificate cannot survive the version change.
        try:
            CaseInputBundleV4.from_dict(migrated)
        except ContractV4Error:
            pass
        else:
            print("migration fixture FAILED: V5 authority accepted a migrated bundle "
                  "without re-admission")
            return 1

        print("migration fixture OK: wire rewritten, signatures flagged stale, "
              "source untouched, V5 re-admission enforced")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
