"""Installed-wheel suite contract for formal, security, concurrency, and chaos."""

from __future__ import annotations

import ast
from pathlib import Path

from tools import wheel_gate


ROOT = Path(__file__).resolve().parents[2]


def _bypass_calls(source: str) -> list[str]:
    tree = ast.parse(source)
    bypasses: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = function.attr if isinstance(function, ast.Attribute) else (
            function.id if isinstance(function, ast.Name) else ""
        )
        if name in {"skip", "skipif", "xfail", "importorskip", "expectedFailure"}:
            bypasses.append(name)
    return bypasses


def test_installed_required_suites_have_zero_skip_or_xfail() -> None:
    selectors = wheel_gate.INSTALLED_TEST_SELECTORS
    files = {selector.split("::", 1)[0] for selector in selectors}
    suites = {Path(path).parts[1] for path in files}

    assert suites == {"formal_e2e", "security", "storage_chaos"}
    assert wheel_gate.INSTALLED_TEST_CASE_COUNT == 27
    assert "tests/security/test_vertical_slice_attacks.py" in files
    assert "tests/storage_chaos/test_vertical_slice_recovery.py" in files
    recovery_source = (ROOT / "tests/storage_chaos/test_vertical_slice_recovery.py").read_text(
        encoding="utf-8"
    )
    assert "test_concurrent_same_run_returns_one_verified_bundle" in recovery_source
    assert all((ROOT / path).is_file() for path in files)
    assert all(_bypass_calls((ROOT / path).read_text(encoding="utf-8-sig")) == [] for path in files)
