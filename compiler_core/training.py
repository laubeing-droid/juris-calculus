"""候选规则训练导出；数据流单向离开语料pack且不能执行promotion。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
from typing import Any, Iterable, Mapping

import yaml

from compiler_core.rule_packs import RulePackRegistry
from compiler_core.types import build_rule_inventory, normalize_rule_admission


def export_rules_as_jsonl(
    rule_paths: Iterable[str | Path],
    out: str | Path,
    split_train: float = 0.8,
    split_dev: float = 0.1,
    split_test: float = 0.1,
    seed: int = 42,
    split_mode: str = "random",
    split_date: str = "2024-01-01",
    *,
    pack_metadata: Mapping[str, str] | None = None,
    candidate_rule_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """导出规则与candidate状态；不读取案件审计包或写回规则文件。"""

    if min(split_train, split_dev, split_test) < 0 or abs(split_train + split_dev + split_test - 1.0) > 1e-9:
        raise ValueError("training splits must be non-negative and sum to 1")
    metadata = dict(pack_metadata or {})
    authoritative_candidates = set(candidate_rule_ids) if candidate_rule_ids is not None else None
    items: list[dict[str, Any]] = []
    for path in rule_paths:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        raw_rules = document.get("rules", []) if isinstance(document, Mapping) else []
        if not isinstance(raw_rules, list):
            raise ValueError("rules must be a list")
        for raw in raw_rules:
            if not isinstance(raw, Mapping):
                continue
            rule = normalize_rule_admission(raw)
            rule_id = str(rule.get("id", ""))
            candidate = (
                rule_id in authoritative_candidates
                if authoritative_candidates is not None
                else str(rule.get("data_quality", "")) == "CANDIDATE_ONLY" or not rule.get("source_anchor")
            )
            items.append({
                "id": rule_id,
                "split_digest": hashlib.sha256(rule_id.encode("utf-8")).hexdigest()[:12],
                "premise_atoms": list(rule.get("premise_atoms", ())),
                "head_claim": rule.get("head_claim", ""),
                "exception_chain": list(rule.get("exception_chain", ())),
                "attacks": list(rule.get("attacks", ())),
                "priority_over": list(rule.get("priority_over", ())),
                "source_anchor": rule.get("source_anchor", ""),
                "source_status": "ANCHORED" if rule.get("source_anchor") else "UNVERIFIED",
                "admission_status": "CANDIDATE_ONLY" if candidate else "REASONING_ELIGIBLE",
                "trust_label": "UNVERIFIED" if candidate else rule.get("trust_label", "VERIFIED"),
                "data_quality": "CANDIDATE_ONLY" if candidate else rule.get("data_quality", "CLEAN"),
                "jurisdiction": rule.get("jurisdiction", metadata.get("jurisdiction", "")),
                "authority_rank": rule.get("authority_rank", ""),
                "valid_from": rule.get("valid_from", ""),
                "valid_to": rule.get("valid_to", ""),
                "pack_id": metadata.get("pack_id", "unversioned-fixture"),
                "pack_version": metadata.get("pack_version", ""),
                "pack_digest": metadata.get("pack_digest", ""),
                "split_seed": seed,
            })
    rng = random.Random(seed)
    rng.shuffle(items)
    total = len(items)
    train_end = int(total * split_train)
    dev_end = train_end + int(total * split_dev)
    splits = {"train": items[:train_end], "dev": items[train_end:dev_end], "test": items[dev_end:]}
    base = Path(out)
    base.parent.mkdir(parents=True, exist_ok=True)
    split_hashes: dict[str, str] = {}
    for split_name, split_items in splits.items():
        path = base.parent / f"{base.stem}_{split_name}.jsonl"
        lines = [json.dumps({**item, "split": split_name}, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for item in split_items]
        payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
        path.write_bytes(payload)
        split_hashes[split_name] = hashlib.sha256(payload).hexdigest()
    inventory = build_rule_inventory(items)
    canonical_items = sorted(items, key=lambda item: str(item["id"]))
    return {
        "schema_version": "1.0",
        "status": "PASS",
        "total_items": total,
        **inventory,
        "splits": {name: len(value) for name, value in splits.items()},
        "split_seed": seed,
        "split_mode": split_mode,
        "split_date": split_date,
        "split_hashes": split_hashes,
        "dataset_hash": hashlib.sha256(
            json.dumps(canonical_items, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "pack_id": metadata.get("pack_id", "unversioned-fixture"),
        "pack_version": metadata.get("pack_version", ""),
        "pack_digest": metadata.get("pack_digest", ""),
        "private_case_facts_included": False,
        "promotion": {"automatic": False, "status": "CANDIDATE_ONLY", "requires_governance": True},
    }


def export_corpus_pack(
    registry: RulePackRegistry,
    pack_id: str,
    output_dir: Path,
    *,
    seed: int = 42,
) -> dict[str, Any]:
    """验证pack后导出训练JSONL，拒绝写回config root。"""

    pack = registry.load_corpus_pack(pack_id)
    destination = Path(output_dir).resolve()
    if _inside_git_worktree(destination):
        raise ValueError("training output cannot be written inside a Git worktree")
    try:
        destination.relative_to(registry.config_root)
    except ValueError:
        pass
    else:
        raise ValueError("training output cannot be written inside the rule-pack config root")
    report = export_rules_as_jsonl(
        pack.rule_paths,
        destination / "rules.jsonl",
        seed=seed,
        pack_metadata={
            "pack_id": pack.verification.pack_id,
            "pack_version": pack.verification.version,
            "pack_digest": pack.verification.content_digest,
            "jurisdiction": pack.verification.jurisdiction,
        },
        candidate_rule_ids=pack.verification.candidate_rule_ids,
    )
    manifest_path = destination / "training_manifest.json"
    manifest_payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    manifest_path.write_text(manifest_payload, encoding="utf-8")
    return {
        **report,
        "artifact_files": ["rules_dev.jsonl", "rules_test.jsonl", "rules_train.jsonl", "training_manifest.json"],
        "manifest_sha256": hashlib.sha256(manifest_payload.encode("utf-8")).hexdigest(),
    }


def generate_model_card(
    model_id: str,
    model_version: str,
    task: str,
    dataset_hash: str,
    eval_metrics: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """生成明确shadow-only的模型卡。"""

    return {
        "model_id": model_id,
        "model_version": model_version,
        "task": task,
        "training_data_hash": dataset_hash,
        "allowed_outputs": ["candidate_claim", "candidate_rule", "source_span", "confidence", "uncertainty"],
        "promotion_status_suggestion": "SHADOW_ONLY",
        "evaluation_metrics": dict(eval_metrics or {}),
        "limitations": [
            "shadow_only - no direct legal conclusion authority",
            "requires source anchor validation",
            "requires external governance and human approval before pack status change",
        ],
        "audit_timestamp": "",
    }


def training_schema_document() -> dict[str, Any]:
    """返回训练导出manifest顶层严格schema。"""

    return {
        "$defs": {
            "TrainingExportManifest": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema_version", "status", "total_items", "corpus_total",
                    "reasoning_eligible_total", "candidate_only_total", "splits", "split_seed",
                    "split_mode", "split_date", "split_hashes", "dataset_hash", "pack_id",
                    "pack_version", "pack_digest", "private_case_facts_included", "promotion",
                ],
                "properties": {
                    "schema_version": {"const": "1.0"},
                    "status": {"const": "PASS"},
                    "total_items": {"type": "integer", "minimum": 0},
                    "corpus_total": {"type": "integer", "minimum": 0},
                    "reasoning_eligible_total": {"type": "integer", "minimum": 0},
                    "candidate_only_total": {"type": "integer", "minimum": 0},
                    "splits": {"type": "object"},
                    "split_seed": {"type": "integer"},
                    "split_mode": {"type": "string"},
                    "split_date": {"type": "string"},
                    "split_hashes": {"type": "object"},
                    "dataset_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "pack_id": {"type": "string"},
                    "pack_version": {"type": "string"},
                    "pack_digest": {"type": "string"},
                    "private_case_facts_included": {"const": False},
                    "promotion": {"type": "object"},
                },
            }
        }
    }


def _inside_git_worktree(path: Path) -> bool:
    """检查目标或其父目录是否位于Git工作树。"""

    current = path
    while True:
        if (current / ".git").exists():
            return True
        if current.parent == current:
            return False
        current = current.parent
