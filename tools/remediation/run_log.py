"""Single JSON run log for one remediation execution.

The runner writes exactly one log per run and never reads previous logs back:
an interrupted run is resumed by rerunning it, not by repairing old artifacts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "jc/remediation-run-log/1.0"
TAIL_CHARS = 2000


def digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def command_record(result: Any, *, expected_exit_codes: tuple[int, ...]) -> dict[str, Any]:
    accepted = (
        result.utf8_valid
        and not result.timed_out
        and result.exit_code in expected_exit_codes
    )
    return {
        "argv": list(result.argv),
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "utf8_valid": result.utf8_valid,
        "accepted": accepted,
        "expected_exit_codes": list(expected_exit_codes),
        "duration_seconds": round(result.duration_seconds, 3),
        "stdout_sha256": digest_text(result.stdout),
        "stderr_sha256": digest_text(result.stderr),
        "stdout_tail": result.stdout[-TAIL_CHARS:],
        "stderr_tail": result.stderr[-TAIL_CHARS:],
    }


def write_run_log(path: Path, payload: dict[str, Any]) -> Path:
    """Atomically write one run log as strict UTF-8 JSON."""

    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("run log schema_version drifted")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(encoded, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
