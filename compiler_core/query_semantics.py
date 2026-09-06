"""V5 branch query semantics (ULM11; JC-UPGRADE-20260906-01 U05).

Internal pure-function layer over the bounded profile families produced by
``compiler_core.argumentation.evaluate_profile_v5``. The wire result is
``contracts.QueryResultV5``; this module computes the multi-flag status
vector with per-branch witnesses and keeps the ULM11 distinctions:

- Argument OUT is not claim refutation: refutation requires an explicit,
  directed QueryRefutation relation with an accepted refuting argument.
- Undecided requires the query to be enterable in that branch.
- An empty extension family never yields a vacuous ``common``.
- An incomplete search reports witnesses for discovered branches only.
"""

from __future__ import annotations

from dataclasses import dataclass

from compiler_core.argumentation import ArgumentationV4Error, ProfileEvaluationV5

_QUERY_PROFILES = frozenset({"grounded", "preferred", "stable", "complete"})


class QuerySemanticsV5Error(ValueError):
    """Stable fail-closed error for the V5 query layer."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise QuerySemanticsV5Error(code, detail)


@dataclass(frozen=True, slots=True)
class QueryRefutationV5:
    """Directed refutation: ``refuter``'s acceptance defeats ``target``.

    Direction is explicit; symmetry is never assumed and reflexive pairs are
    rejected.
    """

    refuter: str
    target: str

    def __post_init__(self) -> None:
        for field_name in ("refuter", "target"):
            value = getattr(self, field_name)
            if type(value) is not str or not value:
                _fail("QUERY_FIELD", f"{field_name} must be a non-empty claim id")
        if self.refuter == self.target:
            _fail("QUERY_REFUTATION_IRREFLEXIVE", "a claim cannot refute itself")


@dataclass(frozen=True, slots=True)
class GateStateV5:
    """Per-branch query gate; excluded branches carry a reason."""

    branch_index: int
    state: str
    reason: str = ""

    def __post_init__(self) -> None:
        if self.state not in ("enterable", "excluded", "incomplete"):
            _fail("QUERY_GATE_STATE", f"unsupported gate state {self.state!r}")
        if self.state == "excluded" and not self.reason:
            _fail("QUERY_GATE_STATE", "excluded branches must record a reason")


@dataclass(frozen=True, slots=True)
class QueryInputV5:
    """One query against one evaluated profile family."""

    query_id: str
    claim: str
    profile: str
    evaluation: ProfileEvaluationV5
    argument_claims: dict[str, str]
    refutations: tuple[QueryRefutationV5, ...] = ()
    gates: tuple[GateStateV5, ...] = ()

    def __post_init__(self) -> None:
        if type(self.query_id) is not str or not self.query_id:
            _fail("QUERY_FIELD", "query_id must be a non-empty string")
        if type(self.claim) is not str or not self.claim:
            _fail("QUERY_FIELD", "claim must be a non-empty string")
        if self.profile not in _QUERY_PROFILES:
            _fail("QUERY_FIELD", f"unsupported profile {self.profile!r}")
        if self.evaluation.profile != self.profile:
            _fail("QUERY_FIELD", "query profile does not match the evaluated family")
        if not isinstance(self.argument_claims, dict) or not self.argument_claims:
            _fail("QUERY_FIELD", "argument_claims must map every argument to its claim")


@dataclass(frozen=True, slots=True)
class QueryStatusV5:
    """The multi-flag answer with witnesses; wire form is contracts.QueryResultV5."""

    query_id: str
    profile: str
    common: bool
    possible: bool
    common_refuted: bool
    possibly_refuted: bool
    undecided_some: bool
    inconsistent_some: bool
    excluded: bool
    gate: str
    acceptance_witnesses: tuple[str, ...]
    refutation_witnesses: tuple[str, ...]


def evaluate_query_v5(query: QueryInputV5) -> QueryStatusV5:
    """Compute the ULM11 status vector over enterable extensions only."""

    evaluation = query.evaluation
    gates = list(query.gates)
    if gates and len(gates) != len(evaluation.extensions):
        _fail(
            "QUERY_GATE_COUNT",
            "gate states must cover the extension family exactly when present",
        )
    if not gates:
        if evaluation.extensions:
            gates = [
                GateStateV5(index, "enterable")
                for index in range(len(evaluation.extensions))
            ]
        else:
            gates = []

    enterable = [
        index for index, gate in enumerate(gates) if gate.state == "enterable"
    ]
    excluded = [gate for gate in gates if gate.state == "excluded"]
    incomplete = [gate for gate in gates if gate.state == "incomplete"]
    if not enterable and not excluded and not incomplete and gates:
        _fail("QUERY_GATE_STATE", "family has no branch gates")

    refuted_by: dict[str, set[str]] = {}
    for pair in query.refutations:
        refuted_by.setdefault(pair.target, set()).add(pair.refuter)

    accepting: list[str] = []
    refuting: list[str] = []
    common = common_refuted = True
    undecided_some = inconsistent_some = False
    for index in enterable:
        extension = evaluation.extensions[index]
        claim_arguments = [
            argument for argument in sorted(extension)
            if query.argument_claims.get(argument) == query.claim
        ]
        accepts = bool(claim_arguments)
        refuters = [
            argument for argument in sorted(extension)
            if argument in refuted_by.get(query.claim, ())
        ]
        refutes = bool(refuters)
        if accepts:
            accepting.extend(claim_arguments)
        if refutes:
            refuting.extend(refuters)
        common = common and accepts
        common_refuted = common_refuted and refutes
        if accepts and refutes:
            inconsistent_some = True
        if not accepts and not refutes:
            undecided_some = True
    possible = any(
        query.argument_claims.get(argument) == query.claim
        for index in enterable
        for argument in evaluation.extensions[index]
    )
    possibly_refuted = any(
        argument in refuted_by.get(query.claim, ())
        and query.argument_claims.get(argument) == query.claim
        for index in enterable
        for argument in evaluation.extensions[index]
    )

    if not enterable:
        # No enterable branch: the family either excluded the query everywhere
        # or its gates are incomplete; no status may be reported.
        common = possible = common_refuted = possibly_refuted = False
        undecided_some = inconsistent_some = False
        if excluded and not incomplete:
            return QueryStatusV5(
                query.query_id, query.profile,
                False, False, False, False, False, False,
                True, "excluded", (), (),
            )
        return QueryStatusV5(
            query.query_id, query.profile,
            False, False, False, False, False, False,
            False, "incomplete", (), (),
        )

    if evaluation.kind == "incomplete" or incomplete:
        # Discovered-branch witnesses only; a partially observed gate or an
        # unexplored family can never carry a universal claim.
        common = False
        common_refuted = False
        gate = "incomplete" if evaluation.kind == "incomplete" else "enterable"
    elif evaluation.kind == "no_extension":
        # An empty extension family admits no vacuous universal claims.
        common = possible = common_refuted = possibly_refuted = False
        undecided_some = inconsistent_some = False
        gate = "enterable"
    else:
        gate = "enterable"

    return QueryStatusV5(
        query.query_id, query.profile,
        common, possible, common_refuted, possibly_refuted,
        undecided_some, inconsistent_some, False, gate,
        tuple(sorted(set(accepting))), tuple(sorted(set(refuting))),
    )


def compose_branch_key_v5(
    scenario_id: str,
    assumptions: tuple[str, ...],
    profile: str,
    extension: frozenset[str],
) -> tuple[str, str, str]:
    """Return the deterministic branch identity components for one extension.

    Branch isolation is enforced by construction: different assumptions,
    profiles or extension structures produce different keys. Cross-branch
    composition of responsibilities and amounts stays rejected downstream.
    """

    if profile not in _QUERY_PROFILES:
        _fail("QUERY_FIELD", f"unsupported profile {profile!r}")
    return scenario_id, "|".join(sorted(assumptions)), profile + "#" + "|".join(sorted(extension))
