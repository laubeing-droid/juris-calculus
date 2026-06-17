#!/usr/bin/env python3
"""v2.0 Centralized config path resolver.

All config file paths in juris-calculus should go through this module.
Override via JURIS_CONFIG_DIR env var to point at your personal YAML library.

Usage:
    from compiler_core.config_paths import rules_path, blueprint_path
    rules = load_rules_from_yaml(rules_path("zh_CN"))

Enables "same algorithm, personal YAML" — each lawyer maintains their own
config root, and jc engine resolves everything through JURIS_CONFIG_DIR.
"""
import os
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_CONFIG_ROOT = Path(os.environ.get("JURIS_CONFIG_DIR", _BASE / "configs"))


def config_root() -> Path:
    """Return the effective config root (env-overridable)."""
    return _CONFIG_ROOT


def blueprint_path() -> str:
    """Path to juris_blueprint.json (Layer 0 truth source)."""
    return str(_CONFIG_ROOT / "juris_blueprint.json")


def rules_path(jurisdiction: str = "zh_CN") -> str:
    """Path to rules.yaml for a given jurisdiction.

    Args:
        jurisdiction: "zh_CN" | "hk" | "en_US" | "uk"
    """
    return str(_CONFIG_ROOT / jurisdiction / "rules.yaml")


def config_dir(jurisdiction: str = "zh_CN") -> str:
    """Path to config directory for a given jurisdiction."""
    return str(_CONFIG_ROOT / jurisdiction)


def domain_config_path(jurisdiction: str = "zh_CN") -> str:
    """Path to domain_config.example.yaml for a given jurisdiction."""
    return str(_CONFIG_ROOT / jurisdiction / "domain_config.example.yaml")


def criminal_complexity_path(jurisdiction: str = "zh_CN") -> str:
    """Path to criminal multi-party/multi-charge scenario config."""
    return str(_CONFIG_ROOT / jurisdiction / "criminal_complexity.yaml")


def router_moe_path(jurisdiction: str = "zh_CN") -> str:
    """Path to MoE router shard config."""
    return str(_CONFIG_ROOT / jurisdiction / "router_moe.yaml")


def juris_contracts_path() -> str:
    """Path to structured experience contracts."""
    return str(_CONFIG_ROOT / "juris_contracts.yaml")


def overrides_path(jurisdiction: str = "hk") -> str:
    """Path to L0 overrides for a given jurisdiction."""
    mapping = {
        "hk": "L0_overrides_hk.yaml",
        "us": "en_US/L0_overrides_us.yaml",
    }
    relative = mapping.get(jurisdiction, f"L0_overrides_{jurisdiction}.yaml")
    return str(_CONFIG_ROOT / relative)


def us_adapter_path() -> str:
    """Path to US_Adapter.yaml."""
    return str(_CONFIG_ROOT / "en_US" / "US_Adapter.yaml")


def extended_rules_path(jurisdiction: str = "hk") -> str:
    """Path to extended_rules.yaml (e.g. HK expanded rules)."""
    return str(_CONFIG_ROOT / jurisdiction / "extended_rules.yaml")
