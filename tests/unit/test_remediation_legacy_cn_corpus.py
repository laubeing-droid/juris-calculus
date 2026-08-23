"""History-bound retirement proof for the exact CN legacy corpus."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = "configs/zh_CN/rules.yaml"
MANIFEST_PATH = "configs/packs/cn-legacy-corpus/manifest.yaml"
V3_COMMIT = "aa0e038daf066bfc0baa4d27ee54adef12c3ae16"


def _git_show(path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"v3.0.2:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    return completed.stdout


def test_frozen_history_locator_reproduces_exact_assets() -> None:
    assert subprocess.run(
        ["git", "rev-parse", "v3.0.2^{}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip() == V3_COMMIT

    rules_bytes = _git_show(RULES_PATH)
    manifest_bytes = _git_show(MANIFEST_PATH)
    assert len(rules_bytes) == 13620766
    assert hashlib.sha256(rules_bytes).hexdigest() == "032206c349154d77eeef771d2b40dcfb62e1f7724c420ba4c09e69aaf88e8a44"
    assert hashlib.sha256(manifest_bytes).hexdigest() == "5613b20bc5e3f61655f087b827e946e58cb38e13ff985f4e01779dc4993f41f7"

    document = yaml.safe_load(rules_bytes)
    rule_ids = [rule["id"] for rule in document["rules"]]
    assert len(rule_ids) == len(set(rule_ids)) == 21144


def test_history_bound_authorization_is_exact_and_non_promotional() -> None:
    record = json.loads((
        ROOT / "remediation/v4/approvals/H5-02-user-authorized-history-bound.json"
    ).read_text(encoding="utf-8"))
    assert record["decision"] == "USER_AUTHORIZED_HISTORY_BOUND"
    assert record["evidence_kind"] == "USER_DIRECTIVE"
    assert record["authority_source"]["cryptographic_signature"] is False
    assert [item["path"] for item in record["history_bound_paths"]] == [RULES_PATH, MANIFEST_PATH]
    assert record["candidate_advisory_decision"]["additional_deletions_approved"] == []
    assert "configs/zh_CN/source_manifest.yaml" in record["excluded_adjacent_paths"]


def test_current_tree_and_disposition_keep_only_history_locators() -> None:
    assert not (ROOT / RULES_PATH).exists()
    assert not (ROOT / MANIFEST_PATH).exists()
    tracked = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert RULES_PATH not in tracked
    assert MANIFEST_PATH not in tracked

    disposition = json.loads((ROOT / "remediation/v4/file-disposition.json").read_text(encoding="utf-8"))
    by_path = {item["path"]: item for item in disposition["paths"]}
    for path in (RULES_PATH, MANIFEST_PATH):
        assert by_path[path]["disposition"] == "DELETE_CURRENT"
        assert by_path[path]["terminal_state"] == "HISTORY_BOUND"
        assert by_path[path]["history_locator_only"] is True
