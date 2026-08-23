"""W5-03 stdio proof that the retired WorkBuddy process has zero tools."""

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
    return subprocess.Popen(
        [sys.executable, "mcp_server.py"],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )


def _read_one(proc: subprocess.Popen[str]) -> Queue[str]:
    queue: Queue[str] = Queue()
    Thread(target=lambda: queue.put(proc.stdout.readline()), daemon=True).start()
    return queue


def _send(proc: subprocess.Popen[str], value: dict) -> None:
    proc.stdin.write(json.dumps(value) + "\n")
    proc.stdin.flush()


def _initialize(proc: subprocess.Popen[str], responses: Queue[str] | None = None) -> dict:
    _send(proc, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
    })
    return json.loads((responses or _read_one(proc)).get(timeout=10))


def test_stdio_starts_silent_and_lists_zero_tools() -> None:
    proc = _start_server()
    try:
        startup = _read_one(proc)
        with pytest.raises(Empty):
            startup.get(timeout=0.2)
        assert _initialize(proc, startup)["result"]["serverInfo"]["name"] == "juris-calculus"
        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert json.loads(_read_one(proc).get(timeout=10))["result"] == {"tools": []}
        _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}})
        assert json.loads(_read_one(proc).get(timeout=10))["result"] == {"resources": []}
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        assert proc.returncode == 0
        assert proc.stderr.read() == ""


def test_retired_advisory_call_is_protocol_error_and_server_survives() -> None:
    proc = _start_server()
    try:
        _initialize(proc)
        _send(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "jc_lookup_rule", "arguments": {"pack_id": "old"}},
        })
        response = json.loads(_read_one(proc).get(timeout=10))
        assert response["result"]["isError"] is True
        assert response["result"]["structuredContent"]["error"]["code"] == "UNKNOWN_TOOL"
        _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {}})
        assert json.loads(_read_one(proc).get(timeout=10))["result"] == {}
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)
        assert proc.returncode == 0
        assert proc.stderr.read() == ""


def test_stdio_protocol_errors_are_stable() -> None:
    messages = [
        "{bad json\n",
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}}) + "\n",
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "not/a/method", "params": {}}) + "\n",
    ]
    completed = subprocess.run(
        [sys.executable, "mcp_server.py"],
        cwd=ROOT,
        input="".join(messages),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]

    assert completed.returncode == 0
    assert [item.get("error", {}).get("code") for item in responses] == [
        -32700, -32002, None, -32601,
    ]
