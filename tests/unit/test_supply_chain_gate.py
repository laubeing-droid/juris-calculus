import json
import subprocess

import pytest

from tools.supply_chain_gate import EXIT_CODES, run_supply_chain_gate


def _runner(return_code: int, stdout: str, stderr: str = ""):
    """构造纯内存 runner，确保门禁单测不会访问网络。"""

    def run(command, **kwargs):
        """模拟 subprocess.run，并校验生产代码保持非抛异常调用方式。"""

        assert kwargs == {"capture_output": True, "text": True, "check": False}
        return subprocess.CompletedProcess(command, return_code, stdout, stderr)

    return run


@pytest.mark.parametrize(
    ("return_code", "stdout", "stderr", "status", "reason", "exit_code"),
    [
        (0, '{"dependencies": []}', "", "PASS", "no_vulnerabilities", 0),
        (
            1,
            json.dumps(
                {
                    "dependencies": [
                        {"name": "demo", "version": "1.0", "vulns": [{"id": "CVE-TEST"}]}
                    ]
                }
            ),
            "Found 1 known vulnerability",
            "FAIL",
            "vulnerabilities_found",
            1,
        ),
        (1, "", "ProxyError: cannot connect to proxy", "BLOCKED", "proxy_error", 2),
        (
            1,
            "",
            "SSLError: CERTIFICATE_VERIFY_FAILED",
            "BLOCKED",
            "tls_error",
            2,
        ),
        (0, "not-json", "", "BLOCKED", "invalid_output", 2),
    ],
)
def test_gate_classifies_injected_pip_audit_results(
    return_code, stdout, stderr, status, reason, exit_code
):
    """覆盖成功、漏洞、代理、TLS 与不可解析输出五类结果。"""

    report = run_supply_chain_gate(runner=_runner(return_code, stdout, stderr))

    assert report["status"] == status
    assert report["reason"] == reason
    assert report["return_code"] == return_code
    assert report["command"][1:3] == ["-m", "pip_audit"]
    assert "--strict" in report["command"]
    assert "--disable-pip" in report["command"]
    assert report["stderr_summary"] == stderr
    assert EXIT_CODES[status] == exit_code
