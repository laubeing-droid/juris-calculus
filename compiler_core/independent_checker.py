"""Independent V4 semantic checker.

This module deliberately does not import the production compiler, router,
providers, or argumentation engine.  It resolves their immutable artifacts and
recomputes the certified finite semantics from canonical bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from fractions import Fraction
from pathlib import Path
from typing import Callable

import compiler_core.artifact_store as _artifact_store_module
import compiler_core.canonical_serialization as _canonical_module
import compiler_core.contracts as _contracts_module
import compiler_core.trust as _trust_module
from compiler_core.artifact_store import ArtifactResolverV4
from compiler_core.canonical_serialization import (
    DigestV4,
    SAFE_INTEGER_MAX,
    SAFE_INTEGER_MIN,
    canonical_bytes,
    digest_value,
    parse_json_document,
)
from compiler_core.contracts import (
    ArgumentV4,
    BackendInvocationV4,
    CanonicalTimeV4,
    CaseRequestV4,
    CheckerReceiptV4,
    ContentRefV4,
    EvidenceManifestV4,
    FactAdmissionReceiptV4,
    FactAttestationV4,
    FactCandidateV4,
    LegalIVLV4,
    LegalSpecV4,
    PackManifestV4,
    PackSignatureV4,
    RulePromotionReceiptV4,
    RuleV4,
    RunIdentityV4,
    SignatureEnvelopeV4,
    SolverReceiptV4,
    SourceBundleV4,
    SourceSnapshotV4,
    TranslationReceiptV4,
    validate_rational_v4,
)
from compiler_core.trust import TrustVerifierV4


CHECKER_SCOPE = "independent-checker"
CHECKER_REPORT_KIND = "checker-report-v4"
CHECKER_RECEIPT_KIND = "checker-receipt-v4"
ARGUMENT_GRAPH_KIND = "argument-graph-v4"
ARGUMENT_KIND = "argument-v4"

BACKEND_SCOPE = "backend"
BACKEND_PROBLEM_KIND = "backend-problem-v4"
BACKEND_INVOCATION_KIND = "backend-invocation-v4"
BACKEND_RESULT_KIND = "backend-result-v4"
BACKEND_PROOF_KIND = "backend-proof-v4"
SOLVER_RECEIPT_KIND = "solver-receipt-v4"
BACKEND_CAPABILITY_KIND = "backend-capability-v4"
BACKEND_LIMITS_KIND = "backend-limits-v4"

LEGAL_IR_SCOPE = "legal-ir"
LEGAL_SPEC_KIND = "legal-spec-v4"
LEGAL_IVL_KIND = "legal-ivl-v4"
IR_TYPE_ENVIRONMENT_KIND = "legal-ir-type-environment"
IR_MODALITY_KIND = "legal-ir-modality"
IR_CLAUSE_KIND = "legal-ir-clause"
IR_SOURCE_MAP_KIND = "legal-ir-source-map"
IR_PROOF_OBLIGATION_KIND = "legal-ir-proof-obligation"
IR_FIELD_MAPPING_KIND = "legal-ir-field-mapping"
IR_TRANSLATOR_KIND = "legal-ir-translator"
TRANSLATION_RECEIPT_KIND = "translation-receipt"

RULE_PACK_SCOPE = "rule-pack"
RULE_COMPONENT_SCOPE = "rule-component"
PACK_SIGNATURE_KIND = "pack-signature"
PACK_MANIFEST_KIND = "pack-manifest"
RULE_KIND = "rule-v4"
RULE_PREMISE_KIND = "rule-premise"
RULE_CONCLUSION_KIND = "rule-conclusion"
RULE_EXCEPTION_KIND = "rule-exception"
RULE_ATTACK_KIND = "rule-attack"
RULE_PRIORITY_KIND = "rule-priority"
RULE_PERMISSION_KIND = "rule-permission"
RULE_TEMPORAL_KIND = "rule-temporal-constraint"
RULE_NUMERIC_KIND = "rule-numeric-constraint"
RULE_PROMOTION_RECEIPT_KIND = "rule-promotion-receipt"

CASE_REQUEST_KIND = "case-request"
CASE_REQUEST_SCOPE = "request"
CASE_REQUEST_BINDING_KIND = "case-request-binding"
CASE_EVIDENCE_SCOPE = "case-evidence"
EVIDENCE_MANIFEST_KIND = "evidence-manifest"
FACT_ADMISSION_SCOPE = "fact-admission"
FACT_ADMISSION_RECEIPT_KIND = "fact-admission-receipt"
ADMITTED_FACT_KIND = "admitted-fact"
FACT_CANDIDATE_KIND = "fact-candidate"
FACT_ATTESTATION_KIND = "fact-attestation"
FACT_PROPOSITION_KIND = "fact-proposition"
FACT_VALUE_KIND = "fact-value"
SOURCE_GATE_RECEIPT_KIND = "source-gate-receipt"
INTERPRETATION_GATE_RECEIPT_KIND = "interpretation-gate-receipt"
FACT_GATE_RECEIPT_KIND = "fact-gate-receipt"
LEGAL_APPROVAL_SCOPE = "legal-approval"
SOURCE_BUNDLE_KIND = "source-bundle"
SOURCE_SNAPSHOT_KIND = "source-snapshot"
SOURCE_PATH_SCOPE = "source-path"
SOURCE_AUTHENTICITY_SCOPE = "source-authenticity"
SOURCE_AUTHENTICITY_RECEIPT_KIND = "source-authenticity-receipt"
SOURCE_RAW_KIND = "source-raw"
SOURCE_NORMALIZED_KIND = "source-normalized"
SOURCE_RETRIEVAL_RECEIPT_KIND = "source-retrieval-receipt"
RUN_IDENTITY_KIND = "run-identity"
RUN_IDENTITY_SCOPE = "run"
TRUST_POLICY_KIND = "trust-policy"

HORN_PROVIDER_ID = "jc-horn-fixpoint"
AAF_PROVIDER_ID = "jc-aaf-grounded"
EXACT_PROVIDER_ID = "jc-exact-temporal-numeric"
PROVIDER_VERSION = "1.0.0"

CheckerSignerV4 = Callable[
    [
        DigestV4,
        DigestV4,
        tuple[ContentRefV4, ...],
        ContentRefV4,
        CanonicalTimeV4,
    ],
    SignatureEnvelopeV4,
]


class IndependentCheckerV4Error(ValueError):
    """Stable fail-closed error raised before a PASS receipt can be issued."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> None:
    raise IndependentCheckerV4Error(code, detail)


def _ref_key(reference: ContentRefV4) -> tuple[str, str]:
    return reference.kind, str(reference.digest)


def _sorted_refs(values: tuple[ContentRefV4, ...]) -> tuple[ContentRefV4, ...]:
    if any(type(value) is not ContentRefV4 for value in values):
        _fail("CHECKER_REFERENCE_TYPE", "witnesses must be exact ContentRefV4 values")
    if len(values) != len(set(values)):
        _fail("CHECKER_DUPLICATE_REFERENCE", "witness references must not repeat")
    return tuple(sorted(values, key=_ref_key))


def _wire_ref(value: object, field: str) -> ContentRefV4:
    if type(value) is not dict:
        _fail("CHECKER_ARTIFACT_SHAPE", f"{field} must be a content reference")
    try:
        return ContentRefV4.from_dict(value)
    except (TypeError, ValueError) as exc:
        raise IndependentCheckerV4Error(
            "CHECKER_ARTIFACT_SHAPE", f"{field} is not a canonical content reference"
        ) from exc


def _wire_refs(value: object, field: str) -> tuple[ContentRefV4, ...]:
    if type(value) is not list:
        _fail("CHECKER_ARTIFACT_SHAPE", f"{field} must be an array")
    return tuple(_wire_ref(item, field) for item in value)


@dataclass(frozen=True, slots=True)
class CheckerExecutionV4:
    receipt: CheckerReceiptV4
    receipt_ref: ContentRefV4
    report_ref: ContentRefV4


@dataclass(frozen=True, slots=True)
class _CheckMaterial:
    run_ref: ContentRefV4
    solver_receipt_ref: ContentRefV4
    solver_receipt: SolverReceiptV4
    problem_ref: ContentRefV4
    invocation_ref: ContentRefV4
    backend_result_ref: ContentRefV4
    argument_graph_ref: ContentRefV4
    argument_graph: dict[str, object]
    input_digest: DigestV4
    report: dict[str, object]
    report_ref: ContentRefV4
    witness_refs: tuple[ContentRefV4, ...]


class _Reader:
    def __init__(self, resolver: ArtifactResolverV4) -> None:
        self.resolver = resolver
        self.seen: set[ContentRefV4] = set()

    def json(self, reference: ContentRefV4, *, kind: str, scope: str) -> dict[str, object]:
        if type(reference) is not ContentRefV4 or reference.kind != kind:
            _fail("CHECKER_REF_KIND", f"expected {kind}")
        raw = self.resolver.resolve_content(
            reference,
            expected_artifact_kind=kind,
            expected_media_type="application/json",
            expected_scope=scope,
            max_bytes=self.resolver.max_artifact_bytes,
        )
        try:
            document = parse_json_document(raw)
        except (TypeError, ValueError) as exc:
            raise IndependentCheckerV4Error(
                "CHECKER_JSON", f"{kind} is not strict canonical JSON"
            ) from exc
        if type(document) is not dict or raw != canonical_bytes(document):
            _fail("CHECKER_NONCANONICAL_JSON", f"{kind} is not canonical JSON")
        self.seen.add(reference)
        return document

    def contract(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
        contract: type,
    ) -> object:
        document = self.json(reference, kind=kind, scope=scope)
        try:
            value = contract.from_dict(document)
        except (TypeError, ValueError) as exc:
            raise IndependentCheckerV4Error(
                "CHECKER_CONTRACT", f"{kind} violates {contract.__name__}"
            ) from exc
        if value.canonical_bytes() != canonical_bytes(document):
            _fail("CHECKER_CONTRACT", f"{kind} contract bytes drifted")
        return value

    def self_digest(
        self,
        reference: ContentRefV4,
        *,
        kind: str,
        scope: str,
        contract: type,
        digest_field: str,
    ) -> object:
        body = self.json(reference, kind=kind, scope=scope)
        if digest_field in body:
            _fail("CHECKER_DIGEST_BODY", f"{kind} stores a recursive digest field")
        try:
            value = contract.from_dict({**body, digest_field: str(reference.digest)})
        except (TypeError, ValueError) as exc:
            raise IndependentCheckerV4Error(
                "CHECKER_CONTRACT", f"{kind} violates {contract.__name__}"
            ) from exc
        if value.canonical_digest() != reference.digest or value.digest_body() != body:
            _fail("CHECKER_SELF_DIGEST", f"{kind} self digest differs")
        return value


def _runtime_build_digest() -> DigestV4:
    modules = {
        "artifact_store": _artifact_store_module,
        "canonical_serialization": _canonical_module,
        "contracts": _contracts_module,
        "independent_checker": __import__(__name__, fromlist=["x"]),
        "trust": _trust_module,
    }
    inputs = {
        name: str(DigestV4.from_bytes(Path(module.__file__).read_bytes()))
        for name, module in sorted(modules.items())
    }
    return digest_value({"schema_version": "jc/checker-build/1.0", "inputs": inputs})


def _algorithm_profile_digest() -> DigestV4:
    return digest_value({
        "schema_version": "jc/independent-checker-profile/1.0",
        "canonical_input": "content-addressed-v4-artifacts",
        "translation": "independent-exhaustive-field-projection",
        "horn": "finite-constitutive-least-fixpoint",
        "aaf": "independent-finite-dung-grounded",
        "exact": "integer-rational-nanosecond-half-open",
        "claim_projection": "all-argument-witnesses",
    })


