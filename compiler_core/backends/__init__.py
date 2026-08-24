"""Certified providers for the first V4 release candidate."""

from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import dataclass
from fractions import Fraction
from multiprocessing.connection import Connection
from pathlib import Path
import sys
from typing import Callable

import compiler_core.argumentation as _argumentation_module
import compiler_core.canonical_serialization as _canonical_module
import compiler_core.contracts as _contracts_module
from compiler_core.argumentation import (
    ARGUMENT_GRAPH_KIND_V4,
    ArgumentGraphV4,
    PermissionRelationV4,
    argument_ref_v4,
    evaluate_argument_graph,
)
from compiler_core.canonical_serialization import (
    DigestV4,
    SAFE_INTEGER_MAX,
    SAFE_INTEGER_MIN,
    canonical_bytes,
    parse_json_document,
)
from compiler_core.contracts import (
    ArgumentV4,
    AttackV4,
    CanonicalTimeV4,
    ContentRefV4,
    PriorityEdgeV4,
    validate_rational_v4,
)


HORN_PROVIDER_ID = "jc-horn-fixpoint"
AAF_PROVIDER_ID = "jc-aaf-grounded"
EXACT_PROVIDER_ID = "jc-exact-temporal-numeric"
PROVIDER_VERSION = "1.0.0"


class ProviderV4Error(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class ProviderRunV4:
    provider_id: str
    provider_version: str
    input_digest: DigestV4
    status: str
    exit_status: int
    result_bytes: bytes
    proof_bytes: bytes | None


ProviderCallableV4 = Callable[[bytes], ProviderRunV4]


def provider_runtime_identity() -> tuple[DigestV4, DigestV4, dict[str, str]]:
    """Bind the interpreter and every formal module executed by a provider."""

    paths = {
        "backends": Path(__file__),
        "argumentation": Path(_argumentation_module.__file__),
        "canonical_serialization": Path(_canonical_module.__file__),
        "contracts": Path(_contracts_module.__file__),
    }
    inputs = {
        name: str(DigestV4.from_bytes(path.read_bytes()))
        for name, path in sorted(paths.items())
    }
    package_digest = DigestV4.from_bytes(canonical_bytes(inputs))
    binary_digest = DigestV4.from_bytes(Path(sys.executable).read_bytes())
    return binary_digest, package_digest, inputs


def _problem(raw: bytes, expected_provider: str) -> tuple[dict[str, object], DigestV4]:
    if type(raw) is not bytes:
        raise ProviderV4Error("PROVIDER_INPUT_TYPE", "problem must be canonical bytes")
    document = parse_json_document(raw)
    if type(document) is not dict or raw != canonical_bytes(document):
        raise ProviderV4Error("PROVIDER_INPUT_CANONICAL", "problem is not canonical JSON")
    if (
        document.get("schema_version") != "jc/backend-problem/1.0"
        or document.get("provider_id") != expected_provider
        or set(document) != {
            "schema_version", "provider_id", "run_identity_ref", "request_ref",
            "case_scope", "limits_ref", "decision_time", "seed", "features",
            "facts", "clauses",
        }
        or type(document.get("case_scope")) is not str
        or not document["case_scope"]
        or type(document.get("seed")) is not int
        or type(document.get("features")) is not dict
        or set(document["features"]) != {
            "conflict_structure", "temporal_constraints", "numeric_constraints",
        }
        or any(type(value) is not bool for value in document["features"].values())
    ):
        raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "problem/provider identity differs")
    try:
        for field in ("run_identity_ref", "request_ref", "limits_ref"):
            ContentRefV4.from_dict(document[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "problem refs are malformed") from exc
    return document, DigestV4.from_bytes(raw)


def _facts(problem: dict[str, object]) -> dict[str, object]:
    rows = problem.get("facts")
    if type(rows) is not list:
        raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "facts must be a list")
    values: dict[str, object] = {}
    for row in rows:
        if (
            type(row) is not dict
            or set(row) != {
                "admission_receipt_ref", "fact_ref", "case_scope", "proposition",
                "value_kind", "value",
            }
            or row.get("case_scope") != problem["case_scope"]
            or type(row.get("proposition")) is not str
            or not row["proposition"]
            or type(row.get("value_kind")) is not str
        ):
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "fact row is malformed")
        try:
            ContentRefV4.from_dict(row["admission_receipt_ref"])
            ContentRefV4.from_dict(row["fact_ref"])
        except (TypeError, ValueError) as exc:
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "fact refs are malformed") from exc
        proposition = row["proposition"]
        if proposition in values:
            raise ProviderV4Error("PROVIDER_DUPLICATE_FACT", proposition)
        values[proposition] = row.get("value")
    return values


