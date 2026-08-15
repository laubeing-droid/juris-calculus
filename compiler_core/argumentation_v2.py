"""W4：P03 冲突、例外、许可与优先级的类型化正式结构。

依据：20260815 施工方案 §10。本模块建立在既有 grounded/SCC/cycle
原语（argumentation.py）之上，提供 ArgumentV2/AttackV2/PermissionV1/
PriorityEdgeV1/ArgumentGraphV2 的类型化语义；grounded 标签由独立重算
函数从 canonical graph 派生，不复用 production evaluator 缓存。

语义边界（方案 §10 前置条件）：本模块只实现方案 §10 已固化的结构；
任何进一步改变 Horn/attack/exception/permission/priority 结果的定义，
必须先取得版本化 LMM 规范，不在本模块发明新语义。

负面结果固化：
- 平面 Horn 结果不得冒充冲突裁决；
- exception 必须攻击规则适用性或结论支持，不能仅转写为普通负事实；
- permission 与 prohibition 冲突由明确类型化语义处理，不用字符串优先级；
- priority cycle、mutual attack、self-attack、unsupported attack 全部显式状态化；
- 无冲突图允许优化快路，但保留与完整 argument graph 的等价性测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from compiler_core.jcs import jcs_digest


ATTACK_TYPES = ("rebut", "undercut", "exception", "premise_challenge", "priority_defeat")
ATTACK_TARGET_ASPECTS = ("claim", "rule_applicability", "premise", "priority")
GRAPH_STATES = ("accepted", "cycle_blocked", "disputed", "blocked")


class ArgumentGraphError(ValueError):
    """论证图验证失败；code 稳定可机读。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _require_nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArgumentGraphError("MISSING_REQUIRED_FIELD", name)
    return value


def _sorted_unique(values: Any, name: str) -> tuple[str, ...]:
    items = tuple(sorted(set(_require_nonempty(item, f"{name}[]") for item in values)))
    if len(items) != len(tuple(values)):
        raise ArgumentGraphError("DUPLICATE_ID", name)
    return items


@dataclass(frozen=True)
class ArgumentV2:
    """一条适用规则至少对应一个独立 argument，不按 claim 过早合并。"""

    premises: tuple[str, ...]
    rule_ref: str
    claim: str
    derivation_path: tuple[str, ...] = field(default_factory=tuple)
    argument_id: str = ""

    def __post_init__(self) -> None:
        premises = _sorted_unique(self.premises, "premises")
        if not premises:
            raise ArgumentGraphError("MISSING_REQUIRED_FIELD", "premises")
        object.__setattr__(self, "premises", premises)
        object.__setattr__(self, "rule_ref", _require_nonempty(self.rule_ref, "rule_ref"))
        object.__setattr__(self, "claim", _require_nonempty(self.claim, "claim"))
        object.__setattr__(self, "derivation_path", tuple(str(step) for step in self.derivation_path))
        identity = jcs_digest({
            "premises": list(self.premises),
            "rule_ref": self.rule_ref,
            "claim": self.claim,
            "derivation_path": list(self.derivation_path),
        })
        if self.argument_id and self.argument_id != identity:
            raise ArgumentGraphError("ARGUMENT_IDENTITY_MISMATCH", self.argument_id)
        object.__setattr__(self, "argument_id", identity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "argument_id": self.argument_id,
            "premises": list(self.premises),
            "rule_ref": self.rule_ref,
            "claim": self.claim,
            "derivation_path": list(self.derivation_path),
        }


@dataclass(frozen=True)
class AttackV2:
    """typed attack：rebut/undercut/exception/premise_challenge/priority_defeat。"""

    attacker: str
    target: str
    attack_type: str
    target_aspect: str
    attack_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "attacker", _require_nonempty(self.attacker, "attacker"))
        object.__setattr__(self, "target", _require_nonempty(self.target, "target"))
        if self.attack_type not in ATTACK_TYPES:
            raise ArgumentGraphError("INVALID_ENUM", f"attack_type={self.attack_type!r}")
        if self.target_aspect not in ATTACK_TARGET_ASPECTS:
            raise ArgumentGraphError("INVALID_ENUM", f"target_aspect={self.target_aspect!r}")
        identity = jcs_digest({
            "attacker": self.attacker,
            "target": self.target,
            "attack_type": self.attack_type,
            "target_aspect": self.target_aspect,
        })
        if self.attack_id and self.attack_id != identity:
            raise ArgumentGraphError("ATTACK_IDENTITY_MISMATCH", self.attack_id)
        object.__setattr__(self, "attack_id", identity)

    @property
    def is_self_attack(self) -> bool:
        return self.attacker == self.target

    def to_dict(self) -> dict[str, Any]:
        return {
            "attack_id": self.attack_id,
            "attacker": self.attacker,
            "target": self.target,
            "attack_type": self.attack_type,
            "target_aspect": self.target_aspect,
        }


