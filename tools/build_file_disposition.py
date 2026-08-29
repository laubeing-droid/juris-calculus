#!/usr/bin/env python3
"""Generate remediation/v4/file-disposition.json from current facts only.

Every tracked Python file is bound to its module-authority class and
production-wheel flag. No legacy Markdown audit, no frozen corpus
fingerprints, and no old task identifiers are consulted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.remediation.process import git_tracked_paths

OUT = ROOT / "remediation" / "v4" / "file-disposition.json"
POLICY = ROOT / "docs" / "architecture" / "module-authority.json"
SCHEMA_VERSION = "jc/file-disposition/2.0"


def build_document(root: Path = ROOT) -> dict[str, object]:
    policy = json.loads((root / "docs/architecture/module-authority.json").read_text(encoding="utf-8"))
    classes = policy["classes"]
    exact = {
        rule["path"].replace("\\", "/"): rule["class"]
        for rule in policy.get("path_rules", [])
    }
    prefixes = sorted(
        ((rule["prefix"], rule["class"]) for rule in policy.get("prefix_rules", [])),
        key=lambda item: (-len(item[0]), item[0]),
    )

    def classify(path: str) -> str:
        if path in exact:
            return exact[path]
        for prefix, authority_class in prefixes:
            if path.startswith(prefix):
                return authority_class
        raise RuntimeError(f"module-authority does not classify: {path}")

    rows: list[dict[str, object]] = []
    for path in git_tracked_paths(root, "*.py"):
        authority_class = classify(path)
        rows.append({
            "path": path,
            "authority_class": authority_class,
            "production_wheel": bool(classes[authority_class].get("production_wheel")),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "tracked_files": "git ls-files -z -- *.py (core.quotepath=false, UTF-8)",
            "authority_policy": "docs/architecture/module-authority.json",
        },
        "count": len(rows),
        "paths": rows,
    }


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    ).encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the committed file instead of rewriting it")
    args = parser.parse_args(argv)
    document = build_document(ROOT)
    encoded = canonical_bytes(document)
    if args.check:
        if not OUT.is_file():
            print("file-disposition.json is missing", file=sys.stderr)
            return 1
        if OUT.read_bytes() != encoded:
            print(
                "file-disposition.json drifted from git tracked python files and "
                "module-authority; regenerate it",
                file=sys.stderr,
            )
            return 1
        print(f"file-disposition OK: {document['count']} tracked python files")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(encoded)
    print(f"file-disposition written: {document['count']} tracked python files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
