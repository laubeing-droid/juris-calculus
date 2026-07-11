"""CanonicalResult单向渲染、profile、防火墙和可视化门禁。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from compiler_core.audit_bundle import evaluate_to_audit_bundle
from compiler_core.rendering import (
    RendererError,
    _render_html,
    load_renderer_profile,
    render_run,
)
from tests.unit.test_audit_bundle import _fixture


def _completed_run(tmp_path: Path):
    """创建带完整审计包的development fixture run。"""

    loaded, request = _fixture(tmp_path / "configs")
    state_root = tmp_path / "state"
    bundle = evaluate_to_audit_bundle(request, loaded, state_root=state_root)
    return state_root, bundle


def _write_profile(path: Path, **overrides) -> Path:
    """写入无可执行模板的声明式测试profile。"""

    payload = {
        "schema_version": "1.0",
        "profile_id": "fixture",
        "version": "1.0.0",
        "locale": "zh-CN",
        "tone": "concise",
        "detail_level": "standard",
        "heading_order": ["status", "claims", "sources", "risks", "review"],
        "heading_aliases": {},
        "show_citations": True,
        "forbidden_phrases": [],
        **overrides,
    }
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_render_writes_bound_artifact_and_metadata_without_re_evaluation(tmp_path, monkeypatch) -> None:
    """renderer只读完整run，写正文与不重复正文的旁车元数据。"""

    state_root, bundle = _completed_run(tmp_path)
    result_path = bundle.run_directory / "result.json"
    original_result = result_path.read_bytes()

    def explode(*_args, **_kwargs):
        raise AssertionError("renderer reached evaluator")

    monkeypatch.setattr("compiler_core.evaluator.FixpointEvaluator", explode)
    output = render_run(bundle.result.semantic.run_id, state_root=state_root)
    metadata = json.loads(output.metadata_path.read_text(encoding="utf-8"))

    assert output.artifact_path.read_text(encoding="utf-8") == output.artifact.content
    assert output.artifact.content_sha256 == hashlib.sha256(output.artifact.content.encode("utf-8")).hexdigest()
    assert metadata["result_digest"] == bundle.result.semantic.result_digest
    assert metadata["content_sha256"] == output.artifact.content_sha256
    assert "content" not in metadata
    assert result_path.read_bytes() == original_result
    assert output.artifact_ref.startswith("renders/")
    assert not output.artifact_ref.startswith(("C:", "D:", "/"))


@pytest.mark.parametrize(("output_format", "suffix"), [("markdown", ".md"), ("mermaid", ".mmd"), ("html", ".html")])
def test_all_formats_are_deterministic_and_explicit(tmp_path, output_format: str, suffix: str) -> None:
    """Markdown、Mermaid和HTML仅在显式render时生成。"""

    state_root, bundle = _completed_run(tmp_path)
    first = render_run(bundle.result.semantic.run_id, state_root=state_root, output_format=output_format)
    second = render_run(bundle.result.semantic.run_id, state_root=state_root, output_format=output_format)

    assert first.artifact.content_sha256 == second.artifact.content_sha256
    assert first.artifact_path.suffix == suffix
    assert not list(bundle.run_directory.glob("*.html"))
    if output_format == "mermaid":
        assert first.artifact.content.startswith("flowchart TD\n")
        assert "result_status" not in first.artifact.content
    if output_format == "html":
        assert "Content-Security-Policy" in first.artifact.content
        assert "<script" not in first.artifact.content.lower()


def test_profile_changes_only_headings_and_never_canonical_result(tmp_path) -> None:
    """声明式profile可改标题，但机器结果bytes保持不变。"""

    state_root, bundle = _completed_run(tmp_path)
    result_path = bundle.run_directory / "result.json"
    before = result_path.read_bytes()
    profile_path = _write_profile(tmp_path / "profile.yaml", heading_aliases={"status": "边界状态"})
    output = render_run(
        bundle.result.semantic.run_id,
        state_root=state_root,
        audience="lawyer",
        profile_path=profile_path,
    )

    assert "## 边界状态" in output.artifact.content
    assert output.artifact.audience == "lawyer"
    assert result_path.read_bytes() == before


def test_profile_precedence_is_explicit_then_private_then_neutral(tmp_path, monkeypatch) -> None:
    """profile选择不读取环境变量覆盖，且显式路径优先于私有默认。"""

    private = _write_profile(tmp_path / "private.yaml", profile_id="private")
    explicit = _write_profile(tmp_path / "explicit.yaml", profile_id="explicit")
    monkeypatch.setattr("compiler_core.rendering.default_private_profile_path", lambda: private)

    assert load_renderer_profile().profile_id == "private"
    assert load_renderer_profile(explicit).profile_id == "explicit"


@pytest.mark.parametrize(
    "overrides",
    [
        {"result_status": "accepted_formal_result"},
        {"heading_order": ["status"]},
        {"heading_aliases": {"status": "bad\nheading"}},
        {"profile_hash": "0" * 64},
    ],
)
def test_profile_fail_closed_on_semantic_or_integrity_overreach(tmp_path, overrides) -> None:
    """profile不得隐藏章节、覆盖结果或伪造hash。"""

    path = _write_profile(tmp_path / "bad.yaml", **overrides)
    with pytest.raises(RendererError):
        load_renderer_profile(path)


def test_forbidden_phrase_blocks_artifact_write(tmp_path) -> None:
    """profile禁用词命中时不写展示产物。"""

    state_root, bundle = _completed_run(tmp_path)
    profile = _write_profile(tmp_path / "profile.yaml", forbidden_phrases=["accepted_formal_result"])
    with pytest.raises(RendererError) as caught:
        render_run(bundle.result.semantic.run_id, state_root=state_root, profile_path=profile)
    assert caught.value.code == "FORBIDDEN_PHRASE_EMITTED"
    assert not (state_root / "renders").exists()


def test_html_escapes_untrusted_text_and_has_no_script_capability() -> None:
    """HTML展示转义不可信内容并以CSP禁用脚本和网络资源。"""

    rendered = _render_html("<script>alert('x')</script> D:/not-a-real-output")
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered
    assert "default-src 'none'" in rendered
