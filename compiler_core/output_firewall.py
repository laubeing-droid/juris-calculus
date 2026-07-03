"""Renderer and output firewall for LSC boundary packets."""

from __future__ import annotations

from typing import Any, Mapping

BLOCKED_FINAL_OPINION_STATUSES = {
    "hypothetical_result",
    "review_only_result",
    "missing_required_fact",
    "conflict_certificate",
    "engine_error",
}

FORBIDDEN_OUTPUT_FIELDS = {
    "final_legal_opinion",
    "court_will_rule",
    "formal_proof_claim",
    "legal_advice",
}


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
    """Validate that rendered output does not overclaim boundary results."""

    forbidden = sorted(FORBIDDEN_OUTPUT_FIELDS.intersection(payload.keys()))
    firewall = renderer_firewall_metadata(result_status)
    errors = []
    if forbidden:
        errors.append(f"forbidden output fields: {', '.join(forbidden)}")
    if result_status in BLOCKED_FINAL_OPINION_STATUSES and payload.get("final_conclusion"):
        errors.append("blocked boundary result cannot carry final_conclusion")
    return {
        "ok": not errors,
        "errors": errors,
        "renderer_firewall": firewall,
    }

