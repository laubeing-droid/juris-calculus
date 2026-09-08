"""The stable Harness-facing integration contract (JC <-> Legal Harness).

This module is the closed surface the Legal Harness talks to. It translates
between the Harness's case-level vocabulary (issues, admitted/assumed/
disputed facts, attack and priority inputs, scenarios) and the sole formal
spine (:class:`compiler_core.application.ApplicationV4`), and projects the
sealed run artifacts back into one readable result object per legal issue.
The Harness never parses JC-internal debug JSON: everything it may read is a
field of :class:`HarnessIssueResultV5` / :class:`HarnessRunResultV5`.

Boundary (fixed by JC-FINAL-FIX-20260908):

    Legal Harness = case orchestration (materials, issue spotting, drafting)
    juris-calculus = formal reasoning kernel over admitted structured inputs

The request builder here only assembles typed V5 inputs onto the existing
public ``CaseRequestV4``; admission, signing, trust and storage stay inside
the existing chain services. Synthetic-sample signing lives in the test
harness, not in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from compiler_core.application import (
    ApplicationV4,
    HORN_SUBJECT_STATE_KIND_V5,
    PROFILE_STAGE_KIND_V5,
)
from compiler_core.canonical_serialization import (
    DigestV4,
    parse_json_document,
)
from compiler_core.contracts import (
    CaseRequestV4,
    ClaimRefutationV5,
    ContentRefV4,
    EvaluationEnvelopeV4,
    IncrementalParentV5,
    OpenObligationEntryV5,
    ProceduralInputV5,
    QueryGateRequestV5,
)
from compiler_core.independent_checker import CHECKER_SCOPE
from compiler_core.rule_packs import JSON_MEDIA_TYPE

HARNESS_CONTRACT_VERSION = "jc-harness-contract/1"


class HarnessContractError(ValueError):
    """Stable fail-closed error for the Harness-facing surface."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class HarnessPriorityInput:
    """One admitted priority relation between two rule conclusions."""

    preferred: str
    defeated: str


@dataclass(frozen=True, slots=True)
class HarnessAttackInput:
    """One admitted attack between two rule conclusions."""

    attacker: str
    target: str
    kind: str = "rebut"


@dataclass(frozen=True, slots=True)
class HarnessQueryInput:
    """One requested legal issue bound to one Dung profile."""

    issue_id: str
    claim: str
    profile: str
    excluded_branch_reasons: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HarnessRunRequest:
    """Everything the Harness sends for one evaluation.

    Facts and rules are admitted upstream through the chain's admission
    services (signed attestations, verified rule packs); this request only
    carries the V5 reasoning inputs plus the parent reference for the
    add-only incremental fast path.
    """

    case_id: str
    request: CaseRequestV4
    queries: tuple[HarnessQueryInput, ...]
    refutations: tuple[ClaimRefutationV5, ...] = ()
    gates: tuple[QueryGateRequestV5, ...] = ()
    procedural: ProceduralInputV5 | None = None
    incremental_parent: IncrementalParentV5 | None = None
    priority_relations: tuple[HarnessPriorityInput, ...] = ()
    attacks: tuple[HarnessAttackInput, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness_contract_version": HARNESS_CONTRACT_VERSION,
            "case_id": self.case_id,
            "request_ref": self.request.to_dict(),
            "queries": [
                {
                    "issue_id": item.issue_id,
                    "claim": item.claim,
                    "profile": item.profile,
                }
                for item in self.queries
            ],
            "refutations": [item.to_dict() for item in self.refutations],
            "gates": [item.to_dict() for item in self.gates],
            "procedural": None if self.procedural is None else self.procedural.to_dict(),
            "incremental_parent": (
                None if self.incremental_parent is None
                else self.incremental_parent.to_dict()
            ),
            "priority_relations": [
                {"preferred": item.preferred, "defeated": item.defeated}
                for item in self.priority_relations
            ],
            "attacks": [
                {"attacker": item.attacker, "target": item.target, "kind": item.kind}
                for item in self.attacks
            ],
        }


@dataclass(frozen=True, slots=True)
class HarnessIssueResultV5:
    """The readable answer for one legal issue (JC -> Harness projection)."""

    issue_id: str
    claim: str
    profile: str
    gate: str
    accepted: bool
    possibly_accepted: bool
    refuted: bool
    possibly_refuted: bool
    undecided_some: bool
    inconsistent_some: bool
    excluded: bool
    acceptance_witnesses: tuple[str, ...]
    refutation_witnesses: tuple[str, ...]
    branch_refs: tuple[str, ...]
    mapping_complete: bool

    def conclusion_status(self) -> str:
        """One human-readable status word for display layers."""

        if self.excluded:
            return "excluded"
        if self.gate == "incomplete":
            return "incomplete"
        if self.inconsistent_some:
            return "inconsistent"
        if self.accepted:
            return "accepted"
        if self.refuted:
            return "refuted"
        if self.possibly_accepted or self.possibly_refuted:
            return "possible"
        return "undecided"

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "claim": self.claim,
            "profile": self.profile,
            "conclusion_status": self.conclusion_status(),
            "gate": self.gate,
            "accepted": self.accepted,
            "possibly_accepted": self.possibly_accepted,
            "refuted": self.refuted,
            "possibly_refuted": self.possibly_refuted,
            "undecided_some": self.undecided_some,
            "inconsistent_some": self.inconsistent_some,
            "excluded": self.excluded,
            "acceptance_witnesses": list(self.acceptance_witnesses),
            "refutation_witnesses": list(self.refutation_witnesses),
            "branch_refs": list(self.branch_refs),
            "mapping_complete": self.mapping_complete,
        }