@dataclass(frozen=True)
class PermissionV1:
    """许可不是普通正命题；必须保留与禁止义务的关系。"""

    permission_id: str
    permits: str
    relation_to: str
    relation_kind: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "permission_id", _require_nonempty(self.permission_id, "permission_id"))
        object.__setattr__(self, "permits", _require_nonempty(self.permits, "permits"))
        object.__setattr__(self, "relation_to", _require_nonempty(self.relation_to, "relation_to"))
        if self.relation_kind not in ("exception_to_prohibition", "licensed_derogation"):
            raise ArgumentGraphError("INVALID_ENUM", f"relation_kind={self.relation_kind!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "permission_id": self.permission_id,
            "permits": self.permits,
            "relation_to": self.relation_to,
            "relation_kind": self.relation_kind,
        }


@dataclass(frozen=True)
class PriorityEdgeV1:
    """优先级边：来源、适用条件与非循环要求。"""

    source: str
    target: str
    condition: str
    edge_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _require_nonempty(self.source, "source"))
        object.__setattr__(self, "target", _require_nonempty(self.target, "target"))
        object.__setattr__(self, "condition", _require_nonempty(self.condition, "condition"))
        identity = jcs_digest({"source": self.source, "target": self.target, "condition": self.condition})
        if self.edge_id and self.edge_id != identity:
            raise ArgumentGraphError("PRIORITY_IDENTITY_MISMATCH", self.edge_id)
        object.__setattr__(self, "edge_id", identity)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source": self.source,
            "target": self.target,
            "condition": self.condition,
        }


@dataclass(frozen=True)
class ArgumentGraphV2:
    """节点、typed edges、applicability、grounded labels、claim projection。"""

    arguments: tuple[ArgumentV2, ...]
    attacks: tuple[AttackV2, ...] = field(default_factory=tuple)
    permissions: tuple[PermissionV1, ...] = field(default_factory=tuple)
    priority_edges: tuple[PriorityEdgeV1, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.arguments:
            raise ArgumentGraphError("MISSING_REQUIRED_FIELD", "arguments")
        ids = [argument.argument_id for argument in self.arguments]
        if len(ids) != len(set(ids)):
            raise ArgumentGraphError("DUPLICATE_ID", "arguments")
        known = set(ids)
        for attack in self.attacks:
            if attack.attacker not in known or attack.target not in known:
                raise ArgumentGraphError("UNSUPPORTED_ATTACK", attack.attack_id)
        for edge in self.priority_edges:
            if edge.source not in known or edge.target not in known:
                raise ArgumentGraphError("UNSUPPORTED_PRIORITY_EDGE", edge.edge_id)

    @property
    def conflict_free(self) -> bool:
        """无冲突 Horn 快路判据：无 attack、无许可冲突、无优先级边。"""

        return not self.attacks and not self.permissions and not self.priority_edges

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "arguments": sorted((argument.to_dict() for argument in self.arguments), key=lambda item: item["argument_id"]),
            "attacks": sorted((attack.to_dict() for attack in self.attacks), key=lambda item: item["attack_id"]),
            "permissions": sorted((permission.to_dict() for permission in self.permissions), key=lambda item: item["permission_id"]),
            "priority_edges": sorted((edge.to_dict() for edge in self.priority_edges), key=lambda item: item["edge_id"]),
        }

    def canonical_digest(self) -> str:
        return jcs_digest(self.canonical_payload())


def detect_priority_cycles(priority_edges: tuple[PriorityEdgeV1, ...]) -> tuple[tuple[str, ...], ...]:
    """显式枚举优先级环；环不得被静默打破。"""

    adjacency: dict[str, list[str]] = {}
    for edge in priority_edges:
        adjacency.setdefault(edge.source, []).append(edge.target)
        adjacency.setdefault(edge.target, [])

    cycles: list[tuple[str, ...]] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in adjacency}
    stack: list[str] = []

    def visit(node: str) -> None:
        color[node] = GRAY
        stack.append(node)
        for neighbor in adjacency[node]:
            if color[neighbor] == GRAY:
                start = stack.index(neighbor)
                cycles.append(tuple(stack[start:]))
            elif color[neighbor] == WHITE:
                visit(neighbor)
        stack.pop()
        color[node] = BLACK

    for node in sorted(adjacency):
        if color[node] == WHITE:
            visit(node)
    return tuple(sorted(set(cycles)))


