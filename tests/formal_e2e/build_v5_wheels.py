"""Build A/B wheels from clean git archives and assert byte identity (V5-06).

Mirrors the CI package job locally: two ``git archive`` extractions of HEAD,
two deterministic wheel builds through tools/wheel_gate.py with a fixed
source date epoch, then a byte-for-byte comparison of the two wheels.

Usage:
    python -B tests/formal_e2e/build_v5_wheels.py --work-dir <temp-dir>
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import subprocess
import sys

SOURCE_DATE_EPOCH = 1760332800


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    work = args.work_dir
    work.mkdir(parents=True, exist_ok=True)

    tar = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"],
        capture_output=True, check=True,
    ).stdout
    wheels: list[pathlib.Path] = []
    reports: list[pathlib.Path] = []
    for name in ("src-a", "src-b"):
        source = work / name
        source.mkdir(parents=True, exist_ok=True)
        subprocess.run(["tar", "-xf", "-", "-C", str(source)], input=tar, check=True)
    for tag in ("a", "b"):
        out_dir = work / f"wheel-{tag}"
        out_dir.mkdir(parents=True, exist_ok=True)
        report = work / f"wheel-report-{tag}.json"
        subprocess.run(
            [sys.executable, "-B", "tools/wheel_gate.py",
             "--source", str(work / f"src-{tag}"),
             "--out-dir", str(out_dir),
             "--source-date-epoch", str(SOURCE_DATE_EPOCH),
             "--no-isolation",
             "--output", str(report)],
            check=True, timeout=1800,
        )
        found = sorted(out_dir.glob("*.whl"))
        if len(found) != 1:
            print(f"wheel build FAILED: expected one wheel for {tag}, found {found}")
            return 1
        wheels.append(found[0])
        reports.append(report)

    digest_a = hashlib.sha256(wheels[0].read_bytes()).hexdigest()
    digest_b = hashlib.sha256(wheels[1].read_bytes()).hexdigest()
    if digest_a != digest_b:
        print(f"wheel build FAILED: A/B wheels differ ({digest_a} != {digest_b})")
        return 1
    print(f"wheel byte-identical: {wheels[0].name} sha256:{digest_a}")
    print(f"reports: {reports[0]} {reports[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
