from __future__ import annotations

from compiler_core.client import JCClient
from compiler_core.production_runtime import create_client
from tests.formal_e2e.test_local_production_chain import runtime_config


def test_create_client_returns_fully_configured_runtime(tmp_path, monkeypatch) -> None:
    config = runtime_config(tmp_path / "runtime.json", tmp_path / "state")
    monkeypatch.setenv("JC_PRODUCTION_CONFIG", str(config))
    client = create_client()
    assert type(client) is JCClient
    assert client._application is not None
    assert client._audit_store is not None
    assert client._evaluation_context is not None
    assert client._replay_executor is not None
    assert client._mcp_output_factory is not None
    assert client.capabilities().legal_production_ready is True