def _request_binding_ref(request: CaseRequestV4) -> ContentRefV4:
    body = {
        "schema_version": "jc/case-request-binding/1.0",
        "request_id": request.request_id,
        "request_schema_version": request.schema_version,
        "legal_context": request.legal_context.to_dict(),
        "decision_time": request.decision_time.to_dict(),
        "source_bundle_ref": request.source_bundle_ref.to_dict(),
        "rule_pack_ref": request.rule_pack_ref.to_dict(),
        "requested_outputs": [item.to_dict() for item in request.requested_outputs],
        "proposal_refs": [item.to_dict() for item in request.proposal_refs],
    }
    return ContentRefV4(CASE_REQUEST_BINDING_KIND, DigestV4.from_bytes(canonical_bytes(body)))


def _instant(value: object) -> CanonicalTimeV4:
    try:
        return CanonicalTimeV4.parse(value)
    except ValueError as exc:
        raise IndependentCheckerV4Error(
            "CHECKER_TIME", "semantic time must be a canonical UTC instant"
        ) from exc


def _interval(clause: dict[str, object], decision_time: CanonicalTimeV4) -> dict[str, object]:
    start = _instant(clause.get("effective_from"))
    raw_end = clause.get("effective_to")
    end = None if raw_end is None else _instant(raw_end)
    if end is not None and not start < end:
        _fail("CHECKER_TIME_ORDER", "rule effective interval must increase")
    return {
        "ivl_id": clause["ivl_id"],
        "effective_from": start.wire,
        "effective_to": None if end is None else end.wire,
        "active": not decision_time < start and (end is None or decision_time < end),
    }


def _argument_ref(argument: ArgumentV4) -> ContentRefV4:
    return ContentRefV4(ARGUMENT_KIND, argument.canonical_digest())


