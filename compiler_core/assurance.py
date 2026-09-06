"""V5 assurance envelope aggregation (ULM14; U08).

Every field aggregates by its own conservative rule and never by an average:
open obligations dominate spec status, crossCheckOnly dominates
implementation assurance, checkFailed dominates run checks, coverage and
legal-input carriers union (open obligations, exemptions, pending and assumed
references are all preserved). Only same-scope envelopes combine.

Default implementation assurance is crossCheckOnly; kernelVerified requires
the envelope itself to carry a nonempty trusted-computing-base reference set,
and even then it never claims Lean-level verification of the Python code.
"""

from __future__ import annotations

from compiler_core.contracts import (
    AssuranceEnvelopeV5,
    NotApplicableEvidenceV5,
    OpenObligationEntryV5,
)

_SPEC_ORDER = ("openObligations", "assumed", "proved")
_IMPLEMENTATION_ORDER = ("crossCheckOnly", "tcbSpecified", "kernelVerified")
_RUN_CHECK_ORDER = ("checkFailed", "unchecked", "checked")


class AssuranceV5Error(ValueError):
    """Stable fail-closed error for assurance aggregation."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise AssuranceV5Error(code, detail)


def _dominate(values: tuple[str, ...], order: tuple[str, ...]) -> str:
    for candidate in order:
        if candidate in values:
            return candidate
    _fail("ASSURANCE_FIELD", f"no value from {order} in {values!r}")


def _merge_obligations(*groups):
    merged: dict[tuple[str, str], OpenObligationEntryV5] = {}
    for group in groups:
        for obligation in group:
            merged.setdefault((obligation.code, obligation.detail), obligation)
    return tuple(sorted(merged.values(), key=lambda item: (item.code, item.detail)))


def _merge_refs(*groups) -> list[str]:
    merged: set[str] = set()
    for group in groups:
        merged.update(group)
    return sorted(merged)


def _merge_exemptions(*groups):
    merged: dict[tuple[str, str], NotApplicableEvidenceV5] = {}
    for group in groups:
        for exemption in group:
            merged.setdefault(
                (exemption.obligation, exemption.reason), exemption,
            )
    return tuple(sorted(merged.values(), key=lambda item: (item.obligation, item.reason)))


def combine_assurance_v5(left: AssuranceEnvelopeV5, right: AssuranceEnvelopeV5) -> AssuranceEnvelopeV5:
    """Combine two envelopes; different scopes are rejected, never averaged."""

    if (
        left.scope_request_ref != right.scope_request_ref
        or left.scope_profile != right.scope_profile
    ):
        _fail("ASSURANCE_SCOPE", "assurance envelopes may only combine within one scope")

    implementation = _dominate(
        (left.implementation, right.implementation), _IMPLEMENTATION_ORDER,
    )
    tcb_refs = _merge_refs(left.tcb_refs, right.tcb_refs)
    if implementation == "kernelVerified" and not tcb_refs:
        _fail("ASSURANCE_UPGRADE", "kernelVerified cannot survive aggregation without a TCB")

    from compiler_core.canonical_serialization import digest_value

    payload = {
        "scope_request_ref": str(left.scope_request_ref),
        "scope_profile": left.scope_profile,
        "spec": _dominate((left.spec, right.spec), _SPEC_ORDER),
        "implementation": implementation,
        "run_check": _dominate((left.run_check, right.run_check), _RUN_CHECK_ORDER),
        "coverage_open_obligations": [
            obligation.to_dict()
            for obligation in _merge_obligations(
                left.coverage_open_obligations, right.coverage_open_obligations,
            )
        ],
        "coverage_not_applicable": [
            exemption.to_dict()
            for exemption in _merge_exemptions(
                left.coverage_not_applicable, right.coverage_not_applicable,
            )
        ],
        "pending_refs": _merge_refs(left.pending_refs, right.pending_refs),
        "assumed_refs": _merge_refs(left.assumed_refs, right.assumed_refs),
        "open_spec_refs": _merge_refs(left.open_spec_refs, right.open_spec_refs),
        "formal_assumption_refs": _merge_refs(
            left.formal_assumption_refs, right.formal_assumption_refs,
        ),
        "tcb_refs": tcb_refs,
        "notices": [
            notice.to_dict()
            for notice in _merge_obligations(left.notices, right.notices)
        ],
    }
    payload["assurance_digest"] = str(digest_value(payload))
    return AssuranceEnvelopeV5.from_dict(payload)


def rebuild_digest(envelope: AssuranceEnvelopeV5) -> AssuranceEnvelopeV5:
    """Re-issue the envelope with its canonical self digest after edits."""

    from compiler_core.canonical_serialization import digest_value

    body = envelope.digest_body()
    return AssuranceEnvelopeV5.from_dict({
        **body,
        "assurance_digest": str(digest_value(body)),
    })
