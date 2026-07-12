#!/usr/bin/env python3
"""Centralized bundled config path resolver.

All config file paths in juris-calculus should go through this module.
Formal runtime always resolves bundled resources. A development override must
be passed explicitly; merely setting JURIS_CONFIG_DIR cannot replace a pack.

Usage:
    from compiler_core.config_paths import rules_path
    rules = load_rules_from_yaml(rules_path("zh_CN"))

Enables "same algorithm, personal YAML" — each lawyer maintains their own
config root, and jc engine resolves everything through JURIS_CONFIG_DIR.
"""
from pathlib import Path

from compiler_core.resources import configs_root


def config_root(*, development: bool = False, override: str | Path | None = None) -> Path:
    """返回bundled根；只有显式development调用可使用自定义目录。"""

    if override is not None and not development:
        raise ValueError("config override requires development=True")
    return Path(override).resolve() if development and override is not None else configs_root()


def rules_path(jurisdiction: str = "zh_CN") -> str:
    """Path to rules.yaml for a given jurisdiction.

    Args:
        jurisdiction: "zh_CN" | "hk" | "en_US" | "uk"
    """
    return str(config_root() / jurisdiction / "rules.yaml")


def config_dir(jurisdiction: str = "zh_CN") -> str:
    """Path to config directory for a given jurisdiction."""
    return str(config_root() / jurisdiction)


def domain_config_path(jurisdiction: str = "zh_CN") -> str:
    """Path to domain_config.example.yaml for a given jurisdiction."""
    return str(config_root() / jurisdiction / "domain_config.example.yaml")


def criminal_complexity_path(jurisdiction: str = "zh_CN") -> str:
    """Path to criminal multi-party/multi-charge scenario config."""
    return str(config_root() / jurisdiction / "criminal_complexity.yaml")


def router_moe_path(jurisdiction: str = "zh_CN") -> str:
    """Path to MoE router shard config."""
    return str(config_root() / jurisdiction / "router_moe.yaml")


def overrides_path(jurisdiction: str = "hk") -> str:
    """Path to L0 overrides for a given jurisdiction."""
    mapping = {
        "hk": "L0_overrides_hk.yaml",
        "us": "en_US/L0_overrides_us.yaml",
    }
    relative = mapping.get(jurisdiction, f"L0_overrides_{jurisdiction}.yaml")
    return str(config_root() / relative)


def us_adapter_path() -> str:
    """Path to US_Adapter.yaml."""
    return str(config_root() / "en_US" / "US_Adapter.yaml")


def extended_rules_path(jurisdiction: str = "hk") -> str:
    """Path to extended_rules.yaml (e.g. HK expanded rules)."""
    return str(config_root() / jurisdiction / "extended_rules.yaml")
