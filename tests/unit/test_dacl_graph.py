#!/usr/bin/env python3
from __future__ import annotations

from compiler_core.dacl_graph import DACLEdgeType, DACLGraph, DACLNodeType, build_dacl_graph
from compiler_core.types import LegalRule


def test_empty_graph_audit_passes():
    graph = DACLGraph()
    report = graph.audit()
    assert report["status"] == "PASS"
    assert report["finding_count"] == 0


def test_orphan_node_is_reported():
    graph = DACLGraph()
    graph.add_node("orphan", DACLNodeType.CLAIM)
    report = graph.audit()
    assert any(f["issue"] == "ORPHAN_NODE" for f in report["findings"])


def test_unanchored_rule_is_reported():
    graph = DACLGraph()
    graph.add_node("unbound_rule", DACLNodeType.RULE, label="no anchor")
    report = graph.audit()
    assert any(f["issue"] == "SOURCE_ANCHOR_MISSING" for f in report["findings"])


def test_anchored_rule_is_clean():
    graph = DACLGraph()
    graph.add_node("bound_rule", DACLNodeType.RULE, label="anchored", source_anchor="statute:42")
    report = graph.audit()
    assert all(f["issue"] != "SOURCE_ANCHOR_MISSING" for f in report["findings"])


def test_final_automated_candidate_without_source_is_blocked():
    graph = DACLGraph()
    graph.add_node("auto_bad", DACLNodeType.CANDIDATE, label="bad promotion", metadata={"promotion": "FINAL_AUTOMATED"})
    report = graph.audit()
    assert any("FINAL_AUTOMATED_WITHOUT" in f["issue"] for f in report["findings"])


def test_final_automated_candidate_with_source_via_derives_from_passes():
    graph = DACLGraph()
    graph.add_node("evidence", DACLNodeType.EVIDENCE, source_anchor="statute:42")
    graph.add_node("cand", DACLNodeType.CANDIDATE, metadata={"promotion": "FINAL_AUTOMATED"})
    graph.add_edge("evidence", "cand", DACLEdgeType.DERIVES_FROM)
    report = graph.audit()
    assert not any("FINAL_AUTOMATED_WITHOUT" in f["issue"] for f in report["findings"])


def test_build_dacl_graph_from_rules():
    rules = [
        LegalRule(
            id="R1", premise_atoms=["payment_due"], head_claim="Breach_Established",
            exception_chain=["R2"], attacks=["Breach_Established"], priority_over=["R3"],
            source_anchor="statute:42",
        ),
        LegalRule(id="R2", premise_atoms=["payment_excused"], head_claim="Defense_Available", source_anchor="statute:43"),
        LegalRule(id="R3", premise_atoms=["no_contract"], head_claim="No_Breach", source_anchor="statute:44"),
    ]
    graph = build_dacl_graph(rules)
    assert graph.nodes["Rule_R1"].node_type == DACLNodeType.RULE
    assert any(edge.edge_type == DACLEdgeType.EXCEPTS for edge in graph.edges)
    assert any(edge.edge_type == DACLEdgeType.ATTACKS for edge in graph.edges)
    assert any(edge.edge_type == DACLEdgeType.SOURCE_ANCHORED_BY for edge in graph.edges)
    report = graph.audit()
    assert report["status"] == "PASS"