def _instant(value: object) -> CanonicalTimeV4:
    try:
        return CanonicalTimeV4.parse(value)
    except ValueError as exc:
        raise ProviderV4Error("EXACT_TIME", "time must be a canonical UTC instant") from exc


def _interval(
    clause: dict[str, object], decision_time: CanonicalTimeV4
) -> dict[str, object]:
    start = _instant(clause.get("effective_from"))
    raw_end = clause.get("effective_to")
    end = None if raw_end is None else _instant(raw_end)
    if end is not None and not start < end:
        raise ProviderV4Error("EXACT_TIME_ORDER", "rule effective interval must increase")
    active = not decision_time < start and (end is None or decision_time < end)
    return {
        "ivl_id": clause["ivl_id"],
        "effective_from": start.wire,
        "effective_to": None if end is None else end.wire,
        "active": active,
    }


def _horn_analysis(problem: dict[str, object]) -> dict[str, object]:
    facts = _facts(problem)
    decision_time = _instant(problem.get("decision_time"))
    clauses = problem.get("clauses")
    if type(clauses) is not list or not clauses:
        raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "clauses must be non-empty")
    clause_fields = {
        "ivl_id", "ivl_ref", "rule_ref", "translation_receipt_refs", "premise_refs",
        "premises", "conclusion_ref", "conclusion", "derivation_refs", "modality",
        "effective_from", "effective_to", "relations", "temporal_constraints",
        "numeric_constraints",
    }
    rules: list[dict[str, object]] = []
    required: set[str] = set()
    intervals: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for clause in clauses:
        if (
            type(clause) is not dict
            or set(clause) != clause_fields
            or type(clause.get("ivl_id")) is not str
            or not clause["ivl_id"]
        ):
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "Horn clause is malformed")
        ivl_id = clause["ivl_id"]
        if ivl_id in seen_ids:
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "clause ids repeat")
        seen_ids.add(ivl_id)
        modality = clause.get("modality")
        if modality not in {"OBLIGATION", "PROHIBITION", "PERMISSION", "CONSTITUTIVE"}:
            raise ProviderV4Error("UNSUPPORTED_SEMANTICS", "rule modality is not certified")
        interval = _interval(clause, decision_time)
        intervals.append(interval)
        premises = clause.get("premises")
        conclusion = clause.get("conclusion")
        premise_refs = clause.get("premise_refs")
        if (
            type(premises) is not list
            or type(premise_refs) is not list
            or len(premises) != len(premise_refs)
            or type(conclusion) is not dict
            or not set(conclusion) <= {
                "schema_version", "rule_id", "fact_key", "value",
            }
            or conclusion.get("schema_version") != "jc/rule-conclusion/1.0"
            or conclusion.get("rule_id") != ivl_id
            or len({"fact_key", "value"} & set(conclusion)) != 1
        ):
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "Horn clause body is malformed")
        try:
            rule_ref = ContentRefV4.from_dict(clause["rule_ref"])
            conclusion_ref = ContentRefV4.from_dict(clause["conclusion_ref"])
            ContentRefV4.from_dict(clause["ivl_ref"])
            for field in ("translation_receipt_refs", "derivation_refs"):
                if type(clause[field]) is not list:
                    raise TypeError(field)
                for reference in clause[field]:
                    ContentRefV4.from_dict(reference)
            for reference in premise_refs:
                ContentRefV4.from_dict(reference)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "clause refs are malformed") from exc
        if any(
            type(clause[field]) is not list
            for field in ("relations", "temporal_constraints", "numeric_constraints")
        ):
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "clause collections are malformed")
        keys: list[str] = []
        for premise in premises:
            if (
                type(premise) is not dict
                or set(premise) != {"schema_version", "rule_id", "fact_key", "required"}
                or premise.get("schema_version") != "jc/rule-premise/1.0"
                or premise.get("rule_id") != ivl_id
                or type(premise.get("fact_key")) is not str
                or not premise["fact_key"]
                or type(premise.get("required")) is not bool
            ):
                raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "Horn premise is malformed")
            if premise["required"]:
                keys.append(premise["fact_key"])
                if interval["active"]:
                    required.add(premise["fact_key"])
        head = conclusion.get("fact_key")
        if modality == "CONSTITUTIVE" and (type(head) is not str or not head):
            raise ProviderV4Error(
                "UNSUPPORTED_SEMANTICS", "constitutive conclusion requires fact_key"
            )
        rules.append({
            "ivl_id": ivl_id,
            "head": head,
            "premises": tuple(keys),
            "conclusion_ref": conclusion_ref,
            "rule_ref": rule_ref,
            "modality": modality,
            "active": interval["active"],
        })
    rules.sort(key=lambda item: (
        str(item["head"]), item["premises"], item["ivl_id"]
    ))
    known = {key for key, value in facts.items() if value is True}
    initial_true = set(known)
    evidence_by_atom: dict[str, ContentRefV4] = {}
    for row in problem["facts"]:
        if row.get("value") is True and type(row.get("fact_ref")) is dict:
            try:
                evidence_by_atom[row["proposition"]] = ContentRefV4.from_dict(
                    row["fact_ref"]
                )
            except (TypeError, ValueError) as exc:
                raise ProviderV4Error(
                    "PROVIDER_INPUT_SCHEMA", "fact evidence reference is malformed"
                ) from exc
    false_facts = sorted(key for key, value in facts.items() if value is False)
    trace: list[dict[str, object]] = []
    fired_refs: list[object] = []
    fired_rule_ids: list[str] = []
    constitutive = [
        row for row in rules if row["active"] and row["modality"] == "CONSTITUTIVE"
    ]
    bound = len({row["head"] for row in constitutive}) + 1
    for iteration in range(1, bound + 1):
        added: list[str] = []
        for row in constitutive:
            ivl_id, head, premises = row["ivl_id"], row["head"], row["premises"]
            if head not in known and all(item in known for item in premises):
                if facts.get(head) is False:
                    raise ProviderV4Error(
                        "HORN_FACT_CONFLICT", f"derived atom conflicts with false fact: {head}"
                    )
                known.add(head)
                added.append(head)
                fired_rule_ids.append(ivl_id)
                reference = row["conclusion_ref"]
                fired_refs.append(reference.to_dict())
                evidence_by_atom[head] = reference
        trace.append({"iteration": iteration, "added": sorted(added)})
        if not added:
            break
    else:
        raise ProviderV4Error("PROVIDER_NONCONVERGENT", "Horn fixpoint exceeded its bound")
    applicable_rule_ids = sorted(
        row["ivl_id"] for row in rules
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
        if row["modality"] != "CONSTITUTIVE"
        and row["ivl_id"] in applicable_rule_ids
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


def _completed(
    provider_id: str,
    input_digest: DigestV4,
    outcome: str,
    outputs: dict[str, object],
    witness: dict[str, object],
) -> ProviderRunV4:
    result = {
        "schema_version": "jc/backend-result/1.0",
        "provider_id": provider_id,
        "provider_version": PROVIDER_VERSION,
        "input_digest": str(input_digest),
        "status": "COMPLETED",
        "outcome": outcome,
        "outputs": outputs,
    }
    result_bytes = canonical_bytes(result)
    proof_bytes = canonical_bytes({
        "schema_version": "jc/backend-proof/1.0",
        "provider_id": provider_id,
        "provider_version": PROVIDER_VERSION,
        "input_digest": str(input_digest),
        "result_digest": str(DigestV4.from_bytes(result_bytes)),
        "witness": witness,
    })
    return ProviderRunV4(
        provider_id,
        PROVIDER_VERSION,
        input_digest,
        "COMPLETED",
        0,
        result_bytes,
        proof_bytes,
    )


def execute_horn(problem_bytes: bytes) -> ProviderRunV4:
    """Run all finite Horn clauses to their deterministic least fixpoint."""

    problem, input_digest = _problem(problem_bytes, HORN_PROVIDER_ID)
    analysis = _horn_analysis(problem)
    facts = analysis["facts"]
    known = analysis["known"]
    return _completed(
        HORN_PROVIDER_ID,
        input_digest,
        "FIXPOINT",
        {
            "derived_atoms": sorted(known - analysis["initial_true"]),
            "derived_refs": analysis["fired_refs"],
            "applicable_norms": analysis["applicable_norms"],
            "false_fact_keys": analysis["false_facts"],
            "missing_fact_keys": sorted(
                analysis["required"] - known - set(facts)
            ),
            "inactive_rule_ids": sorted(
                row["ivl_id"] for row in analysis["intervals"] if not row["active"]
            ),
        },
        {
            "bound": analysis["bound"],
            "trace": analysis["trace"],
            "least_fixpoint": sorted(known),
            "fired_rule_ids": analysis["fired_rule_ids"],
            "applicable_rule_ids": analysis["applicable_rule_ids"],
            "effective_intervals": analysis["intervals"],
        },
    )


def execute_aaf(problem_bytes: bytes) -> ProviderRunV4:
    """Run the certified finite Dung grounded provider on typed IVL relations."""

    problem, input_digest = _problem(problem_bytes, AAF_PROVIDER_ID)
    analysis = _horn_analysis(problem)
    known = analysis["known"]
    applicable_ids = set(analysis["applicable_rule_ids"])
    clauses = problem.get("clauses")
    arguments: list[ArgumentV4] = []
    rows: list[dict[str, object]] = []
    modality_by_id: dict[str, str] = {}
    conclusion_by_id: dict[str, dict[str, object]] = {}
    for clause in clauses:
        modality = clause.get("modality")
        modality_by_id[clause["ivl_id"]] = modality
        conclusion_by_id[clause["ivl_id"]] = clause["conclusion"]
        relations = clause.get("relations")
        if type(relations) is not list or any(type(item) is not dict for item in relations):
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "AAF relations are malformed")
        rows.extend(relations)
        if clause["ivl_id"] not in applicable_ids:
            continue
        try:
            argument = ArgumentV4(
                argument_id=clause["ivl_id"],
                premise_refs=tuple(ContentRefV4.from_dict(item) for item in clause["premise_refs"]),
                rule_ref=ContentRefV4.from_dict(clause["rule_ref"]),
                claim_ref=ContentRefV4.from_dict(clause["conclusion_ref"]),
                derivation_refs=tuple(
                    ContentRefV4.from_dict(item) for item in clause["derivation_refs"]
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "AAF refs are malformed") from exc
        arguments.append(argument)
    all_ids = set(modality_by_id)
    by_id = {item.argument_id: item for item in arguments}
    if len(by_id) != len(arguments):
        raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "AAF argument ids repeat")
    refs = {key: argument_ref_v4(value) for key, value in by_id.items()}
    attacks: list[AttackV4] = []
    priorities: list[PriorityEdgeV4] = []
    permissions: list[PermissionRelationV4] = []
    condition_evidence: list[dict[str, object]] = []
    seen_source_refs: set[ContentRefV4] = set()
    for row in rows:
        kind = row.get("kind")
        expected_fields = {
            "attack": {
                "kind", "source_ref", "attack_type", "target_aspect", "source",
                "target", "condition_fact_key",
            },
            "priority": {
                "kind", "source_ref", "source", "target", "condition",
            },
            "permission": {
                "kind", "source_ref", "permission_id", "permits", "relation_kind",
                "source", "target",
            },
        }.get(kind)
        if expected_fields is None or set(row) != expected_fields:
            raise ProviderV4Error("UNSUPPORTED_SEMANTICS", "AAF relation fields are not certified")
        source, target = row.get("source"), row.get("target")
        if type(source) is not str or type(target) is not str:
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "AAF endpoints must be strings")
        if source not in all_ids or target not in all_ids:
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "AAF endpoint is outside selected IVLs")
        try:
            source_ref = ContentRefV4.from_dict(row["source_ref"])
            if source_ref in seen_source_refs:
                raise ProviderV4Error(
                    "PROVIDER_INPUT_SCHEMA", "AAF relation source refs repeat"
                )
            seen_source_refs.add(source_ref)
            if kind == "attack":
                condition = row["condition_fact_key"]
                if source_ref.kind not in {"rule-exception", "rule-attack"}:
                    raise ProviderV4Error(
                        "PROVIDER_INPUT_SCHEMA", "attack source ref kind is invalid"
                    )
                if source_ref.kind == "rule-exception" and (
                    type(condition) is not str or not condition
                ):
                    raise ProviderV4Error(
                        "UNSUPPORTED_SEMANTICS", "exception requires a fact condition"
                    )
                if condition is not None and (type(condition) is not str or not condition):
                    raise ProviderV4Error(
                        "UNSUPPORTED_SEMANTICS", "attack condition is not certified"
                    )
                if row["attack_type"] not in {
                    "rebut", "undercut", "exception", "premise_challenge",
                } or row["target_aspect"] not in {
                    "claim", "premise", "rule_applicability",
                }:
                    raise ProviderV4Error(
                        "UNSUPPORTED_SEMANTICS", "attack semantics are not certified"
                    )
                if source not in refs or target not in refs or (
                    condition is not None and condition not in known
                ):
                    continue
                if condition is not None:
                    condition_ref = analysis["evidence_by_atom"].get(condition)
                    if type(condition_ref) is not ContentRefV4:
                        raise ProviderV4Error(
                            "UNSUPPORTED_SEMANTICS", "attack condition lacks typed evidence"
                        )
                    condition_evidence.append({
                        "source_ref": source_ref.to_dict(),
                        "condition": condition,
                        "condition_ref": condition_ref.to_dict(),
                    })
                attacks.append(AttackV4(
                    attack_id=f"attack-{source_ref.digest.hex}",
                    attacker_ref=refs[source],
                    target_ref=refs[target],
                    attack_type=row["attack_type"],
                    target_aspect=row["target_aspect"],
                ))
            elif kind == "priority":
                condition = row["condition"]
                if source_ref.kind != "rule-priority" or (
                    type(condition) is not str or not condition
                ):
                    raise ProviderV4Error(
                        "UNSUPPORTED_SEMANTICS", "priority requires a fact condition"
                    )
                if source not in refs or target not in refs or condition not in known:
                    continue
                condition_ref = analysis["evidence_by_atom"].get(condition)
                if type(condition_ref) is not ContentRefV4:
                    raise ProviderV4Error(
                        "UNSUPPORTED_SEMANTICS", "priority condition lacks typed evidence"
                    )
                condition_evidence.append({
                    "source_ref": source_ref.to_dict(),
                    "condition": condition,
                    "condition_ref": condition_ref.to_dict(),
                })
                priorities.append(PriorityEdgeV4(
                    edge_id=f"priority-{source_ref.digest.hex}",
                    preferred_ref=refs[source],
                    defeated_ref=refs[target],
                    condition_ref=condition_ref,
                    source_ref=source_ref,
                ))
            else:
                permits = row["permits"]
                standalone = source == target
                if standalone:
                    if (
                        source_ref.kind != "rule-permission"
                        or modality_by_id[source] != "PERMISSION"
                        or row["relation_kind"] not in {"exception", "standalone"}
                        or type(row["permission_id"]) is not str
                        or not row["permission_id"]
                        or type(permits) is not str
                        or not permits
                    ):
                        raise ProviderV4Error(
                            "UNSUPPORTED_SEMANTICS",
                            "standalone permission is malformed",
                        )
                    if source not in refs:
                        continue
                    permissions.append(PermissionRelationV4(
                        permission_id=row["permission_id"],
                        permission_claim_ref=by_id[source].claim_ref,
                        prohibition_claim_ref=None,
                        source_ref=source_ref,
                    ))
                    continue
                if (
                    source_ref.kind != "rule-permission"
                    or modality_by_id[source] != "PERMISSION"
                    or modality_by_id[target] != "PROHIBITION"
                    or row["relation_kind"] != "exception"
                    or type(row["permission_id"]) is not str
                    or not row["permission_id"]
                    or type(permits) is not str
                    or not permits
                    or conclusion_by_id[source].get("fact_key") != permits
                    or conclusion_by_id[target].get("fact_key") != permits
                ):
                    raise ProviderV4Error(
                        "UNSUPPORTED_SEMANTICS",
                        "permission relation is not typed to a prohibition",
                    )
                if source not in refs or target not in refs:
                    continue
                permissions.append(PermissionRelationV4(
                    permission_id=row["permission_id"],
                    permission_claim_ref=by_id[source].claim_ref,
                    prohibition_claim_ref=by_id[target].claim_ref,
                    source_ref=source_ref,
                ))
                attacks.append(AttackV4(
                    attack_id=f"permission-{source_ref.digest.hex}",
                    attacker_ref=refs[source],
                    target_ref=refs[target],
                    attack_type="exception",
                    target_aspect="rule_applicability",
                ))
        except (KeyError, TypeError, ValueError) as exc:
            if type(exc) is ProviderV4Error:
                raise
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "AAF relation is malformed") from exc
    if not arguments:
        graph_payload = {
            "schema_version": "jc/argument-graph-v4/1.0",
            "arguments": [],
            "attacks": [],
            "priority_edges": [],
            "permission_relations": [],
        }
        outputs = {
            "schema_version": "jc/argumentation-evaluation-v4/1.0",
            "graph_ref": ContentRefV4(
                ARGUMENT_GRAPH_KIND_V4,
                DigestV4.from_bytes(canonical_bytes(graph_payload)),
            ).to_dict(),
            "labels": [],
            "effective_attacks": [],
            "permission_resolutions": [],
            "exception_resolutions": [],
            "claim_projection": [],
            "priority_cycles": [],
            "state": "empty",
        }
        return _completed(
            AAF_PROVIDER_ID,
            input_digest,
            "empty",
            outputs,
            {
                "graph": graph_payload,
                "evaluation": outputs,
                "relation_condition_evidence": [],
                "applicable_rule_ids": [],
                "effective_intervals": analysis["intervals"],
            },
        )
    graph = ArgumentGraphV4(
        arguments=tuple(arguments),
        attacks=tuple(attacks),
        priority_edges=tuple(priorities),
        permission_relations=tuple(permissions),
    )
    evaluation = evaluate_argument_graph(graph)
    outputs = evaluation.to_dict()
    return _completed(
        AAF_PROVIDER_ID,
        input_digest,
        evaluation.state,
        outputs,
        {
            "graph": graph.canonical_payload(),
            "evaluation": outputs,
            "relation_condition_evidence": sorted(
                condition_evidence,
                key=lambda row: (str(row["source_ref"]), row["condition"]),
            ),
            "applicable_rule_ids": analysis["applicable_rule_ids"],
            "effective_intervals": analysis["intervals"],
        },
    )


