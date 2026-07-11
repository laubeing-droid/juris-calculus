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


def test_doctor_blocks_when_cn_official_is_empty() -> None:
    """doctor必须如实报告official空包，不能回退legacy语料。"""

    completed = _run("doctor", "--json")
    payload = json.loads(completed.stdout)

    assert completed.returncode == 3
    assert completed.stderr == ""
    assert payload["status"] == "blocked"
    assert payload["python_supported"] is True
    assert payload["checks"]["cn_official"]["reasoning_ready"] is False
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


def test_packs_list_is_deterministic_and_ignores_implicit_environment_override(monkeypatch) -> None:
    """环境变量本身不得静默替换bundled manifests。"""

    monkeypatch.setenv("JURIS_CONFIG_DIR", str(ROOT / "does-not-exist"))
    completed = _run("packs", "list", "--json")
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert payload["pack_count"] == 5
    assert payload["development_override"] is False
    assert [item["pack_id"] for item in payload["packs"]] == sorted(
        item["pack_id"] for item in payload["packs"]
    )


def test_empty_official_pack_is_blocked_and_missing_pack_is_exit_6() -> None:
    """空official返回3，未安装可选pack返回6，二者均不伪装成功。"""

    official = _run("packs", "verify", "cn-official", "--json")
    missing = _run("packs", "verify", "us-state-ca-official", "--json")

    assert official.returncode == 3
    assert official.stderr == ""
    assert json.loads(official.stdout)["status"] == "blocked"
    assert missing.returncode == 6
    assert missing.stdout == ""
    assert json.loads(missing.stderr)["code"] == "PACK_NOT_INSTALLED"
