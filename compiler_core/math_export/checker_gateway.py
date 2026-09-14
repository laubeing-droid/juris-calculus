"""Fail-closed subprocess gateway to the LMM independent checker.

The gateway runs the reference checker of the pinned legal-math-modeling
checkout in its own interpreter and working directory. It never imports
JC code into that process, and it never calls the JC main solver: the
checker's acceptance depends only on the expected fixture materialized
from the pinned subject and the receipt produced by the JC public entry.
A non-passing report raises; there is no lenient mode.

All invocations use a fixed argument-vector form (``shell=False``) with
``sys.executable`` and repo-internal scripts; no shell is ever involved.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


class IndependentCheckerError(RuntimeError):
    """Raised when the independent checker rejects or cannot be executed."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def materialize_expected(
    lmm_root: Path,
    output_dir: Path,
    *,
    lmm_commit: str,
    runtime_fixture_dir: Path | None = None,
) -> list[Path]:
    """Materialize the subject-bound expected fixtures (LMM party 1)."""

    script = lmm_root / "scripts" / "materialize_runtime_refinement_expected.py"
    if not script.is_file():
        raise IndependentCheckerError(
            "CHECKER_SCRIPT_MISSING", str(script),
        )
    if runtime_fixture_dir is None:
        argv = (
            sys.executable, str(script),
            "--output-dir", str(output_dir),
            "--lmm-commit", lmm_commit,
        )
    else:
        argv = (
            sys.executable, str(script),
            "--output-dir", str(output_dir),
            "--lmm-commit", lmm_commit,
            "--runtime-fixture-dir", str(runtime_fixture_dir),
        )
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        argv, cwd=str(lmm_root), check=False, shell=False,
    )
    if completed.returncode != 0:
        raise IndependentCheckerError(
            "CHECKER_MATERIALIZATION_FAILED",
            f"materializer exited with {completed.returncode}",
        )
    return sorted(output_dir.glob("*.expected.json"))


def verify_receipt(
    lmm_root: Path,
    expected: Path,
    actual: Path,
    *,
    lmm_commit: str,
    runtime_commit: str | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    """Run the independent verifier (LMM party 3) on one receipt.

    Returns the parsed report when it passes; raises
    :class:`IndependentCheckerError` for every other outcome, including
    blocked reports, unknown schemas, and identity mismatches.
    """

    script = lmm_root / "scripts" / "verify_runtime_refinement_receipt.py"
    if not script.is_file():
        raise IndependentCheckerError("CHECKER_SCRIPT_MISSING", str(script))
    argv_tail: tuple[str, ...] = ()
    if runtime_commit is not None:
        argv_tail = argv_tail + (
            "--expected-runtime-commit", runtime_commit,
        )
    if output is not None:
        argv_tail = argv_tail + ("--output", str(output))
    argv = (
        sys.executable, str(script),
        "--expected", str(expected),
        "--actual", str(actual),
        "--expected-lmm-commit", lmm_commit,
    ) + argv_tail
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        argv, cwd=str(lmm_root), capture_output=True, text=True,
        check=False, shell=False,
    )
    if completed.returncode != 0:
        raise IndependentCheckerError(
            "CHECKER_REJECTED",
            (completed.stderr.strip() or completed.stdout.strip())[:800],
        )
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise IndependentCheckerError(
            "CHECKER_REPORT_UNREADABLE", str(exc),
        ) from exc
    if report.get("passed") is not True or report.get("blocked"):
        raise IndependentCheckerError(
            "CHECKER_REPORT_NOT_PASSING",
            json.dumps(report.get("error_codes", [])),
        )
    return report
