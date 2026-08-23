"""Distribution discovery cannot resurrect the retired CN corpus."""

from __future__ import annotations

from pathlib import Path

import pytest

from compiler_core.resources import configs_root
from compiler_core.rule_packs import RulePackError, RulePackRegistry


ROOT = Path(__file__).resolve().parents[2]


def test_bundled_registry_and_git_index_exclude_retired_pack(monkeypatch, tmp_path) -> None:
    retired_id = "cn-" + "legacy-corpus"
    poison_root = tmp_path / "configs"
    poison_manifest = poison_root / "packs" / retired_id / "manifest.yaml"
    poison_manifest.parent.mkdir(parents=True)
    poison_manifest.write_text("pack_id: cn-legacy-corpus\n", encoding="utf-8")
    (poison_root / "zh_CN").mkdir()
    (poison_root / "zh_CN" / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
    monkeypatch.setenv("JURIS_CONFIG_DIR", str(poison_root))

    registry = RulePackRegistry(configs_root())
    assert retired_id not in {item["pack_id"] for item in registry.list_installed()}
    with pytest.raises(RulePackError) as caught:
        registry.verify(retired_id)
    assert caught.value.code == "PACK_NOT_INSTALLED"

    assert not (ROOT / "configs" / "zh_CN" / "rules.yaml").exists()
    assert not (ROOT / "configs" / "packs" / retired_id).exists()


def test_packaging_sources_do_not_name_retired_runtime_assets() -> None:
    for relative in ("pyproject.toml", "tools/build_rule_pack_manifests.py"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "cn-legacy-corpus" not in source
        assert "zh_CN/rules.yaml" not in source
