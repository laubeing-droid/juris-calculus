"""Sole typed authority for append-only V4 semantic audit events."""

from __future__ import annotations

from dataclasses import dataclass
import re

from compiler_core.contracts import ContentRefV4, ContractV4Error


EVENT_SCHEMA_V4 = "jc/audit-event/4.0"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


@dataclass(frozen=True, slots=True)
class AuditEventV4:
    """One canonical event reference in a run's contiguous append-only stream."""

    sequence: int
    stage: str
    artifact_ref: ContentRefV4

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ContractV4Error(
                "AUDIT_EVENT", "event sequence must be a non-negative integer"
            )
        if type(self.stage) is not str or _IDENTIFIER.fullmatch(self.stage) is None:
            raise ContractV4Error(
                "AUDIT_IDENTIFIER", "event stage is not a logical identifier"
            )
        if type(self.artifact_ref) is not ContentRefV4:
            raise ContractV4Error(
                "AUDIT_EVENT", "event artifact_ref must be ContentRefV4"
            )

    def to_wire(self, run_identity_ref: ContentRefV4) -> dict[str, object]:
        if type(run_identity_ref) is not ContentRefV4:
            raise ContractV4Error(
                "AUDIT_EVENT", "run_identity_ref must be ContentRefV4"
            )
        return {
            "schema_version": EVENT_SCHEMA_V4,
            "sequence": self.sequence,
            "stage": self.stage,
            "run_identity_ref": run_identity_ref.to_dict(),
            "artifact_ref": self.artifact_ref.to_dict(),
        }


__all__ = ["AuditEventV4", "EVENT_SCHEMA_V4"]
