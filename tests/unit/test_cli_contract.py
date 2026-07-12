"""JC CLI函数边界、错误schema和stdout/stderr合同。"""

from __future__ import annotations

import io
import json
from pathlib import Path

import yaml

import compiler_core.cli as cli
from tests.unit.test_audit_bundle import _fixture


def _write_corpus(root: Path) -> None:
    """写入一个有来源规则和一个无来源候选，避免单测解析全量语料。"""

    target = root / "zh_CN" / "rules.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(
        yaml.safe_dump({
            "_meta": {"total": 2},
            "rules": [
                {"id": "R-VERIFIED", "premise_atoms": ["A"], "head_claim": "合同成立", "source_anchor": "LAW-1"},
                {"id": "R-CANDIDATE", "premise_atoms": ["B"], "head_claim": "合同待审"},
            ],
        }, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def test_rules_lookup_json_is_deterministic_and_discloses_candidate_status(tmp_path, monkeypatch, capsys) -> None:
    """lookup可以读候选语料，但必须显示准入状态且不向stderr写日志。"""

    _write_corpus(tmp_path)
    monkeypatch.setattr(cli, "configs_root", lambda: tmp_path)

    assert cli.main(["rules", "lookup", "合同", "--limit", "10", "--json"]) == cli.EXIT_OK
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert captured.err == ""
    assert payload["inventory"] == {
        "corpus_total": 2,
        "reasoning_eligible_total": 1,
        "candidate_only_total": 1,
    }
    assert [item["rule_id"] for item in payload["results"]] == ["R-CANDIDATE", "R-VERIFIED"]
    assert [item["admission"] for item in payload["results"]] == ["candidate_only", "reasoning_eligible"]


def test_rules_lookup_reads_explicit_utf8_file(tmp_path, monkeypatch, capsys) -> None:
    """--input只读取显式UTF-8路径，不隐式扫描当前目录。"""

    _write_corpus(tmp_path / "configs")
    query_path = tmp_path / "查询.txt"
    query_path.write_text("R-VERIFIED\n", encoding="utf-8")
    monkeypatch.setattr(cli, "configs_root", lambda: tmp_path / "configs")

    assert cli.main(["rules", "lookup", "--input", str(query_path), "--json"]) == cli.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "R-VERIFIED"
    assert [item["rule_id"] for item in payload["results"]] == ["R-VERIFIED"]


def test_expected_error_uses_stderr_machine_schema_without_traceback(tmp_path, monkeypatch, capsys) -> None:
    """输入错误固定返回2，且JSON错误包含四个稳定字段。"""

    _write_corpus(tmp_path)
    monkeypatch.setattr(cli, "configs_root", lambda: tmp_path)

    assert cli.main(["rules", "lookup", "query", "--limit", "0", "--json"]) == cli.EXIT_INPUT_ERROR
    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert captured.out == ""
    assert payload == {
        "code": "INVALID_LIMIT",
        "message": "--limit must be between 1 and 100",
        "details": {},
        "retryable": False,
    }
    assert "Traceback" not in captured.err


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


def test_evaluate_json_exposes_semantic_result_status_and_logical_artifact_refs(tmp_path, monkeypatch, capsys) -> None:
    """evaluate --json 必须稳定暴露 formal result status 且不泄漏本地路径。"""

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
    assert payload["canonical_result"]["semantic"]["result_status"] == "accepted_formal_result"
    assert all(not ref.startswith(("C:", "D:", "/")) for ref in payload["canonical_result"]["artifact_refs"])