def _strong_components(ids: set[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    adjacency = {item: [] for item in ids}
    reverse = {item: [] for item in ids}
    for source, target in edges:
        if source in ids and target in ids:
            adjacency[source].append(target)
            reverse[target].append(source)
    for values in (*adjacency.values(), *reverse.values()):
        values.sort()

    visited: set[str] = set()
    order: list[str] = []
    for start in sorted(ids):
        if start in visited:
            continue
        visited.add(start)
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node, index = stack[-1]
            if index < len(adjacency[node]):
                child = adjacency[node][index]
                stack[-1] = (node, index + 1)
                if child not in visited:
                    visited.add(child)
                    stack.append((child, 0))
            else:
                stack.pop()
                order.append(node)

    visited.clear()
    components: list[list[str]] = []
    for start in reversed(order):
        if start in visited:
            continue
        component: list[str] = []
        visited.add(start)
        pending = [start]
        while pending:
            node = pending.pop()
            component.append(node)
            for child in reversed(reverse[node]):
                if child not in visited:
                    visited.add(child)
                    pending.append(child)
        components.append(sorted(component))
    return components


def _grounded(ids: set[str], edges: list[tuple[str, str]]) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    attackers: dict[str, set[str]] = {}
    for source, target in edges:
        if source in ids and target in ids:
            attackers.setdefault(target, set()).add(source)
    accepted: set[str] = set()
    for _ in range(len(ids) + 1):
        defended = {
            item
            for item in ids
            if all(attackers.get(attacker, set()) & accepted for attacker in attackers.get(item, set()))
        }
        if defended == accepted:
            break
        accepted = defended
    else:
        _fail("CHECKER_NONCONVERGENT", "grounded fixed point exceeded its finite bound")
    rejected = {
        item for item in ids - accepted if attackers.get(item, set()) & accepted
    }
    undecided = ids - accepted - rejected
    labels = {
        **{item: "IN" for item in accepted},
        **{item: "OUT" for item in rejected},
        **{item: "UNDEC" for item in undecided},
    }
    components = _strong_components(ids, edges)
    component_by_id = {
        item: component for component in components for item in component
    }
    edge_set = set(edges)
    witnesses: dict[str, tuple[str, ...]] = {}
    for item in sorted(ids):
        if item in accepted:
            defenders = {
                defender
                for attacker in attackers.get(item, set())
                for defender in attackers.get(attacker, set()) & accepted
            }
            witnesses[item] = tuple(sorted(defenders))
        elif item in rejected:
            witnesses[item] = tuple(sorted(attackers.get(item, set()) & accepted))
        else:
            component = component_by_id.get(item, [item])
            if len(component) > 1 or (item, item) in edge_set:
                witnesses[item] = tuple(component)
            else:
                witnesses[item] = tuple(sorted(attackers.get(item, set()) & undecided))
    return labels, witnesses


def _horn_analysis(problem: dict[str, object]) -> dict[str, object]:
    rows = problem.get("facts")
    clauses = problem.get("clauses")
    if type(rows) is not list or type(clauses) is not list or not clauses:
        _fail("CHECKER_PROBLEM", "backend facts/clauses are not closed non-empty arrays")
    facts: dict[str, object] = {}
    evidence_by_atom: dict[str, ContentRefV4] = {}
    for row in rows:
        if type(row) is not dict:
            _fail("CHECKER_PROBLEM", "fact row is not an object")
        proposition = row.get("proposition")
        if type(proposition) is not str or not proposition or proposition in facts:
            _fail("CHECKER_PROBLEM", "fact propositions must be unique non-empty strings")
        facts[proposition] = row.get("value")
        if row.get("value") is True:
            evidence_by_atom[proposition] = _wire_ref(row.get("fact_ref"), "fact_ref")

    decision_time = _instant(problem.get("decision_time"))
    rules: list[dict[str, object]] = []
    intervals: list[dict[str, object]] = []
    required: set[str] = set()
    for clause in clauses:
        if type(clause) is not dict:
            _fail("CHECKER_PROBLEM", "clause is not an object")
        modality = clause.get("modality")
        if modality not in {"OBLIGATION", "PROHIBITION", "PERMISSION", "CONSTITUTIVE"}:
            _fail("CHECKER_UNSUPPORTED", "rule modality is not independently certified")
        interval = _interval(clause, decision_time)
        intervals.append(interval)
        premises = clause.get("premises")
        conclusion = clause.get("conclusion")
        if type(premises) is not list or type(conclusion) is not dict:
            _fail("CHECKER_PROBLEM", "clause premise or conclusion is malformed")
        premise_keys = tuple(
            row["fact_key"]
            for row in premises
            if type(row) is dict and row.get("required") is True
        )
        if len(premise_keys) != sum(
            1 for row in premises if type(row) is dict and row.get("required") is True
        ):
            _fail("CHECKER_PROBLEM", "required premise lacks fact_key")
        if interval["active"]:
            required.update(premise_keys)
        head = conclusion.get("fact_key")
        if modality == "CONSTITUTIVE" and (type(head) is not str or not head):
            _fail("CHECKER_UNSUPPORTED", "constitutive conclusion requires fact_key")
        rules.append({
            "ivl_id": clause["ivl_id"],
            "head": head,
            "premises": premise_keys,
            "conclusion_ref": _wire_ref(clause["conclusion_ref"], "conclusion_ref"),
            "rule_ref": _wire_ref(clause["rule_ref"], "rule_ref"),
            "modality": modality,
            "active": interval["active"],
        })
    rules.sort(key=lambda row: (str(row["head"]), row["premises"], row["ivl_id"]))
    known = {key for key, value in facts.items() if value is True}
    initial_true = set(known)
    false_facts = sorted(key for key, value in facts.items() if value is False)
    constitutive = [
        row for row in rules if row["active"] and row["modality"] == "CONSTITUTIVE"
    ]
    trace: list[dict[str, object]] = []
    fired_refs: list[dict[str, object]] = []
    fired_rule_ids: list[str] = []
    bound = len({row["head"] for row in constitutive}) + 1
    for iteration in range(1, bound + 1):
        added: list[str] = []
        for row in constitutive:
            head = row["head"]
            if head not in known and all(item in known for item in row["premises"]):
                if facts.get(head) is False:
                    _fail("CHECKER_FACT_CONFLICT", f"derived atom conflicts with false fact: {head}")
                known.add(head)
                added.append(head)
                fired_rule_ids.append(row["ivl_id"])
                fired_refs.append(row["conclusion_ref"].to_dict())
                evidence_by_atom[head] = row["conclusion_ref"]
        trace.append({"iteration": iteration, "added": sorted(added)})
        if not added:
            break
    else:
        _fail("CHECKER_NONCONVERGENT", "Horn fixed point exceeded its finite bound")
    applicable_rule_ids = sorted(
        row["ivl_id"]
        for row in rules
        if row["active"] and all(item in known for item in row["premises"])
    )
    applicable_norms = [
        {
            "ivl_id": row["ivl_id"],
            "rule_ref": row["rule_ref"].to_dict(),
            "conclusion_ref": row["conclusion_ref"].to_dict(),
            "modality": row["modality"],
        }
        for row in rules
        if row["modality"] != "CONSTITUTIVE" and row["ivl_id"] in applicable_rule_ids
    ]
    return {
        "facts": facts,
        "initial_true": initial_true,
        "known": known,
        "false_facts": false_facts,
        "required": required,
        "trace": trace,
        "bound": bound,
        "fired_refs": fired_refs,
        "fired_rule_ids": fired_rule_ids,
        "applicable_rule_ids": applicable_rule_ids,
        "applicable_norms": applicable_norms,
        "intervals": sorted(intervals, key=lambda row: row["ivl_id"]),
        "evidence_by_atom": evidence_by_atom,
    }


def _graph_and_evaluation(
    problem: dict[str, object], analysis: dict[str, object]
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    clauses = problem["clauses"]
    applicable = set(analysis["applicable_rule_ids"])
    known = set(analysis["known"])
    modality_by_id = {row["ivl_id"]: row["modality"] for row in clauses}
    conclusion_by_id = {row["ivl_id"]: row["conclusion"] for row in clauses}
    all_ids = set(modality_by_id)
    arguments = [
        ArgumentV4(
            argument_id=row["ivl_id"],
            premise_refs=_wire_refs(row["premise_refs"], "premise_refs"),
            rule_ref=_wire_ref(row["rule_ref"], "rule_ref"),
            claim_ref=_wire_ref(row["conclusion_ref"], "conclusion_ref"),
            derivation_refs=_wire_refs(row["derivation_refs"], "derivation_refs"),
        )
        for row in clauses
        if row["ivl_id"] in applicable
    ]
    arguments.sort(key=lambda value: value.argument_id)
    by_id = {value.argument_id: value for value in arguments}
    refs = {key: _argument_ref(value) for key, value in by_id.items()}
    attacks: list[dict[str, object]] = []
    priorities: list[dict[str, object]] = []
    permissions: list[dict[str, object]] = []
    condition_evidence: list[dict[str, object]] = []
    seen_sources: set[ContentRefV4] = set()
    for clause in clauses:
        for row in clause["relations"]:
            kind = row["kind"]
            source, target = row["source"], row["target"]
            if source not in all_ids or target not in all_ids:
                _fail("CHECKER_GRAPH_ENDPOINT", "relation leaves the selected IVL set")
            source_ref = _wire_ref(row["source_ref"], "source_ref")
            if source_ref in seen_sources:
                _fail("CHECKER_GRAPH_DUPLICATE", "relation source references repeat")
            seen_sources.add(source_ref)
            if kind == "attack":
                condition = row["condition_fact_key"]
                if source not in refs or target not in refs or (
                    condition is not None and condition not in known
                ):
                    continue
                if condition is not None:
                    condition_ref = analysis["evidence_by_atom"].get(condition)
                    if type(condition_ref) is not ContentRefV4:
                        _fail("CHECKER_GRAPH_EVIDENCE", "attack condition lacks typed evidence")
                    condition_evidence.append({
                        "source_ref": source_ref.to_dict(),
                        "condition": condition,
                        "condition_ref": condition_ref.to_dict(),
                    })
                attacks.append({
                    "attack_id": f"attack-{source_ref.digest.hex}",
                    "attacker_ref": refs[source].to_dict(),
                    "target_ref": refs[target].to_dict(),
                    "attack_type": row["attack_type"],
                    "target_aspect": row["target_aspect"],
                })
            elif kind == "priority":
                condition = row["condition"]
                if source not in refs or target not in refs or condition not in known:
                    continue
                condition_ref = analysis["evidence_by_atom"].get(condition)
                if type(condition_ref) is not ContentRefV4:
                    _fail("CHECKER_GRAPH_EVIDENCE", "priority condition lacks typed evidence")
                condition_evidence.append({
                    "source_ref": source_ref.to_dict(),
                    "condition": condition,
                    "condition_ref": condition_ref.to_dict(),
                })
                priorities.append({
                    "edge_id": f"priority-{source_ref.digest.hex}",
                    "preferred_ref": refs[source].to_dict(),
                    "defeated_ref": refs[target].to_dict(),
                    "condition_ref": condition_ref.to_dict(),
                    "source_ref": source_ref.to_dict(),
                })
            elif kind == "permission":
                permits = row["permits"]
                if (
                    source_ref.kind != RULE_PERMISSION_KIND
                    or modality_by_id[source] != "PERMISSION"
                    or modality_by_id[target] != "PROHIBITION"
                    or row["relation_kind"] != "exception"
                    or conclusion_by_id[source].get("fact_key") != permits
                    or conclusion_by_id[target].get("fact_key") != permits
                ):
                    _fail("CHECKER_UNSUPPORTED", "permission is not typed to a prohibition")
                if source not in refs or target not in refs:
                    continue
                permissions.append({
                    "permission_id": row["permission_id"],
                    "permission_claim_ref": by_id[source].claim_ref.to_dict(),
                    "prohibition_claim_ref": by_id[target].claim_ref.to_dict(),
                    "source_ref": source_ref.to_dict(),
                })
                attacks.append({
                    "attack_id": f"permission-{source_ref.digest.hex}",
                    "attacker_ref": refs[source].to_dict(),
                    "target_ref": refs[target].to_dict(),
                    "attack_type": "exception",
                    "target_aspect": "rule_applicability",
                })
            else:
                _fail("CHECKER_UNSUPPORTED", "relation kind is not certified")
    arguments_wire = [item.to_dict() for item in arguments]
    attacks.sort(key=lambda row: row["attack_id"])
    priorities.sort(key=lambda row: row["edge_id"])
    permissions.sort(key=lambda row: row["permission_id"])
    graph = {
        "schema_version": "jc/argument-graph-v4/1.0",
        "arguments": arguments_wire,
        "attacks": attacks,
        "priority_edges": priorities,
        "permission_relations": permissions,
    }
    graph_ref = ContentRefV4(ARGUMENT_GRAPH_KIND, DigestV4.from_bytes(canonical_bytes(graph)))
    if not arguments:
        evaluation = {
            "schema_version": "jc/argumentation-evaluation-v4/1.0",
            "graph_ref": graph_ref.to_dict(),
            "labels": [],
            "effective_attacks": [],
            "permission_resolutions": [],
            "exception_resolutions": [],
            "claim_projection": [],
            "priority_cycles": [],
            "state": "empty",
        }
        return graph, evaluation, condition_evidence

    priority_attacks = [
        {
            "attack_id": f"priority::{row['edge_id']}",
            "attacker_ref": row["preferred_ref"],
            "target_ref": row["defeated_ref"],
            "attack_type": "priority_defeat",
            "target_aspect": "claim",
        }
        for row in priorities
    ]
    effective_attacks = sorted(
        [*attacks, *priority_attacks], key=lambda row: row["attack_id"]
    )
    id_by_ref = {reference: key for key, reference in refs.items()}
    attack_pairs = [
        (
            id_by_ref[_wire_ref(row["attacker_ref"], "attacker_ref")],
            id_by_ref[_wire_ref(row["target_ref"], "target_ref")],
        )
        for row in effective_attacks
    ]
    labels_by_id, witnesses_by_id = _grounded(set(by_id), attack_pairs)
    labels = [
        {
            "argument_ref": refs[item].to_dict(),
            "label": labels_by_id[item],
            "witness_refs": [refs[value].to_dict() for value in witnesses_by_id[item]],
        }
        for item in sorted(by_id)
    ]
    permission_resolutions = []
    arguments_by_claim: dict[ContentRefV4, list[ContentRefV4]] = {}
    for key, argument in by_id.items():
        arguments_by_claim.setdefault(argument.claim_ref, []).append(refs[key])
    label_by_ref = {refs[key]: value for key, value in labels_by_id.items()}
    for row in permissions:
        permission_claim = _wire_ref(row["permission_claim_ref"], "permission_claim_ref")
        prohibition_claim = _wire_ref(row["prohibition_claim_ref"], "prohibition_claim_ref")
        permission_args = arguments_by_claim[permission_claim]
        prohibition_args = arguments_by_claim[prohibition_claim]
        permission_labels = {label_by_ref[item] for item in permission_args}
        prohibition_labels = {label_by_ref[item] for item in prohibition_args}
        if "UNDEC" in permission_labels | prohibition_labels:
            status = "disputed"
        elif "IN" in permission_labels and "IN" not in prohibition_labels:
            status = "holds"
        elif "IN" not in permission_labels and "IN" in prohibition_labels:
            status = "does_not_hold"
        else:
            status = "disputed"
        witnesses = _sorted_refs((
            _wire_ref(row["source_ref"], "source_ref"),
            *permission_args,
            *prohibition_args,
        ))
        permission_resolutions.append({
            "permission_id": row["permission_id"],
            "claim_ref": permission_claim.to_dict(),
            "prohibition_ref": prohibition_claim.to_dict(),
            "status": status,
            "witness_refs": [item.to_dict() for item in witnesses],
        })
    exception_resolutions = []
    argument_by_ref = {refs[key]: value for key, value in by_id.items()}
    for row in effective_attacks:
        if row["attack_type"] != "exception":
            continue
        attacker = _wire_ref(row["attacker_ref"], "attacker_ref")
        target = _wire_ref(row["target_ref"], "target_ref")
        attacker_label, target_label = label_by_ref[attacker], label_by_ref[target]
        status = (
            "applied" if (attacker_label, target_label) == ("IN", "OUT")
            else "defeated" if (attacker_label, target_label) == ("OUT", "IN")
            else "disputed"
        )
        exception_resolutions.append({
            "exception_id": row["attack_id"],
            "claim_ref": argument_by_ref[target].claim_ref.to_dict(),
            "target_ref": target.to_dict(),
            "target_aspect": row["target_aspect"],
            "status": status,
            "witness_refs": [item.to_dict() for item in _sorted_refs((attacker, target))],
        })
    claim_projection = [
        {
            "claim_ref": claim.to_dict(),
            "argument_refs": [item.to_dict() for item in sorted(values, key=_ref_key)],
        }
        for claim, values in sorted(arguments_by_claim.items(), key=lambda item: _ref_key(item[0]))
    ]
    priority_pairs = [
        (
            id_by_ref[_wire_ref(row["preferred_ref"], "preferred_ref")],
            id_by_ref[_wire_ref(row["defeated_ref"], "defeated_ref")],
        )
        for row in priorities
    ]
    priority_cycles = [
        [refs[item].to_dict() for item in sorted(component, key=lambda key: _ref_key(refs[key]))]
        for component in _strong_components(set(by_id), priority_pairs)
        if len(component) > 1 or (component[0], component[0]) in set(priority_pairs)
    ]
    priority_cycles.sort(key=lambda cycle: tuple((row["kind"], row["digest"]) for row in cycle))
    if priority_cycles:
        state = "cycle_blocked"
    elif any(row["status"] == "disputed" for row in permission_resolutions):
        state = "disputed"
    elif "UNDEC" in labels_by_id.values():
        state = "disputed"
    else:
        state = "accepted"
    evaluation = {
        "schema_version": "jc/argumentation-evaluation-v4/1.0",
        "graph_ref": graph_ref.to_dict(),
        "labels": labels,
        "effective_attacks": effective_attacks,
        "permission_resolutions": permission_resolutions,
        "exception_resolutions": exception_resolutions,
        "claim_projection": claim_projection,
        "priority_cycles": priority_cycles,
        "state": state,
    }
    return graph, evaluation, sorted(
        condition_evidence,
        key=lambda row: (str(row["source_ref"]), row["condition"]),
    )


def _semantic_state_graph(
    *,
    provider_id: str,
    problem_ref: ContentRefV4,
    outcome: str,
    outputs: dict[str, object],
) -> dict[str, object]:
    """Bind a non-AAF result to a real, deterministic checker graph artifact."""

    return {
        "schema_version": "jc/argument-graph-v4/1.0",
        "provider_id": provider_id,
        "problem_ref": problem_ref.to_dict(),
        "arguments": [],
        "attacks": [],
        "priority_edges": [],
        "permission_relations": [],
        "semantic_state": {
            "outcome": outcome,
            "outputs_digest": str(digest_value(outputs)),
        },
    }


def _safe(value: int) -> int:
    if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
        _fail("CHECKER_EXACT_INTEGER", "exact result exceeds the safe integer range")
    return value


def _ratio(value: object) -> Fraction:
    try:
        numerator, denominator = validate_rational_v4(value)
    except ValueError as exc:
        raise IndependentCheckerV4Error(
            "CHECKER_EXACT_RATIO", "ratio is not canonical and reduced"
        ) from exc
    return Fraction(numerator, denominator)


def _exact_outputs(problem: dict[str, object], analysis: dict[str, object]) -> dict[str, object]:
    applicable = set(analysis["applicable_rule_ids"])
    facts = analysis["facts"]
    decision_time = _instant(problem["decision_time"])
    temporal: list[dict[str, object]] = []
    numeric: list[dict[str, object]] = []
    seen: set[ContentRefV4] = set()
    all_ids = {row["ivl_id"] for row in problem["clauses"]}
    for clause in problem["clauses"]:
        for kind, values in (
            (RULE_TEMPORAL_KIND, clause["temporal_constraints"]),
            (RULE_NUMERIC_KIND, clause["numeric_constraints"]),
        ):
            for row in values:
                reference = _wire_ref(row["constraint_ref"], "constraint_ref")
                owner, target, expression = (
                    row["owner_ivl_id"], row["target_ivl_id"], row["expression"]
                )
                if reference in seen or owner != clause["ivl_id"] or target not in all_ids:
                    _fail("CHECKER_EXACT_BINDING", "constraint reference or owner drifted")
                seen.add(reference)
                if clause["ivl_id"] not in applicable:
                    continue
                if kind == RULE_TEMPORAL_KIND:
                    start, end = _instant(expression.get("start")), _instant(expression.get("end"))
                    if not start < end:
                        _fail("CHECKER_TIME_ORDER", "temporal interval must increase")
                    seconds = end.epoch_seconds - start.epoch_seconds
                    nanoseconds = end.nanosecond - start.nanosecond
                    if nanoseconds < 0:
                        seconds -= 1
                        nanoseconds += 1_000_000_000
                    temporal.append({
                        "constraint_ref": reference.to_dict(),
                        "owner_ivl_id": owner,
                        "target_ivl_id": target,
                        "operation": "interval",
                        "active": CanonicalTimeV4.contains_half_open(start, end, decision_time),
                        "duration": {"seconds": seconds, "nanoseconds": nanoseconds},
                    })
                elif expression.get("operation") == "integer_add":
                    operands = expression.get("operands")
                    if type(operands) is not list or any(type(value) is not int for value in operands):
                        _fail("CHECKER_EXACT_INTEGER", "integer_add operands are invalid")
                    numeric.append({
                        "constraint_ref": reference.to_dict(),
                        "owner_ivl_id": owner,
                        "target_ivl_id": target,
                        "operation": "integer_add",
                        "integer": _safe(sum(operands)),
                    })
                elif expression.get("operation") == "integer_multiply_ratio":
                    fact_key = expression.get("fact_key")
                    if type(fact_key) is not str or type(facts.get(fact_key)) is not int:
                        _fail("CHECKER_EXACT_INTEGER", "numeric fact is not an admitted integer")
                    value = Fraction(facts[fact_key]) * _ratio(expression.get("ratio"))
                    numeric.append({
                        "constraint_ref": reference.to_dict(),
                        "owner_ivl_id": owner,
                        "target_ivl_id": target,
                        "operation": "integer_multiply_ratio",
                        "rational": {
                            "numerator": _safe(value.numerator),
                            "denominator": _safe(value.denominator),
                        },
                    })
                else:
                    _fail("CHECKER_UNSUPPORTED", "numeric operation is not certified")
    return {
        "rule_intervals": analysis["intervals"],
        "temporal": temporal,
        "numeric": numeric,
    }


class IndependentCheckerV4:
    """Recompute one solver execution and issue a signed PASS only on exact parity."""

    def __init__(
        self,
        resolver: ArtifactResolverV4,
        trust: TrustVerifierV4,
        *,
        receipt_issuer: str,
        receipt_signer: CheckerSignerV4,
    ) -> None:
        if (
            type(resolver) is not ArtifactResolverV4
            or type(trust) is not TrustVerifierV4
            or type(receipt_issuer) is not str
            or not receipt_issuer
            or not callable(receipt_signer)
        ):
            _fail("CHECKER_INPUT_TYPE", "checker dependencies are invalid")
        self._resolver = resolver
        self._trust = trust
        self._receipt_issuer = receipt_issuer
        self._receipt_signer = receipt_signer

    def _service_signature(
        self,
        envelope: SignatureEnvelopeV4,
        *,
        subject: DigestV4,
        payload: DigestV4,
        evidence: tuple[ContentRefV4, ...],
        run_ref: ContentRefV4,
        now: CanonicalTimeV4,
        issuer: str | None = None,
    ) -> None:
        if (
            type(envelope) is not SignatureEnvelopeV4
            or (issuer is not None and envelope.issuer != issuer)
            or envelope.run_identity_ref != run_ref
            or envelope.subject_digest != subject
            or envelope.payload_digest != payload
            or envelope.evidence_refs != evidence
            or envelope.status != "APPROVED"
        ):
            _fail("CHECKER_SIGNATURE_BINDING", "service signature context differs")
        self._trust._fresh_without_replay().verify(
            envelope,
            expected_subject_digest=subject,
            expected_payload_digest=payload,
            required_role="service_signer",
            required_scope="service-certificate",
            required_artifact_kind="service-certificate",
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(),
        )

    def _source_snapshot(
        self,
        reader: _Reader,
        reference: ContentRefV4,
        *,
        now: CanonicalTimeV4,
    ) -> SourceSnapshotV4:
        snapshot = reader.contract(
            reference,
            kind=SOURCE_SNAPSHOT_KIND,
            scope=SOURCE_AUTHENTICITY_SCOPE,
            contract=SourceSnapshotV4,
        )
        if DigestV4.from_bytes(snapshot.canonical_bytes()) != reference.digest:
            _fail("CHECKER_SOURCE_BINDING", "source snapshot reference differs from bytes")
        envelope = reader.contract(
            snapshot.authenticity_receipt_ref,
            kind=SOURCE_AUTHENTICITY_RECEIPT_KIND,
            scope=SOURCE_AUTHENTICITY_SCOPE,
            contract=SignatureEnvelopeV4,
        )
        payload = snapshot.to_dict()
        del payload["authenticity_receipt_ref"]
        required_evidence = {
            ContentRefV4(SOURCE_RAW_KIND, snapshot.raw_digest),
            ContentRefV4(SOURCE_NORMALIZED_KIND, snapshot.normalized_digest),
            snapshot.structure_map_ref,
            *snapshot.provenance_refs,
        }
        signed_evidence = set(envelope.evidence_refs)
        if (
            snapshot.authority_tier not in {
                "official_first_party", "official_mirror", "third_party_verified",
                "synthetic_test_only",
            }
            or (snapshot.authority_tier == "synthetic_test_only" and self._trust.target_environment != "test")
            or snapshot.retrieved_at < snapshot.publication_time
            or now < snapshot.retrieved_at
            or envelope.run_identity_ref is not None
            or envelope.issued_at < snapshot.retrieved_at
            or len(signed_evidence) != len(envelope.evidence_refs)
            or not required_evidence <= signed_evidence
            or any(
                item not in required_evidence and item.kind != SOURCE_RETRIEVAL_RECEIPT_KIND
                for item in signed_evidence
            )
        ):
            _fail("CHECKER_SOURCE_BINDING", "source authenticity context differs")
        self._trust._fresh_without_replay().verify(
            envelope,
            expected_subject_digest=snapshot.raw_digest,
            expected_payload_digest=digest_value(payload),
            required_role="source_attestor",
            required_scope=SOURCE_AUTHENTICITY_SCOPE,
            required_artifact_kind=SOURCE_SNAPSHOT_KIND,
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(),
        )
        return snapshot

    def _run_and_request(
        self, reader: _Reader, run_ref: ContentRefV4, now: CanonicalTimeV4
    ) -> tuple[RunIdentityV4, CaseRequestV4, PackManifestV4, SourceBundleV4]:
        run = reader.self_digest(
            run_ref,
            kind=RUN_IDENTITY_KIND,
            scope=RUN_IDENTITY_SCOPE,
            contract=RunIdentityV4,
            digest_field="run_digest",
        )
        request = reader.contract(
            run.request_ref,
            kind=CASE_REQUEST_KIND,
            scope=CASE_REQUEST_SCOPE,
            contract=CaseRequestV4,
        )
        policy_ref = ContentRefV4(TRUST_POLICY_KIND, self._trust.policy.canonical_digest())
        if (
            run.request_ref.digest != request.canonical_digest()
            or run.source_bundle_ref != request.source_bundle_ref
            or run.evidence_manifest_ref != request.evidence_manifest_ref
            or run.fact_attestation_refs != request.fact_attestation_refs
            or run.rule_pack_ref != request.rule_pack_ref
            or run.trust_policy_ref != policy_ref
        ):
            _fail("CHECKER_RUN_BINDING", "run identity differs from request/trust inputs")
        pack_signature = reader.contract(
            run.rule_pack_ref,
            kind=PACK_SIGNATURE_KIND,
            scope=RULE_PACK_SCOPE,
            contract=PackSignatureV4,
        )
        manifest = reader.self_digest(
            pack_signature.manifest_ref,
            kind=PACK_MANIFEST_KIND,
            scope=RULE_PACK_SCOPE,
            contract=PackManifestV4,
            digest_field="manifest_digest",
        )
        if (
            manifest.trust_policy_ref != policy_ref
            or manifest.schema_digest != run.schema_digest
            or manifest.compiler_build_digest != run.engine_build_digest
        ):
            _fail("CHECKER_PACK_BINDING", "pack manifest differs from the run build")
        signature = pack_signature.signature
        if signature.run_identity_ref is not None:
            _fail("CHECKER_PACK_BINDING", "pack release must precede run identity")
        self._trust._fresh_without_replay().verify(
            signature,
            expected_subject_digest=pack_signature.manifest_ref.digest,
            expected_payload_digest=digest_value(pack_signature.signature_body()),
            required_role="pack_releaser",
            required_scope="pack-release",
            required_artifact_kind="rule-pack",
            expected_status="APPROVED",
            now=now,
            separation_from_principals=(),
        )
        source_bundle = reader.self_digest(
            request.source_bundle_ref,
            kind=SOURCE_BUNDLE_KIND,
            scope=SOURCE_PATH_SCOPE,
            contract=SourceBundleV4,
            digest_field="bundle_digest",
        )
        if not source_bundle.snapshots:
            _fail("CHECKER_SOURCE_BINDING", "run source bundle is empty")
        for embedded in source_bundle.snapshots:
            reference = ContentRefV4(
                SOURCE_SNAPSHOT_KIND,
                DigestV4.from_bytes(embedded.canonical_bytes()),
            )
            if self._source_snapshot(reader, reference, now=now) != embedded:
                _fail("CHECKER_SOURCE_BINDING", "bundle snapshot differs from canonical bytes")
        return run, request, manifest, source_bundle

    def _backend_identity(
        self,
        reader: _Reader,
        invocation: BackendInvocationV4,
        problem: dict[str, object],
        problem_ref: ContentRefV4,
    ) -> None:
        limits = reader.json(
            invocation.limits_ref,
            kind=BACKEND_LIMITS_KIND,
            scope=BACKEND_SCOPE,
        )
        capability = reader.json(
            invocation.provider_capability_ref,
            kind=BACKEND_CAPABILITY_KIND,
            scope=BACKEND_SCOPE,
        )
        capability_fields = {
            "schema_version", "provider_id", "provider_version",
            "certified_semantics", "features", "solver_deadline_ms",
            "implementation_kind", "provider_binary_digest",
            "provider_package_digest", "provider_build_inputs",
            "provider_build_digest",
        }
        semantics = {
            HORN_PROVIDER_ID: (
                "constitutive-horn-least-fixpoint-plus-deontic-applicability"
            ),
            AAF_PROVIDER_ID: "finite-typed-dung-grounded-with-empty-framework",
            EXACT_PROVIDER_ID: "applicable-integer-rational-gregorian-closed-form",
        }
        if (
            set(limits) != {"schema_version", "solver_deadline_ms", "seed"}
            or limits.get("schema_version") != "jc/backend-limits/1.0"
            or type(limits.get("solver_deadline_ms")) is not int
            or limits["solver_deadline_ms"] <= 0
            or limits.get("seed") != invocation.seed
            or set(capability) != capability_fields
            or capability.get("schema_version") != "jc/backend-capability/1.0"
            or capability.get("provider_id") != invocation.provider_id
            or capability.get("provider_version") != invocation.provider_version
            or capability.get("certified_semantics") != semantics.get(invocation.provider_id)
            or capability.get("features") != problem.get("features")
            or capability.get("solver_deadline_ms") != limits["solver_deadline_ms"]
            or capability.get("implementation_kind") != "pure-python-source"
            or type(capability.get("provider_build_inputs")) is not dict
            or not capability["provider_build_inputs"]
            or invocation.invocation_id != f"backend-{problem_ref.digest.hex}"
            or invocation.algorithm_profile_digest != digest_value({
                "provider_id": invocation.provider_id,
                "provider_version": invocation.provider_version,
                "features": problem.get("features"),
            })
        ):
            _fail("CHECKER_BACKEND_BUILD", "backend capability or limits binding differs")
        try:
            binary_digest = DigestV4.parse(capability["provider_binary_digest"])
            package_digest = DigestV4.parse(capability["provider_package_digest"])
            build_digest = DigestV4.parse(capability["provider_build_digest"])
        except (TypeError, ValueError) as exc:
            raise IndependentCheckerV4Error(
                "CHECKER_BACKEND_BUILD", "backend build digests are malformed"
            ) from exc
        build_body = dict(capability)
        del build_body["provider_build_digest"]
        if (
            binary_digest != invocation.provider_binary_digest
            or package_digest != invocation.provider_package_digest
            or build_digest != invocation.provider_build_digest
            or build_digest != digest_value(build_body)
        ):
            _fail("CHECKER_BACKEND_BUILD", "backend invocation does not bind capability bytes")

    def _fact_rows(
        self,
        reader: _Reader,
        problem: dict[str, object],
        run: RunIdentityV4,
        run_ref: ContentRefV4,
        request: CaseRequestV4,
        source_bundle: SourceBundleV4,
        now: CanonicalTimeV4,
    ) -> list[dict[str, object]]:
        rows = problem.get("facts")
        if type(rows) is not list or not rows:
            _fail("CHECKER_FACT_BINDING", "formal backend requires admitted facts")
        request_binding = _request_binding_ref(request)
        applicable_sources = tuple(
            ContentRefV4(
                SOURCE_SNAPSHOT_KIND,
                DigestV4.from_bytes(item.canonical_bytes()),
            )
            for item in source_bundle.snapshots
            if item.effective_from <= request.decision_time
            and (item.effective_to is None or request.decision_time < item.effective_to)
        )
        if len(applicable_sources) != 1:
            _fail("CHECKER_SOURCE_BINDING", "request must have one applicable source version")
        applicable_source = applicable_sources[0]
        expected: list[dict[str, object]] = []
        seen_receipts: set[ContentRefV4] = set()
        for row in rows:
            if type(row) is not dict:
                _fail("CHECKER_FACT_BINDING", "backend fact row is malformed")
            receipt_ref = _wire_ref(row.get("admission_receipt_ref"), "admission_receipt_ref")
            if receipt_ref in seen_receipts:
                _fail("CHECKER_FACT_BINDING", "fact admission receipts repeat")
            seen_receipts.add(receipt_ref)
            receipt = reader.contract(
                receipt_ref,
                kind=FACT_ADMISSION_RECEIPT_KIND,
                scope=FACT_ADMISSION_SCOPE,
                contract=FactAdmissionReceiptV4,
            )
            fact = reader.json(receipt.fact_ref, kind=ADMITTED_FACT_KIND, scope=FACT_ADMISSION_SCOPE)
            required_fact_fields = {
                "schema_version", "status", "request_ref", "request_binding_ref",
                "case_scope", "run_identity_ref", "manifest_ref", "candidate_ref",
                "proposition_ref", "value_kind", "value_ref", "source_refs",
                "evidence_refs", "attestation_ref",
            }
            if set(fact) != required_fact_fields:
                _fail("CHECKER_FACT_BINDING", "admitted fact is not a closed artifact")
            candidate_ref = _wire_ref(fact["candidate_ref"], "candidate_ref")
            candidate = reader.contract(
                candidate_ref,
                kind=FACT_CANDIDATE_KIND,
                scope=FACT_ADMISSION_SCOPE,
                contract=FactCandidateV4,
            )
            attestation_ref = _wire_ref(fact["attestation_ref"], "attestation_ref")
            attestation = reader.contract(
                attestation_ref,
                kind=FACT_ATTESTATION_KIND,
                scope=LEGAL_APPROVAL_SCOPE,
                contract=FactAttestationV4,
            )
            manifest_ref = _wire_ref(fact["manifest_ref"], "manifest_ref")
            evidence_manifest = reader.self_digest(
                manifest_ref,
                kind=EVIDENCE_MANIFEST_KIND,
                scope=CASE_EVIDENCE_SCOPE,
                contract=EvidenceManifestV4,
                digest_field="manifest_digest",
            )
            proposition_ref = _wire_ref(fact["proposition_ref"], "proposition_ref")
            value_ref = _wire_ref(fact["value_ref"], "value_ref")
            proposition = reader.json(
                proposition_ref, kind=FACT_PROPOSITION_KIND, scope=FACT_ADMISSION_SCOPE
            )
            value = reader.json(value_ref, kind=FACT_VALUE_KIND, scope=FACT_ADMISSION_SCOPE)
            fact_sources = _wire_refs(fact["source_refs"], "source_refs")
            evidence_refs = _wire_refs(fact["evidence_refs"], "evidence_refs")
            if (
                receipt.request_ref != run.request_ref
                or receipt.run_identity_ref != run_ref
                or receipt.fact_ref != _wire_ref(row.get("fact_ref"), "fact_ref")
                or receipt.attestation_ref != attestation_ref
                or receipt.case_scope != problem["case_scope"]
                or receipt.status != "ADMITTED"
                or receipt.issuer != self._receipt_issuer
                or receipt.subject_digest != receipt.fact_ref.digest
                or receipt.receipt_id != f"fact-admission-{receipt.fact_ref.digest.hex}"
                or receipt.signature.issued_at != receipt.issued_at
                or fact.get("schema_version") != "jc/admitted-fact/1.0"
                or fact.get("status") != "ADMITTED"
                or _wire_ref(fact["request_ref"], "request_ref") != run.request_ref
                or _wire_ref(fact["request_binding_ref"], "request_binding_ref") != request_binding
                or fact["case_scope"] != receipt.case_scope
                or _wire_ref(fact["run_identity_ref"], "run_identity_ref") != run_ref
                or manifest_ref != run.evidence_manifest_ref
                or evidence_manifest.request_ref != request_binding
                or evidence_manifest.case_scope != receipt.case_scope
                or candidate_ref not in evidence_manifest.fact_candidate_refs
                or attestation_ref not in run.fact_attestation_refs
                or attestation.candidate_ref != candidate_ref
                or attestation.request_ref != request_binding
                or attestation.case_scope != receipt.case_scope
                or attestation.proposition_digest != proposition_ref.digest
                or attestation.value_digest != value_ref.digest
                or attestation.admission_basis not in {
                    "documentary_evidence_human_reviewed", "judicial_notice",
                    "admitted_by_opponent", "presumption_of_law",
                }
                or attestation.issuer_role != "legal_reviewer"
                or attestation.dispute_state != "UNDISPUTED"
                or attestation.assumption_state != "NONE"
                or attestation.revocation_ref is not None
                or now < attestation.issued_at
                or attestation.expires_at is None
                or not now < attestation.expires_at
                or attestation.replay_policy_ref != self._trust.policy.replay_policy_ref
                or candidate.proposition_ref != proposition_ref
                or candidate.value_ref != value_ref
                or candidate.value_kind != fact["value_kind"]
                or candidate.evidence_refs != evidence_refs
                or candidate.producer_kind not in {"agent", "extraction", "lawyer", "system"}
                or fact_sources != (applicable_source,)
                or attestation.source_refs != fact_sources
                or attestation.evidence_refs != evidence_refs
                or proposition.get("schema_version") != "jc/fact-proposition/1.0"
                or set(proposition) != {"schema_version", "proposition"}
                or value.get("schema_version") != "jc/fact-value/1.0"
                or set(value) != {"schema_version", "value_kind", "value"}
                or value.get("value_kind") != candidate.value_kind
            ):
                _fail("CHECKER_FACT_BINDING", "fact row differs from request evidence materials")
            legal_evidence = _sorted_refs((
                request_binding,
                manifest_ref,
                candidate_ref,
                proposition_ref,
                value_ref,
                *fact_sources,
                *evidence_refs,
                attestation.replay_policy_ref,
            ))
            if (
                attestation.signature.run_identity_ref is not None
                or attestation.signature.evidence_refs != legal_evidence
                or attestation.signature.nonce != attestation.nonce
                or attestation.signature.issued_at != attestation.issued_at
                or attestation.signature.expires_at != attestation.expires_at
            ):
                _fail("CHECKER_FACT_SIGNATURE", "fact attestation evidence differs")
            self._trust._fresh_without_replay().verify(
                attestation.signature,
                expected_subject_digest=candidate_ref.digest,
                expected_payload_digest=digest_value(attestation.signature_body()),
                required_role="legal_reviewer",
                required_scope="legal-approval",
                required_artifact_kind="legal-approval",
                expected_status="APPROVED",
                now=now,
                separation_from_principals=(),
            )
            common = {
                "schema_version": "jc/fact-gate/1.0",
                "status": "PASS",
                "request_ref": run.request_ref.to_dict(),
                "request_binding_ref": request_binding.to_dict(),
                "case_scope": receipt.case_scope,
                "run_identity_ref": run_ref.to_dict(),
                "candidate_ref": candidate_ref.to_dict(),
            }
            gates = (
                (
                    receipt.source_gate_receipt_ref,
                    SOURCE_GATE_RECEIPT_KIND,
                    {
                        **common,
                        "gate": "source",
                        "source_bundle_ref": request.source_bundle_ref.to_dict(),
                        "source_refs": [item.to_dict() for item in fact_sources],
                    },
                ),
                (
                    receipt.interpretation_gate_receipt_ref,
                    INTERPRETATION_GATE_RECEIPT_KIND,
                    {
                        **common,
                        "gate": "interpretation",
                        "proposition_ref": proposition_ref.to_dict(),
                        "value_kind": candidate.value_kind,
                        "value_ref": value_ref.to_dict(),
                        "interpretation_version": attestation.interpretation_version,
                    },
                ),
                (
                    receipt.fact_gate_receipt_ref,
                    FACT_GATE_RECEIPT_KIND,
                    {
                        **common,
                        "gate": "fact",
                        "manifest_ref": manifest_ref.to_dict(),
                        "attestation_ref": attestation_ref.to_dict(),
                        "evidence_refs": [item.to_dict() for item in evidence_refs],
                    },
                ),
            )
            for gate_ref, kind, expected_gate in gates:
                if reader.json(gate_ref, kind=kind, scope=FACT_ADMISSION_SCOPE) != expected_gate:
                    _fail("CHECKER_FACT_GATE", f"{kind} differs from independent reconstruction")
            receipt_evidence = _sorted_refs((
                run.request_ref,
                request_binding,
                manifest_ref,
                candidate_ref,
                attestation_ref,
                receipt.fact_ref,
                receipt.source_gate_receipt_ref,
                receipt.interpretation_gate_receipt_ref,
                receipt.fact_gate_receipt_ref,
                *fact_sources,
                *evidence_refs,
                self._trust.policy.replay_policy_ref,
            ))
            self._service_signature(
                receipt.signature,
                subject=receipt.fact_ref.digest,
                payload=digest_value(receipt.signature_body()),
                evidence=receipt_evidence,
                run_ref=run_ref,
                now=now,
                issuer=self._receipt_issuer,
            )
            expected.append({
                "admission_receipt_ref": receipt_ref.to_dict(),
                "fact_ref": receipt.fact_ref.to_dict(),
                "case_scope": receipt.case_scope,
                "proposition": proposition["proposition"],
                "value_kind": value["value_kind"],
                "value": value["value"],
            })
        expected.sort(key=lambda row: (row["proposition"], str(row["fact_ref"])))
        if rows != expected:
            _fail("CHECKER_FACT_BINDING", "backend facts differ from admitted fact bytes")
        return expected

    @staticmethod
    def _component(
        reader: _Reader,
        reference: ContentRefV4,
        *,
        owner_rule_id: str,
        selected_rule_ids: set[str],
    ) -> dict[str, object]:
        value = reader.json(reference, kind=reference.kind, scope=RULE_COMPONENT_SCOPE)
        allowed = {
            RULE_PREMISE_KIND: {"schema_version", "rule_id", "fact_key", "required"},
            RULE_CONCLUSION_KIND: {"schema_version", "rule_id", "fact_key", "value"},
            RULE_EXCEPTION_KIND: {
                "schema_version", "rule_id", "attacker", "target", "attack_type",
                "target_aspect", "condition_fact_key",
            },
            RULE_ATTACK_KIND: {
                "schema_version", "rule_id", "attacker", "target", "attack_type",
                "target_aspect", "condition_fact_key",
            },
            RULE_PRIORITY_KIND: {
                "schema_version", "rule_id", "source", "target", "condition",
            },
            RULE_PERMISSION_KIND: {
                "schema_version", "rule_id", "permission_id", "permits",
                "relation_to", "relation_kind",
            },
            RULE_TEMPORAL_KIND: {
                "schema_version", "rule_id", "target_rule_id", "operation", "start", "end",
            },
            RULE_NUMERIC_KIND: {
                "schema_version", "rule_id", "target_rule_id", "operation", "operands",
                "fact_key", "ratio",
            },
        }.get(reference.kind)
        required = {
            RULE_PREMISE_KIND: {"schema_version", "rule_id", "fact_key", "required"},
            RULE_CONCLUSION_KIND: {"schema_version", "rule_id"},
            RULE_EXCEPTION_KIND: {
                "schema_version", "rule_id", "attacker", "target", "attack_type",
                "target_aspect", "condition_fact_key",
            },
            RULE_ATTACK_KIND: {
                "schema_version", "rule_id", "attacker", "target", "attack_type",
                "target_aspect",
            },
            RULE_PRIORITY_KIND: {
                "schema_version", "rule_id", "source", "target", "condition",
            },
            RULE_PERMISSION_KIND: {
                "schema_version", "rule_id", "permission_id", "permits",
                "relation_to", "relation_kind",
            },
            RULE_TEMPORAL_KIND: {"schema_version", "rule_id", "start", "end"},
            RULE_NUMERIC_KIND: {"schema_version", "rule_id", "operation"},
        }.get(reference.kind)
        if (
            allowed is None
            or required is None
            or value.get("schema_version") != f"jc/{reference.kind}/1.0"
            or value.get("rule_id") != owner_rule_id
            or not required <= set(value) <= allowed
            or (
                reference.kind == RULE_CONCLUSION_KIND
                and len({"fact_key", "value"} & set(value)) != 1
            )
        ):
            _fail("CHECKER_COMPONENT_SCHEMA", f"{reference.kind} is not a closed component")
        target = value.get("target_rule_id")
        if target is not None and target not in selected_rule_ids:
            _fail("CHECKER_COMPONENT_SCHEMA", "constraint target leaves selected IVLs")
        if reference.kind in {RULE_EXCEPTION_KIND, RULE_ATTACK_KIND} and (
            value.get("attacker") != owner_rule_id
            or value.get("target") not in selected_rule_ids
        ):
            _fail("CHECKER_COMPONENT_SCHEMA", "attack endpoints leave selected IVLs")
        if reference.kind == RULE_PRIORITY_KIND and (
            value.get("source") != owner_rule_id
            or value.get("target") not in selected_rule_ids
            or type(value.get("condition")) is not str
            or not value["condition"]
        ):
            _fail("CHECKER_COMPONENT_SCHEMA", "priority fields are malformed")
        if reference.kind == RULE_PERMISSION_KIND and (
            value.get("relation_to") not in selected_rule_ids
            or any(
                type(value.get(field)) is not str or not value[field]
                for field in ("permission_id", "permits", "relation_kind")
            )
        ):
            _fail("CHECKER_COMPONENT_SCHEMA", "permission fields are malformed")
        if reference.kind == RULE_PREMISE_KIND and (
            type(value.get("fact_key")) is not str
            or not value["fact_key"]
            or type(value.get("required")) is not bool
        ):
            _fail("CHECKER_COMPONENT_SCHEMA", "premise fields are malformed")
        if reference.kind == RULE_CONCLUSION_KIND and "fact_key" in value and (
            type(value["fact_key"]) is not str or not value["fact_key"]
        ):
            _fail("CHECKER_COMPONENT_SCHEMA", "conclusion fact key is malformed")
        return value

    def _translation_receipt(
        self,
        reader: _Reader,
        reference: ContentRefV4,
        *,
        hop: str,
        source_ref: ContentRefV4,
        target_ref: ContentRefV4,
        source_type: type,
        target_type: type,
        run: RunIdentityV4,
        run_ref: ContentRefV4,
        manifest_ref: ContentRefV4,
        approval_refs: tuple[ContentRefV4, ...],
        previous_ref: ContentRefV4 | None,
        now: CanonicalTimeV4,
    ) -> TranslationReceiptV4:
        receipt = reader.contract(
            reference,
            kind=TRANSLATION_RECEIPT_KIND,
            scope=LEGAL_IR_SCOPE,
            contract=TranslationReceiptV4,
        )
        coverage = tuple(item.name for item in fields(source_type))
        mapping = reader.json(
            receipt.field_mapping_ref, kind=IR_FIELD_MAPPING_KIND, scope=LEGAL_IR_SCOPE
        )
        mappings = mapping.get("mappings")
        if (
            mapping.get("schema_version") != "jc/legal-ir-field-mapping/1.0"
            or mapping.get("hop") != hop
            or mapping.get("source_ref") != source_ref.to_dict()
            or mapping.get("target_ref") != target_ref.to_dict()
            or mapping.get("source_contract") != source_type.__name__
            or mapping.get("target_contract") != target_type.__name__
            or mapping.get("source_fields") != list(coverage)
            or type(mappings) is not list
            or {
                name
                for row in mappings
                if type(row) is dict
                for name in row.get("source_fields", [])
            } != set(coverage)
            or any(
                type(row) is not dict
                or row.get("disposition") not in {"preserve", "lower"}
                or set(row) != {"source_fields", "target_fields", "disposition", "transform"}
                for row in mappings
            )
        ):
            _fail("CHECKER_TRANSLATION_MAPPING", "field mapping is not exhaustive zero-loss")
        translator = reader.json(
            receipt.translator_ref, kind=IR_TRANSLATOR_KIND, scope=LEGAL_IR_SCOPE
        )
        if translator != {
            "schema_version": "jc/legal-ir-translator/1.0",
            "implementation": "compiler_core.legal_ir:LegalIRCompilerV4",
            "hop": hop,
            "engine_build_digest": str(run.engine_build_digest),
            "package_digest": str(run.package_digest),
            "schema_digest": str(run.schema_digest),
            "algorithm_profile_digest": str(run.algorithm_profile_digest),
        }:
            _fail("CHECKER_TRANSLATOR_BINDING", "translator build differs from run identity")
        expected_id = f"translation-{target_ref.digest.hex}-{hop.split('->')[0].lower()}"
        if (
            receipt.receipt_id != expected_id
            or receipt.run_identity_ref != run_ref
            or receipt.hop != hop
            or receipt.source_ref != source_ref
            or receipt.target_ref != target_ref
            or receipt.field_coverage != coverage
            or receipt.lost_fields
            or receipt.defaulted_fields
            or receipt.unsupported_fields
            or receipt.counterexample_refs
            or receipt.status != "PASS"
            or receipt.signature.issued_at != receipt.issued_at
        ):
            _fail("CHECKER_TRANSLATION_RECEIPT", "translation receipt is not exact zero-loss PASS")
        evidence = _sorted_refs((
            run.rule_pack_ref,
            manifest_ref,
            run_ref,
            receipt.translator_ref,
            source_ref,
            target_ref,
            receipt.field_mapping_ref,
            *approval_refs,
            *receipt.proof_obligation_refs,
            *((previous_ref,) if previous_ref is not None else ()),
            self._trust.policy.replay_policy_ref,
        ))
        self._service_signature(
            receipt.signature,
            subject=target_ref.digest,
            payload=digest_value(receipt.signature_body()),
            evidence=evidence,
            run_ref=run_ref,
            now=now,
        )
        return receipt

    def _clauses(
        self,
        reader: _Reader,
        problem: dict[str, object],
        run: RunIdentityV4,
        run_ref: ContentRefV4,
        manifest: PackManifestV4,
        now: CanonicalTimeV4,
    ) -> list[dict[str, object]]:
        observed = problem.get("clauses")
        if type(observed) is not list or not observed:
            _fail("CHECKER_IR_BINDING", "backend clauses must be non-empty")
        ids = [row.get("ivl_id") for row in observed if type(row) is dict]
        if len(ids) != len(observed) or len(ids) != len(set(ids)):
            _fail("CHECKER_IR_BINDING", "backend IVL identities repeat or are malformed")
        selected_ids = set(ids)
        expected_rows: list[dict[str, object]] = []
        for row in observed:
            ivl_ref = _wire_ref(row.get("ivl_ref"), "ivl_ref")
            ivl = reader.self_digest(
                ivl_ref,
                kind=LEGAL_IVL_KIND,
                scope=LEGAL_IR_SCOPE,
                contract=LegalIVLV4,
                digest_field="ivl_digest",
            )
            spec = reader.self_digest(
                ivl.spec_ref,
                kind=LEGAL_SPEC_KIND,
                scope=LEGAL_IR_SCOPE,
                contract=LegalSpecV4,
                digest_field="spec_digest",
            )
            rule = reader.self_digest(
                spec.rule_ref,
                kind=RULE_KIND,
                scope=RULE_PACK_SCOPE,
                contract=RuleV4,
                digest_field="rule_digest",
            )
            if spec.rule_ref not in manifest.rule_refs:
                _fail("CHECKER_PACK_BINDING", "backend rule is outside the run-bound pack")
            if rule.source_snapshot_ref not in manifest.source_refs:
                _fail("CHECKER_PACK_BINDING", "rule source is outside the run-bound pack")
            source = self._source_snapshot(reader, rule.source_snapshot_ref, now=now)
            if (
                rule.jurisdiction != source.jurisdiction
                or rule.source_locator != source.canonical_locator
                or rule.source_structure_ref != source.structure_map_ref
                or rule.effective_from < source.effective_from
                or (
                    source.effective_to is not None
                    and (rule.effective_to is None or source.effective_to < rule.effective_to)
                )
            ):
                _fail("CHECKER_SOURCE_BINDING", "rule validity or locator differs from source")
            rule_body = rule.to_dict()
            expected_spec_body = {
                "spec_id": rule.rule_id,
                "rule_ref": spec.rule_ref.to_dict(),
                **{
                    name: rule_body[name]
                    for name in (
                        "jurisdiction", "governing_law", "authority_ref",
                        "variable_declaration_refs", "premise_refs", "conclusion_ref",
                        "modality", "permission_ref", "exception_refs", "priority_refs",
                        "attack_refs", "temporal_constraint_refs", "numeric_constraint_refs",
                        "source_snapshot_ref", "source_locator", "source_structure_ref",
                        "interpretation_choice_refs", "defined_term_refs",
                        "promotion_receipt_refs", "effective_from", "effective_to",
                    )
                },
            }
            if spec.digest_body() != expected_spec_body:
                _fail("CHECKER_TRANSLATION_LOSS", "RuleV4 to LegalSpecV4 projection changed")
            if len(rule.promotion_receipt_refs) != 1:
                _fail("CHECKER_PACK_BINDING", "formal rule lacks one promotion receipt")
            promotion = reader.contract(
                rule.promotion_receipt_refs[0],
                kind=RULE_PROMOTION_RECEIPT_KIND,
                scope=RULE_PACK_SCOPE,
                contract=RulePromotionReceiptV4,
            )
            approval_refs = (promotion.legal_review_ref,)
            if ivl.interpretation_approval_refs != approval_refs:
                _fail("CHECKER_TRANSLATION_LOSS", "interpretation approval was not preserved")
            type_environment = {
                "schema_version": "jc/legal-ir-type-environment/1.0",
                "spec_ref": ivl.spec_ref.to_dict(),
                "jurisdiction": spec.jurisdiction,
                "governing_law": spec.governing_law,
                "variable_declaration_refs": [item.to_dict() for item in spec.variable_declaration_refs],
                "defined_term_refs": [item.to_dict() for item in spec.defined_term_refs],
            }
            modality = {
                "schema_version": "jc/legal-ir-modality/1.0",
                "spec_ref": ivl.spec_ref.to_dict(),
                "modality": spec.modality,
                "permission_ref": None if spec.permission_ref is None else spec.permission_ref.to_dict(),
            }
            clause = {
                "schema_version": "jc/legal-ir-clause/1.0",
                "spec_ref": ivl.spec_ref.to_dict(),
                "premise_refs": [item.to_dict() for item in spec.premise_refs],
                "conclusion_ref": spec.conclusion_ref.to_dict(),
                "modality_ref": ivl.modality_ref.to_dict(),
                "effective_from": spec.effective_from.to_dict(),
                "effective_to": None if spec.effective_to is None else spec.effective_to.to_dict(),
            }
            source_map = {
                "schema_version": "jc/legal-ir-source-map/1.0",
                "spec_ref": ivl.spec_ref.to_dict(),
                "rule_ref": spec.rule_ref.to_dict(),
                "source_snapshot_ref": spec.source_snapshot_ref.to_dict(),
                "source_locator": spec.source_locator.to_dict(),
                "source_structure_ref": spec.source_structure_ref.to_dict(),
                "promotion_receipt_refs": [item.to_dict() for item in spec.promotion_receipt_refs],
                "effective_from": spec.effective_from.to_dict(),
                "effective_to": None if spec.effective_to is None else spec.effective_to.to_dict(),
            }
            if reader.json(
                ivl.type_environment_ref,
                kind=IR_TYPE_ENVIRONMENT_KIND,
                scope=LEGAL_IR_SCOPE,
            ) != type_environment or reader.json(
                ivl.modality_ref, kind=IR_MODALITY_KIND, scope=LEGAL_IR_SCOPE
            ) != modality or len(ivl.clause_refs) != 1 or reader.json(
                ivl.clause_refs[0], kind=IR_CLAUSE_KIND, scope=LEGAL_IR_SCOPE
            ) != clause or reader.json(
                ivl.source_map_ref, kind=IR_SOURCE_MAP_KIND, scope=LEGAL_IR_SCOPE
            ) != source_map:
                _fail("CHECKER_TRANSLATION_LOSS", "derived IVL artifact differs from LegalSpecV4")
            if len(ivl.proof_obligation_refs) != 1:
                _fail("CHECKER_TRANSLATION_LOSS", "IVL proof obligation cardinality differs")
            expected_proof = {
                "schema_version": "jc/legal-ir-proof-obligation/1.0",
                "obligation": "loss-accounted-ivl-lowering",
                "spec_ref": ivl.spec_ref.to_dict(),
                "type_environment_ref": ivl.type_environment_ref.to_dict(),
                "modality_ref": ivl.modality_ref.to_dict(),
                "clause_refs": [item.to_dict() for item in ivl.clause_refs],
                "source_map_ref": ivl.source_map_ref.to_dict(),
                "authority_ref": spec.authority_ref.to_dict(),
                "exception_attack_refs": [
                    item.to_dict() for item in (*spec.exception_refs, *spec.attack_refs)
                ],
                "permission_refs": [] if spec.permission_ref is None else [spec.permission_ref.to_dict()],
                "priority_refs": [item.to_dict() for item in spec.priority_refs],
                "temporal_constraint_refs": [item.to_dict() for item in spec.temporal_constraint_refs],
                "numeric_constraint_refs": [item.to_dict() for item in spec.numeric_constraint_refs],
                "interpretation_choice_refs": [item.to_dict() for item in spec.interpretation_choice_refs],
                "interpretation_approval_refs": [item.to_dict() for item in approval_refs],
                "defined_term_refs": [item.to_dict() for item in spec.defined_term_refs],
            }
            if reader.json(
                ivl.proof_obligation_refs[0],
                kind=IR_PROOF_OBLIGATION_KIND,
                scope=LEGAL_IR_SCOPE,
            ) != expected_proof:
                _fail("CHECKER_TRANSLATION_LOSS", "IVL proof obligation differs")
            expected_ivl_body = {
                "ivl_id": spec.spec_id,
                "spec_ref": ivl.spec_ref.to_dict(),
                "type_environment_ref": ivl.type_environment_ref.to_dict(),
                "authority_ref": spec.authority_ref.to_dict(),
                "variable_declaration_refs": [item.to_dict() for item in spec.variable_declaration_refs],
                "premise_refs": [item.to_dict() for item in spec.premise_refs],
                "conclusion_ref": spec.conclusion_ref.to_dict(),
                "modality_ref": ivl.modality_ref.to_dict(),
                "clause_refs": [item.to_dict() for item in ivl.clause_refs],
                "exception_attack_refs": [
                    item.to_dict() for item in (*spec.exception_refs, *spec.attack_refs)
                ],
                "permission_refs": [] if spec.permission_ref is None else [spec.permission_ref.to_dict()],
                "priority_refs": [item.to_dict() for item in spec.priority_refs],
                "temporal_constraint_refs": [item.to_dict() for item in spec.temporal_constraint_refs],
                "numeric_constraint_refs": [item.to_dict() for item in spec.numeric_constraint_refs],
                "source_map_ref": ivl.source_map_ref.to_dict(),
                "interpretation_choice_refs": [item.to_dict() for item in spec.interpretation_choice_refs],
                "interpretation_approval_refs": [item.to_dict() for item in approval_refs],
                "defined_term_refs": [item.to_dict() for item in spec.defined_term_refs],
                "proof_obligation_refs": [item.to_dict() for item in ivl.proof_obligation_refs],
            }
            if ivl.digest_body() != expected_ivl_body:
                _fail("CHECKER_TRANSLATION_LOSS", "LegalSpecV4 to LegalIVLV4 projection changed")
            translation_refs = _wire_refs(row.get("translation_receipt_refs"), "translation_receipt_refs")
            if len(translation_refs) != 2:
                _fail("CHECKER_TRANSLATION_RECEIPT", "backend clause requires two translation receipts")
            first = self._translation_receipt(
                reader,
                translation_refs[0],
                hop="RuleV4->LegalSpecV4",
                source_ref=spec.rule_ref,
                target_ref=ivl.spec_ref,
                source_type=RuleV4,
                target_type=LegalSpecV4,
                run=run,
                run_ref=run_ref,
                manifest_ref=ContentRefV4(PACK_MANIFEST_KIND, manifest.manifest_digest),
                approval_refs=approval_refs,
                previous_ref=None,
                now=now,
            )
            self._translation_receipt(
                reader,
                translation_refs[1],
                hop="LegalSpecV4->LegalIVLV4",
                source_ref=ivl.spec_ref,
                target_ref=ivl_ref,
                source_type=LegalSpecV4,
                target_type=LegalIVLV4,
                run=run,
                run_ref=run_ref,
                manifest_ref=ContentRefV4(PACK_MANIFEST_KIND, manifest.manifest_digest),
                approval_refs=approval_refs,
                previous_ref=translation_refs[0],
                now=now,
            )
            first_proof = first.proof_obligation_refs
            if len(first_proof) != 1 or reader.json(
                first_proof[0], kind=IR_PROOF_OBLIGATION_KIND, scope=LEGAL_IR_SCOPE
            ) != {
                "schema_version": "jc/legal-ir-proof-obligation/1.0",
                "obligation": "loss-accounted-spec-translation",
                "source_ref": spec.rule_ref.to_dict(),
                "target_ref": ivl.spec_ref.to_dict(),
                "field_mapping_ref": first.field_mapping_ref.to_dict(),
            }:
                _fail("CHECKER_TRANSLATION_RECEIPT", "RuleV4 proof obligation differs")
            premises = [
                self._component(
                    reader,
                    item,
                    owner_rule_id=ivl.ivl_id,
                    selected_rule_ids=selected_ids,
                )
                for item in ivl.premise_refs
            ]
            conclusion = self._component(
                reader,
                ivl.conclusion_ref,
                owner_rule_id=ivl.ivl_id,
                selected_rule_ids=selected_ids,
            )
            relations: list[dict[str, object]] = []
            for reference in ivl.exception_attack_refs:
                component = self._component(
                    reader,
                    reference,
                    owner_rule_id=ivl.ivl_id,
                    selected_rule_ids=selected_ids,
                )
                relations.append({
                    "kind": "attack",
                    "source_ref": reference.to_dict(),
                    "attack_type": component.get("attack_type", "undercut"),
                    "target_aspect": (
                        "rule_applicability"
                        if component.get("target_aspect", "rule_applicability") == "applicability"
                        else component.get("target_aspect", "rule_applicability")
                    ),
                    "source": component.get("attacker"),
                    "target": component.get("target"),
                    "condition_fact_key": component.get("condition_fact_key"),
                })
            for reference in ivl.priority_refs:
                component = self._component(
                    reader,
                    reference,
                    owner_rule_id=ivl.ivl_id,
                    selected_rule_ids=selected_ids,
                )
                relations.append({
                    "kind": "priority",
                    "source_ref": reference.to_dict(),
                    "source": component.get("source"),
                    "target": component.get("target"),
                    "condition": component.get("condition"),
                })
            for reference in ivl.permission_refs:
                component = self._component(
                    reader,
                    reference,
                    owner_rule_id=ivl.ivl_id,
                    selected_rule_ids=selected_ids,
                )
                relations.append({
                    "kind": "permission",
                    "source_ref": reference.to_dict(),
                    "permission_id": component.get("permission_id"),
                    "permits": component.get("permits"),
                    "relation_kind": component.get("relation_kind"),
                    "source": ivl.ivl_id,
                    "target": component.get("relation_to"),
                })
            relations.sort(key=lambda item: (str(item["kind"]), str(item["source"]), str(item["target"])))

            def constraints(refs: tuple[ContentRefV4, ...]) -> list[dict[str, object]]:
                return [
                    {
                        "constraint_ref": reference.to_dict(),
                        "owner_ivl_id": ivl.ivl_id,
                        "target_ivl_id": component.get("target_rule_id", ivl.ivl_id),
                        "expression": component,
                    }
                    for reference in refs
                    for component in [self._component(
                        reader,
                        reference,
                        owner_rule_id=ivl.ivl_id,
                        selected_rule_ids=selected_ids,
                    )]
                ]

            expected_rows.append({
                "ivl_id": ivl.ivl_id,
                "ivl_ref": ivl_ref.to_dict(),
                "rule_ref": spec.rule_ref.to_dict(),
                "translation_receipt_refs": [item.to_dict() for item in translation_refs],
                "premise_refs": [item.to_dict() for item in ivl.premise_refs],
                "premises": premises,
                "conclusion_ref": ivl.conclusion_ref.to_dict(),
                "conclusion": conclusion,
                "derivation_refs": [item.to_dict() for item in ivl.proof_obligation_refs],
                "modality": spec.modality,
                "effective_from": spec.effective_from.wire,
                "effective_to": None if spec.effective_to is None else spec.effective_to.wire,
                "relations": relations,
                "temporal_constraints": constraints(ivl.temporal_constraint_refs),
                "numeric_constraints": constraints(ivl.numeric_constraint_refs),
            })
        expected_rows.sort(key=lambda item: (item["ivl_id"], item["ivl_ref"]["digest"]))
        if observed != expected_rows:
            _fail("CHECKER_IR_BINDING", "backend clauses differ from canonical IVL artifacts")
        expected_features = {
            "conflict_structure": any(
                row["relations"] for row in expected_rows
            ),
            "temporal_constraints": any(row["temporal_constraints"] for row in expected_rows),
            "numeric_constraints": any(row["numeric_constraints"] for row in expected_rows),
        }
        if problem.get("features") != expected_features:
            _fail("CHECKER_FEATURE_BINDING", "backend features were not derived from IVL")
        return expected_rows

    def _recompute(
        self,
        *,
        run_identity_ref: ContentRefV4,
        solver_receipt_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> _CheckMaterial:
        with self._resolver._snapshot():
            return self._recompute_pinned(
                run_identity_ref=run_identity_ref,
                solver_receipt_ref=solver_receipt_ref,
                now=now,
            )

    def _recompute_pinned(
        self,
        *,
        run_identity_ref: ContentRefV4,
        solver_receipt_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> _CheckMaterial:
        if (
            type(run_identity_ref) is not ContentRefV4
            or run_identity_ref.kind != RUN_IDENTITY_KIND
            or type(solver_receipt_ref) is not ContentRefV4
            or solver_receipt_ref.kind != SOLVER_RECEIPT_KIND
            or type(now) is not CanonicalTimeV4
        ):
            _fail("CHECKER_INPUT_TYPE", "checker requires exact run, solver receipt, and time")
        reader = _Reader(self._resolver)
        run, request, manifest, source_bundle = self._run_and_request(
            reader, run_identity_ref, now
        )
        receipt = reader.contract(
            solver_receipt_ref,
            kind=SOLVER_RECEIPT_KIND,
            scope=BACKEND_SCOPE,
            contract=SolverReceiptV4,
        )
        invocation = reader.contract(
            receipt.invocation_ref,
            kind=BACKEND_INVOCATION_KIND,
            scope=BACKEND_SCOPE,
            contract=BackendInvocationV4,
        )
        problem_ref = invocation.ir_ref
        problem = reader.json(problem_ref, kind=BACKEND_PROBLEM_KIND, scope=BACKEND_SCOPE)
        if set(problem) != {
            "schema_version", "provider_id", "run_identity_ref", "request_ref",
            "case_scope", "limits_ref", "decision_time", "seed", "features",
            "facts", "clauses",
        }:
            _fail("CHECKER_PROBLEM", "backend problem is not a closed artifact")
        self._backend_identity(reader, invocation, problem, problem_ref)
        result = reader.json(
            receipt.backend_result_ref, kind=BACKEND_RESULT_KIND, scope=BACKEND_SCOPE
        )
        if receipt.proof_ref is None:
            _fail("CHECKER_UNCHECKED_PROOF", "completed semantic result requires a proof artifact")
        proof = reader.json(receipt.proof_ref, kind=BACKEND_PROOF_KIND, scope=BACKEND_SCOPE)
        if (
            receipt.run_identity_ref != run_identity_ref
            or receipt.status != "COMPLETED"
            or receipt.exit_status != 0
            or receipt.model_or_core_ref is not None
            or receipt.signature.issued_at != receipt.issued_at
            or invocation.provider_id != problem.get("provider_id")
            or invocation.provider_version != PROVIDER_VERSION
            or problem.get("schema_version") != "jc/backend-problem/1.0"
            or problem.get("run_identity_ref") != run_identity_ref.to_dict()
            or problem.get("request_ref") != run.request_ref.to_dict()
            or problem.get("decision_time") != request.decision_time.wire
            or problem.get("limits_ref") != invocation.limits_ref.to_dict()
            or problem.get("seed") != invocation.seed
        ):
            _fail("CHECKER_BACKEND_BINDING", "solver invocation/problem/run binding differs")
        self._fact_rows(
            reader, problem, run, run_identity_ref, request, source_bundle, now
        )
        self._clauses(reader, problem, run, run_identity_ref, manifest, now)
        solver_evidence = (
            problem_ref,
            receipt.invocation_ref,
            receipt.backend_result_ref,
            receipt.proof_ref,
        )
        self._service_signature(
            receipt.signature,
            subject=receipt.backend_result_ref.digest,
            payload=digest_value(receipt.signature_body()),
            evidence=solver_evidence,
            run_ref=run_identity_ref,
            now=now,
        )
        analysis = _horn_analysis(problem)
        provider_id = invocation.provider_id
        condition_evidence: list[dict[str, object]] = []
        if provider_id == HORN_PROVIDER_ID:
            outcome = "FIXPOINT"
            outputs = {
                "derived_atoms": sorted(analysis["known"] - analysis["initial_true"]),
                "derived_refs": analysis["fired_refs"],
                "applicable_norms": analysis["applicable_norms"],
                "false_fact_keys": analysis["false_facts"],
                "missing_fact_keys": sorted(
                    analysis["required"] - analysis["known"] - set(analysis["facts"])
                ),
                "inactive_rule_ids": sorted(
                    row["ivl_id"] for row in analysis["intervals"] if not row["active"]
                ),
            }
            witness = {
                "bound": analysis["bound"],
                "trace": analysis["trace"],
                "least_fixpoint": sorted(analysis["known"]),
                "fired_rule_ids": analysis["fired_rule_ids"],
                "applicable_rule_ids": analysis["applicable_rule_ids"],
                "effective_intervals": analysis["intervals"],
            }
            graph = _semantic_state_graph(
                provider_id=provider_id,
                problem_ref=problem_ref,
                outcome=outcome,
                outputs=outputs,
            )
        elif provider_id == AAF_PROVIDER_ID:
            graph, evaluation, condition_evidence = _graph_and_evaluation(problem, analysis)
            outcome = evaluation["state"]
            outputs = evaluation
            witness = {
                "graph": graph,
                "evaluation": evaluation,
                "relation_condition_evidence": condition_evidence,
                "applicable_rule_ids": analysis["applicable_rule_ids"],
                "effective_intervals": analysis["intervals"],
            }
        elif provider_id == EXACT_PROVIDER_ID:
            outcome = "EXACT"
            outputs = _exact_outputs(problem, analysis)
            witness = outputs
            graph = _semantic_state_graph(
                provider_id=provider_id,
                problem_ref=problem_ref,
                outcome=outcome,
                outputs=outputs,
            )
        else:
            _fail("CHECKER_UNSUPPORTED", "solver provider is not independently certified")
        expected_result = {
            "schema_version": "jc/backend-result/1.0",
            "provider_id": provider_id,
            "provider_version": PROVIDER_VERSION,
            "input_digest": str(problem_ref.digest),
            "status": "COMPLETED",
            "outcome": outcome,
            "outputs": outputs,
        }
        expected_result_bytes = canonical_bytes(expected_result)
        expected_proof = {
            "schema_version": "jc/backend-proof/1.0",
            "provider_id": provider_id,
            "provider_version": PROVIDER_VERSION,
            "input_digest": str(problem_ref.digest),
            "result_digest": str(DigestV4.from_bytes(expected_result_bytes)),
            "witness": witness,
        }
        if result != expected_result:
            _fail("CHECKER_RESULT_MISMATCH", "backend result differs from independent recomputation")
        if proof != expected_proof:
            _fail("CHECKER_PROOF_MISMATCH", "backend proof differs from independent recomputation")
        graph_ref = ContentRefV4(ARGUMENT_GRAPH_KIND, DigestV4.from_bytes(canonical_bytes(graph)))
        checked_refs = _sorted_refs(tuple(reader.seen))
        input_digest = digest_value({
            "schema_version": "jc/independent-checker-input/1.0",
            "run_identity_ref": run_identity_ref.to_dict(),
            "solver_receipt_ref": solver_receipt_ref.to_dict(),
            "checked_refs": [item.to_dict() for item in checked_refs],
        })
        report = {
            "schema_version": "jc/independent-checker-report/1.0",
            "status": "PASS",
            "run_identity_ref": run_identity_ref.to_dict(),
            "subject_ref": solver_receipt_ref.to_dict(),
            "provider_id": provider_id,
            "problem_ref": problem_ref.to_dict(),
            "backend_result_ref": receipt.backend_result_ref.to_dict(),
            "backend_result_digest": str(DigestV4.from_bytes(expected_result_bytes)),
            "proof_ref": receipt.proof_ref.to_dict(),
            "proof_digest": str(DigestV4.from_bytes(canonical_bytes(expected_proof))),
            "argument_graph_ref": graph_ref.to_dict(),
            "input_digest": str(input_digest),
            "checks": [
                "run-pack-source-fact-binding",
                "rule-spec-ivl-zero-loss",
                "backend-result-and-proof",
                "grounded-labels-and-witnesses",
                "claim-projection",
            ],
        }
        report_ref = ContentRefV4(CHECKER_REPORT_KIND, DigestV4.from_bytes(canonical_bytes(report)))
        witnesses = _sorted_refs((*checked_refs, graph_ref, report_ref))
        return _CheckMaterial(
            run_identity_ref,
            solver_receipt_ref,
            receipt,
            problem_ref,
            receipt.invocation_ref,
            receipt.backend_result_ref,
            graph_ref,
            graph,
            input_digest,
            report,
            report_ref,
            witnesses,
        )

    def check(
        self,
        *,
        run_identity_ref: ContentRefV4,
        solver_receipt_ref: ContentRefV4,
        now: CanonicalTimeV4,
    ) -> CheckerExecutionV4:
        """Independently recompute one execution and issue an internally signed PASS."""

        material = self._recompute(
            run_identity_ref=run_identity_ref,
            solver_receipt_ref=solver_receipt_ref,
            now=now,
        )
        self._register(
            material.argument_graph_ref,
            material.argument_graph,
            kind=ARGUMENT_GRAPH_KIND,
        )
        self._register(material.report_ref, material.report, kind=CHECKER_REPORT_KIND)
        body = {
            "receipt_id": (
                f"checker-{material.solver_receipt_ref.digest.hex}-"
                f"{material.report_ref.digest.hex}"
            ),
            "run_identity_ref": material.run_ref.to_dict(),
            "subject_ref": material.solver_receipt_ref.to_dict(),
            "argument_graph_ref": material.argument_graph_ref.to_dict(),
            "backend_result_ref": material.backend_result_ref.to_dict(),
            "checker_build_digest": str(_runtime_build_digest()),
            "algorithm_profile_digest": str(_algorithm_profile_digest()),
            "input_digest": str(material.input_digest),
            "output_digest": str(material.report_ref.digest),
            "witness_refs": [item.to_dict() for item in material.witness_refs],
            "status": "PASS",
            "issued_at": now.to_dict(),
        }
        signature = self._receipt_signer(
            material.solver_receipt_ref.digest,
            digest_value(body),
            material.witness_refs,
            material.run_ref,
            now,
        )
        if type(signature) is not SignatureEnvelopeV4:
            _fail("CHECKER_SIGNATURE_BINDING", "checker signer returned the wrong type")
        receipt = CheckerReceiptV4.from_dict({**body, "signature": signature.to_dict()})
        self._verify_receipt_value(receipt, material=material, now=now)
        receipt_ref = ContentRefV4(
            CHECKER_RECEIPT_KIND, DigestV4.from_bytes(receipt.canonical_bytes())
        )
        self._register(receipt_ref, receipt.to_dict(), kind=CHECKER_RECEIPT_KIND)
        return CheckerExecutionV4(receipt, receipt_ref, material.report_ref)

    def _register(
        self,
        reference: ContentRefV4,
        document: dict[str, object],
        *,
        kind: str,
    ) -> ContentRefV4:
        raw = canonical_bytes(document)
        if reference.kind != kind or reference.digest != DigestV4.from_bytes(raw):
            _fail("CHECKER_ARTIFACT_BINDING", "checker artifact reference differs from bytes")
        return self._resolver.register_bytes(
            artifact_id=f"{kind}-{reference.digest.hex}",
            content_ref=reference,
            artifact_kind=kind,
            media_type="application/json",
            scope=CHECKER_SCOPE,
            content=raw,
        )

    def _verify_receipt_value(
        self,
        receipt: CheckerReceiptV4,
        *,
        material: _CheckMaterial,
        now: CanonicalTimeV4,
    ) -> None:
        if (
            receipt.receipt_id
            != f"checker-{material.solver_receipt_ref.digest.hex}-{material.report_ref.digest.hex}"
            or receipt.run_identity_ref != material.run_ref
            or receipt.subject_ref != material.solver_receipt_ref
            or receipt.argument_graph_ref != material.argument_graph_ref
            or receipt.backend_result_ref != material.backend_result_ref
            or receipt.checker_build_digest != _runtime_build_digest()
            or receipt.algorithm_profile_digest != _algorithm_profile_digest()
            or receipt.input_digest != material.input_digest
            or receipt.output_digest != material.report_ref.digest
            or receipt.witness_refs != material.witness_refs
            or receipt.status != "PASS"
            or receipt.signature.issued_at != receipt.issued_at
        ):
            _fail("CHECKER_RECEIPT_BINDING", "checker receipt differs from recomputed material")
        self._service_signature(
            receipt.signature,
            subject=material.solver_receipt_ref.digest,
            payload=digest_value(receipt.signature_body()),
            evidence=material.witness_refs,
            run_ref=material.run_ref,
            now=now,
            issuer=self._receipt_issuer,
        )

    def verify_receipt(
        self,
        receipt_ref: ContentRefV4,
        *,
        now: CanonicalTimeV4,
    ) -> CheckerReceiptV4:
        """Resolve an issued receipt, independently recompute, and verify its signature."""

        if type(receipt_ref) is not ContentRefV4 or receipt_ref.kind != CHECKER_RECEIPT_KIND:
            _fail("CHECKER_INPUT_TYPE", "verification requires a checker receipt reference")
        with self._resolver._snapshot():
            return self._verify_receipt_pinned(receipt_ref, now=now)

    def _verify_receipt_pinned(
        self,
        receipt_ref: ContentRefV4,
        *,
        now: CanonicalTimeV4,
    ) -> CheckerReceiptV4:
        reader = _Reader(self._resolver)
        receipt = reader.contract(
            receipt_ref,
            kind=CHECKER_RECEIPT_KIND,
            scope=CHECKER_SCOPE,
            contract=CheckerReceiptV4,
        )
        material = self._recompute(
            run_identity_ref=receipt.run_identity_ref,
            solver_receipt_ref=receipt.subject_ref,
            now=now,
        )
        graph = reader.json(
            receipt.argument_graph_ref,
            kind=ARGUMENT_GRAPH_KIND,
            scope=CHECKER_SCOPE,
        )
        report = reader.json(
            material.report_ref,
            kind=CHECKER_REPORT_KIND,
            scope=CHECKER_SCOPE,
        )
        if graph != material.argument_graph or report != material.report:
            _fail("CHECKER_RECEIPT_BINDING", "stored checker graph or report differs")
        self._verify_receipt_value(receipt, material=material, now=now)
        if receipt_ref.digest != DigestV4.from_bytes(receipt.canonical_bytes()):
            _fail("CHECKER_RECEIPT_BINDING", "checker receipt reference differs from bytes")
        return receipt


__all__ = [
    "ARGUMENT_GRAPH_KIND",
    "CHECKER_RECEIPT_KIND",
    "CHECKER_REPORT_KIND",
    "CHECKER_SCOPE",
    "CheckerExecutionV4",
    "IndependentCheckerV4",
    "IndependentCheckerV4Error",
]
