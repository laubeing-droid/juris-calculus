"""W1 Gate：CLI、JCClient、MCP 对同一请求的结果、错误码和审计一致性。

覆盖方案 §7 Gate 与 §15 真实验收第 3 条：
- 同一 development fixture 经 CLI 与 MCP(stdio) 产生相同 run identity、
  canonical 语义结果和 bundle digest（各自独立 state root）；
- 正式默认包 blocked 时，CLI exit code/错误码、JCClient 异常码、
  MCP 工具错误码完全一致；
- 三入口均收敛于同一 application 审计链（verify_audit_bundle 复核）。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from compiler_core.audit_bundle import verify_audit_bundle
from compiler_core.client import JCClient
from compiler_core.contracts import CaseRequest, SCHEMA_VERSION
from compiler_core.resources import configs_root
from compiler_core.rule_packs import RulePackError, RulePackRegistry
from compiler_core.types import FactTrustStatus, LegalFact
from tests.unit.test_audit_bundle import _fixture
from tests.unit.test_mcp_stdio_protocol import _call, _initialize, _send, _start_server


ROOT = Path(__file__).resolve().parents[2]


def _run_cli(*arguments: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "compiler_core.cli", *arguments],
        cwd=ROOT,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )


def test_cli_and_mcp_same_fixture_same_canonical_result(tmp_path) -> None:
    """同一 fixture 经 CLI 与 MCP 产生相同 run identity 与 bundle digest。"""

    _, request = _fixture(tmp_path / "configs")
    config_root = str(tmp_path / "configs")
    request_text = json.dumps(request.to_dict(), ensure_ascii=False)

    cli_state = tmp_path / "state-cli"
    evaluated_cli = _run_cli(
        "evaluate", "--input", "-", "--development",
        "--config-root", config_root, "--audit-out", str(cli_state), "--json",
        stdin=request_text,
    )
    assert evaluated_cli.returncode == 0, evaluated_cli.stderr
    cli_payload = json.loads(evaluated_cli.stdout)

    mcp_state = tmp_path / "state-mcp"
    input_path = tmp_path / "request.json"
    input_path.write_text(request_text, encoding="utf-8")
    proc = _start_server("--development", "--config-root", config_root, "--audit-out", str(mcp_state))
    try:
        assert _initialize(proc, 61)["id"] == 61
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        evaluated_mcp = _call(proc, 62, "jc_evaluate", {"input_path": str(input_path)})
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        assert proc.returncode == 0

    assert evaluated_mcp["status"] == "ok"
    assert evaluated_mcp["run_id"] == cli_payload["run_id"]
    assert evaluated_mcp["result_status"] == cli_payload["canonical_result"]["semantic"]["result_status"]

    verified_cli = verify_audit_bundle(cli_state, cli_payload["run_id"])
    verified_mcp = verify_audit_bundle(mcp_state, evaluated_mcp["run_id"])
    assert verified_cli.bundle_digest == cli_payload["bundle_digest"]
    assert verified_mcp.bundle_digest == verified_cli.bundle_digest
    assert verified_mcp.semantic_result.to_dict() == verified_cli.semantic_result.to_dict()


def test_blocked_pack_error_code_identical_across_entrypoints(tmp_path) -> None:
    """cn-official blocked 时三入口错误码一致：PACK_NOT_REASONING_READY。"""

    official = RulePackRegistry(configs_root()).verify("cn-official")
    fact = LegalFact(
        id="fact::parity",
        value=True,
        status=FactTrustStatus.VERIFIED_FACT,
        source_ids=("evidence::1",),
        human_reviewed=True,
    )
    request = CaseRequest(
        SCHEMA_VERSION, "CN", "PRC", "2026-07-11", (fact,),
        official.pack_id, official.version, official.content_digest,
    )

    cli_completed = _run_cli(
        "evaluate", "--input", "-", "--audit-out", str(tmp_path / "state-cli"), "--json",
        stdin=json.dumps(request.to_dict(), ensure_ascii=False),
    )
    assert cli_completed.returncode == 3
    cli_error = json.loads(cli_completed.stderr)

    with pytest.raises(RulePackError) as exc:
        JCClient(state_root=tmp_path / "state-client").evaluate(request)

    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request.to_dict(), ensure_ascii=False), encoding="utf-8")
    proc = _start_server("--audit-out", str(tmp_path / "state-mcp"))
    try:
        assert _initialize(proc, 71)["id"] == 71
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        mcp_payload = _call(proc, 72, "jc_evaluate", {"input_path": str(input_path)})
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        assert proc.returncode == 0

    assert cli_error["code"] == "PACK_NOT_REASONING_READY"
    assert exc.value.code == "PACK_NOT_REASONING_READY"
    assert mcp_payload["status"] == "error"
    assert mcp_payload["error"]["code"] == "PACK_NOT_REASONING_READY"