def _ratio(value: object) -> Fraction:
    try:
        numerator, denominator = validate_rational_v4(value)
    except ValueError as exc:
        raise ProviderV4Error("EXACT_RATIO", "ratio must be canonical and reduced") from exc
    return Fraction(numerator, denominator)


def _safe(value: int) -> int:
    if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
        raise ProviderV4Error("EXACT_INTEGER", "exact result exceeds the safe integer range")
    return value


def _constraint(
    document: dict[str, object], expected_kind: str
) -> tuple[ContentRefV4, str, str, dict[str, object]]:
    if set(document) != {
        "constraint_ref", "owner_ivl_id", "target_ivl_id", "expression",
    }:
        raise ProviderV4Error("UNSUPPORTED_SEMANTICS", "constraint binding is not closed")
    try:
        reference = ContentRefV4.from_dict(document["constraint_ref"])
    except (TypeError, ValueError) as exc:
        raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "constraint ref is malformed") from exc
    owner, target, expression = (
        document["owner_ivl_id"], document["target_ivl_id"], document["expression"]
    )
    if (
        reference.kind != expected_kind
        or type(owner) is not str
        or type(target) is not str
        or type(expression) is not dict
        or expression.get("schema_version") != f"jc/{expected_kind}/1.0"
        or expression.get("rule_id") != owner
        or expression.get("target_rule_id", owner) != target
    ):
        raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "constraint owner or target differs")
    return reference, owner, target, expression


