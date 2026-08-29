from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from tests.conftest import ProductionMaterial
from tests.formal_e2e.test_local_production_chain import production_bundle, runtime_config


ROOT = Path(__file__).resolve().parents[2]


def _messages(bundle) -> str:
    values = (
        {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        },
        {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "jc_evaluate", "arguments": {"case_bundle": bundle.to_dict()}},
        },
    )
    return "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in values)


def test_stdio_uses_production_factory_and_case_bundle(
    tmp_path: Path, production_material: ProductionMaterial,
) -> None:
    config = runtime_config(tmp_path / "runtime.json", tmp_path / "state", production_material)
    bundle = production_bundle(15, material=production_material)
    completed = subprocess.run(
        [sys.executable, "-B", "mcp_server.py"], cwd=ROOT,
        input=_messages(bundle), capture_output=True, text=True,
        encoding="utf-8", timeout=30, check=False,
        env={
            **os.environ,
            "JC_RUNTIME_FACTORY": "compiler_core.production_runtime",
            "JC_PRODUCTION_CONFIG": str(config),
        },
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    tool = responses[1]["result"]
    assert completed.returncode == 0
    assert completed.stderr == ""
    assert tool["isError"] is False
    assert tool["structuredContent"]["result"]["decision_status"] == "accepted_formal_result"


def test_stdio_factory_failure_exits_nonzero_without_protocol_output() -> None:
    completed = subprocess.run(
        [sys.executable, "-B", "mcp_server.py"], cwd=ROOT,
        input="", capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "JC_RUNTIME_FACTORY": "missing_runtime_factory"},
        timeout=20, check=False,
    )
    assert completed.returncode != 0
    assert completed.stdout == ""
