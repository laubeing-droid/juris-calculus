"""Public package and CLI contracts that become green only at atomic V4 cutover."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_package_root_exports_only_the_v4_facade() -> None:
    import compiler_core

    exported = set(getattr(compiler_core, "__all__", ()))
    assert {
        "JCClient",
        "ApplicationV4Error",
        "AuditBundleV4Error",
        "CaseRequestV4",
        "ContentRefV4",
        "EvaluationEnvelopeV4",
        "ReplayResultV4",
        "ResourceLimitsV4",
        "RunCapabilityV4",
        "VerifiedAuditBundleV4",
        "__version__",
    } <= exported
    assert not {
        "AuditBundle",
        "CaseRequest",
        "PackVerification",
        "evaluate_registered_case",
    }.intersection(exported)


def test_package_cli_and_runtime_share_the_v4_version() -> None:
    import compiler_core
    from compiler_core.version import __version__

    assert __version__.startswith("4.")
    assert compiler_core.__version__ == __version__
    completed = subprocess.run(
        [sys.executable, "-B", "-m", "compiler_core.cli", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == f"jc {__version__}"
    assert completed.stderr == ""


def test_parallel_v3_w1b_and_compat_runtime_imports_are_absent() -> None:
    forbidden = (
        "compiler_core.compat_v3_v4",
        "compiler_core.contracts_v4",
        "compiler_core.legal_ir_v3",
        "compiler_core.source_service_v2",
        "compiler_core.fact_admission_v1",
        "compiler_core.backend_router_v1",
        "compiler_core.certificate_v1",
        "compiler_core.argumentation_v2",
    )
    assert all(importlib.util.find_spec(name) is None for name in forbidden)


def test_cli_client_and_mcp_sources_are_v4_only() -> None:
    sources = {
        path: _source(path)
        for path in (
            "compiler_core/cli.py",
            "compiler_core/client.py",
            "compiler_core/mcp.py",
            "mcp_server.py",
        )
    }
    joined = "\n".join(sources.values())
    assert "ApplicationV4" in joined
    assert "CaseRequestV4" in joined
    assert "evaluate_registered_case" not in joined
    assert "addons.workbuddy_mcp" not in joined
    assert "compat_v3_v4" not in joined


def test_cli_exit_codes_are_bound_to_strict_v4_admission() -> None:
    from compiler_core import cli

    source = _source("compiler_core/cli.py")
    assert "CaseRequestV4" in source and "ApplicationV4" in source
    assert {
        "EXIT_OK": cli.EXIT_OK,
        "EXIT_INPUT_ERROR": cli.EXIT_INPUT_ERROR,
        "EXIT_ADMISSION_BLOCKED": cli.EXIT_ADMISSION_BLOCKED,
        "EXIT_ENGINE_ERROR": cli.EXIT_ENGINE_ERROR,
        "EXIT_REPLAY_MISMATCH": cli.EXIT_REPLAY_MISMATCH,
        "EXIT_OPTIONAL_COMPONENT_MISSING": cli.EXIT_OPTIONAL_COMPONENT_MISSING,
    } == {
        "EXIT_OK": 0,
        "EXIT_INPUT_ERROR": 2,
        "EXIT_ADMISSION_BLOCKED": 3,
        "EXIT_ENGINE_ERROR": 4,
        "EXIT_REPLAY_MISMATCH": 5,
        "EXIT_OPTIONAL_COMPONENT_MISSING": 6,
    }
