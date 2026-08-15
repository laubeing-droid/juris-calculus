"""W2：P02/P06/P08 来源、版本与路径消费门（SourceSnapshotV2 service）。

依据：20260815 施工方案 §8。本模块是 v2 source service 的正式实现，
收敛 `source_manifest.py`（锚点登记）与 `source_anchor.py`（locator/哈希）
的职责；旧模块在 v3 主链保持原状，v4 主链（W9 切换）只消费本模块。

负面结果固化（方案 §4）：
- 原始法源结构抽取先于 IR 选择；快照必须保留正文、层级、版本、定位和内容哈希；
- 同一标题不同文本必须产生不同 snapshot；标题匹配不代替内容哈希；
- 适用时点先于规则选择；无 decision time、有效期冲突或版本链断裂不得进入 formal evaluation；
- SourcePathV1 仅证明材料路径存在；检索分数只能保存在 candidate metadata；
- 原始材料不写入审计包；审计只保存受控 locator、hash、必要片段摘要和外部引用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
import unicodedata
from typing import Any, Mapping

from compiler_core.jcs import jcs_digest


_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_CANONICAL_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")

AUTHORITY_TIERS = ("official_first_party", "official_mirror", "third_party_verified", "unverified")
GATE_STATUSES = ("PASS", "FAIL", "BLOCKED", "DISPUTED")
PATH_PURPOSES = ("interpretation_chain", "evidence_chain", "provenance_chain")


class SourceGateError(ValueError):
    """来源门验证失败；code 稳定可机读。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GateOutcome:
    """三门统一输出；status 只能取 GATE_STATUSES。"""

    gate: str
    status: str
    reason: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in GATE_STATUSES:
            raise SourceGateError("INVALID_GATE_STATUS", self.status)
        if self.status in ("FAIL", "BLOCKED") and not self.reason:
            raise SourceGateError("MISSING_BLOCKED_REASON", self.gate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "status": self.status,
            "reason": self.reason,
            "details": dict(self.details),
        }


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise SourceGateError("INVALID_DIGEST", name)
    return value


def _require_canonical_time(value: Any, name: str, *, optional: bool = False) -> str:
    if optional and (value is None or value == ""):
        return ""
    if not isinstance(value, str) or not _CANONICAL_TIME_RE.match(value):
        raise SourceGateError("NONCANONICAL_TIME", f"{name}={value!r}")
    return value


def _require_nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceGateError("MISSING_REQUIRED_FIELD", name)
    return value


