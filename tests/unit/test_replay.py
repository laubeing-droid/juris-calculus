"""离线语义replay、pack缓存缺失/篡改和首差异门禁。"""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from compiler_core.audit_bundle import (
    AuditBundleError,
    evaluate_to_audit_bundle,
    replay_audit_bundle,
)
from compiler_core.canonical_serialization import semantic_digest
from compiler_core.rule_packs import sha256_file
from tests.unit.test_audit_bundle import _fixture


def test_offline_replay_matches_events_result_and_graph(tmp_path) -> None:
    """无网络条件下使用内容寻址pack重放三类语义产物。"""

    loaded, request = _fixture(tmp_path / "configs")
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    replay = replay_audit_bundle(tmp_path / "state", bundle.result.semantic.run_id)

    assert tuple(sorted(replay)) == (
        "bundle_digest",
        "events_digest",
        "graph_digest",
        "result_digest",
        "run_id",
        "status",
    )
    assert replay == {
        "status": "PASS",
        "run_id": bundle.result.semantic.run_id,
        "result_digest": bundle.result.semantic.result_digest,
        "events_digest": semantic_digest([event.to_dict() for event in bundle.events]),
        "graph_digest": bundle.graph.graph_digest,
        "bundle_digest": bundle.bundle_digest,
    }


def test_missing_pack_cache_is_exit_6_condition_not_replay_mismatch(tmp_path) -> None:
    """材料缺失与语义不一致必须区分。"""

    loaded, request = _fixture(tmp_path / "configs")
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    cache = tmp_path / "state" / "packs" / loaded.descriptor.content_digest
    shutil.rmtree(cache)

    with pytest.raises(AuditBundleError) as caught:
        replay_audit_bundle(tmp_path / "state", bundle.result.semantic.run_id)
    assert caught.value.code == "REPLAY_MATERIAL_MISSING"


def test_tampered_cached_rule_is_not_used_for_replay(tmp_path) -> None:
    """缓存存在但hash不符时不得运行被篡改规则。"""

    loaded, request = _fixture(tmp_path / "configs")
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    cache = tmp_path / "state" / "packs" / loaded.descriptor.content_digest
    rule_path = cache / "configs" / "fixture" / "rules.yaml"
    rule_path.write_text(rule_path.read_text(encoding="utf-8") + "# tampered\n", encoding="utf-8")

    with pytest.raises(AuditBundleError) as caught:
        replay_audit_bundle(tmp_path / "state", bundle.result.semantic.run_id)
    assert caught.value.code == "REPLAY_PACK_INVALID"


def test_semantic_manifest_tamper_fails_after_checksums_are_rewritten(tmp_path) -> None:
    """攻击者重写checksum仍不能改变pack identity。"""

    loaded, request = _fixture(tmp_path / "configs")
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    manifest_path = bundle.run_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pack_id"] = "forged-pack"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _rewrite_checksums(bundle.run_directory)

    with pytest.raises(AuditBundleError) as caught:
        replay_audit_bundle(tmp_path / "state", bundle.result.semantic.run_id)
    assert caught.value.code == "AUDIT_MANIFEST_MISMATCH"


def test_coherently_rehashed_input_still_fails_semantic_replay(tmp_path) -> None:
    """攻击者同步更新input摘要和外层hash后，重放仍识别run语义变化。"""

    loaded, request = _fixture(tmp_path / "configs")
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    input_path = bundle.run_directory / "input.json"
    manifest_path = bundle.run_directory / "manifest.json"
    input_payload = json.loads(input_path.read_text(encoding="utf-8"))
    input_payload["facts"][0]["value"] = False
    input_path.write_text(json.dumps(input_payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["request_digest"] = semantic_digest(input_payload)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _rewrite_checksums(bundle.run_directory)

    with pytest.raises(AuditBundleError) as caught:
        replay_audit_bundle(tmp_path / "state", bundle.result.semantic.run_id)
    assert caught.value.code == "REPLAY_MISMATCH"
    assert str(caught.value) == "input:$.run_id:value"


def _rewrite_checksums(run_directory: Path) -> None:
    """重写外层校验值以测试语义层验证。"""

    files = ("graph.json", "input.json", "events.jsonl", "manifest.json", "result.json")
    hashes = {name: sha256_file(run_directory / name) for name in files}
    bundle_digest = semantic_digest([{"path": name, "sha256": hashes[name]} for name in sorted(files)])
    lines = [f"{hashes[name]}  {name}" for name in sorted(files)] + [f"BUNDLE  {bundle_digest}"]
    (run_directory / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run_directory / "COMPLETE").write_text(bundle_digest + "\n", encoding="utf-8")
