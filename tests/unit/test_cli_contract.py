"""JC CLI函数边界、错误schema和stdout/stderr合同。"""

from __future__ import annotations

import io
import json

import compiler_core.cli as cli
from tests.unit.test_audit_bundle import _fixture


def test_internal_error_is_redacted(monkeypatch, capsys) -> None:
    """意外异常映射为退出码4，禁止把异常文本和traceback写到输出。"""

    def explode(_args):
        raise RuntimeError("private absolute path D:/client/case")

    class BrokenParser:
        """只为触发main的意外异常保护层提供固定参数。"""

        @staticmethod
        def parse_args(_argv):
            return cli.argparse.Namespace(handler=explode, json_output=True)

    monkeypatch.setattr(cli, "build_parser", BrokenParser)

    assert cli.main(["doctor", "--json"]) == cli.EXIT_ENGINE_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "CLI_INTERNAL_ERROR"
    assert "private absolute path" not in captured.err


def test_development_evaluate_json_exposes_review_status_and_logical_refs(tmp_path, monkeypatch, capsys) -> None:
    """development evaluate必须稳定降级且不泄漏本地路径。"""

    _, request = _fixture(tmp_path / "configs")
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(json.dumps(request.to_dict(), ensure_ascii=False)))

    exit_code = cli.main([
        "evaluate",
        "--input", "-",
        "--development",
        "--config-root", str(tmp_path / "configs"),
        "--audit-out", str(tmp_path / "state"),
        "--json",
    ])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == cli.EXIT_OK
    semantic = payload["canonical_result"]["semantic"]
    assert semantic["result_status"] == "review_only_result"
    assert semantic["certificate_kind"] == "none"
    assert semantic["formal_kernel_used"] is False
    assert all(not ref.startswith(("C:", "D:", "/")) for ref in payload["canonical_result"]["artifact_refs"])
