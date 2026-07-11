"""默认core与可选WorkBuddy协议面的最小烟雾测试。"""

from pathlib import Path

from addons.workbuddy_mcp import TOOL_NAMES, manifest_document, run_smoke


ROOT = Path(__file__).resolve().parents[1]


def test_default_distribution_registers_only_the_jc_cli() -> None:
    """默认wheel不得自动注册MCP server或任何旧工具入口。"""

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '[project.scripts]\njc = "compiler_core.cli:main"' in pyproject
    assert "jc-workbuddy" not in pyproject
    assert "mcp_server" not in pyproject


def test_optional_adapter_smoke_is_explicitly_not_readiness(capsys) -> None:
    """进程内smoke只核对协议面，不宣称WorkBuddy或stdio已就绪。"""

    assert run_smoke(ROOT / "mcp_manifest.json") == 0
    output = capsys.readouterr().out

    assert '"readiness_claimed": false' in output
    assert tuple(manifest_document(ROOT / "mcp_manifest.json")["tools"]) == TOOL_NAMES
