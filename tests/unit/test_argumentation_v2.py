"""W4：P03 类型化论证语义测试。

用例语义与 tests/fixtures/theory_absorption/p03 对齐；
差分 oracle 为既有独立实现 compiler_core.argumentation.grounded_extension。
"""

from __future__ import annotations

import pytest

from compiler_core.argumentation import grounded_extension
from compiler_core.argumentation_v2 import (
    ArgumentGraphError,
    ArgumentGraphV2,
    ArgumentV2,
    AttackV2,
    PermissionV1,
    PriorityEdgeV1,
    detect_priority_cycles,
    evaluate_argument_graph,
    horn_fast_path_labels,
    recompute_grounded_labels,
)


def _argument(claim: str, premises=("fact_A",), rule_ref="rule-1@1.0") -> ArgumentV2:
    return ArgumentV2(premises=premises, rule_ref=rule_ref, claim=claim)


def _exception_graph() -> ArgumentGraphV2:
    arg1 = _argument("obligation_X", premises=("fact_A",), rule_ref="rule-1@1.0")
    arg2 = _argument("exception_to_rule_1", premises=("fact_B",), rule_ref="rule-2@1.0")
    attack = AttackV2(
        attacker=arg2.argument_id,
        target=arg1.argument_id,
        attack_type="exception",
        target_aspect="rule_applicability",
    )
    return ArgumentGraphV2(arguments=(arg1, arg2), attacks=(attack,))


class TestIdentity:
    def test_argument_identity_content_addressed(self):
        first = _argument("claim_C")
        second = _argument("claim_C")
        assert first.argument_id == second.argument_id
        third = _argument("claim_D")
        assert first.argument_id != third.argument_id

    def test_argument_identity_mismatch_rejected(self):
        with pytest.raises(ArgumentGraphError) as exc:
            ArgumentV2(premises=("fact_A",), rule_ref="r@1", claim="c", argument_id="forged")
        assert exc.value.code == "ARGUMENT_IDENTITY_MISMATCH"

    def test_unsupported_attack_rejected_at_construction(self):
        arg = _argument("claim_C")
        with pytest.raises(ArgumentGraphError) as exc:
            ArgumentGraphV2(
                arguments=(arg,),
                attacks=(AttackV2(attacker=arg.argument_id, target="ghost", attack_type="rebut", target_aspect="claim"),),
            )
        assert exc.value.code == "UNSUPPORTED_ATTACK"


class TestExceptionSemantics:
    def test_exception_defeats_rule_applicability_with_witness(self):
        graph = _exception_graph()
        result = recompute_grounded_labels(graph)
        arg1, arg2 = graph.arguments
        assert result["labels"][arg2.argument_id] == "IN"
        assert result["labels"][arg1.argument_id] == "OUT"
        assert arg1.argument_id in result["applicability_defeated"]
        # witness 保留：节点未被删除，攻击 id 被记录
        assert result["applicability_defeated"][arg1.argument_id]
        assert arg1.claim not in result["claim_projection"]

    def test_exception_not_plain_negative_fact(self):
        """exception 必须通过 typed attack 生效，不能作为普通负事实进入前提。"""

        graph = _exception_graph()
        attack = graph.attacks[0]
        assert attack.attack_type == "exception"
        assert attack.target_aspect == "rule_applicability"

    def test_mutation_removing_attack_changes_labels(self):
        graph = _exception_graph()
        mutated = ArgumentGraphV2(arguments=graph.arguments, attacks=())
        before = recompute_grounded_labels(graph)["labels"]
        after = recompute_grounded_labels(mutated)["labels"]
        arg1 = graph.arguments[0]
        assert before[arg1.argument_id] == "OUT"
        assert after[arg1.argument_id] == "IN"