def _numeric(document: dict[str, object], facts: dict[str, object]) -> dict[str, object]:
    reference, owner, target, expression = _constraint(document, "rule-numeric-constraint")
    document = expression
    operation = document.get("operation")
    if operation == "integer_add":
        if set(document) - {"schema_version", "rule_id", "target_rule_id", "operation", "operands"}:
            raise ProviderV4Error("UNSUPPORTED_SEMANTICS", "numeric fields are not certified")
        operands = document.get("operands")
        if type(operands) is not list or any(type(value) is not int for value in operands):
            raise ProviderV4Error("EXACT_INTEGER", "integer_add operands must be integers")
        result = {"operation": operation, "integer": _safe(sum(operands))}
    elif operation == "integer_multiply_ratio":
        if set(document) - {
            "schema_version", "rule_id", "target_rule_id", "operation", "fact_key", "ratio"
        }:
            raise ProviderV4Error("UNSUPPORTED_SEMANTICS", "numeric fields are not certified")
        fact_key = document.get("fact_key")
        if type(fact_key) is not str or type(facts.get(fact_key)) is not int:
            raise ProviderV4Error("EXACT_INTEGER", "numeric fact must be an admitted integer")
        result = Fraction(facts[fact_key]) * _ratio(document.get("ratio"))
        result = {
            "operation": operation,
            "rational": {
                "numerator": _safe(result.numerator),
                "denominator": _safe(result.denominator),
            },
        }
    else:
        raise ProviderV4Error("UNSUPPORTED_SEMANTICS", "numeric operation is not certified")
    return {
        "constraint_ref": reference.to_dict(),
        "owner_ivl_id": owner,
        "target_ivl_id": target,
        **result,
    }


