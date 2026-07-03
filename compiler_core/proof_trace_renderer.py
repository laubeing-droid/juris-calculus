"""Proof trace renderer — converts JSON proof traces to Chinese natural language."""

from typing import Any, Mapping


def format_proof_trace_cn(trace: list) -> str:
    """Format proof trace as readable Chinese text.

    Example output:
    "规则 PC-001 触发：前提（国家赔偿 + 违法行为）满足 → 结论：赔偿责任成立。置信度 0.9。"
    """
    if not trace:
        return "无推理轨迹。"

    lines = []
    for event in trace:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type", "")
        rule_id = event.get("rule_id", "?")
        claim_id = event.get("claim_id", "?")
        premises = event.get("premises", [])
        confidence = event.get("confidence", None)

        if event_type == "RULE_APPLIED":
            prem_str = " + ".join(premises[:3]) if premises else "无前提"
            conf_str = f"。置信度 {confidence:.2f}" if confidence is not None else ""
            lines.append(f"规则 {rule_id} 触发：前提（{prem_str}）满足 → 结论：{claim_id}{conf_str}")
        elif event_type == "RULE_EXCEPTION_TRIGGERED":
            exc = event.get("triggered_exception", "?")
            lines.append(f"规则 {rule_id} 的例外 {exc} 被触发，转向例外规则")
        elif event_type == "RULE_REBUTTED":
            trigger = event.get("trigger_fact", "?")
            lines.append(f"规则 {rule_id} 被反驳：触发事实 {trigger} → 置信度归零")
        elif event_type == "OBLIGATION_GAP":
            missing = event.get("missing_premises", [])
            lines.append(f"规则 {rule_id} 存在义务缺口：缺少 {', '.join(missing[:3])}")
        elif event_type == "PROHIBITION_BLOCK":
            lines.append(f"规则 {rule_id} 触发禁止：{claim_id} 被阻止")
        elif event_type == "FORCED_STATE_APPLIED":
            action = event.get("action", "")
            new_st = event.get("new_state", "")
            lines.append(f"强制收敛：{rule_id} → {action} → {new_st}")
        else:
            lines.append(f"[{event_type}] {rule_id}: {claim_id}")

    return "\n".join(lines) if lines else "无推理轨迹。"


def format_boundary_result_cn(result: Mapping[str, Any]) -> str:
    """Render a boundary result without turning it into legal advice."""

    status = str(result.get("result_status", "unknown"))
    used_facts = ", ".join(result.get("used_fact_keys", [])[:5]) or "无"
    if status == "hypothetical_result":
        return f"边界状态：假设结果；使用事实：{used_facts}；不得作为正式法律意见。"
    if status == "review_only_result":
        return f"边界状态：仅供复核；使用事实：{used_facts}；需要人工确认替代路径。"
    if status == "missing_required_fact":
        return f"边界状态：缺少必要事实；使用事实：{used_facts}；不得输出确定结论。"
    if status == "conflict_certificate":
        return f"边界状态：冲突证书；使用事实：{used_facts}；不自动裁判优先级。"
    if status == "engine_error":
        return "边界状态：运行错误；不得转换为法律建议。"
    return f"边界状态：{status}；使用事实：{used_facts}。"
