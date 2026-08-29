"""The committed required-test manifest describes the current tree.

The manifest keeps V4 governance honest: every selector it names must be a
tracked file that declares the named symbols, suites must exist, and the
policy still forbids SKIP/XFAIL outcomes. It no longer freezes test counts
or any old receipt/wave machinery.
"""
from __future__ import annotations

import configparser
import json
from pathlib import Path

from tools.remediation.checks import manifest_problems

REPO = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO / "tests" / "required-v4-tests.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_committed_manifest_is_valid_against_current_tree() -> None:
    assert manifest_problems(REPO) == []


def test_policy_prohibits_skip_and_xfail_outcomes() -> None:
    policy = _manifest()["required_policy"]
    assert policy["current_state"] == "REQUIRED_NOW"
    assert policy["activation_state"] == "ACTIVE_REQUIRED"
    assert policy["prohibited_outcomes"] == ["SKIP", "XFAIL"]
    assert policy["unimplemented_behavior"] == "FAIL"


def test_pytest_config_keeps_strict_discovery_controls() -> None:
    config_path = REPO / _manifest()["pytest_config"]
    assert config_path.is_file()
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.read_string(config_path.read_text(encoding="utf-8"))
    assert parser.get("pytest", "xfail_strict") == "true"
    assert parser.get("pytest", "addopts").strip() == "--strict-config --strict-markers"


def test_current_v4_guards_remain_declared_required() -> None:
    manifest = _manifest()
    required_files = {
        "tests/packaging/test_official_yaml_admission.py",
        "tests/unit/test_remediation_runner.py",
        "tests/dsh_formal/test_production_bridge.py",
        "tests/formal_e2e/test_local_production_chain.py",
        "tests/integration/test_production_pack_loader.py",
        "tests/security/test_production_pack_attacks.py",
        "tests/mcp_protocol/test_production_stdio.py",
    }
    selectors = {
        entry["selector"].split("::")[0]
        for section in ("required_now", "evidence_tracks", "audit_mutations")
        for entry in manifest[section]
    }
    assert required_files <= selectors
    delivery_guard = {
        entry["selector"] for entry in manifest["audit_mutations"]
        if "test_delivery_guard_rejects_verified_or_byte_drift" in entry.get("selector", "")
    }
    assert delivery_guard, "the production delivery-guard red test must stay manifest-locked"


def test_audit_mutations_are_unique_and_active() -> None:
    mutations = _manifest()["audit_mutations"]
    assert mutations
    ids = [entry["test_id"] for entry in mutations]
    assert len(ids) == len(set(ids))
    assert all(entry["state"] == "ACTIVE_REQUIRED" for entry in mutations)
    assert all(
        set(entry) == {"audit_id", "mutation", "owner_task", "red_failure",
                       "selector", "state", "suite", "test_id"}
        for entry in mutations
    )