def _temporal(
    document: dict[str, object], decision_time: CanonicalTimeV4
) -> dict[str, object]:
    reference, owner, target, expression = _constraint(
        document, "rule-temporal-constraint"
    )
    document = expression
    if document.get("operation") not in {None, "interval"}:
        raise ProviderV4Error("UNSUPPORTED_SEMANTICS", "temporal operation is not certified")
    if set(document) - {
        "schema_version", "rule_id", "target_rule_id", "operation", "start", "end"
    }:
        raise ProviderV4Error("UNSUPPORTED_SEMANTICS", "temporal fields are not certified")
    start, end = _instant(document.get("start")), _instant(document.get("end"))
    if not start < end:
        raise ProviderV4Error("EXACT_TIME_ORDER", "temporal interval must increase")
    seconds = end.epoch_seconds - start.epoch_seconds
    nanoseconds = end.nanosecond - start.nanosecond
    if nanoseconds < 0:
        seconds -= 1
        nanoseconds += 1_000_000_000
    return {
        "constraint_ref": reference.to_dict(),
        "owner_ivl_id": owner,
        "target_ivl_id": target,
        "operation": "interval",
        "active": CanonicalTimeV4.contains_half_open(start, end, decision_time),
        "duration": {"seconds": seconds, "nanoseconds": nanoseconds},
    }


