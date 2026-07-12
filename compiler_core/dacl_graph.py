"""Typed DACL directed graph overlay: duties, authorizations, claims, liabilities."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class DACLNodeType(str, Enum):
    ACTOR = "Actor"
    DUTY = "Duty"
    CLAIM = "Claim"
    LIABILITY = "Liability"
    DEFENSE = "Defense"
    AUTHORITY = "Authority"
    EVIDENCE = "Evidence"
    FACT = "Fact"
    RULE = "Rule"
    CANDIDATE = "Candidate"


class DACLEdgeType(str, Enum):
    SUPPORTS = "supports"
    REBUTS = "rebuts"
    ATTACKS = "attacks"
    EXCEPTS = "excepts"
    AUTHORIZES = "authorizes"
    IMPOSES = "imposes"
    DISCHARGES = "discharges"
    DEPENDS_ON = "depends_on"
    SOURCE_ANCHORED_BY = "source_anchored_by"
    DERIVES_FROM = "derives_from"


_SOURCE_ANCHORABLE = {DACLNodeType.RULE, DACLNodeType.DUTY, DACLNodeType.CLAIM, DACLNodeType.EVIDENCE}


@dataclass
class DACLNode:
    node_id: str
    node_type: DACLNodeType
    label: str = ""
    source_anchor: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DACLEdge:
    source_id: str
    target_id: str
    edge_type: DACLEdgeType
    label: str = ""


@dataclass
class DACLGraph:
    nodes: Dict[str, DACLNode] = field(default_factory=dict)
    edges: List[DACLEdge] = field(default_factory=list)

    def add_node(self, node_id: str, node_type: DACLNodeType, label: str = "", source_anchor: str = "", metadata: Dict[str, Any] | None = None) -> DACLNode:
        if node_id in self.nodes:
            return self.nodes[node_id]
        node = DACLNode(node_id=node_id, node_type=node_type, label=label, source_anchor=source_anchor, metadata=metadata or {})
        self.nodes[node_id] = node
        return node

    def add_edge(self, source_id: str, target_id: str, edge_type: DACLEdgeType, label: str = "") -> DACLEdge:
        self.add_node(source_id, DACLNodeType.FACT)
        self.add_node(target_id, DACLNodeType.FACT)
        edge = DACLEdge(source_id=source_id, target_id=target_id, edge_type=edge_type, label=label)
        self.edges.append(edge)
        return edge

    def audit(self) -> Dict[str, Any]:
        findings: List[Dict[str, Any]] = []
        node_ids = set(self.nodes)
        edge_targets = {edge.target_id for edge in self.edges}
        edge_sources = {edge.source_id for edge in self.edges}
        for edge in self.edges:
            if edge.source_id not in node_ids:
                findings.append({"edge": f"{edge.source_id}-->[{edge.edge_type}]-->{edge.target_id}", "issue": "SOURCE_NODE_MISSING"})
            if edge.target_id not in node_ids:
                findings.append({"edge": f"{edge.source_id}-->[{edge.edge_type}]-->{edge.target_id}", "issue": "TARGET_NODE_MISSING"})
        for node_id, node in self.nodes.items():
            if node.node_type in _SOURCE_ANCHORABLE and not (node.source_anchor or "").strip():
                findings.append({"node": node_id, "type": node.node_type.value, "issue": "SOURCE_ANCHOR_MISSING"})
            if node_id not in edge_targets and node_id not in edge_sources:
                findings.append({"node": node_id, "type": node.node_type.value, "issue": "ORPHAN_NODE"})
        for node_id, node in self.nodes.items():
            if node.node_type == DACLNodeType.CANDIDATE and node.metadata.get("promotion") == "FINAL_AUTOMATED":
                findings.append({"node": node_id, "issue": "FINAL_AUTOMATED_PROMOTION_FORBIDDEN"})
        blocking = [f for f in findings if "MISSING" in f.get("issue", "") or "FINAL_" in f.get("issue", "")]
        return {
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
            "finding_count": len(findings),
            "blocking_count": len(blocking),
            "status": "PASS" if not blocking else "FAIL",
            "findings": findings,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": {nid: {"type": node.node_type.value, "label": node.label, "source_anchor": node.source_anchor} for nid, node in self.nodes.items()},
            "edges": [{"source": edge.source_id, "target": edge.target_id, "type": edge.edge_type.value, "label": edge.label} for edge in self.edges],
        }


def build_dacl_graph(rules: List[Any], claims: List[Any] | None = None, facts: List[Any] | None = None, traces: List[Any] | None = None) -> DACLGraph:
    graph = DACLGraph()
    head_anchor_map: Dict[str, str] = {}
    for rule in rules:
        label = getattr(rule, "head_claim", "") or str(rule)
        anchor = getattr(rule, "source_anchor", "") or ""
        node = graph.add_node(f"Rule_{rule.id}", DACLNodeType.RULE, label=label, source_anchor=anchor)
        if label and anchor and anchor != "UNANCHORED":
            head_anchor_map[label] = anchor
        for premise in getattr(rule, "premise_atoms", []) or []:
            fact_node = graph.add_node(f"Fact_{premise}", DACLNodeType.FACT, label=premise)
            graph.add_edge(node.node_id, fact_node.node_id, DACLEdgeType.DEPENDS_ON)
        for exc in getattr(rule, "exception_chain", []) or []:
            exc_node = graph.add_node(f"Defense_{exc}", DACLNodeType.DEFENSE, label=exc)
            graph.add_edge(exc_node.node_id, node.node_id, DACLEdgeType.EXCEPTS)
            anchor_node = graph.add_node(f"Evidence_{rule.id}", DACLNodeType.EVIDENCE, label=node.source_anchor, source_anchor=node.source_anchor)
            graph.add_edge(node.node_id, anchor_node.node_id, DACLEdgeType.SOURCE_ANCHORED_BY)
    for rule in rules:
        rule_node_id = f"Rule_{rule.id}"
        for atk in getattr(rule, "attacks", []) or []:
            claim_anchor = head_anchor_map.get(atk, "") if isinstance(atk, str) else ""
            atk_node = graph.add_node(f"Claim_{atk}", DACLNodeType.CLAIM, label=atk, source_anchor=claim_anchor)
            graph.add_edge(atk_node.node_id, rule_node_id, DACLEdgeType.ATTACKS)
    for rule in rules:
        rule_node_id = f"Rule_{rule.id}"
        for prio in getattr(rule, "priority_over", []) or []:
            prio_node = graph.add_node(f"Rule_{prio}", DACLNodeType.RULE, label=prio)
            graph.add_edge(rule_node_id, prio_node.node_id, DACLEdgeType.ATTACKS)
    if claims:
        for claim in claims:
            claim_id = getattr(claim, "id", "") or str(claim)
            claim_node = graph.add_node(f"Claim_{claim_id}", DACLNodeType.CLAIM, label=getattr(claim, "description", "") or "")
            for node in getattr(claim, "proof_trace", []) or []:
                if isinstance(node, dict):
                    rule_id = node.get("rule_id", "")
                    if rule_id and f"Rule_{rule_id}" in graph.nodes:
                        graph.add_edge(f"Claim_{claim_id}", f"Rule_{rule_id}", DACLEdgeType.DERIVES_FROM)
    if facts:
        for fact in facts:
            fact_id = getattr(fact, "id", "") or str(fact)
            fact_node = graph.add_node(f"Fact_{fact_id}", DACLNodeType.FACT, label=getattr(fact, "description", "") or "")
            source = getattr(fact, "source_anchor", "") or ""
            if source:
                src_node = graph.add_node(f"Evidence_{fact_id}", DACLNodeType.EVIDENCE, label=source, source_anchor=source)
                graph.add_edge(fact_node.node_id, src_node.node_id, DACLEdgeType.SOURCE_ANCHORED_BY)
    if traces:
        for trace_item in traces:
            if isinstance(trace_item, dict):
                for role in ("rule_id", "claim_id", "premise"):
                    target_id = trace_item.get(role, "")
                    base = f"{role.capitalize()}_{target_id}" if role == "premise" else f"{role.capitalize()}_{target_id}"
                    existing = base if base in graph.nodes else (f"Rule_{target_id}" if role == "rule_id" else f"Claim_{target_id}" if role == "claim_id" else f"Fact_{target_id}")
                    if existing and existing in graph.nodes:
                        pass
    return graph


