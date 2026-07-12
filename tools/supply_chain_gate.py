"""基于 pip-audit 的 fail-closed 供应链门禁。"""

from __future__ import annotations

import json
import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


EXIT_CODES = {"PASS": 0, "FAIL": 1, "BLOCKED": 2}


def _summarize_stderr(stderr: str, limit: int = 500) -> str:
    """压缩 stderr，避免机器报告被安装器的冗长诊断淹没。"""

    summary = " ".join(stderr.split())
    return summary if len(summary) <= limit else summary[: limit - 3] + "..."


def _vulnerability_count(stdout: str) -> int | None:
    """解析 pip-audit JSON；结构不完整时返回 None 触发 fail-closed。"""

    try:
        payload: Any = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None

    dependencies = payload.get("dependencies") if isinstance(payload, dict) else payload
    if not isinstance(dependencies, list):
        return None

    count = 0
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not isinstance(dependency.get("vulns"), list):
            return None
        count += len(dependency["vulns"])
    return count


def _blocked_reason(stderr: str) -> str:
    """为常见基础设施故障给出稳定、可机读的阻断原因。"""

    normalized = stderr.lower()
    if "proxy" in normalized:
        return "proxy_error"
    if any(marker in normalized for marker in ("ssl", "tls", "certificate_verify_failed")):
        return "tls_error"
    return "audit_error"


def run_supply_chain_gate(
    requirements: str | Path = "requirements/core.lock",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """执行 pip-audit，并将结果严格归类为 PASS、FAIL 或 BLOCKED。"""

    command = [
        sys.executable,
        "-m",
        "pip_audit",
        "--requirement",
        str(requirements),
        "--format",
        "json",
        "--progress-spinner",
        "off",
        "--strict",
    ]
    try:
        completed = runner(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        return {
            "command": command,
            "status": "BLOCKED",
            "return_code": None,
            "stderr_summary": _summarize_stderr(str(exc)),
            "vulnerability_count": None,
            "reason": "execution_error",
        }

    vulnerability_count = _vulnerability_count(completed.stdout)
    # 基础设施错误比派生出的 JSON 解析错误更具体，应优先进入报告。
    blocked_reason = _blocked_reason(completed.stderr)
    if blocked_reason != "audit_error":
        reason = blocked_reason
    elif vulnerability_count is None:
        reason = "invalid_output"
    else:
        reason = "audit_error"
    report = {
        "command": command,
        "status": "BLOCKED",
        "return_code": completed.returncode,
        "stderr_summary": _summarize_stderr(completed.stderr),
        "vulnerability_count": vulnerability_count,
        "reason": reason,
    }

    # pip-audit 以 0 表示无漏洞、1 表示发现漏洞；其余组合均视为结果不可信。
    if completed.returncode == 0 and vulnerability_count == 0:
        report.update(status="PASS", reason="no_vulnerabilities")
    elif completed.returncode == 1 and vulnerability_count and vulnerability_count > 0:
        report.update(status="FAIL", reason="vulnerabilities_found")
    return report


def main(argv: list[str] | None = None) -> int:
    """输出单个 JSON 报告，并返回与门禁状态对应的进程退出码。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", default="requirements/core.lock")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_supply_chain_gate(args.requirements)
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