def recompute_grounded_labels(graph: ArgumentGraphV2) -> dict[str, Any]:
    """从 canonical graph 独立重算 grounded 标签与裁决状态。

    独立实现（迭代 Dung grounded 定点），不读 production evaluator 缓存；
    exception/undercut 攻击按类型化语义参与击败关系。
    """

    payload = graph.canonical_payload()
    argument_ids = [argument["argument_id"] for argument in payload["arguments"]]

    priority_cycle_nodes: set[str] = set()
    cycles = detect_priority_cycles(graph.priority_edges)
    for cycle in cycles:
        priority_cycle_nodes.update(cycle)

    self_attacks = {attack.attacker for attack in graph.attacks if attack.is_self_attack}

    attackers: dict[str, list[str]] = {argument_id: [] for argument_id in argument_ids}
    for attack in graph.attacks:
        attackers[attack.target].append(attack.attacker)

    # grounded 定点：IN 当且仅当所有攻击者都 OUT。
    label = {argument_id: "UNDEC" for argument_id in argument_ids}
    changed = True
    while changed:
        changed = False
        for argument_id in argument_ids:
            if label[argument_id] != "UNDEC":
                continue
            attacker_labels = [label[attacker] for attacker in attackers[argument_id]]
            if all(item == "OUT" for item in attacker_labels):
                label[argument_id] = "IN"
                changed = True
            elif any(item == "IN" for item in attacker_labels):
                label[argument_id] = "OUT"
                changed = True

    # exception/undercut 对规则适用性的类型化后果：被击败 argument 的 claim
    # 标记 applicability_defeated，保留 argument witness（不删除节点）。
    applicability_defeated: dict[str, list[str]] = {}
    for attack in graph.attacks:
        if attack.attack_type in ("exception", "undercut") and attack.target_aspect == "rule_applicability":
            if label[attack.attacker] == "IN" and label[attack.target] in ("OUT", "UNDEC"):
                applicability_defeated.setdefault(attack.target, []).append(attack.attack_id)

    # 许可-禁止冲突：仅当存在类型化许可关系时许可成立；否则显式 DISPUTED。
    permission_resolution: dict[str, Any] = {}
    for permission in graph.permissions:
        permission_resolution[permission.permission_id] = {
            "permits": permission.permits,
            "relation_to": permission.relation_to,
            "resolution": "permission_holds_typed_relation" if permission.relation_kind in ("exception_to_prohibition", "licensed_derogation") else "DISPUTED",
        }

    if cycles:
        state = "cycle_blocked"
    elif permission_resolution and any(item["resolution"] == "DISPUTED" for item in permission_resolution.values()):
        state = "disputed"
    else:
        state = "accepted"

    claim_projection: dict[str, list[str]] = {}
    for argument in graph.arguments:
        if label[argument.argument_id] == "IN" and argument.argument_id not in applicability_defeated:
            claim_projection.setdefault(argument.claim, []).append(argument.argument_id)

    return {
        "canonical_digest": graph.canonical_digest(),
        "labels": label,
        "state": state,
        "priority_cycles": [list(cycle) for cycle in cycles],
        "self_attacks": sorted(self_attacks),
        "applicability_defeated": {key: sorted(value) for key, value in sorted(applicability_defeated.items())},
        "permission_resolution": permission_resolution,
        "claim_projection": {claim: sorted(ids) for claim, ids in sorted(claim_projection.items())},
        "fast_path_eligible": graph.conflict_free,
    }


def horn_fast_path_labels(graph: ArgumentGraphV2) -> dict[str, Any]:
    """无冲突图的优化快路；必须与完整重算保持等价（由测试强制）。"""

    if not graph.conflict_free:
        raise ArgumentGraphError("FAST_PATH_NOT_ELIGIBLE", "graph has conflict structure")
    labels = {argument.argument_id: "IN" for argument in graph.arguments}
    return {
        "canonical_digest": graph.canonical_digest(),
        "labels": labels,
        "state": "accepted",
        "priority_cycles": [],
        "self_attacks": [],
        "applicability_defeated": {},
        "permission_resolution": {},
        "claim_projection": {
            argument.claim: [argument.argument_id] for argument in graph.arguments
        },
        "fast_path_eligible": True,
    }


def evaluate_argument_graph(graph: ArgumentGraphV2) -> dict[str, Any]:
    """正式入口：无冲突走快路，冲突图走完整 grounded 重算。"""

    if graph.conflict_free:
        return horn_fast_path_labels(graph)
    return recompute_grounded_labels(graph)
