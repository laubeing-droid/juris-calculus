#!/usr/bin/env python3
"""Thin compatibility entry for the V4 remediation runner.

All behavior lives in tools/remediation/: the 3.0 plan loader, the generic
UTF-8 strict process boundary, the dependency-ordered runner, and the single
run log. The historical 2.0 plan (remediation/v4/tasks.json) is byte-frozen
history and is not an input of this entry point.
"""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.remediation.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
