"""从已验证审计包按需生成展示产物；渲染过程不可到达求值器。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

import yaml

from compiler_core.audit_bundle import default_state_root, verify_audit_bundle
from compiler_core.canonical_serialization import semantic_digest
from compiler_core.contracts import (
    PROTECTED_RESULT_FIELDS,
    RenderedArtifact,
    RendererProfile,
    SemanticResult,
)
from compiler_core.output_firewall import (
    FORBIDDEN_CONCLUSION_PHRASES,
    FORBIDDEN_OUTPUT_FIELDS,
    validate_output_contract,
)
from compiler_core.resources import neutral_profile_path
from compiler_core.version import __version__


RENDERER_ID = "jc-neutral-renderer"
RENDERER_VERSION = __version__
PROFILE_SCHEMA_VERSION = "1.0"
REQUIRED_HEADINGS = frozenset({"status", "claims", "sources", "risks", "review"})
PROFILE_FIELDS = frozenset({
    "schema_version",
    "profile_id",
    "version",
    "profile_hash",
    "locale",
    "tone",
    "detail_level",
    "heading_order",
    "heading_aliases",
    "show_citations",
    "forbidden_phrases",
})


class RendererError(RuntimeError):
    """neutral renderer、firewall、格式或写入失败的稳定错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RenderOutput:
    """已写入展示文件和旁车元数据的结果。"""

    artifact: RenderedArtifact
    artifact_path: Path
    metadata_path: Path
    artifact_ref: str
    metadata_ref: str

    def public_dict(self) -> dict[str, Any]:
        """返回紧凑机器响应，不把正文或绝对路径写入stdout。"""

        return {
            "result_digest": self.artifact.result_digest,
            "content_sha256": self.artifact.content_sha256,
            "format": self.artifact.format,
            "audience": self.artifact.audience,
            "profile_id": self.artifact.profile_id,
            "profile_version": self.artifact.profile_version,
            "profile_hash": self.artifact.profile_hash,
            "warnings": list(self.artifact.warnings),
            "artifact_ref": self.artifact_ref,
            "metadata_ref": self.metadata_ref,
        }