@dataclass(frozen=True, slots=True)
class HarnessRunResultV5:
    """The closed JC -> Harness result for one evaluation.

    ``artifact_refs`` points at the sealed audit bundle files an external
    reader may verify through the existing read/verify surface; nothing in
    this object requires parsing JC-internal debug JSON.
    """

    case_id: str
    run_status: str
    decision_status: str
    completeness: str
    issues: tuple[HarnessIssueResultV5, ...]
    procedure_kinds: tuple[str, ...]
    open_obligations: tuple[OpenObligationEntryV5, ...]
    missing_fact_keys: tuple[str, ...]
    admitted_fact_keys: tuple[str, ...]
    assumed_fact_keys: tuple[str, ...]
    horn_mode: str
    horn_fallback_reason: str | None
    horn_parent_binding: str | None
    horn_solver_work: int
    horn_checker_work: int
    assurance_specs: tuple[str, ...]
    composition_value: Mapping[str, Any] | None
    artifact_refs: tuple[Mapping[str, str], ...]
    audit_manifest_ref: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "harness_contract_version": HARNESS_CONTRACT_VERSION,
            "case_id": self.case_id,
            "run_status": self.run_status,
            "decision_status": self.decision_status,
            "completeness": self.completeness,
            "issues": [item.to_dict() for item in self.issues],
            "procedure_kinds": list(self.procedure_kinds),
            "open_obligations": [item.to_dict() for item in self.open_obligations],
            "missing_fact_keys": list(self.missing_fact_keys),
            "admitted_fact_keys": list(self.admitted_fact_keys),
            "assumed_fact_keys": list(self.assumed_fact_keys),
            "horn": {
                "mode": self.horn_mode,
                "fallback_reason": self.horn_fallback_reason,
                "parent_binding": self.horn_parent_binding,
                "solver_rule_evaluations": self.horn_solver_work,
                "checker_rule_evaluations": self.horn_checker_work,
            },
            "assurance_specs": list(self.assurance_specs),
            "composition": self.composition_value,
            "artifact_refs": [dict(item) for item in self.artifact_refs],
            "audit_manifest_ref": dict(self.audit_manifest_ref),
        }


