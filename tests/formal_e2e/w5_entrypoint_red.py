"""Atomic three-entrypoint V4 sink and derived-trust obligations."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_PATHS = (
    "compiler_core/cli.py",
    "compiler_core/client.py",
    "compiler_core/mcp.py",
    "mcp_server.py",
)


def _sources() -> dict[str, str]:
    return {
        path: (ROOT / path).read_text(encoding="utf-8") for path in ADAPTER_PATHS
    }


def _loaded_names(source: str) -> set[str]:
    tree = ast.parse(source)
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def test_public_entrypoints_reject_v3_route() -> None:
    sources = _sources()
    joined = "\n".join(sources.values())
    assert "ApplicationV4" in joined
    for marker in (
        "evaluate_registered_case",
        "compat_v3_v4",
        "legal_ir_v3",
        "addons.workbuddy_mcp",
    ):
        assert marker not in joined


def test_vertical_slice_derives_trust_instead_of_accepting_caller_pass() -> None:
    sources = _sources()
    loaded = set().union(*(_loaded_names(source) for source in sources.values()))
    assert "ApplicationV4" in loaded
    assert not {
        "AuditBundle",
        "CaseRequest",
        "PackVerification",
        "evaluate_registered_case",
    }.intersection(loaded)
    joined = "\n".join(sources.values())
    assert '"PASS"' not in joined
    assert "formal_kernel_used" not in joined


def test_cli_client_and_mcp_share_one_application_v4_sink() -> None:
    sources = _sources()
    joined = "\n".join(sources.values())
    assert joined.count("ApplicationV4") >= 1
    assert joined.count(".evaluate(") >= 1
    for path, source in sources.items():
        assert "ApplicationV4" in source or "JCClient" in source, path
