"""Proof trace visualizer — Mermaid flowchart output."""


def to_mermaid(trace: list) -> str:
    """Convert proof trace to Mermaid flowchart syntax."""
    lines = ["graph TD"]
    for i, event in enumerate(trace):
        if not isinstance(event, dict):
            continue
        etype = event.get("event_type", "?")
        rule_id = event.get("rule_id", "?")
        claim_id = event.get("claim_id", "?")
        node_id = f"N{i}"
        if etype == "RULE_APPLIED":
            lines.append(f'    {node_id}["{rule_id} → {claim_id[:20]}"]')
            if i > 0:
                lines.append(f"    N{i-1} --> {node_id}")
        elif etype == "RULE_REBUTTED":
            lines.append(f'    {node_id}["REBUTTED: {rule_id}"]')
            lines.append(f'    {node_id} style {node_id} fill:#f66')
            if i > 0:
                lines.append(f"    N{i-1} --> {node_id}")
        elif etype == "RULE_EXCEPTION_TRIGGERED":
            exc = event.get("triggered_exception", "?")
            lines.append(f'    {node_id}["EXCEPTION: {rule_id} → {exc[:15]}"]')
            lines.append(f'    {node_id} style {node_id} fill:#ff9')
            if i > 0:
                lines.append(f"    N{i-1} --> {node_id}")
    return "\n".join(lines)


def to_mermaid_md(trace: list) -> str:
    """Convert to Mermaid markdown block."""
    return f"```mermaid\n{to_mermaid(trace)}\n```"
