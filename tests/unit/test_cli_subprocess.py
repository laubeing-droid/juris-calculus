"""真实Python子进程下的CLI framing、stdin和退出码门禁。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def _run(*arguments: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """从仓库根启动模块CLI并完整捕获协议流。"""

    return subprocess.run(
        [sys.executable, "-m", "compiler_core.cli", *arguments],
        cwd=ROOT,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )


def test_doctor_json_stdout_is_single_machine_document() -> None:
    """doctor JSON模式stdout只有一个JSON文档且不泄漏绝对路径。"""

    completed = _run("doctor", "--json")
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert payload["status"] == "ok"
    assert payload["python_supported"] is True
    assert "D:\\" not in completed.stdout
    assert "C:\\" not in completed.stdout


def test_rules_lookup_accepts_stdin_and_returns_candidate_corpus_result() -> None:
    """--input -消费stdin，且不把legacy语料描述成official pack。"""

    completed = _run("rules", "lookup", "--input", "-", "--limit", "1", "--json", stdin="PC-001\n")
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert payload["pack_id"] == "cn-legacy-corpus"
    assert payload["match_count"] >= 1
    assert payload["results"][0]["rule_id"] == "PC-001"


def test_json_usage_error_has_exit_2_and_no_stdout() -> None:
    """缺少查询时argparse也必须遵守机器错误schema。"""

    completed = _run("rules", "lookup", "--json")
    payload = json.loads(completed.stderr)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert payload["code"] == "CLI_USAGE_ERROR"
    assert set(payload) == {"code", "message", "details", "retryable"}
    assert "Traceback" not in completed.stderr
