"""V5 procedure and burden-of-proof consequences (ULM12; U06).

Implements the frozen decision table of JC-UPGRADE-20260906-01 section 8 as a
total four-way function. This layer never simulates judicial authority: a
reviewer string is only usable when the caller has verified the authorization
reference through the trust machinery; an unverified authority is a pending
state, never the success branch.

    | semantic solve        | procedural input      | authorized finding | output                |
    |-----------------------|-----------------------|--------------------|-----------------------|
    | incomplete            | any                   | any                | solverIncomplete      |
    | complete (all kinds)  | valid pure procedural | any                | proceduralDisposition |
    | complete              | none                  | valid satisfied    | success consequence   |
    | complete              | none                  | valid unmet        | failure consequence   |
    | complete              | none                  | none / unverified  | pendingLegalJudgment  |
"""

from __future__ import annotations

from dataclasses import dataclass

from compiler_core.canonical_serialization import DigestV4
from compiler_core.contracts import (
    OpenObligationEntryV5,
    ProcedureAuthorityV5,
    ProcedureResultV5,
)

_EVALUATION_KINDS = frozenset({"no_extension", "extensions", "incomplete"})


class ProcedureV5Error(ValueError):
    """Stable fail-closed error for the procedure layer."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise ProcedureV5Error(code, detail)


@dataclass(frozen=True, slots=True)
class BurdenRuleOutcomeV5:
    """The entity consequences declared by one admitted burden rule."""

    satisfied_status: str
    failure_status: str

    def __post_init__(self) -> None:
        for field_name in ("satisfied_status", "failure_status"):
            value = getattr(self, field_name)
            if type(value) is not str or not value:
                _fail("PROCEDURE_RULE_FIELD", f"{field_name} must be a non-empty status")


def adjudicate_v5(
    *,
    request_ref: DigestV4,
    evaluation_kind: str,
    evaluation_open_obligations: tuple[OpenObligationEntryV5, ...] = (),
    procedural_status: str | None = None,
    authority: ProcedureAuthorityV5 | None = None,
    authorization_verified: bool = False,
    rule_outcomes: BurdenRuleOutcomeV5 | None = None,
) -> ProcedureResultV5:
    """Return the frozen four-way procedure output for one completed solve."""

    if evaluation_kind not in _EVALUATION_KINDS:
        _fail("PROCEDURE_EVALUATION", f"unsupported evaluation kind {evaluation_kind!r}")

    if evaluation_kind == "incomplete":
        obligations = evaluation_open_obligations or (
            OpenObligationEntryV5("solver_incomplete", "semantic solve did not finish"),
        )
        return ProcedureResultV5(
            request_ref=request_ref,
            kind="solver_incomplete",
            status=None,
            missing=(),
            open_obligations=obligations,
            authority_ref=None,
        )

    if procedural_status is not None:
        if type(procedural_status) is not str or not procedural_status:
            _fail("PROCEDURE_INPUT", "procedural status must be a non-empty string")
        return ProcedureResultV5(
            request_ref=request_ref,
            kind="procedural_disposition",
            status=procedural_status,
            missing=(),
            open_obligations=(),
            authority_ref=None,
        )

    if authority is None or not authorization_verified:
        missing = "authorization-unverified" if authority is not None else "burden-rule-or-finding"
        return ProcedureResultV5(
            request_ref=request_ref,
            kind="pending_legal_judgment",
            status=None,
            missing=(missing,),
            open_obligations=(),
            authority_ref=None,
        )

    if rule_outcomes is None:
        _fail("PROCEDURE_RULE_MISSING", "a verified authority needs its admitted rule outcomes")
    if rule_outcomes.satisfied_status == rule_outcomes.failure_status:
        _fail("PROCEDURE_RULE_AMBIGUOUS", "success and failure consequences must differ")

    status = (
        rule_outcomes.satisfied_status
        if authority.finding == "satisfied"
        else rule_outcomes.failure_status
    )
    return ProcedureResultV5(
        request_ref=request_ref,
        kind="adjudicated_status",
        status=status,
        missing=(),
        open_obligations=(),
        authority_ref=authority.authorization_ref,
    )
