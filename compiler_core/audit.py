"""唯一语义审计事件记录器与由事件派生的reasoning Graph JSON。"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from compiler_core.canonical_serialization import semantic_digest
from compiler_core.contracts import CertificateKind, SemanticResult


AUDIT_SCHEMA_VERSION = "1.0"
GRAPH_SCHEMA_VERSION = "1.0"
MAX_DETAIL_TEXT = 4096
_ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:home|Users|tmp|var|private)/)")
_DETAIL_FIELDS = {
    "RUN_STARTED": {"engine_version"},
    "INPUT_VALIDATED": {"request_digest"},
    "RELEVANCE_SET_BUILT": {"algorithm_version", "candidate_rule_count", "rule_ids_digest"},
    "FACT_ADMISSION_DECIDED": {"status", "admitted", "reasoning_tier"},
    "RULE_MATCHED": {"source_status", "admitted"},
    "RULE_BLOCKED": {"reason", "modality"},
    "RULE_FIRED": {"confidence", "modality"},
    "CLAIM_DERIVED": {"confidence"},
    "ATTACK_ADDED": {"source_claim_id", "target_claim_id"},
    "EXCEPTION_APPLIED": {"exception_rule_id"},
    "PRIORITY_RESOLVED": {"source_claim_id", "target_claim_id"},
    "PERMISSION_EVALUATED": {"disposition"},
    "TAINT_PROPAGATED": {"taint_source"},
    "MISSING_FACT_RECORDED": {
        "reason",
        "impacted_rule_ids",
        "impacted_claim_ids",
        "allowed_answer_types",
        "source_requirement",
    },
    "BRANCH_CREATED": {"branch_index", "assumptions_digest"},
    "CHECKER_STARTED": {"theorem_refs_digest"},
    "CHECKER_VERDICT": {"accepted", "violations"},
    "RESULT_FINALIZED": {"result_status", "result_digest"},
    "RUN_FAILED": {"error_type"},
}


class AuditValidationError(ValueError):
    """审计事件、因果引用或图结构违反公共契约。"""


@dataclass(frozen=True)
class AuditEvent:
    """无时间戳、无路径、可确定性重放的一条语义事件。"""

    run_id: str
    seq: int
    event_type: str
    parent_event_ids: tuple[str, ...] = field(default_factory=tuple)
    fact_ids: tuple[str, ...] = field(default_factory=tuple)
    premise_ids: tuple[str, ...] = field(default_factory=tuple)
    rule_id: str = ""
    claim_id: str = ""
    before_status: str = ""
    after_status: str = ""
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    taint: tuple[str, ...] = field(default_factory=tuple)
    outcome: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.run_id or self.seq < 1:
            raise AuditValidationError("event requires run_id and positive seq")
        if self.event_type not in _DETAIL_FIELDS:
            raise AuditValidationError(f"unknown event_type: {self.event_type}")
        for name in ("parent_event_ids", "fact_ids", "premise_ids", "source_ids", "taint"):
            object.__setattr__(self, name, tuple(sorted({str(item) for item in getattr(self, name) if str(item)})))
        details = dict(self.details)
        unknown = set(details) - _DETAIL_FIELDS[self.event_type]
        if unknown:
            raise AuditValidationError(f"unknown details for {self.event_type}: {sorted(unknown)}")
        canonical: dict[str, Any] = {}
        for key, value in sorted(details.items()):
            canonical[key] = _safe_detail_value(value)
        object.__setattr__(self, "details", MappingProxyType(canonical))

    @property
    def event_id(self) -> str:
        """返回run内稳定事件ID。"""

        return f"event::{self.run_id}::{self.seq:06d}"

    def to_dict(self) -> dict[str, Any]:
        """返回JSON可序列化的深层事件副本。"""

        return {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "seq": self.seq,
            "event_type": self.event_type,
            "parent_event_ids": list(self.parent_event_ids),
            "fact_ids": list(self.fact_ids),
            "premise_ids": list(self.premise_ids),
            "rule_id": self.rule_id,
            "claim_id": self.claim_id,
            "before_status": self.before_status,
            "after_status": self.after_status,
            "source_ids": list(self.source_ids),
            "taint": list(self.taint),
            "outcome": self.outcome,
            "details": {
                key: list(value) if isinstance(value, tuple) else value
                for key, value in self.details.items()
            },
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AuditEvent":
        """严格恢复事件，并核对派生event ID与schema。"""

        if payload.get("schema_version") != AUDIT_SCHEMA_VERSION:
            raise AuditValidationError("unsupported audit schema")
        allowed = {
            "schema_version", "event_id", "run_id", "seq", "event_type", "parent_event_ids",
            "fact_ids", "premise_ids", "rule_id", "claim_id", "before_status", "after_status",
            "source_ids", "taint", "outcome", "details",
        }
        if set(payload) != allowed:
            raise AuditValidationError("audit event fields mismatch")
        event = cls(
            run_id=str(payload["run_id"]),
            seq=int(payload["seq"]),
            event_type=str(payload["event_type"]),
            parent_event_ids=tuple(payload["parent_event_ids"]),
            fact_ids=tuple(payload["fact_ids"]),
            premise_ids=tuple(payload["premise_ids"]),
            rule_id=str(payload["rule_id"]),
            claim_id=str(payload["claim_id"]),
            before_status=str(payload["before_status"]),
            after_status=str(payload["after_status"]),
            source_ids=tuple(payload["source_ids"]),
            taint=tuple(payload["taint"]),
            outcome=str(payload["outcome"]),
            details=dict(payload["details"]),
        )
        if payload["event_id"] != event.event_id:
            raise AuditValidationError("audit event_id mismatch")
        return event


class AuditRecorder:
    """每案唯一、串行递增的审计记录器；可接收application原始回调。"""

    def __init__(
        self,
        run_id: str,
        *,
        downstream: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        if not run_id:
            raise AuditValidationError("recorder requires run_id")
        self.run_id = run_id
        self._events: list[AuditEvent] = []
        self._downstream = downstream
        self._fact_events: dict[str, str] = {}
        self._rule_events: dict[str, str] = {}
        self._claim_events: dict[str, str] = {}
        self._last_by_type: dict[str, str] = {}

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        """返回不可变事件序列。"""

        return tuple(self._events)

    @property
    def events_digest(self) -> str:
        """计算事件JSON投影摘要。"""

        return semantic_digest([event.to_dict() for event in self._events])

    def __call__(self, raw_event: Mapping[str, Any]) -> None:
        """把现有最小回调事件映射为一个或多个正式语义事件。"""

        raw = dict(raw_event)
        event_type = str(raw.get("event_type", ""))
        handlers = {
            "RUN_STARTED": self._record_run_started,
            "REQUEST_VALIDATED": self._record_input_validated,
            "RELEVANCE_SET_BUILT": self._record_relevance,
            "FACT_ADMISSION": self._record_fact_admission,
            "RULE_ADMISSION": self._record_rule_admission,
            "RULE_APPLIED": self._record_rule_fired,
            "RULE_EXCEPTION_TRIGGERED": self._record_exception,
            "PROHIBITION_BLOCK": self._record_prohibition,
            "ATTACK": self._record_attack,
            "PRIORITY": self._record_priority,
            "PERMISSION": self._record_permission,
            "TAINT": self._record_taint,
            "MISSING_FACT": self._record_missing_fact,
            "BRANCH_CREATED": self._record_branch,
            "CHECKER_STARTED": self._record_checker_started,
            "CHECKER_VERDICT": self._record_checker_verdict,
            "RESULT_FINALIZED": self._record_result,
            "ENGINE_ERROR": self._record_failure,
        }
        handler = handlers.get(event_type)
        if handler is not None:
            handler(raw)

    def record(
        self,
        event_type: str,
        *,
        parent_event_ids: Iterable[str] = (),
        fact_ids: Iterable[str] = (),
        premise_ids: Iterable[str] = (),
        rule_id: str = "",
        claim_id: str = "",
        before_status: str = "",
        after_status: str = "",
        source_ids: Iterable[str] = (),
        taint: Iterable[str] = (),
        outcome: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> AuditEvent:
        """追加一条已验证事件并同步可选观察者。"""

        known_ids = {event.event_id for event in self._events}
        parents = tuple(parent_event_ids)
        missing = sorted(set(parents) - known_ids)
        if missing:
            raise AuditValidationError(f"unknown parent events: {missing}")
        event = AuditEvent(
            run_id=self.run_id,
            seq=len(self._events) + 1,
            event_type=event_type,
            parent_event_ids=parents,
            fact_ids=tuple(fact_ids),
            premise_ids=tuple(premise_ids),
            rule_id=rule_id,
            claim_id=claim_id,
            before_status=before_status,
            after_status=after_status,
            source_ids=tuple(source_ids),
            taint=tuple(taint),
            outcome=outcome,
            details=details or {},
        )
        self._events.append(event)
        self._last_by_type[event_type] = event.event_id
        if event_type == "FACT_ADMISSION_DECIDED":
            for fact_id in event.fact_ids:
                self._fact_events[fact_id] = event.event_id
        if event_type in {"RULE_MATCHED", "RULE_FIRED", "RULE_BLOCKED"} and rule_id:
            self._rule_events[rule_id] = event.event_id
        if event_type == "CLAIM_DERIVED" and claim_id:
            self._claim_events[claim_id] = event.event_id
        if self._downstream is not None:
            self._downstream(event.to_dict())
        return event

    def _record_run_started(self, raw: Mapping[str, Any]) -> None:
        self.record("RUN_STARTED", details={"engine_version": str(raw.get("engine_version", ""))})

    def _record_input_validated(self, raw: Mapping[str, Any]) -> None:
        self.record(
            "INPUT_VALIDATED",
            parent_event_ids=self._parents("RUN_STARTED"),
            details={"request_digest": str(raw.get("request_digest", ""))},
        )

    def _record_relevance(self, raw: Mapping[str, Any]) -> None:
        self.record(
            "RELEVANCE_SET_BUILT",
            parent_event_ids=self._parents("INPUT_VALIDATED"),
            details={
                "algorithm_version": str(raw.get("algorithm_version", "")),
                "candidate_rule_count": int(raw.get("candidate_rule_count", 0)),
                "rule_ids_digest": str(raw.get("rule_ids_digest", "")),
            },
        )

    def _record_fact_admission(self, raw: Mapping[str, Any]) -> None:
        self.record(
            "FACT_ADMISSION_DECIDED",
            parent_event_ids=self._parents("INPUT_VALIDATED"),
            fact_ids=(str(raw.get("fact_id", "")),),
            after_status=str(raw.get("status", "")),
            source_ids=tuple(raw.get("source_ids", ())),
            outcome="admitted" if raw.get("admitted") else "blocked",
            details={
                "status": str(raw.get("status", "")),
                "admitted": bool(raw.get("admitted")),
                "reasoning_tier": str(raw.get("reasoning_tier", "")),
            },
        )

    def _record_rule_admission(self, raw: Mapping[str, Any]) -> None:
        self.record(
            "RULE_MATCHED" if raw.get("admitted") else "RULE_BLOCKED",
            parent_event_ids=self._parents("RELEVANCE_SET_BUILT", "INPUT_VALIDATED"),
            rule_id=str(raw.get("rule_id", "")),
            source_ids=tuple(raw.get("source_ids", ())),
            outcome="admitted" if raw.get("admitted") else "candidate_only",
            details=(
                {"source_status": str(raw.get("source_status", "")), "admitted": True}
                if raw.get("admitted")
                else {"reason": str(raw.get("source_status", "UNVERIFIED")), "modality": ""}
            ),
        )

    def _record_rule_fired(self, raw: Mapping[str, Any]) -> None:
        rule_id = str(raw.get("rule_id", ""))
        claim_id = str(raw.get("claim_id", ""))
        premises = tuple(str(item) for item in raw.get("premises", ()))
        parent_ids = [self._rule_events.get(rule_id, "")]
        parent_ids.extend(self._fact_events.get(item, "") for item in premises)
        fired = self.record(
            "RULE_FIRED",
            parent_event_ids=tuple(item for item in parent_ids if item),
            premise_ids=premises,
            rule_id=rule_id,
            claim_id=claim_id,
            outcome="fired",
            details={"confidence": float(raw.get("confidence", 0.0)), "modality": str(raw.get("modality", ""))},
        )
        self.record(
            "CLAIM_DERIVED",
            parent_event_ids=(fired.event_id,),
            rule_id=rule_id,
            claim_id=claim_id,
            outcome="derived",
            details={"confidence": float(raw.get("confidence", 0.0))},
        )

    def _record_exception(self, raw: Mapping[str, Any]) -> None:
        rule_id = str(raw.get("rule_id", ""))
        self.record(
            "EXCEPTION_APPLIED",
            parent_event_ids=tuple(item for item in (self._rule_events.get(rule_id, ""),) if item),
            rule_id=rule_id,
            claim_id=str(raw.get("claim_id", "")),
            outcome="exception",
            details={"exception_rule_id": str(raw.get("triggered_exception", ""))},
        )

    def _record_prohibition(self, raw: Mapping[str, Any]) -> None:
        rule_id = str(raw.get("rule_id", ""))
        self.record(
            "RULE_BLOCKED",
            parent_event_ids=tuple(item for item in (self._rule_events.get(rule_id, ""),) if item),
            premise_ids=tuple(raw.get("premises", ())),
            rule_id=rule_id,
            claim_id=str(raw.get("claim_id", "")),
            outcome="prohibited",
            details={"reason": "PROHIBITION", "modality": "PROHIBITION"},
        )

    def _record_attack(self, raw: Mapping[str, Any]) -> None:
        source = str(raw.get("source", ""))
        target = str(raw.get("target", ""))
        parents = tuple(item for item in (self._claim_events.get(source, ""), self._claim_events.get(target, "")) if item)
        self.record(
            "ATTACK_ADDED",
            parent_event_ids=parents,
            claim_id=target,
            outcome="attack",
            details={"source_claim_id": source, "target_claim_id": target},
        )

    def _record_priority(self, raw: Mapping[str, Any]) -> None:
        self.record(
            "PRIORITY_RESOLVED",
            parent_event_ids=self._parents("ATTACK_ADDED"),
            rule_id=str(raw.get("rule_id", "")),
            outcome="priority",
            details={
                "source_claim_id": str(raw.get("source", "")),
                "target_claim_id": str(raw.get("target", "")),
            },
        )

    def _record_permission(self, raw: Mapping[str, Any]) -> None:
        self.record(
            "PERMISSION_EVALUATED",
            parent_event_ids=tuple(item for item in (self._rule_events.get(str(raw.get("rule_id", "")), ""),) if item),
            rule_id=str(raw.get("rule_id", "")),
            claim_id=str(raw.get("claim_id", "")),
            outcome="review_only",
            details={"disposition": "permission_not_fact"},
        )

    def _record_taint(self, raw: Mapping[str, Any]) -> None:
        self.record(
            "TAINT_PROPAGATED",
            parent_event_ids=tuple(item for item in (self._claim_events.get(str(raw.get("claim_id", "")), ""),) if item),
            rule_id=str(raw.get("rule_id", "")),
            claim_id=str(raw.get("claim_id", "")),
            taint=tuple(raw.get("taint", ())),
            outcome="review_required",
            details={"taint_source": str(raw.get("taint_source", ""))},
        )

    def _record_missing_fact(self, raw: Mapping[str, Any]) -> None:
        fact_id = str(raw.get("fact_id", ""))
        self.record(
            "MISSING_FACT_RECORDED",
            parent_event_ids=tuple(item for item in (self._fact_events.get(fact_id, ""),) if item)
            or self._parents("INPUT_VALIDATED"),
            fact_ids=(fact_id,),
            outcome="missing",
            details={
                "reason": str(raw.get("reason", "UNKNOWN")),
                "impacted_rule_ids": tuple(raw.get("impacted_rule_ids", ())),
                "impacted_claim_ids": tuple(raw.get("impacted_claim_ids", ())),
                "allowed_answer_types": tuple(raw.get("allowed_answer_types", ())),
                "source_requirement": str(raw.get("source_requirement", "")),
            },
        )

    def _record_branch(self, raw: Mapping[str, Any]) -> None:
        self.record(
            "BRANCH_CREATED",
            parent_event_ids=self._parents("FACT_ADMISSION_DECIDED", "INPUT_VALIDATED"),
            outcome=str(raw.get("branch_id", "")),
            details={
                "branch_index": int(raw.get("branch_index", 0)),
                "assumptions_digest": str(raw.get("assumptions_digest", "")),
            },
        )

    def _record_checker_started(self, raw: Mapping[str, Any]) -> None:
        parents = tuple(
            event.event_id
            for event in self._events
            if event.event_type in {"CLAIM_DERIVED", "ATTACK_ADDED", "RULE_BLOCKED"}
        )
        self.record(
            "CHECKER_STARTED",
            parent_event_ids=parents,
            details={"theorem_refs_digest": str(raw.get("theorem_refs_digest", ""))},
        )

    def _record_checker_verdict(self, raw: Mapping[str, Any]) -> None:
        self.record(
            "CHECKER_VERDICT",
            parent_event_ids=self._parents("CHECKER_STARTED"),
            outcome="accepted" if raw.get("accepted") else "rejected",
            details={
                "accepted": bool(raw.get("accepted")),
                "violations": tuple(str(item) for item in raw.get("violations", ())),
            },
        )

    def _record_result(self, raw: Mapping[str, Any]) -> None:
        parents = self._parents("CHECKER_VERDICT")
        if not parents:
            parents = self._parents("MISSING_FACT_RECORDED", "BRANCH_CREATED", "FACT_ADMISSION_DECIDED")
        self.record(
            "RESULT_FINALIZED",
            parent_event_ids=parents,
            outcome=str(raw.get("result_status", "")),
            details={
                "result_status": str(raw.get("result_status", "")),
                "result_digest": str(raw.get("result_digest", "")),
            },
        )

    def _record_failure(self, raw: Mapping[str, Any]) -> None:
        self.record(
            "RUN_FAILED",
            parent_event_ids=tuple(event.event_id for event in self._events[-1:]),
            outcome="engine_error",
            details={"error_type": str(raw.get("error_type", ""))},
        )

    def _parents(self, *event_types: str) -> tuple[str, ...]:
        """按给定语义类型选择已存在的最近父事件。"""

        return tuple(self._last_by_type[item] for item in event_types if item in self._last_by_type)


@dataclass(frozen=True)
class GraphNode:
    """reasoning graph稳定节点。"""

    node_id: str
    node_type: str
    status: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.node_id, "type": self.node_type, "status": self.status, "details": dict(self.details)}


@dataclass(frozen=True)
class GraphEdge:
    """reasoning graph显式法律关系边。"""

    source: str
    target: str
    edge_type: str
    event_id: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "type": self.edge_type, "event_id": self.event_id}


@dataclass(frozen=True)
class GraphDocument:
    """仅由SemanticResult与AuditEvent派生的确定性Graph JSON。"""

    run_id: str
    result_digest: str
    graph_digest: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    summary: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GRAPH_SCHEMA_VERSION,
            "run_id": self.run_id,
            "result_digest": self.result_digest,
            "graph_digest": self.graph_digest,
            "summary": dict(self.summary),
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def build_reasoning_graph(result: SemanticResult, events: Iterable[AuditEvent]) -> GraphDocument:
    """从正式事件和结果构图；不得访问evaluator或根据相邻事件连边。"""

    material = tuple(events)
    nodes: dict[str, GraphNode] = {}
    edges: dict[tuple[str, str, str, str], GraphEdge] = {}

    def add_node(node_id: str, node_type: str, status: str = "", details: Mapping[str, Any] | None = None) -> None:
        if node_id:
            nodes[node_id] = GraphNode(node_id, node_type, status, details or {})

    def add_edge(source: str, target: str, edge_type: str, event_id: str) -> None:
        if source and target:
            edge = GraphEdge(source, target, edge_type, event_id)
            edges[(source, target, edge_type, event_id)] = edge

    for event in material:
        for fact_id in event.fact_ids:
            add_node(fact_id, "missing_fact" if event.event_type == "MISSING_FACT_RECORDED" else "fact", event.after_status)
        if event.rule_id:
            add_node(event.rule_id, "rule", event.outcome)
        if event.claim_id:
            add_node(event.claim_id, "claim", event.outcome)
        for source_id in event.source_ids:
            add_node(source_id, "source", "verified")
            if event.rule_id:
                add_edge(source_id, event.rule_id, "provenance", event.event_id)
            for fact_id in event.fact_ids:
                add_edge(source_id, fact_id, "provenance", event.event_id)
        if event.event_type == "RULE_FIRED":
            for premise in event.premise_ids:
                add_node(premise, "fact")
                add_edge(premise, event.rule_id, "premise", event.event_id)
            add_edge(event.rule_id, event.claim_id, "support", event.event_id)
        elif event.event_type == "ATTACK_ADDED":
            source = str(event.details["source_claim_id"])
            target = str(event.details["target_claim_id"])
            add_node(source, "claim")
            add_node(target, "claim")
            add_edge(source, target, "attack", event.event_id)
        elif event.event_type == "EXCEPTION_APPLIED":
            exception = str(event.details["exception_rule_id"])
            add_node(exception, "rule")
            add_edge(exception, event.rule_id, "exception", event.event_id)
        elif event.event_type == "PRIORITY_RESOLVED":
            source = str(event.details["source_claim_id"])
            target = str(event.details["target_claim_id"])
            add_node(source, "claim")
            add_node(target, "claim")
            add_edge(source, target, "priority", event.event_id)
        elif event.event_type == "PERMISSION_EVALUATED":
            add_edge(event.rule_id, event.claim_id, "permission", event.event_id)
        elif event.event_type == "RULE_BLOCKED" and event.claim_id:
            add_edge(event.rule_id, event.claim_id, "prohibition", event.event_id)
        elif event.event_type == "TAINT_PROPAGATED":
            add_edge(event.rule_id or event.claim_id, event.claim_id, "taint", event.event_id)
        elif event.event_type == "BRANCH_CREATED":
            branch_id = event.outcome
            add_node(branch_id, "branch", "created")

    checker_events = tuple(event for event in material if event.event_type in {"CHECKER_STARTED", "CHECKER_VERDICT"})
    if checker_events:
        checker_id = f"checker::{result.run_id}"
        add_node(checker_id, "checker", "accepted" if result.checker_accepted else "review")
        for claim_id in result.claims:
            add_node(claim_id, "claim", result.result_status.value)
            add_edge(checker_id, claim_id, "checker_validation", _last_event_id(material, "CHECKER_VERDICT"))
    if result.certificate_kind != CertificateKind.NONE:
        certificate_id = f"certificate::{result.result_digest[:16]}"
        add_node(certificate_id, "certificate", result.certificate_kind.value)
        for claim_id in result.claims:
            add_edge(claim_id, certificate_id, "support", _last_event_id(material, "RESULT_FINALIZED"))
    for branch in result.branches:
        add_node(branch.branch_id, "branch", branch.result_status.value)
        for claim_id in branch.claims:
            add_node(claim_id, "claim", branch.result_status.value)
            add_edge(branch.branch_id, claim_id, "branch_of", _last_event_id(material, "BRANCH_CREATED"))
    missing_event_ids = {
        fact_id: event.event_id
        for event in material
        if event.event_type == "MISSING_FACT_RECORDED"
        for fact_id in event.fact_ids
    }
    for review in result.missing_fact_review:
        add_node(review.fact_id, "missing_fact", review.reason)
        event_id = missing_event_ids.get(review.fact_id, "")
        for rule_id in review.impacted_rule_ids:
            add_node(rule_id, "rule", "blocked_by_missing_fact")
            add_edge(review.fact_id, rule_id, "missing_premise", event_id)
        for claim_id in review.impacted_claim_ids:
            add_node(claim_id, "claim", "potential_only")
            for rule_id in review.impacted_rule_ids:
                add_edge(rule_id, claim_id, "potential_conclusion", event_id)

    ordered_nodes = tuple(sorted(nodes.values(), key=lambda item: (item.node_type, item.node_id)))
    ordered_edges = tuple(sorted(edges.values(), key=lambda item: (item.edge_type, item.source, item.target, item.event_id)))
    summary = {
        "node_count": len(ordered_nodes),
        "edge_count": len(ordered_edges),
        "event_count": len(material),
    }
    projection = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "run_id": result.run_id,
        "result_digest": result.result_digest,
        "summary": summary,
        "nodes": [node.to_dict() for node in ordered_nodes],
        "edges": [edge.to_dict() for edge in ordered_edges],
    }
    return GraphDocument(
        run_id=result.run_id,
        result_digest=result.result_digest,
        graph_digest=semantic_digest(projection),
        nodes=ordered_nodes,
        edges=ordered_edges,
        summary=MappingProxyType(summary),
    )


def audit_schema_document() -> dict[str, Any]:
    """返回AuditEvent与GraphDocument的公共JSON Schema片段。"""

    event_types = sorted(_DETAIL_FIELDS)
    detail_defs = {
        f"{event_type}Details": _detail_schema(event_type)
        for event_type in event_types
    }
    return {
        "$defs": {
            **detail_defs,
            "AuditEvent": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "schema_version", "event_id", "run_id", "seq", "event_type", "parent_event_ids",
                    "fact_ids", "premise_ids", "rule_id", "claim_id", "before_status", "after_status",
                    "source_ids", "taint", "outcome", "details",
                ],
                "properties": {
                    "schema_version": {"const": AUDIT_SCHEMA_VERSION},
                    "event_id": {"type": "string"},
                    "run_id": {"type": "string"},
                    "seq": {"type": "integer", "minimum": 1},
                    "event_type": {"type": "string", "enum": event_types},
                    "parent_event_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "fact_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "premise_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "rule_id": {"type": "string"},
                    "claim_id": {"type": "string"},
                    "before_status": {"type": "string"},
                    "after_status": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "taint": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                    "outcome": {"type": "string"},
                    "details": {
                        "oneOf": [
                            {"$ref": f"#/$defs/{event_type}Details"}
                            for event_type in event_types
                        ]
                    },
                },
            },
            "GraphDocument": {
                "type": "object",
                "additionalProperties": False,
                "required": ["schema_version", "run_id", "result_digest", "graph_digest", "summary", "nodes", "edges"],
                "properties": {
                    "schema_version": {"const": GRAPH_SCHEMA_VERSION},
                    "run_id": {"type": "string"},
                    "result_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "graph_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "summary": {"$ref": "#/$defs/GraphSummary"},
                    "nodes": {"type": "array", "items": {"$ref": "#/$defs/GraphNode"}},
                    "edges": {"type": "array", "items": {"$ref": "#/$defs/GraphEdge"}},
                },
            },
            "GraphSummary": {
                "type": "object",
                "additionalProperties": False,
                "required": ["node_count", "edge_count", "event_count"],
                "properties": {
                    "node_count": {"type": "integer", "minimum": 0},
                    "edge_count": {"type": "integer", "minimum": 0},
                    "event_count": {"type": "integer", "minimum": 0},
                },
            },
            "GraphNode": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "type", "status", "details"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "type": {
                        "type": "string",
                        "enum": ["fact", "rule", "claim", "source", "missing_fact", "checker", "certificate", "branch"],
                    },
                    "status": {"type": "string"},
                    "details": {"type": "object"},
                },
            },
            "GraphEdge": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source", "target", "type", "event_id"],
                "properties": {
                    "source": {"type": "string", "minLength": 1},
                    "target": {"type": "string", "minLength": 1},
                    "type": {
                        "type": "string",
                        "enum": [
                            "premise", "support", "attack", "exception", "priority", "permission",
                            "prohibition", "provenance", "taint", "checker_validation", "branch_of",
                            "missing_premise", "potential_conclusion",
                        ],
                    },
                    "event_id": {"type": "string"},
                },
            },
        }
    }


def _safe_detail_value(value: Any) -> Any:
    """限制details为标量或标量序列，并阻断路径/超长文本。"""

    if isinstance(value, (list, tuple, set)):
        return tuple(_safe_detail_value(item) for item in value)
    if not isinstance(value, (str, int, float, bool)) and value is not None:
        raise AuditValidationError(f"unsupported detail value: {type(value).__name__}")
    if isinstance(value, str):
        if len(value) > MAX_DETAIL_TEXT:
            raise AuditValidationError("audit detail text exceeds limit")
        if _ABSOLUTE_PATH_RE.search(value):
            raise AuditValidationError("absolute path forbidden in audit detail")
    return value


def _detail_schema(event_type: str) -> dict[str, Any]:
    """为每类事件生成独立、无额外字段的details schema。"""

    properties: dict[str, Any] = {}
    for field_name in sorted(_DETAIL_FIELDS[event_type]):
        if field_name in {"accepted", "admitted"}:
            properties[field_name] = {"type": "boolean"}
        elif field_name in {"candidate_rule_count", "branch_index"}:
            properties[field_name] = {"type": "integer", "minimum": 0}
        elif field_name == "confidence":
            properties[field_name] = {"type": "number"}
        elif field_name == "violations" or field_name.endswith("_ids") or field_name == "allowed_answer_types":
            properties[field_name] = {
                "type": "array",
                "items": {"type": "string", "maxLength": MAX_DETAIL_TEXT},
                "uniqueItems": True,
            }
        else:
            properties[field_name] = {"type": "string", "maxLength": MAX_DETAIL_TEXT}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(properties),
        "properties": properties,
    }


def _last_event_id(events: Iterable[AuditEvent], event_type: str) -> str:
    """返回指定类型最后一条事件ID。"""

    matched = [event.event_id for event in events if event.event_type == event_type]
    return matched[-1] if matched else ""