def compute_normalized_hash(raw_text: str, *, profile: str = "nfc-collapse-whitespace") -> str:
    """等价规范化必须可复算：NFC + 全 Unicode 空白折叠为单空格 + 首尾修剪。"""

    if profile != "nfc-collapse-whitespace":
        raise SourceGateError("UNKNOWN_NORMALIZATION_PROFILE", profile)
    normalized = unicodedata.normalize("NFC", raw_text)
    lines = []
    for line in normalized.splitlines():
        collapsed = re.sub(r"\s+", " ", line).strip()
        lines.append(collapsed)
    canonical = "\n".join(lines).strip()
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CanonicalLocator:
    """受控 locator；审计只保存它，不保存原始材料。"""

    kind: str
    value: str
    page: int | None = None
    span_start: int | None = None
    span_end: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _require_nonempty(self.kind, "locator.kind"))
        object.__setattr__(self, "value", _require_nonempty(self.value, "locator.value"))
        for name in ("page", "span_start", "span_end"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value < 0):
                raise SourceGateError("INVALID_LOCATOR", name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "page": self.page,
            "span_start": self.span_start,
            "span_end": self.span_end,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "CanonicalLocator":
        if not isinstance(payload, Mapping):
            raise SourceGateError("MISSING_REQUIRED_FIELD", "canonical_locator")
        allowed = {"kind", "value", "page", "span_start", "span_end"}
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise SourceGateError("UNKNOWN_FIELD", ", ".join(unknown))
        return cls(
            kind=payload.get("kind"),
            value=payload.get("value"),
            page=payload.get("page"),
            span_start=payload.get("span_start"),
            span_end=payload.get("span_end"),
        )


@dataclass(frozen=True)
class SourceSnapshotV2:
    """法源快照（方案 §8 最少字段集）。"""

    source_id: str
    authority_tier: str
    issuer: str
    title: str
    publication_time: str
    effective_time: str
    revision_time: str
    retrieved_at: str
    canonical_locator: CanonicalLocator
    raw_hash: str
    normalized_hash: str
    structure_map_ref: str
    signature_receipt_ref: str
    expiry_time: str = ""
    supersedes: str = ""
    superseded_by: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _require_nonempty(self.source_id, "source_id"))
        if self.authority_tier not in AUTHORITY_TIERS:
            raise SourceGateError("INVALID_AUTHORITY_TIER", self.authority_tier)
        object.__setattr__(self, "issuer", _require_nonempty(self.issuer, "issuer"))
        object.__setattr__(self, "title", _require_nonempty(self.title, "title"))
        for name in ("publication_time", "effective_time", "revision_time", "retrieved_at"):
            object.__setattr__(self, name, _require_canonical_time(getattr(self, name), name))
        object.__setattr__(self, "expiry_time", _require_canonical_time(self.expiry_time, "expiry_time", optional=True))
        object.__setattr__(self, "raw_hash", _require_sha256(self.raw_hash, "raw_hash"))
        object.__setattr__(self, "normalized_hash", _require_sha256(self.normalized_hash, "normalized_hash"))
        object.__setattr__(self, "structure_map_ref", _require_nonempty(self.structure_map_ref, "structure_map_ref"))
        object.__setattr__(self, "signature_receipt_ref", _require_nonempty(self.signature_receipt_ref, "signature_receipt_ref"))
        if not isinstance(self.canonical_locator, CanonicalLocator):
            object.__setattr__(self, "canonical_locator", CanonicalLocator.from_dict(self.canonical_locator))

    @property
    def snapshot_identity(self) -> str:
        """内容寻址身份：同一标题不同文本必须产生不同 identity。"""

        return jcs_digest({
            "title": self.title,
            "raw_hash": self.raw_hash,
            "revision_time": self.revision_time,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "authority_tier": self.authority_tier,
            "issuer": self.issuer,
            "title": self.title,
            "publication_time": self.publication_time,
            "effective_time": self.effective_time,
            "expiry_time": self.expiry_time,
            "revision_time": self.revision_time,
            "retrieved_at": self.retrieved_at,
            "canonical_locator": self.canonical_locator.to_dict(),
            "raw_hash": self.raw_hash,
            "normalized_hash": self.normalized_hash,
            "structure_map_ref": self.structure_map_ref,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "signature_receipt_ref": self.signature_receipt_ref,
            "snapshot_identity": self.snapshot_identity,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SourceSnapshotV2":
        if not isinstance(payload, Mapping):
            raise SourceGateError("MISSING_REQUIRED_FIELD", "snapshot")
        allowed = {
            "source_id", "authority_tier", "issuer", "title",
            "publication_time", "effective_time", "expiry_time", "revision_time",
            "retrieved_at", "canonical_locator", "raw_hash", "normalized_hash",
            "structure_map_ref", "supersedes", "superseded_by", "signature_receipt_ref",
        }
        unknown = sorted(set(payload) - allowed)
        if unknown:
            raise SourceGateError("UNKNOWN_FIELD", ", ".join(unknown))
        required = allowed - {"expiry_time", "supersedes", "superseded_by"}
        missing = sorted(required - set(payload))
        if missing:
            raise SourceGateError("MISSING_REQUIRED_FIELD", ", ".join(missing))
        return cls(
            source_id=payload["source_id"],
            authority_tier=payload["authority_tier"],
            issuer=payload["issuer"],
            title=payload["title"],
            publication_time=payload["publication_time"],
            effective_time=payload["effective_time"],
            expiry_time=payload.get("expiry_time") or "",
            revision_time=payload["revision_time"],
            retrieved_at=payload["retrieved_at"],
            canonical_locator=payload["canonical_locator"],
            raw_hash=payload["raw_hash"],
            normalized_hash=payload["normalized_hash"],
            structure_map_ref=payload["structure_map_ref"],
            supersedes=str(payload.get("supersedes") or ""),
            superseded_by=str(payload.get("superseded_by") or ""),
            signature_receipt_ref=payload["signature_receipt_ref"],
        )


@dataclass(frozen=True)
class EvidenceManifestV1:
    """证据清单（方案 §8 最少字段集）。"""

    evidence_id: str
    document_hash: str
    locators: tuple[CanonicalLocator, ...]
    custody_provenance: str
    fact_candidate_refs: tuple[str, ...]
    contradiction_refs: tuple[str, ...]
    redaction_state: str
    review_state: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", _require_nonempty(self.evidence_id, "evidence_id"))
        object.__setattr__(self, "document_hash", _require_sha256(self.document_hash, "document_hash"))
        object.__setattr__(self, "custody_provenance", _require_nonempty(self.custody_provenance, "custody_provenance"))
        if self.redaction_state not in ("none", "redacted", "partial"):
            raise SourceGateError("INVALID_ENUM", f"redaction_state={self.redaction_state!r}")
        if self.review_state not in ("unreviewed", "in_review", "reviewed", "disputed"):
            raise SourceGateError("INVALID_ENUM", f"review_state={self.review_state!r}")
        locators = tuple(
            locator if isinstance(locator, CanonicalLocator) else CanonicalLocator.from_dict(locator)
            for locator in self.locators
        )
        if not locators:
            raise SourceGateError("MISSING_REQUIRED_FIELD", "locators")
        object.__setattr__(self, "locators", locators)
        object.__setattr__(self, "fact_candidate_refs", tuple(sorted(set(map(str, self.fact_candidate_refs)))))
        object.__setattr__(self, "contradiction_refs", tuple(sorted(set(map(str, self.contradiction_refs)))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "document_hash": self.document_hash,
            "locators": [locator.to_dict() for locator in self.locators],
            "custody_provenance": self.custody_provenance,
            "fact_candidate_refs": list(self.fact_candidate_refs),
            "contradiction_refs": list(self.contradiction_refs),
            "redaction_state": self.redaction_state,
            "review_state": self.review_state,
        }


@dataclass(frozen=True)
class SourcePathEdgeV1:
    """路径边：关系类型、两端哈希、locator 与检索收据。"""

    edge_id: str
    source: str
    target: str
    relation: str
    source_hash: str
    target_hash: str
    locator: str
    retrieval_receipt_ref: str

    def __post_init__(self) -> None:
        for name in ("edge_id", "source", "target", "relation", "locator", "retrieval_receipt_ref"):
            object.__setattr__(self, name, _require_nonempty(getattr(self, name), f"edge.{name}"))
        object.__setattr__(self, "source_hash", _require_sha256(self.source_hash, "edge.source_hash"))
        object.__setattr__(self, "target_hash", _require_sha256(self.target_hash, "edge.target_hash"))


@dataclass(frozen=True)
class SourcePathNodeV1:
    node_id: str
    kind: str
    hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _require_nonempty(self.node_id, "node.node_id"))
        object.__setattr__(self, "kind", _require_nonempty(self.kind, "node.kind"))
        object.__setattr__(self, "hash", _require_sha256(self.hash, "node.hash"))


@dataclass(frozen=True)
class SourcePathV1:
    """有向材料路径；仅证明路径存在，不证明法律适用性。"""

    path_id: str
    purpose: str
    nodes: tuple[SourcePathNodeV1, ...]
    edges: tuple[SourcePathEdgeV1, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "path_id", _require_nonempty(self.path_id, "path_id"))
        if self.purpose not in PATH_PURPOSES:
            raise SourceGateError("INVALID_ENUM", f"purpose={self.purpose!r}")
        if not self.nodes or not self.edges:
            raise SourceGateError("MISSING_REQUIRED_FIELD", "nodes/edges")
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise SourceGateError("DUPLICATE_ID", "nodes")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise SourceGateError("UNKNOWN_FIELD", f"edge {edge.edge_id} references unknown node")

    def integrity_outcome(self) -> GateOutcome:
        """断链与环检查；检索分数不允许出现在路径内部。"""

        node_hash = {node.node_id: node.hash for node in self.nodes}
        for edge in self.edges:
            if node_hash[edge.source] != edge.source_hash or node_hash[edge.target] != edge.target_hash:
                return GateOutcome(
                    gate="source_path",
                    status="FAIL",
                    reason="broken_link_hash_mismatch",
                    details={"edge_id": edge.edge_id},
                )
        adjacency: dict[str, list[str]] = {node.node_id: [] for node in self.nodes}
        for edge in self.edges:
            adjacency[edge.source].append(edge.target)
        if _has_cycle(adjacency):
            return GateOutcome(gate="source_path", status="BLOCKED", reason="cycle_detected")
        return GateOutcome(gate="source_path", status="PASS")


def _has_cycle(adjacency: Mapping[str, list[str]]) -> bool:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node: WHITE for node in adjacency}

    def visit(node: str) -> bool:
        color[node] = GRAY
        for neighbor in adjacency[node]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and visit(neighbor):
                return True
        color[node] = BLACK
        return False

    return any(color[node] == WHITE and visit(node) for node in adjacency)


def reject_retrieval_score(payload: Mapping[str, Any], scope: str) -> None:
    """检索分数只能保存在 candidate metadata，不得进入路径/快照。"""

    for key, value in payload.items():
        if key in ("retrieval_score", "score", "rank_score"):
            raise SourceGateError("RETRIEVAL_SCORE_IN_PATH", f"{scope}.{key}")
        if isinstance(value, Mapping):
            reject_retrieval_score(value, f"{scope}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                if isinstance(item, Mapping):
                    reject_retrieval_score(item, f"{scope}.{key}[{index}]")


class SourceServiceV2:
    """快照登记、来源门、适用时点门与版本链检查。"""

    def __init__(self) -> None:
        self._snapshots: dict[str, SourceSnapshotV2] = {}
        self._terminal_bindings: dict[str, dict[str, str]] = {}

    def register(self, snapshot: SourceSnapshotV2) -> None:
        existing = self._snapshots.get(snapshot.source_id)
        if existing is not None and existing.raw_hash != snapshot.raw_hash:
            # 同一 source_id 换文本必须走 supersedes 版本链，不允许原地替换。
            raise SourceGateError("CONTENT_HASH_DIVERGENCE", snapshot.source_id)
        self._snapshots[snapshot.source_id] = snapshot

    def get(self, source_id: str) -> SourceSnapshotV2 | None:
        return self._snapshots.get(source_id)

    def source_gate(self, snapshot: SourceSnapshotV2) -> GateOutcome:
        """来源身份、完整性、版本和 locator 门。"""

        missing = [
            name for name in ("raw_hash", "normalized_hash", "signature_receipt_ref", "structure_map_ref")
            if not getattr(snapshot, name)
        ]
        if missing:
            return GateOutcome("source_gate", "BLOCKED", "hash_locator_version_missing", {"missing": missing})
        if snapshot.authority_tier == "unverified":
            return GateOutcome("source_gate", "BLOCKED", "authority_tier_unverified")
        if snapshot.supersedes and self.get(snapshot.supersedes) is None:
            return GateOutcome(
                "source_gate", "BLOCKED", "version_chain_broken",
                {"supersedes": snapshot.supersedes},
            )
        return GateOutcome("source_gate", "PASS")

    def applicability_gate(self, snapshot: SourceSnapshotV2, decision_time: str | None) -> GateOutcome:
        """适用时点先于规则选择；缺失或冲突不得进入 formal evaluation。"""

        if not decision_time:
            return GateOutcome("temporal_applicability", "BLOCKED", "decision_time_missing_or_version_chain_broken")
        if not _CANONICAL_TIME_RE.match(decision_time):
            return GateOutcome("temporal_applicability", "BLOCKED", "decision_time_missing_or_version_chain_broken")
        if snapshot.supersedes and self.get(snapshot.supersedes) is None:
            return GateOutcome("temporal_applicability", "BLOCKED", "decision_time_missing_or_version_chain_broken")
        if decision_time < snapshot.effective_time:
            return GateOutcome(
                "temporal_applicability", "FAIL", "rule_not_effective_at_decision_time",
                {"effective_time": snapshot.effective_time, "decision_time": decision_time},
            )
        if snapshot.expiry_time and decision_time >= snapshot.expiry_time:
            return GateOutcome(
                "temporal_applicability", "FAIL", "rule_not_effective_at_decision_time",
                {"expiry_time": snapshot.expiry_time, "decision_time": decision_time},
            )
        return GateOutcome("temporal_applicability", "PASS")

    def path_gate(self, path: SourcePathV1) -> GateOutcome:
        """路径完整性 + 最后一跳仍须通过 source authority gate。"""

        integrity = path.integrity_outcome()
        if integrity.status != "PASS":
            return integrity
        terminal_node = path.edges[-1].target
        # 最后一跳的 authority 检查要求路径终端绑定已登记快照；未绑定即 BLOCKED。
        snapshot = self._terminal_snapshot(path)
        if snapshot is None:
            return GateOutcome(
                "source_path", "BLOCKED", "terminal_source_unregistered",
                {"node_id": terminal_node},
            )
        authority = self.source_gate(snapshot)
        if authority.status != "PASS":
            return GateOutcome(
                "source_path", authority.status, authority.reason,
                {"terminal_node": terminal_node, **dict(authority.details)},
            )
        return GateOutcome("source_path", "PASS", details={"terminal_node": terminal_node})

    def bind_terminal(self, path_id: str, node_id: str, source_id: str) -> None:
        """把路径终端节点绑定到已登记快照（最后一跳 authority 检查的输入）。"""

        self._terminal_bindings.setdefault(path_id, {})[node_id] = source_id

    def _terminal_snapshot(self, path: SourcePathV1) -> SourceSnapshotV2 | None:
        source_id = self._terminal_bindings.get(path.path_id, {}).get(path.edges[-1].target)
        if source_id is None:
            return None
        return self.get(source_id)
