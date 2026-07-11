"""US legacy资源的唯一规则身份和默认入口消歧门禁。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _load(relative: str) -> dict:
    """读取一个仓库内US YAML资源。"""

    return yaml.safe_load((ROOT / relative).read_text(encoding="utf-8")) or {}


def test_us_adapter_and_constraints_have_unique_semantic_ids() -> None:
    """Transactional和Use immunity不得再因同名ID互相覆盖。"""

    adapter = _load("configs/en_US/US_Adapter.yaml")
    overrides = _load("configs/en_US/L0_overrides_us.yaml")
    rule_ids = [rule["id"] for rule in adapter["rules"]]
    constraint_ids = [rule["id"] for rule in overrides["constraint_rules"]]

    assert [item for item, count in Counter(rule_ids).items() if count > 1] == []
    assert [item for item, count in Counter(constraint_ids).items() if count > 1] == []
    assert {"US-Immunity-Transactional", "US-Immunity-Use"} <= set(rule_ids)
    assert {
        "US-CONSTRAINT-US-Immunity-Transactional",
        "US-CONSTRAINT-US-Immunity-Use",
    } <= set(constraint_ids)


def test_old_empty_us_default_is_an_explicit_tombstone() -> None:
    """空rules.yaml必须指向唯一替代pack，禁止与adapter形成双默认。"""

    tombstone = _load("configs/en_US/rules.yaml")

    assert tombstone["rules"] == []
    assert tombstone["_meta"] == {
        "status": "TOMBSTONE",
        "reason": "The empty legacy default was ambiguous with US_Adapter.yaml.",
        "replacement_pack": "us-l0-adapter-legacy-corpus",
    }
