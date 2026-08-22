"""Package-root version identity contract for the staged V4 cutover."""

from __future__ import annotations

import ast
from pathlib import Path

import compiler_core
from compiler_core.version import __version__ as version_source


REPO = Path(__file__).resolve().parents[2]


def test_package_root_exports_v4_version() -> None:
    """W1-02 exports the sole version source; W5-CUTOVER changes its value."""

    assert compiler_core.__version__ == version_source
    assert "__version__" in compiler_core.__all__

    source = (REPO / "compiler_core" / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "compiler_core.version"
        and any(alias.name == "__version__" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert version_source not in {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
