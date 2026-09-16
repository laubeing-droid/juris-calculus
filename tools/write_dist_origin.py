#!/usr/bin/env python3
"""Write the dist origin manifest for a built juris_calculus wheel.

JC-03 installed-lane identity honesty: an installed artifact must be
verifiable against the source producer it was built from. This tool
records, next to the wheel, the source commit/tree and worktree
dirtiness observed at build time plus the wheel and RECORD digests. The
installed verification lane consumes exactly this manifest; it never
resolves identity through a git call in some other working directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORIGIN_SCHEMA = "jc/dist-origin/1.0"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


def _git(args: list[str]) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed argv
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True,
        check=True, shell=False,
    )
    return completed.stdout.strip()


def record_digest(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        record_name = next(
            name for name in archive.namelist()
            if name.endswith(".dist-info/RECORD")
        )
        content = archive.read(record_name).replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    wheel = args.wheel.resolve()
    if not wheel.is_file():
        raise SystemExit(f"wheel is missing: {wheel}")
    commit = _git(["rev-parse", "HEAD"])
    if SHA_PATTERN.fullmatch(commit) is None:
        raise SystemExit("source HEAD is not a 40-character Git SHA")
    tree = _git(["rev-parse", "HEAD^{tree}"])
    status = subprocess.run(  # noqa: S603 - fixed argv
        ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True,
        text=True, check=True, shell=False,
    ).stdout
    dirty = sorted(line for line in status.splitlines() if line.strip())
    manifest = {
        "schema_version": ORIGIN_SCHEMA,
        "mode": "installed",
        "source_commit": commit,
        "source_tree": tree,
        "worktree_dirty_at_build": bool(dirty),
        "dirty_entries_at_build": dirty,
        "wheel": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "record_entries_sha256": record_digest(wheel),
        "written_at_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ",
        ),
    }
    output = (args.output or wheel.parent / "juris-calculus-origin.json").resolve()
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"origin manifest written to {output}")
    print(
        f"source {commit[:12]} tree {tree[:12]} dirty={bool(dirty)} "
        f"wheel {wheel.name}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
