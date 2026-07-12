"""Track C0: Four-stage no-uncertainty-upgrade -- CompletionStatus & StageResult."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, TypeVar

from compiler_core.version import __version__

T = TypeVar("T")
C = TypeVar("C")


class CompletionStatus(Enum):
    COMPLETE = "complete"
    TRUNCATED = "truncated"
    UNKNOWN = "unknown"
    ERROR = "error"
    INCOMPATIBLE = "incompatible"
    VERIFICATION_FAILED = "verification_failed"


@dataclass(frozen=True)
class StageResult(Generic[T, C]):
    status: CompletionStatus
    value: T | None
    certificate: C | None
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)
    input_digest: str = ""
    producer_version: str = field(default_factory=lambda: f"v{__version__}")


# --- Core Property: no_uncertainty_upgrade ---

def no_uncertainty_upgrade(*upstream: StageResult) -> bool:
    """Return True if all upstream stages are COMPLETE.

    Per C0 contract: upstream incomplete => downstream MUST NOT produce
    definitive output. This function gates all downstream computation.
    """
    return all(s.status == CompletionStatus.COMPLETE for s in upstream)


# --- Trust Label Mapping ---

TRUST_LABEL_MAP = {
    (CompletionStatus.COMPLETE, True): "ALLOWED / FORBIDDEN / UNDECIDED",
    (CompletionStatus.TRUNCATED, False): "INCOMPLETE_REASONING",
    (CompletionStatus.INCOMPATIBLE, False): "INCOMPLETE_ATTACK_GRAPH",
    (CompletionStatus.UNKNOWN, False): "COMPUTATION_UNKNOWN",
    (CompletionStatus.VERIFICATION_FAILED, False): "VERIFICATION_FAILED",
    (CompletionStatus.ERROR, False): "UNGROUNDED_SOURCE",
}


def compute_trust_label(
    horn: StageResult,
    aaf: StageResult,
    grounded: StageResult,
    cert_valid: bool,
) -> str:
    """Compute Trust Label from four stages, enforcing no-uncertainty-upgrade.

    If any upstream stage is not COMPLETE, the label reflects the
    lowest-fidelity failure, never a definitive conclusion.
    """
    if not no_uncertainty_upgrade(horn, aaf, grounded):
        for stage in (horn, aaf, grounded):
            if stage.status != CompletionStatus.COMPLETE:
                return TRUST_LABEL_MAP.get((stage.status, False), "UNKNOWN")
    if not cert_valid:
        return TRUST_LABEL_MAP[(CompletionStatus.VERIFICATION_FAILED, False)]
    return TRUST_LABEL_MAP[(CompletionStatus.COMPLETE, True)]
