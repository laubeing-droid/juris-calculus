"""审计包最终化、checksum、隐私、原子中断和路径独立性门禁。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import compiler_core.audit_bundle as bundle_module
from compiler_core.audit_bundle import (
    AuditBundleError,
    evaluate_to_audit_bundle,
    state_root_diagnostics,
    verify_audit_bundle,
)
from compiler_core.canonical_serialization import semantic_digest
from compiler_core.contracts import CaseRequest, SCHEMA_VERSION
from compiler_core.rule_packs import RulePackRegistry, sha256_file
from compiler_core.types import FactTrustStatus, LegalFact
from tests.unit.test_rule_pack_manifest import _write_pack


def _fixture(config_root: Path):
    """构造只有一条可准入规则的development official pack和匹配请求。"""

    rule = {
        "id": "R-ANCHORED",
        "premise_atoms": ["fact::a"],
        "head_claim": "claim::a",
        "source_anchor": "LAW-1",
        "norm_modality": "CONSTITUTIVE",
    }
    _write_pack(
        config_root,
        rules=[rule],
        inventory={"corpus_total": 1, "reasoning_eligible_total": 1, "candidate_only_total": 0},
    )
    loaded = RulePackRegistry(config_root, development_override=True).load_reasoning_pack("fixture-official")
    fact = LegalFact(
        id="fact::a",
        value=True,
        status=FactTrustStatus.VERIFIED_FACT,
        source_ids=("evidence::1",),
        human_reviewed=True,
    )
    request = CaseRequest(
        SCHEMA_VERSION,
        "CN",
        "PRC",
        "2026-07-11",
        (fact,),
        loaded.descriptor.pack_id,
        loaded.descriptor.version,
        loaded.descriptor.content_digest,
    )
    return loaded, request


def test_complete_bundle_has_fixed_files_hashes_and_semantic_digests(tmp_path) -> None:
    """COMPLETE包具备固定文件集，逐文件与四层语义摘要均可复验。"""

    loaded, request = _fixture(tmp_path / "configs")
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    verified = verify_audit_bundle(tmp_path / "state", bundle.result.semantic.run_id)

    assert sorted(path.name for path in bundle.run_directory.iterdir()) == [
        "COMPLETE",
        "checksums.sha256",
        "events.jsonl",
        "graph.json",
        "input.json",
        "manifest.json",
        "result.json",
    ]
    assert verified.bundle_digest == bundle.bundle_digest
    assert verified.semantic_result.to_dict() == bundle.result.semantic.to_dict()
    assert verified.manifest["events_digest"] == semantic_digest([event.to_dict() for event in bundle.events])
    assert all(not ref.startswith(("C:", "D:", "/")) for ref in bundle.result.artifact_refs)


def test_same_case_in_different_state_roots_has_same_semantic_and_bundle_digests(tmp_path) -> None:
    """本地存储路径不得进入result、graph或bundle内容。"""

    loaded, request = _fixture(tmp_path / "configs")
    first = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state-a")
    second = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state-b")

    assert first.result.semantic.result_digest == second.result.semantic.result_digest
    assert first.graph.graph_digest == second.graph.graph_digest
    assert first.bundle_digest == second.bundle_digest


@pytest.mark.parametrize("name", ["input.json", "events.jsonl", "result.json", "graph.json", "manifest.json"])
def test_any_canonical_file_tamper_fails_checksum(tmp_path, name: str) -> None:
    """五个规范文件任一字节变化都不能通过完整性门禁。"""

    loaded, request = _fixture(tmp_path / "configs")
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    path = bundle.run_directory / name
    path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(AuditBundleError) as caught:
        verify_audit_bundle(tmp_path / "state", bundle.result.semantic.run_id)
    assert caught.value.code == "AUDIT_CHECKSUM_MISMATCH"


def test_missing_complete_is_always_incomplete(tmp_path) -> None:
    """即使其他文件齐全，删除COMPLETE也不得视为可用包。"""

    loaded, request = _fixture(tmp_path / "configs")
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    (bundle.run_directory / "COMPLETE").unlink()

    with pytest.raises(AuditBundleError) as caught:
        verify_audit_bundle(tmp_path / "state", bundle.result.semantic.run_id)
    assert caught.value.code == "AUDIT_BUNDLE_INCOMPLETE"


def test_invalid_event_sequence_fails_even_after_attacker_rewrites_checksums(tmp_path) -> None:
    """重算外层hash仍不能掩盖重复seq。"""

    loaded, request = _fixture(tmp_path / "configs")
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    event_path = bundle.run_directory / "events.jsonl"
    lines = event_path.read_text(encoding="utf-8").splitlines()
    second = json.loads(lines[1])
    second["seq"] = 1
    second["event_id"] = second["event_id"].rsplit("::", 1)[0] + "::000001"
    lines[1] = json.dumps(second, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    event_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _rewrite_checksums(bundle.run_directory)

    with pytest.raises(AuditBundleError) as caught:
        verify_audit_bundle(tmp_path / "state", bundle.result.semantic.run_id)
    assert caught.value.code == "INVALID_EVENT_SEQUENCE"


def test_truncated_jsonl_and_unknown_parent_fail_after_checksum_rewrite(tmp_path) -> None:
    """外层hash不能掩盖截断JSON或不存在的parent event。"""

    loaded, request = _fixture(tmp_path / "configs")
    first = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state-a")
    event_path = first.run_directory / "events.jsonl"
    event_path.write_bytes(event_path.read_bytes()[:-2])
    _rewrite_checksums(first.run_directory)
    with pytest.raises(AuditBundleError) as truncated:
        verify_audit_bundle(tmp_path / "state-a", first.result.semantic.run_id)
    assert truncated.value.code == "INVALID_EVENT_STREAM"

    second = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state-b")
    event_path = second.run_directory / "events.jsonl"
    lines = event_path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[1])
    payload["parent_event_ids"] = ["event::missing::000001"]
    lines[1] = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    event_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _rewrite_checksums(second.run_directory)
    with pytest.raises(AuditBundleError) as parent:
        verify_audit_bundle(tmp_path / "state-b", second.result.semantic.run_id)
    assert parent.value.code == "INVALID_EVENT_SEQUENCE"


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        ("input.json", lambda payload: payload["facts"][0].update({"value": False})),
        ("result.json", lambda payload: payload["semantic"]["risk_labels"].append("FORGED")),
        ("graph.json", lambda payload: payload["summary"].update({"node_count": 999})),
    ],
)
def test_inner_semantic_digests_reject_rehashed_tamper(tmp_path, name, mutate) -> None:
    """input/result/graph被改且外层checksum重写后，内层摘要仍必须失败。"""

    loaded, request = _fixture(tmp_path / "configs")
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    path = bundle.run_directory / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    _rewrite_checksums(bundle.run_directory)

    with pytest.raises(AuditBundleError) as caught:
        verify_audit_bundle(tmp_path / "state", bundle.result.semantic.run_id)
    assert caught.value.code == "AUDIT_SEMANTIC_DIGEST_MISMATCH"


def test_raw_text_is_not_stored_and_structured_absolute_path_is_rejected(tmp_path) -> None:
    """原始卷宗字段不落包；必要结构字段含机器路径时明确拒绝。"""

    loaded, request = _fixture(tmp_path / "configs")
    request.facts[0].raw_text = "client secret D:/private/case.txt"
    request.facts[0].description = "client narrative"
    request.facts[0].provenance = {"path": "D:/private/source.pdf"}
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    stored = (bundle.run_directory / "input.json").read_text(encoding="utf-8")

    assert "client secret" not in stored
    assert "client narrative" not in stored
    assert "private/source" not in stored

    request.facts[0].value = "D:/private/value.txt"
    with pytest.raises(AuditBundleError) as caught:
        evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "other-state")
    assert caught.value.code == "AUDIT_PRIVACY_VIOLATION"


def test_write_interruption_leaves_no_complete_marker(tmp_path, monkeypatch) -> None:
    """中途写入失败保留可识别的中断目录，但绝不写COMPLETE。"""

    loaded, request = _fixture(tmp_path / "configs")
    original = bundle_module._atomic_write

    def interrupt(path: Path, payload: bytes) -> None:
        if path.name == "graph.json":
            raise OSError("simulated interruption")
        original(path, payload)

    monkeypatch.setattr(bundle_module, "_atomic_write", interrupt)
    with pytest.raises(OSError, match="simulated interruption"):
        evaluate_to_audit_bundle(request, loaded, state_root=tmp_path / "state")
    run_directories = list((tmp_path / "state" / "runs").iterdir())
    assert len(run_directories) == 1
    assert not (run_directories[0] / "COMPLETE").exists()


def test_audit_root_inside_repository_is_rejected(tmp_path) -> None:
    """正式审计默认不得污染跟踪仓库。"""

    loaded, request = _fixture(tmp_path / "configs")
    repository_state = Path(__file__).resolve().parents[2] / ".forbidden-audit-state"

    with pytest.raises(AuditBundleError) as caught:
        evaluate_to_audit_bundle(request, loaded, state_root=repository_state)
    assert caught.value.code == "AUDIT_PATH_IN_REPOSITORY"
    assert not repository_state.exists()


def test_state_root_doctor_reports_writable_space_and_repository_boundary(tmp_path) -> None:
    """doctor诊断不泄漏路径，并区分正常用户目录与仓库目录。"""

    healthy = state_root_diagnostics(tmp_path / "state")
    repository = state_root_diagnostics(Path(__file__).resolve().parents[2] / ".forbidden-audit-state")

    assert healthy["resource"] == "explicit-state-root"
    assert healthy["writable"] is True
    assert healthy["in_repository"] is False
    assert healthy["free_bytes"] > 0
    assert repository["in_repository"] is True
    assert repository["writable"] is False
    assert all("path" not in key for key in healthy)


def _rewrite_checksums(run_directory: Path) -> None:
    """模拟攻击者重写外层hash和COMPLETE，用于测试内层语义门禁。"""

    files = ("graph.json", "input.json", "events.jsonl", "manifest.json", "result.json")
    hashes = {name: sha256_file(run_directory / name) for name in files}
    bundle_digest = semantic_digest([{"path": name, "sha256": hashes[name]} for name in sorted(files)])
    text = "".join(f"{hashes[name]}  {name}\n" for name in sorted(files))
    text += f"BUNDLE  {bundle_digest}\n"
    (run_directory / "checksums.sha256").write_text(text, encoding="utf-8")
    (run_directory / "COMPLETE").write_text(bundle_digest + "\n", encoding="utf-8")
