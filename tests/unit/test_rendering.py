"""CanonicalResult单向渲染、固定neutral展示、防火墙和可视化门禁。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
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


def test_render_uses_packaged_neutral_profile_and_never_canonical_result(tmp_path) -> None:
    """render固定使用包内neutral profile，且不改变机器结果bytes。"""

    state_root, bundle = _completed_run(tmp_path)
    result_path = bundle.run_directory / "result.json"
    before = result_path.read_bytes()
    output = render_run(
        bundle.result.semantic.run_id,
        state_root=state_root,
        audience="lawyer",
    )
    neutral = load_renderer_profile()

    assert output.artifact.profile_hash == neutral.profile_hash
    assert output.artifact.audience == "lawyer"
    assert result_path.read_bytes() == before


def test_profile_override_is_disabled(tmp_path) -> None:
    """任何显式profile覆盖都必须fail closed。"""

    with pytest.raises(RendererError) as caught:
        load_renderer_profile(tmp_path / "explicit.yaml")
    assert caught.value.code == "PROFILE_OVERRIDE_DISABLED"


def test_profile_override_blocks_artifact_write(tmp_path) -> None:
    """显式profile覆盖请求不得落盘任何展示产物。"""

    state_root, bundle = _completed_run(tmp_path)
    with pytest.raises(RendererError) as caught:
        render_run(bundle.result.semantic.run_id, state_root=state_root, profile_path=tmp_path / "profile.yaml")
    assert caught.value.code == "PROFILE_OVERRIDE_DISABLED"
    assert not (state_root / "renders").exists()


def test_html_escapes_untrusted_text_and_has_no_script_capability() -> None:
    """HTML展示转义不可信内容并以CSP禁用脚本和网络资源。"""

    rendered = _render_html("<script>alert('x')</script> D:/not-a-real-output")
    assert "&lt;script&gt;" in rendered
    assert "<script>" not in rendered
    assert "default-src 'none'" in rendered
