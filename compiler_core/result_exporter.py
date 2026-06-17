"""Result exporter — JSON/CSV/Markdown."""
import json
import csv
import io
from typing import List, Any


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
