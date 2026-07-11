"""真实子进程stdio生命周期与四工具端到端回归测试。"""

from __future__ import annotations

import json
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread

import pytest

from tests.unit.test_audit_bundle import _fixture


ROOT = Path(__file__).resolve().parents[2]
CASE_INDEX = ROOT / "tests" / "fixtures" / "synthetic_case_index.json"


def _start_server(*args: str) -> subprocess.Popen[str]:
    """启动真实适配器子进程并保留独立协议管道。"""

    return subprocess.Popen(
        [sys.executable, "mcp_server.py", *args],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _read_one_async(proc: subprocess.Popen[str]) -> Queue[str]:
    """异步读取一行，使Windows管道也能断言启动与通知保持静默。"""

    queue: Queue[str] = Queue()
    Thread(target=lambda: queue.put(proc.stdout.readline()), daemon=True).start()
    return queue


def _send(proc: subprocess.Popen[str], message: dict) -> None:
    """发送并刷新单行JSON-RPC请求。"""

    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def _initialize(proc: subprocess.Popen[str], request_id: int = 41) -> dict:
    """执行initialize并返回服务端响应。"""

    _send(proc, {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1"},
        },
    })
    return json.loads(_read_one_async(proc).get(timeout=10))


def _call(proc: subprocess.Popen[str], request_id: int, name: str, arguments: dict) -> dict:
    """调用一项MCP工具并提取structuredContent。"""

    _send(proc, {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    response = json.loads(_read_one_async(proc).get(timeout=30))
    assert response["id"] == request_id
    return response["result"]["structuredContent"]


def test_stdio_waits_for_client_and_completes_handshake() -> None:
    proc = _start_server()
    try:
        first_line = _read_one_async(proc)
        with pytest.raises(Empty):
            first_line.get(timeout=0.2)

        _send(proc, {
            "jsonrpc": "2.0",
            "id": 41,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "pytest", "version": "1"}},
        })
        initialized = json.loads(first_line.get(timeout=10))
        assert initialized["id"] == 41
        assert initialized["result"]["serverInfo"]["name"] == "juris-calculus"

        next_line = _read_one_async(proc)
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        _send(proc, {"jsonrpc": "2.0", "id": 42, "method": "tools/list", "params": {}})
        listed = json.loads(next_line.get(timeout=10))
        assert [tool["name"] for tool in listed["result"]["tools"]] == [
            "jc_evaluate", "jc_lookup_rule", "jc_analyze_strategy", "jc_analyze_similar_cases",
        ]

        _send(proc, {"jsonrpc": "2.0", "id": 43, "method": "resources/list", "params": {}})
        assert json.loads(_read_one_async(proc).get(timeout=10))["result"] == {"resources": []}
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        assert proc.returncode == 0


def test_stdio_errors_are_protocol_correct_and_server_survives() -> None:
    messages = [
        "{bad json\n",
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 4, "method": "not/a/method", "params": {}}) + "\n",
    ]
    proc = subprocess.run(
        [sys.executable, "mcp_server.py"], cwd=ROOT, input="".join(messages),
        text=True, capture_output=True, timeout=30, check=False,
    )
    responses = [json.loads(line) for line in proc.stdout.splitlines()]

    assert proc.returncode == 0
    assert [item.get("error", {}).get("code") for item in responses] == [-32700, -32002, None, -32600, -32601]
    assert responses[2]["id"] == 2


def test_stdio_calls_all_four_tools_through_one_audited_run(tmp_path) -> None:
    """真实stdio逐项调用四工具，且协议stdout只包含JSON。"""

    _, request = _fixture(tmp_path / "configs")
    input_path = tmp_path / "request.json"
    input_path.write_text(json.dumps(request.to_dict(), ensure_ascii=False), encoding="utf-8")
    proc = _start_server(
        "--development", "--config-root", str(tmp_path / "configs"), "--audit-out", str(tmp_path / "state"),
    )
    try:
        assert _initialize(proc, 51)["id"] == 51
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        evaluated = _call(proc, 52, "jc_evaluate", {"input_path": str(input_path)})
        looked_up = _call(proc, 53, "jc_lookup_rule", {"pack_id": "fixture-official", "rule_id": "R-ANCHORED"})
        strategy = _call(proc, 54, "jc_analyze_strategy", {"run_id": evaluated["run_id"]})
        similar = _call(proc, 55, "jc_analyze_similar_cases", {
            "run_id": evaluated["run_id"], "index_path": str(CASE_INDEX), "limit": 2,
        })

        assert evaluated["status"] == "ok" and evaluated["artifact_refs"]
        assert looked_up["results"][0]["rule_id"] == "R-ANCHORED"
        assert strategy["analysis_status"] == "ADVISORY"
        assert similar["analysis_status"] == "ADVISORY"
        extra_line = _read_one_async(proc)
        with pytest.raises(Empty):
            extra_line.get(timeout=0.2)
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        assert proc.returncode == 0
        assert proc.stderr.read() == ""