def execute_exact(problem_bytes: bytes) -> ProviderRunV4:
    """Run integer/rational/Gregorian operations without binary floating point."""

    problem, input_digest = _problem(problem_bytes, EXACT_PROVIDER_ID)
    analysis = _horn_analysis(problem)
    facts = analysis["facts"]
    decision_time = _instant(problem.get("decision_time"))
    clauses = problem.get("clauses")
    applicable_ids = set(analysis["applicable_rule_ids"])
    all_ids = {clause["ivl_id"] for clause in clauses}
    temporal: list[object] = []
    numeric: list[object] = []
    seen_refs: set[ContentRefV4] = set()
    for clause in clauses:
        if type(clause.get("temporal_constraints")) is not list or type(
            clause.get("numeric_constraints")
        ) is not list:
            raise ProviderV4Error("PROVIDER_INPUT_SCHEMA", "exact constraints must be lists")
        for kind, values in (
            ("rule-temporal-constraint", clause["temporal_constraints"]),
            ("rule-numeric-constraint", clause["numeric_constraints"]),
        ):
            for row in values:
                if type(row) is not dict:
                    raise ProviderV4Error(
                        "PROVIDER_INPUT_SCHEMA", "exact constraint is not an object"
                    )
                reference, owner, target, expression = _constraint(row, kind)
                if reference in seen_refs:
                    raise ProviderV4Error(
                        "PROVIDER_INPUT_SCHEMA", "exact constraint refs repeat"
                    )
                seen_refs.add(reference)
                if owner != clause["ivl_id"] or target not in all_ids:
                    raise ProviderV4Error(
                        "PROVIDER_INPUT_SCHEMA", "constraint binding leaves selected IVLs"
                    )
                operation = expression.get("operation")
                if kind == "rule-temporal-constraint":
                    if set(expression) - {
                        "schema_version", "rule_id", "target_rule_id", "operation",
                        "start", "end",
                    } or operation not in {None, "interval"}:
                        raise ProviderV4Error(
                            "UNSUPPORTED_SEMANTICS", "temporal operation is not certified"
                        )
                    start, end = _instant(expression.get("start")), _instant(
                        expression.get("end")
                    )
                    if not start < end:
                        raise ProviderV4Error(
                            "EXACT_TIME_ORDER", "temporal interval must increase"
                        )
                elif operation == "integer_add":
                    if set(expression) - {
                        "schema_version", "rule_id", "target_rule_id", "operation",
                        "operands",
                    }:
                        raise ProviderV4Error(
                            "UNSUPPORTED_SEMANTICS", "numeric fields are not certified"
                        )
                    operands = expression.get("operands")
                    if type(operands) is not list or any(
                        type(value) is not int for value in operands
                    ):
                        raise ProviderV4Error(
                            "EXACT_INTEGER", "integer_add operands must be integers"
                        )
                elif operation == "integer_multiply_ratio":
                    if set(expression) - {
                        "schema_version", "rule_id", "target_rule_id", "operation",
                        "fact_key", "ratio",
                    }:
                        raise ProviderV4Error(
                            "UNSUPPORTED_SEMANTICS", "numeric fields are not certified"
                        )
                    if type(expression.get("fact_key")) is not str:
                        raise ProviderV4Error(
                            "EXACT_INTEGER", "numeric fact key must be a string"
                        )
                    _ratio(expression.get("ratio"))
                else:
                    raise ProviderV4Error(
                        "UNSUPPORTED_SEMANTICS", "numeric operation is not certified"
                    )
        if clause["ivl_id"] not in applicable_ids:
            continue
        temporal.extend(clause["temporal_constraints"])
        numeric.extend(clause["numeric_constraints"])
    temporal_outputs = [_temporal(row, decision_time) for row in temporal]
    numeric_outputs = [_numeric(row, facts) for row in numeric]
    return _completed(
        EXACT_PROVIDER_ID,
        input_digest,
        "EXACT",
        {
            "rule_intervals": analysis["intervals"],
            "temporal": temporal_outputs,
            "numeric": numeric_outputs,
        },
        {
            "rule_intervals": analysis["intervals"],
            "temporal": temporal_outputs,
            "numeric": numeric_outputs,
        },
    )


