"""CanonicalResult到RenderedArtifact单向边界的基础输出防火墙。"""

from __future__ import annotations

from typing import Any, Mapping

from compiler_core.contracts import PROTECTED_RESULT_FIELDS

BLOCKED_FINAL_OPINION_STATUSES = {
    "hypothetical_result",
    "review_only_result",
    "missing_required_fact",
    "conflict_certificate",
    "engine_error",
}

FORBIDDEN_OUTPUT_FIELDS = {
    "final_conclusion",
    "final_legal_opinion",
    "court_will_rule",
    "formal_proof_claim",
    "legal_advice",
}

FORBIDDEN_CONCLUSION_PHRASES = (
    "court will rule",
    "definitive legal advice",
    "最终法律意见",
    "必然胜诉",
    "法院必然支持",
)


def renderer_firewall_metadata(result_status: str) -> dict[str, Any]:
    """Return machine metadata describing what a renderer may claim."""

    blocked = result_status in BLOCKED_FINAL_OPINION_STATUSES
    return {
        "formal_legal_opinion": False,
        "rendering_role": "review_packet" if blocked else "kernel_explanation",
        "machine_state_preserved": True,
        "may_render_final_conclusion": not blocked,
        "blocked_reason": "boundary_status_not_final" if blocked else "",
    }


def validate_output_contract(payload: Mapping[str, Any], *, result_status: str) -> dict[str, Any]:
    """递归拒绝渲染层伪造或覆盖正式字段，且不修改输入payload。"""

    forbidden = _forbidden_paths(payload)
    firewall = renderer_firewall_metadata(result_status)
    errors = []
    if forbidden:
        errors.append(f"forbidden output fields: {', '.join(forbidden)}")
    if result_status in BLOCKED_FINAL_OPINION_STATUSES and _contains_truthy_key(payload, "final_conclusion"):
        errors.append("blocked boundary result cannot carry final_conclusion")
    phrase_paths = _forbidden_phrase_paths(payload)
    if phrase_paths:
        errors.append(f"forbidden conclusion phrases: {', '.join(phrase_paths)}")
    return {
        "ok": not errors,
        "errors": errors,
        "renderer_firewall": firewall,
    }


def _forbidden_paths(value: Any, path: str = "$") -> list[str]:
    """递归定位越权字段路径；受保护结果字段不得由renderer重新声明。"""

    found: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            child = f"{path}.{key}"
            if key in FORBIDDEN_OUTPUT_FIELDS or key in PROTECTED_RESULT_FIELDS:
                found.append(child)
            found.extend(_forbidden_paths(nested, child))
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            found.extend(_forbidden_paths(nested, f"{path}[{index}]"))
    return sorted(found)


def _contains_truthy_key(value: Any, target: str) -> bool:
    """检查任意嵌套层是否声明非空结论字段。"""

    if isinstance(value, Mapping):
        return any((key == target and bool(nested)) or _contains_truthy_key(nested, target) for key, nested in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_truthy_key(item, target) for item in value)
    return False


def _forbidden_phrase_paths(value: Any, path: str = "$") -> list[str]:
    """递归定位断言式终局措辞；这是字段门禁之外的附加防线。"""

    found: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            found.extend(_forbidden_phrase_paths(nested, f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            found.extend(_forbidden_phrase_paths(nested, f"{path}[{index}]"))
    elif isinstance(value, str):
        normalized = value.casefold()
        if any(phrase.casefold() in normalized for phrase in FORBIDDEN_CONCLUSION_PHRASES):
            found.append(path)
    return sorted(found)

