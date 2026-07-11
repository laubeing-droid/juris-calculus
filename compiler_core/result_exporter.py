"""Result exporter — JSON/CSV/Markdown."""
import json
import csv
import io
from typing import Any, Mapping

from compiler_core.reasoning_boundary import ensure_required_audit_fields


def export_json(claims: list) -> str:
    data = [{"id": c.id, "confidence": c.confidence, "description": c.description[:200],
             "trust": c.get_trust_label()} for c in claims]
    return json.dumps(data, ensure_ascii=False, indent=2)


def export_csv(claims: list) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "confidence", "trust", "description"])
    for c in claims:
        writer.writerow([c.id, c.confidence, c.get_trust_label(), c.description[:200]])
    return output.getvalue()


def export_markdown(claims: list) -> str:
    lines = ["| ID | Confidence | Trust | Description |", "|---|---|---|---|"]
    for c in claims:
        lines.append(f"| {c.id} | {c.confidence:.2f} | {c.get_trust_label()} | {c.description[:60]} |")
    return "\n".join(lines)


def export_boundary_json(result: Mapping[str, Any]) -> str:
    """Export a reasoning-boundary result only when audit fields are present."""

    if not ensure_required_audit_fields(result):
        raise ValueError("boundary result is missing required audit fields")
    return json.dumps(dict(result), ensure_ascii=False, sort_keys=True, indent=2)