def load_renderer_profile(path: Path | None = None) -> RendererProfile:
    """只加载内置neutral profile并验证其规范hash。"""

    selected = resolve_renderer_profile_path(path)
    try:
        payload = yaml.safe_load(selected.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RendererError("PROFILE_UNAVAILABLE", type(exc).__name__) from exc
    if not isinstance(payload, dict):
        raise RendererError("INVALID_RENDERER_PROFILE", "profile must be an object")
    unknown = sorted(set(payload) - PROFILE_FIELDS)
    protected = sorted(set(payload) & (PROTECTED_RESULT_FIELDS | FORBIDDEN_OUTPUT_FIELDS))
    if unknown or protected:
        raise RendererError(
            "INVALID_RENDERER_PROFILE",
            f"forbidden profile fields: {', '.join(protected or unknown)}",
        )
    if str(payload.get("schema_version", "")) != PROFILE_SCHEMA_VERSION:
        raise RendererError("INVALID_RENDERER_PROFILE", "unsupported profile schema version")
    digest_payload = {key: value for key, value in payload.items() if key != "profile_hash"}
    calculated_hash = semantic_digest(digest_payload)
    declared_hash = str(payload.get("profile_hash", ""))
    if declared_hash and declared_hash != calculated_hash:
        raise RendererError("PROFILE_HASH_MISMATCH", "profile content does not match profile_hash")
    aliases = payload.get("heading_aliases", {}) or {}
    if not isinstance(aliases, dict):
        raise RendererError("INVALID_RENDERER_PROFILE", "heading_aliases must be an object")
    headings = tuple(str(item) for item in payload.get("heading_order", ()))
    if not REQUIRED_HEADINGS.issubset(headings):
        raise RendererError("INVALID_RENDERER_PROFILE", "protected headings cannot be omitted")
    forbidden = tuple(str(item) for item in payload.get("forbidden_phrases", ()))
    if any(not item.strip() for item in forbidden):
        raise RendererError("INVALID_RENDERER_PROFILE", "forbidden phrases cannot be empty")
    try:
        return RendererProfile(
            profile_id=str(payload.get("profile_id", "")),
            version=str(payload.get("version", "")),
            profile_hash=calculated_hash,
            locale=str(payload.get("locale", "zh-CN")),
            tone=str(payload.get("tone", "concise")),
            detail_level=str(payload.get("detail_level", "standard")),
            heading_order=headings,
            heading_aliases=tuple((str(key), _clean_heading(value)) for key, value in aliases.items()),
            show_citations=bool(payload.get("show_citations", True)),
            forbidden_phrases=forbidden,
        )
    except ValueError as exc:
        raise RendererError("INVALID_RENDERER_PROFILE", str(exc)) from exc


def resolve_renderer_profile_path(explicit_path: Path | None = None) -> Path:
    """JC 公共内核固定只接受包内 neutral profile。"""

    if explicit_path is not None:
        raise RendererError("PROFILE_OVERRIDE_DISABLED", "JC render is fixed to the packaged neutral profile")
    return neutral_profile_path()


def render_run(
    run_id: str,
    *,
    state_root: Path | None = None,
    output_format: str = "markdown",
    audience: str = "agent",
    profile_path: Path | None = None,
) -> RenderOutput:
    """验证审计包后渲染并写入独立renders目录。"""

    if output_format not in {"markdown", "mermaid", "html"}:
        raise RendererError("INVALID_RENDER_FORMAT", output_format)
    if audience not in {"agent", "lawyer"}:
        raise RendererError("INVALID_AUDIENCE", audience)
    root = Path(state_root or default_state_root()).resolve()
    verified = verify_audit_bundle(root, run_id)
    profile = load_renderer_profile(profile_path)
    semantic = verified.semantic_result
    before = semantic.to_dict()
    presentation = _presentation(semantic, verified.graph_payload, profile, audience)
    firewall = validate_output_contract(presentation, result_status=semantic.result_status.value)
    if not firewall["ok"]:
        raise RendererError("OUTPUT_FIREWALL_BLOCKED", "; ".join(firewall["errors"]))
    if output_format == "mermaid":
        content = _render_mermaid(semantic, verified.graph_payload)
    else:
        markdown = _render_markdown(presentation, profile)
        content = _render_html(markdown) if output_format == "html" else markdown
    if before != semantic.to_dict() or semantic_digest(before) != semantic_digest(semantic.to_dict()):
        raise RendererError("CANONICAL_RESULT_DRIFT", "renderer changed the semantic result")
    for phrase in profile.forbidden_phrases:
        if phrase.casefold() in content.casefold():
            raise RendererError("FORBIDDEN_PHRASE_EMITTED", phrase)
    content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    warnings = tuple(sorted(set(presentation["warnings"])))
    artifact = RenderedArtifact(
        result_digest=semantic.result_digest,
        renderer_id=RENDERER_ID,
        renderer_version=RENDERER_VERSION,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        profile_hash=profile.profile_hash,
        audience=audience,
        locale=profile.locale,
        format=output_format,
        content=content,
        content_sha256=content_sha256,
        warnings=warnings,
    )
    logical_run = _safe_run_component(run_id)
    relative_root = Path("renders") / logical_run / semantic.result_digest / profile.profile_hash
    suffix = {"markdown": ".md", "mermaid": ".mmd", "html": ".html"}[output_format]
    artifact_relative = relative_root / f"{audience}{suffix}"
    metadata_relative = relative_root / f"{audience}{suffix}.render.json"
    artifact_path = root / artifact_relative
    metadata_path = root / metadata_relative
    metadata = {
        "schema_version": "1.0",
        **artifact.metadata_dict(),
        "artifact_ref": artifact_relative.as_posix(),
    }
    _atomic_write(artifact_path, content.encode("utf-8"))
    _atomic_write(
        metadata_path,
        (json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"),
    )
    return RenderOutput(
        artifact,
        artifact_path,
        metadata_path,
        artifact_relative.as_posix(),
        metadata_relative.as_posix(),
    )


def _presentation(
    result: SemanticResult,
    graph: Mapping[str, Any],
    profile: RendererProfile,
    audience: str,
) -> dict[str, Any]:
    """构建不含受保护字段名的展示模型。"""

    warnings = list(result.risk_labels)
    if result.review_required:
        warnings.append("REVIEW_REQUIRED")
    if not result.formal_kernel_used:
        warnings.append("FORMAL_KERNEL_NOT_USED")
    return {
        "run": result.run_id,
        "digest": result.result_digest,
        "status_value": result.result_status.value,
        "execution_value": result.execution_status.value,
        "certificate_value": result.certificate_kind.value,
        "claim_ids": list(result.claims),
        "branch_items": [
            {
                "branch": branch.branch_id,
                "status_value": branch.result_status.value,
                "claim_ids": list(branch.claims),
                "taint_values": list(branch.taint),
            }
            for branch in result.branches
        ],
        "fact_ids": list(result.used_fact_ids),
        "rule_ids": list(result.used_rule_ids),
        "source_refs": list(result.source_ids),
        "missing_ids": list(result.missing_fact_ids),
        "missing_items": [
            {
                "fact": item.fact_id,
                "rule_ids": list(item.impacted_rule_ids),
                "claim_ids": list(item.impacted_claim_ids),
                "reason_value": item.reason,
                "answer_types": list(item.allowed_answer_types),
                "source_need": item.source_requirement,
            }
            for item in result.missing_fact_review
        ],
        "risk_values": list(result.risk_labels),
        "taint_values": list(result.taint),
        "review_value": result.review_required,
        "checker_value": result.checker_accepted,
        "graph_summary": dict(graph.get("summary", {})),
        "audience": audience,
        "detail_level": profile.detail_level,
        "warnings": warnings,
    }


def _render_markdown(presentation: Mapping[str, Any], profile: RendererProfile) -> str:
    """按profile排序渲染完整受保护章节。"""

    aliases = dict(profile.heading_aliases)
    titles = {
        "status": "状态",
        "claims": "结论",
        "branches": "分支",
        "sources": "来源与使用材料",
        "risks": "风险与污点",
        "review": "复核与缺失事实",
        "graph": "推理图摘要",
    }
    titles.update(aliases)
    sections = {
        "status": [
            f"- run_id: `{presentation['run']}`",
            f"- result_status: `{presentation['status_value']}`",
            f"- execution_status: `{presentation['execution_value']}`",
            f"- certificate_kind: `{presentation['certificate_value']}`",
            f"- checker_accepted: `{str(presentation['checker_value']).lower()}`",
        ],
        "claims": _items(presentation["claim_ids"], "无正式结论"),
        "branches": _branch_lines(presentation["branch_items"]),
        "sources": [
            "### source_snapshot_ids",
            *_items(presentation["source_refs"], "无已验证来源"),
            "### used_rule_ids",
            *_items(presentation["rule_ids"], "无已使用规则"),
            "### used_fact_ids",
            *_items(presentation["fact_ids"], "无已使用事实"),
        ],
        "risks": [
            "### risk_labels",
            *_items(presentation["risk_values"], "无风险标签"),
            "### taint",
            *_items(presentation["taint_values"], "无污点标签"),
        ],
        "review": [
            f"- review_required: `{str(presentation['review_value']).lower()}`",
            "### missing_fact_ids",
            *_items(presentation["missing_ids"], "无缺失事实"),
            *_missing_review_lines(presentation["missing_items"]),
        ],
        "graph": [
            f"- nodes: `{presentation['graph_summary'].get('node_count', 0)}`",
            f"- edges: `{presentation['graph_summary'].get('edge_count', 0)}`",
            f"- events: `{presentation['graph_summary'].get('event_count', 0)}`",
        ],
    }
    order = list(profile.heading_order)
    if presentation["branch_items"] and "branches" not in order:
        order.append("branches")
    if profile.detail_level == "detailed" and "graph" not in order:
        order.append("graph")
    lines = ["# JC 审计推理结果", ""]
    for key in order:
        lines.extend([f"## {titles[key]}", "", *sections[key], ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_mermaid(result: SemanticResult, graph: Mapping[str, Any]) -> str:
    """把现有Graph JSON映射为确定性Mermaid，不推导新关系。"""

    lines = ["flowchart TD"]
    summary_label = _mermaid_label(
        f"status={result.result_status.value}; review={str(result.review_required).lower()}; "
        f"risks={','.join(result.risk_labels) or 'none'}"
    )
    lines.append(f'  summary["{summary_label}"]')
    nodes = list(graph.get("nodes", ()))
    node_names = {str(node.get("id", "")): f"n{index}" for index, node in enumerate(nodes)}
    for node in nodes:
        node_id = str(node.get("id", ""))
        label = _mermaid_label(f"{node.get('type', '')}: {node_id}")
        lines.append(f'  {node_names[node_id]}["{label}"]')
    for edge in graph.get("edges", ()):
        source = node_names.get(str(edge.get("source", "")))
        target = node_names.get(str(edge.get("target", "")))
        if source and target:
            label = _mermaid_label(str(edge.get("type", "")))
            lines.append(f"  {source} -->|{label}| {target}")
    return "\n".join(lines) + "\n"


def _render_html(markdown: str) -> str:
    """生成无脚本、带本地CSP的按需单文件HTML。"""

    escaped = html.escape(markdown, quote=True)
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>JC audit result</title><style>body{max-width:72rem;margin:2rem auto;padding:0 1rem;"
        "font:15px/1.6 system-ui,sans-serif;color:#172033;background:#f7f8fa}pre{white-space:pre-wrap;"
        "overflow-wrap:anywhere;background:white;border:1px solid #d9dee8;border-radius:8px;padding:1.5rem}</style>"
        f"</head><body><pre>{escaped}</pre></body></html>\n"
    )


def _items(values: Any, empty: str) -> list[str]:
    """渲染稳定列表并显式表示空集。"""

    material = [str(item) for item in values]
    return [f"- `{item}`" for item in material] if material else [f"- {empty}"]


def _branch_lines(branches: Any) -> list[str]:
    """渲染分支摘要，不把分支review-only包装为正式certificate。"""

    lines = []
    for branch in branches:
        lines.append(
            f"- `{branch['branch']}`: `{branch['status_value']}`; "
            f"claims={','.join(branch.get('claim_ids', ())) or 'none'}; "
            f"taint={','.join(branch.get('taint_values', ())) or 'none'}"
        )
    return lines or ["- 无分支"]


def _missing_review_lines(items: Any) -> list[str]:
    """渲染UNKNOWN事实的影响范围和可接受回答类型。"""

    lines: list[str] = []
    for item in items:
        lines.extend([
            f"### `{item['fact']}`",
            f"- reason: `{item['reason_value']}`",
            f"- impacted_rule_ids: `{','.join(item['rule_ids']) or 'none'}`",
            f"- impacted_claim_ids: `{','.join(item['claim_ids']) or 'none'}`",
            f"- allowed_answer_types: `{','.join(item['answer_types'])}`",
            f"- source_requirement: {item['source_need']}",
        ])
    return lines


def _clean_heading(value: Any) -> str:
    """限制profile标题为单行短文本。"""

    text = str(value).strip()
    if not text or len(text) > 80 or any(character in text for character in "\r\n<>"):
        raise RendererError("INVALID_RENDERER_PROFILE", "heading alias must be short plain text")
    if any(phrase.casefold() in text.casefold() for phrase in FORBIDDEN_CONCLUSION_PHRASES):
        raise RendererError("INVALID_RENDERER_PROFILE", "heading alias contains a forbidden conclusion phrase")
    return text


def _mermaid_label(value: str) -> str:
    """转义Mermaid标签中的不可信标识符。"""

    return html.escape(value.replace("\r", " ").replace("\n", " "), quote=True)[:240]


def _safe_run_component(run_id: str) -> str:
    """把逻辑run ID映射为本地跨平台目录名。"""

    return run_id.replace("::", "--")


def _atomic_write(path: Path, payload: bytes) -> None:
    """同目录临时文件写入后原子替换目标。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
