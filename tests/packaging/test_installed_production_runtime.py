from __future__ import annotations

from pathlib import Path

from compiler_core.formal_bridge import PIN_FIELDS
from tools.local_production import PROFILE_PIN_FIELDS, _venv_python
from tools.wheel_gate import expected_payload_paths


ROOT = Path(__file__).resolve().parents[2]


def test_release_profile_pins_exact_runtime_identity() -> None:
    assert PROFILE_PIN_FIELDS == PIN_FIELDS
    assert set(PROFILE_PIN_FIELDS) >= {
        "wheel_digest", "package_digest", "lock_digest", "schema_digest",
        "tool_spec_digest", "active_pack_ref", "trust_policy_ref",
        "storage_capability_ref", "legal_production_ready",
    }


def test_final_wheel_contains_production_runtime_and_bridge_only() -> None:
    payload = expected_payload_paths(ROOT)
    assert {
        "compiler_core/production_pack.py",
        "compiler_core/production_runtime.py",
        "compiler_core/formal_bridge.py",
    } <= payload
    assert not any(path.startswith(("tests/", "tools/")) for path in payload)


def test_release_venv_path_is_platform_native(tmp_path: Path) -> None:
    python = _venv_python(tmp_path)
    assert python.name in {"python", "python.exe"}
