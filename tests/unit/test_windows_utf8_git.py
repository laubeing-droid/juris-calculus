"""Windows Chinese-path regression for every Git and subprocess boundary.

Git emits tracked paths as UTF-8 bytes. Any helper that decodes child output
with the Windows locale code page (GBK on Chinese systems) corrupts Chinese
file names or raises UnicodeDecodeError in a reader thread. The runner's
process helpers decode strictly as UTF-8; these tests prove it on a real
repository whose path and tracked file names contain Chinese.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.remediation.process import (
    child_environment,
    expand_argv,
    git_text,
    git_tracked_paths,
    run_command,
)


def test_process_helpers_decode_chinese_repo_paths(tmp_path: Path) -> None:
    repo = tmp_path / "中文仓库"
    repo.mkdir()
    tracked = [
        "普通文件.py",
        "目录一/中文文件名.md",
        "目录二/深一层/规则-民法典第一条.yaml",
    ]
    for relative in tracked:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes("内容\n".encode("utf-8"))
    env = child_environment()
    for arguments in (
        ["git", "init"],
        ["git", "add", "-A"],
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-m", "中文提交"],
    ):
        completed = subprocess.run(arguments, cwd=repo, capture_output=True, env=env)
        assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")

    assert git_tracked_paths(repo) == sorted(tracked)
    assert git_tracked_paths(repo, "*.md") == ["目录一/中文文件名.md"]
    status = git_text(repo, "status", "--porcelain=v1", "--untracked-files=all")
    assert status == ""


def test_run_command_strict_utf8_stdout_and_stderr(tmp_path: Path) -> None:
    code = (
        "import sys; "
        "sys.stdout.write('中文输出-民法典第一条\\n'); "
        "sys.stderr.write('中文诊断\\n'); "
        "sys.exit(0)"
    )
    result = run_command(
        [sys.executable, "-B", "-c", code], cwd=tmp_path, timeout_seconds=60,
    )
    assert result.passed
    assert result.stdout.replace("\r\n", "\n") == "中文输出-民法典第一条\n"
    assert result.stderr.replace("\r\n", "\n") == "中文诊断\n"


def test_run_command_reports_timeout_and_missing_executable(tmp_path: Path) -> None:
    hung = run_command(
        [sys.executable, "-B", "-c", "import time; time.sleep(30)"],
        cwd=tmp_path, timeout_seconds=1,
    )
    assert hung.timed_out and not hung.passed

    missing = run_command(
        ["jc-definitely-missing-executable", "--version"],
        cwd=tmp_path, timeout_seconds=30,
    )
    assert missing.exit_code == 127 and not missing.passed


def test_expand_argv_placeholders(tmp_path: Path) -> None:
    expanded = expand_argv(
        ("{python}", "-B", "{root}", "{temp}", "工具"),
        python="py.exe", root=str(tmp_path), temp="D:/jcv4-test",
    )
    assert expanded == ["py.exe", "-B", str(tmp_path), "D:/jcv4-test", "工具"]