CERTIFIED_PROVIDERS: dict[str, ProviderCallableV4] = {
    HORN_PROVIDER_ID: execute_horn,
    AAF_PROVIDER_ID: execute_aaf,
    EXACT_PROVIDER_ID: execute_exact,
}


def _runtime_identity_wire() -> dict[str, object]:
    binary, package, inputs = provider_runtime_identity()
    return {
        "provider_binary_digest": str(binary),
        "provider_package_digest": str(package),
        "provider_build_inputs": inputs,
    }


def decode_provider_message(
    raw: bytes,
) -> tuple[str, ProviderRunV4 | str | None, dict[str, object]]:
    document = parse_json_document(raw)
    if (
        type(document) is not dict
        or raw != canonical_bytes(document)
        or set(document) != {
            "schema_version", "outcome", "runtime_identity", "run", "error_code",
        }
        or document.get("schema_version") != "jc/backend-provider-wire/1.0"
        or type(document.get("runtime_identity")) is not dict
    ):
        raise ProviderV4Error("PROVIDER_WIRE", "provider message is malformed")
    outcome = document.get("outcome")
    if outcome == "completed":
        run = document.get("run")
        if type(run) is not dict or set(run) != {
            "provider_id", "provider_version", "input_digest", "status", "exit_status",
            "result_base64", "proof_base64",
        }:
            raise ProviderV4Error("PROVIDER_WIRE", "provider run message is malformed")
        try:
            value = ProviderRunV4(
                run["provider_id"],
                run["provider_version"],
                DigestV4.parse(run["input_digest"]),
                run["status"],
                run["exit_status"],
                b64decode(run["result_base64"], validate=True),
                (
                    None
                    if run["proof_base64"] is None
                    else b64decode(run["proof_base64"], validate=True)
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ProviderV4Error("PROVIDER_WIRE", "provider run encoding is invalid") from exc
        if document.get("error_code") is not None:
            raise ProviderV4Error("PROVIDER_WIRE", "completed message carries an error")
        return outcome, value, document["runtime_identity"]
    if outcome == "provider_error" and type(document.get("error_code")) is str:
        if document.get("run") is not None:
            raise ProviderV4Error("PROVIDER_WIRE", "error message carries a run")
        return outcome, document["error_code"], document["runtime_identity"]
    if outcome == "crashed" and document.get("run") is None:
        return outcome, None, document["runtime_identity"]
    raise ProviderV4Error("PROVIDER_WIRE", "provider outcome is unsupported")


def provider_process_entry(
    provider_id: str, problem_bytes: bytes, sender: Connection
) -> None:
    """Run one provider behind a terminable process boundary."""

    identity: dict[str, object] = {}
    try:
        identity = _runtime_identity_wire()
        run = CERTIFIED_PROVIDERS[provider_id](problem_bytes)
    except ProviderV4Error as exc:
        message = {
            "schema_version": "jc/backend-provider-wire/1.0",
            "outcome": "provider_error",
            "runtime_identity": identity,
            "run": None,
            "error_code": exc.code,
        }
    except BaseException:
        message = {
            "schema_version": "jc/backend-provider-wire/1.0",
            "outcome": "crashed",
            "runtime_identity": identity,
            "run": None,
            "error_code": None,
        }
    else:
        message = {
            "schema_version": "jc/backend-provider-wire/1.0",
            "outcome": "completed",
            "runtime_identity": identity,
            "run": {
                "provider_id": run.provider_id,
                "provider_version": run.provider_version,
                "input_digest": str(run.input_digest),
                "status": run.status,
                "exit_status": run.exit_status,
                "result_base64": b64encode(run.result_bytes).decode("ascii"),
                "proof_base64": (
                    None
                    if run.proof_bytes is None
                    else b64encode(run.proof_bytes).decode("ascii")
                ),
            },
            "error_code": None,
        }
    try:
        sender.send_bytes(canonical_bytes(message))
    finally:
        sender.close()
