#!/usr/bin/env python3
"""Write minimal deterministic build provenance bound to wheel and spec commits."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from compiler_core.version import __version__


SPEC_COMMIT = "a3a015941f75091c87d57aa956e712f1546dd7d4"


def main() -> int:
    """Generate provenance without embedding local absolute paths."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    wheel = args.wheel
    payload = {
        "schema_version": "1.0",
        "engine_version": __version__,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "spec_commit": SPEC_COMMIT,
        "python": platform.python_version(),
        "platform": platform.system(),
        "wheel": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "wheel_size_bytes": wheel.stat().st_size,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": args.output.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
