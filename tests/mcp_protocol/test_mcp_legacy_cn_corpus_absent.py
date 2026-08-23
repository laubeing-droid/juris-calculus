"""A retired legacy lookup cannot survive the W5-03 zero-tool boundary."""

from __future__ import annotations

import io
import json

from addons.workbuddy_mcp import WorkBuddyAdapter, run_stdio


def test_retired_pack_lookup_is_unavailable_and_sets_protocol_is_error(monkeypatch) -> None:
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "jc_lookup_rule",
                "arguments": {"pack_id": "cn-" + "legacy-corpus", "rule_id": "R-1"},
            },
        },
    ]
    stdin = io.StringIO("".join(json.dumps(item) + "\n" for item in requests))
    stdout = io.StringIO()
    monkeypatch.setattr("sys.stdin", stdin)
    monkeypatch.setattr("sys.stdout", stdout)

    run_stdio(WorkBuddyAdapter())

    response = json.loads(stdout.getvalue().splitlines()[1])
    assert response["result"]["isError"] is True
    assert response["result"]["structuredContent"]["error"]["code"] == "UNKNOWN_TOOL"
