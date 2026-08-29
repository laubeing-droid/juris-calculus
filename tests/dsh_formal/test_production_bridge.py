from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

from compiler_core.canonical_serialization import DigestV4, canonical_bytes
from compiler_core.formal_bridge import (
    FormalBridgeError, FormalBridgeV4, load_active_profile, main,
)
from compiler_core.mcp import runtime_tools_list
from compiler_core.production_runtime import ProductionRuntimeConfigV4, create_client
from tests.conftest import ProductionMaterial
from tests.formal_e2e.test_local_production_chain import production_bundle, runtime_config


def _registry(
    tmp_path: Path, material: ProductionMaterial,
    *, pin_mutation: tuple[str, object] | None = None,
) -> Path:
    config = runtime_config(tmp_path / "runtime.json", tmp_path / "state", material)
    client = create_client(ProductionRuntimeConfigV4.from_path(config))
    capabilities = client.capabilities().to_dict()
    pins = {
        field: capabilities[field]
        for field in (
            "schema_version", "engine_version", "engine_source_tree",
            "engine_build_digest", "wheel_digest", "package_digest", "lock_digest",
            "schema_digest", "tool_spec_digest", "active_pack_ref", "trust_policy_ref",
            "storage_capability_ref", "kernel_ready", "legal_production_ready",
        )
    }
    if pin_mutation is not None:
        pins[pin_mutation[0]] = pin_mutation[1]
    profile = {
        "schema_version": "jc/formal-profile/1.0",
        "profile_id": "local-production",
        "production": True,
        "loaded_by_default": False,
        "python": sys.executable,
        "module": "mcp_server",
        "cwd": str(Path.cwd()),
        "environment": {
            "JC_RUNTIME_FACTORY": "compiler_core.production_runtime",
            "JC_PRODUCTION_CONFIG": str(config),
        },
        "allowed_tools": [
            "jc_capabilities", "jc_evaluate", "jc_verify_run", "jc_read_artifact",
        ],
        "tools_list_digest": str(DigestV4.from_bytes(canonical_bytes(runtime_tools_list()))),
        "capability_pins": pins,
        "page_bytes": 97,
        "startup_timeout_seconds": 30,
        "tool_timeout_seconds": 90,
    }
    registry = {
        "schema_version": "jc/formal-profile-registry/1.0",
        "active_profile": "local-production",
        "profiles": {"local-production": profile},
    }
    path = tmp_path / "profile-registry.json"
    path.write_bytes(canonical_bytes(registry))
    return path


def test_real_stdio_production_factory_delivers_exact_certificate(
    tmp_path: Path, production_material: ProductionMaterial,
) -> None:
    bundle = production_bundle(15, material=production_material)
    profile = load_active_profile(_registry(tmp_path, production_material))
    with FormalBridgeV4(profile) as bridge:
        delivery = bridge.deliver(bundle)
    assert delivery.marker == "JC_FORMAL_VERIFIED"
    assert delivery.artifact_digest == DigestV4.from_bytes(delivery.content)
    assert len(delivery.content) > profile.page_bytes


@pytest.mark.parametrize("mutation", ("tools", "capabilities"))
def test_startup_pin_drift_fails_closed(
    tmp_path: Path, mutation: str, production_material: ProductionMaterial,
) -> None:
    if mutation == "tools":
        registry_path = _registry(tmp_path, production_material)
        registry = json.loads(registry_path.read_bytes())
        registry["profiles"]["local-production"]["tools_list_digest"] = "sha256:" + "f" * 64
        registry_path.write_bytes(canonical_bytes(registry))
    else:
        registry_path = _registry(
            tmp_path, production_material,
            pin_mutation=("wheel_digest", "sha256:" + "f" * 64),
        )
    with pytest.raises(FormalBridgeError, match="MCP_.*DRIFT"):
        FormalBridgeV4(load_active_profile(registry_path)).connect()


@pytest.mark.parametrize("mutation", ("verify", "read"))
def test_delivery_guard_rejects_verified_or_byte_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
    production_material: ProductionMaterial,
) -> None:
    profile = load_active_profile(_registry(tmp_path, production_material))
    with FormalBridgeV4(profile) as bridge:
        session = bridge.session
        assert session is not None
        original = session._call_tool

        def altered(name: str, arguments: dict[str, object]):
            result = copy.deepcopy(original(name, arguments))
            if mutation == "verify" and name == "jc_verify_run":
                result["verification"]["status"] = "FAILED"
            if mutation == "read" and name == "jc_read_artifact":
                result["content_base64"] = "eA=="
            return result

        monkeypatch.setattr(session, "_call_tool", altered)
        with pytest.raises(FormalBridgeError):
            bridge.deliver(production_bundle(15, material=production_material))


def test_reconnect_revalidates_and_delivers_article_13(
    tmp_path: Path, production_material: ProductionMaterial,
) -> None:
    profile = load_active_profile(_registry(tmp_path, production_material))
    with FormalBridgeV4(profile) as bridge:
        first = bridge.session
        second = bridge.connect()
        assert first is not None and first.generation == 0 and second.generation == 1
        delivery = bridge.deliver(production_bundle(13, material=production_material))
        assert delivery.marker == "JC_FORMAL_VERIFIED"
        assert delivery.generation == 1


def test_cli_uses_registry_without_changing_general_jc(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
    production_material: ProductionMaterial,
) -> None:
    bundle_path = tmp_path / "bundle.json"
    bundle = production_bundle(15, material=production_material)
    bundle_path.write_bytes(bundle.canonical_bytes())
    registry_path = _registry(tmp_path, production_material)
    assert main(["--registry", str(registry_path), "--input", str(bundle_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["marker"] == "JC_FORMAL_VERIFIED"
    assert "formal_bridge" not in Path("compiler_core/cli.py").read_text(encoding="utf-8")
