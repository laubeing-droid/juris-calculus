"""版本化规则包hash、计数、来源准入和开发覆盖门禁。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from compiler_core.config_paths import config_root
from compiler_core.resources import configs_root
from compiler_core.rule_packs import (
    RulePackError,
    RulePackRegistry,
    manifest_content_digest,
    sha256_file,
)


def _write_pack(
    root: Path,
    *,
    pack_id: str = "fixture-official",
    rules: list[dict] | None = None,
    sources: list[dict] | None = None,
    inventory: dict[str, int] | None = None,
) -> Path:
    """写出完整测试pack，所有hash均从实际文件计算。"""

    rules = rules if rules is not None else [
        {
            "id": "R-ANCHORED",
            "premise_atoms": ["fact::a"],
            "head_claim": "claim::a",
            "source_anchor": "LAW-1",
            "norm_modality": "CONSTITUTIVE",
        },
        {
            "id": "R-CANDIDATE",
            "premise_atoms": ["fact::b"],
            "head_claim": "claim::b",
            "norm_modality": "CONSTITUTIVE",
        },
    ]
    sources = sources if sources is not None else [
        {
            "source_id": "LAW-1",
            "source_type": "statute",
            "title": "Fixture Law",
            "jurisdiction": "CN",
            "verified": True,
            "content_hash": "a" * 64,
        }
    ]
    rule_path = root / "fixture" / "rules.yaml"
    source_path = root / "fixture" / "sources.yaml"
    rule_path.parent.mkdir(parents=True, exist_ok=True)
    rule_path.write_text(
        yaml.safe_dump({"_meta": {"total": len(rules)}, "rules": rules}, sort_keys=False),
        encoding="utf-8",
    )
    source_path.write_text(yaml.safe_dump({"sources": sources}, sort_keys=False), encoding="utf-8")
    expected_inventory = inventory or {
        "corpus_total": len(rules),
        "reasoning_eligible_total": 1,
        "candidate_only_total": len(rules) - 1,
    }
    manifest = {
        "schema_version": "1.0",
        "pack_id": pack_id,
        "version": "1.0.0",
        "kind": "official",
        "status": "active",
        "jurisdiction": "CN",
        "governing_law": "PRC",
        "effective_from": "2026-01-01",
        "effective_to": "",
        "rule_files": [{"path": "fixture/rules.yaml", "sha256": sha256_file(rule_path)}],
        "source_files": [{"path": "fixture/sources.yaml", "sha256": sha256_file(source_path)}],
        "config_files": [],
        "inventory": expected_inventory,
        "content_digest": "",
        "build_commit": "b" * 40,
    }
    manifest["content_digest"] = manifest_content_digest(manifest)
    manifest_path = root / "packs" / pack_id / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


def test_text_resource_hash_is_stable_across_windows_and_posix_newlines(tmp_path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_bytes(b"rules:\n- id: R1\n")
    expected = sha256_file(path)

    path.write_bytes(b"rules:\r\n- id: R1\r\n")

    assert sha256_file(path) == expected


def test_one_anchored_and_one_unsourced_rule_have_separate_inventories(tmp_path) -> None:
    """有hash来源规则可晋升，无来源规则保留候选且不得被丢弃。"""

    _write_pack(tmp_path)
    result = RulePackRegistry(tmp_path).verify("fixture-official")

    assert result.integrity_valid is True
    assert result.reasoning_ready is True
    assert result.inventory == {
        "corpus_total": 2,
        "reasoning_eligible_total": 1,
        "candidate_only_total": 1,
    }
    assert result.candidate_rule_ids == ("R-CANDIDATE",)
    assert result.issues == ()


def test_tampered_file_hash_fails_closed(tmp_path) -> None:
    """manifest生成后修改规则文件必须使完整性失败。"""

    _write_pack(tmp_path)
    rule_path = tmp_path / "fixture" / "rules.yaml"
    rule_path.write_text(rule_path.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")

    result = RulePackRegistry(tmp_path).verify("fixture-official")
    assert result.integrity_valid is False
    assert result.reasoning_ready is False
    assert "FILE_HASH_MISMATCH" in {issue["code"] for issue in result.issues}


def test_duplicate_rule_and_bad_inventory_are_rejected(tmp_path) -> None:
    """重复ID与声明计数漂移均为完整性错误。"""

    duplicate = {
        "id": "R-DUP",
        "premise_atoms": ["fact::a"],
        "head_claim": "claim::a",
        "source_anchor": "LAW-1",
        "norm_modality": "CONSTITUTIVE",
    }
    _write_pack(
        tmp_path,
        rules=[duplicate, dict(duplicate)],
        inventory={"corpus_total": 99, "reasoning_eligible_total": 0, "candidate_only_total": 99},
    )

    result = RulePackRegistry(tmp_path).verify("fixture-official")
    codes = {issue["code"] for issue in result.issues}
    assert result.integrity_valid is False
    assert {"DUPLICATE_RULE_ID", "INVENTORY_MISMATCH"} <= codes


def test_unknown_priority_target_blocks_official_admission(tmp_path) -> None:
    """official规则的悬空priority引用不得进入eligible index。"""

    rule = {
        "id": "R-PRIORITY",
        "premise_atoms": ["fact::a"],
        "head_claim": "claim::a",
        "source_anchor": "LAW-1",
        "norm_modality": "CONSTITUTIVE",
        "priority_over": ["missing::claim"],
    }
    _write_pack(
        tmp_path,
        rules=[rule],
        inventory={"corpus_total": 1, "reasoning_eligible_total": 0, "candidate_only_total": 1},
    )

    result = RulePackRegistry(tmp_path).verify("fixture-official")
    assert result.integrity_valid is False
    assert result.reasoning_ready is False
    assert "UNKNOWN_PRIORITY_TARGET" in {issue["code"] for issue in result.issues}


def test_invalid_manifest_date_range_is_rejected_even_with_fresh_digest(tmp_path) -> None:
    """重算digest不能掩盖非法日期或倒置有效期。"""

    manifest_path = _write_pack(tmp_path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["effective_from"] = "not-a-date"
    manifest["effective_to"] = "2025-01-01"
    manifest["content_digest"] = manifest_content_digest(manifest)
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")

    result = RulePackRegistry(tmp_path).verify("fixture-official")
    assert result.integrity_valid is False
    assert "INVALID_MANIFEST_DATE" in {issue["code"] for issue in result.issues}


def test_duplicate_pack_id_and_missing_optional_pack_do_not_fallback(tmp_path) -> None:
    """重复pack与未安装pack均显式失败，不选择同法域其他目录。"""

    first = _write_pack(tmp_path, pack_id="same-pack")
    second = tmp_path / "packs" / "other-directory" / "manifest.yaml"
    second.parent.mkdir(parents=True)
    second.write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
    registry = RulePackRegistry(tmp_path)

    with pytest.raises(RulePackError, match="same-pack") as duplicate:
        registry.manifests()
    assert duplicate.value.code == "DUPLICATE_PACK_ID"

    second.unlink()
    with pytest.raises(RulePackError, match="not-installed") as missing:
        registry.verify("not-installed")
    assert missing.value.code == "PACK_NOT_INSTALLED"


def test_bundled_manifests_are_hash_and_count_consistent() -> None:
    """当前五个发布manifest均完整，official为空时只报告BLOCKED。"""

    results = {result.pack_id: result for result in RulePackRegistry(configs_root()).verify_all()}

    assert set(results) == {
        "cn-official",
        "cn-legacy-corpus",
        "hk-legacy-corpus",
        "us-federal-legacy-corpus",
        "us-l0-adapter-legacy-corpus",
    }
    assert all(result.integrity_valid for result in results.values())
    assert results["cn-official"].reasoning_ready is False
    assert results["cn-legacy-corpus"].inventory == {
        "corpus_total": 21144,
        "reasoning_eligible_total": 0,
        "candidate_only_total": 21144,
    }
    assert results["hk-legacy-corpus"].inventory["corpus_total"] == 133
    assert results["us-federal-legacy-corpus"].inventory["corpus_total"] == 123
    assert results["us-l0-adapter-legacy-corpus"].inventory["corpus_total"] == 81


def test_environment_variable_alone_cannot_replace_bundled_root(tmp_path, monkeypatch) -> None:
    """JURIS_CONFIG_DIR只作为显式development参数来源，不影响正式config_root。"""

    monkeypatch.setenv("JURIS_CONFIG_DIR", str(tmp_path))
    assert config_root() == configs_root()
    with pytest.raises(ValueError, match="development=True"):
        config_root(override=tmp_path)
    assert config_root(development=True, override=tmp_path) == tmp_path.resolve()


def test_manifest_machine_result_contains_no_absolute_paths() -> None:
    """公开验证结果只含逻辑资源和hash，不泄漏安装路径。"""

    result = RulePackRegistry(configs_root()).verify("cn-official").to_dict()
    encoded = json.dumps(result, ensure_ascii=False)
    assert "D:\\" not in encoded
    assert "C:\\" not in encoded
