from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WHEEL_GATE = _load("jc_w6_04_wheel_gate", "tools/wheel_gate.py")
W6_01_TESTS = _load("jc_w6_01_wheel_tests", "tests/packaging/test_wheel_gate_v4.py")
DIGEST = "sha256:" + "a" * 64
COMMAND_LABELS = (
    "create-venv",
    "install-test-lock",
    "install-wheel",
    "pip-check",
    "origin-and-retirement-probe",
    "cli-version",
    "cli-capabilities",
    "mcp-stdio-lifecycle",
    "formal-e2e",
)


def _report() -> dict[str, object]:
    return {
        "schema_version": "jc/installed-wheel-e2e/1.0",
        "status": "PASS",
        "wheel_sha256": DIGEST,
        "test_lock_sha256": DIGEST,
        "wheelhouse": {"file_count": 12, "manifest_sha256": DIGEST},
        "installed_distributions": {"count": 14, "sha256": DIGEST},
        "installed_version": "4.0.0rc1",
        "source_tree_absent": True,
        "imports_from_fresh_environment": True,
        "network_disabled_during_install_and_execution": True,
        "rejected_imports": list(WHEEL_GATE.REJECTED_IMPORTS),
        "cli_version": "jc 4.0.0rc1",
        "cli_capabilities_error": "RUNTIME_NOT_CONFIGURED",
        "mcp_server_version": "4.0.0rc1",
        "mcp_tools": [
            "jc_capabilities", "jc_evaluate", "jc_verify_run", "jc_read_artifact",
        ],
        "mcp_capabilities_error": "RUNTIME_NOT_CONFIGURED",
        "formal_e2e": {
            "tests": WHEEL_GATE.INSTALLED_TEST_CASE_COUNT,
            "skipped": 0,
            "failures": 0,
            "errors": 0,
            "case_ids_sha256": WHEEL_GATE.INSTALLED_TEST_CASE_IDS_SHA256,
            "sha256": DIGEST,
        },
        "commands": [
            {
                "label": label,
                "return_code": 6 if label == "cli-capabilities" else 0,
                "stdout_sha256": DIGEST,
                "stderr_sha256": DIGEST,
            }
            for label in COMMAND_LABELS
        ],
    }


def test_nonformal_module_injection_fails_exact_record_gate(tmp_path: Path) -> None:
    wheel = W6_01_TESTS._wheel(tmp_path, "extra")
    with pytest.raises(RuntimeError, match="wheel file set drifted"):
        WHEEL_GATE.validate_wheel(ROOT, wheel)


def test_installed_harness_contains_only_tests_fixtures_and_builder() -> None:
    assert WHEEL_GATE.INSTALLED_TEST_CASE_COUNT == 27
    assert set(WHEEL_GATE.INSTALLED_TEST_SELECTORS) == {
        "tests/formal_e2e/test_positive_vertical_slice.py",
        "tests/formal_e2e/test_three_entrypoint_error_matrix.py::"
        "test_canonical_result_matrix_across_cli_client_and_stdio_mcp",
        "tests/formal_e2e/test_three_entrypoint_error_matrix.py::"
        "test_contract_error_code_is_identical_across_entrypoints",
        "tests/formal_e2e/test_three_entrypoint_error_matrix.py::"
        "test_storage_error_is_typed_retryable_redacted_and_uncommitted",
        "tests/security/test_vertical_slice_attacks.py",
        "tests/storage_chaos/test_vertical_slice_recovery.py",
        "tests/formal_e2e/test_installed_production.py::"
        "test_installed_required_suites_have_zero_skip_or_xfail",
    }
    assert not any(
        path.startswith(("compiler_core/", "configs/", "schemas/"))
        for path in WHEEL_GATE.INSTALLED_HARNESS_PATHS
    )
    assert WHEEL_GATE.REJECTED_IMPORTS == (
        "addons",
        "pipeline",
        "compiler_core.adapter_base",
        "compiler_core.analysis",
        "compiler_core.compat_v3_v4",
        "compiler_core.contracts_v4",
        "schemas.w1b",
    )


def test_complete_installed_wheel_report_is_accepted() -> None:
    assert WHEEL_GATE.validate_installed_e2e_report(
        _report(), wheel_digest=DIGEST, lock_digest=DIGEST,
    ) == []


@pytest.mark.parametrize(
    "mutation",
    ("wheel", "import", "cli", "junit", "command"),
)
def test_installed_wheel_evidence_mutations_fail_closed(mutation: str) -> None:
    report = copy.deepcopy(_report())
    if mutation == "wheel":
        report["wheel_sha256"] = "sha256:" + "b" * 64
    elif mutation == "import":
        report["imports_from_fresh_environment"] = False
    elif mutation == "cli":
        report["cli_capabilities_error"] = "UNKNOWN"
    elif mutation == "junit":
        report["formal_e2e"]["skipped"] = 1
    else:
        report["commands"][-1]["return_code"] = 1
    assert WHEEL_GATE.validate_installed_e2e_report(
        report, wheel_digest=DIGEST, lock_digest=DIGEST,
    )
