"""真实子进程 stdio 生命周期回归测试。"""

from __future__ import annotations

import json
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
from threading import Thread

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _start_server() -> subprocess.Popen[str]:
    """启动真实 MCP 子进程，避免进程内 smoke 绕过 stdio 循环。"""
    return subprocess.Popen(
        [sys.executable, "mcp_server.py"],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _read_one_async(proc: subprocess.Popen[str]) -> Queue[str]:
    """异步读取一行，使 Windows 管道也能验证服务端没有抢跑输出。"""
    queue: Queue[str] = Queue()
    Thread(target=lambda: queue.put(proc.stdout.readline()), daemon=True).start()
    return queue


def _send(proc: subprocess.Popen[str], message: dict) -> None:
    """发送单行 JSON-RPC 消息并刷新客户端输入。"""
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()


def test_stdio_waits_for_client_and_completes_handshake():
    proc = _start_server()
    try:
        first_line = _read_one_async(proc)
        with pytest.raises(Empty):
            first_line.get(timeout=0.2)

        _send(proc, {
            "jsonrpc": "2.0",
            "id": 41,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1"},
            },
        })
        initialize = json.loads(first_line.get(timeout=10))
        assert initialize["id"] == 41
        assert initialize["result"]["serverInfo"]["name"] == "juris-calculus"

        next_line = _read_one_async(proc)
        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        _send(proc, {"jsonrpc": "2.0", "id": 42, "method": "tools/list", "params": {}})
        listed = json.loads(next_line.get(timeout=10))
        assert listed["id"] == 42
        assert len(listed["result"]["tools"]) == 33
    finally:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        proc.wait(timeout=10)
        assert proc.returncode == 0


def test_stdio_errors_are_protocol_correct_and_server_survives():
    messages = [
        "{bad json\n",
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 4, "method": "not/a/method", "params": {}}) + "\n",
    ]
    proc = subprocess.run(
        [sys.executable, "mcp_server.py"],
        cwd=ROOT,
        input="".join(messages),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    responses = [json.loads(line) for line in proc.stdout.splitlines()]

    assert proc.returncode == 0
    assert [item.get("error", {}).get("code") for item in responses] == [
        -32700,
        -32002,
        None,
        -32600,
        -32601,
    ]
    assert responses[2]["id"] == 2


def test_stdio_business_call_keeps_stdout_json_only():
    """验证首次业务调用的惰性初始化不会向协议 stdout 注入诊断文本。"""
    proc = _start_server()
    try:
        _send(proc, {
            "jsonrpc": "2.0",
            "id": 51,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "1"},
            },
        })
        initialize = json.loads(_read_one_async(proc).get(timeout=10))
        assert initialize["id"] == 51

        _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        _send(proc, {
            "jsonrpc": "2.0",
            "id": 52,
            "method": "tools/call",
            "params": {
                "name": "check_threat",
                "arguments": {"facts": ["ordinary contract facts"]},
            },
        })
        response = json.loads(_read_one_async(proc).get(timeout=90))

        assert response["id"] == 52
        assert "error" not in response
        tool_payload = json.loads(response["result"]["content"][0]["text"])
        assert tool_payload["status"] == "ok"
        assert tool_payload["payload"]["facts_checked"] == ["ordinary contract facts"]

        # 响应结束后 stdout 必须保持安静，否则下一条协议消息会被污染。
        extra_line = _read_one_async(proc)
        with pytest.raises(Empty):
            extra_line.get(timeout=0.2)
    finally:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        proc.wait(timeout=10)
        assert proc.returncode == 0