def _stage_documents(
    application: ApplicationV4,
    envelope: EvaluationEnvelopeV4,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Recover the sealed V5 stage / Horn state documents for this run.

    Reads exactly what an external verifier reads: the verified audit bundle
    of this run, with the stage artifacts addressed by their content refs.
    """

    stage: dict[str, Any] | None = None
    horn: dict[str, Any] | None = None
    try:
        capability = application._audit_store.capability_for(
            ContentRefV4("run-identity", envelope.run_identity.canonical_digest())
        )
        verified = application._audit_store.verify_run(
            capability, now=application._clock(),
        )
    except Exception:
        return stage, horn
    from base64 import b64decode

    for name in sorted(verified.files):
        try:
            payload = parse_json_document(verified.files[name])
        except ValueError:
            continue
        if type(payload) is not dict or type(payload.get("artifacts")) is not list:
            continue
        for item in payload["artifacts"]:
            kind = item.get("artifact_kind")
            if kind not in (PROFILE_STAGE_KIND_V5, HORN_SUBJECT_STATE_KIND_V5):
                continue
            content = parse_json_document(
                b64decode(item["content_base64"], validate=True),
            )
            if kind == PROFILE_STAGE_KIND_V5:
                stage = content
            else:
                horn = content
    return stage, horn


def evaluate_for_harness(
    application: ApplicationV4,
    request: HarnessRunRequest,
    *,
    request_ref: ContentRefV4,
    run_ref: ContentRefV4,
    case_scope: str,
) -> HarnessRunResultV5:
    """Run one Harness request through the sole formal spine and project it.

    This is the single Harness -> JC -> Harness entry: the same
    ``ApplicationV4.evaluate`` the Python, CLI and MCP surfaces use, plus a
    read-only projection of the sealed stage documents into the closed
    Harness result contract.
    """

    envelope = application.evaluate(request_ref, run_ref, case_scope=case_scope)
    return project_harness_result(application, request, envelope=envelope)


def project_harness_result(
    application: ApplicationV4,
    request: HarnessRunRequest,
    *,
    envelope: EvaluationEnvelopeV4,
) -> HarnessRunResultV5:
    """Project one already-evaluated envelope into the closed result contract.

    The evaluation half lives in :func:`evaluate_for_harness` (or any caller
    that already holds an envelope); this half reads only sealed artifacts so
    a projection never re-evaluates.
    """

    stage, horn = _stage_documents(application, envelope)
    issues: list[HarnessIssueResultV5] = []
    procedure_kinds: tuple[str, ...] = ()
    assurance_specs: tuple[str, ...] = ()
    composition_value: Mapping[str, Any] | None = None
    obligations: list[OpenObligationEntryV5] = []
    mapping_complete = True
    if stage is not None:
        mapping_complete = stage.get("mapping_coverage", {}).get("status") == "complete"
        rows = {row["query_id"]: row for row in stage.get("queries", [])}
        for query in request.queries:
            row = rows.get(query.issue_id)
            if row is None:
                raise HarnessContractError(
                    "HARNESS_ISSUE_MISSING",
                    f"issue {query.issue_id!r} has no sealed query row",
                )
            issues.append(HarnessIssueResultV5(
                issue_id=query.issue_id,
                claim=row["claim"],
                profile=row["profile"],
                gate=row["gate"],
                accepted=row["common"],
                possibly_accepted=row["possible"],
                refuted=row["common_refuted"],
                possibly_refuted=row["possibly_refuted"],
                undecided_some=row["undecided_some"],
                inconsistent_some=row["inconsistent_some"],
                excluded=row["excluded"],
                acceptance_witnesses=tuple(row["acceptance_witnesses"]),
                refutation_witnesses=tuple(row["refutation_witnesses"]),
                branch_refs=tuple(row.get("branch_refs", ())),
                mapping_complete=mapping_complete and not row.get("mapping_incomplete", False),
            ))
        procedure_kinds = tuple(
            row["kind"] for row in stage.get("procedures", [])
        )
        assurance_specs = tuple(
            entry["assurance"]["spec"]
            for entry in stage.get("profiles", {}).values()
        )
        composition = stage.get("composition")
        if composition is not None:
            composition_value = composition
        for entry in stage.get("mapping_coverage", {}).get("open_obligations", []):
            obligations.append(OpenObligationEntryV5(
                entry["code"], entry["detail"],
            ))
        for profile_row in stage.get("profiles", {}).values():
            for entry in profile_row.get("open_obligations", []):
                obligations.append(OpenObligationEntryV5(
                    entry["code"], entry["detail"],
                ))
    horn_mode = horn.get("mode", "unknown") if horn else "not_run"
    horn_fallback = horn.get("fallback_reason") if horn else None
    horn_parent = (
        None if horn is None or horn.get("parent") is None
        else str(DigestV4(horn["parent"]["subject_digest"]))
    )
    solver_work = int(horn["solver_metrics"].get("rule_evaluations", 0)) if horn else 0
    checker_work = int(horn["checker_metrics"].get("rule_evaluations", 0)) if horn else 0

    result = envelope.result
    missing_keys = tuple(
        sorted({
            requirement.fact_key
            for requirement in result.missing_facts
        })
    )
    # The Horn subject state records exactly the admitted boolean-true fact
    # keys the derivation layer consumed; assumed facts have no formal
    # channel in this spine (assumption inputs exit before the formal path).
    admitted_keys = tuple(sorted(horn.get("facts", ()))) if horn else ()
    artifact_refs = (
        {"kind": "audit-manifest", "digest": str(envelope.audit_manifest_ref.digest)},
    )
    return HarnessRunResultV5(
        case_id=request.case_id,
        run_status=envelope.transport_outcome.status,
        decision_status=result.decision_status.value,
        completeness=result.completeness_state.value,
        issues=tuple(issues),
        procedure_kinds=procedure_kinds,
        open_obligations=tuple(obligations),
        missing_fact_keys=missing_keys,
        admitted_fact_keys=admitted_keys,
        assumed_fact_keys=(),
        horn_mode=horn_mode,
        horn_fallback_reason=horn_fallback,
        horn_parent_binding=horn_parent,
        horn_solver_work=solver_work,
        horn_checker_work=checker_work,
        assurance_specs=assurance_specs,
        composition_value=composition_value,
        artifact_refs=artifact_refs,
        audit_manifest_ref=envelope.audit_manifest_ref.to_dict(),
    )


__all__ = [
    "HARNESS_CONTRACT_VERSION",
    "HarnessAttackInput",
    "HarnessContractError",
    "HarnessIssueResultV5",
    "HarnessPriorityInput",
    "HarnessQueryInput",
    "HarnessRunRequest",
    "HarnessRunResultV5",
    "evaluate_for_harness",
    "project_harness_result",
]
