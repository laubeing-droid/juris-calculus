"""从已跟踪规则资源确定性生成当前pack manifests。"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ROOT / "configs"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler_core.rule_packs import PACK_SCHEMA_VERSION, manifest_content_digest, sha256_file
PACK_SPECS = (
    {
        "pack_id": "cn-official",
        "kind": "official",
        "status": "blocked",
        "jurisdiction": "CN",
        "governing_law": "PRC",
        "rule_files": (),
        "source_files": (),
        "config_files": (),
    },
    {
        "pack_id": "cn-legacy-corpus",
        "kind": "legacy_corpus",
        "status": "candidate",
        "jurisdiction": "CN",
        "governing_law": "PRC",
        "rule_files": ("zh_CN/rules.yaml",),
        "source_files": ("zh_CN/source_manifest.yaml",),
        "config_files": ("zh_CN/domain_config.example.yaml", "zh_CN/ontology_map.yaml"),
    },
    {
        "pack_id": "hk-legacy-corpus",
        "kind": "legacy_corpus",
        "status": "candidate",
        "jurisdiction": "HK",
        "governing_law": "HKSAR",
        "rule_files": ("hk/rules.yaml", "hk/extended_rules.yaml"),
        "source_files": ("hk/provenance.yaml",),
        "config_files": ("L0_overrides_hk.yaml",),
    },
    {
        "pack_id": "us-federal-legacy-corpus",
        "kind": "legacy_corpus",
        "status": "candidate",
        "jurisdiction": "US-FEDERAL",
        "governing_law": "US-FEDERAL",
        "rule_files": ("us/rules.yaml",),
        "source_files": (),
        "config_files": (),
    },
    {
        "pack_id": "us-l0-adapter-legacy-corpus",
        "kind": "legacy_corpus",
        "status": "candidate",
        "jurisdiction": "US-FEDERAL",
        "governing_law": "US-FEDERAL",
        "rule_files": ("en_US/US_Adapter.yaml",),
        "source_files": (),
        "config_files": ("en_US/L0_overrides_us.yaml",),
    },
)


def _manifest_payload(spec: dict[str, Any], build_commit: str) -> str:
    """从固定规格生成一个规范 manifest，不执行写入。"""

    rule_files = [_file_entry(path) for path in spec["rule_files"]]
    source_files = [_file_entry(path) for path in spec["source_files"]]
    config_files = [_file_entry(path) for path in spec["config_files"]]
    corpus_total = sum(_rule_count(CONFIGS / entry["path"]) for entry in rule_files)
    document: dict[str, Any] = {
        "schema_version": PACK_SCHEMA_VERSION,
        "pack_id": spec["pack_id"],
        "version": "3.0.0a1",
        "kind": spec["kind"],
        "status": spec["status"],
        "jurisdiction": spec["jurisdiction"],
        "governing_law": spec["governing_law"],
        "effective_from": "2026-07-11",
        "effective_to": "",
        "rule_files": rule_files,
        "source_files": source_files,
        "config_files": config_files,
        "inventory": {
            "corpus_total": corpus_total,
            "reasoning_eligible_total": 0,
            "candidate_only_total": corpus_total,
        },
        "content_digest": "",
        "build_commit": build_commit,
    }
    document["content_digest"] = manifest_content_digest(document)
    return yaml.safe_dump(document, allow_unicode=True, sort_keys=False)


def build_manifests(build_commit: str) -> tuple[Path, ...]:
    """按固定spec写出manifest并返回路径。"""

    if len(build_commit) != 40 or any(character not in "0123456789abcdef" for character in build_commit):
        raise ValueError("build_commit must be a full lowercase Git SHA")
    written: list[Path] = []
    for spec in PACK_SPECS:
        target = CONFIGS / "packs" / spec["pack_id"] / "manifest.yaml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_manifest_payload(spec, build_commit), encoding="utf-8")
        written.append(target)
    return tuple(written)


def stale_manifests(build_commit: str) -> tuple[Path, ...]:
    """返回与当前规范不一致的 manifest；全程只读。"""

    if len(build_commit) != 40 or any(character not in "0123456789abcdef" for character in build_commit):
        raise ValueError("build_commit must be a full lowercase Git SHA")
    stale: list[Path] = []
    for spec in PACK_SPECS:
        target = CONFIGS / "packs" / spec["pack_id"] / "manifest.yaml"
        if not target.is_file() or target.read_text(encoding="utf-8") != _manifest_payload(spec, build_commit):
            stale.append(target)
    return tuple(stale)


def _file_entry(relative_path: str) -> dict[str, str]:
    """构造带当前文件hash的manifest项。"""

    path = CONFIGS / relative_path
    return {"path": relative_path, "sha256": sha256_file(path)}


def _rule_count(path: Path) -> int:
    """读取规则数组实际长度，不相信注释或静态数字。"""

    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = document.get("rules", []) if isinstance(document, dict) else []
    if not isinstance(rules, list):
        raise ValueError(f"rules must be an array: {path.name}")
    return len(rules)


def main() -> int:
    """CLI入口；build commit必须由调用者明确提供。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--build-commit", required=True)
    parser.add_argument("--check", action="store_true", help="verify manifests without writing them")
    args = parser.parse_args()
    if args.check:
        stale = stale_manifests(args.build_commit)
        for path in stale:
            print(path.relative_to(ROOT).as_posix())
        return 1 if stale else 0
    for path in build_manifests(args.build_commit):
        print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