class TestCyclesAndSelfAttack:
    def test_priority_cycle_explicit_state(self):
        args = tuple(_argument(f"claim_{index}", rule_ref=f"rule-{index}@1.0") for index in range(3))
        edges = (
            PriorityEdgeV1(source=args[0].argument_id, target=args[1].argument_id, condition="lex_superior"),
            PriorityEdgeV1(source=args[1].argument_id, target=args[2].argument_id, condition="lex_superior"),
            PriorityEdgeV1(source=args[2].argument_id, target=args[0].argument_id, condition="lex_superior"),
        )
        graph = ArgumentGraphV2(arguments=args, priority_edges=edges)
        cycles = detect_priority_cycles(edges)
        assert cycles and len(cycles[0]) == 3
        result = recompute_grounded_labels(graph)
        assert result["state"] == "cycle_blocked"
        assert result["priority_cycles"]

    def test_mutual_attack_stays_undecided(self):
        arg1 = _argument("claim_A")
        arg2 = _argument("claim_B")
        attacks = (
            AttackV2(attacker=arg1.argument_id, target=arg2.argument_id, attack_type="rebut", target_aspect="claim"),
            AttackV2(attacker=arg2.argument_id, target=arg1.argument_id, attack_type="rebut", target_aspect="claim"),
        )
        graph = ArgumentGraphV2(arguments=(arg1, arg2), attacks=attacks)
        result = recompute_grounded_labels(graph)
        assert result["labels"][arg1.argument_id] == "UNDEC"
        assert result["labels"][arg2.argument_id] == "UNDEC"
        assert not result["claim_projection"]

    def test_self_attack_recorded_explicitly(self):
        arg = _argument("claim_A")
        attack = AttackV2(attacker=arg.argument_id, target=arg.argument_id, attack_type="rebut", target_aspect="claim")
        graph = ArgumentGraphV2(arguments=(arg,), attacks=(attack,))
        result = recompute_grounded_labels(graph)
        assert result["self_attacks"] == [arg.argument_id]
        assert result["labels"][arg.argument_id] == "UNDEC"


class TestPermissionSemantics:
    def test_permission_requires_typed_relation(self):
        with pytest.raises(ArgumentGraphError) as exc:
            PermissionV1(permission_id="perm-x", permits="action_Y", relation_to="prohibition_Z", relation_kind="string_order")
        assert exc.value.code == "INVALID_ENUM"

    def test_permission_resolution_independent_of_identifier_order(self):
        """许可-禁止冲突不得用字符串优先级解决：id 互换不影响裁决。"""

        perm_a = PermissionV1("perm-1", "action_Y", "prohibition_Z", "exception_to_prohibition")
        perm_b = PermissionV1("perm-2", "action_Y", "prohibition_A", "exception_to_prohibition")
        arg = _argument("claim_A")
        graph_a = ArgumentGraphV2(arguments=(arg,), permissions=(perm_a, perm_b))
        graph_b = ArgumentGraphV2(arguments=(arg,), permissions=(perm_b, perm_a))
        assert (
            recompute_grounded_labels(graph_a)["permission_resolution"]
            == recompute_grounded_labels(graph_b)["permission_resolution"]
        )


class TestFastPathAndOracle:
    def test_conflict_free_fast_path_equivalence(self):
        arg = _argument("conclusion_C")
        graph = ArgumentGraphV2(arguments=(arg,))
        assert graph.conflict_free
        fast = horn_fast_path_labels(graph)
        full = recompute_grounded_labels(graph)
        assert fast["labels"] == full["labels"]
        assert fast["claim_projection"] == full["claim_projection"]
        assert evaluate_argument_graph(graph)["fast_path_eligible"] is True

    def test_fast_path_refused_for_conflict_graph(self):
        with pytest.raises(ArgumentGraphError) as exc:
            horn_fast_path_labels(_exception_graph())
        assert exc.value.code == "FAST_PATH_NOT_ELIGIBLE"

    def test_independent_oracle_alignment(self):
        """v2 重算必须与既有独立 grounded 实现一致（差分 oracle）。"""

        graph = _exception_graph()
        arg1 = _argument("extra_claim", premises=("fact_C",), rule_ref="rule-3@1.0")
        graph = ArgumentGraphV2(arguments=(*graph.arguments, arg1), attacks=graph.attacks)
        v2_labels = recompute_grounded_labels(graph)["labels"]
        oracle = grounded_extension(
            [{"id": argument.argument_id} for argument in graph.arguments],
            [(attack.attacker, attack.target) for attack in graph.attacks],
        )
        assert set(oracle["accepted"]) == {key for key, value in v2_labels.items() if value == "IN"}
        assert set(oracle["rejected"]) == {key for key, value in v2_labels.items() if value == "OUT"}
        assert set(oracle["undecided"]) == {key for key, value in v2_labels.items() if value == "UNDEC"}
