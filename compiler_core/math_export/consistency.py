"""Cross-entry semantic consistency for C06 run witnesses.

The same canonical probe evaluated through the CLI, the ``JCClient``
facade and the MCP tool surface must yield the same mapped status, the
same mathematics subject fingerprint and the same input identity. Any
disagreement is a cross-entry inconsistency and fails the integration.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from compiler_core.math_export.witness import validate_witness

_COMPARED_FIELDS = (
    "schema_version",
    "status",
    "lmm_subject_fingerprint",
    "lmm_commit",
    "input_digest",
    "decision_status",
    "issues",
    "intake_error_code",
)


class CrossEntryInconsistency(RuntimeError):
    """Raised when public entries disagree about one probe case."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"CROSS_ENTRY_INCONSISTENT: {detail}")
        self.detail = detail


def assert_cross_entry_consistency(
    witnesses: Sequence[Mapping[str, Any]],
    *,
    required_entries: int = 3,
) -> dict[str, Any]:
    """Group witnesses by case and require agreement across entries.

    Returns a summary mapping each case id to its agreed status and the
    entries that produced it. Raises :class:`CrossEntryInconsistency` for
    missing entries, duplicate entries, digest mismatches, or any
    disagreement in the compared semantic fields.
    """

    by_case: dict[str, dict[str, Mapping[str, Any]]] = {}
    for witness in witnesses:
        validate_witness(witness)
        case = by_case.setdefault(str(witness["case_id"]), {})
        entry = str(witness["entry"])
        if entry in case:
            raise CrossEntryInconsistency(
                f"duplicate {entry} witness for {witness['case_id']}",
            )
        case[entry] = witness
    summary: dict[str, Any] = {}
    for case_id, entries in sorted(by_case.items()):
        if len(entries) < required_entries:
            raise CrossEntryInconsistency(
                f"{case_id}: {len(entries)} entries below the required "
                f"{required_entries}",
            )
        reference = next(iter(entries.values()))
        for entry, witness in sorted(entries.items()):
            for field in _COMPARED_FIELDS:
                if witness[field] != reference[field]:
                    raise CrossEntryInconsistency(
                        f"{case_id}: {entry} disagrees on {field}: "
                        f"{witness[field]!r} != {reference[field]!r}",
                    )
        summary[case_id] = {
            "status": reference["status"],
            "entries": sorted(entries),
            "agreement": True,
        }
    return summary
