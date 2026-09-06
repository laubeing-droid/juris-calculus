"""Offline V4 -> V5 case-bundle migration (SOURCE_TOOL; U10).

Only mechanical, explicitly-reported field conversions happen here:

- wire schema_version strings ``jc/4.0`` become ``jc/5.0``;
- every changed field is listed in a structured diff report;
- every signature in the bundle is flagged STALE_SIGNATURE: the signed body
  changed, so the old signature can never be accepted by the V5 admission
  path and re-admission through the formal gates is mandatory;
- rule-pack, fact-attestation and certificate references are carried as
  references only; this tool never re-signs, never re-admits, never rewrites
  an old artifact in place, and never upgrades a candidate to an admitted
  state.

Usage:
    python -B tools/migrate_v4_bundle.py --input old-bundle.json \
        --output work/migrated-bundle.json --report work/migration-report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

V4_WIRE = "jc/4.0"
V5_WIRE = "jc/5.0"
CASE_BUNDLE_SCHEMA = "jc/case-input-bundle/1.0"
SCHEMA_VERSION_FIELDS = {"schema_version", "engine_api"}


class MigrationError(ValueError):
    """Stable error for migration refusal; never a silent rewrite."""


def migrate_document(document: object) -> tuple[dict, dict]:
    """Return (migrated document, migration report) without touching the input."""

    if not isinstance(document, dict):
        raise MigrationError("MIGRATION_INPUT", "input must be a JSON object")
    changes: list[dict[str, object]] = []
    stale_signatures: list[str] = []

    def walk(node: object, path: str) -> object:
        if isinstance(node, dict):
            migrated: dict[str, object] = {}
            for key, value in node.items():
                child_path = f"{path}/{key}"
                if key in SCHEMA_VERSION_FIELDS and value == V4_WIRE:
                    migrated[key] = V5_WIRE
                    changes.append({"path": child_path, "from": V4_WIRE, "to": V5_WIRE})
                elif key == "schema_version" and isinstance(value, str) and value.startswith("jc/") and value != V4_WIRE and value != V5_WIRE:
                    # sub-schema versions (case-input-bundle, rule packs, receipts)
                    # are format versions, not wire versions; they carry over
                    migrated[key] = value
                else:
                    migrated[key] = walk(value, child_path)
            for signature_key in ("signature", "service_signature", "sealed_certificate"):
                if signature_key in node:
                    stale_signatures.append(f"{path}/{signature_key}")
            return migrated
        if isinstance(node, list):
            return [walk(item, f"{path}[{index}]") for index, item in enumerate(node)]
        return node

    migrated_document = walk(document, "")
    report = {
        "schema_version": "jc/v4-to-v5-migration-report/1.0",
        "tool": "tools/migrate_v4_bundle.py",
        "source_class": "SOURCE_TOOL",
        "changed_fields": changes,
        "stale_signatures": stale_signatures,
        "obligations": [
            "re-admission is mandatory: every stale signature must be re-issued "
            "through V5 admission; the old signature can never validate the "
            "migrated body",
            "fact attestations and rule packs must pass V5 admission again; "
            "migration does not grant admission or authority",
            "old certificates stay sealed with the old artifacts and are never "
            "reused as V5 evidence",
        ],
        "not_claims": [
            "this tool does not sign, admit, verify, or certify anything",
        ],
    }
    return migrated_document, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--wire-version", choices=(V5_WIRE,), default=V5_WIRE)
    args = parser.parse_args()

    raw = args.input.read_bytes()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        print(f"migration refused: input is not strict UTF-8 JSON: {exc}", file=sys.stderr)
        return 2

    try:
        migrated, report = migrate_document(document)
    except MigrationError as exc:
        print(f"migration refused: {exc}", file=sys.stderr)
        return 2

    report["source_bytes"] = len(raw)
    report["source_sha256"] = "sha256:" + __import__("hashlib").sha256(raw).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(
        json.dumps(migrated, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
    args.report.write_bytes(
        json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8") + b"\n")
    print(
        f"migrated {args.input} -> {args.output}; "
        f"{len(report['changed_fields'])} field changes, "
        f"{len(report['stale_signatures'])} stale signatures; "
        "re-admission required"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
