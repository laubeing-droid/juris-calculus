"""由审计事件派生的Graph JSON关系、排序和无伪因果门禁。"""

from __future__ import annotations

from compiler_core.application import evaluate_case
from compiler_core.audit import AuditRecorder, build_reasoning_graph
from compiler_core.canonical_serialization import content_id
from compiler_core.types import FactTrustStatus, LegalRule
from tests.unit.test_application_service import _fact, _manifest, _pack, _request, _rule


def _run(rules: tuple[LegalRule, ...], pack_ids: tuple[str, ...]):
    """执行一案并返回语义结果、事件和graph。"""

    request = _request(_fact())
    recorder = AuditRecorder(content_id("run", request.to_dict()))
    result = evaluate_case(
        request,
        _pack(*pack_ids),
        rules,
        source_manifest=_manifest(),
        audit_sink=recorder,
    )
    return result, recorder, build_reasoning_graph(result, recorder.events)


def test_formal_graph_has_fact_rule_claim_source_checker_and_certificate_paths() -> None:
    """正式claim不得孤立，必须存在premise/support/provenance/checker路径。"""

    result, recorder, graph = _run((_rule(),), ("R1",))
    node_types = {node.node_type for node in graph.nodes}
    edge_types = {edge.edge_type for edge in graph.edges}

    assert graph.run_id == result.run_id
    assert graph.result_digest == result.result_digest
    assert len(graph.graph_digest) == 64
    assert {"fact", "rule", "claim", "source", "checker", "certificate"} <= node_types
    assert {"premise", "support", "provenance", "checker_validation"} <= edge_types
    assert any(edge.source == "R1" and edge.target == "claim::result" for edge in graph.edges)
    assert graph.summary == {
        "node_count": len(graph.nodes),
        "edge_count": len(graph.edges),
        "event_count": len(recorder.events),
    }


def test_priority_graph_contains_both_attack_and_priority_edges() -> None:
    """priority不是attack的文本别名，两种关系都必须显式存在。"""

    winner = LegalRule(
        id="WINNER",
        premise_atoms=["fact::trigger"],
        head_claim="claim::winner",
        priority_over=["claim::loser"],
        source_anchor="source::law",
    )
    loser = LegalRule(
        id="LOSER",
        premise_atoms=["fact::trigger"],
        head_claim="claim::loser",
        source_anchor="source::law",
    )
    _, _, graph = _run((winner, loser), ("WINNER", "LOSER"))

    relations = {(edge.source, edge.target, edge.edge_type) for edge in graph.edges}
    assert ("claim::winner", "claim::loser", "attack") in relations
    assert ("claim::winner", "claim::loser", "priority") in relations


def test_exception_graph_uses_explicit_rule_relation() -> None:
    """例外边来自EXCEPTION_APPLIED事件，不来自事件相邻顺序。"""

    general = LegalRule(
        id="GENERAL",
        premise_atoms=["fact::trigger"],
        head_claim="claim::general",
        exception_chain=["EXCEPTION"],
        source_anchor="source::law",
    )
    exception = LegalRule(
        id="EXCEPTION",
        premise_atoms=["fact::trigger"],
        head_claim="claim::exception",
        source_anchor="source::law",
    )
    _, _, graph = _run((general, exception), ("GENERAL", "EXCEPTION"))

    assert any(
        edge.source == "EXCEPTION" and edge.target == "GENERAL" and edge.edge_type == "exception"
        for edge in graph.edges
    )


def test_graph_is_deterministic_across_rule_input_order() -> None:
    """规则输入顺序不得改变事件语义排序或Graph JSON。"""

    first = LegalRule(
        id="A",
        premise_atoms=["fact::trigger"],
        head_claim="claim::a",
        source_anchor="source::law",
    )
    second = LegalRule(
        id="B",
        premise_atoms=["fact::trigger"],
        head_claim="claim::b",
        source_anchor="source::law",
    )
    _, _, graph_one = _run((first, second), ("A", "B"))
    _, _, graph_two = _run((second, first), ("A", "B"))

    assert graph_one.to_dict() == graph_two.to_dict()


def test_review_graph_exposes_permission_prohibition_and_taint_edges() -> None:
    """review原因必须作为机器边出现，不能只在文本风险标签中。"""

    permission = LegalRule(
        id="PERMISSION",
        premise_atoms=["fact::trigger"],
        head_claim="claim::permission",
        norm_modality="PERMISSION",
        source_anchor="source::law",
    )
    prohibition = LegalRule(
        id="PROHIBITION",
        premise_atoms=["fact::trigger"],
        head_claim="claim::blocked",
        norm_modality="PROHIBITION",
        source_anchor="source::law",
    )
    tainted = LegalRule(
        id="TAINTED",
        premise_atoms=["fact::trigger"],
        head_claim="claim::tainted",
        concepts=["unregistered::concept"],
        mechanical_exception=False,
        source_anchor="source::law",
    )
    _, _, graph = _run(
        (permission, prohibition, tainted),
        ("PERMISSION", "PROHIBITION", "TAINTED"),
    )

    edge_types = {edge.edge_type for edge in graph.edges}
    assert {"permission", "prohibition", "taint"} <= edge_types


def test_missing_fact_graph_has_no_fabricated_checker_node() -> None:
    """checker未运行时Graph不得因固定模板创建checker。"""

    request = _request(_fact(FactTrustStatus.UNKNOWN))
    recorder = AuditRecorder(content_id("run", request.to_dict()))
    result = evaluate_case(
        request,
        _pack(),
        (_rule(),),
        source_manifest=_manifest(),
        audit_sink=recorder,
    )
    graph = build_reasoning_graph(result, recorder.events)

    assert any(node.node_type == "missing_fact" for node in graph.nodes)
    assert all(node.node_type != "checker" for node in graph.nodes)


def test_disputed_graph_has_stable_branch_nodes_and_edges() -> None:
    """分支节点和branch_of边来自显式BRANCH_CREATED/result branches。"""

    request = _request(_fact(
        FactTrustStatus.DISPUTED,
        alternatives=({"value": False}, {"value": True}),
    ))
    recorder = AuditRecorder(content_id("run", request.to_dict()))
    result = evaluate_case(
        request,
        _pack(),
        (_rule(),),
        source_manifest=_manifest(),
        audit_sink=recorder,
    )
    graph = build_reasoning_graph(result, recorder.events)

    assert len([node for node in graph.nodes if node.node_type == "branch"]) == 2
    assert any(edge.edge_type == "branch_of" for edge in graph.edges)
