"""V5 incremental Horn safety and the read-only empirical channel (ULM15; U09).

The add-only fast path is valid only for Horn facts/rules added inside one
fixed finite universe. Every non-monotonic change (deletion, revocation, rule
rewrite, profile change, mapping change, assumption-set change, universe
growth) invalidates the child subject and forces full recomputation. Horn
monotonicity says nothing about downstream Dung labels, procedure outputs or
composition: those layers always recompute.

The empirical channel is read-only by construction: empirical artifacts are
addressed and digested separately from normative outputs, and no function in
this module accepts an empirical value into a normative computation. Without
a model or evaluation reference there is no estimate — the honest return is a
typed absence, never a number.
"""

from __future__ import annotations

from dataclasses import dataclass

from compiler_core.canonical_serialization import digest_value
from compiler_core.contracts import DigestV4, EmpiricalResultV5, HornDeltaV5


class IncrementalV5Error(ValueError):
    """Stable fail-closed error for the incremental layer."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise IncrementalV5Error(code, detail)


def _subject_digest(
    universe: frozenset[str],
    facts: frozenset[str],
    rules: tuple[tuple[str, tuple[str, ...]], ...],
) -> DigestV4:
    return DigestV4(digest_value({
        "universe": sorted(universe),
        "facts": sorted(facts),
        "rules": [[head, sorted(body)] for head, body in sorted(rules)],
    }))


@dataclass(frozen=True, slots=True)
class HornSubjectV5:
    """A Horn subject: fixed universe, facts, and rules over that universe."""

    universe: frozenset[str]
    facts: frozenset[str]
    rules: tuple[tuple[str, tuple[str, ...]], ...]
    subject_digest: DigestV4

    def __post_init__(self) -> None:
        outside = (set(self.facts) | {head for head, _ in self.rules}) - set(self.universe)
        if outside:
            _fail(
                "HORN_UNIVERSE_ESCAPE",
                f"subject leaves its fixed universe: {sorted(outside)[:3]}",
            )
        expected = _subject_digest(self.universe, self.facts, self.rules)
        if str(self.subject_digest) != str(expected):
            _fail(
                "HORN_SUBJECT_DIGEST",
                "subject_digest does not bind universe, facts, and rules",
            )

    @classmethod
    def build(
        cls, universe: frozenset[str], facts: frozenset[str],
        rules: tuple[tuple[str, tuple[str, ...]], ...],
    ) -> "HornSubjectV5":
        return cls(
            universe=universe, facts=facts, rules=tuple(sorted(rules)),
            subject_digest=_subject_digest(universe, facts, tuple(sorted(rules))),
        )


def horn_closure(subject: HornSubjectV5) -> frozenset[str]:
    """Least fixed point of the immediate-consequence operator (proved core)."""

    derived: set[str] = set(subject.facts)
    changed = True
    while changed:
        changed = False
        for head, body in subject.rules:
            if head in derived:
                continue
            if all(atom in derived for atom in body):
                derived.add(head)
                changed = True
    return frozenset(derived)


def validate_add_only_delta(
    parent: HornSubjectV5,
    delta: HornDeltaV5,
    added_rules: tuple[tuple[str, tuple[str, ...]], ...],
) -> None:
    """Reject every non-monotonic delta shape before any fast path runs."""

    if str(parent.subject_digest) != str(delta.parent_subject_digest):
        _fail("HORN_PARENT_MISMATCH", "delta does not bind the parent subject")
    added = set(delta.added_facts)
    if not added <= set(parent.universe):
        _fail("HORN_UNIVERSE_GROWTH", "delta adds facts outside the fixed universe")
    if not added.isdisjoint(parent.facts):
        _fail("HORN_DELTA_REDELIVERY", "delta re-adds existing facts")
    for head, body in added_rules:
        if head not in parent.universe or any(atom not in parent.universe for atom in body):
            _fail("HORN_UNIVERSE_GROWTH", "delta adds rules outside the fixed universe")
    if (parent.facts | {head for head, _ in parent.rules}) & {head for head, _ in added_rules}:
        # re-adding a head is allowed (OR-route), but an identical rule body is a redelivery
        if set(added_rules) & set(parent.rules):
            _fail("HORN_DELTA_REDELIVERY", "delta re-adds an existing rule")


def add_only_child(
    parent: HornSubjectV5,
    delta: HornDeltaV5,
    added_rules: tuple[tuple[str, tuple[str, ...]], ...],
) -> HornSubjectV5:
    """Build the child subject under the add-only contract (universe unchanged)."""

    validate_add_only_delta(parent, delta, added_rules)
    child = HornSubjectV5.build(
        universe=parent.universe,
        facts=parent.facts | set(delta.added_facts),
        rules=(*parent.rules, *added_rules),
    )
    if str(child.subject_digest) != str(delta.child_subject_digest):
        _fail("HORN_CHILD_MISMATCH", "delta does not bind the recomputed child subject")
    return child


def incremental_matches_full_recompute(
    parent: HornSubjectV5,
    delta: HornDeltaV5,
    added_rules: tuple[tuple[str, tuple[str, ...]], ...],
) -> bool:
    """IncrementalImplementationCorrect observation for one delta.

    The fast path is only ever trusted when it equals the independent full
    recomputation of the extended subject; the comparison result is the
    acceptance evidence, not an assumption.
    """

    child = add_only_child(parent, delta, added_rules)
    extended = HornSubjectV5.build(
        universe=parent.universe,
        facts=parent.facts | set(delta.added_facts),
        rules=(*parent.rules, *added_rules),
    )
    return horn_closure(child) == horn_closure(extended)


def requires_full_recompute(
    *,
    deleted_facts: tuple[str, ...] = (),
    revoked_attestations: tuple[str, ...] = (),
    rule_rewrites: tuple[str, ...] = (),
    profile_changed: bool = False,
    mapping_changed: bool = False,
    assumptions_changed: bool = False,
    universe_growth: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Name the non-monotonic changes that invalidate an incremental subject."""

    reasons: list[str] = []
    if deleted_facts:
        reasons.append("fact_deletion")
    if revoked_attestations:
        reasons.append("attestation_revocation")
    if rule_rewrites:
        reasons.append("rule_rewrite")
    if profile_changed:
        reasons.append("profile_change")
    if mapping_changed:
        reasons.append("mapping_change")
    if assumptions_changed:
        reasons.append("assumption_set_change")
    if universe_growth:
        reasons.append("universe_growth")
    return tuple(reasons)


@dataclass(frozen=True, slots=True)
class EmpiricalEstimateV5:
    """A read-only empirical observation bound to one normative subject."""

    normative_subject_digest: DigestV4
    result: EmpiricalResultV5 | None
    absent_reason: str | None = None

    def __post_init__(self) -> None:
        if self.result is None and not self.absent_reason:
            _fail(
                "EMPIRICAL_ABSENCE_UNRECORDED",
                "without a result the honest absence reason must be recorded",
            )
        if self.result is not None and self.absent_reason:
            _fail("EMPIRICAL_STATE", "result and absence reason are mutually exclusive")


def attach_empirical_v5(
    normative_subject_digest: DigestV4,
    *,
    result: EmpiricalResultV5 | None = None,
    absent_reason: str | None = None,
) -> EmpiricalEstimateV5:
    """Attach (or honestly decline) an empirical estimate for one subject."""

    if result is None and absent_reason is None:
        absent_reason = "no-verified-empirical-model"
    return EmpiricalEstimateV5(
        normative_subject_digest=normative_subject_digest,
        result=result,
        absent_reason=absent_reason,
    )
